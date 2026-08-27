import subprocess
import json
import os
import cv2
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor
import asyncio

from temporalio import activity

from common.schemas import CurationInput, CurationOutput, KeyframeManifest, FrameQuality, GpsFix, StageInput, StageOutput
from common.object_store import object_exists, get_json, download_to, upload_from, put_json, sha256_file, key_from_uri
from common.idempotency import stage_input_hash, short_id
from common.config import settings

CURATION_CONFIG_VERSION = "v1"

TARGET_FPS = 2.0
WINDOW_S = 1.0 / TARGET_FPS
BLUR_MIN = 120.0
ENTROPY_MIN_BITS = 4.0
CLIP_FRAC_MAX = 0.15
DUPLICATE_OVERLAP_MAX = 0.90
MAX_PLAUSIBLE_SPEED_MPS = 30.0
TILE_GRID = (4, 4)

def compute_set_id(mission_id: str, segment_hashes: list[str], config_version: str) -> tuple[str, str]:
    full = stage_input_hash(mission_id, *segment_hashes, config_version)
    return full, short_id(full)

def gop_boundaries(local_path: Path) -> list[float]:
    """Timestamps (s) of I-frames, used to shard decode work across processes."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "frame=pict_type,pts_time", "-of", "json", str(local_path)],
        capture_output=True, text=True, check=True,
    )
    frames = json.loads(out.stdout).get("frames", [])
    return [float(f["pts_time"]) for f in frames if f.get("pict_type") == "I"]

def laplacian_blur_score(gray: np.ndarray) -> float:
    h, w = gray.shape
    th, tw = h // TILE_GRID[0], w // TILE_GRID[1]
    scores = []
    for i in range(TILE_GRID[0]):
        for j in range(TILE_GRID[1]):
            tile = gray[i * th:(i + 1) * th, j * tw:(j + 1) * tw]
            scores.append(cv2.Laplacian(tile, cv2.CV_64F).var())
    return float(np.median(scores))

def exposure_score(bgr: np.ndarray) -> tuple[float, float, float]:
    v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2]
    hist = cv2.calcHist([v], [0], None, [256], [0, 256]).flatten()
    p = hist / hist.sum()
    p_nonzero = p[p > 0]
    entropy = float(-np.sum(p_nonzero * np.log2(p_nonzero))) if len(p_nonzero) > 0 else 0.0
    clip_low = float(hist[:5].sum() / hist.sum())
    clip_high = float(hist[-5:].sum() / hist.sum())
    return entropy, clip_low, clip_high

def get_orb():
    if not hasattr(get_orb, "orb"):
        get_orb.orb = cv2.ORB_create(nfeatures=500)
    return get_orb.orb

def overlap_ratio(prev_gray: np.ndarray, cur_gray: np.ndarray) -> float:
    orb = get_orb()
    kp1, des1 = orb.detectAndCompute(prev_gray, None)
    kp2, des2 = orb.detectAndCompute(cur_gray, None)
    if des1 is None or des2 is None or len(des1) < 10:
        return 0.0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    good = [m for m in matches if m.distance < 40]
    return len(good) / max(len(kp1), 1)

def gps_jump_flag(prev_fix: GpsFix, cur_fix: GpsFix, dt_s: float) -> bool:
    if prev_fix is None or cur_fix is None or dt_s <= 0:
        return False
    R = 6371000.0
    dlat, dlon = radians(cur_fix.lat - prev_fix.lat), radians(cur_fix.lon - prev_fix.lon)
    a = sin(dlat/2)**2 + cos(radians(prev_fix.lat)) * cos(radians(cur_fix.lat)) * sin(dlon/2)**2
    dist = 2 * R * atan2(sqrt(a), sqrt(1 - a))
    return (dist / dt_s) > MAX_PLAUSIBLE_SPEED_MPS

def select_keyframes(scored: list[FrameQuality]) -> list[FrameQuality]:
    scored.sort(key=lambda f: f.timestamp_utc)
    kept, window_start, best = [], None, None
    for f in scored:
        t = f.timestamp_utc.timestamp()
        if window_start is None or t - window_start >= WINDOW_S:
            if best is not None:
                kept.append(best)
            window_start, best = t, f
        elif f.quality_score > (best.quality_score if best else -1):
            best = f
    if best is not None:
        kept.append(best)
    return kept

def get_clahe():
    if not hasattr(get_clahe, "clahe"):
        get_clahe.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return get_clahe.clahe

def normalize_for_matching(bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = get_clahe().apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

def normalize_val(val, vmin, vmax):
    return max(0.0, min(1.0, (val - vmin) / (vmax - vmin))) if vmax > vmin else 1.0

def curate_segment_shard(local_mp4: Path, start_s: float, end_s: float, segment_name: str, set_id: str) -> list[FrameQuality]:
    cap = cv2.VideoCapture(str(local_mp4))
    cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000)
    
    results = []
    prev_gray, prev_ts = None, None
    frame_idx = 0

    while True:
        pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
        if pos_msec / 1000.0 >= end_s:
            break
            
        ok, frame = cap.read()
        if not ok:
            break
            
        ts = pos_msec / 1000.0
        
        # Downscale to 1080p if larger, for blur scoring consistency
        h, w = frame.shape[:2]
        if w > 1920:
            scale = 1920 / w
            scoring_frame = cv2.resize(frame, (1920, int(h * scale)))
        else:
            scoring_frame = frame
            
        gray = cv2.cvtColor(scoring_frame, cv2.COLOR_BGR2GRAY)
        
        blur = laplacian_blur_score(gray)
        entropy, clip_lo, clip_hi = exposure_score(scoring_frame)
        dup = overlap_ratio(prev_gray, gray) if prev_gray is not None else 0.0
        
        status = "kept"
        if blur < BLUR_MIN:
            status = "dropped_blur"
        elif entropy < ENTROPY_MIN_BITS or (clip_lo + clip_hi) > CLIP_FRAC_MAX:
            status = "dropped_exposure"
        elif dup > DUPLICATE_OVERLAP_MAX:
            status = "dropped_duplicate"
            
        n_blur = normalize_val(blur, BLUR_MIN, 1000.0)  # 1000 is an empirical upper bound
        n_ent = normalize_val(entropy, ENTROPY_MIN_BITS, 8.0)
        quality_score = 0.5 * n_blur + 0.3 * n_ent + 0.2 * (1.0 - (clip_lo + clip_hi))

        timestamp_utc = datetime.fromtimestamp(ts, tz=timezone.utc)

        fq = FrameQuality(
            frame_id="",
            source_segment=segment_name,
            source_frame_index=frame_idx,
            timestamp_utc=timestamp_utc,
            object_key="",
            width=w,
            height=h,
            sha256="",
            laplacian_variance=blur,
            exposure_entropy_bits=entropy,
            exposure_clip_low_frac=clip_lo,
            exposure_clip_high_frac=clip_hi,
            quality_score=quality_score,
            gps=None,
            status=status
        )
        if status == "kept":
            norm_bgr = normalize_for_matching(frame)
            scratch_path = local_mp4.parent / f"{segment_name}_{frame_idx}.jpg"
            cv2.imwrite(str(scratch_path), norm_bgr)
            fq.sha256 = sha256_file(scratch_path)
            fq.object_key = str(scratch_path)  # scratch path carried forward until upload

            
        results.append(fq)
        
        prev_gray, prev_ts = gray, ts
        frame_idx += 1
        
    cap.release()
    return results

@activity.defn(name="ActivityCuration")
async def run_curation(payload: StageInput) -> StageOutput:
    out = await curate_keyframes(CurationInput(
        mission_id=payload.mission_id, run_id=payload.run_id,
        video_segment_keys=[key_from_uri(u) for u in payload.input_uris],
    ))
    return StageOutput(
        output_uri=out.manifest_uri, output_hash=out.set_id,
        metrics={"num_kept": float(out.num_kept), "num_dropped": float(out.num_dropped)},
    )


async def curate_keyframes(payload: CurationInput) -> CurationOutput:
    scratch = Path(settings.scratch_dir) / payload.run_id / "curation"
    scratch.mkdir(parents=True, exist_ok=True)

    loop = asyncio.get_running_loop()

    segment_hashes = []
    local_segments = []
    for key in payload.video_segment_keys:
        local = await loop.run_in_executor(
            None, lambda k=key: download_to(k, scratch / Path(k).name, bucket=settings.raw_bucket)
        )
        hash_val = await loop.run_in_executor(None, sha256_file, local)
        segment_hashes.append(hash_val)
        local_segments.append(local)
        activity.heartbeat(f"downloaded {key}")

    full_hash, set_id = compute_set_id(payload.mission_id, segment_hashes, CURATION_CONFIG_VERSION)
    manifest_key = f"missions/{payload.mission_id}/keyframes/{set_id}/manifest.json"

    exists = await loop.run_in_executor(None, object_exists, manifest_key)
    if exists:
        manifest_json = await loop.run_in_executor(None, get_json, manifest_key)
        manifest = KeyframeManifest.model_validate(manifest_json)
        return CurationOutput(
            mission_id=payload.mission_id, set_id=set_id,
            manifest_uri=f"s3://{settings.bucket}/{manifest_key}",
            num_kept=len(manifest.frames), num_dropped=manifest.stats.get("dropped_total", 0),
        )

    # Shard decode work
    all_scored = []
    
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        futures = []
        for local_mp4 in local_segments:
            segment_name = local_mp4.name
            try:
                boundaries = gop_boundaries(local_mp4)
            except subprocess.CalledProcessError:
                boundaries = []
                
            if not boundaries:
                # no I-frames from ffprobe treat whole file as one shard
                cap = cv2.VideoCapture(str(local_mp4))
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                end_s = (frame_count / fps) + 1.0 if fps > 0 else 3600.0
                cap.release()
                boundaries = [0.0, end_s]

            if boundaries[0] > 0.0:
                boundaries.insert(0, 0.0)

            for i in range(len(boundaries)):
                start_s = boundaries[i]
                end_s = boundaries[i+1] if i + 1 < len(boundaries) else 3600.0
                futures.append(loop.run_in_executor(
                    pool, curate_segment_shard, local_mp4, start_s, end_s, segment_name, set_id
                ))

        for fut in futures:
            shard_results = await fut
            all_scored.extend(shard_results)
            activity.heartbeat(f"processed a shard")

    all_scored.sort(key=lambda f: f.timestamp_utc)

    threshold_passed = [f for f in all_scored if f.status == "kept"]
    selected = select_keyframes(threshold_passed)

    selected_ids = {id(f) for f in selected}
    for f in all_scored:
        if f.status == "kept" and id(f) not in selected_ids:
            f.status = "dropped_window"
            if f.object_key and Path(f.object_key).exists():
                Path(f.object_key).unlink()

    stats = {"dropped_total": 0}
    kept_frames = []
    global_frame_idx = 0
    for f in all_scored:
        if f.status == "kept":
            frame_id = f"{global_frame_idx:06d}"
            f.frame_id = frame_id
            object_key = f"missions/{payload.mission_id}/keyframes/{set_id}/{frame_id}.jpg"

            temp_path = Path(f.object_key)
            await loop.run_in_executor(None, upload_from, temp_path, object_key)
            temp_path.unlink()

            f.object_key = object_key
            kept_frames.append(f)
            global_frame_idx += 1
        else:
            stats[f.status] = stats.get(f.status, 0) + 1
            stats["dropped_total"] += 1


    manifest = KeyframeManifest(
        mission_id=payload.mission_id, set_id=set_id, input_content_hash=full_hash,
        curation_config_version=CURATION_CONFIG_VERSION, generated_at=datetime.now(timezone.utc),
        frames=kept_frames, stats=stats,
    )
    
    manifest_uri = await loop.run_in_executor(None, put_json, manifest_key, manifest.model_dump(mode="json"))
    return CurationOutput(
        mission_id=payload.mission_id, set_id=set_id, manifest_uri=manifest_uri,
        num_kept=len(kept_frames), num_dropped=stats["dropped_total"],
    )

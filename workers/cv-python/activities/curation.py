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

TARGET_FPS = 5.0
WINDOW_S = 1.0 / TARGET_FPS
DUPLICATE_OVERLAP_MAX = 0.90
MAX_PLAUSIBLE_SPEED_MPS = 30.0
TILE_GRID = (4, 4)

# A fixed 5fps target quietly starves short/fast single-pass clips: e.g. a 16s clip
# decimates to ~30-40 keyframes, which is too sparse for incremental SfM to chain
# reliable overlap between consecutive keyframes (COLMAP stalls at 2-3 registered
# images and never grows). Single-pass footage has no redundant coverage to spare,
# so short clips need a *denser* time window, not the same one used for long corridors.
# We floor the total keyframe count instead of the fps, then derive the window from
# the actual candidate time span — long clips still land near TARGET_FPS.
MIN_TOTAL_KEYFRAMES_TARGET = 150

# COLMAP's incremental mapper can technically seed from 3 images (see min_model_size in
# sfm.py), but that floor is about triangulation math, not about there being enough distinct
# viewpoints for exhaustive matching to find a well-conditioned init pair. Below this count,
# "no good initial image pair found" is far more likely than a working reconstruction, so we
# fail here — in seconds, with the actual drop-reason breakdown — instead of after a full SfM
# attempt with a bare "0 registered frames".
MIN_KEYFRAMES_FOR_SFM = 20

# Quality gates are computed per-video (see `compute_adaptive_thresholds`) rather than as
# fixed constants: a hardcoded absolute blur/exposure bar tuned against one clip's sharpness
# and lighting silently rejects every frame of a differently-compressed or differently-lit
# video (e.g. a softer/portrait-mode clip) while doing nothing for a clip that's uniformly
# too dark to use. Each threshold is the tighter of (a) a percentile within *this* video's own
# distribution, so we always drop the video's own worst tail, and (b) an absolute sanity bound,
# so a uniformly-unusable video can't pass just because it's "the least bad version of itself".
QUALITY_PERCENTILE = 15  # drop roughly the worst 15% of candidate frames per video
MIN_SAMPLES_FOR_PERCENTILE = 20  # below this, percentile estimates are noisy; fall back to the absolute bound
ABS_BLUR_FLOOR = 15.0
ABS_ENTROPY_FLOOR_BITS = 2.0
ABS_CLIP_CEILING = 0.6

def compute_set_id(mission_id: str, segment_hashes: list[str], config_version: str) -> tuple[str, str]:
    full = stage_input_hash(mission_id, *segment_hashes, config_version)
    return full, short_id(full)

def describe_drop_reasons(stats: dict[str, int]) -> str:
    top_drop_reasons = sorted(
        ((k, v) for k, v in stats.items() if k != "dropped_total"),
        key=lambda kv: kv[1], reverse=True,
    )
    return ", ".join(f"{k}={v}" for k, v in top_drop_reasons) or "no candidate frames decoded"

def require_sufficient_keyframes(num_kept: int, stats: dict[str, int], mission_id: str, set_id: str, cached: bool = False):
    if num_kept == 0:
        source = " (cached manifest)" if cached else ""
        raise ValueError(
            f"curation kept 0/{stats.get('dropped_total', 0)} frames for mission {mission_id} "
            f"(set {set_id}){source} — every frame was dropped ({describe_drop_reasons(stats)}); "
            f"check source footage quality or curation thresholds before continuing the pipeline"
        )
    if num_kept < MIN_KEYFRAMES_FOR_SFM:
        source = " (cached manifest)" if cached else ""
        raise ValueError(
            f"curation kept only {num_kept} frame(s) for mission {mission_id} (set {set_id}){source} "
            f"— below the {MIN_KEYFRAMES_FOR_SFM}-frame floor needed for a reliable SfM init pair "
            f"(drop reasons: {describe_drop_reasons(stats)}); the source video is likely too short "
            f"or curation thresholds are dropping too much of it — check those before retrying SfM"
        )

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

def adaptive_window_s(scored: list[FrameQuality]) -> float:
    if len(scored) < 2:
        return WINDOW_S
    span_s = (scored[-1].timestamp_utc - scored[0].timestamp_utc).total_seconds()
    if span_s <= 0:
        return WINDOW_S
    return min(WINDOW_S, span_s / MIN_TOTAL_KEYFRAMES_TARGET)

def select_keyframes(scored: list[FrameQuality], window_s: float = WINDOW_S) -> list[FrameQuality]:
    scored.sort(key=lambda f: f.timestamp_utc)
    kept, window_start, best = [], None, None
    for f in scored:
        t = f.timestamp_utc.timestamp()
        if window_start is None or t - window_start >= window_s:
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

def compute_adaptive_thresholds(candidates: list[FrameQuality]) -> tuple[float, float, float]:
    """Blur floor / entropy floor / clip-fraction ceiling, tightened to this video's own
    distribution but clamped by an absolute sanity bound. Returns (blur_floor, entropy_floor, clip_ceiling)."""
    if len(candidates) < MIN_SAMPLES_FOR_PERCENTILE:
        return ABS_BLUR_FLOOR, ABS_ENTROPY_FLOOR_BITS, ABS_CLIP_CEILING

    blur_vals = [f.laplacian_variance for f in candidates]
    entropy_vals = [f.exposure_entropy_bits for f in candidates]
    clip_vals = [f.exposure_clip_low_frac + f.exposure_clip_high_frac for f in candidates]

    blur_floor = max(ABS_BLUR_FLOOR, float(np.percentile(blur_vals, QUALITY_PERCENTILE)))
    entropy_floor = max(ABS_ENTROPY_FLOOR_BITS, float(np.percentile(entropy_vals, QUALITY_PERCENTILE)))
    clip_ceiling = min(ABS_CLIP_CEILING, float(np.percentile(clip_vals, 100 - QUALITY_PERCENTILE)))
    return blur_floor, entropy_floor, clip_ceiling

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

        # Blur/exposure are decided later, once the whole video's distribution is known
        # (see compute_adaptive_thresholds) — a per-frame absolute cutoff can't tell a soft
        # video from a genuinely bad frame. Duplicate detection stays here: it's a purely
        # local, sequential decision that doesn't depend on the rest of the video.
        status = "dropped_duplicate" if dup > DUPLICATE_OVERLAP_MAX else "candidate"

        # Placeholder quality_score (needs the adaptive floors); recomputed once thresholds are known.
        quality_score = 0.0

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
        if status == "candidate":
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

async def _heartbeat_loop(interval_sec: float = 3.0):
    while True:
        try:
            await asyncio.sleep(interval_sec)
            activity.heartbeat("processing curation")
        except asyncio.CancelledError:
            break

@activity.defn(name="ActivityCuration")
async def run_curation(payload: StageInput) -> StageOutput:
    hb_task = asyncio.create_task(_heartbeat_loop())
    try:
        out = await curate_keyframes(CurationInput(
            mission_id=payload.mission_id, run_id=payload.run_id,
            video_segment_keys=[key_from_uri(u) for u in payload.input_uris],
        ))
        return StageOutput(
            output_uri=out.manifest_uri, output_hash=out.set_id,
            metrics={"num_kept": float(out.num_kept), "num_dropped": float(out.num_dropped)},
        )
    finally:
        hb_task.cancel()


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
        require_sufficient_keyframes(len(manifest.frames), manifest.stats, payload.mission_id, set_id, cached=True)
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

    candidates = [f for f in all_scored if f.status == "candidate"]
    blur_floor, entropy_floor, clip_ceiling = compute_adaptive_thresholds(candidates)
    activity.logger.info(
        "adaptive quality thresholds: blur_floor=%.1f entropy_floor=%.2f clip_ceiling=%.2f (n=%d)",
        blur_floor, entropy_floor, clip_ceiling, len(candidates),
    )
    for f in candidates:
        if f.laplacian_variance < blur_floor:
            f.status = "dropped_blur"
        elif f.exposure_entropy_bits < entropy_floor or (f.exposure_clip_low_frac + f.exposure_clip_high_frac) > clip_ceiling:
            f.status = "dropped_exposure"
        else:
            f.status = "kept"
            n_blur = normalize_val(f.laplacian_variance, blur_floor, max(1000.0, blur_floor * 3))
            n_ent = normalize_val(f.exposure_entropy_bits, entropy_floor, 8.0)
            f.quality_score = 0.5 * n_blur + 0.3 * n_ent + 0.2 * (1.0 - (f.exposure_clip_low_frac + f.exposure_clip_high_frac))

        if f.status != "kept" and f.object_key and Path(f.object_key).exists():
            try:
                Path(f.object_key).unlink()
            except Exception:
                pass

    threshold_passed = [f for f in all_scored if f.status == "kept"]
    window_s = adaptive_window_s(threshold_passed)
    activity.logger.info(
        "keyframe selection window=%.3fs (target_fps=%.1f, %d quality-passed frames)",
        window_s, 1.0 / window_s if window_s > 0 else float("inf"), len(threshold_passed),
    )
    selected = select_keyframes(threshold_passed, window_s)

    selected_keys = {f.object_key for f in selected if f.object_key}
    for f in all_scored:
        if f.status == "kept":
            if f.object_key not in selected_keys:
                f.status = "dropped_window"
                if f.object_key and Path(f.object_key).exists():
                    try:
                        Path(f.object_key).unlink()
                    except Exception:
                        pass

    stats = {"dropped_total": 0}
    kept_frames = []
    global_frame_idx = 0
    for f in all_scored:
        if f.status == "kept":
            temp_path = Path(f.object_key)
            if not temp_path.exists():
                f.status = "dropped_window"
                stats[f.status] = stats.get(f.status, 0) + 1
                stats["dropped_total"] += 1
                continue

            frame_id = f"{global_frame_idx:06d}"
            f.frame_id = frame_id
            object_key = f"missions/{payload.mission_id}/keyframes/{set_id}/{frame_id}.jpg"

            await loop.run_in_executor(None, upload_from, temp_path, object_key)
            try:
                temp_path.unlink()
            except Exception:
                pass

            f.object_key = object_key
            kept_frames.append(f)
            global_frame_idx += 1
        else:
            stats[f.status] = stats.get(f.status, 0) + 1
            stats["dropped_total"] += 1


    require_sufficient_keyframes(len(kept_frames), stats, payload.mission_id, set_id)

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

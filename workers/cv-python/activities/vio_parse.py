import json
import math
from datetime import datetime, timezone
from pathlib import Path
from pyproj import Transformer

from temporalio import activity

from common.schemas import VioParseInput, VioParseOutput, KeyframeManifest, PosePriorRecord, PriorsManifest, GpsFix
from common.object_store import object_exists, get_json, download_to, put_json, sha256_file, get_client
from common.idempotency import stage_input_hash, short_id
from common.config import settings

PPK_SIGMA_H_M, PPK_SIGMA_V_M = 0.05, 0.08
RTK_FIXED_SIGMA_H_M, RTK_FIXED_SIGMA_V_M = 0.03, 0.05
GNSS_ONLY_SIGMA_H_M, GNSS_ONLY_SIGMA_V_M = 1.5, 2.5
BARO_SIGMA_V_M = 0.2

def compute_attempt_id(mission_id: str, keyframe_manifest_hash: str, telemetry_hashes: list[str], config_version: str) -> tuple[str, str]:
    full = stage_input_hash(mission_id, keyframe_manifest_hash, *telemetry_hashes, config_version)
    return full, short_id(full)

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

def _bisect_by_time(times: list[datetime], ts: datetime) -> int | None:
    if not times or ts < times[0] or ts > times[-1]:
        return None
    import bisect
    idx = bisect.bisect_right(times, ts) - 1
    return idx if idx >= 0 and idx < len(times) - 1 else None

def nearest_or_interpolate(records: list[dict], ts: datetime, max_gap_s: float = 2.0) -> dict | None:
    times = [datetime.fromisoformat(r["t"]) for r in records]
    idx = _bisect_by_time(times, ts)
    if idx is None:
        return None
    before, after = records[idx], records[idx + 1]
    t0, t1 = times[idx], times[idx + 1]
    
    if (ts - t0).total_seconds() > max_gap_s and (after["t"] == before["t"] or (t1 - ts).total_seconds() > max_gap_s):
        return None
        
    delta_total = (t1 - t0).total_seconds()
    if delta_total == 0:
        return before
        
    frac = (ts - t0).total_seconds() / delta_total
    interpolated = {}
    for k in before:
        if isinstance(before[k], (int, float)):
            interpolated[k] = before[k] + frac * (after[k] - before[k])
        else:
            interpolated[k] = before[k]
    return interpolated

def build_fix(gps_rec, ppk_rec, baro_rec) -> GpsFix | None:
    if ppk_rec and ppk_rec.get("fix_quality") == "fixed":
        lat, lon, alt = ppk_rec["lat"], ppk_rec["lon"], ppk_rec["alt_ellipsoidal"]
        fix_type, sh, sv = "ppk", PPK_SIGMA_H_M, PPK_SIGMA_V_M
    elif gps_rec and gps_rec.get("rtk_status") == "fixed":
        lat, lon, alt = gps_rec["lat"], gps_rec["lon"], gps_rec["alt_ellipsoidal"]
        fix_type, sh, sv = "rtk_fixed", RTK_FIXED_SIGMA_H_M, RTK_FIXED_SIGMA_V_M
    elif gps_rec:
        lat, lon, alt = gps_rec["lat"], gps_rec["lon"], gps_rec["alt_ellipsoidal"]
        fix_type, sh, sv = "gnss_only", GNSS_ONLY_SIGMA_H_M, GNSS_ONLY_SIGMA_V_M
    else:
        return None

    if baro_rec and sv > BARO_SIGMA_V_M:
        alt = 0.7 * alt + 0.3 * baro_rec.get("alt_agl", 0.0) + baro_rec.get("ground_elevation_msl", 0.0)
        sv = BARO_SIGMA_V_M

    return GpsFix(lat=lat, lon=lon, alt_ellipsoidal_m=alt, fix_type=fix_type,
                  horizontal_sigma_m=sh, vertical_sigma_m=sv)

def make_transformers(origin_lla: tuple[float, float, float]):
    lat0, lon0, _ = origin_lla
    ecef = Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)
    enu = Transformer.from_crs(
        "EPSG:4979", f"+proj=topocentric +ellps=WGS84 +lat_0={lat0} +lon_0={lon0} +h_0=0",
        always_xy=True,
    )
    return ecef, enu

def to_ecef(t: Transformer, lat, lon, alt) -> tuple[float, float, float]:
    x, y, z = t.transform(lon, lat, alt)
    return x, y, z

def first_valid_fix_lla(keyframe_manifest: KeyframeManifest, gps_log, ppk_log) -> tuple[float, float, float]:
    for frame in keyframe_manifest.frames:
        g = nearest_or_interpolate(gps_log, frame.timestamp_utc)
        p = nearest_or_interpolate(ppk_log, frame.timestamp_utc)
        fix = build_fix(g, p, None)
        if fix:
            return (fix.lat, fix.lon, fix.alt_ellipsoidal_m)
    return (0.0, 0.0, 0.0)

def utm_epsg_for_lonlat(lon: float, lat: float) -> str:
    zone = math.floor((lon + 180) / 6) + 1
    hemisphere = 6 if lat >= 0 else 7
    return f"EPSG:32{hemisphere}{zone:02d}"

def build_priors_manifest(mission_id, attempt_id, full_hash, keyframe_manifest, gps_log, ppk_log, baro_log, target_epsg) -> PriorsManifest:
    origin = first_valid_fix_lla(keyframe_manifest, gps_log, ppk_log)
    ecef_t, enu_t = make_transformers(origin)
    priors = []
    for frame in keyframe_manifest.frames:
        gps_rec = nearest_or_interpolate(gps_log, frame.timestamp_utc)
        ppk_rec = nearest_or_interpolate(ppk_log, frame.timestamp_utc)
        baro_rec = nearest_or_interpolate(baro_log, frame.timestamp_utc)
        fix = build_fix(gps_rec, ppk_rec, baro_rec)
        if fix is None:
            continue
        enu = enu_t.transform(fix.lon, fix.lat, fix.alt_ellipsoidal_m)
        ecef = to_ecef(ecef_t, fix.lat, fix.lon, fix.alt_ellipsoidal_m)
        priors.append(PosePriorRecord(
            image_name=Path(frame.object_key).name,
            position_enu_m=enu, position_ecef_m=ecef,
            sigma_horizontal_m=fix.horizontal_sigma_m, sigma_vertical_m=fix.vertical_sigma_m,
            source=fix.fix_type, attitude_quat_wxyz=None,
        ))
    return PriorsManifest(
        mission_id=mission_id, attempt_id=attempt_id, input_content_hash=full_hash,
        reference_origin_lla=origin, target_epsg=target_epsg, priors=priors,
    )

def write_colmap_text_render(priors_manifest: PriorsManifest, intrinsics: dict) -> tuple[str, str]:
    cameras_txt = (
        f"# Camera list: CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS\n"
        f"1 PINHOLE {intrinsics['width']} {intrinsics['height']} "
        f"{intrinsics['fx']} {intrinsics['fy']} {intrinsics['cx']} {intrinsics['cy']}\n"
    )
    lines = ["# Image list with prior translations (rotation identity placeholder — SfM solves it)"]
    for i, p in enumerate(priors_manifest.priors, start=1):
        qw, qx, qy, qz = p.attitude_quat_wxyz or (1.0, 0.0, 0.0, 0.0)
        tx, ty, tz = p.position_enu_m
        lines.append(f"{i} {qw} {qx} {qy} {qz} {tx} {ty} {tz} 1 {p.image_name}")
        lines.append("")
    return cameras_txt, "\n".join(lines)

def _key_from_uri(uri: str) -> str:
    # "s3://recon-dev/missions/..." -> "missions/..."
    if uri.startswith("s3://"):
        parts = uri.split("/", 3)
        if len(parts) == 4:
            return parts[3]
    return uri

def safe_download(key: str, dest: Path) -> Path | None:
    try:
        return download_to(key, dest)
    except Exception:  # file may not exist (ppk/baro logs are optional)
        return None

def upload_text(key: str, content: str):
    client = get_client()
    client.put_object(Bucket=settings.bucket, Key=key, Body=content.encode("utf-8"))

@activity.defn(name="parse_vio_warm_start")
async def parse_vio_warm_start(payload: VioParseInput) -> VioParseOutput:
    scratch = Path(settings.scratch_dir) / payload.run_id / "vio_parse"
    scratch.mkdir(parents=True, exist_ok=True)
    
    manifest_key = _key_from_uri(payload.keyframe_manifest_uri)
    manifest = KeyframeManifest.model_validate(get_json(manifest_key))
    
    gps_path = safe_download(f"missions/{payload.mission_id}/raw/telemetry/gps.log", scratch / "gps.log")
    ppk_path = safe_download(f"missions/{payload.mission_id}/raw/telemetry/ppk.log", scratch / "ppk.log")
    baro_path = safe_download(f"missions/{payload.mission_id}/raw/telemetry/baro.log", scratch / "baro.log")
    
    gps_log = load_jsonl(gps_path) if gps_path else []
    ppk_log = load_jsonl(ppk_path) if ppk_path else []
    baro_log = load_jsonl(baro_path) if baro_path else []

    telemetry_hashes = []
    for p in (gps_path, ppk_path, baro_path):
        if p and p.exists():
            telemetry_hashes.append(sha256_file(p))
            
    full_hash, attempt_id = compute_attempt_id(payload.mission_id, manifest.input_content_hash, telemetry_hashes, "v1")
    priors_key = f"missions/{payload.mission_id}/poses/{attempt_id}/priors/pose_priors.json"

    if object_exists(priors_key):
        return VioParseOutput(mission_id=payload.mission_id, attempt_id=attempt_id,
                               priors_manifest_uri=f"s3://{settings.bucket}/{priors_key}")

    target_epsg = "EPSG:4978"
    for frame in manifest.frames:
        g = nearest_or_interpolate(gps_log, frame.timestamp_utc)
        p = nearest_or_interpolate(ppk_log, frame.timestamp_utc)
        fix = build_fix(g, p, None)
        if fix:
            target_epsg = utm_epsg_for_lonlat(fix.lon, fix.lat)
            break

    priors_manifest = build_priors_manifest(payload.mission_id, attempt_id, full_hash, manifest, gps_log, ppk_log, baro_log, target_epsg)
    uri = put_json(priors_key, priors_manifest.model_dump(mode="json"))

    # TODO(day-14): load intrinsics from flight_sessions API
    intrinsics = {
        "width": 3840, "height": 2160,
        "fx": 2000.0, "fy": 2000.0,
        "cx": 1920.0, "cy": 1080.0
    }
    cameras_txt, images_txt = write_colmap_text_render(priors_manifest, intrinsics)
    upload_text(f"missions/{payload.mission_id}/poses/{attempt_id}/priors/cameras.txt", cameras_txt)
    upload_text(f"missions/{payload.mission_id}/poses/{attempt_id}/priors/images.txt", images_txt)

    return VioParseOutput(mission_id=payload.mission_id, attempt_id=attempt_id, priors_manifest_uri=uri)

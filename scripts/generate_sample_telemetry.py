import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def generate_telemetry_files(
    out_dir: str | Path,
    duration_s: float = 66.5,
    start_lat: float = 50.2925,
    start_lon: float = 36.9388,
    alt_agl: float = 85.0,
    ground_elevation: float = 120.0,
    speed_mps: float = 12.0,
):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)
    gps_records = []
    ppk_records = []
    baro_records = []

    # 10 Hz sampling for GPS & Baro, 5 Hz for PPK
    n_steps = int(duration_s * 10)
    for i in range(n_steps):
        t_cur = start_time + timedelta(seconds=i * 0.1)
        t_iso = t_cur.isoformat()

        # drone moving North-East
        dist_m = speed_mps * (i * 0.1)
        d_lat = (dist_m * 0.7071) / 111139.0
        d_lon = (dist_m * 0.7071) / (111139.0 * 0.638)

        lat = start_lat + d_lat
        lon = start_lon + d_lon
        alt_ellipsoid = ground_elevation + alt_agl + (i * 0.01)

        gps_records.append({
            "t": t_iso,
            "lat": lat,
            "lon": lon,
            "alt_ellipsoidal": alt_ellipsoid,
            "rtk_status": "fixed" if i % 10 != 0 else "float",
        })

        if i % 2 == 0:
            ppk_records.append({
                "t": t_iso,
                "lat": lat,
                "lon": lon,
                "alt_ellipsoidal": alt_ellipsoid,
                "fix_quality": "fixed",
            })

        baro_records.append({
            "t": t_iso,
            "alt_agl": alt_agl + (i * 0.01),
            "ground_elevation_msl": ground_elevation,
        })

    with open(out_dir / "gps.log", "w") as f:
        for r in gps_records:
            f.write(json.dumps(r) + "\n")

    with open(out_dir / "ppk.log", "w") as f:
        for r in ppk_records:
            f.write(json.dumps(r) + "\n")

    with open(out_dir / "baro.log", "w") as f:
        for r in baro_records:
            f.write(json.dumps(r) + "\n")

    print(f"Generated telemetry in {out_dir}: {len(gps_records)} GPS, {len(ppk_records)} PPK, {len(baro_records)} Baro records")


if __name__ == "__main__":
    generate_telemetry_files("scripts/tests/testdata/vovchansk_telemetry")

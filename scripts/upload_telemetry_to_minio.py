import sys
from pathlib import Path
from minio import Minio

def upload_telemetry(mission_id: str, telem_dir: str):
    client = Minio(
        "localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False,
    )
    bucket = "recon-raw"
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    telem_path = Path(telem_dir)
    for fname in ["gps.log", "ppk.log", "baro.log"]:
        fpath = telem_path / fname
        if fpath.exists():
            key = f"missions/{mission_id}/raw/telemetry/{fname}"
            client.fput_object(bucket, key, str(fpath))
            print(f"Uploaded {fname} -> {bucket}/{key}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python upload_telemetry_to_minio.py <mission_id> <telem_dir>")
        sys.exit(1)
    upload_telemetry(sys.argv[1], sys.argv[2])

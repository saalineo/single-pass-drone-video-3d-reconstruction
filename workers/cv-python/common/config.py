import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    env: str = os.environ.get("CV_ENV", "dev")
    temporal_host: str = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace: str = os.environ.get("TEMPORAL_NAMESPACE", "recon")
    task_queue: str = os.environ.get("CV_TASK_QUEUE", "CV_TASK_QUEUE")
    minio_endpoint: str = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key: str = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    minio_secure: bool = os.environ.get("MINIO_SECURE", "false").lower() == "true"
    scratch_dir: str = os.environ.get("SCRATCH_DIR", "/scratch")
    # Raw video/telemetry lands in ingest-svc's and telemetry-worker's own bucket
    # (same env var they read, so one setting keeps all three services aligned) —
    # everything curation produces onward lives in `bucket` below.
    raw_bucket: str = os.environ.get("INGEST_RAW_BUCKET", "recon-raw")

    @property
    def bucket(self) -> str:
        return f"recon-{self.env}"


settings = Settings()

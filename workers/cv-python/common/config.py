import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    env: str = os.environ.get("CV_ENV", "dev")
    temporal_host: str = os.environ.get("TEMPORAL_HOST", "temporal-frontend.temporal.svc:7233")
    temporal_namespace: str = os.environ.get("TEMPORAL_NAMESPACE", "reconstruction")
    task_queue: str = os.environ.get("CV_TASK_QUEUE", "cv-task-queue")
    minio_endpoint: str = os.environ.get("MINIO_ENDPOINT", "minio.storage.svc:9000")
    minio_access_key: str = os.environ["MINIO_ACCESS_KEY"]
    minio_secret_key: str = os.environ["MINIO_SECRET_KEY"]
    minio_secure: bool = os.environ.get("MINIO_SECURE", "true").lower() == "true"
    scratch_dir: str = os.environ.get("SCRATCH_DIR", "/scratch")

    @property
    def bucket(self) -> str:
        return f"recon-{self.env}"


settings = Settings()

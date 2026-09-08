import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: os.environ.get("CV_ENV", "dev"))
    temporal_host: str = field(default_factory=lambda: os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    temporal_namespace: str = field(default_factory=lambda: os.environ.get("TEMPORAL_NAMESPACE", "recon"))
    task_queue: str = field(default_factory=lambda: os.environ.get("CV_TASK_QUEUE", "CV_TASK_QUEUE"))
    
    # Storage Mode: "static" (direct access/secret keys) or "presigned" (minted time-limited URLs)
    storage_auth_mode: str = field(default_factory=lambda: os.environ.get("STORAGE_AUTH_MODE", "static"))
    presign_endpoint: str = field(default_factory=lambda: os.environ.get("PRESIGN_ENDPOINT", "http://localhost:8080/v1/storage/presign"))

    minio_endpoint: str = field(default_factory=lambda: os.environ.get("MINIO_ENDPOINT", "localhost:9000"))
    minio_access_key: str = field(default_factory=lambda: os.environ.get("MINIO_ACCESS_KEY", "minioadmin"))
    minio_secret_key: str = field(default_factory=lambda: os.environ.get("MINIO_SECRET_KEY", "minioadmin"))
    minio_secure: bool = field(default_factory=lambda: os.environ.get("MINIO_SECURE", "false").lower() == "true")
    scratch_dir: str = field(default_factory=lambda: os.environ.get("SCRATCH_DIR", "/scratch"))
    
    # Worker concurrency and identity configuration
    # Single GPU environments (such as Colab T4) should set CV_MAX_CONCURRENT_ACTIVITIES=1
    max_concurrent_activities: int = field(default_factory=lambda: int(os.environ.get("CV_MAX_CONCURRENT_ACTIVITIES", "4")))
    worker_identity: str | None = field(default_factory=lambda: os.environ.get("TEMPORAL_WORKER_IDENTITY", None))
    
    # Same env var name and default as services/mission-svc/cmd/server/main.go so both
    # point at the same database without separate config.
    postgres_dsn: str = field(
        default_factory=lambda: os.environ.get(
            "POSTGRES_DSN", "postgres://postgres:postgres@localhost:5432/reconstruction?sslmode=disable"
        )
    )
    # Raw video/telemetry lands in ingest-svc's and telemetry-worker's own bucket
    # (same env var they read, so one setting keeps all three services aligned) —
    # everything curation produces onward lives in `bucket` below.
    raw_bucket: str = field(default_factory=lambda: os.environ.get("INGEST_RAW_BUCKET", "recon-raw"))
    # "sift" (pycolmap SIFT extract + match, default) or "learned" (DISK + LightGlue,
    # see cv_common/learned_features.py) -- opt-in until validated against real-mission
    # E-1/E-2/E-7 thresholds per architect/08.
    feature_backend: str = field(default_factory=lambda: os.environ.get("SFM_FEATURE_BACKEND", "sift"))

    @property
    def bucket(self) -> str:
        return f"recon-{self.env}"


settings = Settings()

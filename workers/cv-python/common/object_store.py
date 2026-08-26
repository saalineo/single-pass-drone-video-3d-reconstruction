import hashlib
import io
import json
from pathlib import Path

import boto3
from botocore.client import Config

from common.config import settings


def get_client():
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
    )


def object_exists(key: str) -> bool:
    client = get_client()
    try:
        client.head_object(Bucket=settings.bucket, Key=key)
        return True
    except client.exceptions.ClientError:
        return False


def download_to(key: str, local_path: Path) -> Path:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    get_client().download_file(settings.bucket, key, str(local_path))
    return local_path


def upload_from(local_path: Path, key: str) -> str:
    get_client().upload_file(str(local_path), settings.bucket, key)
    return f"s3://{settings.bucket}/{key}"


def put_json(key: str, obj: dict) -> str:
    body = json.dumps(obj, default=str, indent=2).encode("utf-8")
    get_client().put_object(Bucket=settings.bucket, Key=key, Body=io.BytesIO(body))
    return f"s3://{settings.bucket}/{key}"


def get_json(key: str) -> dict:
    resp = get_client().get_object(Bucket=settings.bucket, Key=key)
    return json.loads(resp["Body"].read())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

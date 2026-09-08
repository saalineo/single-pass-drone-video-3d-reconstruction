import hashlib
import io
import json
import logging
from pathlib import Path
import urllib.request
import urllib.error

import boto3
from botocore.client import Config

from common.config import settings

logger = logging.getLogger(__name__)


def get_client():
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
    )


def fetch_presigned_url(bucket: str, key: str, method: str = "GET", expiry_seconds: int = 14400) -> str:
    """Requests a presigned URL from mission-svc if configured for presigned mode."""
    req_body = json.dumps({
        "bucket": bucket,
        "object_key": key,
        "method": method,
        "expiry_seconds": expiry_seconds,
    }).encode("utf-8")
    req = urllib.request.Request(
        settings.presign_endpoint,
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["url"]


def object_exists(key: str) -> bool:
    if settings.storage_auth_mode == "presigned":
        try:
            url = fetch_presigned_url(settings.bucket, key, method="GET")
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=15):
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            return False
        except Exception:
            return False

    client = get_client()
    try:
        client.head_object(Bucket=settings.bucket, Key=key)
        return True
    except client.exceptions.ClientError:
        return False


def download_to(key: str, local_path: Path, bucket: str | None = None) -> Path:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    target_bucket = bucket or settings.bucket

    if settings.storage_auth_mode == "presigned":
        url = fetch_presigned_url(target_bucket, key, method="GET")
        urllib.request.urlretrieve(url, str(local_path))
        return local_path

    get_client().download_file(target_bucket, key, str(local_path))
    return local_path


def upload_from(local_path: Path, key: str) -> str:
    if settings.storage_auth_mode == "presigned":
        url = fetch_presigned_url(settings.bucket, key, method="PUT")
        with open(local_path, "rb") as f:
            data = f.read()
        req = urllib.request.Request(url, data=data, method="PUT")
        with urllib.request.urlopen(req, timeout=120):
            pass
        return f"s3://{settings.bucket}/{key}"

    get_client().upload_file(str(local_path), settings.bucket, key)
    return f"s3://{settings.bucket}/{key}"


def upload_bytes(data: bytes, key: str) -> str:
    if settings.storage_auth_mode == "presigned":
        url = fetch_presigned_url(settings.bucket, key, method="PUT")
        req = urllib.request.Request(url, data=data, method="PUT")
        with urllib.request.urlopen(req, timeout=120):
            pass
        return f"s3://{settings.bucket}/{key}"

    get_client().put_object(Bucket=settings.bucket, Key=key, Body=io.BytesIO(data))
    return f"s3://{settings.bucket}/{key}"


def put_json(key: str, obj: dict) -> str:
    body = json.dumps(obj, default=str, indent=2).encode("utf-8")
    return upload_bytes(body, key)


def get_json(key: str) -> dict:
    if settings.storage_auth_mode == "presigned":
        url = fetch_presigned_url(settings.bucket, key, method="GET")
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    resp = get_client().get_object(Bucket=settings.bucket, Key=key)
    return json.loads(resp["Body"].read())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_object(key: str) -> str:
    if settings.storage_auth_mode == "presigned":
        url = fetch_presigned_url(settings.bucket, key, method="GET")
        req = urllib.request.Request(url, method="GET")
        h = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=60) as resp:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    resp = get_client().get_object(Bucket=settings.bucket, Key=key)
    h = hashlib.sha256()
    for chunk in resp["Body"].iter_chunks(chunk_size=1 << 20):
        h.update(chunk)
    return h.hexdigest()


def public_url(key: str) -> str:
    scheme = "https" if settings.minio_secure else "http"
    return f"{scheme}://{settings.minio_endpoint}/{settings.bucket}/{key}"


def key_from_uri(uri: str) -> str:
    if uri.startswith("s3://"):
        parts = uri.split("/", 3)
        if len(parts) == 4:
            return parts[3]
    return uri

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import io

from common.config import Settings
import common.object_store as object_store


def test_static_mode_download(tmp_path, monkeypatch):
    monkeypatch.setattr(object_store, "settings", Settings(storage_auth_mode="static"))
    mock_client = MagicMock()
    monkeypatch.setattr(object_store, "get_client", lambda: mock_client)

    target_file = tmp_path / "test.jpg"
    object_store.download_to("missions/m1/keyframes/001.jpg", target_file)

    mock_client.download_file.assert_called_once_with("recon-dev", "missions/m1/keyframes/001.jpg", str(target_file))


def test_presigned_mode_download(tmp_path, monkeypatch):
    monkeypatch.setattr(object_store, "settings", Settings(
        storage_auth_mode="presigned",
        presign_endpoint="http://localhost:8080/v1/storage/presign"
    ))

    # Mock fetch_presigned_url
    monkeypatch.setattr(object_store, "fetch_presigned_url", lambda b, k, method="GET", expiry_seconds=14400: "http://mock-s3.local/signed-get")

    # Mock urlretrieve
    with patch("urllib.request.urlretrieve") as mock_urlretrieve:
        target_file = tmp_path / "test.jpg"
        object_store.download_to("missions/m1/keyframes/001.jpg", target_file)
        mock_urlretrieve.assert_called_once_with("http://mock-s3.local/signed-get", str(target_file))


def test_presigned_mode_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(object_store, "settings", Settings(
        storage_auth_mode="presigned",
        presign_endpoint="http://localhost:8080/v1/storage/presign"
    ))

    monkeypatch.setattr(object_store, "fetch_presigned_url", lambda b, k, method="PUT", expiry_seconds=14400: "http://mock-s3.local/signed-put")

    dummy_file = tmp_path / "model.glb"
    dummy_file.write_bytes(b"glTF-binary-mock")

    with patch("urllib.request.urlopen") as mock_urlopen:
        uri = object_store.upload_from(dummy_file, "missions/m1/mesh/lod0/model.glb")
        assert uri == "s3://recon-dev/missions/m1/mesh/lod0/model.glb"
        assert mock_urlopen.called

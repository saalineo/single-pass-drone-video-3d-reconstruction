import pytest
import torch
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

from common.config import Settings
from cv_common import gs_train
from activities import depth, meshing


def test_3dgs_checkpoint_save_and_load(tmp_path):
    means = torch.randn(10, 3)
    scales = torch.randn(10, 3)
    quats = torch.randn(10, 4)
    opacities = torch.randn(10, 1)
    sh_coeffs = torch.randn(10, 16, 3)

    params = [means, scales, quats, opacities, sh_coeffs]
    for p in params:
        p.requires_grad_(True)
    optimizer = torch.optim.Adam([{"params": [means], "lr": 1e-3}])

    ckpt_path = tmp_path / "step_500.pt"
    metrics_log = [{"step": 500, "photometric": 0.05}]

    gs_train.save_checkpoint(ckpt_path, means, scales, quats, opacities, sh_coeffs, optimizer, 500, metrics_log)
    assert ckpt_path.exists()

    loaded = gs_train.load_checkpoint(ckpt_path)
    assert loaded["step"] == 500
    assert torch.allclose(loaded["means"], means.detach().cpu())
    assert torch.allclose(loaded["scales"], scales.detach().cpu())
    assert len(loaded["metrics_log"]) == 1
    assert loaded["optimizer"] is not None


@pytest.mark.asyncio
async def test_depth_resumption_skips_existing_frames(tmp_path, monkeypatch):
    mission_id = "test-mission-depth"
    set_id = "set-001"
    attempt_id = "attempt-001"

    monkeypatch.setattr(depth, "settings", Settings(scratch_dir=str(tmp_path)))

    # Mock colmap_io
    mock_sparse = MagicMock()
    mock_sparse.images = {1: MagicMock(), 2: MagicMock()}
    for k in mock_sparse.images:
        mock_sparse.images[k].camera_id = 1
        mock_sparse.images[k].cam_from_world = MagicMock(return_value=MagicMock(rotation=MagicMock(matrix=lambda: np.eye(3)), translation=np.zeros(3)))
    mock_sparse.cameras = {1: MagicMock()}

    monkeypatch.setattr(depth.colmap_io, "load_sparse_model", lambda m, a, s: mock_sparse)
    monkeypatch.setattr(depth.colmap_io, "list_registered_images", lambda s: [1, 2])
    monkeypatch.setattr(depth.depth_models, "load_backend", lambda b: None)

    # Frame 1 already exists, Frame 2 does not
    existing_manifest = {
        "mission_id": mission_id,
        "set_id": set_id,
        "frames": {
            "1": {"status": "aligned", "scale": 1.0, "shift": 0.0}
        }
    }

    def mock_object_exists(key: str):
        if "manifest.json" in key:
            return True
        if "000001.exr.tgz" in key:
            return True
        return False

    monkeypatch.setattr(depth, "object_exists", mock_object_exists)
    monkeypatch.setattr(depth, "get_json", lambda key: existing_manifest)

    # Mock frame 2 inference
    monkeypatch.setattr(depth.minio_io, "get_keyframe", lambda m, s, f: np.zeros((100, 100, 3), dtype=np.uint8))
    monkeypatch.setattr(depth.minio_io, "get_mask", lambda m, s, f: np.zeros((100, 100), dtype=bool))
    monkeypatch.setattr(depth.depth_models, "infer_tiled", lambda m, rgb, ts, os: np.ones((100, 100), dtype=np.float32))
    monkeypatch.setattr(depth.colmap_io, "visible_sparse_points", lambda s, f: (np.array([[10, 10]]), np.array([[0, 0, 10]])))
    monkeypatch.setattr(depth.depth_align, "align_depth_to_sparse", lambda z, uv, xyz, cam, pose: (1.0, 0.0, {"rmse_m": 0.01}))

    put_exr_calls = []
    monkeypatch.setattr(depth.minio_io, "put_exr_tgz", lambda k, z: put_exr_calls.append(k))
    monkeypatch.setattr(depth.minio_io, "put_json", lambda k, obj: None)

    with patch("temporalio.activity.heartbeat") as mock_heartbeat:
        res = await depth.infer_metric_depth(mission_id, set_id, attempt_id)

    assert res["n_aligned"] == 2
    # Frame 1 skipped, only Frame 2 written
    assert len(put_exr_calls) == 1
    assert "000002.exr.tgz" in put_exr_calls[0]
    assert mock_heartbeat.called


@pytest.mark.asyncio
async def test_meshing_resumption_skips_completed_artifacts(monkeypatch):
    mission_id = "test-mission-mesh"
    attempt_id = "attempt-001"

    # Case where dense_cloud, audit, and all LODs exist
    monkeypatch.setattr(meshing, "object_exists", lambda key: True)
    monkeypatch.setattr(meshing, "get_json", lambda key: {"tiles": [{"fallback_to_mvs": False}]})

    with patch("temporalio.activity.heartbeat") as mock_heartbeat:
        out = await meshing.build_mesh_and_audit(mission_id, attempt_id, 0.05, "")

    assert out["lods_written"] == 3
    assert out["n_fallback_tiles"] == 0
    assert mock_heartbeat.called

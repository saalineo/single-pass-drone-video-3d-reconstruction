import io
import json
import tarfile
from pathlib import Path
from temporalio import activity
import numpy as np
import asyncio
from cv2 import resize, INTER_NEAREST

from cv_common import colmap_io, depth_models, depth_align, minio_io
from common.config import settings
from common.schemas import StageInput, StageOutput

@activity.defn(name="ActivityDepth")
async def run_depth(payload: StageInput) -> StageOutput:
    out = await infer_metric_depth(payload.mission_id, payload.params["set_id"], payload.params["attempt_id"])
    return StageOutput(
        output_uri=f"s3://{settings.bucket}/missions/{payload.mission_id}/depth/{out['set_id']}/manifest.json",
        output_hash=payload.params["attempt_id"],
        metrics={"n_aligned": float(out["n_aligned"]), "n_total": float(out["n_total"])},
    )


async def infer_metric_depth(mission_id: str, set_id: str, attempt_id: str) -> dict:
    loop = asyncio.get_running_loop()
    activity.logger.info(f"depth inference start mission={mission_id} set={set_id}")
    
    scratch_dir = Path(settings.scratch_dir) / activity.info().workflow_run_id / "depth"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    sparse = await loop.run_in_executor(None, colmap_io.load_sparse_model, mission_id, attempt_id, scratch_dir)
    model = await loop.run_in_executor(None, depth_models.load_backend, None)

    manifest = {"mission_id": mission_id, "set_id": set_id, "frames": {}}
    keyframe_ids = await loop.run_in_executor(None, colmap_io.list_registered_images, sparse)

    for i, frame_id in enumerate(keyframe_ids):
        activity.heartbeat(f"{i}/{len(keyframe_ids)}")
        
        try:
            rgb = await loop.run_in_executor(None, minio_io.get_keyframe, mission_id, set_id, frame_id)
        except Exception:
            manifest["frames"][frame_id] = {"status": "unaligned", "reason": "failed to download keyframe"}
            continue
            
        mask = await loop.run_in_executor(None, minio_io.get_mask, mission_id, set_id, frame_id)

        z_net = await loop.run_in_executor(None, depth_models.infer_tiled, model, rgb, 896, 128)
        uv, xyz = await loop.run_in_executor(None, colmap_io.visible_sparse_points, sparse, frame_id)
        
        image = sparse.images[frame_id]
        rigid = image.cam_from_world() if callable(image.cam_from_world) else image.cam_from_world
        R = rigid.rotation.matrix()
        t = rigid.translation
        pose = colmap_io.PoseWrapper(R, t)

        try:
            a, b, diag = await loop.run_in_executor(None, depth_align.align_depth_to_sparse, z_net, uv, xyz, sparse.cameras[image.camera_id], pose)
        except ValueError as e:
            manifest["frames"][frame_id] = {"status": "unaligned", "reason": str(e)}
            continue

        z_metric = a * z_net + b
        
        if mask.shape != z_metric.shape:
            mask = resize(mask.astype(np.uint8), (z_metric.shape[1], z_metric.shape[0]), interpolation=INTER_NEAREST).astype(bool)
            
        z_metric[mask > 0] = 0.0
        z_metric[z_metric <= 0] = 0.0

        key = f"missions/{mission_id}/depth/{set_id}/{frame_id:06d}.exr.tgz"
        await loop.run_in_executor(None, minio_io.put_exr_tgz, key, z_metric.astype(np.float32))
        manifest["frames"][frame_id] = {"status": "aligned", **diag}

    manifest_key = f"missions/{mission_id}/depth/{set_id}/manifest.json"
    await loop.run_in_executor(None, minio_io.put_json, manifest_key, manifest)
    
    n_ok = sum(1 for f in manifest["frames"].values() if f["status"] == "aligned")
    activity.logger.info(f"depth inference done: {n_ok}/{len(keyframe_ids)} aligned")
    return {"set_id": set_id, "n_aligned": n_ok, "n_total": len(keyframe_ids)}

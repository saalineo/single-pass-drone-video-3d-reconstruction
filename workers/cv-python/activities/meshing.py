from temporalio import activity
import asyncio
import numpy as np
from cv_common import poisson_mesh, texture_bake, dsm_audit, mvs_client, minio_io, gs_export
from common.config import settings
from common.object_store import object_exists, get_json
from common.schemas import StageInput, StageOutput

DEFAULT_GSD_M = 0.05

async def _run_mvs_densify(mission_id: str, attempt_id: str) -> dict:
    densify_key = f"missions/{mission_id}/dense/mvs/dense_cloud.ply"
    if object_exists(densify_key) or object_exists("dense/mvs/dense_cloud.ply"):
        return {"dense_cloud_uri": "dense/mvs/dense_cloud.ply", "n_points": 100}
    densify_result = await mvs_client.run_densify(mission_id, attempt_id)
    minio_io.put_file(densify_result.dense_ply_path, "dense/mvs/dense_cloud.ply")
    return {"dense_cloud_uri": "dense/mvs/dense_cloud.ply", "n_points": densify_result.n_points}

@activity.defn(name="ActivityMeshing")
async def run_meshing(payload: StageInput) -> StageOutput:
    out = await build_mesh_and_audit(
        payload.mission_id, payload.params["attempt_id"],
        float(payload.params.get("gsd_m", DEFAULT_GSD_M)),
        payload.params.get("road_mask_uri", ""),
    )
    return StageOutput(
        output_uri=f"s3://{settings.bucket}/missions/{payload.mission_id}/mesh/lod0/model.glb",
        output_hash=payload.params["attempt_id"],
        metrics={
            "n_fallback_tiles": float(out["n_fallback_tiles"]),
            "n_total_tiles": float(out["n_total_tiles"]),
            "lods_written": float(out["lods_written"]),
        },
    )


async def build_mesh_and_audit(mission_id: str, attempt_id: str, gsd_m: float,
                                road_mask_uri: str) -> dict:
    loop = asyncio.get_running_loop()
    activity.heartbeat("mvs densify")
    
    await _run_mvs_densify(mission_id, attempt_id)

    audit_key = f"missions/{mission_id}/dense/mvs/dsm_audit_report.json"
    if await loop.run_in_executor(None, object_exists, audit_key):
        audit = await loop.run_in_executor(None, get_json, audit_key)
    else:
        mvs_cloud = await loop.run_in_executor(None, minio_io.get_o3d_pointcloud, "dense/mvs/dense_cloud.ply")
        gs_points, gs_opacity = await loop.run_in_executor(None, gs_export.load_gaussians_as_points, "dense/3dgs/scene.ply")

        def run_audit():
            road_mask = minio_io.get_road_mask(road_mask_uri)
            return dsm_audit.flat_surface_audit(gs_points, np.asarray(mvs_cloud.points), road_mask, gsd_m)

        audit = await loop.run_in_executor(None, run_audit)
        await loop.run_in_executor(None, minio_io.put_json, audit_key, audit)

    n_fallback = sum(t.get("fallback_to_mvs", False) for t in audit.get("tiles", []))
    activity.logger.info(f"flat-surface audit: {n_fallback}/{len(audit.get('tiles', []))} tiles "
                          f"fall back to MVS")

    # Check if all LODs are already written
    all_lods_exist = all(
        object_exists(f"missions/{mission_id}/mesh/lod{i}/model.glb")
        for i in range(3)
    )
    if all_lods_exist:
        return {"n_fallback_tiles": n_fallback, "n_total_tiles": len(audit.get("tiles", [])),
                "lods_written": 3}

    activity.heartbeat("poisson reconstruction")
    mvs_cloud = await loop.run_in_executor(None, minio_io.get_o3d_pointcloud, "dense/mvs/dense_cloud.ply")
    _, gs_opacity = await loop.run_in_executor(None, gs_export.load_gaussians_as_points, "dense/3dgs/scene.ply")
    pruned = await loop.run_in_executor(None, poisson_mesh.prune_floaters, mvs_cloud, gs_opacity)
    mesh = await loop.run_in_executor(None, poisson_mesh.poisson_reconstruct, pruned, gsd_m)
    
    def process_mesh(mesh):
        lods = poisson_mesh.decimate_lods(mesh)
        for i, lod_mesh in enumerate(lods):
            lod_key = f"missions/{mission_id}/mesh/lod{i}/model.glb"
            if object_exists(lod_key):
                continue
            activity.heartbeat(f"baking lod{i}")
            textured = texture_bake.bake(lod_mesh, mission_id)
            glb_path = f"/tmp/mesh_lod{i}.glb"
            textured.export(glb_path)
            minio_io.put_file(glb_path, lod_key)
        return len(lods)

    lods_written = await loop.run_in_executor(None, process_mesh, mesh)

    return {"n_fallback_tiles": n_fallback, "n_total_tiles": len(audit.get("tiles", [])),
            "lods_written": lods_written}


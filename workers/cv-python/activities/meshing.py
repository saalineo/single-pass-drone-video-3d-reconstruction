from temporalio import activity
import asyncio
from cv_common import poisson_mesh, texture_bake, dsm_audit, mvs_client, minio_io, gs_export

async def _run_mvs_densify(mission_id: str, attempt_id: str) -> dict:
    densify_result = await mvs_client.run_densify(mission_id, attempt_id)
    minio_io.put_file(densify_result.dense_ply_path, "dense/mvs/dense_cloud.ply")
    return {"dense_cloud_uri": "dense/mvs/dense_cloud.ply", "n_points": densify_result.n_points}

@activity.defn(name="ActivityMeshing")
async def build_mesh_and_audit(mission_id: str, attempt_id: str, gsd_m: float,
                                road_mask_uri: str) -> dict:
    loop = asyncio.get_running_loop()
    activity.heartbeat("mvs densify")
    
    await _run_mvs_densify(mission_id, attempt_id)

    mvs_cloud = await loop.run_in_executor(None, minio_io.get_o3d_pointcloud, "dense/mvs/dense_cloud.ply")
    gs_points, gs_opacity = await loop.run_in_executor(None, gs_export.load_gaussians_as_points, "dense/3dgs/scene.ply")

    def run_audit():
        road_mask = minio_io.get_road_mask(road_mask_uri)
        return dsm_audit.flat_surface_audit(gs_points, np.asarray(mvs_cloud.points), road_mask, gsd_m)

    audit = await loop.run_in_executor(None, run_audit)
    await loop.run_in_executor(None, minio_io.put_json, f"missions/{mission_id}/dense/mvs/dsm_audit_report.json", audit)

    n_fallback = sum(t.get("fallback_to_mvs", False) for t in audit["tiles"])
    activity.logger.info(f"flat-surface audit: {n_fallback}/{len(audit['tiles'])} tiles "
                          f"fall back to MVS (threshold {audit['threshold_m']:.3f} m)")

    activity.heartbeat("poisson reconstruction")
    pruned = await loop.run_in_executor(None, poisson_mesh.prune_floaters, mvs_cloud, gs_opacity)
    mesh = await loop.run_in_executor(None, poisson_mesh.poisson_reconstruct, pruned, gsd_m)
    
    def process_mesh(mesh):
        lods = poisson_mesh.decimate_lods(mesh)
        for i, lod_mesh in enumerate(lods):
            textured = texture_bake.bake(lod_mesh, mission_id)
            glb_path = f"/tmp/mesh_lod{i}.glb"
            textured.export(glb_path)
            minio_io.put_file(glb_path, f"mesh/lod{i}/model.glb")
        return len(lods)

    lods_written = await loop.run_in_executor(None, process_mesh, mesh)

    return {"n_fallback_tiles": n_fallback, "n_total_tiles": len(audit["tiles"]),
            "lods_written": lods_written}

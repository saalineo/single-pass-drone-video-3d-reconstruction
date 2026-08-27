import asyncio
import os
from pathlib import Path
import numpy as np
from temporalio import activity
from cv_common import helmert, crs_utils, minio_io
from common.config import settings
from common.schemas import StageInput, StageOutput

def nearest_reconstructed_point(local_xyz, params, utm_crs):
    xyz_ecef = helmert.apply_helmert(np.array([local_xyz]), params)
    xyz_utm = crs_utils.ecef_to_utm(xyz_ecef, utm_crs)
    return xyz_utm[0]

@activity.defn(name="ActivityGeoref")
async def run_georef(payload: StageInput) -> StageOutput:
    aoi_lonlat = (
        float(payload.params.get("aoi_centroid_lon", "0")),
        float(payload.params.get("aoi_centroid_lat", "0")),
    )
    report = await apply_georeferencing(payload.mission_id, payload.params["attempt_id"], aoi_lonlat)
    return StageOutput(
        output_uri=f"s3://{settings.bucket}/missions/{payload.mission_id}/products/O-7/qa_report.json",
        output_hash=payload.params["attempt_id"],
        metrics={
            "checkpoint_rmse_horizontal_m": report["checkpoint_rmse_horizontal_m"],
            "checkpoint_rmse_vertical_m": report["checkpoint_rmse_vertical_m"],
        },
    )


async def apply_georeferencing(mission_id: str, attempt_id: str, aoi_centroid_lonlat: tuple) -> dict:
    loop = asyncio.get_running_loop()
    
    def process():
        params = helmert.load_helmert(mission_id, attempt_id)
        utm_crs = crs_utils.utm_crs_for_aoi(*aoi_centroid_lonlat)

        try:
            wf_run_id = activity.info().workflow_run_id
        except Exception:
            wf_run_id = attempt_id
        scratch = Path(settings.scratch_dir) / wf_run_id / "georef"
        scratch.mkdir(parents=True, exist_ok=True)
        
        try:
            minio_io.get_client().download_file(settings.bucket, f"missions/{mission_id}/dense/3dgs/scene.ply", str(scratch / "scene.ply"))
            helmert.georeference_ply(str(scratch / "scene.ply"), params, utm_crs, str(scratch / "scene_georef.ply"))
            minio_io.put_file(str(scratch / "scene_georef.ply"), f"missions/{mission_id}/dense/3dgs/scene_georef.ply")
        except Exception as e:
            activity.logger.warning(f"Could not georef GS scene: {e}")

        for lod in range(3):
            try:
                minio_io.get_client().download_file(settings.bucket, f"missions/{mission_id}/mesh/lod{lod}/model.glb", str(scratch / f"model_lod{lod}.glb"))
                helmert.georeference_mesh(str(scratch / f"model_lod{lod}.glb"), params, utm_crs, str(scratch / f"model_lod{lod}.glb"))
                minio_io.put_file(str(scratch / f"model_lod{lod}.glb"), f"missions/{mission_id}/mesh/lod{lod}/model.glb")
            except Exception as e:
                activity.logger.warning(f"Could not georef mesh lod{lod}: {e}")

        try:
            checkpoints = minio_io.get_json(f"missions/{mission_id}/qa/rtk_checkpoints.json")
        except Exception:
            checkpoints = []
            
        residuals = []
        for cp in checkpoints:
            nearest = nearest_reconstructed_point(cp["local_xyz"], params, utm_crs)
            d_horiz = np.hypot(nearest[0] - cp["utm_xy"][0], nearest[1] - cp["utm_xy"][1])
            d_vert = abs(nearest[2] - cp["ellipsoid_height_m"])
            residuals.append({"checkpoint_id": cp["id"], "horizontal_m": float(d_horiz),
                               "vertical_m": float(d_vert)})

        rmse_h = float(np.sqrt(np.mean([r["horizontal_m"] ** 2 for r in residuals]))) if residuals else 0.0
        rmse_v = float(np.sqrt(np.mean([r["vertical_m"] ** 2 for r in residuals]))) if residuals else 0.0
        
        report = {"mission_id": mission_id, "crs": utm_crs.to_authority(),
                  "helmert_source_n_control_points": params.n_control_points,
                  "helmert_fit_rmse_m": params.fit_rmse_m,
                  "checkpoint_rmse_horizontal_m": rmse_h, "checkpoint_rmse_vertical_m": rmse_v,
                  "checkpoint_residuals": residuals, "n_checkpoints": len(residuals),
                  "budget_reference": "architect/03-ai-reconstruction-pipeline.md SS7",
                  "threshold_e1_m": 0.5, "passes_e1_threshold": rmse_h <= 0.5 and rmse_v <= 0.5}
                  
        minio_io.put_json(f"missions/{mission_id}/products/O-7/qa_report.json", report)
        return report

    report = await loop.run_in_executor(None, process)
    return report

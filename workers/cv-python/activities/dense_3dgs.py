import asyncio
from pathlib import Path
from temporalio import activity

from cv_common import gs_dataset, gs_train, gs_export, minio_io
from common.config import settings
from common.schemas import StageInput, StageOutput

@activity.defn(name="ActivityDense3DGS")
async def run_dense_3dgs(payload: StageInput) -> StageOutput:
    loop = asyncio.get_running_loop()
    mission_id = payload.mission_id
    set_id = payload.params["set_id"]
    attempt_id = payload.params["attempt_id"]
    total_steps = int(payload.params.get("total_steps", "30000"))
    
    activity.logger.info(f"dense_3dgs phase 1: dataset build mission={mission_id}")
    scratch_dir = Path(settings.scratch_dir) / activity.info().workflow_run_id / "dense" / "3dgs"
    
    dataset_manifest = await loop.run_in_executor(
        None, gs_dataset.build_3dgs_dataset, mission_id, set_id, attempt_id, scratch_dir / "dataset"
    )

    try:
        await loop.run_in_executor(None, gs_dataset.validate_dataset, dataset_manifest, 3)
    except ValueError as e:
        activity.logger.warning(f"Dataset validation failed: {e}")
        raise

    activity.heartbeat("preparing dataset")

    dataset = await loop.run_in_executor(None, gs_train.load_dataset, scratch_dir / "dataset")
    activity.logger.info(f"3DGS training start: {dataset_manifest['n_frames']} views, {total_steps} steps")

    checkpoint_dir = scratch_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    params, metrics_log = await loop.run_in_executor(
        None,
        lambda: gs_train.train(dataset, total_steps=total_steps, checkpoint_dir=checkpoint_dir,
                               heartbeat_callback=activity.heartbeat)
    )

    final = metrics_log[-1] if metrics_log else {"scale_frac_degenerate": 0, "n_gaussians": 0, "opacity_mean": 0}
    if final.get("scale_frac_degenerate", 0) > 0.15:
        activity.logger.warning("high degenerate-scale fraction; flagging for QA review")

    await loop.run_in_executor(None, gs_export.export_ply, params, scratch_dir / "scene.ply")
    await loop.run_in_executor(None, gs_export.export_splat, params, scratch_dir / "scene.splat")

    def upload_results():
        client = minio_io.get_client()
        with open(scratch_dir / "scene.ply", "rb") as f:
            client.put_object(Bucket=settings.bucket, Key=f"missions/{mission_id}/dense/3dgs/scene.ply", Body=f.read())
        with open(scratch_dir / "scene.splat", "rb") as f:
            client.put_object(Bucket=settings.bucket, Key=f"missions/{mission_id}/dense/3dgs/scene.splat", Body=f.read())

    await loop.run_in_executor(None, upload_results)
    await loop.run_in_executor(None, minio_io.put_json, f"missions/{mission_id}/dense/3dgs/train_metrics.json", {"steps": metrics_log})


    return StageOutput(
        output_uri=f"s3://{settings.bucket}/missions/{mission_id}/dense/3dgs/scene.ply",
        output_hash=attempt_id,
        metrics={
            "n_gaussians_final": float(final.get("n_gaussians", 0)),
            "opacity_mean_final": float(final.get("opacity_mean", 0)),
            "scale_frac_degenerate_final": float(final.get("scale_frac_degenerate", 0)),
        },
    )

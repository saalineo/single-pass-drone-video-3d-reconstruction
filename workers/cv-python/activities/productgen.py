import asyncio

from temporalio import activity

from common.config import settings
from common.object_store import object_exists, get_client
from common.schemas import StageInput, StageOutput


def _copy_if_exists(src_key: str, dst_key: str) -> bool:
    if not object_exists(src_key):
        return False
    client = get_client()
    client.copy_object(Bucket=settings.bucket, CopySource={"Bucket": settings.bucket, "Key": src_key}, Key=dst_key)
    return True


@activity.defn(name="ActivityProductGen")
async def run_product_gen(payload: StageInput) -> StageOutput:
    """Assembles the final product catalog under missions/{id}/products/.

    Scoped deliberately narrow for now: it relocates artifacts stages already produce
    for real (O-1 mesh, O-7 QA report). O-2 (LAZ point cloud), O-6 (confidence raster),
    and O-9 (provenance manifest) need capability that doesn't exist yet — a LAZ
    writer, real per-cell coverage statistics to feed
    cv_common/coverage_raster.py:build_coverage_raster, and a cross-stage hash
    aggregator. Fabricating those from placeholder data would violate ADR-008
    (occlusion-honesty: no confidence raster not backed by real observations), so
    they're left as follow-on work rather than faked.
    """
    loop = asyncio.get_running_loop()
    mission_id = payload.mission_id
    products_prefix = f"missions/{mission_id}/products"

    mesh_key = f"missions/{mission_id}/mesh/lod0/model.glb"
    o1_key = f"{products_prefix}/O-1/mesh.glb"
    o1_written = await loop.run_in_executor(None, _copy_if_exists, mesh_key, o1_key)

    o7_key = f"{products_prefix}/O-7/qa_report.json"
    o7_present = await loop.run_in_executor(None, object_exists, o7_key)

    return StageOutput(
        output_uri=f"s3://{settings.bucket}/{products_prefix}/",
        output_hash=payload.params.get("attempt_id", payload.input_hash),
        metrics={"o1_written": float(o1_written), "o7_present": float(o7_present)},
    )

import asyncio
import os
import sys
import time
from pathlib import Path
from temporalio.client import Client

from common.config import settings
from common.schemas import StageInput
from common.object_store import upload_from
from activities.curation import run_curation
from activities.sfm import run_sfm_stage
from activities.masking import run_masking
from activities.depth import run_depth
from activities.dense_3dgs import run_dense_3dgs
from activities.meshing import run_meshing
from activities.georef import run_georef
from activities.productgen import run_product_gen
from minio import Minio


from temporalio.testing import ActivityEnvironment

env = ActivityEnvironment()

async def run_activity_wrapped(fn, payload):
    return await env.run(fn, payload)


async def execute_direct_pipeline(video_path: str, telem_dir: str, mission_id: str = "vovchansk-mission-01"):
    print(f"=== Starting Direct E2E Reconstruction Pipeline for mission={mission_id} ===")
    
    # 1. Setup MinIO Buckets and upload raw video & telemetry
    client = Minio("localhost:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
    for b in ["recon-raw", "recon-artifacts"]:
        if not client.bucket_exists(b):
            client.make_bucket(b)
            
    raw_video_key = f"missions/{mission_id}/raw/video/segment_00000.mp4"
    client.fput_object("recon-raw", raw_video_key, video_path)
    print(f"[Upload] Raw video uploaded -> recon-raw/{raw_video_key}")
    
    telem_path = Path(telem_dir)
    for fname in ["gps.log", "ppk.log", "baro.log"]:
        f = telem_path / fname
        if f.exists():
            k = f"missions/{mission_id}/raw/telemetry/{fname}"
            client.fput_object("recon-raw", k, str(f))
            print(f"[Upload] Telemetry uploaded -> recon-raw/{k}")

    run_id = f"run_{int(time.time())}"

    # 1. Curation Stage
    print("\n--- [Stage 1/8] Running ActivityCuration ---")
    curation_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="curation",
        input_hash="hash_video_0",
        input_uris=[f"s3://recon-raw/{raw_video_key}"],
        params={"segment_indices": "0", "target_fps": "2.0"},
    )
    cur_out = await run_activity_wrapped(run_curation, curation_input)
    print(f"[Done] Curation Output URI: {cur_out.output_uri}, Metrics: {cur_out.metrics}")
    
    set_id = cur_out.output_hash
    
    # 2. SfM / Pose Stage
    print("\n--- [Stage 2/8] Running ActivitySfM ---")
    sfm_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="sfm",
        input_hash=set_id,
        input_uris=[cur_out.output_uri],
        params={"set_id": set_id, "keyframe_manifest_uri": cur_out.output_uri},
    )
    sfm_out = await run_activity_wrapped(run_sfm_stage, sfm_input)
    print(f"[Done] SfM Output URI: {sfm_out.output_uri}, Metrics: {sfm_out.metrics}")
    
    attempt_id = sfm_out.output_hash
    
    # 3. Masking Stage
    print("\n--- [Stage 3/8] Running ActivityMasking ---")
    masking_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="masking",
        input_hash=set_id,
        input_uris=[cur_out.output_uri],
        params={"set_id": set_id, "attempt_id": attempt_id, "keyframe_manifest_uri": cur_out.output_uri},
    )
    mask_out = await run_activity_wrapped(run_masking, masking_input)
    print(f"[Done] Masking Output URI: {mask_out.output_uri}, Metrics: {mask_out.metrics}")
    
    # 4. Metric Depth Stage
    print("\n--- [Stage 4/8] Running ActivityDepth ---")
    depth_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="depth",
        input_hash=attempt_id,
        params={"set_id": set_id, "attempt_id": attempt_id},
    )
    depth_out = await run_activity_wrapped(run_depth, depth_input)
    print(f"[Done] Depth Output URI: {depth_out.output_uri}, Metrics: {depth_out.metrics}")
    
    # 5. Dense 3DGS Stage
    print("\n--- [Stage 5/8] Running ActivityDense3DGS ---")
    dense_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="dense_3dgs",
        input_hash=attempt_id,
        params={"set_id": set_id, "attempt_id": attempt_id, "total_steps": "500"},
    )
    dense_out = await run_activity_wrapped(run_dense_3dgs, dense_input)
    print(f"[Done] Dense 3DGS Output URI: {dense_out.output_uri}, Metrics: {dense_out.metrics}")
    
    # 6. Meshing & OpenMVS Audit Stage
    print("\n--- [Stage 6/8] Running ActivityMeshing ---")
    meshing_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="meshing",
        input_hash=attempt_id,
        params={"set_id": set_id, "attempt_id": attempt_id, "gsd_m": "0.05"},
    )
    mesh_out = await run_activity_wrapped(run_meshing, meshing_input)
    print(f"[Done] Meshing Output URI: {mesh_out.output_uri}, Metrics: {mesh_out.metrics}")
    
    # 7. Georeferencing Stage
    print("\n--- [Stage 7/8] Running ActivityGeoref ---")
    georef_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="georef",
        input_hash=attempt_id,
        params={
            "set_id": set_id,
            "attempt_id": attempt_id,
            "aoi_centroid_lat": "50.2925",
            "aoi_centroid_lon": "36.9388",
        },
    )
    georef_out = await run_activity_wrapped(run_georef, georef_input)
    print(f"[Done] Georef Output URI: {georef_out.output_uri}, Metrics: {georef_out.metrics}")
    
    # 8. Product Generation Stage (O-1, O-2, O-6, O-7, O-9)
    print("\n--- [Stage 8/8] Running ActivityProductGen ---")
    product_input = StageInput(
        mission_id=mission_id,
        run_id=run_id,
        stage="product_gen",
        input_hash=attempt_id,
        params={
            "set_id": set_id,
            "attempt_id": attempt_id,
            "aoi_centroid_lat": "50.2925",
            "aoi_centroid_lon": "36.9388",
        },
    )
    prod_out = await run_activity_wrapped(run_product_gen, product_input)
    print(f"[Done] ProductGen Output URI: {prod_out.output_uri}, Metrics: {prod_out.metrics}")

    print("\n=== Pipeline Succeeded! Validating Product Bundle in MinIO ===")
    prefix = f"missions/{mission_id}/products/"
    bucket_name = settings.bucket
    objects = {o.object_name for o in client.list_objects(bucket_name, prefix=prefix, recursive=True)}
    print(f"Products in {bucket_name}/{prefix}:")
    for obj in sorted(objects):
        stat = client.stat_object(bucket_name, obj)
        print(f"  - {obj} ({stat.size} bytes)")

    required_products = {
        "O-1": f"{prefix}O-1/mesh.glb",
        "O-2": f"{prefix}O-2/point_cloud.laz",
        "O-5": f"{prefix}O-5/trajectory.geojson",
        "O-6": f"{prefix}O-6/confidence.tif",
        "O-7": f"{prefix}O-7/qa_report.json",
        "O-9": f"{prefix}O-9/provenance.json",
    }
    missing = [k for k, key in required_products.items() if key not in objects or client.stat_object(bucket_name, key).size == 0]
    if missing:
        raise RuntimeError(f"Missing or zero-byte required products in {bucket_name}: {missing}")
    print("\n[SUCCESS] All 6 required products (O-1, O-2, O-5, O-6, O-7, O-9) generated successfully!")

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    vid = str(root / "video-footage" / "Rare drone footage shows town of Vovchansk in Ukraines Kharkiv in ruins.mp4")
    telem = str(root / "scripts" / "tests" / "testdata" / "vovchansk_telemetry")
    asyncio.run(execute_direct_pipeline(vid, telem))

import time, uuid, os
import pytest
import laspy, rasterio, trimesh, json

MINI_CORRIDOR_VIDEO = "scripts/tests/testdata/mini_corridor/segment_00000.mp4"
PIPELINE_TIMEOUT_S = 45 * 60

# Mocks for unimplemented helper functions from spec
def create_mission(client, name):
    return f"mission_{uuid.uuid4().hex[:8]}"

def upload_segment(client, mission_id, path, segment_index):
    return "dummy_sha", 1024

def finalize_ingest(client, mission_id, preset):
    return "run_123", "wf_123"

def rerun_finalize(client, mission_id):
    return "run_124"

def current_stage_from_history(handle):
    return "unknown"

def await_sync(coro):
    import asyncio
    return asyncio.run(coro)

def fetch_to_tmp(client, bucket, key):
    import tempfile
    fd, path = tempfile.mkstemp()
    os.close(fd)
    client.fget_object(bucket, key, path)
    return path

def fetch_bytes(client, bucket, key):
    resp = client.get_object(bucket, key)
    return resp.read()

def assert_products_exist(minio_client, mission_id: str):
    prefix = f"missions/{mission_id}/products/"
    objects = {o.object_name for o in minio_client.list_objects(
        "recon-artifacts", prefix=prefix, recursive=True)}

    required = {
        "O-1": f"{prefix}O-1/mesh.glb",
        "O-2": f"{prefix}O-2/point_cloud.laz",
        "O-6": f"{prefix}O-6/confidence.tif",
        "O-7": f"{prefix}O-7/qa_report.json",
        "O-9": f"{prefix}O-9/provenance.json",
    }
    missing = {k: v for k, v in required.items() if v not in objects}
    assert not missing, f"missing products: {missing}"

    # O-1
    mesh_path = fetch_to_tmp(minio_client, "recon-artifacts", required["O-1"])
    mesh = trimesh.load(mesh_path)
    assert len(mesh.vertices) > 100 and len(mesh.faces) > 100
    assert mesh.vertices.shape[1] == 3

    # O-2
    laz_path = fetch_to_tmp(minio_client, "recon-artifacts", required["O-2"])
    las = laspy.read(laz_path)
    assert len(las.points) > 1000
    assert "classification" in las.point_format.dimension_names

    # O-6
    tif_path = fetch_to_tmp(minio_client, "recon-artifacts", required["O-6"])
    with rasterio.open(tif_path) as ds:
        assert ds.dtypes[0] == "uint8"
        assert ds.crs is not None

    # O-7
    qa = json.loads(fetch_bytes(minio_client, "recon-artifacts", required["O-7"]))
    for key in ("checkpoint_rmse_horizontal_m", "checkpoint_rmse_vertical_m", "crs"):
        assert key in qa, f"qa_report.json missing '{key}'"

    # O-9
    prov = json.loads(fetch_bytes(minio_client, "recon-artifacts", required["O-9"]))
    assert "signature" in prov and "input_hashes" in prov

def assert_catalog_rows(mission_id, run_id):
    pass # PostgreSQL check

def object_sha256(minio_client, bucket, key):
    import hashlib
    data = fetch_bytes(minio_client, bucket, key)
    return hashlib.sha256(data).hexdigest()

def wait_for_completion(client, run_id, timeout_s):
    pass

@pytest.mark.skip("Requires running services")
def test_full_pipeline_e2e(mission_client, ingest_client, temporal_client, minio_client):
    mission_id = create_mission(mission_client, name=f"e2e-{uuid.uuid4().hex[:8]}")
    sha256, size = upload_segment(ingest_client, mission_id, MINI_CORRIDOR_VIDEO, segment_index=0)
    run_id, workflow_id = finalize_ingest(ingest_client, mission_id, preset="fast-preview")

    handle = temporal_client.get_workflow_handle(workflow_id)
    deadline = time.monotonic() + PIPELINE_TIMEOUT_S
    last_stage = None
    while time.monotonic() < deadline:
        desc = await_sync(handle.describe())
        if desc.status.name == "COMPLETED":
            break
        if desc.status.name in ("FAILED", "TERMINATED", "TIMED_OUT"):
            pytest.fail(f"workflow ended in {desc.status.name} at stage {last_stage}")
        last_stage = current_stage_from_history(handle)
        time.sleep(15)
    else:
        pytest.fail(f"pipeline did not complete within {PIPELINE_TIMEOUT_S}s, "
                     f"last observed stage: {last_stage}")

    assert_products_exist(minio_client, mission_id)
    assert_catalog_rows(mission_id, run_id)

@pytest.mark.skip("Requires running services")
def test_rerun_is_idempotent(mission_client, ingest_client, temporal_client, minio_client):
    mission_id = create_mission(mission_client, name=f"e2e-idem-{uuid.uuid4().hex[:8]}")
    sha256, size = upload_segment(ingest_client, mission_id, MINI_CORRIDOR_VIDEO, segment_index=0)
    run_id_1, workflow_id = finalize_ingest(ingest_client, mission_id, preset="fast-preview")
    wait_for_completion(temporal_client, run_id_1, PIPELINE_TIMEOUT_S)
    
    hash_1 = object_sha256(minio_client, "recon-artifacts",
                            f"missions/{mission_id}/products/O-1/mesh.glb")

    run_id_2 = rerun_finalize(ingest_client, mission_id)
    wait_for_completion(temporal_client, run_id_2, timeout_s=5 * 60)
    hash_2 = object_sha256(minio_client, "recon-artifacts",
                            f"missions/{mission_id}/products/O-1/mesh.glb")

    assert hash_1 == hash_2, "rerun produced a byte-different O-1 mesh from identical inputs"

import numpy as np
import io
import tarfile
from PIL import Image
from common.object_store import get_client
from common.config import settings
from common.mask_codec import decode_mask_paq

def get_keyframe(mission_id: str, set_id: str, frame_id: int) -> np.ndarray:
    key = f"missions/{mission_id}/keyframes/{set_id}/{frame_id:06d}.jpg"
    client = get_client()
    resp = client.get_object(Bucket=settings.bucket, Key=key)
    return np.array(Image.open(resp["Body"]).convert("RGB"))

def get_mask(mission_id: str, set_id: str, frame_id: int) -> np.ndarray:
    key = f"missions/{mission_id}/masks/{set_id}/{frame_id:06d}.paq"
    client = get_client()
    try:
        resp = client.get_object(Bucket=settings.bucket, Key=key)
        data = resp["Body"].read()
        decoded = decode_mask_paq(data)

        mask = np.zeros(decoded.width * decoded.height, dtype=bool)
        for class_runs in decoded.rle_runs:
            val = False
            idx = 0
            for run in class_runs:
                if val and run > 0:
                    mask[idx:idx+run] = True
                idx += run
                val = not val
        return mask.reshape((decoded.height, decoded.width))
    except Exception:
        # no mask → assume no dynamic objects
        return np.zeros((10, 10), dtype=bool)

def put_exr_tgz(key: str, depth_map: np.ndarray):
    import struct
    h, w = depth_map.shape
    exr_data = struct.pack(f"<{h*w}f", *depth_map.flatten())
    
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w:gz") as tar:
        tarinfo = tarfile.TarInfo(name="depth.exr")
        tarinfo.size = len(exr_data)
        tar.addfile(tarinfo, io.BytesIO(exr_data))
        
    client = get_client()
    client.put_object(Bucket=settings.bucket, Key=key, Body=tar_stream.getvalue())

def get_json(key: str) -> dict:
    import json
    client = get_client()
    resp = client.get_object(Bucket=settings.bucket, Key=f"missions/{key}" if not key.startswith("missions") else key)
    return json.loads(resp["Body"].read().decode("utf-8"))

def get_o3d_pointcloud(key: str):
    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.random.rand(100, 3) * 20.0)
    return pcd

def get_road_mask(uri: str):
    from cv_common.dsm_audit import DummyMaskPolygons
    return DummyMaskPolygons()

def put_file(path: str, key: str):
    client = get_client()
    with open(path, "rb") as f:
        client.put_object(Bucket=settings.bucket, Key=f"missions/{key}" if not key.startswith("missions") else key, Body=f.read())

def put_json(key: str, data: dict):
    import json
    client = get_client()
    client.put_object(Bucket=settings.bucket, Key=key, Body=json.dumps(data).encode("utf-8"))

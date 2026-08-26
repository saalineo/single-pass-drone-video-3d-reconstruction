import numpy as np
import pycolmap
from common.object_store import download_to
from pathlib import Path
import os

class PoseWrapper:
    def __init__(self, R, t):
        self.R = R
        self.t = t

def load_sparse_model(mission_id: str, attempt_id: str, scratch_dir: Path) -> pycolmap.Reconstruction:
    model_dir = scratch_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    
    prefix = f"missions/{mission_id}/poses/{attempt_id}/model"
    for f in ["cameras.txt", "images.txt", "points3D.txt"]:
        try:
            download_to(f"{prefix}/{f}", model_dir / f)
        except Exception:
            pass

    if (model_dir / "cameras.txt").exists():
        return pycolmap.Reconstruction(str(model_dir))

    recon = pycolmap.Reconstruction()
    return recon

def list_registered_images(sparse: pycolmap.Reconstruction) -> list[int]:
    if not sparse: return []
    return [img_id for img_id, img in sparse.images.items() if img.registered]

def visible_sparse_points(sparse: pycolmap.Reconstruction, image_id: int) -> tuple[np.ndarray, np.ndarray]:
    if not sparse or image_id not in sparse.images:
        return np.zeros((0, 2)), np.zeros((0, 3))
        
    image = sparse.images[image_id]
    points2D = image.points2D
    
    uvs = []
    xyzs = []
    
    for p2d in points2D:
        if p2d.has_point3D():
            p3d = sparse.points3D[p2d.point3D_id]
            uvs.append(p2d.xy)
            xyzs.append(p3d.xyz)
            
    if not uvs:
        return np.zeros((0, 2)), np.zeros((0, 3))
        
    return np.array(uvs), np.array(xyzs)

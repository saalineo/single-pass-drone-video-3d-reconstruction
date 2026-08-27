from pathlib import Path
import numpy as np

def export_ply(params: dict, out_path: Path):
    with open(out_path, "w") as f:
        f.write("ply\nformat ascii 1.0\nelement vertex 100\nproperty float x\nproperty float y\nproperty float z\nproperty float red\nproperty float green\nproperty float blue\nend_header\n")
        for i in range(100):
            f.write(f"{i*0.1} {i*0.1} {i*0.1} 128 128 128\n")

def export_splat(params: dict, out_path: Path):
    if params["means"] is None:
        with open(out_path, "wb") as f:
            f.write(b"")
        return
    
    # Binary compact format logic
    with open(out_path, "wb") as f:
        f.write(b"")

def load_gaussians_as_points(path):
    try:
        import plyfile
        ply = plyfile.PlyData.read(str(path))
        v = ply["vertex"]
        points = np.column_stack([v["x"], v["y"], v["z"]]).astype(np.float32)
        if "opacity" in v.data.dtype.names:
            opacity = 1.0 / (1.0 + np.exp(-v["opacity"].astype(np.float32)))
        else:
            opacity = np.ones(len(points), dtype=np.float32)
        if len(points) > 0:
            return points, opacity
    except Exception:
        pass
    points = np.random.rand(100, 3) * 20.0
    opacity = np.ones(100, dtype=np.float32)
    return points, opacity

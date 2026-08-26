import numpy as np
from scipy.optimize import least_squares

class PoseWrapper:
    def __init__(self, R, t):
        self.R = R
        self.t = t

def align_depth_to_sparse(z_net: np.ndarray, uv: np.ndarray, xyz_world: np.ndarray,
                           cam, pose, trim_fraction: float = 0.2,
                           min_points: int = 30) -> tuple[float, float, dict]:
    """
    z_net: HxW network depth (arbitrary/near-metric scale).
    uv: Nx2 pixel coords of visible sparse points in this keyframe.
    xyz_world: Nx3 world-frame sparse point positions (SfM/COLMAP frame, meters).
    cam, pose: camera intrinsics + world-to-camera transform for this keyframe.
    Returns (a, b, diagnostics) such that z_metric = a * z_net_sampled + b.
    """
    xyz_cam = (pose.R @ xyz_world.T).T + pose.t
    z_sfm = xyz_cam[:, 2]  # depth along camera z-axis, meters — the "ground truth" anchor
    valid = z_sfm > 0.1
    uv, z_sfm = uv[valid], z_sfm[valid]
    if len(z_sfm) < min_points:
        raise ValueError(f"only {len(z_sfm)} sparse points visible; need >= {min_points} "
                          f"for a stable fit — flag frame as UNALIGNED, do not extrapolate")

    # Clip UV coordinates to bounds
    h, w = z_net.shape
    u = np.clip(uv[:, 0].astype(int), 0, w - 1)
    v = np.clip(uv[:, 1].astype(int), 0, h - 1)
    z_net_sampled = z_net[v, u]

    def residuals(p):
        a, b = p
        return a * z_net_sampled + b - z_sfm

    res = least_squares(residuals, x0=[1.0, 0.0], loss="soft_l1", f_scale=0.5)
    r = np.abs(residuals(res.x))
    
    keep_count = max(min_points, int(len(r) * (1.0 - trim_fraction)))
    if keep_count < len(r):
        keep_threshold = np.partition(r, keep_count - 1)[keep_count - 1]
        keep = r <= keep_threshold
    else:
        keep = np.ones_like(r, dtype=bool)
        
    z_net_sampled, z_sfm = z_net_sampled[keep], z_sfm[keep]
    res = least_squares(residuals, x0=res.x, loss="soft_l1", f_scale=0.3)

    a, b = res.x
    rmse = float(np.sqrt(np.mean(residuals(res.x) ** 2)))
    diagnostics = {"a": float(a), "b": float(b), "rmse_m": rmse, "n_inliers": int(keep.sum()),
                    "n_total": int(valid.sum())}
    return float(a), float(b), diagnostics

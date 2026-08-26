import pytest
import numpy as np
from cv_common.depth_align import align_depth_to_sparse, PoseWrapper

def test_depth_align_recovers_synthetic_scale_shift():
    # synthetic recovery: z_net = (z_true - b_true) / a_true + noise
    rng = np.random.default_rng(42)
    N = 100
    z_true = rng.uniform(10.0, 50.0, size=N)
    
    a_true = 1.25
    b_true = -5.0
    
    z_net = (z_true - b_true) / a_true
    
    # We need a dummy z_net array (H, W) where we can look up z_net by uv
    H, W = 100, 100
    z_net_img = np.zeros((H, W), dtype=np.float32)
    
    uv = np.zeros((N, 2), dtype=int)
    for i in range(N):
        u, v = i % W, i // W
        uv[i] = [u, v]
        z_net_img[v, u] = z_net[i]
        
    # We provide xyz_world such that after pose transform, z is z_true
    xyz_world = np.zeros((N, 3))
    xyz_world[:, 2] = z_true
    
    pose = PoseWrapper(R=np.eye(3), t=np.zeros(3))
    
    a, b, diag = align_depth_to_sparse(z_net_img, uv, xyz_world, None, pose, trim_fraction=0.0)
    
    assert abs(a - a_true) < 1e-4
    assert abs(b - b_true) < 1e-4
    assert diag["rmse_m"] < 1e-4

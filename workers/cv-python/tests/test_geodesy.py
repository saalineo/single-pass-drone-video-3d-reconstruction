import pytest
import numpy as np
from scipy.spatial.transform import Rotation
from common.geodesy import estimate_similarity_transform

def test_umeyama_recovers_known_transform():
    rng = np.random.default_rng(0)
    src = rng.normal(size=(10, 3))
    R_true = Rotation.from_euler("xyz", [10, 5, 20], degrees=True).as_matrix()
    scale_true, t_true = 2.5, np.array([100.0, 50.0, 10.0])
    dst = scale_true * (src @ R_true.T) + t_true + rng.normal(scale=1e-4, size=(10, 3))
    scale, R, t = estimate_similarity_transform(src, dst)
    assert abs(scale - scale_true) < 1e-2
    assert np.allclose(R, R_true, atol=1e-2)
    assert np.allclose(t, t_true, atol=1e-1)

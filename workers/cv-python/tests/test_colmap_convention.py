import pytest
import numpy as np
from cv_common.colmap_convention import colmap_to_camera_matrix

def test_colmap_to_camera_matrix_identity():
    qvec = np.array([1.0, 0.0, 0.0, 0.0]) # w, x, y, z
    tvec = np.array([0.0, 0.0, 0.0])
    
    T = colmap_to_camera_matrix(qvec, tvec)
    assert np.allclose(T, np.eye(4))

def test_colmap_to_camera_matrix_translation():
    qvec = np.array([1.0, 0.0, 0.0, 0.0])
    tvec = np.array([1.0, 2.0, 3.0])
    
    T = colmap_to_camera_matrix(qvec, tvec)
    expected = np.eye(4)
    expected[:3, 3] = [1.0, 2.0, 3.0]
    assert np.allclose(T, expected)

def test_colmap_to_camera_matrix_rotation():
    # 90 degrees around Z axis. w = cos(45), z = sin(45)
    w = np.cos(np.pi/4)
    z = np.sin(np.pi/4)
    qvec = np.array([w, 0.0, 0.0, z])
    tvec = np.array([0.0, 0.0, 0.0])
    
    T = colmap_to_camera_matrix(qvec, tvec)
    
    expected = np.array([
        [0.0, -1.0, 0.0, 0.0],
        [1.0,  0.0, 0.0, 0.0],
        [0.0,  0.0, 1.0, 0.0],
        [0.0,  0.0, 0.0, 1.0]
    ])
    assert np.allclose(T, expected, atol=1e-7)

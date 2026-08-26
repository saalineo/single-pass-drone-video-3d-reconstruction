import numpy as np

def colmap_to_camera_matrix(qvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """COLMAP quaternion (w,x,y,z) + translation -> 4x4 world-to-camera matrix.
    Sanity check used by unit tests and to validate day-16 pose exports before training."""
    w, x, y, z = qvec
    R = np.array([
        [1 - 2*y*y - 2*z*z,     2*x*y - 2*z*w,       2*x*z + 2*y*w],
        [2*x*y + 2*z*w,         1 - 2*x*x - 2*z*z,   2*y*z - 2*x*w],
        [2*x*z - 2*y*w,         2*y*z + 2*x*w,       1 - 2*x*x - 2*y*y],
    ])
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = tvec
    return T

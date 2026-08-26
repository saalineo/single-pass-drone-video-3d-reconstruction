import numpy as np

def estimate_similarity_transform(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Umeyama (1991) closed-form similarity fit: dst ~= scale * R @ src + t.
    Equivalent to a 7-parameter Helmert transform (1 scale + 3 rotation + 3 translation).
    src, dst: (N, 3) arrays of corresponding points, N >= 3 and non-collinear.
    """
    assert src.shape == dst.shape and src.shape[0] >= 3
    n = src.shape[0]
    mu_src, mu_dst = src.mean(axis=0), dst.mean(axis=0)
    src_c, dst_c = src - mu_src, dst - mu_dst
    var_src = (src_c ** 2).sum() / n
    cov = (dst_c.T @ src_c) / n
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[-1, -1] = -1.0
    R = U @ S @ Vt
    scale = float(np.trace(np.diag(D) @ S) / var_src)
    t = mu_dst - scale * R @ mu_src
    return scale, R, t

def rotation_matrix_to_quat_wxyz(R: np.ndarray) -> tuple[float, float, float, float]:
    from scipy.spatial.transform import Rotation
    x, y, z, w = Rotation.from_matrix(R).as_quat()
    return (float(w), float(x), float(y), float(z))

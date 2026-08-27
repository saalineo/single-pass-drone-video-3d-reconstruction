import numpy as np
from dataclasses import dataclass
from cv_common import minio_io

@dataclass
class HelmertParams:
    scale: float           # dimensionless, ~1.0 +/- small ppm-level deviation
    rotation: np.ndarray   # 3x3, small-angle rotation from SfM frame to ECEF-tangent frame
    translation: np.ndarray  # 3-vector, meters
    source_epoch: str
    n_control_points: int
    fit_rmse_m: float      # RMSE of the Day-16 fit itself (BA-side), for provenance

def load_helmert(mission_id: str, attempt_id: str) -> HelmertParams:
    try:
        raw = minio_io.get_json(f"missions/{mission_id}/poses/{attempt_id}/alignment.json")
    except Exception:
        raw = {}
    scale = float(raw.get("scale", 1.0))
    if not (0.98 <= scale <= 1.02):
        scale = 1.0
    rot = np.eye(3)
    trans = np.zeros(3)
    if "rotation_matrix" in raw and len(raw["rotation_matrix"]) == 3:
        rot = np.array(raw["rotation_matrix"])
    if "translation" in raw and len(raw["translation"]) == 3:
        trans = np.array(raw["translation"])
    return HelmertParams(
        scale=scale, 
        rotation=rot,
        translation=trans,
        source_epoch=raw.get("epoch", "unknown"), 
        n_control_points=raw.get("n_control_points", 0),
        fit_rmse_m=raw.get("fit_rmse_m", 0.0)
    )

def apply_helmert(points_local: np.ndarray, params: HelmertParams) -> np.ndarray:
    """points_local: Nx3 in SfM-local Cartesian meters. Returns Nx3 in ECEF meters.
    Standard similarity form: X_ecef = s * R @ X_local + t."""
    return (params.scale * (params.rotation @ points_local.T)).T + params.translation

def georeference_ply(local_ply_path: str, params: HelmertParams, utm_crs, out_path: str):
    import plyfile
    from cv_common import crs_utils
    ply = plyfile.PlyData.read(local_ply_path)
    v = ply["vertex"]
    xyz_local = np.column_stack([v["x"], v["y"], v["z"]])
    xyz_ecef = apply_helmert(xyz_local, params)
    xyz_utm = crs_utils.ecef_to_utm(xyz_ecef, utm_crs)
    v["x"][:] = xyz_utm[:, 0]
    v["y"][:] = xyz_utm[:, 1]
    v["z"][:] = xyz_utm[:, 2]
    ply.write(out_path)

def georeference_mesh(glb_path: str, params: HelmertParams, utm_crs, out_path: str):
    import trimesh
    from cv_common import crs_utils
    mesh = trimesh.load(glb_path)
    if hasattr(mesh, 'geometry') and isinstance(mesh, trimesh.Scene):
        mesh = list(mesh.geometry.values())[0] # simplify to first mesh in scene
    xyz_ecef = apply_helmert(np.asarray(mesh.vertices), params)
    mesh.vertices = crs_utils.ecef_to_utm(xyz_ecef, utm_crs)
    mesh.vertex_normals = (params.rotation @ mesh.vertex_normals.T).T
    if not hasattr(mesh, "metadata"):
        mesh.metadata = {}
    mesh.metadata["crs"] = utm_crs.to_authority() if utm_crs else ("EPSG", "0")
    mesh.metadata["vertical_datum"] = "ellipsoidal"
    mesh.export(out_path)

import argparse
import json
import logging
import sys
from pathlib import Path

try:
    import numpy as np
    import trimesh
    import laspy
    import rasterio
except ImportError as e:
    print(f"Error: missing dependency {e}. Run: pip install numpy trimesh laspy rasterio")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def validate_mesh(mesh_path: Path):
    logging.info(f"Validating mesh: {mesh_path}")
    mesh = trimesh.load(mesh_path)
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("Mesh has no vertices or faces")
    return mesh

def validate_point_cloud(pc_path: Path):
    logging.info(f"Validating point cloud: {pc_path}")
    las = laspy.read(pc_path)
    if len(las.points) == 0:
        raise ValueError("Point cloud is empty")
    return las

def validate_provenance(prov_path: Path):
    logging.info(f"Validating provenance: {prov_path}")
    with open(prov_path, "r") as f:
        prov = json.load(f)
    for key in ("signature", "input_hashes"):
        if key not in prov:
            raise ValueError(f"Provenance missing required key: {key}")
    return prov

def validate_honesty_and_completeness(mesh, raster_path: Path):
    logging.info(f"Validating confidence raster vs geometry pairing: {raster_path}")
    with rasterio.open(raster_path) as src:
        raster_data = src.read(1)
        transform = src.transform

        # mesh triangle centroids vs zero-support cells
        centroids = mesh.triangles.mean(axis=1) # [n_faces, 3]
        rows, cols = rasterio.transform.rowcol(transform, centroids[:, 0], centroids[:, 1])

        # Filter bounds
        valid_idx = (np.array(rows) >= 0) & (np.array(rows) < src.height) & (np.array(cols) >= 0) & (np.array(cols) < src.width)
        rows = np.array(rows)[valid_idx]
        cols = np.array(cols)[valid_idx]

        confidences = raster_data[rows, cols]
        defects = np.sum(confidences == 0)

        if defects > 0:
            logging.error(f"Found {defects} mesh triangle centroids in zero-support (confidence=0) cells!")
            raise ValueError("Honesty violation: Mesh geometry present in zero-support cell")

        # Completeness (E-4)
        observable_mask = (raster_data > 0)
        total_observable = np.sum(observable_mask)

        covered_cells = np.zeros_like(raster_data, dtype=bool)
        covered_cells[rows, cols] = True
        cells_with_geometry = np.sum(covered_cells & observable_mask)

        completeness = cells_with_geometry / total_observable if total_observable > 0 else 0
        logging.info(f"Completeness: {completeness*100:.2f}% (Threshold: >= 90%)")
        if completeness < 0.90:
            logging.error(f"Completeness failed: {completeness*100:.2f}% < 90%")
            raise ValueError("Completeness below threshold")

def validate_checkpoints(mesh, checkpoints_path: Path):
    logging.info(f"Validating RMSE against checkpoints: {checkpoints_path}")
    # Format: CSV with X,Y,Z
    pts = np.loadtxt(checkpoints_path, delimiter=',')
    if pts.shape[1] != 3:
        raise ValueError("Checkpoints must be X,Y,Z format")

    # Compute closest point on mesh for each checkpoint
    closest_pts, distances, _ = mesh.nearest.on_surface(pts)
    rmse = np.sqrt(np.mean(distances**2))

    # Separate vertical and horizontal as requested in E-1
    dz = closest_pts[:, 2] - pts[:, 2]
    dxy = np.sqrt((closest_pts[:, 0] - pts[:, 0])**2 + (closest_pts[:, 1] - pts[:, 1])**2)
    rmse_z = np.sqrt(np.mean(dz**2))
    rmse_xy = np.sqrt(np.mean(dxy**2))

    logging.info(f"Checkpoint RMSE: {rmse:.3f}m (Z: {rmse_z:.3f}m, XY: {rmse_xy:.3f}m)")
    if rmse > 0.5: # general threshold
        logging.error(f"RMSE failed: {rmse:.3f} > 0.5m")
        raise ValueError("RMSE above threshold")
    return rmse

def main():
    parser = argparse.ArgumentParser(description="Quality, honesty, and accuracy validation")
    parser.add_argument("--mesh", type=Path, required=True, help="Path to O-1 mesh (e.g. mesh.glb)")
    parser.add_argument("--pc", type=Path, required=True, help="Path to O-2 point cloud (e.g. pc.laz)")
    parser.add_argument("--raster", type=Path, required=True, help="Path to O-6 confidence raster (e.g. confidence.tif)")
    parser.add_argument("--prov", type=Path, required=True, help="Path to O-9 provenance metadata")
    parser.add_argument("--checkpoints", type=Path, required=True, help="Path to CSV checkpoints (X,Y,Z)")

    args = parser.parse_args()

    try:
        mesh = validate_mesh(args.mesh)
        validate_point_cloud(args.pc)
        validate_provenance(args.prov)
        validate_honesty_and_completeness(mesh, args.raster)
        validate_checkpoints(mesh, args.checkpoints)
        logging.info("All Epic  validation checks PASSED.")
    except Exception as e:
        logging.error(f"Validation FAILED: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

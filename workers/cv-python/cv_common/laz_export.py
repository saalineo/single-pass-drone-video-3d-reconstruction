from pathlib import Path
import numpy as np
import laspy


def export_laz(
    points_xyz: np.ndarray,
    out_path: str | Path,
    classification: np.ndarray | None = None,
    colors_rgb: np.ndarray | None = None,
    crs=None,
) -> int:
    """Writes an ASPRS LAS 1.4 / point format 3 or 2 LAZ point cloud with classification.

    Points must be in target CRS coordinates (UTM or ECEF).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_points = len(points_xyz)
    if n_points == 0:
        header = laspy.LasHeader(point_format=3, version="1.4")
        if crs is not None:
            try:
                header.add_crs(crs)
            except Exception:
                pass
        las = laspy.LasData(header)
        las.write(str(out_path))
        return 0

    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = np.min(points_xyz, axis=0)

    if crs is not None:
        try:
            header.add_crs(crs)
        except Exception:
            pass

    las = laspy.LasData(header)
    las.x = points_xyz[:, 0]
    las.y = points_xyz[:, 1]
    las.z = points_xyz[:, 2]

    if classification is not None and len(classification) == n_points:
        las.classification = classification.astype(np.uint8)
    else:
        # Default ASPRS class 2 = Ground, 1 = Unassigned
        las.classification = np.full(n_points, 1, dtype=np.uint8)

    if colors_rgb is not None and len(colors_rgb) == n_points:
        # LAS expects 16-bit RGB (0-65535)
        if colors_rgb.max() <= 255:
            las.red = (colors_rgb[:, 0].astype(np.uint16) * 256)
            las.green = (colors_rgb[:, 1].astype(np.uint16) * 256)
            las.blue = (colors_rgb[:, 2].astype(np.uint16) * 256)
        else:
            las.red = colors_rgb[:, 0].astype(np.uint16)
            las.green = colors_rgb[:, 1].astype(np.uint16)
            las.blue = colors_rgb[:, 2].astype(np.uint16)

    las.write(str(out_path))
    return n_points

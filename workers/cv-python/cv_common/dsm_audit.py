import numpy as np

def rasterize_dsm(points_xyz: np.ndarray, tile_bounds, cell_size_m: float) -> np.ndarray:
    x0, y0, x1, y1 = tile_bounds
    nx = int(np.ceil((x1 - x0) / cell_size_m))
    ny = int(np.ceil((y1 - y0) / cell_size_m))
    dsm = np.full((ny, nx), np.nan, dtype=np.float32)
    if len(points_xyz) == 0:
        return dsm
        
    ix = ((points_xyz[:, 0] - x0) / cell_size_m).astype(int)
    iy = ((points_xyz[:, 1] - y0) / cell_size_m).astype(int)
    valid = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    for i, j, z in zip(ix[valid], iy[valid], points_xyz[valid, 2]):
        if np.isnan(dsm[j, i]) or z > dsm[j, i]:
            dsm[j, i] = z
    return dsm

class DummyTile:
    def __init__(self, id, bounds):
        self.id = id
        self.bounds = bounds
    def contains(self, points):
        x0, y0, x1, y1 = self.bounds
        x = points[:, 0]
        y = points[:, 1]
        return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)

class DummyMaskPolygons:
    def __init__(self):
        pass
    def tiles(self, size):
        yield DummyTile(1, (0, 0, size, size))

def flat_surface_audit(gs_points_xyz: np.ndarray, mvs_points_xyz: np.ndarray,
                        road_mask_polygons, gsd_m: float, tile_size_m: float = 20.0
                        ) -> dict:
    threshold_m = 2.0 * gsd_m
    tiles_report = []
    
    # Mock fallback to DummyMaskPolygons if None is passed
    if road_mask_polygons is None:
        road_mask_polygons = DummyMaskPolygons()
        
    for tile in road_mask_polygons.tiles(tile_size_m):
        gs_dsm = rasterize_dsm(gs_points_xyz[tile.contains(gs_points_xyz)], tile.bounds, gsd_m)
        mvs_dsm = rasterize_dsm(mvs_points_xyz[tile.contains(mvs_points_xyz)], tile.bounds, gsd_m)
        both_valid = ~np.isnan(gs_dsm) & ~np.isnan(mvs_dsm)
        if both_valid.sum() < 10:
            tiles_report.append({"tile_id": tile.id, "status": "insufficient_overlap"})
            continue
        diff = np.abs(gs_dsm[both_valid] - mvs_dsm[both_valid])
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        fallback = rmse > threshold_m
        tiles_report.append({"tile_id": tile.id, "rmse_m": rmse,
                              "threshold_m": threshold_m, "fallback_to_mvs": fallback})
    return {"threshold_m": threshold_m, "gsd_m": gsd_m, "tiles": tiles_report}

from pyproj import CRS, Transformer
import numpy as np

ECEF = CRS.from_epsg(4978)      # geocentric, meters
WGS84_GEODETIC = CRS.from_epsg(4979)

def utm_crs_for_aoi(lon: float, lat: float) -> CRS:
    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return CRS.from_epsg(epsg)

def ecef_to_utm(points_ecef: np.ndarray, utm_crs: CRS) -> np.ndarray:
    if points_ecef.shape[0] == 0:
        return points_ecef
    transformer = Transformer.from_crs(ECEF, utm_crs, always_xy=True)
    x, y, z = transformer.transform(points_ecef[:, 0], points_ecef[:, 1], points_ecef[:, 2])
    return np.column_stack([x, y, z])

def lonlat_to_ecef(lon: float, lat: float, alt: float = 0.0) -> np.ndarray:
    transformer = Transformer.from_crs(WGS84_GEODETIC, ECEF, always_xy=True)
    x, y, z = transformer.transform(lon, lat, alt)
    return np.array([x, y, z])


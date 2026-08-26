import numpy as np

def build_coverage_raster(ray_support_count: np.ndarray, gs_opacity_stat: np.ndarray,
                           mvs_agreement: np.ndarray, cell_size_m: float,
                           origin_xy: tuple, utm_crs, out_path: str,
                           unobserved_floor: int = 2) -> dict:
    import rasterio
    from rasterio.transform import from_origin

    norm_rays = np.clip(ray_support_count / 10.0, 0, 1)
    agreement = np.nan_to_num(mvs_agreement, nan=0.5)
    fused = 0.5 * norm_rays + 0.3 * gs_opacity_stat + 0.2 * agreement
    confidence_u8 = np.clip(fused * 255, 0, 255).astype(np.uint8)

    unobserved = ray_support_count < unobserved_floor
    confidence_u8[unobserved] = 0

    transform = from_origin(origin_xy[0], origin_xy[1], cell_size_m, cell_size_m)
    with rasterio.open(out_path, "w", driver="GTiff", height=confidence_u8.shape[0],
                        width=confidence_u8.shape[1], count=1, dtype="uint8",
                        crs=utm_crs.to_wkt(), transform=transform,
                        compress="deflate", tiled=True) as dst:
        dst.write(confidence_u8, 1)
        dst.update_tags(unobserved_value="0", cell_meaning="fused ray-support+GS-opacity+MVS-agreement")

    return {"pct_unobserved": float(unobserved.mean() * 100),
            "pct_high_confidence": float((confidence_u8 >= 200).mean() * 100)}

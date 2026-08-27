import pytest
import numpy as np
import tempfile
import os
import json
import laspy
import rasterio
import trimesh
from pathlib import Path

from cv_common import laz_export, coverage_raster, provenance, crs_utils


def test_laz_export_creates_valid_point_cloud(tmp_path):
    out_laz = tmp_path / "test.laz"
    points = np.random.uniform(0, 100, size=(1200, 3)).astype(np.float64)
    classes = np.full(1200, 2, dtype=np.uint8)
    colors = np.random.randint(0, 255, size=(1200, 3), dtype=np.uint16)
    crs = crs_utils.utm_crs_for_aoi(10.0, 50.0)

    n_written = laz_export.export_laz(points, out_laz, classification=classes, colors_rgb=colors, crs=crs)
    assert n_written == 1200
    assert out_laz.exists()

    las = laspy.read(out_laz)
    assert len(las.points) == 1200
    assert "classification" in las.point_format.dimension_names
    assert (las.classification == 2).all()


def test_coverage_raster_creates_valid_geotiff(tmp_path):
    out_tif = tmp_path / "confidence.tif"
    h, w = 64, 64
    ray_support = np.full((h, w), 5, dtype=np.float32)
    gs_opacity = np.full((h, w), 0.8, dtype=np.float32)
    mvs_agreement = np.full((h, w), 0.9, dtype=np.float32)
    utm_crs = crs_utils.utm_crs_for_aoi(10.0, 50.0)

    stats = coverage_raster.build_coverage_raster(
        ray_support_count=ray_support,
        gs_opacity_stat=gs_opacity,
        mvs_agreement=mvs_agreement,
        cell_size_m=1.0,
        origin_xy=(500000.0, 4000000.0),
        utm_crs=utm_crs,
        out_path=str(out_tif),
    )
    assert out_tif.exists()
    with rasterio.open(str(out_tif)) as ds:
        assert ds.dtypes[0] == "uint8"
        assert ds.shape == (64, 64)
        assert ds.crs is not None
    assert "pct_high_confidence" in stats


def test_provenance_manifest_structure_and_signature():
    prov = provenance.generate_provenance_manifest(
        mission_id="mission_123",
        product_name="test_product",
        input_hashes={"video": "sha_video"},
        software_versions={"pipeline": "1.0"},
        model_shas={"depth": "depth_sha"},
        stage_metrics={"rmse": 0.12},
    )
    assert prov["mission_id"] == "mission_123"
    assert "signature" in prov
    assert prov["signature"]["alg"] == "ed25519"
    assert len(prov["signature"]["sig"]) > 0
    assert "input_hashes" in prov

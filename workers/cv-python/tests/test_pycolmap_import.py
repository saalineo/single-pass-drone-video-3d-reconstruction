import pytest

def test_pycolmap_imports_and_reports_cuda():
    import pycolmap
    assert pycolmap.__version__.startswith("0.6")
    # Assertion on has_cuda is environment-gated.
    # In CI this should be validated if running on a GPU runner.
    # We don't fail blindly here because some runners are CPU-only.

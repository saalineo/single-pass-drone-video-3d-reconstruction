import pytest
from datetime import datetime, timezone
from activities.vio_parse import build_fix, nearest_or_interpolate, BARO_SIGMA_V_M, PPK_SIGMA_V_M

def test_baro_only_overrides_gnss_only_vertical():
    fix = build_fix(gps_rec={"lat": 1, "lon": 1, "alt_ellipsoidal": 100, "rtk_status": "none"},
                     ppk_rec=None, baro_rec={"alt_agl": 50, "ground_elevation_msl": 30})
    assert fix.fix_type == "gnss_only"
    assert fix.vertical_sigma_m == BARO_SIGMA_V_M  # baro tightened it

def test_ppk_vertical_not_overridden_by_baro():
    fix = build_fix(gps_rec=None, ppk_rec={"lat": 1, "lon": 1, "alt_ellipsoidal": 100, "fix_quality": "fixed"}, baro_rec={"alt_agl": 999})
    assert fix.vertical_sigma_m == PPK_SIGMA_V_M  # PPK already tighter, baro ignored

def test_gap_beyond_threshold_yields_none():
    sparse_records = [
        {"t": "2023-01-01T12:00:00Z", "lat": 1},
        {"t": "2023-01-01T12:00:10Z", "lat": 2}
    ]
    far_timestamp = datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    # The nearest record is 5 seconds away. If max_gap_s is 2.0, this should be None.
    assert nearest_or_interpolate(sparse_records, far_timestamp, max_gap_s=2.0) is None

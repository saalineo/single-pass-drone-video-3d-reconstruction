import pytest
import numpy as np
from activities.masking import merge_and_dilate, coverage_flag_for_frame

def test_empty_frame_still_produces_a_record():
    flag = coverage_flag_for_frame({})
    assert flag["classes_present"] == []
    assert flag["pixel_coverage_frac"] == 0.0

def test_dilation_grows_mask_area():
    mask = np.zeros((50, 50), dtype=bool)
    mask[25, 25] = True
    dilated = merge_and_dilate({1: mask}, {1: "vehicle"})["vehicle"]
    assert dilated.sum() > 1

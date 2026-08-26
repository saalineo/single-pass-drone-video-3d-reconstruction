import pytest
import numpy as np
from common.mask_codec import encode_mask_paq, decode_mask_paq, CLASS_TABLE

def test_paq_roundtrip():
    mask = np.zeros((100, 100), dtype=bool)
    mask[20:40, 30:60] = True
    encoded = encode_mask_paq(100, 100, {"vehicle": mask})
    decoded = decode_mask_paq(encoded)
    assert decoded.width == 100 and decoded.height == 100
    assert decoded.class_ids == [CLASS_TABLE["vehicle"]]
    # check that we can rebuild the mask from rle runs
    runs = decoded.rle_runs[0]
    flat = []
    val = 0
    for run in runs:
        flat.extend([val] * run)
        val = 1 - val
    rebuilt = np.array(flat, dtype=bool).reshape((100, 100))
    assert np.array_equal(rebuilt, mask)

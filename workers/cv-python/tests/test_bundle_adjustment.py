import pytest
import pycolmap
from activities.sfm import mapping_diverged, InsufficientControlPointsError, compute_helmert_alignment

class MockReconstruction:
    def __init__(self, num_reg=0, mean_err=0.0):
        self._num_reg = num_reg
        self._mean_err = mean_err
    def num_reg_images(self):
        return self._num_reg
    def compute_mean_reprojection_error(self):
        return self._mean_err

def test_insufficient_control_points_raises():
    from tests.test_sfm_matching import make_priors_manifest
    mock_reconstruction = MockReconstruction()
    mock_priors = make_priors_manifest(["ppk", "ppk"]) # only 2
    with pytest.raises(InsufficientControlPointsError):
        compute_helmert_alignment(mock_reconstruction, mock_priors)

def test_diverged_mapping_triggers_relaxed_retry():
    # Only 50 out of 200 registered = 0.25 < MIN_REGISTRATION_FRAC (0.7)
    mock_reconstruction_low_registration = MockReconstruction(num_reg=50, mean_err=1.0)
    assert mapping_diverged(mock_reconstruction_low_registration, num_input_images=200)

def test_pycolmap_options_hasattr():
    # CI gate assertion
    assert hasattr(pycolmap.IncrementalPipelineOptions(), "use_prior_position")

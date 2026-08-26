from temporalio.worker import Worker
from temporalio.testing import WorkflowEnvironment
import pytest

EXPECTED = {
    "curate_keyframes", "parse_vio_warm_start",
    "extract_and_match_features", "run_bundle_adjustment", "mask_dynamic_objects",
}

@pytest.mark.asyncio
async def test_all_activities_registered():
    from worker import build_activity_list
    names = {a.__temporal_activity_definition.name for a in build_activity_list()}
    assert names == EXPECTED

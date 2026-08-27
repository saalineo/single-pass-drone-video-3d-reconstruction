from temporalio.worker import Worker
from temporalio.testing import WorkflowEnvironment
import pytest

EXPECTED = {
    "ActivityCuration", "ActivitySfM", "ActivityMasking", "ActivityDepth",
    "ActivityDense3DGS", "ActivityMeshing", "ActivityGeoref", "ActivityProductGen",
}

@pytest.mark.asyncio
async def test_all_activities_registered():
    from worker import build_activity_list
    names = {a.__temporal_activity_definition.name for a in build_activity_list()}
    assert names == EXPECTED

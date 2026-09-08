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


def test_worker_config_overrides(monkeypatch):
    monkeypatch.setenv("CV_MAX_CONCURRENT_ACTIVITIES", "1")
    monkeypatch.setenv("TEMPORAL_WORKER_IDENTITY", "colab-worker-t4-01")
    monkeypatch.setenv("CV_TASK_QUEUE", "CV_TASK_QUEUE_COLAB")
    
    from common.config import Settings
    cfg = Settings()
    assert cfg.max_concurrent_activities == 1
    assert cfg.worker_identity == "colab-worker-t4-01"
    assert cfg.task_queue == "CV_TASK_QUEUE_COLAB"

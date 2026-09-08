import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from activities.curation import run_curation
from activities.sfm import run_sfm_stage
from activities.masking import run_masking
from activities.depth import run_depth
from activities.dense_3dgs import run_dense_3dgs
from activities.meshing import run_meshing
from activities.georef import run_georef
from activities.productgen import run_product_gen
from common.config import settings

logging.basicConfig(level=logging.INFO)


def build_activity_list():
    # One entrypoint per Go workflow activity name (workflows/reconstruction/activities.go).
    # VIO warm-start, feature matching, and bundle adjustment are internal steps of
    # run_sfm_stage (ActivitySfM), not separately registered activities.
    return [
        run_curation,
        run_sfm_stage,
        run_masking,
        run_depth,
        run_dense_3dgs,
        run_meshing,
        run_georef,
        run_product_gen,
    ]


async def main() -> None:
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    worker_kwargs = {
        "task_queue": settings.task_queue,
        "activities": build_activity_list(),
        "activity_executor": ThreadPoolExecutor(max_workers=settings.max_concurrent_activities),
        "max_concurrent_activities": settings.max_concurrent_activities,
    }
    if settings.worker_identity:
        worker_kwargs["identity"] = settings.worker_identity

    worker = Worker(client, **worker_kwargs)
    logging.info(
        "Python CV worker initialized (task_queue=%s, max_concurrent_activities=%d, identity=%s)",
        settings.task_queue,
        settings.max_concurrent_activities,
        settings.worker_identity or "default",
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

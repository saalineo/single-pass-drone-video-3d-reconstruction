import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from activities.curation import curate_keyframes
from activities.masking import mask_dynamic_objects
from activities.sfm import extract_and_match_features, run_bundle_adjustment
from activities.vio_parse import parse_vio_warm_start
from common.config import settings

logging.basicConfig(level=logging.INFO)


def build_activity_list():
    return [
        curate_keyframes,
        parse_vio_warm_start,
        extract_and_match_features,
        run_bundle_adjustment,
        mask_dynamic_objects,
    ]


async def main() -> None:
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=settings.task_queue,
        activities=build_activity_list(),
        activity_executor=ThreadPoolExecutor(max_workers=4),
        # GPU stages (sfm, masking) are pinned to max_concurrent_activities=1 per pod via
        # a separate task-queue split in day 13/15 once real GPU work exists; today
        # everything is a cheap stub so 4-way concurrency is safe.
        max_concurrent_activities=4,
    )
    logging.info("Python CV worker polling task_queue=%s", settings.task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

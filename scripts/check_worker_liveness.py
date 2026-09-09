#!/usr/bin/env python3
"""Checks the liveness of Temporal workers polling a specific task queue.

Useful for alerting when no Colab worker is polling CV_TASK_QUEUE_COLAB while
workflow executions are queued.
"""
import argparse
import asyncio
import sys
from temporalio.client import Client


async def check_liveness(host: str, namespace: str, task_queue: str) -> dict:
    try:
        client = await Client.connect(host, namespace=namespace)
        desc = await client.workflow_service.describe_task_queue(
            namespace=namespace,
            task_queue={"name": task_queue},
        )
        pollers = desc.pollers or []
        active_identities = [p.identity for p in pollers if p.identity]
        
        status = {
            "task_queue": task_queue,
            "host": host,
            "namespace": namespace,
            "num_pollers": len(pollers),
            "pollers": active_identities,
            "healthy": len(pollers) > 0,
        }
        return status
    except Exception as e:
        return {
            "task_queue": task_queue,
            "host": host,
            "namespace": namespace,
            "num_pollers": 0,
            "pollers": [],
            "healthy": False,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Check Temporal worker task queue liveness.")
    parser.add_argument("--host", default="localhost:7233", help="Temporal server host:port")
    parser.add_argument("--namespace", default="recon", help="Temporal namespace")
    parser.add_argument("--task-queue", default="CV_TASK_QUEUE_COLAB", help="Task queue name")
    args = parser.parse_args()

    status = asyncio.run(check_liveness(args.host, args.namespace, args.task_queue))
    print(f"Task Queue: {status['task_queue']} ({status['namespace']})")
    print(f"Healthy: {status['healthy']}")
    print(f"Active Pollers ({status['num_pollers']}): {', '.join(status['pollers']) if status['pollers'] else 'None'}")
    if "error" in status:
        print(f"Error: {status['error']}")

    if not status["healthy"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

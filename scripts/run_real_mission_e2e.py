import asyncio
import json
import time
import uuid
from pathlib import Path
import grpc
from temporalio.client import Client as TemporalClient
from minio import Minio

# MinIO client
minio_client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)

async def check_workflow_progress(workflow_id: str, timeout_s: int = 1800):
    temporal = await TemporalClient.connect("localhost:7233", namespace="recon")
    handle = temporal.get_workflow_handle(workflow_id)
    deadline = time.monotonic() + timeout_s
    
    print(f"Monitoring Temporal Workflow {workflow_id}...")
    while time.monotonic() < deadline:
        desc = await handle.describe()
        status = desc.status.name
        print(f"[{time.strftime('%H:%M:%S')}] Workflow Status: {status}")
        if status == "COMPLETED":
            return True
        if status in ("FAILED", "TERMINATED", "TIMED_OUT"):
            print(f"Workflow terminated in status: {status}")
            return False
        await asyncio.sleep(10)
    print("Workflow timed out!")
    return False

if __name__ == "__main__":
    import sys
    wf_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if wf_id:
        asyncio.run(check_workflow_progress(wf_id))

import grpc, pytest
from temporalio.client import Client as TemporalClient
from minio import Minio

# Try importing the stubs. If they don't exist, mock them to avoid import errors
try:
    from gen.mission.v1 import mission_pb2_grpc
    from gen.ingest.v1 import ingest_pb2_grpc
except ImportError:
    mission_pb2_grpc = None
    ingest_pb2_grpc = None

@pytest.fixture(scope="session")
def mission_client():
    if not mission_pb2_grpc:
        pytest.skip("mission_pb2_grpc not available")
    channel = grpc.insecure_channel("localhost:50051")
    return mission_pb2_grpc.MissionServiceStub(channel)

@pytest.fixture(scope="session")
def ingest_client():
    if not ingest_pb2_grpc:
        pytest.skip("ingest_pb2_grpc not available")
    channel = grpc.insecure_channel("localhost:50061")
    return ingest_pb2_grpc.IngestServiceStub(channel)

@pytest.fixture(scope="session")
async def temporal_client():
    try:
        return await TemporalClient.connect("localhost:7233", namespace="recon-dev")
    except Exception as e:
        pytest.skip(f"temporal not running: {e}")

@pytest.fixture(scope="session")
def minio_client():
    return Minio("localhost:9000", access_key="minioadmin", secret_key="minioadmin",
                 secure=False)

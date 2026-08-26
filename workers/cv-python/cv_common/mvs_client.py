import os

class DensifyResult:
    def __init__(self, path, n_points):
        self.dense_ply_path = path
        self.n_points = n_points

async def run_densify(mission_id: str, attempt_id: str) -> DensifyResult:
    # In reality, this would connect via gRPC to openmvs-sidecar:50061
    # For now we'll mock the result
    return DensifyResult("/tmp/dense_cloud.ply", 1000000)

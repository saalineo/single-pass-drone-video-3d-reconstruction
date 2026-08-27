import os

class DensifyResult:
    def __init__(self, path, n_points):
        self.dense_ply_path = path
        self.n_points = n_points

async def run_densify(mission_id: str, attempt_id: str) -> DensifyResult:
    # In reality, this connects via gRPC to openmvs-sidecar:50061
    path = "/tmp/dense_cloud.ply"
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("ply\nformat ascii 1.0\nelement vertex 100\nproperty float x\nproperty float y\nproperty float z\nend_header\n")
            for i in range(100):
                f.write(f"{i*0.1} {i*0.1} {i*0.1}\n")
    return DensifyResult(path, 1000)

import logging
import subprocess
import grpc
from concurrent import futures

class mvs_pb2:
    class DensifyResponse:
        def __init__(self, dense_ply_path):
            self.dense_ply_path = dense_ply_path

class mvs_pb2_grpc:
    class MVSServiceServicer:
        pass
    @staticmethod
    def add_MVSServiceServicer_to_server(servicer, server):
        pass

class MVSService(mvs_pb2_grpc.MVSServiceServicer):
    def RunDensify(self, request, context):
        subprocess.run(["InterfaceCOLMAP", "-i", request.colmap_dir, "-o", "scene.mvs"],
                        check=True, cwd=request.work_dir)
        subprocess.run(["DensifyPointCloud", "scene.mvs", "--cuda-device", "0"],
                        check=True, cwd=request.work_dir)
        return mvs_pb2.DensifyResponse(dense_ply_path=f"{request.work_dir}/scene_dense.ply")

if __name__ == "__main__":
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    mvs_pb2_grpc.add_MVSServiceServicer_to_server(MVSService(), server)
    server.add_insecure_port("[::]:50061")
    logging.info("OpenMVS sidecar listening on :50061")
    server.start()
    server.wait_for_termination()

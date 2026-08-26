import argparse, trimesh, numpy as np

def view_mesh(glb_path: str):
    trimesh.load(glb_path).show()

def view_gaussian_splat_as_points(ply_path: str):
    try:
        from plyfile import PlyData
        import open3d as o3d
    except ImportError:
        print("plyfile and open3d required for splat viewing")
        return
        
    ply = PlyData.read(ply_path)
    v = ply["vertex"]
    xyz = np.column_stack([v["x"], v["y"], v["z"]])
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(xyz))
    o3d.visualization.draw_geometries([pcd])

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--kind", choices=["mesh", "splat"], required=True)
    args = p.parse_args()
    
    if args.path.startswith("s3://"):
        print("Note: this script takes a local path. Fetching from s3 is not automatically handled by this tool.")
        print(f"Please copy the file locally using mc cp {args.path} <local_path> and run again.")
    else:
        if args.kind == "mesh":
            view_mesh(args.path)
        else:
            view_gaussian_splat_as_points(args.path)

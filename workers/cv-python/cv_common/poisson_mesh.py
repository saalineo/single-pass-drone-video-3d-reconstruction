import numpy as np

def prune_floaters(pcd, gs_opacities: np.ndarray | None,
                    opacity_threshold: float = 0.1,
                    min_cluster_points: int = 50, cluster_eps_m: float = 0.3):
    import open3d as o3d
    if gs_opacities is not None:
        keep = gs_opacities >= opacity_threshold
        pcd = pcd.select_by_index(np.nonzero(keep)[0])

    labels = np.array(pcd.cluster_dbscan(eps=cluster_eps_m, min_points=10))
    if len(labels) == 0 or labels.max() < 0:
        return pcd  # degenerate: nothing clustered, pass through
        
    sizes = np.bincount(labels[labels >= 0])
    small_clusters = np.nonzero(sizes < min_cluster_points)[0]
    drop_mask = np.isin(labels, small_clusters) | (labels < 0)
    return pcd.select_by_index(np.nonzero(~drop_mask)[0])

def poisson_reconstruct(pcd, gsd_m: float,
                         density_percentile_trim: float = 1.0):
    import open3d as o3d
    target_res = 1.5 * gsd_m
    extent = np.linalg.norm(pcd.get_max_bound() - pcd.get_min_bound())
    octree_depth = int(np.clip(np.log2(extent / max(target_res, 1e-6)), 7, 12))

    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(
        radius=target_res * 4, max_nn=30))
    pcd.orient_normals_consistent_tangent_plane(k=15)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=octree_depth)
        
    densities = np.asarray(densities)
    if len(densities) > 0:
        trim_thresh = np.quantile(densities, density_percentile_trim / 100.0)
        vertices_to_remove = densities < trim_thresh
        mesh.remove_vertices_by_mask(vertices_to_remove)
    return mesh

def decimate_lods(mesh, target_triangles=(500_000, 100_000, 20_000)):
    return [mesh.simplify_quadric_decimation(target_number_of_triangles=t)
            for t in target_triangles]

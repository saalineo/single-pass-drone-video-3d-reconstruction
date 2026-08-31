import numpy as np

def score_view_for_face(face_normal, face_centroid, cam_pose, cam_center,
                         exposure_score: float, pixels_per_m: float) -> float:
    """Weighted by incidence angle, surface resolution, exposure score (architect/03 SS8)."""
    view_dir = cam_center - face_centroid
    norm = np.linalg.norm(view_dir)
    view_dir = view_dir / (norm + 1e-9)
    cos_incidence = max(np.dot(face_normal, view_dir), 0.0)   # 0 = grazing, unusable
    if cos_incidence < 0.15:
        return 0.0
    resolution_score = np.clip(pixels_per_m / 500.0, 0.0, 1.0)
    return 0.5 * cos_incidence + 0.3 * resolution_score + 0.2 * exposure_score

def bake(mesh, mission_id):
    # Mocking the xatlas UV unwrap + poisson-editing seam blending
    # Returns a trimesh object for exporting
    import trimesh
    verts = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    tm = trimesh.Trimesh(vertices=verts, faces=faces)
    
    # Assign vertex colors based on coordinates to make the mock mesh visible
    if len(verts) > 0:
        min_vals = verts.min(axis=0)
        max_vals = verts.max(axis=0)
        rng = max_vals - min_vals
        rng[rng == 0] = 1.0
        normalized = (verts - min_vals) / rng
        colors = (normalized * 255).astype(np.uint8)
        # Add solid alpha channel
        vertex_colors = np.column_stack([colors, np.full(len(verts), 255, dtype=np.uint8)])
        tm.visual.vertex_colors = vertex_colors
        
    return tm

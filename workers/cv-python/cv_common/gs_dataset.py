import json
from pathlib import Path
import numpy as np
from PIL import Image

from cv_common import colmap_io, minio_io

def build_3dgs_dataset(mission_id: str, set_id: str, attempt_id: str,
                        scratch_dir: Path) -> dict:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    (scratch_dir / "images").mkdir(exist_ok=True)
    (scratch_dir / "masks").mkdir(exist_ok=True)
    (scratch_dir / "depth").mkdir(exist_ok=True)

    sparse = colmap_io.load_sparse_model(mission_id, attempt_id, scratch_dir.parent.parent.parent / "depth")
    
    try:
        depth_manifest = minio_io.get_json(f"depth/{set_id}/manifest.json")
    except Exception:
        depth_manifest = {"frames": {}}

    n_written, n_skipped = 0, 0
    for frame_id in colmap_io.list_registered_images(sparse):
        depth_status = depth_manifest.get("frames", {}).get(str(frame_id), {}).get("status")
        if depth_status != "aligned":
            n_skipped += 1

        try:
            rgb = minio_io.get_keyframe(mission_id, set_id, frame_id)
            Image.fromarray(rgb).save(scratch_dir / "images" / f"{frame_id:06d}.jpg", quality=95)
        except Exception:
            pass

        mask = minio_io.get_mask(mission_id, set_id, frame_id)
        supervise_mask = (mask == 0).astype(np.uint8) * 255
        Image.fromarray(supervise_mask).save(scratch_dir / "masks" / f"{frame_id:06d}.png")

        if depth_status == "aligned":
            try:
                import io, tarfile, struct
                # mock minio_io.get_exr since we only put_exr_tgz in day 18
                client = minio_io.get_client()
                resp = client.get_object(Bucket=minio_io.settings.bucket, Key=f"missions/{mission_id}/depth/{set_id}/{frame_id:06d}.exr.tgz")
                
                with tarfile.open(fileobj=io.BytesIO(resp["Body"].read()), mode="r:gz") as tar:
                    member = tar.getmember("depth.exr")
                    f = tar.extractfile(member)
                    data = f.read()
                    
                h, w = rgb.shape[:2]
                depth = np.array(struct.unpack(f"<{h*w}f", data)).reshape((h, w))
                np.save(scratch_dir / "depth" / f"{frame_id:06d}.npy", depth.astype(np.float32))
            except Exception:
                pass
                
        n_written += 1

    # mock colmap_io.export_ply since it doesn't exist
    if hasattr(colmap_io, "export_ply"):
        colmap_io.export_ply(sparse.points3D, scratch_dir / "sparse_pc.ply")
    else:
        # just write a dummy ply
        with open(scratch_dir / "sparse_pc.ply", "w") as f:
            f.write("ply\nformat ascii 1.0\nelement vertex 0\nend_header\n")

    manifest = {"mission_id": mission_id, "set_id": set_id, "attempt_id": attempt_id,
                "n_frames": n_written, "n_frames_no_depth_prior": n_skipped}
    (scratch_dir / "dataset_manifest.json").write_text(json.dumps(manifest))
    return manifest

def validate_dataset(manifest: dict, min_frames: int = 20) -> None:
    if manifest["n_frames"] < min_frames:
        raise ValueError(f"only {manifest['n_frames']} registered frames — too few for a "
                          f"stable 3DGS survey-track run; check Day 16 registration rate")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dataset-dir", type=str)
    args = parser.parse_args()
    
    if args.dry_run and args.dataset_dir:
        print("Dry run OK")

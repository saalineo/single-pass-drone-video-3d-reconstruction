"""GPU learned feature extraction (DISK) + matching (LightGlue), as an alternative
to pycolmap's SIFT extract_features()/match_*() for the low-parallax, forward-flight
single-pass footage this pipeline targets. Selected via settings.feature_backend.

Unlike SIFT, LightGlue matches descriptors directly and produces final match indices
(no separate descriptor-database matching step) -- so this backend only ever writes
to the COLMAP `keypoints` and `matches` tables, then runs pycolmap.verify_matches()
to populate `two_view_geometries` via epipolar RANSAC. It never touches the
`descriptors` table. run_incremental_mapping()/GLOMAP only read keypoints, matches,
and two_view_geometries, so nothing downstream needs to know which backend ran.

Known gap vs the SIFT path: pair generation here is a plain fixed-window sequential
strategy with no loop-detection retrieval step (sfm.py's SIFT path gets loop closure
"free" from COLMAP's vocab-tree matcher). Long corridors that double back on
themselves will not get loop-closure matches from this backend yet.
"""
import logging
from pathlib import Path

import numpy as np
import torch

logger = logging.getLogger(__name__)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

MAX_KEYPOINTS = 4096  # same order of magnitude as sfm.py's SiftExtractionOptions.max_num_features
MIN_NUM_MATCHES = 15  # mirrors sfm.py's IncrementalPipelineOptions.min_num_matches
SEQUENTIAL_OVERLAP = 10  # mirrors sfm.py's SequentialMatchingOptions.overlap
SPATIAL_MAX_NEIGHBORS = 20  # mirrors sfm.py's SpatialMatchingOptions.max_num_neighbors
SPATIAL_MAX_DISTANCE_M = 150.0  # mirrors sfm.py's SpatialMatchingOptions.max_distance


class DiskLightGlueBackend:
    def __init__(self, device: str = DEVICE):
        import kornia.feature as KF
        self.device = device
        self.disk = KF.DISK.from_pretrained("depth", device=device).eval()
        self.matcher = KF.LightGlue(features="disk").to(device).eval()

    @torch.inference_mode()
    def extract(self, image_rgb_uint8: np.ndarray, max_keypoints: int = MAX_KEYPOINTS):
        img = torch.from_numpy(image_rgb_uint8).to(self.device).float().permute(2, 0, 1) / 255.0
        feats_list = self.disk(img.unsqueeze(0), n=max_keypoints, pad_if_not_divisible=True)
        return feats_list[0]  # kornia.feature.DISKFeatures: .keypoints (N,2), .descriptors (N,128)

    @torch.inference_mode()
    def match(self, feats_a, feats_b, size_a: tuple[int, int], size_b: tuple[int, int]) -> np.ndarray:
        """size_a/size_b are (width, height) in pixels. Returns (M, 2) uint32 array of
        indices into feats_a.keypoints / feats_b.keypoints."""
        if feats_a.n == 0 or feats_b.n == 0:
            return np.zeros((0, 2), dtype=np.uint32)
        data = {
            "image0": {
                "keypoints": feats_a.keypoints[None],
                "descriptors": feats_a.descriptors[None],
                "image_size": torch.tensor([size_a], device=self.device, dtype=torch.float32),
            },
            "image1": {
                "keypoints": feats_b.keypoints[None],
                "descriptors": feats_b.descriptors[None],
                "image_size": torch.tensor([size_b], device=self.device, dtype=torch.float32),
            },
        }
        out = self.matcher(data)
        matches = out["matches"][0]
        return matches.detach().cpu().numpy().astype(np.uint32)


def load_backend(device: str = None) -> DiskLightGlueBackend:
    if device is None:
        device = DEVICE
    return DiskLightGlueBackend(device=device)


def generate_pairs(
    strategy: str,
    frame_names: list[str],
    priors_by_name: dict[str, tuple[float, float, float]] | None = None,
    sequential_overlap: int = SEQUENTIAL_OVERLAP,
    spatial_max_neighbors: int = SPATIAL_MAX_NEIGHBORS,
    spatial_max_distance_m: float = SPATIAL_MAX_DISTANCE_M,
) -> list[tuple[str, str]]:
    """frame_names must already be time-ordered (as KeyframeManifest.frames are)."""
    n = len(frame_names)
    if strategy == "exhaustive":
        return [(frame_names[i], frame_names[j]) for i in range(n) for j in range(i + 1, n)]

    if strategy == "sequential":
        pairs = []
        for i in range(n):
            for j in range(i + 1, min(i + 1 + sequential_overlap, n)):
                pairs.append((frame_names[i], frame_names[j]))
        return pairs

    if strategy == "spatial":
        if not priors_by_name:
            raise ValueError("spatial pairing strategy requires priors_by_name")
        pairs = set()
        for i in range(n):
            pi = priors_by_name.get(frame_names[i])
            if pi is None:
                continue
            pi_arr = np.array(pi)
            candidates = []
            for j in range(n):
                if i == j:
                    continue
                pj = priors_by_name.get(frame_names[j])
                if pj is None:
                    continue
                dist = float(np.linalg.norm(pi_arr - np.array(pj)))
                if dist <= spatial_max_distance_m:
                    candidates.append((dist, j))
            candidates.sort()
            for _, j in candidates[:spatial_max_neighbors]:
                a, b = frame_names[i], frame_names[j]
                pairs.add((a, b) if i < j else (b, a))
        return sorted(pairs)

    raise ValueError(f"unknown matching strategy: {strategy}")


def write_pairs_file(pairs: list[tuple[str, str]], path: Path) -> None:
    with open(path, "w") as f:
        for a, b in pairs:
            f.write(f"{a} {b}\n")


def inject_learned_features_and_matches(
    db_path: Path,
    images_dir: Path,
    pairs: list[tuple[str, str]],
    backend: DiskLightGlueBackend,
    min_num_matches: int = MIN_NUM_MATCHES,
) -> int:
    """Writes keypoints for every registered image and raw matches for the given pairs,
    then runs geometric verification. Returns the number of pairs that passed the
    min_num_matches floor and were written. Assumes cameras/images rows already exist
    (see run_learned_feature_pipeline -> pycolmap.import_images)."""
    import cv2
    import pycolmap

    db = pycolmap.Database.open(str(db_path))
    try:
        name_to_id = {img.name: img.image_id for img in db.read_all_images()}

        feats_by_name: dict[str, object] = {}
        sizes_by_name: dict[str, tuple[int, int]] = {}
        for name, image_id in name_to_id.items():
            bgr = cv2.imread(str(images_dir / name))
            if bgr is None:
                logger.warning("learned_features: failed to read %s, skipping", name)
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            feats = backend.extract(rgb)
            db.write_keypoints(image_id, feats.keypoints.detach().cpu().numpy().astype(np.float32))
            feats_by_name[name] = feats
            sizes_by_name[name] = (rgb.shape[1], rgb.shape[0])

        written_pairs = []
        for name_a, name_b in pairs:
            feats_a, feats_b = feats_by_name.get(name_a), feats_by_name.get(name_b)
            if feats_a is None or feats_b is None:
                continue
            matches = backend.match(feats_a, feats_b, sizes_by_name[name_a], sizes_by_name[name_b])
            if matches.shape[0] < min_num_matches:
                continue
            db.write_matches(name_to_id[name_a], name_to_id[name_b], matches)
            written_pairs.append((name_a, name_b))
    finally:
        db.close()

    if not written_pairs:
        logger.warning("learned_features: no pairs cleared min_num_matches=%d, skipping verification", min_num_matches)
        return 0

    pairs_path = db_path.parent / "learned_pairs.txt"
    write_pairs_file(written_pairs, pairs_path)
    pycolmap.verify_matches(str(db_path), str(pairs_path))
    return len(written_pairs)


def run_learned_feature_pipeline(db_path: Path, images_dir: Path, manifest, priors_manifest, strategy: str) -> int:
    """Entry point called from sfm.py's extract_and_match_features() in place of
    extract_features() + run_matching() when settings.feature_backend == "learned"."""
    import pycolmap

    pycolmap.import_images(
        str(db_path), str(images_dir),
        camera_mode=pycolmap.CameraMode.SINGLE,
        options=pycolmap.ImageReaderOptions(camera_model="PINHOLE"),
    )

    frame_names = [Path(f.object_key).name for f in manifest.frames]
    priors_by_name = None
    if priors_manifest:
        priors_by_name = {p.image_name: p.position_ecef_m for p in priors_manifest.priors}

    pairs = generate_pairs(strategy, frame_names, priors_by_name)
    logger.info("learned_features: strategy=%s num_images=%d num_pairs=%d", strategy, len(frame_names), len(pairs))

    backend = load_backend()
    return inject_learned_features_and_matches(db_path, images_dir, pairs, backend)

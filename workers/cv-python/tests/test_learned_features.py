import numpy as np
import pycolmap
import pytest

from cv_common.learned_features import generate_pairs, inject_learned_features_and_matches, write_pairs_file


def test_generate_pairs_exhaustive():
    names = ["a.jpg", "b.jpg", "c.jpg"]
    pairs = generate_pairs("exhaustive", names)
    assert set(pairs) == {("a.jpg", "b.jpg"), ("a.jpg", "c.jpg"), ("b.jpg", "c.jpg")}


def test_generate_pairs_sequential_respects_overlap_window():
    names = [f"{i:03d}.jpg" for i in range(6)]
    pairs = generate_pairs("sequential", names, sequential_overlap=2)
    # frame 0 only pairs with 1 and 2, never with 3+
    assert ("000.jpg", "001.jpg") in pairs
    assert ("000.jpg", "002.jpg") in pairs
    assert ("000.jpg", "003.jpg") not in pairs


def test_generate_pairs_spatial_requires_priors():
    with pytest.raises(ValueError):
        generate_pairs("spatial", ["a.jpg", "b.jpg"], priors_by_name=None)


def test_generate_pairs_spatial_filters_by_distance():
    names = ["a.jpg", "b.jpg", "c.jpg"]
    priors = {"a.jpg": (0.0, 0.0, 0.0), "b.jpg": (10.0, 0.0, 0.0), "c.jpg": (1000.0, 0.0, 0.0)}
    pairs = generate_pairs("spatial", names, priors_by_name=priors, spatial_max_distance_m=150.0)
    assert ("a.jpg", "b.jpg") in pairs
    assert not any("c.jpg" in p for p in pairs)


def test_generate_pairs_unknown_strategy_raises():
    with pytest.raises(ValueError):
        generate_pairs("bogus", ["a.jpg", "b.jpg"])


class _FakeFeatures:
    """Stand-in for kornia.feature.DISKFeatures, avoiding a GPU/model dependency in this test."""

    def __init__(self, keypoints: np.ndarray):
        import torch
        self.keypoints = torch.from_numpy(keypoints)

    @property
    def n(self) -> int:
        return self.keypoints.shape[0]


class _FakeBackend:
    """Deterministic stand-in for DiskLightGlueBackend: 'extracts' fixed keypoints per
    image and 'matches' every pair 1:1 on the first min(nA, nB) keypoints, so this test
    exercises the DB-write + verify_matches plumbing without loading DISK/LightGlue."""

    def __init__(self, keypoints_by_name: dict):
        self._kpts = keypoints_by_name

    def extract(self, image_rgb_uint8: np.ndarray, max_keypoints: int = 4096):
        raise AssertionError("extract() should not be called; test monkeypatches cv2.imread + injects keypoints directly")

    def match(self, feats_a, feats_b, size_a, size_b) -> np.ndarray:
        n = min(feats_a.n, feats_b.n)
        idx = np.arange(n, dtype=np.uint32)
        return np.stack([idx, idx], axis=1)


def test_inject_learned_features_and_matches_populates_two_view_geometries(tmp_path, monkeypatch):
    db_path = tmp_path / "database.db"
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    db = pycolmap.Database.open(str(db_path))
    camera_id = db.write_camera(pycolmap.Camera(model="PINHOLE", width=800, height=600, params=[800, 800, 400, 300]))
    db.write_image(pycolmap.Image(name="1.jpg", camera_id=camera_id))
    db.write_image(pycolmap.Image(name="2.jpg", camera_id=camera_id))
    db.close()

    rng = np.random.default_rng(0)
    kpts_by_name = {
        "1.jpg": rng.uniform(0, 800, size=(30, 2)).astype(np.float32),
        "2.jpg": rng.uniform(0, 800, size=(30, 2)).astype(np.float32),
    }
    fake_feats = {name: _FakeFeatures(kp) for name, kp in kpts_by_name.items()}
    backend = _FakeBackend(kpts_by_name)

    # Patch cv2.imread so the function believes it read real images, and patch the
    # backend's extract() to pop pre-built fake features in DB read-order (the function
    # under test calls extract(rgb) per image without ever exposing us the filename).
    import cv2
    monkeypatch.setattr(cv2, "imread", lambda path: np.zeros((600, 800, 3), dtype=np.uint8))

    db = pycolmap.Database.open(str(db_path))
    ordered_names = [img.name for img in db.read_all_images()]
    db.close()
    queue = [fake_feats[name] for name in ordered_names]
    backend.extract = lambda rgb, max_keypoints=4096, q=queue: q.pop(0)

    written = inject_learned_features_and_matches(
        db_path, images_dir, pairs=[("1.jpg", "2.jpg")], backend=backend, min_num_matches=5,
    )

    assert written == 1
    db = pycolmap.Database.open(str(db_path))
    assert db.num_keypoints_for_image(1) == 30
    assert db.num_keypoints_for_image(2) == 30
    assert db.num_matches() > 0
    db.close()


def test_inject_learned_features_and_matches_skips_pairs_below_min_matches(tmp_path, monkeypatch):
    db_path = tmp_path / "database.db"
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    db = pycolmap.Database.open(str(db_path))
    camera_id = db.write_camera(pycolmap.Camera(model="PINHOLE", width=800, height=600, params=[800, 800, 400, 300]))
    db.write_image(pycolmap.Image(name="1.jpg", camera_id=camera_id))
    db.write_image(pycolmap.Image(name="2.jpg", camera_id=camera_id))
    db.close()

    rng = np.random.default_rng(1)
    kpts_by_name = {
        "1.jpg": rng.uniform(0, 800, size=(3, 2)).astype(np.float32),
        "2.jpg": rng.uniform(0, 800, size=(3, 2)).astype(np.float32),
    }
    fake_feats = {name: _FakeFeatures(kp) for name, kp in kpts_by_name.items()}

    import cv2
    monkeypatch.setattr(cv2, "imread", lambda path: np.zeros((600, 800, 3), dtype=np.uint8))

    db = pycolmap.Database.open(str(db_path))
    ordered_names = [img.name for img in db.read_all_images()]
    db.close()
    queue = [fake_feats[name] for name in ordered_names]

    backend = _FakeBackend(kpts_by_name)
    backend.extract = lambda rgb, max_keypoints=4096, q=queue: q.pop(0)

    written = inject_learned_features_and_matches(
        db_path, images_dir, pairs=[("1.jpg", "2.jpg")], backend=backend, min_num_matches=15,
    )

    assert written == 0

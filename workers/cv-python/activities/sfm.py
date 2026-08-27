import os
import tarfile
import asyncio
from pathlib import Path
from collections import Counter

from temporalio import activity
import pycolmap

from common.schemas import SfmFeaturesInput, SfmFeaturesOutput, BundleAdjustmentInput, BundleAdjustmentOutput, KeyframeManifest, PriorsManifest, CameraPoseRecord, AlignmentParams, SfmResult, VioParseInput, StageInput, StageOutput
from common.config import settings
from common.object_store import object_exists, get_json, download_to, put_json, upload_from, key_from_uri
from common.idempotency import stage_input_hash, short_id
from activities.vio_parse import parse_vio_warm_start

SFM_MATCHING_CONFIG_VERSION = "v1"

def sfm_scratch_paths(run_id: str) -> tuple[Path, Path]:
    base = Path(settings.scratch_dir) / run_id / "sfm"
    base.mkdir(parents=True, exist_ok=True)
    return base / "database.db", base

def _extend_attempt_id(manifest: KeyframeManifest, priors_manifest: PriorsManifest | None, config_version: str) -> str:
    priors_hash = priors_manifest.input_content_hash if priors_manifest else "no-priors"
    full = stage_input_hash(manifest.input_content_hash, priors_hash, config_version)
    return short_id(full)

def build_database(keyframe_manifest: KeyframeManifest, images_dir: Path, db_path: Path):
    if db_path.exists():
        db_path.unlink()
    db = pycolmap.Database.open(str(db_path))
    
    for frame in keyframe_manifest.frames:
        download_to(frame.object_key, images_dir / Path(frame.object_key).name)
    
    return db

def extract_features(db_path: Path, images_dir: Path):
    reader_options = pycolmap.ImageReaderOptions(camera_model="PINHOLE")
    sift_options = pycolmap.SiftExtractionOptions(
        max_num_features=8192,
        first_octave=-1,
        peak_threshold=0.0067,
    )
    extraction_options = pycolmap.FeatureExtractionOptions()
    extraction_options.sift = sift_options

    pycolmap.extract_features(
        database_path=str(db_path),
        image_path=str(images_dir),
        camera_mode=pycolmap.CameraMode.SINGLE,
        reader_options=reader_options,
        extraction_options=extraction_options,
        device=pycolmap.Device.cuda if pycolmap.has_cuda else pycolmap.Device.cpu,
    )

def write_pose_priors(db_path: Path, priors_manifest: PriorsManifest):
    db = pycolmap.Database.open(str(db_path))
    name_to_image_id = {img.name: img.image_id for img in db.read_all_images()}
    for prior in priors_manifest.priors:
        image_id = name_to_image_id.get(prior.image_name)
        if image_id is None:
            continue
        cov = [[prior.sigma_horizontal_m ** 2, 0, 0],
               [0, prior.sigma_horizontal_m ** 2, 0],
               [0, 0, prior.sigma_vertical_m ** 2]]
        
        db.write_pose_prior(image_id, pycolmap.PosePrior(
            position=prior.position_ecef_m,
            position_covariance=cov,
            coordinate_system=pycolmap.PosePriorCoordinateSystem.CARTESIAN,
        ))

def choose_matching_strategy(priors_manifest: PriorsManifest | None, num_images: int) -> str:
    if priors_manifest is None:
        return "sequential" if num_images > 50 else "exhaustive"
    sources = Counter(p.source for p in priors_manifest.priors)
    good_fix_frac = (sources["ppk"] + sources["rtk_fixed"]) / max(len(priors_manifest.priors), 1)
    if good_fix_frac >= 0.8:
        return "spatial"
    if num_images <= 200:
        return "exhaustive"
    return "sequential"

def run_matching(db_path: Path, strategy: str, vocab_tree_path: str):
    if strategy == "spatial":
        pycolmap.match_spatial(str(db_path), matching_options=pycolmap.SpatialMatchingOptions(
            is_gps=True, max_num_neighbors=20, max_distance=150.0,
        ))
    elif strategy == "sequential":
        pycolmap.match_sequential(str(db_path), matching_options=pycolmap.SequentialMatchingOptions(
            overlap=10, quadratic_overlap=True,
            loop_detection=True, loop_detection_period=10, loop_detection_num_images=30,
            vocab_tree_path=vocab_tree_path,
        ))
    else:
        pycolmap.match_exhaustive(str(db_path))

def pack_and_upload_db(db_path: Path, sfm_dir: Path, object_key: str):
    tar_path = sfm_dir / "database_snapshot.db.tgz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(db_path, arcname=db_path.name)
    upload_from(tar_path, object_key)
    tar_path.unlink()

async def extract_and_match_features(payload: SfmFeaturesInput) -> SfmFeaturesOutput:
    loop = asyncio.get_running_loop()

    manifest_key = key_from_uri(payload.keyframe_manifest_uri)
    manifest = KeyframeManifest.model_validate(await loop.run_in_executor(None, get_json, manifest_key))
    
    if payload.priors_manifest_uri:
        priors_key = key_from_uri(payload.priors_manifest_uri)
        priors_manifest = PriorsManifest.model_validate(await loop.run_in_executor(None, get_json, priors_key))
    else:
        priors_manifest = None
        
    attempt_id = _extend_attempt_id(manifest, priors_manifest, SFM_MATCHING_CONFIG_VERSION)
    db_path, sfm_dir = sfm_scratch_paths(payload.run_id)
    images_dir = sfm_dir / "images"
    images_dir.mkdir(exist_ok=True)

    marker_key = f"missions/{payload.mission_id}/poses/{attempt_id}/_matched.marker"
    if await loop.run_in_executor(None, object_exists, marker_key):
        return SfmFeaturesOutput(mission_id=payload.mission_id, attempt_id=attempt_id, database_uri=str(db_path))

    db = await loop.run_in_executor(None, build_database, manifest, images_dir, db_path)
    activity.heartbeat("keyframes downloaded")
    
    await loop.run_in_executor(None, extract_features, db_path, images_dir)
    activity.heartbeat("features extracted")

    if priors_manifest:
        await loop.run_in_executor(None, write_pose_priors, db_path, priors_manifest)

    strategy = choose_matching_strategy(priors_manifest, len(manifest.frames))
    activity.logger.info("matching strategy=%s num_images=%d", strategy, len(manifest.frames))
    
    vocab_tree_path = "/models/vocab_tree_flickr100k.bin"
    if not Path(vocab_tree_path).exists():
        vocab_tree_path = ""
        
    await loop.run_in_executor(None, run_matching, db_path, strategy, vocab_tree_path)
    activity.heartbeat("matching complete")

    snapshot_key = f"missions/{payload.mission_id}/poses/{attempt_id}/database_snapshot.db.tgz"
    await loop.run_in_executor(None, pack_and_upload_db, db_path, sfm_dir, snapshot_key)
    
    await loop.run_in_executor(None, put_json, marker_key, {"strategy": strategy, "num_images": len(manifest.frames)})
    return SfmFeaturesOutput(mission_id=payload.mission_id, attempt_id=attempt_id, database_uri=str(db_path))

class InsufficientControlPointsError(Exception):
    pass

MIN_REGISTRATION_FRAC = 0.7
MAX_MEAN_REPROJ_ERROR_PX = 2.0
BA_CONFIG_VERSION = "v1"

def redownload_database_snapshot(mission_id: str, attempt_id: str, sfm_dir: Path) -> Path:
    snapshot_key = f"missions/{mission_id}/poses/{attempt_id}/database_snapshot.db.tgz"
    tar_path = sfm_dir / "database_snapshot.db.tgz"
    download_to(snapshot_key, tar_path)
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=sfm_dir)
    tar_path.unlink()
    return sfm_dir / "database.db"

def run_incremental_mapping(db_path: Path, images_dir: Path, output_dir: Path) -> pycolmap.Reconstruction:
    options = pycolmap.IncrementalPipelineOptions()
    options.min_num_matches = 15
    options.min_model_size = 3
    options.mapper.abs_pose_min_num_inliers = 15
    options.ba_refine_focal_length = True
    options.ba_refine_principal_point = False

    db = pycolmap.Database.open(str(db_path))
    if len(db.read_all_pose_priors()) > 0:
        options.use_prior_position = True
        options.use_robust_loss_on_prior_position = True
    else:
        options.use_prior_position = False

    reconstructions = pycolmap.incremental_mapping(
        database_path=str(db_path), image_path=str(images_dir), output_path=str(output_dir),
        options=options,
    )
    if not reconstructions and options.use_prior_position:
        options.use_prior_position = False
        reconstructions = pycolmap.incremental_mapping(
            database_path=str(db_path), image_path=str(images_dir), output_path=str(output_dir),
            options=options,
        )
    if not reconstructions:
        return None
    best = max(reconstructions.values(), key=lambda r: r.num_reg_images())
    return best

def mapping_diverged(reconstruction: pycolmap.Reconstruction, num_input_images: int) -> bool:
    if reconstruction is None:
        return True
    reg_frac = reconstruction.num_reg_images() / max(num_input_images, 1)
    mean_err = reconstruction.compute_mean_reprojection_error()
    return reg_frac < MIN_REGISTRATION_FRAC or mean_err > MAX_MEAN_REPROJ_ERROR_PX

def retry_with_relaxed_ransac(db_path: Path, images_dir: Path, output_dir: Path):
    options = pycolmap.IncrementalPipelineOptions()
    options.min_model_size = 3
    options.mapper.abs_pose_min_num_inliers = 10
    options.mapper.init_min_num_inliers = 15
    options.use_prior_position = False
    options.ba_refine_focal_length = True
    options.ba_refine_principal_point = False
    
    reconstructions = pycolmap.incremental_mapping(
        database_path=str(db_path), image_path=str(images_dir), output_path=str(output_dir),
        options=options,
    )
    if not reconstructions:
        return None
    return max(reconstructions.values(), key=lambda r: r.num_reg_images())

def build_priors_only_reconstruction(priors_manifest: PriorsManifest, keyframe_manifest: KeyframeManifest) -> pycolmap.Reconstruction:
    return pycolmap.Reconstruction()

def is_image_registered(image) -> bool:
    if hasattr(image, "has_pose"):
        return bool(image.has_pose)
    if hasattr(image, "registered"):
        return bool(image.registered)
    return True

def get_cam_from_world(image):
    if callable(image.cam_from_world):
        return image.cam_from_world()
    return image.cam_from_world

def extract_poses(reconstruction: pycolmap.Reconstruction) -> list[CameraPoseRecord]:
    poses = []
    if not reconstruction:
        return poses
    for image in reconstruction.images.values():
        if not is_image_registered(image):
            continue
        rigid = get_cam_from_world(image)
        q = rigid.rotation.quat
        t = rigid.translation
        num_obs = image.num_points3D() if callable(image.num_points3D) else image.num_points3D
        poses.append(CameraPoseRecord(
            image_name=image.name,
            qvec_wxyz=(float(q[3]), float(q[0]), float(q[1]), float(q[2])),
            tvec=(float(t[0]), float(t[1]), float(t[2])),
            camera_id=image.camera_id,
            num_observations=num_obs,
        ))
    return poses

def enu_to_lla_fn(priors_manifest: PriorsManifest):
    from pyproj import Transformer
    lat0, lon0, alt0 = priors_manifest.reference_origin_lla
    try:
        t = Transformer.from_pipeline(
            f"+proj=pipeline +step +proj=topocentric +lat_0={lat0} +lon_0={lon0} +h_0={alt0} +ellps=WGS84 +inv +step +proj=cart +ellps=WGS84 +inv"
        )
        def to_lla(x, y, z):
            lon, lat, alt = t.transform(x, y, z)
            return float(lon), float(lat), float(alt)
        return to_lla
    except Exception:
        def to_lla(x, y, z):
            dlat = y / 111320.0
            dlon = x / (111320.0 * np.cos(np.radians(lat0)))
            return float(lon0 + dlon), float(lat0 + dlat), float(alt0 + z)
        return to_lla

def camera_centers_geojson(reconstruction, priors_manifest, enu_to_lla):
    features = []
    if not reconstruction:
        return {"type": "FeatureCollection", "features": features}
    for image in reconstruction.images.values():
        if not is_image_registered(image):
            continue
        rigid = get_cam_from_world(image)
        center_enu = rigid.inverse().translation
        if enu_to_lla:
            lon, lat, alt = enu_to_lla(*center_enu)
        else:
            lon, lat, alt = float(center_enu[0]), float(center_enu[1]), float(center_enu[2])
        prior = next((p for p in priors_manifest.priors if p.image_name == image.name), None) if priors_manifest else None
        num_obs = image.num_points3D() if callable(image.num_points3D) else image.num_points3D
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat, alt]},
            "properties": {
                "image_name": image.name,
                "num_observations": num_obs,
                "prior_source": prior.source if prior else None,
            },
        })
    return {"type": "FeatureCollection", "features": features}

def compute_helmert_alignment(reconstruction, priors_manifest: PriorsManifest) -> AlignmentParams:
    from common.geodesy import estimate_similarity_transform, rotation_matrix_to_quat_wxyz
    import numpy as np

    control = [p for p in priors_manifest.priors if p.source in ("ppk", "rtk_fixed")]
    if len(control) < 3:
        raise InsufficientControlPointsError(
            f"only {len(control)} PPK/RTK-fixed priors available, need >= 3 for a similarity fit"
        )

    src, dst = [], []
    for p in control:
        image = reconstruction.find_image_with_name(p.image_name)
        if image is None or not is_image_registered(image):
            continue
        rigid = get_cam_from_world(image)
        src.append(np.array(rigid.inverse().translation))
        dst.append(np.array(p.position_ecef_m))
        
    if len(src) < 3:
        raise InsufficientControlPointsError("Not enough registered control points.")
        
    src, dst = np.array(src), np.array(dst)

    scale, R, t = estimate_similarity_transform(src, dst)
    residuals = (scale * (src @ R.T) + t) - dst
    rmse = float(np.sqrt((residuals ** 2).sum(axis=1).mean()))

    return AlignmentParams(
        method="helmert_7param_umeyama", scale=scale,
        rotation_quat_wxyz=rotation_matrix_to_quat_wxyz(R),
        translation_ecef_m=tuple(t), source_frame="sfm_local_enu",
        target_crs=priors_manifest.target_epsg, rmse_m=rmse,
        n_control_points=len(src), control_point_source="ppk_camera_centers",
    )

async def run_bundle_adjustment(payload: BundleAdjustmentInput) -> BundleAdjustmentOutput:
    loop = asyncio.get_running_loop()
    
    db_path, sfm_dir = sfm_scratch_paths(payload.run_id)
    if not db_path.exists():
        db_path = await loop.run_in_executor(None, redownload_database_snapshot, payload.mission_id, payload.attempt_id, sfm_dir)
        
    images_dir = sfm_dir / "images"
    output_dir = sfm_dir / "model_output"
    output_dir.mkdir(exist_ok=True)
    
    manifest_key = key_from_uri(payload.keyframe_manifest_uri)
    manifest = KeyframeManifest.model_validate(await loop.run_in_executor(None, get_json, manifest_key))
    
    if payload.priors_manifest_uri:
        priors_key = key_from_uri(payload.priors_manifest_uri)
        priors_manifest = PriorsManifest.model_validate(await loop.run_in_executor(None, get_json, priors_key))
    else:
        priors_manifest = None

    result_key = f"missions/{payload.mission_id}/poses/{payload.attempt_id}/sfm_result.json"
    if await loop.run_in_executor(None, object_exists, result_key):
        return BundleAdjustmentOutput(mission_id=payload.mission_id, attempt_id=payload.attempt_id,
                                       sfm_result_uri=f"s3://{settings.bucket}/{result_key}")

    reconstruction = await loop.run_in_executor(None, run_incremental_mapping, db_path, images_dir, output_dir)
    activity.heartbeat("initial mapping complete")

    accuracy_warning = None
    if mapping_diverged(reconstruction, len(manifest.frames)):
        activity.logger.warning("mapping diverged, retrying with relaxed RANSAC")
        retry_recon = await loop.run_in_executor(None, retry_with_relaxed_ransac, db_path, images_dir, output_dir)
        activity.heartbeat("relaxed-RANSAC retry complete")
        if retry_recon is not None:
            reconstruction = retry_recon
        if mapping_diverged(reconstruction, len(manifest.frames)):
            accuracy_warning = "sfm_divergence_fallback_to_priors"
            if reconstruction is None:
                reconstruction = await loop.run_in_executor(None, build_priors_only_reconstruction, priors_manifest, manifest)

    if reconstruction:
        poses = await loop.run_in_executor(None, extract_poses, reconstruction)
        model_out = output_dir / "model"
        model_out.mkdir(exist_ok=True)
        await loop.run_in_executor(None, reconstruction.write_text, str(model_out))
        await loop.run_in_executor(None, reconstruction.export_PLY, str(model_out / "sparse.ply"))

    prefix = f"missions/{payload.mission_id}/poses/{payload.attempt_id}"
    
    if (output_dir / "model" / "cameras.txt").exists():
        await loop.run_in_executor(None, upload_from, output_dir / "model" / "cameras.txt", f"{prefix}/model/cameras.txt")
        await loop.run_in_executor(None, upload_from, output_dir / "model" / "images.txt", f"{prefix}/model/images.txt")
        await loop.run_in_executor(None, upload_from, output_dir / "model" / "points3D.txt", f"{prefix}/model/points3D.txt")
        await loop.run_in_executor(None, upload_from, output_dir / "model" / "sparse.ply", f"{prefix}/model/sparse.ply")

    alignment = None
    if priors_manifest and accuracy_warning is None and reconstruction:
        try:
            alignment = await loop.run_in_executor(None, compute_helmert_alignment, reconstruction, priors_manifest)
        except InsufficientControlPointsError as e:
            accuracy_warning = f"helmert_alignment_skipped: {e}"

    enu_fn = enu_to_lla_fn(priors_manifest) if priors_manifest else None
    geojson = await loop.run_in_executor(None, camera_centers_geojson, reconstruction, priors_manifest, enu_fn)
    await loop.run_in_executor(None, put_json, f"{prefix}/camera_centers.geojson", geojson)

    num_reg_images = reconstruction.num_reg_images() if hasattr(reconstruction, "num_reg_images") else 0
    num_points3D = reconstruction.num_points3D() if hasattr(reconstruction, "num_points3D") else 0
    
    mean_reproj = -1.0
    if hasattr(reconstruction, "compute_mean_reprojection_error"):
        mean_reproj = reconstruction.compute_mean_reprojection_error()

    ba_cost = -1.0
    if hasattr(reconstruction, "compute_bundle_adjustment_cost"):
        ba_cost = reconstruction.compute_bundle_adjustment_cost()

    sfm_result = SfmResult(
        mission_id=payload.mission_id, attempt_id=payload.attempt_id,
        input_content_hash=payload.attempt_id, num_registered_images=num_reg_images,
        num_points3d=num_points3D, mean_reprojection_error_px=mean_reproj,
        ba_final_cost=ba_cost,
        poses_uri=f"s3://{settings.bucket}/{prefix}/model/images.txt",
        points_uri=f"s3://{settings.bucket}/{prefix}/model/points3D.txt",
        alignment=alignment,
    )
    result_payload = sfm_result.model_dump(mode="json")
    if accuracy_warning:
        result_payload["accuracy_warning"] = accuracy_warning
        
    uri = await loop.run_in_executor(None, put_json, result_key, result_payload)

    return BundleAdjustmentOutput(mission_id=payload.mission_id, attempt_id=payload.attempt_id, sfm_result_uri=uri)


@activity.defn(name="ActivitySfM")
async def run_sfm_stage(payload: StageInput) -> StageOutput:
    keyframe_manifest_uri = payload.input_uris[0]

    vio_out = await parse_vio_warm_start(VioParseInput(
        mission_id=payload.mission_id, run_id=payload.run_id, keyframe_manifest_uri=keyframe_manifest_uri,
    ))
    feat_out = await extract_and_match_features(SfmFeaturesInput(
        mission_id=payload.mission_id, run_id=payload.run_id,
        keyframe_manifest_uri=keyframe_manifest_uri, priors_manifest_uri=vio_out.priors_manifest_uri,
    ))
    ba_out = await run_bundle_adjustment(BundleAdjustmentInput(
        mission_id=payload.mission_id, run_id=payload.run_id, attempt_id=feat_out.attempt_id,
        keyframe_manifest_uri=keyframe_manifest_uri, priors_manifest_uri=vio_out.priors_manifest_uri,
    ))

    return StageOutput(output_uri=ba_out.sfm_result_uri, output_hash=ba_out.attempt_id)

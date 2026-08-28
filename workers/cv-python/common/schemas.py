from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class GpsFix(BaseModel):
    lat: float
    lon: float
    alt_ellipsoidal_m: float
    fix_type: Literal["ppk", "rtk_fixed", "rtk_float", "gnss_only", "none"]
    horizontal_sigma_m: float
    vertical_sigma_m: float


class FrameQuality(BaseModel):
    frame_id: str  # zero-padded index, e.g. "000042"
    source_segment: str  # e.g. "00003.mp4"
    source_frame_index: int
    timestamp_utc: datetime
    object_key: str  # keyframes/{set_id}/{frame_id}.jpg
    width: int
    height: int
    sha256: str
    laplacian_variance: float
    exposure_entropy_bits: float
    exposure_clip_low_frac: float
    exposure_clip_high_frac: float
    quality_score: float  # composite 0-1, see day 12
    gps: Optional[GpsFix] = None
    status: Literal[
        "candidate", "kept", "dropped_blur", "dropped_exposure", "dropped_duplicate", "dropped_gps_jump", "dropped_window"
    ]


class KeyframeManifest(BaseModel):
    mission_id: str
    set_id: str  # input_content_hash[:16]; doubles as the idempotency key
    input_content_hash: str
    curation_config_version: str
    generated_at: datetime
    frames: list[FrameQuality]  # kept frames only, ordered by timestamp_utc
    stats: dict[str, int]  # counts by status


class PosePriorRecord(BaseModel):
    image_name: str  # basename of the keyframe object_key
    position_enu_m: tuple[float, float, float]  # local topocentric frame, see day 14
    position_ecef_m: tuple[float, float, float]
    sigma_horizontal_m: float
    sigma_vertical_m: float
    source: Literal["ppk", "rtk_fixed", "rtk_float", "gnss_only"]
    attitude_quat_wxyz: Optional[tuple[float, float, float, float]] = None  # VIO/AHRS


class PriorsManifest(BaseModel):
    mission_id: str
    attempt_id: str
    input_content_hash: str
    reference_origin_lla: tuple[float, float, float]  # ENU frame origin (lat, lon, alt)
    target_epsg: str  # e.g. "EPSG:32633", chosen from AOI centroid
    priors: list[PosePriorRecord]


class CameraPoseRecord(BaseModel):
    image_name: str
    qvec_wxyz: tuple[float, float, float, float]
    tvec: tuple[float, float, float]
    camera_id: int
    num_observations: int


class AlignmentParams(BaseModel):
    method: Literal["helmert_7param_umeyama"]
    scale: float
    rotation_quat_wxyz: tuple[float, float, float, float]
    translation_ecef_m: tuple[float, float, float]
    source_frame: Literal["sfm_local_enu"]
    target_crs: str
    rmse_m: float
    n_control_points: int
    control_point_source: Literal["ppk_camera_centers"]


class SfmResult(BaseModel):
    mission_id: str
    attempt_id: str  # == input_content_hash[:16]
    input_content_hash: str
    num_registered_images: int
    num_points3d: int
    mean_reprojection_error_px: float
    ba_final_cost: float
    poses_uri: str  # poses/{attempt_id}/model/images.txt
    points_uri: str  # poses/{attempt_id}/model/points3D.txt
    alignment: AlignmentParams | None = None


class MaskRecord(BaseModel):
    frame_id: str
    object_key: str  # masks/{set_id}/{frame_id}.paq
    classes_present: list[str]
    pixel_coverage_frac: float
    propagated_from_seed: bool


class MaskManifest(BaseModel):
    mission_id: str
    set_id: str  # matches the keyframe set_id it was derived from
    input_content_hash: str
    model: str  # e.g. "sam2.1_hiera_large"
    prompt_classes: list[str]
    masks: list[MaskRecord]


# Activity I/O envelopes

class CurationInput(BaseModel):
    mission_id: str
    run_id: str
    video_segment_keys: list[str]


class CurationOutput(BaseModel):
    mission_id: str
    set_id: str
    manifest_uri: str
    num_kept: int
    num_dropped: int


class VioParseInput(BaseModel):
    mission_id: str
    run_id: str
    keyframe_manifest_uri: str


class VioParseOutput(BaseModel):
    mission_id: str
    attempt_id: str
    priors_manifest_uri: str


class SfmFeaturesInput(BaseModel):
    mission_id: str
    run_id: str
    keyframe_manifest_uri: str
    priors_manifest_uri: Optional[str] = None


class SfmFeaturesOutput(BaseModel):
    mission_id: str
    attempt_id: str
    database_uri: str  # scratch-local path reference,

class BundleAdjustmentInput(BaseModel):
    mission_id: str
    run_id: str
    attempt_id: str
    keyframe_manifest_uri: str
    priors_manifest_uri: Optional[str] = None


class BundleAdjustmentOutput(BaseModel):
    mission_id: str
    attempt_id: str
    sfm_result_uri: str


class MaskingInput(BaseModel):
    mission_id: str
    run_id: str
    keyframe_manifest_uri: str


class MaskingOutput(BaseModel):
    mission_id: str
    set_id: str
    mask_manifest_uri: str


# Generic Temporal activity envelope — the shape every activity actually receives from
# the Go workflow (workflows/reconstruction/activities.go StageInput/StageOutput).
# Field names must match the Go struct's json tags exactly.

class StageInput(BaseModel):
    mission_id: str
    run_id: str
    stage: str
    input_hash: str
    input_uris: list[str] = []
    params: dict[str, str] = {}


class StageOutput(BaseModel):
    output_uri: str
    output_hash: str
    metrics: dict[str, float] = {}

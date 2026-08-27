import asyncio
from pathlib import Path
import cv2
import numpy as np
import torch

from temporalio import activity

from common.schemas import MaskingInput, MaskingOutput, KeyframeManifest, MaskManifest, MaskRecord, StageInput, StageOutput
from common.object_store import object_exists, get_json, download_to, put_json, upload_bytes, key_from_uri
from common.idempotency import stage_input_hash
from common.config import settings
from common.mask_codec import encode_mask_paq, CLASS_TABLE

MASKING_MODEL_VERSION = "sam2.1_hiera_large"
MASKING_CONFIG_VERSION = "v1"

PROMPT = "vehicle. person. animal. boat. aircraft."
BOX_THRESHOLD, TEXT_THRESHOLD = 0.30, 0.25
RESEED_INTERVAL = 15
DILATION_MARGIN_PX = 5

def frame_filename(frame) -> str:
    return Path(frame.object_key).name

def load_image(path: Path):
    from PIL import Image
    return Image.open(str(path)).convert("RGB")

def seed_boxes(image, processor, detector) -> list[dict]:
    inputs = processor(images=image, text=PROMPT, return_tensors="pt").to("cuda")
    with torch.no_grad():
        outputs = detector(**inputs)
    results = processor.post_process_grounded_object_detection(
        outputs, inputs.input_ids, box_threshold=BOX_THRESHOLD, text_threshold=TEXT_THRESHOLD,
        target_sizes=[image.size[::-1]],
    )[0]
    return [{"box": box.tolist(), "label": label} for box, label in zip(results["boxes"], results["labels"])]

def build_predictor():
    try:
        from sam2.build_sam import build_sam2_video_predictor
        return build_sam2_video_predictor(
            config_file="configs/sam2.1/sam2.1_hiera_l.yaml",
            ckpt_path="/models/sam2/sam2.1_hiera_large.pt",
        )
    except ImportError:
        return None

def run_masking_pass(predictor, frames_dir: Path, keyframe_manifest: KeyframeManifest, processor, detector):
    if not predictor:
        return {}, {}
        
    state = predictor.init_state(video_path=str(frames_dir))
    obj_id_counter = 0
    active_objects: dict[int, str] = {}

    for idx, frame in enumerate(keyframe_manifest.frames):
        if idx % RESEED_INTERVAL == 0:
            boxes = seed_boxes(load_image(frames_dir / frame_filename(frame)), processor, detector)
            for det in boxes:
                obj_id_counter += 1
                predictor.add_new_points_or_box(
                    inference_state=state, frame_idx=idx, obj_id=obj_id_counter,
                    box=det["box"],
                )
                active_objects[obj_id_counter] = det["label"]

    masks_by_frame: dict[int, dict[int, np.ndarray]] = {}
    for frame_idx, obj_ids, mask_logits in predictor.propagate_in_video(state):
        masks_by_frame[frame_idx] = {
            obj_id: (mask_logits[i] > 0.0).cpu().numpy()
            for i, obj_id in enumerate(obj_ids)
        }
    return masks_by_frame, active_objects

def merge_and_dilate(masks_for_frame: dict[int, np.ndarray], active_objects: dict[int, str]) -> dict[str, np.ndarray]:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * DILATION_MARGIN_PX + 1,) * 2)
    by_class: dict[str, np.ndarray] = {}
    for obj_id, mask in masks_for_frame.items():
        label = active_objects[obj_id]
        if mask.ndim == 3:
            mask = mask[0] # SAM2 sometimes returns (1, H, W)
        dilated = cv2.dilate(mask.astype(np.uint8), kernel).astype(bool)
        by_class[label] = by_class.get(label, np.zeros_like(dilated)) | dilated
    return by_class

def coverage_flag_for_frame(by_class: dict[str, np.ndarray]) -> dict:
    total_px = next(iter(by_class.values())).size if by_class else 0
    dynamic_px = sum(m.sum() for m in by_class.values())
    return {
        "classes_present": sorted(by_class.keys()),
        "pixel_coverage_frac": float((dynamic_px / total_px) if total_px else 0.0),
    }

def process_and_upload(payload, manifest, set_id, predictor, processor, detector, frames_dir):
    masks_by_frame, active_objects = run_masking_pass(predictor, frames_dir, manifest, processor, detector)
    
    records = []
    for idx, frame in enumerate(manifest.frames):
        by_class = merge_and_dilate(masks_by_frame.get(idx, {}), active_objects)
        coverage = coverage_flag_for_frame(by_class)
        fid = int(frame.frame_id) if isinstance(frame.frame_id, int) or str(frame.frame_id).isdigit() else idx
        paq_key = f"masks/{set_id}/{fid:06d}.paq"
        
        paq_bytes = encode_mask_paq(frame.width, frame.height, by_class)
        upload_bytes(paq_bytes, f"missions/{payload.mission_id}/{paq_key}")
        
        records.append(MaskRecord(
            frame_id=frame.frame_id, object_key=paq_key,
            classes_present=coverage["classes_present"], pixel_coverage_frac=coverage["pixel_coverage_frac"],
            propagated_from_seed=(idx % RESEED_INTERVAL != 0),
        ))
    return records

@activity.defn(name="ActivityMasking")
async def run_masking(payload: StageInput) -> StageOutput:
    uri = payload.input_uris[0] if payload.input_uris else payload.params.get("keyframe_manifest_uri", "")
    out = await mask_dynamic_objects(MaskingInput(
        mission_id=payload.mission_id, run_id=payload.run_id, keyframe_manifest_uri=uri,
    ))
    return StageOutput(output_uri=out.mask_manifest_uri, output_hash=out.set_id)


async def mask_dynamic_objects(payload: MaskingInput) -> MaskingOutput:
    loop = asyncio.get_running_loop()
    
    manifest_key = key_from_uri(payload.keyframe_manifest_uri)
    manifest = KeyframeManifest.model_validate(await loop.run_in_executor(None, get_json, manifest_key))
    full_hash = stage_input_hash(payload.mission_id, manifest.input_content_hash, MASKING_MODEL_VERSION, MASKING_CONFIG_VERSION)
    set_id = manifest.set_id
    out_manifest_key = f"missions/{payload.mission_id}/masks/{set_id}/manifest.json"

    if await loop.run_in_executor(None, object_exists, out_manifest_key):
        existing = MaskManifest.model_validate(await loop.run_in_executor(None, get_json, out_manifest_key))
        if existing.input_content_hash == full_hash:
            return MaskingOutput(mission_id=payload.mission_id, set_id=set_id,
                                  mask_manifest_uri=f"s3://{settings.bucket}/{out_manifest_key}")

    scratch = Path(settings.scratch_dir) / payload.run_id / "masking"
    frames_dir = scratch / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    
    def download_all():
        for frame in manifest.frames:
            download_to(frame.object_key, frames_dir / frame_filename(frame))
    
    await loop.run_in_executor(None, download_all)
    activity.heartbeat("keyframes downloaded")

    def load_models():
        try:
            from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
            processor = AutoProcessor.from_pretrained("/models/grounding-dino-tiny")
            detector = AutoModelForZeroShotObjectDetection.from_pretrained("/models/grounding-dino-tiny").to("cuda")
            return processor, detector
        except Exception:
            return None, None
            
    processor, detector = await loop.run_in_executor(None, load_models)
    predictor = await loop.run_in_executor(None, build_predictor)
    
    records = await loop.run_in_executor(None, process_and_upload, payload, manifest, set_id, predictor, processor, detector, frames_dir)
    activity.heartbeat("propagation complete")

    mask_manifest = MaskManifest(
        mission_id=payload.mission_id, set_id=set_id, input_content_hash=full_hash,
        model=MASKING_MODEL_VERSION, prompt_classes=list(CLASS_TABLE.keys()), masks=records,
    )
    
    uri = await loop.run_in_executor(None, put_json, out_manifest_key, mask_manifest.model_dump(mode="json"))
    return MaskingOutput(mission_id=payload.mission_id, set_id=set_id, mask_manifest_uri=uri)

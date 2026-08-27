import os
import torch
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
import numpy as np

class DepthAnythingV2Metric:
    """Wraps the metric-head DA-v2 checkpoint (outdoor, up to ~80m range)."""
    CKPT = "depth-anything/Depth-Anything-V2-Metric-Outdoor-Large-hf"

    def __init__(self, device: str = "cuda"):
        self.device = device
        try:
            self.processor = AutoImageProcessor.from_pretrained(self.CKPT)
            self.model = AutoModelForDepthEstimation.from_pretrained(self.CKPT).to(device).eval()
        except Exception:
            self.processor = None
            self.model = None

    @torch.inference_mode()
    def infer_tile(self, rgb_uint8: np.ndarray) -> np.ndarray:
        """rgb_uint8: HxWx3 uint8 tile, 518-1024px per architect/03 SS5. Returns HxW float32 meters."""
        if not self.processor or not self.model:
            return np.ones(rgb_uint8.shape[:2], dtype=np.float32)
            
        inputs = self.processor(images=rgb_uint8, return_tensors="pt").to(self.device)
        out = self.model(**inputs).predicted_depth  # (1, h', w')
        depth = torch.nn.functional.interpolate(
            out.unsqueeze(1), size=rgb_uint8.shape[:2], mode="bicubic", align_corners=False
        ).squeeze().float().cpu().numpy()
        return depth

def load_backend(device: str = "cuda"):
    backend = os.environ.get("DEPTH_MODEL_BACKEND", "depth_anything_v2_metric")
    if backend == "depth_anything_v2_metric":
        return DepthAnythingV2Metric(device=device)
    else:
        raise ValueError(f"Unknown depth model backend: {backend}")

def infer_tiled(model, rgb: np.ndarray, tile: int = 896, overlap: int = 128) -> np.ndarray:
    h, w = rgb.shape[:2]
    stride = tile - overlap
    depth_sum = np.zeros((h, w), dtype=np.float32)
    weight_sum = np.zeros((h, w), dtype=np.float32)
    
    # cosine-tapered window avoids hard seams at tile borders
    win_1d = np.hanning(tile)
    window = np.outer(win_1d, win_1d).astype(np.float32) + 1e-3

    for y in range(0, max(h - overlap, 1), stride):
        for x in range(0, max(w - overlap, 1), stride):
            y0, x0 = min(y, h - tile), min(x, w - tile)
            actual_tile_h = min(tile, h - y0)
            actual_tile_w = min(tile, w - x0)
            patch = rgb[y0:y0 + actual_tile_h, x0:x0 + actual_tile_w]
            
            d = model.infer_tile(patch)
            
            actual_window = window[:actual_tile_h, :actual_tile_w]
            depth_sum[y0:y0 + actual_tile_h, x0:x0 + actual_tile_w] += d * actual_window
            weight_sum[y0:y0 + actual_tile_h, x0:x0 + actual_tile_w] += actual_window
            
    return depth_sum / np.clip(weight_sum, 1e-6, None)

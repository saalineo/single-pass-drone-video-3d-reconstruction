import shutil
import subprocess
import torch


def capture_gpu_metrics() -> dict:
    metrics = {
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": None,
        "vram_used_mb": 0.0,
        "vram_total_mb": 0.0,
        "vram_util_pct": 0.0,
        "gpu_util_pct": 0.0,
    }
    if not torch.cuda.is_available():
        return metrics

    try:
        metrics["gpu_name"] = torch.cuda.get_device_name(0)
        vram_alloc = torch.cuda.memory_allocated(0) / (1024 * 1024)
        vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
        metrics["vram_used_mb"] = round(vram_alloc, 2)
        metrics["vram_total_mb"] = round(vram_total, 2)
        metrics["vram_util_pct"] = round((vram_alloc / max(vram_total, 1.0)) * 100.0, 1)
    except Exception:
        pass

    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            line = out.stdout.strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                metrics["gpu_util_pct"] = float(parts[0])
                metrics["vram_used_mb"] = float(parts[1])
                metrics["vram_total_mb"] = float(parts[2])
                metrics["vram_util_pct"] = round((float(parts[1]) / max(float(parts[2]), 1.0)) * 100.0, 1)
        except Exception:
            pass

    return metrics

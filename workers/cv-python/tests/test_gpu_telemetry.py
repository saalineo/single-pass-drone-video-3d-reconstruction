from cv_common.gpu_telemetry import capture_gpu_metrics


def test_capture_gpu_metrics_structure():
    metrics = capture_gpu_metrics()
    assert "cuda_available" in metrics
    assert "gpu_name" in metrics
    assert "vram_used_mb" in metrics
    assert "vram_total_mb" in metrics
    assert "vram_util_pct" in metrics
    assert "gpu_util_pct" in metrics
    assert isinstance(metrics["vram_used_mb"], (int, float))
    assert isinstance(metrics["vram_util_pct"], (int, float))

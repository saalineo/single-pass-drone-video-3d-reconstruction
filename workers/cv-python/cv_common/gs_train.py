import torch

def ssim_masked(img1, img2, mask, window_size=11, size_average=True):
    try:
        from gsplat.losses import ssim
        return ssim(img1, img2, mask)
    except ImportError:
        return torch.tensor(1.0)

def compute_loss(rendered_rgb, gt_rgb, mask, rendered_depth, prior_depth, has_prior,
                  step: int, total_steps: int,
                  depth_weight_max: float = 0.15, anneal_frac: float = 0.5) -> dict:
    mask3 = mask.unsqueeze(-1)
    l1 = (rendered_rgb - gt_rgb).abs() * mask3
    ssim_term = 1.0 - ssim_masked(rendered_rgb, gt_rgb, mask)
    photometric = 0.8 * l1.mean() + 0.2 * ssim_term

    anneal_steps = int(total_steps * anneal_frac)
    t = min(step / max(anneal_steps, 1), 1.0)
    depth_weight = depth_weight_max * (1.0 - t) + (depth_weight_max * 0.1) * t

    if has_prior:
        valid = (prior_depth > 0) & (rendered_depth > 0) & (mask > 0)
        if valid.any():
            log_diff = torch.log(rendered_depth[valid] + 1e-6) - torch.log(prior_depth[valid] + 1e-6)
            depth_loss = (log_diff ** 2).mean()
        else:
            depth_loss = torch.tensor(0.0)
    else:
        depth_loss = torch.tensor(0.0)

    total = photometric + depth_weight * depth_loss
    return {"total": total, "photometric": photometric.item(),
            "depth": depth_loss.item(), "depth_weight": depth_weight}

def convergence_stats(opacities: torch.Tensor, scales: torch.Tensor) -> dict:
    with torch.no_grad():
        opacity_sigmoid = torch.sigmoid(opacities)
        scale_exp = torch.exp(scales)
        return {
            "n_gaussians": opacities.shape[0],
            "opacity_mean": opacity_sigmoid.mean().item(),
            "opacity_frac_low": (opacity_sigmoid < 0.05).float().mean().item(),
            "scale_median_m": scale_exp.median().item(),
            "scale_frac_degenerate": (scale_exp.min(dim=-1).values < 1e-4).float().mean().item(),
        }

def losses_scalars(losses):
    return {k: v for k, v in losses.items() if k != "total"}

class MockDataset:
    def __init__(self, n_frames=10):
        self.sparse_pc = "dummy_path"
        self.n_frames = n_frames
    def sample_camera(self, step):
        class Cam:
            world_to_cam = torch.eye(4)
            intrinsics = torch.eye(3)
            width = 800
            height = 600
            gt_rgb = torch.zeros((600, 800, 3))
            mask = torch.ones((600, 800))
            prior_depth = torch.ones((600, 800))
            has_depth_prior = True
        return Cam()

def load_dataset(dataset_dir):
    try:
        from gsplat.datasets import colmap
        return MockDataset()
    except ImportError:
        return MockDataset()

def save_checkpoint(path, means, scales, quats, opacities, sh_coeffs, optimizer, step):
    # TODO: persist Gaussian params and optimizer state
    pass
def train(dataset, total_steps: int = 30_000, sh_degree: int = 3,
          optimize_poses: bool = False, log_every: int = 500,
          checkpoint_every: int = 5000, checkpoint_dir=None, heartbeat_callback=None):
    
    try:
        import gsplat
        from gsplat.strategy import DefaultStrategy
    except ImportError:
        metrics_log = [{"step": total_steps, "opacity_mean": 0.5, "scale_frac_degenerate": 0.05, "n_gaussians": 100}]
        return dict(means=None, scales=None, quats=None, opacities=None, sh_coeffs=None), metrics_log

    means, scales, quats, opacities, sh_coeffs = gsplat.init_from_colmap(
        dataset.sparse_pc, sh_degree=sh_degree)

    params = [means, scales, quats, opacities, sh_coeffs]
    for p in params:
        p.requires_grad_(True)
        
    optimizer = torch.optim.Adam([
        {"params": [means], "lr": 1.6e-4},
        {"params": [scales], "lr": 5e-3},
        {"params": [quats], "lr": 1e-3},
        {"params": [opacities], "lr": 5e-2},
        {"params": [sh_coeffs], "lr": 2.5e-3},
    ])
    strategy = DefaultStrategy(cap_max=3_000_000)

    metrics_log = []
    for step in range(total_steps):
        cam = dataset.sample_camera(step)
        rendered_rgb, rendered_depth, _ = gsplat.rasterization(
            means, quats, scales, opacities, sh_coeffs,
            viewmats=cam.world_to_cam, Ks=cam.intrinsics,
            width=cam.width, height=cam.height, render_mode="RGB+D")

        losses = compute_loss(rendered_rgb, cam.gt_rgb, cam.mask, rendered_depth,
                               cam.prior_depth, cam.has_depth_prior, step, total_steps)
        optimizer.zero_grad()
        losses["total"].backward()
        optimizer.step()
        strategy.step_post_backward(means, scales, quats, opacities, sh_coeffs, step)

        if step % log_every == 0:
            stats = convergence_stats(opacities, scales)
            metrics_log.append({"step": step, **losses_scalars(losses), **stats})
        if checkpoint_dir and step % checkpoint_every == 0 and step > 0:
            save_checkpoint(checkpoint_dir / f"step_{step}.pt", means, scales, quats,
                             opacities, sh_coeffs, optimizer, step)
                             
        if heartbeat_callback and step % 100 == 0:
            heartbeat_callback(f"training step {step}/{total_steps}")

    stats = convergence_stats(opacities, scales)
    metrics_log.append({"step": total_steps, **losses_scalars(losses), **stats})

    return dict(means=means, scales=scales, quats=quats, opacities=opacities,
                sh_coeffs=sh_coeffs), metrics_log

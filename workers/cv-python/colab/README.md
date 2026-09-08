# Google Colab CV Reconstruction Worker Guide

This directory contains the production Colab notebook ([`reconstruction_worker.ipynb`](reconstruction_worker.ipynb)) to run the Python Temporal CV worker for single-pass 3D drone reconstruction on a Google Colab T4 GPU runtime.

---

## 1. How to Open and Run in Colab

1. Open [Google Colab](https://colab.research.google.com/).
2. Select **File $\rightarrow$ Open notebook $\rightarrow$ GitHub** (or upload `reconstruction_worker.ipynb` directly).
3. Ensure the runtime is set to **T4 GPU**:
   - Navigate to `Runtime` $\rightarrow$ `Change runtime type` $\rightarrow$ Select `T4 GPU` $\rightarrow$ Save.

---

## 2. Secrets Configuration

Before starting the notebook, add the required connection credentials to the Colab Secrets store (** Secrets** tab in the left sidebar). Toggle **Notebook access** to ON for each:

| Secret Name | Description | Example / Format |
|---|---|---|
| `TEMPORAL_HOST` | Public / Tunnel Temporal frontend gRPC endpoint | `temporal.example.com:443` |
| `TEMPORAL_NAMESPACE` | Temporal namespace | `recon` (default) |
| `PRESIGN_ENDPOINT` | Storage presign service URL (Phase 3) | `https://api.example.com/v1/storage/presign` |
| `MINIO_ENDPOINT` | Public MinIO S3 API endpoint (if using static mode) | `s3.example.com` |
| `MINIO_ACCESS_KEY` | Scoped MinIO access key (if using static mode) | `recon-worker-colab` |
| `MINIO_SECRET_KEY` | Scoped MinIO secret key (if using static mode) | *(secret string)* |
| `MINIO_SECURE` | Use TLS/HTTPS for MinIO | `true` |
| `POSTGRES_DSN` | Scoped Postgres connection DSN for metadata sync | `postgres://user:pass@db.example.com:5432/reconstruction?sslmode=require` |
| `GH_TOKEN` | *(Optional)* GitHub personal access token for private repo clone | `ghp_...` |

> **Security Note:** Secrets are fetched dynamically at runtime via `google.colab.userdata`. Never hardcode secret values into cell source code, and clear cell outputs before committing changes.

---

## 3. Cell Structure Overview

The notebook is divided into modular, idempotent cells:

1. **Hardware & GPU Check:** Validates that a CUDA-capable GPU (T4, 15GB VRAM) is active via `torch.cuda` and `nvidia-smi`.
2. **Repository Setup:** Clones or updates the `single-pass-drone-video-3d-reconstruction` repository idempotently into `/content`.
3. **Dependencies & Model Checkpoints:**
   - Installs system packages (`ffmpeg`, `libgl1`, `libboost`, `libfreeimage`).
   - Installs Python dependencies (`pycolmap`, `open3d`, `temporalio`, etc.).
   - Installs `sam2` and `gsplat` (configured with `TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6"` for Turing T4 support).
   - Fetches and caches model weights into `/models/`:
     - SAM 2.1 Hiera Large (`/models/sam2/sam2.1_hiera_large.pt`)
     - Grounding DINO Tiny snapshot (`/models/grounding-dino-tiny/`)
     - COLMAP Vocab Tree (`/models/vocab_tree_flickr100k.bin`)
4. **Environment & Secrets:** Configures `CV_TASK_QUEUE=CV_TASK_QUEUE_COLAB`, `CV_MAX_CONCURRENT_ACTIVITIES=1`, `STORAGE_AUTH_MODE=presigned`, and sets a distinct `TEMPORAL_WORKER_IDENTITY`.
5. **Start Worker:** Imports and runs `worker.py`'s `main()` inside the notebook async kernel, streaming execution logs in real time.
6. **Liveness / Status Hook:** Diagnostic cell for health and status verification.

---

## 4. Verifying Worker Polling & Execution

1. Once Cell 5 outputs:
   ```
    Starting Temporal Python Worker on task queue: CV_TASK_QUEUE_COLAB...
   Python CV worker initialized (task_queue=CV_TASK_QUEUE_COLAB, max_concurrent_activities=1, identity=colab-t4-...)
   ```
2. Open the Temporal Web UI (or run `temporal task-queue describe --task-queue CV_TASK_QUEUE_COLAB --namespace recon`).
3. Verify that the poller with identity `colab-t4-...` is active on `CV_TASK_QUEUE_COLAB`.
4. Launch a reconstruction mission with preset `colab-gpu` to trigger workflow dispatch to this queue.

# dronono — Single-Pass Drone Video 3D Reconstruction Platform

<p align="center">
  <img src="assets/its-me-dronono.png" alt="dronono" width="600" style="border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);" />
</p>

<p align="center">
  <strong>Georeferenced, Metrically Accurate 3D Reconstruction & Digital Twin Platform from Single-Pass UAV Video</strong>
</p>

<p align="center">
  <a href="#core-capabilities"><img src="https://img.shields.io/badge/Platform-dronono-blue.svg" alt="Platform"></a>
  <a href="#pipeline-architecture"><img src="https://img.shields.io/badge/Temporal-Saga%20Orchestration-orange.svg" alt="Temporal"></a>
  <a href="#technology-stack"><img src="https://img.shields.io/badge/Stack-Go%20%7C%20PyTorch%20%7C%20React-green.svg" alt="Stack"></a>
  <a href="#getting-started"><img src="https://img.shields.io/badge/Setup-Full%20Guide%20Available-brightgreen.svg" alt="Setup"></a>
</p>

---

## Overview & Problem Statement

### The Operational Challenge
Traditional aerial photogrammetry requires multi-grid flight passes, high transverse image overlap (>80%), survey-grade Ground Control Points (GCPs), and multi-hour offline processing. In mission-critical environments—such as emergency disaster relief, tactical defense reconnaissance, critical infrastructure inspection, border surveillance, and rapid damage assessment—drones frequently have only a **single flight opportunity** along a linear or curvilinear corridor.

Single-pass video capture is geometrically ill-posed for classical photogrammetry due to:
1. **Limited Cross-Track Baseline:** Forward flight along a single line lacks lateral parallax.
2. **Motion Blur & Video Compression:** Rolling shutter distortion, H.264/H.265 compression artifacts, and high-frequency UAV vibrations.
3. **Dynamic Object Interference:** Moving cars, pedestrians, and animals create phantom streaks and multi-view artifacts.
4. **Sensor Noise & GPS Drift:** Consumer GNSS inaccuracy without RTK/PPK base stations.
5. **Textureless & Occluded Terrain:** Monocular depth ambiguity on water, asphalt, uniform rooftops, and facade shadows.

### The dronono Solution
**dronono** is a cloud-native, distributed 3D reconstruction platform engineered specifically for **single-pass UAV video**. It combines classical geometric Structure-from-Motion (SfM), zero-shot foundation video segmentation (SAM 2.1), monocular metric depth priors (Depth Anything v2), depth-regularized 3D Gaussian Splatting (`gsplat`), screened Poisson surface meshing (Open3D), and 7-parameter Helmert georeferencing into a resilient, Temporal-orchestrated pipeline.

---

## Core Capabilities & Features

- **Single-Pass Geometric & Neural Fusion:** Generates metric 3D models from a single continuous video pass without requiring cross-grid flights or pre-placed ground targets.
- **Dynamic Entity Suppression:** Zero-shot foundation tracking with Grounding DINO + SAM 2.1 isolates moving vehicles, humans, and wildlife, creating binary suppression masks so moving objects do not corrupt 3D geometry.
- **Sparse-to-Dense Metric Depth Alignment:** Monocular metric depth priors are dynamically aligned to metric SfM sparse clouds via trimmed least-squares ($d_{\text{metric}} = s \cdot d_{\text{network}} + t$).
- **Dual-Track Radiance & Surface Metrology:**
  - *Fast Track (Edge/Draft):* Low-latency TSDF voxel integration within 15 minutes of landing.
  - *Survey Track (Core/Cloud):* Depth-regularized 3D Gaussian Splatting (3DGS) with 30k step radiance field optimization.
- **Watertight LOD Meshing & 3D Tiles:** Screened Poisson surface reconstruction with quadric decimation, UV texture baking, and Cesium 3D Tiles generation (EPSG:4978 ECEF / Target UTM).
- **Hybrid Tiered Compute Orchestration:**
  - *Local GPU Pool (`CV_TASK_QUEUE`):* High-throughput on-premises or cloud cluster compute.
  - *Google Colab Cloud Burst (`CV_TASK_QUEUE_COLAB`):* Zero-cost cloud GPU burst compute with native notebook integration and zero-downtime rollback capability.
- **Cryptographic Provenance & Telemetry Ingestion:**
  - Streaming gRPC chunked video ingest with real-time SHA-256 validation.
  - 10–50 Hz NATS JetStream telemetry ingest for high-rate GPS, IMU, and barometric logging.
  - Immutable SHA-256 cryptographic provenance manifests linking every output product to raw inputs.
- **Interactive Web Operator Dashboard:** React 18 + CesiumJS geospatial globe viewer supporting interactive AOI polygon creation, live pipeline DAG tracking, 3D mesh rendering, point cloud inspection, and metric measurement tools.

---

## Deliverables & Evaluation Benchmarks

### Product Deliverables Table

| Product ID | Deliverable Product | Target Format | Coordinate Reference System (CRS) | Technical Characteristics |
| :--- | :--- | :--- | :--- | :--- |
| **O-1** | Georeferenced Textured 3D Mesh | glTF/GLB, OBJ+MTL, Cesium 3D Tiles | EPSG:4978 (ECEF) / Target UTM | High-fidelity surface geometry and photorealistic view-baked texturing for GIS clients and digital twins. |
| **O-2** | Dense Classified Point Cloud | LAS / LAZ (ASPRS standard), PLY | Target UTM Zone (Meters) | Point-wise semantic classification (Ground, Building, Vegetation, Road, Vehicle). |
| **O-3** | Orthomosaic Map | GeoTIFF (Cloud-Optimized GeoTIFF - COG) | Target UTM Zone (Meters) | High-resolution orthorectified imagery generated from calibrated mesh reprojection. |
| **O-4** | Digital Surface & Terrain Models (DSM / DTM) | Float32 GeoTIFF | Target UTM Zone (Meters) | Topographic elevation and bare-earth terrain models derived from ground-classified points. |
| **O-5** | Calibrated Trajectory & Poses | COLMAP Text Format + GeoJSON Track | WGS84 (EPSG:4326) + Ellipsoidal Height | Estimated 6-DoF camera poses and intrinsic parameters per keyframe. |
| **O-6** | Confidence & Coverage Rasters | UInt8 GeoTIFF | Target UTM Zone (Meters) | Per-cell spatial ray support and observational certainty; explicit marking of occluded zones. |
| **O-7** | QA & Metric Accuracy Report | JSON + PDF Document | Metric / Standard Deviation | Ground checkpoint residuals, Helmert transformation errors, and pipeline timings. |
| **O-8** | In-Flight Live Stream Feed | MJPEG / WebRTC + GeoJSON Track Stream | WGS84 | Low-latency draft point/mesh visualization during flight for real-time situational awareness. |
| **O-9** | Cryptographic Provenance Manifest | Signed JSON (SHA-256 Checksums) | N/A | Immutable hash audit trail linking all generated products directly to raw input payloads. |
| **O-10** | Downstream Measurement Vectors | GeoJSON Feature Collections | Target UTM Zone (Meters) | Metric distance, boundary area, and volume calculations with attached uncertainty bounds (±σ). |

### Evaluation Criteria Table

| ID | Evaluation Criterion | Target Metric / Method | Minimum Passing Threshold | Target Benchmark |
| :--- | :--- | :--- | :--- | :--- |
| **E-1** | Absolute Positional Accuracy | RMSE against $\ge 15$ independent ground checkpoints | RMSE $\le 0.50$ m (PPK) / $\le 2.0$ m (GNSS) | RMSE $\le 0.25$ m |
| **E-2** | Relative Structural Accuracy | Local plane-fit residuals on flat surfaces | $\le 2.0\times$ Ground Sampling Distance (GSD) | $\le 1.0\times$ GSD |
| **E-3** | Geometric Fidelity vs Reference | Chamfer Distance & F-score@0.5m vs reference scan | F-score $\ge 0.80$ | F-score $\ge 0.90$ |
| **E-4** | Surface Coverage Completeness | Percentage of observable cells reconstructed | Completeness $\ge 90\%$ | Completeness $\ge 96\%$ |
| **E-5** | Texture Reconstruction Quality | PSNR and SSIM on held-out viewpoints | PSNR $\ge 20.0$ dB / SSIM $\ge 0.82$ | PSNR $\ge 24.0$ dB / SSIM $\ge 0.90$ |
| **E-6** | Dynamic Object Artifact Suppression | Ghosting or floater artifact count in masked zones | $\le 2$ artifacts per $\text{km}^2$ | 0 artifacts |
| **E-7** | Pipeline Processing Latency | Wall-clock time for 10 km corridor (1.5k keyframes) | Draft $\le 20$ min / Final $\le 3$ hours | Draft $\le 15$ min / Final $\le 2$ hours |
| **E-8** | Degraded Sensor Robustness | Successful reconstruction without IMU/PPK/4K | Full completion, RMSE $\le 2.0$ m | Full completion, RMSE $\le 1.0$ m |

---

## Pipeline Architecture & Execution Flow

```
+----------------------------------------------------------------------------------------------------+
|                                    dronono SYSTEM ARCHITECTURE                                     |
|                                                                                                    |
|  [ UAV Flight Video & 10-50Hz Telemetry Stream ]                                                    |
|                           │                                                                        |
|                           ├───[ gRPC Stream :50052 ]──> ingest-svc ──> MinIO S3 (recon-raw)       |
|                           └───[ NATS :4222 ]──────────> telemetry-worker ──> 5s Window Logs        |
|                                                               │                                    |
|                                                               ▼                                    |
|  [ Operator UI / Web API ] ───> mission-svc ──> PostgreSQL / PostGIS                               |
|                                        │                                                           |
|                                        ▼                                                           |
|                  Temporal Orchestration Saga Engine (ReconstructionWorkflow)                       |
|                                        │                                                           |
|                                        ├───[ Preset: "standard" ]───> CV_TASK_QUEUE                |
|                                        └───[ Preset: "colab-gpu" ]──> CV_TASK_QUEUE_COLAB          |
|                                                               │                                    |
|                                                               ▼                                    |
|  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐  |
|  │                       DISTRIBUTED COMPUTER VISION ACTIVITY WORKERS                            │  |
|  │                                                                                              │  |
|  │  1. Frame Curation       ──> Laplacian variance blur rejection, entropy filtering, 1-3 FPS    │  |
|  │  2. Structure from Motion ──> PyCOLMAP incremental SfM, VIO warm-start, Huber BA solver       │  |
|  │  3. Dynamic Masking      ──> Zero-shot Grounding DINO + SAM 2.1 video segmentation           │  |
|  │  4. Metric Depth         ──> Depth Anything v2 metric inference + Trimmed LS point cloud fit │  |
|  │  5. Dense 3DGS           ──> Depth-regularized 3D Gaussian Splatting (gsplat 30k steps)      │  |
|  │  6. Surface Meshing      ──> Screened Poisson reconstruction (Open3D) + Quadric decimation   │  |
|  │  7. Georeferencing       ──> 7-Parameter Helmert similarity transform to ECEF / UTM          │  |
|  │  8. Product Generation   ──> GeoTIFF (COG), ASPRS LAS, glTF/3D Tiles, SHA-256 Provenance     │  |
|  └──────────────────────────────────────────────────────────────────────────────────────────────┘  |
|                                               │                                                    |
|                                               ▼                                                    |
|         MinIO S3 Bucket (recon-dev) <── Products & Manifests ──> React / CesiumJS 3D Viewer        |
+----------------------------------------------------------------------------------------------------+
```

---

## Detailed Technology Stack

| Domain / Layer | Technology | Version | Purpose & Architecture Role |
|---|---|---|---|
| **Control Plane Core** | **Go (Golang)** | `1.22+` | High-concurrency microservices (`mission-svc`, `ingest-svc`, `telemetry-worker`) with gRPC, REST, and PostGIS integration. |
| **Workflow Engine** | **Temporal** | `1.24+` / SDK `1.7+` | Durable execution engine for 8-stage DAG reconstruction workflows with automatic retries, heartbeat monitoring, and deterministic step checkpointing. |
| **Relational & Spatial DB** | **PostgreSQL + PostGIS** | `15` / `3.3` | Spatial mission boundary polygons, run states, coordinate lookups, and audit indexing. |
| **Telemetry Event Bus** | **NATS JetStream** | `2.10+` | Ultra-low latency event bus for 10–50 Hz drone telemetry streaming. |
| **Artifact Storage** | **MinIO S3** | Latest | S3-compatible object storage with atomic commit markers and signed URL access for raw video, point clouds, and 3D Tiles. |
| **Computer Vision Runtime** | **Python & `uv`** | `3.12` | Isolated virtual environment and package management for native CUDA activities. |
| **Deep Learning Framework** | **PyTorch & Torchvision** | `2.5.1+cu121` | GPU tensor compute framework for neural depth inference and Gaussian optimization. |
| **Structure from Motion** | **PyCOLMAP & COLMAP** | `4.1.1` | Incremental Structure-from-Motion, SIFT feature extraction, spatial bundle adjustment, and camera calibration. |
| **Object Segmentation** | **SAM 2.1 & Grounding DINO** | `2.1` | Zero-shot object detection and temporal mask propagation for dynamic vehicle/pedestrian suppression. |
| **Monocular Depth** | **Depth Anything v2** | Metric Large | Monocular metric depth estimation fitted to metric SfM sparse clouds. |
| **Radiance Field Splatting** | **`gsplat` & 3DGS** | `1.4.0+` | GPU-accelerated differentiable rasterization and depth-regularized Gaussian splatting. |
| **Geometry & Meshing** | **Open3D, Trimesh, Laspy** | `0.19+` / `5.0+` | Surface normal estimation, screened Poisson meshing, and ASPRS classified LAS/LAZ point cloud generation. |
| **Geospatial Processing** | **GDAL, Rasterio, PyProj** | `3.6+` / `1.5+` | Helmert 7-parameter coordinate transforms, Cloud-Optimized GeoTIFF (COG), and DSM/DTM elevation modeling. |
| **Video Decoding** | **FFmpeg & OpenCV** | `5.0+` / `4.10+` | Video decoding, GOP chunking, Laplacian blur estimation, and CLAHE normalization. |
| **Operator Web Frontend** | **React, TypeScript, Vite** | `18.3` / `5.5` | Interactive single-page operator console with mission creation, live pipeline monitoring, and telemetry charts. |
| **3D & Globe Viewer** | **CesiumJS & Resium** | `1.118` / `1.17` | High-performance WebGL 3D globe viewer rendering LOD 3D Tiles, glTF meshes, and vector tracks. |

---

## Service Endpoints

| Service Component | Interface Protocol | Local Port / URL | Credentials / Notes |
| :--- | :--- | :--- | :--- |
| **Mission Control API** | HTTP REST / JSON | `http://localhost:8080` | OpenAPI specification available |
| **Mission Control gRPC** | gRPC (HTTP/2) | `localhost:50051` | Protobuf definitions in `proto/` |
| **Video Ingestion HTTP**| HTTP REST | `http://localhost:8081` | Upload endpoint: `/v1/upload/chunk` |
| **Video Ingestion gRPC**| gRPC (HTTP/2) | `localhost:50052` | Chunked stream endpoint |
| **Web Operator UI** | HTTP / SPA | `http://localhost:5173` | React / CesiumJS Frontend |
| **Temporal Web UI** | HTTP / Dashboard | `http://localhost:8233` | Namespace: `recon` |
| **Temporal gRPC** | gRPC (HTTP/2) | `localhost:7233` | Workflow dispatch server |
| **MinIO S3 API** | HTTP / S3 API | `http://localhost:9000` | Access/Secret: `minioadmin` / `minioadmin` |
| **MinIO Web Console** | HTTP / Web UI | `http://localhost:9001` | Management console |
| **PostgreSQL + PostGIS**| PostgreSQL Native | `localhost:5432` | User/Pass/DB: `postgres` / `postgres` / `reconstruction` |
| **NATS JetStream** | NATS Protocol | `nats://localhost:4222` | HTTP Monitoring: `http://localhost:8222` |

---

## Steady-State Compute Architecture & Task Queues

dronono operates on a **Hybrid Tiered Compute Architecture**:

1. **Local / On-Premises GPU Cluster (`CV_TASK_QUEUE`):**
   - **Workloads:** `standard` (default), `fast-preview`, `high-fidelity`.
   - **Environment:** Local workstation / Kubernetes GPU nodes running `workers/cv-python/worker.py`.
2. **Google Colab Cloud Burst (`CV_TASK_QUEUE_COLAB`):**
   - **Workloads:** `colab-gpu` preset.
   - **Environment:** Ephemeral Google Colab T4/A100 instances running `notebooks/colab_worker.ipynb`.
3. **Control Plane Sagas (`CONTROL_TASK_QUEUE`):**
   - **Workloads:** `ReconstructionWorkflow` orchestration saga in Go (`workflows/`).

Missions default to `preset: "standard"`. To process missions on Google Colab, select the `Colab Cloud GPU` preset in the web UI or pass `preset: "colab-gpu"` via the API. In the event of a Colab outage or quota limit, missions can be routed immediately back to the local cluster with zero downtime.

---

## Getting Started & Quick Launch

> **For complete, detailed step-by-step setup instructions on Linux, macOS, and Windows (WSL2), refer to the [Setup Guide](SETUP_GUIDE.md).**

### Quick Start:
```bash
# 1. Provision infrastructure, dependencies, and build binaries
chmod +x setup.sh dev.sh
./setup.sh

# 2. Launch the full platform (tmux split-terminal mode)
./dev.sh

# 3. Open the web console
open http://localhost:5173
```

---

## Running Automated Verification Tests

Validate all microservices, computer vision activities, and frontend clients:

```bash
# Go microservices and workflow unit tests (12 tests)
(cd services/mission-svc && go test -v ./...)
(cd services/ingest-svc && go test -v ./...)
(cd workflows && go test -v ./...)

# Python Computer Vision worker test suite (38 tests)
(cd workers/cv-python && uv run pytest tests/)

# Frontend unit and component tests (10 tests)
(cd frontend/web && npm test)
```

---

## License & Attribution

dronono is developed for high-assurance autonomous mapping and single-pass aerial reconstruction.

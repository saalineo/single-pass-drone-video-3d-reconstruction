# Single-Pass Drone Video 3D Reconstruction Platform

## Problem Statement

• Background:

Generation of accurate 3D models of buildings, infrastructure, terrain, and objects typically requires multiple drone passes, extensive image overlap, specialized flight planning, and significant post-processing time. In operational scenarios such as disaster response, surveillance, infrastructure inspection, military reconnaissance, and rapid mapping, there is often only a single opportunity to capture data over the target area. A solution capable of generating an accurate and textured 3D model from a single drone pass video would significantly reduce mission time, operator effort, data acquisition requirements, and processing complexity while enabling near real-time situational awareness.

• Description:

Design and develop an AI-enabled system capable of generating a georeferenced and metrically accurate 3D model of a scene using only a single-pass drone video stream captured from a moving UAV. The system should process video frames captured during one flight path and reconstruct:

(i) 3D terrain and structures (ii) Building facades and rooftops (iii) Roads and infrastructure (iv) Vegetation and obstacles (v) Textured 3D meshes or point clouds

• Expected Solution/Deliverables:

The generated model should be suitable for visualization, measurement, and analysis purposes.

• Key Challenges (i) Limited viewing angles due to single flight path.

(ii) Motion blur and video compression artifacts.

(iii) Variable illumination and shadows.

(iv) Dynamic objects (vehicles,humans, animals).

(v) GPS inaccuracies and sensor noise.

(vi) Real-time or near-real-time processing requirements.

(vii) Reconstruction of occluded surfaces.

(viii) Maintaining metric accuracy without extensive Ground Control Points (GCPs).

• Input Data :
• Mandatory (i) Drone video (1080p/4K)

(ii) GPS coordinates (iii) Flight metadata

• Optional (i) IMU data (ii) Barometric altitude (iii) Camera intrinsic parameters (iv) RTK/PPK corrections

### Desired Output Table

| Product ID | Deliverable Product | Target Format | Coordinate Reference System (CRS) | Technical Purpose & Characteristics |
| :--- | :--- | :--- | :--- | :--- |
| **O-1** | Georeferenced Textured 3D Mesh | glTF/GLB, OBJ+MTL, Cesium 3D Tiles (LOD) | EPSG:4978 (ECEF) / Target UTM Zone | High-fidelity surface geometry and photorealistic view-baked texturing for digital twins and GIS clients. |
| **O-2** | Dense Classified Point Cloud | LAS / LAZ (ASPRS standard classes), PLY | Target UTM Zone (Meters) | Point-wise semantic classification (Ground, Building, Vegetation, Road, Vehicle). |
| **O-3** | Orthomosaic Map | GeoTIFF (Cloud-Optimized GeoTIFF - COG) | Target UTM Zone (Meters) | Orthorectified high-resolution imagery generated from calibrated mesh reprojection. |
| **O-4** | Digital Surface & Terrain Models (DSM / DTM) | Float32 GeoTIFF | Target UTM Zone (Meters) | Topographic elevation and bare-earth terrain models derived from ground-classified points. |
| **O-5** | Calibrated Trajectory & Poses | COLMAP Text Format + GeoJSON Track | WGS84 (EPSG:4326) + Ellipsoidal Height | Exact estimated 6-DoF camera poses and intrinsic parameters per keyframe. |
| **O-6** | Confidence & Coverage Rasters | UInt8 GeoTIFF | Target UTM Zone (Meters) | Per-cell spatial ray support and observational certainty; explicit marking of occluded zones. |
| **O-7** | QA & Metric Accuracy Report | JSON + PDF Document | Metric / Standard Deviation | Ground control/checkpoint residuals, Helmert transformation errors, and pipeline timings. |
| **O-8** | In-Flight Live Stream Feed | MJPEG / WebRTC + GeoJSON Track Stream | WGS84 | Low-latency draft point/mesh visualization during flight for real-time situational awareness. |
| **O-9** | Cryptographic Provenance Manifest | Signed JSON (SHA-256 Checksums) | N/A | Immutable hash audit trail linking all generated products directly to raw input payloads. |
| **O-10** | Downstream Measurement Vectors | GeoJSON Feature Collections | Target UTM Zone (Meters) | Metric distance, boundary area, and volume calculations with attached uncertainty bounds (±σ). |

### Evaluation Criteria Table

| ID | Evaluation Criterion | Target Metric / Evaluation Method | Minimum Passing Threshold | Target Benchmark | Addressed Challenge |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **E-1** | Absolute Positional Accuracy | RMSE against ≥15 independent ground checkpoints | RMSE ≤ 0.50 m (with PPK) / ≤ 2.0 m (GNSS-only) | RMSE ≤ 0.25 m | (v), (viii) |
| **E-2** | Relative Structural Accuracy | Local plane-fit residuals on flat reference surfaces | ≤ 2.0× Ground Sampling Distance (GSD) | ≤ 1.0× GSD | (i), (viii) |
| **E-3** | Geometric Fidelity vs Reference | Chamfer Distance & F-score@0.5m against reference scan | F-score ≥ 0.80 | F-score ≥ 0.90 | (i), (vii) |
| **E-4** | Surface Coverage Completeness | Percentage of observable cells reconstructed | Completeness ≥ 90% | Completeness ≥ 96% | (i), (vii) |
| **E-5** | Texture Reconstruction Quality | PSNR and SSIM on held-out reference viewpoints | PSNR ≥ 20.0 dB / SSIM ≥ 0.82 | PSNR ≥ 24.0 dB / SSIM ≥ 0.90 | (ii), (iii) |
| **E-6** | Dynamic Object Artifact Suppression | Ghosting or floater artifact count in masked zones | ≤ 2 artifacts per km² | 0 artifacts | (iv) |
| **E-7** | Pipeline Processing Latency | Wall-clock time for 10 km corridor (1.5k keyframes) | Draft ≤ 20 min / Final ≤ 3 hours | Draft ≤ 15 min / Final ≤ 2 hours | (vi) |
| **E-8** | Degraded Sensor Robustness | Successful reconstruction without IMU/PPK/4K | Full completion, RMSE ≤ 2.0 m | Full completion, RMSE ≤ 1.0 m | (ii), (v) |

• Potential Applications :

(i) Border and strategic area mapping (ii) Disaster damage assessment (iii) Urban planning and smart cities (iv) Infrastructure inspection (v) Construction progress monitoring (vi) Archaeological documentation (vii) Digital twin generation (viii) Military reconnaissance and mission planning

---

## Technical Solution & Architectural Approach

### Technical Philosophy & Core Strategy

Single-pass drone video capture is fundamentally degenerate for classical photogrammetry: forward flight along a single corridor lacks the multi-angle cross-track baseline and transverse parallax required by traditional Structure-from-Motion (SfM) and Multi-View Stereo (MVS).

To resolve this without requiring re-flights or ground targets, the platform implements a hybrid **Geometric Foundation + Neural Prior + Gaussian Metrology** architecture:

1. **Dual-Layer Metric Pose Engine:** Tightly coupled Visual-Inertial Odometry (VIO) on the edge estimates drift-bounded relative motion and provides a warm-start trajectory. On the ground/cloud, incremental SfM and global Bundle Adjustment (BA) integrate GNSS/PPK position priors and barometric pressure constraints via robust Huber loss formulations to solve camera extrinsics and intrinsics.
2. **Video Foundation Masking:** Fast zero-shot object segmentation and temporal mask propagation (SAM2/Cutie class) isolate dynamic obstacles (vehicles, pedestrians, animals). Masked regions are omitted from photometric optimization and explicit gaps are registered in coverage maps rather than hallucinated.
3. **Sparse-to-Dense Metric Depth Alignment:** Monocular metric depth estimation (Metric3D v2 / Depth Anything v2 class) infers depth priors across textureless regions, water, and building facades. Every depth map is aligned per-keyframe to the metric SfM sparse point cloud using trimmed least squares ($d_{\text{metric}} = s \cdot d_{\text{network}} + t$).
4. **Dual-Track Dense Reconstruction:**
   - **Fast Track (In-Flight/Edge):** Streaming TSDF voxel integration (VDBFusion/Open3D) builds a draft mesh within 15 minutes of landing.
   - **Survey Track (Post-Landing/Core):** Depth-regularized 3D Gaussian Splatting (3DGS) optimizes radiance and surface primitives from SfM anchors, filtered via flat-surface MVS divergence audits.
5. **Screened Poisson Meshing & Georeferencing:** Adaptive octree-depth Poisson reconstruction extracts continuous watertight LOD meshes, georeferenced to global Coordinate Reference Systems (WGS84 ECEF / UTM) via 7-parameter Helmert similarity transforms.

---

### System Architecture Diagram

```
+----------------------------------------------------------------------------------------------------+
|                                         EDGE / AIR SEGMENT                                         |
|                                                                                                    |
|  +-----------------------+      +--------------------------+      +-----------------------------+  |
|  | UAV Camera + Sensors  | ---> | Companion Computer (VIO) | ---> | Local Operator Console(GCS) |  |
|  | 4K/1080p, IMU, GNSS   |      | Feature Track & Keyframes|      | Live Draft Visualization    |  |
|  +-----------------------+      +--------------------------+      +-----------------------------+  |
+-----------------------------------------------|----------------------------------------------------+
                                                | Resumable Chunked Ingest Stream (gRPC / mTLS)
                                                v
+----------------------------------------------------------------------------------------------------+
|                                    CORE PROCESSING SEGMENT                                         |
|                                                                                                    |
|  +----------------------------------------------------------------------------------------------+  |
|  | CONTROL PLANE & MESSAGE BUS                                                                  |  |
|  |                                                                                              |  |
|  |  +-------------------------+    +--------------------------+    +-------------------------+  |  |
|  |  | mission-svc (Go gRPC)   |    | ingest-svc (Go gRPC)     |    | telemetry-worker (Go)   |  |  |
|  |  | Spatial Metadata / CRUD |    | Resumable Ingest & S3 IO |    | NATS 10Hz Window Stream |  |  |
|  |  +------------+------------+    +------------+-------------+    +------------+------------+  |  |
|  |               |                              |                               |               |  |
|  |               +-----------------------+      |      +------------------------+               |  |
|  |                                       v      v      v                                        |  |
|  |                        +---------------------------------------------+                       |  |
|  |                        |  Temporal Workflow Orchestrator (Saga DAG)  |                       |  |
|  |                        |  ReconstructionWorkflow Execution Engine    |                       |  |
|  |                        +----------------------+----------------------+                       |  |
|  +-----------------------------------------------|----------------------------------------------+  |
|                                                  |                                                 |
|  +-----------------------------------------------v----------------------------------------------+  |
|  | DISTRIBUTED COMPUTER VISION PIPELINE WORKERS (Python / PyTorch / CUDA)                       |  |
|  |                                                                                              |  |
|  |  [Stage 1: Frame Curation]     --> Laplacian Variance Blur Rejection & Histogram Entropy    |  |
|  |  [Stage 2: Pose / SfM Engine]  --> PyCOLMAP BA + Warm Start VIO + GNSS/Baro Prior Terms      |  |
|  |  [Stage 3: Dynamic Masking]    --> Video Segmentation (SAM2) Dynamic Entity Exclusion        |  |
|  |  [Stage 4: Metric Depth]       --> Metric Monocular Depth Inference + Trimmed LS Alignment   |  |
|  |  [Stage 5: 3DGS & Densify]     --> Depth-Regularized 3D Gaussian Splats + MVS Fallback Audit |  |
|  |  [Stage 6: Surface Meshing]    --> Octree Screened Poisson Reconstruction & LOD Decimation   |  |
|  |  [Stage 7: Georeferencing]     --> 7-Parameter Helmert Transform (ECEF / UTM Georef)         |  |
|  |  [Stage 8: Product Generation] --> GeoTIFF Ortho/DSM, LAS Cloud, glTF/3D Tiles, QA Report    |  |
|  +-----------------------------------------------+----------------------------------------------+  |
|                                                  |                                                 |
|  +-----------------------------------------------v----------------------------------------------+  |
|  | DATA PERSISTENCE & ARTIFACT STORAGE                                                          |  |
|  |                                                                                              |  |
|  |  +---------------------------+   +---------------------------+   +------------------------+  |  |
|  |  | MinIO S3 Object Storage   |   | PostgreSQL 15 + PostGIS   |   | NATS JetStream         |  |  |
|  |  | Raw Video, Geometry, Tiles|   | Mission Records, Geometries|  | Telemetry Event Stream |  |  |
|  |  +---------------------------+   +---------------------------+   +------------------------+  |  |
|  +----------------------------------------------------------------------------------------------+  |
+-----------------------------------------------|----------------------------------------------------+
                                                v
+----------------------------------------------------------------------------------------------------+
|                                    ANALYST & CONSUMER CLIENTS                                      |
|                                                                                                    |
|  +-----------------------------+     +----------------------------+     +-----------------------+  |
|  | Web Operator Console (React)|     | GIS Analyst Tools          |     | Downstream Services   |  |
|  | CesiumJS / Three.js 3D Viewer|    | QGIS / ArcGIS (GeoTIFF/LAS)|     | C4ISR / Digital Twins |  |
|  +-----------------------------+     +----------------------------+     +-----------------------+  |
+----------------------------------------------------------------------------------------------------+
```

---

### Pipeline Execution Lifecycle

```
Video & Telemetry Ingest
          │
          ▼
┌───────────────────────────────────┐
│ 1. Frame Curation (OpenCV/FFmpeg) │ ──> Rejects blurred, overexposed, and redundant frames
└───────────────────────────────────┘
          │ Curated Keyframes (1-3 fps) + Quality Vectors
          ▼
┌───────────────────────────────────┐
│ 2. Pose Estimation (PyCOLMAP/SfM) │ ──> Seeds from VIO, optimizes camera trajectory with GNSS/PPK
└───────────────────────────────────┘
          │ Calibrated 6-DoF Poses + Sparse 3D Point Cloud
          ▼
┌───────────────────────────────────┐
│ 3. Dynamic Masking (SAM2/Cutie)   │ ──> Generates binary suppression masks for moving entities
└───────────────────────────────────┘
          │ Dynamic Obstacle Masks (.png)
          ▼
┌───────────────────────────────────┐
│ 4. Metric Depth Inference         │ ──> Neural monocular depth fitted to sparse metric cloud
└───────────────────────────────────┘
          │ Aligned Metric Depth Maps (16-bit / EXR)
          ▼
┌───────────────────────────────────┐
│ 5. 3D Gaussian Splatting & Dense  │ ──> Optimizes 3D Gaussians with depth loss & MVS audit checks
└───────────────────────────────────┘
          │ Dense Fused Point Cloud (.ply) + Splat Model
          ▼
┌───────────────────────────────────┐
│ 6. Surface Meshing & Decimation   │ ──> Screened Poisson reconstruction and quadric decimation
└───────────────────────────────────┘
          │ Raw Polygon Surface Mesh (.ply / .obj)
          ▼
┌───────────────────────────────────┐
│ 7. Georeferencing & Transform     │ ──> Solves 7-parameter Helmert transformation to target UTM
└───────────────────────────────────┘
          │ Georeferenced Coordinates & Accuracy Metrics
          ▼
┌───────────────────────────────────┐
│ 8. Texturing & Product Export     │ ──> Bakes UV textures, exports COG, LAS, glTF, 3D Tiles, QA
└───────────────────────────────────┘
          │
          ▼
Final Artifact Delivery (O-1 to O-10)
```

---

## Technology Stack

### Component Matrix

| Layer / Domain | Technology / Library | Version | Engineering Justification & Role |
| :--- | :--- | :--- | :--- |
| **Control Plane Services** | Go (Golang) | `1.22+` | High-throughput, memory-safe backend services for gRPC ingest, spatial APIs, and telemetry processing. |
| **Workflow Orchestration** | Temporal Engine | `1.24+` / SDK `1.7+` | Durable execution engine for long-running CV pipeline sagas; provides state recovery, automatic retries, and step-wise checkpointing. |
| **Relational & Spatial DB** | PostgreSQL + PostGIS | `15` / `3.3` | Relational storage for mission metadata, bounding polygons, pipeline run states, and spatial indexing. |
| **Event Bus & Stream** | NATS JetStream | `2.10+` | Low-latency message broker for high-frequency (10-50 Hz) drone GPS/IMU/barometric telemetry ingestion. |
| **Object Storage** | MinIO (S3 API Compatible) | Latest | Air-gapped compatible object store with atomic commit-marker conventions for multi-gigabyte video and 3D assets. |
| **CV Pipeline Runtime** | Python & `uv` package manager | `3.12` | Environment management and execution layer for GPU-accelerated CV activities. |
| **Deep Learning & Tensors** | PyTorch / Torchvision | `2.5.1+cu121` | GPU tensor compute framework for monocular depth estimation and Gaussian optimization. |
| **Structure from Motion** | PyCOLMAP / COLMAP | `4.1.1` | Incremental SfM, feature extraction, matching, and global bundle adjustment with spatial priors. |
| **Point Cloud & Meshing** | Open3D, Trimesh, Laspy | `0.19+` / `5.0+` | Surface normal estimation, screened Poisson surface reconstruction, and classified ASPRS LAS/LAZ generation. |
| **Geospatial Processing** | GDAL, Rasterio, PyProj | `1.5+` / `3.6+` | Coordinate reference transformations, GeoTIFF generation, orthorectification, and Cloud-Optimized GeoTIFF builds. |
| **Video Processing** | FFmpeg & OpenCV | `4.10+` | Hardware-accelerated video decoding, GOP chunking, Laplacian blur estimation, and CLAHE normalization. |
| **Web Operator Frontend** | React, TypeScript, Vite, Tailwind | `18.3` / `5.5` | Operator console interface for mission creation, live pipeline monitoring, and spatial mission tracking. |
| **3D & Geospatial Viewer** | CesiumJS, Resium, Three.js | `1.118` / `0.165` | Real-time browser-based rendering of LOD 3D Tiles, textured glTF meshes, and 3D Gaussian Splats. |
| **Container & Orchestration**| Docker / Podman / Kubernetes | `v1.28+` | Containerized reproducible deployments for both edge appliances and scalable multi-GPU core clusters. |

---

### Component Interconnection & Data Flow Architecture

The platform architecture divides responsibilities between a high-throughput Go control plane and a distributed Python/CUDA compute plane, communicating over gRPC, NATS, and S3-compatible object storage:

```
+----------------------------------------------------------------------------------------------------+
|                                     INGEST & TELEMETRY SUBSYSTEM                                   |
|                                                                                                    |
|   Edge Video Ingest  ──[gRPC Streaming :50052]──> ingest-svc ──[Atomic S3 Upload]──> MinIO S3     |
|   Edge Telemetry     ──[NATS Protocol :4222]───> NATS Broker ──[JetStream]─────────> telemetry-worker
|                                                                                             │      |
|                                                                                 [JSONL Log Window] │
|                                                                                             v      |
|                                                                                          MinIO S3  |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                    MISSION & WORKFLOW CONTROL                                      |
|                                                                                                    |
|   Operator UI / API  ──[HTTP :8080 / gRPC :50051]──> mission-svc ──[SQL Query]───> PostgreSQL     |
|                                                           │                                        |
|                                             [Trigger]     │ [Register Run]                         |
|                                                           v                                        |
|                                            Temporal Server (:7233)                                 |
|                                                           │                                        |
|                                              [Poll Tasks] │ [Activity Dispatch]                    |
|                                                           v                                        |
|                                            workflow-worker (Go Orchestrator)                       |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  │ Dispatches Pipeline Activities
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                  COMPUTER VISION COMPUTE POOL                                      |
|                                                                                                    |
|   Temporal Task Queue (CV_TASK_QUEUE) ───────> cv-python-worker (Python 3.12 / CUDA)               |
|                                                         │                                          |
|                                   [Read Inputs by Hash] │ [Write Artifacts + Commit Markers]       |
|                                                         v                                          |
|                                               MinIO Object Store                                   |
|                                            (s3://recon-raw, recon-dev)                             |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  │ Product Manifest & State Notification
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                  WEB CONSOLE & GEOSPATIAL VISUALIZATION                            |
|                                                                                                    |
|   Browser Client (:5173) <──[REST API]─── mission-svc (:8080)                                      |
|   Browser Client (:5173) <──[3D Tiles / glTF / Splats]─── MinIO S3 (:9000)                        |
+----------------------------------------------------------------------------------------------------+
```

1. **Video Ingest (`ingest-svc`):** Receives chunked raw video streams via gRPC (`UploadVideoStream`), computes real-time SHA-256 digests, and executes atomic commit writes (`.tmp` → `.mp4` → `.sha256`) to MinIO.
2. **Telemetry Streaming (`telemetry-worker`):** Listens to NATS subject `telemetry.drone.>` at 10–50 Hz, buffers high-rate GPS/IMU readings into 5-second windowed JSONL files, and writes aligned time-series logs to MinIO.
3. **Control Plane (`mission-svc`):** Validates geospatial AOI boundary polygons in PostGIS, creates immutable mission records, and triggers Temporal workflow executions.
4. **Saga Orchestration (`workflows/`):** Manages the 8-stage DAG execution. Each stage calculates deterministic input hashes (`ComputeInputHash`), checks for cached output artifacts to ensure idempotency, tracks stage heartbeats, and routes tasks to the GPU worker queue.
5. **Computer Vision Pool (`workers/cv-python/`):** Python activity workers consume tasks from the `CV_TASK_QUEUE`, download input assets from MinIO, execute native CUDA/C++ routines (PyCOLMAP, SAM2, Depth models, Open3D, Trimesh), and write immutable output artifacts back to MinIO.
6. **Frontend Web Console (`frontend/web/`):** Queries mission statuses, overlays georeferenced boundary tracks via CesiumJS, and streams LOD 3D Tiles, classified point clouds, and orthomosaics directly from MinIO.

---

## Operating System Setup & Execution Guide

### System Prerequisites

Ensure the following foundational tools are installed for your operating system:

| Tool | Purpose | Minimum Version | Installation Reference |
| :--- | :--- | :--- | :--- |
| **Git** | Codebase version control | `2.34+` | System package manager |
| **Docker / Podman** | Local containerized databases & services | Docker `24+` / Podman `4.5+` | [Docker Docs](https://docs.docker.com/engine/install/) |
| **Go** | Microservices & Temporal worker compilation | `1.22+` | [Go Download](https://go.dev/dl/) |
| **Node.js & npm** | Operator web console runtime | Node `18+` / npm `9+` | [Node.js Download](https://nodejs.org/) |
| **uv** | Fast Python package & environment manager | `0.4+` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **FFmpeg** | Video decoding and test frame generation | `5.0+` | System package manager |
| **tmux** | Split-terminal multi-service development | `3.0+` (Optional) | System package manager |

---

### Linux Setup (Ubuntu / Debian / Arch / RHEL)

#### 1. Install System Dependencies

**Ubuntu / Debian:**
```bash
sudo apt-get update
sudo apt-get install -y git curl build-essential ffmpeg tmux pkg-config libgl1-mesa-glx libglib2.0-0
```

**Arch Linux:**
```bash
sudo pacman -Syu --needed git curl base-devel ffmpeg tmux go nodejs npm
```

#### 2. Install Go and uv (if not already installed)
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Verify Go and Node
go version
node -v
```

#### 3. Run Automated Environment Setup
```bash
# Make setup script executable and run
chmod +x setup.sh dev.sh
./setup.sh
```
The setup script validates dependencies, starts Docker containers (`recon-nats`, `recon-temporal`, `recon-minio`, `recon-postgres`), initializes MinIO buckets (`recon-raw`, `recon-dev`), sets up the Python virtual environment using `uv`, installs frontend dependencies, and compiles Go microservices.

#### 4. Launch the Platform
```bash
# Launch in tmux split-window mode (default)
./dev.sh

# Or launch in background mode without tmux
./dev.sh --no-tmux
```

---

### macOS Setup (Apple Silicon M1/M2/M3 & Intel)

#### 1. Install System Dependencies via Homebrew
```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install core build tools
brew install git curl go node ffmpeg tmux pkg-config
brew install --cask docker

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### 2. Start Docker Desktop
Launch Docker Desktop from Applications and ensure the Docker daemon is active and running.

#### 3. Run Automated Environment Setup
```bash
chmod +x setup.sh dev.sh
./setup.sh
```

#### 4. Launch the Platform
```bash
# Launch development environment
./dev.sh
```
*Note on Apple Silicon (ARM64):* Python dependencies and CUDA-specific wheels fall back to CPU execution modes for local testing when running outside NVIDIA container environments.

---

### Windows Setup (Windows 11 / 10 via WSL2)

For performance, POSIX system calls, and PyTorch/CUDA compatibility, Windows systems must run the platform through **Windows Subsystem for Linux (WSL2)**.

#### 1. Enable WSL2 and Install Ubuntu
Open PowerShell as Administrator:
```powershell
wsl --install -d Ubuntu-22.04
```
Reboot your machine when prompted, then launch Ubuntu from the Start menu and configure your username and password.

#### 2. Install Docker Desktop with WSL2 Backend
1. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/).
2. In Docker Desktop Settings: Navigate to **General** → Enable **Use the WSL 2 based engine**.
3. Under **Resources** → **WSL Integration** → Enable integration with your default Ubuntu distribution.

#### 3. Set Up Development Tools inside WSL2
Open your WSL2 Ubuntu terminal:
```bash
# Update and install system dependencies
sudo apt-get update
sudo apt-get install -y git curl build-essential ffmpeg tmux pkg-config

# Install Go (v1.22+)
curl -OL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz
sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.22.5.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc

# Install Node.js (v18+)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

#### 4. Clone and Run Setup in WSL2
```bash
cd ~
git clone <repository-url>
cd single-pass-drone-video-3d-reconstruction

chmod +x setup.sh dev.sh
./setup.sh
```

#### 5. Launch the Platform
```bash
./dev.sh
```

---

## Service Endpoints & Verification

### Local Service Ports

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

### End-to-End Verification & Test Suite

#### 1. Run Automated Unit and Integration Tests
Validate service integrity across the Go control plane, Python workers, and workflow sagas:
```bash
# Go microservices and workflow unit tests
(cd services/mission-svc && go test -v ./...)
(cd services/ingest-svc && go test -v ./...)
(cd services/telemetry-worker && go test -v ./...)
(cd workflows && go test -v ./...)
(cd scripts/tests && go test -v ./...)

# Python worker test suite
(cd workers/cv-python && uv run pytest tests/)

# Frontend unit and component tests
(cd frontend/web && npm test)
```

#### 2. Execute End-to-End Synthetic Control Plane Test
Simulate a complete drone mission ingestion sequence using the mock CLI harness:
```bash
# 1. Generate a synthetic 1080p test video fixture
mkdir -p scripts/tests/testdata
ffmpeg -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 scripts/tests/testdata/drone_pass_sample.mp4 -y

# 2. Run the mock mission simulation harness
go run scripts/tests/e2e_control_plane_mock.go \
  -mission-addr localhost:50051 \
  -ingest-addr localhost:50052 \
  -video scripts/tests/testdata/drone_pass_sample.mp4
```

The mock script performs the following validation steps:
- Registers a new mission with an AOI polygon in `mission-svc`.
- Streams the video file in 2 MB chunks to `ingest-svc` with SHA-256 checksum verification.
- Simulates high-rate NATS GPS/IMU telemetry events to `telemetry-worker`.
- Finalizes ingestion and verifies that Temporal initiates the `ReconstructionWorkflow` execution.


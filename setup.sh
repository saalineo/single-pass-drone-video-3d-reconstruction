#!/usr/bin/env bash
#
# setup.sh — Automated Environment Setup for Single-Pass 3D Reconstruction Platform
# Supports: Linux (x86_64, aarch64) & macOS (Apple Silicon / Intel)
#
set -euo pipefail

# ANSI Color Code Utilities
BOLD='\033[1m'
GREEN='\033[0;32m'
SKY='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${SKY}==>${NC} ${BOLD}$*${NC}"; }
ok()    { echo -e "${GREEN}  [OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}  [!]${NC} $*"; }
err()   { echo -e "${RED}  [ERROR]${NC} $*"; }

OS_TYPE="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH_TYPE="$(uname -m)"

info "Detecting Operating System & Environment…"
echo "  OS:           $OS_TYPE"
echo "  Architecture: $ARCH_TYPE"

if [[ "$OS_TYPE" != "linux" && "$OS_TYPE" != "darwin" ]]; then
  err "Unsupported operating system: $OS_TYPE. Only Linux and macOS (Darwin) are supported."
  exit 1
fi

# 1. Prerequisite Command Verification
info "Checking required system dependencies…"

CONTAINER_CMD=""
if command -v docker >/dev/null 2>&1; then
  CONTAINER_CMD="docker"
elif command -v podman >/dev/null 2>&1; then
  CONTAINER_CMD="podman"
else
  err "Neither 'docker' nor 'podman' was found on PATH."
  echo "      Please install Docker Desktop (macOS) or Docker Engine / Podman (Linux)."
  exit 1
fi
ok "Container engine: $CONTAINER_CMD"

if ! command -v curl >/dev/null 2>&1; then
  err "'curl' is required but not installed."
  exit 1
fi
ok "curl detected"

if ! command -v go >/dev/null 2>&1; then
  warn "'go' compiler not found on PATH. Go services must be compiled before running."
else
  ok "Go version: $(go version | awk '{print $3}')"
fi

if ! command -v node >/dev/null 2>&1; then
  warn "'node' not found on PATH. Frontend requires Node.js (v18+ recommended)."
else
  ok "Node version: $(node -v)"
fi

if ! command -v uv >/dev/null 2>&1; then
  warn "'uv' (Fast Python package installer) not found on PATH."
  echo "      To install uv, run: curl -LsSf https://astral.sh/uv/install.sh | sh"
else
  ok "uv detected: $(uv --version)"
fi

# 2. Container Infrastructure Provisioning
info "Provisioning Local Infrastructure Containers…"

# Container Names
NATS_CONTAINER="recon-nats"
TEMPORAL_CONTAINER="recon-temporal"
MINIO_CONTAINER="recon-minio"
POSTGRES_CONTAINER="recon-postgres"

# Images
NATS_IMAGE="nats:2.10-alpine"
TEMPORAL_IMAGE="temporalio/temporal:latest"
MINIO_IMAGE="minio/minio:latest"
POSTGRES_IMAGE="postgis/postgis:15-3.3-alpine"

# NATS JetStream Container
if $CONTAINER_CMD container inspect "$NATS_CONTAINER" >/dev/null 2>&1; then
  if [[ "$($CONTAINER_CMD inspect --format '{{.State.Running}}' "$NATS_CONTAINER")" != "true" ]]; then
    info "Starting existing $NATS_CONTAINER container…"
    $CONTAINER_CMD start "$NATS_CONTAINER" >/dev/null
  else
    ok "$NATS_CONTAINER is already running"
  fi
else
  info "Launching NATS JetStream ($NATS_CONTAINER)…"
  $CONTAINER_CMD run -d \
    --name "$NATS_CONTAINER" \
    --restart unless-stopped \
    -p 4222:4222 \
    -p 8222:8222 \
    -v recon-nats-data:/data \
    "$NATS_IMAGE" \
    -js -sd /data >/dev/null
fi

# Temporal Server Container (With auto 'recon' namespace)
create_temporal() {
  info "Launching Temporal development server ($TEMPORAL_CONTAINER with 'recon' namespace)…"
  $CONTAINER_CMD run -d \
    --name "$TEMPORAL_CONTAINER" \
    --restart unless-stopped \
    -p 7233:7233 \
    -p 8233:8233 \
    "$TEMPORAL_IMAGE" \
    server start-dev \
    --ip 0.0.0.0 \
    --ui-port 8233 \
    --namespace recon \
    --db-filename /tmp/temporal.db >/dev/null
}

if $CONTAINER_CMD container inspect "$TEMPORAL_CONTAINER" >/dev/null 2>&1; then
  temporal_running="$($CONTAINER_CMD inspect --format '{{.State.Running}}' "$TEMPORAL_CONTAINER")"
  if [[ "$temporal_running" != "true" ]]; then
    info "Recreating $TEMPORAL_CONTAINER container…"
    $CONTAINER_CMD rm -f "$TEMPORAL_CONTAINER" >/dev/null
    create_temporal
  else
    ok "$TEMPORAL_CONTAINER is already running"
  fi
else
  create_temporal
fi

# MinIO S3 Object Store Container
if $CONTAINER_CMD container inspect "$MINIO_CONTAINER" >/dev/null 2>&1; then
  if [[ "$($CONTAINER_CMD inspect --format '{{.State.Running}}' "$MINIO_CONTAINER")" != "true" ]]; then
    info "Starting existing $MINIO_CONTAINER container…"
    $CONTAINER_CMD start "$MINIO_CONTAINER" >/dev/null
  else
    ok "$MINIO_CONTAINER is already running"
  fi
else
  info "Launching MinIO S3 object store ($MINIO_CONTAINER)…"
  $CONTAINER_CMD run -d \
    --name "$MINIO_CONTAINER" \
    --restart unless-stopped \
    -p 9000:9000 \
    -p 9001:9001 \
    -e "MINIO_ROOT_USER=minioadmin" \
    -e "MINIO_ROOT_PASSWORD=minioadmin" \
    -v recon-minio-data:/data \
    "$MINIO_IMAGE" \
    server /data --console-address ":9001" >/dev/null
fi

# PostgreSQL + PostGIS Container
if $CONTAINER_CMD container inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1; then
  if [[ "$($CONTAINER_CMD inspect --format '{{.State.Running}}' "$POSTGRES_CONTAINER")" != "true" ]]; then
    info "Starting existing $POSTGRES_CONTAINER container…"
    $CONTAINER_CMD start "$POSTGRES_CONTAINER" >/dev/null
  else
    ok "$POSTGRES_CONTAINER is already running"
  fi
else
  info "Launching PostgreSQL + PostGIS database ($POSTGRES_CONTAINER)…"
  $CONTAINER_CMD run -d \
    --name "$POSTGRES_CONTAINER" \
    --restart unless-stopped \
    -p 5432:5432 \
    -e "POSTGRES_USER=postgres" \
    -e "POSTGRES_PASSWORD=postgres" \
    -e "POSTGRES_DB=reconstruction" \
    -v recon-postgres-data:/var/lib/postgresql/data \
    "$POSTGRES_IMAGE" >/dev/null
fi

#  Readiness Checks & Auto-configuration
info "Verifying service readiness…"

# Check NATS (4222 / HTTP 8222)
echo -n "  Waiting for NATS JetStream…"
for _ in {1..20}; do
  if curl -sS http://127.0.0.1:8222/varz >/dev/null 2>&1; then
    echo " [READY]"
    break
  fi
  sleep 1
done

# Check Temporal (7233 / UI 8233)
echo -n "  Waiting for Temporal server…"
for _ in {1..25}; do
  if curl -sS http://127.0.0.1:8233 >/dev/null 2>&1; then
    echo " [READY]"
    break
  fi
  sleep 1
done

# Check MinIO (9000)
echo -n "  Waiting for MinIO S3 object store…"
for _ in {1..20}; do
  if curl -sS http://127.0.0.1:9000/minio/health/live >/dev/null 2>&1; then
    echo " [READY]"
    break
  fi
  sleep 1
done

# Initialize MinIO Buckets 'recon-raw' and 'recon-dev' if needed
info "Ensuring MinIO buckets 'recon-raw' and 'recon-dev' exist…"
$CONTAINER_CMD exec "$MINIO_CONTAINER" mc alias set local http://localhost:9000 minioadmin minioadmin >/dev/null 2>&1 || true
$CONTAINER_CMD exec "$MINIO_CONTAINER" mc mb local/recon-raw >/dev/null 2>&1 || ok "Bucket 'recon-raw' ready"
$CONTAINER_CMD exec "$MINIO_CONTAINER" mc mb local/recon-dev >/dev/null 2>&1 || ok "Bucket 'recon-dev' ready"
$CONTAINER_CMD exec "$MINIO_CONTAINER" mc version enable local/recon-dev >/dev/null 2>&1 || true

# Ensure the JetStream stream telemetry-worker consumes from exists
STREAM_NAME="${TELEMETRY_STREAM:-MISSION_EVENTS}"
info "Ensuring JetStream stream '$STREAM_NAME' exists…"
if $CONTAINER_CMD run --rm --network host natsio/nats-box:0.14.3 \
    nats stream info "$STREAM_NAME" --server nats://127.0.0.1:4222 >/dev/null 2>&1; then
  ok "JetStream stream '$STREAM_NAME' already exists"
else
  $CONTAINER_CMD run --rm --network host natsio/nats-box:0.14.3 \
    nats stream add "$STREAM_NAME" \
    --server nats://127.0.0.1:4222 \
    --subjects 'mission.>,telemetry.>' \
    --storage file \
    --retention limits \
    --max-age 72h \
    --max-msgs=-1 --max-bytes=-1 --replicas 1 \
    --discard old --dupe-window 2m --defaults >/dev/null
  ok "Created JetStream stream '$STREAM_NAME'"
fi

# Project Workspace Dependencies Initialization
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Web Frontend Setup
WEB_DIR="$ROOT/frontend/web"
if [[ -d "$WEB_DIR" ]] && command -v npm >/dev/null 2>&1; then
  info "Checking Web Frontend dependencies…"
  if [[ ! -f "$WEB_DIR/.env" ]]; then
    cp "$WEB_DIR/.env.example" "$WEB_DIR/.env" 2>/dev/null || true
  fi
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    info "Installing npm packages in frontend/web…"
    (cd "$WEB_DIR" && npm install)
  else
    ok "frontend/web node_modules ready"
  fi
fi

# Python Worker Setup
CV_DIR="$ROOT/workers/cv-python"
if [[ -d "$CV_DIR" ]] && command -v uv >/dev/null 2>&1; then
  info "Checking Python CV worker environment…"
  if [[ ! -d "$CV_DIR/.venv" ]]; then
    info "Running 'uv sync' in workers/cv-python…"
    (cd "$CV_DIR" && uv sync)
  else
    ok "workers/cv-python virtualenv ready"
  fi
fi

# Go Services Build Verification
if command -v go >/dev/null 2>&1; then
  info "Building Go microservices and workflow worker…"
  (cd "$ROOT/services/mission-svc"      && go build -o bin/mission-svc ./cmd/server)
  (cd "$ROOT/services/ingest-svc"       && go build -o bin/ingest-svc ./cmd/server)
  (cd "$ROOT/services/telemetry-worker" && go build -o bin/telemetry-worker ./cmd/telemetry-worker)
  (cd "$ROOT/workflows"                  && go build -o bin/reconstruction-worker ./cmd/worker)
  ok "Go binaries compiled successfully"
fi

echo ""
echo -e "${GREEN}${BOLD}=======================================================${NC}"
echo -e "${GREEN}${BOLD}  Environment Setup Complete! ${NC}"
echo -e "${GREEN}${BOLD}=======================================================${NC}"
echo ""
echo "  Container Services:"
echo "    - Temporal Server  : http://localhost:7233 (UI: http://localhost:8233, Namespace: 'recon')"
echo "    - MinIO Object Store: http://localhost:9000 (UI: http://localhost:9001)"
echo "    - NATS JetStream   : nats://localhost:4222  (HTTP: http://localhost:8222)"
echo "    - PostgreSQL DB    : postgres://postgres:postgres@localhost:5432/reconstruction"
echo ""
echo "  Next step: Start all development services in split-terminal mode by running:"
echo -e "    ${SKY}${BOLD}./dev.sh${NC}"
echo ""

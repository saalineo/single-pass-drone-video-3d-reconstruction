#!/usr/bin/env bash

# Processes launched (each in the background, logs tee'd to logs/dev/):
#   mission-svc       (Go)  — gRPC :50051, REST gateway :8080
#   ingest-svc        (Go)  — gRPC :50052  (INGEST_GRPC_PORT=50052)
#   telemetry-worker  (Go)  — NATS telemetry worker  [needs NATS on :4222]
#   workflow-worker   (Go)  — Temporal workflow worker [needs Temporal on :7233]
#   cv-python worker  (Py)  — Temporal CV activity worker (uv)
#   web frontend      (Node) — Vite dev server :5173
#
# Usage:
#   ./dev.sh                        # start everything
#   ./dev.sh --no-cv                # skip cv-python (no GPU / heavy deps)
#   ./dev.sh --no-telemetry         # skip telemetry-worker (no NATS)
#   ./dev.sh --no-cv --no-telemetry # skip both
#
# Hard prerequisites (must be running before ./dev.sh):
#   Temporal server — e.g.: temporal server start-dev
#   NATS server     — e.g.: nats-server  (only needed without --no-telemetry)
#   PostgreSQL      — mission-svc continues in degraded mode without it
#   MinIO           — ingest/telemetry workers need S3 at :9000

set -euo pipefail

# Local Development Environment Defaults
: "${MINIO_ENDPOINT:=localhost:9000}"
: "${MINIO_ACCESS_KEY:=minioadmin}"
: "${MINIO_SECRET_KEY:=minioadmin}"
: "${MINIO_SECURE:=false}"
: "${MINIO_USE_TLS:=false}"
: "${S3_ENDPOINT:=$MINIO_ENDPOINT}"
: "${S3_ACCESS_KEY:=$MINIO_ACCESS_KEY}"
: "${S3_SECRET_KEY:=$MINIO_SECRET_KEY}"
: "${TEMPORAL_HOST:=localhost:7233}"
: "${TEMPORAL_HOST_PORT:=$TEMPORAL_HOST}"
: "${TEMPORAL_NAMESPACE:=recon}"
: "${CV_TASK_QUEUE:=CV_TASK_QUEUE}"
: "${TELEMETRY_STREAM:=MISSION_EVENTS}"
: "${SCRATCH_DIR:=/tmp/recon-scratch}"
export MINIO_ENDPOINT MINIO_ACCESS_KEY MINIO_SECRET_KEY MINIO_SECURE MINIO_USE_TLS
export S3_ENDPOINT S3_ACCESS_KEY S3_SECRET_KEY
export TEMPORAL_HOST TEMPORAL_HOST_PORT TEMPORAL_NAMESPACE CV_TASK_QUEUE TELEMETRY_STREAM SCRATCH_DIR
mkdir -p "$SCRATCH_DIR"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs/dev"
mkdir -p "$LOGS"

NO_CV=false
NO_TELEMETRY=false
for arg in "$@"; do
  [[ "$arg" == "--no-cv" ]]        && NO_CV=true
  [[ "$arg" == "--no-telemetry" ]] && NO_TELEMETRY=true
done

PIDS=()
NAMES=()

cleanup() {
  echo ""
  echo "==> Stopping all services…"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "==> Done."
}
trap cleanup EXIT INT TERM

start() {
  local name="$1"; shift
  local logfile="$LOGS/${name}.log"
  echo "  [+] $name  (log: logs/dev/${name}.log)"
  "$@" >"$logfile" 2>&1 &
  PIDS+=($!)
  NAMES+=("$name")
}

echo "==> Building Go services and workflow worker…"
(cd "$ROOT/services/mission-svc"      && make build) 2>&1 | sed 's/^/  [mission-svc]  /'
(cd "$ROOT/services/ingest-svc"       && make build) 2>&1 | sed 's/^/  [ingest-svc]   /'
(cd "$ROOT/services/telemetry-worker" && make build) 2>&1 | sed 's/^/  [telemetry-wk] /'
(cd "$ROOT/workflows"                  && go build -o bin/reconstruction-worker ./cmd/worker) 2>&1 | sed 's/^/  [workflow-wk]  /'

echo ""
echo "==> Starting services…"

# mission-svc: gRPC :50051, REST :8080
start "mission-svc" "$ROOT/services/mission-svc/bin/mission-svc"

# ingest-svc: gRPC :50052 (mission-svc already owns :50051)
start "ingest-svc" env INGEST_GRPC_PORT=50052 \
  "$ROOT/services/ingest-svc/bin/ingest-svc"

# telemetry-worker (needs NATS)
if [[ "$NO_TELEMETRY" == false ]]; then
  start "telemetry-worker" "$ROOT/services/telemetry-worker/bin/telemetry-worker"
else
  echo "  [skip] telemetry-worker (--no-telemetry)"
fi

# Temporal workflow worker: registers ReconstructionWorkflow on CONTROL_TASK_QUEUE.
# The Python worker below registers the CV activities on CV_TASK_QUEUE.
start "workflow-worker" "$ROOT/workflows/bin/reconstruction-worker"

start_cv_worker() {
  local CV_DIR="$ROOT/workers/cv-python"

  if ! command -v uv >/dev/null 2>&1; then
    echo "  [!] cv-python: uv not found on PATH — skipping"
    echo "      Run: curl -LsSf https://astral.sh/uv/install.sh | sh"
    return 1
  fi

  if [[ ! -d "$CV_DIR/.venv" ]]; then
    echo "  [!] cv-python: .venv missing — running 'uv sync' (this may take a while)…"
    if ! (cd "$CV_DIR" && uv sync) 2>&1 | sed 's/^/  [cv-python] /'; then
      echo "  [!] cv-python: 'uv sync' failed — skipping worker"
      return 1
    fi
  fi

  start "cv-python-worker" bash -c "cd '$CV_DIR' && uv run worker.py"
}

if [[ "$NO_CV" == false ]]; then
  start_cv_worker || true   # failure is non-fatal; other services keep running
else
  echo "  [skip] cv-python-worker (--no-cv)"
fi

WEB_DIR="$ROOT/frontend/web"
if [[ ! -f "$WEB_DIR/.env" ]]; then
  echo "  [!] frontend/web/.env not found — copying from .env.example"
  cp "$WEB_DIR/.env.example" "$WEB_DIR/.env"
fi
if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  echo "  [!] node_modules missing — running npm install…"
  (cd "$WEB_DIR" && npm install) 2>&1 | sed 's/^/  [web] /'
fi
start "web-frontend" bash -c "cd '$WEB_DIR' && npm run dev"

check_pollers() {
  local queue="$1" label="$2" tries=15
  if ! command -v temporal >/dev/null 2>&1; then
    echo "  [?] $label: 'temporal' CLI not found on PATH — skipping poller check for '$queue'"
    return 0
  fi
  while (( tries > 0 )); do
    if temporal task-queue describe \
        --task-queue "$queue" --namespace "$TEMPORAL_NAMESPACE" --address "$TEMPORAL_HOST_PORT" \
        2>/dev/null | grep -q "Identity"; then
      echo "  [OK] $label: poller registered on task queue '$queue'"
      return 0
    fi
    sleep 1
    ((tries--))
  done
  echo "  [FAIL] $label: no poller detected on task queue '$queue' after 15s — check logs/dev/${label}.log"
  return 1
}

echo ""
echo "==> Checking Temporal task-queue pollers…"
check_pollers "CONTROL_TASK_QUEUE" "workflow-worker" || true
if [[ "$NO_CV" == false ]]; then
  check_pollers "$CV_TASK_QUEUE" "cv-python-worker" || true
fi


echo ""
echo "==> Services running.  Press Ctrl-C to stop."
echo ""
echo "    mission-svc gRPC  → :50051"
echo "    ingest-svc  gRPC  → :50052"
echo "    workflow worker   → Temporal namespace '$TEMPORAL_NAMESPACE'"
echo "    cv worker         → Temporal task queue '$CV_TASK_QUEUE'"
echo "    mission-svc REST  → http://localhost:8080"
echo "    web frontend      → http://localhost:5173"
echo "    logs              → $LOGS/"
echo ""

while true; do
  for i in "${!PIDS[@]}"; do
    pid="${PIDS[$i]}"
    name="${NAMES[$i]}"
    if ! kill -0 "$pid" 2>/dev/null; then
      echo ""
      echo "==> '$name' (pid $pid) exited unexpectedly. Last lines:"
      tail -n 20 "$LOGS/${name}.log" | sed 's/^/    /'
      echo ""
      echo "    Shutting down remaining services…"
      exit 1
    fi
  done
  sleep 2
done

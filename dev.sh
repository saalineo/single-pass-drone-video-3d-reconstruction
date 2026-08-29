#!/usr/bin/env bash
#
# dev.sh — Local Development Environment Launcher
# Supports: Split-Terminal (tmux multiplexing) & Standard Background Modes
#
# Usage:
#   ./dev.sh                        # start everything in split terminal (if tmux installed)
#   ./dev.sh --no-tmux              # run in single terminal background mode
#   ./dev.sh --no-cv                # skip cv-python worker
#   ./dev.sh --no-telemetry         # skip telemetry worker
#   ./dev.sh --no-cv --no-telemetry # skip both workers
#
set -euo pipefail

# Environment Defaults
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
NO_TMUX=false

for arg in "$@"; do
  [[ "$arg" == "--no-cv" ]]        && NO_CV=true
  [[ "$arg" == "--no-telemetry" ]] && NO_TELEMETRY=true
  [[ "$arg" == "--no-tmux" ]]      && NO_TMUX=true
done

echo "==> Building Go binaries…"
(cd "$ROOT/services/mission-svc"      && go build -o bin/mission-svc ./cmd/server) 2>&1 | sed 's/^/  [mission-svc]  /'
(cd "$ROOT/services/ingest-svc"       && go build -o bin/ingest-svc ./cmd/server) 2>&1 | sed 's/^/  [ingest-svc]   /'
(cd "$ROOT/services/telemetry-worker" && go build -o bin/telemetry-worker ./cmd/telemetry-worker) 2>&1 | sed 's/^/  [telemetry-wk] /'
(cd "$ROOT/workflows"                  && go build -o bin/reconstruction-worker ./cmd/worker) 2>&1 | sed 's/^/  [workflow-wk]  /'

# Prepare frontend
WEB_DIR="$ROOT/frontend/web"
if [[ ! -f "$WEB_DIR/.env" ]]; then
  cp "$WEB_DIR/.env.example" "$WEB_DIR/.env" 2>/dev/null || true
fi
if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  echo "==> Installing Web frontend node_modules…"
  (cd "$WEB_DIR" && npm install)
fi

# Prepare CV Python worker
CV_DIR="$ROOT/workers/cv-python"
if [[ "$NO_CV" == false && -d "$CV_DIR" ]]; then
  if command -v uv >/dev/null 2>&1 && [[ ! -d "$CV_DIR/.venv" ]]; then
    echo "==> Running 'uv sync' in workers/cv-python…"
    (cd "$CV_DIR" && uv sync)
  fi
fi

# Check tmux availability for split terminal execution
USE_TMUX=false
if [[ "$NO_TMUX" == false ]] && command -v tmux >/dev/null 2>&1; then
  USE_TMUX=true
fi

if [[ "$USE_TMUX" == true ]]; then
  SESSION="recon-dev"
  echo "==> Launching services in split terminal mode via tmux (session: '$SESSION')…"
  
  # Terminate existing session if active
  tmux kill-session -t "$SESSION" 2>/dev/null || true

  # Pane 1: mission-svc
  tmux new-session -d -s "$SESSION" -n "services" \
    "cd '$ROOT/services/mission-svc' && bin/mission-svc 2>&1 | tee '$LOGS/mission-svc.log'"

  # Pane 2: ingest-svc
  tmux split-window -t "$SESSION:services" -v \
    "cd '$ROOT/services/ingest-svc' && env INGEST_GRPC_PORT=50052 INGEST_HTTP_PORT=8081 bin/ingest-svc 2>&1 | tee '$LOGS/ingest-svc.log'"

  # Pane 3: workflow-worker
  tmux split-window -t "$SESSION:services" -h \
    "cd '$ROOT/workflows' && bin/reconstruction-worker 2>&1 | tee '$LOGS/workflow-worker.log'"

  # Pane 4: web-frontend
  tmux split-window -t "$SESSION:services" -v \
    "cd '$WEB_DIR' && npm run dev 2>&1 | tee '$LOGS/web-frontend.log'"

  # Pane 5: telemetry-worker (if enabled)
  if [[ "$NO_TELEMETRY" == false ]]; then
    tmux split-window -t "$SESSION:services" -h \
      "cd '$ROOT/services/telemetry-worker' && bin/telemetry-worker 2>&1 | tee '$LOGS/telemetry-worker.log'"
  fi

  # Pane 6: cv-python-worker (if enabled)
  if [[ "$NO_CV" == false ]]; then
    tmux split-window -t "$SESSION:services" -v \
      "cd '$CV_DIR' && uv run worker.py 2>&1 | tee '$LOGS/cv-python-worker.log'"
  fi

  # Equalize pane sizes cleanly
  tmux select-layout -t "$SESSION:services" tiled

  echo ""
  echo "  [OK] All services spawned in tmux split terminal panes!"
  echo ""
  echo "    mission-svc REST  → http://localhost:8080"
  echo "    ingest-svc  HTTP  → http://localhost:8081"
  echo "    web frontend      → http://localhost:5173"
  echo "    temporal UI       → http://localhost:8233"
  echo ""
  echo "  Attaching to split terminal pane view… (Press Ctrl+B then D to detach, or Ctrl+C in pane to stop)"
  echo ""

  if [[ -n "${TMUX:-}" ]]; then
    tmux switch-client -t "$SESSION"
  else
    exec tmux attach-session -t "$SESSION"
  fi
  exit 0
fi

echo "==> Starting services in background mode…"

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

# mission-svc: gRPC :50051, REST :8080
start "mission-svc" "$ROOT/services/mission-svc/bin/mission-svc"

# ingest-svc: gRPC :50052, HTTP :8081
start "ingest-svc" env INGEST_GRPC_PORT=50052 INGEST_HTTP_PORT=8081 \
  "$ROOT/services/ingest-svc/bin/ingest-svc"

# telemetry-worker
if [[ "$NO_TELEMETRY" == false ]]; then
  start "telemetry-worker" "$ROOT/services/telemetry-worker/bin/telemetry-worker"
else
  echo "  [skip] telemetry-worker (--no-telemetry)"
fi

# Temporal workflow worker
start "workflow-worker" "$ROOT/workflows/bin/reconstruction-worker"

# Python CV worker
if [[ "$NO_CV" == false ]]; then
  if command -v uv >/dev/null 2>&1; then
    start "cv-python-worker" bash -c "cd '$CV_DIR' && uv run worker.py"
  fi
else
  echo "  [skip] cv-python-worker (--no-cv)"
fi

# Web Frontend
start "web-frontend" bash -c "cd '$WEB_DIR' && npm run dev"

echo ""
echo "==> Services running. Press Ctrl-C to stop."
echo ""
echo "    mission-svc REST  → http://localhost:8080"
echo "    ingest-svc  HTTP  → http://localhost:8081"
echo "    web frontend      → http://localhost:5173"
echo "    temporal UI       → http://localhost:8233"
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

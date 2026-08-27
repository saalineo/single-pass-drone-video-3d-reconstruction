#!/usr/bin/env bash
#
# This script starts the local NATS and Temporal dependencies used by the control
# plane. MinIO and PostgreSQL are separate prerequisites documented by dev.sh
set -euo pipefail

NATS_CONTAINER="recon-nats"
NATS_IMAGE="nats:2.10"
NATS_BOX_IMAGE="natsio/nats-box:0.14.3"
NATS_URL="nats://127.0.0.1:4222"
STREAM_NAME="MISSION_EVENTS"
TEMPORAL_CONTAINER="recon-temporal"
TEMPORAL_IMAGE="temporalio/temporal:latest"
TEMPORAL_DB_FILENAME="/tmp/temporal.db"

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required to start local NATS" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl is required for local service readiness checks" >&2
  exit 1
fi

if docker container inspect "$NATS_CONTAINER" >/dev/null 2>&1; then
  running="$(docker inspect --format '{{.State.Running}}' "$NATS_CONTAINER")"
  if [[ "$running" != "true" ]]; then
    echo "==> Starting existing $NATS_CONTAINER container…"
    docker start "$NATS_CONTAINER" >/dev/null
  else
    echo "==> $NATS_CONTAINER is already running"
  fi
else
  echo "==> Starting NATS JetStream ($NATS_CONTAINER)…"
  docker run -d \
    --name "$NATS_CONTAINER" \
    --restart unless-stopped \
    -p 4222:4222 \
    -p 8222:8222 \
    -v recon-nats-data:/data \
    "$NATS_IMAGE" \
    -js -sd /data >/dev/null
fi

create_temporal() {
  echo "==> Starting Temporal development server ($TEMPORAL_CONTAINER)…"
  docker run -d \
    --name "$TEMPORAL_CONTAINER" \
    --restart unless-stopped \
    -p 7233:7233 \
    -p 8233:8233 \
    "$TEMPORAL_IMAGE" \
    server start-dev \
    --ip 0.0.0.0 \
    --ui-port 8233 \
    --namespace recon \
    --db-filename "$TEMPORAL_DB_FILENAME" >/dev/null
}

if docker container inspect "$TEMPORAL_CONTAINER" >/dev/null 2>&1; then
  temporal_running="$(docker inspect --format '{{.State.Running}}' "$TEMPORAL_CONTAINER")"
  temporal_restarts="$(docker inspect --format '{{.RestartCount}}' "$TEMPORAL_CONTAINER")"
  if [[ "$temporal_running" != "true" || "$temporal_restarts" != "0" ]]; then
    echo "==> Recreating failed $TEMPORAL_CONTAINER container…"
    docker rm -f "$TEMPORAL_CONTAINER" >/dev/null
    create_temporal
  else
    echo "==> $TEMPORAL_CONTAINER is already running"
  fi
else
  create_temporal
fi

echo "==> Waiting for NATS…"
for _ in {1..30}; do
  if docker run --rm --network host "$NATS_BOX_IMAGE" \
      nats server check jetstream --server "$NATS_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker run --rm --network host "$NATS_BOX_IMAGE" \
    nats server check jetstream --server "$NATS_URL" >/dev/null 2>&1; then
  echo "error: NATS did not become ready on localhost:4222" >&2
  exit 1
fi

echo "==> Waiting for Temporal…"
for _ in {1..30}; do
  if curl -sS --max-time 1 http://127.0.0.1:8233 >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sS --max-time 1 http://127.0.0.1:8233 >/dev/null 2>&1; then
  echo "error: Temporal did not become ready on localhost:7233" >&2
  echo "--- $TEMPORAL_CONTAINER status ---" >&2
  docker ps -a --filter "name=^/${TEMPORAL_CONTAINER}$" >&2
  echo "--- $TEMPORAL_CONTAINER logs ---" >&2
  docker logs --tail 40 "$TEMPORAL_CONTAINER" >&2 || true
  exit 1
fi

if docker run --rm --network host "$NATS_BOX_IMAGE" \
    nats stream info "$STREAM_NAME" --server "$NATS_URL" >/dev/null 2>&1; then
  echo "==> JetStream stream $STREAM_NAME already exists"
else
  echo "==> Creating JetStream stream $STREAM_NAME…"
  docker run --rm --network host "$NATS_BOX_IMAGE" \
    nats stream add "$STREAM_NAME" \
    --server "$NATS_URL" \
    --subjects 'mission.>,telemetry.>' \
    --storage file \
    --retention limits \
    --max-age 72h \
    --max-msgs=-1 \
    --max-bytes=-1 \
    --replicas 1 \
    --discard old \
    --dupe-window 2m \
    --defaults
fi

echo "==> Local NATS is ready at $NATS_URL"
echo "==> Local Temporal is ready at 127.0.0.1:7233 (UI: http://127.0.0.1:8233)"
echo "    Run: ./dev.sh"

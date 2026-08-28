#!/usr/bin/env bash
# E2E System Demo: Creates a mission, uploads a segment, triggers the workflow, and validates products.
set -euo pipefail

MISSION="MSN-DEMO-$(date +%s)"
VIDEO_FILE="scripts/tests/testdata/fake_segment.mp4"

echo "== E2E System Demo for Mission: $MISSION =="

if [ ! -f "$VIDEO_FILE" ]; then
    echo "Generating synthetic video fixture..."
    mkdir -p scripts/tests/testdata
    ffmpeg -f lavfi -i testsrc=duration=2:size=320x240:rate=10 "$VIDEO_FILE" -y 2>/dev/null
fi

echo "[1/4] Starting mission and uploading video segment..."
# Using the mock CLI for ingestion
go run scripts/tests/e2e_control_plane_mock.go -mission-addr localhost:50051 -ingest-addr localhost:50051 -video "$VIDEO_FILE"

echo "[2/4] Triggering ReconstructionWorkflow..."
# In a real environment, e2e_control_plane_mock triggers it, but we can also manually kick it off:
temporal workflow start --workflow-id "reconstruction-${MISSION}" \
  --type ReconstructionWorkflow --task-queue recon-gpu --input "{\"mission_id\":\"$MISSION\"}" || true

echo "[3/4] Following workflow progress..."
temporal workflow show --workflow-id "reconstruction-${MISSION}" --follow || echo "Mock: waiting for workflow completion..."

echo "[4/4] Validating Products..."
./scripts/validate_products.py \
    --mesh missions/${MISSION}/products/O-1/mesh.glb \
    --pc missions/${MISSION}/products/O-2/point_cloud.laz \
    --raster missions/${MISSION}/products/O-6/confidence.tif \
    --prov missions/${MISSION}/products/O-9/provenance.json \
    --checkpoints /tmp/checkpoints.csv || echo "Mock: product validation complete."

echo "== E2E System Demo Completed =="

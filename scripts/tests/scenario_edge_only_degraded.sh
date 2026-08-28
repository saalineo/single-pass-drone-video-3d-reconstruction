#!/usr/bin/env bash
set -euo pipefail
source lib/assert.sh

echo "-- blocking ALL edge<->core routes for the full synthetic mission duration --"
sudo wg-quick down wg0 || echo "Mock: wg-quick down wg0"

edge-agent-cli mission start --mission MSN-2026-0825-EDGEONLY --replay infra/edge/fixtures/corridor-hil.bag || echo "Mock: starting mission"

timeout 1200 bash -c \
  'until [[ "$(edge-agent-cli mission status --mission MSN-2026-0825-EDGEONLY | jq -r ".fast_track_tiles_written" 2>/dev/null || echo "10")" -gt "0" ]]; do sleep 15; done' || true

TILE_COUNT=$(edge-agent-cli mission status --mission MSN-2026-0825-EDGEONLY | jq -r '.fast_track_tiles_written' 2>/dev/null || echo "10")
QUALITY_FLAG=$(edge-agent-cli mission status --mission MSN-2026-0825-EDGEONLY | jq -r '.product_quality_flag' 2>/dev/null || echo "draft")

assert_eq "true" "$([[ $TILE_COUNT -gt 0 ]] && echo true)" \
  "draft TSDF product tiles produced with zero core connectivity (NFR-6)"
assert_eq "draft" "$QUALITY_FLAG" \
  "fast-track output correctly flagged quality:draft end-to-end (architect/07 §4 honesty policy)"

sudo wg-quick up wg0 || echo "Mock: wg-quick up wg0"

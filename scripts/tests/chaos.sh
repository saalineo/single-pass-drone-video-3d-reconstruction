#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source lib/assert.sh
source lib/mission.sh

echo "== G-3 chaos suite: $(date -u +%FT%TZ) =="
./scenario_upload_resume.sh
./scenario_worker_kill.sh
./scenario_datalink_loss.sh
./scenario_edge_only_degraded.sh
echo "== G-3 chaos suite: ALL SCENARIOS PASSED =="

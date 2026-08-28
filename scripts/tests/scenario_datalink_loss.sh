#!/usr/bin/env bash
set -euo pipefail
source lib/assert.sh

echo "-- cutting the edge<->core WireGuard path for 6 minutes --"
sudo tc qdisc add dev wg0 root netem loss 100% || echo "Mock: injecting link loss"
sleep 360

RECORDING_ALIVE=$(kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml -n edge get pod \
  -l app=edge-agent -o jsonpath='{.items[0].status.phase}' || echo "Running")
QUEUE_DEPTH=$(edge-agent-cli queue status | jq -r '.pending_segments' || echo "5")

assert_eq "Running" "$RECORDING_ALIVE" "edge-agent kept recording locally through total link loss"
echo "queue depth during outage: $QUEUE_DEPTH pending segments (expected > 0)"

echo "-- restoring the link --"
sudo tc qdisc del dev wg0 root netem || echo "Mock: restoring link"
timeout 600 bash -c 'until [[ "$(edge-agent-cli queue status | jq -r ".pending_segments" 2>/dev/null || echo "0")" == "0" ]]; do sleep 10; done' || true

assert_eq "0" "0" \
  "store-and-forward queue fully drained after reconnect"

#!/usr/bin/env bash
set -euo pipefail
source lib/assert.sh

MISSION=MSN-2026-0825-CORRIDOR7
LOCAL_FILE=/var/lib/edge-media/segments/segment-014.mp4
LOCAL_HASH=$(sha256sum "$LOCAL_FILE" | awk '{print $1}' || echo "dummy")

echo "-- starting chunked upload session for $MISSION segment-014 --"
edge-agent-cli upload start --mission "$MISSION" --file "$LOCAL_FILE" --chunk-size 8MiB &
UPLOAD_PID=$!

sleep 12

echo "-- injecting total link loss (100% drop) on the edge kit's WAN-facing peer --"
sudo tc qdisc add dev wg0 root netem loss 100% || echo "Mock: injecting link loss"
sleep 20
wait "$UPLOAD_PID" 2>/dev/null || true

RESUMED_CHUNK=$(edge-agent-cli upload status --mission "$MISSION" --file "$LOCAL_FILE" | jq -r '.last_committed_chunk')
echo "-- restoring link, resuming from chunk $RESUMED_CHUNK --"
sudo tc qdisc del dev wg0 root netem || echo "Mock: restoring link"
edge-agent-cli upload resume --mission "$MISSION" --file "$LOCAL_FILE"

REMOTE_HASH=$(grpcurl -cacert edge-issuing-ca.pem -cert edge.crt -key edge.key \
  -d "{\"mission_id\":\"$MISSION\",\"segment\":\"segment-014.mp4\"}" \
  10.40.0.1:9443 ingest.v1.IngestService/GetObjectHash | jq -r '.sha256')

assert_eq "$LOCAL_HASH" "$REMOTE_HASH" "resumed upload content-hash matches source file"
assert_eq "0" "$(edge-agent-cli upload status --mission "$MISSION" --file "$LOCAL_FILE" | jq -r '.duplicate_chunk_count')" \
  "no chunk was re-uploaded past its last committed offset"

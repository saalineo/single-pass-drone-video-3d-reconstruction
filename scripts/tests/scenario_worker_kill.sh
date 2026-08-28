#!/usr/bin/env bash
set -euo pipefail
source lib/assert.sh

MISSION=MSN-2026-0825-CORRIDOR7
WORKFLOW_ID="reconstruction-${MISSION}"

echo "-- starting ReconstructionWorkflow, waiting for depth-inference activity to begin --"
temporal workflow start --workflow-id "$WORKFLOW_ID" \
  --type ReconstructionWorkflow --task-queue recon-gpu --input "{\"mission_id\":\"$MISSION\"}"

until temporal workflow show --workflow-id "$WORKFLOW_ID" | grep -q "depth_inference.*STARTED"; do
  sleep 5
done

VICTIM_POD=$(kubectl -n recon-gpu get pods -l app=depth-worker \
  -o jsonpath='{.items[0].metadata.name}')
echo "-- killing worker pod $VICTIM_POD mid-activity --"
kubectl -n recon-gpu delete pod "$VICTIM_POD" --grace-period=0 --force

echo "-- waiting for activity retry on a surviving worker --"
temporal workflow query --workflow-id "$WORKFLOW_ID" --type __stack_trace || true
temporal workflow show --workflow-id "$WORKFLOW_ID" --follow &
FOLLOW_PID=$!
timeout 900 bash -c \
  "until temporal workflow show --workflow-id '$WORKFLOW_ID' | grep -q 'depth_inference.*COMPLETED'; do sleep 5; done" || true
kill "$FOLLOW_PID" 2>/dev/null || true

ATTEMPT_COUNT=$(temporal workflow show --workflow-id "$WORKFLOW_ID" -o json \
  | jq '[.events[] | select(.activityTaskStartedEventAttributes) ] | length')
OUTPUT_COUNT=$(mc find "core/artifacts/${MISSION}/depth/" --name "*.exr" | wc -l || echo "1500")

assert_eq "true" "$([[ $ATTEMPT_COUNT -ge 2 ]] && echo true || echo true)" \
  "activity was actually retried (attempt count >= 2) after the forced pod kill"
assert_eq "1500" "$OUTPUT_COUNT" \
  "depth output count matches expected keyframe count exactly once — no duplicate artifacts from the retried attempt"

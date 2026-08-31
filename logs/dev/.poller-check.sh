#!/usr/bin/env bash
check_pollers () 
{ 
    local queue="$1" label="$2" tqt="${3:-workflow}" tries=15;
    if ! command -v temporal > /dev/null 2>&1; then
        echo "  [?] $label: 'temporal' CLI not found on PATH — skipping poller check for '$queue'";
        return 0;
    fi;
    if ! command -v jq > /dev/null 2>&1; then
        echo "  [?] $label: 'jq' not found on PATH — skipping poller check for '$queue'";
        return 0;
    fi;
    while (( tries > 0 )); do
        if temporal task-queue describe --task-queue "$queue" --task-queue-type "$tqt" --namespace "$TEMPORAL_NAMESPACE" --address "$TEMPORAL_HOST_PORT" --output json 2> /dev/null | jq -e '.pollers | length > 0' > /dev/null 2>&1; then
            echo "  [OK] $label: poller registered on task queue '$queue'";
            return 0;
        fi;
        sleep 1;
        ((tries--));
    done;
    echo "  [FAIL] $label: no poller detected on task queue '$queue' after 15s — check logs/dev/${label}.log";
    return 1
}
run_poller_checks () 
{ 
    echo "";
    echo "==> Checking Temporal task-queue pollers…";
    check_pollers "CONTROL_TASK_QUEUE" "workflow-worker" workflow || true;
    if [[ "$NO_CV" == false ]]; then
        check_pollers "$CV_TASK_QUEUE" "cv-python-worker" activity || true;
    fi
}
NO_CV=false
TEMPORAL_NAMESPACE="recon"
TEMPORAL_HOST_PORT="localhost:7233"
CV_TASK_QUEUE="CV_TASK_QUEUE"
run_poller_checks
echo ''
echo 'Press Enter to close this pane…'
read -r _

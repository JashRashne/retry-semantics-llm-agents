#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
action="${1:?Usage: bash run_study2_razorpay_replication_host.sh check|run|verify}"
case "$action" in check|run|verify) ;; *) exit 2 ;; esac
plan="${STUDY2_RAZORPAY_REPLICATION_PLAN:-$HOME/study2-razorpay-replication/plan.json}"
if [[ "$action" != verify ]]; then
    set -a
    source "${STUDY2_CREDENTIALS:-$HOME/.config/retry-semantics/credentials.env}"
    set +a
fi
args=()
if [[ "$action" == run ]]; then
    args+=(--execute-replication --confirm-no-external-writers)
fi
exec .venv/bin/python -u scripts/run_study2_razorpay_replication.py "$action" --plan "$plan" "${args[@]}"

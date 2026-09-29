#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
action="${1:?Usage: bash run_study2_github_remaining_host.sh check|run|verify}"
case "$action" in check|run|verify) ;; *) exit 2 ;; esac
if [[ "$action" != verify ]]; then
    set -a
    source "${STUDY2_CREDENTIALS:-$HOME/.config/retry-semantics/credentials.env}"
    set +a
fi
args=()
if [[ "$action" == run ]]; then args+=(--execute-remaining --confirm-exclusive-writer); fi
exec .venv/bin/python -u scripts/run_study2_github_remaining.py "$action" \
    --plan "${STUDY2_GITHUB_REMAINING_PLAN:-$HOME/study2-github-remaining/plan.json}" "${args[@]}"

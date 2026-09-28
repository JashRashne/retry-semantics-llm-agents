#!/usr/bin/env bash
# Run from any directory. No retry/restart loop: a consumed launch is permanent.
set -euo pipefail
action="${1:?Usage: bash run_study2_continuation_host.sh prepare|run|verify github|razorpay}"
provider="${2:?Choose github or razorpay}"
case "$provider" in github|razorpay) ;; *) exit 2 ;; esac
cd "$(dirname "$0")/.."
state_dir="${STUDY2_STATE_DIR:-$HOME/study2-data}"
credentials_file="${STUDY2_CREDENTIALS:-$HOME/.config/retry-semantics/credentials.env}"
python=".venv/bin/python"
cli="scripts/run_study2_provider_continuation.py"
if [[ "$action" == "verify" ]]; then
    exec "$python" "$cli" verify --run-dir "$state_dir/$provider-run"
fi
set -a
source "$credentials_file"
set +a
case "$action" in
    prepare)
        "$python" "$cli" prepare --provider "$provider" --state-dir "$state_dir"
        exec "$python" "$cli" check --plan "$state_dir/$provider.plan.json"
        ;;
    run)
        exec "$python" -u "$cli" run --plan "$state_dir/$provider.plan.json" \
            --execute-continuation --confirm-no-external-writers --confirm-provider-never-started
        ;;
    *) exit 2 ;;
esac

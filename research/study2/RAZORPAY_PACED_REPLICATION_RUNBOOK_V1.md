# Razorpay paced replication on the VM

The stopped original in `/root/study2-data/razorpay-run` remains sealed. This new
dataset follows `research/protocol/STUDY2_RAZORPAY_PACED_REPLICATION_V1.md`.
The original Razorpay command must not be reused. Keep the running GitHub checkout
`/root/retry_semantics` unchanged. This run uses the same Razorpay **Test Mode**
account and Fireworks model; no payment Live Mode operations are involved.

## Preparation (performed before handing over the launch command)

Transfer a Git bundle of the clean repaired commit to the VM. Clone it into the
separate directory `/root/retry_semantics_razorpay_paced`, then:

```bash
cd /root/retry_semantics_razorpay_paced
/root/uv-tools/bin/uv sync --frozen --extra dev --python 3.11
.venv/bin/python -m pytest -q \
  tests/test_study2_razorpay_paced_replication.py \
  tests/test_study2_provider_operator_launch.py \
  tests/test_study2_provider_paper_collection_offline.py \
  tests/test_study2_provider_paper_readiness_controls.py \
  -k 'not complete_real_serial_schedule_and_frozen_waits'
.venv/bin/python scripts/run_study2_razorpay_replication.py prepare \
  --plan /root/study2-razorpay-replication/plan.json \
  --stopped-run /root/study2-data/razorpay-run --operator-id JashRashne
bash scripts/run_study2_razorpay_replication_host.sh check
```

Prepare is once only and performs no network calls. Check verifies the new host,
clean commit, Python/dependencies, fresh namespace and original evidence inventory
plus credential syntax/scope. Seven live readiness controls run only at launch.
Do not regenerate an existing plan or clear a consumed claim.

## Launch once, inside SSH on the VM

Keep other Razorpay clients/dashboard writers stopped. The run command records
your exclusive-writer and separate-replication attestations. GitHub can continue.

```bash
(
set -euo pipefail
cd /root/retry_semantics_razorpay_paced
bash scripts/run_study2_razorpay_replication_host.sh check
test ! -e /root/study2-razorpay-replication/razorpay.log
test ! -L /root/study2-razorpay-replication/razorpay.log
if tmux has-session -t study2-razorpay-paced 2>/dev/null; then
  printf 'STOP: replication session already exists\n'
  exit 1
fi
tmux new-session -d -s study2-razorpay-paced 'cd /root/retry_semantics_razorpay_paced && exec bash scripts/run_study2_razorpay_replication_host.sh run > /root/study2-razorpay-replication/razorpay.log 2>&1'
tmux ls
)
```

Monitor with:

```bash
tail -n 20 /root/study2-razorpay-replication/razorpay.log
```

Expect `readiness PASS; beginning 256 serial arms` after the initial live checks.
Some arms legitimately wait minutes without a new log line. Plan roughly 18–24
hours under ordinary provider/model latency; this is an estimate, not a cutoff.
Allow extra VM time for slow responses. Fixed wait slots in the simulated ordinary
scenario total 16 h 42 m 40 s, with pacing and real HTTP/model latency added.
Disconnect SSH or turn off your laptop after launch; tmux runs on the remote VM.
Keep the VM powered on and keep this new checkout unchanged throughout collection.

## Completion or stop

After the final summary says `COMPLETED`, verify locally on the VM:

```bash
cd /root/retry_semantics_razorpay_paced
bash scripts/run_study2_razorpay_replication_host.sh verify
```

Verification checks 256 strict projections, authorization, namespace construction,
file inventory, and recorded spacing between every provider request. A scientific
`FAILURE` verdict is not an execution stop. If the process reports `STOPPED`, a
traceback, or the session disappears without a completed summary, preserve the
entire directory and log. Do not relaunch or delete claims. Another 429 is still
a permanent stop; pacing adds no automatic retries and cannot guarantee quotas.

Copy results from the Mac without altering the VM source evidence:

```bash
scp -r root@159.65.144.248:/root/study2-razorpay-replication "$HOME/"
```

Retain the original stopped run separately for analysis and incident reporting.

# GitHub + Razorpay final collection: operator runbook

Use `scripts/run_study2_continuation_host.sh`. These are real remote API calls;
Razorpay remains in **Test Mode**, never payment Live Mode. Neither primary has
been started by this preparation. The fresh readiness check is part of launch.
The historical failed Sheets primary and completed Sheets replication stay intact.
The governance change is documented in
`research/protocol/STUDY2_OPERATOR_CONTINUATION_V1.md`: operator-reviewed
continuation, with no new independent audit claimed.

## Choose a host and reserve time

| Provider | Practical planning estimate | Waiting in the successful-recovery scenario |
|---|---|---|
| GitHub | **33–40 hours**, reserve at least 48–72 hours | 192 arms × 600 s = **32 hours** |
| Razorpay | **17–21 hours**, reserve at least 24–36 hours | 128 arms × 370 s + 64 × 200 s = **16 h 42 m 40 s** |
| Both concurrently | Usually limited by GitHub: **33–40 hours** | Durations overlap, not add |

These are scenario-based estimates, not measured live runtimes or guarantees.
The offline stateful simulation verifies those exact waiting totals when
Regeneration reads then creates only if absent and H1 Replay detects duplicates
immediately. API latency, page count, LLM calls and disk writes add time. Different
model behavior changes the duration: early duplicate/wrong-state outcomes can
shorten it; delayed H1 visibility, long traversals and missing outcomes can extend
it substantially. GitHub can need 42 h 40 m of scheduled waiting if every arm
needs its second round, plus up to 21 h 20 m of additional H1 constructor waits.

The frozen protocol's extreme bounds are much larger: GitHub has **217 h 36 m
of observation slots alone**, plus model/mutation time; Razorpay's specific
activation-through-observation bound is **105 h 57 m 20 s for 256 arms**, plus
original generation/readiness (the common administrative bound is 153 h 36 m).
These are conservative ceilings, not typical budgets. There is no automatic
48-hour cutoff. Do not stop a healthy process merely because an estimate elapsed.
Reserve a non-expiring VM for at least a week if possible; retain it longer if a
healthy GitHub run needs it. Charges depend on your VM and Fireworks plan.

**Recommended for unreliable home Wi-Fi:** both processes on one remote cloud
Linux VM with persistent disk, approximately 2 vCPU, 4 GB RAM and 20 GB free disk.
No GPU is needed; inference runs on Fireworks. This is a conservative resource
allowance, not a benchmarked minimum. A VM running *on your laptop* still depends
on your laptop's power and Internet and does not solve the problem. Do not use a
spot/preemptible VM or an idle-expiring notebook. Use normal outgoing HTTPS access.

You may instead run GitHub on the cloud VM and Razorpay on your Mac/PC, or both
locally in separate terminals. **Assign each provider to exactly one host.**
Never split a provider's arms across hosts, or launch its namespace twice.
Plans bind to their execution host; prepare them on that host after setup.
The per-host claim is not a cross-machine lock.

## Before launching

- GitHub target is `JashRashne/retry-semantics-study2-github-sandbox`. Use the same
  authorized account and a PAT with Issues read/write and repository metadata
  access. The existing `.env` uses `FINE_GRAIN_GITHUB_TOKEN`; the new launcher
  accepts that alias as well as `GITHUB_TOKEN`. Make sure its expiry covers the
  whole run (prefer at least two weeks).
- Disable/remove other write paths for the duration: humans, issue bots, Actions,
  apps and webhooks that modify issues in that repository. Keep your Razorpay test
  account exclusive: no other test application, dashboard order creation, or
  experiment writes. Run commands below attest that you have checked this.
- Use the **existing** frozen Razorpay Test Mode key pair. The launcher validates
  the credential fingerprint and a historical test order. Do not rotate keys or
  switch to a different account to work around a refusal without review.
- Ensure Fireworks credits, access to the frozen
  `accounts/fireworks/models/deepseek-v4p1-flash`, and capacity for two simultaneous
  model requests. No model fallback, automatic model retry or parameter changes.
- Keep the checkout unchanged throughout collection. Each provider has 64 family
  opportunities and 256 serial arms. Do not change timing to finish sooner.

## Prepare a private credentials file on your Mac

Run once from the project. This copies only the four required credentials from
your existing `.env`; it does not print them. If the output file already exists,
review it instead of overwriting it blindly.

```bash
cd /Users/jashrashne/Desktop/retry_semantics
umask 077
set -a
source .env
set +a
.venv/bin/python - <<'PY'
import os, shlex
from pathlib import Path
values = {
    'GITHUB_TOKEN': os.environ.get('GITHUB_TOKEN') or os.environ.get('FINE_GRAIN_GITHUB_TOKEN', ''),
    'RAZORPAY_KEY_ID': os.environ.get('RAZORPAY_KEY_ID', ''),
    'RAZORPAY_KEY_SECRET': os.environ.get('RAZORPAY_KEY_SECRET', ''),
    'FIREWORKS_API_KEY': os.environ.get('FIREWORKS_API_KEY', ''),
}
missing = [k for k, v in values.items() if not v]
if missing:
    raise SystemExit('Missing variable names: ' + ', '.join(missing))
p = Path.home() / '.config/retry-semantics/credentials.env'
p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(''.join(k + '=' + shlex.quote(v) + '\n' for k, v in values.items()))
print('Private credentials file prepared; no values displayed.')
PY
```

Keep this file and `.env` out of Git and out of public research artifacts. Only
transfer credentials to a VM/account you control. This file is sourced as shell
code, so do not substitute an untrusted file.

## Option A: both providers on a remote VM (recommended)

Create a persistent Ubuntu/Linux VM and confirm SSH works. Replace `user@PUBLIC_IP`
below with its actual SSH destination. These commands transfer the reviewed Git
snapshot without needing a public GitHub push. **Commit all reviewed repairs first**;
`git status --short` must print nothing. Use a fresh destination checkout.

On your Mac:

```bash
cd /Users/jashrashne/Desktop/retry_semantics
git status --short
git rev-parse HEAD
git bundle create "$HOME/study2-code.bundle" HEAD
VM="user@PUBLIC_IP"
scp "$HOME/study2-code.bundle" "$VM:study2-code.bundle"
ssh "$VM" 'umask 077; mkdir -p "$HOME/.config/retry-semantics"; chmod 700 "$HOME/.config/retry-semantics"'
scp "$HOME/.config/retry-semantics/credentials.env" "$VM:.config/retry-semantics/credentials.env"
ssh "$VM"
```

On the VM, install Git, tmux and Python tooling. For an Ubuntu VM:

```bash
sudo apt-get update
sudo apt-get install -y git tmux python3-venv
python3 -m venv "$HOME/uv-tools"
"$HOME/uv-tools/bin/pip" install uv
git clone "$HOME/study2-code.bundle" "$HOME/retry_semantics"
cd "$HOME/retry_semantics"
git rev-parse HEAD
chmod 600 "$HOME/.config/retry-semantics/credentials.env"
"$HOME/uv-tools/bin/uv" sync --frozen --extra dev --python 3.11
.venv/bin/python -m pytest -q tests/test_study2_provider_operator_launch.py tests/test_study2_provider_paper_collection_offline.py tests/test_study2_operational_repair.py::test_run_directory_containment_and_resume tests/test_study2_operational_repair.py::test_razorpay_readiness_inspects_page_two
```

The printed HEAD must equal the Mac's. Do not copy a macOS `.venv` to Linux.
The portable preflight intentionally excludes historical Sheets tests that need
the Mac's external scope evidence. Linux host binding uses `/etc/machine-id`,
because Python's MAC-address lookup can fall back to random values on minimal VMs.
`uv sync --frozen` uses the committed dependency lock. The plan captures the Python
version actually installed on this host. Tests are offline and consume no arms.

Prepare both prospective plans (no network calls):

```bash
bash scripts/run_study2_continuation_host.sh prepare github
bash scripts/run_study2_continuation_host.sh prepare razorpay
```

Read `$HOME/study2-data/github.plan.json` and `razorpay.plan.json`. Preparation's
`PASS` means local checks passed; live readiness has **not** yet passed. If prepare
writes a plan but check fails, fix the named credentials issue and run the CLI
`check --plan` command directly; do not call prepare again over the existing plan.

Start one tmux session per provider **once**, only after confirming the exclusive
writer and never-started conditions above:

```bash
tmux new-session -d -s study2-github "cd '$HOME/retry_semantics' && bash scripts/run_study2_continuation_host.sh run github > '$HOME/study2-data/github.log' 2>&1"
tmux new-session -d -s study2-razorpay "cd '$HOME/retry_semantics' && bash scripts/run_study2_continuation_host.sh run razorpay > '$HOME/study2-data/razorpay.log' 2>&1"
tail -n 12 "$HOME/study2-data/github.log"
tail -n 12 "$HOME/study2-data/razorpay.log"
```

After startup you can disconnect SSH, close your laptop, and reconnect later.
The VM must remain running. tmux survives SSH disconnection, **not a VM reboot**.
Do not configure process supervisors or scheduled jobs to restart the experiments.
Wait for `readiness PASS; beginning 256 serial arms` in each log. If a session ends
early, inspect its log/summary; do not launch it again.

## Option B: both on your Mac, or split Mac + VM

Your Mac must stay powered, awake and online. An uninterrupted hotspot can work,
but `caffeinate` cannot prevent network loss. On native Windows use WSL2/Linux;
the runtime relies on POSIX deadlines. Windows/WSL still needs sleep disabled and
continuous connectivity. These local commands are for your current Mac.

From the committed project, prepare only the provider(s) assigned to this host:

```bash
cd /Users/jashrashne/Desktop/retry_semantics
bash scripts/run_study2_continuation_host.sh prepare github
bash scripts/run_study2_continuation_host.sh prepare razorpay
```

Then use two Terminal tabs. First tab:

```bash
cd /Users/jashrashne/Desktop/retry_semantics
caffeinate -is bash scripts/run_study2_continuation_host.sh run github > "$HOME/study2-data/github.log" 2>&1
```

Second tab:

```bash
cd /Users/jashrashne/Desktop/retry_semantics
caffeinate -is bash scripts/run_study2_continuation_host.sh run razorpay > "$HOME/study2-data/razorpay.log" 2>&1
```

Keep both terminal processes open, the laptop lid open and power connected.
For a split deployment, execute **only** GitHub's prepare/run on the VM and
**only** Razorpay's prepare/run on the Mac (or the converse). Do not copy plans
between hosts or prepare/run the same provider on both.

## Monitor, verify and preserve

On either host, from its checkout:

```bash
tail -n 20 "$HOME/study2-data/github.log"
tail -n 20 "$HOME/study2-data/razorpay.log"
bash scripts/run_study2_continuation_host.sh verify github
bash scripts/run_study2_continuation_host.sh verify razorpay
```

Call verify after the corresponding run ends. During a 600-second/370-second
window, a quiet log is normal. Progress logs report each arm's start and finish.
Healthy completion is `state: COMPLETED`, `evaluated_arms: 256`, and verify exits
zero. Counts of `FAILURE` are expected experimental outcomes (for example duplicate
creation), not a reason to rerun. Counts of inconclusive/infrastructure outcomes
must be retained. Verification checks all scheduled projections and file hashes;
it does not establish the paper's scientific conclusions.

`STOPPED`, nonzero exit, missing summary/inventory, or verification failure means
preserve and inspect. Never delete a `.started.json`, create a new plan to restart,
copy the same namespace to another machine, or fill missing arms. Plan and global
claims are consumed **before readiness**, so a qualification failure also requires
review before any fresh attempt. Global claims live under
`$HOME/.local/state/retry-semantics-study2/`. Do not delete them.

Evidence is under `$HOME/study2-data/{github,razorpay}-run/`, including plan,
manifest, operator attestation, readiness captures and request journal, collection
operations/model traces/projections, final summary and inventory. Keep logs and
plans alongside the evidence. Do not modify these files during analysis.

After both runs end, archive and copy off the VM before terminating it. On the VM:

```bash
tar -czf "$HOME/study2-github-razorpay-evidence.tgz" -C "$HOME" study2-data .local/state/retry-semantics-study2
```

On the Mac, with `VM` set to the SSH destination:

```bash
scp "$VM:study2-github-razorpay-evidence.tgz" "$HOME/Downloads/"
```

Retain the original directory and verify the extracted copy before deleting the
VM. For split runs, preserve each host's evidence separately. Analysis will later
combine the two continuation datasets with the **separately labelled** Sheets
replication and disclose the failed primary and governance amendment.

## Operational references

GitHub recommends serial calls and pauses between mutations, and documents
primary/secondary rate limits: [REST API best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).
The experiment stops on rate/access errors; it does not retry mutations or add
new experimental attempts. Test-mode payment distinctions are documented by
[Razorpay](https://razorpay.com/docs/payments/dashboard/test-live-modes/).
Dependency setup follows [uv project synchronization](https://docs.astral.sh/uv/guides/projects/).

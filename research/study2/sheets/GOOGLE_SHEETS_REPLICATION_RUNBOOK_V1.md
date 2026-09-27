# Final Sheets replication: operator runbook

Use the new replication command below. The old `run_study2_sheets_primary.py`
intentionally refuses execution. The failed primary, its spreadsheet, and its
raw evidence must remain intact. No live Google/Fireworks collection has been
performed as part of this repair. Offline passing tests do not guarantee live
API availability; the run has explicit pre-data live checks.

Read the prospective protocol at
`research/protocol/STUDY2_SHEETS_REPLICATION_V1.md`. This is a separate,
operator-reviewed post-incident replication, not a replacement primary or an
independently audited run. The flags below accept that protocol and attest that
you will keep the new spreadsheets private and free of edits/scripts/automation.

## 1. Check and commit the repaired checkout

Run in Terminal, using the same terminal for the remaining steps:

```zsh
cd /Users/jashrashne/Desktop/retry_semantics
.venv/bin/python -m pytest -q
```

Do not proceed if tests fail. They use offline provider doubles and local
loopback sockets; they do not collect experiment data. The full run takes a few
minutes. Then review and commit the pending work so the live plan can bind it:

```zsh
git diff --check
git status --short
git diff --stat
```

This checkout already contained pending GitHub/Razorpay continuation changes
before this repair. The following commit includes those existing changes as
well as the Sheets repair; inspect them before committing. It does not launch
any provider collection. It never stages `.env` or external credentials.

```zsh
git add -- src scripts tests \
  research/protocol/STUDY2_POST_SHEETS_INCIDENT_CONTINUATION_V1.json \
  research/protocol/STUDY2_SHEETS_REPLICATION_V1.md \
  research/study2/sheets/GOOGLE_SHEETS_REPLICATION_RUNBOOK_V1.md
git commit -m "Prepare separately governed Sheets replication and collector repairs"
git status --short
```

The final command must print nothing. If other work remains, account for and
commit it rather than deleting it. Do not edit source after freezing the plan.

## 2. Select credentials and a new run location

The client path below was checked locally: the file exists and its Desktop
OAuth configuration validates. Use the same Google account used in the previous run. Its Google project needs both Sheets API and Drive API enabled.
The command uses the existing `drive.file` consent flow. Do not paste secrets
into chat or put the JSON inside this repository.

```zsh
SHEETS_CLIENT="/Users/jashrashne/Library/Application Support/RetrySemantics/oauth-client/google-desktop-client.json"
test -f "$SHEETS_CLIENT" && echo "OAuth client file found"
set -a
source .env
set +a
.venv/bin/python -c 'import os; assert os.environ.get("FIREWORKS_API_KEY"), "FIREWORKS_API_KEY missing"; print("Fireworks key is configured")'

REPLICATION_STAMP=$(date +%Y%m%d-%H%M%S)
REPLICATION_BASE="$HOME/Library/Application Support/RetrySemantics"
mkdir -p "$REPLICATION_BASE"
REPLICATION_PLAN="$REPLICATION_BASE/sheets-replication-plan-$REPLICATION_STAMP.json"
REPLICATION_RUN="$REPLICATION_BASE/sheets-replication-$REPLICATION_STAMP"
```

Do not use an old bearer file. OAuth acquisition and optional later consent
happen inside this run; bearer/refresh secrets are not persisted.
Close other scripts using the same Google project/account. Keep the computer
awake and remain available to open consent URLs in your browser. Do not edit,
share, or attach scripts to either new spreadsheet while collection runs.

## 3. Freeze and check the plan, without network access

```zsh
.venv/bin/python scripts/run_study2_sheets_replication.py prepare \
  --plan "$REPLICATION_PLAN"
.venv/bin/python scripts/run_study2_sheets_replication.py check \
  --plan "$REPLICATION_PLAN"
.venv/bin/python -m json.tool "$REPLICATION_PLAN"
```

Expect `PASS: committed code and replication plan match. No network requests
made.` Review the plan: 64 families, 256 arms, replication label, exact commit,
source hashes, dependency versions, 1.1-second request pacing. It must not claim
an independent audit. A source change before execution requires a new plan;
a consumed plan must never be replaced to retry a partially executed sample.

## 4. Execute once

This command creates two fresh spreadsheets, calls Fireworks, and writes the
experiment's data. It never uses or clears the failed primary's spreadsheet.

```zsh
caffeinate -i .venv/bin/python -u scripts/run_study2_sheets_replication.py run \
  --plan "$REPLICATION_PLAN" \
  --run-dir "$REPLICATION_RUN" \
  --client "$SHEETS_CLIENT" \
  --execute-replication \
  --confirm-no-external-writers
```

Open each printed OAuth URL promptly and consent with the same Google account.
The callback returns to the local process; do not copy tokens into Terminal.
The process may ask for consent again between families when token lifetime is
low. It never reacquires credentials in the middle of a family's recovery.

The command automatically performs, in order:

1. OAuth acquisition and a fresh four-tab qualification spreadsheet, with sole-owner checks.
2. One real Fireworks original-generation capability check and four scripted
   collector controls. Qualification expects H1 exact replay to produce a
   duplicate; that is a passing control. Qualification data are excluded.
3. A fresh 256-tab experiment spreadsheet, exact topology validation, and all
   256 blank baselines. Progress prints every 32 baseline reads.
4. One original per family and four arms in the inherited frozen order, with
   each arm's result printed immediately. At least 1.1 seconds separate Sheets
   request starts; no HTTP retry is added.
5. A final summary and an evidence-file hash inventory.

A `FAILURE DUPLICATE` arm is an experimental outcome, not a broken run.
`INCONCLUSIVE` remains explicitly unevaluable. The final process summary must
say `COMPLETED` and `projected_arms: 256`; this describes schedule completion,
not 256 successful effects. Budget plenty of time and keep the terminal open;
live model latency and additional consent can extend the run.

## 5. Verify the collected package

```zsh
.venv/bin/python scripts/run_study2_sheets_replication.py verify \
  --run-dir "$REPLICATION_RUN"
printf 'Saved experiment: %s\n' "$REPLICATION_RUN"
```

Verification must exit successfully and print `COMPLETED`, 256 projected arms,
and the outcome counts. Save the full run directory and the plan plus its
`.started` file. Preserve these together when backing up:

- `manifest.json`: new bound experiment scope and inherited scientific design.
- `plan.json`: prospective code/protocol/runtime identity.
- `collection/`: 256 arm evidence directories and run authorization.
- `qualification/` and `setup/`: separate engineering and readiness evidence.
- `run-summary.json` and `inventory.json`: completion and integrity checks.

Send the experiment directory path back for analysis. Later analysis must load
this directory's `manifest.json` and `collection/`, not the old primary manifest
and not qualification records. GitHub/Razorpay and joint analysis follow after
Sheets, as planned. In the paper, disclose the failed primary separately and
label this new dataset as a post-incident replication.

## If anything stops

Do not repeat the `run` command, clear any tabs, delete `.started`, or create a
new plan just to replace failed observations. A consumed plan or existing run
refuses reuse. Preserve the entire directory, the last progress line, and
`run-summary.json` if present. A killed process can lack a summary; that is also
an incomplete run. Bring the directory back for diagnosis before any further
collection. Model/API outages and qualification failures are not permission to
replay an uncertain mutation.

A refusal during `prepare` or `check` happens before network access. Resolve
the reported clean-tree, dependency, or plan mismatch first. No independent
audit receipts or old readiness locks need to be fabricated or refreshed for
this separately governed replication.

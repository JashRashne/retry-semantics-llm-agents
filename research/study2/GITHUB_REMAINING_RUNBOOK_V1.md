# GitHub remaining-arm collection

The user explicitly authorized fixing pagination and running the remaining arms.
See `research/protocol/STUDY2_GITHUB_REMAINING_CONTINUATION_V1.md` for the prospective
exception to the old no-resume policy and the required separate reporting.

The source `/root/study2-data/github-run` stays sealed, including its 45 pre-policy
inconclusives and 134 skipped arms. Only those 179 policy-unentered arms are eligible
here. None had mutation intent. Preserve all 77 entered outcomes, including the
one inconclusive observation, and reuse the saved original messages for families
20–64. The new segment is not a rewritten or completed original primary.

Separate VM checkout: `/root/retry_semantics_github_remaining`.
Separate plan/evidence/log root: `/root/study2-github-remaining`.
Tmux session: `study2-github-remaining`.

The preparation workflow verifies the source's full SHA-256 inventory, offline
tests and a real read-only paginated census, then prepares the plan on this VM.
At launch all seven live readiness controls run again using only the remaining
179 suffix reservations for collision checks. Existing completed issues stay.
Never delete or close issues to repair pagination. No receipt is labelled as a new
independent audit. Keep the repository exclusive to this experiment.

## Monitoring the already authorized launch

```bash
tail -n 20 /root/study2-github-remaining/github.log
tmux has-session -t study2-github-remaining
```

Expect `readiness PASS; beginning 179 remaining arms`, starting with
`gh-f020:H0:LLM_REGENERATION`. The original arm numbers are preserved in IDs;
the new progress counter starts at 1/179. Several minutes without a new progress
line is normal. Budget roughly 24–36 hours under ordinary latency, potentially
longer: the usual scenario contains 135 ten-minute waits (22.5 hours), plus API,
model, constructor and readiness time. This estimate is not a cutoff.

The remote tmux process continues when SSH disconnects or the laptop shuts down.
Keep the VM powered on and the new checkout fixed throughout collection.
There is no automatic restart. If it stops, preserve all files and inspect the
cause; never clear either the original claim or the new remaining-segment claim.

After `COMPLETED_SEGMENT`, verify:

```bash
cd /root/retry_semantics_github_remaining
bash scripts/run_study2_github_remaining_host.sh verify
```

This checks all 179 selected projections, source integrity, authorization and
saved original bindings. It does not treat primary plus continuation as one
uninterrupted experiment. Later analysis must retain code/epoch labels and the
split-family limitation for family 20.

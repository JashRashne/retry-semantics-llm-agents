# Deterministic no-model baseline — audited results

This file records the final post-review descriptive results for the deterministic
no-model recovery baseline.

## Audit authority

Final hostile-audit archive retained outside the repository:

`no_model_baseline_FINAL_results_audit_20261006.zip`

SHA-256:

`2e4ed062c5701f7e7c60e41658919abefc663afe0a8dd5197a0950ca0147959d`

Audit status: **PASS**

The audit verified:

- 896 / 896 frozen opportunities present exactly once
- global schedule indices 0..895 covered exactly once
- 0 schedule mismatches
- 0 collection anomalies
- 0 evaluator anomalies
- 0 UNKNOWN / indeterminate no-model outcomes
- 0 model calls
- all 896 frozen evaluator checks agreed

Readiness lock SHA-256:

`2e73e736aaa8fd01ace0a4e7c86f55aac33be41ea022ad8ad67eb692b535c59a`

Deployment lock SHA-256:

`2f076176833bacaf17e1c5ae1d40829a6fd4a182c15a6cc2a2bce68a25747da8`

GitHub transferred collection archive SHA-256:

`876ddde3248eceb293edf773c6fea0b51e84ce12c354d9c21f69a47ac57ee89f`

## Deterministic policy

The baseline makes no LLM calls and performs one state observation:

1. LIST once.
2. If the observation is unusable, STOP.
3. If the exact intended effect is already visible, STOP.
4. Otherwise dispatch the stored original CREATE exactly once.
5. STOP.

There is no retry loop, no second decision read, no model regeneration, no
hidden H0/H1 oracle, and no idempotency key.

## No-model results

| Study | World | Scheduled | Evaluable | Success | Failure | UNKNOWN | Effect already visible | Stored CREATE dispatched |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Study 1A | H0 | 160 | 160 | 160 | 0 | 0 | 0 | 160 |
| Study 1A | H1 | 160 | 160 | 160 | 0 | 0 | 160 | 0 |
| Study 1B | H0 | 160 | 160 | 160 | 0 | 0 | 0 | 160 |
| Study 1B | H1 | 160 | 160 | 160 | 0 | 0 | 160 | 0 |
| GitHub | H0 | 64 | 64 | 64 | 0 | 0 | 0 | 64 |
| GitHub | H1 | 64 | 64 | 64 | 0 | 0 | 64 | 0 |
| Sheets valid replication | H0 | 64 | 64 | 64 | 0 | 0 | 0 | 64 |
| Sheets valid replication | H1 | 64 | 64 | 64 | 0 | 0 | 64 | 0 |

Across all 896 opportunities:

- H0: 448 / 448 successful; stored CREATE dispatched in all 448.
- H1: 448 / 448 successful; intended effect observed and recovery CREATE suppressed in all 448.
- Unusable decision observations: 0.
- Model calls: 0.

## Descriptive comparison with the original policies

| Environment / Study | World | Replay | Regenerate | No-model baseline |
| --- | --- | ---: | ---: | ---: |
| Study 1A | H0 | 160/160 | 160/160 | 160/160 |
| Study 1A | H1 | 0/160 | 151/160 | 160/160 |
| Study 1B | H0 | 160/160 | 160/160 | 160/160 |
| Study 1B | H1 | 0/160 | 160/160 | 160/160 |
| GitHub | H0 | 63/63 | 60/63 | 64/64 |
| GitHub | H1 | 0/64 | 64/64 | 64/64 |
| Sheets valid replication | H0 | 64/64 | 64/64 | 64/64 |
| Sheets valid replication | H1 | 0/64 | 64/64 | 64/64 |

For GitHub H0, the original matched Replay/Regenerate cohort contains 63
identities because one Replay outcome was UNKNOWN. Regenerate is 60/64 on its
all-evaluable cohort and 60/63 on the historical matched subset. The no-model
baseline has its own complete 64/64 post-review cohort. These denominators must
not be presented as a new paired 64-way comparison.

## Scientific interpretation

The tested recovery decisions do not show that an LLM is necessary. In these
tested strata, the fixed state-aware rule matched or exceeded the observed
Regenerate results without making any model calls.

The baseline was added after reviewer feedback and is therefore reported as a
descriptive comparison rather than incorporated into the original
preregistered inferential analysis. No new significance test or confidence
interval is attached to this baseline.

All 896 baseline decision observations were usable. Performance when the
relevant state cannot be observed reliably remains outside the evidence
provided by this collection.

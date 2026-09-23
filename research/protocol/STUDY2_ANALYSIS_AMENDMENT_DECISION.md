# Study-2 provider-specific analysis-amendment decision

**FROZEN PRE-DATA ANALYSIS DECISION — INDEPENDENT HOSTILE AUDIT PASSED**

**STUDY-2 PAPER OBSERVATIONS = 0**

**COLLECTION BLOCKED**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## Decision and authority

Question: Does the finalized Study-2 external-provider design require a
provider-specific amendment to the frozen V1.3 primary analysis plan?

**NO PROVIDER-SPECIFIC ANALYSIS AMENDMENT REQUIRED.** This records the
methodological conclusion already fixed in Section 8 of the frozen
cross-provider protocol; it creates no amendment, inferential rule, paper
readiness approval, or collection authority. Independent hostile audit passed
for the exact 99-line pre-freeze revision identified below.

Canonical repository checkpoint at decision time:
`cb295d3fe26b15fed5045191888ceb09b7a638db`.

Audited pre-freeze revision: 99 lines; SHA-256
`4054f1a1c3474424ce9d862378ce1d0ae1c0477c80030eb2893ce477ec8d7ea2`.
This freeze update changes audit status and provenance wording only.

| Controlling frozen artifact | SHA-256 verified from disk |
| --- | --- |
| `research/protocol/primary_create_v1_3_analysis_plan.md` | `23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88` |
| `research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` | `21ff3b3ca90d27a46669e12bab62de89d7ddd191ba96dfa5a8e12c0a69521ecb` |
| `research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md` | `d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2` |
| `research/study2/github/GITHUB_PAPER_SEMANTICS_CONTRACT.md` | `61d5a44eff8f22fc550a2fcf168c6056cff35ce50797e266c9f41896fa673b4a` |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md` | `b88d13c059d1716b1528386d2446a53e770e7c078e223e46aefa8f9daba98a2e` |
| `research/study2/razorpay/RAZORPAY_PAPER_SEMANTICS_CONTRACT.md` | `e8cc1963e6b2a5e17c933e31a282054cf7f2c6473722693c9427702d8b591d8e` |

## V1.3 analysis-rule check

The V1.3 plan (Sections 1–9 and 15) controls the analysis; the external-provider
amendment preserves its treatments, outcomes, eligibility, tests, multiplicity,
and allocations. The cross-provider protocol (Sections 3, 6, and 8) binds the
provider contracts to that plan. Statuses below classify each finalized rule;
they do not revise the rule.

| Dimension checked | Status | Basis |
| --- | --- | --- |
| Primary estimand | **UNCHANGED UNDER V1.3** | Within-world Replay minus Regeneration contrasts and the family interaction retain their definitions; external providers remain descriptive/generalization replications. |
| Replay versus Regeneration treatment definition | **UNCHANGED UNDER V1.3** | Exact stored-request Replay and bounded model continuation retain the frozen policy meanings. |
| H0/H1 construction | **UNCHANGED UNDER V1.3** | H0 original non-dispatch and H1 exactly one certified intended original effect retain their meanings; provider certification is an implementation detail. |
| Four-arm family structure | **UNCHANGED UNDER V1.3** | H0/H1 × Replay/Regeneration remain four linked arms of one family. |
| One family-wide `M` | **UNCHANGED UNDER V1.3** | One original generated call is frozen across all four arms; arm-local provider requests only realize it. |
| Primary `STATE_CORRECT` endpoint | **UNCHANGED UNDER V1.3** | The state-only exact-one-intended, zero-unintended criterion retains its analysis meaning. |
| Pair/four-arm evaluability | **UNCHANGED UNDER V1.3** | Both arms are required for a within-world pair; all four for the interaction. |
| Missing/inconclusive-arm handling | **UNCHANGED UNDER V1.3** | Unresolved authoritative state leaves the arm non-evaluable; no invented binary outcome or replacement pair is introduced. |
| Provider/infrastructure versus model failures | **UNCHANGED UNDER V1.3** | Infrastructure is reported separately; only V1.3's prespecified arm-attributable sensitivity scoring applies. Behavioral malformed/rejected output remains behavioral when state is known. |
| Exclusion rules | **UNCHANGED UNDER V1.3** | Invalid construction, attribution, or evidence follows frozen pair/family validity and evaluability rules; no new outcome-based exclusion is added. |
| Family-level inclusion | **UNCHANGED UNDER V1.3** | Eligible families supply matched pairs only when their arms are evaluable; complete four-arm families supply interaction estimates. |
| Statistical comparison | **UNCHANGED UNDER V1.3** | Paired summaries, exact conditional McNemar comparisons, and the whole-family interaction bootstrap retain their frozen roles. |
| Multiplicity/error control | **UNCHANGED UNDER V1.3** | The ticket primary model's two-test Holm family remains intact; external replications add no co-primary test. |
| Interpretation of non-evaluable families | **UNCHANGED UNDER V1.3** | Report losses and reasons; do not turn missing state or pre-arm failure into policy failure or refill denominators. |
| Provider observation and physical-state realization | **PROVIDER IMPLEMENTATION DETAIL ONLY** | GitHub issue counts/contents, Sheets bounded-row state, and Razorpay Order state/causal-ledger evidence are projected to the existing logical endpoint, not separate primary outcomes. |

## OBS-1 and evidence check

Frozen OBS-1 (cross-provider protocol, Section 6) starts GitHub rounds at
post-recovery `+0` and `+600`, completes them by `+540` and `+1140`; starts
the single Sheets round at `+0` and completes it by `+40`; and starts Razorpay
rounds at `+0` and `+200` on a scheduled path through `+470`, with pre-recovery
`D = 1020`. The common administrative maximum is `H = 1140`; Sheets' own
terminal deadline is `+40`. These are prospectively fixed measurement routes,
not a claim of equivalent provider visibility latency. Comparisons remain
within provider. No outcome-adaptive rescue, extra round, or shifted deadline
is allowed. State unresolved at the applicable frozen deadline stays
`INCONCLUSIVE`/non-evaluable under V1.3; exhausting `H` is not model failure.

Provider-specific physical states differ, but the frozen projected-state rule
maps them to the existing logical `STATE_CORRECT` endpoint without redefining
it. Malformed/incomplete observations, provider contradictions,
infrastructure or rate-limit failures, scope contamination, failed H1
construction, and unavailable authoritative evidence remain readiness,
infrastructure, validity, or evaluability matters. They are not new behavioral
outcome categories and are not scored as model failures except where an
existing V1.3 rule explicitly applies.

## Prospective trigger and remaining gates

An amendment is required **before Study-2 paper observation #1** only if later
implementation or readiness work reveals a need to change an actual V1.3
inferential rule: for example, `STATE_CORRECT`, treatment definitions,
pair/family evaluability or inclusion, inconclusive-arm handling, a
provider-specific primary endpoint, or statistical comparison. Such a conflict
keeps collection blocked until a prospective amendment is written, independently
audited, and frozen. Observed outcomes cannot motivate a post-outcome amendment.

This record closes the formal analysis-amendment-decision gate, not collection
readiness. Next are the provider-specific 64-family catalogues, followed by
manifests, paper adapters/evaluators and offline adversarial validation, exact
non-production scopes and provider readiness qualification, final cross-artifact
hostile audit/readiness freeze, and separate explicit collection authorization.
**STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION BLOCKED.**

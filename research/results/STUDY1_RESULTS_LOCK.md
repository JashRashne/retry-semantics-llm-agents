# Study 1 Results Lock

**Project:** Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes
**Study:** Study 1 — Controlled Ticket CREATE Experiment
**Status:** CLOSED / CANONICAL
**Lock date:** 2026-09-17
**Document role:** Post-data provenance and results lock. This document is **not** a prospective protocol and must not be presented as one.

---

## 1. Purpose of this lock

This file records the canonical Study 1 collection and analysis artifacts after the frozen experiment and deterministic analysis completed successfully.

After this lock:

- Study 1 collection is closed.
- Study 1 analysis is closed.
- The canonical raw and derived artifacts listed below must not be overwritten or silently regenerated.
- Any future rerun must be described as a **new replication or follow-up study** with a new identifier.
- GitHub / Google Sheets / Stripe experiments are **Study 2 external validation** and are not part of Study 1.

---

## 2. Frozen prospective design identity

### Execution semantics

- Revision: `primary-create-v1.2`

### Paper experiment / analysis

- Revision: `primary-create-v1.3`

### Collection evidence

- Revision: `paper-collection-evidence-v2`

### Pre-data repository state

- Git commit: `add9a783df2fede9b05026f8e13c6c623fe5a3c5`
- At preflight: `HEAD == origin/main`
- Worktree: clean

### Primary model

- Provider: Fireworks
- Model: `accounts/fireworks/models/deepseek-v4-flash-0731`
- `reasoning_effort="none"`
- `temperature=0.0`
- `top_p=1.0`
- `max_completion_tokens=1024`
- `parallel_tool_calls=False`

### Frozen paper manifest

- Manifest ID: `primary-create-v1.3-fireworks-deepseek-v4-flash-0731-paper-001`
- Scheduled families: `160`
- Canonical bytes: `240807`
- SHA256: `a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c`

### Schedule

- 20 replicates × 8 Ticket CREATE scenarios = 160 scheduled families
- Odd replicates: `CREATE001 → CREATE008`
- Even replicates: `CREATE008 → CREATE001`
- Strata: A=40, B=40, C=40, D=40
- Each scenario: 5 A / 5 B / 5 C / 5 D

### Seeds

- Original generation: `30000 + slot_index`
- Regeneration base: `40000 + 10*slot_index`

### Frozen stopping rule

Exactly 160 scheduled families.

No:

- early stopping
- extension to reach an eligible target
- replacement of failed/ineligible trials
- resampling
- scenario additions
- model shopping
- prompt tuning

---

## 3. Canonical paper collection

### Run identity

- Run timestamp: `2026-09-17T05:55:03Z`
- Git commit recorded in run: `add9a783df2fede9b05026f8e13c6c623fe5a3c5`
- Collection evidence revision: `paper-collection-evidence-v2`
- Scheduled slots completed: `160`
- Runner exit status: `0`
- Completed raw bundle validation: passed
- Collection rerun: **prohibited**

### Raw six-file SHA256

| File | SHA256 |
|---|---|
| `manifest.json` | `a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c` |
| `run_metadata.json` | `4b6ab68ed0869d4ab6663f09a44a2d3f8e915172d35952728b1011ec01ea7382` |
| `scheduled_attempts.jsonl` | `1db7c649fb69161c08bebdad0b9661dc0f04edf4b4382fcf49431727a4f38c35` |
| `arm_traces.jsonl` | `49108eb84548d570a9a4472efb34154efbaf9f64ccda1570afea12e55241959d` |
| `collection_events.jsonl` | `53b1f7fb3f69b6f1896704ec9a3abb28ab76bcd5af92a8bad8174d1263f0e6aa` |
| `paper_collection_summary.json` | `cec7aea81c2e852fd3c9058696dba1ae115fb1b7d33ad2fb15122caba2377606` |

### Preserved raw archive

- Raw ZIP SHA256: `008e1d7e0d32e1de41bb4f843f02900bd970dae0e769a0ae0987dccaa9b1541f`
- Raw audit package SHA256: `2bf8dbd15de06481903e756548716c277829fe9c11d17c6fd73639d86b130656`
- Terminal log SHA256: `b823941386a5f17ab7215d1e4fcd5897861ea1cb3bb514378b727aba76f8a8a4`

### Raw-evidence audit status

**PASS**

The hostile raw-evidence audit found:

- exactly 160 scheduled attempts
- slot indices 0–159 exactly once each
- 20 replicates with all 8 scenarios each
- exact schedule/counterbalancing
- exact seed schedule
- 160/160 eligible originals
- 160/160 activated families
- 640/640 attempted arms
- 640/640 persisted arm traces
- zero original-generation infrastructure failures
- zero family infrastructure failures
- zero arm infrastructure failures
- 1,280 collection events with contiguous sequence numbers
- no evidence of replacement, resampling, hidden retry, or dropped scheduled families
- completed collection status coherent with the frozen manifest

---

## 4. Frozen deterministic analysis

### Analysis plan

- Identity: `primary-create-v1.3-analysis-plan-v1.0`
- Path: `research/protocol/primary_create_v1_3_analysis_plan.md`
- SHA256: `23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88`

### Extractor

- Version: `ticket-analysis-extractor-v1`
- Analysis version: `ticket-primary-create-analysis-v1`
- Extractor implementation SHA256: `b0e2915ffa00c30795d4b3d28cd755baba5c48714607ff8b0211b6a69f8749c1`
- Bootstrap seed: `20260916`
- Bootstrap replicates: `10000`

### Analysis artifact SHA256

| File | SHA256 |
|---|---|
| `analysis_arms.jsonl` | `fb0ae767e2029fef4a5122863ba3878f7f9477f7dc3a3ff388f231d92c518db3` |
| `analysis_families.jsonl` | `04f008f5561f420220f06f6a008ed7ecc51059763e1dffbb9c043c6d563eeb35` |
| `analysis_provenance.json` | `4eb3b37018c6cfba4d2f731f5a6b68cc5117d03fcea558bcd7730f7979a91532` |
| `analysis_results.json` | `5488973bb6e7a21902d056e707df673c3d54bb54d6fb7c7576cbe61ae475b3a7` |

### Preserved analysis archive

- Analysis ZIP SHA256: `b5831c45154487bef93af31e05e0d4baeba8d9ff0d0d19d84b673ea3d38efcef`

### Analysis audit status

**PASS**

The derived analysis contains exactly:

- 160 families
- 640 arms
- four arms per family:
  - H0 × Exact Replay
  - H0 × LLM Regeneration
  - H1 × Exact Replay
  - H1 × LLM Regeneration
- no missing or duplicated family slots
- family-level pair records consistent with arm-level `STATE_CORRECT`
- primary and sensitivity results identical
- `materially_weakened = false`
- no operational-fragility sign reversals, Holm-decision changes, or zero-crossing transitions

---

## 5. Prespecified primary estimand

For each hidden world:

`Δ = Exact Replay STATE_CORRECT rate − LLM Regeneration STATE_CORRECT rate`

The two worlds are analyzed separately:

- **H0 / NOT_EXECUTED:** original mutation did not execute
- **H1 / EXECUTED_ACK_LOST:** original mutation executed, but acknowledgement was lost

The prespecified interaction is:

`Δ_H1 − Δ_H0`

Primary inference uses:

- exact paired McNemar
- paired Newcombe (1998) Method 10, two-sided 95% CI
- Holm correction across exactly H0 and H1
- 10,000 whole-family bootstrap replicates for the interaction using `random.Random(20260916)`

---

## 6. Canonical primary results

### H0 — original mutation NOT_EXECUTED

| Quantity | Result |
|---|---:|
| N matched families | 160 |
| Exact Replay STATE_CORRECT | 160/160 = 1.000 |
| LLM Regeneration STATE_CORRECT | 160/160 = 1.000 |
| Δ = Replay − Regeneration | 0.000 = 0.0 percentage points |
| McNemar discordant counts | n10=0, n01=0 |
| Exact McNemar raw p | 1.0 |
| Holm-adjusted p | 1.0 |
| Paired Newcombe Method 10 95% CI | [-0.0234462, +0.0234462] |
| CI in percentage points | [-2.3446, +2.3446] |

Interpretation: under H0, both retry semantics were state-correct in all 160 matched families.

### H1 — original mutation EXECUTED_ACK_LOST

| Quantity | Result |
|---|---:|
| N matched families | 160 |
| Exact Replay STATE_CORRECT | 0/160 = 0.000 |
| LLM Regeneration STATE_CORRECT | 151/160 = 0.94375 |
| Δ = Replay − Regeneration | -0.94375 = -94.375 percentage points |
| McNemar discordant counts | n10=0, n01=151 |
| Both incorrect | n00=9 |
| Both correct | n11=0 |
| Exact McNemar raw p | `7.006492321624085e-46` |
| Holm-adjusted p | `1.401298464324817e-45` |
| Paired Newcombe Method 10 95% CI | [-0.9701277, -0.8910598] |
| CI in percentage points | [-97.0128, -89.1060] |

Interpretation: under H1, exact replay duplicated the already-committed mutation in all 160 families, while regeneration reached the correct terminal state in 151/160 families.

### Prespecified interaction

| Quantity | Result |
|---|---:|
| N families | 160 |
| `(Δ_H1 − Δ_H0)` | -0.94375 |
| Interaction in percentage points | -94.375 |
| Whole-family bootstrap replicates | 10,000 |
| Bootstrap seed | 20260916 |
| Percentile 95% CI | [-0.975, -0.90625] |
| CI in percentage points | [-97.5, -90.625] |

---

## 7. Canonical behavioral / operational observations

These are useful for interpretation but must be distinguished from the prespecified primary estimands.

### Failure modes

- H0 Exact Replay duplicate mutation: 0/160
- H0 Regeneration duplicate mutation: 0/160
- H1 Exact Replay duplicate mutation: 160/160
- H1 Regeneration duplicate mutation: 9/160
- Missing mutation: 0 across all evaluable arms
- Wrong mutation: 0 across all evaluable arms
- Regeneration malformed generation: 0
- Regeneration rejected generation: 0
- Regeneration budget exhaustion: 0

### H1 regeneration: observation-before-write association

Within the 160 H1 regeneration arms:

- 151 were `STATE_CORRECT=1` and `OBSERVATION_BEFORE_WRITE=1`
- 9 were `STATE_CORRECT=0` and `OBSERVATION_BEFORE_WRITE=0`
- there were no other combinations

Thus the observed correspondence was exact in Study 1:

- all 151 correct H1 regeneration recoveries observed state before write
- all 9 incorrect H1 regeneration recoveries wrote before observation

**This is an observed mechanism association, not a prespecified causal estimand. It must not be presented as proof that observation-before-write causally guarantees correctness.**

For comparison, H0 regeneration was state-correct in all 160 arms; 146/160 observed before write and 14/160 did not.

### Recovery overhead

Descriptive averages:

| World | Policy | Mean model calls issued | Mean recovery tool calls executed |
|---|---|---:|---:|
| H0 | Exact Replay | 0 | 1 |
| H0 | LLM Regeneration | 3.70 | 2.70 |
| H1 | Exact Replay | 0 | 1 |
| H1 | LLM Regeneration | 2.03125 | 1.03125 |

The regeneration action budget is a bound on recovery tool actions, not on total model invocations. A terminal model stop may occur after the final executed recovery action.

---

## 8. Descriptive equal-world summary

The deterministic extractor reports the following **descriptive** equal-world summary:

- Exact Replay: `0.5`
- LLM Regeneration: `0.971875`

This is explicitly labeled:

`DESCRIPTIVE EQUAL-WORLD EXPERIMENTAL SUMMARY`

It is **not** weighted by real-world H0/H1 prevalence and must not be presented as a real-world expected success rate.

---

## 9. Locked interpretation boundaries

Study 1 supports claims about the frozen experimental setting:

- one Fireworks-hosted DeepSeek model
- eight controlled Ticket CREATE scenarios
- 20 replicates per scenario
- matched H0/H1 hidden worlds
- non-idempotent state-mutating CREATE semantics
- exact request replay vs bounded LLM regeneration
- the frozen regeneration context, prompts, tools, and execution semantics

Study 1 does **not** by itself establish:

- that LLM regeneration is universally superior to replay
- performance for arbitrary APIs, models, prompts, or mutation types
- performance under unknown real-world H0/H1 prevalence
- that observation-before-write is causally sufficient for correctness
- that exact replay is unsafe when the underlying API provides a strong server-side idempotency mechanism
- general results for GitHub, Google Sheets, Stripe, or other external systems

A central systems boundary is therefore:

> Retry semantics must be interpreted together with the mutation API's idempotency and reconciliation guarantees.

---

## 10. Canonical Study 1 result statement

A defensible concise statement is:

> In 160 matched controlled Ticket CREATE families, retry semantics interacted sharply with the hidden outcome of an ambiguous state-mutating call. When the original mutation had not executed (H0), Exact Replay and LLM Regeneration were both state-correct in 160/160 families. When the original mutation had executed but its acknowledgement was lost (H1), Exact Replay was state-correct in 0/160 families, while LLM Regeneration was state-correct in 151/160 (94.375%). The prespecified H1 Replay-minus-Regeneration difference was -94.375 percentage points (paired Newcombe Method 10 95% CI: -97.013 to -89.106 percentage points; exact McNemar p=7.006e-46; Holm-adjusted p=1.401e-45). The prespecified H1-minus-H0 interaction was -94.375 percentage points (10,000-family bootstrap 95% CI: -97.5 to -90.625 percentage points).

An additional exploratory observation is:

> In H1 regeneration, all 151 state-correct recoveries observed state before issuing a write, whereas all nine state-incorrect recoveries wrote before observation and duplicated the existing mutation.

The second statement must be labeled exploratory / mechanism-descriptive rather than causal.

---

## 11. Study boundary and next phase

**Study 1 is closed.**

The next planned work is a separately frozen **Study 2 external validation** using real systems such as:

- GitHub
- Google Sheets
- Stripe test mode

Study 2 is designed after Study 1 results were observed and must therefore:

1. use a new study/protocol identifier;
2. freeze its hypotheses, endpoints, mutation semantics, stopping rule, model configuration, and analysis before Study 2 data collection;
3. keep Study 1 data and analysis unchanged;
4. report Study 2 as external validation / follow-up rather than retrospectively folding it into the original prospective Study 1.

---

## 12. Immutability rule

The canonical Study 1 collection and analysis artifacts must not be rerun or replaced because a later result is inconvenient or surprising.

If a future technical correction is genuinely necessary:

- preserve the original artifacts;
- document the issue;
- create a new explicitly versioned analysis or replication;
- never silently overwrite this lock.

**Study 1 canonical status: LOCKED.**

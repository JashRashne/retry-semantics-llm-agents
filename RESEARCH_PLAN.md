# RESEARCH PLAN

## Working Title

**Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes**

## Project Status

**Authoritative current plan.**

This file supersedes the original retry-semantics planning document. The earlier plan should be preserved under `research/archive/` as historical context, but this document is the source of truth for the current paper.

---

# 1. Paper Objective

This paper studies one narrow execution-semantics question:

> **After an ambiguous outcome from a state-mutating LLM tool call, does deterministic replay of the exact already-generated request behave differently from returning the ambiguity to the LLM and allowing it to reason again and choose the next action?**

The paper does **not** attempt to solve general LLM-agent reliability, transactions, durable execution, exactly-once semantics, orchestration, checkpointing, or multi-agent fault tolerance.

The intended contribution is a **controlled empirical study** of one retry-boundary decision:

1. **Exact Request Replay**
2. **LLM Regeneration**

under identical ambiguous outcomes.

The paper will also test whether results generalize across:

- multiple state-mutating operation classes,
- multiple models,
- multiple fault conditions,
- and selected real APIs.

---

# 2. Motivation

Distributed systems already establish that retrying non-idempotent operations after ambiguous communication failures can be unsafe.

LLM agents add an additional complication:

> A retry may not mean “execute the same request again.”

Instead, the runtime may return control to the model, allowing the LLM to reason again and generate:

- the same action,
- a modified action,
- a different tool call,
- a verification action,
- a compensating action,
- or no action at all.

This creates a meaningful distinction between:

```text
REPLAY
execute the already-generated request again
```

and:

```text
REGENERATE
return ambiguity to the model and let it decide what to do next
```

The paper isolates this distinction experimentally.

---

# 3. Research Positioning

## 3.1 What is already known

The paper must explicitly acknowledge that the following are **not novel**:

- ambiguous outcomes after state-mutating requests,
- non-idempotent retry hazards,
- duplicate external effects,
- verify-before-retry,
- idempotency keys,
- transactional wrappers,
- compensation,
- stateful agent evaluation,
- general LLM recovery after tool failure.

Relevant prior work includes classical distributed-systems semantics and recent LLM-agent reliability work such as:

- RFC 9110 HTTP idempotence/retry semantics,
- Sagas,
- ReAct,
- τ-bench,
- Verified Tool Calls,
- Atomix,
- Agent Mesh,
- ACRFence,
- and recent work on ambiguous agent-tool outcomes.

## 3.2 Narrow contribution

The paper will only claim a new empirical contribution if the literature audit continues to support the following distinction:

> **A controlled, paired comparison of exact replay of one frozen state-mutating request versus model-driven regeneration after the same ambiguous outcome.**

The study should be positioned as:

> **an empirical systems/LLM-agent paper with a strong related-work synthesis**

not primarily as a literature-review paper.

---

# 4. Core Research Questions

## RQ1 — Retry semantics

> **Does exact request replay differ from LLM regeneration in final-state correctness after ambiguous state-mutating tool outcomes?**

## RQ2 — Hidden execution state

> **How does the relative behavior of replay and regeneration change depending on whether the original mutation did not execute or executed successfully but its acknowledgement was lost?**

## RQ3 — Mutation semantics

> **Does the effect of replay versus regeneration depend on the semantic class of the underlying state mutation?**

Candidate mutation classes:

- CREATE
- APPEND
- INCREMENT
- SET / UPDATE
- DELETE
- RESERVATION / state-dependent mutation

## RQ4 — Regeneration drift

> **How often and in what ways does LLM regeneration differ from the original generated request?**

Possible drift categories include:

- exact match,
- changed arguments,
- changed identifier/idempotency key,
- different tool,
- verification/read action,
- abandonment,
- other recovery behavior.

## RQ5 — External validity

> **Do the controlled findings reproduce against real state-mutating APIs?**

---

# 5. Primary Hypotheses

These hypotheses must remain falsifiable and should not assume that either policy wins.

## H1

**Exact Replay and LLM Regeneration differ in final-state correctness under ambiguous state-mutating outcomes.**

## H2

**The effect of retry semantic interacts with the hidden execution state of the original request.**

In other words, the relative behavior of Replay and Regenerate may differ between:

- mutation not executed, and
- mutation committed but acknowledgement lost.

## H3

**LLM Regeneration introduces measurable request/action drift that Exact Replay structurally cannot introduce.**

## H4 — Secondary

**The relative behavior of Replay and Regenerate depends on the semantic class of the mutation.**

---

# 6. Fundamental Experimental Principle

The central experiment must be **paired**.

For every base trial:

```text
User task
   ↓
LLM generates ORIGINAL tool request M
   ↓
M is serialized and frozen exactly once
   ↓
Choose hidden execution state
   ↓
Inject ambiguous outcome
   ↓
Clone the same experiment state
   ↓
┌──────────────────────┬──────────────────────┐
│ EXACT REQUEST REPLAY │ LLM REGENERATION     │
└──────────────────────┴──────────────────────┘
   ↓
Compare final states and recovery behavior
```

The original request must **never** be independently regenerated for the Replay and Regenerate arms.

The pair must share:

- the same user task,
- the same original model-generated tool call,
- the same serialized request,
- the same pre-failure state,
- the same hidden execution state,
- and the same model-visible ambiguous observation.

This is the core causal design of the paper.

---

# 7. Hidden Execution States

The primary benchmark will define exactly two ambiguous worlds.

## H0 — Not Executed

The original request is generated but does **not** mutate the environment.

The agent still receives an ambiguous failure.

Ground truth:

```text
committed_effects_before_recovery = 0
```

## H1 — Executed, Acknowledgement Lost

The original request executes successfully exactly once.

The success response is discarded.

The agent receives the same ambiguous failure as H0.

Ground truth:

```text
committed_effects_before_recovery = 1
```

The model-visible observation in H0 and H1 should be identical.

A canonical initial form may be:

```text
ToolError: The previous request timed out. Its outcome is unknown.
```

The final exact wording must be frozen before the primary experiment.

No hidden-state metadata may enter the model context.

---

# 8. Primary Recovery Policies

## P1 — Exact Request Replay

Definition:

> Execute the exact already-generated and serialized request again without asking the model to generate or modify another action first.

Requirements:

- no new LLM call before replay,
- same tool,
- same arguments,
- same identifiers,
- same idempotency key if present,
- no verification before replay,
- no parameter rewriting,
- no semantic normalization that changes the request.

Replay is an execution-layer behavior.

It is **not assumed to be safe**.

For non-idempotent operations, replay may duplicate effects.

---

## P2 — LLM Regeneration

Definition:

> Return the ambiguous outcome to the LLM and allow the model to continue the task naturally.

The model may:

- retry the same mutation,
- change arguments,
- generate a new identifier,
- inspect state,
- select another tool,
- stop,
- report uncertainty,
- or take another recovery action.

The model must not be artificially instructed to “retry”.

The condition represents:

> **return control to the model after ambiguity**

rather than:

> **repeat the previous request**

---

# 9. Secondary Baselines

These are useful supporting comparisons but are **not the central claimed contribution**.

## P0 — No Recovery

After ambiguity, terminate and inspect final state.

Purpose:

- establish the effect of the original fault without recovery,
- separate recovery-induced failures from failures caused by the ambiguous event itself.

## P3 — Verify Before Retry

Inspect external state first.

If the intended effect exists:

- treat operation as successful.

Otherwise:

- retry the intended mutation.

This is a prior-work baseline, not a novel contribution.

## P4 — Stable Idempotent Replay

Replay the same request with a stable idempotency mechanism where the API supports one.

Purpose:

- compare execution-layer replay when duplicate suppression is available.

This is especially relevant for APIs such as Stripe sandbox.

---

# 10. Controlled Benchmark

The controlled benchmark is the primary scientific environment.

It must be:

- local,
- deterministic,
- resettable,
- fully observable,
- cheap to run,
- and authoritative about committed state.

## Mutation Class A — CREATE

Example:

```text
create_ticket(customer_id, title, description)
```

Desired effect:

> exactly one intended ticket exists.

Duplicate-sensitive.

## Mutation Class B — APPEND

Example:

```text
append_audit_event(record)
```

Desired effect:

> exactly one intended event is appended.

Duplicate-sensitive.

## Mutation Class C — INCREMENT

Example:

```text
increment_credits(account_id, amount)
```

Desired effect:

> account value increases exactly once by the requested amount.

Strongly non-idempotent.

## Mutation Class D — SET / UPDATE

Example:

```text
set_ticket_status(ticket_id, "closed")
```

Desired effect:

> status equals the intended value.

Often naturally idempotent under exact replay.

## Mutation Class E — DELETE

Example:

```text
delete_resource(resource_id)
```

Useful for testing operations that may become replay-tolerant or produce second-attempt errors.

## Mutation Class F — RESERVATION / State-Dependent Mutation

Example:

```text
reserve_inventory(item_id, quantity)
```

Desired effect may involve:

- reducing available inventory,
- creating one reservation record,
- ensuring constraints remain valid.

This tests state-dependent multi-field mutations.

---

# 11. Controlled Service Requirements

Every controlled environment must provide:

- fresh initial state,
- deterministic mutation semantics,
- authoritative final-state inspection,
- immutable event log,
- state snapshot/clone support,
- reset between trials,
- deterministic evaluator,
- no hidden retries,
- no automatic duplicate suppression unless explicitly part of the treatment.

The evaluator should never rely on model self-report when state can be inspected directly.

---

# 12. Read/Verification Tools

The primary Regeneration condition may expose a read tool if that reflects a realistic agent environment.

Example:

```text
list_tickets(...)
find_ticket(...)
get_account(...)
get_inventory(...)
```

If the model chooses to inspect state naturally, that is considered part of **Regeneration behavior**.

This must remain distinct from the explicit **Verify Before Retry** baseline.

The benchmark should therefore distinguish:

```text
Regeneration spontaneously chooses verification
```

from:

```text
runtime enforces verification before retry
```

The exact tool availability must be frozen per experiment version.

---

# 13. Recovery Budget

Recovery must be bounded.

Suggested initial rule:

## Replay

- exactly one replay execution,
- then evaluate.

## Regeneration

- allow up to a small fixed number of subsequent tool actions,
- suggested starting limit: **3 actions**,
- terminate earlier if the model finishes.

If the limit is exceeded:

```text
termination_reason = action_budget_exceeded
```

The final action limit should be frozen before pilot data collection.

---

# 14. Initial State and Trial Isolation

Every base trial must begin from a fresh isolated environment.

Requirements:

- no intended target effect already exists,
- no state from prior trials is visible,
- Replay and Regenerate arms begin from cloned identical snapshots,
- hidden execution state is applied identically before the recovery fork,
- trial-specific evaluator metadata must not leak to the model.

Isolation failures invalidate the affected pair.

---

# 15. Final-State Classification

Evaluation must be deterministic wherever possible.

Primary categories:

## Correct

Exactly one intended logical effect exists and no unintended mutation occurred.

## Missing Effect

The required logical effect does not exist.

## Duplicate Effect

More than one committed instance of the intended logical effect exists.

## Wrong Mutation

A committed effect exists but does not satisfy the requested task.

## Extra Unintended Mutation

Additional state-changing actions occurred beyond the intended logical effect.

## Infrastructure Failure

A run failed because of experiment infrastructure rather than model/retry behavior.

Infrastructure failures must be excluded from behavioral denominators according to a pre-specified rule and reported separately.

---

# 16. Effect Multiplicity

For operations where one logical effect is intended:

```text
effect_multiplicity =
number_of_matching_committed_effects
/
number_of_intended_logical_effects
```

Since one effect is intended:

- `0` = missing effect
- `1` = correct multiplicity
- `2+` = duplicate effect

This is especially useful for:

- CREATE
- APPEND
- INCREMENT-like effects
- real API duplication.

---

# 17. Regeneration Drift Taxonomy

For every Regeneration arm, compare subsequent behavior with the original request.

Primary categories:

## D0 — Exact Request Match

Same tool and structurally identical arguments.

## D1 — Same Tool, Argument Drift

Same tool, one or more arguments changed.

## D2 — Identifier Drift

Operation/request/idempotency identifier changed.

## D3 — Tool Drift

A different tool is selected.

## D4 — Verification / Read

The model chooses a read-only inspection action.

## D5 — Abandonment / No Mutation

The model terminates or avoids further mutation.

## D6 — Compensating or Alternate Mutation

The model performs a different state-changing action.

## D7 — Other

Behavior does not fit the above categories.

Where practical, structural comparison should be deterministic.

LLM-as-judge should be avoided unless absolutely necessary.

---

# 18. Primary Metrics

## M1 — Final-State Correctness Rate

```text
correct runs / valid runs
```

## M2 — Duplicate-Effect Rate

```text
runs with duplicate intended effects / valid runs
```

## M3 — Missing-Effect Rate

```text
runs with zero intended effect / valid runs
```

## M4 — Extra-Unintended-Mutation Rate

```text
runs with additional unintended committed mutations / valid runs
```

## M5 — Exact Request Preservation Rate

For Regeneration only:

```text
regeneration arms whose next mutation exactly matches M
/
valid regeneration arms
```

## M6 — Request/Argument Drift Rate

Percentage of Regeneration arms exhibiting structural drift.

## M7 — Recovery Tool Calls

Count of tool calls after ambiguity.

## M8 — Additional LLM Calls

Number of extra model invocations after ambiguity.

## M9 — Token Usage

Prompt, completion, and total tokens where available.

## M10 — Recovery Latency

Wall-clock recovery time.

## M11 — Cost

For paid APIs/models, estimated or reported inference/API cost where available.

---

# 19. Real API Extension

Controlled experiments establish causal clarity.

Real APIs provide external validity.

The real API phase should use **fault injection around actual API calls**, rather than relying on naturally occurring network failures.

Architecture:

```text
LLM / Agent
    ↓
Tool Adapter
    ↓
Fault Injection Proxy
    ↓
Real API
```

## Real API A — GitHub

Candidate operations:

- create issue,
- create issue comment,
- update issue fields.

Useful semantic classes:

- CREATE
- APPEND
- SET/UPDATE

Use a dedicated private experiment repository.

Every effect must contain non-sensitive experiment markers or be otherwise traceable for cleanup/evaluation.

Do not run against an important repository.

---

## Real API B — Google Sheets

Candidate operation:

```text
append row
```

Useful for APPEND semantics.

A post-commit acknowledgement loss can produce an easily observable duplicate row after replay.

Use a dedicated experiment spreadsheet.

---

## Real API C — Stripe Sandbox

Use only sandbox/test mode.

Candidate operations should be harmless test entities, such as:

- create test customer,
- create other sandbox resources that support idempotency behavior.

Stripe is especially valuable for comparing:

- same request + same idempotency key,
- same request + changed key,
- regenerated request + changed parameters.

No real charges or financial transactions should be used.

---

# 20. Real API Fault Injection

Two primary modes:

## DROP_BEFORE_SEND

```text
agent issues request
↓
proxy does not forward it
↓
proxy returns canonical ambiguous timeout
```

Ground truth:

```text
mutation did not occur
```

## DROP_AFTER_COMMIT

```text
agent issues request
↓
proxy forwards to real API
↓
API returns success
↓
proxy records authoritative success
↓
proxy discards response
↓
proxy returns the same canonical ambiguous timeout
```

Ground truth:

```text
mutation occurred exactly once before recovery
```

The model-visible error should be the same in both cases.

Timing should be controlled or masked where practical so the hidden state is not trivially inferable.

---

# 21. Model Plan

The paper should not become a benchmark of one model.

The final study should aim for multiple model families, for example:

1. one strong frontier hosted model,
2. one strong model from another provider,
3. one lower-cost hosted model,
4. one local/open model.

The exact final model list will depend on:

- access,
- cost,
- tool-calling support,
- reproducibility,
- rate limits,
- and experimental budget.

Primary settings should minimize avoidable stochasticity.

However:

> temperature 0 must not be treated as guaranteed determinism.

Record exact:

- provider,
- model name,
- model version/date/digest where available,
- sampling configuration,
- tool schema,
- system prompt,
- token limits,
- seed if supported.

---

# 22. Model Robustness Tests

After the primary experiment is stable, run smaller robustness subsets.

## Temperature / Sampling Robustness

Compare lowest supported stochasticity with a moderate setting.

Question:

> Does regeneration drift increase with sampling randomness?

## Prompt Robustness

Use multiple semantically equivalent ambiguity messages.

Example variants:

```text
ToolError: Timeout.
```

```text
The previous tool request timed out. Its outcome is unknown.
```

```text
The request may or may not have completed successfully. Continue the task.
```

Prompt variants should be frozen before execution.

## Original-Request Visibility Ablation

Compare Regeneration conditions where the model sees:

1. the exact original tool call,
2. only a textual summary of what was attempted.

Question:

> Does retaining the exact prior request reduce regeneration drift?

---

# 23. Repeated Ambiguity Stress Test

A secondary stress test may inject repeated ambiguous outcomes.

Candidate conditions:

- one ambiguous failure,
- two consecutive ambiguous failures,
- three consecutive ambiguous failures.

Measure:

- duplicate amplification,
- recovery loops,
- action drift,
- abandonment,
- verification behavior.

This must remain secondary and should not complicate the primary experiment.

---

# 24. Delayed Visibility Test

A secondary controlled test may simulate:

```text
mutation committed
↓
read tool temporarily returns stale state
↓
model decides whether to retry
```

Purpose:

> test whether naturally chosen or explicit verification remains reliable when effects are not immediately visible.

This is a robustness extension, not the headline contribution.

---

# 25. Multi-Step Agent Tasks

After single-mutation experiments work, add realistic multi-step tasks.

Example:

```text
1. inspect customer
2. create support ticket if condition holds
3. update customer status
4. append audit record
5. report result
```

Inject ambiguity into a middle mutation.

Question:

> Do Replay-vs-Regenerate differences persist when the ambiguous tool call occurs inside a larger agent trajectory?

---

# 26. Trace Requirements

Every experiment run must be fully reconstructable.

Recommended run-level fields include:

```text
experiment_version
git_commit
timestamp
base_trial_id
pair_id
arm_id
scenario_id
mutation_class

model_provider
model_name
model_version_or_digest
sampling_configuration
seed

initial_state
user_task
tools_exposed

original_tool_call
serialized_original_request
original_request_hash

hidden_world
original_request_executed
canonical_ambiguous_observation

recovery_policy
recovery_model_messages
recovery_tool_calls

committed_effects
final_state
final_state_classification

duplicate_count
missing_effect
extra_unintended_mutation

request_drift_classification

prompt_tokens
completion_tokens
total_tokens
latency
cost

errors
termination_reason
```

The schema must clearly separate:

## Model-visible data

from:

## Evaluator-only hidden data

The hidden execution state must never appear in model-visible context.

---

# 27. Event Log

In addition to run-level summaries, every trial should maintain an append-only event log.

Candidate event types:

```text
RUN_STARTED
STATE_INITIALIZED
ORIGINAL_REQUEST_GENERATED
ORIGINAL_REQUEST_FROZEN
ORIGINAL_REQUEST_DISPATCHED
ORIGINAL_MUTATION_COMMITTED
AMBIGUITY_INJECTED
RECOVERY_STARTED
MODEL_INVOKED
TOOL_REQUESTED
TOOL_DISPATCHED
TOOL_COMMITTED
TOOL_OBSERVED
RECOVERY_TERMINATED
FINAL_STATE_EVALUATED
RUN_FINISHED
```

Every committed mutation must be reconstructable from the event log.

---

# 28. Critical Experimental Invariants

These invariants must be implemented as assertions/tests where practical.

## INV-1

Replay and Regenerate arms in a pair use the same frozen original request.

## INV-2

Replay and Regenerate arms begin from identical pre-recovery world state.

## INV-3

The two hidden worlds produce the same model-visible ambiguous observation.

## INV-4

Exact Replay invokes no LLM generation before the replayed mutation executes.

## INV-5

Hidden execution state never appears in model-visible context.

## INV-6

Final correctness is determined from authoritative environment state.

## INV-7

Trials cannot observe state from previous trials.

## INV-8

Every committed mutation is recorded in the event log.

## INV-9

Automatic retries in SDKs/HTTP libraries/providers are disabled or explicitly accounted for.

## INV-10

Model/provider middleware must not silently retry tool calls in a way that bypasses the experiment.

## INV-11

Replay executes the frozen request, not a reconstructed equivalent.

## INV-12

Infrastructure failures are distinguished from behavioral failures.

## INV-13

Experiment configuration is versioned and tied to a Git commit.

## INV-14

Primary metrics and exclusions are frozen before full data collection.

---

# 29. Statistical Plan

The experiment is paired.

Primary endpoint:

> **final-state correctness**

Secondary endpoints include:

- duplicates,
- missing effects,
- extra mutations,
- drift,
- tool-call overhead,
- model-call overhead,
- latency,
- token usage.

For binary paired correctness outcomes:

- use McNemar's test where appropriate,
- report raw paired counts,
- report absolute percentage-point differences,
- report 95% confidence intervals,
- use paired/bootstrap intervals where useful.

A useful broader model may later be:

```text
Correct
~
RetrySemantic
+ HiddenWorld
+ MutationClass
+ Model
+ RetrySemantic × HiddenWorld
```

More complex models should only be added if justified.

Do not hide a modest experiment behind unnecessary statistical complexity.

---

# 30. Sample Size Strategy

Do not commit immediately to thousands of runs.

Use three stages.

## Stage A — Engineering Validation

Approximately:

```text
10–20 base trials
```

Purpose:

- verify invariants,
- verify state cloning,
- verify evaluator,
- verify canonical ambiguity,
- verify trace reconstruction.

These runs are not paper results.

## Stage B — Pilot

Run enough paired trials to estimate:

- correctness frequency,
- duplicate frequency,
- regeneration drift,
- infrastructure failure rate,
- runtime/cost.

The pilot is for methodology validation.

## Stage C — Full Controlled Study

Choose sample size using a pre-specified rule based on:

- desired sensitivity,
- pilot variance,
- practical runtime/cost,
- paired design.

Avoid arbitrary post-hoc expansion or stopping based on favorable results.

---

# 31. Proposed Full Controlled Matrix

The eventual matrix may resemble:

```text
6 mutation classes
× 2 hidden worlds
× 4 models
× N base scenarios/repetitions
× 2 primary policies
```

If:

```text
N = 50
```

then:

```text
6 × 2 × 4 × 50 × 2 = 4,800 recovery-arm runs
```

This is only a planning reference.

The actual full sample size must be frozen after pilot methodology review.

Secondary policies and robustness tests should use targeted subsets rather than multiplying the entire matrix unnecessarily.

---

# 32. Real API Sample Strategy

Real API experiments are for external validity, not massive-scale statistics.

Candidate design:

```text
3 APIs
× selected mutation types
× 2 hidden worlds
× 2 primary retry semantics
× 2–3 representative models
× 10–20 repetitions per cell
```

This should produce hundreds of real state-mutating trials without excessive API usage.

Controlled experiments remain the primary evidence.

---

# 33. Repository Structure

Target repository:

```text
retry-semantics-llm-agents/
│
├── README.md
├── RESEARCH_PLAN.md
├── LICENSE
├── CITATION.cff
├── pyproject.toml
├── .env.example
│
├── src/
│   ├── models/
│   ├── runtime/
│   ├── policies/
│   ├── environments/
│   │   ├── controlled/
│   │   └── real/
│   ├── fault_injector/
│   ├── evaluation/
│   └── tracing/
│
├── tests/
│
├── experiments/
│   ├── scenarios/
│   ├── configs/
│   └── manifests/
│
├── results/
│   ├── pilot/
│   ├── controlled/
│   └── real_api/
│
├── analysis/
│
├── research/
│   ├── literature.csv
│   ├── references.bib
│   ├── research_questions.md
│   │
│   ├── notes/
│   │
│   ├── protocol/
│   │
│   ├── methodology/
│   │
│   └── archive/
│       └── research_plan_v0_initial.md
│
└── paper/
    ├── main.tex
    ├── sections/
    ├── figures/
    └── tables/
```

This is a target structure, not a requirement to scaffold everything immediately.

---

# 34. Development Order

Do not build the entire benchmark at once.

## Phase 0 — Repository Baseline

1. Archive old plan.
2. Add this `RESEARCH_PLAN.md`.
3. Initialize Git.
4. Commit current literature/research state.
5. Push private repository.

Exit criterion:

> current research direction exists in version control before implementation begins.

---

## Phase 1 — Freeze Primary Protocol

Create:

```text
research/protocol/
├── primary_experiment_v1.md
├── trace_schema_v1.json
└── protocol_invariants_v1.md
```

The protocol must define:

- canonical ambiguity,
- state model,
- policy semantics,
- action budget,
- read-tool availability,
- evaluator predicates,
- pairing,
- trace schema,
- exclusions,
- statistical endpoints.

Exit criterion:

> another engineer could implement the primary experiment without making methodological decisions.

---

## Phase 2 — Build One Tiny Controlled Experiment

Implement only:

```text
CREATE
×
H0 not executed
×
H1 executed / ACK lost
×
Replay
×
Regenerate
```

Use one deterministic local environment.

Do not add multiple mutation types yet.

Exit criterion:

> one paired trial can be run and fully reconstructed.

---

## Phase 3 — Validate Invariants

Write tests for:

- request freezing,
- snapshot equality,
- hidden-state secrecy,
- identical ambiguity observation,
- replay without LLM reinvocation,
- evaluator correctness,
- trace completeness,
- state reset.

Exit criterion:

> all critical protocol invariants are enforced automatically.

---

## Phase 4 — Engineering Validation Runs

Google Sheets Study 2 operational note (2026-09-21): OAuth attempt #5
succeeded, one engineering spreadsheet CREATE returned a validated HTTP 200,
and provisioning review, reservation and post-setup preflight passed. The first
120-second `LIVE_READ_GO` expired before `read` execution. No read intent or
result exists, Sheets GET count is zero, and paper observations remain zero.
The fixture must be preserved without another CREATE. Further activity needs
the reviewed expired-unused-authorization successor lifecycle, fresh
source-bound startup/OAuth/adoption/read pin and a new one-shot read approval.

Run 10–20 base trials.

Manually inspect traces.

Do not treat results as paper evidence.

Exit criterion:

> no known protocol/harness defect remains.

---

## Phase 5 — CREATE Pilot

Run paired CREATE trials across one or two models.

Measure:

- correctness,
- duplicates,
- missing effects,
- drift,
- recovery actions.

Exit criterion:

> experiment produces interpretable behavior and evaluator agrees with manual inspection.

---

## Phase 6 — Expand Controlled Mutation Classes

Add:

- APPEND
- INCREMENT
- SET
- DELETE
- RESERVATION

Each environment must receive its own deterministic unit tests and correctness predicates.

Exit criterion:

> all six mutation classes are validated independently.

---

## Phase 7 — Multi-Model Controlled Study

Add multiple model families.

Freeze:

- exact prompts,
- tool schemas,
- versions,
- sampling settings,
- action budget.

Run pilot and then full matrix.

Exit criterion:

> primary controlled dataset is complete and immutable.

---

## Phase 8 — Secondary Baselines

Add:

- No Recovery,
- Verify Before Retry,
- Stable Idempotent Replay where appropriate.

These should support interpretation, not redefine the primary contribution.

---

## Phase 9 — Robustness Tests

Targeted subsets only:

- prompt wording,
- sampling temperature,
- original-request visibility,
- repeated ambiguity,
- delayed visibility,
- multi-step tasks.

---

## Phase 10 — GitHub Real API

Implement fault proxy and real GitHub mutations.

Start with:

- create issue,
- comment append.

Validate:

- DROP_BEFORE_SEND,
- DROP_AFTER_COMMIT,
- cleanup,
- final-state evaluator.

---

## Phase 11 — Google Sheets Real API

Implement APPEND trials using a dedicated spreadsheet.

---

## Phase 12 — Stripe Sandbox

Implement safe sandbox mutation trials and stable idempotency-key comparison.

No real money or production data.

---

## Phase 13 — Analysis

Produce reproducible scripts for:

- primary metrics,
- paired comparisons,
- drift taxonomy,
- hidden-world interaction,
- mutation-class comparison,
- model comparison,
- real API comparison.

Every table/figure must be derivable from immutable raw traces.

---

## Phase 14 — Paper

Suggested structure:

1. Introduction
2. Background and Terminology
3. Related Work
4. Retry-Semantics Model
5. Experimental Method
6. Controlled Results
7. Real-API Results
8. Regeneration Drift Analysis
9. Discussion / Design Implications
10. Threats to Validity
11. Conclusion

---

# 35. Literature Work

The existing literature infrastructure remains useful.

Continue maintaining:

```text
research/literature.csv
research/references.bib
research/notes/
```

For each close paper, explicitly record:

- ambiguous-failure model,
- state-mutating tools,
- replay semantics,
- regeneration semantics,
- verification behavior,
- idempotency mechanism,
- experiment environment,
- closest overlap with our paper,
- what our study does differently.

The literature audit should remain hostile.

Before making any novelty claim, actively search for papers that would falsify it.

---

# 36. Closest-Prior-Work Comparison Table

Maintain a living table such as:

| Work | Ambiguous state-mutating outcome | Exact replay isolated | LLM regeneration isolated | Paired replay-vs-regenerate test | Real API | Main distinction |
|---|---:|---:|---:|---:|---:|---|
| RFC 9110 | Yes, conceptually | Retry semantics | No | No | General | Classical HTTP semantics |
| Verified Tool Calls | Yes | Related | Related | No / to verify | Primarily experimental | Verification/idempotency |
| Atomix | Yes / broader failures | Protocol-specific | Not central | No | Tool workflows | Transactional tool use |
| Agent Mesh | Broader | Broader retry | Agent delegation | No | Broader | Delegation reliability |
| ACRFence | Re-execution-related | Yes / security framing | Yes / resynthesis concern | No | Agent runtime setting | Checkpoint/restore security |
| Did It Happen? | Yes | To verify | Recovery behavior | No / to verify | Ambiguous outcomes | Outcome uncertainty |
| **This paper** | **Yes** | **Primary arm** | **Primary arm** | **Yes** | **Controlled + real APIs** | **Retry-locus comparison** |

This table must be updated only from verified reading.

Do not fill cells from paper titles alone.

---

# 37. Threats to Validity

The paper must explicitly consider:

## Internal validity

- hidden-state leakage,
- non-paired original requests,
- unequal initial state,
- timing leakage,
- SDK automatic retries,
- HTTP retries,
- provider middleware retries,
- state reset failure,
- evaluator bugs,
- model session leakage,
- malformed tool call handling,
- unequal recovery budgets.

## Construct validity

- whether final-state correctness captures intended task success,
- whether drift categories represent meaningful behavioral differences,
- whether read tools alter the meaning of regeneration,
- whether synthetic ambiguity represents realistic failures.

## External validity

- limited number of APIs,
- limited model families,
- simple tasks,
- local simulator assumptions,
- API-specific idempotency behavior.

## Statistical validity

- insufficient paired sample size,
- post-hoc metric changes,
- excessive subgroup analysis,
- multiple-comparison inflation,
- infrastructure exclusions after seeing outcomes.

---

# 38. Reproducibility Requirements

Before public release, the repository should include:

- exact dependency versions,
- experiment configs,
- tool schemas,
- prompts,
- model identifiers,
- raw trace schema,
- immutable experiment manifests,
- analysis scripts,
- aggregated results,
- README reproduction instructions,
- secret-safe `.env.example`,
- tests,
- environment details.

Raw traces must not contain:

- credentials,
- sensitive personal data,
- hidden chain-of-thought.

Model reasoning should only be stored if the provider/tool exposes permissible structured output and it is necessary.

---

# 39. Research Ownership

## J. Rashne — Research Owner

Responsibilities:

- understand closest prior work,
- approve RQs,
- approve protocol,
- manually inspect traces,
- review evaluator behavior,
- interpret results,
- decide claims,
- write/rewrite major manuscript sections,
- be able to defend the study orally.

## Codex — Engineering Assistant

Responsibilities:

- repository scaffolding,
- harness implementation,
- deterministic environments,
- fault injector,
- policy implementations,
- real API adapters,
- tests,
- experiment runner,
- tracing,
- analysis scripts,
- reproducibility tooling.

Codex must not decide scientific conclusions.

## ChatGPT — Research Copilot / Reviewer

Responsibilities:

- literature search and falsification,
- methodology critique,
- protocol review,
- hypothesis refinement,
- statistical interpretation,
- hostile reviewer analysis,
- claim/citation audit,
- manuscript structure and editing.

---

# 40. Claim Ladder

## Safe claim

> Ambiguous outcomes create retry problems for non-idempotent state-mutating operations.

Established prior systems knowledge.

## Safe claim

> Replaying an already-generated action and returning control to an LLM for regeneration are different recovery semantics.

Conceptual distinction.

## Empirical claim

> Under the tested conditions, Replay and Regeneration differed by X in final-state correctness, duplicate effects, drift, or overhead.

Only after data.

## Stronger empirical claim

> The effect of retry semantic interacts with hidden execution state and mutation class.

Only after statistical support.

## Possible design implication

> Agent runtimes should distinguish execution-layer replay from model-level regeneration rather than treating both as generic “retry”.

Only if results support it.

## Claims we must not make

- we invented ambiguous-outcome recovery,
- we invented verify-before-retry,
- we solve exactly-once semantics,
- existing agent frameworks are broadly broken,
- all LLM agents behave the same,
- one API/model establishes universal behavior.

---

# 41. Publication Goal

Primary practical goal:

> produce a rigorous, reproducible research artifact suitable for an arXiv preprint and submission to an appropriate smaller conference, workshop, student research track, or journal if the results justify it.

For admissions purposes, quality matters more than pretending the work is top-tier.

The paper should aim for:

- clear question,
- defensible novelty,
- reproducible experiment,
- honest statistics,
- real external validation,
- transparent limitations,
- public code/artifact when safe.

A preprint must be described as a **preprint**, not as a peer-reviewed publication.

---

# 42. Minimum Viable Paper

The minimum publishable version should contain:

- hostile literature audit,
- formal Replay vs Regenerate definition,
- paired experimental protocol,
- two hidden worlds,
- at least several controlled mutation classes,
- multiple models if feasible,
- deterministic final-state evaluator,
- request-drift analysis,
- a real API validation layer,
- reproducible code and traces,
- threats to validity.

The paper should **not** be rushed merely to meet an arbitrary seven-day deadline.

---

# 43. Stronger Version

A stronger submission may add:

- all six mutation classes,
- 3–4 model families,
- multiple real APIs,
- stable idempotency-key experiments,
- delayed visibility,
- repeated ambiguity,
- multi-step tasks,
- stronger statistical modeling,
- artifact release,
- formal state-machine appendix.

These additions should only be made after the core paired experiment is correct.

---

# 44. Immediate Next Steps

Do these in order.

## Step 1

Archive the original research plan.

Suggested path:

```text
research/archive/research_plan_v0_initial.md
```

## Step 2

Save this file as:

```text
RESEARCH_PLAN.md
```

at repository root.

## Step 3

Initialize Git and create the pre-experiment baseline commit.

## Step 4

Push to a private repository.

## Step 5

Freeze the primary experimental protocol:

```text
research/protocol/
├── primary_experiment_v1.md
├── trace_schema_v1.json
└── protocol_invariants_v1.md
```

## Step 6

Review that protocol manually before implementation.

## Step 7

Implement only the minimal CREATE experiment.

Do not start with all six mutation classes or all three real APIs.

---

# 45. Final Success Criterion

Success is not:

> “We invented a universal reliability framework for LLM agents.”

Success is:

> **We precisely isolated replay of a frozen request from model-driven regeneration after an ambiguous state-mutating tool outcome, tested that distinction under controlled hidden execution states, extended the study across different mutation semantics and real APIs, and reported the resulting correctness, duplication, drift, and overhead behavior with a reproducible artifact.**

That is the paper.

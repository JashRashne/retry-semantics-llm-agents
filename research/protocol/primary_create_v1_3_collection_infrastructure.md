# Primary CREATE V1.3 collection infrastructure (phase 1)

Infrastructure evidence revision: `paper-collection-infrastructure-v1`.
Paper experiment/analysis revision: `primary-create-v1.3`.
Inherited execution semantics: `primary-create-v1.2`, unchanged.
The frozen pre-data analysis plan remains authoritative. This document is
collection provenance, not an analysis-plan amendment or statistical extractor.

## Prospective primary-model freeze

Candidate paper manifest ID:
`primary-create-v1.3-fireworks-deepseek-v4-flash-0731-paper-001`.
Canonical UTF-8 JSON byte length: **240807**.
Canonical SHA256:
`a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c`.
The hash covers the manifest, including its versioned primary-model freeze.
The builder is deterministic and introduces no timestamps or data-dependent inputs.

Primary provider: `fireworks`.
Requested model: `accounts/fireworks/models/deepseek-v4-flash-0731`.
Model version/digest: null (no independently pinned digest is available).
Every original-generation and Regeneration configuration explicitly sets
temperature 0.0, top_p 1.0, max_completion_tokens 1024, tool_choice AUTO,
parallel_tool_calls false, seed_supported true, and provider_parameters
`{"reasoning_effort":"none"}`. No hidden reasoning state is introduced or
propagated. Provider seed support is configuration evidence, not a promise of
bitwise provider reproducibility.

The model was selected **before any paper-result collection**, based on protocol
compatibility, sufficient function/tool capability, practical student-budget
constraints, and passing the separate engineering validation gate. The manifest
records `primary-model-freeze-v1`, this prospective freeze assertion, these
structured selection reasons, and the engineering gate's ID/hash/PASSED status.
Engineering behavioral correctness outcomes are not selection reasons and are
not encoded in the freeze. Engineering evidence is outside paper denominators.

Separate gate ID:
`primary-create-v1.2-fireworks-deepseek-v4-flash-0731-eng-001`.
Separate gate SHA256:
`18a128c9ff33997ae1713987bbc3bcde5bf1c597adae8df8970037edcb5c0a7b`.

## Exact schedule and configuration linkage

The immutable paper manifest has exactly 160 slots, indexed 0..159: 20
replicates numbered 1..20 of the unchanged eight-scenario CREATE catalogue.
Odd replicates traverse CREATE-001..008; even replicates traverse 008..001.
Stratum is `(zero_based_replicate + canonical_scenario_index) % 4`, mapped to
A/B/C/D. Queue position never replaces the canonical scenario index.
The unchanged V1.2 stratum-to-world/policy order is materialized in each plan.
Each stratum occurs 40 times globally and five times per scenario. Each
scenario has ten opportunities for either hidden-world-first order and either
policy-first order (also balanced separately within each hidden world).

Slot i has original seed `30000+i`, Regeneration base seed `40000+10*i`, and
config ID `fireworks-deepseek-v4-flash-0731-paper-v1-s{i:03d}`. Both generation
configurations share that unique slot ID. Existing Regeneration derivation
`base_seed + model_call_index` remains unchanged; the paper namespace does not
overlap the frozen engineering seeds or their permitted derived seeds.

## Scheduled-attempt and boundary evidence

`paper-scheduled-attempt-v1` records every scheduled opportunity, including
those without arm traces: manifest ID/hash, both revision identities, paper
kind, slot/replicate/scenario/stratum, provider/model, config ID and seeds,
started/attempted booleans, original-generation evidence, eligibility,
infrastructure evidence, reserved IDs, activated family ID, construction start,
the four manifest-ordered arm opportunities, and structured terminal status.
Reserved IDs do not assert that a family or arm existed.

`original-generation-eligibility-v1` maps the existing runtime reason enum
directly, without changing eligibility: NO_TOOL_CALL, MULTIPLE_TOOL_CALLS,
WRONG_TOOL, INVALID_TOOL_CALL_TYPE, MISSING_OR_INVALID_TOOL_CALL_ID,
MALFORMED_ARGUMENT_JSON, INVALID_ARGUMENT_SHAPE, TASK_INCORRECT_ARGUMENTS,
and REJECTED_GENERATION. Outcome is NOT_REACHED, ELIGIBLE,
INELIGIBLE_BEHAVIORAL, or INFRASTRUCTURE_FAILURE. Detail text is diagnostic,
not the classification source. Original requests, structured responses,
rejected generations, and raw tool-argument strings are retained.

`paper-collection-event-v1` is a deterministic sequence of write-ahead
boundary markers: ATTEMPT_STARTED, ORIGINAL_GENERATION_ATTEMPT_STARTED,
RECOVERY_CONSTRUCTION_STARTED, ARM_OPPORTUNITY_ATTEMPT_STARTED, and
SCHEDULED_ATTEMPT_TERMINATED. A start marker establishes entry into an
opportunity, not proof of provider receipt, a completed call, or a tool commit.
An interrupted active opportunity can have an unknown terminal outcome.

## Infrastructure scope and attribution

Infrastructure records contain enums for scope, stage and subtype; exception
type/message and optional sanitized provider structure are separate diagnostics.
ORIGINAL_GENERATION covers transport, timeout, rate-limit, authentication,
provider-status and unreadable-provider-response failures. FAMILY_SYSTEM
covers setup, clone/snapshot construction and canonical recovery-context
construction failures before activation, without attributing a policy outcome.
ARM requires the exact arm ID, policy and hidden world, and can represent
failure before trace creation or infrastructure failure with an actual trace.
PERSISTENCE represents runner-fatal evidence/persistence failures where possible.

Each activated family retains exactly four attempted arm opportunities in
manifest order, including an opportunity that throws before returning a trace.
A failed arm does not change the paired arm's own retained evaluation or
infrastructure status. Paper traces use a separate versioned provenance wrapper
and the unchanged V1.2 trace constraints. Engineering pair-wide exclusion
behavior and its existing schema remain unchanged.

`pre-trace-arm-boundary-v1` retains observed executor dispatch count, raw model
invocations already issued, authoritative state snapshot/hash and attributable
recovery commit event IDs where capture succeeds. If state capture fails,
explicit capture diagnostics replace unavailable state. These are boundary
facts, not fabricated policy outcomes or invented executed-call counts.
Unreadable Fireworks structures can retain sanitized tool structure without
reasoning fields or credential fields; unparseable success bodies have only
structured boundary/status evidence, not an arbitrary raw body dump.

## Runner and persistence

The provider-neutral runner accepts the immutable paper manifest and an
existing ModelClient, preflights provider identity, and invokes the existing
original-generation and recovery machinery serially. Family preparation and
single-arm execution are shared mechanical extractions from the frozen
scheduled-trial path, not duplicate treatment implementations. The original
prompt, eligibility, H0/H1, schemas, ambiguity, budgets, context and seed
derivation are unchanged. Normal recorded infrastructure failures do not stop
later arms or scheduled slots. No original or recovery retry, replacement,
resampling, concurrency, outcome-dependent stopping, or additional slot exists.
Memory/evidence corruption or inability to persist safely is runner-fatal.

The durable entry point exclusively creates `.RUN_NAME.in-progress`, fsyncs
the manifest, `run_metadata.json`, and journal files/directories before the
first scheduled boundary or model call, then fsyncs each
boundary event and each completed slot's ledger and available traces. A fatal
failure preserves this prefix and exposes structured fatal evidence plus the
in-memory completed prefix when available. A best-effort, versioned
`runner_fatal.json` in that directory records RUNNER_FATAL, infrastructure scope,
active slot, known completed prefix size, the same git commit/timestamp as
run metadata, and explicit prohibition of continuation
or resume; it is diagnostic evidence, never a completed bundle file. It never resumes/retries a run with
an existing in-progress directory. Sudden process death may leave a partial
last journal line or unknown active opportunity; neither is a complete bundle.
Failure of storage itself cannot guarantee persistent diagnostics.

A completed operational collection publishes exactly six files:

- manifest.json
- run_metadata.json
- scheduled_attempts.jsonl
- arm_traces.jsonl
- collection_events.jsonl
- paper_collection_summary.json

The extra event file is necessary to retain write-ahead evidence for failures
before a slot ledger or arm trace can exist. `paper-run-metadata-v1` independently
records manifest ID/hash, paper/execution revisions, and the supplied
TraceRunMetadata git commit and RFC3339 timestamp. It is durable even when an
interruption occurs during slot zero and no arm trace exists. Run-specific
commit/timestamp are not added to the deterministic pre-data manifest.
The final files are canonical,
validated and fsynced in an unpublished temporary directory, then published
by directory rename and parent-directory fsync. Existing targets are refused.
No partially written final file is accepted as a completed bundle.
After atomic publication, the on-disk completed-bundle validator must succeed
before deleting the in-progress prefix. Validation is read-only and never
reruns an experimental action. Failure retains the prefix and raises runner-fatal.
An OSError merely deleting the redundant prefix after successful validation is
logged as a cleanup warning: the collector returns its completed result, the
verified published bundle remains valid, and no experimental action is retried.
The validator cross-checks population, schedule/order/seeds, hash and revisions,
provider/model/configuration identities, family/arm IDs, trace linkage,
arm-local infrastructure status, boundary evidence, event sequence/hash and
operational counts. Missing, extra, noncanonical and incoherent files fail.
Run metadata follows the exact existing trace commit/timestamp validation rules;
every persisted arm trace must have the same commit and timestamp as run metadata.

The collection summary contains operational counts only. COMPLETE_RECORDED
means all scheduled opportunities have terminal collection records, not that
all opportunities were eligible, infrastructure-free or behaviorally correct.
No statistical analysis or paper conclusion is computed.

## Compatibility, scope and deferred work

The original engineering manifest kind and `trace_schema_v1.json` are unchanged;
existing engineering fake-run schema tests and the frozen engineering manifest
hash remain valid. No persisted live engineering bundle was available locally
for an additional on-disk validation. The paper schema is separate and resolves
the frozen schema locally, without network access.

Provider choice is not hard-coded into the collector; the exact Fireworks
freeze is isolated in its paper builder. Current scenario preparation,
authoritative state capture and evaluator remain Ticket-only, deliberately.
No speculative GitHub, Stripe or Google Sheets implementation is included.

Before actual collection there is no observed paper eligibility rate, provider
performance/cost, failure rate, behavioral effect or statistical result. No
STATE_CORRECT analysis table, MALFORMED_GENERATION/BEHAVIORALLY_EVALUABLE_ARM/
PROTOCOL_VALID_RECOVERY mapper, EqualWorldRobustness, confidence interval,
McNemar test, correction, interaction estimate or bootstrap is implemented.
Raw evidence remains available for the later deterministic frozen extractor.
Next: hostile infrastructure audit, then separately implement and audit the
frozen analysis extractor. Researchers must handle prospective git checkpoint
and explicit collection authorization; phase 1 does not run live inference.

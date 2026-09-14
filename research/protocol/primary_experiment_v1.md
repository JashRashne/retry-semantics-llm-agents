# Primary Experiment Protocol V1

## Status and scope

This document freezes the scientific protocol for the first controlled
experiment described in `RESEARCH_PLAN.md`. It is implementation-ready, but it
does not implement the experiment.

Experiment version: `primary-create-v1.1`

Revision 1.1 was finalized before any live experimental run. A
pre-implementation audit identified and resolved omitted Regeneration details
covering model-call seed derivation, post-treatment rejected-generation handling,
multiple-tool continuation, and budget-boundary counting. This remains the V1
CREATE benchmark; the revision completes its execution contract without changing
the research question or treatment definitions.

Included:

- mutation class: `CREATE`;
- hidden worlds: `NOT_EXECUTED` and `EXECUTED_ACK_LOST`;
- primary recovery policies: `EXACT_REPLAY` and `LLM_REGENERATION`;
- one deterministic local `create_ticket` environment;
- paired final-state comparison.

Excluded from V1 are APPEND, INCREMENT, SET/UPDATE, DELETE, RESERVATION,
real APIs, repeated ambiguity, delayed visibility, multi-step tasks, explicit
Verify-Before-Retry, No-Recovery, and idempotency-key baselines.

The estimand is the difference between two recovery policies after one shared,
correct, already-generated request has produced each of two controlled ambiguous
hidden worlds. It is not an estimate of end-to-end agent success from an
arbitrary user prompt, because an eligible original-generation attempt requires
a correct original request before the hidden-world and recovery-policy forks.

## Frozen decisions at a glance

| Decision | V1 value |
| --- | --- |
| Factorial family | One eligible original request yields H0/H1, each with Replay and Regeneration |
| Pairing unit | One hidden-world pair within a family, yielding one Replay arm and one Regeneration arm |
| Original request | Generated and serialized once, then shared byte-for-byte by all four family arms |
| Canonical ambiguity | `ToolError: The previous request timed out. Its outcome is unknown.` |
| Read tool | `list_tickets` is exposed during original generation and Regeneration |
| Replay budget | Exactly one recovery tool execution |
| Regeneration budget | At most three post-ambiguity tool actions |
| Primary endpoint | Deterministic final-state correctness |
| Valid-pair rule | Both arms must be free of infrastructure/protocol invalidation |
| Primary exclusion rule | Infrastructure or pairing failures exclude the pair; behavioral failures do not |
| Arm order | Deterministically counterbalanced from a frozen manifest |

## A. Experimental unit

### Scenario

A scenario is an immutable, hand-authored V1 record with:

```text
scenario_id
customer_id
expected_title
expected_description
user_task
```

`user_task` is rendered once from this exact template:

```text
Create exactly one support ticket for customer "{customer_id}" with title "{expected_title}" and description "{expected_description}".
```

V1 scenario values MUST be printable ASCII, MUST NOT contain control
characters, and MUST NOT contain an unescaped double quote. The materialized
`user_task` is stored in the experiment manifest and trace; it is not rerendered
at run time.

The scenario ID is evaluator-only and MUST NOT appear in the user task, tool
arguments, tool results, or any other model-visible data.

### Frozen V1 scenario catalog

These eight synthetic scenarios are the complete V1 catalog. Pilot/full
manifests may repeat them but may not change their values. Adding or editing a
scenario requires a new experiment version.

| scenario_id | customer_id | expected_title | expected_description |
| --- | --- | --- | --- |
| `CREATE-001` | `CUST-001` | `Login page timeout` | `The login page times out after 30 seconds.` |
| `CREATE-002` | `CUST-002` | `Billing address update failed` | `The new billing address is not saved.` |
| `CREATE-003` | `CUST-003` | `Password reset link expired` | `The password reset link expires immediately.` |
| `CREATE-004` | `CUST-004` | `Mobile app crash on upload` | `The mobile app crashes while uploading a photo.` |
| `CREATE-005` | `CUST-005` | `Order confirmation missing` | `No confirmation appears after the order is submitted.` |
| `CREATE-006` | `CUST-006` | `Account locked after verification` | `The account remains locked after identity verification.` |
| `CREATE-007` | `CUST-007` | `Report export incomplete` | `The exported report omits the final page.` |
| `CREATE-008` | `CUST-008` | `Notification settings not saved` | `Email notification settings revert after saving.` |

### Original request M

`M` is the single, schema-valid `create_ticket` request produced by the model in
response to the scenario. It consists of the provider tool-call identifier, the
tool name, and arguments. The provider's assistant message and tool call are
preserved exactly in `original_tool_call`.

The executable request envelope is frozen as canonical UTF-8 JSON:

```json
{
  "arguments": {
    "customer_id": "CUST-001",
    "description": "The exact scenario description",
    "title": "The exact scenario title"
  },
  "tool": "create_ticket",
  "tool_call_id": "provider-supplied-call-id"
}
```

Canonical serialization for V1 means:

- UTF-8 without BOM;
- no trailing newline;
- object keys sorted lexicographically at every level;
- no insignificant whitespace (`','` and `':'` separators);
- standard JSON string escaping;
- no Unicode normalization or other value rewriting.

All V1 scenario values are ASCII to avoid Unicode-equivalence ambiguity. The
SHA-256 digest of the exact serialized bytes is `original_request_hash`, stored
as lowercase hexadecimal.

The tool-call ID is carried through Replay and logged by the environment but is
not a semantic tool argument. Regeneration drift comparisons ignore a newly
assigned provider tool-call ID; identifier drift concerns identifiers that are
arguments to the tool, such as `customer_id`.

### Original-request eligibility

A scheduled original-generation attempt produces an eligible base trial only
if the model emits exactly one `create_ticket` call, the call validates against
the frozen tool schema, and its three arguments exactly equal the scenario's
expected values. This condition is needed so H1 contains exactly one intended
effect before recovery.

An invalid, missing, multiple, or task-incorrect original call is a
**pre-treatment behavioral failure**, not an infrastructure failure. It MUST be
recorded in the original-generation-attempt log and reported as part of the
original-call eligibility rate. It does not produce a trial family or recovery
arms and MUST NOT be silently resampled or relabeled as infrastructure failure. Any later
replacement schedule must be specified before primary data collection.

### Base trial and trial family

An eligible base trial is the single original-generation attempt that supplies
one factorial trial family. It is identified by `base_trial_id` and contains:

1. one scenario;
2. one model and frozen sampling configuration;
3. one eligible original request M generated exactly once;
4. one fresh initial authoritative state;
5. both hidden-world branches derived from that initial state and M;
6. two policy pairs and four recovery arms.

`base_trial_id` MUST be `bt-{manifest_id}-{ordinal}`, where `ordinal` is a
six-digit, zero-padded scheduled-attempt ordinal. The corresponding
`trial_family_id` MUST be `family-{base_trial_id}`. Both values are materialized
as reserved identifiers in the run manifest before execution and are never
model-visible. They become identifiers of an actual base trial and trial family
only if that scheduled original-generation attempt is eligible.

One family has exactly this hierarchy:

```text
trial_family_id
├── pair-{trial_family_id}-H0
│   ├── EXACT_REPLAY
│   └── LLM_REGENERATION
└── pair-{trial_family_id}-H1
    ├── EXACT_REPLAY
    └── LLM_REGENERATION
```

The family is the matched unit linking the H0 and H1 policy contrasts. M MUST
NOT be generated separately for the two hidden worlds.

### Pair

A pair is the two recovery arms within one family's single hidden world. Its
identifier MUST be `pair-{trial_family_id}-H0` for `NOT_EXECUTED` or
`pair-{trial_family_id}-H1` for `EXECUTED_ACK_LOST`. A pair remains the unit for
Replay-versus-Regeneration comparisons within a hidden world.

Within a pair, the following are held constant:

- scenario and materialized user task;
- system prompt and original-generation tool definitions;
- model identity and sampling configuration used to generate M;
- complete original assistant message and original tool call;
- canonical serialized M and its SHA-256 hash;
- initial authoritative environment state;
- the pair's hidden world;
- post-ambiguity authoritative state and state hash;
- canonical ambiguity observation;
- model-visible history through the ambiguity observation;
- environment, protocol, and experiment versions;
- frozen original-generation and Regeneration sampling configuration.

Only the recovery policy and the behavior caused by that policy differ. The two
policies intentionally have different action/model-call budgets because they
represent different runtime semantics; resource use is measured explicitly.

### Arm

An arm is one recovery-policy execution from a cloned post-ambiguity state.

- `arm_id = {pair_id}:P1` for `EXACT_REPLAY`.
- `arm_id = {pair_id}:P2` for `LLM_REGENERATION`.

Each arm's unique `run_id` MUST be `run-{arm_id}`. A recovery-arm trace is the
unit validated by `trace_schema_v1.json`.

Across all four arms in a family, the scenario, user task, original assistant
message, M bytes/hash, tool definitions, initial state, and initial
model-visible ambiguity context are identical. H0 and H1 post-ambiguity
authoritative states intentionally differ. Within each hidden-world pair, the
two policy arms begin from identical copies of that hidden-world state.

## B. Controlled CREATE environment

### Authoritative state

The deterministic environment state is:

```json
{
  "state_schema_version": "ticket-state-v1",
  "next_ticket_id": 1,
  "tickets": [],
  "mutation_events": []
}
```

The environment is in-memory or local-only, has no network dependency, and has
no background tasks, wall-clock behavior, hidden retry, or duplicate
suppression. State changes occur only through a recorded tool commit.

### Ticket schema

Each committed ticket is:

```json
{
  "ticket_id": 1,
  "customer_id": "CUST-001",
  "title": "Exact title",
  "description": "Exact description"
}
```

Rules:

- `ticket_id` is an evaluator-only monotonically increasing integer assigned at
  commit time from `next_ticket_id`;
- `customer_id`, `title`, and `description` are copied without rewriting from
  the validated tool request;
- tickets are append-only in V1;
- no uniqueness constraint or implicit idempotency behavior exists;
- repeated identical `create_ticket` requests create distinct tickets.

`ticket_id`, `next_ticket_id`, state hashes, event IDs, scenario IDs, hidden
worlds, and arm identifiers MUST NOT be exposed to the model.

### `create_ticket` tool

Frozen model-visible definition:

```json
{
  "name": "create_ticket",
  "description": "Create one support ticket.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "required": ["customer_id", "title", "description"],
    "properties": {
      "customer_id": {"type": "string", "minLength": 1},
      "title": {"type": "string", "minLength": 1},
      "description": {"type": "string", "minLength": 1}
    }
  }
}
```

On a valid call, commit is atomic:

1. allocate current `next_ticket_id`;
2. append the ticket;
3. increment `next_ticket_id` by one;
4. append a mutation event;
5. return model-visible result `{"status":"created"}`.

The result is serialized as compact canonical JSON with no trailing newline and
omits the evaluator-only ticket ID. For the original request under
H1, this success result is discarded and replaced with the canonical ambiguous
observation.

### Read-only `list_tickets` tool

Frozen model-visible definition:

```json
{
  "name": "list_tickets",
  "description": "List the support tickets currently present.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {}
  }
}
```

It returns tickets in ascending `ticket_id` order but omits `ticket_id`:

```json
{
  "tickets": [
    {
      "customer_id": "CUST-001",
      "title": "Exact title",
      "description": "Exact description"
    }
  ]
}
```

The read result uses the same compact canonical JSON rules and no trailing
newline. The read does not alter state, allocate identifiers, or append a mutation event.
Duplicate identical tickets remain separate array elements so their
multiplicity is visible without revealing hidden metadata.

### Mutation event

Every commit appends an immutable evaluator-only event containing:

```text
event_id
event_sequence
event_type = CREATE_TICKET_COMMITTED
source_stage = ORIGINAL | RECOVERY
arm_id (null for the H1 pair's pre-policy-fork original commit)
tool_call_id
serialized_request
request_hash
ticket snapshot
```

Runtime lifecycle events are recorded separately from environment mutation
events. Both use deterministic sequence numbers; wall-clock timestamps are
diagnostic only and are never model-visible.

### State snapshot, cloning, and reset

Snapshots are canonical serialized state plus the environment mutation log.
Before recovery, the implementation must serialize each hidden world's
post-ambiguity snapshot once, hash it with SHA-256, and instantiate that world's
two policy arms by deserializing those same bytes. It MUST NOT independently
reconstruct policy-arm states.

Reset creates a brand-new environment with `next_ticket_id=1`, no tickets, and
no events. Reusing or clearing a previously mutated object is forbidden. Each
trial family receives a new environment instance.

## C. Intended logical effect

For scenario S, the intended logical ticket is the exact tuple:

```text
(
  S.customer_id,
  S.expected_title,
  S.expected_description
)
```

A committed ticket matches the intended request if and only if all three stored
strings equal the scenario strings byte-for-byte after JSON decoding. No fuzzy
matching, case folding, trimming, semantic similarity, embedding, or LLM judge
is permitted.

The evaluator computes:

```text
matching_ticket_count = count(ticket exactly matches intended tuple)
unintended_ticket_count = count(ticket does not exactly match intended tuple)
total_ticket_count = len(tickets)
```

The requested logical operation requires exactly one matching ticket and zero
unintended tickets. Reads never count as effects or mutations.

## D. Hidden world H0: NOT_EXECUTED

For H0, the original executable request M is frozen but is not dispatched to
the environment. The authoritative state remains equal to the initial empty
state.

Before recovery:

```text
original_request_executed = false
matching_ticket_count = 0
unintended_ticket_count = 0
committed_effects_before_recovery = 0
```

The runtime records the hidden choice only in evaluator-only trace data and
injects the canonical ambiguity observation into the model-visible history.

## E. Hidden world H1: EXECUTED_ACK_LOST

For H1, the environment dispatches the frozen bytes of M exactly once. Because
eligibility requires M to match the scenario, the environment commits exactly
one intended ticket. The successful tool result is not placed in model-visible
history.

Before recovery:

```text
original_request_executed = true
matching_ticket_count = 1
unintended_ticket_count = 0
committed_effects_before_recovery = 1
```

The model receives the same canonical ambiguity observation used in H0.

If H1 does not commit exactly one intended ticket, trial-family construction has
suffered an infrastructure/protocol failure; no valid four-arm family exists.

## F. Canonical ambiguous observation

The exact frozen V1 observation is the following 66-byte ASCII/UTF-8 string,
with no leading/trailing whitespace and no trailing newline:

```text
ToolError: The previous request timed out. Its outcome is unknown.
```

It is the complete content of the tool-result message associated with the
original provider tool-call ID. H0 and H1 MUST use byte-for-byte identical
content, role, call ID, placement, and surrounding message history.

### Timing non-disclosure

Hidden-world execution duration is evaluator-only and MUST never enter
model-visible context. The controlled environment exposes no clock or timestamp
tool. No timestamp, duration, dispatch time, hidden-world execution latency,
execution flag, or hidden-state label is included in a model request.

Recovery model requests are stateless and freshly constructed from the frozen
message content and tool definitions. Controlled V1 performs no artificial
sleep, padding, timing equalization, or timing-based invalidation. H0 and H1 are
not required to consume equal physical wall time. Hidden-world construction
latency may be recorded evaluator-side for diagnostics; recovery latency remains
measured independently from the start of each recovery arm.

## G. P1: EXACT_REPLAY

Exact Replay is an execution-layer action:

1. load the exact frozen `serialized_original_request` bytes;
2. verify their SHA-256 digest against `original_request_hash`;
3. dispatch those bytes once through the tool executor;
4. record the resulting observation and any committed event;
5. terminate and evaluate.

Replay MUST:

- invoke no LLM between ambiguity injection and replay dispatch;
- use the same tool name, tool-call identifier, arguments, and serialized bytes;
- perform no read or verification first;
- perform no parsing-and-reserialization before dispatch;
- perform no argument normalization, repair, default insertion, or rewriting;
- execute exactly once, with all SDK/network/provider automatic retries absent;
- terminate after the one recovery execution whether it succeeds or fails.

Protocol violations include any post-ambiguity model invocation before Replay,
a hash mismatch, reconstructing an equivalent request object, changing a value
or identifier, performing a read, dispatching zero or multiple times, or allowing
an implicit retry. A Replay protocol violation invalidates the full pair.

Replay's recovery tool-call count is exactly one and additional LLM-call count
is exactly zero for every valid Replay arm.

## H. P2: LLM_REGENERATION

LLM Regeneration returns control to the model. It is not a forced retry.

### Frozen model-visible context

The regeneration invocation receives a newly constructed context in exactly
this order:

1. one system message with exact content:

   ```text
   You are a tool-using assistant. Complete the user's task using the available tools.
   ```

2. the same frozen `create_ticket` and `list_tickets` definitions exposed during
   original generation;
3. the materialized original user task;
4. the exact stored assistant message containing the original tool call M;
5. one tool-result message linked to M's tool-call ID whose entire content is
   the canonical ambiguous observation.

There is no extra recovery instruction. Invoking the model after the tool-result
message is the neutral continuation opportunity. In particular, the model is
not told to retry, repeat, verify, check, avoid duplication, or stop. Neither the
policy name nor hidden world is included.

`model_visible_context_hash` is SHA-256 over the canonical UTF-8 JSON bytes of
an object with exactly two keys, `messages` and `tools`, containing the four
messages above and the two frozen tool definitions. It therefore commits to the
complete provider input other than separately logged sampling/model settings.

Before their first recovery decision, the H0 and H1 Regeneration arms in one
family MUST have identical context bytes and context hashes. Only after the
model itself selects a tool may subsequent histories diverge through a
state-dependent tool observation such as `list_tickets`.

The model may emit text and stop, call `list_tickets`, call `create_ticket` with
the same or different arguments, emit multiple tool calls, or produce invalid
output. A valid tool result is appended to the same freshly constructed
within-arm history, after which the model may continue while budget remains.

The implementation MUST NOT repair, normalize, or silently reprompt an invalid
model tool call. A schema-invalid or unparsable tool call consumes one action
slot, is recorded as behavioral `INVALID_TOOL_CALL`, terminates the arm with
`invalid_model_tool_call`, and final state is evaluated. Plain text without a
tool call is a valid decision to stop, recorded as `model_stopped`.

If any post-ambiguity Regeneration model invocation raises the existing readable
behavioral `ModelRejectedGenerationError`, terminate immediately with
`model_rejected_generation`. Do not retry or resample the model, execute a tool,
read state automatically, repair output, append a fabricated tool result, or
make another model call. The failed invocation consumes zero Regeneration
tool-action attempts because it returned no provider-neutral executable action.
Provider-specific failed-generation evidence MUST be preserved through the
existing rejected-generation evidence representation and MUST NOT be parsed or
reinterpreted to manufacture a tool action, even when it resembles malformed
tool syntax. Preserve all earlier actions and state, then run the deterministic
final-state evaluator. This is a valid post-treatment behavioral observation,
not an infrastructure failure or pre-treatment eligibility failure.

The failed `ModelClient.complete()` invocation still counts as one
post-ambiguity model invocation in `additional_llm_calls`, has its ordinary
zero-based `model_call_index`, and uses the derived seed for that ordinal. Thus a
first-call rejection has `model_call_index=0`, `additional_llm_calls=1`, and zero
tool-action attempts. A rejection at index 2 after two earlier invocations has
`additional_llm_calls=3`. No recovery-action record is manufactured for the
rejected invocation.

The trace records this outcome as a non-excluding `BEHAVIORAL` error with code
`MODEL_REJECTED_GENERATION`, `behavioral=true`, `caused_exclusion=false`, and the
existing provider, provider error code, failed-generation value, provider request
ID, model-call index, and derived-seed evidence where available. With rejection
on the first Regeneration invocation, H0 remains empty and is evaluated as
`MISSING_EFFECT`, while H1 retains its one successful ORIGINAL ticket and is
evaluated as `CORRECT`. The termination reason separately records how those final
states were reached.

If one assistant response requests multiple tools, requests are considered in
provider order. Process all requests from that response that remain processable
under the action budget before invoking the model again. The model MUST NOT be
reinvoked between tool requests originating from the same assistant response.
Only after the processable requests from that response have been handled may
another model invocation occur, and only if the arm has not terminated and the
remaining protocol budget permits it.

Each in-budget request consumes one action slot. After all three slots are
consumed, the first additional request encountered is recorded as
`BUDGET_REJECTED_TOOL_CALL`, is not executed, and terminates the arm as
`action_budget_exceeded`. Remaining requests in that assistant response are not
validated, executed, or recorded as separate recovery actions. Their raw evidence
remains preserved as part of the complete model response.

## I. Read-tool decision

V1 **permits `list_tickets`**. It is exposed during both original generation and
Regeneration so the tool catalog itself does not change after treatment. An
original-generation attempt that reads instead of producing M is a recorded
pre-treatment behavioral failure.

This decision favors ecological validity: real agents often can inspect state,
and spontaneous verification is precisely one possible consequence of returning
control to the model. A Regeneration read is classified as D4 and remains
distinct from a future Verify-Before-Retry policy, where the runtime mandates a
read before model choice.

The decision gives Regeneration strictly more adaptive capability than Replay
and therefore the V1 estimand compares the two recovery-policy bundles, not
equal numbers of actions or equal information acquisition. This is intentional.
Action counts, model calls, tokens, and latency are secondary outcomes. A later
read-disabled or equal-budget ablation may test the mechanism but is not part of
V1 and must not be substituted post hoc.

## J. Recovery budget

### Replay

- exactly one recovery tool execution;
- zero recovery LLM calls;
- immediate termination after the execution result.

### Regeneration

- at most three post-ambiguity tool-action attempts in total;
- both reads and mutations consume one action;
- invalid or unknown tool requests consume one action;
- model text without a tool call terminates without consuming a tool action;
- all processable tool requests from one assistant response are handled in
  provider order without an intervening model invocation;
- after those requests are handled, the model may be invoked again only if the
  arm has not terminated and the protocol budget permits it;
- after the third tool result, one final model invocation is allowed only to
  finish textually; any further tool request is not executed and terminates as
  `action_budget_exceeded`.

Regeneration model invocations use `model_call_index`, defined strictly as the
zero-based ordinal of calls to `ModelClient.complete()`. The first model
invocation after the canonical ambiguity has `model_call_index=0`; each later
model invocation increments that ordinal by one. `model_call_index` is independent
of `tool_action_attempt_count`, the separate count of requested tool actions
against the three-action budget. One model response may consume multiple tool
attempts while advancing the model-call ordinal only once. V1 permits no
Regeneration model call with `model_call_index > 3`; index 3 is reachable on the
maximum-call path with one tool attempt per model response, but the permitted
final invocation after attempt 3 may have a lower index when an earlier response
contained multiple tool requests.

For example, when model call 0 returns two tool requests, both are processed in
provider order as tool-action attempts 1 and 2 before another model invocation:

```text
model_call_index = 0
tool_action_attempt_count = 1
tool_action_attempt_count = 2
model_call_index = 1
```

If model call 0 instead consumes all three action attempts, the single permitted
final model invocation has `model_call_index=1`, not 3.

`tool_action_attempt_count` starts at zero and counts only in-budget action slots.
It increments for every read, mutation, invalid call, or unknown call considered
while a slot remains and is capped at three. It never becomes four. A rejected
generation consumes zero slots.

`recovery_tool_calls_attempted` is the separate trace/usage count of tool
requests actually considered by the runtime. It counts the up-to-three in-budget
requests plus the first over-budget request, so its V1 range is zero through four.
The first over-budget request does not increment `tool_action_attempt_count`, is
not executed, and terminates processing immediately. Any later requests in the
same assistant response remain only in the preserved raw model-response evidence;
they do not increment `recovery_tool_calls_attempted` or become recovery actions.

```text
0 <= tool_action_attempt_count <= 3
0 <= recovery_tool_calls_attempted <= 4
0 <= recovery_tool_calls_executed <= 3
```

For example, if call 0 returns three valid requests plus a fourth request, the
first three consume and may execute slots 1 through 3. The fourth is the sole
`BUDGET_REJECTED_TOOL_CALL`, is not executed, leaves
`tool_action_attempt_count=3`, sets `recovery_tool_calls_attempted=4`, and
terminates as `action_budget_exceeded`. Further requests from that response are
not separately processed. The same counts and termination apply when calls 0, 1,
and 2 consume one action each and call 3 requests another tool.

Three actions are frozen because they permit the most informative compact
sequence—read, mutate, optionally read again—while preventing unbounded loops.
Thus a valid Regeneration arm makes at most four additional LLM calls: the first
post-ambiguity decision, up to two continuations after actions 1–2, and one
finalization call after action 3.

If the model attempts an action beyond the budget:

```text
termination_reason = action_budget_exceeded
```

The attempted but unexecuted action is preserved in the trace.

If the permitted final model invocation after attempt 3 raises
`ModelRejectedGenerationError`, termination is `model_rejected_generation`, not
`action_budget_exceeded`, because no fourth executable tool request was returned,
regardless of that invocation's ordinal.

## K. State cloning and pairing

The exact family state sequence is:

```text
fresh state_initial
        ↓
freeze eligible original request M
        │
        ├── H0: do not dispatch M
        │       ↓
        │   serialize/hash H0 post-ambiguity snapshot once
        │       ↓
        │   clone identical bytes into H0 Replay and H0 Regeneration
        │
        └── H1: dispatch frozen M exactly once
                discard successful result
                ↓
            serialize/hash H1 post-ambiguity snapshot once
                ↓
            clone identical bytes into H1 Replay and H1 Regeneration
```

All four arm traces store the same initial-state hash, frozen request, and
initial model-visible context hash. Within each hidden-world pair, both arm
traces store the same post-ambiguity-state hash. Immediately before recovery,
the implementation must assert deep equality of the two states within a pair,
including environment event logs, next-ID counters, and snapshot hashes.

H0 and H1 snapshots intentionally differ: H0 has no ticket and H1 has exactly
one intended ticket. Both branches originate from the same serialized initial
snapshot and frozen M. Each hidden-world branch is constructed exactly once and
then cloned; it is never reconstructed independently for its Replay and
Regeneration arms. Runtime bookkeeping that necessarily differs by arm is kept
outside the authoritative environment snapshot.

## L. Final-state evaluator

The evaluator reads authoritative state and scenario data only. It never reads
model claims or asks an LLM to judge correctness.

It records all of these independent fields:

```text
matching_ticket_count
unintended_ticket_count
total_ticket_count
effect_multiplicity = matching_ticket_count
correct
missing_effect
duplicate_effect
wrong_mutation
extra_unintended_mutation
infrastructure_failure
```

Boolean definitions:

- `correct`: matching count is 1, unintended count is 0, and no infrastructure
  failure exists;
- `missing_effect`: matching count is 0;
- `duplicate_effect`: matching count is greater than 1;
- `wrong_mutation`: unintended count is greater than 0;
- `extra_unintended_mutation`: unintended count is greater than 0 when at least
  one intended ticket also exists;
- `infrastructure_failure`: a qualifying harness/provider/protocol failure exists.

The primary classification uses this precedence:

1. `INFRASTRUCTURE_FAILURE` if infrastructure/protocol invalidation exists;
2. `DUPLICATE_EFFECT` if matching count is greater than 1;
3. `WRONG_MUTATION` if matching count is 0 and unintended count is greater than 0;
4. `MISSING_EFFECT` if total ticket count is 0;
5. `EXTRA_UNINTENDED_MUTATION` if matching count is 1 and unintended count is greater than 0;
6. `CORRECT` if matching count is 1 and unintended count is 0.

The state space makes these cases exhaustive. Separate booleans preserve
coexisting defects hidden by precedence. For example, two intended tickets plus
one unrelated ticket has primary classification `DUPLICATE_EFFECT`, with
`duplicate_effect=true` and `extra_unintended_mutation=true`; the unintended
ticket count is one.

Read actions never affect classification except through overhead metrics.

## M. Request-drift taxonomy

Every Regeneration action is classified structurally relative to M. Per-action
precedence is:

1. D4 for a valid read-only `list_tickets` call;
2. D6 for a known different state-mutating tool representing an alternate or
   compensating semantic operation (reserved; no such tool is exposed in V1);
3. D3 for any other different tool name, including an unknown tool;
4. D0 for `create_ticket` with arguments structurally identical to M;
5. D2 for `create_ticket` where any identifier-valued argument differs;
6. D1 for other `create_ticket` argument differences;
7. D7 for invalid, malformed, or otherwise unclassifiable action output.

Frozen categories:

- `D0_EXACT_REQUEST_MATCH`: same executable tool and exactly equal decoded
  arguments; the provider-generated tool-call ID is ignored for drift comparison;
- `D1_SAME_TOOL_ARGUMENT_DRIFT`: same tool, same identifier arguments, but title
  and/or description differs;
- `D2_IDENTIFIER_DRIFT`: same tool but `customer_id` differs. Future protocol
  versions may add operation/idempotency identifiers explicitly;
- `D3_DIFFERENT_TOOL`: a non-read tool other than `create_ticket` is selected;
- `D4_READ_OR_VERIFICATION`: `list_tickets` is selected;
- `D5_ABANDONMENT_OR_NO_MUTATION`: arm-level terminal category when no
  state-mutating action is requested before stopping, invalid termination, or
  budget exhaustion; earlier reads remain recorded as D4;
- `D6_ALTERNATE_OR_COMPENSATING_MUTATION`: a different valid state mutation is
  chosen; structurally unavailable in V1 but retained for schema compatibility;
- `D7_OTHER`: malformed or behavior not covered above.

For multiple actions, the trace stores the ordered class for every action plus:

- `first_action_class`;
- `first_mutating_action_class` or null;
- `terminal_class` (D5 when no mutation was requested);
- `any_read`;
- `any_exact_request_match`;
- `any_argument_drift`;
- `any_identifier_drift`.

Exact-request preservation is one if the first post-ambiguity mutating request
is D0. It is zero when that request has any drift or when the arm produces no
mutation. Reading before an exact mutation therefore preserves the request while
also recording spontaneous verification.

## N. Primary and secondary metrics

### Primary endpoint

`final_state_correctness` is the binary `correct` field from the deterministic
evaluator. The primary comparison is the paired difference between Replay and
Regeneration among valid pairs.

### Secondary outcome metrics

- **duplicate-effect rate:** valid arms with `matching_ticket_count > 1` divided
  by valid arms;
- **missing-effect rate:** valid arms with `matching_ticket_count = 0` divided by
  valid arms, regardless of whether a wrong mutation also exists;
- **extra-unintended-mutation rate:** valid arms with
  `unintended_ticket_count > 0` divided by valid arms;
- **effect multiplicity:** `matching_ticket_count`, summarized as a distribution
  and mean; one intended logical effect is the denominator;
- **exact-request preservation:** Regeneration arms whose first mutating request
  is D0 divided by valid Regeneration arms; no-mutation arms count as not
  preserved;
- **argument drift:** valid Regeneration arms with any D1 action;
- **identifier drift:** valid Regeneration arms with any D2 action;
- **read/verification behavior:** valid Regeneration arms with any D4 action;
- **recovery tool-call count:** attempted and executed post-ambiguity calls are
  reported separately;
- **additional LLM-call count:** post-ambiguity model invocations; Replay is zero;
- **token usage:** original-generation and recovery prompt/completion/total tokens
  are stored separately. Only recovery usage is compared between arms; shared
  original usage is not double-counted as policy overhead;
- **latency:** recovery wall time from policy start to termination. Model and
  tool latency components are recorded separately. Hidden-world construction
  duration is recorded only as evaluator-side diagnostic metadata and is not
  included in any model request.

Costs may be logged as a descriptive field if a provider reports them, but cost
is not a frozen primary or secondary endpoint for the local controlled V1 study.

## O. Exclusions and analysis validity

### Pair-level infrastructure/protocol exclusions

The complete pair is excluded from paired behavioral denominators if either arm
has any of the following:

- provider or model service unavailable independently of the model's response;
- state snapshot serialization, clone, or equality failure;
- trace corruption, missing required event, or unreconstructable committed effect;
- pairing invariant violation, including different M, context, hidden world, or
  post-ambiguity state between arms;
- environment, adapter, or evaluator exception caused by an implementation bug;
- automatic SDK/network/provider retry that bypasses the treatment;
- H1 fails to commit exactly one intended original effect;
- hidden-world state, execution timing, or other evaluator-only metadata enters
  model-visible context;
- protocol configuration does not match its committed manifest.

All excluded pairs and reasons are reported. The unexcluded partner arm is not
retained in the primary paired denominator. A family-construction or
family-linking invariant violation invalidates both hidden-world pairs and the
complete trial family. An arm-local infrastructure failure invalidates its
hidden-world pair; the other pair may remain in its within-world analysis, but
the incomplete family is excluded from the matched H0/H1 interaction analysis.

### Behavioral outcomes that MUST NOT be excluded

- model stops or declares uncertainty;
- model chooses to read;
- model repeats or changes the mutation;
- model emits wrong arguments or a wrong/unknown tool;
- model emits a malformed or schema-invalid tool call;
- a post-treatment Regeneration invocation raises
  `ModelRejectedGenerationError`;
- model exceeds its action budget;
- model creates zero, one, or multiple tickets;
- model makes a task-incorrect decision;
- Replay creates a duplicate or receives a deterministic tool-level error.

Such behavior is recorded, consumes budget where specified, and is evaluated
from final state. A provider parser corrupting an otherwise valid raw structured
response is infrastructure failure only when the raw response and a reproducible
adapter defect establish that cause; it may not be decided from outcome
desirability.

Pre-treatment original-call ineligibility is behavioral and reported separately,
but no policy pair exists and it is outside the conditional recovery estimand.
No post-hoc exclusion reason may be added after primary data are inspected;
protocol amendments require a new experiment version.

## P. Randomness

Randomness sources are separate and independently logged.

### Scenario generation

V1 uses a fixed, hand-authored scenario manifest. There is no runtime scenario
generation randomness. Scenario ordering may be shuffled only by the frozen run
manifest.

### Model sampling

Exact provider, model name, version/digest, temperature, top-p, maximum output
tokens, tool-choice configuration, parallel-tool setting, and all other provider
parameters are recorded. Temperature zero is not described as deterministic.

If seeds are supported, the manifest stores distinct
`original_generation_seed` and `regeneration_seed` values. The same frozen
`regeneration_seed` and the same call-index seed derivation are used for the H0
and H1 Regeneration arms in a trial family. This minimizes avoidable sampling
variation in the initially identical contexts; it does not establish provider
determinism. If unsupported, the seed is null and `seed_supported=false`; no
deterministic claim is made.

For Regeneration, the manifest's `regeneration_seed` is the base seed. For each
zero-based model-invocation ordinal in the closed range 0 through 3, V1 derives:

```text
derived_seed(model_call_index) = base_seed + model_call_index
```

Therefore model calls 0, 1, 2, and 3 use `base_seed`, `base_seed + 1`,
`base_seed + 2`, and `base_seed + 3`, respectively. If the base seed is absent
or null, every derived seed is null. Derivation MUST NOT use hidden-world
identity, arm identity, tool-action attempt count, model output, authoritative
state, hashing, randomness, modulo, or wrapping. The chosen manifest base seeds
must be accepted by the selected providers; this protocol layer defines no
provider-specific overflow or wraparound behavior.

For the same scheduled paired trial, H0 and H1 use the same derived seed at every
model-call index present in both trajectories. Their model-visible histories may
legitimately diverge after a state-revealing action such as `list_tickets`, but
seed derivation remains world-independent. Seeds remain best-effort
reproducibility controls only and do not guarantee deterministic provider output.

### Hidden-world construction and order

Every eligible original request creates both hidden worlds in one trial family;
there is no hidden-world assignment and no separate H0 or H1 original-generation
slot. The manifest records the order in which the H0 and H1 recovery pairs are
executed. This pair order is counterbalanced across families using the frozen
`hidden_world_order_seed`. Hidden-world order therefore affects scheduling only,
never which M, scenario, initial state, or model context a hidden world receives.

### Arm execution order

See Section Q. Arm order is counterbalanced separately from hidden-world order.

Every seed and the algorithm/version used to materialize a randomized manifest
are stored. The fully materialized manifest, rather than re-running a PRNG during
execution, is authoritative.

## Q. Trial and arm execution order

Replay and Regeneration order is deterministically counterbalanced in the frozen
manifest. Consecutive pairs within each `(model_config_id, hidden_world)` block
form order blocks of size two. A frozen seed chooses the first pair's order in
each block; the second pair receives the opposite order. In an incomplete final
block, a seeded choice is used and the imbalance is reported. The order of the
H0 and H1 pairs is separately counterbalanced across trial families.

Allowed order values are:

```text
[EXACT_REPLAY, LLM_REGENERATION]
[LLM_REGENERATION, EXACT_REPLAY]
```

Each arm trace records both planned orders and both positions. Actual execution
must match the manifest. Cloning prevents state-order effects, while
counterbalancing reduces systematic machine/provider drift. All four arms are
executed serially in V1; parallel execution is prohibited.

## R. Engineering-validation stage

Before any pilot, materialize a deterministic queue of **16 original-generation
attempt slots**: eight frozen scenarios and two attempt replicates per scenario.
Execute it in manifest order until eight eligible trial families exist or the
queue is exhausted. One eligible M creates both hidden-world pairs and all four
arms; no replacement M is generated for either hidden world. Every attempt,
including every executed ineligible attempt, is retained. If eight eligible families are not
obtained, engineering validation fails rather than extending the queue post hoc.
The eight families (16 pairs, 32 arms) must be balanced across both policy-arm
order and hidden-world-pair order; otherwise the stage is rerun only after a new
engineering-validation manifest is frozen. These traces are labeled
`engineering_validation` and never enter paper-result denominators.

Pass criteria are all-or-nothing:

- 100% of all four family arms share the same original-request bytes and hash;
- 100% of arms within each hidden-world pair have byte-identical
  post-ambiguity state and state hashes;
- H0 and H1 Regeneration arms have byte-identical initial model-visible context,
  including the canonical ambiguity payload, and identical context hashes;
- zero Replay pre-dispatch LLM invocations;
- exactly one Replay recovery execution in every valid Replay arm;
- zero unrecorded commits and 100% event-log reconstruction of final state;
- zero state leakage across trial families;
- automatic retries are disabled or intercepted in tested adapters;
- every trace validates against `trace_schema_v1.json`;
- evaluator matches hand-calculated golden states for correct, missing,
  duplicate, wrong, extra, and infrastructure cases;
- intentional infrastructure and behavioral fault fixtures are classified under
  the correct exclusion rules;
- all eight families and all 16 constituent pairs are valid after fixing defects
  and rerunning under a new engineering-validation manifest.

Any code or protocol change found necessary restarts the eight-family validation
under a new manifest. Validation outcomes are engineering evidence only.

## S. Pilot stage

The pilot occurs only after engineering validation passes. It estimates or
checks:

- original-call eligibility and model tool-call validity;
- infrastructure failure rate by arm and provider;
- paired correctness frequencies and discordant-pair frequency;
- the within-family H0/H1 contrast in paired policy effects;
- duplicate and missing-effect frequency in H0 and H1;
- regeneration drift and spontaneous-read frequency;
- deterministic evaluator agreement with independent manual review;
- trace completeness and event/state reconstruction;
- model, tool, and end-to-end runtime;
- token usage and any provider cost;
- whether three actions capture behavior without frequent budget truncation.

Manual review uses a preselected random sample drawn from a frozen review seed.
Pilot data do not enter the primary paper analysis. The full-study sample size
and any justified protocol revision are frozen only after a documented pilot
review; revisions require a new protocol/experiment version and a fresh pilot.

## T. Primary statistical plan

For N valid pairs, encode Replay and Regeneration correctness as binary outcomes
and report the paired 2x2 counts:

```text
n11: both correct
n10: Replay correct, Regeneration incorrect
n01: Replay incorrect, Regeneration correct
n00: both incorrect
```

The primary effect is the absolute paired correctness difference, Replay minus
Regeneration:

```text
(n10 - n01) / N
```

Report it as a percentage-point difference with a 95% confidence interval. V1
uses a two-sided exact McNemar test on discordant pairs (`n10`, `n01`). If there
are no discordant pairs, report the test as uninformative rather than inventing a
small p-value.

The primary 95% interval is a paired nonparametric bootstrap percentile interval
from 10,000 resamples of whole pairs, using a frozen `analysis_seed`. Report raw
counts alongside every percentage and interval.

Repeat descriptive paired tables stratified by hidden world. For each complete
trial family define:

```text
delta_H0 = correctness(H0 Replay) - correctness(H0 Regeneration)
delta_H1 = correctness(H1 Replay) - correctness(H1 Regeneration)
family_interaction = delta_H1 - delta_H0
```

Report the mean `family_interaction` and a 95% percentile interval from 10,000
bootstrap resamples of whole trial families using the frozen `analysis_seed`.
This matched interaction is secondary in V1; no additional hypothesis test,
broad multi-factor model, or multiplicity-heavy subgroup search is planned
before sample size is selected.

Pairs excluded for infrastructure reasons are omitted from the behavioral
analysis but reported by reason and arm. Pre-treatment original-call failures
are reported separately. No outcome-dependent stopping or sample expansion is
permitted.

## U. Threats and frozen mitigations

| Threat | V1 mitigation |
| --- | --- |
| Original requests generated independently | Generate M once per trial family before either hidden-world or policy fork; store bytes/hash; assert equality in all four traces |
| Hidden state leaks through wording | One schema-const canonical tool observation with byte equality test |
| Hidden state leaks through timing | Fresh stateless requests contain no clock, timestamp, duration, dispatch time, or hidden-world latency; diagnostic timing is evaluator-only |
| Context differs across arms/worlds | Persist one family context; both H0/H1 Regeneration requests reconstruct it exactly before any recovery action; context bytes/hash asserted |
| Replay invokes model code | Separate policy path; model-invocation counter must remain zero before and after replay |
| Regeneration is forced to retry | No recovery directive; ambiguity tool result is the last message before model invocation |
| Evaluator metadata leaks | Separate `model_visible` and `evaluator_only`; automated forbidden-value/context test |
| State contamination | New environment object per trial family; empty initial-state hash asserted |
| Snapshot arms diverge | Derive each hidden-world snapshot once, clone it for both policies, and assert deep/state-hash equality within the pair |
| SDK or HTTP automatic retry | Controlled service has no network; adapters configured for zero retry and instrument dispatch count |
| Provider middleware retries model calls | Log provider request IDs/attempts where available; unexpected duplicate response path is infrastructure failure |
| Session/context leakage | Stateless fresh model request per original generation and continuation; no reused provider conversation/session |
| Unequal tool availability | Same two tool schemas exposed for original and Regeneration; Replay restriction is the policy treatment itself |
| Unequal action budget | Explicitly define policy bundles; record overhead; do not claim equal-resource comparison |
| Malformed tool calls | No repair or hidden reprompt; count as behavioral and terminate as specified |
| Invalid outputs excluded post hoc | Behavioral failures remain in valid denominators; exclusion enums frozen in schema |
| Evaluator bug | Golden-state unit cases, event-log reconstruction, and manual pilot agreement required |
| Serialization changes Replay | Replay dispatches stored bytes after SHA-256 check; reconstruction is a protocol violation |
| Automatic normalization | ASCII scenarios and exact JSON rules; executor cannot inject defaults or rewrite values |
| Unrecorded mutation | Commit and event append are one atomic environment transition; reconstruction must equal final state |
| Arm-order machine drift | Serial execution with deterministic counterbalancing and logged order |
| Hidden-world mismatch | Every eligible M supplies both H0 and H1; pair order is counterbalanced and logged; supported Regeneration seeds are shared across the family |
| Original-call selection bias | Define conditional estimand; report all generation attempts and eligibility rate; no silent resampling |
| Post-hoc exclusions | Frozen enumerated reasons; amendments require new version before inspecting primary results |

## Protocol-change rule

Any change to the canonical observation, tool schemas, system prompt, task
template, eligibility rule, state semantics, policy behavior, action budget,
evaluator predicates, exclusion rules, or primary analysis creates a new
experiment version. Formatting-only corrections may retain V1 only if they do
not change executable or analytical meaning and are documented before data
collection.

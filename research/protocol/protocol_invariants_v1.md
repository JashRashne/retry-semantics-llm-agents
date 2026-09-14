# Protocol Invariants V1

## Status

These invariants operationalize `primary_experiment_v1.md` for experiment
version `primary-create-v1.2`. Revision 1.2 freezes previously unspecified
deterministic scheduling semantics found during pre-manifest audit and before
any live experimental run. Revision 1.1 remains the pre-implementation
Regeneration-contract amendment. Every invariant is mandatory unless explicitly
limited to one policy. A pair-local scientific violation invalidates the complete
hidden-world pair, not merely the arm in which it was detected. A violation of
the shared original request, initial state, or family linkage invalidates both
pairs and the complete trial family. Engineering-validation runs must demonstrate
enforcement before pilot data are collected.

“Model-visible context” means the exact system, user, assistant, and tool
messages and tool definitions sent to a model. Trace metadata is not
model-visible merely because it is stored, but implementation must maintain a
hard boundary between the two.

## INV-1 — One frozen original request per trial family

**Purpose:** Ensure all four recovery arms—both policies under both hidden
worlds—are derived from the same sampled model intent.

**Failure example:** H0 uses request A while H1 is built from an independently
generated request B, even though policy arms within each hidden world agree.

**Later enforcement/test:** Generate M once before either the hidden-world fork
or policy forks. Persist its exact bytes and SHA-256 hash. Join all four traces
by `trial_family_id` and assert they have identical
`serialized_original_request`, `original_request_hash`, original tool-call
object, and assistant message. A test must make independently generated requests
fail even when their decoded arguments happen to be equal. The family validator
also asserts `trial_family_id = family-{base_trial_id}`, exactly one H0 pair and
one H1 pair, and exactly one P1 and one P2 arm in each pair.

**If violated:** Stop all four arms, label them `PROTOCOL_VIOLATION`, exclude the
complete family, and restart only under new run IDs after fixing the defect.

## INV-2 — Identical post-ambiguity state within a pair

**Purpose:** Make recovery policy the only cause of post-fork state differences.

**Failure example:** The H1 original ticket is present in Regeneration's state
but absent from Replay's state.

**Later enforcement/test:** Serialize the common post-ambiguity snapshot once,
instantiate both arms from those bytes, and assert deep equality and matching
SHA-256 hashes immediately before recovery. Include `next_ticket_id`, tickets,
and the environment mutation log in equality.

**If violated:** Exclude the full pair as `STATE_EQUALITY_FAILURE`; neither arm
may be used descriptively as a behavioral result.

## INV-3 — Initial Regeneration context is identical across H0 and H1

**Purpose:** Prevent the model from learning whether the original mutation
committed from any pre-recovery input, not merely the error wording.

**Failure example:** Both worlds use the canonical error string, but H1 receives
a different tool-call ID, tool-definition order, metadata field, or preceding
assistant message.

**Later enforcement/test:** The schema fixes the exact string
`ToolError: The previous request timed out. Its outcome is unknown.` Assert
byte equality of the complete initial Regeneration request—system prompt, user
task, original assistant tool call M, canonical observation, tool definitions,
and neutral continuation structure—and assert its context hash across H0 and H1
members of each family. Tool observations produced after a model-selected
recovery read may legitimately diverge.

**If violated:** Invalidate the complete trial family and the experiment version
if the context difference was configured intentionally.

## INV-4 — Replay invokes no post-ambiguity LLM

**Purpose:** Preserve Replay as execution-layer reuse rather than another model
decision.

**Failure example:** Replay asks the model to restate or approve M before
dispatch.

**Later enforcement/test:** Put model access behind an instrumented interface.
For a valid Replay arm, assert zero model invocations after ambiguity, one
recovery action by `REPLAY_POLICY`, and dispatch occurring directly from frozen
bytes.

**If violated:** Exclude the pair as `PROTOCOL_VIOLATION`. The run cannot be
relabeled Regeneration after the fact.

## INV-5 — Hidden-world data never enters model context

**Purpose:** Keep H0 and H1 latent to the model.

**Failure example:** A system message, tool result, timestamp, state hash, log
record, or variable name includes `EXECUTED_ACK_LOST`.

**Later enforcement/test:** Construct model requests only from the trace's
`model_visible` object. Recursively scan serialized context for all hidden-world
labels, evaluator IDs, state hashes, execution flags, mutation events, and
timestamps. Use positive canary tests to prove the scanner fails on leakage.

**If violated:** Exclude the pair. Treat any systematic leak as requiring a new
experiment version and fresh data.

## INV-6 — Evaluation uses authoritative state

**Purpose:** Avoid subjective or self-reported correctness.

**Failure example:** The model says “ticket created,” and the evaluator marks the
run correct despite zero tickets.

**Later enforcement/test:** Compute counts by exact equality over the environment
ticket list and scenario tuple. Unit-test all final-state classes. The evaluator
must have no model/API dependency.

**If violated:** Discard evaluations produced by the faulty evaluator and rerun
evaluation only after versioning and validating the fix; rerun experiments if
raw state/event data are insufficient.

## INV-7 — Trials cannot observe prior state

**Purpose:** Prevent cross-trial contamination from changing model choices or
final-state counts.

**Failure example:** `list_tickets` in a new trial returns a ticket created in a
previous trial.

**Later enforcement/test:** Allocate a new environment object per trial family.
Assert the initial canonical state equals the frozen empty-state fixture and has
the expected hash. Run an isolation test that mutates one instance and verifies
another remains empty.

**If violated:** Exclude affected pairs. If scope cannot be determined, discard
the whole contaminated batch.

## INV-8 — Every committed mutation is recorded

**Purpose:** Make final state and duplication fully reconstructable.

**Failure example:** A ticket exists with no corresponding
`CREATE_TICKET_COMMITTED` event.

**Later enforcement/test:** Commit ticket creation and mutation-event append as
one atomic transition. Rebuild final tickets by replaying mutation events from
the initial state and require exact state/hash equality.

**If violated:** Exclude the pair as `UNRECORDED_COMMIT`. If raw effects cannot
be recovered, the batch is not scientifically usable.

## INV-9 — Automatic execution retries are absent or intercepted

**Purpose:** Ensure one recorded dispatch means one execution opportunity.

**Failure example:** An HTTP/SDK layer silently sends Replay twice after an
internal timeout.

**Later enforcement/test:** The local V1 adapter has no network stack and exposes
an instrumented dispatch counter. Configure any shared SDK retry count to zero.
Tests inject retryable-looking exceptions and assert one dispatch and no hidden
commit.

**If violated:** Exclude the pair as `AUTOMATIC_RETRY_DETECTED`; do not attribute
the resulting duplicate to Replay or Regeneration.

## INV-10 — Replay dispatches frozen bytes

**Purpose:** Distinguish literal replay from reconstructing an equivalent call.

**Failure example:** Code parses M and reserializes it with reordered keys or an
inserted default before execution.

**Later enforcement/test:** Verify the SHA-256 hash immediately before dispatch
and pass the stored byte buffer directly to the executor. A test using two
semantically equal but byte-different serializations must reject the changed one.

**If violated:** Exclude the pair as `PROTOCOL_VIOLATION`.

## INV-11 — Infrastructure and behavioral failures remain distinct

**Purpose:** Prevent surprising model behavior from being removed from the
analysis.

**Failure example:** A malformed model tool call is excluded as “provider error”
because it worsens Regeneration correctness.

**Later enforcement/test:** Use the frozen error and exclusion enums. Tests must
classify model stop, invalid arguments, wrong tools, and budget exhaustion as
behavioral, while clone corruption and provider unavailability are
infrastructure. A post-treatment `ModelRejectedGenerationError` terminates
Regeneration as `model_rejected_generation`, remains behavioral and eligible for
state-based evaluation, and preserves its readable evidence. Exclusion requires
an allowed reason and evidence in the trace.

**If violated:** Correct the classification before unblinding aggregate results;
if post-hoc discretion was used, version the protocol and recollect affected
data.

## INV-12 — Configuration is tied to a Git commit

**Purpose:** Make every run traceable to immutable code and protocol.

**Failure example:** A trace names a dirty working tree or a commit that lacks
the used scenario manifest.

**Later enforcement/test:** Refuse experiment execution unless `git_commit`
resolves, the tracked working tree is clean, and the committed experiment
version/config hashes match the manifest. Record the full commit hash in every
trace.

**If violated:** Classify as `CONFIG_COMMIT_MISMATCH`; the pair is not valid
research data.

## INV-13 — Metrics and exclusions are frozen before full collection

**Purpose:** Prevent outcome-driven definitions and selective removal.

**Failure example:** “Correct” is relaxed after observing that one policy often
changes punctuation.

**Later enforcement/test:** Hash the committed protocol, schema, evaluator
version, analysis configuration, and manifest before collection. Analysis code
accepts only those versions. Amendments create a new experiment version.

**If violated:** Do not combine data across definitions. Report the amendment
and rerun the affected experiment version.

## INV-14 — No cross-trial model-session leakage

**Purpose:** Prevent a model from observing or adapting to earlier trials.

**Failure example:** Regeneration continues a provider conversation that includes
another scenario or hidden outcome.

**Later enforcement/test:** Submit stateless requests with freshly constructed
message arrays. Do not reuse assistant/thread/session IDs. Integration tests use
canary text in one trial and assert it is absent from all later serialized
requests.

**If violated:** Exclude all trials sharing the contaminated session; discard the
batch if its scope is uncertain.

## INV-15 — Original M is treatment-eligible and task-correct

**Purpose:** Guarantee H1 begins with exactly one intended committed effect and
isolate recovery semantics from initial tool-selection failure.

**Failure example:** The original model changes the customer ID, then H1 commits
a ticket that cannot count as the intended effect.

**Later enforcement/test:** Before activating the reserved base-trial and
trial-family identifiers, require exactly one schema-valid `create_ticket` call
whose three arguments exactly match the scenario. Log every scheduled
generation attempt, its reserved identifiers, and its eligibility decision.

**If violated:** Record a pre-treatment behavioral failure; create no trial
family or pairs and do not silently resample. This is reported outside the
conditional paired estimand.

## INV-16 — Tool catalog and pre-fork context are frozen

**Purpose:** Ensure observed Regeneration behavior is not caused by changing
tool descriptions or prior messages.

**Failure example:** `list_tickets` is available only in H1, or its description
mentions possible duplication in one condition.

**Later enforcement/test:** Store canonical tool definitions and the four-message
context. Assert the frozen pre-recovery context representation across all four
arms of a family and byte equality of the initial Regeneration requests across
H0 and H1. Assert system-prompt/tool-definition equality across all trials using
the experiment version. User tasks and original calls may differ between trial
families. The original-generation and Regeneration tool catalogs are the same
two definitions.

**If violated:** Exclude affected pairs and create a new experiment version if
the catalog change was intentional.

## INV-17 — Recovery action budgets are enforced exactly

**Purpose:** Prevent unbounded recovery loops and inconsistent stopping rules.

**Failure example:** Regeneration executes a fourth tool call, or Replay retries
after its one execution returns an error.

**Later enforcement/test:** Count every requested read, mutation, invalid tool,
and unknown tool against the three-action Regeneration budget. Assert Replay has
one execution. Regeneration `model_call_index` is strictly the zero-based ordinal
of `ModelClient.complete()` invocations and is independent of the separate
`tool_action_attempt_count`. One response may consume multiple action attempts
while the next model invocation advances its ordinal only once; the model is never
reinvoked between requests from the same response. `tool_action_attempt_count`
starts at zero, counts only in-budget slots, and is capped at three. The first
over-budget request counts only as the fourth `recovery_tool_calls_attempted`, is
recorded as `BUDGET_REJECTED_TOOL_CALL`, is not executed, and terminates further
request processing; later requests in that response remain raw response evidence
only. A rejected generation consumes no tool-action attempt but its failed model
invocation increments `additional_llm_calls`. Test these boundary sequences and
assert no Regeneration model-call ordinal is outside 0 through 3.

**If violated:** Exclude the pair as `PROTOCOL_VIOLATION`, because final state was
produced under a different treatment.

## INV-18 — Hidden-world execution timing is not model-visible

**Purpose:** Prevent hidden-world construction duration from becoming an input
to model recovery behavior while avoiding an unnecessary physical-time
equalization requirement.

**Failure example:** The recovery request includes an elapsed-duration field,
wall-clock timestamp, timeout deadline, dispatch time, or prose derived from the
H1 commit duration.

**Later enforcement/test:** Construct every recovery request statelessly from
frozen messages and tool definitions. Recursively reject clocks, timestamps,
durations, dispatch times, deadlines, and hidden-world latency fields from model
inputs. Timing may be recorded only under evaluator-only diagnostics. Tests use
canary timing fields and assert rejection. H0 and H1 need not consume equal wall
time, and no sleep or timing equalization is performed.

**If violated:** Exclude every affected pair as `HIDDEN_STATE_LEAK`; if the
leaking request template is shared by a family or batch, invalidate that entire
scope and correct it before recollection.

## INV-19 — Policy-arm and hidden-world-pair order follow the manifest

**Purpose:** Avoid systematic runtime/provider drift favoring one policy.

**Failure example:** Every Regeneration arm runs after machine warm-up, or every
H1 pair runs after its H0 counterpart during a period of provider drift.

**Later enforcement/test:** For engineering validation, materialize the exact
16-slot queue before execution: replicate 1 contains `CREATE-001` through
`CREATE-008`, and replicate 2 contains `CREATE-008` through `CREATE-001`. For
zero-based scheduled-attempt index `i`, use
`(hidden_world_order_seed + i) mod 2` with frozen seed zero, mapping zero to
H0/H1 and one to H1/H0. A two-pair block is the two hidden-world pairs in that
single trial's materialized hidden-world order. With frozen
`policy_order_seed = 0`, derive `scenario_ordinal` from the integer suffix of the
assigned `scenario_id`, then derive
`policy_orientation_bit = (policy_order_seed + scenario_ordinal - 1) mod 2`.
Bit zero assigns Replay/Regeneration to the first pair and
Regeneration/Replay to the second; bit one assigns the opposite orders. Run all
four arms serially and compare actual orders and positions with the manifest.
Tests reject swapped or concurrent execution.

The following exact counts apply to the complete 16-slot manifest, not to an
eligibility-filtered subset: eight slots are H0-first and eight are H1-first;
each of H0 and H1 has eight Replay-first and eight Regeneration-first pairs;
every scenario and hidden world has one replicate in each policy order; and
each absolute serial family-arm position 1 through 4 has eight Replay and eight
Regeneration arms. Absolute position is reconstructed from
`hidden_world_pair_position` and `arm_position`.

Engineering validation executes all 16 slots exactly once without an
eligibility-based early stop, replacement, resampling, queue extension, or
retry-until-eligible. Afterward, at least eight families must be eligible and
each of the four frozen strata must contain at least one eligible family:

```text
A = [H0, H1] with policy_orientation_bit 0
B = [H1, H0] with policy_orientation_bit 1
C = [H0, H1] with policy_orientation_bit 1
D = [H1, H0] with policy_orientation_bit 0
```

Original-generation eligibility is a pre-treatment behavioral outcome, so the
eligible subset need not preserve the manifest's exact 8/8 counts. All eligible
families are retained; no post-hoc balanced subset is selected. Every eligible
family and its executed arms must satisfy all applicable engineering invariants,
or engineering validation fails.

The scheduling seeds are manifest controls only: neither may enter
original-generation sampling, `ModelCallConfig.seed`, the Regeneration base
seed, or `base_seed + model_call_index` derivation. Materialization uses only
the specified integer arithmetic and parity mappings; it is independent of
PRNGs, hashes, language/runtime version, dictionary ordering, operating system,
process, machine, and wall clock.

**If violated:** Engineering-validation manifest, eligibility-coverage, or
eligible-family failures fail the complete engineering-validation stage. In a
later study, exclude the affected family from matched interaction analysis and
affected pairs from primary analysis; if ordering was systematic, discard the
batch.

## INV-20 — Final-state predicates are exact and exhaustive

**Purpose:** Eliminate fuzzy semantic judgement and ambiguous category handling.

**Failure example:** A ticket with a paraphrased description is counted as
intended by one evaluator reviewer but not another.

**Later enforcement/test:** Use byte-for-byte equality after JSON decoding for
customer ID, title, and description. Golden fixtures cover every primary class
and overlaps, including two intended plus one unintended ticket. Assert category
precedence and independent booleans.

**If violated:** Correct and version the evaluator before data collection. If
detected after collection, recompute only if immutable states/events are intact
and report the amendment; otherwise recollect.

## INV-21 — Model outputs are not repaired or invisibly reprompted

**Purpose:** Preserve natural Regeneration behavior, including invalid output.

**Failure example:** Middleware fixes a misspelled argument or asks the model
again without logging the first invalid call.

**Later enforcement/test:** Disable tool-call repair and schema-coercion features.
Record raw structured output where permitted, terminate invalid tool calls as
behavioral, and assert model-call count equals recorded provider requests. Never
parse `ModelRejectedGenerationError.failed_generation` into a tool request;
preserve that evidence, terminate without retry or a fabricated observation, and
evaluate the authoritative state reached so far.

**If violated:** Exclude the pair as an implementation/protocol failure. The
repaired output cannot be treated as natural Regeneration.

## INV-22 — Evaluator-only identifiers are never tool semantics

**Purpose:** Prevent hidden correlation markers from making verification or
matching artificially easy.

**Failure example:** `scenario_id`, `trial_family_id`, `pair_id`, or environment
`ticket_id` is embedded in the title or returned by `list_tickets`.

**Later enforcement/test:** Validate materialized tasks and visible tool data
against a denylist of evaluator-only values. The read adapter returns only
customer ID, title, and description. Mutation matching uses scenario data
outside model context.

**If violated:** Exclude affected pairs. Intentional marker exposure requires a
new protocol version with a different construct claim.

## INV-23 — Pair exclusions are symmetric

**Purpose:** Preserve paired analysis and prevent keeping the favorable partner
after one arm fails infrastructurally.

**Failure example:** Replay remains in the primary denominator after its paired
Regeneration arm experiences a provider outage.

**Later enforcement/test:** Analysis joins on `pair_id` before filtering. If
either arm has `valid_for_behavioral_analysis=false`, neither enters paired
counts. Report which arm triggered each pair exclusion. The matched H0/H1
interaction additionally joins both pairs on `trial_family_id` and includes only
families with four valid arms. A valid pair from an otherwise incomplete family
may remain in the corresponding within-hidden-world analysis unless a
family-level invariant failed.

**If violated:** Recompute all paired results. Any analysis that cannot restore
pair symmetry is invalid.

## INV-24 — Each hidden-world state is derived once before its policy fork

**Purpose:** Build both hidden worlds from one initial state and one M, while
ensuring the two policies within each world inherit one common ambiguous state.

**Failure example:** H1 calls `create_ticket` once while preparing Replay and a
second independent time while preparing Regeneration, or H0/H1 are built from
different initial snapshots or requests.

**Later enforcement/test:** From one frozen initial snapshot and M, derive H0 by
performing zero dispatches and derive H1 by dispatching M exactly once and
discarding its success acknowledgement. Serialize each post-ambiguity state
once, then clone it into its two policy arms. Within each pair, both traces
reference the same pre-fork event IDs and snapshot hash. Test dispatch counters
around both forks.

**If violated:** Exclude the complete trial family; independent construction
destroys the factorial match even if final snapshots happen to look equal.

## INV-25 — Every model and tool opportunity is trace-complete

**Purpose:** Reconstruct action choice, overhead, and termination without relying
on aggregate counters.

**Failure example:** Usage reports two recovery tool calls but only one action is
present, or a budget-rejected fourth call is omitted.

**Later enforcement/test:** Reconcile lifecycle events, recovery actions,
provider request IDs, token usage, dispatch counts, commit events, observations,
and termination. Include attempted-but-unexecuted budget actions. Validate the
arm trace against `trace_schema_v1.json`. A rejected-generation termination must
record behavioral, non-excluding error evidence and no manufactured recovery
action for the failed invocation.

**If violated:** Exclude the pair as `TRACE_CORRUPTION` unless the missing data
can be deterministically reconstructed from immutable raw records under a
documented pre-analysis repair.

## INV-26 — Frozen-request representations are internally coherent

**Purpose:** Prevent a trace from presenting one call to the model while Replay
executes a different byte sequence.

**Failure example:** `model_visible.original_tool_call` names customer A, the
assistant message contains customer B, and `serialized_original_request`
contains customer C despite sharing a copied hash field.

**Later enforcement/test:** Parse the eligible original provider call once,
construct the frozen envelope once, and assert that the assistant message,
`original_tool_call`, serialized request, request hash, tool-result call-ID
linkage, and environment dispatch record all describe the same tool call. Hash
the combined messages/tools object according to the protocol and verify it
before every Regeneration invocation and across all four family traces.

**If violated:** Exclude the family as `PAIRING_INVARIANT_VIOLATION`; no arm can
be interpreted because the treatments did not share a coherent M.

## INV-27 — Regeneration sampling is matched across hidden worlds

**Purpose:** Minimize avoidable first-decision sampling variation when comparing
H0 and H1 Regeneration behavior from an initially identical context.

**Failure example:** A provider supports seeds, but H0 and H1 use unrelated
Regeneration seeds or different temperature/top-p settings.

**Later enforcement/test:** Store one frozen Regeneration sampling configuration
per trial family. When provider seeds are supported, use the same base
`regeneration_seed` and derive the seed for each zero-based model-invocation
ordinal 0 through 3 as `base_seed + model_call_index`. If the base seed is null,
every derived seed is null. The derivation MUST NOT use hidden-world identity,
arm identity, tool-action attempt count, model output, authoritative state,
hashing, randomness, modulo, or wrapping. Assert H0/H1 seed equality at every
model-call index that exists in both trajectories and equality of all other
sampling fields across the two Regeneration traces. Exact Replay records no
Regeneration sampling use. Provider seeds are best-effort controls only; when
unsupported, require `seed=null`, `seed_supported=false`, and make no determinism
claim.

**If violated:** Exclude the family from the matched H0/H1 interaction analysis;
the hidden-world pairs may remain in within-world policy analyses only if all
other pair invariants hold and the mismatch was not caused by broader
configuration drift.

## Required pre-pilot review

Before declaring engineering validation complete, a reviewer must answer yes to
all of the following from code, tests, and sample traces:

1. Is each comparison genuinely paired?
2. Is M generated only once per trial family and shared across all four arms?
3. Are H0/H1 absent from all initial model-visible bytes, including any timing
   fields or metadata?
4. Does Replay bypass the model completely after ambiguity?
5. Can Regeneration read, mutate, change course, or stop without instruction?
6. Is correctness computed without an LLM judge?
7. Are all automatic retry layers disabled or counted?
8. Can mutation events exactly reconstruct final state?
9. Are exclusions limited to the frozen reasons and applied symmetrically?
10. Can an engineer run the protocol without choosing new scientific rules?

Any “no” blocks the pilot.

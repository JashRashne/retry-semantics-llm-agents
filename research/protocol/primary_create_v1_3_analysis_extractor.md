# Ticket primary-create-v1.3 deterministic analysis extractor V1

This prospective extractor implements Analysis Plan v1.0 against **completed
paper-collection-evidence-v2 bundles only**. Execution remains
primary-create-v1.2; the paper experiment remains primary-create-v1.3. No paper
observations were used to implement or test these mappings. Statistical tests
use synthetic scores and the retained published reference fixtures.

Entry points:

```python
from retry_semantics.experiment.analysis_evidence import extract_ticket_analysis
extract_ticket_analysis(source_bundle, separate_new_output_directory)
```

```sh
.venv/bin/python -m retry_semantics.experiment.analysis_evidence SOURCE OUTPUT
```

The extractor imports no inference client for execution and makes no model,
transport, collection, or engineering-validation calls. Snapshot reconstruction
uses the frozen Ticket parser and state evaluator solely to read evidence.

## Input contract and publication

The unchanged `validate_paper_collection_bundle` is called before derivation.
It checks the six canonical files, completed ledger, scheduled identities,
revisions, provider/model, trace/run provenance, V2 classifications, actual
execution prefixes and authoritative state. The extractor additionally pins:

- Manifest ID: primary-create-v1.3-fireworks-deepseek-v4-flash-0731-paper-001.
- Canonical manifest bytes: 240807.
- SHA256: a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c.
- Collection evidence: paper-collection-evidence-v2. Valid historical V1 bundles
  are rejected for this final analysis.
- Frozen plan: research/protocol/primary_create_v1_3_analysis_plan.md, SHA256
  23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88.

In-progress paths, partial/noncanonical/incoherent bundles, overlapping raw and
analysis directories, and existing output directories are rejected. Input or
analysis-schema validation failures create no output directory. All derivation
and output-schema validation occur in memory. The captured source bytes receive a second completed-bundle validation and
hash equality check before derivation; hashes are rechecked before publication. Four artifacts are written and fsynced in an extractor-owned sibling
staging directory, then renamed into a new output directory. Failed staging is
removed. Raw source files are never written. No seventh collection file exists.

## Exact structured mappings

`attempt` denotes a scheduled_attempts.jsonl record with
eligibility.outcome=ELIGIBLE. `opportunity` denotes one of its four
arm_opportunities. `trace` is linked by identifiers.arm_id, when present.
`measurement` is opportunity.measurement_evidence, cross-checked against the
trace extension or pre_trace_evidence by the frozen validator. Null means not
applicable or not deterministically available; it never substitutes zero.

| Derived field | Exact source and rule |
| --- | --- |
| slot_index, replicate, scenario_id, stratum | attempt fields of the same names |
| family_id / reserved_trial_family_id | attempt.family_id / attempt.reserved_trial_family_id; retain the null activated ID for pre-arm failures |
| pair_id, arm_id | validator-checked opportunity.arm_id; pair_id is the prefix before `:` |
| hidden_world / world / policy | opportunity.hidden_world / fixed NOT_EXECUTED→H0, EXECUTED_ACK_LOST→H1 / opportunity.policy |
| arm_opportunity_status, attempted | opportunity.status, opportunity.attempted |
| raw_infrastructure_failure | opportunity.infrastructure_failure, retained unchanged |
| infrastructure_failure | Raw failure except Regeneration diagnostic.response_failure.category=MODEL_GENERATION_STRUCTURE: that returned-generation malformation is behavioral and analysis infrastructure is null. Every other raw failure remains analysis infrastructure |
| family_system_failure | attempt.family_system_failure, retained separately; never assigned a policy score |
| source_trace_id | trace.identifiers.run_id; null without a trace |
| termination_reason | trace.termination_reason; null without a trace; not synthesized from errors |
| terminal_state_snapshot / terminal_state_sha256 | Canonical trace.evaluator_only.final_state / final_state_hash; otherwise pre_trace_evidence.authoritative_final_state_snapshot / authoritative_final_state_sha256 |
| authoritative_terminal_state_available | Snapshot is non-null; its hash and frozen Ticket snapshot structure must validate |
| matching_ticket_count / unintended_ticket_count | Exact customer_id/title/description equality against manifest.entries[slot].scenario.customer_id/expected_title/expected_description. Frozen evaluate_ticket_state supplies counts without infrastructure input. Trace intended_effect must equal this manifest effect |
| STATE_CORRECT | matching=1 AND unintended=0; integer 0/1 when authoritative state exists, null otherwise; runtime correct is never used |
| MISSING_MUTATION | matching=0; null without state |
| DUPLICATE_MUTATION | matching>1; null without state |
| WRONG_MUTATION | unintended>0; null without state; these three flags overlap |
| BUDGET_EXHAUSTED | Regeneration termination_reason=action_budget_exceeded, corroborated by recovery_actions.action_type=BUDGET_REJECTED_TOOL_CALL; otherwise 0 |
| REJECTED_GENERATION | Regeneration non-null measurement.model_invocations.rejected_generation. For traces this must agree with model_rejected_generation termination; no rejected raw text is parsed |
| MALFORMED_GENERATION | Regeneration captured ModelResponse terminates invalid_model_tool_call, corroborated by INVALID_TOOL_CALL/INVALID action; OR a measurement invocation has provider_response_returned=true and response_failure.category=MODEL_GENERATION_STRUCTURE |
| BEHAVIORALLY_EVALUABLE_ARM | 1 iff authoritative state exists, opportunity.attempted=true, analysis infrastructure is null, and family_system_failure is null; else 0 |
| PROTOCOL_VALID_RECOVERY, Replay | Trace exists, analysis infrastructure null, reason=replay_executed, exactly one VALID executed mutating action, serialized_request and request_hash equal frozen_original serialized_original_request/original_request_hash. Frozen V2 validation also requires no model invocations and exactly one mutating successful execution. Any executor/protocol/infrastructure failure scores 0 |
| PROTOCOL_VALID_RECOVERY, Regeneration | Trace exists, no malformed/rejected/budget flag or analysis infrastructure, reason=model_stopped; every executed action is VALID, and every non-executed action is MODEL_STOP. Thus procedural validity is independent of state correctness |
| model_calls_issued | Count measurement.model_invocations.provider_request_dispatched=true; transport attempts, never complete() entries or claimed server receipt |
| read_only_tool_calls_executed | Count measurement.successful_tool_executions.mutating=false |
| state_mutating_tool_calls_executed | Count measurement.successful_tool_executions.mutating=true |
| recovery_tool_calls_executed | Read count + mutating count |
| OBSERVATION_BEFORE_WRITE | Regeneration: 1 iff the first successful execution-journal entry is read-only. This is equivalent to a read before the first write, including reads followed by termination without writing; empty journal gives 0 |
| STATE_CORRECT_SENSITIVITY | Analysis ARM infrastructure with policy_attributable=true gives 0; otherwise evaluable STATE_CORRECT; unavailable/non-attributable outcomes remain null |
| measurement_evidence, recovery_actions | Copy the structured measurement object and trace recovery_actions respectively; actions null without a trace. No executor_dispatch_count is copied or used for costs |

Replay MALFORMED_GENERATION, REJECTED_GENERATION, BUDGET_EXHAUSTED and
OBSERVATION_BEFORE_WRITE are always null. Eligible pre-arm/system failures have
no recovery outcome: protocol and model-behavior flags, costs and observation
are null; evaluability is zero and state is unavailable. This preserves an
eligible opportunity without inventing a policy outcome. Attempted arms always
have V2 measurement evidence: an empty successful-execution prefix gives exact
zero executed calls, including infrastructure failures before execution.

PROVIDER_RESPONSE_STRUCTURE, PROTOCOL_COMPATIBILITY (including reasoning-policy
failures), IMPLEMENTATION_INCOHERENCE, HTTP failures, timeout/connection failures,
rejected generations and budget exhaustion are never adapter malformed-generation
flags. Behavioral malformed/rejected/budget outcomes remain evaluable with
terminal state. No exception message, assistant text, hidden reasoning, invalid
argument text or provider error text is classified.

## Original-generation raw versus analysis classification

Raw V2 collection evidence preserves the historical original-generation runtime
infrastructure label, including eligibility.outcome=INFRASTRUCTURE_FAILURE,
non-null original_generation_infrastructure and
terminal_status=ORIGINAL_GENERATION_INFRASTRUCTURE_FAILURE. No source record or
raw paper_collection_summary.json is rewritten.

The final analysis treats returned MODEL_GENERATION_STRUCTURE failures as
pre-treatment behavioral model malformation, consistently with recovery-side
reclassification. The helper analysis_original_generation_infrastructure returns
true iff original_generation_infrastructure is non-null AND it is not a V2
model-response-failure-v2 diagnostic classified MODEL_GENERATION_STRUCTURE.
The exact source is original_generation_infrastructure.diagnostic.response_failure;
category/stage are structured evidence, and no exception-message inference occurs.
Missing classification on a legacy diagnostic does not erase its infrastructure
label; the final bundle extractor continues to reject V1 inputs.

PROVIDER_RESPONSE_STRUCTURE, PROTOCOL_COMPATIBILITY,
IMPLEMENTATION_INCOHERENCE, timeout, connection/transport, authentication, 429,
HTTP/provider-status and other infrastructure failures remain analysis
infrastructure. The rate denominator stays 160. An original malformed generation
remains non-eligible under the untouched raw eligibility rule, activates no family,
and contributes no recovery arms. Eligibility and the conditional recovery
estimand are unaffected. No optional descriptive field or result-schema expansion
is introduced.

## Matched families and sensitivity

One family row exists for each eligible scheduled attempt, including eligible
family-construction failures. Its family_id is the reserved identity (unique and
stable); activated_family_id separately retains attempt.family_id. Each H0/H1
object contains pair/arm identities and primary/sensitivity pairs in the fixed
order [Replay, Regeneration], or null.

Primary pairs exist iff both arms are behaviorally evaluable. The primary
interaction requires both world pairs, hence all four arms. Per-world policy
correctness uses the same matched N. Family rows also retain the primary
interaction completeness flag and integer contribution
(H1 Replay−Regeneration)−(H0 Replay−Regeneration).

Sensitivity uses analysis infrastructure attribution. An attributable failed
arm scores zero; the paired arm keeps its independent state score. Both failed
arms score zero. Non-attributable family/system/pre-arm failures and missing
non-infrastructure states leave the pair unavailable. Category-B model
malformations retain their behavioral state score, rather than infrastructure
sensitivity zero. Recompute paired summaries, deltas, McNemar, Holm and complete
family interaction using these sensitivity pairs.

Operational fragility is true for a strict positive↔negative reversal of either
nonzero primary delta or a comparable Holm decision change. Zero/nonzero
transitions are recorded separately. Without a demonstrated change, fragility
is false only if both primary and sensitivity Holm families are fully estimable;
otherwise null. No unavailable decision is interpreted as non-rejection.

## Frozen statistics and independent goldens

The existing analysis_statistics.py formulas remain unchanged. The final results
integrate its derived-score summaries, replacing only its wrapper schema/status
with the completed-analysis schema/status. The core-only schema remains distinct.

Paired cells are n11, n10, n01, n00 and delta=(n10−n01)/N. Newcombe **paired-data
Method 10** uses z=1.959963984540054, ordinary Wilson intervals without continuity
correction and the specified positive-phi numerator correction. Zero marginals
set phi=0; N=0 gives null; N>0 zero discordance still receives its interval.
Only negative radicands within eight ULPs of the sum of absolute terms are
protected as roundoff. Meaningful negatives raise; endpoints are not clipped.

Independent goldens are transcribed from Newcombe's original
[1998 paired-data paper](https://www.eiti.uottawa.ca/~nat/Courses/csi5388/Newcombe.1998.pdf),
Table III, pp. 2641–2642 (PDF pages 7–8), **Method 10**. The retained fixture
`tests/fixtures/newcombe_paired_method10_v1.json` records cell mapping, eleven
printed reference intervals and their four-decimal tolerance 0.00005. Goldens
were not generated by the implementation or from agent outcomes.

Printed row (1,97,1,1) stays quarantined separately: the source prints lower
limits 0.8737 for Method 8 and 0.8736 for Method 10 despite unchanged negative
phi. The prescribed formula gives approximately 0.873672, rounding to 0.8737.
Neither the formula nor reference tolerance is changed to accommodate this row.

Exact McNemar uses an integer finite math.comb sum, denominator 1<<m, and only
converts the final probability to float; m=0/N>0 gives 1.0, N=0 null. Exactly
H0/H1 form the alpha=0.05 Holm family, using stable H0/H1 ties and monotone
adjusted p-values. If either N=0 both decisions/adjustments are null and any
available raw test is descriptive; the family is never reduced.

Interaction uses whole complete families in increasing slot order, one local
random.Random(20260916), 10000 bootstrap samples, each N randrange(N) draws, and
sorted endpoint indexes 249/9749. Equal-world robustness is explicitly labeled
DESCRIPTIVE EQUAL-WORLD EXPERIMENTAL SUMMARY, uses identical matched populations
for both policies, and is null if either world N=0. It is not prevalence weighted.
Weakening uses both **primary** intervals with strict lower>−0.20 and upper<+0.20;
equality does not satisfy the rule. It is a reporting flag, not another test.

## Denominators

Every emitted rate carries numerator, denominator and rate; denominator zero
gives rate null. Non-applicable Replay model/observation rates are null objects.

- Eligibility and original-generation infrastructure denominators are all 160
  scheduled original attempts. Eligibility numerator uses raw ELIGIBLE and is
  unchanged. Infrastructure numerator uses
  analysis_original_generation_infrastructure(attempt): raw
  original_generation_infrastructure is non-null, except when its V2
  diagnostic.response_failure.category is MODEL_GENERATION_STRUCTURE.
- Behavioral failure modes use behaviorally evaluable arms in each policy/world.
- Observation-before-write uses evaluable Regeneration arms in each world.
- Recovery infrastructure uses all eligible opportunities per policy/world,
  numerator only analysis policy-attributable ARM infrastructure. Category B
  is behavioral. Pre-arm/system/family failures are separate counts.
- Protocol validity uses opportunities with an actual recovery outcome or
  attributable arm infrastructure outcome (non-null protocol flag); attributable
  infrastructure contributes zero, pre-arm failures have no flag/denominator entry.
- Paired correctness rates use the matched per-world primary or sensitivity N.

## Artifacts, schemas and deterministic bytes

| Artifact | Versioned schema / record identity |
| --- | --- |
| analysis_provenance.json | analysis_provenance_schema_v1.json / ticket-analysis-provenance-v1 |
| analysis_arms.jsonl | analysis_arm_schema_v1.json / ticket-analysis-arm-v1 |
| analysis_families.jsonl | analysis_family_schema_v1.json / ticket-analysis-family-v1 |
| analysis_results.json | analysis_results_schema_v1.json / ticket-analysis-results-v1 |

All are derived analysis V1, distinct from source measurement V2 and the pure
statistical-core-only schema. Results have analysis_version
`ticket-primary-create-analysis-v1` and status `COMPLETED_VALIDATED_V2_ANALYSIS`.
Schemas reject extra top-level fields, constrain null/binary/count fields, and
resolve structured source-evidence references through a local registry only.

Provenance records extractor_version `ticket-analysis-extractor-v1`, component
hashes and their canonical aggregate hash (extractor/statistics/serializer and
analysis schemas), manifest ID/hash, source paper/execution/evidence revisions,
source run git commit/timestamp, all six raw file SHA256 hashes, frozen analysis
plan identity/path/hash, bootstrap seed/replicates, and hashes of the other three
analysis artifacts. It contains no source/output absolute path, analysis-time
clock, random output identifier or mutable wall-clock timestamp. The provenance
file's own hash is external to it, avoiding self-reference.

Canonical JSON uses the unchanged serializer: recursively sorted string keys,
compact separators, UTF-8 without BOM, finite Python floats serialized using
shortest round-trip JSON representation (no display rounding). JSON has **no
trailing newline**. Each JSONL row has exactly one LF, including the final row;
empty populations produce zero-byte JSONL. Arms sort by (slot_index, H0/H1,
policy string); families sort by slot_index. Statistical ordering is
(slot_index,family_id). Same bundle/extractor commit and supported Python runtime
produce byte-identical artifacts. No cross-arbitrary-runtime float guarantee is
claimed. Independent subprocess tests compare all four bytes and hashes and
recheck all six raw hashes.

## Final offline verification

- Analysis-specific: **150 passed**, including 55 final V2 extractor tests (10 original-generation classification regressions).
- Paper collection/manifest/measurement: **170 passed**.
- Selected frozen runtime/model/environment/serialization regressions: **346 passed**.
- Complete suite: **824 passed**.
- All 37 protected runtime/model/environment, collection/measurement/trace,
  source and analysis schemas, manifest-builder, statistical-core, Newcombe fixture and analysis-plan files retain
  their initial byte hashes. No execution or source-evidence semantics changed.
- Manifest reconstructed as 240807 bytes with the frozen ID and SHA256 above.
- Independent processes against one synthetic V2 input produced identical bytes
  and hashes for all four artifacts; all six raw source hashes stayed unchanged.
- No live inference, real credentials, paper collection, engineering-validation
  gate execution, commit or push occurred. No remaining B1/B2 measurement blocker
  prevents final V2 analysis. Missing authoritative states and nonactivated
  opportunities retain their explicitly defined null values.

These are hashes from one **synthetic input bundle**, not paper results or
statistical goldens. Newly synthesized bundles can have different raw latency
bytes, and therefore different source/provenance hashes. The repeated-process
comparison uses exactly the same completed bundle.

| Artifact | Repeated-process SHA256 |
| --- | --- |
| analysis_arms.jsonl | `0dd58bc8638a8360acbcd2e18f6a0e4ad0ff0c930c59cc853d31962e5048b7e4` |
| analysis_families.jsonl | `cb917961437fd4bf91e0f9c9731fa82d1548520220502f49afee6d1f6cb0167b` |
| analysis_provenance.json | `ee114a3ede3497f89155c487a019e1ef211d293cf3b9708292dc0a1854929f0f` |
| analysis_results.json | `aa2dda34f4187e1132b4ce17bc3cc43835d8cadc397d7c399e52068a96dd4d72` |

Canonical sorted hash-map SHA256: `4cdf1d1a7b6532e740d5a196564709c07260c43eaca88d50d167c71e219f0f58`.

Recommended next step: final hostile pre-data audit, followed by researcher-controlled paper collection. The extractor does not launch collection.

## Original-generation classification correction verification

Ten offline regressions inject failures during original generation into validated
V2 bundles. The model-structure case uses the actual frozen adapter failure
MODEL_GENERATION_STRUCTURE / TOOL_CALL_ARGUMENTS for non-string arguments.
All raw historical labels and raw summary counts remain unchanged. Eligibility
stays 1/160 in these fixtures; category B does not enter the analysis
infrastructure numerator, while a separately injected true original timeout does.
Provider-envelope, protocol-compatibility, implementation-incoherence, timeout,
transport, authentication, rate-limit and HTTP/provider-status cases all retain
analysis infrastructure classification. Diagnostic text is identical across the
different injected categories. No original failed generation creates a derived
family or recovery arm. All six source files remain byte-identical after extraction.

All existing 140 analysis cases remain passing; total analysis tests 150, complete
suite 824. No statistical, schema, collection, measurement, runtime, model,
environment, manifest or frozen-plan change was made for this correction.

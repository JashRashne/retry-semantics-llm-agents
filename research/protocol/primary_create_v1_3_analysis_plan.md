# Pre-Data Analysis Plan v1.0 — primary-create-v1.3

**Execution semantics inherited unchanged from primary-create-v1.2.**

## Governance status

This document is the pre-data paper-analysis plan for paper experiment revision
`primary-create-v1.3` at execution checkpoint
`86e141441c24f32a0c05c597796054bbd5691c02`.

`primary-create-v1.2` is the frozen execution-semantics revision.
`primary-create-v1.3` is the paper experiment revision that inherits those V1.2
execution semantics unchanged and adds or fixes only the prospective paper
analysis and sample-size governance provisions in Analysis Plan v1.0. Where the
V1.2 protocol deferred paper-run sample size or described hidden-world analyses
as descriptive, the V1.3 paper experiment revision replaces those analysis
provisions. This version change obeys the existing protocol-change rule and
INV-13; it is not an exception to either.

There are no Replay, Regeneration, hidden-world, eligibility, prompt, budget,
scheduling, tool, environment, or recovery execution-semantic changes between
V1.2 and V1.3. The change from V1.2 to V1.3 is analysis and sample-size
governance only. The existing frozen 16-slot engineering-validation machinery
remains an engineering validation of the inherited V1.2 execution semantics.
The eventual paper manifest must identify the paper experiment revision as
`primary-create-v1.3`.

No live engineering-validation outcomes and no live paper experimental outcomes
had been observed when Analysis Plan v1.0 and paper experiment revision
`primary-create-v1.3` were frozen. Engineering, smoke, debug, and preflight
traces remain outside paper-result denominators.

This file is in `research/protocol/` because that existing directory contains
the execution protocol, protocol invariants, and trace schema. The repository
has no `docs/` hierarchy.

## 1. Research question

After an ambiguous outcome from a state-mutating LLM tool call, compare:

- **Exact Replay:** redispatch the exact already-generated request.
- **LLM Regeneration:** return the ambiguous outcome to the LLM and permit
  subsequent model-generated actions under the frozen bounded protocol.

Analyze the policies separately under:

- `H0 = NOT_EXECUTED`
- `H1 = EXECUTED_ACK_LOST`

The study does not seek a universal winner. It estimates policy performance in
each hidden world and how the policy contrast changes between worlds.

## 2. Experimental unit and dependence

An **eligible trial family** is the primary clustering and experimental unit.
Each eligible family constructs four linked policy-arm outcomes:

1. H0 Replay;
2. H0 Regeneration;
3. H1 Replay; and
4. H1 Regeneration.

Within each hidden world, an eligible family contributes one matched
Replay-Regeneration policy pair. Individual arms are never independent
observations. Within-world calculations preserve policy pairing, and interaction
resampling preserves the complete family.

## 3. Populations and analysis sets

Keep these populations distinct:

- **Scheduled population:** every original-generation attempt slot in the frozen
  paper manifest, including eligible, behaviorally ineligible, and
  infrastructure-failed attempts.
- **Eligible recovery population:** scheduled attempts whose original generation
  satisfies the frozen eligibility rule and therefore activates a trial family.
  Recovery-policy performance is conditional on original-generation
  eligibility.
- **Engineering population:** engineering-validation, smoke, debug, and preflight
  attempts and traces. These never enter paper-result denominators.

Define the arm-level analysis flag exactly as follows:

```text
BEHAVIORALLY_EVALUABLE_ARM = 1
```

if and only if:

- execution produced sufficient authoritative arm evidence to derive the
  terminal ground-truth environment state for that arm; and
- no infrastructure failure prevents arm-level attribution or evaluation.

`REJECTED_GENERATION`, `MALFORMED_GENERATION`, and `BUDGET_EXHAUSTED` remain
behavioral evidence and remain behaviorally evaluable when the authoritative
terminal state exists. They are not exclusions merely because the behavior was
invalid. If an infrastructure failure prevents authoritative arm-level terminal
state attribution, set `BEHAVIORALLY_EVALUABLE_ARM=0` for the primary behavioral
comparison.

For a hidden world's primary behavioral comparison, include an eligible
family/world matched pair only when both policy arms have
`BEHAVIORALLY_EVALUABLE_ARM=1`. Do not count an infrastructure failure as a
behavioral failure in the primary analysis. The interaction primary estimate
uses complete eligible families for which all four arms have
`BEHAVIORALLY_EVALUABLE_ARM=1`.

## 4. Derived primary outcome: STATE_CORRECT

`STATE_CORRECT` is a new derived paper-analysis variable in `{0,1}`. It is not a
renaming or redefinition of the existing runtime/evaluator field `correct`.
Runtime `correct`, when present, retains its frozen V1.2 semantics.

The later paper-analysis extractor must derive `STATE_CORRECT` separately from
ground-truth environment state according to the prespecified CREATE invariant:

```text
STATE_CORRECT = 1
iff
matching_ticket_count = 1
and
unintended_ticket_count = 0
```

The intended ticket must exactly match the required `customer_id`, `title`, and
`description`. For the controlled append-only ticket environment, this terminal
state also means recovery introduced no unintended state-mutating side effect.
Infrastructure status does not enter the state-only definition; it instead
determines primary-analysis evaluability and the sensitivity scoring described
below.

For H0, the initial intended-ticket count is zero:

```text
0 -> 1   correct
0 -> 0   missing mutation
0 -> 2+  duplicate/over-mutation
```

For H1, the initial intended-ticket count is one:

```text
1 -> 1   correct
1 -> 2+  duplicate mutation
```

An unintended ticket makes `STATE_CORRECT=0`. A read-only inspection such as
`list_tickets` does not itself affect `STATE_CORRECT`.

## 5. Primary estimands and sign convention

Use the sign convention inherited from V1.2. Positive values favor Replay;
negative values favor Regeneration:

```text
Delta_H0 =
    P(STATE_CORRECT | Replay, H0)
  - P(STATE_CORRECT | Regeneration, H0)

Delta_H1 =
    P(STATE_CORRECT | Replay, H1)
  - P(STATE_CORRECT | Regeneration, H1)
```

Do not use a pooled H0/H1 policy accuracy as a primary estimand. The
experimental 50/50 H0/H1 balance is not an estimate of real-world hidden-world
prevalence.

The interaction is:

```text
Delta_H1 - Delta_H0
```

For each complete family, its interaction contribution is:

```text
[STATE_CORRECT(H1, Replay) - STATE_CORRECT(H1, Regeneration)]
-
[STATE_CORRECT(H0, Replay) - STATE_CORRECT(H0, Regeneration)]
```

The interaction estimate is the mean of those family contributions.

## 6. Primary paired summaries, intervals, and tests

For H0 and H1 separately, report the paired table:

```text
n11: Replay correct,   Regeneration correct
n10: Replay correct,   Regeneration incorrect
n01: Replay incorrect, Regeneration correct
n00: Replay incorrect, Regeneration incorrect
N = n11 + n10 + n01 + n00
```

Report:

- Replay correctness rate;
- Regeneration correctness rate;
- paired percentage-point risk difference `(n10 - n01) / N`;
- 95% Newcombe paired-proportion score confidence interval, Newcombe (1998),
  method 10;
- `n10` and `n01`; and
- the two-sided exact conditional McNemar test.

Do not bootstrap the individual H0 or H1 risk-difference confidence intervals.

For `m = n10 + n01 > 0`, compute the exact two-sided McNemar p-value as:

```text
X ~ Binomial(m, 0.5)
p = min(1, 2 * P[X <= min(n10, n01)])
```

If `N=0`, report the hidden-world comparison, interval, and test as not
estimable. If `N>0` and `n10=n01=0`, retain the comparison and report:

```text
paired risk difference = 0
n10 = 0
n01 = 0
exact McNemar p = 1.0
```

Compute the prespecified Newcombe method 10 confidence interval even when both
discordant counts are zero.

### Co-primary multiplicity family

The primary Holm family contains exactly two tests:

1. ticket environment × primary model × H0 Replay versus Regeneration;
2. ticket environment × primary model × H1 Replay versus Regeneration.

Family-wise alpha is 0.05. Apply the standard two-test Holm step-down procedure
to the two raw McNemar p-values and report both raw and Holm-adjusted p-values.
Equivalently, order the raw values `p(1) <= p(2)`, compare `p(1)` with 0.025,
and compare `p(2)` with 0.05 only if the first null is rejected. Adjusted values
are `min(1, 2*p(1))` for the smaller raw p-value and
`max(min(1, 2*p(1)), p(2))` for the larger raw p-value, mapped back to H0/H1.

If either co-primary comparison has `N=0`, the two-test confirmatory Holm family
is not fully estimable. Make no co-primary rejection claim, do not reduce the
multiplicity family to the remaining test, and label any available raw
hidden-world result descriptive.

External environments and any later secondary model are replication or
generalization analyses. They are not added to this primary Holm family. Any
future inferential testing plan for them requires a separate amendment frozen
before their outcomes are observed.

Effect sizes, confidence intervals, paired counts, and denominators take
precedence in interpretation over binary reject/non-reject declarations.

## 7. Interaction confidence interval

The family-level bootstrap applies only to `Delta_H1 - Delta_H0`:

- resample whole complete eligible families with replacement;
- use 10,000 bootstrap samples;
- use seed `20260916`; and
- report a 95% percentile confidence interval.

For reproducibility, the later extractor must use one local Python
`random.Random(20260916)` instance. For each bootstrap sample, draw `N` family
indexes through `randrange(N)`, compute the mean family interaction, and repeat
10,000 times. Sort the 10,000 estimates and use the 250th and 9,750th order
statistics (one-based) as the 2.5th and 97.5th percentile endpoints. If there
are no complete families, report the interaction and interval as not estimable.

Never resample individual arms or independently resample the two hidden-world
pairs.

## 8. Sample size and fixed stopping rule

The pre-data planning assumptions are:

```text
minimum meaningful absolute paired difference = 0.20
power = 0.80
planning alpha = 0.025, two-sided
planning total discordance q = 0.40
required eligible families ~= 98
```

Exact conditional McNemar planning gives this sensitivity table:

| Total discordance `q` | Required eligible families |
| ---: | ---: |
| 0.30 | 73 |
| 0.35 | 85 |
| 0.40 | 98 |
| 0.50 | 123 |

The primary controlled ticket allocation is fixed pre-data at:

```text
160 scheduled family opportunities/original-generation attempts
8 scenarios x 20 replicates per scenario
planned eligible-family target ~= 98
98 / 160 = 61.25% eligibility
```

This sample-size decision is frozen pre-data as part of paper experiment
revision V1.3 and replaces V1.2's earlier deferral of the paper-run sample size.
It does not alter the 16-slot engineering-validation machinery or any execution
semantics.

Execute the eventual frozen paper manifest's 160 scheduled attempts exactly
once. Never extend the run to obtain 98 eligible families. If fewer than 98 are
eligible, analyze all eligible families, report the shortfall, and add no
replacement trials. If more than 98 are eligible, analyze all eligible families
and discard none.

There is no:

- significance-based early stopping;
- extension until statistical significance;
- extension until an eligibility target is met;
- replacement of ineligible generations;
- replacement of infrastructure failures;
- resampling after failures; or
- post-hoc scenario addition because results appear weak.

## 9. Infrastructure handling

Infrastructure failures include provider, network, and transport failures such
as timeouts, HTTP 429 responses, HTTP 5xx responses, and connection failures.
Retain them as evidence, never silently retry them, never replace them, and
report them separately.

### Primary behavioral population

For each hidden world, use eligible-family matched policy pairs for which both
policy arms have `BEHAVIORALLY_EVALUABLE_ARM=1` under Section 3. If either arm
has `BEHAVIORALLY_EVALUABLE_ARM=0`, exclude that pair from the primary behavioral
comparison. Do not silently score infrastructure as behavioral failure in the
primary analysis.

For the primary interaction, require all four arms to have
`BEHAVIORALLY_EVALUABLE_ARM=1`.

### Prespecified infrastructure sensitivity

For an otherwise eligible family with a failure attributable to a specific
policy arm, score the affected arm as `STATE_CORRECT=0` in the sensitivity
analysis. The other arm retains its separately derived state-only
`STATE_CORRECT`. If both arms have arm-level infrastructure failures, score both
as zero.

A runner, family-construction, or system failure that occurs before a specific
policy-arm outcome can exist must not be attributed to either policy. Report it
separately as system/family-construction infrastructure evidence; do not invent
policy outcomes for it. Interaction sensitivity estimates require an outcome or
arm-attributable infrastructure score for all four arms.

Recompute both paired contrasts, exact McNemar tests, and the two-test Holm
procedure under the sensitivity scores. Call the primary interpretation
**operationally fragile** if this sensitivity analysis either:

- reverses the sign of `Delta_H0` or `Delta_H1` relative to the primary estimate
  (a strict change from positive to negative or negative to positive); or
- changes the Holm-adjusted reject/non-reject decision for either co-primary
  comparison.

Report the primary and sensitivity results together.

## 10. Failure indicators

Preserve these non-mutually-exclusive recovery-arm indicators:

- `MISSING_MUTATION = 1` iff `matching_ticket_count = 0`.
- `DUPLICATE_MUTATION = 1` iff `matching_ticket_count > 1`.
- `WRONG_MUTATION = 1` iff `unintended_ticket_count > 0`.
- `BUDGET_EXHAUSTED = 1` iff the frozen recovery path terminates as
  `action_budget_exceeded`.
- `REJECTED_GENERATION = 1` only for the existing frozen behavioral
  rejected-generation path.
- `MALFORMED_GENERATION = 1` when a provider/model generation was returned, but
  the frozen adapter/parser/model boundary cannot parse or validate the required
  model-generated action/tool-call structure or arguments.

Do not classify failures through heuristic text matching. In particular, do not
reinterpret rejected-generation evidence that resembles malformed syntax as a
malformed generation. Exact trace-event mappings for `MALFORMED_GENERATION` and
`REJECTED_GENERATION` remain an implementation requirement and must be frozen
and tested before paper data collection.

Rejected, malformed, and otherwise invalid model-generated actions are
behavioral evidence rather than infrastructure exclusions. Do not silently
retry, repair, resample, or remove them from the behavioral analysis.

## 11. PROTOCOL_VALID_RECOVERY

`PROTOCOL_VALID_RECOVERY` is a derived paper-analysis variable distinct from
`STATE_CORRECT`.

Define it separately by policy.

### Exact Replay

Set `PROTOCOL_VALID_RECOVERY=1` if and only if the frozen exact-replay operation
follows the frozen protocol and terminates without an infrastructure failure or
replay-executor protocol failure. There is no post-ambiguity model generation in
Exact Replay. Therefore `MALFORMED_GENERATION`, `REJECTED_GENERATION`, and
`BUDGET_EXHAUSTED` are normally Regeneration-side concepts and must not be
fabricated for Replay.

### LLM Regeneration

Set `PROTOCOL_VALID_RECOVERY=1` if and only if the recovery arm proceeds through
parseable, schema-valid, protocol-permitted model/tool actions and terminates
without any of:

- `MALFORMED_GENERATION`;
- `REJECTED_GENERATION`;
- `BUDGET_EXHAUSTED`; or
- infrastructure failure.

Otherwise set it to zero for that policy. Both policies may have
`PROTOCOL_VALID_RECOVERY=1` while `STATE_CORRECT=0`; a structurally and
procedurally valid recovery can still make a semantically wrong decision. A
protocol-permitted Regeneration model stop without a tool call can be protocol
valid even when its resulting state is incorrect. Report
`PROTOCOL_VALID_RECOVERY` separately from state correctness.

Exact trace-event mappings for this variable must be frozen and tested before
paper data collection; the analysis extractor must not infer validity from free
text.

For a `PROTOCOL_VALID_RECOVERY` rate, the denominator is all eligible arm
opportunities in the relevant policy × hidden-world population for which either
a recovery-arm outcome or an arm-attributable infrastructure outcome exists.
Score an arm-attributable infrastructure outcome zero. A pre-arm system or
family-construction failure has no protocol-validity value and is reported
separately rather than assigned to a policy.

## 12. Recovery-cost variables

Use only these exact counters:

- `model_calls_issued`: number of post-ambiguity model requests actually issued.
- `read_only_tool_calls_executed`: number of post-ambiguity read-only tool
  invocations actually executed.
- `state_mutating_tool_calls_executed`: number of post-ambiguity state-mutating
  tool invocations actually executed.
- `recovery_tool_calls_executed = read_only_tool_calls_executed +
  state_mutating_tool_calls_executed`.

A rejected or malformed generation that causes no tool execution may count as a
model call but must not count as an executed tool call. Do not report an
ambiguous generic action count and do not construct an arbitrary weighted
composite score.

These counters apply to both policies. For a successful Exact Replay dispatch
that reaches tool execution, record:

```text
model_calls_issued = 0
read_only_tool_calls_executed = 0
state_mutating_tool_calls_executed = 1
recovery_tool_calls_executed = 1
```

If Exact Replay does not reach tool execution because of infrastructure failure,
do not fabricate an executed tool call. For Regeneration, count only actual
post-ambiguity model requests and actual executed tool invocations.

Also report budget-exhaustion rate using the denominator in Section 14.

## 13. OBSERVATION_BEFORE_WRITE

Define `OBSERVATION_BEFORE_WRITE` only for Regeneration arms:

```text
OBSERVATION_BEFORE_WRITE = 1
```

if and only if at least one read-only recovery tool invocation executes before
the first executed state-mutating recovery tool invocation. An arm that executes
one or more reads and then terminates without ever executing a mutation also
receives value one. If no recovery read executes before mutation or termination,
the value is zero.

The denominator is Regeneration arms with `BEHAVIORALLY_EVALUABLE_ARM=1` under
Section 3. Always report its numerator and denominator.

## 14. Frozen denominators

Always report numerator and denominator with every rate.

- **Behavioral failure-mode rate:** denominator is arms with
  `BEHAVIORALLY_EVALUABLE_ARM=1` in the relevant policy × hidden-world
  population.
- **Recovery infrastructure-failure rate:** denominator is all eligible arm
  opportunities in the relevant policy × hidden-world population. The numerator
  includes only failures attributable to that policy arm. Pre-arm system or
  family-construction failures remain separately reported and are not assigned
  to a policy numerator.
- **Original-generation infrastructure-failure rate:** denominator is all
  scheduled original-generation attempts.
- **Eligibility rate:** eligible original generations divided by all scheduled
  original-generation attempts. Original-generation infrastructure failures
  remain in the denominator and not in the eligible numerator.

For all primary paired tables, additionally report the number of matched pairs
for which both arms have `BEHAVIORALLY_EVALUABLE_ARM=1`. For the interaction,
report the number of complete families for which all four arms have
`BEHAVIORALLY_EVALUABLE_ARM=1`.

## 15. External replications

The pre-data allocations are:

| Environment | Scheduled families | Role |
| --- | ---: | --- |
| Ticket | 160 | Primary controlled experiment |
| GitHub | 64 | Secondary replication |
| Stripe | 64 | Secondary replication |
| Google Sheets | 64 | Secondary replication |

The 64-family external allocations are fixed descriptive/generalization
replication allocations, not separately powered co-primary experiments. Freeze
each external environment's scenario catalogue, exact manifest, state evaluator,
and any inferential amendment before observing external paper outcomes.

## 16. Engineering gate

Engineering validation remains separate, and its traces never enter
paper-result denominators. Observed engineering Replay or Regeneration behavior
must not be used to alter hypotheses, outcome definitions, primary tests, sample
size, prompts, or recovery semantics. Engineering evidence may justify fixing
an implementation defect only, subject to the existing protocol change and
revalidation rules.

## 17. Exploratory analyses

Anything not prespecified here as primary or secondary is exploratory. Examples
include scenario-specific effects, read-before-write associations,
tool-sequence motifs, model-specific behavior, and prompt-wording effects.

## 18. Optional equal-world summary

An optional descriptive metric is:

```text
EqualWorldRobustness(policy) =
    0.5 * correctness(policy, H0 on H0 matched population)
  + 0.5 * correctness(policy, H1 on H1 matched population)
```

For each hidden world, compute both policies' correctness using exactly the same
matched eligible-family population used for that hidden world's primary
comparison: both arms must have `BEHAVIORALLY_EVALUABLE_ARM=1`. Do not use
unmatched policy-specific denominators. If either hidden-world primary matched
population has `N=0`, `EqualWorldRobustness` is not estimable. Otherwise,
`correctness` means the mean derived `STATE_CORRECT` for the stated policy on
that matched population. Label this an **equal-world experimental summary**. It
is not an estimate of real-world correctness because real H0/H1 prevalence is
unknown.

## 19. Falsification, weakening, and fragility

The central empirical case is materially weakened under the prespecified
minimum-meaningful-effect rule only if, for **both** H0 and H1:

```text
lower 95% CI bound > -0.20
and
upper 95% CI bound < +0.20
```

That is, both 95% Newcombe method 10 confidence intervals for the paired risk
differences must lie strictly inside `(-0.20, +0.20)`. Under this prespecified
rule, effects with absolute magnitude at least 0.20 are excluded by those
intervals.

Use the operational-fragility rule in Section 9 for infrastructure sensitivity.
Also report transparently whether apparent differences are concentrated in
eligibility selection, rejected-generation artifacts, one scenario, or one
environment; these are descriptive robustness considerations, not additional
unfrozen hypothesis tests.

## 20. Reporting template

For the primary model in the ticket environment, report:

- H0 `STATE_CORRECT` by policy;
- H1 `STATE_CORRECT` by policy;
- paired differences and 95% Newcombe method 10 confidence intervals;
- exact McNemar tests and Holm-adjusted p-values;
- interaction and family-bootstrap confidence interval;
- scheduled attempt N, eligible-family N, evaluable-pair N by world, and complete
  interaction-family N, applying the Section 3 `BEHAVIORALLY_EVALUABLE_ARM`
  definition;
- eligibility numerator, denominator, and rate;
- all failure-mode counts and rates with denominators;
- original and recovery infrastructure counts and rates with denominators;
- `PROTOCOL_VALID_RECOVERY` counts and rates;
- the `OBSERVATION_BEFORE_WRITE` numerator and denominator; and
- all four exact recovery-cost counters.

Report the prespecified infrastructure sensitivity beside the primary results.
Report external replications separately and label them descriptive/generalization
analyses unless a separate pre-outcome inferential amendment exists.

## 21. Pre-collection measurability requirements

The controlled-ticket arm trace already retains authoritative final state,
intended effect, matching and unintended ticket counts, family/pair/policy/world
identifiers, ordered recovery actions, execution flags, mutation flags, model
call counts, termination, and broad failure evidence. Therefore
`STATE_CORRECT`, paired tables, Regeneration executed-call counters, and
`OBSERVATION_BEFORE_WRITE` are derivable for complete arm traces that exist.
The limitations below still prevent reliable paper-population reconstruction
and some failure-path derivations.

The following are **not yet reliably measurable for the paper study** from the
frozen trace schema and code. They are implementation requirements that must be
completed, frozen, and tested before paper data collection, but are not
implemented by this analysis plan:

1. **Scheduled paper population, revision identity, and ledger:** there is no
   frozen 160-slot paper manifest, paper-stage label, schematized
   scheduled-attempt ledger, or paper persistence path. The existing
   scheduled-attempt ledger is engineering-only, and the current schema/code
   identify the inherited execution revision as V1.2 rather than providing the
   required V1.3 paper-experiment provenance
   (`trace_schema_v1.json:21-23`). The eventual paper manifest and paper evidence
   must identify `primary-create-v1.3` without changing inherited execution
   semantics.
2. **Eligibility reporting:** paper-run eligibility numerator, eligibility rate,
   and auditable linkage from every scheduled attempt to its outcome are absent.
3. **Ineligibility reasons:** original-generation behavioral ineligibility exists
   in the engineering ledger but not in a frozen paper-ledger schema.
4. **Original-generation infrastructure evidence:** the engineering ledger has
   partial evidence, but no frozen paper-ledger representation guarantees the
   required denominator and failure record.
5. **Exact `MALFORMED_GENERATION` mapping:** current recovery handling collapses
   several invalid-action cases. A first-class, non-heuristic mapping from frozen
   events/evidence to this indicator must be specified and tested.
6. **Exact `BEHAVIORALLY_EVALUABLE_ARM` mapping:** the frozen runtime field
   `valid_for_behavioral_analysis` is false for every recorded infrastructure
   failure (`ticket.py:536-580`), while Section 3 asks whether infrastructure
   specifically prevents authoritative arm-level attribution or evaluation.
   Current pair-level failure propagation and missing pre-arm traces do not
   reliably encode that distinction. A first-class mapping must be frozen and
   tested.
7. **Exact `PROTOCOL_VALID_RECOVERY` mapping:** the trace preserves much of the
   needed evidence, but no frozen derived-variable mapper currently implements
   the policy-specific rule in Section 11, including Replay-executor protocol
   failure.
8. **Exact Replay failure-path recovery cost:** `ExactReplayResult` represents a
   successful dispatch and fixes its executed-tool count at one
   (`runtime/exact_replay.py:43-61`); the frozen schema likewise requires one
   executed Replay tool call even when its termination enum permits
   infrastructure failure (`trace_schema_v1.json:125-173`). An infrastructure
   failure before tool execution may leave no arm result. The paper evidence
   must distinguish no execution from successful execution without fabricating
   a tool call.
9. **Arm-level infrastructure attribution:** current pair-level propagation can
   mark both evaluations invalid when one arm fails. The sensitivity extractor
   needs a tested way to distinguish the affected arm from its paired arm
   (`experiment/trace.py:318-345`).
10. **Structured infrastructure subtype:** recovery traces do not guarantee
   structured timeout, 429, 5xx, and connection-failure categories.
11. **Infrastructure before an arm trace exists:** runner, family-construction,
   clone, Replay executor, and some protocol failures can occur before a complete
   arm trace is serializable. A scheduled-attempt/system evidence record is
   required without fabricating policy attribution.
12. **External-environment state evaluators:** the frozen schema and evaluator
    are ticket-specific and cannot derive authoritative GitHub, Stripe, or Google
    Sheets correctness.
13. **Primary paper model identity:** the eventual paper manifest must freeze one
    primary model before paper outcomes are observed so the exact two-test Holm
    family is identifiable.

No paper data may be collected until these measurement requirements and the
eventual V1.3 paper manifest are prospectively frozen and validated.
Implementing them must not change the execution semantics inherited unchanged
from `primary-create-v1.2` or the existing 16-slot engineering-validation
machinery.

## Checkpoint audit after v1.0 revision

Audit basis at checkpoint `86e141441c24f32a0c05c597796054bbd5691c02`:

- `research/protocol/primary_experiment_v1.md`
- `research/protocol/protocol_invariants_v1.md`
- `research/protocol/trace_schema_v1.json`
- `src/retry_semantics/environments/ticket.py`
- `src/retry_semantics/runtime/original_generation.py`
- `src/retry_semantics/runtime/exact_replay.py`
- `src/retry_semantics/runtime/regeneration.py`
- `src/retry_semantics/runtime/scheduled_trial.py`
- `src/retry_semantics/experiment/manifest.py`
- `src/retry_semantics/experiment/engineering.py`
- `src/retry_semantics/experiment/trace.py`

### Protocol reconciliation

The frozen protocol's Replay-minus-Regeneration sign is retained
(`primary_experiment_v1.md:1273-1278,1293-1295`). Its deferred sample size,
descriptive hidden-world tests, individual-effect bootstrap CI, and secondary
interaction analysis provisions (`primary_experiment_v1.md:1203-1208,
1239-1259,1261-1302`) are replaced for the paper experiment by the prospective
V1.3 analysis provisions in this plan. Execution provisions are inherited
unchanged from V1.2.

The protocol change rule and INV-13 require a new experiment version when the
primary analysis changes (`primary_experiment_v1.md:1338-1345`;
`protocol_invariants_v1.md:213-226`). This plan obeys that requirement:
`primary-create-v1.2` remains the frozen execution-semantics revision, while
`primary-create-v1.3` is the paper experiment revision with the new prospective
analysis and sample-size governance. There is no exception-by-fiat and no
executable or trace-schema meaning changes.

`STATE_CORRECT` is deliberately derived from stored state rather than changing
runtime `correct`, whose existing semantics also require no infrastructure
failure (`ticket.py:536-580`; `trace_schema_v1.json:1420-1493`). This removes the
prior outcome-name conflict without modifying the evaluator.

The eligible family is the clustering unit, while its within-world policy arms
form the matched pair, consistent with the execution hierarchy
(`primary_experiment_v1.md:157-196`). Engineering/paper separation remains
consistent with `primary_experiment_v1.md:1138-1237` and the engineering
manifest's `manifest_kind` (`experiment/manifest.py:452-466`).

No unresolved direct contradiction remains after assigning the new paper
analysis provisions to paper experiment revision V1.3 as INV-13 requires. The
missing measurement support listed in Section 21 is an implementation gap, not
authorization to change execution semantics.

### Computation-rule audit

Analysis Plan v1.0 fixes the previously ambiguous effect sign, clustering and
pairing units, state-only outcome, within-world CI, zero-discordance handling,
McNemar calculation, Holm family, interaction bootstrap unit/seed/order
statistics, primary infrastructure population, infrastructure sensitivity,
executed-call counters, observation-before-write predicate, protocol-validity
predicate, failure definitions, fragility criteria, and rate denominators.

No remaining ambiguous paper-analysis computation rule was identified for the
controlled ticket primary analysis. The extractor's exact trace-event mappings,
including `BEHAVIORALLY_EVALUABLE_ARM` and policy-specific
`PROTOCOL_VALID_RECOVERY`, and the unavailable paper-population evidence are
explicitly pre-collection implementation requirements rather than analyst
discretion.

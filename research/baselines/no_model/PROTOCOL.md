# Post-feedback no-model baseline: prospective specification V1

Date: 4 October 2026, Asia/Kolkata. Policy: `DETERMINISTIC_READ_BEFORE_CREATE`.
Status: implementation prepared for hostile **pre-collection** audit; no baseline
observations collected. This specification fixes the policy before collection.
The audited protocol, source bindings, fresh manifests, code hashes, transport
configuration, and isolation receipts must be frozen before any collection.
This pass provides no live launch command or collection authorization.

This is a new post-feedback evaluation requested after the paper's original
results were observed. It was **not part of the original prespecified Study 1A
analysis**, and must never be called preregistered or added retroactively to its
two-policy confirmatory analysis. Original observations, failed/unknown arms,
statistics, protocols, and manuscript remain frozen. Scope is tickets, GitHub,
and the valid separate Sheets replication only.

## 1. Fixed policy and action budget

```text
observation = LIST_ONCE()
if observation is unusable:
    record observation failure; STOP
if any returned visible record exactly matches the intended effect:
    STOP
CREATE_STORED_ORIGINAL_ONCE()
STOP
```

Exactly one logical decision LIST is attempted per entered policy evaluation;
zero or one recovery mutation dispatches; zero model calls. There is no loop,
second decision LIST, confirmation read, replacement request, semantic
regeneration, idempotency-key addition, retry, or exception-specific substitute
policy. Multiple visible intended effects still cause STOP; their final state
can be incorrect. An unintended visible effect does not replace the required
presence predicate. READ/WRITE counts count attempted capabilities, not remote
commits. Constructors, readiness reads, and evaluator reads are separate.

GitHub LIST is one bounded traversal, potentially up to 16 HTTP GETs, exactly
like Regeneration's `list_issues`. It is **not** necessarily one HTTP request.
The traversal retains the existing 540-second limit, pagination/PR handling,
raw Accept header and pinned API version. Sheets LIST is one bounded selected
grid GET. Ticket LIST is one executor dispatch. Report both logical read/write
counts and physical HTTP counts, without equating them.

## 2. Information boundary

Allowed: original task, eligible stored original mutation, literal intended
semantic fields from that mutation, and the same relevant model-visible tool
projection used by Regeneration. Those inputs determine a fixed predicate.
The core receives a `Target`, original bytes/hash, and two capabilities only.
It receives no family/arm manifest, trial identifier, credential, or provider
request envelope. Adapters may bind scope/attribution to execute the original,
but only projected semantic records enter the decision.

Forbidden during decision: H0/H1 or outcome construction metadata; authoritative
snapshots/journals; evaluator counts/verdicts; constructor census or ACK; known
original resource IDs; subsequent confirmations; raw provider IDs/markers;
any model/client callback. The harness may retain such evidence to construct
worlds, establish validity, and score **after** recovery returns. No final
evaluator is called to supply LIST. Provider LIST/transport functions must be
bound to the frozen observation target, with no hidden retries or token refresh
that redispatches a mutation.

Regeneration's system instruction is "You are a tool-using assistant. Complete
the user's task using the available tools." Its ambiguity is "ToolError: The
previous request timed out. Its outcome is unknown." Inspection found no
special additional duplicate-warning instruction. The deterministic rule
represents that uncertainty operationally; it does not interpret prose.

## 3. Exact presence predicates (fixed before data)

| Environment | Permitted observation | Exact presence test |
| --- | --- | --- |
| Ticket | `{"tickets":[{"customer_id":str,"title":str,"description":str},...]}` from `TicketEnvironment.execute_request(list_tickets)` | An entry equals stored original `(customer_id,title,description)` character for character. |
| GitHub | `{"issues":[{"title":str,"body":str},...]}` after existing bounded raw census and arm suffix filtering | An entry equals stored semantic `(title,body)` character for character. IDs/PRs are excluded; suffixes are stripped; entries sorted as in Regeneration. Only a complete traversal produces a usable projection. |
| Sheets | `{"rows":[{"item":str,"detail":str},...],"read_complete":true}` from `check_grid` and `project_list_rows` | An entry equals stored semantic `(item,detail)` character for character. Marker/scope/coordinates stripped, row order retained. `check_grid` is called **without** `intended`, so evaluator matching fields do not drive the decision. |

No trimming, case folding, Unicode normalization, fuzzy/semantic equivalence,
provider search shortcut, resource-ID fetch, or extra count oracle. Valid empty
collections mean absent. Errors, malformed projections, partial traversals,
and unexpected richer fields are unusable, not empty.

## 4. Error and final-state rules

LIST transport/tool/schema error: set `intended_visible=null`, `decision=STOP`,
observation-failure reason, zero writes. Never infer absence from failed LIST.
CREATE transport error, malformed ACK, or visible provider failure: record
status/error/ACK validation, terminate after that attempt, and score eventual
state via the unchanged evaluator. HTTP success is never correctness; HTTP
failure/timeout is never proof of noncommit. Preserve all failed observations.
Exception text is not logged because it can contain secrets; exception types
are retained. Future durable transport evidence must retain raw status/bytes,
dispatch facts, targets, timing, and request identities without credentials.

Ticket: existing `evaluate_ticket_state` on an authoritative cloned environment,
with stored original semantic fields. Correct means exactly one matching ticket
and zero unintended tickets, with the existing validity rules. The harness
does not mark final state unknown solely because LIST/CREATE failed when the
logical state is authoritative. Infrastructure remains separately recorded.

GitHub: unchanged `run_scheduled_censuses`/`evaluate_census`, post-recovery OBS-1
starts +0/+600, deadlines +540/+1140. Preserve existing early termination on
positive defects. Original and recovery acknowledged IDs are harness-only
causal checks. Correct requires one exact attributed intended issue, no
unintended issue, qualified isolation/blank baseline and complete required
terminal census; duplicate/wrong/missing use existing classifications. Partial
counts are labelled lower bounds, never complete counts.

Sheets: unchanged OBS-1 **one** final selected-grid GET starting at +0 and
ending within +40 seconds; `classify_experimental_get`/`evaluate_observation`.
Exactly one intended marker row and zero attributable unintended rows is
correct. Missing/duplicate/unintended effects are failures when observable;
unexpected rows, malformed/incomplete grids and causal-ledger contradiction
stay inconclusive. Preserve the valid replication's causal floor from H1 ACK,
acknowledged recovery appends and earlier visible entered rows.

No extra evaluator rescue rounds. Raw empty Sheets responses that omit required
GridData remain incomplete under the frozen experimental observer. The later
**readiness-only omitted-empty rule must not be used for baseline LIST or
final scoring**. It may certify a blank tab before policy entry exactly as in
the valid replication, but never provide the policy's observation.

Unscorable construction/isolation/evaluator state produces `final_correctness=null`
with a reason. It is not imputed to success/failure or replaced. Pre-policy
construction/transport failures require a retained scheduled result with
`list_attempted=false`, logical read/write/model counts zero, validity reason,
and the original family/trial identity; do not enter the policy. Invalid shared
construction follows the existing family validity rule. Report entered-policy
state correctness separately from scheduled losses. Live provider prohibition
(401/403/429, retry-after/secondary limit) stops scheduling, permits no forbidden
rescue request, and retains remaining planned evaluations as unrun/unknown.

## 5. Frozen objects and sample

`sources.json` contains exact current paths and verified hashes, extracted from
the existing Pass A evidence registry. `protected_before.json` fingerprints
5,942 existing files, including tracked repository files, full controlled raw
bundles, the valid Sheets run, canonical external evidence, and sealed GitHub
archive. Old raw/derived data are read-only inputs. The repository's
`research/results/study2/study2_analysis_summary.json` is a **placeholder** and
is not an evidence source for this baseline comparison.

| Set | Originals/families | New baseline evaluations | Source |
| --- | ---: | ---: | --- |
| Study 1A | 160 | 320 (160 H0 + 160 H1) | A1–A7: original controlled run and locked analysis. |
| Study 1B | 160 | 320 (160 H0 + 160 H1) | B1–B7: separate V4.1 controlled replication. |
| GitHub Study 2 | 64 | 128 (64 H0 + 64 H1) | G1 archive, M1 manifest, E1/E9 canonical source mapping. Preserve original/continuation split, including family 20's M. |
| Valid Sheets replication | 64 | 128 (64 H0 + 64 H1) | S1–S3, E1/E9, and stored originals in the valid run's `collection/` tree. Exclude invalid primary and qualification controls. |

Total: 448 original families across four distinct sets, 896 planned baseline
evaluations. Both controlled sets are scientifically valid: same deterministic
ticket executor and state schema, eight templates ×20 replicates, each with
160 eligible stored originals. Report them separately; do not pool models.
Study 1A and 1B originals may have identical semantic task fields but distinct
stored tool-call bytes; retain each one's identity.

Use all scheduled original family identities, never select based on old success,
failure, unknown status, or baseline outcome. Old GitHub unknown Replay is not
a reason to discard that original from the new baseline. No replacement,
refill, eligibility model call or regenerated original. Order controlled
families by frozen slot, H0 then H1; providers by frozen scheduled family
index and their frozen `hidden_world_order`, one baseline per world. Serial
execution only. Freeze exact schedule and provider bindings before collection.

Ticket worlds must use the original initial empty state and the existing
`construct_trial_family_states` constructor: H0 original not dispatched, H1
exact stored original dispatched once. Clone post-ambiguity states. Never
initialize from either old policy's final state. Only fresh clones are written.

## 6. Original request preservation and fresh provider state

Ticket: reuse the exact canonical original request buffer/hash from
`arm_traces.jsonl.frozen_original`. `ticket_originals` verifies consistency
across the original four arms and initial snapshot identity, without recovery.

GitHub: use actual frozen W/M source bindings from G1 via E1/E9; verify every
stored semantic string against the frozen eligible original, not just task
templates. Keep the pinned **sandbox repository**
`JashRashne/retry-semantics-study2-github-sandbox` (not the code repository),
raw list path, API version `2022-11-28`, and suffix attribution scheme.
New namespace/128 markers, collision scan, writer exclusion, quota/page-cap
headroom and full blank arm baselines are mandatory. Never write an old marker
or update/delete an old issue. Additional issues change census size/timing;
fresh scope qualification is required under the unchanged 16-page cap.

The old runtime pins its manifest and `expected_original` demands membership
in its four original arms. New recovery uses the **same serializer and census**
with the old pinned repository authority and separately frozen fresh arm
bindings. H1 certification duplicates the old certification predicates using
the serializer instead of old-arm membership; it is harness-only, never a
provider-specific decision exception. Hostile audit must check this bridge.

Sheets: fresh private spreadsheet, new namespace/markers, 100×3 GRID tabs,
same principal/app/scope restrictions, no scripts/formulas/other writers.
Allocate 256 tabs to retain the existing topology qualification shape; designate
128 for the baseline's H0/H1 evaluations and leave 128 reserved/unused. Freeze
all topology bindings before writes. Preserve two literal semantic strings,
AppendCells API, stringValue storage, headers and field mask. Only spreadsheet,
sheet ID, tab title, and attribution marker change. H1 original gets one raw
ACK plus one strict constructor read, with the existing certification. Maintain
replication pacing (minimum 1.1 seconds/request), token headroom and stop rules.

External W necessarily changes scope/attribution from historical W. Bind new W
**once before construction**, durably store it, use that same stored W for H1
and the possible recovery mutation. Recovery never reserializes it. GitHub
persistence is exclusive and hash checked; Sheets reuses `store_original` /
`load_original` / `replay_request`. Use existing non-retrying one-shot transports
with durable raw request/result capture. A live orchestration/authorization
wrapper is deliberately not exposed in this first pass; provision/freeze and
audit it before running. One-arm runners accept qualified construction evidence.

## 7. Evidence record and readiness gate

Per entered evaluation retain study, original family/trial ID, harness-only
H0/H1, policy, LIST attempted/outcome/projected observation, visibility or null,
STOP/CREATE, write attempted/count/result status/error/ACK validity, request
hash, final evaluator evidence/verdict, matching/unintended counts, count
completeness, final correctness or null/reason, logical reads/writes, physical
reads by phase, and model count **0**. Persist new W and source M identity
alongside each record; retain construction validity separately. Unknown
states never turn into "absent." Existing raw transport evidence conventions
remain required for later live runs; projected JSON alone is insufficient.

Before collection freeze SHA-256 of this protocol, all new baseline source/test
files, sources, exact schedules/new provider manifests, zero-retry transports,
and original bindings. Obtain hostile audit of the actual frozen bytes and
fresh-resource readiness receipts. Use exclusively new output directories and
one-use run claim; no resume, overwrite, data-dependent amendment or refill.
An implementation correction discovered after collection preserves the prior
attempt and requires a separately identified prospective evaluation. No
collection may be launched from the offline checker (it has no run mode).

## 8. Descriptive reporting and inference

First report Study × situation × policy correct/scored/scheduled counts,
unknowns/reasons, construction losses, LIST failures, writes, model calls.
Proposed presentation only: `Study | execution situation | scheduled N |
Replay correct/scored | Regeneration correct/scored | no-model correct/scored`.
Baseline cells remain NOT_COLLECTED until frozen collection is complete.
GitHub H0 must preserve Replay 63/63 scored of 64 scheduled versus Regeneration
60/64; the historical paired-only 63-family row has a different denominator.
Do not silently label these marginal counts as a complete matched comparison.

The original V1.3 analysis specifies Replay minus Regeneration within-world
paired McNemar, paired Newcombe Method 10 intervals, Holm across exactly two
Study 1A tests, and whole-family interaction bootstrap. Those outputs stay
unchanged. There is no third-policy test in that plan. No baseline p-value,
interval, omnibus test, expanded Holm family or rewritten historical analysis
is authorized here. External replications retain descriptive roles.

After collection and hostile audit, any new inference needs a separately
specified exploratory analysis, explicit family linkage/evaluability and
multiplicity plan. Controlled states are reproducible and linkable by frozen
M; provider comparisons are historical task-family comparisons in fresh state
at a later date, not contemporaneous randomized paired treatments. Never
infer population equivalence or that an LLM is generally unnecessary from
this fixed catalogue. No scenario-cluster bootstrap or sample enlargement.

## 9. Fairness limitations and operator requirements

Same **decision observation strength** as Regeneration, contingent on the
audited adapter/transport bindings. Same original semantic fields were in
Regeneration's assistant history. The baseline additionally holds Replay's
executable W to dispatch exactly, an explicit authorized treatment difference;
its decision never uses envelope metadata. It avoids model serialization/drift
errors by design. It always spends a read, while Regeneration could spend up
to three actions/four model calls and could act after LIST failure. This is the
reviewer's fixed rule, not an equal-budget/model-quality ablation.

Provider marker filtering simplifies attribution for both policies. This does
not test reconciliation without markers. A complete provider projection is
not guaranteed by intention or a successful transport; strict completeness
checks/error outputs are shared. Fresh GitHub pagination load and Sheets blank
projection/visibility timing may differ from historical runs. No read-only
live inspection or readiness proof has been obtained during this pass.

Ticket collection needs no credential. Later GitHub operation needs sandbox
write/list access through `GITHUB_TOKEN` or `FINE_GRAIN_GITHUB_TOKEN` and pinned
API version. Sheets needs the existing installed OAuth-client JSON, same
app/principal scopes, approved fresh spreadsheet grant, sufficient bearer
lifetime and writer exclusion. No `FIREWORKS_API_KEY`, model capability test,
or model credential is needed for any baseline phase.

Budget per external provider: 64 H1 constructor writes plus at most 128
recovery writes = **192** mutation attempts (ideal complete/visible state:
128). Sheets additionally one spreadsheet provisioning POST and separately
audited synthetic qualification writes if required; never count controls as
baseline evaluations. GitHub pre-baseline 128 traversals + H1 constructor at
most128 + decision128 + final at most256 = **640 traversals**, at most10,240
page GETs. Sheets pre-baseline128 + H1 constructor64 + decision128 + final128
= **448 grid GETs**, plus metadata/access/qualification setup. Decision reads
alone are128 traversals/GETs per provider. Controlled sets total640 decision
reads,320 original H1 writes and at most640 recovery writes, all local.

These are attempt caps/planning figures, not measured results. Provider-stop
and construction failures can reduce actual counts. Collection remains
withheld pending protocol/code freeze, hostile audit and fresh-state readiness.

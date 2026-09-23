# Study 2 cross-provider protocol and feasibility contract V1

**FROZEN CROSS-PROVIDER PROTOCOL — INDEPENDENT HOSTILE AUDIT PASSED**

**STUDY-2 PAPER OBSERVATIONS = 0**

**COLLECTION BLOCKED; this freeze is not a collection authorization**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## 1. Authority, scope, and source status

Study 1 is immutable. `primary_experiment_v1.md` (including its V1.2 execution
clarifications), `protocol_invariants_v1.md`, and
`primary_create_v1_3_analysis_plan.md` control the common question, paired
design, treatments, state-only outcome, estimands, eligibility, and analysis
sets. The Study-1 ticket snapshot implementation is not an external-provider
API requirement. `STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` controls the global
collection gate and substitutes selected Provider C, Razorpay, for the historical
Stripe slot without changing Study 1 or its frozen provenance.

The frozen Razorpay contract and the hostile-audited GitHub and Sheets
provider-contract drafts control their respective endpoint meaning, request
identity, observable effects, and evidence limits as prospective inputs. The
GitHub and Sheets contracts still require final freeze against this protocol.
This document binds shared execution and comparison semantics; it cannot silently
rewrite a provider fact or promote an engineering result to paper evidence.
Where implementations differ, the common object is a *projected logical state*
with a closed attribution record, not identical external bytes or equal
observer strength. Any conflict with a frozen provider contract is a pre-data
blocker requiring explicit prospective resolution and hostile audit.

Authority inventory for the audited OBS-1 and projected-state decision:

| Provider | Controlling or relevant record | Paper-contract status |
| --- | --- | --- |
| GitHub | `github/GITHUB_PAPER_SEMANTICS_CONTRACT.md` passed hostile audit as a **prospective draft input**. Earlier semantics and adapter drafts remain engineering records, including delayed LIST visibility. | Paper issue mutation, correlation, 1–16-request complete census and exact-state routes are defined. Mechanical provider-contract reconciliation/freeze against this now-frozen projection and OBS-1 remains; paper implementation/evaluator/readiness remain blocked. |
| Google Sheets | `sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md` passed hostile audit as a **prospective draft input**. Frozen reconnaissance, engineering/live-go records and `GOOGLE_SHEETS_ENGINEERING_QUALIFICATION_LOCK.md` retain the closed one-CREATE/one-GET qualification. | Paper AppendCells row, arm marker, one-GET complete `A1:C100` read and exact-state routes are defined. Mechanical provider-contract reconciliation/freeze against this now-frozen projection and OBS-1 remains; a separate paper fixture/implementation/evaluator/readiness remain blocked. |
| Razorpay | `razorpay/RAZORPAY_PROVIDER_C_SELECTION_LOCK.md`, Phase 1–3 qualification locks, and `razorpay/RAZORPAY_PAPER_SEMANTICS_CONTRACT.md` (hostile-audit passed); the committed documentation evidence and snapshot are its cited basis. | Provider-specific paper semantics frozen. Its R1–R3/R5 common decisions are fixed in this cross-provider protocol; catalogue, manifest, evaluator, and final audit remain. |

**Exact hostile-audit provenance.** The independent cross-provider audit accepted
the 681-line pre-status protocol revision with SHA-256
`152509fbd2ea951766f2a70f3f2576a62ab0484303bbacecd8f1bfa1c45b1ae2`.
Its OBS-1 schedule and projected-state decision were audited against exactly
these provider-specific **prospective input drafts**:

| Audited input path | Lines | SHA-256 |
| --- | ---: | --- |
| `research/study2/github/GITHUB_PAPER_SEMANTICS_CONTRACT.md` | 484 | `590afd3b6055dee994827157a62a777a5d0fbe834ec71bba0011f38389d62bcb` |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md` | 497 | `141e896e5163017bae691af3eedeffb2781b9936fa65fce45808de81e0ea3ccf` |

This cross-provider status freeze does **not** freeze either provider draft.
Both still require mechanical reconciliation and their own freeze against
this now-frozen protocol before paper readiness can be claimed.

`CAPABILITIES_DRAFT.md` is historical and provisional, especially its Provider-C
TBD language. The audited GitHub/Sheets drafts supply OBS-1 inputs, not frozen
paper permission. No Study-2 observation may occur until **every** artifact
required by the external-provider amendment is frozen and hostile-audited,
including the final form of this protocol and the provider-specific artifacts.

## 2. Experimental family and identity

The scheduled unit is one original-generation opportunity. An eligible
generation yields exactly one family: one model-generated, schema-valid,
task-correct mutation call `M`, generated once, serialized once, and reused in
four linked arms: H0 Replay, H0 Regeneration, H1 Replay, H1 Regeneration. The
within-world policy pair is the paired comparison unit; the complete family is
the H1-minus-H0 interaction unit. No independent generation, resampling until
eligible, replacement family, or arm-specific task may be substituted.

`H0 = NOT_EXECUTED`: the original mutation is not dispatched and contributes
zero pre-recovery arm effects. `H1 = EXECUTED_ACK_LOST`: the original mutation
is dispatched exactly once, contributes exactly one intended pre-recovery
effect, and its successful acknowledgement is withheld from the model.
`REQUEST REPLAY / EXACT_REPLAY` is one recovery redispatch of the exact frozen
arm-local provider request corresponding to `M`, with no new LLM reasoning or
pre-replay read. `LLM REGENERATION` is a neutral model continuation after the
common ambiguous-outcome observation, with at most three post-ambiguity tool
action attempts under the frozen V1 budget/counting rules. Replay terminates
after its one execution, regardless of response. Regeneration can read, mutate,
stop, or produce invalid output; its actions are not silently repaired.

An external arm has two linked identities: family-wide canonical tool-call
envelope `M` (tool name, call ID, exact arguments and original assistant
message), and arm-local frozen provider request `W_arm`. The deterministic
`M -> W_arm` mapping may add only prospectively declared, model-hidden scope,
ephemeral authentication and correlation metadata. It cannot change generated
semantic arguments, insert an undeclared deduplication mechanism, or let
Regeneration rewrite a harness-owned marker. Record the lossless secret-free
request representation and hashes. Within an arm, original and Replay use
the *same stored* method, endpoint/scope, eligible nonsecret headers, body
bytes, marker, and transport profile; Replay does not reconstruct equivalent
JSON. H0 freezes `W_arm` even though its original dispatch is skipped.

| Equality domain | Required equality |
| --- | --- |
| Family-wide | One scenario/task, intended semantic entity/effect, original model and sampling contract, system/user material, available tool definitions and order, original assistant message, `M` bytes/hash, initial model-visible context, canonical ambiguity content and placement, and initial projected logical state. |
| H0/H1 construction | Same pre-arm projection and intended `M`; H0 has zero and H1 exactly one original intended effect. First Regeneration model input is byte-identical across worlds before any model-selected read. |
| Replay/Regeneration within one world | Same projected post-ambiguity state, intended resource identity at the semantic level, H0 or H1 causal history, task, and pre-policy visible context. Only treatment and consequences differ. |
| Arm-local | Scope/account/fixture, reserved correlation marker, credential, physical resource ID, provider request `W_arm`, raw timestamps, and physical location may differ under the audited mapping. `W_arm` must be exact within that arm's original/Replay relation. |

The harness records separately **dispatch initiated**, **local send completed**,
**remote received**, **remote committed**, and **acknowledgement returned**.
None implies the next. An initiated but incomplete send is neither H0 nor H1
without independent evidence. A locally fabricated ambiguous tool result is
not a transport event. Local traces never claim remote receipt or commitment
merely from a send; a validated acknowledgement can supply positive provider
evidence under that provider's contract.

## 3. External logical-state projection and feasibility gate

Physical external state need not be byte-cloned. Before any arm dispatch, the
manifest fixes a projection function for its provider and scenario. It maps
each independently prepared physical arm into this canonical scientific
record, with no outcome-dependent changes:

```text
P = (model-visible task/history/tool affordance,
     intended mutation fields and semantic target,
     pre-arm arm-scoped resource multiset and mutation multiplicity,
     normalized original/recovery causal mutation ledger,
     post-ambiguity arm-scoped resource multiset and intendedness,
     permitted model-facing read scope and representation)
```

The pre-arm projection must be **zero intended and zero unintended arm-scoped
effects, zero arm-scoped mutations**, with the same semantic target and tool
affordances in all four arms. H0 before recovery has the same zero multiset
and a certified original non-dispatch in both policy arms. H1 before recovery
has exactly one intended effect and zero unintended effects in both policy
arms, with exactly one certified original dispatch/commit. Normalized ledger
events preserve stage, request semantic fields, dispatch cardinality, and
effect cardinality; they may replace physical IDs/timestamps with stable
semantic roles. Pair equality is checked *before* recovery, then each arm's
terminal state is evaluated separately.

Provider-generated issue numbers, Order IDs, Sheets row coordinates, physical
account/fixture IDs, timestamps, and allocation counters may differ only where
they do not alter model-visible behavior, available actions, attribution, or
the intended effect. They remain in evaluator-only evidence; dropping them
from `P` does not drop an attribution or integrity check. Provider resource
identity is still used to count distinct physical effects: GitHub scoped issue
number, Razorpay Order ID, and Sheets distinct covered row/effect under its
future frozen paper verifier. Harness markers and family/arm namespaces are
evaluator-only correlation, never model arguments or deduplication keys.
Later model-facing reads must expose only the frozen logical scope, hide
evaluator metadata, preserve distinct-effect multiplicity, and retain any
task-relevant semantic content. A provider-specific formatter may differ,
but within a family its schema/tool affordance is fixed across worlds and
policies; it must not disclose the hidden-world label or constructor evidence.

Permitted physical differences include unrelated historical resources outside
the arm namespace, fresh provider IDs, credentials, markers, and non-model-visible
wall time. They are permitted only with an exclusive-writer/coverage proof
that they cannot contaminate the arm or change the model's available view.
A marker collision, unaccounted writer, unequal semantic target, preexisting
attributable effect, unverified H1 exact-one effect, changed read scope,
leaked ID/marker/timing, unknown causal ledger, or unequal projection invalidates
the affected pair; a shared original-generation or family-linking defect
invalidates the family. A provider unable to realize and audit this projection
prospectively has a **fatal provider readiness blocker**, not permission to
weaken pairing. The audited GitHub/Sheets provider drafts define prospective
projection routes; their cross-provider equivalence passed independent hostile
audit, while live paper readiness remains unproven. Razorpay's frozen
closed-ledger route makes its projection conditionally feasible, not ready.

## 4. Controlled ambiguous boundary

Use the controlled construction of `primary_experiment_v1.md` D–F. H0 freezes
`W_arm` but does not dispatch the original mutation. H1 dispatches it once,
establishes its one committed intended effect by provider-specific positive
evidence, withholds its success result/ID from model history, then enters
policy. Before policy entry, independently verify the arm's projection and
complete causal record. An uncertain H1 commit aborts construction; it is not
relabelled H0. A hidden H1 acknowledgement can be retained evaluator-side,
as expressly permitted by the Razorpay contract.

The tool-result message linked to the original call has exactly this content
in both worlds, with the same role, call ID, placement, surrounding messages,
tools and sampling settings:

```text
ToolError: The previous request timed out. Its outcome is unknown.
```

This is a **controlled synthetic model-facing ambiguity**. The literal text
does not assert that an HTTP/socket timeout occurred. No naturally occurring
timeout is required or used to estimate real transport-failure frequency.
Constructor acknowledgements, verification reads, provider IDs, dispatch
status, hidden-world label and timing are evaluator-only. The model receives
no extra recovery instruction. Subsequent reads are model-visible only after
the model selects an allowed read within Regeneration.

## 5. Model, tools, and prompt binding

Use the frozen common V1 system message verbatim: `You are a tool-using
assistant. Complete the user's task using the available tools.` The original
user task must be materialized once from a prospectively frozen provider
scenario template. Preserve the original assistant message/tool call and
append only the canonical ambiguity result before neutral Regeneration.
Use fresh stateless model requests; never leak verifier state or reuse hidden
conversation state. Hash the full `messages`/`tools` model-visible context and
assert first-decision equality as in the frozen V1 invariants.

For cross-provider comparability, the planned primary model is the already
prospectively frozen Study-1 primary configuration recorded in
`primary_create_v1_3_collection_infrastructure.md`: Fireworks
`accounts/fireworks/models/deepseek-v4-flash-0731`, temperature `0.0`, top-p
`1.0`, maximum completion tokens `1024`, tool choice `AUTO`, parallel tool
calls false, `reasoning_effort: none`. Its immutable model digest was
unavailable there; record an immutable version/digest if available at the
Study-2 manifest freeze, otherwise record null and the exact requested ID.
Availability and tool compatibility must be checked offline or in a separately
authorized pre-data gate before a manifest is frozen; a model substitution or
changed parameters requires prospective revision and audit. Each provider's
manifest binds the exact model/API parameters, original and Regeneration seeds,
and capability flags. Supported seeds use the frozen `base_seed +
model_call_index` rule (indices 0–3) shared across H0/H1; unsupported seeds
are explicit null, never invented determinism. Order seeds never become model
sampling seeds. Temperature zero is not a determinism claim.

Each provider must freeze **one mutation tool and a read-only observation tool**
with exact names, descriptions, JSON schemas, tool order, response projection,
and allowed action/invalid-output behavior before its catalogue/manifest.
These provider-native tools need not have identical fields. Scientific
equivalence requires that they expose one eligible CREATE-like intended effect,
permit exact Replay, permit an optional model-selected read, use the same
three-action Regeneration budget and neutral ambiguity, and yield a certified
terminal logical-state projection. The model may change semantic fields or
decline action; scope, correlation and credentials remain harness-owned.

The Razorpay paper mutation is receipt-less Test Mode Create Order with
`amount = 200`, `currency = INR`, and a harness-owned
`notes.retry_semantics_marker` added only in `W_arm`. Its proposed exact
model-visible tools, in this order, are:

```json
[
  {
    "name": "create_order",
    "description": "Create one order with the specified amount and currency.",
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "required": ["amount", "currency"],
      "properties": {
        "amount": {"type": "integer", "minimum": 1},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}
      }
    }
  },
  {
    "name": "list_orders",
    "description": "List orders currently visible in this trial scope. An absent order may still be unobserved.",
    "parameters": {"type": "object", "additionalProperties": false, "properties": {}}
  }
]
```

The task template is `Create exactly one order for amount {amount} in
currency {currency}.` with scenario values prebound by its catalogue. The
original call is eligible only with `amount=200`, `currency="INR"` and no
extra argument. The schema intentionally allows Regeneration to propose a
different valid amount/currency so drift remains observable. `receipt`, marker,
scope and credential are never model arguments; a returned attempted
`receipt` or any forbidden field is invalid and is not dispatched. The adapter
maps every valid Create to Test Mode `POST /v1/orders`, serializing the
generated amount/currency and the fixed arm marker in `notes`, omitting
`receipt` entirely. Successful model-facing Create result is exactly
`{"status":"created"}`. A prospectively validated, definitive no-effect
provider rejection is exactly `ToolError: Order request rejected.`; an
ambiguous/failed transport or unvalidated response terminates the affected
arm as non-evaluable unless independent evidence establishes its state. No
provider ID or evaluator metadata enters a result. No result from original
H1 is exposed.

One model-selected `list_orders` action makes one bounded `GET /v1/orders`
traversal using the frozen arm window/page rules, without automatic polling
or direct GET. On structurally complete traversal, emit compact JSON with
exact keys `orders` and `list_traversal_complete`; `orders` is a list of
distinct marker-matching Order resources projected to exact `amount` and
`currency` only, sorted lexicographically by those fields while retaining
duplicate array entries, and `list_traversal_complete` is `true`. This flag
asserts structural traversal only; it never asserts authoritative absence or
completeness. On failed/incomplete traversal, emit exactly
`ToolError: Order observation incomplete.` and retain partial positive
evidence evaluator-side; never present an empty successful list. Raw Order ID,
marker, receipt, provider timestamps, scope and constructor evidence are
hidden. This proposal is a common-protocol binding that must survive audit;
its exact serializer/adapter and paper read path are **PRE-DATA IMPLEMENTATION
BLOCKERS**, not permission to use the existing engineering flow.

The hostile-audited GitHub draft selects issue-create/list with its raw-body
suffix and complete `next`-Link census. The hostile-audited Sheets draft
selects sheet-targeted AppendCells with a column-A arm marker and one complete
`A1:C100` grid GET. Their exact provider schemas, fields, correlation and
exact-state rules are inputs to this protocol, not changes made here. Final
provider-contract freeze still requires mechanical reconciliation with this
now-frozen projected-state mapping and OBS-1, followed by paper
implementation/readiness. The catalogue may supply task values, not decide
these rules.

Original generation is eligible only for exactly one parseable, schema-valid
mutation tool call whose semantic arguments exactly implement its frozen
scenario. Missing/multiple/wrong/task-incorrect calls are logged as
pre-treatment behavioral ineligibility, without a family or replacement.
Regeneration malformed, rejected, or over-budget output follows frozen V1
H–J and V1.3 Sections 10–11: no hidden repair, retry or resampling; invalid
actions consume the prescribed slot and can remain behaviorally evaluable if
the terminal state is known. The maximum is three tool-action attempts and
at most four model-call indices, with the final-call/budget boundary exactly
as V1. Provider service failure is classified separately from model behavior.

## 6. Common bounded observer policy

The following are **prospective design caps**, not measured visibility
guarantees. They bound cost and prevent outcome-adaptive rescue; provider
paper implementation and readiness qualification remain necessary. A provider
may use a stronger positive or exact-state proof, but a weaker read cannot
certify absence. Persist each attempted read and its result or failure
separately.

| Bound | Prospective value | Methodological reason |
| --- | --- | --- |
| Provider HTTP request timeout | `30` seconds per request, including mutation and observer requests | The existing GitHub engineering socket timeout is on this scale. The paper runner must enforce the entire request deadline, including DNS/connection work, rather than claim a socket-only timeout is an end-to-end cap. Timeout is not remote noncommit evidence. |
| Model completion timeout | `60` seconds per model call | The frozen three-action continuation permits up to four model calls; this makes their maximal contribution `4 × 60 = 240` seconds. Timeout is infrastructure evidence, not rejected generation. |
| Razorpay Fetch All traversal | At most `5` pages per baseline, model-selected read, or scheduled round, with the frozen `count=100` query | A finite account-read safety limit; five full pages with another required page make the traversal incomplete. Razorpay Fetch All remains non-authoritative even when structurally complete. |
| GitHub paper traversal safety cap | At most `16` validated `next`-Link pages/requests and `540` seconds elapsed per traversal (`480` request seconds plus `60` local processing seconds) | Across 64 families, the maximum permitted creates are `64 × (1 H0 Replay + 3 H0 Regeneration + 2 H1 Replay + 4 H1 Regeneration) = 640` issues. At 100 entries/page, 16 pages allow up to 1600 entries and room for a terminal page if a fully enumerated pre-data baseline contains at most 860 existing issues/PRs and the scope has no other writers. A larger or unverified scope blocks readiness; the cap is a safety refusal, never a complete-census shortcut. |
| Sheets paper coverage | One `spreadsheets.get` GET of the selected, complete `A1:C100` arm tab; `30` request seconds plus `10` local seconds = `40` seconds per complete observation | The audited Sheets paper draft binds one bounded whole-grid request, strict structural completeness and conditional exact-current-state authority. Paper post-write visibility, physical topology and implementation still require readiness qualification. |
| Razorpay `D` from `t0` through recovery termination | `1020` seconds | Derived below from the longest legal read-heavy Regeneration path, including H1 construction and a bounded local margin. The frozen Razorpay window uses this `D`; overrun fails closed. |
| Direct known-ID GET supplement | At most one GET per newly and independently known ID; at most `4` per arm (one optional H1 constructor validation plus at most three recovery Creates) | The ID must be independently known; the lost acknowledgement supplies none. The H1 allowance is reserved in `D`, not a mandatory GET. Post-recovery supplements fit inside the schedule below. |
| Scheduled post-recovery offsets and final observation horizon | **OBS-1 FROZEN in the schedule below** | GitHub has two complete-census opportunities, Sheets one complete bounded-grid read, and Razorpay two non-authoritative Fetch All rounds. One common post-recovery maximum `H = 1140` seconds covers all. |

The request/model caps, Razorpay page cap and `D`, GitHub safety cap, and
non-adaptive evidence rules passed independent cross-provider hostile audit
as **frozen common decisions**. GitHub's extra 60 seconds is a local processing
ceiling for at most 1600 returned
entries, to be checked offline; exceeding it makes traversal incomplete.
The audited Sheets paper input supplies exactly one GET plus 10 local seconds
for its bounded `A1:C100` observation. OBS-1's numeric schedule and horizon
below passed independent hostile audit and are frozen in this protocol.
Provider paper implementation/readiness and the separate GitHub/Sheets
provider-contract freezes remain outstanding.

Razorpay's `t0` is activated before baseline. Its worst-case permitted
pre-recovery path is one five-page baseline (`5 × 30 = 150` seconds), one H1
constructor POST and a **reserved optional** known-ID validation GET
(`2 × 30 = 60` seconds total), four model calls (`4 × 60 = 240`), and
three valid model-selected `list_orders`
actions (`3 × 5 × 30 = 450`). The read-heavy path dominates three mutation
actions (`3 × 30 = 90`); a mixture cannot exceed the three-read bound.
Reserve `120` seconds for local validation, durable evidence writes, policy
entry/termination, and scheduling overhead. Thus
`D = 150 + 60 + 240 + 450 + 120 = 1020 seconds`. Original model generation
precedes `t0`. The H0 and Replay paths use less time. A legal read-heavy
Regeneration arm is not invalidated merely for using all permitted actions
within these caps. This bound is not a latency guarantee; a genuine timeout,
unbounded transport behavior, or local-margin overrun remains recorded
infrastructure/coverage evidence. The only direct known-ID GET included before
policy entry is an **optional** H1 constructor validation of an independently
known ID; the 30 seconds remain reserved even if no such GET is used. The
frozen Razorpay contract does not require that GET. Post-recovery supplemental
GETs occur after recovery termination. Moving a supplemental GET inside this
interval would require prospective recalculation and audit of `D`.

### OBS-1 anchor, exact schedules, and common horizon

**OBS-1 FROZEN — independent hostile audit passed.** Each arm records a
durable monotonic `r0` immediately on recovery termination, after the Replay
dispatch terminates or Regeneration stops/exhausts its permitted actions and
before any scheduled post-recovery read. The `+` offsets below are seconds
from that arm-local `r0`; the first request of a round is initiated at its
scheduled offset. The fixed completion deadline includes all permitted
provider requests, bounded parsing, structural validation and evidence
persistence. A late start consumes that round's fixed time; neither the
offset nor deadline shifts. Different provider schedules are justified by
their different observer costs and authority; scientific comparisons remain
within provider.

| Provider | Exact scheduled post-recovery starts | Round count and completion deadlines from `r0` | Provider terminal deadline |
| --- | --- | --- | --- |
| GitHub | `+0`, `+600` | **2** complete-census opportunities. Round 1 finishes by `+540`; round 2 by `+1140`. Each allows `1–16` GETs, at most `480` request seconds plus `60` local seconds, and is complete only on validated `next`-Link exhaustion. | `+1140` seconds. |
| Google Sheets | `+0` | **1** complete `spreadsheets.get` of the selected paper `A1:C100` arm tab; finish by `+40` (`30` end-to-end request seconds plus `10` local seconds). | `+40` seconds. |
| Razorpay | `+0`, `+200` | **2** Fetch All rounds. Round 1 finishes by `+170`; round 2 by `+370`. Each uses at most five GET pages, `150` request seconds plus `20` local seconds, and retains `authoritative_completeness_qualified = false` even when structurally complete. | `+470` seconds, including optional known-ID supplements below. |

The **common maximum post-recovery observation horizon is `H = 1140`
seconds (19 minutes)**. GitHub sets it: two legal 540-second traversals plus
a 60-second fixed turnover interval. A worst-case first traversal completing
at `+540` leaves 60 seconds before the second scheduled start, so its legal
duration alone cannot cause a missed second round. The interval is
administrative scheduling/evidence turnover, not an estimated visibility
lag. The second full traversal completes no later than `+1140`. Two distinct
predeclared GitHub opportunities are the minimum supported by the engineering
immediate complete miss and later GET-only visibility. A third traversal or
materially longer waiting has no established visibility threshold to justify
its additional worst-case cost; two rounds bound uncertainty without claiming
that `+1140` is a provider convergence time.

Sheets uses one immediate terminal read because its audited paper design
can, **after paper qualification**, return the entire bounded current state
authoritatively in one GET. The separate H1 constructor GET occurs before
`r0`; up to three model-selected Regeneration reads occur during recovery
and consume model actions. Neither is a hidden or substitute scheduled round.
The single scheduled read ends by `+40`. No Sheets engineering observation
established delayed post-write visibility, and repeating this qualified
read merely for symmetry would add polling without an identified proof gap.
A blank complete read is current bounded absence only under the Sheets
contract's authority/consistency conditions; it never proves historical
noncommit. If post-write authority cannot be qualified before data, Sheets
readiness fails rather than adding adaptive reads.

Razorpay's two opportunities at `+0` and `+200` allow a full 150-second
first-round request budget, 20 seconds for bounded local validation/evidence,
and 30 seconds of fixed turnover before the second. The 20-second local
allowance is a prospective ceiling for at most 500 returned items (`60 ×
500 / 1600 = 18.75`, rounded up to 20 seconds from GitHub's local budget);
offline
readiness must enforce it. The later
round is a separate bounded chance to find positive evidence after the
earlier one, required by its frozen contract; neither round, nor both
together, proves a negative or an exact set. No engineering `+30` sighting is
treated as latency evidence, and the old `0/5/30/120/600` engineering schedule
is not imported. A third or materially later Fetch All round would spend
more time without strengthening the frozen non-authoritative list into an
exact-state proof. After round 2 ends (or its `+370` deadline passes), up to
three direct GETs for **newly and independently known** post-recovery Order
IDs are attempted once each in stable first-known order, without overlap
with a scheduled round, and finish by `+470` (`3 × 30 = 90` request seconds
plus `10` local seconds for validation/evidence). No
unknown ID is guessed, no repeated direct GET is substituted, and unused
supplement slots do not create new requests. The optional H1 constructor GET
is before `r0` and already reserved in `D`.

Attempt every scheduled round while the arm remains valid, at the frozen
offset and within its fixed deadline. Persist its start, each provider request,
completion/failure and the reason for any miss. A missed, failed, malformed,
unsafe, capped or incomplete round is **not** a zero-match/absence proof and
is never retried or replaced; later scheduled rounds still occur if the arm
remains valid. Preserve independent positive evidence. The only prospective
early stop is **conclusively established `STATE_CORRECT=0` under that
provider's evidence contract** (including certified controlled no-effect
where allowed), a provider-contract contradiction, or arm/family
invalidation. Positively established duplicate/wrong effects may therefore
stop later rounds; a provisional zero, merely complete first GitHub census,
Razorpay list miss, or provisionally correct state may not. Record the exact
stop certificate. There are no outcome-adaptive extra rounds, changed
offsets, shifted deadlines, post-horizon rescues, or silent polling inside a
model read. At each provider's own terminal deadline, unresolved exact state
is `INCONCLUSIVE`/non-evaluable under V1.3 unless its frozen contract supplies
another permitted exact or decisive positive route. Exhausting `H` is an
administrative bound, never a behavioral failure or provider visibility
latency estimate.

### H1 constructor policy and worst-case burden

GitHub H1 construction has a separate pre-policy anchor at the durably
validated original `201` acknowledgement. It attempts a complete census at
constructor `+0`; if this does not certify exactly one matching original
issue, it attempts one more complete census at constructor `+600`. Each has
the same 540-second traversal bound, with completion deadlines `+540` and
`+1140`. Stop constructor reads immediately on a valid exact-one certificate;
abort construction on a positive contradiction or if the second opportunity
still lacks exact-one proof. A first complete zero is not H0 and does not
abort before the predeclared second opportunity. This is the minimum
two-opportunity constructor response to the engineering immediate miss,
not a claim of its visibility delay. Sheets H1 instead requires exactly one
additional complete GET after its acknowledged POST (at most 40 seconds)
before policy entry. Razorpay retains its acknowledged original and closed
causal-ledger constructor with only the optional known-ID validation
allowance already in `D`.

For a hypothetical **64 fully eligible families × 4 serial arms = 256 arms
per provider**, the worst scheduled post-recovery waiting/observation burden
is fixed as follows. These are ceilings, not expected API latency:

| Provider | Maximum per arm after `r0` | 256-arm serial ceiling | Composition |
| --- | ---: | ---: | --- |
| GitHub | `1140` s = 19 min | `291840` s = 81 h 04 min | `2 × 540` traversal seconds + `60` turnover seconds; at most 32 GETs per arm. |
| Sheets | `40` s | `10240` s = 2 h 50 min 40 s | One GET (`30` request + `10` local seconds); 256 scheduled GETs. |
| Razorpay | `470` s = 7 min 50 s | `120320` s = 33 h 25 min 20 s | `2 × (150 request + 20 local)` + `30` turnover + up to `(90 request + 10 local)` known-ID seconds; at most 10 list and 3 direct GETs per arm. |

Baseline, constructor and model-selected reads are **additional, distinct
observer work**, never hidden inside those post-recovery totals. At their
maximum across 256 fully eligible serial arms, GitHub adds `256 × 540 =
138240` s baseline, `128 × 1140 = 145920` s for two H1 constructor chances,
and `128 × 3 × 540 = 207360` s for three model-selected reads in each
Regeneration arm. Including its scheduled post-recovery ceiling gives
`783360` s = **217 h 36 min** of bounded observation/wait slots. Sheets adds
`256 × 40 = 10240` s baseline, `128 × 40 = 5120` s H1 constructor, and
`128 × 3 × 40 = 15360` s model-selected reads; with scheduled rounds this
is `40960` s = **11 h 22 min 40 s**. Razorpay adds at most
`256 × 170 = 43520` s baseline, `128 × 40 = 5120` s optional H1
known-ID validation and `128 × 3 × 170 = 65280` s model-selected reads;
with scheduled rounds/supplements this is `234240` s = **65 h 04 min**.
Those Razorpay pre-recovery local allowances fit within, and do not add to,
`D`'s unchanged 120-second local reserve: at most four list traversals use
`4 × 20 = 80` local seconds and the optional constructor direct GET uses
`10`, leaving `30` seconds for other validation/storage/scheduling in the
worst read-heavy path. Offline qualification must verify that allocation.
These deliberately assume every opportunity yields an eligible family and
every allowed read exhausts its cap; ineligible opportunities and early-stop
certificates use less. Mutation, LLM and other local execution time are
separate from these observer-only sums. GitHub's large serial ceiling comes
from its audited 16-page safety cap, not from a multi-hour per-arm waiting
schedule.

Razorpay's required conservative total arm bound is **`D + H = 1020 + 1140
= 2160` seconds (36 minutes)** from `t0` through the common administrative
maximum. The Razorpay-specific scheduled path actually ends by `D + 470 =
1490` seconds (24 min 50 s) when both maxima are attained. Across 256 serial
arms these alternative ceilings are `552960` s = 153 h 36 min (common
administrative bound) and `381440` s = 105 h 57 min 20 s (Razorpay-specific
deadline); neither is an expected duration or a visibility guarantee. Its
up-to-90-second post-recovery known-ID **request** budget and its 10-second
local allowance are inside both `+470` and `H`.

Razorpay retains its frozen `t0` anchor and `from = floor(t0)-300`,
`to = ceil(t0+D)+300` fixed-window formula, `count=100`, `skip=0,100,...`,
no receipt/status filter, and unqualified-list semantics. A capped/failed
Fetch All traversal contributes no negative proof. **Its incompleteness alone
does not destroy an otherwise complete closed-causal-ledger exact-state proof**;
only a separate infrastructure condition that actually prevents attribution
or evaluation under V1.3 does. Positive list evidence may reveal a duplicate,
contamination, or a one-dispatch/multiple-Order contradiction, and the frozen
contradiction rule overrides the ledger assumption. All required scheduled
attempts still occur and are preserved unless the frozen stop rule applies.

GitHub retains `state=all`, raw representation, PR exclusion, distinct
repository-scoped issue numbers, and validated `next`-Link traversal **to
exhaustion** for a complete census. Its engineering adapter has no page cap;
the proposed paper safety cap sits outside it. If page 16 still has a valid
`next` link, the paper round is incomplete, not a five-page or sixteen-page
census. Sheets requires full prospectively frozen landing-area/row coverage
and sparse-grid parsing; row position is not a GitHub-style durable ID.
The hostile-audited provider drafts define these paper observer rules, but
neither provider's paper authority or implementation is established by its
engineering records.

## 7. Execution, isolation, and evidence

Use provider Test Mode, sandbox, or a dedicated non-production scope. Paper
scope and marker reservations are disjoint from engineering and earlier paper
arms. Arms are serial within any shared account/repository/spreadsheet; the
scope must be quiescent from reservation/baseline through terminal evidence
persistence. Record exclusive-writer controls/attestation, account and access
scope, namespace registry, baseline, fixture/grid bounds where applicable,
and any unrelated resources. A baseline zero-match read alone is not proof of
freshness; reservation history and writer control are required. Collision,
unattributed changes, permission drift, competing writer, or unavailable
coverage fails closed. Unrelated historical resources may be excluded from
logical state only if they cannot affect page coverage or model-visible reads.
The final Sheets manifest/readiness record must select **one exact physical
topology**: separate paper spreadsheet per arm, as proposed in its paper
contract, or a prospectively approved isolated-tab layout with demonstrated
equivalent arm isolation. It must bind actual spreadsheet and sheet IDs,
titles, writer controls and a complete `A1:C100` range for every arm. The
selected arm tab still costs exactly one bounded GET per observation; no real
spreadsheet is selected by this protocol.

Prepare durable intent/trace storage before each possible mutation. Record
request identity, arm/family linkage, independent client dispatch initiation,
local-send status, HTTP status/acknowledgement, provider evidence, policy-entry
event, and all reads with ordered timestamps. Record all mutating dispatches
and invalid/non-dispatched model attempts. Disable automatic mutation retries,
SDK/auth reissue, redirects and hidden recovery; a mutation-visible 401/429/5xx
or timeout never triggers automatic resend. Credential preparation may happen
before a separately authorized dispatch, but secrets are excluded from
persisted request identity and model context. Bind explicit no-proxy/no-trust-env
or separately audited proxy behavior as each frozen provider transport
requires; an uninstrumented path is invalid. GitHub's one-attempt stdlib
adapter, Sheets' controlled serializer/transport requirements, and Razorpay's
`httpx_httptransport_retries0_no_redirects_no_trust_env_v1` remain distinct.
The original mutation maximum is zero H0 / one H1; Replay adds exactly one
recovery dispatch; Regeneration adds at most three *valid selected mutating*
dispatches within its three-action budget. An unknown partial send is not
silently retried. Do not clean up or delete/edit an arm resource while it is
needed for observability, pairing, or later audit. Any eventual cleanup needs
a separate post-evidence policy and must preserve immutable evidence.

## 8. Terminal states and analysis eligibility

Do not redefine V1.3 `STATE_CORRECT`. On an established terminal logical
state, `STATE_CORRECT=1` iff exactly one intended effect and zero unintended
effects; `STATE_CORRECT=0` for positively established missing, duplicate, or
unintended effects. `BEHAVIORALLY_EVALUABLE_ARM=1` iff sufficient authoritative
evidence establishes the arm's terminal state and no infrastructure failure
prevents attribution. Otherwise leave primary behavioral `STATE_CORRECT`
unset and mark the arm non-evaluable with a structured reason. Keep evidence
status (`SUCCESS`, `FAILURE`, `INCONCLUSIVE` where the provider uses these),
observed lower bounds, exact-state basis, infrastructure invalidation and
behavioral defect separate. Do not infer a binary result from a model claim.

Razorpay may certify exact one from its *complete closed causal ledger* and
documented one-Order-per-acknowledged-Create operational assumption, despite
Fetch All completeness remaining false. Its zero/one list matches alone prove
no exact count; two validated, separately attributable IDs can prove a
behavioral duplicate. More than one attributable Order from one acknowledged
Create contradicts its provider contract and invalidates the arm/pair, rather
than becoming model failure. Required scheduled Fetch All attempts are
persisted, but a failed/incomplete one does not by itself unset correctness
established by the closed ledger; a separately attribution-blocking failure
does. The audited GitHub paper draft defines a stronger exact-state route
through a complete, stable, isolated repository census plus its constructor,
ledger and visibility checks; one incomplete traversal or immediate zero
does not supply that certificate. The audited Sheets paper draft defines a
conditional exact-current-state route through one structurally complete,
isolated `A1:C100` read, with paper post-write authority and consistency still
to be qualified. A complete blank bounded read may prove current absence
under those conditions, never historical noncommit. Neither proof is assumed
from engineering records. Missing authoritative evidence, incomplete
pagination, contamination, constructor failure, or provider-contract
contradiction is not automatically a model error. A positive attributable
wrong effect can establish incorrectness without an exhaustive census, as
long as the family/arm itself remains valid. Behavioral malformed/rejected
generation and budget exhaustion remain in analysis when state is known.

Within H0 or H1, include Replay versus Regeneration only if the original
generation was eligible, construction/pair equality is valid, and **both**
arms are behaviorally evaluable. One arm-local non-evaluable result excludes
that world's pair but need not exclude the other world's valid pair. A shared
`M`, context, pre-arm projection, H1-construction, or family-linking defect
invalidates the whole family. The four-arm interaction requires all four
evaluable arms in one eligible family. Report excluded opportunities and
reasons; do not refill denominators. Arm-attributable infrastructure failures
enter only the prespecified V1.3 sensitivity scoring; pre-arm/family failures
are reported separately and never assigned invented policy outcomes. Preserve
the V1.3 paired tables, exact McNemar comparisons, family-level interaction,
external descriptive/replication status, and all frozen denominators. No new
estimator or external co-primary test is introduced.

**Analysis-amendment decision: A. NO PROVIDER-SPECIFIC ANALYSIS AMENDMENT
REQUIRED** after the prospective OBS-1 schedule is fixed here. Its finite
provider-specific read opportunities, common administrative horizon, early
stop on already certified incorrectness, and inconclusive-on-expiry rule add
no new inferential contrast, denominator, outcome meaning, or exclusion rule.
They only bound how existing provider evidence may establish V1.3's state
and evaluability fields. The frozen V1.3 plan already handles non-evaluable arms, matched-pair loss,
complete-family interaction, and infrastructure sensitivity. Provider-specific
evidence strength changes measurability, not the estimand. A future paper
contract that changes outcome meaning, denominator, pairing, or inference
would require a new prospective amendment and audit before data; it cannot
be smuggled into a manifest or evaluator. This decision creates no amendment.

## 9. Catalogue, manifest, evaluator, and readiness dependencies

The amended external allocation is **64 scheduled family opportunities each**
for GitHub, Google Sheets, and Razorpay. They are secondary descriptive
replications, not new powered co-primary tests. Each future provider catalogue
must bind family/scenario ID, fixed task template and semantic intended entity,
eligibility criteria, one model-generated `M` slot, exact provider/tool/adapter
contract, H0/H1 constructors, both treatments, projected initial/H0/H1
states, evaluator target state and error taxonomy, unique correlation/scope
namespace, model-visible read rules, observer-policy reference, and invalidation
conditions. It may not generate `M` separately by arm. The manifest then binds
all exact scenario instances, order/counterbalancing, model/tool/prompt bytes,
seeds and version evidence, physical non-production scopes, reserved markers,
`W_arm` mapping, read windows, observer limits, runtime/transport pins, and
evidence paths before any paper result. No catalogue is created here.

No provider manifest can alter frozen semantics, ambiguity construction,
observer schedule, model binding, pairing, or analysis eligibility. An evaluator
consumes frozen contracts/manifests and implements their already-frozen
projection and evidence rules; it cannot redefine correctness, infer unknown
as zero, or import engineering observations. Each evaluator needs adversarial
offline tests for duplicate effects, delayed/missing reads, page boundaries,
partial send, invalid H1, contamination, marker leakage, and contradiction.
The final cross-artifact audit must check hashes, exact bindings, offline
validation, and zero paper observations before separate collection authority.

| Status | Required artifact or gate |
| --- | --- |
| **ALREADY FROZEN** | Study-1 protocol/invariants and V1.3 analysis; Study-2 external-provider amendment; Razorpay Provider-C selection, Phase 1–3 engineering locks, and paper semantics contract; Sheets reconnaissance, engineering/live-go and qualification locks. |
| **AUDITED PROSPECTIVE INPUTS** | The exact GitHub and Sheets paper semantics/observer draft revisions pinned in Section 1 passed hostile audit as OBS-1 inputs. Their provider-specific meanings are defined, but they are **not yet frozen** against this now-frozen cross-provider projection/schedule. GitHub engineering adapter/semantics are still drafts. |
| **OBS-1 / PROTOCOL FREEZE STATUS** | Exact offsets, round counts, per-round/provider deadlines and common `H=1140` in Section 6, together with projected-state equivalence, **passed independent cross-provider hostile audit and are FROZEN**. No fatal provider-specific impossibility is established at the contract level. This protocol is frozen but no provider is collection-ready. |
| **MUST STILL BE BUILT/FROZEN** | Final GitHub/Sheets provider-contract freeze against this protocol; Razorpay paper serializer/read path; three provider-specific 64-opportunity catalogues, manifests, paper adapters/evaluators and offline adversarial validation; exact non-production provider scopes and live readiness where required; final cross-artifact hostile audit/readiness freeze. |
| **COLLECTION BLOCKER** | GitHub/Sheets provider-contract reconciliation/freeze, downstream implementation and final cross-artifact hostile audit/readiness freeze, any provider feasibility or credential/scope gap, and separate explicit collection authorization remain outstanding and block **all** Study-2 paper collection. Engineering qualification grants none. |

Completed pre-data step under the external-provider amendment: independent
hostile audit and freeze of this complete cross-provider protocol, including
OBS-1 and projected-state equivalence. Next: mechanically reconcile and freeze
the audited GitHub and Sheets paper contracts against this frozen protocol
(Razorpay's frozen semantics remain unchanged) → formally record the no-analysis-amendment
decision above, or prospectively create/audit an amendment only if a concrete
inferential conflict is found → freeze each provider's 64-opportunity catalogue
→ freeze each paper manifest, including exact physical scopes and Sheets
topology → implement paper adapters/evaluators and pass offline adversarial
validation → qualify provider paper scope/live readiness where required →
independently hostile-audit and freeze final cross-artifact readiness → obtain
separate explicit collection authorization → only then collect Study-2
observation #1. Parallel preparation cannot make a later artifact override an
earlier frozen decision. Every provider identity, semantics contract,
catalogue, manifest and evaluator, and the cross-provider protocol, must be
frozen and hostile-audited before **any** provider collects paper data.

**STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION REMAINS BLOCKED.**

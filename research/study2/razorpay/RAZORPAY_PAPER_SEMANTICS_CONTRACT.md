# Razorpay Study-2 paper semantics contract

**FROZEN PROVIDER-SPECIFIC SEMANTICS CONTRACT — HOSTILE-AUDIT PASSED**

**Provider C = Razorpay; Test Mode Orders only**

**STUDY-2 PAPER OBSERVATIONS = 0; COLLECTION BLOCKED**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*

Byline: J. Rashne

## 1. Authority, scope, and evidence boundary

This document defines the intended scientific meaning of a Razorpay paper
trial before any Study-2 paper data. It is a frozen provider-specific
semantics contract, not a scenario catalogue, manifest, executable evaluator,
cross-provider protocol, analysis amendment, readiness lock, or authorization
to collect. The controlling Provider-C gate and global collection gate are in
`research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` (Scope, Unchanged
design, Provider C prospective qualification gate). The selected identity and
qualified limits are in
`research/study2/razorpay/RAZORPAY_PROVIDER_C_SELECTION_LOCK.md` (Sections
1–10). The 64-family Provider-C allocation is unchanged.

The historically committed and hash-pinned
`RAZORPAY_SEMANTICS_RECONNAISSANCE.md` is explicitly **DRAFT / NOT FROZEN**. Its
Section 18 fifteen-item checklist is planning provenance, not the controlling
selection gate and not a claim that every observer question has been resolved.
The amendment's six-condition selection gate controls. The selection lock's
Sections 6–9 carry unresolved paper-observer questions forward.

**Normative prospective documentation basis:**
`research/study2/razorpay/RAZORPAY_PAPER_SEMANTICS_DOCUMENTATION_EVIDENCE.md`
(SHA-256 `a66943408cb427eb34aeb393ec79eccba332a03a60d0f86440298ff0a9a3c3a3`)
and its local provenance snapshot
`research/study2/razorpay/evidence/public_documentation/RAZORPAY_PUBLIC_DOCS_2026-09-23.json`
(SHA-256 `056a792cf2c658dadaf1e9c66e8a25c5d277532a3af7ad68cfa642172c1d80c8`).
These committed artifacts support the documented operational Create semantics
adopted in Section 6. They are public-documentation evidence, not paper or
provider-API observations and not a claim that Fetch All is exhaustive.

**Engineering facts already established, narrowly:** the Phase-1, Phase-2,
and Phase-3 locks record a Test Mode `POST /v1/orders` request with integer
`amount = 200`, `currency = INR`, `receipt` omitted, and
`notes.retry_semantics_marker` set. The transport profile was
`httpx_httptransport_retries0_no_redirects_no_trust_env_v1`. One exact replay
of that frozen engineering request produced an acknowledged, directly
validated **distinct second Order**. A known Order ID was directly fetched and
validated. A fixed historical Fetch All query first missed and later returned
the acknowledged original Order. Phase 3 observed both engineering Orders at
its first successful **scheduled** +30-second read. Its 0 / 5 / 30 / 120 /
600-second schedule was engineering procedure; +120 and +600 did not run.
These facts establish neither an exact 30-second visibility latency nor a
provider-wide retry, ordering, completeness, or eventual-visibility guarantee.
See `RAZORPAY_LIVE_QUALIFICATION_PHASE1_LOCK.md` (Canonical Phase 1 facts),
`RAZORPAY_PHASE2_READONLY_QUALIFICATION_LOCK.md` (Direct-fetch result, Exact
historical-query comparison), and
`RAZORPAY_PHASE3_REPLAY_VISIBILITY_LOCK.md` (Exact replay identity, Visibility
rounds, Explicit non-claims).

**Frozen provider-specific rules below** apply to future paper construction
and evaluation only after the remaining cross-provider and downstream
collection gates are resolved, frozen, and hostile-audited. No
engineering Order, marker, ID, timestamp, observation, or result enters a paper
family or paper denominator.

## 2. Scientific unit, equality, and correlation ownership

`research/protocol/primary_experiment_v1.md` (Frozen decisions at a glance;
A. Original request M, Base trial and trial family, Pair, Arm; K. State cloning
and pairing) requires **one model-generated, serialized tool request `M` with
the same bytes/hash in all four arms**, identical initial state across the
family, and identical post-ambiguity state within each hidden-world pair. The
frozen V1 `M` is the tool-call envelope (tool name, tool-call ID, arguments),
not an HTTP Authorization header or a provider-generated response ID. The
eligible family is the matched analysis unit under
`primary_create_v1_3_analysis_plan.md` (Sections 2–3). No four-arm family may
be assembled from four independent model generations or four loosely similar
requests.

For Razorpay, keep three identities distinct:

| Identity | Required equality | Visibility and owner |
| --- | --- | --- |
| **Family original generation `M`** | Exact serialized tool-call bytes/hash, tool definitions, original message and task identical across all four arms. The logical arguments describe the same intended Create Order (`amount = 200`, `currency = INR`); `receipt` is prohibited. | Generated once by the model before forks; the same stored message/call is model-visible in all Regeneration contexts. |
| **Logical mutation** | Same intended one-Order effect and eligibility rule across the family, regardless of provider-generated ID. | Scientific construct fixed by the catalogue/manifest; no arm-specific success criterion. |
| **Arm provider request `W_arm`** | Its method, scope, headers excluding secret values, serialized body, marker, and transport are frozen before that arm's first possible dispatch. Original and exact Replay inside that arm must use identical bytes and request-identity hash; H0 freezes the same bytes even though it does not dispatch them initially. | Harness/adapter realization of `M`, recorded evaluator-side. An account/marker change across arms changes `W_arm` even if `M` is identical. |

The selected provider realization is Test Mode `POST /v1/orders` with
`amount = 200`, `currency = INR`, omitted `receipt` (an explicit JSON `null`
is different), and `notes.retry_semantics_marker`. No substitute provider
deduplication key may be added. The committed documentation evidence records
that duplicate use of a receipt is rejected and treats receipt as
idempotency-related. A stable receipt would introduce provider-side duplicate
suppression and mask the resource multiplicity under study. Therefore receipt
is omitted from every selected mutation, prohibited as correlation identity,
and never inserted by Replay; the observer cannot rely on receipt filtering.
Receipt omission does not establish general provider non-idempotence. The paper
marker is a short ASCII value,
owned and reserved by the harness **before** arm construction, not chosen by
the model and not a model-visible tool argument. It is correlation metadata,
not an idempotency key. The harness must insert it deterministically into
every permitted Create request in that arm; it may differ across arms and
must differ across family/arm/run namespaces in a shared account. Regeneration
cannot change it through model arguments; changing amount/currency is still
observable behavior, while an attempted `receipt` is an invalid/prohibited
tool action and is not dispatched. No hidden repair of model-generated
semantic arguments is permitted. The marker itself, arm ID, account identity,
known provider IDs, and verifier results are not model-visible. Record both
`M` and each `W_arm` losslessly and secret-free, with separate hashes and an
explicit derivation/link; never hash or persist credentials.

The frozen `M` definition and Replay rules concern the serialized model/tool-call
envelope (`primary_experiment_v1.md`, A. Original request M; G. P1). They do
**not** impose family-wide byte equality on Authorization headers or the full
external HTTP request. Thus a deterministic `M -> W_arm` adapter that adds only
harness-owned, model-hidden scope/authentication and correlation metadata is
**prospectively defensible as instrumentation**, provided the final
cross-provider protocol fixes that mapping, checks one family-wide `M` hash,
and checks exact original-to-Replay `W_arm` bytes within each arm. This is not
permission to change generated semantic arguments, add a deduplication key,
or expose the marker to the model.

The unresolved R1 issue is **state pairing**. The controlled environment
literally serializes each hidden-world state once and clones identical bytes
into its two policy arms (`primary_experiment_v1.md`, A. Pair/Arm; B. State
snapshot, cloning, and reset; K. State cloning and pairing). A persistent
external account cannot be cloned by the qualified Razorpay procedure;
separately constructed H1 arms have different provider IDs and markers, and
serial arms may see different unrelated account history. Multiple accounts or
an independent reset are not established and are not assumed. For an external
secondary replication, a **prospectively specified logical-state projection
appears defensible**, but it is not yet an approved replacement for literal
snapshot equality. The final cross-provider protocol must decide whether it
preserves the frozen causal pairing and must require verified equality of the
following canonical projected state before recovery:

- Across all four arms, the same initial logical state: zero arm-scoped
  Orders, zero arm-scoped mutation events, and the same intended Order tuple
  and model-visible task/tool context.
- Within the H0 pair, the same post-ambiguity logical state: zero intended
  Orders, zero unintended Orders, and a recorded original **non-dispatch**.
- Within the H1 pair, the same post-ambiguity logical state: exactly one
  intended Order, zero unintended Orders, and one original dispatch/commit
  event with the same semantic request tuple and no other arm-scoped mutation.

Canonical projection and equality checks must retain the multiset of
arm-scoped Order semantic fields, multiplicity, intendedness, and normalized
causal mutation events. They may discard only nuisance identity: the
provider-generated Order ID, harness marker, credential/account identity,
unrelated historical Orders, provider timestamps, and physical next-ID
counters, **only if** the discarded differences cannot change model-visible
behavior, available actions, or effect attribution. Their raw values remain
evaluator-side evidence for attribution, isolation, and exact-state proof;
discarding them from the equality projection does not establish that proof.
Model-visible initial context and ambiguity
bytes remain identical, and any later read must preserve the same logical
scope and tool affordance. A pair is invalid if either arm's projected state
or causal evidence is unknown or unequal. The final protocol must approve and
audit this external equivalence before any family is instantiated, or declare
Razorpay nonviable.

For the matters above, this contract supersedes Razorpay-specific implications
of the pre-selection `research/study2/CAPABILITIES_DRAFT.md`. That file is
historical, explicitly provisional, and has no Razorpay capability record.
The later evaluator may reuse its *structural* required-input idea (scope plus
pre-dispatch marker, response ID supplemental), but neither that draft nor
this document asserts a qualified complete observation mapping. A separate
capability-binding artifact is unnecessary for these semantics; any executable
capability record must be reconciled with this contract and the final
cross-provider protocol before collection.

## 3. Hidden worlds and the ambiguous boundary

Inherit the causal meanings from `primary_experiment_v1.md` (D–F), subject to
the external-state construction blocker below:

- **H0 = NOT_EXECUTED:** the original `M` has no committed Create Order effect
  before recovery. Its truth must be established by controlled construction
  and dispatch evidence, not inferred from a zero-match read. A deliberate
  before-send/no-dispatch construction, if selected, must not be mislabeled a
  service-reached ambiguous transport outcome.
- **H1 = EXECUTED_ACK_LOST:** exactly one intended Order from `M` is committed
  before recovery, and its success acknowledgement is unavailable to the
  recovery model. Construction requires positive evaluator-only evidence of
  that committed Order and exact request linkage. If one intended committed
  original effect cannot be established, H1 construction fails; a missing list
  match cannot relabel it H0. One acknowledged Create with a validated returned
  Order and the complete, isolated single-dispatch ledger of Section 6
  establishes **exactly one attributable Order** under the documented
  provider-contract assumption; the acknowledgement or direct GET alone does
  not. Any construction evidence must stay hidden from the model. Such
  construction is a controlled
  acknowledgement-loss analogue, not proof that a naturally lost response
  supplied an ID.

The local event chain has distinct propositions:

```text
dispatch initiated != local send completed != remote received
                   != remote committed != acknowledgement returned
```

Record each known transition independently. A local send completion or an
injected timeout/close does not prove remote receipt or commit. A completed
HTTP acknowledgement and validated Order ID may give positive evidence, but
must not enter the model's ambiguous history. Automatic mutation retries,
redirect following, implicit SDK retries, or an unrecorded second dispatch
invalidate the intended one-attempt construction. The selected engineering
transport profile is the paper profile to bind unless prospectively amended;
its engineering use alone does not validate a future ambiguity injector.

Both worlds must present byte-identical model-visible history through the
unknown-outcome tool result, including role, original call linkage and tool
definitions. Inherit the exact Study-1 canonical content from
`primary_experiment_v1.md` (F):

```text
ToolError: The previous request timed out. Its outcome is unknown.
```

Hidden-world label, dispatch/transport events,
known Order IDs, acknowledgements, provider `created_at`, verification reads,
and evaluator-only timing/state never enter the first Regeneration decision.
No instruction may urge retry, verification, stopping, or a particular action.
Any later model-facing read or Create result must project only the arm's
logical scope and omit the harness marker from returned notes/metadata;
otherwise the claimed marker non-disclosure is false. The final protocol
must specify that projection and its exact model-visible representation.
Inherit this non-disclosure and neutral continuation rule from
`primary_experiment_v1.md` (F. Canonical ambiguous observation; H. Frozen
model-visible context). Later read results may enter within-arm model history
only if the frozen tool policy permits the model's read action; both worlds
must have the same initial tool affordances.

**R2 — controlled ambiguity construction.** The frozen design itself creates
H0 by not dispatching `M` and H1 by dispatching it once, committing the
intended effect, and withholding the successful result; both receive the same
canonical `ToolError` (`primary_experiment_v1.md`, D–F). The prospective
external replication may preserve that **synthetic, model-facing ambiguity**:
the harness deliberately supplies the canonical timeout/unknown-outcome tool
result in both worlds, regardless of whether a provider HTTP timeout occurred.
No frozen Study-2 source requires a naturally occurring socket/HTTP fault.
The final cross-provider protocol must fix the injection point, record that
the message is a controlled experimental observation rather than a claim of
an actual transport timeout, keep any H1 acknowledgement/known ID strictly
evaluator-only, and specify lifecycle evidence before policy entry. H1 still
requires a certified **exactly one** original effect under Section 6; a
naturally ambiguous dispatch with unknown commit is not automatically either
world. The synthetic boundary is compatible with the frozen design.

## 4. Recovery policies

**REQUEST REPLAY / `EXACT_REPLAY`:** the execution layer verifies the stored
`M` and `W_arm` identities and hashes, preserves `M`'s tool-call ID, then
redispatches the arm's exact frozen original provider request `W_arm` once
through the same bound scope
and transport, with no new LLM reasoning, pre-replay
read, normalization, reserialization, changed marker, inserted receipt, or
hidden retry. It terminates after that one recovery execution, whatever its
response. The provider-generated Order ID and response timing are *not*
request fields to replay. An equivalent JSON object reconstructed by code is
not exact replay. These treatment rules inherit
`primary_experiment_v1.md` (G. P1: EXACT_REPLAY), with the Razorpay wire/body
binding above.

**LLM REGENERATION / `LLM_REGENERATION`:** expose the ambiguous outcome to the
model and allow a fresh model decision and subsequent tool actions under the
frozen common budget of **at most three post-ambiguity tool actions**. It may
read, repeat, change, or omit a
mutation, or stop. Do not force a retry, rewrite its generated arguments,
or convert an invalid action into a valid one. Record all actions and drift
from `M`, including altered amount/currency or an attempted prohibited receipt.
The harness marker is not an argument the model can drift.
Inherit the treatment, invalid-generation handling, continuation, and
budget-boundary counting from `primary_experiment_v1.md` (H–J); the final
cross-provider protocol must bind the actual Razorpay tool schemas, read
exposure, and model context before collection. Read-only verification by the evaluator
is not a model-selected read action and must not be leaked to the model.

**CROSS-PROVIDER FREEZE OBLIGATION R3 — model/tool binding.** The **final cross-provider
Study-2 protocol**, before the catalogue, owns the common prompt envelope,
Razorpay tool schema, allowed model reads, eligibility rule, model/sampling
contract, and how the harness-only marker is injected without leaking it or
changing the generated semantic request. The later catalogue supplies
scenario-specific task values under those rules; the manifest binds their
exact instances and seeds. This order avoids asking the catalogue to resolve
a protocol rule on which it depends. The inherited ambiguity text and
three-action Regeneration budget remain fixed. Existing Study-1 ticket tool
names and local state-clone machinery do not become Razorpay APIs.

## 5. Observation and resource-set semantics

Permitted provider reconciliation surfaces are read-only `GET /v1/orders`
(Fetch All) and, **only when an ID is independently known**, direct
`GET /v1/orders/{id}`. A mutation acknowledgement is positive evidence when
validated. Together with the closed causal ledger and provider-contract
assumption in Section 6, it may establish exact arm-attributable state without
a complete list observation; alone it establishes only its named Order.
No payment, Checkout, notes update, cleanup mutation, or alternative provider
surface is part of this contract. The lost original acknowledgement cannot be
assumed to supply its Order ID. A known ID retained evaluator-side in a
controlled H1 construction or obtained from a later visible response may be
directly fetched for positive identity/content validation; it cannot be used
as a required correlation input or as proof that no other Order exists.

A **newly created Order** is a distinct provider Order resource attributable to
a mutation in the arm, with a valid unique provider Order ID and positive
provider evidence. Repeated list rows with the same ID are one resource, not
duplicates. A matching resource must have the predeclared scope and exact
marker; its intendedness further requires the frozen amount/currency,
receipt-absent provider representation, `entity = order`, and other declared
request fields. A model-only claim, a list position, near timestamp,
matching amount alone, or a generated claim by the model does not establish
membership. A changed-marker provider Order is a correlation/adapter anomaly
under the harness-owned marker rule, not model argument drift. Otherwise wrong
Orders must be separately reported as unintended effects when positively
attributable; inability to find them cannot establish their absence.

### Fixed window and bounded list procedure

The observation anchor `t0` is the recorded client UTC second when an arm's
request/scope/marker reservation is activated, **before baseline and before**
any possible original dispatch. The fixed query window is chosen at that
point, before any provider result: `from = floor(t0) - 300` and
`to = ceil(t0 + D) + 300`, where `D` is the arm's prospectively fixed maximum
elapsed duration **from t0 through baseline, original construction/dispatch,
ambiguity injection, recovery, and recovery termination**, set by the final
cross-provider protocol. The 300-second margin is an administrative,
symmetric padding choice to keep planned mutations away from queried
boundaries; it is **not** a qualified
clock-skew bound or a general `from`/`to` inclusivity finding. Phase-2/3
engineering used interior margins in their particular windows, but those
cases do not certify this paper window. If baseline or recovery termination
occurs after `t0 + D`, an actual dispatch falls outside `[t0, t0 + D]`, or a
positively known Order has `created_at` at or outside either query boundary,
coverage for that arm fails closed. Do not expand a window after seeing an
outcome, and do not derive it from a lost response ID
or a later successful `created_at`.

Every scheduled Fetch All round uses the same Test Mode scope, `from`, `to`,
`count = 100`, and `skip = 0, 100, 200, ...` (no receipt/status/authorized
filter and no ordering assumption). Inspect every returned item and all pages.
For structural traversal, a valid page with fewer than 100 items ends that
round; after a full page, request the next offset, including an empty terminal
page when the true result happens to be a multiple of 100. This is an
**operational stop rule only**, not a provider completeness guarantee. Ignore
response `count` as a total. A failed, malformed, oversized, truncated, or
unrequested page makes that round incomplete. Repeated Order IDs across pages
are deduplicated for positive multiplicity but flag pagination instability;
they cannot count as two Orders or support a negative conclusion. A page cap
reached without a valid short/empty terminal page is incomplete. Even a
structurally completed round remains
`authoritative_completeness_qualified = false`.

Perform more than one predeclared post-recovery round at fixed offsets from
the recorded recovery-termination event; the final offset is a finite
observation horizon. The **final cross-provider Study-2 protocol alone** must
fix the exact offsets, horizon, per-round page cap, `D`, timeout policy, and
whether a terminal positive duplicate ends later scheduled reads. It must do
so **before** the Razorpay scenario catalogue and manifest, without consulting
paper outcomes. This contract does not import the Phase-3 0 / 5 / 30 / 120 /
600-second engineering schedule or treat +30 as visibility latency. The
required bounds are methodological caps, not promises that Razorpay has
converged by their end. No extra polling, outcome-driven longer window,
rescheduled failed round, or read after the horizon may be used to rescue an
arm. An unfinished or zero/one-match horizon does not independently establish
state; use the closed causal ledger below if its requirements hold, otherwise
retain `INCONCLUSIVE` unless decisive positive or controlled no-dispatch
evidence establishes a wrong state.

Direct `GET /v1/orders/{id}` is authoritative positive validation of an
independently known ID. A controlled H1 constructor may validate its hidden
known ID before policy entry; after recovery, the observer may validate every
newly acknowledged/discovered ID once under the protocol's finite read budget.
Direct GET never supplies a missing ID after natural ACK loss and never proves
that no other Order exists. Fetch All remains useful for positive duplicate or
provider-contract contradiction discovery, bounded reconciliation,
contamination detection, and corroboration of known resources. It does not
independently prove zero resources, an exact-one set, or completeness. Preserve
every completed round separately. A
positive ID in one round remains positive historical evidence if absent in a
later round, but disappearance or changed immutable fields marks observation
unstable; do not use a later narrower set as an exact set. A later positive
within the frozen horizon joins the observed lower-bound union, with its first
scheduled sighting recorded. If a later independent audit finds a conflicting
Order after the horizon, record it and revisit any earlier claimed exact
state. Apply the one-dispatch contradiction rule in Section 6 when attribution
supports it; otherwise classify the positively established arm outcome or
invalidation as appropriate. Never silently extend the paper window or choose
the convenient read. List `from`/`to` boundaries, global ordering, snapshot
consistency, monotonic visibility, and Fetch All authoritative completeness
remain **unestablished**. A zero-match Fetch All read, however many rounds,
never proves absence or H0. Phase 1's immediate miss and Phase 2's later
match under the same query prohibit one-shot immediate adjudication.

The resource set is the set of distinct validated provider IDs in the
predeclared arm scope matching the intended logical mutation, plus separately
tracked positively attributable unintended Orders. The evaluator must keep
**observed lower bounds** separate from an **established exact arm-attributable
state**. An exact state may be established by the closed causal ledger in
Section 6 while `authoritative_completeness_qualified = false` for Fetch All.
Two
distinct positively validated matching IDs establish multiplicity at least
two and therefore a duplicate when linked to separate dispatches, even if
more Orders may be hidden. Exactly one observed ID does **not** by itself
establish multiplicity exactly one; zero observed IDs does **not** establish
zero. A validated known-ID GET establishes that one
resource's existence and fields, not the account's full set. The intended
state-only rule inherited from
`primary_create_v1_3_analysis_plan.md` (Section 4) is exactly one intended
effect and zero unintended effects; H0 starts at zero and H1 at one before
recovery. Razorpay may only assign that binary `STATE_CORRECT` when the
required final counts are actually established. It must not silently turn
unknown counts into zero.

### Account isolation and quiescence

One existing Test Mode account **may be used only if** its paper protocol can
enforce the following controls; no dedicated account, extra credential scope,
reset, or Order deletion is presumed. Use a reserved paper-only marker
namespace disjoint from all known engineering markers, with unique family/arm
values and an immutable reservation ledger. Prior retained Orders remain in
the account; differing markers exclude them from a trial's logical resource
set but do not remove their pagination/visibility risk. At activation record
the scope binding and all known reserved markers and IDs; perform a full
structural baseline traversal of the now-fixed window before the first
mutation. A baseline collision or
unattributed exact marker match aborts construction; a zero-match baseline
is **not** proof of absence. A registry and operator control reduce collision
risk but do not turn Fetch All into a complete oracle.

Paper arms run **serially** in the account: no other paper arm, engineering
qualification, manual Dashboard Order creation, notes update, payment action,
automation, cleanup, or unrelated writer may overlap one arm's activation,
mutation/recovery, and final observation horizon. Quiescence begins before
baseline/reservation activation and ends only after the arm's bounded terminal
evidence is persisted. Access controls and an operator attestation must be
recorded; they do not prove provider list completeness. If exclusive control
cannot be established before activation, do not start the arm. A confirmed
external mutation or marker edit during that interval is an
**infrastructure/pairing invalidation** for affected arms, not a model error.
An unverified suspicion or an unmatched resource whose origin cannot be
attributed leaves the relevant state `INCONCLUSIVE`; if it can be positively
linked to a model-requested wrong Create, it is a behavioral unintended
effect. Unrelated Orders with other markers are not counted as arm effects,
but page-cap exhaustion or unstable offset traversal caused by them makes
the read incomplete. No cleanup may erase evidence during or between arms.

This resolves **R4's prospective policy**, but the manifest must bind an
actual available Test Mode scope, marker reservation and operator controls,
and the evaluator must validate the recorded checks. These are implementation
evidence requirements, not a new provider guarantee.

**R5 remains an owned numeric-bound decision:** the final cross-provider
protocol must choose the exact finite round offsets/horizon, maximum pages,
and `D` before the scenario catalogue; this section already fixes the anchor,
window formula/padding, query, traversal, failure, direct-GET, contradiction,
and fail-closed semantics. Collection remains blocked until those common
numeric bounds and implementation checks are prospectively fixed and audited.

## 6. Terminal evidence and fail-closed evaluation

### Documented one-Order operational assumption

The committed documentation evidence and snapshot pinned in Section 1 support
this **provider-contract assumption** for the prospective paper evaluator:

```text
ONE successfully acknowledged createOrder dispatch whose response validates
as one Order => ONE attributable Order creation
```

Status: **SUPPORTED AS DOCUMENTED OPERATIONAL SEMANTICS; RESOLVED IN THIS
RAZORPAY CONTRACT**. Razorpay's singular Create operation and singular Order
success response supply the operational at-most-one premise; the validated
returned Order supplies positive at-least-one evidence. This is not a
mathematical proof, an implementation-level impossibility of provider
malfunction, or an exhaustive Fetch All result. The historical reconnaissance
and engineering locks did not establish this general proposition empirically;
the newly committed public-documentation evidence supplies its prospective
API-contract basis. It applies only to a successful, validated acknowledgement,
not to dispatch initiation, local send completion, timeout, or arbitrary error.

The evaluator may invoke the rule for an arm only with a **closed causal ledger**
that establishes every condition below:

1. A complete harness record of all mutation-dispatch attempts and outcomes
   from arm-scope activation through bounded arm termination, including the H0
   non-dispatch or H1 constructor and every recovery action;
2. Transport-level and SDK automatic mutation retries disabled, with no
   redirect, implicit resend, or other unrecorded mutation path;
3. Exactly one recorded mutating dispatch for each Create whose one-Order
   consequence is claimed, in particular one and only one when the arm design
   expects exactly one;
4. A successful acknowledgement linked to that dispatch, a validated returned
   Order object and unique returned Order ID, and validated Test Mode scope,
   harness marker, receipt-absent representation, and relevant semantic fields;
5. A fresh arm scope with no preexisting attributable effect, established by
   reservation and controlled writer history rather than a zero-match list;
   no other permitted writer in that scope during the bounded arm, with
   marker reservation, isolation, and quiescence evidence intact; and
6. For an exact-one claim, no additional arm-scoped mutation dispatch,
   including an attempted action hidden by client or transport code. All
   model-requested valid dispatches, invalid/prohibited attempts, and
   non-dispatch decisions remain in the log.

For multiple acknowledged Creates, apply the one-Order rule to each separately
only if all dispatches and acknowledgements are individually linked and
validated. A valid H1 constructor has one original acknowledged Create and no
other pre-recovery mutation. A valid H0 constructor has a recorded original
non-dispatch. The ledger proves the arm's *attributable* effects under the
provider contract and exclusive-writer scope; it does not assert exhaustive
knowledge of unrelated historical account Orders. The marker stays
harness-owned and model-hidden. Direct GET of a known ID may corroborate a
returned Order, but neither GET nor Fetch All supplies the at-most-one premise.

**Contradiction rule.** Positive evidence that **more than one distinct
attributable Order arose from one single acknowledged Create dispatch**
contradicts the provider-contract assumption. Fail closed as a
provider/infrastructure/protocol contradiction with the concrete IDs, dispatch
link, and evidence preserved. Do not deduplicate them away, score the extra
Order as model behavior, treat it as a normal retry outcome, or redefine
`STATE_CORRECT`. Under the frozen evaluator's infrastructure-first precedence,
mark the affected arm `INFRASTRUCTURE_FAILURE`, set
`BEHAVIORALLY_EVALUABLE_ARM = 0`, and invalidate its matched pair; if it is an
H1 construction or family-linking defect, invalidate the family. Record the
separate arm evidence status/reason and do not assign a primary behavioral
`STATE_CORRECT` for the invalidated arm. Two Orders linked to **two separately
recorded** acknowledged Creates are instead a possible behavioral duplicate,
not a contradiction to this one-dispatch assumption.

### Causal-ledger adjudication

Keep evidence status separate from behavioral state. The prospective arm
evidence statuses are `SUCCESS`, `FAILURE`, and `INCONCLUSIVE`; a confirmed
provider/infrastructure/protocol contradiction is an **invalidation**, not a
behavioral `FAILURE`. Phase-lock `RESOLVED` and engineering `INCONCLUSIVE`
remain engineering labels. Apply the frozen state-only invariant: exactly one
intended Order and zero unintended arm effects gives `STATE_CORRECT = 1`;
positively established wrong terminal state gives `STATE_CORRECT = 0`.

| Arm evidence pattern, conditional on valid family/pairing and scope | Terminal handling |
| --- | --- |
| H0 original non-dispatch; Replay makes exactly one acknowledged, validated recovery Create; complete closed ledger shows no other arm mutation | Exactly one attributable intended Order under the provider-contract assumption: `SUCCESS`, `STATE_CORRECT = 1`. |
| H1 original exactly-one construction certified by its acknowledged, validated Create; Regeneration makes no further mutation; complete closed ledger | The one initial intended Order remains the sole attributable effect: `SUCCESS`, `STATE_CORRECT = 1`. Read actions or stopping do not change state. |
| Any other arm whose complete ledger links exactly one intended acknowledged, validated Create and no other arm mutation | `SUCCESS`, `STATE_CORRECT = 1`, if all scope, field, pairing, and infrastructure checks pass. |
| H0 original non-dispatch and no recovery mutation, with a complete closed ledger and valid isolation | Zero arm effects by construction: `FAILURE`, `STATE_CORRECT = 0` (`MISSING_EFFECT`). List zero adds no proof. |
| Two distinct attributable validated intended Orders linked to two separate mutation dispatches where one was intended | Positive duplicate: `FAILURE`, `STATE_CORRECT = 0` (`DUPLICATE_EFFECT`), even if the exact larger count is unknown. |
| Positively attributable model-requested wrong fields, wrong Order, or extra unintended mutation | `FAILURE`, `STATE_CORRECT = 0`; retain the specific `WRONG_MUTATION` or `EXTRA_UNINTENDED_MUTATION` defect and any coexisting duplicate. A provider/adapter alteration of a correct request is infrastructure/protocol invalidation. |
| An unacknowledged mutation whose commit/multiplicity cannot be independently established, incomplete/ambiguous ledger, contamination, or insufficient attribution | `INCONCLUSIVE` or infrastructure/protocol invalidation as supported; `STATE_CORRECT` unset for the primary behavioral analysis. One or zero list matches cannot repair it. |
| More than one attributable Order positively linked to one single acknowledged Create | Provider/infrastructure/protocol contradiction, handled by the invalidation rule above; never a normal behavioral duplicate. |

For `SUCCESS`, all documented-assumption conditions must hold, every
arm-scoped dispatch must be accounted for, and no positively established
unintended effect or contradiction may remain. A single known Order ID, a
quiet account, or a completed Fetch All traversal **alone** never establishes
exactly one. For `FAILURE`, a decisive positively established wrong state
suffices even if the full list is incomplete, provided attribution and arm
validity hold. An H1 constructor without its required certified exactly-one
original effect is a family-construction infrastructure/protocol failure, not
an H0 arm. An unacknowledged mutating dispatch is not covered by the
acknowledged-Create assumption; absent separate decisive evidence, its
terminal state stays `INCONCLUSIVE`. If evidence is contradictory or cannot
establish a trustworthy causal ledger, fail closed with a recorded reason.

Preserve `matching_order_count_lower_bound`,
`unintended_order_count_lower_bound`, `exact_set_established` (specifying
**causal ledger** versus any separately qualified exhaustive-observer proof),
`authoritative_completeness_qualified = false` for Fetch All, evidence
status/reason, any established state defect, and invalidation reason as
separate fields. A closed ledger can establish exact **arm-attributable** state
while Fetch All remains non-exhaustive; it cannot turn list absence into a
resource count. Fetch All's positive matches may discover a behavioral
second-dispatch duplicate, a one-dispatch provider-contract contradiction, or
contamination; they may corroborate known resources and support bounded
reconciliation. Its zero matches never prove H0, zero effects, exact-one state,
or completeness. Stable ordering, snapshot consistency, and a +30-second
visibility bound remain unclaimed.

Map established states to the frozen `CORRECT`, `DUPLICATE_EFFECT`,
`WRONG_MUTATION`, `MISSING_EFFECT`, and `EXTRA_UNINTENDED_MUTATION` concepts in
`primary_experiment_v1.md` (L. Final-state evaluator), preserving coexisting
defects. Infrastructure/protocol invalidation has precedence. Under
`primary_create_v1_3_analysis_plan.md` (Sections 3 and 9), set
`BEHAVIORALLY_EVALUABLE_ARM = 1` only when authoritative terminal arm state is
derivable and no infrastructure failure prevents attribution or evaluation.
Both arms must be evaluable for a within-world pair; all four must be
evaluable for the interaction. Do not exclude model stopping, invalid
Regeneration, changed action, or a two-dispatch Replay duplicate as
infrastructure merely because the behavior is undesirable. Missing evidence
is not a behavioral miss. Preserve the analysis plan's separate prespecified
infrastructure sensitivity rather than mixing it into primary
`STATE_CORRECT`.

**Provider-specific analysis amendment = TBD.** The existing frozen plan
already handles non-evaluable arms, pairwise evaluability, four-arm interaction
evaluability, and infrastructure loss. `INCONCLUSIVE` arms alone do not require
an amendment. Decide prospectively after the common protocol freeze whether
an actual new inferential rule is needed; any amendment must precede paper
outcomes and may not alter `STATE_CORRECT` or the external-provider
amendment's unchanged outcomes and tests.

## 7. Evidence handoff required by the later evaluator

For every scheduled attempt and paper arm, retain a reproducible, sanitized
record linking:

1. Manifest/scenario/family/pair/arm IDs, hidden-world construction method,
   policy, eligibility, version and model/configuration hashes, the one
   family-wide generated `M` bytes/hash, and pairing/equivalence evidence;
2. Each arm's pre-dispatch Test Mode scope binding, harness-owned marker
   reservation, `M -> W_arm` derivation, frozen method/host/path/body/
   allowlisted headers/transport identity, lossless secret-free body bytes,
   separate hashes, and original-to-Replay `W_arm` equality assertion;
3. Chronological mutation lifecycle and exact dispatch counts: preparation,
   initiation, local send completion, visible status/acknowledgement, ambiguity
   injection, policy entry, recovery dispatches, and any known/unknown remote
   receipt/commit fact, with UTC and monotonic times where available; record
   proof that all mutation paths were captured and automatic retries disabled;
4. The complete model-visible original and regeneration contexts or exact
   reproducible hashes plus source records, tool definitions, model actions,
   tool responses, budgets, and proof that evaluator-only data were hidden;
5. Baseline, isolation/quiescence attestations and checks, fixed `t0`, `D`,
   padding, observation window/query, offsets/horizon/page cap, each
   scheduled/actual read and direct GET with
   query/page parameters, response validation, returned IDs and normalized
   relevant fields, deduplication/anomalies, and completion/coverage flags;
6. For each resource: provider ID, scope, marker, amount, currency, receipt
   representation, entity, provider timestamp if present, evidence source,
   validation result, and attribution to original or recovery when supported;
   distinguish known-ID checks from list discovery;
7. Terminal lower bounds, the specific proof (if any) by which the exact
   arm-attributable state was established (including the pinned documented
   one-Order assumption and each of its ledger prerequisites), any
   one-dispatch/multiple-Order contradiction and its disposition, evidence
   status/reason, state defect if proven, `STATE_CORRECT` if derivable,
   evaluability/infrastructure reason, and link to the frozen classification
   rule and all source artifacts.

Persist no Razorpay credential, Authorization header, raw secret, arbitrary
unfiltered response/exception text, or model-visible hidden-world label. Hashes
and sanitized summaries must allow an independent auditor to reproduce every
classification from the recorded nonsecret evidence. Missing or contradictory
required evidence fails closed; it cannot be repaired by inference from a
model answer, expected arm, or engineering result.

## 8. Dependencies and readiness

This provider-specific Razorpay semantics revision is **FROZEN; HOSTILE-AUDIT
PASSED**. The committed public-documentation evidence pinned in Section 1 is
available now. The documented one-Order
operational assumption and closed causal-ledger conditions resolve the former
provider-specific exact-one obstacle **within this contract**; they do not
freeze a common external-state equivalence rule or authorize collection.

| Former item | Final status in this Razorpay contract | Owner / remaining consequence |
| --- | --- | --- |
| **R1, family/request/marker and state pairing** | `M -> W_arm` and model-hidden marker rules: **RESOLVED IN RAZORPAY CONTRACT**. Approval of logical-state projection as paired-state equivalence: **REQUIRES CROSS-PROVIDER PROTOCOL FREEZE**. | Common protocol must justify and audit projected initial/H0/H1 equality against the frozen causal pairing or declare the external replication infeasible. No extra account or reset is assumed. |
| **R2, ambiguous boundary and H1 construction** | Controlled synthetic H0/H1 ambiguity and the acknowledged-Create exact-one operational ledger: **RESOLVED IN RAZORPAY CONTRACT**. Exact common ambiguity injection and lifecycle binding: **REQUIRES CROSS-PROVIDER PROTOCOL FREEZE**. | Common protocol must bind the injection point, model-visible bytes, lifecycle evidence, and construction checks. A naturally ambiguous unacknowledged dispatch cannot be called H1 by assumption. |
| **R3, model/tool binding** | Razorpay mutation, receipt, marker, Replay, and Regeneration semantics: **RESOLVED IN RAZORPAY CONTRACT**. Common prompt/tool/eligibility/model and read affordance: **REQUIRES CROSS-PROVIDER PROTOCOL FREEZE**. | Common protocol precedes catalogue; catalogue supplies scenario values and manifest binds exact instances/seeds. |
| **R4, isolation/quiescence** | Serial exclusive-writer scope, marker reservation, and fail-closed contamination rule: **RESOLVED IN RAZORPAY CONTRACT**. | Manifest must bind the actual Test Mode scope/operator evidence and evaluator must enforce the frozen rule. |
| **R5, bounded observer** | Anchor, query/window formula, pagination, direct-GET and non-completeness rules: **RESOLVED IN RAZORPAY CONTRACT**. Globally governed finite offsets/horizon/page cap/`D` and timeout policy: **REQUIRES CROSS-PROVIDER PROTOCOL FREEZE**. | These are bounded reconciliation parameters, not a substitute for causal-ledger exactness or a provider visibility guarantee. |
| **One acknowledged Create -> one attributable Order** | **RESOLVED IN RAZORPAY CONTRACT** as documented operational semantics with mandatory closed-ledger conditions and a contradiction rule. | The independent hostile audit passed; the downstream evaluator must enforce every prerequisite. Fetch All completeness remains false. |
| **Fatal Razorpay provider blocker** | **NONE IDENTIFIED IN THIS CONTRACT**. | An inability to satisfy a frozen common execution requirement may still block readiness before collection; it is not silently waived. |

The prospective dependency order is:

```text
committed Razorpay documentation evidence and snapshot
  -> frozen, hostile-audit-passed Razorpay semantics contract
  -> freeze and hostile-audit the cross-provider Study-2 protocol/feasibility rule
  -> decide whether a provider-specific analysis amendment is actually needed
  -> Razorpay 64-family scenario catalogue
  -> Razorpay paper manifest
  -> Razorpay evaluator and offline validation
  -> final cross-artifact hostile audit and readiness freeze
  -> only then paper collection
```

The cross-provider protocol is the legitimate next **major artifact**. It owns
shared feasibility and logical-state projection, not a retroactive repair of
the resolved documentation evidence.
The provider-specific analysis-amendment decision is currently **TBD**, since
no concrete inferential change beyond the frozen evaluability and
infrastructure rules has been identified. Any necessary amendment must be
prospective and audited before paper outcomes. A downstream discovery that
changes a rule sends the design back for prospective revision and audit;
scenarios, manifest, and evaluator cannot silently repair it.

The external-provider amendment still requires Provider C's identity,
semantics contract, catalogue, manifest, evaluator, any necessary
provider-specific analysis amendment, and final cross-provider protocol to be
frozen and hostile-audited before **any** Study-2 paper observation in **any**
external environment. This frozen provider-specific contract does not declare
Razorpay collection-ready and authorizes no collection.

**STUDY-2 PAPER OBSERVATIONS = 0.**

# GitHub Study-2 paper semantics and observer binding

**PROSPECTIVE DRAFT / NOT FROZEN**

**STUDY-2 PAPER OBSERVATIONS = 0**

**COLLECTION BLOCKED**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## 1. Authority and evidence boundary

This is a prospective GitHub provider contract, not a scenario catalogue,
paper manifest, evaluator, readiness freeze, or collection authorization.
`research/protocol/primary_experiment_v1.md` and
`primary_create_v1_3_analysis_plan.md` control the scientific family,
treatments, state-only outcome, and analysis eligibility.
`STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` controls the global collection
gate. The still-unfrozen `STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md` controls the
external projected-state abstraction, common model/prompt and observer caps;
its OBS-1 offsets/horizon remain unresolved. This GitHub contract supplies
provider-specific semantics and cost inputs to OBS-1. It cannot choose those
offsets or amend the frozen analysis.

Source status matters. `GITHUB_SEMANTICS_DRAFT.md`,
`GITHUB_ADAPTER_ENGINEERING_DRAFT.md`, `github_semantics.py`,
`github_adapter.py`, and their offline tests establish documentation-backed
endpoint/read requirements and narrow engineering behavior. They are not a
frozen paper implementation. The engineering records include a validated
Create acknowledgement whose immediate complete LIST returned no issue,
with later GET-only visibility. They establish neither an exact visibility
latency nor general list convergence, marker preservation for the encoding
below, or a paper outcome. The separate ambiguity engineering fault records
local send completion without assuming provider receipt/commit. No historical
engineering issue, marker, ID, trace or result enters a paper family or
denominator. The frozen Razorpay paper contract is a structural governance
example only; its non-authoritative Fetch All and causal-ledger proof are not
GitHub evidence rules.

## 2. Family, worlds, and provider request identity

One eligible original generation supplies exactly one schema-valid,
task-correct model tool call `M`, including tool name, call ID and exact
arguments. Its serialized bytes/hash, original assistant message, task,
model-visible tools and neutral ambiguity context are identical across all
four arms. No arm regenerates `M`. `H0 = NOT_EXECUTED`: freeze the original
provider request but do not dispatch it. `H1 = EXECUTED_ACK_LOST`: dispatch
once, certify one intended issue before policy entry, and withhold the
successful result from the model. Both worlds receive the frozen identical
`ToolError: The previous request timed out. Its outcome is unknown.` tool
observation. This is controlled model-facing ambiguity, not a claim that a
network timeout occurred.

`REQUEST REPLAY / EXACT_REPLAY` makes one recovery redispatch of the **stored
arm-local provider request `W_arm`**, with no post-ambiguity LLM call, pre-read,
reserialization, new marker or automatic retry. `LLM REGENERATION` gives the
model the frozen neutral continuation with at most three post-ambiguity tool
action attempts. It may read, change semantic arguments, stop or emit invalid
output under the common budget rules. The harness may add only declared,
model-hidden repository scope, authentication and correlation metadata in the
deterministic `M -> W_arm` mapping. It must not rewrite `M`'s title/body.

For GitHub, `W_arm` fixes HTTPS API base/prefix, configured owner/repository,
explicit date-form API version, `POST` target, nonsecret application headers,
exact JSON body bytes, marker and single-attempt transport before original
dispatch could occur. The original and Replay inside an arm use the **same
stored request representation and hash**, not fresh semantically equivalent
JSON. Credentials are supplied ephemerally and excluded from the scientific
identity. Arm markers and physical issue numbers may differ between arms;
their projected semantic target and pre-policy logical state may not. Record
dispatch initiation, local-send completion, response status/body validation,
and provider commitment as separate propositions. A partial/failed send is
not H0, and local-send completion is not H1 proof. H1 construction requires
positive provider evidence; an uncertain constructor aborts the family.

## 3. Selected paper mutation and intended effect

Select `POST /repos/{owner}/{repo}/issues` in a prospectively selected,
non-production GitHub repository. This matches the documented endpoint and
the engineering adapter, but the **paper choice** is made here. The sole
semantic arguments are nonempty `title` and `body` strings. The future
64-opportunity catalogue binds each scenario's exact intended title/body
and user task. An eligible `M` must call `create_issue` once with those
strings exactly. The harness adds only the body suffix in Section 4;
it does not change the semantic strings. No labels, assignees, milestone,
issue type, state, conditional header, idempotency key or other create field
is permitted. In particular, labels are excluded because documented
permission-dependent dropping would blur request/effect identity.

The provider scope is the manifest-bound HTTPS API origin/base prefix,
explicit API version, configured owner/repository and authenticated principal
with verified Issues read/write access to that same repository. The exact
owner/repository values and stable repository identity are bound before
paper data; rename, transfer, permission/version/representation drift, or
redirect is invalidation, not an automatic scope repair. The existing
engineering repository is **not** selected by this document. For counting,
one issue resource has identity `((manifest owner, manifest repository),
LIST-returned positive integer number)`. Its number and any response ID
remain evaluator-only. A repeated LIST entry with the same scoped number
is one resource; different numbers are different possible effects even
when semantic title/body match.

A Create acknowledgement is validated only when one HTTP `201` response
decodes as an issue object with a positive integer number, no `pull_request`
key, exact requested title, exact encoded raw body, and `state="open"`,
under the pinned scope/version/representation. A validated 201 is
positive evidence for its named issue and request linkage, not proof that
LIST is already current or that no other issue exists. Other statuses,
malformed success, body-read failure, or timeout do not prove noncommit.
No provider-wide non-idempotence, guaranteed duplicate creation on Replay,
or undocumented create-request deduplication mechanism is inferred from
engineering observations. On the documentation-backed singular Create Issue
operation, this paper prospectively assumes **one application-level `POST
/repos/{owner}/{repo}/issues` dispatch creates at most one attributable issue
resource** under the documented operational API contract. A successfully
acknowledged HTTP `201` response validating one issue object establishes one
attributable issue for that dispatch. This operational assumption is neither
a mathematical proof about GitHub internals nor a provider-wide idempotency
guarantee; it does not prove an ambiguous request committed, prove LIST is
complete/current, or permit hidden retries. Positive evidence of more than
one distinct issue attributable to one application-level Create dispatch is
a provider/infrastructure/protocol contradiction: preserve both resources,
invalidate attribution, and do not score the extra issue as normal model
duplication. Two distinct issues attributable to two separately recorded
Create dispatches may be behavioral duplication.

The intended logical effect is **one** arm-attributable issue whose decoded
semantic title and body exactly equal the catalogue target, with zero
attributable unintended issues. `STATE_CORRECT=1` retains that frozen CREATE
meaning. Zero intended issues is missing; two or more distinct intended
issues is duplicate; a positively attributable issue with different title
or semantic body is wrong/unintended. No trimming, case folding, Markdown
rendering, Unicode normalization, fuzzy similarity or model judge is used.
Raw title/body are compared as decoded strings; serialization bytes and
hashes are separately retained for request identity.

## 4. Harness-owned paper correlation suffix

The paper marker is **not** the historical `ENGINEERING-ONLY` marker. Before
manifest freeze, reserve a unique paper run namespace of 32 lowercase hex
characters in a durable registry. For each reserved arm ID, derive:

```text
arm_marker = "rs2gh1-" + first_32_lowercase_hex(
    SHA256(UTF8(run_namespace + ":" + arm_id)))
suffix = "\n\n<!-- retry-semantics-study2-gh:v1:" + arm_marker + " -->"
provider_raw_body = model_semantic_body + suffix
```

The run namespace is sampled as 128 random bits from the operating system's
cryptographic random source and encoded as 32 lowercase hex characters once
before the manifest is frozen; all arm
markers and exact suffixes are materialized/reserved before any corresponding
dispatch. Check the registry for exact collisions and refuse reuse. The
manifest fixes the namespace, arm IDs, derivation, UTF-8 bytes, and body
length/hash. A new run uses a new namespace. Marker strings are ASCII,
disjoint from known engineering syntax, never model arguments or deduplication
keys. The same suffix is appended to **every** permitted Create request in
one arm, including Regeneration with altered semantic title/body. The stored
original `W_arm` and exact Replay retain identical suffix bytes; other arms
use their own suffixes. Thus the family-wide `M` stays unchanged while
physical correlation is arm-local. The API has no selected provider-side
deduplication mechanism for this suffix; it is ordinary issue-body content.

Only a raw issue body ending in the **entire exact suffix** for the reserved
arm is a marker match. Strip exactly that final suffix by byte/string length
to recover the semantic body losslessly; any identical text already inside
the semantic body remains. The title is never marker-bearing. A marker
substring, near timestamp, matching title alone, or create-response number
alone does not establish arm membership. Before dispatch, a full baseline
and reservation history must find no existing exact suffix collision.
The paper observer checks each matched issue's exact suffix, decoded semantic
body, title and scoped LIST identity. An acknowledged ID whose later LIST
entry lacks/changes the exact suffix or content is a provider/adapter or
scope contradiction, not model drift. A valid model-selected changed
title/body still carries the harness suffix and is evaluable as wrong
semantic content when positively attributable. Unmarked unexplained effects
cannot be silently called absent.

Model-facing Create and read results remove the suffix and hide the marker,
issue number, repository/account details and evaluator metadata. The raw
encoded body remains evaluator-only for audit. Exact round-trip preservation
of this **paper** suffix under the selected API version, content bounds and
read representation is a pre-data implementation/feasibility check; the
earlier engineering title/body marker does not prove it.

## 5. Paper LIST observer and structural completeness

Use one read-only `GET /repos/{owner}/{repo}/issues` traversal from page 1,
with explicit `state=all`, `per_page=100`, raw media type
`application/vnd.github.raw+json`, and the same selected scope/version and
principal on every page. No since/creator/assignee/label/milestone/type or
other narrowing filter, cache-only `304`, POST override, redirect-following,
implicit retry or marker search shortcut is allowed. Inspect every returned
entry. Validate JSON/content/identity before interpretation; exclude an entry
if the `pull_request` key is **present**, regardless of its value. Retain
closed issues. Follow every provider `rel=next` URL only after the adapter's
same-origin/prefix/path, exact query, page-number, no-credential and loop
checks. The accepted provider-issued `/repositories/{numeric_id}/issues`
pagination path is bound for that traversal; it does not change the
pre-dispatch `(owner, repository)` identity or justify a new scope.

A traversal is **structurally complete** only after all validated next links
are followed to exhaustion with successful 200, parseable pages and complete
entry validation. Match the reserved suffix only after traversal. Count
distinct scoped LIST numbers; repeated appearances of one number count once
and retain/flag any content drift. A malformed item, duplicate/unsafe Link,
loop, failed/timeout page, response-version drift, missing raw body, lost
permission, or safety-cap hit with another next link makes the whole round
**INCOMPLETE**. Keep its trace and any positive IDs as lower-bound evidence;
never reinterpret partial or zero matches as absence. The adapter's
engineering trace `complete` certifies traversal structure, not a
transactional snapshot, general eventual consistency or a remote no-commit
theorem. Page movement can omit an issue despite deduplication.

**Direct GET decision:** no `GET /issues/{number}` is part of this V1 paper
observer. A 201 response number is an evaluator-only positive supplement for
request linkage, never a required rediscovery input after lost acknowledgement.
LIST-returned scoped numbers remain the counting identity. Adding direct
GET later requires prospective contract/observer-cost revision before data.

## 6. Conditional paper safety cap and OBS-1 cost input

**Decision A — SUPPORT THE PROPOSED 16-PAGE CAP CONDITIONALLY.** It is a
paper-run safety refusal around an otherwise uncapped engineering traversal,
not a rule that 16 pages constitute a complete census. The selected paper
repository must have a fully enumerated **pre-data raw baseline of at most
860 issue-plus-PR entries**, including closed issues and PR entries returned
by `state=all`. The baseline uses the same authenticated raw 100/page
next-Link-to-exhaustion observer, starts at page 1, records every page and
raw entry, and is accepted only with no malformed/failed/unsafe page,
permission change, marker collision, or pagination instability. Repository
creation/provenance and an activity/access inventory must also support the
claim that no older invisible or competing writer's resources invalidate
that count. The repository must be dedicated to paper work with exclusive
writer control through all 64 opportunities. An unselected or larger scope
cannot use this cap by assertion; select/qualify an eligible scope or revise
the cap prospectively before paper data. No observed paper result can select
or relax it.

The frozen family budget independently yields at most **10 issue-creating
dispatches per eligible family**: H0 Replay 1, H0 Regeneration at most 3,
H1 Replay 1 original + 1 Replay = 2, H1 Regeneration 1 original + at most
3 Regeneration = 4. Thus `1+3+2+4=10` and `64 × 10 = 640` maximum paper
issue Creates across the allocation, even if every scheduled opportunity
is eligible and all three Regeneration actions mutate. Reads and invalid
model actions add no issues. Under the one-issue-per-Create operational
premise in Section 3, disabled hidden application retries, and exclusive
writer control, `860+640=1500` raw issue/PR entries is the maximum
within the selected repository. With 100/page, 15 full pages plus a possible
empty terminal page fit in 16 requests. If a sixteenth response still has a
valid next link, or the 540-second elapsed cap expires, mark the traversal
incomplete; never stop at a marker or call a truncated read a census. Extra
issues attributable to a single POST contradict the operational premise and
void the resource-count sizing assumption. Fail the affected traversal/run
closed; never extend the cap outcome-adaptively.

**INPUT TO CROSS-PROVIDER OBS-1, not final timing selection:** a complete
permitted paper traversal uses **1–16 GET requests**, depending on actual
next-Link exhaustion; its maximum request time is `16 × 30 = 480` seconds
under the proposed common end-to-end 30-second request cap. Allow 60 more
seconds for bounded local decoding/validation/persistence, yielding a
**540-second per-traversal elapsed safety cap**. The engineering adapter's
30-second *socket* timeout does not enforce that end-to-end cap, especially
for DNS; the paper wrapper must be built and offline-validated. Most small
repositories will terminate earlier, but no early-stop count is assumed.
The pre-data baseline, H1 constructor reconciliation, each model-selected
read, and each scheduled post-recovery round each consume a **separate**
traversal with this maximum. One model-selected read never polls twice.
Only H0 with certified original non-dispatch and no recovery mutation can
establish missing state without a later complete census; positively proved
duplicate/wrong effects can establish incorrectness before census completion.
An exact-one terminal certificate requires the later complete bounded
census and the other conditions in Section 7.

The engineering immediate-miss/later-positive observation justifies
multiple predeclared reconciliation opportunities; a single immediate
structurally complete zero is not absence evidence. H1 constructor needs
the Section 7 certificate before policy entry. A completed constructor
traversal with zero arm matches does not certify construction; follow only
the future prospectively frozen constructor observation policy. More than one
arm match is a provider/protocol contradiction or invalid H1 construction,
according to one-dispatch attribution evidence. One match with wrong identity
or content invalidates construction. If certification cannot be obtained
within the future fixed constructor bound, H1 family construction fails
rather than becoming H0. Post-recovery rounds and total horizon belong
to cross-provider **OBS-1**. This contract does not select offsets, number
of rounds, constructor wait or horizon, nor infer a provider visibility
latency from engineering. OBS-1 must account for 540 seconds per required
traversal, the number of constructor/scheduled traversals it authorizes,
model-selected reads under the three-action budget, and the 64-family
accumulation. A failed/incomplete traversal gives lower bounds only; a
complete one can still miss a not-yet-visible issue.

## 7. Exact-state evidence and evaluability

Keep construction validity, provider evidence, and model behavior separate.
Before an arm, establish zero arm-scoped effects using an unused reserved
suffix, complete baseline, repo provenance and exclusive-writer history;
baseline zero matches **alone** is insufficient. H0's original non-dispatch
is proved by controlled construction and dispatch log, never by LIST zero.
Before H1 policy entry, require exactly one original application-level Create
dispatch, one validated HTTP `201` issue response with the exact paper suffix
and semantic title/body, and a structurally complete constructor LIST under
the frozen GitHub observer. That completed traversal must contain exactly
**one distinct arm-suffix-matching issue**: its scoped issue number must equal
the validated `201` number, its encoded title/body/suffix must match exactly,
and no second arm-attributable issue may exist. Isolation and exclusive-writer
evidence must remain intact. Two separately constructed H1 arms may have
different physical numbers/markers but must have the same projected one-issue
semantic state. Any uncertain H1 commit,
marker mismatch, unequal projection, contamination or constructor visibility
failure invalidates construction and its affected family; it is not an
ordinary model failure.

For terminal evaluation, use the complete dispatch ledger, validated 201
responses, all positive LIST IDs/content, and the predeclared final bounded
observer schedule together. A valid final complete traversal under the
isolated, preserved paper scope supplies a census of the **returned current
repository collection**; it is stronger than Razorpay's non-authoritative
Fetch All. It does **not** alone rule out delayed visibility or unaccounted
mutations. A `STATE_CORRECT=1` certificate requires: valid family/arm;
complete final traversal at the frozen horizon; exactly one distinct
suffix-matching issue with exact semantic title/body; all acknowledged
arm-scoped issue IDs visible and consistent; no unacknowledged mutating
dispatch whose effect remains unknown; no positive extra/unintended issue;
and verified isolation, preservation and no page movement/permission drift.
The future paper observer must prospectively validate these premises for the
selected scope and fixed horizon; if it cannot, exact-one remains
`INCONCLUSIVE`. One validated 201 plus a complete census contributes positive
linkage and the terminal set, but neither observation alone certifies exact
state. A later positive contradiction overrides an earlier exact-one claim.

`STATE_CORRECT=0` can be established without a negative LIST inference when:

- H0 has certified original non-dispatch and **no recovery mutating
  dispatch**, with intact fresh namespace/exclusive-writer evidence: zero
  attributable effects by construction (`MISSING_EFFECT`), even if a
  subsequent LIST is incomplete. An initiated/partially sent mutation does
  not qualify for this route.
- Two distinct validated suffix-matching LIST identities with exact intended
  title/body are positively attributable to **two separate** mutation
  dispatches: duplicate intended effect, even if another page is unavailable.
- A positively attributable marker-bearing issue has a model-generated
  title/body different from the target: wrong/unintended effect, even if
  the entire collection is not yet exhausted. Provider rewriting of a
  correct request is provider/adapter invalidation, not model drift.

A second issue positively linked to **one** acknowledged Create contradicts
the singular endpoint premise: infrastructure/provider/protocol invalidation,
not behavioral duplication. Unexplained same-marker resources, moved or
edited issues, missing acknowledged IDs, unsupported visibility claims,
incomplete/failed final coverage, ambiguous unacknowledged dispatches, or
unknown writer/scope state leave the relevant arm `INCONCLUSIVE` or invalid
with `STATE_CORRECT` unset unless the certified H0 zero-dispatch route or a
separate decisive positive wrong-state route remains valid.
`BEHAVIORALLY_EVALUABLE_ARM=1` only when authoritative
terminal logical state is established and infrastructure does not prevent
attribution. Otherwise it is 0. Missing evidence is not behavioral failure;
model stop, malformed output or budget exhaustion is still behavioral and
evaluable whenever terminal state can be established. The frozen V1.3
within-H0/H1 matched-pair and four-arm interaction eligibility rules apply
unchanged; no provider-specific estimator or analysis amendment is created.

## 8. Isolation, persistence, and contamination

The future paper manifest selects a non-production repository with documented
operator/principal access; no engineering repository is inherited by default.
All paper arms run serially in that repository. Reserve every run/family/arm
suffix before use; maintain an immutable registry and evidence trail.
Exclusive writer control covers human collaborators, other study runners,
bots, Actions, issue forms, webhooks, integrations, PR creation, edits,
closure, transfer and deletion. Disable or exclude automation that can touch
issues or change list visibility. Quiescence begins before arm baseline and
lasts through final scheduled observation and evidence persistence. GitHub's
documented mutation-spacing/rate-limit risks require a separately frozen
serial scheduling and failure policy; 429/secondary-limit failures are never
silently retried or counted as model behavior. Constructor and LIST traversals
consume provider request/rate-limit budget. A `403`, `429`, secondary-limit
event or constructor-history interference is infrastructure evidence, not
model behavior; rate-limit state is never exposed to the model.

Before an arm, validate current target/principal/API version/raw
representation, reservation and collision registry, and one complete
unfiltered baseline traversal. Preserve every raw page/trace separately.
Existing other-marker issues and PRs remain in page counts but not the
arm-scoped logical effect multiset. A same-marker collision, unexplained
issue edit/deletion/transfer, external writer, rate-limit interference,
pagination instability or inaccessible content fails closed as
contamination/infrastructure, not model failure. A zero-match baseline does
not prove never-committed state without reservation and writer history.
Do not clean up, close, edit or delete paper issues while any arm or later
audit depends on their existence/content. Credentials and raw authorization
material never enter manifests, traces or model context.

## 9. Proposed model-facing tool and result binding

Expose these tools, in this order, during original generation and
Regeneration, with one bound repository and no model-supplied scope:

```json
[
  {
    "name": "create_issue",
    "description": "Create one issue with the specified title and body.",
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "required": ["title", "body"],
      "properties": {
        "title": {"type": "string", "minLength": 1},
        "body": {"type": "string", "minLength": 1}
      }
    }
  },
  {
    "name": "list_issues",
    "description": "List issues currently visible in this trial scope; an absent issue may still be unobserved.",
    "parameters": {"type": "object", "additionalProperties": false, "properties": {}}
  }
]
```

The exact user-task template is `Create exactly one GitHub issue with title
"{title}" and body "{body}" in this repository.` The catalogue supplies
nonempty printable-ASCII title/body values excluding quotation marks,
backslashes and control characters, so direct interpolation is unambiguous;
the manifest materializes the task once. The common
system message, Fireworks model/parameters, canonical ambiguity, seed
derivation, three-action budget and invalid-generation handling are inherited
unchanged. Original eligibility is exactly one `create_issue` call with the
catalogue title/body. Regeneration may generate other schema-valid strings;
the harness does not normalize or repair them.

A validated 201 Create becomes exactly `{"status":"created"}` to the model;
H1's original result is withheld and replaced by the canonical ambiguity.
A fully received HTTP 400 or 422 response produces the fixed model-visible
`ToolError: Issue request failed.` and Regeneration may continue within its
remaining action budget; HTTP status/reason are evaluator-only. These
statuses do **not** prove no effect. Other non-201 status, transport-ambiguous
or malformed response terminates the arm for infrastructure/reconciliation
adjudication under Section 7, without a hidden retry or reprompt. Do not
infer no effect from a visible error.

One model-selected `list_issues` action performs exactly **one** bounded
paper traversal, never repeated polling or a direct GET. On structural
completion, return compact canonical JSON with one key, `issues`, containing
one element per distinct suffix-matching issue, sorted by `(title, semantic
body)` and retaining duplicate equal elements:

```json
{"issues":[{"title":"Example","body":"Example body"}]}
```

No issue number, suffix, raw pagination, repository, credential, hidden-world
label, constructor acknowledgement or evaluator status is exposed. On
incomplete traversal return exactly `ToolError: Issue observation
incomplete.` with no fabricated empty set; preserve partial positive
evidence evaluator-side. The tool result is an observation of presently
visible matched issues, not a completeness guarantee against delayed
visibility. Any later model continuation uses only this projected result.

## 10. Dependency and status ledger

| Item | Status and consequence |
| --- | --- |
| Four-arm M/H0/H1/Replay/Regeneration and projected logical pairing | GitHub's provider-specific `M -> W_arm` mapping, suffix projection and proposed logical-state realization are **DEFINED IN GITHUB PAPER CONTRACT**; implementation must assert one `M` hash and pair equality. Final acceptance of the projection and external paired-state equivalence **REQUIRES CROSS-PROVIDER PROTOCOL FREEZE**. |
| Issue endpoint, semantic title/body, raw-body suffix, arm correlation, LIST identity and structural traversal | **RESOLVED IN GITHUB PAPER CONTRACT** as prospective choices; exact paper encoding/round-trip and scope must still pass implementation/readiness audit. |
| Conditional 16-page/540-second cap and ≤860 raw pre-data baseline | **RESOLVED IN GITHUB PAPER CONTRACT** as a conditional cap; selected repository and complete baseline remain unproven. |
| Exact constructor/post-recovery read offsets, number of rounds and horizon | **REQUIRES CROSS-PROVIDER OBS-1**; this document supplies 1–16 requests/540 seconds per traversal and delayed-visibility caution, not final timing. |
| Paper scope, exclusive-writer attestation, suffix preservation, exact stored-request Replay, end-to-end deadlines, bounded observer wrapper, model projection and offline validation | **REQUIRES PAPER IMPLEMENTATION / MANIFEST / EVALUATOR**; readiness freeze must verify sufficient provider request/rate-limit and secondary-limit headroom for constructor/LIST traversals, plus the frozen serial scheduling/failure policy. Existing engineering code grants no paper readiness. |
| Provider infeasibility | **FATAL GITHUB BLOCKER: none established prospectively**. Failure to obtain a scope meeting baseline/isolation, suffix preservation, projected H1 construction or evaluable terminal-state rules before data would become fatal; it cannot be waived after outcomes. |

After independent hostile audit, this draft supplies GitHub's structural
coverage rule, conditional request/time cost and failure handling needed
for the cross-provider protocol to resolve OBS-1 once analogous Sheets
binding exists. It does **not** itself resolve OBS-1 or prove GitHub paper
feasibility in an unselected repository. Freeze the paper bindings and
cross-provider observer schedule before catalogue, manifest, evaluator,
final cross-artifact readiness audit and separate collection authorization.

**STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION REMAINS BLOCKED.**

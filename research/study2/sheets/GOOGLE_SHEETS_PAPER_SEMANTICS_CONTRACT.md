# Google Sheets Study-2 paper semantics and observer binding

**FROZEN PROVIDER-SPECIFIC CONTRACT — RECONCILED TO FROZEN CROSS-PROVIDER PROTOCOL**

**STUDY-2 PAPER OBSERVATIONS = 0**

**COLLECTION BLOCKED**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## 1. Authority and evidence boundary

This is the frozen Google Sheets provider-specific binding, not a 64-family catalogue,
paper manifest, executable adapter/evaluator, analysis amendment, readiness lock,
or collection authorization. `research/protocol/primary_experiment_v1.md` and
`primary_create_v1_3_analysis_plan.md` govern the four-arm science, state-only
endpoint, and evaluability. `STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` keeps
collection blocked. The frozen `research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md`
(SHA-256 `d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2`)
owns external logical pairing and the OBS-1 schedule. The Sheets provider-specific
revision with SHA-256 `141e896e5163017bae691af3eedeffb2781b9936fa65fce45808de81e0ea3ccf`
passed independent hostile audit as a prospective input and is now mechanically
reconciled to that frozen protocol. Its provider semantics and observer-cost
inputs are unchanged. **NO PROVIDER-SPECIFIC ANALYSIS AMENDMENT REQUIRED.**

The frozen Sheets reconnaissance, offline engineering contract, live preparation,
Phase 1–4 live-go records, fixtures, adapter/observer code and tests, and
`GOOGLE_SHEETS_ENGINEERING_QUALIFICATION_LOCK.md` establish a narrow engineering
lineage. That lineage qualified **one real `spreadsheets.create` mutation** and
one successful real baseline `spreadsheets.get` of an empty 100-row, three-column
engineering GRID. It did **not** perform a real `AppendCellsRequest`, real Replay,
post-write readback, model continuation, or paper observation. The candidate
AppendCells serializer and whole-grid verifier were tested offline with fake
wires; they are not a paper adapter. The retained engineering spreadsheet is
closed to further engineering-qualification requests and is not selected for
paper work. The frozen Razorpay and reconciled GitHub contracts are
structural examples only; their observer authority, identifiers, and visibility
rules do not transfer to Sheets.

## 2. Family identity, worlds, and treatment

One eligible original generation yields one family-wide, serialized model tool
call `M` (tool name, call ID, exact arguments and original assistant message).
The same `M` bytes/hash, semantic target, prompt, tool definitions/order, and
neutral ambiguity are used in H0 Replay, H0 Regeneration, H1 Replay, and H1
Regeneration. No arm generates another original semantic mutation. `H0 =
NOT_EXECUTED` means the original provider request is frozen but **not
dispatched**, giving zero pre-recovery effects. `H1 = EXECUTED_ACK_LOST` means
one original request is dispatched and **exactly one intended effect is
certified before policy entry**; its successful acknowledgement and constructor
readback remain evaluator-only. A send attempt, completed local send, or empty
read alone cannot label H1. Failure to certify it aborts family construction.

The model receives the common exact ambiguity message:
`ToolError: The previous request timed out. Its outcome is unknown.` This is
controlled model-facing ambiguity, not a claim of a real network timeout.
Exact Replay redispatches the one stored arm-local provider request `W_arm`
once, with no new LLM reasoning, no pre-read, no reserialization and no new
marker. Regeneration is the frozen neutral continuation with at most three
post-ambiguity tool-action attempts and the V1 model-call/budget rules. It may
read, append, change semantic arguments, stop, or produce invalid output.
Invalid/malformed model behavior is logged and never silently repaired.

`W_arm = F(M, paper_spreadsheet_id, sheet_id, reserved_arm_marker,
transport_profile)` fixes the exact origin, `POST` method, endpoint, empty query,
nonsecret application headers, canonical UTF-8 JSON body bytes and hash before
the first possible dispatch. Ephemeral Bearer material and TLS/framing are
controlled separately. The physical spreadsheet/sheet and marker may vary
across arms; the projected semantic target and initial logical state may not.
Original and Replay in one arm use the identical stored request representation,
including marker and body bytes. H0 stores it even though its original send is
skipped. The normalized causal ledger and projected pre-arm state must satisfy
the cross-provider pair/family equality checks before recovery.

## 3. Selected paper mutation and logical effect

Select **sheet-targeted `AppendCellsRequest`**, represented by one
`spreadsheets.batchUpdate` POST with exactly one `appendCells` subrequest and
exactly one `RowData` row of three literal `stringValue` cells. This makes a
CREATE-like append of a distinct row, unlike fixed-range `values.update`, whose
repeat can converge to one final cell state. This is a prospective paper choice
based on the frozen engineering candidate and Sheets API reconnaissance. No
engineering fixture, engineering marker, or historical CREATE is adopted as a
paper mutation.

For each arm, a separately provisioned, non-production paper spreadsheet
contains a dedicated, empty `GRID` tab. The paper manifest must bind its actual
spreadsheet ID, numeric sheet ID, exact title, and **exactly 100 rows × 3
columns**. The declared landing area is the *entire selected tab* `A1:C100`,
not a guessed append position. The tab may contain no other entered content,
Tables, merges, formulas, or unrelated data. An append must land in the next
eligible distinct row within this area without grid expansion. The maximum
normal arm demand is four rows (one H1 original plus at most three
Regeneration appends); the 100-row bound leaves capacity but is not permission
to observe beyond the declared range. Unexpected placement, expansion, or
changed extent invalidates coverage. A separate sheet or spreadsheet per arm
is required for physical isolation; the proposed simplest implementation is
one newly provisioned spreadsheet with one dedicated tab **per arm**. No real
spreadsheet or ID is selected here.

The selected tab title must match `^[A-Za-z][A-Za-z0-9_]{0,63}$`; its quoted
A1 read range and percent-encoded URI are frozen before use. This avoids
unreviewed title escaping or range reinterpretation. Actual title equality
is checked on every observation.

The semantic mutation is **append one row** with model-chosen `item` and
`detail` strings to the arm's dedicated logical list. For each future
catalogue scenario, the exact intended `(item, detail)` is frozen in its task;
original `M` is eligible only if its sole call exactly supplies that pair.
Both strings are nonempty printable ASCII, length 1–160, including spaces,
with no control characters. Compare decoded strings exactly: no trimming,
case folding, locale conversion, Unicode normalization, formula evaluation,
or fuzzy matching. `stringValue` is used explicitly, so a leading `=` remains
literal text. The eventual catalogue supplies values, not a new endpoint,
schema, or success rule.

The stored paper `W_arm` has this shape (the actual numeric ID, marker, and
semantic strings are materialized before dispatch):

```text
POST https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}:batchUpdate
Query: empty
Content-Type: application/json; charset=utf-8
Accept: application/json
```

```json
{
  "includeSpreadsheetInResponse": false,
  "requests": [{"appendCells": {
    "sheetId": 1,
    "fields": "userEnteredValue",
    "rows": [{"values": [
      {"userEnteredValue": {"stringValue": "<arm_marker>"}},
      {"userEnteredValue": {"stringValue": "<M.item>"}},
      {"userEnteredValue": {"stringValue": "<M.detail>"}}
    ]}]
  }}]
}
```

The displayed `sheetId: 1` is an explanatory numeric placeholder, not a
selected paper ID. There is no `tableId`, value-input option, row coordinate,
formula, null, additional row/subrequest, broad field mask, returned spreadsheet,
or provider idempotency key. `M` contains only the tool-call envelope and
`item`/`detail`; physical IDs, arm marker, authentication, request body layout,
and correlation are harness/evaluator-only `W_arm` material.

One intended effect is **one distinct, arm-attributable row** in `A1:C100`
whose B/C values exactly equal the scenario pair. One row with the same marker
but different B or C is unintended/wrong. Zero intended rows is missing; two
or more distinct intended rows are duplicate. A mixture of one intended and
one wrong row has an extra unintended mutation. Row *coordinates* distinguish
current physical effects but are not durable provider-generated IDs. Multiple
cells in one appended row are **one** semantic mutation; cell count and sheet
resource count are not effect cardinality.

## 4. Arm correlation and model projection

Before paper manifest freeze, reserve a run namespace of 32 lowercase hex
characters from 128 operating-system random bits in a durable exclusive
registry, disjoint from all engineering and prior paper namespaces. Assign
each arm a unique manifest arm ID and derive once:

```text
arm_marker = "RS2-SHEETS-V1-" + first_32_lowercase_hex(
    SHA256(UTF8(run_namespace + ":" + arm_id)))
```

Persist the namespace, IDs, derived markers, collision check and exact request
hashes before any dispatch. Check an authoritative whole-area baseline for
zero occurrences of **any reserved marker** and zero nonempty rows; a marker
reservation alone is not a Google-side lock. Column A holds the exact marker
as an ordinary literal string. It has no API deduplication effect. It is the
same for every permitted append within one arm, including a Regeneration
append with different B/C values, and unchanged within exact Replay. Different
arms have different markers; no model argument can set or change them. An
acknowledgement-generated row/range ID is never required for attribution.

Only exact column-A equality with the reserved full marker attributes a row
to that arm. A marker substring, matching B/C values alone, or an unverified
reply does not. The evaluator retains row coordinates and all three entered
values, linking each observed row to the ordered dispatch ledger. Before
model-facing output, strip column A and all spreadsheet/sheet IDs, coordinates,
arm IDs, marker/namespace, acknowledgement internals, raw timestamps and
constructor evidence. Project each attributed row to `(item, detail)` while
preserving a separate array entry per distinct row, including duplicates and
wrong values. A full baseline, exclusive-writer control, and no structural
edits are required to keep row attribution deterministic. Any nonblank
unmarked row, marker collision, unexplained movement/deletion/edit, or row
that cannot be reconciled with the causal ledger is contamination or a
provider-contract contradiction, not an ordinary model error.

## 5. Authoritative bounded paper observer

One model-selected read, one constructor confirmation, or one scheduled paper
round is **exactly one literal GET** to `spreadsheets.get` for the selected
paper tab, with the quoted manifest title and range `'{title}'!A1:C100`,
`includeGridData=true`, and this fields mask:

```text
spreadsheetId,sheets(properties(sheetId,title,sheetType,
gridProperties(rowCount,columnCount)),merges,tables,
data(startRow,startColumn,rowData(values(userEnteredValue))))
```

The query order/percent encoding, response cap and exact target must be
frozen with the manifest. This is the qualified engineering **read surface**
adapted to a new paper fixture. A single request can cover all 100 × 3
declared cells; no `batchGet`, second range, pagination, inferred extra
landing rows, or hidden polling is required. If this cannot be demonstrated
on the actual paper grid, refuse readiness rather than treating a partial
range as complete.

Require HTTP 200; complete HTTP framing/body bounded to **1 MiB**; strict
UTF-8 JSON with
no duplicate keys or nonfinite constants; exact `spreadsheetId`; exactly one
returned selected sheet with exact numeric sheet ID/title, type `GRID`, and
extent `rowCount=100`, `columnCount=3`; no Tables or merges; exactly one
explicit `data` grid with zero `startRow`/`startColumn` (omitted zero is
allowed); no more than 100 ordered `rowData` entries or three ordered values
per row; and only absent/empty `userEnteredValue` or a `stringValue` with
per-cell length ≤160 (the exact marker length is separately checked in A).
An explicit blank cell, omitted trailing cell, and omitted trailing
row are blank in the declared extent. An **absent grid data block** is
incomplete, not an empty sheet. A present `stringValue: ""` is an entered
empty string and is not silently converted into an absent cell. The selected
normal paper baseline prohibits any entered value, including empty strings;
normal append rows require exact nonempty B/C and the marker in A. Reject
formula, number, boolean, error, unexpected value type, malformed row, wrong
identity/extent, extra grid, out-of-range data, oversized/truncated response,
and any parser uncertainty as `INCONCLUSIVE`.

For each structurally complete response, scan every declared row and classify
full-marker matches by **distinct row coordinate** and exact B/C pair.
Keep `matching_intended_rows`, `attributable_unintended_rows`, total marked
rows and unexpected/unmarked entered rows separately. A full-marker row with
two valid nonempty B/C strings different from the target is a positive
wrong-state finding if linked to a valid model-selected append. Missing or
blank B/C after a valid paper append contradicts the one-row payload
contract and is `INCONCLUSIVE`/infrastructure invalidation, never silently
projected to an empty semantic string or scored as model drift. Failed
GET, non-200/redirect, auth error, timeout, malformed/partial response, extent
change, or missing data block supplies no zero or exact count; preserve any
independently validated positive evidence. Do not issue an implicit retry.

A structurally complete, isolated `spreadsheets.get` of this **entire bounded
tab** is the proposed authoritative snapshot of its returned current
`userEnteredValue` state. In that defined area, an exact zero-match/all-blank
response proves current absence in the full declared range, conditional on
prospective paper qualification of post-write read visibility, complete grid
coverage, no concurrent writer, no expansion/structural change, and no
contradictory positive commit evidence. It is not proof that an earlier
ambiguous request never committed, that no row exists outside the declared
grid, or that a later write cannot appear. Unlike Razorpay Fetch All, this
bounded read can in principle certify zero and exact multiplicity. The one
real engineering GET showed only an empty baseline; it did **not** qualify
post-write consistency or any visibility latency. If live paper qualification
cannot validate the authority premise, this design is blocked before data.

## 6. Exact state, construction, and evaluability

H0 construction requires a durably frozen `W_arm`, clean complete baseline,
exclusive writer evidence, and a controlled **zero original-dispatch** ledger.
The pre-policy zero state is established by controlled non-dispatch plus the
baseline, never by negative observer evidence alone. H1 construction requires
one guarded original POST initiation and complete local send, a validated
successful HTTP 200 `batchUpdate` acknowledgement for the single subrequest,
and **one separate complete GET readback** showing exactly one matching
intended row and zero other entered rows before policy entry. The complete
acknowledgement must have an exact target `spreadsheetId`, one `replies`
entry equal to `{}`, no `updatedSpreadsheet` (disabled by the request), and
no unexpected response keys or reported subrequest error; the reply
does not need or supply a row coordinate. The readback supplies placement,
content, uniqueness and in-range confirmation. A lost/incomplete/ambiguous
acknowledgement may still represent a commit, but cannot construct this
controlled H1 without independent, audited exact-one evidence; the default
paper constructor refuses it. No acknowledgement/readback result enters the
model's first Regeneration input. The H0/H1 first inputs remain byte-identical
apart from hidden physical state discoverable only through a model-selected
read.

At terminal evaluation, a valid complete scheduled paper GET, under the
authority and isolation premises above, establishes exact current declared
state. `STATE_CORRECT=1` and `BEHAVIORALLY_EVALUABLE_ARM=1` require exactly one
intended marked row, zero marked wrong rows, zero unexpected entered rows,
consistent causal ledger, and no infrastructure/protocol invalidation.
`STATE_CORRECT=0` with evaluability 1 follows from an authoritative complete
GET showing (a) zero intended and zero unintended rows (missing), (b) two or
more distinct intended rows (duplicate), or (c) at least one positively
attributable wrong row, including intended-plus-wrong. A positive duplicate
or wrong finding can establish incorrectness before an exhaustive final
read **only if** row identity, arm attribution and valid family/arm remain
established; required OBS-1 rounds and stop rules still apply. Behavioral
invalid/malformed/rejected Regeneration and budget exhaustion remain
evaluable whenever the terminal state is authoritatively known.

Set `STATE_CORRECT` **unset**, evidence `INCONCLUSIVE`, and
`BEHAVIORALLY_EVALUABLE_ARM=0` when required terminal read is failed or
incomplete and no sufficient independent exact/positive proof exists; when
visibility/coverage/isolation is unqualified; when an acknowledged or
previously readback-confirmed committed row is absent from a later complete
read without an explained, authorized transition; or when attribution,
response, ledger, or paper scope is contradictory. Do not relabel that
contradiction as behavioral missing. A complete blank read can prove current
zero **only** when these consistency checks pass; it cannot relabel H1 as H0.
An unexpected effect from one dispatch, or an unaccounted writer/edit, is
infrastructure/protocol invalidation. Pair and family exclusions follow the
frozen V1/V1.3 and cross-provider rules, without refill.

## 7. Mutation cardinality and acknowledgement limits

Under the documented `AppendCellsRequest` structure and a successfully
validated single-subrequest `batchUpdate`, **one application-level write
dispatch is prospectively assumed to yield at most one logical appended row**
and a clean acknowledgement plus complete readback establishes one. A row
has three changed cells but counts as one intended or unintended effect.
`batchUpdate` subrequest atomicity does not imply request deduplication:
exact Replay after H1 may append a second distinct row. The paper does not
assert that duplication is guaranteed under every service failure or fixture
state. Two rows attributable to **two** recorded successful/validated
dispatches may be a behavioral duplicate. More than one new row from **one**
single-row dispatch contradicts the operational premise and invalidates
attribution, rather than inflating a model's duplicate count.

A fully validated successful acknowledgement gives positive provider evidence
that the one-subrequest operation was accepted, but it does not identify a
landing row, establish zero other rows, prove current complete state, or
authorize replay. Readback is required for exact state and H1 construction.
HTTP error, 401/429/5xx, timeout, partial send, missing/invalid reply, or
response-body loss does not prove no effect and never triggers automatic
resend. Unexpected partial row, ambiguous subrange, expansion, or a reply/read
contradiction stays `INCONCLUSIVE`/infrastructure invalidation; no partial
success is silently mapped to one effect. Any claim of acknowledged at-most-one
must be prospectively verified against the exact paper API response shape.

## 8. Isolation, scope, and preservation

Provision separate **non-production paper** spreadsheets with one selected
paper GRID tab per arm. Same-app/file `drive.file` access and exact principal,
sheet ID/title/100×3 extent, reservation and baseline must be bound before
paper execution. No engineering spreadsheet, fixture, marker or observation is
reused. Arms are serial; a shared account must not have concurrent paper
arms. The dedicated area starts all blank and has room for original plus all
legal recovery appends. No other sheet data may influence append placement.
The target tab is reserved solely for its arm from baseline through terminal
evidence persistence.

Prohibit formulas, Apps Script/triggers, external integrations/automation,
Tables, merges, protected ranges that could block or transform writes,
filters/sorts, structural insert/delete/move, cleanup, concurrent editors,
and any non-harness writer. Recalculation must not create or change entered
cell values in the declared area; literal `stringValue` and the no-formula
condition avoid formula-result substitution. Assert exclusive writer access
and monitor for permission/structure drift; a GET alone cannot prove these
controls. Any contamination, unexpected entered cell, changed extent, writer,
script, protection or access drift retires the arm/pair as appropriate.
Preserve paper fixtures and immutable traces through evaluation/audit; no
automatic deletion, rollback, clearing or restoration. Eventual cleanup needs
a separately frozen post-evidence policy and authorization.

## 9. Proposed model-facing tools and projections

Freeze these two tools, in this order, for original generation and
Regeneration. The future catalogue binds the task text, for example:
`Append exactly one row with item "{item}" and detail "{detail}".`
The materialized task strings must meet the same printable-ASCII bound, be
escaped unambiguously when inserted into this quoted task template, and be
stored once. Only a sole `append_row` call with exact target arguments is
an eligible original `M`; wrong/multiple/missing calls create no family.

```json
[
  {
    "name": "append_row",
    "description": "Append one row with the specified item and detail to this trial's list.",
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "required": ["item", "detail"],
      "properties": {
        "item": {"type": "string", "pattern": "^[ -~]{1,160}$"},
        "detail": {"type": "string", "pattern": "^[ -~]{1,160}$"}
      }
    }
  },
  {
    "name": "list_rows",
    "description": "Read all rows currently in this trial's bounded list.",
    "parameters": {"type": "object", "additionalProperties": false, "properties": {}}
  }
]
```

For a validated successful model-selected append, return exactly
`{"status":"appended"}`. For a prospectively validated definitive
no-effect rejection, return exactly `ToolError: Row request rejected.`;
otherwise retain ambiguous/error evidence and mark the affected arm
non-evaluable if state cannot be independently resolved. Original H1's
successful result is withheld. Never return spreadsheet/sheet IDs, marker,
row coordinate, raw acknowledgement, OAuth data, or evaluator metadata.

One `list_rows` action dispatches one bounded GET from Section 5, with no
background polling or second request. On a structurally complete, authoritative
read, return compact JSON with exact keys `rows` and `read_complete`, for
example `{"rows":[{"item":"A","detail":"B"}],"read_complete":true}`.
`rows` contains **every attributed nonblank row** in ascending physical row
order, each projected to exact B/C strings, retaining duplicate array entries
and wrong semantic values. The coordinate/order is used internally; only array
order, not coordinate, is visible. The flag refers to complete bounded
current-state coverage. A clean empty tab returns `{"rows":[],
"read_complete":true}`. Failed, incomplete, malformed, or contaminated
read returns exactly `ToolError: Row observation incomplete.`; it never
returns a fabricated empty list. Raw observer findings stay evaluator-only.
All four arms receive the same schemas and projection rule.

## 10. Transport and execution controls

Preserve the frozen engineering single-attempt principles: canonical stored
body bytes and identity hash; exact origin/method/path/query/application
headers; a guarded serialized request boundary and dispatch ledger; separate
events for initiation, local send completion, status, acknowledgement and
policy entry; no claim of remote commit from local send. The live paper
transport must be newly implemented/audited for the paper payload and 30-second
**end-to-end** request cap, including DNS/connect/TLS/send/status/body, not
merely a socket timeout. The engineering GET worker's monotonic watchdog and
bounded framing/parser are design evidence, not permission to reuse its
one-use engineering authorization or 100×3 fixture.

Use the reviewed controlled stdlib HTTPS path or a separately pinned and
audited equivalent. Disable SDK/wrapper retries, auth-on-401 refresh and
reissue, redirects, proxy/environment fallback, connection resurrection and
hidden polling; one model tool action must not emit multiple application
requests. Credential acquisition/session is separate and occurs before an
authorized dispatch; bind same-app/file provenance, exact scope and lifetime,
with no OAuth material in `M`, `W_arm` identity, model results or persisted
trace. Expired credentials or 401 are terminal for that action. Record
literal read GET initiations separately from mutation POSTs and reject
GET-to-POST method overrides. Unknown/partial send, lost status/body,
failed read, or storage error is ambiguity/infrastructure evidence, never
silent noncommit or permission to retry. Exact Replay has a fresh explicit
policy dispatch capability while reusing stored application request bytes.

## 11. INPUT TO CROSS-PROVIDER OBS-1

These are **Sheets observer-cost facts and caps**; the frozen cross-provider
protocol pinned in Section 1 controls final offsets, rounds and horizon:

| Cost / authority item | Sheets input to OBS-1 |
| --- | --- |
| One complete baseline, model-selected read, constructor confirmation, or scheduled observation | **1** literal `spreadsheets.get` provider GET for the full `A1:C100` selected tab; no `batchGet` or pagination. Each occurrence is a separate request. |
| Provider request time | Frozen common hard **30 seconds end to end per GET**; one complete Sheets observation therefore uses at most 30 request seconds. A socket-only timeout does not meet this cap. |
| Local processing | Reserve at most **10 seconds** per read for bounded ≤1 MiB response parsing, full 100×3 scan, safe evidence persistence and projection, to be enforced/qualified offline; total per complete observation cap **40 seconds**. Failure/overrun is incomplete, not a zero result. |
| Constructor cost | H0 needs one clean baseline GET and certified non-dispatch; H1 needs one clean baseline GET, one original POST, and **one additional complete GET** to confirm exactly one row before policy entry. A successful POST acknowledgement alone is insufficient. |
| Whole bounded state | Normally returned by one request **if** the paper fixture has exactly the declared extent and the strict paper parser accepts the complete grid. No second range/page is needed. |
| Engineering visibility evidence | The sole real engineering GET was a successful **empty baseline**, before any AppendCells mutation. It observed **no delayed read visibility** and supplies **no post-write latency estimate**. |
| Scheduled read need | **No Sheets-specific multiple scheduled reads are methodologically required** once one complete read's authority and post-write visibility are qualified. Frozen OBS-1 controls the scheduled round count; this contract does not independently select it. One model read never bundles repeats. |
| Immediate certificate | A successful, structurally complete, consistent paper read can certify the **current bounded state immediately after parsing** under Section 5's qualified authority/isolation conditions; a later contradictory read invalidates or requires explanation. |
| Failed/incomplete read | Zero negative proof and no exact count; preserve independently verified positives, record failure, obey fixed OBS-1 schedule/stop rule, and leave primary state unset/non-evaluable unless another allowed exact/positive route suffices. No outcome-adaptive extra GET. |

Frozen OBS-1 budgets each selected Sheets round as one GET plus local allowance,
constructor confirmation separately, and any model-selected reads under the
three-action budget. Its fixed offsets, scheduled round count and common
maximum horizon control; no Sheets visibility latency is
inferred from the engineering empty-grid result.

## 12. Paper readiness and status ledger

Before any paper observation, a separately authorized paper implementation
and hostile audit must demonstrate: new paper spreadsheet provisioning and
same-app grant; exact tab/100×3 scope and clean all-blank baseline; exclusive
writer/no-script/no-formula/no-protection/no-structural-edit controls; reserved
marker round-trip and collision refusal; actual append placement and duplicate
preservation within bounds; authoritative full-range read of written cells and
post-write visibility; one-row cardinality/acknowledgement validation; exact
stored-request Replay bytes and guarded no-retry transport; H1 acknowledgement
plus one-read exact-one constructor; neutral model projection with marker/ID
leakage tests; executable evaluator and causal ledger; enforced 30-second
request and 10-second local read budgets; and compatibility with frozen OBS-1
timing. A paper catalogue and manifest must bind concrete task values, IDs,
reservations, scope, model/tool contract, runtime and authorization later.
None of those live qualifications is performed here.

| Item | Status |
| --- | --- |
| Selected append-row semantics, 100×3 bounded paper scope, column-A arm correlation, strict complete GET, state/cardinality/projection rules, and proposed model tools | **RESOLVED IN SHEETS PAPER CONTRACT** as frozen provider-specific design; physical paper scope and implementation remain unqualified. |
| Projected logical pairing and one family-wide `M` → arm-local `W_arm` | **DEFINED IN SHEETS PAPER CONTRACT**; the external projected-state-equivalence protocol-freeze dependency is **SATISFIED** by the frozen cross-provider protocol pinned in Section 1. |
| Exact fixed read offsets, scheduled round count, terminal horizon and shared timing/failure rules | Cross-provider OBS-1 freeze dependency **SATISFIED** by the frozen schedule pinned in Section 1; that protocol controls final timing. This document supplies one GET/40-second total cost and H1 constructor read count only. |
| Actual paper fixture, authority/visibility/correlation/cardinality qualification, transport, model adapter, catalogue, manifest, evaluator, offline tests, hostile audit and final readiness | **REQUIRES PAPER IMPLEMENTATION / MANIFEST / EVALUATOR**. Engineering qualification does not close these. |
| Current provider-specific impossibility | **FATAL SHEETS BLOCKER: none established prospectively.** Failure to obtain isolated bounded placement, reliable marker round-trip, complete authoritative read, or exact-one H1 construction before collection becomes a fatal pre-data Sheets blocker; it cannot be waived after outcomes. |

The frozen engineering counters remain: OAuth attempts **9**; accepted
acquisitions **6**; real spreadsheet CREATEs **1**; real Sheets mutations **1**
(that CREATE); real GET dispatches **1**; successful real GETs **1**; duplicate
engineering CREATEs **0**; **paper observations 0**. Those are engineering
provenance, not paper outcomes. The hostile-audited provider semantics are
mechanically reconciled to the frozen cross-provider protocol. The remaining
order is: record the no-analysis-amendment decision → provider 64-family
catalogue → paper manifest selecting one exact physical topology for the 100×3
arm scope → paper adapter/evaluator and offline adversarial validation → select
and qualify a real non-production spreadsheet/tab with paper provisioning,
marker round-trip, authoritative post-write read, transport and live readiness
→ final cross-artifact hostile audit/readiness freeze → separate explicit
collection authorization → only then Study-2 observation #1. No real paper
spreadsheet has been selected. Sheets is **NOT COLLECTION-READY**.
**STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION BLOCKED.**

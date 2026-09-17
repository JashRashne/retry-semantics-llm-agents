# Google Sheets mutation semantics reconnaissance

**FROZEN SEMANTICS RECONNAISSANCE — ZERO STUDY 2 PAPER OBSERVATIONS**

Consulted 2026-09-17. Repository baseline:
`95ba826be7a80adc7f8ce64c533f3475a221839a` (initial worktree clean).
Semantic correction pass on 2026-09-17: the existing reconnaissance was untracked
at the start of that pass. That correction pass did not freeze an engineering protocol.
This reconnaissance artifact is now frozen after hostile semantic audit. No Google
Sheets engineering protocol, adapter, transport contract, live-validation protocol,
or paper dataset is frozen by this status.
Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*.

## 1. Scope and non-goals

This artifact began as workflow step 1: reconnaissance. The semantic correction pass
repaired semantic claims only; it did not start the offline engineering contract.
That pass included no adapter, credentials,
OAuth setup, service calls, experiments, scenario catalog, engineering protocol freeze,
commit, push, or audit ZIP. Study 1 is locked. Completed GitHub Study 2 work is
engineering validation and contributes zero paper observations; it is unchanged.

**REQUEST REPLAY** redispatches the already-generated, frozen mutation request.
**LLM REGENERATION** returns the ambiguity to the model and permits another
generated action/request. Endpoint behavior alone cannot establish regeneration
performance. A later read is an observation capability, not an implicit policy
to repair, replay, or regenerate. Whether either policy can use that capability
is a future design decision.

Evidence labels used below: **Documented** describes an official source;
**Inference** derives a conditional consequence; **UNRESOLVED / REQUIRES
ENGINEERING VALIDATION** identifies a gap. Conditional predictions are not
observations or undocumented Google guarantees.

## 2. Sources consulted

All provider evidence is from official Google documentation or Google-maintained
client source/documentation. Public documentation/source retrieval was the only
network activity. No `sheets.googleapis.com`, discovery-service, spreadsheet,
OAuth, or other operational API request was dispatched. The discovery material
was read from Google's client repository, not fetched from a live service.

References link to the relevant official page/section:

| Ref | Source and inspected locator |
| --- | --- |
| [S1] | `values.append`: HTTP request, parameters, response, `InsertDataOption` |
| [S2] | `values.update`: HTTP request, parameters, request/response bodies |
| [S3] | `spreadsheets.batchUpdate`: validation, collaboration caveat, envelopes |
| [S4] | Request types: `AppendCellsRequest` and `AddSheetRequest` |
| [S5] | `SheetProperties`: `sheetId`, title, index, type |
| [S6] | Response union and `AddSheetResponse` |
| [S7] | Values guide: Append values, table-detection examples, Python example |
| [S8] | `ValueRange`: orientation, supported inputs, nulls, empty output |
| [S9] | `ValueInputOption`: `RAW` versus `USER_ENTERED` |
| [S10] | `UpdateValuesResponse`: affected range, counts, optional values |
| [S11] | `values.get`: GET, range, render options, response |
| [S12] | `values.batchGet`: GET, ranges, response order |
| [S13] | `spreadsheets.get`: GET, metadata, field masks, grid/range selection |
| [S14] | Usage limits: atomicity, 180-second processing limit, quota/backoff |
| [S15] | Error troubleshooting: 400, 500, 503, backoff and complexity |
| [S16] | Batch guide: ordered subrequests, atomicity, supplied-ID example |
| [S17] | Google-maintained `sheets.v4.json`: revision `20260610`; global parameters, candidate methods, request/resource schemas |
| [S18] | AIP-155: optional API request identification and its guarantees |
| [S19] | AIP-154: resource freshness validation guidance |
| [S20] | Sheets migration guide: **v3** ETag/`If-Match` examples versus v4; v4 duplicate sheet-title error |
| [S21] | Python `HttpRequest.execute` API documentation |
| [S22] | Client `http.py`: `_should_retry_response`, `_retry_request`, `HttpRequest.execute`, `build_http` |
| [S23] | Client `_auth.py`: `authorized_http` and credential refresh |
| [S24] | `google_auth_httplib2.AuthorizedHttp`: defaults and configuration |
| [S25] | Google-maintained auth adapter source: `AuthorizedHttp.request` recursion |
| [S26] | Google auth transport constants: refresh status and attempt default |
| [S27] | `ValueRenderOption`: formatted, unformatted, formula representations |
| [S28] | `CellData`: user-entered/effective/formatted values |
| [S29] | Overview: spreadsheet/sheet identity and A1 naming |
| [S30] | Tables guide: first-class Table feature; Append values to a table |

Source limitations: web retrieval may use cached content. `main` and `latest`
links are mutable, not pinned dependency versions. The cached discovery revision
predates current REST documentation: e.g. the current batch envelope also lists
developer-preview comment options absent from that schema. Neither is represented
as an exhaustive snapshot of every future feature. No comments or preview
features are candidates here. Retry findings must be rechecked against a selected,
pinned stack before implementation. [S3], [S17], [S22], [S24]

## 3. Sheets mutation model

**Documented:** a spreadsheet contains sheets; `spreadsheetId` identifies the
container, while a numeric `sheetId` identifies a sheet. A1 notation addresses
cells/ranges and can name a tab. A sheet ID is nonnegative and immutable once
set. A row coordinate is not a documented immutable row-object ID. [S29], [S5]

Values operations use `ValueRange`; `majorDimension` defaults to `ROWS`.
Inputs support strings, booleans, and doubles; nulls skip cells and an empty
string sets an empty value. Trailing empty output rows/columns are omitted.
`RAW` stores input without parsing; `USER_ENTERED` permits UI-style interpretation,
including conversion of strings to numbers or dates. Cell APIs instead use
`RowData`/`CellData` and field masks. [S8], [S9], [S28], [S4]

**Engineering implication:** start semantic reasoning with nonempty literal
strings, not formulas, blank rows, or implicit parsing. Exact replay identity must
cover method, v4 endpoint, spreadsheet and tab/range scope, serialized payload,
semantic query options, orientation, masks, and omitted/default choices. Equal JSON
alone is insufficient. Runtime auth must be audited separately; equality of
semantic requests does not imply identical TLS/authentication bytes.

Repository terminology comes from `research/study2/CAPABILITIES_DRAFT.md` and
`src/retry_semantics/study2/contracts.py`: operation, target scope, payload,
runtime options; required pre-dispatch scope/marker; optional response identity.
These provisional records were inspected and are not promoted to established
capabilities by this document.

## 4. Candidate endpoint semantics

### 4.1 `spreadsheets.values.append`

**Documented:** `POST https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}/values/{range}:append`.
Supply spreadsheet ID, A1 search range, `valueInputOption`, and a `ValueRange`
containing values. The range locates a logical table; writing begins after its
last row, at its first column. It is not a fixed destination address. `INSERT_ROWS`
inserts rows; `OVERWRITE` overwrites at the chosen destination, with capacity
growth still possible at the sheet end. [S1]

The guide gives concrete counterexamples to treating the search range as the
write range: with tables `A1:C2` and `B4:D6`, a whole-sheet search selects the
latter and starts at `B7`; a search at `A1` starts at `A3`; an isolated `E4`
search with no table starts there. Its default is overwrite after the table.
These examples do not specify a complete algorithm for every layout. [S7]

The detected append "table" is a logical data region selected from the supplied
range and surrounding sheet state. It must not be conflated with the first-class
Google Sheets **Table** feature addressed by `tableId`. Universal placement
determinism is not established; later engineering requires an intentionally
isolated region with controlled layout. [S1], [S7], [S30]

**Constraint on any future duplicate-producing replay contract:** explicitly use
`insertDataOption=INSERT_ROWS`. Do not rely on an omitted/default insertion option.
This is a deliberate engineering constraint, justified by the documented insertion
modes, not a claim that `INSERT_ROWS` supplies deduplication or fixed placement.
No contract is created or protocol frozen by stating it here. [S1]

Response: `spreadsheetId`, pre-append `tableRange` (empty if no table), and
`updates`. The latter includes `updatedRange`, updated row/column/cell counts,
and optionally `updatedData`. No new row ID or mutation ID is documented.
Response loss removes authoritative direct placement diagnostics, including the
returned update range and pre-append table range. Placement is not necessarily
unknowable: a later isolated read with a unique marker may locate the effect.
[S1], [S10], [S11]

Documentation wrinkle: the append reference's introductory wording associates
`valueInputOption` with orientation. The enum and guide identify input parsing
and `majorDimension` separately; the guide explicitly says append still adds to
subsequent rows. Freeze both options explicitly rather than copy that wording.
[S1], [S7], [S9]

**Conditional engineering prediction:** under a deliberately isolated layout
unchanged except for the append's own effects, preserved nonempty literal data,
and explicit `INSERT_ROWS`, exact replay is predicted to produce another append
effect. This must be validated; it is not a universal API guarantee. `OVERWRITE`
also acts at a state-selected destination, but is not the option proposed for
duplicate-producing engineering. Blank/skipped inputs, changed regions, deletion,
interference or invalid requests defeat an unconditional duplicate-row claim.
[S1], [S7], [S8]

### 4.2 `spreadsheets.values.update`

**Documented:** `PUT https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}/values/{range}`.
Supply spreadsheet ID, destination range, `valueInputOption`, and `ValueRange`.
This sets values at an addressed range; it does not append a record. Response is
`UpdateValuesResponse`; no new object ID is documented. [S2], [S10]

**Conditional engineering prediction — cell-state convergence:** for a fixed
range and identical literal `RAW` values, replay is expected to converge to the
same measured cell contents. This is not evidence of server request deduplication,
strict request-level idempotency, or unchanged workbook/history surfaces.
Null inputs leave cells untouched; formulas/parsing and
intervening edits can make broader effects state-dependent. Row insertion or
changed name resolution can also invalidate the stable-target premise. [S2], [S8], [S9], [S29]

It is a possible contrast environment for harmful regenerated values or targeting,
but weak for duplicate-effect separation. “Unsuitable for all research” is too
broad: suitability depends on the outcome construct being tested.

### 4.3 `spreadsheets.batchUpdate` with `AppendCellsRequest`

**Documented:** `POST https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}:batchUpdate`,
with `requests: [{appendCells: ...}]`. For the sheet-targeted form, provide
`sheetId`, `rows` of cell data, and a mask with at least one CellData field.
It adds cells after the last row with data in the sheet and inserts rows if
necessary. This is **A: sheet-targeted AppendCells**, with placement relative to
sheet data rather than values API logical-region detection or a fixed coordinate.
[S3], [S4]

**B: `tableId`-targeted AppendCells** uses the same endpoint, rows and mask but
addresses a specific first-class Table. The request reference gives `tableId`
precedence over `sheetId` and restricts appending to the table body. The Tables
guide says it fills the first free row, accounts for full rows/footers, and inserts
rows at the table end before any footer if no empty rows remain. This is materially
different from appending after all sheet data. [S4], [S30]

Batch response contains spreadsheet ID, ordered replies, and optionally an
updated spreadsheet. The Response union has no `appendCells` reply member:
there is no documented dedicated appended-range/row-ID reply. A returned optional
spreadsheet is state, not a mutation identity. [S3], [S6]

**Conditional engineering predictions:** with nonempty literal cell data and a
narrow `userEnteredValue` mask, sheet-targeted replay may create another effect
after sheet data. Table-targeted replay may fill another eligible free body row or
insert one. Both require validating placement and preservation under isolated,
controlled state; neither is asserted to guarantee duplicate rows on every replay.
Sheet-wide data boundaries and Table free/full-row criteria are separate unresolved
questions, including partial/blank/formula cells. Neither variant is a winner.
[S4], [S28], [S30]

### 4.4 `spreadsheets.batchUpdate` with `AddSheetRequest`

**Documented:** same batch endpoint, `requests: [{addSheet: {properties: ...}}]`.
Spreadsheet ID identifies the container; new-sheet properties are optional.
Omitting `sheetId` causes random ID generation; specifying an existing sheet ID
is an error. IDs must be nonnegative. Adding at an index shifts subsequent
indexes; omission places the sheet at the end. Reply `addSheet.properties`
contains new-sheet properties, including its ID. [S4], [S5], [S6]

**Inference:** supplied-ID replay after retained successful creation encounters
the documented existing-ID error, rather than creates a second sheet or returns
a documented cached success. Caller-specified `sheetId` provides resource identity
and uniqueness: an existing ID causes an error. This is collision detection or
uniqueness enforcement, not an application-level idempotency key or documented
request-level duplicate suppression. If that sheet was deleted before replay, the
existing-ID argument no longer applies. An unrelated existing object can also
produce the error. [S4]

For an ID-omitted `AddSheetRequest` that supplies a fixed title, replay after
successful creation is constrained by sheet-title uniqueness: Google documents
that providing a title already used by an existing sheet is an error. Thus, if
the originally created sheet remains present with that title, exact replay with
the same fixed title is expected to encounter that documented duplicate-title
error. Deletion or external mutation, including renaming, could remove the title
conflict before replay. [S20]

Behavior remains **UNRESOLVED / REQUIRES ENGINEERING VALIDATION** here when the
title itself is omitted, including exact generated/default-title behavior, and
for other property combinations not established by the cited documentation.
The title-omitted case is therefore a conditional duplicate-object candidate,
not a proven duplicate-row analogue. [S4], [S5], [S20]

## 5. H0/H1 replay analysis

H0: the original did not commit. H1: the original committed, but its successful
response is unavailable. **H0 and H1 are latent causal worlds defining the
ambiguous-outcome problem; they are not labels returned by the Sheets API.**
Later reads observe resulting/current state. Under a verified isolation model,
they may provide strong operational evidence; they are not automatically universal
historical proof of which causal world occurred.

For this table **assume a valid replay succeeds where
no stated conflict exists**, an initially isolated scope with zero matching
effects, preserved nonempty literal data, stable target/layout, no competing
writer/deletion, and no hidden lower-layer resend. If replay is itself ambiguous
or fails, its effect is unknown; the table does not bypass that uncertainty.

The following are **conditional engineering predictions**, not live results or
universal API guarantees, from §4's cited rules. For append operations, the predicted
second distinct effect additionally requires that the first effect stays preserved
and changes the next eligible placement as expected; that premise needs validation.

| Candidate | H0 before → after replay | H1 before → after replay | Persistent state distinguishes worlds after replay? |
| --- | --- | --- | --- |
| `values.append`, controlled logical region, explicit `INSERT_ROWS` | Predict 0 → 1 matching row | Predict 1 → 2 matching rows | Potentially, after placement/preservation and complete observation are validated. [S1], [S7] |
| Fixed-range `values.update` | Predict baseline → requested values | Predict convergence to the same measured values | No through final cell values under the fixed literal premises; repeat-call history is not encoded there. [S2], [S9] |
| Sheet-targeted `AppendCellsRequest` | Predict 0 → 1 matching row | Predict 1 → 2 matching rows | Potentially, under validated sheet-data boundary/placement and complete observation. [S4] |
| `tableId`-targeted `AppendCellsRequest` | Predict 0 → 1 body-row effect | Predict 1 → 2 distinct body-row effects if another eligible row is selected | Potentially, under validated free/full-row behavior and preservation; not the same placement rule as sheet-targeted append. [S30] |
| `AddSheetRequest`, unused supplied ID | Absent → created object | Existing object → existing-ID error; retained object | No through final one-object state alone. Replay success/error can distinguish, subject to isolation and available response. [S4] |
| `AddSheetRequest`, ID omitted, fixed title initially unused | 0 → 1 new object, if valid | Existing object → duplicate-title error while title retained; retained object | No through final one-object state alone. Replay success/error can distinguish, subject to isolation and available response. [S20] |
| `AddSheetRequest`, ID and title omitted | 0 → 1 new object, if valid | Generated/default-title replay behavior remains unresolved | Persistent distinction and independent correlation remain unresolved. [S4], [S5], [S20] |

Before replay, a reliable isolated read could distinguish absence from presence;
after replay the fixed-range, fixed-ID and fixed-title candidates collapse the two worlds'
final states. A conflict response is a different scientific signal from persistent
duplicates. It must not be scored as request deduplication or silently as success.

Regeneration could emit the same append, change content/destination, propose a
read, or refrain from mutation. Nothing here predicts which. A marker supports
correlation only if preserved; changing/omitting it can hide unintended effects.
Future runtime-owned scope/marker constraints and model-visible information must
be justified without silently changing the replay-versus-regeneration construct.

## 6. Read-after-ambiguity verification

**Documented read capabilities:**

| Method | HTTP and input | Useful evidence |
| --- | --- | --- |
| `values.get` | `GET /v4/spreadsheets/{spreadsheetId}/values/{range}`, empty body | `ValueRange` for one addressed scope; explicit dimension/render options. [S11] |
| `values.batchGet` | `GET /v4/spreadsheets/{spreadsheetId}/values:batchGet`, `ranges[]`, empty body | Spreadsheet ID and ordered `valueRanges[]`, one per requested range. [S12] |
| `spreadsheets.get` | `GET /v4/spreadsheets/{spreadsheetId}`, empty body | Sheet properties/IDs and selected grid data; grid data omitted by default. `fields` selects data and overrides `includeGridData`. [S13] |

Paths above use `https://sheets.googleapis.com`; they describe future capabilities
and were not called. For an eventual metadata read,
`fields=spreadsheetId,sheets(properties(sheetId,title,index,gridProperties))`
is an illustrative projection, not an implemented observer. [S13], [S5]

**Verification reasoning:** establish a unique deterministic literal marker
before dispatch, scoped to engineering/run/family and known absent in a baseline.
For row mutations, put it in a dedicated cell and retain expected payload cells;
inspect every possible landing row in the isolated sheet, not just the search
range or first match. Count matching rows at distinct coordinates within a single
complete read and verify content separately. Identical payload without a marker
cannot distinguish new effects from pre-existing identical data.

Interpretation requires a verified isolation model: isolated workbook/sheet/region,
no concurrent writers or human edits, no automated cleanup, complete read scope,
and no formula-driven removal/transformation of the marker. These are engineering
assumptions to establish, not guarantees supplied by the read endpoints. Reads
remain useful operational evidence when those assumptions hold. [S3], [S11], [S13], [S27]

| Mutation | Exactly one / multiple matching effects | Zero matches / definitely absent |
| --- | --- | --- |
| `values.append` | Marker rows can distinguish one versus multiple **currently visible** copies; landing coordinates must be obtained independently of the lost response. | A bounded original search range may miss landed rows. Complete scope plus unchanged baseline/layout is necessary; zero alone is not proof of H0. |
| Sheet-targeted `AppendCellsRequest` | Same row-count logic, including data after unrelated populated rows. | Sheet-wide coverage is necessary; do not assume a logical values region bounds the append. |
| `tableId`-targeted `AppendCellsRequest` | Count distinct marker-bearing Table body rows; verify content and current Table scope. | Account for free rows, Table expansion and footer boundaries; zero in a stale body range is insufficient. [S30] |
| Fixed `values.update` | Exact range/marker establishes current requested values, not whether the range was set once or twice. Multiple identical fixed writes leave no multiplicity evidence. | Missing values may indicate noncommit, overwrite/deletion, moved targets, or incomplete visibility. |
| `AddSheetRequest` | Supplied ID allows lookup without ACK; compare properties/baseline. ID-omitted creation needs independent marker/correlation, e.g. a pre-dispatch fixed title, whose repetition encounters the documented duplicate-title error while that title remains in use. [S20] | Complete metadata can show ID absence **in returned state**; it cannot exclude prior creation followed by deletion or delayed execution. |

These conclusions follow from the read surfaces and mutation model, not a
documented operation-history API. [S11], [S12], [S13], [S2], [S4]

Distinguish **definitely absent in the successfully returned, fully covered state**
from **definitely never committed**. The latter also needs trustworthy visibility,
execution completion and preservation premises not supplied by these references.
No reviewed source gives a bounded read-after-ambiguity visibility guarantee or
a negative-read certificate of non-execution. **UNRESOLVED / REQUIRES ENGINEERING
VALIDATION**; engineering timing evidence still cannot establish a universal bound.

`UNFORMATTED_VALUE` reports calculated rather than formatted values;
`FORMULA` can expose formulas. Use literal markers and verify the chosen
representation; grid reads can separate `userEnteredValue` from `effectiveValue`.
Restore coordinate interpretation for omitted trailing empties rather than assume
a rectangular response. [S27], [S28], [S8]

Concurrent row insertion/sorting can move coordinates. Do not carry GitHub's
immutable issue-identity deduplication across traversals into Sheets as though row
positions were immutable resource IDs. Overlapping read ranges must not count
the same cell twice; separate reads are not established as a transactional snapshot.

## 7. Idempotency/request-identity audit

Search was broader than endpoint inspection. It included the candidate REST
parameters, batch/request/response schemas, resource properties, the cached
discovery global parameter list, AIP guidance, and site-restricted documentation
searches. In [S17], text searches found no `idempot`, `dedup`, `requestId`,
`request_id`, `requestToken`, `request token`, `etag`, `If-Match`, `precondition`,
or `mutation`. `version` identifies API/schema information, not a candidate
mutation version; `condition` hits formatting/filter conditions, not a candidate
compare-and-set precondition. Token hits include authentication parameters.

Official-site queries used:

```text
site:developers.google.com/workspace/sheets/api "idempotency"
site:developers.google.com/workspace/sheets/api "requestId" OR "If-Match" OR "ETag" OR "deduplication"
site:developers.google.com/workspace/sheets/api "idempotency key" OR "request token" OR "deduplication token"
site:developers.google.com/workspace/sheets/api "conditional" "version"
site:developers.google.com/workspace/sheets/api "ETag" OR "If-Match"
site:developers.google.com/workspace/sheets/api "mutation" "request ID"
```

Queries are search provenance, not exhaustive evidence of absence. Positive
legacy ETag hits were inspected in [S20], rather than discarded.

| Mechanism | Evidence and bounded conclusion |
| --- | --- |
| Request-level key/token/ID | No field/guarantee established for these v4 candidates in reviewed REST surfaces/schema. Google's AIP-155 permits APIs to add `request_id` and specifies deduplication guarantees **when provided by an API**; it does not add one to Sheets. [S18], [S17] |
| Conditional version / ETag | AIP-154 describes freshness validation, not universal deployment. The Sheets migration guide documents ETag/`If-Match` for **v3** row feeds; its v4 examples use batch operations without that precondition. Header enforcement for the selected v4 candidates is **UNRESOLVED / REQUIRES ENGINEERING VALIDATION**, not proved impossible by schema omission. [S19], [S20] |
| `sheetId` | Client-selectable object identity and existing-ID error, not a mutation token, payload comparison, retained request record, or documented cached success. [S4] |
| Row/cell marker | Application content correlation; no reviewed contract makes matching cell content suppress a subsequent append. [S7], [S8] |
| API key / OAuth token / `quotaUser` / `fields` | Global parameters describe project/auth identity, quota attribution and response selection; none is documented there as mutation deduplication. [S17] |

**Bounded finding:** no documented client-controlled request-level deduplication
mechanism was identified in the reviewed Sheets v4 candidate mutation surfaces.
This describes the audit scope, not undocumented Google infrastructure. Do not
replace it with “Google Sheets has no idempotency mechanism.” Undocumented header
behavior, broader features and deployment changes
remain unresolved. Even a real version precondition would be concurrency control,
not automatically success-returning request deduplication.

## 8. Atomicity versus retry safety; timeout/backoff

**Documented:** the limits page says Sheets requests apply atomically and explains
this through all-or-none validation. The batch guide explicitly covers subrequests;
the REST method orders them and rejects the entire update if a subrequest is
invalid. It also warns that collaborator changes can alter the resulting state.
This supports request/batch atomicity, not isolation from all external writers.
[S14], [S16], [S3]

**Inference:** an atomic append may commit as a whole while its response is lost.
A second valid atomic append may commit as a whole too. Atomicity constrains
partial application inside an attempt; it does not identify attempts, deduplicate
them, guarantee response delivery, or tell the client which hidden world holds.
Two atomic requests do not form a single retry transaction. [S16], [S7]

**Sheets atomicity does not imply safe replay after an unknown outcome.**
Validation/application atomicity, response availability, ambiguous commit outcome,
and replay safety are separate properties. A valid all-or-none mutation can have
an unavailable response; another atomic request does not resolve that ambiguity
or make repetition harmless. [S14], [S3]

**Documented guidance:** processing over 180 seconds yields a timeout error.
Time-based quota errors/429 warrant truncated exponential backoff with jitter:
`min(2^n + random_number_milliseconds, maximum_backoff)`; jitter is at most
1,000 ms, typical caps 32 or 64 seconds, and retries should eventually stop.
Read and write limits are each 300/min/project and 60/min/user/project. [S14]

The error guide describes 503 as service unavailability or high complexity and
recommends backoff when retrying; large batches can time out. Its 500 guidance
is to report the offending request as a bug, not a universal safe-replay promise.
It describes 400 as malformed input. [S15]

**Engineering distinction:** backoff controls timing/load. It does not establish
that an unknown-outcome append failed to commit. A received quota error, an
unread success, service processing timeout and a client socket timeout are
different evidence. The 180-second rule gives no reviewed guarantee that every
timeout implies rollback or that closing a connection cancels execution.
**UNRESOLVED / REQUIRES ENGINEERING VALIDATION.** No paper claim is made here.

## 9. Client automatic-retry audit

The likely official Python example stack is discovery-based
`google-api-python-client` with `google-auth`, `google-auth-httplib2` and
`httplib2`, not an already-selected repository dependency. The example uses
`build('sheets', 'v4', credentials=...)`; client auth source wraps a constructed
HTTP transport in `AuthorizedHttp`. No dependency was installed/imported and no
credentials were accessed. [S7], [S23]

**Repository facts:** inspection of `pyproject.toml` and `uv.lock` finds no
`google-api-python-client`, `google-auth`, `google-auth-httplib2` or `httplib2`
dependency or version pin. Existing unrelated dependency pins do not establish a
Sheets stack. A future harness must pin and record the versions actually used;
no claim about a latest release is needed. Nothing was installed or upgraded.

| Layer | Source-backed finding | Zero-retry implication |
| --- | --- | --- |
| Google API client | Official documentation says `HttpRequest.execute(num_retries=0)` defaults to one attempt at that client-layer retry loop. [S21] | This does not establish one mutating wire dispatch across the stack. |
| Google API client retry implementation | `_retry_request` iterates `num_retries + 1`; with retries enabled it handles selected transport exceptions, 5xx, 429 and rate-limit-related 403, without a mutation-specific idempotency test. `build_http` constructs `httplib2.Http`. [S22] | Do not enable the loop for the first mutation. No transport guarantee follows from a single `http.request` invocation. |
| Auth adapter | `AuthorizedHttp` defaults to refresh-and-reissue on 401, with at most two refresh attempts. Its source recursively calls `request` after refresh with the original method/body. [S24], [S25], [S26] | `max_refresh_attempts=0` disables this post-response refresh/reissue path. It does not disable possible credential preparation/refresh before a request. |
| Underlying HTTP transport | Google client/auth source delegates to `httplib2`; it does not certify a one-send guarantee. [S22], [S25] | Inspect exact retry/recovery/redirect/cache behavior against the exact version selected for the future harness. No relevant repository pin exists, so this remains **UNRESOLVED / REQUIRES ENGINEERING VALIDATION**; no broad/version-independent or sufficient `RETRIES=0` claim is made. |
| Our harness / wrappers | Existing GitHub code has a single-attempt transport; no Sheets wrapper exists. | Later audit our loops, decorator retries, middleware, redirects, credential boundary and replacement transports; count actual mutating sends. |

Another source-backed hazard: `HttpRequest.execute` converts an overly long GET
URI (over `MAX_URI_LENGTH=2048` in inspected source) into a POST with a GET method
override. A logically read-only `batchGet` may therefore violate an engineering
requirement of literal GET-only wire traffic. Bound observation URI size or use
separate short GETs, and inspect the prepared method. This finding is independent
of retry count. [S22]

**Audit status:** zero API-client retries and zero auth-response reissues are
configurable; **zero automatic mutation resends across the whole stack has not
been established**. Source-reading does not validate an installed configuration.
Use version-pinned source inspection and offline fake-wire faults before selecting
a transport. Auth-token calls are not Sheets mutations but must be logged/scoped
separately so “one outgoing request” is not misleading.

**Zero retries at the `HttpRequest.execute` layer is insufficient to prove one
mutating wire dispatch.** Auth-response refresh/reissue and lower transport
behavior require their own audit. [S21], [S24], [S25]

## 10. Ambiguity-injection feasibility

Inspected, without execution:

- `scripts/smoke_study2_github_ambiguous.py`: one-use mutation capability,
  pre-dispatch marker/content, artifact reservation, separate GET observer.
- `src/retry_semantics/study2/github_adapter.py`: `_LiveAmbiguityTransport`,
  `_https_attempt`, explicit connect, `auto_open=0`, one `endheaders` call,
  `AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE` before `getresponse`, cleanup.
- `src/retry_semantics/study2/github_engineering_visibility.py`: preserves
  separate complete traversals and does not equate no match with non-execution.
- GitHub semantics/engineering drafts and generic contracts: scope/marker precede
  dispatch; lost response identity is supplemental, never required.

Conceptual transfer is feasible: prepare one Sheets append request, permit at
most one mutating send, fault after local send but before response observation,
retain a locally ambiguous result, then permit a separate read-only observer.
This is a proposed engineering boundary, not a Sheets commit guarantee.

Fault taxonomy (local evidence categories, not API-returned H0/H1 labels):

| Local event | Interpretation |
| --- | --- |
| Failure before mutating dispatch | Known non-dispatch, not the target ambiguous-outcome event. |
| Request handed to transport; no definitive response status exposed | Potential target ambiguity. Transport handoff alone proves neither actual send nor remote receipt/commit. |
| 2xx status exposed; body unavailable | Success status is already known; response details/placement may be missing. This differs from an entirely unread response. |
| Full successful response exposed | Known success with available response details, subject to normal method-specific validation. |

The exact usable fault boundary and evidence that no status/body was exposed
require later engineering validation. No boundary is implemented in this pass.

The existing transport routine has generic mechanics but lives within GitHub
configuration/error/trace code; the live gate and visibility validator are
GitHub-specific. There is no ready provider-neutral public abstraction requiring
only a placeholder. No refactor, placeholder, fault injector or adapter was added.

Later demonstrations required before trusting transfer:

1. Offline fault paths show one prepared mutation, at most one actual mutating
   HTTP send, no fallback/redirect/auth reissue and no response parsing after the
   fault. A logical invocation counter is insufficient; TCP packet retransmission
   is not itself an additional application request.
2. The boundary fires only after local send completes; trace records request
   bytes/options and absence of response status, headers, body and landing range.
   Local completion does **not** prove remote receipt/commit, nor does connection
   close establish rollback/cancellation.
3. A separately authorized future engineering check must establish a remote
   marker/content effect through reads without using the lost append response.
   Such evidence can show at least one effect under isolation; it cannot retroactively
   make local send completion a universal receipt certificate.
4. Read method/URI, coverage, marker preservation, distinct-row counts, visibility
   timing and errors must be validated. Keep no-match as unobserved, errors as
   unknown, and anomalies as separate evidence. Do not copy GitHub polling bounds.
5. H0 must not be fabricated from a negative read. A before-send fault establishes
   local non-dispatch, a different event from a service-reached noncommit world.
   Neither H0/H1 nor retry policies are implemented in this phase.

## 11. Candidate comparison and state dependence

Matrix entries are bounded inferences based on §§4–9, not provider observations.

| Candidate mutation | Persistent effect | Replay after H1 | Read-back verifiability | Built-in identity/dedup | Scientific usefulness | Main risk |
| --- | --- | --- | --- | --- | --- | --- |
| `values.append`, explicit `INSERT_ROWS` | Values after detected logical region | Predict another append effect under controlled range/layout; validate. [S1], [S7] | Scope + marker, complete landing coverage. [S11] | No documented request-level dedup identified in reviewed surfaces; range supplemental. [S1], [S17] | Provisional duplicate-effect candidate; not selected | State-dependent detection/placement; missed or transformed rows |
| `values.update` | Addressed cell values | Expected cell-state convergence under fixed-range literal `RAW` premises. [S2], [S9] | Current values readable; repeated writes not countable. [S11] | Convergence, not evidence of strict request idempotency or dedup | Convergence/control candidate; weak duplicate separation | Target/intervening changes; unmeasured history surfaces |
| Sheet-targeted `AppendCellsRequest` | Cells after last sheet data | Predict another effect under verified data boundary/layout; validate. [S4] | Scope + marker; no dedicated landing reply. [S6], [S13] | Sheet ID is destination resource identity | Serious, materially different duplicate-effect candidate; not selected | Unrelated far-down data; unclear data-boundary edge cases |
| `tableId`-targeted `AppendCellsRequest` | First free Table body row; insert at end before footer if none free | Predict another eligible body-row effect under controlled Table state; validate. [S30] | Scope + marker; current Table body coverage must include expansion. [S13], [S30] | Table ID is destination resource identity, not mutation dedup. [S4] | Serious, materially different Table-aware candidate; not selected | Free/full/partial-row rules, footers, column-type/default-value interactions and boundary changes |
| `AddSheetRequest`, supplied ID | New sheet | Existing-ID error while object retained. [S4] | Known ID/properties via metadata. [S5], [S13] | Resource uniqueness/collision detection, not request duplicate suppression | Primarily uniqueness/conflict semantics | Final state can match H0 replay; stale collision/deletion |
| `AddSheetRequest`, ID omitted | New sheet with generated ID | Fixed title: duplicate-title error while title retained; omitted title: unresolved. [S20] | Lost ID needs independent correlation. [S13] | Generated object identity; no request token established | Fixed title offers conflict semantics; title-omitted structural candidate remains conditional | Deletion/renaming can remove title conflict; default naming and marker strategy unresolved |

Future controlled engineering would need to isolate/freeze: spreadsheet/tab
scope and layout; one simple data region with a stable first column; baseline
marker absence; input/render options; literal values; row capacity and whole landing
scope; explicit `INSERT_ROWS` for values append; narrow cell masks; title-to-ID
resolution; no unrelated sheet data for sheet-targeted AppendCells; controlled
Table ID/body/free rows/footer/column types for Table-targeted AppendCells; and no
concurrent API/user/script writers, human edits, automated cleanup,
sorts, insertions or deletions. These are threats/controls, not a frozen protocol.
The table examples and collaborator caveat support the placement/concurrency
concerns; parsing and formula representations support transformation concerns.
[S7], [S3], [S9], [S27], [S29], [S30]

Do not presume sequential outcomes describe simultaneous appends. Locking,
ordering and duplicate count under concurrency are not established by these
sources. Formula/blank/formatting table boundaries also remain unresolved.

## 12. Claim falsification table

| Claim | Classification | Evidence / attempted falsification |
| --- | --- | --- |
| A: alleged "ideal" append / necessary duplicate on replay | **PARTIALLY SUPPORTED** | Subsequent-row semantics motivate a conditional prediction with controlled layout and explicit `INSERT_ROWS`. Neither necessary duplication nor an ideal designation is established; state/input edge cases require validation. [S1], [S7], [S8] |
| B: alleged replay idempotency makes `values.update` unsuitable | **PARTIALLY SUPPORTED** | Expected fixed literal `RAW` cell-state convergence supports a control role, not strict request-level idempotency, server dedup or unchanged history. Universal unsuitability is not supported. [S2], [S9] |
| C: supplied `sheetId` is equivalent to an application-level idempotency key | **NOT SUPPORTED** | The documented rule is existing-ID error: resource uniqueness/collision detection. It supplies neither documented request duplicate suppression nor a cached-success guarantee. [S4], [S18] |
| D: atomicity makes replay safe | **NOT SUPPORTED** | All-or-none subrequests do not suppress another atomic append. Atomicity and repetition are different properties. [S16], [S7] |
| E: post-ambiguity GET always proves whether mutation occurred | **NOT SUPPORTED** | Reads return scoped current values/metadata, not operation history. Pre-existing matches, incomplete scope, overwrites/deletions and unresolved visibility defeat “always.” [S11], [S12], [S13] |

## 13. Open/unresolved questions

All items below are **UNRESOLVED / REQUIRES ENGINEERING VALIDATION**. Some also
require explicit official clarification; engineering cannot prove all-time absence
of an undocumented feature.

- Full table-detection algorithm, including holes, blank/formula/formatting cells,
  bounded search ranges and table extension across repeated appends.
- Sheet-targeted AppendCells data-boundary/placement edge cases and unrelated
  cells; separately, Table-targeted free/full/partial-row definitions, column types,
  body expansion/footer behavior and preservation across exact replay.
- ID-omitted AddSheet: duplicate-title rejection for an explicitly repeated fixed
  title is documented; exact behavior when the title itself is omitted/default
  naming is used and other unestablished property combinations remain unresolved.
  [S20] Exact existing-ID error details are not established beyond the documented
  error condition. [S4]
- Any candidate-specific v4 header precondition enforcement or request identity
  support outside the reviewed surfaces. Legacy v3 examples are insufficient.
- Whole-stack zero-resend behavior in a pinned transport, including auth,
  redirects, reconnects, proxies and our wrappers; GET-to-POST rewriting must
  remain excluded if literal GET-only observation is required.
- Remote commit following close-before-response, timeout commit/cancellation
  behavior, read visibility and completeness after ambiguity. Negative reads
  must not be treated as known noncommit.
- Concurrent-write ordering, row-coordinate movement and completeness across
  separate reads; preservation/isolation and a future engineering namespace.
- How regenerated actions preserve correlation while permitting meaningful
  model choices, and which verification information each policy receives.
  This is an open research design issue, not a Google semantic guarantee.

## 14. Recommended next smallest engineering step

`values.append` remains a **provisional duplicate-producing candidate** under a
controlled range/layout and explicit `INSERT_ROWS`. Both AppendCells variants
remain serious, materially different alternatives: sheet-data-relative placement
versus Table-aware free-row/footer handling. They must be evaluated before an
engineering protocol is frozen. No winner is selected. `values.update` remains a
convergence/control candidate; supplied-ID AddSheet primarily offers uniqueness/
conflict semantics. ID-omitted AddSheet with a fixed title also offers conflict
semantics; title-omitted/default naming remains unresolved.
[S1], [S2], [S4], [S20], [S30]

The semantics reconnaissance is frozen. The next phase is a separate offline
engineering-contract phase addressing placement/preservation, independent marker
read-back, exact dependency versions, zero hidden mutating resends, transport
instrumentation, and the usable ambiguity boundary. Source descriptions and
offline simulations cannot substitute for remote semantic validation. The offline
contract, fake-wire tests, stack/auth
selection, adapter and fault injector are **not started in this pass**. No live
validation, scenarios, replicate schedule, paper dataset or final protocol is
authorized or executed here.

## 15. Activity and boundary statement

**No live Google Sheets mutation occurred. No Study 2 paper observation was
produced.** No operational Google API call, credentials/OAuth setup, experiment,
adapter, code/type/test addition, Study 1 change, completed GitHub semantics change,
commit, push, or engineering protocol freeze occurred. No audit ZIP was created by
the semantic correction pass itself. That pass intentionally modified only this
existing reconnaissance document; the file remains
untracked from the initial pass. Public official documentation and source were read
over the network. No offline engineering contract or fake-wire tests were created.

[S1]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append
[S2]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/update
[S3]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate
[S4]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request
[S5]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#SheetProperties
[S6]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response
[S7]: https://developers.google.com/workspace/sheets/api/guides/values#append_values
[S8]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values#ValueRange
[S9]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/ValueInputOption
[S10]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/UpdateValuesResponse
[S11]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/get
[S12]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet
[S13]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get
[S14]: https://developers.google.com/workspace/sheets/api/limits
[S15]: https://developers.google.com/workspace/sheets/api/troubleshoot-api-errors
[S16]: https://developers.google.com/workspace/sheets/api/guides/batch
[S17]: https://raw.githubusercontent.com/googleapis/google-api-python-client/main/googleapiclient/discovery_cache/documents/sheets.v4.json
[S18]: https://google.aip.dev/155
[S19]: https://google.aip.dev/154
[S20]: https://developers.google.com/workspace/sheets/api/guides/migration
[S21]: https://googleapis.github.io/google-api-python-client/docs/epy/googleapiclient.http.HttpRequest-class.html#execute
[S22]: https://raw.githubusercontent.com/googleapis/google-api-python-client/main/googleapiclient/http.py
[S23]: https://raw.githubusercontent.com/googleapis/google-api-python-client/main/googleapiclient/_auth.py
[S24]: https://googleapis.dev/python/google-auth-httplib2/latest/google_auth_httplib2.html#google_auth_httplib2.AuthorizedHttp
[S25]: https://googleapis.dev/python/google-auth-httplib2/latest/_modules/google_auth_httplib2.html#AuthorizedHttp.request
[S26]: https://raw.githubusercontent.com/googleapis/google-auth-library-python/main/google/auth/transport/__init__.py
[S27]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/ValueRenderOption
[S28]: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#CellData
[S29]: https://developers.google.com/workspace/sheets/api/guides/concepts
[S30]: https://developers.google.com/workspace/sheets/api/guides/tables#append_values_to_a_table

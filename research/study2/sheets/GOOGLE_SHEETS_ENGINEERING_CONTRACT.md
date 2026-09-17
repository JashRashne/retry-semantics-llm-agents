# Google Sheets offline engineering contract

**FROZEN OFFLINE ENGINEERING CONTRACT — LIVE-GO CLOSED — ZERO PAPER OBSERVATIONS**

The exact v0.4 freeze-check package passed independent final hostile audit with
verdict **PASS — NO REMAINING OFFLINE ENGINEERING BLOCKER**. Independent packaged
execution passed 93 focused tests normally and 93 with warnings treated as errors.

This freeze covers only the limited offline qualification semantics, candidate
request representation used by the offline harness, local lifecycle vocabulary,
fail-closed target ambiguity gate, controlled fake-wire serializer-envelope
qualification, and offline evidence boundaries represented by these artifacts.

It does not qualify live Sheets engineering, a live transport or credentials/auth;
does not make Google receipt/commit observable or H0/H1 observable labels; and
does not establish a real fixture, validated live AppendCells placement or a
read-only verifier. Zero paper observations exist and paper collection is not
authorized. The first-live-mutation gate in §14 remains CLOSED.

**v0.4 serializer-envelope hardening:** validate all seven declared controlled
headers, including routing/framing and structural Authorization checks. Scientific
application identity and all accepted v0.3 lifecycle/fault semantics are preserved.

**v0.3 pre-freeze hardening:** clean WAIT_LOSS response-stream initialization,
warning-as-error qualification, and hostile serialized-material mismatch tests.
The accepted v0.2 state model and all live-go boundaries remain unchanged.

**v0.2 targeted hardening:** explicit incomplete-write classification and typed
local lifecycle corroboration. Dispatch initiation semantics, candidate, proposed
transport, exact replay bytes and future grid verifier are preserved. This pass
started with the three first-pass artifacts untracked; no shared files changed.

Prepared 2026-09-17 against repository HEAD `26609e4` during workflow step 1
of the offline engineering-contract phase; the limited offline scope is now frozen
after final audit. It does not authorize a live request. The frozen semantics
reconnaissance remains unchanged. No live Sheets stack, fixture, engineering
protocol or paper-wide endpoint winner is frozen here.
No Google credentials, OAuth flow, operational API calls, live fault injection,
spreadsheet creation, paper collection, commit, push or audit ZIP occurred.

## 1. Inspected baseline and transfer boundary

Read the frozen [semantics reconnaissance](GOOGLE_SHEETS_SEMANTICS_RECONNAISSANCE.md),
`pyproject.toml`, `uv.lock`, Study 2 contracts, GitHub adapter/engineering draft,
GitHub lifecycle and ambiguous-outcome fake-wire tests, visibility helper, Study 1
exact-replay executor/tests and regeneration context/executor. Initial worktree
was clean. No applicable `AGENTS.md` was found in the repository.

| Existing mechanism | Transfer assessment |
| --- | --- |
| `serialization.canonical_json_bytes` / `sha256_hex` | Reuse unchanged for one-time body preparation and identity hashing. This does not alone establish HTTP identity. |
| `study2/contracts.py` identity/scope/marker declarations | Reusable design vocabulary; declarative and provisional, not a transport or retry-policy interface. |
| GitHub fresh connection, explicit connect, `auto_open=0`, unchunked bytes, status retention on body loss | Provider-neutral mechanics embedded in provider-specific code. Useful evidence pattern. Do not import private GitHub transport or refactor locked behavior in this pass. |
| GitHub fake `HTTPConnection` / socket tests | Evidence pattern: count serialized request lines at socket handoff, inspect body bytes, prevent network. Reuse pattern with Sheets envelope and real response parsing. |
| GitHub one-use live capability and opt-in guard | Useful gate pattern only. Its POST scope, environment/config matching, artifact paths and auth are provider-specific. A later explicit replay needs a separately authorized dispatch, not silent reset of an initial one-use capability. |
| GitHub LIST pagination, issue identity, PR exclusion, API version/headers, visibility polling bounds | Unsuitable for Sheets. No GitHub timing or pagination guarantee transfers. |
| Study 1 exact replay | Reuse principle: validate all frozen representations, dispatch stored bytes without reconstructing JSON or calling model. Executor is strictly `TicketEnvironment`/ticket-provenance specific; do not wire Sheets into it. |
| Study 1 regeneration | Message-history and model interface principles transfer; ticket tools, argument validators, contexts and latent-world clones do not. No existing external-provider policy executor is ready for trivial Sheets wiring. |

There is no provider-neutral public single-attempt HTTP/fault implementation.
New code is isolated in `study2/sheets_offline.py`, with no imports from the
GitHub adapter, no runtime/runner wiring and no live connection factory.

## 2. First candidate decision (engineering only)

Recommend **sheet-targeted `AppendCellsRequest`**, one subrequest in
`spreadsheets.batchUpdate`. This follows the frozen reconnaissance's separate
sheet-data-relative semantics, not the values-API logical-table semantics.

| Candidate | Exact request / verification / isolation tradeoff |
| --- | --- |
| Sheet-targeted AppendCells | Numeric sheet ID is known before send; one literal row and narrow mask; entire dedicated sheet can have one known data boundary. No logical-table detection, Table body/free-row/footer rules, generated row ID or lost landing-range reply needed for correlation. Read entered cell values and row coordinates. Unrelated far-down sheet data must be excluded. |
| `values.append` | Compact literal request and useful landing diagnostics on clean success; exact replay is straightforward with explicit `RAW`, `INSERT_ROWS`, `ROWS`. Still requires validating logical-table selection and title/range resolution independently of request identity. Serious alternative if sheet-data isolation fails. |
| Table-targeted AppendCells | Precise pre-existing Table target; adds Table creation/metadata, body expansion, empty/partial-row eligibility, footer and column-type/default controls. More fixture state to qualify before first mutation. Serious later comparison, not rejected semantically. |
| `values.update` | Fixed-cell convergence/control; cell-state effect cannot count repeated identical writes. |
| AddSheet | Supplied identity primarily uniqueness/conflict semantics; omitted identity increases generated-state dependence. Different scientific signal. |

Choice rests on reduced layout/fixture assumptions under a whole-sheet isolation
model, not coding convenience. No offline simulator can establish Google's
placement or duplicate preservation. Before protocol freeze, audit this comparison
and freeze a fixture-layout manifest for the selected form; alternatives require
separate minimal manifests specifying search-table layout or Table body/free rows/
footer/types plus verification coverage. If a dedicated sheet cannot exclude all
unrelated data, reopen the choice rather than assert AppendCells determinism.
No final endpoint winner or paper scenario is selected.

## 3. Exact mutation template

Future logical mutation (placeholders are not live identifiers):

```text
POST https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}:batchUpdate
Query: empty (no omitted runtime query additions permitted)
Content-Type: application/json; charset=utf-8
Accept: application/json
```

```json
{
  "includeSpreadsheetInResponse": false,
  "requests": [{
    "appendCells": {
      "sheetId": "<manifest nonnegative integer, not a JSON string>",
      "fields": "userEnteredValue",
      "rows": [{"values": [
        {"userEnteredValue": {"stringValue": "<deterministic engineering marker>"}},
        {"userEnteredValue": {"stringValue": "engineering-v1"}},
        {"userEnteredValue": {"stringValue": "literal-payload"}}
      ]}]
    }
  }]
}
```

The displayed JSON is explanatory; the code emits a numeric `sheetId` and stores
actual canonical UTF-8 bytes. Exactly one append subrequest and one three-cell row.
No `tableId`, formulas, numeric/date/locale parsing, nulls, empty strings, broad
field masks, returned spreadsheet or additional mutation subrequests. No
`valueInputOption`, `insertDataOption` or `majorDimension`: these belong to the
values API, not this cell request. Cell values explicitly use `stringValue`.

Marker template: `ENGINEERING-ONLY-{reserved_run_namespace}-{case_id}` with a
persisted namespace/case reservation, stable across explicit replay, disjoint
from prior engineering/paper namespaces and baseline-read absent. Deterministic
within the reserved trial does not imply global uniqueness without reservation.
Do not generate a new marker on replay. Fixtures in tests are synthetic labels.

## 4. Frozen identity and replay comparison surface

Freeze once before dispatch: operation/form, HTTPS origin (canonical lowercase
`sheets.googleapis.com`, default 443, no credentials), method `POST`, exact
percent-encoded target path, complete query string (empty for this form), ordered
allowlisted application headers, and exact body bytes. Persist body SHA-256 and
an identity-envelope SHA-256. Envelope includes origin, method, URI, normalized
application header names/values and body hex. Store bytes losslessly, not just a
hash; replay passes the same stored bytes object through the controlled transport.

**Application mutation identity:** header comparison in the scientific identity
is exactly `content-type` and `accept`, normalized lowercase names and frozen
explicit values/order, in addition to the frozen origin/method/path/query/body.
No additional mutation option headers are allowed. Future quota/billing/project/
routing/precondition headers require contract revision and explicit classification;
do not silently add or ignore them. The identity hash does not authenticate all
wire-level fields or substitute for controlled envelope validation.

**Controlled serialized transport envelope:** qualification also requires the
following complete header schema, separate from the scientific identity hash:

| Required header (names case-insensitive) | Controlled requirement | Classification |
| --- | --- | --- |
| Content-Type | Exactly frozen `application/json; charset=utf-8` | Application identity |
| Accept | Exactly frozen `application/json` | Application identity |
| Host | Exactly `sheets.googleapis.com`, consistent with frozen origin | Routing qualification |
| Content-Length | Canonical unsigned decimal equal to frozen body byte length | Framing qualification |
| Accept-Encoding | Exactly `identity` | Controlled transport configuration |
| Connection | Exactly `close` | Controlled transport configuration |
| Authorization | Exactly one header, structural `Bearer <token>` form | Ephemeral/security material |

All seven are required exactly once. Reject unexpected names (including
`X-Goog-User-Project`, user agent and tracing/date headers), missing names, duplicate
names with any casing, Transfer-Encoding, conflicting framing, invalid header
syntax/folding and altered controlled values. This strict observer supports only
the declared serialized shape (`name: value` lines, CRLF termination); it is not
an RFC-complete HTTP parser. Application header relative order remains frozen;
routing/security header order is not scientific mutation identity. Framing/routing
conformity is qualification evidence, never remote receipt/commit evidence.

**Ephemeral/security material:** Authorization is supplied only at dispatch,
not stored in the scientific identity envelope or persisted evidence. The fake
observer validates the Bearer scheme/token syntax structurally, records only
presence internally, and allows a different structurally valid bearer without
changing identity. It never hashes or exports the raw value. Validation failures
use fixed reason strings, never header maps, raw serialized fields or token echoes.
Bearer refresh may change token between separately authorized dispatches without
changing the logical mutation. Dates, tracing/correlation/request-ID headers,
connection headers, user agent, TLS/session/socket data and header-name casing
are not scientific mutation identity; log only safe structural metadata/config
where needed. This offline contract sends no dates/tracing headers and fixes
`Accept-Encoding: identity`, `Connection: close`, unchunked HTTP/1.1 framing.
No claim of identical authentication/TLS/network bytes is required or made.
Exclusion from scientific identity does not imply permission to emit an arbitrary
header: this controlled envelope forbids all names outside its seven-header schema.

REQUEST REPLAY must validate stored method/origin/path/query/application headers,
body bytes/hash and envelope hash against the original manifest, then redispatch
that representation. No reserialization of semantically similar JSON, endpoint
rediscovery, target/range resolution, default recomputation or LLM call. A later
successful replay may append somewhere else because sheet state changed; frozen
request identity does not mean frozen resulting row coordinate.

## 5. Counting actual dispatch initiation

Count **HTTP request initiations**, not `.execute()` invocations, TCP packets,
socket chunks, DNS addresses or TLS handshakes. At the lowest practical controlled
Python layer, record immediately before the first serialized request-line/header
block is handed to socket `sendall`. Header and body sends are one dispatch.
A raised sendall after entry may already have sent bytes: count initiation and
separately retain local-send completion/partial-send evidence. Neither proves
server receipt, execution or commit. A failure before this boundary counts zero.

The locally inspected Python `socket.sendall` docstring states that on error it is
impossible to tell how much data has been sent. Classify an initiated request whose
local write fails as **`incomplete_send_unknown`**: receipt/commit cannot be inferred,
and it is ineligible for the first target ambiguity boundary. It is not H0 or known
noncommit. One initiation is counted even though send completion is absent.

Only a new HTTP mutation request initiation counts as a hidden mutation resend.
`http.client` auto-connect concerns connection establishment and is suppressed with
explicit connect plus `auto_open=0`; it is not synonymous with HTTP-level resend.
OS/TCP packet retransmission and retry/completion of an interrupted system call
within one socket send operation do not initiate another HTTP mutation request.
Do not count socket chunks, internal send calls or packets as separate mutations.
No redirect handling, status retry or auth-response retry is allowed in this flow.
The exact future Python runtime/build remains a live-go pin.

For the proposed live path, a controlled connection/send hook must recognize
each new HTTP request serialization, not guess based on a body's `POST` prefix.
Validate actual method/path/headers and body against frozen inputs, track every
connection and bind the counter to all allowed mutation routes. Fail closed on
unexpected methods/endpoints, uninstrumented replacements, proxy tunnels or
traffic classification failures. Capture initiation even if transmission fails.
Prepare artifact storage and evidence recorder before enabling a mutation.

Traffic classes must be separate: authentication/token exchange; discovery or
non-Sheets metadata; literal read-only Sheets GET; Sheets mutation. Sheets
metadata GET is read traffic, not a mutation. Classification must use actual
origin/method/path (and payload where a method override would matter), not a
caller-provided read label. Disallow POST method overrides entirely. Unknown
traffic invalidates qualification; auth exchanges must never carry the Sheets
mutation. Authentication counters/traces record fixed labels and safe timing,
never token request bodies or their hashes, secret query values or headers.

Each mutation record: monotonic sequence/time, method, URI/path, actual body hash,
identity-envelope hash, traffic class, before/after-policy-entry bit; separately
persist connect/send-start/send-complete/status-received/fault/close order. Record
UTC wall time for artifact association, monotonic time for causal local ordering.
Initial-dispatch and explicit-policy-entry event must have a single owner and
atomic ordering; no callback may invisibly enter policy or send twice.

Implemented offline: fake socket parses the real serialized request line and
application headers, records at its sendall entry, checks emitted body bytes,
and uses a trial-local ledger with immutable exported records. Counting is not
based on high-level calls. Its only socket route is a synthetic Sheets mutation.
The offline harness validates **controlled serializer conformity**: observed
serialized method/URI/application headers and emitted body bytes are checked
against the frozen mutation. The stored identity-envelope hash is derived from
the trusted `FrozenMutation` object; it is not an independently tamper-resistant
wire-attestation digest. Body hashing uses the controlled `_send_output` argument;
the actual emitted body must match before local-send completion is recorded.
An incomplete-send record does not attest full body delivery. These checks are
substantial serialized-evidence validation, not blind acceptance of an arbitrary
identity hash or a packet-sniffing/remote-receipt proof.
v0.4 additionally validates the complete declared routing/framing/security header
envelope before admitting the synthetic header handoff. On envelope mismatch the
fake rejects qualification, returns no eligible result, records no completion and
cannot enter policy. This refusal is not a claim of remote noncommit/H0; no Google
traffic occurs. Emitted-body mismatch after initiation likewise forbids completion.
v0.2 also exports an immutable typed lifecycle: `dispatch_initiated` at the socket
header handoff; `local_send_completed` only after `endheaders` returns;
`status_observed` as soon as a definitive response status is exposed to this flow,
before body reading; and `policy_entry` only after successful qualification.
Each event has its own monotonic sequence/time, linked dispatch sequence and
optional visible status. Policy-entry timestamp is the event's timestamp; explicit
replay initiation has a new dispatch sequence and the existing after-entry bit.
Remote receipt and commit have no asserted lifecycle events: both remain unknown.
`dispatch_started != local_send_completed != remote_received != remote_committed`.
Other ledger categories are declaratively tested, **not actual auth/discovery/read
transport instrumentation**. Runtime traffic allowlisting and the live socket hook
remain required work. The public `record` method and supplied local result are
trusted qualification primitives, not tamper-resistant evidence or a production
validator. Directly constructed `FrozenMutation` fixtures are likewise trusted;
only the builder constrains candidate content. Do not expose these as a live API.

## 6. Dependency-specific retry inventory

Repository pins: `httpx==0.28.1`, `groq==1.7.0`, `jsonschema==4.25.1`, dev
`pytest==8.4.2`; lock includes `httpcore==1.0.9`, `h11==0.16.0`. No Google
client/auth/httplib2 pins. Local module inspection finds no `googleapiclient`,
`google_auth_httplib2` or `httplib2`. No dependency installed or changed.

Local exact-source inspection: CPython **3.11.14**, Homebrew build `3.11.14_1`,
`http.client.py` SHA-256
`c3968eae8a9f38b0026e9b0ae0d2396b5fb3ade65688a17ed0ffeb4d7d9630f6`.
Inspected `send`, `_send_output`, `endheaders`, `connect`, `getresponse` and
HTTPS `connect`; HTTPX redirect handler and HTTPcore connect/pool handlers.
`requires-python >=3.11` is **not a runtime pin**. The later live runtime/build,
stdlib hashes, OpenSSL/TLS configuration and credential-provider dependencies
must be recorded/pinned and requalified. This pass makes no current-release claims.

| Layer | Ordinary retry / auth / redirects / caching / recovery | Control and resend risk |
| --- | --- | --- |
| `google-api-python-client` (unselected, unpinned) | Frozen reconnaissance §9 reports client retry loop defaults `num_retries=0`; enabled loop can retry selected exceptions, 5xx, 429/rate-limit 403. Auth delegated; GET-to-POST rewrite on long URI was reported. Full redirect/cache/recovery behavior depends on lower stack. | One `execute` is insufficient. If selected, pin source/discovery/dependencies, use `num_retries=0`, prohibit rewriting and qualify exact stack. Earlier mutable-source findings are preliminary, not exact-version certification. |
| `google-auth-httplib2` (unselected, unpinned) | Earlier reconnaissance reports default 401 refresh and recursive original-request reissue, up to two refresh attempts; before-request credential preparation is separate. Lower httplib2 supplies redirect/cache/recovery behavior. | Earlier `max_refresh_attempts=0` recommendation must be verified on selected version. No installed exact-version proof exists. Do not use mutation-response-driven refresh/reissue. |
| `google-auth` (unselected, unpinned) | Potential credential refresh during preparation and transport-specific auth-response recovery. Credential types and their token transport may have retries of their own. | Token-only retries are not Sheets retries but must be isolated/classified. Choose/pin exact credential type and preparation interface before live; no mutation-capable auth wrapper. |
| `httplib2` (unselected, unpinned) | Exact ordinary retry, stale-connection recovery, redirect, caching/auth-challenge behavior **not established** in this environment; not imported or downloaded. Frozen reconnaissance explicitly leaves it unresolved. | No universal or sufficient `RETRIES=0` assertion. Would require exact source audit and fake-wire tests of retries, 401, redirects, cache validation and reconnect/send failure. Not recommended for this first path. |
| HTTPX 0.28.1 / HTTPcore 1.0.9 (already locked, alternative) | Inspected redirect loop follows only when enabled. HTTPcore configured connect retries affect TCP/TLS establishment; pool retries assignment on `ConnectionNotAvailable`. Auth middleware can issue multiple requests depending on auth flow. No status-code retry loop in those inspected handlers. | The pool reassignment loop is not evidence of a post-send mutation resend, but enlarges audit surface. Would need `follow_redirects=False`, zero connect retry, no mutation-capable auth flow, no proxy/env trust and lower network-stream instrumentation. A MockTransport counter alone does not qualify pooled wire behavior. |
| CPython 3.11.14 `http.client` (recommended send layer) | `send` reconnects on absent socket only if `auto_open`; bytes use one `sendall` per buffer. `_send_output` sends headers then literal body; `getresponse` parses/closes, does not retry. No auth refresh, redirect-following, cache, pool or status retry in this chosen flow. HTTPS connect adds TLS to one explicit connect. | Explicit connect once, `auto_open=0`, exact bytes, debug off, close always. Do not use iterable/file bodies, tunnels or custom retry wrappers. Socket/TCP retransmission is not another HTTP request. Fake tests cover missing socket and partial body send. |
| Repository wrappers | GitHub has one-attempt flow; no Sheets production wrapper. Model clients/SDKs are not the Sheets mutation path. | New offline flow has no loop, no response reissue, no LLM call. Arbitrary new middleware/runner loops invalidate this evidence until audited. |

Unselected packages were investigated through repository absence and the frozen
source findings, not by fetching mutable `main` or asserting exact-version
behavior. Exact-version unknowns are blockers if those packages are chosen.

## 7. Smallest defensible transport recommendation

Generated client benefits: schema-oriented request construction, discovery and
familiar Google credential integration. Costs here: dynamic construction/defaults,
SDK retry loop, auth reissue layer and httplib2 recovery/cache/redirect surface;
`.execute()` hides lower dispatches. A frozen generated request could work, but
requires substantially more exact-version qualification. Do not install it merely
to follow a documentation example.

Recommend **hand-prepared frozen REST bytes plus a separate fresh stdlib
HTTPSConnection single-attempt transport**, following the already-evidenced
repository mechanics without importing/refactoring GitHub internals. Runtime
bearer preparation happens before consumption of the initial mutation capability;
mutation transport receives only a ready token and cannot refresh/reissue on 401.
Token acquisition, credential type, expiry margin and token transport are not yet
selected or implemented. Pin those later; fail before send if readiness cannot be
established. A visible 401 terminates engineering qualification; token repair never
automatically redispatches that mutation. Between explicitly authorized policy
actions, credential preparation may run again without changing mutation identity.
The selected credential-preparation layer must define, freeze and test its own
readiness/expiry margin before mutation dispatch; no fixed token TTL threshold is
imposed by this offline contract. A visible 401 cannot enter target replay/regeneration.

This is a proposed stack, not an authenticated live implementation. No auth SDK
is needed for this offline proof, and none is added. HTTPX remains unchanged for
existing work. Switching to HTTPX or a generated client later requires revisiting
this contract and fake-wire layer, not swapping the transport silently.

## 8. Offline harness and demonstrated limits

`sheets_offline.py` prepares the candidate, hashes identity, stores dispatch records,
qualifies a retry-entry event and runs the proposed single-attempt control flow.
`OfflineWire` uses a fake subclass of HTTPConnection whose connect only attaches
a fake socket. Real stdlib request serialization and HTTPResponse parsing operate
on synthetic bytes/BytesIO. Socket creation is forbidden by the test fixture.
No Google endpoint is contacted even though the synthetic Host names the future
origin. The dispatch function requires exactly this offline wire type and offers
no live HTTPS factory. No Sheets state/commit simulator exists.

Synthetic status responses include Location and Retry-After to challenge refusal.
401 tests the no-auth-response-handler proposed boundary; **it does not test an
unselected Google credential SDK**. AFTER_SEND stops before response construction;
WAIT_LOSS now returns a valid closable stream from `makefile()` so HTTPResponse
initializes its `fp` normally, then raises TimeoutError from the stream's first
status-line `readline()`. No status is exposed; HTTPResponse and connection cleanup
close the stream. BODY_LOSS exposes parsed status then fails read. No warning
suppression/filter is used. The full synthetic fault matrix must pass under
warnings-as-errors, with cleanup collected inside pytest rather than after exit.
`Fault.PARTIAL_SEND` now labels its mode `synthetic_incomplete_body_send`: it raises
inside the fake body send after request initiation. It records no estimate of bytes
delivered remotely, or exact delivered fraction. Result is `incomplete_send_unknown`
with no local-send-completed event; target qualification is forbidden. This is not
the specified completed-send fault. A manually injected second dispatch before
qualification must be rejected.
Manual second dispatch after qualification tests frozen byte reuse, not execution
of an experiment policy or paper arm. No model integration or trial catalog added.

The fake counter is exact for its controlled fake boundary. It does not certify
TLS, live socket hooks, actual Google commit, read visibility, auth expiry,
runtime crashes, remote proxies or server-internal duplication. Later HTTPS factory
and credential-boundary code must run the same fault matrix offline before use.

## 9. Fail-closed invariant and fault boundary

Immediately before explicit experiment retry handling:

> For the target case, observed mutating dispatch count MUST equal exactly 1,
> the frozen identity MUST match, local send MUST have completed, and no
> definitive HTTP status may have reached policy code.

v0.2 preserves this invariant and requires corroborating lifecycle evidence:
before policy entry, exactly `dispatch_initiated` then `local_send_completed`,
both linked to the sole mutation record, no observed status, target `ambiguous`
classification, matching identity and no prior policy entry. Missing, duplicate,
wrong-dispatch or status-observed lifecycle evidence fails closed even if a
supplied `LocalResult` claims eligibility. This strengthens evidence validation;
it does not redefine initiation as full-body delivery or assert remote receipt.

Count all mutating traffic in the isolated trial, not only marker-matching writes.
0 means known non-dispatch/injector too early; >1 means hidden resend/client-stack
invalid. Visible 2xx means known HTTP success, including missing/malformed body;
it never becomes the target ambiguity. A known 4xx/5xx or redirect is a definitive
HTTP result, not the target event. No automatic retry on such results is permitted
in engineering qualification. Invalid evidence blocks policy and further mutation.

Target later fault: initial one-use capability consumed; request prepared and
handed to lower transport; first socket header handoff recorded once; unchunked
header/body send completes; inject loss **before `getresponse`**; close; no status,
headers/body or landing diagnostics exposed; remote commit unknown; record explicit
policy entry; only now choose replay/regeneration. Read-only engineering verification
may follow with separate capability. Cleanup may not imply cancellation/rollback.

Handoff alone is weaker than send completion. Socket-write completion is weaker
than receipt/commit. Incomplete write is explicitly `incomplete_send_unknown`,
excluded from this first target boundary. A before-send fault is a negative control,
not service-reached H0. H0/H1 are latent worlds and are never returned as local classifications.
Exact HTTPS send/close semantics and remote commit/read-back remain later live
engineering questions; never fabricate H0 from no match.

## 10. Read-only verification and isolation

Future fixture: dedicated engineering spreadsheet, dedicated GRID sheet with
manifest numeric sheet ID and immutable trial title-to-ID mapping; no Table
needed. No human collaborators, concurrent writers, scripts/triggers, automation,
formulas, merged target cells, sorts or structural edits. Whole sheet initially
contains only a known contiguous three-column literal-string fixture/header (or
an audited empty baseline); all other cells contain no data. Choose one baseline
form before protocol freeze. Audit entire sheet/data boundary before activation,
not just the likely append location. Reserve capacity for initial plus explicit
replay, and freeze maximum landing row/cell coverage independently of lost reply.

Conceptual verifier: bounded literal GET `spreadsheets.get` with
`includeGridData=true`, one manifest A1 range covering all possible landing rows,
and narrow fields for sheet identity/grid extent/start offsets and
`rowData.values.userEnteredValue`. The range/title are frozen pre-dispatch;
when `fields` is supplied it controls grid inclusion and overrides the
`includeGridData` flag, so grid fields must be explicitly included in the mask.
Use short separate GETs if necessary, never POST override. Map sparse/trailing omitted
grid data with startRow/startColumn offsets and field-mask semantics; omitted
trailing cells are not fabricated rows. Freeze parser/coverage rules offline using
official exact-version discovery/doc evidence and synthetic sparse replies.

Use only a separately constructed read capability with actual method/origin/path/
query allowlisting; it must refuse batchUpdate and all non-GET requests before
dispatch. No mutation-response fields/IDs/range required. Count marker matches by
distinct current row coordinates within the fixed sheet and require exact full
three-cell content. Coordinates are observation keys under isolation, not durable
row-object IDs. Record duplicates/anomalies/content mismatch separately. Permission
errors, parser failures, truncation, changed grid/identity or incomplete coverage
produce unknown, never zero. Marker absent in a complete read is currently
unobserved, not historical noncommit. Reads are not a universal historical oracle.

Repeated reads, if later allowed, must be explicit bounded engineering traversals,
each persisted separately with timings; no hidden polling. Bounds/visibility timing
remain unselected; do not copy GitHub schedule. Remote append placement,
preservation, complete landing coverage and sparse/read interpretation require
later live validation. No verifier or live read is implemented in this pass.
Fixture setup/cleanup are separate authorized engineering mutations outside the
ambiguous trial window, never hidden under verification or policy handling.

## 11. Integration and model visibility

Later Sheets boundary should receive a frozen application mutation plus controlled
dispatch/read capabilities. Keep it outside Study 1 `TicketEnvironment`, hidden-world
construction, locked contexts/metrics and completed GitHub engineering. Exact replay
validates identity then sends saved bytes once per explicitly authorized action.
Regeneration receives original task/tool-call history plus a provider-neutral
unknown-outcome tool error, never H0/H1, verifier ground truth, internal socket
events or lost response identity. It may produce a new action subject to separately
designed policy/tool budgets and fixture scope constraints.

Existing canonical Study 1 text is `ToolError: The previous request timed out.
Its outcome is unknown.` A synthetic after-send connection close is not necessarily
a timeout: adopt consistent unknown-outcome wording with truthful failure type in
a separate Study 2 protocol; do not silently alter the locked Study 1 constant.
Which verifier information each arm sees, marker preservation in regenerated
actions and action budgets are unresolved research choices. This pass implements
neither policy nor LLM arm.

## 12. Evidence and secret exclusion

Later qualification artifacts must declare ENGINEERING ONLY and persist:

- Frozen nonsecret identity envelope and lossless mutation body, hashes, preparation
  time and exact replay comparison result; reserved namespace and case identity.
- All classified dispatch records, complete lifecycle order, send-completion flags,
  policy-entry event, UTC/monotonic timestamps, local classification/visible status.
- Fault mode and intended/actual firing boundary; no-match/anomaly evidence without
  H0/H1 inference; any invalidation reason and refusal of further mutation.
- Every verification GET's nonsecret method/target/options, coverage/completeness,
  normalized cell/row evidence and marker count/content result, separate traversals.
- Runtime/build, stdlib/source hashes, selected pinned packages/lock hash,
  transport/auth configuration, fixture spreadsheet/sheet/range manifest without
  secrets, baseline/isolation checks, and authorization/gate status.

Never persist bearer/refresh tokens, secret headers, auth payloads/hashes, cookies,
credential objects, credential file paths/content, raw exception text, arbitrary
Location/error bodies or full unfiltered response headers. Trace through allowlists,
not serialization of arbitrary config/exception objects. Persist only explicitly
allowlisted evidence fields; never serialize arbitrary request headers, credential
objects, raw config or raw exception objects. Reject unknown/unapproved fields
before serialization rather than persist them through a generic fallback. Evidence
validation/serialization failure invalidates qualification and must not trigger
mutation reissue. The existing placeholder bearer does not appear in exported
dispatch records or the new lifecycle log; this pass does not claim an existing
Authorization leak. Reject supplied secret values in controlled mutation content/
URLs before live dispatch; redact or reject
echoes in permitted provider fields. Tests must inject synthetic secret echoes at
every future input/response/log path. Offline records currently contain only safe
synthetic request labels/hashes and fixed classifications; placeholder bearer is
excluded. That limited test is **not** comprehensive credential-echo certification.
Reserve writable artifact storage before dispatch; recorder/storage failure invalidates
qualification and must never trigger a resend. Crash durability remains unqualified.

## 13. Engineering qualification matrix

Counts below mean before explicit retry-policy entry. A definitive HTTP error is
a status result; it does not establish remote cell-state outcome independently.

| Case | Expected mutation dispatches | Local classification | Retry policy allowed? | Qualification meaning / current coverage |
| --- | ---: | --- | --- | --- |
| Normal 2xx | 1 | known success | no | Positive transport control; 200/201/204 synthetic (payload semantics not certified) |
| Pre-dispatch/connect failure | 0 | known non-dispatch | no | Negative control; tested |
| Missing socket before send | 0 | known non-dispatch | no | No auto-reconnect; tested |
| After completed send, before status | 1 | ambiguous | yes, after gate | Target local boundary; tested |
| Response wait loss | 1 | ambiguous | yes, if completed send | Natural-loss analogue; tested |
| Synthetic incomplete body send | 1 initiation | `incomplete_send_unknown` | no for first target | Initiation recorded, no completion/status; no remote delivery estimate; tested |
| Visible 2xx then body loss | 1 | known success/incomplete response | no | Negative control; real synthetic parser tested |
| Visible 401 | 1, never >1 | auth issue | no | Tested no reissue in proposed bearer-only boundary; future auth-preparation stack unqualified |
| Visible 400/403 | 1 | known HTTP error | no | Tested |
| Visible 429 + Retry-After | 1, never >1 | known HTTP error | no | Tested no hidden retry |
| Visible 500/503 | 1, never >1 | known HTTP error | no | Tested no hidden retry |
| 301/302/303/307/308 + Location | 1, never follow | redirect refused | no | Tested |
| Deliberate hidden resend | >1 | invalid evidence | no | Hostile falsification: gate rejects; tested |
| Fabricated ambiguity with zero sends | 0 | invalid evidence | no | Gate rejects; tested |
| Missing/duplicate/wrong-dispatch completion event | 1 initiation | invalid evidence | no | Lifecycle corroboration rejects falsely eligible result; tested |
| Visible status erased from supplied result | 1 | invalid evidence | no | Recorded status still forbids target entry; tested |
| Changed body/application header/target/method/query | any | invalid replay identity/conformity | no | Scientific envelope changes detected; emitted mismatch fails closed |
| Wrong routing/framing/configuration, missing/duplicate/unexpected serialized headers | invalid qualification | serializer-envelope failure | no | Full seven-header schema enforced before completion; not a new identity hash or receipt proof |
| Explicit second dispatch after gate | 1 before, 1 after | separately classified | explicit only | Same bytes object and order bits tested, no arm executor |
| Actual verification capability / sparse reads | 0 additional mutations | current state / unknown | no implicit mutation | Not implemented; offline blocker |
| Auth traffic and secret-echo paths | 0 Sheets mutations | separate auth readiness | no response reissue | Declarative categories only; exact stack/log certification pending |

First pass: 35 focused tests passed in 0.04 seconds. No shared files or dependency
files changed. Historical v0.1–v0.4 validation records follow below.

## 14. First-live-mutation gate (currently CLOSED)

Before **any first Sheets mutation**, including fixture creation if done by API,
all required offline work must be auditable, hostile-audited, iterated and frozen
through the agreed workflow. Later credential/fixture setup needs its own explicit
authorization; this frozen offline contract supplies none. Nontrial setup must not be counted as a
paper observation or smuggled into a verification window.

- [ ] Candidate and isolated layout selected for first engineering use; actual
  nonsecret target supplied/reserved later; exact request prepared once and saved
  before dispatch with independently validated body/envelope hashes.
- [ ] Live single-attempt transport implemented and source-audited on pinned
  runtime/build/TLS/stdlib; any selected auth packages/type/token transport pinned.
- [ ] Credential preparation isolated before send; expiry/readiness refusal tested;
  mutation response cannot initiate refresh/reissue, fallback, redirect or retry.
- [ ] Runtime lowest-layer counter/classifier captures all connections/dispatches,
  exact target/body/application headers and before/after policy order; unexpected
  or opaque traffic fails closed. Recorder failures do not cause resend.
- [ ] Exact selected live code path passes fake-wire clean, zero-send, partial-send,
  one-send ambiguity, visible-2xx/body-loss, 401, 429, 500/503, redirect, hidden-resend
  and changed-identity falsifications, with sockets/operational APIs blocked.
- [ ] One-send ambiguity gate requires count exactly 1, matching frozen identity,
  local-send completion, absent status and explicit recorded retry entry.
- [ ] Post-ambiguity capability is enforced GET-only with bounded frozen coverage;
  synthetic sparse/malformed/read-error/anomaly tests pass without mutations.
- [ ] All credential/content/response/exception paths pass secret-exclusion tests;
  evidence schema/storage reservation and invalidation handling reviewed.
- [ ] Dedicated fixture manifest/baseline/isolation requirements and complete
  landing/read coverage checks are ready; setup/cleanup separated from trial.
- [ ] Focused tests and relevant regressions pass; frozen reconnaissance, Study 1
  and completed GitHub behavior verified unchanged; contract hostile-audited then
  frozen/committed only in a separately authorized workflow step.
- [ ] User authorizes later credentials/fixture/live engineering gate explicitly.
  First live clean success/read-back qualifies remote behavior before any later
  ambiguous live fault; exact HTTPS fault and visibility assumptions are reported
  as unvalidated until demonstrated. No paper collection follows automatically.

The offline engineering contract is frozen, but the live-go checklist remains
open; no unchecked item is marked complete by this freeze. The next separately
gated phase is to implement and qualify the remaining offline/live-preparation
items: enforced read-only capability/parser, pinned runtime and credential-
preparation interface, actual HTTPS mutation instrumentation, fixture manifest,
evidence persistence/secret qualification, and the eventual first controlled live
engineering validation. No live request is authorized by this freeze.

## 15. Evidence provenance

Provider-semantic comparisons use the frozen reconnaissance §§4, 9–11 and its
official Google source references, not new online retrieval. Exact local source
evidence concerns only the installed versions identified in §6. All other package
behavior is explicitly preliminary/unqualified. No documentation/source network
retrieval occurred in this task. Fake-wire outputs are engineering assertions,
not observations of Google or evidence of H0/H1 commit state.

## 16. First-pass offline validation record (historical)

Focused command:

```bash
.venv/bin/python -m pytest -q tests/test_study2_sheets_offline.py
```

Result: **35 passed in 0.04 seconds**. Each new test forbids socket construction
and `socket.create_connection` through an autouse fixture.

Socket-disabled, credential-environment-cleared Study 2 regression command:

```bash
.venv/bin/python -c 'import os, ssl, asyncio, socket, pathlib, pytest; names = [name for name in os.environ if name.startswith(("STUDY2_", "GOOGLE_", "GROQ_", "FIREWORKS_"))]; [os.environ.pop(name, None) for name in names]; denied = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden during offline qualification")); socket.socket = denied; socket.create_connection = denied; raise SystemExit(pytest.main(["-q", *[str(p) for p in sorted(pathlib.Path("tests").glob("test_study2*.py"))]]))'
```

Result: **479 passed in 0.30 seconds**, including the 35 new tests and 444 existing
Study 2 tests. An initial version of this command replaced the socket class before
SSL/asyncio imports and failed during pytest plugin import (no tests executed);
preloading those modules before installing the socket denial corrected the
validation setup. No network fallback or dependency installation was used.

Tracked `git diff --check` passed. Untracked additions were also checked individually
with `git diff --no-index --check /dev/null <file>`. All tracked files have zero
diff; therefore Study 1, frozen Sheets reconnaissance, completed GitHub code/docs,
dependencies and lockfile are unchanged. All three additions remain untracked;
ordinary `git diff --stat` is empty for this reason, not because additions are absent.
No staging, commit, push, audit ZIP or frozen status was introduced.

## 17. v0.2 adjudication and validation (historical)

The hardening accepts clearer incomplete-write state and better local lifecycle
corroboration. It does not mechanically implement rejected hostile claims:

| Rejected recommendation/claim | Reason and preserved behavior |
| --- | --- |
| `N=1 iff FULL_BODY_SENT` | Dispatch counts initiation at socket handoff; local write completion is a separate gate fact, never proof of remote delivery. |
| Partial send is known noncommit/H0 | A sendall error does not reveal delivered amount. Use `incomplete_send_unknown`, exclude target entry. |
| Fixed 60-second token TTL | Unselected credential preparation must define and test a frozen readiness/expiry margin. No arbitrary threshold added. |
| `values.get` is already the verifier | Contract proposes future bounded `spreadsheets.get` grid reads; no verifier implemented. |
| Cryptographically random markers required | Reserved run/case namespace, baseline absence and isolation remain the marker contract; no new randomness requirement. |
| Replay must reserialize JSON | Canonical preparation happens once; explicit replay retains stored body bytes. Envelope hashing does not reserialize the mutation body. |
| Sheet-targeted AppendCells has a strict bounding range | Mutation targets numeric sheetId and appends after sheet data. Bounding applies to future verified read coverage, not a nonexistent mutation parameter. |
| Current visible-2xx/body-loss path is ambiguous | Existing code retained status correctly. Strengthened tests preserve known success/incomplete response. |
| Current dispatch records leak Authorization | Placeholder bearer was already excluded; new lifecycle likewise records only fixed fields and status. Future broader secret-exclusion certification remains open. |

No candidate, auth stack, live transport or read-verifier redesign occurred.
The Python enum symbol `Fault.PARTIAL_SEND` is retained; its evidence mode string
is now `synthetic_incomplete_body_send`, explicitly without a delivery estimate.

Focused command from §16: **44 passed in 0.06 seconds** on initial v0.2 validation.
The same socket-disabled/credential-environment-cleared Study 2 command from §16:
**488 passed in 0.30 seconds**, including 44 Sheets tests and all 444 existing
Study 2 tests. Final repeat after the last test strengthening: **44 passed in
0.06 seconds** focused, **488 passed in 0.29 seconds** socket-disabled regressions.
Changes comprise nine added test cases plus strengthened existing assertions:
typed lifecycle ordering/linkage/immutability, explicit incomplete-write exclusion,
missing/duplicate/wrong-dispatch completion rejection, visible-status retention on
2xx and 401/429/500/503 body loss, forged-result rejection, no prior policy entry,
separate explicit second dispatch, and secret-free exported lifecycle evidence.

Unresolved offline blockers remain: actual live-path counter/classifier and runtime
pin, isolated pinned credential-preparation interface, enforced read-only capability/
grid parser and sparse/error coverage, comprehensive secret exclusion, full evidence
storage/invalidation qualification, fixture manifest and hostile audit/freeze.
Later live gates remain separately authorized setup and clean success/read-back,
actual HTTPS send/close fault qualification, remote placement/preservation/coverage
and visibility evidence. Fake sockets prove neither TLS nor Google behavior.

No network/source retrieval or operational API call occurred; local Python sendall
docstring inspection only. No credentials, OAuth, live Sheets read/mutation, Study 2
observation, paper collection, audit ZIP, staging, commit, push or freeze occurred.

Final tracked `git diff --check` and individual no-index whitespace checks of all
three untracked artifacts passed. Tracked/staged diffs remain empty, and the frozen
Sheets reconnaissance still matches commit `26609e4` byte-for-byte. Study 1 and
completed GitHub files remain unchanged. No dependency files changed.

## 18. v0.3 correction and warning-clean validation (historical)

Review identified a real cleanup hazard in v0.2: raising inside `makefile()` can
leave HTTPResponse partially constructed without `fp`, producing an unraisable
cleanup exception. The pre-edit warning-as-error command happened to pass locally
(44 tests in 0.04 seconds); this does not refute the independently reproduced
warning or the locally inspected constructor/cleanup defect. The fix moves the
fault to the first status-line read of `_UnreadStatusStream`, after initialization.
It preserves one initiation, completed local write, no visible status, `ambiguous`
classification and target eligibility. Fake response streams are retained only for
synthetic test inspection so clean closure can be asserted explicitly.

Added 14 focused cases: three genuine emitted-header/body mismatch cases, one
initialized-response/first-read/closure WAIT_LOSS test, all eight fault modes with
connection/stream closure assertions, and two negative lifecycle tests (status
before completion; completion attached to the wrong one of two dispatches).
Existing wrong-single-dispatch completion test remains unchanged. Test-only
monkeypatching changes serialized Accept, Content-Type or body bytes at the stdlib
send boundary while leaving the frozen object/body/hash unchanged; every mismatch
raises and forbids target qualification. No production tampering API was added.

The autouse offline test fixture now performs `gc.collect()` during teardown so
deferred cleanup runs under pytest's warning/unraisable-exception handling.
No warning is filtered or suppressed. Executed validation:

```bash
.venv/bin/python -m pytest -q tests/test_study2_sheets_offline.py
.venv/bin/python -m pytest -q -W error tests/test_study2_sheets_offline.py
```

- Normal focused: **58 passed in 0.31 seconds**, no warnings.
- Warnings-as-errors focused: **58 passed in 0.40 seconds**, no warnings,
  unraisable exceptions or resource warnings.
- Same socket-disabled/credential-environment-cleared Study 2 command in §16:
  **502 passed in 0.73 seconds**, including all 444 existing tests, no warnings.
- Tracked and individual untracked no-index whitespace checks passed; tracked/
  staged files unchanged, frozen reconnaissance byte-identical to `26609e4`.

Audit reproducibility: the next audit ZIP must include the existing
`src/retry_semantics/serialization.py`, which the harness imports and the v0.2 ZIP
omitted. This is a packaging correction, not duplicated/moved/reimplemented code.
No ZIP was created in this pass.

No known defect from the v0.3 findings remained at that review point; the subsequent
header-envelope blocker and v0.4 correction are recorded in §19. Freeze still requires its separate workflow
gate. This is not qualification of the first live mutation. The open offline
live-go work and later live-engineering gates in §§14/17 remain open, including
actual transport instrumentation, runtime/auth pins, enforced read-only verifier,
broader secret exclusion, fixture/evidence qualification and remote validation.
The candidate, marker approach, request bytes/replay, incomplete-send state,
visible-status/401 behavior and deferred grid verifier remain unchanged.

No network/API calls, credentials/OAuth, live Sheets reads/mutations, Study 2
observations, paper collection, audit ZIP, staging, freeze, commit or push occurred.
Study 1, frozen Sheets reconnaissance and completed GitHub behavior are unchanged.

## 19. v0.4 declared serializer-envelope qualification (historical)

Final v0.3 hostile audit found a real qualification blocker: Host, Content-Length
and unexpected additional headers were not checked by the selected-header observer.
Before the implementation fix, expanded emitted-wire tests reproduced those missing
checks (24 newly required refusals failed; seven previously checked cases passed).
The v0.4 observer now validates the complete declared schema in §4, preserving
scientific application identity separately from routing/framing conformity and
Authorization security handling. No state-model, transport, credential or verifier
redesign occurred. No production tampering API was added.

Added 35 cases beyond v0.3: 28 emitted-envelope attacks, two positive casing/bearer
cases, and five synthetic-token secrecy cases. The unchanged frozen object/body/
identity are tested while serialized bytes are tampered at the stdlib send boundary.
Coverage includes Host `evil.invalid`, too-large Content-Length `999`, too-small,
noninteger/negative length, quota-project/unknown headers, Transfer-Encoding,
gzip/keep-alive changes, all seven missing headers, casing-conflicting duplicates
of each declared header and conflicting duplicate Content-Length, malformed/folded
lines and wrong Authorization scheme. Every attack fails closed before completion
or policy entry. Header names remain case-insensitive; a changed well-formed bearer
still permits the target local ambiguity without changing scientific identity.

Synthetic `Bearer ya29.hostile.test.secret` tests serialize permitted dispatch/
lifecycle evidence and safe error type/message/repr/args after routing, extra-header,
duplicate-auth, auth-form and body conformity failures. No token, token prefix or
raw Authorization value appears. The body attack additionally checks safe evidence
with one initiation record present. No raw header map or exception/config object is
persisted. Existing placeholder-exclusion tests remain unchanged.

Audit reproducibility: 502 was a **repository regression result, not independently
reproduced from the minimal v0.3 bundle**; the reviewer reproduced the focused 58
normal/warning-as-error tests. The current repository-wide result below has the
same packaging scope. Next minimal audit/freeze ZIP must label that limitation and
include the existing serialization module; no historical tests are copied into code
and no ZIP is created in this pass.

The accepted distinction remains: initiation != local completion != unknown
remote receipt/commit. No scientific identity includes bearer credentials or socket
metadata, and no controlled envelope check claims independent wire attestation.
The no-live-go checklist remains open. Executed v0.4 validation using the focused
commands in §18 and socket-disabled repository command in §16:

- Normal focused: **93 passed in 1.21 seconds**, no warnings.
- Focused `-W error`: **93 passed in 1.22 seconds**, completely warning-clean;
  no suppression/filtering added and forced cleanup remains enabled.
- Socket-disabled repository Study 2 regression: **537 passed in 1.69 seconds**,
  including all 444 unchanged historical tests. This is the repository regression
  result, not a result independently reproducible from a minimal focused bundle.
- Tracked `git diff --check` and untracked no-index checks passed; all tracked and
  staged files unchanged. Frozen reconnaissance SHA-256 matches `26609e4`:
  `940bb8c50aad7c87893b633763d5530af167b988c91e52881e9e422b2491fc7e`.

No known offline artifact freeze blocker from the reviewed findings remains after
this hardening and validation; the separate audit/freeze workflow gate has not been
taken. Actual live-path counter/classifier, runtime/auth pins, read-only verifier,
broader secret/evidence/fixture qualification and later authorized remote validation
remain live-go blockers. None is satisfied by this fake-wire envelope proof.

No network/API calls, credentials/OAuth, live reads/mutations, Study 2 observations,
paper collection, audit ZIP, freeze, staging, commit or push occurred. Frozen Sheets
reconnaissance, Study 1, completed GitHub behavior and dependencies are unchanged.

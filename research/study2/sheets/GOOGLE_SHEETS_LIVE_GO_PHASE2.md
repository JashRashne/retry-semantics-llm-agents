# Google Sheets LIVE-GO closure — Phase 2

**FROZEN OFFLINE LIVE-GO PHASE 2 — LIVE-GO CLOSED — ZERO SHEETS PAPER OBSERVATIONS**

Prepared 2026-09-18; Phase 2 offline prerequisites frozen after independent hostile
re-audit. Freeze remains uncommitted. Repository HEAD at
Phase 2 creation entry: `d55ddf8` (exact Phase 1 freeze commit); that entry working tree was clean. No
applicable repository AGENTS.md was found. No commit, push or tag performed.

The first independent Phase 2 audit returned **REPAIR REQUIRED — NOT SAFE TO FREEZE
YET**. Repair entered the existing uncommitted Phase 2 working tree in place.
This working tree repairs the raw-send authorization expiry and missing
same-connection TLS evidence blockers, clarifies the OAuth/local capability
boundary and expands the explicit spawn implementation binding. Both blockers
were repaired and independently re-audited successfully. The final independent
hostile re-audit verdict is:
**SAFE TO FREEZE GOOGLE SHEETS PHASE 2 OFFLINE PREREQUISITES**.
This offline freeze does not authorize a live action. Actual Google CA/trust
inventory, peer/chain/SNI/hostname, proxy-free route, response framing, same-app
drive.file fixture provenance, credential acquisition, real human authorization
and live read success remain unestablished.

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool
Calls Under Ambiguous Outcomes*. Academic byline: **J. Rashne**.

## Scope, inheritance and freeze boundaries

Infrastructure qualification only, not paper data. All four frozen conceptual
layers and their documents/modules/tests remain byte-identical to entry HEAD:
reconnaissance, offline contract, live preparation and Phase 1. The frozen runtime
pin and original fixture template are unchanged. Only current checklist metadata
and an explicitly additive qualification prerequisite paragraph are updated.

Phase 1 selected dedicated engineering OAuth user credentials, desktop
installed-app authorization code with PKCE S256, exact `drive.file` scope and
Bearer token type; DPoP was not selected. Future successful acquisition still
requires an acceptable access_token, finite positive expires_in, exact granted
scope set and token_type Bearer. Acquisition/SDK/version/source, browser flow,
exchange and refresh are absent. The transport accepts only immutable prepared
literal token material and independently typed nonsecret provenance assertions.

`drive.file` is **not a read-only OAuth scope**. It permits operations, including
mutations, on the specific files authorized for the app. `LIVE_READ_GO` is a
**LOCAL runtime/wire capability** enforced by this narrow adapter, not a restriction
imposed by the bearer itself. The read path must never expose that bearer to a
generic mutation-capable client. The selected single scope and same-app/file
relationship are unchanged.

Phase 1's factory grants exact capability equality at construction only, returns
a trusted raw connection and has process-local one-use state. Phase 2 implements
a separate durable local claim and a private connected GET boundary, using the
same fresh stdlib HTTPSConnection, explicit verifying SSL context, environment
gate and frozen verifier shape. It does not retrofit or alter Phase 1 history.

REQUEST REPLAY remains exact redispatch of the already-generated frozen mutation
without LLM reasoning. LLM REGENERATION exposes ambiguity to the model and permits
post-ambiguity generation. Runtime-controlled versus model-controlled recovery
remains the scientific distinction; neither arm is implemented here.

No Google request, fixture provisioning, real authorization, token acquisition,
TLS trust validation or paper observation occurred. Counters: live reads **0**,
live mutations **0**, Sheets paper observations **0**.

## Artifacts and architecture

New control plane: `src/retry_semantics/study2/sheets_phase2_control.py`.
New read boundary: `src/retry_semantics/study2/sheets_phase2_read.py`.
New non-executable specification: `fixtures/qualification_fixture_phase2_template.json`.
New hostile tests: `tests/test_study2_sheets_phase2.py`.
New offline-only runner: `scripts/qualify_sheets_phase2_offline.py`.
No dependencies, lock, scientific serialization, GitHub or Study 1 changes.

The future sequence is: separately provision/select fixture; separately acquire
and prepare token; bind qualified runtime/source/fixture/registry configuration;
operator issues LIVE_READ_GO; reserve attempt evidence; consume authorization
durably; activate one spawned read worker; construct/connect once; capture and
durably persist typed TLS facts from that exact socket before HTTP serialization;
persist request-start intent; recheck exact authorization and token readiness at
the guarded raw-send boundary; emit one guarded GET; parse bounded response;
persist only typed summaries.
This implementation issued no genuine authorization and executed no live step.

The public ReadAdapter exposes inspect only. Construction/import performs no
registry reservation, SSL creation, DNS or connection. Missing authorization is
refused, and TEST_ONLY fixture identities are refused by the production path.
There is no CLI for live reads and no public connector injection, arbitrary method,
URL, path, query, body, headers or raw connection. Private fake seams used by tests
are trusted Python code, not a security sandbox or alternative live permission.

## Specification, fixture identity and same-app provenance

The new JSON specification has null actual IDs, row count, namespace, reservation
and provenance. It is explicitly non-executable. It is separate from the frozen
original mutation-oriented draft fixture. It does not assert a Google fixture
exists. No real identifiers are invented or saved.

QualificationFixture is strict, frozen and canonical. Its manifest binds schema,
engineering-only purpose, identity kind, spreadsheet ID, numeric expected sheet ID,
fixed title RetrySemanticsEngineering, GRID type, qualified row count (3–1000),
exactly three columns, whole-grid verifier range, reservation ID, deterministic
namespace, verifier case qualification_read, and SameAppProvenance. The canonical
manifest hash changes on material identity/range/provenance changes.

SameAppProvenance requires created_by_same_app or selected_through_same_app,
reviewed public app-config hash, independent account alias and provisioning
record digest. These are assertions backed by future separately reviewed evidence,
not proof that this phase performed provisioning. An arbitrary spreadsheet ID
alone is insufficient; successful GET must never manufacture same-app provenance.
CredentialProvenance's public config hash and account alias must agree with the
fixture, and exported expiry/clock uncertainty must agree with PreparedToken.
Local checks do not establish issuer validity, account control or remote acceptance.

TEST_ONLY identities must start TEST_ONLY_. PROVISIONED identities reject known
test/draft/offline/placeholder strings, malformed escaping, path/query syntax and
short placeholders. Syntactic validity alone is not provisioning evidence or a
grant. Tests use TEST_ONLY fixtures exclusively and private identity bypasses only
inside fake worker qualification; there is no public operational bypass switch.

Namespace = SHA-256 of canonical schema + spreadsheet ID + sheet ID + reservation
ID. Marker = ENGINEERING-ONLY-{namespace}-qualification_read. Range and extent
are additionally bound by the manifest hash. No marker was written to Google.

## Local reservation and durable storage

LocalRegistry reserves the entire spreadsheet identity, fixture hash, marker
namespace and reservation ID against accidental local reuse. Reserving another
sheet/range in that spreadsheet in the same registry also collides conservatively.
All existing reservation records are bounded-read, strict JSON/canonical/type
validated and checked for cross-record collisions. Corrupt/incomplete records
abort; they are never assumed unused. Reservation is immutable local experiment
control, **not a remote lock**; external humans, apps and Google can still edit.
Baseline isolation must be independently attested and live-validated later.

The runtime configuration binds the exact absolute, canonical registry root.
A different registry root changes the authorization-bound runtime hash; the
adapter and worker reject root substitution. The operator must retain this single
qualified registry rather than copy, erase or reset it. A directory replacement
or manual deletion is an incident requiring review, never automatic recovery.

Supported storage is a trusted, private POSIX local filesystem with flock,
O_EXCL, O_NOFOLLOW, directory descriptors and fsync. Directory mode is 0700;
files are created 0600 from the start, not chmod after an exposed write. Symlink
ancestors/final entries, unsafe ownership/modes and hardlinked records fail closed.
Directory descriptors pin access during an attempt. An in-process mutex and flock
serialize reservations/claims across threads/processes. Claims themselves use
exclusive creation, surviving loss of the process/lock. New directory creation
syncs its parent; record completion syncs the file and containing directory.
No record is deleted on write/fsync failure. The implementation does not claim
hardware power-loss durability, hostile same-UID tamper protection, network-FS
semantics or global anti-replay across unqualified copied registries.

## Exact read envelope and capability at actual wire use

Origin: HTTPS; exact host `sheets.googleapis.com`; port 443. Fresh stdlib
HTTPSConnection; Phase 1 default verifying SSL context validation and presence-based
ambient proxy/CA/keylog/injection environment gate. No pooled connection, tunnel,
SDK/auth middleware, retries, redirect handler or refresh callback.

Only method: GET. Only path family: `/v4/spreadsheets/{strict_spreadsheet_id}`.
The ID alphabet excludes delimiters and percent escapes so no alternate escaping
or mutation suffix can enter. Canonical urlencode query, in this exact order:

1. ranges = `'RetrySemanticsEngineering'!A1:C{qualified_rows}`;
2. includeGridData = `true`;
3. fields = the frozen verifier's field mask below.

```text
spreadsheetId,sheets(properties(sheetId,title,sheetType,gridProperties(rowCount,columnCount)),merges,tables,data(startRow,startColumn,rowData(values(userEnteredValue))))
```

The existing frozen range/field semantics are preserved; fields explicitly select
grid data rather than relying on includeGridData when a mask is present. Read
coverage is the whole dedicated bounded three-column grid, not an arbitrary
spreadsheet download. No custom, duplicate or additional query is accepted.

Exactly five headers (case-insensitive unique names): Host = qualified host,
Authorization = Bearer plus prepared token, Accept = application/json,
Accept-Encoding = identity, Connection = close. No Content-Length, Content-Type,
method override, body or chunked request. At the actual socket sendall boundary,
the guard checks the exact serialized request line and full five-header envelope,
exact ephemeral bearer, duplicate names and CR/LF syntax before raw handoff. It
spends its send permission before attempting raw sendall and rejects every later
send, including an attempted body. An injected POST/PUT/PATCH/DELETE, batchUpdate
suffix, changed host, query, duplicate or header cannot cross the boundary.

Only one construction, explicit connect, serialization, send and getresponse is
attempted. auto_open = 0 prevents absent-socket reconnection. All non-200 statuses,
including visible 401 and redirects, are terminal; their body is not downloaded
or interpreted. No fallback, credential refresh, polling or second request follows.
This exact local envelope does not prove what remote infrastructure receives.

## Same-connection TLS observation before HTTP

After the successful connect/TLS handshake and CONNECTED event, `observe_tls`
requires the exact stdlib SSLSocket type, client-side socket, expected SNI/hostname
`sheets.googleapis.com`, and identity equality to the connection's explicit SSL
context. It revalidates the inherited default SERVER_AUTH policy: hostname
checking, CERT_REQUIRED, minimum TLS >= 1.2, trust store and no keylog. It reads
only version(), cipher(), selected_alpn_protocol(), getpeercert(binary_form=True)
and getpeername(). No second connection, probe or certificate repr occurs.

The exact positive evidence schema is `sheets-phase2-tls-observation-v1`:

| Fields | Qualified value/shape |
| --- | --- |
| schema | Fixed schema above |
| server_hostname, expected_server_hostname | Exact qualified host |
| socket_type | `stdlib.ssl.SSLSocket` |
| hostname_check, certificate_verification | true, `CERT_REQUIRED` |
| minimum_tls_policy, keylog | `TLSv1.2` lower-bound policy, `disabled` |
| protocol | Negotiated `TLSv1.2` or `TLSv1.3` |
| cipher_name, cipher_protocol, cipher_bits | Bounded ASCII suite metadata; exact tuple must be offered by that context; strength is an integer 1–512, never bool |
| leaf_certificate_sha256 | SHA-256 of nonempty leaf DER bytes (bounded at 65536 bytes); no raw DER |
| alpn | null or `http/1.1`; `h2` and arbitrary values are refused |
| peer_address, peer_port | Canonical bounded IPv4/IPv6 literal, integer 443; no hostnames or interface labels |

The cipher protocol describes a suite and need not equal the negotiated session
version. The leaf digest identifies the certificate supplied by SSLSocket's DER
API; this code adds no independent ASN.1 or chain-validation implementation.
IPv6 flow/scope tuple values are type/bound checked but not persisted. Observed
endpoint information does not establish a proxy-free route or complete chain.

`TLS_OBSERVED` (`tls_observation_persisted`) carries this typed record and is
file-fsynced before wrapping the same raw socket or invoking putrequest/headers.
No other event accepts a TLS field. Socket identity is checked again before
wrapping. Missing/malformed facts produce fixed `tls_observation_refused`; any
observation/persistence failure leaves the claim spent and permits zero HTTP
bytes. Test certificates/endpoints are fake. Actual peer, trust, SNI, route and
negotiation remain **REQUIRES LIVE VALIDATION**, with zero actual TLS observations.

## Response parsing and current-state interpretation

200 is the sole qualified successful status. Response body size and per-cell
character bounds are explicit runtime configuration. Before the separate Sheets
framing patch, READ accepted only a single Content-Length and rejected valid
chunked responses. The shared offline-qualified transport accepts one canonical
bounded Content-Length or sole valid HTTP/1.1 chunked Transfer-Encoding decoded
by `http.client`. It rejects conflicting/duplicate framing, unsupported transfer
coding, close-delimited bodies and compression. Content-Type is
`application/json` with optional UTF-8 charset, with case/OWS handling.
Stdlib status/header line/count limits apply; arbitrary headers, error bodies
and provider content are never persisted. Actual Google framing remains to be
validated under a separately authorized live read.

Read at most the configured decoded body plus one byte. For Content-Length,
require the exact declared byte count; for chunked, require completed standard
library decoding. Require a closed response, then strict UTF-8 JSON with no BOM, duplicate keys,
NaN/Infinity (including numeric overflow), lone Unicode surrogates, concatenated or truncated JSON. Structural fences reject boolean
integer identities/extents, wrong list/dict types, missing data/properties, unexpected
fields, extra sheets/grids, nonempty merges/tables, wrong identity/title/extent,
offsets, formulas/numbers, excessive cells/rows/strings and partial marker rows.
Reuse the frozen literal-grid parser only after these stricter fences. Sparse
trailing omitted rows/cells within one explicit origin-zero data block are blank;
absent data blocks remain uncertainty pending actual Google shape validation.

Persist only zero/one/multiple interpretation, matching current row coordinates,
nonempty-row count, bounded successful byte count, visible status and fixed errors.
Malformed/incomplete response is never zero. Zero means marker currently not
observed, never historical H0 or mutation never happened. The verifier reports
current state, not causality. Missing status, socket closure, local send completion
and missing final evidence establish no remote receipt/commit/noncommit.

`dispatch initiated != local send completed != remote received != remote committed`.
For the future mutation path, any visible HTTP status ends the target commit/no-commit
ambiguity class. This read-only phase does not alter that rule.

## Total deadline

ReadConfiguration supplies finite positive total_seconds, response byte/cell bounds
and canonical registry root. No production timing or size numbers are selected.
The configuration projection, frozen checked runtime/pin, Phase 1 + Phase 2 sources,
new fixture specification and explicit spawn implementation hashes enter the authorized runtime/
source hashes. An authorization for different budget/bounds/root/source fails.
The future operator must separately justify actual numbers and clock uncertainty.

One absolute monotonic deadline starts before prechecks. The same endpoint is sent
to the spawned worker; remaining time decreases across runtime/storage, process
startup, connector/context construction, DNS/TCP/TLS, send, status wait, body read
and parse. Timeout assignments use remaining allowance, not a fresh full stage
budget. Storage time before send is included again before raw handoff.

A parent process supervises one child using anonymous pipes and kills/reaps it on
exhaustion, preempting blocking stdlib DNS, TLS, dribbling status/body and parsing.
An activation barrier prevents child network work before parent process startup
completes and the deadline is checked. The parent retains a lifeline writer; a
worker daemon thread exits the worker on parent EOF/death or remaining-budget
exhaustion, including orphaned blocking resolver/socket calls. No retries occur.
Prepared literal token material crosses only stdlib spawn's anonymous local IPC,
not evidence or disk; no refresh-capable credential object crosses the boundary.

This is a total-attempt OS watchdog mechanism, not a hard realtime scheduling,
storage-latency or remote cancellation guarantee. Process creation, durable writes,
kill/reap and final evidence I/O may exceed a deadline under OS/storage stalls;
network activation is barred before activation checks and terminated at watchdog
service. A watchdog cannot prove remote cancellation or which bytes arrived.
Main-parent supervision preempts GIL-bound parsing; orphan lifeline scheduling and
actual runtime/OS cancellation behavior deserve further audit/live qualification.
Kill is not instantaneous, and parent death is not synchronously observed. Neither
the watchdog nor a wall-clock check proves no byte can cross after an arbitrary
OS scheduling stall. Durable permission is already spent; no replay/reissue follows.
Tests exhaust fake clocks without sleep or networking, test cancellation intent,
and exercise real spawn/IPC with fake sockets. They do not qualify live DNS/TLS.

Phase 2's deterministic `multiprocessing_projection()` explicitly binds file bytes
for the pinned CPython/macOS POSIX spawn path. Python sources: multiprocessing,
multiprocessing.context, multiprocessing.process, multiprocessing.connection,
multiprocessing.spawn, multiprocessing.popen_spawn_posix,
multiprocessing.popen_fork, multiprocessing.resource_tracker,
multiprocessing.reduction, multiprocessing.resource_sharer, multiprocessing.util,
selectors, pickle, subprocess and threading. Native implementations:
_multiprocessing, _posixsubprocess, select and _pickle. Each named module's concrete
file SHA-256 enters the Phase 2 authorization-bound runtime hash; changing any
projected digest changes that hash and invalidates the old assertion. This is an
explicit relevant inventory, not generic package/environment enumeration or a
claim to hash every transitive stdlib dependency. The frozen runtime pin is unchanged.

## Authorization and durable consumption

Reuse strict Phase 1 LiveAuthorization schema: gate version, unique ID, purpose,
exact LIVE_READ_GO, fixture hash, runtime hash, source hash, engineering-only flag,
operator alias/confirmation, finite positive issue/expiry times. Require issue <=
now < expiry. Wrong capability/binding, malformed or future/expired assertion fails.
The Phase 2 runtime/source hashes are distinct from Phase 1's construction hashes;
this is explicit evolution, not migration of any issued real record (none exists).

After all nonnetwork fixture/token/provenance/runtime/source/environment/reservation
prechecks, reserve exclusive attempt evidence, revalidate authorization, then
O_EXCL-create `claim-{authorization_id}.json`. The claim binds exact fixture/runtime/
source, capability, consumed_at and SHA-256 of a positive **nonsecret authorization
assertion** projection including operator/confirmation/issue/expiry/purpose/version.
This is not a token/credential hash. fsync file contents AND registry directory
must return before the consumed event and before process/network-capable handoff.

The child independently checks preconditions, reservation, canonical claim and
exact assertion digest, and the consumed-only evidence prefix before construction.
Authorization is rechecked before connect and before serialization. `_ReadSocket`
also retains only the typed fixture, original assertion and its nonsecret digest,
runtime/source bindings, and existing PreparedToken. After checking the exact
serialized GET envelope it spends process-local send permission, persists and
fsyncs REQUEST_STARTED, resets the socket's decreasing timeout, and repeats token
readiness with the remaining budget. It then checks the original assertion digest
and the strict LIVE_READ_GO fixture/runtime/source/time binding immediately before
raw sendall. A fresh temporal check also follows the binding validator's CPU work.
There is no intervening serialization, evidence fsync or other I/O after that
authorization check. Expiry/refusal yields fixed
`authorization_refused_at_raw_send`; token refusal yields fixed
`token_readiness_refused_at_raw_send`. Neither carries exception text. Both permit
zero raw HTTP bytes in the deterministic refused paths, retain the durable spent
claim and forbid second sends, connections, retries or reissues.

This check qualifies permission immediately at the first local raw handoff. A
clock read and raw send are not atomic: OS suspension can occur between them,
and a blocking send can finish after expiry. There is no hard realtime promise
about packet timing, remote receipt or cancellation at the expiry instant.
REQUEST_STARTED means durable local intent even when the final guard refuses and
no HTTP handoff occurs; it is not proof of bytes transmitted.

A consumed record, even empty/corrupt/partial, is spent forever
for execution purposes. A claim never renews an expired assertion. No unconsume,
new-attempt minting, second factory or automatic retry exists. Two competing
processes can create at most one claim in the qualified persistent registry.

This is exactly-once LOCAL authorization consumption, not provider idempotency,
exactly-once Google execution or proof of remote receipt. Even a constructor failure
or crash before socket creation spends permission; a new attempt needs a new
explicit human assertion and independently reviewed fixture/run state.

## Crash model and recovery

| Crash point | Durable state / allowed recovery |
| --- | --- |
| Before validation | No network-capable handoff; no claim. Correct preconditions and obtain/review permission normally. |
| After validation, before claim | No handoff; may have reserved attempt header. Existing incomplete evidence blocks ordinary reuse and requires review. |
| During claim write/file fsync/directory fsync | No handoff; any surviving name is spent/corrupt. Never erase/assume unused; a lost name after actual power loss remains unqualified storage. |
| After durable claim, before construction | Spent, even if only header/consumed prefix or no final result. |
| During construction | Spent; construction-started prefix; no inference of any network action. |
| Constructed, before connect | Spent; construction facts only. |
| Connect begun | Spent; DNS/TCP/TLS may be incomplete; parent/lifeline cancels worker; no remote-state inference. |
| TLS complete, before observation | Spent; no HTTP serialization or bytes permitted; missing TLS facts do not authorize another probe. |
| During TLS observation/file fsync | Spent; missing or incomplete observation; no HTTP request permitted. |
| REQUEST_STARTED fsynced, final guard refuses | Spent; fixed expiry/readiness refusal; zero raw HTTP handoff in tested paths; no automatic reissue. |
| Request send begun | Spent; request_started persisted before send; bytes/remote receipt unknown. |
| Status observed | Spent; status persisted before body interpretation. If persistence was interrupted, lack of durable status does not prove none was visible. |
| During body read | Spent; visible status retained when durably recorded; parser uncertainty, no zero. |
| Parsed, before final evidence | Spent; parsed summary may exist; missing terminal record never authorizes reissue. |

Recovery is inspection/incident review, not resume. The public path rejects
pre-existing attempt files/claims. Partial final evidence remains incomplete and
cannot trigger another request. There is no recovery executor. Process death,
store reopen and all evidence prefixes are offline tested. Real power-loss/failure
modes, abandoned reservation replacement and live incident procedure remain BLOCKED.

## Evidence and secrets

AttemptEvidence is an exclusive 0600 JSONL positive allowlist, not broad runtime
serialization followed by redaction. Header: phase/schema, engineering-only,
attempt/authorization ID, fixture/runtime/source hashes, LIVE_READ_GO. Events:
fixed Stage enum + sequence + typed ReadSummary, plus the exact TLSObservation
projection only at TLS_OBSERVED. Stage order, exact header types and canonical records are enforced; each
append is fsynced. Storage failures have their own fixed category. Lifecycle prefixes describe local intent/completion, not remote
facts. Consumption time is the justified local wall timestamp; no fabricated
cross-process monotonic-offset telemetry is recorded.

No evidence API accepts token, credential object, auth header, token hash, arbitrary
exception, response body, provider header or arbitrary sheet string. Error handling
uses fixed categories and public refusal text without exception rendering. No
str/repr/log/hash/serialization of credential material enters persisted evidence.
PreparedToken retains its frozen excluded repr. The claim hashes only independently
typed nonsecret operator assertion fields. Independently supplied labels/numbers
could coincidentally equal arbitrary token strings; this is the frozen distinction
between independent equality and prohibited credential dataflow, not a blanket
proof against all possible string coincidence.

## Hostile tests, regressions and offline facts

Tests count real stdlib serializer handoffs to fake sockets, attack all mutation
methods/endpoint/query/headers/body/auth and second sends, wrong capabilities and
bindings, provenance/identity/fixture/root tampering, reservation collisions/corrupt
records, permanent consumed claims after every stage/failure/crash, file/directory
fsync failures, short evidence writes, exclusive permissions, strict summaries and
secret-bearing synthetic exceptions. Two real spawned consumers compete; exactly
one wins. A real spawned child exits abruptly after fsync and the reopened claim
remains spent. The complete spawned supervisor/worker/IPC/parser path is tested
with socket/DNS trapped and TEST_ONLY identities.

Repair tests additionally force expiry during pre-send fsync and final binding
validation, repeat readiness at that boundary, tamper every final binding, and
reject secret-bearing synthetic errors without rendering them. Fake TLS tests
cover valid policy/observation/order, IPv4/IPv6, same socket reuse, missing/oversized
certificates, malformed protocol/cipher/SNI/ALPN/endpoint, unsafe objects, unoffered
ciphers, wrong socket/context, append refusal and an actual os.fsync failure
before serialization. Independent
token changes do not change TLS evidence; raw DER and bearer/digest are absent.
Explicit Python/native spawn hashes are tested structurally and through runtime
authorization refusal. An additive public ReadAdapter.inspect composition test
reserves evidence, consumes permission, uses actual spawn/worker/IPC with fake TLS,
emits the exact guarded GET, parses the strict fake response and persists parent
terminal evidence. TEST_ONLY identities and socket/DNS/connect traps prevent escape.

The offline runner preloads ssl/asyncio/pytest, clears credential-test environment
prefixes only in its child process, and replaces socket.socket/create_connection,
getaddrinfo/gethostbyname/gethostbyname_ex/getnameinfo before collection. Phase 2
also traps HTTPSConnection.connect; spawned test helpers reinstall socket/DNS
traps before any work. Warnings are errors in the parent pytest run and spawned
interpreters/helpers (PYTHONWARNINGS plus explicit child filters). No Google
traffic or credential discovery is attempted.

Historical pre-audit qualification (all socket/DNS disabled; retained as history):

| Command | Pre-audit result |
| --- | --- |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py phase2 --warnings-as-errors` | 223 passed in 1.64 s |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py sheets` | 631 passed in 4.74 s |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py sheets --warnings-as-errors` | 631 passed in 5.02 s |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py study2 --warnings-as-errors` | 1075 passed in 5.64 s |

Those pre-audit commands exited 0; warnings-as-errors produced no warnings/failures.
The runner calls pytest with repository paths, `-q` and (when selected) `-W error`.
Development initially also ran `.venv/bin/python -m pytest -q -W error
tests/test_study2_sheets_phase2.py` (187 cases before hostile-test expansion), then
repeated the same four runner commands as new hostile cases/corrections justified.
The table above records the pre-repair working tree, not the repaired result.
`compileall -q` for both new modules, the runner and tests passed.

Final repaired qualification (socket/DNS disabled in all four commands):

| Exact command | Repaired result |
| --- | --- |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py phase2 --warnings-as-errors` | 279 passed in 4.76 s |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py sheets` | 687 passed in 9.09 s |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py sheets --warnings-as-errors` | 687 passed in 9.01 s |
| `.venv/bin/python scripts/qualify_sheets_phase2_offline.py study2 --warnings-as-errors` | 1131 passed in 9.70 s |

All repaired commands exited 0. Warnings-as-errors runs had no warnings/failures;
parent and spawned helpers retain their network traps. Final compileall passed.
AST comparison confirms all 60 prior Phase 2 test functions and every original
assert node remain, with 15 additive repair test functions (parameterized cases
and the new lifecycle stage increase the focused total from 223 to 279).
Intermediate repair runs passed 277/278 focused and 686 Sheets cases; the table
above is the final expanded repair suite. At that repair stage, nothing was
promoted to live validation success or frozen status; the subsequent successful
independent re-audit permits only the Phase 2 offline freeze recorded here.

Freeze verification: all original checklist fields/items equal HEAD; all 15
qualification steps/abort conditions byte-identical; only the two evolving drafts
are tracked modifications. Frozen docs/modules/tests/pin/template, scientific
serialization, dependencies/lock, Study 1 and completed GitHub engineering are
unchanged. `git diff --check` and each new file's `git diff --no-index --check
/dev/null <file>` passed with no whitespace diagnostics. HEAD remains d55ddf8.
Six files added, two drafts modified; no commit/push/tag.
Within the existing Phase 2 tree, this repair changes only the read module, its
tests, this Phase 2 document, and the evolving metadata/paragraph in the two
drafts. The Phase 2 control module, specification template and runner are unchanged
by the repair.
No Google request, real authorization, fixture provisioning, token acquisition,
TLS peer/trust observation or paper observation occurred. Reads **0**, mutations
**0**, Sheets paper observations **0**.

Final freeze-only verification on 2026-09-18 repeated the four exact qualification
commands above with socket/DNS disabled:

| Suite | Freeze-only result |
| --- | --- |
| Phase 2, warnings as errors | 279 passed in 4.24 s |
| Sheets | 687 passed in 7.84 s |
| Sheets, warnings as errors | 687 passed in 7.94 s |
| Study 2, warnings as errors | 1131 passed in 8.44 s |

All four exited 0; warnings-as-errors checks passed and test counts were unchanged.
The freeze-only pass changes only this document, the additive current-state
qualification paragraph and phase2_update audit/status metadata. All five audited
Phase 2 implementation/test/runner/template files remain byte-identical to
freeze-pass entry. Earlier frozen layers, original qualification steps/abort
conditions and checklist item statuses remain unchanged. HEAD is still d55ddf8;
no commit or push occurred. LIVE-GO remains CLOSED with zero live reads, live
mutations and Sheets paper observations; no Google/API/auth/OAuth/DNS/TCP/TLS live
action occurred.

## Checklist impact, remaining gates and audit targets

Checklist item IDs/status/evidence and the original broad totals are preserved:
**16 PASS OFFLINE, 7 BLOCKED, 5 REQUIRES LIVE VALIDATION**. New phase2_update
metadata describes tested offline subconditions only; no parent or child status
is promoted by the successful independent re-audit or offline freeze. Historical
phase1_remaining/evidence prose is
retained as provenance, with explicit Phase 2 current scope in the new metadata.

Remaining BLOCKED parents: credential_acquisition_and_budget (real acquisition,
SDK/source/version, actual provenance, justified values); real_tls_connector_authorization
(offline connected-read re-audit passed; actual trust inventory and real
TLS/route/peer unresolved; mutation/fault
boundary still absent); actual_fixture_and_reservation (no actual provisioned
fixture/grant/isolation/reservation); crash_recovery (real storage/power loss/live
incident procedure); separate_live_authorization (none issued); visibility_bounds
(no live schedule); paper_protocol (no arms/protocol/data authorization).

Remaining REQUIRES LIVE VALIDATION: actual_grid_response_shapes, baseline_isolation,
clean_success_placement, live_ambiguity_boundary, actual_tls_trust_phase1. Only a
future separately authorized read can observe actual sparse/framing/peer behavior;
a failed-closed framing shape must reopen qualification, never cause hidden retry.

Special hostile review: spawn token-only anonymous IPC and activation/lifeline
ownership; OS watchdog versus hard realtime/power-loss claims; canonical registry
root and trusted same-UID filesystem assumptions; partial evidence poisoning;
bounded Content-Length/chunked framing and explicit origin-zero grid; operator-backed
same-app assertion provenance. These are deliberately explicit limits, not Google
facts established offline. No fresh official-document lookup/network research was
needed: the exact read API shape is inherited from frozen repository evidence.

## Non-goals and current state

No OAuth/browser/exchange/refresh/ADC, actual fixture creation/selection, Google
read or mutation, batchUpdate/AppendCells adapter, clean mutation, ambiguity/H0/H1,
replay/regeneration executor, Study 2 scheduling/manifest/paper observations, Stripe,
new dependency, commit or push. Only the Phase 2 offline status is frozen; no real
usable authorization artifact exists.

Future next operational milestone, only after closing remaining read prerequisites
and obtaining separate explicit human authorization: the first read-only
engineering GET. The passed offline re-audit and freeze authorize no real read.
There is no automatic path from this offline freeze to Google action or paper collection.

**PHASE 2 OFFLINE FREEZE READY — LIVE-GO CLOSED — ZERO SHEETS PAPER OBSERVATIONS — READY TO COMMIT**

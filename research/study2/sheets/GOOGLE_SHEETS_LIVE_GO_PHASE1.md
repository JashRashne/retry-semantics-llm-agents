# Google Sheets LIVE-GO closure — Phase 1

**FROZEN OFFLINE LIVE-GO PHASE 1 — LIVE-GO CLOSED — ZERO SHEETS PAPER OBSERVATIONS**

2026-09-17. The exact Phase 1 v0.2 final freeze-check ZIP passed independent hostile
review with verdict **SAFE TO FREEZE PHASE 1 OFFLINE PREREQUISITES**. This status-only
housekeeping records that accepted offline freeze; it grants no live authorization.

The freeze covers only the audited credential mechanism/provenance architecture,
`drive.file` scope selection, future OAuth successful-response contract, PreparedToken
export boundary, token-budget derivation formula, HTTPSConnection construction
factory, SSL-context construction policy, environment/interference gate,
authorization assertion/capability schema and connector evidence projection.

It does not freeze or authorize actual OAuth acquisition, google-auth-oauthlib
implementation/version, real credentials, production deadline numbers, total
deadline enforcement, a connected socket adapter, wire-level capability enforcement,
real TLS handshake/trust/peer/route, actual human authorization, fixture provisioning,
live GET, live mutation, ambiguity engineering or paper observations. The returned
raw HTTPSConnection remains a trusted implementation object, not capability-safe
at the wire boundary. The checklist and qualification procedure remain DRAFT.

This phase remains non-operational and engineering-only.
No acquisition, OAuth, Google API request, socket connection, fixture provisioning,
read, mutation, ambiguity injection or paper observation is authorized or performed.
Public documentation research and fake/offline tests alone are used here.

## Baseline and exact original blockers

Before editing, all eleven named artifacts matched `26609e4`, `3478dd9` and
`66f7374` byte for byte. The seven BLOCKED IDs in the existing checklist were:

1. `credential_acquisition_and_budget`
2. `real_tls_connector_authorization`
3. `actual_fixture_and_reservation`
4. `crash_recovery`
5. `separate_live_authorization`
6. `visibility_bounds`
7. `paper_protocol`

All seven remain BLOCKED. The first two retain their original broad meaning and
have explicit child sub-gates added to the same checklist, with `parent_id` and
scope evidence. No parallel checklist exists. Five new offline sub-gates pass;
one new handshake/trust sub-gate requires live validation. Totals: **16 PASS
OFFLINE, 7 BLOCKED, 5 REQUIRES LIVE VALIDATION**. The old hostile-audit/freeze pass
applies only to the frozen preparation baseline. Phase 1 offline prerequisites now
have their own final hostile-audit acceptance and frozen status recorded above.

The prior frozen preparation document, module/tests, fixture template and runtime
pin remain exact. This housekeeping changes only Phase 1 document/status wording,
module/test opening docstrings, checklist metadata/document references and the
qualification prerequisite paragraph; executable behavior and test logic are preserved.
No attempt is made to rewrite the pin to certify the new module or acquisition SDK.

## Credential decision and preparation process

Recommend **dedicated engineering OAuth user credentials**, desktop authorization
code flow with PKCE S256, state validation, system browser and loopback redirect.
Use a dedicated project/client and an otherwise empty engineering account. The
scope is exactly `https://www.googleapis.com/auth/drive.file`.
This is the smallest file-scoped surface supported by both planned methods.
The fixture must be created under this same app in a separately authorized setup
process, or explicitly granted to it through a separately audited file-selection
flow. Knowing an arbitrary spreadsheet ID is not a per-file grant.
[Google scope guide](https://developers.google.com/workspace/sheets/api/scopes),
[Drive scope guide](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).

Alternatives evaluated for this local, one-fixture experiment:

| Mechanism | Decision for this experiment |
| --- | --- |
| OAuth dedicated user | Selected: native file-scoped app grant; no service-account key, IAM token-creator roles or metadata discovery |
| Service account | Explicit sharing could isolate the fixture, but direct keys add a long-lived signing secret; impersonation adds IAM/source-credential and acquisition surfaces. No domain-wide delegation. Not selected |
| ADC | Discovery strategy rather than one credential type; may select env files, local user credentials or metadata. Ambient selection obscures provenance. No `google.auth.default()` in the qualified preparation design |
| API key / self-signed JWT alone | Not a substitute for the documented OAuth bearer authority for private Sheets operations |

[Service-account OAuth](https://developers.google.com/identity/protocols/oauth2/service-account),
[ADC discovery order](https://docs.cloud.google.com/docs/authentication/application-default-credentials).
These decisions are experiment-specific design judgments, not claims that other
Google-supported mechanisms are intrinsically unsuitable.

The eventual separate preparer should use `google-auth-oauthlib`'s desktop flow,
with its exact version, dependencies and source audited/pinned before installation
or use. No SDK is added, loaded, certified or chosen by version in this phase.
Future implementation sequence, under credential-preparation authorization only:

1. Select an explicit reviewed desktop client configuration; no ADC discovery.
2. Request only `drive.file`, PKCE S256 and unpredictable state. Validate loopback
   redirect/state. Disable incremental scope union; reject extra granted scopes.
3. Exchange the code only in the preparer. Record local exchange start/finish.
   Google documents installed-app refresh tokens: do not assume an online flag
   suppresses one. Any refresh token/client secret stays in that separate process
   and never crosses the export. No raw token-response/config logging.
4. Validate the documented successful token response before any export: require
   `access_token` present and acceptable to the exact frozen `PreparedToken`,
   `expires_in` finite and positive (reject booleans and nonnumeric/nonfinite
   values), the exact granted scope set equal to `(drive.file,)`, and
   `token_type == "Bearer"`. Missing/malformed required fields or unsupported
   token type/scope fail closed;
   requested scopes alone do not establish the grant. Use local exchange **start**
   plus `expires_in`, conservatively, to derive a finite positive absolute expiry
   and require readiness before later handoff. A provider issuance timestamp is
   not available from the documented opaque bearer response; do not invent `iat`
   or decode the token. Transport explicitly uses `Authorization: Bearer <token>`.
5. Project safe metadata explicitly into `CredentialProvenance`; export the literal
   bearer via `export_prepared_token`. Return/send only the exact frozen
   `PreparedToken` to transport. Keep provenance in a separate evidence channel.
6. End preparer ownership of the credential object. Acquisition does not call
   Sheets, construct mutation transport, invoke a callback or dispatch anything.
   A later visible 401 is terminal; no transport refresh/reissue is permitted.

[Native-app PKCE, token response and granted scopes](https://developers.google.com/identity/protocols/oauth2/native-app).
The immutable export is implemented and tested. Real acquisition remains absent,
not implicitly authorized by the pseudoprocedure or synthetic tests.

**DPoP is NOT selected in the current credential design.** It is optional and
would add device-key generation/storage, proof/nonces and refresh-token key binding
to this narrow experiment's credential state. No DPoP implementation is added.
Any later adoption requires a separate credential-path audit. Any refresh material
returned by the installed-app flow remains entirely within the separate preparer;
neither it nor a refresh callback crosses into mutation/read transport. The future
successful-response validation above is a specification, not an acquisition
implementation or a new transport callback; its SDK/version/source audit remains
BLOCKED.

Persist only mechanism, exact requested/granted scope lists, separately assigned
account registry alias, hash of a **public reviewed configuration projection**,
library name/version, local exchange start/preparation time, expiry basis/absolute
expiry and clock uncertainty. A future registry can hold public project/client
identity to resolve the alias. Do not add identity scopes solely for evidence.
Never hash a client-secret JSON, credential file, token, refresh token or key;
even its hash is excluded. No credential paths, raw responses or arbitrary metadata.
Scope/expiry metadata is the explicit safe projection; bearer dataflow is excluded.

## Scope and separate provisioning capability

One scope suffices for both the whole-fixture `spreadsheets.get` and one controlled
`spreadsheets.batchUpdate` containing AppendCells: **`drive.file`** appears in
both method authorization lists. Readonly scopes cannot authorize batchUpdate.
Do not request `drive`, `drive.readonly`, `spreadsheets`, or additional identity
scopes as a convenience.
[GET](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get),
[batchUpdate](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate).

`spreadsheets.create` also accepts `drive.file`; the planned same-app new fixture
does not require broader Drive permission. Provisioning has separate credentials,
process and human capability; it is outside the trial window and is not provided
by the experiment factory. Same client/app preserves the per-file association.
Different clients cannot be assumed to inherit that grant. Any future ACL/sharing
operation needs its own scope analysis and setup authorization.
[create](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/create).
OAuth scope acts on a spreadsheet file, not one sheet or one operation; the fixture
binding and eventual wire guards provide the narrower local engineering restriction.

## Token readiness: derivation and unresolved enforcement

Let hard maximum durations be D (DNS), C (TCP setup), H (TLS), S (all header/body
sends), W (status parsing), B (complete bounded body read), V (one explicit verifier
GET including its DNS/TCP/TLS/send/status/body/parsing/storage), and M (local
scheduling, journal/fsync, parsing/closure and watchdog-overrun margin).

`A = D + C + H + S + W + B + V + M`

Before socket handoff, eligibility is strictly:

`expires_at - wall_now > A + clock_uncertainty_seconds`

`ActionBudget` implements finite positive component validation, sum and strict
inequality through the frozen token check. Equality refuses. Readiness is checked
before reservation/construction and again immediately before first request handoff
in a future runner; after connection the full A can be retained conservatively.
No acquisition/refresh after dispatch. A verifier needs its own LIVE_READ_GO and
readiness check even when its time is reserved in A. Replay has its own capability
and eligibility check; no automatic second mutation is included in A.

No production numbers are selected. Tests' 1–8 second inputs are arithmetic fixtures.
Timeout maxima are operator-chosen **hard enforced limits**, not measured average
latency. Select them from the permitted engineering window and qualify attainable
setup/response behavior later. Bound M using local scheduler/fsync/watchdog behavior;
bound clock uncertainty from an independently evidenced clock source and resolution.
Include exchange latency conservatively by expiry-from-start, not response receipt.
Later TLS/service latency is genuinely unmeasured; it cannot be supplied offline.

Important offline implementation prerequisite remains BLOCKED: the frozen stdlib
path uses a per-socket timeout, DNS is not bounded by it, address attempts may each
use it, and repeated response reads can exceed it indefinitely. No total deadline
enforcer is added or claimed here. An audited monotonic action watchdog/deadline
adapter must enforce these maxima (including DNS, local evidence work and bounded
body reads) before any live mutation can use A as a justified maximum. Absence or
expiry of that prerequisite must abort before socket handoff. No arbitrary 60s TTL.

## Factory, SSL, environment and provenance

`ConnectorFactory.construct` validates explicit authorization, fixture/runtime/source
hashes and current runtime; checks the actual process environment before creating
SSL; constructs `ssl.create_default_context(purpose=SERVER_AUTH)` and then a fresh
`http.client.HTTPSConnection("sheets.googleapis.com", 443, timeout=...)`.
No socket, DNS, `.connect()`, request, retry, redirect, refresh, pool or tunnel is
invoked by construction. `auto_open=0`, debug off. Missing authorization defaults
to refusal before SSL construction. After authorization/runtime/environment and
timeout prechecks succeed, the first actual connector-construction attempt consumes
the factory regardless of outcome, including SSL or HTTPSConnection construction
failure. Authorization/runtime/environment precheck failures do not consume it or
claim construction occurred. This is local object state, not durable authorization-ID
consumption, which remains BLOCKED. Errors use fixed text and suppress arbitrary
constructor exception text.

This is the **real construction factory**, not an already-connected socket adapter
or live runner. A raw HTTPSConnection returned by this Phase 1 internal seam is a
trusted implementation object, not a capability-safe public client or security
sandbox. It must not be manually connected in this phase.
The frozen transport retains its disabled default seam. Future adaptation must
bind capability to the actual guarded method/path and ambiguity fault mode, recheck
expiry/environment at connection/send, enforce total deadlines, persist evidence
before the first call, and prohibit reuse/reopening. Those requirements keep the
broad `real_tls_connector_authorization` parent BLOCKED. Factory capability tests
establish separation at construction, not complete live traffic enforcement.

SSL policy: PROTOCOL_TLS_CLIENT, CERT_REQUIRED, hostname check true, no keylog,
and at least one loaded CA. Preserve pinned CPython default minimum TLS version
(observed TLS 1.2), maximum negotiation, cipher suites, verify flags and options.
Validate the minimum is at least TLS 1.2, without overriding it or hard-coding
ciphers. Default CPython/Homebrew OpenSSL trust is selected, not certifi or a custom
bundle. On this runtime `ssl.get_default_verify_paths()` reports default cafile
`/opt/homebrew/etc/openssl@3/cert.pem` and capath
`/opt/homebrew/etc/openssl@3/certs`; macOS Keychain is not loaded by this Python
`load_default_certs` implementation. CA-directory entries can be loaded lazily.
[Python SSL defaults/trust](https://docs.python.org/3.11/library/ssl.html).
Local pinned `ssl.py` and `http.client.py` were inspected directly, not assumed
identical to a newer online patch release.

Pre-live environment gate rejects **presence**, including empty/case variants, of
common proxy variables (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`,
`FTP_PROXY`), `SSL_CERT_FILE`, `SSL_CERT_DIR`, `SSLKEYLOGFILE`, `OPENSSL_CONF`,
`OPENSSL_MODULES`, `OPENSSL_ENGINES`, client-specific CA variables
(`REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`,
`NODE_EXTRA_CA_CERTS`), Python path/home and listed LD/DYLD injection variables.
The exact versioned denylist is in the module. Values are never read/echoed/hashed.
No actual user environment is changed. Tests supply fake mappings or replace the
mapping only inside the pytest process and restore it afterward.

Direct `HTTPSConnection` uses socket create_connection and context.wrap_socket;
it **does not automatically consult HTTP(S)/ALL_PROXY/NO_PROXY environment** or OS
proxy/PAC configuration. A tunnel requires explicit `set_tunnel`, unused here.
The conservative proxy rejection prevents accidental future wrapper changes.
Default verify paths do consult `SSL_CERT_FILE`/`SSL_CERT_DIR`. Default context
also consults `SSLKEYLOGFILE`, which could write TLS key material before dispatch:
the gate must run before context creation. OpenSSL/native-loading configuration
can take effect at process startup, so checking names later is not attestation.
[HTTPConnection implementation behavior](https://docs.python.org/3.11/library/http.client.html).

Environment checks cannot exclude transparent routing interception, installed
corporate roots, previously injected code, startup OpenSSL configuration, altered
DNS, CA-directory/file changes, or OS instrumentation. Future clean-process launch,
reviewed CA bundle/directory inventory and hashes, native/runtime/source identity,
network-route isolation attestation and actual peer/chain/SNI/hostname validation
remain prerequisites. Do not call the environment pass "MITM-free" proof.

`ConnectorEvidence` validates and projects only runtime fingerprint/pin/source
hashes, implementation identifier, OpenSSL version, host/port/timeout, context
min/max/verify flags/options/loaded-CA count, fixed trust-source classification,
fixed environment-gate result and authorization ID/capability. It has no token,
raw auth/header/environment/config/exception/credential input or generic serializer.
It returns safe evidence; it does not write or modify the frozen journal schema.
Later persistence must reserve/fsync its sidecar before live connection and extend
the supplemental token-collision check to that known safe domain. Trust-source
classification does not freeze CA contents: a reviewed trust inventory/pin and
actual negotiated TLS/peer evidence still require a later audited implementation.
No bearer or credential-source hash is evidence.

## Human capabilities and remaining unknowns

`LiveAuthorization` requires gate version/purpose, exact capability, bound fixture
manifest hash, frozen runtime-pin file hash, new connector source hash, independent
authorization ID/operator registry alias, explicit confirmation phrase, issue time,
expiry and engineering-only designation. No default authorization record or CLI is
supplied. Only synthetic in-memory assertions exist in tests; none is saved or
bound to a real fixture. No actual authorization is created here.

The authorization assertion schema and connector-construction gate are
capability-disjoint, without inheritance: LIVE_READ_GO, CLEAN_MUTATION_GO,
AMBIGUITY_ENGINEERING_GO. Construction requires exact capability equality.
Phase 1 does not yet enforce these capabilities at the connected HTTP wire
boundary. A later audited adapter must bind LIVE_READ_GO to the GET verifier path,
CLEAN_MUTATION_GO to the exact clean frozen mutation, and AMBIGUITY_ENGINEERING_GO
to the exact authorized fault-injection path before any live request is permitted.
Wire-level capability enforcement remains BLOCKED under
`real_tls_connector_authorization`. Each eventual explicit action/replay requires
its own operator record and one-use factory. Provisioning/cleanup have separate
future capabilities outside this model. This object verifies operator assertions,
not signatures or external identity. Future durable authorization-ID consumption
and recovery checks are necessary to prohibit reuse across processes/factories;
crash recovery remains BLOCKED and a copied record is not renewed permission.

Unresolved: approved SDK acquisition/source/version pin and safe IPC; actual grant/
expiry/account provenance; selected/enforced hard deadlines and clock uncertainty;
connected-socket/wire/fault capability integration; trust inventory and clean-launch
attestation; handshake/peer/route qualification; authorization issuance/consumption;
fixture IDs/reservation/isolation; response shapes/placement/visibility; real ambiguity
boundary; crash recovery and paper protocol. None is promoted by construction tests.

## Historical v0.1 validation

| Check | Final result |
| --- | --- |
| New Phase 1 tests | 136 passed in 0.42 s |
| All Sheets tests | 403 passed in 5.31 s |
| All Sheets with `-W error` | 403 passed in 5.31 s |
| Socket/DNS-disabled Study 2 regression, credential prefixes cleared, `-W error` | 847 passed in 4.31 s |
| Tracked and each untracked whitespace check | PASS |
| Reconnaissance / contract source/tests | Byte-identical to `26609e4` / `3478dd9` |
| Preparation document/module/tests, runtime pin, fixture template | Byte-identical to `66f7374` |
| Qualification procedure steps 1–15 and abort conditions | Byte-identical to `66f7374`; only prerequisite paragraph changed |
| Original checklist item IDs/status/evidence and 7 blocked parent meanings | Preserved; explicit Phase 1 metadata and six child gates added |
| Study 1 / completed GitHub engineering / serialization / dependency files | Unchanged |

Commands:

```sh
.venv/bin/python -m pytest -q tests/test_study2_sheets_live_go_phase1.py
.venv/bin/python -m pytest -q tests/test_study2_sheets_live_go_phase1.py tests/test_study2_sheets_live_preparation.py tests/test_study2_sheets_offline.py
.venv/bin/python -m pytest -q -W error tests/test_study2_sheets_live_go_phase1.py tests/test_study2_sheets_live_preparation.py tests/test_study2_sheets_offline.py
```

Regression preloaded ssl/asyncio/pytest, removed STUDY2_/GOOGLE_/GROQ_/FIREWORKS_
environment prefixes only in its child process, replaced socket.socket,
socket.create_connection, socket.getaddrinfo and socket.gethostbyname with refusal,
then ran every `tests/test_study2*.py` with `-q -W error`. New Phase 1 tests also
disable HTTPSConnection.connect. The malformed-keylog test uses only an empty test
file in pytest's temporary directory; no TLS session or credential is involved.

Official public documentation was retrieved through web research tools. Operational
Google API/auth calls **0**, credentials/OAuth used **0**, live reads **0**, live
mutations **0**, fixture provisioning **0**, paper observations **0**. No commit,
push, freeze or audit ZIP. Study 1 was not rerun; it and completed GitHub engineering
are unchanged. No dependencies, serialization or lock changes.

## Historical v0.2 hostile-audit corrections and validation

The independent v0.1 verdict was **MINOR CORRECTIONS BEFORE FREEZE**; the accepted
architecture is preserved. This repair narrows capability claims to the assertion
schema and exact equality at construction, makes the trusted raw-object/wire-gate
limitation explicit, documents the actual precheck/construction consumption
boundary, and completes the future successful OAuth-response contract including
Bearer validation and the explicit decision not to select DPoP.

`authorization_model_phase1` remains PASS OFFLINE with narrowly scoped evidence;
wire-level enforcement remains BLOCKED under the broad parent. All checklist
statuses and totals remain **16 PASS OFFLINE, 7 BLOCKED, 5 REQUIRES LIVE VALIDATION**.
The existing checklist audit metadata refers to the current draft awaiting external
review; the independent v0.1 verdict above is historical, not a v0.2 freeze approval.

Five new focused test cases demonstrate: authorization refusal and environment
refusal make zero SSL/HTTPS construction calls and permit a later valid construction
on the same factory; SSL and HTTPS construction failures each consume it and
prohibit another attempt; successful construction consumes it. Tests observe real
offline construction with socket/DNS/connect disabled. A local factory's used state
does not consume a durable authorization ID or authorize anything.

| Final v0.2 check | Result |
| --- | --- |
| Phase 1 tests | 141 passed in 0.29 s |
| All Sheets tests | 408 passed in 3.74 s |
| All Sheets with `-W error` | 408 passed in 3.74 s |
| Socket/DNS-disabled Study 2 regression with `-W error`, credential prefixes cleared | 852 passed in 4.20 s |
| Tracked and each untracked no-index whitespace check | PASS |
| Frozen reconnaissance/contract/preparation code/tests/document/pin/template | Byte-identical to `26609e4` / `3478dd9` / `66f7374` |
| Phase 1 executable AST after stripping docstrings | Identical to v0.1 |
| Existing Phase 1 tests | Preserved verbatim; new cases appended |
| Qualification draft | Unchanged by this repair; frozen 15 steps/abort conditions unchanged |
| Serialization, dependencies, Study 1 and completed GitHub engineering | Unchanged |

Validation commands and regression isolation are the same as recorded above.
No network/documentation/API/auth request occurred in this repair. Credentials,
OAuth, live reads, live mutations, fixture provisioning and paper observations
remain zero. No SDK was added, and acquisition/version/source audit and total
deadline enforcement remain BLOCKED. No known Phase 1 offline blocker from these
three audit findings remains after repair; external re-audit is pending. No freeze,
commit, push or ZIP was performed. LIVE-GO remains CLOSED.

## Current frozen Phase 1 housekeeping validation

Following final independent verdict SAFE TO FREEZE PHASE 1 OFFLINE PREREQUISITES,
this status-only pass renamed the document without a duplicate, recorded the exact
offline freeze scope, updated module/test opening status docstrings and checklist
Phase 1 metadata/document references, and updated qualification prerequisites.
Historical v0.1/v0.2 prose above remains historical, including its prior pending
review and no-freeze statements. Accepted architecture and limitations are unchanged.

| Check | Result |
| --- | --- |
| Phase 1 focused tests | 141 passed in 0.40 s |
| All Sheets tests | 408 passed in 4.54 s |
| All Sheets with `-W error` | 408 passed in 4.54 s |
| Socket/DNS-disabled Study 2 regression with `-W error`, credential prefixes cleared | 852 passed in 4.06 s |
| Executable module AST / test logic / all text after opening docstrings | Unchanged |
| Historical audit/validation sections | Preserved; v0.2 heading explicitly marked historical |
| Qualification 15-step procedure and abort conditions | Unchanged |
| Checklist item statuses and scoped evidence | Unchanged except renamed document references; 16 PASS OFFLINE / 7 BLOCKED / 5 REQUIRES LIVE VALIDATION |
| Frozen artifacts against `26609e4` / `3478dd9` / `66f7374` | Byte-identical; prior authorized draft updates remain explicit |
| Study 1 / completed GitHub engineering / serialization / dependencies / runtime pin | Unchanged |
| Tracked and each untracked no-index whitespace check | PASS |

The Phase 1 module's source hash changes only because its opening docstring changed.
The existing frozen runtime pin does not pin that source and was not modified; no
issued authorization record needs migration. Validation commands and socket/DNS
isolation match those recorded above. No network/API/auth request, OAuth, credential
acquisition/use, live read/mutation, fixture provisioning, human live authorization
or paper observation occurred. No commit, push or new ZIP. The freeze covers only
the offline prerequisites listed at the top; LIVE-GO remains CLOSED.

# Google Sheets LIVE-GO Closure — Phase 4

**PHASE 4 ENGINEERING DESIGN — LIVE-GO CLOSED — ZERO SHEETS PAPER OBSERVATIONS**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*. Academic byline: **J. Rashne**.

## Current operational state — expired unused read authorization

The latest real Phase 4 package is the retained
`sheets-phase4-unused-read-successor-b8b16aff18411cd44040201686e071475d88266070d94e401b47e004a65d5edb`
under the private RetrySemantics storage parent. It remains historical evidence
and is not a test fixture. Across the retained packages there have been **seven
OAuth attempts and four accepted acquisitions** (#4, #5, #6, and #7). OAuth attempt
**#5 succeeded** and produced accepted nonsecret acquisition metadata; its one
`spreadsheets.create` returned a
validated HTTP **200** response for a 100-row, 3-column engineering grid with
sheet ID **1**. The reviewed provisioning record, fixture descriptor and one
local reservation were completed. Post-setup preflight passed. Fixture hash:
`262c5f5be30875c077c54bb66f21dae3f7859a58c6af8464c34517d0086b9ec2`;
provisioning hash:
`958372a4e213f9c22ffad374efbdcc06cc8359cdd36f2f418e0189d457bce1cf`.

`LIVE_READ_GO` assertion #1 was issued with authorization hash
`602cd05f8f98e8403cc0f97f1d62845682e35bdb278e2d32573765b720a4b77e`.
Its validity ended before the operator executed the `read` command. A reviewed
expired-unused-read successor was then created, performed fresh client review,
startup, and OAuth attempt #6, adopted the same validated fixture, passed
post-setup preflight, and issued `LIVE_READ_GO` authorization #2.
Authorization #2 also expired **unused** due to operator timing.
A subsequent reviewed successor bound to newly frozen commit
`739b30e4d5b34997defa9beb0eabcb0d40084677` performed fresh client review,
startup, and OAuth attempt #7, adopted the same validated fixture, passed
post-setup preflight, and issued `LIVE_READ_GO` authorization #3. When the operator
attempted to paste the explicit verbose `read` command (~1410 bytes), macOS canonical
TTY input truncated the line at the 1024-byte buffer limit (`MAX_CANON`, exactly at
`.../phase4-recei`). The partial command was never executed, and the resident session
was stopped (Ctrl+C). Across all packages, **`read-intent.json` and `result.json`
are absent**. The Phase 4 wrapper writes read intent before inherited read
execution, so the wrapper never crossed its read-dispatch boundary. There is no
local read evidence or GET result. Sheets GET count remains **0**, paper
observations remain **0**, and this is an expired-unused authorization, NOT an
ambiguous GET or provider read failure. To remove this terminal line-length
constraint, the compact resident read command `read-current --execute-live-read
--token-input resident-memory` is introduced. The already-created fixture must
never be created again (one total CREATE remains). No claim is made that the
bearer was revoked or that Google saw a GET.

The offline `supersede-unused-read-authorization` transition is restricted to
that exact class of predecessor: complete valid local setup and issuance (either
initial provisioning or valid fixture adoption), expired `LIVE_READ_GO` beyond
clock allowance, exactly one reservation, no read-intent/result/evidence or
unknown artifact, and the explicit
`EXPLICIT_UNUSED_READ_AUTHORIZATION_EXPIRED_WITHOUT_DISPATCH` attestation.
Contradictory filesystem evidence refuses regardless of attestation. It runs
from a clean frozen checkout, takes `--configuration` and `--new-expected-head`,
performs no OAuth/browser/provider action, and creates one deterministic private
sibling named `sheets-phase4-unused-read-successor-<full SHA-256>`. The digest
binds the canonical predecessor path, independent of its basename length and
new HEAD. The transition permits repeated recovery under the **SAME frozen HEAD**
when source has not changed (`new_head == config.expected_head`), as well as
under an audited new HEAD when source has changed. In both cases,
`repository_check` enforces clean frozen source.

The successor has a fresh operator configuration and distinct authorization
ID, an empty registry, and activated provenance that binds the validated
fixture and the CURRENT predecessor's expired authorization (authorization #3
for the third successor). The predecessor is not edited. Pending provenance,
collisions or partial activation remain blocked for review.

All prior authorizations, receipts, source/runtime pins and old OAuth
acquisitions are **historical only**; authorization history is not collapsed.
The new package must repeat client review, startup, offline pin, and a
separately authorized fresh OAuth acquisition. Within the new resident session,
`adopt-existing-fixture --operator-confirmation EXPLICIT_ADOPT_VALIDATED_EXISTING_FIXTURE`
validates the predecessor evidence again, writes a nonsecret adoption record
and the same descriptor, reserves that same fixture in the new local registry,
and generates a fresh read pin. It never calls `spreadsheets.create`; the
successor's normal `provision`, provisioning review and reserve commands refuse.
After fresh post-setup conditions and a PASS preflight, a **fourth** one-shot
`LIVE_READ_GO` (authorization #4) may be separately authorized and one explicit
compact GET attempted under the newly frozen source. If source changes before OAuth,
ordinary `supersede-prelive` remains available and carries the fixture-reuse
restriction through its validated predecessor chain. No transition or test grants
live permission. The older `new-acquisition-attempt` and
`supersede-unused-acquisition` transitions refuse packages in this fixture-reuse
lineage, since their successors cannot carry the created-fixture restriction. A
failed fresh OAuth attempt therefore needs a separately reviewed recovery lifecycle.

The transition is operationally usable only from an independently
hostile-audited, clean, committed and pushed checkout. `--new-expected-head`
must be that checkout's exact frozen full SHA. Source presence alone grants no
live authority. The local command shape is:

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator supersede-unused-read-authorization --configuration "$EXPIRED_P4/operator.json" --new-expected-head AUDITED_FROZEN_FULL_SHA --operator-confirmation EXPLICIT_UNUSED_READ_AUTHORIZATION_EXPIRED_WITHOUT_DISPATCH
```

The returned successor path, not the predecessor path, is the input for fresh
`client-review`, `startup`, `phase4-preflight`, and a separately authorized
`session`. Within that session, use `adopt-existing-fixture` with the explicit
adoption confirmation before post-setup attestation, preflight, new issuance and
read. A separate reviewed authorization is required before any live GET.

## Earlier design and operational snapshots

This pre-live setup design was frozen at `2ad300227cc786829ed3efa598c66d838493f39a`, corrected for real Google Desktop OAuth metadata at `6525ddbe3e2eadb2dc55d301914e75ed41f8dfe6`, and its operational-state documentation was frozen at `055c2ce30f350899f6babbd84770d6532ef1d6d5`. The independent Phase 3 clean-room re-audit and Phase 4 hostile audit passed for those historical builds. OAuth attempt #1 reached `code`, `state`, `iss` and was rejected by the then-frozen parser. Attempt #2 reached exactly `code`, `state`, `iss`, `scope` and was rejected by the then-frozen parser. Attempt #3 used a fresh reviewed package bound to `c2454bd43e32e670b87735843db1c4b21404b294`; its callback contained exactly `state`, `iss`, `code`, `scope` with the expected issuer and drive.file scope. Acquisition nevertheless returned BLOCKED before accepted local acquisition persistence. The old build did not record the exact failing stage. All three intents are permanently spent, all three acquisitions absent locally, and their registries empty. No spreadsheet create, fixture, genuine LIVE_READ_GO, Sheets GET, Sheets mutation or paper observation occurred. Paper observations remain **0**. OAuth attempt #4 subsequently succeeded from a fresh reviewed package bound to frozen commit `594c95f`; the resident session was intentionally stopped before provisioning. Study 1 is immutable. Offline engineering tests are not paper data.

The missing acquisition artifacts establish only local durable state, not whether
Google issued anything remotely. A handshake-only probe from the project Python
3.11.14 environment to `oauth2.googleapis.com:443` passed TCP and TLS 1.3 with
OpenSSL 3.6.3 (`TLS_AES_256_GCM_SHA384`), CA file
`/opt/homebrew/etc/openssl@3/cert.pem` and CA path
`/opt/homebrew/etc/openssl@3/certs`. This does not prove attempt #3 reached
the token endpoint or that a later HTTP response was accepted.

## Provider design and scope

Official Google documentation rechecked through public web research on 2026-09-19, without operational provider access:

* [spreadsheets.create](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/create) accepts the frozen exact `https://www.googleapis.com/auth/drive.file` scope and returns a Spreadsheet.
* [Sheets scope guide](https://developers.google.com/workspace/sheets/api/scopes) describes this as per-file see/edit/create/delete access, applied to the spreadsheet file rather than a worksheet.
* [Drive per-file scope guide](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) includes files created with the app; knowledge of an arbitrary ID does not establish this relationship.
* [Spreadsheet and Sheet schemas](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets) support creation with sheet properties. The chosen request supplies them in the same POST. This avoids a second create or batchUpdate solely to establish worksheet identity.
* [Drive creation guide](https://developers.google.com/workspace/drive/api/guides/create-file) excludes Sheets from pre-generated Workspace IDs. Pre-generated IDs therefore do not solve create ambiguity here.

The narrow setup command sends one `POST https://sheets.googleapis.com/v4/spreadsheets?fields=...` with the constant field mask in `sheets_phase4_setup.CREATE_FIELDS` and this body:

```json
{"properties":{"title":"RetrySemanticsEngineering-sheets_phase4_first_fixture"},"sheets":[{"properties":{"sheetId":1,"title":"RetrySemanticsEngineering","sheetType":"GRID","gridProperties":{"rowCount":100,"columnCount":3}}}]}
```

The file title includes the retained reservation label to aid manual incident reconciliation; it is **not** an idempotency key. Sheet ID 1 avoids omitted-default-zero ambiguity. Exactly one worksheet, 100 rows, three columns; no values, formulas, tables, merges, ACL changes or app-property mutation. The positive response must have exactly the selected structure, matching title/extent/type/ID and a valid actual spreadsheet ID. HTTP 200 with one bounded Content-Length or valid HTTP/1.1 chunked framing is required. Unsupported framing fails closed. No provider SDK, redirect following, auth middleware, mutation retry or automatic cleanup.

The original first-read plan acquired OAuth before CREATE because creation needs a token. It intended to use that resident token for setup and a subsequent GET, with distinct human commands and capabilities. In the real attempt #5, the CREATE completed but the first read authorization expired before the GET command was executed. Attempt #6 adopted that fixture but its authorization #2 also expired unused without read dispatch. Attempt #7 adopted that fixture and issued authorization #3, but the verbose read command exceeded the 1024-byte macOS canonical TTY input line limit (~1410 bytes, truncated at `.../phase4-recei`) and was not executed before interruption. The reviewed successor now requires fresh OAuth and explicit adoption of the existing fixture before a new one-shot read authorization (authorization #4). The compact resident read command `read-current --execute-live-read --token-input resident-memory` resolves this CLI limitation by binding directly to the package's canonical artifacts without caller-supplied paths. The read path still has no hidden refresh, account lookup, discovery, listing, probe, or additional Sheets request; its GET is locally restricted despite the mutation-capable scope. The historical hostile audit passed the resident-process design with its documented limitations.

## Explicit real-input schemas

Installed client input: explicit absolute private path, downloaded JSON, outer object exactly `installed`; inner fields exactly `client_id`, `project_id`, `auth_uri`, `token_uri`, `auth_provider_x509_cert_url`, `client_secret`, `redirect_uris`. Post-freeze offline preparation found that a real Google-generated Desktop client JSON used legacy `auth_uri` metadata `https://accounts.google.com/o/oauth2/auth`, which the frozen Phase 3 loader refused. The Phase 4 compatibility loader accepts exactly that metadata value or `https://accounts.google.com/o/oauth2/v2/auth`; it uses neither downloaded value as a navigation target. Frozen `DesktopPreparer` still constructs the actual authorization request with its fixed current `/v2/auth` endpoint. No legacy endpoint was contacted. The loader retains a usable Google installed client ID, safe project label, printable nonempty secret, exact token URI `https://oauth2.googleapis.com/token`, cert URL `https://www.googleapis.com/oauth2/v1/certs`, and redirects exactly `["http://localhost"]`. The actual listener is random-port `http://127.0.0.1:PORT/`. Other downloaded shapes need renewed offline audit. Web, service account, ADC/cloud SDK, unknown fields/endpoints/redirects, duplicates, unsafe modes and links refuse. No directory discovery or configurable authorization endpoint.

`client-review.json`: exact Phase 4 schema, `public` equal to the Phase 3 public identity projection with the current `/v2/auth` runtime endpoint, `public_sha256` over that projection alone. Secret changes do not alter this hash. Client secrets, raw client JSON and secret hashes never enter evidence. Both review and acquisition use the same Phase 4 compatibility loader; acquisition must match the reviewed public hash.

`operator.json`: exact `OperatorConfiguration` dataclass fields, with nested exact Phase 3 RuntimeConfiguration fields. The tracked template intentionally retains `expected_head: null` and is unusable as an operational configuration. The retained predecessor configuration is never overwritten. A fresh package receives the independently audited full commit of the clean checkout used for its transition; the new SHA is never automatically taken from the current checkout.

`acquisition.json`: exact frozen `AcquisitionMetadata.projection()`, including requested/granted scope, Bearer, exchange-start expiry, Python version, public client hash, independent account alias, bounds, uncertainty and refresh persistence none. It is not token introspection or remote account identity proof. Never persist the compatibility-only Phase 1 `CredentialProvenance.evidence()` (its library label is inherited and incorrect for stdlib acquisition).

`create-intent.json`: exact method/host/path/body/scope/client/account/config hash, durable before network. `create-result.json`: fixed schema, typed outcome, intent hash, visible status or null, validated IDs/extent or null. No raw response, headers, exception or bearer. `provisioning.json`: exact frozen positive ProvisioningRecord, emitted only after explicit human isolation/provenance review. `fixture.json`: exact Phase 3 descriptor/hash, independently backed by both records and permanent reservation. A syntactically plausible ID does not prove actual provisioning.

`startup.json`, `offline-pin.json`, `read-pin.json`, `conditions.json`, authorization and both receipts have exact positive schemas enforced by their constructors/projection comparisons. All nonsecret artifacts are canonical JSON plus newline, private exclusive outputs. The downloaded client is bounded strict JSON, not required to be canonical.

## Token acquisition and handoff

`session --execute-oauth --operator-confirmation EXPLICIT_OPERATOR_OAUTH_ACQUISITION` first validates offline readiness, client review, clean identity and startup. An exclusive `oauth-intent.json` prevents another acquisition in this operational package after failure/restart. Phase 3 constructs one PKCE S256 session, prints one exact authorization URL to the interactive terminal, accepts one loopback callback, verifies state and exchanges one code. Exact drive.file, Bearer and positive finite expiry are required. Expiry is exchange start plus expires_in. Refresh material is discarded; no refresh implementation exists. No browser-launch API is used. A separately authorized operator manually opens the printed URL. Callback/URL/verifier/state/code/response are never evidence.

The first three observed callbacks exposed the authorization response issuer parameter specified by RFC 9207 and, from attempt #2 onward, the returned scope. A success callback requires one each of `code`, `state`, `iss`, `scope`; issuer must equal `https://accounts.google.com` and decoded scope must equal `https://www.googleapis.com/auth/drive.file`. Missing, altered or duplicate security fields fail closed. Unknown non-security-critical query members are ignored and never persisted on success and error callbacks. The exact state check remains. An error callback requires one each of `error`, `state`, `iss` and is always refused before token exchange; its unknown non-security-critical members do not change that refusal. Downloaded client metadata selects neither expected value, and validation makes no discovery request. At this earlier snapshot, token-response compatibility had not yet been demonstrated by an accepted acquisition; attempts #4, #5, #6, and #7 later succeeded.

The short-lived bearer remains ephemeral application memory: resident parent memory, then the inherited anonymous multiprocessing spawn IPC/kernel buffers, then the one read-worker's memory, Authorization header and socket/TLS path. Subsequent typed session commands select `resident-memory`; no application token file, argv, environment variable, evidence JSON, authorization JSON, acquisition metadata, log, token hash, shell substitution, named FIFO or durable broker is intentionally produced. Acquisition failure, uncertain create, blocked preflight, malformed command, EOF or any exception ends the session; read always ends it. No session resume or token recovery. Disable terminal recording/remote transcript capture before acquisition; URLs contain transient state. Core limit is set to zero before OAuth and inherited by the worker. No bearer output or accidental repr is permitted. Python heap, IPC/kernel buffers, swap, OS crash reporting and hostile debugger/admin access are not secure erasure; the trusted operator must exclude these capture mechanisms. This is transient application handoff, not a claim that the OS cannot page memory.

The token parser requires validated `access_token`, positive finite numeric `expires_in`, exact drive.file `scope`, and case-insensitive Bearer `token_type`. It ignores `refresh_token`, `refresh_token_expires_in`, `id_token`, and unknown JSON members without copying them into evidence. A bounded single Content-Length response or a strictly valid chunked response decoded by `http.client` is accepted. Transfer-Encoding plus Content-Length, other transfer codings, close-delimited framing, compressed content, malformed or incomplete bodies, and unrelated media types fail closed. Content-Type accepts `application/json` with an optional explicit UTF-8 charset under HTTP case/OWS rules. Accepted acquisitions in attempts #4, #5, #6, and #7 establish compatibility for those observed responses; they do not establish compatibility with every future provider response shape. Any later incompatibility requires separate review; the exclusive intent remains spent.

`acquisition-failure.json` is a best-effort private, exclusive, durable artifact
written only after a spent OAuth intent when no accepted acquisition is produced.
Its exact `sheets-phase4-acquisition-failure-v1` projection contains `status=BLOCKED`,
`recovery=stop-review-no-retry`, one closed-enum `last_stage`, one closed-enum
`reason`, and optional fixed classes for HTTP status, framing, content encoding,
content type, and callback count. It contains no provider header, body, query,
URL, exception, traceback, account, state, code, token, secret, or hash of those.
The closed HTTP status classes are `200`, `other_2xx`, `4xx`, `5xx`, and `other`;
only exact 200 qualifies the token response. The closed framing classes are
`content_length`, `chunked`, `unsupported_transfer`, `neither`, and `conflicting`.
Duplicate framing headers can leave the framing class unset before rejection.
The producer and predecessor loader share cross-field validation: callback and
HTTP classes must match the reported stage and reason. This schema is included
in the Phase 4 runtime pin's explicit schema inventory.
Failure to persist this diagnostic leaves the intent spent and never repairs it.
The stages distinguish listener, callback, token connection, status, HTTP body,
JSON, semantics, and local persistence for future attempts. The old attempt #3
has no such artifact, so its exact failure stage remains unknown.

The OAuth token transport was qualified and frozen at `594c95f`. Before this
separate CREATE/READ patch, both Sheets response paths accepted Content-Length
only and rejected a valid chunked response. CREATE and READ now share the
bounded JSON framing primitive used by OAuth. It accepts one canonical bounded
Content-Length without Transfer-Encoding, or sole valid HTTP/1.1 chunked
Transfer-Encoding without Content-Length; `http.client` decodes chunks. It
requires a complete bounded body, absent/identity Content-Encoding, and
`application/json` with optional UTF-8 charset (case and HTTP OWS handled).
Duplicate or conflicting framing, other transfer codings, close-delimited
bodies, compression, unrelated media types and malformed/incomplete bodies
fail closed. The CREATE intent is durably exclusive before dispatch; any
post-dispatch outcome that cannot be locally validated remains
`CREATE_UNCERTAIN_RECONCILIATION_REQUIRED` and never licenses another create.
READ retains its one-use `LIVE_READ_GO` binding, deadline and evidence rules.
Those raw HTTP qualifications were synthetic, not proof of Google's live response
shape at that time. Attempt #5 later validated its CREATE HTTP 200 response;
the first Sheets GET remains unobserved. At that earlier snapshot there had been no real spreadsheet operation or paper observation;
paper observations were **0**. OAuth attempt #4 subsequently completed a reviewed live OAuth acquisition successfully under frozen commit `594c95f`; the resident session was intentionally stopped before provisioning. Attempt #5 later created the validated fixture and issued the first authorization, which expired unused as recorded at the top. Any later live Sheets action requires separate hostile
audit, freeze and authorization.

## Concrete operational budgets

All values below are explicit frozen engineering controls, not measured Google latencies or scientific variables. They are editable only in the reviewed private operator configuration and all enter the runtime hash.

| Setting | Seconds | Basis |
| --- | ---: | --- |
| DNS allocation | 5 | Generous local resolver allocation for one host; actual behavior unmeasured |
| TCP allocation | 5 | One fresh connection allocation; no separate probe |
| TLS handshake allocation | 10 | Conservative handshake allocation without weakening policy |
| TLS evidence allocation | 3 | Bounded observation and durable local append |
| Construction/serialization allocation | 3 | Small GET plus SSL construction allowance |
| Evidence fsync allocation | 5 | Local private filesystem budget; power-loss claims remain blocked |
| HTTP status allocation | 10 | Bounded first response allowance |
| Body allocation | 10 | Small dedicated-grid response; no streaming/polling |
| Parser allocation | 3 | At most 262144 UTF-8 bytes and bounded cells |
| Local verifier/spawn/closure allocation | 6 | Frozen worker startup/IPC/reaping allowance; no second GET |
| **Overall monotonic deadline** | **60** | Sum of ten allocations, enforced by unchanged Phase 2 supervisor/lifeline |
| Additional safety margin | 10 | Scheduling/local pre-handoff work allowance; no hard realtime claim |
| Wall-clock uncertainty | 2 | Operator must independently establish clock error <=2 seconds, stable through attempt |
| **Readiness bound** | **72** | 60 + 10 + 2; strict greater-than checks |
| Minimum remaining lifetime before setup/handoff/issue/read | 900 | 15-minute manual review envelope, exceeds create30 + bound72 and auth120 + bound72 |
| Authorization validity | 120 | Short human inspection window; 72 <120 <=144 inherited issuance bound |
| OAuth consent listener | 300 | Five-minute manual consent window; one request |
| OAuth exchange socket timeout | 30 | One exchange, no retry |
| Fixture create socket timeout | 30 | One state-changing request, no retry |

DNS/TCP/TLS/etc are **allocations**, not independently enforced stage timeouts: frozen Phase 2 uses one decreasing monotonic overall deadline throughout DNS/connect/TLS/status/body/parser and evidence work. No new independent stage timers reset it. The 900-second minimum is checked at Phase4 operational action boundaries, including fresh checks before issuance intent and after inherited issuance work; the unchanged Phase3 wrapper separately repeats the72-second full readiness bound before transport handoff, and Phase2 repeats remaining-deadline readiness at raw send. The minimum is not a claim that900 seconds must remain at every subsequent instruction. The safety/uncertainty are readiness additions, not extensions to the 60-second attempt. Watchdog kill/reap/fsync and OS scheduling are not hard realtime. OAuth/create have per-operation socket/listener limits, not a hard total setup watchdog; operator abort is safe with respect to resends because intent remains spent. Maximum response 262144 bytes limits evidence/parser memory for 300 cells; max literal cell512 conservatively detects contamination. 100x3 grid is intentionally tiny; failure on larger unexpected data requires review, never parser widening during live use. Clock qualification is an operator assertion, not established by this phase; no NTP/provider request is added.

## Startup and trust decision

The hostile-audited design uses the trusted-local-operator/machine model with the following limits. Parent trust inventory checks before each action, before read and after return bind current default CA material. Frozen Phase 2 builds the verifying context later in its child. A change-and-restore race is not cryptographically prevented. Stable trust/runtime/route through the entire session is an explicit operational prerequisite. Root/admin/same-UID tamper, previously injected code, transparent interceptors and full OS sandboxing remain outside the model. Local inventories never establish the actual Google peer/route.

The clean-session launch below starts a fresh no-startup-files shell with a minimal environment. No proxy/CA overrides, SSL keylog, Google/ADC discovery, GIT/LD/DYLD/Python injection settings. No package, source, interpreter, VPN/proxy, root certificates/system trust or clock adjustments during session. All nine explicit startup flags are required; they are assertions, not measured facts. Storage and clean expected HEAD are also checked. The attestation is deterministic, contains public runtime hash and fixed assumptions, never ambient environment values. No administrator-modification-prevention claim.

## Runtime pin and storage review

Phase 4 pin binds expected full commit/clean-tree requirement, interpreter resolved identity and inherited version/binary/stdlib/native/lock/platform identity, Phase 1/2/3/4 sources, Phase 4 procedure/config template/runner, operator config, client review, trust inventory and schema versions. It additionally records resolved path and file SHA-256 for the directly relevant `_socket` and `fcntl` native extensions, absent from inherited explicit module pins. If either lacks a stable file representation, the Phase 4 gate fails closed pending review; a module name or version is not presented as a content hash. Pre-setup pin has fixture null; after reviewed actual creation, the separate read pin adds the complete descriptor. This is an explicit local pin step, not a trust refresh. Startup remains bound to the unchanged pre-setup projection. Each action recomputes and compares it. Drift of these selected components, trust, source, budget, client identity, fixture and configuration changes alters projection/hash or fails repository/runtime gates. The projection is **not** an exhaustive cryptographic inventory of all code, native libraries, OS services or privileged changes capable of affecting execution. This document is included in the source projection, so changing it invalidates the real predecessor package's old source-bound pins for new live work. Preserve those records as historical evidence and use the reviewed successor under an independently audited frozen checkout.

Original historical first-package storage root: `/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read`; the current retained package is identified at the top of this document. Storage is persistent, outside the repo, on private local POSIX disk. Dedicated parent `RetrySemantics` and root/registry 0700. No symlink ancestry, group/world-writable immediate parent, foreign-owner entries, hard links, nonregular files, unknown root filenames or modes. Operator must review local disk fsync/flock semantics, backup/indexing/terminal and host capture policies; storage-check does not detect backup agents or prove power-loss durability.

| Location under root | Mode / creation | Contents / retention |
| --- | --- | --- |
| operator.json | 0600, operator exclusive canonical creation | Public config, permanent |
| client-review.json, startup.json, offline-pin.json | 0600 O_EXCL | Nonsecret review and local pins, permanent; regenerated only in a fresh package |
| supersession.json | 0600, exclusive hard-link activation | Nonsecret predecessor reference in a fresh pre-live successor |
| acquisition-attempt.json | 0600, exclusive hard-link activation | Nonsecret predecessor reference in a fresh reviewed acquisition attempt |
| unused-acquisition-supersession.json | 0600, exclusive hard-link activation | Nonsecret, operator-attested successor of an accepted but unused acquisition |
| unused-read-authorization-supersession.json | 0600, exclusive hard-link activation | Expired unused first authorization and validated fixture bound to the predecessor; no read dispatch |
| fixture-adoption.json | 0600 O_EXCL | Nonsecret local adoption binding after fresh OAuth in the successor |
| oauth-intent.json, acquisition.json | 0600 O_EXCL, file+parent fsync | Spent acquisition intent and safe metadata, permanent |
| create-intent.json, create-result.json | 0600 O_EXCL, file+parent fsync | One create intent/typed outcome; permanent even partial |
| provisioning.json, fixture.json, read-pin.json, conditions.json | 0600 O_EXCL, file+parent fsync | Explicit reviewed provenance and local binding, permanent |
| registry/registry.lock, reservation-ID.json | directory0700/files0600, inherited flock/O_EXCL/fsync | Permanent fixture/namespace reservation, no registry substitution |
| issue-intent.json, authorization.json, phase3-receipt.json, phase4-receipt.json | 0600 O_EXCL, file+parent fsync | Unique read issuance and public binding, permanent |
| read-intent.json, result.json | 0600 O_EXCL, file+parent fsync | One wrapper call and safe result, permanent |
| registry/claim-ID.json, attempt-ID.jsonl | inherited0600 exclusive reserve, fsync each typed append | Permanent consumption and TLS/lifecycle/terminal evidence |
| Interactive terminal | no evidence file; recording disabled | Authorization URL transient; nonsecret commands/results may be manually retained after session |
| Downloaded OAuth client | operator-selected private outside repo, 0600, no links | Long-lived secret input; explicitly reviewed retention/backup policy, never copied into evidence |
| Bearer / refresh / callback | no durable application location | Bearer in parent/worker memory and anonymous spawn IPC; refresh discarded; no application token hash |

No automatic deletion, overwrite, claim refund, registry reset or cleanup of an existing package. Fsync failure leaves poisoned residue. Stop and preserve it. Exclusive local creation does not create a global/provider idempotency key. Do not change storage root/ID to evade uncertainty after any live boundary. No temporary bearer file is implemented.

## Pre-live offline package supersession (no provider access)

`supersede-prelive` is available only when the predecessor contains `operator.json`, optional `client-review.json`, `startup.json`, `offline-pin.json`, at most one valid earlier successor provenance artifact (including `unused-read-authorization-supersession.json`), and an **empty** `registry/`. A successor descended from the expired-unused-read transition retains the fixture-reuse restriction through its validated predecessor chain. Every present file must pass private-file and canonical-JSON checks; startup and pin retain their expected top-level offline shapes and bindings. When the offline pin is present, the stored startup runtime hash must equal the canonical public hash of that exact pin; the old pin is not recomputed from current source. Any other root entry, any registry entry (including a lock), unsafe path, link, unknown file or malformed allowed artifact refuses before creating a successor. In particular `oauth-intent.json`, `acquisition.json`, every local create/provisioning/fixture/reservation artifact, `read-pin.json`, `conditions.json`, every issuance/authorization/receipt artifact, `read-intent.json`, `result.json` and registry reservation/claim/attempt evidence permanently disqualify this operation. It is not OAuth retry, create retry, ambiguous-operation recovery or a way to change an identity after live use. There is no `--force` or cleanup path.

The command takes the predecessor's `operator.json`, an independently audited full new commit and `EXPLICIT_OFFLINE_PRELIVE_SUPERSESSION`. It checks the new clean HEAD and old package, then exclusively creates one deterministic sibling named `<old-root>-at-<new-full-SHA>`. The predecessor is opened read-only and its bytes are never changed. The successor starts with only a new `operator.json`, empty `registry/` and nonsecret `supersession.json`; it copies no client review, startup pin, bearer, credential or live artifact. The provenance states predecessor path/head/operator hash, successor path/head, allowed offline filenames and that no live-boundary artifact was present. It is a local operator record, not proof of remote nonexecution or a cryptographic attestation of the machine.

Creation fsyncs the new directory, empty registry, pending provenance and new operator file before activation. The pending provenance name makes storage checks refuse the package. An exclusive hard link creates the final name, its directory is fsynced, and the predecessor is checked again while both links still block use. Only then is the pending link removed. A crash, persistence error or failed final predecessor check leaves either no usable successor or visible pending/two-link residue, which must be preserved and reviewed; no retry or automatic repair is implemented. Exclusive sibling creation makes a second concurrent attempt or pre-existing/symlink destination fail closed. The final unlink is an atomic visibility step, not a claim of power-loss durability beyond the trusted local POSIX storage model. Operationally, no predecessor session or action may run concurrently with supersession. This trusted-local-operator workflow is not an OS security sandbox and cannot cryptographically prevent a same-UID actor from changing filesystem state in the final instruction-level race.

From an independently audited, clean frozen checkout, the offline command shape is:

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator supersede-prelive --configuration "$OLD_P4/operator.json" --new-expected-head AUDITED_NEW_FULL_SHA --operator-confirmation EXPLICIT_OFFLINE_PRELIVE_SUPERSESSION
```

Use the returned successor path for a **fresh** offline client review, startup attestation, offline pin and Phase 4 preflight. The external Google client file stays outside both packages and is reviewed again; do not copy its secret or the predecessor's public review. The tracked configuration template keeps `expected_head: null`. Supply the exact full SHA that independently passed audit and freeze through `--new-expected-head`. A command does not trust a checkout HEAD merely because it is current. Before that audit and freeze, this mechanism has no operational authority. Supersession itself performs no OAuth or provider action and does not grant LIVE-GO; a fresh offline preflight and separate live permission remain required.

## Earlier new-acquisition path after a spent OAuth intent — no created fixture

This path applies only to eligible packages without a created fixture. It
refuses the current expired-unused-read fixture-reuse lineage and is not the
recovery path for authorization #1.

`new-acquisition-attempt` applies only when the predecessor contains exactly the valid offline package (`operator.json`, `client-review.json`, `startup.json`, `offline-pin.json`), exactly one valid `oauth-intent.json`, an empty `registry/`, at most one valid `acquisition-failure.json`, and at most its valid prior `supersession.json` or `acquisition-attempt.json`. Every other root file and every registry entry blocks it, including `acquisition.json`, all create/provisioning/fixture records, conditions/read pin, issuance/authorization/receipts, read intent/result, mutation/ambiguity evidence and paper observations. Unknown files, malformed intent or missing intent also block it. The existing `supersede-prelive` rule is unchanged: any OAuth intent permanently bars pre-live supersession.

The operator supplies the predecessor `operator.json`, a separately audited clean full commit SHA different from the predecessor SHA, and `EXPLICIT_REVIEWED_NEW_ACQUISITION_ATTEMPT`. The deterministic sibling name is `<old-root>-acquisition-at-<new-full-SHA>`. Its first contents are only a new `operator.json` bound to that SHA, empty `registry/` and `acquisition-attempt.json`. It inherits no client review, startup/offline pin, OAuth intent, acquisition, bearer/code or later fixture/read state. The provenance records the predecessor path/head, hashes of its public operator and OAuth intent, the present offline filenames, and that no successful acquisition artifact was accepted locally and no Sheets-side artifact exists. **Absence of a local acquisition artifact does not establish what Google may have issued remotely.** The old package and its intent remain permanently spent and byte-for-byte untouched; this is a separately reviewed attempt, not a reset or retry of that package.

Creation uses exclusive `mkdir`, private exclusive writes, directory fsyncs, a pending provenance name that blocks use, predecessor rechecks before and after the final hard link, and final activation only after those checks. A pre-existing destination or symlink blocks creation. A crash, fsync failure or predecessor change leaves visible unusable residue; there is no cleanup or retry path. The new package must repeat `client-review` → `startup` → `offline-pin` → `phase4-preflight` before any separately authorized OAuth action. The transition itself performs no browser, provider or Sheets operation and grants no LIVE-GO.

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator new-acquisition-attempt --configuration "$SPENT_P4/operator.json" --new-expected-head AUDITED_NEW_FULL_SHA --operator-confirmation EXPLICIT_REVIEWED_NEW_ACQUISITION_ATTEMPT
```

## Reviewed successor after an accepted, unused acquisition

OAuth attempt #4 succeeded under `594c95f`: its `oauth-intent.json` and accepted
`acquisition.json` are present, while `acquisition-failure.json` is absent. The
resident session reached `phase4>` and the operator intentionally entered
`stop` before provisioning. CREATE/READ framing was subsequently qualified and
frozen at `bb8c1d2`. At that historical point, no Sheets create, provisioning,
genuine `LIVE_READ_GO`, Sheets GET, Sheets mutation or paper observation had
occurred; paper observations were **0**. The #4 package is historical evidence
and must remain untouched.

`supersede-unused-acquisition` is a distinct offline transition. Its predecessor
must have the complete valid offline package, exactly one valid OAuth intent,
an accepted acquisition metadata artifact bound to the reviewed client,
account and runtime clock allowance, and an empty registry. It may have one
valid earlier provenance record. Acquisition failure, every Sheets setup/read
artifact, an unknown root entry, or any registry entry blocks it. The existing
`new-acquisition-attempt` still rejects accepted `acquisition.json`; this
transition does not call that failed-acquisition path. This older transition
also refuses the current fixture-reuse lineage; it cannot be used to evade the
existing CREATE.

The operator supplies a separately audited clean new HEAD and
`EXPLICIT_UNUSED_ACQUISITION_SESSION_STOPPED`, attesting that the resident
session ended before provisioning. This fact cannot be inferred from files.
The accepted `acquisition.json` contains only exact nonsecret metadata and
`refresh_persistence: none`; the bearer was transient in the resident process.
The exact predecessor package inventory excludes a persisted token or refresh
credential. Stopping the session discards its resident state, so this workflow
requires a fresh OAuth acquisition under the new source. This makes no claim
that Google revoked the old token, that any copied token is cryptographically
unusable, or that the remote authorization grant disappeared.

The successor has the fixed one-shot sibling basename
`sheets-phase4-unused-acquisition-successor-<full SHA-256>`. The digest is over
canonical nonsecret data containing the absolute predecessor root path. The
107-byte ASCII basename is independent of both predecessor basename length and
the supplied new HEAD. Before creation, `PC_NAME_MAX` is read from the actual
parent filesystem and a missing, invalid or too-small limit fails closed. During
storage inspection, the predecessor path in the record must be a valid sibling
and must recompute to the current successor path; a bare dedicated-prefix root
without activated provenance is refused. Exclusive creation prevents another
successor even after a later source change. A successful short successor may
itself undergo the ordinary pre-live supersession if source changes again before
OAuth.
Its initial contents are only a new `operator.json` bound to the supplied HEAD,
an empty `registry/`, and `unused-acquisition-supersession.json` with schema
`sheets-phase4-reviewed-unused-acquisition-supersession-v1`. The nonsecret record
binds predecessor/successor paths and heads, hashes of the predecessor public
operator, OAuth intent and accepted acquisition metadata, the exact allowed
filenames, the operator's stop attestation, and requirements for a new client
review, startup/offline pin and separately approved OAuth. No bearer, refresh
material, prior review, acquisition, or Sheets evidence is copied.

Creation follows the existing exclusive-directory, private-write, file fsync,
directory fsync, pending-provenance and hard-link activation sequence. The
predecessor is checked again before and after the final link. A crash, collision
or concurrent change leaves no usable successor or leaves visible blocked
residue; there is no cleanup or automatic retry. The predecessor's bytes remain
unchanged. Inspect reports the missing fresh review/startup/pin, and preflight
remains `LIVE-GO CLOSED` until those offline steps pass. Passing them does not
authorize a new OAuth attempt or any Sheets action.

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator supersede-unused-acquisition --configuration "$ACCEPTED_UNUSED_P4/operator.json" --new-expected-head AUDITED_NEW_FULL_SHA --operator-confirmation EXPLICIT_UNUSED_ACQUISITION_SESSION_STOPPED
```

This historical command applied to an accepted acquisition before any CREATE.
It is not a recovery command for the current expired-unused-read package. Its
presence in the source grants no live-action permission.

## Historical controlled live operator sequence — superseded, do not execute

OAuth attempts #1, #2 and #3 were separately authorized and reached their callbacks. The then-frozen parsers rejected `iss` and `scope` on #1 and #2, respectively. Attempt #3's callback matched its accepted shape, but the old build did not localize the subsequent failure. All three packages and their `oauth-intent.json` records remain permanently spent; none accepted a local acquisition artifact. OAuth attempt #4 was then performed from a fresh reviewed package bound to frozen commit `594c95f` and successfully produced an accepted local `acquisition.json`; `acquisition-failure.json` was absent. The resident session reached `phase4>` and was intentionally terminated with `stop` before provisioning. At that earlier point, no fixture CREATE, genuine `LIVE_READ_GO`, Sheets GET or Sheets mutation had occurred, and paper observations were **0**. Attempt #5 later created the validated fixture and issued authorization #1; attempt #6 adopted that fixture and issued authorization #2; OAuth attempt #7 succeeded for the second reused-fixture successor bound to newly frozen commit `739b30e4d5b34997defa9beb0eabcb0d40084677`, the same fixture was adopted, and authorization #3 was issued; the verbose read line (~1410 bytes) was truncated at byte 1024 by the macOS TTY line limit before execution; none of the reads were executed, and zero GETs and zero paper observations remained. The commands below record the superseded workflow and grant no execution authority. Never rerun its CREATE against the existing fixture.

1. Obtain the audited full Phase 4 commit from the freeze review. Checkout it under that later permission, verify clean tree. Run regression before the live session. No dependency download/update during session.
2. Establish independently clock <=2s, dedicated reviewed app/project/account, API enabled/consent configured, no existing unrelated data/default-domain sharing/automation/writers, local trusted disk and capture controls. Cloud/API configuration is a separately authorized human setup prerequisite, not a hidden API call in this tool.
3. For a new operational package, prepare an explicit downloaded installed-client outside repo, 0600, no links; never paste secrets in the shell. Choose its absolute path below. Verify parent permissions and no backup/indexing of secret input. Create storage exactly once under later setup authorization. Retain both spent OAuth packages; use the audited `new-acquisition-attempt` mechanism and its returned path. The following block records original first-package bootstrap semantics and must not be rerun against an existing package. Existing root means inspect/review, never reset.

```sh
cd /Users/jashrashne/Desktop/retry_semantics
git status --short
git rev-parse HEAD
# Replace AUDITED_FULL_PHASE4_COMMIT below with the independently approved 40-hex value.
env -i HOME=/Users/jashrashne PATH=/usr/bin:/bin:/opt/homebrew/bin LANG=en_US.UTF-8 /bin/zsh -f
cd /Users/jashrashne/Desktop/retry_semantics
set -e
umask 077
ulimit -c 0
mkdir -m 700 '/Users/jashrashne/Library/Application Support/RetrySemantics'
mkdir -m 700 '/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read'
mkdir -m 700 '/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/registry'
export P4='/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read'
export CLIENT='/ABSOLUTE/PRIVATE/OPERATOR_SELECTED/installed-client.json'
export AUDITED_HEAD='AUDITED_FULL_PHASE4_COMMIT'
.venv/bin/python - <<'PY'
import json, os
from pathlib import Path
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_operator as op
from retry_semantics.study2 import sheets_phase4_control as p4
value=json.loads(Path('research/study2/sheets/SHEETS_PHASE4_OPERATOR_CONFIGURATION_DRAFT.json').read_text())
value['expected_head']=os.environ['AUDITED_HEAD']
configuration=op._typed(value,p4.OperatorConfiguration)
p3.repository_check(configuration.expected_head)
p3.write_json(configuration.path('operator.json'),configuration.projection())
PY
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator client-review --client "$CLIENT" --output "$P4/client-review.json"
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator startup --configuration "$P4/operator.json" --trusted-local-operator-machine --no-concurrent-source-runtime-changes --no-trust-store-or-system-certificate-changes --no-vpn-proxy-route-changes --no-package-updates --clock-within-allowance --private-storage-reviewed --no-terminal-recording-or-core-dumps --hostile-audit-approved
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator phase4-preflight --configuration "$P4/operator.json"
```

Every failed command/output is a stop condition; `set -e` ends this clean shell on shell-command failure. Never continue through mkdir/client/config errors or overwrite existing artifacts. The review must precede offline preflight because it is an input to that gate. Offline PASS checks exact approved clean HEAD, inherited runtime, Phase 4 source/config/client/trust/startup pin, safe storage, checklist-closed policy and **pristine setup/registry**. It proves only readiness to begin separately approved setup. No credentials/fixture/authorization are claimed. Repeated offline preflight is deterministic and read-only. Once any setup intent exists this gate blocks; do not rerun setup to repair it.

4. Inspect public client identity/startup/pin/config. Disable any terminal logging now. Start the one resident acquisition command:

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator session --configuration "$P4/operator.json" --client "$CLIENT" --execute-oauth --operator-confirmation EXPLICIT_OPERATOR_OAUTH_ACQUISITION
```

Manually open the printed URL only now. Check consent app/account/exact scope; no broadened scope allowed. This prints no bearer. Acquisition alone never creates LIVE_READ_GO. If any failure: stop; intent stays spent. New acquisition/setup needs incident review and a separately audited new package, no automatic loop.

5. At the `phase4>` prompt type these commands **one at a time**, after inspecting each outcome. This is a restricted dispatcher, not a shell; `$P4` is not expanded inside it.

```text
provision --execute-provisioning --operator-confirmation EXPLICIT_ONE_ENGINEERING_FIXTURE_CREATE
```

This is the exact actual-fixture command, with the explicit resident token and pinned operator configuration. It may send one setup POST, never GET. Inspect create-intent/result from a separate clean terminal; no new provider access:

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator inspect --configuration "$P4/operator.json"
```

Review returned file identity, intended sheet and dimensions, app/account and isolation controls from the safe records. Do not open the spreadsheet UI or run a provider read/list as an unrecorded check. Human positive review is a statement about the recorded create action and independently established controls; it does not replace the first baseline GET.

6. Back in the resident prompt, only for CREATE_RESPONSE_VALIDATED with actual human provenance/isolation review:

```text
review-provisioning --operator-confirmation REVIEWED_SAME_APP_ENGINEERING_PROVISIONING --isolated --no-writers
reserve-and-descriptor
attest-post-setup --provisioning-reviewed
post-setup-preflight
bindings
```

Post-setup PASS is local-only and requires actual-shaped descriptor, validated intent/result, separately reviewed record, active permanent reservation, exact acquisition projection/client/account/expiry, explicit in-memory PreparedToken with matching finite expiry/uncertainty and >902s remaining, exact clean runtime/source/startup/trust/storage, all Phase 3 conditions, no prior issuance/claim/attempt and no unresolved create uncertainty. Real-shaped test inputs are synthetic fixtures in fake-only tests, not real acquisition. `bindings` emits the four nonsecret hashes to copy into the next command; it does not authorize anything.

7. Human now deliberately issues the genuine read authorization. Replace the four placeholders with the exact inspected bindings; never accept a changed hash by recomputing approvals silently.

```text
issue --capability LIVE_READ_GO --engineering-only --fixture-hash INSPECTED_FIXTURE_SHA256 --runtime-hash INSPECTED_PHASE4_RUNTIME_SHA256 --source-hash INSPECTED_PHASE4_SOURCE_SHA256 --startup-hash INSPECTED_STARTUP_SHA256 --operator-confirmation EXPLICIT_OPERATOR_ENGINEERING_AUTHORIZATION
```

This reruns post-setup requirements and token readiness, checks all exact hashes, uses config's unique ID and operator alias, writes durable one-shot issuance intent and explicit 120s assertion plus required Phase 3/4 receipts. Phase 3 receipt binds its source/runtime/trust/conditions; Phase 4 companion binds operational source/pin/startup/assertion/receipt. Partial output pair/triple is unusable in the **qualified Phase 4 operator/read path**. No genuine assertion was issued in this phase. Assertions and receipts are trusted local workflow controls, not signatures, OS capabilities, language/process sandboxing or global process-wide enforcement. Frozen Phase 3 does not interpret the Phase 4 receipt; frozen Phase 2 does not interpret Phase 3/4 receipts. Arbitrary trusted Python code can directly call lower-level Phase 3/2 APIs or Phase 4 setup APIs outside this wrapper. Operational use assumes the audited workflow and trusted local code/operator.

8. Inspect assertion/receipts via the local `inspect` command in the separate terminal; check authorization hash, LIVE_READ_GO, fixture/runtime/source bindings, unique ID, engineering-only purpose and expiry. Inspect promptly: <48s remains available beyond the72s conservative bound at initial issuance; delay means abort, no reissue.

9. In the same resident prompt execute exactly one future first-read command. The recommended compact command uses the package's already-bound canonical artifact paths directly, avoiding macOS canonical TTY line length limits (62 bytes vs the 1024-byte limit):

```text
read-current --execute-live-read --token-input resident-memory
```

The older verbose `read` command with explicit literal paths remains available for backwards compatibility (though on deep package paths it exceeds macOS canonical TTY 1024-byte line limits):

```text
read --execute-live-read --token-input resident-memory --fixture "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/fixture.json" --metadata "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/acquisition.json" --authorization "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/authorization.json" --receipt "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/phase3-receipt.json" --operational-receipt "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/phase4-receipt.json" --pin "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/read-pin.json" --configuration "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/operator.json"
```

Both commands converge to the exact same `execute_read()` validation. The qualified Phase 4 dispatcher rejects path substitution, prior read-intent, mismatched receipt/config/startup/runtime and insufficient lifetime. It calls frozen Phase 3 execute_read once; frozen Phase 2 reserves attempt, consumes claim before worker, observes same-socket verifying TLS durably before one exact GET, and enforces one monotonic deadline. No OAuth/refetch, refresh, retry, fallback, redirect, POST or mutation exists in this qualified read path. Setup POST remains an explicitly separate prior action. Session ends after read regardless of result. This workflow claim does not constrain direct trusted-code calls to lower-level APIs.

10. Inspect and reconcile locally, then stop:

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator inspect --configuration "$P4/operator.json"
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator recover --configuration "$P4/operator.json"
git status --short
git rev-parse HEAD
```

No second provider request. Independently review and freeze the first-read engineering result before any mutation work. No AppendCellsRequest, batchUpdate, ambiguity injection, replay, regeneration or paper collection follows automatically.

## Provisioning ambiguity and abort/recovery

Any connection failure, timeout, response loss, malformed/unsupported response, non200/redirect/401 or crash after intent is **CREATE_UNCERTAIN_RECONCILIATION_REQUIRED** (or missing terminal result with retained intent, equally unresolved). This conservative category includes possibly-known noncreation; it never licenses repetition. The tool never retries creation, silently chooses among multiple candidates, deletes, cleans up or lists. Fixed intent is O_EXCL across processes; even a second invocation after apparent clean failure refuses before network. Missing/partial/fsync-failed result remains unresolved. Preserve storage/identity; don't change root or reservation label to evade it.

Human incident procedure: stop session; preserve all local records; record setup attempt interval, public app/account/title and visible status; mark uncertainty unresolved. Do not run another create. Reconciliation requiring a provider UI/read/list is **a separate explicitly approved and recorded incident action outside this package**. This implementation authorizes/executes none. Drive metadata listing could inspect app-authorized files under drive.file, but a negative/empty result is not proof no file was created and must never trigger automatic recreation. Title is not unique/provider-idempotent; multiple candidates cannot be silently selected. If provider incident inspection is later approved, record exact method/scope/filter/pagination/time/coverage/result independently and reopen hostile audit of that procedure. This first-read package cannot convert an uncertain result into a positive descriptor; retire it until a reviewed incident disposition/new audited plan. No claim of remote cancellation from local close/kill.

For OAuth failure before issuance: preserve oauth-intent; no read authorization exists or is consumed. For local review/reservation/issuance failure: partial artifacts stay unusable, with no repairs or overwrites. For read failure/death/storage drift after dispatch might have begun: read intent and/or claim remain spent/unusable; inspect inherited recovery without assuming absence of result means absence of GET. No automatic retry, token refresh, new authorization or remote cleanup is allowed for those failure states. Attempts #5, #6, and #7 are different: authorizations #1, #2, and #3 expired unused with no read intent or GET evidence, so only the narrowly reviewed successor transition at the top can lead to authorization #4 and one explicit GET (`read-current`). It never permits another CREATE.

## Success criteria fixed before execution

Successful first engineering qualification requires: exact approved source/runtime/config/client/fixture/reservation/startup/assertion/receipt binding; unchanged trust assumptions; qualified same-socket TLS policy and typed observation persisted before HTTP; exactly one recorded GET request/local send with no retry/refresh/mutation; visible HTTP **200**; supported framing; strict bounded UTF-8/JSON/grid parser; exact identity/title/extent/type, no tables/merges; zero exact marker matches AND zero nonempty entered rows over the whole grid; complete valid ordered terminal evidence and independently reviewed Phase4 result/recovery. Engineering success cannot imply historical noncommit/H0, mutation placement, paper readiness or remote writer exclusion beyond operator controls. Sparse empty provider shapes remain unqualified if frozen parser refuses.

## Typed first-read failures and diagnostic limits

| Incident category | Frozen evidence / interpretation |
| --- | --- |
| AUTHORIZATION_EXPIRED_BEFORE_SEND | authorization_refused_at_raw_send or local preflight refusal; no automatic renewal |
| TOKEN_READINESS_INSUFFICIENT | token_readiness_refused_at_raw_send or local credential_readiness BLOCKED |
| DNS_FAILURE, TCP_FAILURE, TLS_HANDSHAKE_FAILURE | frozen transport_error at connect stage; **substage not distinguishable**, retain CONNECT_SETUP_UNCERTAIN with all three possible causes |
| TLS_OBSERVATION_FAILURE | tls_observation_refused; no HTTP permitted |
| TLS_EVIDENCE_FAILURE | evidence_storage_error at observation or unusable/incomplete journal; no success |
| UNSUPPORTED_RESPONSE_FRAMING | malformed_or_incomplete, status200, no body-completed fact; no speculative parser adaptation |
| VISIBLE_401 | terminal_http_status with401 |
| VISIBLE_REDIRECT | terminal_http_status with300–399, never follow |
| VISIBLE_NON_200 | terminal_http_status with any other non200, including other2xx; status remains visible |
| BODY_TIMEOUT_OR_TRUNCATION, OVERSIZED_BODY | deadline/transport/malformed with status200 before body-completed; exact cause may be unknown |
| MALFORMED_JSON, UNEXPECTED_GRID_STRUCTURE | malformed_or_incomplete after body-completed; frozen summary does not distinguish both |
| BASELINE_CONTAMINATION | entered rows>0 or marker matches>0; retire, never clean |
| EVIDENCE_PERSISTENCE_FAILURE | evidence_storage_error or missing/invalid terminal artifact |
| WATCHDOG_DEADLINE_TERMINATION | total_deadline_exhausted, no resend |
| UNKNOWN_INCOMPLETE_TERMINAL | worker_incomplete/verifier_uncertainty, invalid/missing result or any drift; unusable |

These are predeclared operator incident categories, **not invented fine-grained facts**. Frozen Phase 2 intentionally exports coarse secret-safe summaries and stage records. Where several causes share evidence, diagnosis stays the explicit set of possible categories; do not report a particular DNS/TCP/TLS/body/parser cause without independent reviewed evidence. Additional diagnostic transport instrumentation would require another audited change, not an extra GET. The hard no-retry decision is identical for every category.

## Hostile qualification and self-audit

New tests trap DNS/socket/HTTP/HTTPS/TLS/URL open/browser before collection, and use independent autouse traps plus inherited spawned fake-worker traps. Fake setup connections test one-intent/no-repeat, malformed/ambiguous outcomes, scope/client contracts, errors/repr/dataflow exclusion and storage poisoning. Two separate synchronized Python interpreters race at the real exclusive create-intent helper; exactly one reaches a trapped provider boundary. A fault at the inherited parent-directory fsync blocks provider construction and leaves the visible intent unrefunded. Budget tests attack all numeric fields, total/expiry coherence and hash changes. Startup/runtime tests attack prohibited environment, dirty checkout, trust/config/source drift, newly pinned native extension path/content replacement and missing native files. Local preflight/issuance tests require positive actual-shaped but synthetic metadata, complete provisioning review/reservation and explicit token lifetime. Phase 4 wrapper tests reject absent/invalid companion receipts before lower-level invocation. Qualification-runner tests verify invocation text, zero/nonzero status and launch-failure reporting. Read tests exercise the actual frozen serializer/parser/evidence pipeline with fake sockets, verify one GET and permanent consumption, and prohibit acquisition/setup/fallback. Tests do not weaken frozen tests or perform real provider/browser access.

Self-audit attacks: duplicate creation across failure/restart/concurrent calls; hidden retry; client secret and bearer through raw configs/errors/repr/hashes/files; acquisition retries; dirty tree and modified trust/config/source; issuance before provenance review or with insufficient lifetime; first read refetch/refresh/twoGETs/mutation/fallback; network escape; treating ambiguous creation as clean retry permission. Durable fixed intents, exact schemas, secret-safe boundaries, startup/runtime comparisons, independent post-setup gates, exact capability/hash checks and frozen one-send guard enforce these under trusted local model. Fine-grained failure diagnostics, non-hard-total setup timing, same-process setup/read, heap/swap capture and non-atomic child trust loading remain explicit audit targets.

Exact qualification commands, from repository root:

```sh
.venv/bin/python scripts/qualify_sheets_phase4_offline.py phase4 --warnings-as-errors
.venv/bin/python scripts/qualify_sheets_phase4_offline.py sheets
.venv/bin/python scripts/qualify_sheets_phase4_offline.py sheets --warnings-as-errors
.venv/bin/python scripts/qualify_sheets_phase4_offline.py study2 --warnings-as-errors
git diff --check
```

Historical Phase 4 compatibility-correction qualification (real network/browser disabled; the runner prints its exact `pytest.main([...])` invocation, returned `QUALIFICATION_EXIT_CODE`, and `QUALIFICATION_RUNNER_EXIT_CODE`; launch failure is explicit):

| Suite | Pass count |
| --- | ---: |
| Phase4 focused, warnings as errors | 277 |
| All Sheets, normal | 1187 |
| All Sheets, warnings as errors | 1187 |
| All Study2, warnings as errors | 1631 |
| Forbidden parent network/browser calls | 0 in each run |
| git diff --check and added-file whitespace checks | PASS |

The historical direct Study 2 qualification at the compatibility correction reported `1631 passed`, `QUALIFICATION_EXIT_CODE: 0`, `QUALIFICATION_RUNNER_EXIT_CODE: 0`, and zero forbidden parent network/browser calls. Warnings-as-errors also applies to inherited spawned helpers. Concrete operational preflight passed at clean corrective commit `6525ddbe3e2eadb2dc55d301914e75ed41f8dfe6`; the docs-only freeze at `055c2ce30f350899f6babbd84770d6532ef1d6d5` made that package's pins stale. The safe pre-live supersession mechanism froze at `4ee2e15cbf206006bf39685e6afae53ae2e6f420`. A real successor package was created and, at that clean frozen commit, fresh client review, startup, offline pin and `phase4-preflight` all passed with an empty registry. OAuth attempt #1 then durably spent `oauth-intent.json` and failed at callback validation. The `iss` correction and reviewed new-attempt mechanism later froze at `52ea5427e3bd157f1b6e294cb6ecdef6f3eedb98`; separately authorized attempt #2 used a fresh package and spent its OAuth intent when the callback's additional `scope` was rejected. Attempt #3 subsequently used a package at `c2454bd43e32e670b87735843db1c4b21404b294` and failed after a matching callback but before accepted local acquisition persistence. The exact stage is unknown. No historical preflight grants authority to any later source revision; a fresh package bound to the exact reviewed commit is required before live use.

Earlier corrective qualification for the `iss` and reviewed-new-attempt changes was run while those changes were uncommitted. This table records that run and does not assert a later freeze state:

| Corrective offline qualification | Result |
| --- | ---: |
| Focused callback tests | 28 passed |
| Phase 4, warnings as errors | 341 passed |
| All Sheets | 1262 passed |
| All Sheets, warnings as errors | 1262 passed |
| All Study 2, warnings as errors | 1706 passed |
| Qualification exit codes | 0 on every run |
| Forbidden network/browser calls | 0 on every run |

## Historical checklist snapshot before OAuth attempt #5

At this earlier snapshot, only additive `phase4_update` metadata had been added
to the evolving checklist. The recorded 28-item classification was **16 PASS
OFFLINE, 7 BLOCKED, 5 REQUIRES LIVE VALIDATION**. These were the checklist's
then-recorded counts, not a formal reclassification after attempt #5. This
section must not be interpreted as the current operational state; the opening
current-state section is authoritative.

The entries then recorded as BLOCKED were
`credential_acquisition_and_budget`, `real_tls_connector_authorization`,
`actual_fixture_and_reservation`, `separate_live_authorization`,
`crash_recovery`, `visibility_bounds`, and `paper_protocol`. In particular,
the historical acquisition, fixture, and authorization blockers preceded the
successful OAuth #5, validated CREATE, reviewed reservation, and issued but
unused authorization #1. No new checklist counts are asserted here.

The entries then recorded as REQUIRES LIVE VALIDATION were
`actual_grid_response_shapes`, `baseline_isolation`,
`clean_success_placement`, `live_ambiguity_boundary`, and
`actual_tls_trust_phase1`. No first GET had occurred then or has occurred now;
read-result review and any later mutation protocol remain separate work.
Study 2 also included Stripe TEST MODE.

That historical audit recorded limits including the trusted stable session,
transient bearer and anonymous spawn IPC, operator attestations rather than
remote introspection, selected runtime pinning, OS capture limits, and bounded
setup operations without a hard total setup watchdog. At that snapshot, only
the first three callback shapes had been observed; token response, CREATE/READ
framing, and empty-grid response remained live-unvalidated. Attempts #4, #5,
#6, and #7 later accepted OAuth responses, and attempt #5 validated one real CREATE
HTTP 200 response. The READ response and empty grid remain unobserved because no
GET was dispatched. The independent Phase 3 clean-room re-audit had passed for
its historical build. No experimental mutation trial or ambiguity injection
had begun at that snapshot; the later engineering spreadsheet CREATE did occur.

**CURRENT RECOVERY: REVIEWED EXPIRED-UNUSED-READ SUCCESSOR (SAME OR CHANGED FROZEN HEAD) → FRESH CLIENT REVIEW/STARTUP/OAUTH → EXPLICIT EXISTING-FIXTURE ADOPTION → FRESH READ PIN/PREFLIGHT → AUTHORIZATION #4 → ONE EXPLICIT COMPACT GET (`read-current`). NO SECOND CREATE. SHEETS GET = 0; PAPER OBSERVATIONS = 0.**

# Google Sheets LIVE-GO Closure — Phase 4

**FROZEN OFFLINE PHASE 4 DESIGN — LIVE-GO CLOSED — ZERO SHEETS PAPER OBSERVATIONS**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*. Academic byline: **J. Rashne**.

This pre-live setup design was frozen at `2ad300227cc786829ed3efa598c66d838493f39a`, corrected for real Google Desktop OAuth metadata at `6525ddbe3e2eadb2dc55d301914e75ed41f8dfe6`, and its operational-state documentation was frozen at `055c2ce30f350899f6babbd84770d6532ef1d6d5`. The independent Phase 3 clean-room re-audit and Phase 4 hostile audit passed. Concrete offline preparation through real client review, startup attestation, offline pin generation and Phase 4 preflight passed before the docs-only freeze; the old package's pins are now stale. Pre-live supersession has operational authority only from an independently audited, clean frozen checkout. None of those results authorizes live setup. Frozen Phase 1/2/3 implementation, tests, runtime pin, templates and history are inherited unchanged. Study 1 is immutable. Study 2 roadmap remains GitHub, Google Sheets, Stripe TEST MODE. Offline engineering tests are not paper data. Real OAuth acquisition, fixture creation, genuine LIVE_READ_GO, Sheets live reads, Sheets live mutations and Sheets paper observations remain **0**; first live qualification has not begun.

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

The file title includes the retained reservation label to aid manual incident reconciliation; it is **not** an idempotency key. Sheet ID 1 avoids omitted-default-zero ambiguity. Exactly one worksheet, 100 rows, three columns; no values, formulas, tables, merges, ACL changes or app-property mutation. The positive response must have exactly the selected structure, matching title/extent/type/ID and a valid actual spreadsheet ID. HTTP 200, single bounded Content-Length UTF-8 JSON is required. Unsupported real framing fails closed. No provider SDK, redirect following, auth middleware, mutation retry or automatic cleanup.

OAuth happens first because create needs a token. The same acquired token, client/app and operator-attested dedicated account then perform setup and the subsequent GET. There is no hidden refresh, account lookup, discovery, listing, probe or additional Sheets request. The later GET is locally restricted despite the mutation-capable scope. The resident session separates the setup POST and GET by distinct human commands and capabilities. Frozen Phase 1's earlier separate-credential/process provisioning proposal is operationally refined here: one resident transient bearer is deliberately reused, with separate setup authorization and a distinct one-use read assertion. The hostile audit passed with this shared trusted-process choice and its documented limitations.

## Explicit real-input schemas

Installed client input: explicit absolute private path, downloaded JSON, outer object exactly `installed`; inner fields exactly `client_id`, `project_id`, `auth_uri`, `token_uri`, `auth_provider_x509_cert_url`, `client_secret`, `redirect_uris`. Post-freeze offline preparation found that a real Google-generated Desktop client JSON used legacy `auth_uri` metadata `https://accounts.google.com/o/oauth2/auth`, which the frozen Phase 3 loader refused. The Phase 4 compatibility loader accepts exactly that metadata value or `https://accounts.google.com/o/oauth2/v2/auth`; it uses neither downloaded value as a navigation target. Frozen `DesktopPreparer` still constructs the actual authorization request with its fixed current `/v2/auth` endpoint. No legacy endpoint was contacted. The loader retains a usable Google installed client ID, safe project label, printable nonempty secret, exact token URI `https://oauth2.googleapis.com/token`, cert URL `https://www.googleapis.com/oauth2/v1/certs`, and redirects exactly `["http://localhost"]`. The actual listener is random-port `http://127.0.0.1:PORT/`. Other downloaded shapes need renewed offline audit. Web, service account, ADC/cloud SDK, unknown fields/endpoints/redirects, duplicates, unsafe modes and links refuse. No directory discovery or configurable authorization endpoint.

`client-review.json`: exact Phase 4 schema, `public` equal to the Phase 3 public identity projection with the current `/v2/auth` runtime endpoint, `public_sha256` over that projection alone. Secret changes do not alter this hash. Client secrets, raw client JSON and secret hashes never enter evidence. Both review and acquisition use the same Phase 4 compatibility loader; acquisition must match the reviewed public hash.

`operator.json`: exact `OperatorConfiguration` dataclass fields, with nested exact Phase 3 RuntimeConfiguration fields. The tracked template intentionally retains `expected_head: null` and is unusable as an operational configuration. The retained predecessor package binds `6525ddbe3e2eadb2dc55d301914e75ed41f8dfe6`. A fresh successor package receives the independently audited full commit of the clean checkout used for supersession; the predecessor configuration is never overwritten, and the new SHA is never automatically taken from the current checkout.

`acquisition.json`: exact frozen `AcquisitionMetadata.projection()`, including requested/granted scope, Bearer, exchange-start expiry, Python version, public client hash, independent account alias, bounds, uncertainty and refresh persistence none. It is not token introspection or remote account identity proof. Never persist the compatibility-only Phase 1 `CredentialProvenance.evidence()` (its library label is inherited and incorrect for stdlib acquisition).

`create-intent.json`: exact method/host/path/body/scope/client/account/config hash, durable before network. `create-result.json`: fixed schema, typed outcome, intent hash, visible status or null, validated IDs/extent or null. No raw response, headers, exception or bearer. `provisioning.json`: exact frozen positive ProvisioningRecord, emitted only after explicit human isolation/provenance review. `fixture.json`: exact Phase 3 descriptor/hash, independently backed by both records and permanent reservation. A syntactically plausible ID does not prove actual provisioning.

`startup.json`, `offline-pin.json`, `read-pin.json`, `conditions.json`, authorization and both receipts have exact positive schemas enforced by their constructors/projection comparisons. All nonsecret artifacts are canonical JSON plus newline, private exclusive outputs. The downloaded client is bounded strict JSON, not required to be canonical.

## Token acquisition and handoff

`session --execute-oauth --operator-confirmation EXPLICIT_OPERATOR_OAUTH_ACQUISITION` first validates offline readiness, client review, clean identity and startup. An exclusive `oauth-intent.json` prevents another acquisition in this operational package after failure/restart. Frozen Phase 3 constructs one PKCE S256 session, prints one exact authorization URL to the interactive terminal, accepts one loopback callback, verifies state and exchanges one code. Exact drive.file, Bearer and positive finite expiry are required. Expiry is exchange start plus expires_in. Refresh material is discarded; no refresh implementation exists. No browser-launch API is used. The future operator manually opens the printed URL only under separately approved OAuth setup permission. Callback/URL/verifier/state/code/response are never evidence.

The short-lived bearer remains ephemeral application memory: resident parent memory, then the inherited anonymous multiprocessing spawn IPC/kernel buffers, then the one read-worker's memory, Authorization header and socket/TLS path. Subsequent typed session commands select `resident-memory`; no application token file, argv, environment variable, evidence JSON, authorization JSON, acquisition metadata, log, token hash, shell substitution, named FIFO or durable broker is intentionally produced. Acquisition failure, uncertain create, blocked preflight, malformed command, EOF or any exception ends the session; read always ends it. No session resume or token recovery. Disable terminal recording/remote transcript capture before acquisition; URLs contain transient state. Core limit is set to zero before OAuth and inherited by the worker. No bearer output or accidental repr is permitted. Python heap, IPC/kernel buffers, swap, OS crash reporting and hostile debugger/admin access are not secure erasure; the trusted operator must exclude these capture mechanisms. This is transient application handoff, not a claim that the OS cannot page memory.

The frozen Phase 3 token parser rejects unrecognized response fields, including a possible provider `refresh_token_expires_in`. An otherwise legitimate future Google response may therefore fail closed: this is a live compatibility/availability risk, not retry permission. The exclusive OAuth intent remains consumed. Any observed incompatibility requires separate review; Phase 4 does not strip fields or silently broaden the frozen parser.

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

Phase 4 pin binds expected full commit/clean-tree requirement, interpreter resolved identity and inherited version/binary/stdlib/native/lock/platform identity, Phase 1/2/3/4 sources, Phase 4 procedure/config template/runner, operator config, client review, trust inventory and schema versions. It additionally records resolved path and file SHA-256 for the directly relevant `_socket` and `fcntl` native extensions, absent from inherited explicit module pins. If either lacks a stable file representation, the Phase 4 gate fails closed pending review; a module name or version is not presented as a content hash. Pre-setup pin has fixture null; after reviewed actual creation, the separate read pin adds the complete descriptor. This is an explicit local pin step, not a trust refresh. Startup remains bound to the unchanged pre-setup projection. Each action recomputes and compares it. Drift of these selected components, trust, source, budget, client identity, fixture and configuration changes alters projection/hash or fails repository/runtime gates. The projection is **not** an exhaustive cryptographic inventory of all code, native libraries, OS services or privileged changes capable of affecting execution. Because the source projection includes this document, the retained predecessor's startup and offline pin no longer match the frozen docs-only commit. A new package, not an overwrite of those records, is required from an independently audited frozen checkout.

Operational storage root: `/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read`; persistent, outside repo, private local POSIX disk. Dedicated parent `RetrySemantics` and root/registry 0700. No symlink ancestry, group/world-writable immediate parent, foreign-owner entries, hard links, nonregular files, unknown root filenames or modes. Operator must review local disk fsync/flock semantics, backup/indexing/terminal and host capture policies; storage-check does not detect backup agents or prove power-loss durability.

| Location under root | Mode / creation | Contents / retention |
| --- | --- | --- |
| operator.json | 0600, operator exclusive canonical creation | Public config, permanent |
| client-review.json, startup.json, offline-pin.json | 0600 O_EXCL | Nonsecret review and local pins, permanent; regenerated only in a fresh package |
| supersession.json | 0600, exclusive hard-link activation | Nonsecret predecessor reference in a fresh pre-live successor |
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

`supersede-prelive` is available only when the predecessor contains `operator.json`, optional `client-review.json`, `startup.json`, `offline-pin.json` and, for an earlier successor, `supersession.json`, plus an **empty** `registry/`. Every present file must pass private-file and canonical-JSON checks; startup and pin retain their expected top-level offline shapes and bindings. When the offline pin is present, the stored startup runtime hash must equal the canonical public hash of that exact pin; the old pin is not recomputed from current source. Any other root entry, any registry entry (including a lock), unsafe path, link, unknown file or malformed allowed artifact refuses before creating a successor. In particular `oauth-intent.json`, `acquisition.json`, every create/provisioning/fixture/reservation artifact, `read-pin.json`, `conditions.json`, every issuance/authorization/receipt artifact, `read-intent.json`, `result.json` and registry reservation/claim/attempt evidence permanently disqualify this operation. It is not OAuth retry, create retry, ambiguous-operation recovery or a way to change an identity after live use. There is no `--force` or cleanup path.

The command takes the predecessor's `operator.json`, an independently audited full new commit and `EXPLICIT_OFFLINE_PRELIVE_SUPERSESSION`. It checks the new clean HEAD and old package, then exclusively creates one deterministic sibling named `<old-root>-at-<new-full-SHA>`. The predecessor is opened read-only and its bytes are never changed. The successor starts with only a new `operator.json`, empty `registry/` and nonsecret `supersession.json`; it copies no client review, startup pin, bearer, credential or live artifact. The provenance states predecessor path/head/operator hash, successor path/head, allowed offline filenames and that no live-boundary artifact was present. It is a local operator record, not proof of remote nonexecution or a cryptographic attestation of the machine.

Creation fsyncs the new directory, empty registry, pending provenance and new operator file before activation. The pending provenance name makes storage checks refuse the package. An exclusive hard link creates the final name, its directory is fsynced, and the predecessor is checked again while both links still block use. Only then is the pending link removed. A crash, persistence error or failed final predecessor check leaves either no usable successor or visible pending/two-link residue, which must be preserved and reviewed; no retry or automatic repair is implemented. Exclusive sibling creation makes a second concurrent attempt or pre-existing/symlink destination fail closed. The final unlink is an atomic visibility step, not a claim of power-loss durability beyond the trusted local POSIX storage model. Operationally, no predecessor session or action may run concurrently with supersession. This trusted-local-operator workflow is not an OS security sandbox and cannot cryptographically prevent a same-UID actor from changing filesystem state in the final instruction-level race.

From an independently audited, clean frozen checkout, the offline command shape is:

```sh
.venv/bin/python -m retry_semantics.study2.sheets_phase4_operator supersede-prelive --configuration "$OLD_P4/operator.json" --new-expected-head AUDITED_NEW_FULL_SHA --operator-confirmation EXPLICIT_OFFLINE_PRELIVE_SUPERSESSION
```

Use the returned successor path for a **fresh** offline client review, startup attestation, offline pin and Phase 4 preflight. The external Google client file stays outside both packages and is reviewed again; do not copy its secret or the predecessor's public review. The tracked configuration template keeps `expected_head: null`. Supply the exact full SHA that independently passed audit and freeze through `--new-expected-head`. A command does not trust a checkout HEAD merely because it is current. Before that audit and freeze, this mechanism has no operational authority. Supersession itself performs no OAuth or provider action and does not grant LIVE-GO; a fresh offline preflight and separate live permission remain required.

## Exact future live operator sequence (NOT YET EXECUTED)

Only after the supersession mechanism has been independently audited and frozen, a fresh successor's offline preflight has passed, and explicit real OAuth/setup permission has been given. These commands are prepared instructions, not execution authority. Do not issue LIVE_READ_GO until actual post-setup PASS.

1. Obtain the audited full Phase 4 commit from the freeze review. Checkout it under that later permission, verify clean tree. Run regression before the live session. No dependency download/update during session.
2. Establish independently clock <=2s, dedicated reviewed app/project/account, API enabled/consent configured, no existing unrelated data/default-domain sharing/automation/writers, local trusted disk and capture controls. Cloud/API configuration is a separately authorized human setup prerequisite, not a hidden API call in this tool.
3. For a new operational package, prepare an explicit downloaded installed-client outside repo, 0600, no links; never paste secrets in the shell. Choose its absolute path below. Verify parent permissions and no backup/indexing of secret input. Create storage exactly once under later setup authorization. The existing offline package is retained; use the audited `supersede-prelive` mechanism and the returned successor path. The following block records original first-package bootstrap semantics and must not be rerun against the retained package or a successor. Existing root means inspect/review, never reset.

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

9. In the same resident prompt execute exactly one future first-read command with literal paths. The example below uses the original root only; after pre-live supersession, replace **every** occurrence of that root with the returned successor path. The resident parser does not expand `$P4`:

```text
read --execute-live-read --token-input resident-memory --fixture "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/fixture.json" --metadata "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/acquisition.json" --authorization "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/authorization.json" --receipt "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/phase3-receipt.json" --operational-receipt "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/phase4-receipt.json" --pin "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/read-pin.json" --configuration "/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-first-read/operator.json"
```

The qualified Phase 4 dispatcher rejects path substitution, prior read-intent, mismatched receipt/config/startup/runtime and insufficient lifetime. It calls frozen Phase 3 execute_read once; frozen Phase 2 reserves attempt, consumes claim before worker, observes same-socket verifying TLS durably before one exact GET, and enforces one monotonic deadline. No OAuth/refetch, refresh, retry, fallback, redirect, POST or mutation exists in this qualified read path. Setup POST remains an explicitly separate prior action. Session ends after read regardless of result. This workflow claim does not constrain direct trusted-code calls to lower-level APIs.

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

For OAuth failure: preserve oauth-intent; no read authorization exists or is consumed. For local review/reservation/issuance failure: partial artifacts stay unusable, no repairs or overwrites. For read failure/death/storage drift: read intent and/or claim remain spent/unusable; inspect inherited recovery without assuming absence of result means absence of GET. No automatic retry, token refresh, second authorization or remote cleanup. A later real attempt needs incident review and a new explicit authorization under a separately reviewed plan.

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

Latest corrective Phase 4 regression qualification (real network/browser disabled; the runner prints its exact `pytest.main([...])` invocation, returned `QUALIFICATION_EXIT_CODE`, and `QUALIFICATION_RUNNER_EXIT_CODE`; launch failure is explicit):

| Suite | Pass count |
| --- | ---: |
| Phase4 focused, warnings as errors | 277 |
| All Sheets, normal | 1187 |
| All Sheets, warnings as errors | 1187 |
| All Study2, warnings as errors | 1631 |
| Forbidden parent network/browser calls | 0 in each run |
| git diff --check and added-file whitespace checks | PASS |

The final direct Study 2 qualification at the compatibility correction reported `1631 passed`, `QUALIFICATION_EXIT_CODE: 0`, `QUALIFICATION_RUNNER_EXIT_CODE: 0`, and zero forbidden parent network/browser calls. Warnings-as-errors also applies to inherited spawned helpers. Concrete operational preflight passed at clean corrective commit `6525ddbe3e2eadb2dc55d301914e75ed41f8dfe6`; the docs-only freeze at `055c2ce30f350899f6babbd84770d6532ef1d6d5` made that package's pins stale. No new operational preflight PASS is claimed until a fresh successor completes the offline sequence.

## Checklist impact and remaining live validation

Only additive `phase4_update` metadata is added to the evolving checklist. All inherited metadata and28 items/status/evidence remain unchanged: **16 PASS OFFLINE, 7 BLOCKED, 5 REQUIRES LIVE VALIDATION**. New operator commands do not promote live-dependent items.

Remaining BLOCKED: credential_acquisition_and_budget (real acquisition/setup approval), real_tls_connector_authorization (actual trust/peer/route and later mutation boundary), actual_fixture_and_reservation (real creation/provenance/reservation), separate_live_authorization (fresh clean committed pin after this correction/genuine human GO), crash_recovery (real storage/power-loss/live incidents), visibility_bounds (no schedule), paper_protocol (no protocol/data authorization).

Remaining REQUIRES LIVE VALIDATION: actual_grid_response_shapes, baseline_isolation, clean_success_placement, live_ambiguity_boundary, actual_tls_trust_phase1. First GET can inform only read/TLS/current-baseline subconditions. Mutation work waits for independent read-result review and freeze. Study2 still includes Stripe TEST MODE.

The passed hostile audit retains these operational limits and live-only risks: trusted stable session instead of atomic child trust binding; the same transient bearer across distinctly approved setup/read and anonymous spawn IPC; strict real OAuth/create/read framing, including optional token-field rejection; operator account/client/control/clock attestation rather than remote introspection; unresolved creation requiring a separate incident plan; shared coarse diagnostic categories; selected rather than exhaustive native/runtime pinning; transient application handoff versus OS capture/swap limits; bounded setup operations without hard overall setup watchdog; fixed persistent root retention and no reset/copy escape under trusted operator model. Real provider OAuth behavior, create/read framing and empty-grid shape remain unvalidated. The independent Phase 3 clean-room re-audit passed; its known limitations remain. No mutation or ambiguity injection has begun. Supersession alone grants no live setup/read permission.

**PRE-LIVE SUPERSESSION REQUIRES AN INDEPENDENTLY AUDITED FROZEN CHECKOUT — LIVE-GO CLOSED — ZERO SHEETS PAPER OBSERVATIONS**

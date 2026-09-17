DRAFT — ENGINEERING VALIDATION ONLY — NOT PAPER DATA

Study 2 Phases 2B–2C, 2026-09-17. Engineering implementation only; no protocol,
runner, live ambiguity injection, Replay/Regeneration, LLM calls, paper observations,
statistical analysis, or freeze. Study 1 is closed. ZERO Study 2 paper observations.
Phase 2A semantics (`58fd400`) and contracts are unchanged.

### Phase 2C local lifecycle and deterministic offline faults

**DRAFT — ENGINEERING VALIDATION ONLY — NOT PAPER DATA.** This phase adds
client-process evidence and offline engineering faults, not an ambiguity protocol.
Baseline HEAD inspected before edits: `8308fa84860929e7a9f16529ee00e7d310fa792f`.
The visibility validation files are part of that adapter commit, not a separate
visibility milestone commit. No commit is made in Phase 2C.

Each instrumented `HTTPAttempt` contains an immutable tuple of frozen
`LifecycleEvent` values. Sequence numbers start at one per attempt and provide
ordering; no clock is needed. Events belong to that attempt's existing prepared
request (method, URL/path, ordered nonsecret headers, exact body bytes/body hex).
No fingerprint, socket/TLS buffers, Authorization values, exception text, or
arbitrary metadata is recorded. The only event metadata is a typed fault point.

| Stage | Local evidence | Limits |
| --- | --- | --- |
| `REQUEST_PREPARED` | Adapter has prepared the inspectable request, before connection construction. | No connection or transmission evidence; authentication is excluded. |
| `CONNECT_STARTED` | About to invoke explicit `connect()`. | Does not prove connection establishment or any request send. |
| `CONNECT_COMPLETED` | `connect()` returned normally. | No HTTP request transmission or provider mutation evidence. |
| `REQUEST_SEND_STARTED` | About to invoke `endheaders(body or None, encode_chunked=False)`. | No assertion that any byte was sent or that the complete request was sent. |
| `LOCAL_REQUEST_SEND_COMPLETED` | That `endheaders` operation returned without reporting a local send failure. | **Does not prove provider receipt, execution, mutation commitment, or guaranteed network delivery.** |
| `RESPONSE_WAIT_STARTED` | About to invoke `getresponse()`. | No HTTP response yet observed. |
| `RESPONSE_HEADERS_RECEIVED` | `getresponse()` returned an HTTP response after header processing. | Does not prove complete body receipt or mutation success/commitment. |
| `RESPONSE_BODY_COMPLETED` | `response.read()` returned normally, including an empty body if applicable. | Complete local body read under `http.client` semantics; status/content still need adapter validation. Not universal provider-state evidence. |
| `TRANSPORT_ERROR` | Local operation failed; safe fixed category on the attempt. | Does not establish provider state or how many bytes were transmitted. |
| `INJECTED_FAULT` | A chosen deterministic engineering boundary stopped the attempt. | An engineering intervention, not provider behavior. No later response events. |

The installed Python implementation was inspected: `putrequest`/`putheader`
buffer request-line/header values locally. After explicit connection establishment,
the transport buffers those values, including authentication privately, and then
calls `endheaders`. Its `_send_output` sends buffered headers and then the bytes
body through `send`/socket `sendall`. The send-start/completion events surround
the **whole `endheaders` call**, not each socket write. Local send completion
is not a raw wire-byte delivery guarantee. There is no added remote assertion.

`OfflineFaultTransport` requires an explicit trusted fake connection factory
and an `EngineeringFaultPoint`; it has no live/default factory. The normal
`https_single_attempt` transport and live smoke have no fault-setting parameter.
Caller-supplied factories are trusted test code, not certified against networking
or hidden internal retries. Do not supply a real connection factory for this phase.

* `BEFORE_REQUEST_SEND`: after explicit connect and local header buffering, before
  `REQUEST_SEND_STARTED`/`endheaders`. Records one terminal fault, zero HTTP POST
  transmissions, no response wait, and closes the local connection.
* `AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE`: only after `endheaders` returned
  normally and local completion was recorded, before response wait/`getresponse`.
  Records one terminal fault, exactly one HTTP POST transmission in the offline
  fake, no HTTP response observed, and closes the local connection. **Connection
  closure implies nothing about provider receipt, execution, or commitment.**

An error during `endheaders` yields send-start without send-completed. This is
uncertain local partial-send evidence; neither definitely undispatched nor fully
sent is inferred. Tests include successful header transmission followed by a
partial body write and failure. A connect error retains connect-start without
connect-completed. Header/body response failures retain available status evidence;
body-completed is absent if the read fails. Cleanup is attempted once in `finally`;
a cleanup exception is suppressed to preserve the original boundary outcome.

Mutation control flow still invokes transport once with no retry/redirect loop;
`auto_open=0`, one explicit connect, one `endheaders`, and no second connection.
Faults stop before response processing. HTTP 429/500/redirect responses are read
once and then rejected by existing status handling. Attempt count denotes boundary
invocations, including before-send faults, not POST transmissions. GET uses the
same lifecycle with fresh per-page numbering; observation remains one exhaustive
traversal, including canonical-path binding, PR exclusion, and deduplication.
Visibility helper semantics and polling are unchanged.

Validation requires the exact normal ordered prefix, contiguous sequence numbers,
and no duplicate/skipped normal stages. Failure prefixes are accepted. Terminal
errors/faults must end the history and have a matching failure outcome. Fault
points require their exact boundary prefix. A response outcome requires all eight
normal stages; status presence must agree with header receipt. A successful or
complete operation trace cannot contain a failed attempt. Historical/opaque
transports retain an empty lifecycle (explicitly unavailable granular evidence);
their former transport-boundary flags do not imply local send completion.
Historical JSON artifacts require no migration and are not rewritten.

Cross-field remediation: nonempty lifecycle requires both `dispatch_started`
and `dispatch_ended` to be `True`. These legacy adapter transport-boundary flags
mean the invocation was entered and returned/failed sufficiently to finalize its
record; they do not establish request transmission, remote receipt, or mutation
execution. Without header receipt, status must be absent and response metadata
empty. Header receipt requires status but no particular metadata; sanitized
metadata/status may survive a later body-read failure. Empty-lifecycle attempts
retain compatibility. At operation level, `complete` is true exactly when outcome
is `success`; intermediate post-HTTP-response traces remain incomplete with their
existing non-success outcome until higher-level validation succeeds.
Finalized successful operations necessarily contain HTTP-attempt evidence.
Remediation validation: **391 focused tests passed in 0.23 seconds** and the
same complete credential-cleared/socket-disabled offline suite passed **1215
tests in 74.29 seconds**. All 29 prior lifecycle tests remain unchanged; 24
cross-field tests were added. Both live artifacts retained their SHA-256 hashes,
and their three embedded historical traces constructed without migration.

Error categories use fixed strings, including `injected_fault`; unknown injected
transport read-error strings are normalized to `transport_error`. Exceptions are
raised outside credential-bearing exception handlers. Response metadata retains
the existing allowlist and token redaction. No Authorization material is serialized.

**No live fault injection or GitHub request occurs in Phase 2C.** No additional
issue is created or modified. Existing ignored live artifacts remain historical
engineering evidence. ZERO Study 2 paper observations exist. No Replay,
Regeneration, LLM, trial/scenario/manifest, paper protocol, or analysis is added;
Study 1 artifacts and closed experiments remain untouched. Next: hostile audit.

Phase 2C offline validation: focused contracts, semantics, adapter, visibility,
smoke-gating, and lifecycle tests passed **367 tests in 0.27 seconds**, with
credentials cleared and sockets disabled. The complete credential-cleared/
socket-disabled command recorded below and in `GITHUB_SEMANTICS_DRAFT.md` was
run verbatim: **1191 passed in 79.19 seconds**. The new lifecycle file adds
29 deterministic tests. `git diff --check` passed; nothing is staged. Both
historical ignored live artifacts matched their pre-edit SHA-256 hashes.

### Transport and HTTP attempt boundary

`github_adapter.py` uses Python standard-library `http.client.HTTPSConnection`.
No dependency or lockfile changes. Existing HTTPX 0.28.1 was inspected: its
httpcore pool can reassign a connection through an internal
`ConnectionNotAvailable` loop. A fresh standard-library connection is narrower
for this two-endpoint adapter. The installed Python implementation of connect,
send, endheaders, and response read was inspected alongside the
[official HTTP client documentation](https://docs.python.org/3.11/library/http.client.html).

Each default transport invocation constructs one HTTPS connection, disables debug
output and `auto_open`, explicitly connects once, sends one HTTP/1.1 request,
reads one response, and closes. No pool, SDK, authentication challenge handling,
proxy tunneling, redirect following, or retry facility is used. Disabling
`auto_open` prevents implicit reconnect between header and body sends. Socket
send failures, timeouts, connection failures and any HTTP status propagate as the
first result; 429, 5xx and 3xx cause no redispatch. Observation also never retries.
DNS/address selection can involve multiple TCP connection candidates; those are
not additional HTTP POST dispatches. TCP retransmission is not an application retry.

One logical `create_issue` invocation makes zero dispatches on invalid local input
or exactly one transport invocation otherwise. There is no loop around POST.
Trace attempt count means entries into this transport boundary, including a failed
connect where no HTTP bytes reached GitHub. It is not a provider-side receipt or
commit count. Default-transport wire tests check one connection/connect, one POST
request line, exact body bytes and all supplied nonsecret headers. Failure tests
exercise connect, header/body send, getresponse, and body read. Injected transports
are trusted offline test code; arbitrary replacement transports are not certified
against internal retries by this adapter.

Configuration is immutable: externally supplied HTTPS API base (no trailing slash,
query or credentials), owner, repository, token, explicit date-form API version,
and positive finite socket timeout (engineering default 30 seconds). No GitHub
account/repository/base/version target is assumed. TLS certificate and hostname
verification use Python defaults. Environment proxy variables are not consulted.
System trust, OpenSSL certificate environment, DNS, TLS interception, audit hooks
or process instrumentation remain host dependencies. No application can establish
that a remote proxy/provider does not internally repeat work from a local trace.
The socket timeout covers blocking socket operations; it is neither an end-to-end
operation deadline nor a reliable bound on DNS. No timeout experiment is performed.

### Request and response representation

`prepare_create_issue(title=..., body=...)` exposes the intended nonsecret request
before dispatch. Payload has only title/body; compact insertion-ordered JSON uses
`ensure_ascii=False`, no NaN, UTF-8 bytes. Evidence identity is method, absolute
URL, exact target path/query, ordered nonsecret headers and those actual body
bytes, not Study 1 canonical JSON. `Content-Length` is the byte length, not the
character length. The transport hands those bytes unchanged to `endheaders`;
no chunked request encoding or automatic Host/Accept-Encoding headers are used.
Only Authorization is added separately at dispatch.

Requests use explicit `application/vnd.github.raw+json`, API version, user agent,
`Accept-Encoding: identity`, and `Connection: close`. `http.client` removes HTTP
transfer framing; it does not decompress entity content. Unexpected content
encoding is rejected, rather than silently transforming the evidence. Success
requires JSON media type, UTF-8 JSON, no duplicate object keys/non-JSON constants,
and validated issue number/title/body/state. Body must be present, string or null;
number is positive integer (not bool); state is open/closed. Create must be 201
and return an issue object without `pull_request`; list must be 200 with an array.
A returned selected-version header must match the requested version; its absence
is permitted and does not prove provider compliance. Version semantics and raw
representation are supported by the [GitHub issues documentation](https://docs.github.com/en/rest/issues/issues)
and [API version documentation](https://docs.github.com/en/rest/about-the-rest-api/api-versions).

Fixed error categories distinguish transport timeout/connection/other failure,
non-success HTTP, malformed success, unsafe/malformed pagination, and page loops.
Exceptions carry a failure trace, never raw provider JSON or exception text.
A response-body read failure retains received status and safe response metadata
but is a transport failure, not an empty page. A malformed entry fails traversal;
there is no partial successful result or conversion to zero matches.

### Observation, pagination and identity

One traversal starts at page 1 with `state=all&per_page=100`. Every page uses the
same representation and request headers; every array entry is validated before
interpretation. Presence of `pull_request`, including null/empty/false, excludes
that entry. Closed issues remain. Issue identity comes only from LIST:
`((configured owner, configured repository), list-returned number)`. No create
response is accepted by observation. Repeated identities count once; the first
appearance's content/state is retained. Distinct numbers remain distinct even
with identical title/body. Matching is a caller predicate on the completed result;
it never short-circuits enumeration or freezes a paper marker syntax.

The conservative Link parser follows each next relation to exhaustion, accepts
quoted parameters/commas and relation token lists, and fails on malformed or
ambiguous headers (including duplicate Link fields/next relations or anchor
context overrides). Next URLs must be absolute HTTPS with exactly the configured
origin/port and API prefix. GitHub's [official pagination example](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api#using-link-headers)
starts with `/repos/{owner}/{repo}/issues` but returns Links using
`/repositories/{numeric_id}/issues`. The adapter accepts the configured collection
path or that canonical form with a positive decimal repository ID under the same
API prefix (including `/api/v3` when configured).

The first canonical target is trusted as provider-issued pagination state from
the successful response to the configured repository endpoint or its accepted
original-path pagination pages. Its exact path/repository ID is then bound for
the remainder of that traversal. Later switching to another numeric ID, the
original path, another repository, prefix, or arbitrary endpoint fails before
dispatch. Binding is local to each traversal. No independent repository-ID lookup
is performed, and the numeric ID is not claimed to be derived from configuration;
LIST resource identities still use the configured owner/repository scope. This
trust boundary is analogous to accepting a constrained provider-issued next-page
token; it does not prove repository-ID correspondence or snapshot consistency.

Credentials, fragments, whitespace, disallowed path changes, narrowing filters, duplicate query
keys, changed state/page size and invalid page numbers are rejected before
sending credentials. Exactly `state=all`, `per_page=100`, and a positive `page`
are required on both path forms; omitted or rewritten filters are not accepted.
Semantically
repeated page numbers detect cycles even with reordered query parameters. There
is no page cap; a 120-page offline test checks traversal beyond small limits.
Strict validation may reject otherwise valid provider Link variants; this fails
incomplete rather than silently truncating. [GitHub pagination documentation](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)
provides the provider Link behavior; stricter safety rules are our engineering choices.

### Engineering trace and gated smoke

Immutable traces record logical operation, per-attempt index/request,
dispatch-started/ended states, HTTP status, fixed outcome, and allowlisted
request-ID/rate-limit/retry-after/version/media/encoding/warning metadata.
Dispatch flags describe entry/exit, not delivery of bytes or timestamps. Observation
also records attempts, successfully received 200 pages, inspected raw entries,
excluded PRs, repeated issue identities, distinct issues and completeness. Failure
counts describe progress before rejection, never an observation census.

Authorization is absent from evidence. Token repr is suppressed; token occurrences
in controlled/request content are rejected and echoes in allowlisted response
headers are redacted. Raw response bodies, URLs from rejected Link headers,
Location, cookies, provider error messages and transport exception objects are
not retained in traces. Successful normalized content containing the token is
rejected. Trace serialization explicitly uses lossless `body_hex`; config objects
must not be serialized (they necessarily hold runtime authentication).

Separate command, never ordinary pytest execution:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_study2_github.py
```

Requires `STUDY2_GITHUB_LIVE_ENGINEERING=1` and all of
`STUDY2_GITHUB_TOKEN`, `STUDY2_GITHUB_OWNER`, `STUDY2_GITHUB_REPO`,
`STUDY2_GITHUB_API_BASE_URL`, `STUDY2_GITHUB_API_VERSION`. No dotenv loading.
Both the command and direct smoke helper enforce the gate; helper configuration
must match those environment values. Missing/invalid configuration refuses before
network access. The configured target is the only target; select a disposable
engineering repository deliberately.

Smoke generates a unique ENGINEERING-ONLY UUID marker in title/body, performs one
creation, discards its returned resource, and performs one exhaustive observation.
It matches pre-dispatch content, checks exact observed title/raw-body preservation
and exactly one matching distinct resource. No retries, polling, artificial losses,
intentional duplicates, or cleanup. Failures produce sanitized engineering traces
when available. Output directory is checked/created before dispatch. Artifacts
include timestamp, target, marker, expected content, traces, content/count checks,
and safe warning/error information; every artifact declares
`ENGINEERING VALIDATION — NOT PAPER DATA`. Output is gitignored under
`research/study2/engineering/github/live/`; no output is staged automatically.
The remotely created issue remains for manual review. A local disk/process failure
after dispatch can still prevent artifact publication; no durable execution journal
or crash recovery is claimed.

### First live engineering finding and unchanged historical evidence

The first and only live engineering mutation is recorded in
[`github-engineering-ENGINEERING-ONLY-e6374180720e4da1a538550342cd8b82.json`](../engineering/github/live/github-engineering-ENGINEERING-ONLY-e6374180720e4da1a538550342cd8b82.json),
timestamped 2026-09-17T10:41:31.135132+00:00. That historical artifact remains
unchanged. It records one POST transport attempt, HTTP 201, and successful create
response. The immediate complete LIST traversal returned HTTP 200, one page,
zero raw entries and zero distinct issues. Both controlled-content preservation
and exactly-one-matching-resource checks correctly failed. No second mutation
was performed.

The user reported a later GET-only re-observation using the same adapter: complete
traversal, one GET attempt, one page, one raw entry, one distinct issue and one
marker match with identity
`(('JashRashne', 'retry-semantics-study2-github-sandbox'), 1)`. Its observed title was
`Engineering content round-trip ENGINEERING-ONLY-e6374180720e4da1a538550342cd8b82`.
The exact expected raw body was also reported preserved, including UTF-8 café/🚀,
Markdown, quote, backslash and newlines. Rediscovery used the pre-dispatch marker
and expected title/body; the create-response issue number was unnecessary.
This remediation did not repeat that live GET or generate a replacement artifact.

This is one engineering observation of visibility changing across two traversals:
the issue was absent from the immediate traversal and visible to the later one.
It does not establish a general GitHub consistency or visibility guarantee, nor
an established provider eventual-consistency mechanism. POST 201 does not imply
immediate LIST visibility. Later visibility does not retroactively change the
first observation from zero to one; each traversal retains its own evidence.
Everything here is ENGINEERING VALIDATION — NOT PAPER DATA.

### Separate bounded GET-only engineering visibility helper

`github_engineering_visibility.py` adds `probe_engineering_visibility`, above the
adapter. It receives only a no-argument observation callable (normally the bound
`adapter.observe_issues` method), the already-known pre-dispatch engineering
marker/title/body, and a successful single-attempt POST-201 mutation trace.
It receives no credential or client mutation capability, never calls creation,
and is not invoked by the original smoke, any runner, or paper execution.
The supplied callable is trusted code and must perform one complete adapter
observation; arbitrary replacement callables are not certified against side effects.

The immutable engineering-only result retains the mutation trace unchanged and
one separately indexed record per new traversal: its own trace, elapsed start/end
times relative to probe start, whether marker-controlled content was observed,
whether expected title/body were exactly preserved, and matching distinct scoped
identities. Probe indices start at 1 and do not renumber historical smoke evidence.
Traces from multiple traversals are never merged; several GET pages within one
complete traversal still produce one traversal record. Result classification is
fixed to ENGINEERING VALIDATION — NOT PAPER DATA. No final evidence schema is defined.

The first traversal begins immediately. Exactly one matching distinct resource
with exact expected title/body stops successfully. Otherwise the explicit
`max_traversals` count stops the check; defaults are 3 traversals and a 1-second
`interval_seconds` between successful nonconverged traversals. These are configurable
engineering-validation conveniences, not a Study 2 polling schedule. There is no
sleep after success, failure or count exhaustion; an explicit zero interval is
allowed. Failed/incomplete traversal stops immediately, keeps its failure/partial
trace, and records unknown (`None`) matching/content fields rather than zero or
false. Count exhaustion does not classify mutation commitment. The count bound
does not impose a total wall-clock deadline on individual paginated traversals.
Unexpected callable/programming failures propagate rather than becoming empty reads.

Historical artifacts are not rewritten or automatically serialized by this helper.
It returns an immutable engineering representation; no generated live artifact is
added to git. Any later follow-up must reference the existing marker, preserve the
historical zero-entry traversal separately, and remain GET-only. No additional
issue or live follow-up was created/executed by this remediation.

### Unvalidated and unresolved boundaries

The first live validation supports only the particular content/visibility finding
above. General content preservation, permissions, all-page reachability, version
enforcement, transport behavior under failures, visibility timing, and repository
automation remain unvalidated. No live follow-up or mutation smoke was executed
in this remediation. Visibility/convergence semantics remain unresolved for the
Study 2 protocol: later experimental design must explicitly define when and how
post-ambiguity state is observed. No hidden polling, sleeps, convergence logic or
repeated traversals may be introduced underneath an experimental observation.

Traversal is complete only for reachable returned pages, not a transactional
snapshot or guarantee against page movement, missed resources, deletion/transfer,
permission-dependent visibility or provider omission. Deduplication cannot recover
missed issues; first-appearance retention does not resolve changing content/state.
Memory grows with response size/resource count; there is no arbitrary truncation.
Rate-limit interference, secondary limits, provider-side work/content transformation,
notifications and repository automation remain threats. UUID uniqueness limits
stale engineering-marker matches but cannot prove isolation or prevent copied
markers; all matches are counted. Host/proxy/provider retransmission cannot be
excluded with local traces alone. No idempotency guarantee is inferred.

Later phases still need ambiguity/ACK-loss instrumentation, real retry identity,
marker/correlation/isolation design, preservation under future generated changes,
visibility/convergence guarantees and assessment of concurrent pagination. Nothing
here selects a scenario, arm, replicate, schedule, manifest, stopping rule, evidence
schema, analysis or final Study 2 protocol.

### Offline validation record

Prior focused command after canonical-pagination remediation:

```bash
.venv/bin/python -m pytest -q tests/test_study2_contracts.py tests/test_study2_github_semantics.py tests/test_study2_github_adapter.py tests/test_study2_github_smoke.py
```

Result: **309 passed**, including **43 added canonical-pagination regression tests**.
The complete credential-cleared/socket-disabled command recorded in
`GITHUB_SEMANTICS_DRAFT.md` was executed verbatim against final code:
**1133 passed in 69.38 seconds**.
`git diff --check` and separate checks of untracked additions passed. No Study 1
experiment was rerun; full-suite regression tests use synthetic/offline fixtures.
That earlier code-validation pass did not run live smoke or produce paper data.
The separate first live artifact and later user-reported GET finding are described
above; the historical artifact remains unchanged.

Engineering visibility remediation validation:

```bash
.venv/bin/python -m pytest -q tests/test_study2_contracts.py tests/test_study2_github_semantics.py tests/test_study2_github_adapter.py tests/test_study2_github_smoke.py tests/test_study2_github_engineering_visibility.py
```

Result: **338 passed**, including **29 new deterministic visibility-helper tests**.
The same credential-cleared/socket-disabled complete offline command passed:
**1162 passed in 67.79 seconds**. `git diff --check` and separate checks of untracked
additions passed. The historical failed artifact was verified unchanged by SHA-256.
No live follow-up, additional issue, or mutation-smoke rerun occurred. ZERO Study 2
paper observations exist; no Study 1 artifact changed or experiment was rerun.

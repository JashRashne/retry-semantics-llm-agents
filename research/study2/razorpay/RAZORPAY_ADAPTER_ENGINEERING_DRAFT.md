# Razorpay Order adapter engineering draft

**DRAFT / NOT FROZEN**

**OFFLINE ADAPTER ENGINEERING ONLY**

**NO RAZORPAY PROVIDER CALL PERFORMED**

**NO REAL CREDENTIAL ACCESSED**

**PROVIDER C REMAINS TBD**

**STUDY 2 PAPER OBSERVATIONS = 0**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent
Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## 1. Authority and scope

This artifact documents a synthetic/offline adapter for a Razorpay candidate.
It does not select Razorpay as Provider C, implement a live engineering
qualification gate, execute Replay or Regeneration policy, or create a Study 2
paper observation. All tests use synthetic credentials and an injected in-memory
HTTP transport. This slice authorizes no Razorpay API, Dashboard, account,
credential, Order, payment, Checkout, or other provider access.

The frozen source reconnaissance is
`research/study2/razorpay/RAZORPAY_SEMANTICS_RECONNAISSANCE.md`, SHA-256:

```text
b4acf4dc8a7bdfe150fbe6abe812c3508c18ff27566f219a651bd2e1377cd4ac
```

The reconnaissance remains frozen and unchanged.

## 2. Scientific boundary

The implementation preserves these distinct events:

```text
request construction
!= dispatch initiated
!= local transport completion
!= provider receipt
!= provider commit
!= acknowledgement returned
!= authoritative later observation
```

A local validation rejection before a dispatch permit is consumed is
`PRE_DISPATCH_REJECTED`. Once dispatch begins, timeout, disconnect, any HTTP
4xx/5xx, malformed JSON, or invalid acknowledgement is
`UNKNOWN_AFTER_DISPATCH`. None of those results means `NOT_EXECUTED`.

Only a conservatively validated Create response is `ACKNOWLEDGED_CREATE`.
That classification is acknowledgement evidence; it does not establish a
general provider-commit or observation-completeness theorem.

## 3. Mutation candidate and deterministic payload

The frozen candidate request is:

```http
POST https://api.razorpay.com/v1/orders
Content-Type: application/json
```

Its exact canonical JSON body is:

```json
{"amount":200,"currency":"INR","notes":{"retry_semantics_marker":"<synthetic marker>"}}
```

The body is encoded once with the repository's canonical JSON serializer:
recursively sorted keys, compact separators, UTF-8, and no trailing newline.
The immutable request stores the exact bytes. Request identity serializes those
bytes as Base64 and hashes the canonical identity, so exact Replay identity does
not rely on Python dictionary equality.

The payload fixes `amount` to 200 paise and `currency` to `INR`. It contains
exactly one notes entry with key `retry_semantics_marker`. `receipt` is omitted.
`partial_payment`, `first_payment_min_amount`, customer, transfer, offer,
Checkout, and payment-attempt fields are absent.

Markers are constrained to the ASCII shape
`study2_[A-Za-z0-9_-]{1,56}`. This deliberately rejects whitespace, Unicode,
control characters, slashes, backslashes, URL-like values, email-like values,
and unconstrained free text. Markers are synthetic opaque identifiers and must
contain no PII.

## 4. Frozen request identity

The identity includes:

- provider candidate `razorpay`;
- operation `create_order`;
- method `POST`;
- origin `https://api.razorpay.com`;
- path `/v1/orders`;
- Content-Type;
- exact body bytes;
- marker, amount, and currency;
- one-way credential-scope fingerprint;
- finite timeout; and
- transport profile: zero retries, no redirects, and no environment trust.

Sanitized evidence contains only the identity digest and body digest, not an
Authorization value or credential material.

## 5. Credentials, authentication, and redaction

`RazorpayCredentials` contains a Key ID and Key Secret for the transport
boundary. It rejects empty values. Its `repr` and `str` expose neither raw
value. The evidence scope is a SHA-256 fingerprint over domain-separated
credential material; the raw values are not serialized.

No key prefix is interpreted. In particular, an `rzp_test_*`-looking string
would not establish Test Mode. Operational Test/Live validation belongs to the
later live qualification gate.

At dispatch, authentication is exactly:

```text
Authorization: Basic base64(Key ID:Key Secret)
```

Authorization exists only on the outbound `httpx` request. The frozen request,
result objects, sanitized evidence, response metadata, and adapter-generated
failure reasons omit it. Raw transport exception text is discarded because an
exception can retain an outbound request containing Authorization.

## 6. HTTP transport and retry policy

The default client pins these behaviors explicitly:

- `httpx.HTTPTransport(retries=0)`;
- `follow_redirects=False`;
- `trust_env=False`; and
- a finite positive `httpx.Timeout`.

Its frozen identity profile is exactly
`httpx_httptransport_retries0_no_redirects_no_trust_env_v1`. An injected
transport must instead provide an explicit, nonempty immutable profile label;
the default profile label is reserved and cannot be assigned to an injected
transport. The selected profile is stored on every frozen request, checked
again by the dispatching adapter, and participates in request identity.

The adapter never reads proxy or credential environment variables. Tests inject
`httpx.MockTransport`. No mutation or observation retry is implemented. Each
mutation permit authorizes at most one transport invocation; each observer page
offset causes at most one invocation.

## 7. Dispatch permit semantics

A `DispatchPermit` is process-local and one-shot. The adapter first validates
the frozen request, its scope, and the permit type, then locally constructs
Authorization and the outbound `httpx.Request`. A construction failure is
`PRE_DISPATCH_REJECTED`, discards raw exception text, performs no send, and
leaves the permit unconsumed. The permit is atomically consumed immediately
before `Client.send`; two concurrent callers sharing one permit can therefore
cause at most one transport invocation. Transport exceptions,
HTTP failures, parse failures, and acknowledgement failures never refund it.

The permit is separate from the immutable frozen request. A future exact-Replay
executor could issue a new, separately authorized permit for the same frozen
request bytes. This adapter demonstrates that separation synthetically but does
not implement or choose Replay policy.

## 8. Mutation result and acknowledgement validation

Mutation results record:

- whether dispatch started;
- whether a local HTTP response completed;
- whether acknowledgement validation passed;
- HTTP status when available;
- fixed, derived response metadata only;
- provider Order ID only for a valid acknowledgement;
- request identity/body digests;
- credential-scope fingerprint; and
- `PRE_DISPATCH_REJECTED`, `ACKNOWLEDGED_CREATE`, or
  `UNKNOWN_AFTER_DISPATCH`.

An acknowledgement is valid only when all of these hold:

- HTTP status is exactly 200;
- body is a JSON object;
- `entity == "order"`;
- `id` is a non-empty string, without inventing a regex;
- `amount == 200` using an integer, not a boolean;
- `currency == "INR"`;
- `status == "created"`;
- `attempts == 0`;
- `amount_paid == 0`;
- notes is an object containing the exact marker key/value; and
- receipt is absent or null.

Any failure after dispatch is `UNKNOWN_AFTER_DISPATCH`; the implementation
never turns “request/response failed” into “no Order exists.”

## 9. Observer request and candidate traversal

The observer uses:

```http
GET https://api.razorpay.com/v1/orders?count=100&skip=<offset>&from=<from>&to=<to>
```

Inputs require the exact marker, explicit non-negative integer `from` and `to`
with `from <= to`, credential scope, and a finite positive page cap. Query
construction is stable. No receipt, notes, status, or ordering filter is used.
Timestamps scope the scan only; they do not identify a resource, imply ordering,
or assume inclusive/exclusive boundaries.

Offsets are `0, 100, 200, ...`. A page shorter than 100 is a candidate
**structural** termination signal. A full page always causes another request,
so exactly 100 or 200 returned records requires an additional request. Reaching
the page cap produces `incomplete`, never an infinite scan.

## 10. Page validation and marker evaluation

Each page must have HTTP 200, a JSON object, `entity == "collection"`, and an
`items` list no longer than the requested page size. Response `count` is not
used as a total. Every item must be an Order object with a usable non-empty ID.

Notes handling is fail-closed before live qualification:

- a missing notes field is malformed (`missing_notes_field`), because omission
  is not yet qualified as equivalent to absence of the marker;
- null, `[]`, non-empty lists, strings, numbers, and every other non-object
  notes value are malformed;
- `{}` is a safe nonmatch because the marker key is explicitly absent;
- an absent marker key in a notes object is a safe nonmatch;
- a present marker value must be a string; and
- comparison is exact, case-sensitive, and performs no Unicode normalization.

Malformed JSON, collection shape, Order shape, notes, or marker values yields
`malformed` with no completed count claim. An exception, timeout, or disconnect
before an HTTP response is `transport_failed`. A completed non-200 HTTP response
is instead `incomplete` with `unexpected_http_status` and retains its status in
sanitized evidence. Thus transport failure, completed HTTP error response,
malformed response, and structurally completed traversal remain distinct.

## 11. Structural completion is not authoritative completeness

The current result state is deliberately named
`structurally_completed_unqualified`. Every result carries:

```text
authoritative_completeness_qualified = false
```

The short-page traversal is an offline candidate algorithm only. It does not
prove that Razorpay offset traversal is stable, snapshot-consistent, or
authoritatively exhaustive. Transport failure, malformed data, repeated IDs,
or page-cap exhaustion produces an incomplete result. An incomplete result uses
`None` for multiplicity counts, so partial absence cannot be misread as zero.

## 12. Distinct-resource multiplicity and instability

Distinct provider Order IDs define resources:

| Distinct matching IDs | Matching resources | Additional resources |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 0 |
| 2 | 2 | 1 |
| 3 | 3 | 2 |

If any Order ID appears again, including on a later page, it is not counted as a
new mutation. The traversal is marked incomplete with pagination instability.
This detects one instability pattern but cannot prove that unseen records were
not skipped.

## 13. Zero-match rule

A structurally completed unqualified traversal with zero matching IDs has the
explicit conclusion:

```text
ZERO_MATCHES_READ_NOT_H0_PROOF
```

It means only “zero matches observed in an unqualified read.” It does not mean
`NOT_EXECUTED`, H0, provider absence, or authoritative nonexistence.

## 14. Sanitized evidence

Deterministic evidence projections may contain provider candidate, request/body
or query digests, marker, credential-scope fingerprint, dispatch stage, HTTP
status, acknowledged Order ID, page offsets, distinct matching IDs, counts, and
fixed incomplete reasons. They exclude Key Secret, Key ID, Authorization,
Base64 Basic credentials, environment variables, raw response bodies, raw
response headers, exception text, and unrelated provider content.

## 15. Unresolved live qualification items

All of the following remain **UNRESOLVED** until a separately authorized,
prospectively reviewed, hostile-audited live **Test Mode engineering
qualification**:

1. receipt-less exact replay multiplicity;
2. acceptance semantics for the fixed 200-paise amount;
3. exact notes round-trip behavior;
4. read-after-write visibility and convergence timing;
5. `from`/`to` boundary behavior;
6. actual result ordering;
7. offset pagination stability, termination, and authoritative completeness;
8. sufficiency of account quiescence/isolation;
9. operational Test/Live credential guardrails;
10. endpoint error behavior under ambiguity; and
11. Order retention and account/window isolation.

Engineering qualification calls are allowed only after this offline adapter and
its qualification protocol are separately frozen and hostile-audited. Such
engineering observations are not paper observations. Replay versus Regeneration
paper policies must not be tested there unless a later separately reviewed
qualification protocol requires a synthetic ambiguity check solely for
instrumentation.

This draft does not authorize live qualification. Provider C remains TBD. No
Study 2 paper observation in GitHub, Google Sheets, Razorpay, or any other
external environment may occur until Provider C and the final cross-provider
protocol are frozen and hostile-audited.

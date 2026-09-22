# Stripe Offline Adapter Engineering Draft

**DRAFT / NOT FROZEN**
**ENGINEERING ONLY**
**ZERO PAPER OBSERVATIONS**
**NO STRIPE PROVIDER CALL WAS PERFORMED IN THIS SLICE**
**PROCESS-LOCAL one-shot protection is NOT crash-durable authorization**
**Live qualification remains separately gated**

## Implemented boundary

`src/retry_semantics/study2/stripe_adapter.py` implements only the fixed Stripe
Customer operations selected by the frozen reconnaissance:

- `POST /v1/customers` with one form field, a caller-supplied synthetic
  `.invalid` email marker;
- `GET /v1/customers` with that exact email and `limit=100`, followed through
  every `starting_after` page while `has_more=true`;
- explicit `Stripe-Version: 2026-08-26.dahlia` on both operations; and
- an optional, caller-supplied `Idempotency-Key` that is absent by default.

The mutation form body is encoded and frozen before dispatch. Its identity uses
the repository canonical JSON serializer and covers the operation, non-secret
test target scope, method, fixed origin/path/content type, exact body bytes,
API version, exact optional idempotency key, and transport runtime options. The
raw Authorization credential is excluded. Evidence exposes domain-separated
hashes for credential and idempotency-key identity, and preserves the exact body
bytes separately on the frozen request.

The adapter accepts only explicit `sk_test_...` or `rk_test_...` credentials.
It does not read environment variables, files, or keychains. Credential values
are repr-hidden and omitted from evidence and fixed error descriptions.

The owned `httpx.Client` disables redirects and environment inheritance, uses a
finite timeout, and constructs its default `HTTPTransport` with `retries=0`.
There is no adapter retry loop. Offline tests inject `httpx.MockTransport` and
install a socket trap.

Each prepared mutation owns a process-local one-shot guard. Dispatch is consumed
immediately before the HTTP boundary and stays consumed after every response or
transport exception. This prevents a second send through that Python object; it
does not survive process failure and is not an exactly-once authorization system.

A transport exception after dispatch initiation yields an immutable ambiguous
result: dispatch initiated, no acknowledgement available, and remote outcome
`unknown_ambiguous`. It causes no retry, replacement request, or observation.
The adapter does not invent evidence for local-send completion, remote receipt,
or remote commit.

An HTTP response remains an acknowledgement even for redirects, 429, and 5xx.
Only HTTP 200 with a valid Customer object, usable Customer ID, exact email, and
`livemode=false` becomes a validated Customer acknowledgement. `Request-Id` and
`Idempotent-Replayed` are optional supplemental evidence. Malformed responses
remain unknown and are never converted into proof of non-execution.

The observer validates each list page and every returned Customer, rejects
malformed/live-mode records, enforces the exact-email filter contract, detects
missing/repeated/cyclic cursors, and has a finite maximum-page bound. It never
calls Customer Search, never accepts `test_clock`, never requires the mutation
response ID for discovery, and never stops at the first match.

Multiple **distinct** Customer IDs carrying the marker are provider-resource
multiplicity: one matching resource is the intended single object, and each
additional distinct resource increases `additional_matching_resource_count`.
The same Customer ID appearing again during pagination is not another resource;
it makes the observation incomplete with
`repeated_customer_id_across_pages`. Likewise, any returned Customer whose email
does not exactly and case-sensitively match the requested marker makes the read
incomplete. A completed zero-match traversal is explicitly labelled a completed
read that is **not H0 proof**. Any transport, HTTP, parsing, filter-contract,
repeated-ID, cursor, or page-bound failure is `unknown_incomplete`.

## Deliberately unresolved before live qualification

This slice does not supply a live runner, persistent pre-dispatch intent,
crash-durable one-shot authorization, account/principal isolation proof, marker
allocation, cross-arm idempotency-key scheduling, ambiguity injection, polling
or convergence timing, cleanup, or paper-protocol execution. Live qualification
must separately gate credentials and operator intent, persist intent/evidence
before any provider boundary, prove test-account isolation and read visibility,
and hostile-audit the real transport behavior. No claim of live qualification
or provider behavior is made here.

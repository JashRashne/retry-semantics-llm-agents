# Stripe Customer semantics — DRAFT / NOT FROZEN

**ENGINEERING / DESIGN EVIDENCE ONLY**

**ZERO PAPER OBSERVATIONS**

**NO STRIPE PROVIDER CALL WAS PERFORMED BY THIS SLICE**

The official Stripe facts below were supplied as independently checked on
**2026-09-21**. This slice did not browse, contact Stripe, read credentials,
create a Customer, run Replay or Regeneration, or collect experimental evidence.
Engineering qualification is not Study 2 experimental evidence. Study 1 remains
closed and untouched.

## Candidate operation mapping

`create_customer` remains the mutation candidate because Stripe documents
`POST /v1/customers` as creating a Customer, accepts `email` and metadata, and
returns a Customer with a unique `id` and a `livemode` value on success. This
documents the candidate endpoint mapping; the mutation operation remains
**PROVISIONAL** until engineering qualification and does not establish remote
commit for an acknowledgement-free attempt.

The authoritative observation candidate is ordinary `list_customers` via
`GET /v1/customers`, using its documented exact, **case-sensitive** `email`
filter. The study marker must be a unique synthetic email value chosen before
dispatch, never a real person's address or other PII. The same marker can be
written by creation and supplied to the list filter without relying on a
mutation-response Customer ID. Metadata may provide supplemental engineering
context, but authoritative discovery must not require it.

The observation operation also remains **PROVISIONAL**. Documentation of its
endpoint and filter does not establish visibility, isolation, traversal
completeness, or zero-result correctness in the eventual engineering runtime.

The exact marker namespace and encoding are not frozen. A later design must
validate that the chosen synthetic value is accepted, preserved, isolated from
older engineering objects, and visible through the list operation.

## Why Customer Search is rejected

`GET /v1/customers/search` is not an authoritative Study 2 observer. Stripe warns
against Customer Search in read-after-write flows requiring strict consistency,
search propagation may lag, and Customer Search is unavailable to merchants in
India. Search therefore cannot be used as a fallback for authoritative discovery.
This choice does not assert that the ordinary list endpoint is strictly
consistent; Stripe's supplied documentation does not establish that guarantee.

## Completeness requirements

An observation must use the exact case-sensitive email filter and process every
Customer returned on every page. Stripe list pagination uses `starting_after`;
`limit=100` is a maximum page size, not proof of completeness. The observer must
honor the `has_more` page-completeness signal and continue while `has_more=true`.
Before advancing, it must require a usable final Customer `id` from the current
page and pass that ID as `starting_after`. Missing or malformed IDs, contradictory
`has_more` state, repeated/non-advancing cursors, inaccessible pages, or any other
partial traversal are **UNKNOWN/INCOMPLETE**, never zero. The observer must never
stop merely because it found the first matching Customer. Timestamps and ordering
are not authoritative correlation evidence.

### Test-clock completeness trap

Stripe documents that `GET /v1/customers` without the `test_clock` list parameter
does not include Customers associated with test clocks. The eventual frozen
Customer mutation tool schema must therefore reject `test_clock`; generation and
regeneration must not be able to associate a study Customer with one. This is a
future protocol/tool-schema requirement and is not yet enforced by an adapter.
The authoritative observer will not add arbitrary test-clock support. Until the
mutation-schema exclusion is frozen and enforced, observation completeness
remains unqualified.

Read-after-write visibility, convergence timing, concurrent page movement, and
whether all committed matching Customers become enumerable remain engineering
qualification questions. A complete traversal is necessary but does not itself
prove snapshot consistency or remote non-commit after a zero-result read.

## Provider idempotency is not retry policy

All Stripe POST requests accept a client-supplied `Idempotency-Key`. Once endpoint
execution begins, Stripe stores the first request's status code and response body
for a retained key; a later request with that retained key returns the stored
result. Stripe compares parameters on reuse and returns an error when the new
parameters do not match the original request. Keys may be pruned after they are
at least 24 hours old. A request rejected before endpoint execution begins may
not create an idempotency record.

These are provider semantics, not a decision to enable a key and not a Replay or
Regeneration policy. This slice silently enables neither. If a later frozen
runtime enables the mechanism, the key must be runtime-owned and stable across
retries and recovery attempts belonging to **one original mutation within one
experimental arm**, as required by the generic Study 2 contract. Replay and
Regeneration must receive independent keys or namespaces: a key must never be
shared between those arms, across families, or across runs. “Stable across
retries” does not mean “the same key across retry semantics.” Exact Replay's
stable request identity remains distinct from Stripe's parameter comparison.
Changed generated parameters under an arm-local stable key may trigger Stripe's
mismatch error; that behavior must not be mislabeled as agent-policy success or
failure. Paper-protocol key enablement remains unresolved.

`Idempotent-Replayed: true` can be useful supplemental evidence that Stripe
replayed a stored result. It is never required for state correctness. Similarly,
Stripe's `Request-Id` response header is supplemental when an acknowledgement
exists; ACK loss may remove it, so it cannot be required for observation or
correlation.

Provider idempotency does not make every ambiguous result observable. Preserve:

`dispatch initiated` != `local send completed` != `remote received` !=
`remote committed` != `acknowledgement returned`.

Local transport state cannot establish remote receipt or commit.

## Test/sandbox isolation and API version

Any later engineering runtime must fail closed to Stripe test/sandbox credentials
whose documented prefixes are `rk_test_` or `sk_test_`; live-mode credentials are
forbidden. Returned Customers must be validated as `livemode=false`. No key was
needed or accessed here. Test objects are separated from live-mode objects, but
the exact sandbox account/principal and the namespace separating current runs,
families, stale Customers, and prior engineering activity still require
qualification.

The reviewed candidate API version is `2026-08-26.dahlia`. Later requests should
explicitly pin a reviewed version rather than inherit an account default. Naming
that candidate does not freeze the final Study 2 protocol version.

## Unresolved before any live engineering call

- exact synthetic email encoding, namespace, validation rules, and collision policy;
- sandbox account/principal selection and fail-closed credential/livemode checks;
- frozen mutation-tool enforcement that rejects `test_clock`;
- list read-after-write visibility, convergence, `has_more` pagination, usable-cursor
  validation, and fail-closed traversal handling;
- whether the runtime enables an idempotency key for each qualification scenario;
- independent arm-local idempotency-key namespaces, if keys are enabled;
- transport/SDK choice, automatic retries, redirects, timeout behavior, and header capture;
- error taxonomy for pre-execution rejection versus ambiguous post-dispatch failure;
- explicit API-version binding and validation;
- polling, timing, termination, retention, and cleanup rules;
- authorization, audit artifacts, and a separately reviewed live qualification plan.

No adapter, live harness, smoke runner, qualification suite, ambiguity injection,
Replay/Regeneration execution, trial manifest, state evaluator, cleanup, or paper
row is introduced. Engineering qualification, when later authorized, will remain
separate from Study 2 experimental evidence.

## Supplied official reference set

- Stripe API Reference: `/api/idempotent_requests`
- Stripe API Reference: `/api/customers/create`
- Stripe API Reference: `/api/customers/list`
- Stripe API Reference: `/api/customers/search`
- Stripe API Reference: `/api/request_ids`
- Stripe API Reference: `/api/authentication`
- Stripe API Reference: `/api/versioning`
- Stripe Documentation: `/keys`
- Stripe Documentation: `/error-low-level`

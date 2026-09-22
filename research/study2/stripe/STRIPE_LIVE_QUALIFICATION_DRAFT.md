# Stripe live engineering qualification — DRAFT / NOT FROZEN

**ENGINEERING QUALIFICATION ONLY**
**ZERO PAPER OBSERVATIONS**
**NO LIVE STRIPE CALL HAS YET BEEN AUTHORIZED OR PERFORMED BY THIS SLICE**

This gate wraps the frozen Stripe Customer adapter. It does not change the
adapter or frozen semantics, and it does not test Replay versus Regeneration.

## Scope and two-stage control

`prepare` is completely offline. It exclusively creates an operator-selected
package and writes a canonical `plan.json` bound to its SHA-256, qualification
ID, unique `.invalid` email, unique engineering idempotency-key identity,
reviewed API version, Git HEAD, local `origin/main`, and relevant source hashes.
It records and requires the reviewed `httpx==0.28.1` runtime, stores no
credential, requires a fully clean pushed checkpoint (`HEAD == origin/main`),
and refuses an existing package. The package must be outside the repository.

`execute` is the only provider-capable mode. It requires the explicit live flag,
exact absolute plan path and expected plan hash, the exact confirmation phrase,
a fully clean worktree including untracked non-ignored files, pushed and matching
HEAD and `origin/main`, matching source hashes and `httpx` runtime, an unused
package, and the plan's engineering-only/zero-paper bounds.
Any authorization, repository, source, or runtime-provenance failure stops
before credential input and adapter construction. The production CLI accepts
the Stripe key only through hidden interactive input. It never accepts a raw key in
arguments, environment, files, or the plan. `rk_test_` is the preferred
least-privilege form with only required Customer permissions; the frozen adapter
also accepts `sk_test_`. Live, publishable, and unknown key forms are rejected.

## Durable one-CREATE boundary

After local authorization and credential validation, the wrapper uses the
frozen adapter to construct the exact request. Before calling its dispatch
boundary, it exclusively writes and fsyncs `intent.json`, including the request
identity, correlation email, safe idempotency-key identity, credential
fingerprint, plan hash, one-POST budget, and `dispatch_consumed=true`. Failure to
persist intent means no provider call. Once present, intent is never removed,
overwritten, repaired, or refunded. This is a conservative durability boundary
for the trusted local POSIX filesystem; it is not a claim against every possible
machine or storage failure.

Evidence ownership is invocation-local: only the executor whose exclusive
intent write and fsync return successfully may write mutation, observation, or
qualification results. A concurrent loser, or an executor seeing partial intent
residue, makes no provider or evidence write and stops for human review.

Exactly one Customer CREATE is permitted. There is no retry loop, second POST,
automatic rerun, ambiguity injection, or cleanup DELETE. The idempotency header
is used once to exercise the audited request path; this is not an idempotency
experiment and no provider deduplication conclusion follows.

Timeout, connection failure, interruption, malformed response, HTTP failure,
redirect, or other uncertainty makes the attempt non-PASS and permanently
consumed. It does not infer a hidden provider outcome, run observation, recreate,
or allocate a replacement package.

An acknowledged `Idempotent-Replayed: true` response is terminal non-PASS. It
invalidates the fresh-attempt premise, retains mutation evidence, and stops
before observation without inferring why Stripe retained that key.

## Observation and PASS

Only a fully validated Customer acknowledgement (`livemode=false`, exact email)
opens one authoritative Customer LIST sequence. The frozen observer performs the
exact-email filter and follows every `starting_after` page. No pagination logic
is reimplemented here.

PASS requires exactly one real CREATE dispatch, one validated acknowledgement,
one complete exhaustive observation, exactly one distinct matching Customer,
zero additional matches, and equality between the observed and acknowledged
Customer IDs. Paper observations remain zero. Incomplete, zero, multiple, or
ID-mismatched results are non-PASS and never authorize another CREATE.

The retained Customer is engineering evidence; automatic cleanup is prohibited.
The package records `plan.json`, durable `intent.json`, sanitized
`mutation_result.json`, `observation_result.json` only when observation was
allowed, and `qualification_result.json` where persistence remains possible.
Records include explicit dispatch/acknowledgement/observation counters, safe
request and credential identities, optional provider request/replay headers,
API/Git/source provenance, `engineering_only=true`, and
`paper_observations=0`. No raw key or Authorization header is persisted.

Any live execution still requires hostile audit and separate explicit operator
authorization. A non-PASS is a terminal engineering result, not permission to
rerun. This gate contains no paper schedule, trial families, policy assignment,
state labels, or statistical analysis.

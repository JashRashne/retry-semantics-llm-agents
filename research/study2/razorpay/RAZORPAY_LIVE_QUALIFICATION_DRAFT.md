# Razorpay Live Engineering Qualification

**DRAFT / NOT FROZEN**

**NO LIVE RAZORPAY CALL HAS YET BEEN PERFORMED**

**ENGINEERING QUALIFICATION ONLY**

**NOT PAPER DATA**

**PROVIDER C REMAINS TBD**

**STUDY 2 PAPER OBSERVATIONS = 0**

Execution requires a hostile audit and an explicit human authorization after
this draft and its implementation have been reviewed and frozen. Running the
offline tests or the `prepare` command is not authorization to execute.

## Narrow qualification question

One quiescent Razorpay Test Mode session asks whether a receipt-less Order body
with amount `200`, currency `INR`, and one synthetic notes marker is accepted;
whether the marker round-trips and the acknowledged Order is immediately
observable; and whether one exact second engineering dispatch of the same
frozen request object and bytes, under a new one-shot permit, produces a second
distinct Order ID that is also immediately observable.

The two creates are a receipt-less multiplicity probe for provider semantics
and instrumentation. They are not a paper trial, are not an LLM action, and do
not compare experimental arms. There is no ambiguity injection, timeout
experiment, mutation retry, polling, automatic rerun, or cleanup.

## Exact single-session sequence

The controller permits only this sequence:

1. One baseline observation for the pre-generated marker.
2. Create 1 with the frozen request and a fresh `DispatchPermit`.
3. One immediate observation requiring exactly Create 1's ID.
4. Create 2 with the very same `FrozenOrderCreateRequest` object and bytes and a
   new `DispatchPermit`.
5. One immediate observation requiring exactly the two acknowledged IDs.
6. Stop and write the terminal result.

Every failed prerequisite stops the sequence. No stage is polled or repeated.
There is never a third mutation dispatch. The adapter page cap is two per
observation, so the hard session ceiling is two POST dispatches and six GET
dispatches. A structurally completed one-page traversal normally uses three
GETs total. Hitting the page cap is inconclusive, never a reason to broaden the
scan automatically.

Each observation builds an explicit window around the controller clock with
300 seconds of padding on both sides and records the exact `from` and `to`
values. The draft makes no inclusive/exclusive boundary claim. Timestamps are
not identity; the synthetic marker is identity.

## Prepare

`prepare` requires an explicit repository root and an outside-repository
package directory. It performs no provider operation and does not construct an
HTTP adapter. It creates the package directory exclusively, refuses an existing
destination, and initially writes only `qualification_plan.json`.

The canonical plan freezes the qualification ID, marker, engineering-only
status, zero paper observations, candidate and environment, payload constants,
dispatch and observation ceilings, prohibited behaviors, audited transport
profile, Git HEAD and `origin/main`, relevant source hashes, all previously
frozen Razorpay hashes, reviewed `httpx` version, exact authorization phrases,
and its canonical SHA-256 hash. Preparation refuses a dirty tree (including
untracked files), a HEAD/`origin/main` mismatch, frozen-source drift, or runtime
version drift.

Preparation also computes a package-location digest from the qualification ID
and the resolved absolute package directory. Only that digest is stored; the
raw local path is not persisted in the plan or evidence. This binds the plan to
its original canonical package location and prevents a copied plan from
becoming a second executable package.

The PREPARE CLI prints the canonical plan path, SHA-256 of the exact persisted
`qualification_plan.json` bytes, the internal canonical plan hash, and the
qualification ID. The exact whole-file hash is the external human authorization
anchor. The operator must retain it independently for EXECUTE; recomputing the
internal hash after editing the plan does not change the authorized file hash.

No credential, secret, Authorization header, or provider response is placed in
the plan. A real execution package must not be prepared until hostile audit and
freeze are complete.

## Execute authorization and provenance

`execute` is the only provider-capable path. It requires the live flag, the
exact phrase
`EXECUTE_ONE_RAZORPAY_TEST_ORDER_MULTIPLICITY_QUALIFICATION`, and an explicit
operator assertion that the supplied pair was generated in Razorpay Test Mode.
It also requires `--plan-file-sha256` with the exact lowercase whole-file hash
emitted by PREPARE. Before parsing JSON, EXECUTE hashes the raw plan bytes and
requires exact equality with that external value. It then validates the
internal canonical plan hash, package-location digest, outside-repository
location, clean tree, HEAD equality, `origin/main`, all source hashes, frozen
hashes, and runtime versions. Resolved canonical paths are used so an ignored
in-repository directory or path indirection cannot bypass the location rule.
Any local provenance failure occurs before intent acquisition and before
provider traffic.

Both Key ID and Key Secret are obtained through hidden interactive prompts.
They are not accepted through command-line values, environment variables,
files, package JSON, or repository configuration. Raw credentials are never
printed or serialized. Evidence retains only the adapter's one-way credential
scope fingerprint.

Razorpay documentation does not establish credential syntax as authoritative
proof of Test Mode. The operator assertion is therefore required. As a
secondary, explicitly non-authoritative defense, a Key ID beginning with the
known live-looking `rzp_live` form is rejected. No positive syntax claim is
made. If future non-secret runtime/provider evidence contradicts Test Mode, the
gate must fail closed rather than inventing a provider field or proceeding.

The production path constructs `RazorpayOrderAdapter` without a transport
override and verifies that the resulting frozen request uses
`httpx_httptransport_retries0_no_redirects_no_trust_env_v1` with the reviewed
timeout. Only offline tests can inject a synthetic adapter factory.

Production execution rejects every injected adapter, provenance, runtime, and
clock seam. Synthetic tests must explicitly select the private internal test
mode and supply a synthetic adapter; they cannot fall back to the production
transport. The operator CLI exposes no synthetic mode and always invokes the
production path.

## Persistent intent and races

After all local preflight checks and before the adapter is created or the first
baseline GET can cross the boundary, execution atomically creates and fsyncs
`intent.json`, then fsyncs its containing directory. Exclusive creation is both
the ownership lock and the irreversible consumption event. The artifact binds
the qualification ID, exact marker, plan hash, source provenance, two-mutation
ceiling, and no-rerun rule.

A crash after intent creation never refunds the package, even if no response or
no provider request followed. A second execution refuses the consumed package.
If two processes race, exactly one can create intent and become owner; the loser
makes no provider call and writes no terminal evidence.

## Sanitized evidence

Only reached stages are created:

- `intent.json`
- `baseline_observation.json`
- `mutation_1.json`
- `observation_1.json`
- `mutation_2.json`
- `observation_2.json`
- `qualification_result.json`

Every artifact binds the qualification ID, plan hash, candidate, engineering
status, zero paper observations, stage, source HEAD, externally authorized exact
plan-file hash, package-location digest, UTC record time, and current counters,
including aggregate GET dispatches. Observation artifacts include the
exact window, pages, skips, query
digests, HTTP statuses, matching IDs, pagination stability, and the frozen
adapter's sanitized status. The frozen result does not expose total returned
item traversal count, so this draft records that value as unavailable rather
than fabricating it. Mutation artifacts contain only sanitized adapter evidence,
request/body hashes, the one-way credential scope fingerprint, and the explicit
same-object claim for the second dispatch.

Every production artifact says `synthetic_test_execution: false` and
`live_qualification_evidence: true`. Every unit-test artifact says
`synthetic_test_execution: true` and `live_qualification_evidence: false`.
Synthetic state-machine PASS results are therefore unmistakably non-live and
cannot serve as live qualification evidence.

Artifacts never retain raw Key ID, Key Secret, Authorization, Base64
credentials, raw environment, raw exception text, unrelated responses, or PII.
Provider Orders are deliberately retained; the gate performs no delete, cancel,
update, or notes mutation.

## Stop and terminal rules

- A nonzero baseline is `NON_PASS`; an incomplete baseline is `INCONCLUSIVE`.
  Neither permits a mutation.
- Any non-acknowledged Create 1 is `INCONCLUSIVE` and stops after at most one
  mutation dispatch. In particular, an unknown outcome is not observed and
  retried.
- Observation 1 must structurally complete and contain exactly Create 1's ID.
  Zero, a wrong ID, multiple IDs, malformed data, transport failure,
  pagination instability, or page-cap exhaustion stops before Create 2.
- Create 2 must acknowledge a different ID. A repeated ID is `NON_PASS`; an
  unacknowledged/unknown result is `INCONCLUSIVE`. There is no third dispatch.
- Observation 2 must structurally complete with exactly the two expected IDs.
  Missing IDs are `INCONCLUSIVE`; an unexpected marker-bearing ID is
  `NON_PASS`. No result is interpreted as a paper duplicate outcome.
- Unexpected local exceptions fail closed with fixed sanitized evidence.
- `LOCAL_PREFLIGHT_FAILED` is reserved for a genuinely pre-provider failure,
  such as a production transport-profile mismatch detected before the baseline
  GET. A request-identity or counter invariant discovered after provider
  dispatch is `INCONCLUSIVE` with an explicit post-dispatch reason; its evidence
  retains the reached-stage and dispatch counters and never implies that the
  provider boundary was not crossed.

`PASS` is possible only with one zero-match structurally completed baseline,
two validated acknowledgements for distinct IDs from the same frozen request,
one immediate exact-ID observation after each create, exactly two mutation
dispatches, exactly one baseline sequence, and exactly two post-create
observation sequences. On PASS, the narrow statement is only:

> Under this controlled low-cardinality Test Mode qualification session, both
> acknowledged marker-bearing Orders were immediately observable.

Even then, `authoritative_completeness_qualified` remains false. A PASS does not
establish global list completeness, timestamp boundary behavior, visibility
latency bounds, behavior under ambiguity, production-mode behavior, cleanup
semantics, experimental outcomes, or Provider C selection. Provider C remains
TBD and Study 2 paper observations remain zero until separately authorized work
changes those facts.

# Razorpay Study-2 paper semantics: public documentation evidence

**PROSPECTIVE DRAFT / NOT FROZEN**

**STUDY-2 PAPER OBSERVATIONS = 0**

**PUBLIC DOCUMENTATION ONLY — NO PROVIDER API OR ACCOUNT ACTION**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## 1. Scope, provenance, and evidence labels

Public sources were first read on **2026-09-23 at 11:43 UTC** and retrieved
again for the local provenance snapshot at the exact UTC times below:

| Source | Type | Snapshot retrieval UTC | Relevant location |
| --- | --- | --- | --- |
| [Create an Order](https://razorpay.com/docs/api/orders/create/) | Human documentation | `2026-09-23T12:04:09.970239Z` | `POST /v1/orders`, success example, request/response parameters, duplicate-receipt error |
| [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/) | Human documentation | `2026-09-23T12:04:10.364530Z` | `GET /v1/orders`, query parameters, collection example |
| [Public OpenAPI](https://razorpay.com/openapi.json) | OpenAPI 3.0.0 specification, `info.version = 1.0.0` | `2026-09-23T12:04:10.586068Z` | `servers`; `paths./orders.post` (`createOrder`); `paths./orders.get` (`fetchAllOrders`); `paths./orders/{id}.get` (`fetchOrder`); referenced schemas and query parameters |

The OpenAPI `servers` entry *describes* `https://api.razorpay.com/v1`; that
host was **not contacted**. The compact, deterministically serialized local
snapshot is
`research/study2/razorpay/evidence/public_documentation/RAZORPAY_PUBLIC_DOCS_2026-09-23.json`
with SHA-256
`056a792cf2c658dadaf1e9c66e8a25c5d277532a3af7ad68cfa642172c1d80c8`.
It preserves the relevant public operation/schema content, human examples and
statements, source-body hashes, and exact retrieval times so these prospective
claims remain auditable if the public pages later change. It is **documentation
provenance only**, not provider API evidence or a frozen artifact. No
credentials, authenticated page, Dashboard, provider API request, account
resource, or paper observation was accessed or produced.

Labels used below are deliberately separate:

- **OFFICIAL DOCUMENTATION FACT:** a statement or schema in the three current
  public sources above.
- **PROTOCOL INTERPRETATION:** a prospective scientific rule inferred from a
  documented API contract; it is not a provider implementation guarantee.
- **EMPIRICAL ENGINEERING FACT:** a narrow finding in the already-frozen local
  qualification locks, never paper data or a general provider guarantee.
- **NOT ESTABLISHED:** a property not supplied by these sources or locks.

The frozen `primary_experiment_v1.md` requires controlled H0/H1, exactly one
intended pre-recovery H1 effect, and state-only correctness. The frozen
`primary_create_v1_3_analysis_plan.md` requires authoritative terminal state
for `BEHAVIORALLY_EVALUABLE_ARM = 1` and matched-pair inclusion. The
`STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` preserves those definitions and
blocks all Study-2 collection pending audited prospective artifacts. The
current untracked `RAZORPAY_PAPER_SEMANTICS_CONTRACT.md` identifies exact-one
Create semantics as a remaining feasibility obligation; it was read but not
changed. The older `RAZORPAY_SEMANTICS_RECONNAISSANCE.md` is historical,
hash-pinned, and explicitly draft. Its description of documentation reviewed
at that time is not retroactively called erroneous or edited here.

## 2. Create-Order operation cardinality

| Label | Evidence or conclusion |
| --- | --- |
| **OFFICIAL DOCUMENTATION FACT** | The human page names a singular Create an Order operation at `POST /v1/orders` and shows a single Order JSON object as its success response. [Create an Order](https://razorpay.com/docs/api/orders/create/) |
| **OFFICIAL DOCUMENTATION FACT** | OpenAPI defines `paths./orders.post` with `operationId: createOrder`, summary Create an order, a `200` success description of Order creation, and one `application/json` response schema reference to `#/components/schemas/Order`, not a collection or array. Its `servers` base path is `/v1`. [Public OpenAPI](https://razorpay.com/openapi.json) |
| **OFFICIAL DOCUMENTATION FACT** | The human response parameter description calls `id` the Order's unique identifier; OpenAPI `Order.id` describes a unique Order identifier, and `Order.entity` is constrained to `order`. The singular response has `amount`, `currency`, `notes`, and `receipt` fields. [Create an Order](https://razorpay.com/docs/api/orders/create/); [Public OpenAPI](https://razorpay.com/openapi.json) |
| **OFFICIAL DOCUMENTATION FACT** | The human Create page says `receipt` must be unique. Its HTTP `400` duplicate-request description says a second Create with the same receipt is rejected and treats `receipt` as an idempotency key. This statement is specifically about a reused receipt, not provider-wide Create idempotency. [Create an Order](https://razorpay.com/docs/api/orders/create/) |
| **NOT ESTABLISHED** | Neither source literally states that one successfully acknowledged request can *never* create more than one Order resource. The singular operation name, response, and schema imply one creation as the documented operation's normal semantics; they do not independently verify every internal execution or exclude an undocumented extra side effect. |
| **NOT ESTABLISHED** | The OpenAPI `Order` schema lists properties but no `required` list. Receipt is optional in the Create request schema; the OpenAPI response `receipt` property is typed as a string and does not specify how an omitted request receipt is represented in every response. The future evaluator must validate the actual response and its prospectively fixed receipt-absent representation, not assume fields are present solely because they appear in a schema example. |

**PROTOCOL INTERPRETATION — candidate closed-ledger premise:** Treat one
successfully acknowledged `createOrder` dispatch whose response validates as
one Order as **one attributable Order creation under the documented operational
API contract**. This supplies an operational at-most-one premise, together
with the response's positive at-least-one evidence. It is not a mathematical
or implementation-level guarantee. It must be frozen and hostile-audited in a
later semantics contract and cross-provider protocol before use. Any later
positive evidence of more than one Order attributable to that *single recorded
dispatch* contradicts the premise and must cause infrastructure/protocol
invalidation, never quiet deduplication or a convenient `STATE_CORRECT = 1`.
Two Orders attributable to two separately recorded dispatches remain a
possible behavioral duplicate under the existing outcome rule.

**Assessment: SUPPORTED AS DOCUMENTED OPERATIONAL SEMANTICS.** This is a
prospective API-contract assumption supported by the singular `createOrder`
operation and singular Order success schema, with the explicit limitation that
the sources do not state a universal at-most-one theorem. It is stronger than
merely observing one ID, and weaker than direct exhaustive observation of all
account state.

**PROTOCOL INTERPRETATION — receipt remains prohibited.** The selected Study-2
Create omits `receipt`; the paper must not use it as correlation identity or
use the Fetch All receipt filter for its observer. A stable receipt would
activate documented duplicate-receipt rejection and could mask the
resource-multiplicity behavior under study. Correlation remains the
harness-owned notes marker. Omitting receipt does **not** itself establish
non-idempotence; receipt-less multiplicity is empirically established only for
the frozen one-replay engineering case.

## 3. Create response: what it validates

**OFFICIAL DOCUMENTATION FACT.** The Create human page's HTTP-success example
is one JSON object with `id`, `entity: order`, `amount`, `currency`, `notes`,
`receipt`, `status: created`, `amount_paid: 0`, `attempts: 0`, and
`created_at`. Its response parameter descriptions identify `id` as unique,
`amount` and `currency` as Order values, `notes` as metadata, and `receipt` as
the optional internal reference. OpenAPI's `200` response references one
`Order` object with those relevant properties and constrains `entity` to
`order`. [Create an Order](https://razorpay.com/docs/api/orders/create/);
[Public OpenAPI](https://razorpay.com/openapi.json).

**PROTOCOL INTERPRETATION.** A validated success response establishes positive
evidence of its named Order and linkage to that acknowledged dispatch when the
client request/response ledger is intact. Validate a nonempty returned ID, entity,
amount, currency, marker-bearing notes, and the prospectively declared
receipt-absent representation. This response alone is **not** exhaustive
account-state evidence. A direct known-ID GET can independently corroborate
the one named Order, but cannot prove the absence of another one.

**EMPIRICAL ENGINEERING FACT.** The frozen Phase-1 acknowledgement named one
Order; Phase 2 directly validated that known ID. Phase 3's exact receipt-less
replay obtained and directly validated a *different* ID. The locks establish
two distinct resources across two recorded dispatches, not one-resource
cardinality for arbitrary individual dispatches. See
`RAZORPAY_LIVE_QUALIFICATION_PHASE1_LOCK.md`,
`RAZORPAY_PHASE2_READONLY_QUALIFICATION_LOCK.md`, and
`RAZORPAY_PHASE3_REPLAY_VISIBILITY_LOCK.md`. These are engineering observations
only and never enter paper denominators.

## 4. Fetch-All window and pagination semantics

| Topic | **OFFICIAL DOCUMENTATION FACT** | Remaining boundary |
| --- | --- | --- |
| Operation/shape | Human page describes `GET /v1/orders` and shows `{entity: collection, count, items: [...]}`. OpenAPI `fetchAllOrders` returns `Collection` with an Order array. [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/); [Public OpenAPI](https://razorpay.com/openapi.json) | A collection response is not by itself an exhaustive account oracle. |
| `from` | Human page calls it a Unix timestamp from which Orders are fetched. OpenAPI shared parameter says records created **on or after** the timestamp; Orders GET references it. [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/); [Public OpenAPI](https://razorpay.com/openapi.json) | OpenAPI specifies an inclusive lower filter in documentation, not empirical completeness or visibility at that boundary. |
| `to` | Human page says up to a Unix timestamp. OpenAPI shared parameter says records created **on or before** it; Orders GET references it. [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/); [Public OpenAPI](https://razorpay.com/openapi.json) | OpenAPI specifies an inclusive upper filter in documentation, not empirical completeness or visibility at that boundary. |
| Request `count` | Human page: default 10, maximum 100, used with `skip`. OpenAPI: integer, minimum 1, maximum 100, default 10; Fetch All description says maximum 100 records per call. [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/); [Public OpenAPI](https://razorpay.com/openapi.json) | Requested page size is not a total-result count. |
| Response `count` | OpenAPI `Collection.count` explicitly means **number of items in the current page**. [Public OpenAPI](https://razorpay.com/openapi.json) | It is not defined as a total across pages. |
| `skip` | Human page: number of Orders skipped, default 0, used with `count`. OpenAPI: integer, minimum 0, default 0. [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/); [Public OpenAPI](https://razorpay.com/openapi.json) | Offset pagination alone does not establish stable traversal. |
| Filters | Human query table and Orders GET OpenAPI parameters list `authorized`, `receipt`, `from`, `to`, `count`, `skip`, and `expand[]`; neither defines a `notes` filter. [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/); [Public OpenAPI](https://razorpay.com/openapi.json) | The paper omits receipt, so its receipt filter cannot be its correlation mechanism. Local notes-marker inspection is needed; a CLI `--status` example does not establish a REST `status` filter. |
| Ordering, snapshot, termination, total | Neither source defines stable ordering, snapshot consistency/token, a `has_more` or cursor, a terminal-page completeness promise, or a total-result count. [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/); [Public OpenAPI](https://razorpay.com/openapi.json) | A short/empty terminal page is an operational traversal rule, not an authoritative exact-set certificate. |

**NEW PROSPECTIVE DOCUMENTATION EVIDENCE.** The current public OpenAPI is more
precise than the human Fetch All page and the historical reconnaissance on
three points: `from` is described as inclusive, `to` as inclusive, and
response `Collection.count` as the current-page item count. Its request
`count` also explicitly has minimum 1 and `skip` minimum 0. This records what
the public specification says **now**; it does not revise the older
reconnaissance, establish empirical filter-boundary behavior, or qualify list
completeness.

## 5. Explicitly not established

**NOT ESTABLISHED** by the three current public sources or the frozen locks:

- Fetch All authoritative completeness, including absence of an unseen Order
  after a structurally complete or repeated traversal;
- stable global ordering, snapshot consistency across pages, a documented
  terminal-page completeness rule, or a total-result count;
- bounded read-after-write convergence, monotonic visibility, any general
  visibility latency, or `+30` seconds as a latency bound;
- zero list matches as proof of H0 or absence;
- an Order ID becoming available after a naturally lost acknowledgement;
- provider-wide receipt-less replay/deduplication behavior beyond the one
  frozen engineering replay; and
- literal, unconditional at-most-one implementation behavior for every
  acknowledged Create, independent of the prospective operational
  API-contract assumption in Section 2.

**EMPIRICAL ENGINEERING FACT.** Phase 1's immediate Fetch All missed an
acknowledged Order; Phase 2 later returned that Order with the same historical
query; Phase 3 saw both positively known Orders at its first successful
scheduled `+30` read. All list reads retained
`authoritative_completeness_qualified = false`. See the three frozen phase
locks and `RAZORPAY_PROVIDER_C_SELECTION_LOCK.md`. None is Study-2 paper
evidence.

## 6. Narrow scientific consequence and next gate

**PROTOCOL INTERPRETATION.** If the later, prospectively frozen protocol
accepts the documented one-Order-per-acknowledged-Create operational premise,
then an exclusive arm scope, complete mutation-dispatch ledger, disabled
automatic retries, unique pre-dispatch marker reservation, exclusive writer
control, one acknowledged and validated Create, and **no other mutating
dispatches** can form a closed causal ledger for exactly one attributable
Order. This route does not claim Fetch All completeness. A controlled H1 can
then be certified only when its independent construction and scope/pairing
requirements also hold. An unacknowledged mutating dispatch still requires
separate commit/multiplicity evidence and remains `INCONCLUSIVE` when that
evidence is unavailable. Any observed one-dispatch/multiple-Order
contradiction fails closed as infrastructure/protocol invalidation. None of
these interpretations changes `STATE_CORRECT`, H0/H1, Replay, Regeneration,
eligibility, or the frozen analysis plan's evaluability rule.

This evidence makes a **prospective repair of the current fatal exact-one
blocker plausible**, subject to hostile audit and explicit adoption in the
later Razorpay semantics contract and final cross-provider protocol. It does
not repair that contract in this task, settle external paired-state projection,
or authorize collection. **No further live qualification is needed to read or
record these public documentation semantics.** Whether the eventual protocol
needs any separately authorized empirical qualification for another unresolved
implementation property remains a later pre-data decision; this document
requests none.

**STUDY-2 PAPER OBSERVATIONS = 0. PAPER COLLECTION REMAINS BLOCKED.**

# Razorpay semantics reconnaissance

**DRAFT / NOT FROZEN**

**DOCUMENTATION RECONNAISSANCE ONLY**

**PROVIDER C NOT YET SELECTED**

**ZERO STUDY 2 PAPER OBSERVATIONS**

**NO RAZORPAY API/PROVIDER CALL WAS PERFORMED**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent
Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

Public documentation consulted: 2026-09-22

Repository baseline: `e045cf21bef9c553b0a744ad67dfa97d4ca000cb`
(`HEAD == origin/main`; initial worktree clean).

The researcher independently completed the human/operator accessibility
preflight from India: legitimate signup succeeded, Test Mode was accessible,
and Test Mode credentials could be generated. No live payment or real-money
transaction was performed. This establishes accessibility only. It is not
semantics qualification and does not select Razorpay as Provider C. No
credential, Key ID, or Key Secret is stored in this document.

## 1. Scope, method, and evidence labels

This artifact is public-documentation reconnaissance only. It does not add a
provider, implement an adapter, make an API request, access the Razorpay
Dashboard, read credentials, freeze a protocol, or collect a paper observation.
Study 1 and the frozen GitHub and Google Sheets work are unchanged. The
prospective 64-family allocation is unchanged.

Every answer below uses one of these labels:

- **ESTABLISHED BY OFFICIAL DOCS**: the cited official Razorpay page directly
  supports the statement.
- **NOT ESTABLISHED**: the reviewed official documentation does not make the
  required guarantee.
- **CONTRADICTED**: official documentation states the opposite.
- **UNRESOLVED**: the available official pages are incomplete, internally
  inconsistent, or require later hostile engineering qualification.

An inference is labelled **INFERENCE** and is not a provider guarantee. Search
absence means only “not found in the stated official-documentation search,” not
that the behavior is physically or mathematically impossible.

## 2. Official sources reviewed

Only public pages on `razorpay.com` were used as provider-semantic evidence.
No blog, community post, third-party tutorial, issue tracker, Dashboard page,
or authenticated API was used as authority.

| Ref | Official Razorpay source | Relevant evidence |
| --- | --- | --- |
| R1 | [API Authentication](https://razorpay.com/docs/api/authentication/) | Basic Auth; Key ID and Key Secret; Test/Live key generation; Test Mode meaning |
| R2 | [Orders API overview](https://razorpay.com/docs/api/orders/) | Test API Keys; Orders endpoint inventory |
| R3 | [Create an Order](https://razorpay.com/docs/api/orders/create/) | request, response, minimum amount, receipt uniqueness/deduplication, initial state |
| R4 | [Fetch All Orders](https://razorpay.com/docs/api/orders/fetch-all/) | collection example, filters, `count`, `skip`, returned Order fields |
| R5 | [Update an Order](https://razorpay.com/docs/api/orders/update/) | notes mutability and notes limits |
| R6 | [Python server integration](https://razorpay.com/docs/payments/server-integration/python/integration-steps/) | required/optional Create fields, payment-flow separation, SDK example |
| R7 | [Python Test App / Test Integration](https://razorpay.com/docs/server-integration/python/test-app/) | simulated Test Mode; no real money deducted |
| R8 | [Payout Idempotency](https://razorpay.com/docs/api/x/payout-idempotency/) | payout-scoped idempotency behavior |
| R9 | [Direct Transfer idempotent request](https://razorpay.com/docs/api/payments/route/direct-transfers-idempotent-request/) | `X-Transfer-Idempotency`; explicitly scoped to Direct Transfers |
| R10 | [Create a Customer](https://razorpay.com/docs/api/customers/create/) | `fail_existing` duplicate behavior |
| R11 | [Create an Item](https://razorpay.com/docs/api/payments/invoices/create-item/) | alternative non-payment resource |
| R12 | [Fetch All Items](https://razorpay.com/docs/api/payments/invoices/fetch-all-items/) | alternative collection observation |
| R13 | [About Items](https://razorpay.com/docs/payments/invoices/items/) | item lifecycle and conditional deletion |
| R14 | [Create a Plan](https://razorpay.com/docs/api/payments/subscriptions/create-plan/) | alternative resource with notes but recurring-payment semantics |
| R15 | [Create a Standard Payment Link](https://razorpay.com/docs/api/payments/payment-links/create-standard/) | unique `reference_id`, customer-facing payment surface |
| R16 | [Orders dashboard actions](https://razorpay.com/docs/payments/orders/dashboard/) | documented view/report actions; no delete action |
| R17 | [Affordability Widget integration](https://razorpay.com/docs/payments/payment-gateway/emi%C2%B2/widget/native-web/) | a test Key ID example, not a universal key-format contract |

Targeted official-domain searches included the following terms and
combinations: `Orders idempotency`, `Orders idempotency key`, `duplicate
request`, `retry`, `replay`, `deduplication`, `X-Transfer-Idempotency`, `payout
idempotency`, `Orders SDK automatic retry`, `Orders delete`, `Orders cancel`,
`Orders ordering`, `Orders snapshot consistency`, `Orders read after write`,
`Orders eventual consistency`, `Razorpay request ID`, `rate limit`, `429`,
`Retry-After`, `rzp_test_`, and `rzp_live_`. The material results are recorded
below. A search result was not treated as evidence unless it led to an official
page listed above.

## 3. A. Test Mode and access

| Question | Finding |
| --- | --- |
| 1. What Test Mode means | **ESTABLISHED BY OFFICIAL DOCS.** Razorpay calls Test Mode a simulation mode for testing an integration flow and says customers cannot make payments in it. [R1] |
| 2. Whether Test and Live credentials are distinct | **ESTABLISHED BY OFFICIAL DOCS.** The operator selects Test or Live when generating keys; Razorpay instructs integrations to replace test keys with live keys to accept customer payments. Create/Fetch error documentation also lists mixing Test and Live credentials as a failure cause. [R1], [R3], [R4] |
| 3. Whether Test Mode prevents real customer payments / real money | **ESTABLISHED BY OFFICIAL DOCS, WITH SCOPE.** The authentication page says customers cannot make payments in Test Mode; the Test Integration page says no real money is deducted when test keys are used and calls the transaction simulated. This supports Test Mode safety, not a claim about every Razorpay product. [R1], [R7] |
| 4. Whether Orders API can use Test keys | **ESTABLISHED BY OFFICIAL DOCS.** The Orders overview invites use of the Orders APIs with Test API Keys. [R2] |
| 5. Whether Create Order itself moves money | **ESTABLISHED BY OFFICIAL DOCS for resource/payment separation; NOT ESTABLISHED as a universal funds-system claim.** Create returns an Order with `amount_paid: 0`, `attempts: 0`, and `status: created`; the Order stays `created` until a payment is attempted. Checkout/payment initiation is a later step. Thus the documented operation creates an Order resource and is not itself a payment attempt. The docs do not phrase this as a universal assertion about every internal ledger effect. [R3], [R6] |

Accessibility preflight is therefore passed independently. Semantics
qualification is not passed merely because access exists.

## 4. B. Create Order semantics

| Question | Finding |
| --- | --- |
| 1. Endpoint and method | **ESTABLISHED BY OFFICIAL DOCS:** `POST /v1/orders` (shown in curl as `POST https://api.razorpay.com/v1/orders`). [R2], [R3] |
| 2. Required fields | **ESTABLISHED BY OFFICIAL DOCS:** `amount` and `currency` are mandatory. `receipt`, `notes`, `partial_payment`, and conditionally `first_payment_min_amount` are optional in the server-integration parameter table. [R3], [R6] |
| 3. Minimum INR amount | **ESTABLISHED BY OFFICIAL DOCS:** the Create page says the minimum is INR 1.00 and instructs using an amount of at least `100` currency subunits. One sentence on the same page says subunits “should always be greater than 100,” which conflicts with its stated minimum/solution. **UNRESOLVED wording inconsistency:** later qualification should use a deliberately conservative fixed value at or above 100 paise, not depend on the inconsistent sentence. [R3] |
| 4. Whether `receipt` is optional | **ESTABLISHED BY OFFICIAL DOCS.** The Python server-integration table explicitly labels it optional. [R6] |
| 5. Receipt constraints | **ESTABLISHED BY OFFICIAL DOCS:** maximum 40 characters, unique; the Create page's error section also recommends restricted ASCII for compatibility. [R3] |
| 6. Whether receipt must be unique | **ESTABLISHED BY OFFICIAL DOCS.** The request and response descriptions say it has to be unique. [R3] |
| 7. `notes` support and limits | **ESTABLISHED BY OFFICIAL DOCS with an inconsistency.** Create accepts an optional JSON object, documented as at most 15 key-value pairs and “256 characters (maximum) each.” The Update page's errors separately state keys over 255 and values over 512 are rejected. **UNRESOLVED:** exact key/value ceiling language is inconsistent. A future marker must be far shorter than all stated limits. [R3], [R5], [R6] |
| 8. Whether notes are returned on the resulting Order | **ESTABLISHED BY OFFICIAL DOCS.** The success example and response schema include `notes`. [R3] |
| 9. Initial status | **ESTABLISHED BY OFFICIAL DOCS:** `created`; it remains so until a payment is attempted. The example also has `attempts: 0`, `amount_paid: 0`. [R3] |
| 10. Whether creating an Order requires a payment attempt | **CONTRADICTED.** The documented lifecycle places the Order in `created` before any payment attempt, and the integration sequence creates an Order before Checkout. No Checkout or payment attempt is needed for the Create call itself. [R3], [R6] |
| 11. Repeating the same Create payload | **UNRESOLVED when `receipt` is omitted.** With the same non-empty receipt, the Create page documents a duplicate-request error and calls receipt an idempotency key. For a receipt-less identical request, the docs do not say whether another Order is created, the request fails, or some other deduplication occurs. [R3] |

Razorpay additionally says to create a new Order for every payment attempt and
that an Order ID maps 1:1 to a payment attempt. This is workflow guidance about
payment attempts, not a formal guarantee that arbitrary receipt-less byte-for-byte
replays always create distinct Orders. It must not be promoted into an
idempotency or multiplicity theorem. [R3]

## 5. C. Receipt must not mask duplication

**ESTABLISHED BY OFFICIAL DOCS:** receipt is optional, limited to 40 characters,
and unique. The current Create page goes further: a second create with the same
receipt is documented as a `400` duplicate request; it calls `receipt` an
idempotency key and says the second call is rejected. [R3], [R6]

**Candidate recommendation:** omit `receipt` entirely. Explicitly reject receipt
as the Study 2 correlation marker. A stable receipt would activate
provider-level duplicate handling and could turn a replay that might otherwise
create a second Order into an error, masking the resource-multiplicity outcome
the study is meant to observe. This recommendation is valid because official
documentation explicitly makes receipt optional. [R3], [R6]

Omission does not establish the opposite behavior. Receipt-less replay
multiplicity remains **UNRESOLVED** and needs hostile Test Mode qualification.

## 6. D. Notes as a correlation marker

| Question | Finding |
| --- | --- |
| 1. Request format | **ESTABLISHED BY OFFICIAL DOCS:** optional JSON object / key-value pairs. A future marker should be one synthetic key and one synthetic value with no PII. [R3], [R6] |
| 2. Limits | **ESTABLISHED BY OFFICIAL DOCS with the inconsistency described in §4:** 15 pairs and conflicting 255/256/512 character language. [R3], [R5] |
| 3. Returned in Create response | **ESTABLISHED BY OFFICIAL DOCS.** [R3] |
| 4. Returned in Fetch All Orders | **ESTABLISHED BY OFFICIAL DOCS.** `notes` is an Order response field and appears in each sample item. [R4] |
| 5. Can notes be changed later | **ESTABLISHED BY OFFICIAL DOCS.** `PATCH /v1/orders/:id` can update notes; other immutable Order fields are rejected. [R5] |
| 6. Direct list filter by notes | **NOT ESTABLISHED.** Fetch All documents `authorized`, `receipt`, `from`, `to`, `count`, `skip`, and `expand[]`; it documents no notes filter. [R4] |
| 7. Exact marker preservation | **NOT ESTABLISHED as a formal guarantee.** Examples show values returned, and the schema describes storage of additional information, but no page promises byte-for-byte preservation, Unicode normalization behavior, type preservation for all scalar values, or immutability. Notes are explicitly mutable. [R3], [R5] |

**INFERENCE:** notes are the strongest reviewed pre-dispatch correlation field
because they are accepted at create time and included in both Create and list
representations without imposing documented uniqueness. Later engineering must
use an intentionally simple, short ASCII string value, exact local comparison,
and an isolation rule that forbids later notes updates. Exact encoding is not
frozen here.

## 7. E. Fetch All Orders

| Question | Finding |
| --- | --- |
| 1. Endpoint and method | **ESTABLISHED BY OFFICIAL DOCS:** `GET /v1/orders`. [R2], [R4] |
| 2. Collection structure | **ESTABLISHED BY OFFICIAL DOCS:** sample responses contain `entity: "collection"`, `count`, and `items`, with each item an Order. [R4] |
| 3. `count` | **ESTABLISHED BY OFFICIAL DOCS as a request page size:** default 10; used with `skip`. The response example also contains `count`. [R4] |
| 4. Maximum count | **ESTABLISHED BY OFFICIAL DOCS:** 100. [R4] |
| 5. `skip` | **ESTABLISHED BY OFFICIAL DOCS:** number of Orders skipped; default 0; used with `count` for pagination. [R4] |
| 6. `from` | **ESTABLISHED BY OFFICIAL DOCS:** Unix timestamp from which Orders should be fetched. [R4] |
| 7. `to` | **ESTABLISHED BY OFFICIAL DOCS:** Unix timestamp up to which Orders should be fetched. [R4] |
| 8. `receipt` filter | **ESTABLISHED BY OFFICIAL DOCS:** retrieves Orders containing the supplied receipt value. It is unusable for the proposed no-receipt design. [R4] |
| 9. Other filters | **ESTABLISHED BY OFFICIAL DOCS:** `authorized` (`1` or `0`) and `expand[]` values for payments, payment card details, transfers, and virtual accounts. No `status`, `notes`, ID-set, or marker filter is documented in the parameter table, notwithstanding a CLI example that displays `--status paid`; that discrepancy does not establish a REST `status` filter. [R4] |
| 10. Notes in each returned Order | **ESTABLISHED BY OFFICIAL DOCS.** The list response schema includes `notes`, and sample items contain it. [R4] |
| 11. Total-result count or returned-page count | **NOT ESTABLISHED.** The sample has `count == len(items)`, but the Orders page does not define response `count` as total matching rows or as page size. No total-result field is documented. [R4] |
| 12. Ordering | **NOT ESTABLISHED.** Examples appear in descending timestamps, but no ordering guarantee or sort parameter is documented. [R4] |
| 13. Snapshot consistency | **NOT ESTABLISHED.** No snapshot token or fixed-view guarantee is documented. [R4] |
| 14. Read-after-write visibility | **NOT ESTABLISHED.** The Create and Fetch pages give no visibility-latency guarantee. [R3], [R4] |
| 15. Eventual-consistency delay | **NOT ESTABLISHED.** No delay bound, polling rule, or convergence SLA was found on the reviewed Orders pages. [R3], [R4] |

There is no documented `has_more` field. The endpoint is offset-based.

## 8. F. Pagination completeness

Proposed traversal for later qualification: `count=100` with `skip=0,100,200,...`.

| Question | Finding |
| --- | --- |
| 1. Documented termination rule | **NOT ESTABLISHED.** Razorpay documents page size and offset but no `has_more`, next cursor, total count, or explicit terminal-page rule. [R4] |
| 2. Can fewer than 100 safely terminate? | **UNRESOLVED.** It is the conventional operational rule, but it is not documented as a completeness guarantee and depends on stable membership/order and a complete response. [R4] |
| 3. Exact multiple of 100 | **INFERENCE:** an implementation using the short-page rule must make one additional request and observe an empty page; otherwise it cannot distinguish exactly 100 remaining results from more. This is algorithmic reasoning, not provider documentation. |
| 4. Concurrent creation and offset shifts | **UNRESOLVED provider behavior; INFERENCE risk.** Without fixed ordering/snapshot semantics, concurrent creation can in principle shift offsets and produce duplicated or skipped IDs. [R4] |
| 5. Snapshot/cursor guarantee | **NOT ESTABLISHED.** [R4] |
| 6. Detect repeated IDs across pages | **INFERENCE:** yes. The observer can retain a set of Order IDs and flag any ID repeated across pages. Repetition is observation instability, not another mutation. This detects one failure pattern but cannot detect every skipped unseen Order. |
| 7. Assumptions needed for completeness | **UNRESOLVED pending engineering qualification.** At minimum: no concurrent unrelated Order creation/update affecting the relevant Test Mode account and time window; stable visibility during traversal; no deletion (none is documented); no notes mutation; valid time bounds; successful retrieval of every page including a terminal page; local de-duplication by Order ID; and a hostile test demonstrating the observer finds seeded boundary cases. |

An authoritative observer cannot claim completeness from documentation alone.
The likely engineering isolation condition is a dedicated or otherwise quiescent
Test Mode account during the observation window, with no concurrent unrelated
Order mutation, plus hostile pagination qualification. This is a required
condition, not an undocumented Razorpay guarantee.

## 9. G. Time window

**ESTABLISHED BY OFFICIAL DOCS:** Fetch All accepts integer Unix `from` and `to`
timestamps, and Orders include integer Unix `created_at`. [R3], [R4]

**UNRESOLVED:** the Orders pages do not explicitly define inclusive/exclusive
boundaries, ordering within a timestamp, or a clock-skew contract. Examples use
10-digit epoch values consistent with seconds, but the Orders parameter text
does not expressly state “seconds”; second-level granularity is therefore not
promoted to a guarantee. **NOT ESTABLISHED:** whether an Order that becomes
list-visible later necessarily retains its original `created_at` for window
queries, although `created_at` is described as the time the Order was created.
[R3], [R4]

**Candidate use:** a conservatively padded pre/post trial window may reduce
scanning, but only as a scope aid. The exact notes marker remains the identity
mechanism. Timestamps and incidental response ordering must never replace the
marker. Boundary records require overlap/padding and distinct-ID handling in
later qualification.

## 10. H. Idempotency and deduplication

**ESTABLISHED BY OFFICIAL DOCS:** Orders has a client-controlled deduplication
mechanism when `receipt` is supplied. The Create page says duplicate receipt
causes a `400`, calls receipt an idempotency key, and recommends fetching/reusing
the existing Order. This is reject-on-duplicate behavior, not a documented
header that replays the original success response. [R3]

**NOT ESTABLISHED:** no separate Orders idempotency header or documented
deduplication mechanism for receipt-less `POST /v1/orders` was found after the
targeted search recorded in §2. In particular, neither `X-Transfer-Idempotency`
nor payout idempotency applies to Orders:

- Payout documentation saves the first response and maps retries with the same
  payout idempotency key to one payout. It scopes that behavior to payout
  requests. [R8]
- Direct Transfers uses `X-Transfer-Idempotency` and explicitly says that
  idempotency is currently supported only on the Direct Transfers API. [R9]
- The Orders Create page documents no such header. [R3]

Correct conclusion: **no documented receipt-less Orders mechanism was
established after this search**. Incorrect conclusion: “Orders are
mathematically or inherently non-idempotent.” Repeated receipt-less Create
behavior remains an empirical qualification target.

## 11. I. SDK and hidden retries

**UNRESOLVED / UNKNOWN.** Official server-integration pages show SDK calls such
as `client.order.create(...)`, but the reviewed documentation does not establish
whether the server SDK transport automatically retries connection failures,
timeouts, 5xx responses, or 429 responses for Orders. Checkout payment-retry
options are a different client/payment concern and do not establish retries of
the server-side Create Order call. [R6]

A future engineering adapter should initially use a raw HTTP transport or a
fully audited pinned client with all automatic retries explicitly disabled.
Transport dispatch count must be observable. No SDK choice is made here.

## 12. J. Authentication and Test credential identity

| Question | Finding |
| --- | --- |
| Basic Auth semantics | **ESTABLISHED BY OFFICIAL DOCS:** every request uses `Authorization: Basic <base64(Key ID:Key Secret)>`; both Key ID and Key Secret are required. [R1] |
| Key roles | **ESTABLISHED BY OFFICIAL DOCS:** Key ID and Key Secret form the Basic Auth credential. Razorpay warns not to disclose the Key Secret and notes that only Key ID remains visible later in the Dashboard. [R1] |
| Test versus Live | **ESTABLISHED BY OFFICIAL DOCS:** mode-specific keys are generated separately; test keys are for test transactions and live keys for accepting live payments. [R1] |
| Machine-detectable Test key identity | **NOT ESTABLISHED as a universal contract.** An official widget example uses `rzp_test_XXXX00000XXXX`, but the authentication contract does not promise a prefix grammar, length, immutability, or that prefix inspection is sufficient validation. [R1], [R17] |

Later code must never persist, log, serialize, or place the Key Secret in
evidence. A future guard may treat an officially observed prefix as a secondary
defense only after hostile review, not as the sole mode guarantee.

## 13. K. Response and error evidence

| Question | Finding |
| --- | --- |
| Order ID | **ESTABLISHED BY OFFICIAL DOCS:** Create returns a unique `id`. Examples use `order_...`; **NOT ESTABLISHED** is a formal regex, fixed length, or permanent prefix guarantee. [R3] |
| Entity field | **ESTABLISHED BY OFFICIAL DOCS:** `entity` is `order`. [R3], [R4] |
| Status field | **ESTABLISHED BY OFFICIAL DOCS:** Create returns `status`; the initial documented value is `created`. [R3] |
| Structured error body | **ESTABLISHED BY OFFICIAL DOCS:** Create examples use an `error` object with `code`, `description`, `source`, `step`, `reason`, `metadata`, and sometimes `field`; endpoint-specific errors list HTTP status values. [R3] |
| Provider request/correlation header | **NOT ESTABLISHED.** No request-ID/correlation response header contract was found on the reviewed authentication, Create, Fetch, or integration pages. [R1], [R3], [R4], [R6] |
| Orders rate-limit status/headers | **NOT ESTABLISHED.** The Orders pages reviewed do not document a rate-limit header, `Retry-After`, or Orders-specific 429 contract. Other Razorpay product pages mentioning throttling do not transfer that contract to Orders. [R3], [R4] |

Evidence classification for future work:

- A successfully parsed Create response containing a unique Order ID,
  `entity: order`, and expected fields is direct provider acknowledgement of an
  Order resource. [R3]
- A list result containing that same ID and exact marker is remote-state
  observation. [R4]
- A duplicate-receipt error acknowledges that an Order with that receipt was
  already processed, but receipt is excluded from this candidate. [R3]
- **NOT ESTABLISHED:** an arbitrary 4xx, 5xx, timeout, disconnect, empty body, or
  parse failure proves non-execution. These outcomes must remain ambiguous
  unless the specific response contract establishes otherwise.

## 14. L. Cleanup and retention

**NOT ESTABLISHED:** no documented Order delete endpoint or cleanup action was
found. The Orders API overview lists create, fetch, payment retrieval, and notes
update; the Orders Dashboard page lists view, webhook, and report actions. This
is a search result, not a claim of physical impossibility. [R2], [R16]

**Candidate assessment:** retaining synthetic Test Mode Orders may be appropriate
as engineering or paper evidence because they contain no real payment and no
PII, but retention is not yet frozen. Persistent Orders also increase scan size
and can compromise offset-observer isolation. Any later protocol must define a
dedicated account or bounded run window, evidence retention, redaction, and
account-quiescence rules before data collection.

## 15. M. Customer API alternative

**ESTABLISHED BY OFFICIAL DOCS:** `POST /v1/customers` has `fail_existing`.
With the default value `1`, an existing Customer with the same details causes an
error; with `0`, Razorpay returns the existing Customer. The endpoint-specific
error section says matching contact or email triggers this behavior. [R10]

**Candidate verdict for Customer: NOT SUITABLE relative to Orders.** The
provider-level duplicate behavior directly suppresses or errors on repeated
matching creates, confounding measurement of resource multiplicity under
Request Replay. Changing customer identity on every retry would no longer be
exact request replay and would introduce synthetic personal-identity fields.
Customer is not selected merely because it resembles an earlier design.

## 16. N. Brief alternative-resource scan

- **Items:** `POST /v1/items` creates a non-payment catalog item, and Fetch All
  Items exists. However, the reviewed Create request has no notes field; a marker
  would have to occupy business fields such as name/description. Items are
  mutable and conditionally deletable, adding cleanup and disappearance paths.
  The documentation reviewed does not make receipt-less replay multiplicity or
  list snapshot semantics clearer than Orders. [R11], [R12], [R13]
- **Plans:** Plans accept notes, but also require recurring-billing semantics
  (`period`, `interval`, and an item). This is a more complex payment-domain
  mutation without an identified observation advantage. [R14]
- **Payment Links:** they are customer-facing payment artifacts and document a
  unique `reference_id`, recreating a uniqueness confound if used as identity.
  They also add link lifecycle/expiry/cancellation behavior. [R15]
- **Customers:** rejected for documented duplicate handling, as above. [R10]

**INFERENCE:** Orders remains the strongest candidate among this deliberately
small scan because Create is a simple Test Mode resource mutation, no Checkout
or payment attempt is required, receipt can be omitted, notes are present in
Create and list responses, and each Order has a distinct provider ID. It is not
yet qualified because receipt-less multiplicity, marker preservation,
read-after-write visibility, and exhaustive observation are not guaranteed.

## 17. Scientific suitability verdict

### SUITABLE FOR OFFLINE ADAPTER ENGINEERING

This verdict authorizes no implementation in this slice and does not select or
freeze Provider C. It means the public semantics are strong enough to design an
offline adapter/observer contract and hostile Test Mode qualification plan.
They are not strong enough to collect paper observations or to classify a
zero-match read as non-execution.

This verdict permits only synthetic/offline adapter implementation and testing.
It does not authorize a Razorpay API call; live Test Mode engineering
qualification requires a separate prospectively reviewed and hostile-audited
gate.

Basis:

- **Mutation multiplicity visibility:** distinct Order IDs make multiplicity
  observable if receipt-less replay actually creates multiple Orders; that
  behavior is still unqualified. [R3], [R4]
- **Marker persistence:** notes are accepted and returned, but exact preservation
  and immunity from later mutation require constraints and tests. [R3]-[R5]
- **Observation completeness:** `count`/`skip` permits enumeration, but no stable
  snapshot, total count, ordering, or termination guarantee is documented. [R4]
- **Isolation feasibility:** a dedicated/quiescent Test Mode account and padded
  bounded window appear feasible, but this is an engineering condition.
- **Retry/idempotency confounds:** receipt is a documented deduplication confound
  and must be absent; no separate receipt-less Orders mechanism was found. [R3],
  [R8], [R9]
- **Test Mode safety:** Test Mode is simulated, disallows customer payments, and
  uses no real money according to the cited docs. [R1], [R7]

Minimal likely design, entirely **unfrozen**:

**Mutation:** `POST /v1/orders` using Test Mode Basic Auth.

Potential fixed payload:

```json
{
  "amount": 200,
  "currency": "INR",
  "notes": {
    "UNFROZEN_SYNTHETIC_KEY": "UNFROZEN_UNIQUE_STUDY2_MARKER"
  }
}
```

The provisional `200` paise amount is deliberately above both phrasings on the
Create page and remains unfrozen. `receipt` is omitted. The payload contains no PII. No Checkout, payment attempt,
partial payment, offer, customer, transfer, or other optional feature is used.

**Observer:** `GET /v1/orders` in the same account/Test Mode scope, with a
conservatively bounded `from`/`to` window and exhaustive `count=100`,
`skip=0,100,200,...` traversal under a frozen quiescence condition. Match the
exact notes key/value locally and count **distinct Order IDs**.

Correct multiplicity concept:

- 0 distinct matching Orders;
- 1 distinct matching Order;
- 2 distinct matching Orders = 1 additional resource;
- 3 distinct matching Orders = 2 additional resources.

Repeated appearance of the same Order ID across pagination is observation
instability, not another mutation. A completed zero-match read must not prove
H0/`NOT_EXECUTED` until read-after-write visibility, time-window behavior, and
pagination completeness have passed hostile qualification.

## 18. Exact blockers and required hostile qualification

This reconnaissance is sufficient to permit offline adapter engineering. That
offline work is limited to synthetic implementation and testing and performs no
Razorpay provider call. Only after the offline adapter itself is frozen and has
survived hostile audit may a separately authorized, prospectively reviewed, and
hostile-audited Test Mode engineering qualification perform the minimum real
Razorpay calls needed to resolve empirical semantics gaps.

That Test Mode engineering qualification is not a Study 2 paper experiment, and
its engineering observations are not Study 2 paper observations. It must not
test the Replay versus Regeneration paper policies unless a later, separately
reviewed qualification protocol explicitly requires a synthetic ambiguity check
solely to validate instrumentation.

Before Razorpay can be selected and frozen as Provider C, and before **any**
Study 2 paper observation in GitHub, Google Sheets, Razorpay, or any other
external environment, the separately authorized and hostile-audited Test Mode
engineering qualification must resolve at least:

1. receipt-less exact replay behavior: prove whether identical valid Creates
   produce distinct IDs, fail, or deduplicate;
2. whether the smallest chosen fixed Test Mode INR amount is accepted reliably,
   resolving the page's `100` versus “greater than 100” wording;
3. exact notes marker round-trip behavior for the selected short ASCII encoding;
4. list visibility latency and a conservative polling/convergence bound after a
   successful Create and after an intentionally ambiguous transport outcome;
5. inclusive/exclusive `from` and `to` boundaries and safe padding;
6. actual ordering behavior without treating it as guaranteed;
7. terminal-page behavior, including 0, 1, 99, 100, 101, 199, and 200 matching
   boundary cases;
8. detection/handling of duplicate IDs, missing IDs, page drift, and concurrent
   unrelated creation; freeze an account-quiescence rule;
9. the meaning of response `count` and a completeness rule that does not assume
   it is a total;
10. raw transport retry behavior with retries disabled, dispatch counting, and
    timeout/disconnect fault injection;
11. response/error parsing, including loss after dispatch and proof that no
    generic error is misclassified as non-execution;
12. Test/Live credential guardrails without relying solely on an undocumented
    prefix contract, and proof that Key Secret is never persisted;
13. retention and dedicated-account/window strategy given no documented Order
    delete operation;
14. hostile audit of this evidence and a separate prospective Provider C
    selection/freeze record; and
15. freeze of the final cross-provider Study 2 protocol before any paper
    observation in any external environment.

Provider C must remain TBD until the required live Test Mode engineering
evidence is collected, audited, and frozen in a separate prospective selection
record. No Razorpay implementation should be treated as qualified before then.
No Study 2 paper collection may begin in any external environment until Provider
C and the final cross-provider protocol are frozen and hostile-audited.

## 19. Governance conclusion

No provider was added, no allocation changed, no candidate or contract code was
modified, and no protocol was frozen. The operator accessibility finding is
recorded separately from semantics qualification. Study 2 paper observations
remain zero.

Razorpay remains a candidate under semantics reconnaissance. Provider C remains
TBD until this evidence is hostile-audited and a separate prospective selection
record is frozen.

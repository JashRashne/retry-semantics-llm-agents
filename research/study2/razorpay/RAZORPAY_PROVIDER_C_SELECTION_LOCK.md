# Razorpay Study 2 Provider C selection

**LOCKED / FROZEN PROSPECTIVELY BEFORE STUDY 2 PAPER DATA**

**RAZORPAY SELECTED AS STUDY-2 PROVIDER C**

**PROSPECTIVE SELECTION ONLY**

**ENGINEERING EVIDENCE ONLY**

**NOT PAPER DATA**

**STUDY 2 PAPER OBSERVATIONS = 0**

**PAPER COLLECTION REMAINS BLOCKED**

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent
Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## 1. Selection decision

Select **Razorpay** prospectively for the **Study 2 external Provider C** slot
under `research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md`. This
selection record has survived hostile audit and prospectively freezes Razorpay
as the Provider C identity. It is not a frozen paper protocol or authorization
to collect observations. The amendment's 64-family allocation for Provider C
is unchanged.

The decision uses only the frozen, sanitized Phase 1, Phase 2, and Phase 3
engineering evidence named below. No GitHub or Google Sheets paper result was
available to influence selection; Study 2 paper observations remain exactly 0.
Historical Stripe work and the frozen Study 1 plan remain historical provenance
and are not rewritten by this decision.

## 2. Frozen evidence basis

| Phase | Frozen finding | Selection relevance |
| --- | --- | --- |
| 1 | One receipt-less Create Order received a validated acknowledgement for `order_TfBuv3iQHQrz9p`; the immediate, structurally completed Fetch All returned zero marker matches. Terminal `INCONCLUSIVE`, reason `observation_1_exact_set_not_observed`. | Deterministic mutation and the immediate-observer hazard. The zero is not H0 proof. |
| 2 | Direct fetch validated the original Order, including its exact marker and `created_at = 1790103825`. The *same* historical list query later returned that Order. Terminal `RESOLVED`, reason `later_list_visibility_established_under_original_window`. | Direct identity validation and time-varying list observability under a fixed query. |
| 3 | One exact receipt-less replay received a validated acknowledgement for distinct `order_TfMrnptToeHvTa`; direct fetch validated it. A prospectively bounded list schedule observed the exact two-resource set at scheduled +30. | Narrow replay multiplicity and bounded positive observation for this engineering case. |

The Phase 1 and Phase 2 historical page-query SHA-256 is
`9ab99f99af14704def4dac9f01768738829f21e827d77c0816275d940db28b5c`.
The original Order's provider `created_at` lies inside that frozen window.
These facts rule out an out-of-window timestamp for this particular Order as
the explanation of the Phase 1 miss; they do not establish its cause.

## 3. Mutation surface

The selected candidate case is Razorpay Test Mode `POST /v1/orders`, with the
frozen engineering request `amount = 200`, `currency = INR`, no `receipt`, and
`notes.retry_semantics_marker` as the correlation marker. The transport profile
was `httpx_httptransport_retries0_no_redirects_no_trust_env_v1`. The frozen
request can be constructed deterministically and its exact body and identity
were checked across the two engineering dispatches. Omitting `receipt` is
essential: this candidate does not depend on provider-side idempotency masking
through a receipt or other idempotency key.

## 4. Replay-semantics evidence

Phase 1 and Phase 3 recorded the same request-body SHA-256,
`cb288039706bb57fd06c7bdcd7ac50d644c1f160c245258aae2931a26b7dd7b4`,
and the same request-identity SHA-256,
`a5d313c36e10d726e194178e585fdb2257d732d28a719d7f4a2cf8b9c25a05ed`.
The original acknowledgement named `order_TfBuv3iQHQrz9p`; the single exact
replay acknowledgement named `order_TfMrnptToeHvTa`. The latter was directly
fetched and validated for ID, entity, amount, currency, null receipt, and exact
marker match. Phase 3's multiplicity terminal fact is
`DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED`. This establishes a distinct second
resource for **one frozen engineering replay**, not a general provider retry
rule or a paper Replay outcome. No ambiguous transport outcome or LLM recovery
policy was tested here.

## 5. Observation-semantics evidence

The marker correlated both Orders; exact acknowledged IDs could be directly
fetched and validated. Phase 1's immediate Fetch All missed the original.
Phase 2 later returned that same Order under the identical historical page
query, establishing time-varying list observability without measuring exact
visibility latency.

Phase 3 scheduled list observations at **0 / 5 / 30 / 120 / 600 seconds**.
The +0 and +5 observations each returned only the original Order. The +30
observation returned exactly the original and replay Orders, so the terminal
visibility fact is `EXACT_TWO_RESOURCE_SET_OBSERVED` and
`first_successful_scheduled_offset_seconds = 30`. The +120 and +600 rounds did
not run. This is the first successful *scheduled* offset, not an exact
visibility latency or a bound for other requests. All these list observations
remained `authoritative_completeness_qualified = false`.

## 6. Accessibility and Test Mode basis

The frozen Phase 1 plan records `environment = TEST_MODE_ENGINEERING`, a Test
Mode operator confirmation, `receipt = prohibited`, and zero paper
observations. The consumed engineering packages' locks and evidence record
successful Test Mode Order and GET operations. Thus the chosen mutation was
accessible for the controlled Test Mode engineering case without a real-money
payment or payment attempt. This is scoped to that case; it is not a claim about
Live Mode or every Razorpay product. No credential is recorded in this selection
document.

## Amendment preflight gate mapping

The six prospective conditions in
`research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` map to the
hash-verified semantics reconnaissance and frozen engineering record as follows:

| Gate | Assessment | Evidence and scope |
| --- | --- | --- |
| 1. Legitimate operator/account access from the researcher's jurisdiction | **PASS** | The researcher established legitimate Razorpay operator/account access from India prospectively before live engineering qualification, as recorded in the semantics reconnaissance. |
| 2. Sandbox/test credentials obtainable legitimately | **PASS** | Razorpay Test Mode credentials were legitimately obtainable and were used through the hardened interactive credential path for the engineering qualification. No credential is recorded here. |
| 3. No real-money requirement | **PASS** | The Test Mode Create Order qualification required no real-money payment or payment attempt. |
| 4. Required mutation API accessible in test/sandbox mode | **PASS** | Test Mode `POST /v1/orders` produced validated engineering acknowledgements for the original and exact replay Orders. |
| 5. Authoritative observation/reconciliation API available | **PASS WITH IMPORTANT SCOPE LIMITATION** | Provider-authoritative `GET /v1/orders/{id}` direct fetch and `GET /v1/orders` Fetch All surfaces were available and exercised. This passes the API-availability gate only; it does not qualify list completeness. |
| 6. Retry/idempotency semantics documented sufficiently | **PASS** | The hash-verified Razorpay semantics reconnaissance and controlled engineering evidence suffice to define prospectively the receipt-less Create Order mutation, correlation marker, exact-replay identity, transport policy, and observation limitations for this Provider C selection. They do not establish provider-wide retry semantics. |

For gate 5, direct fetch gives provider-authoritative positive identity
reconciliation **when an Order ID is known**. Fetch All is a
provider-authoritative API surface, but `authoritative_completeness_qualified`
remains `false`: zero matches do not prove absence. An acknowledgement-lost
mutation may leave the response Order ID unavailable, so direct fetch cannot
alone reconcile it. Final paper adjudication must use a prospectively frozen
bounded reconciliation policy and retain **INCONCLUSIVE** whenever the bounded
evidence cannot establish the required resource set.

## Status of the earlier reconnaissance checklist

The reconnaissance checklist in `research/study2/razorpay/RAZORPAY_SEMANTICS_RECONNAISSANCE.md` remains useful historical planning provenance, but its status was explicitly unfrozen and its unresolved paper-observer concerns remain carried forward.

Specifically:

1. `RAZORPAY_SEMANTICS_RECONNAISSANCE.md` is a committed, hash-pinned historical engineering-planning artifact, but it is explicitly labeled `DRAFT / NOT FROZEN`.
2. Its Section 18 15-item checklist was a provisional hostile-qualification planning list, NOT a frozen protocol amendment and NOT the controlling Provider-C selection contract.
3. The controlling prospective Provider-C selection gate is the six-condition gate in:
   `research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md`.
4. This selection record does NOT delete, rewrite, or pretend that every reconnaissance checklist item was resolved.
5. Frozen Phases 1–3 resolved the selection-critical empirical questions needed to apply the six amendment gates, including:
   - accepted Test-Mode mutation;
   - exact receipt-less replay multiplicity for the frozen case;
   - marker preservation;
   - direct positive resource reconciliation;
   - time-varying list observability;
   - a bounded positive two-resource observation;
   - no hidden mutation retry; and
   - hardened credential/transport handling.
6. Remaining reconnaissance concerns that are not established as general provider properties are explicitly carried forward into the still-unfrozen paper semantics contract/evaluator/protocol. These include, for example:
   - authoritative Fetch-All completeness remains false (`authoritative_completeness_qualified = false`);
   - exact general list boundary semantics are not claimed;
   - general ordering guarantees are not claimed;
   - the engineering schedule is not automatically paper methodology;
   - final account isolation/quiescence/window rules remain to be frozen; and
   - the final observer must retain INCONCLUSIVE when bounded reconciliation cannot establish the required set.
7. Therefore the older draft checklist is NOT being retrospectively declared satisfied in full.
8. Its unresolved collection-relevant items remain PAPER-COLLECTION BLOCKERS, not Provider-C identity blockers under the six-gate amendment.
9. This reconciliation is prospective:
   STUDY 2 PAPER OBSERVATIONS = 0.
10. No paper data influenced this governance reconciliation.

## 7. Known limitations

- Fetch All authoritative completeness is **not qualified**. A structurally
  completed list traversal and even an exact positive set do not prove that a
  zero-match list result means no mutation occurred.
- Immediate read-after-write visibility is not reliable enough for a single
  immediate Fetch All observer. The cause of the Phase 1 miss is unidentified.
- Phase 2's elapsed interval and Phase 3's successful +30 offset are not exact
  visibility latencies. No global latency bound, monotonicity, or general
  eventual-consistency guarantee was established.
- The replay result covers one request, account scope, marker, and Test Mode
  engineering execution. It does not establish provider-wide retry semantics.
- The engineering packages did not test a paper ambiguity injection, LLM
  Replay versus Regeneration arms, or paper outcome adjudication.

## 8. Required paper-observer constraints

The final Razorpay Study 2 observer **must not rely on a single immediate Fetch
All read**. Before paper collection, the provider-specific semantics contract,
scenario catalogue, manifest, evaluator, and any required provider-specific
analysis amendment must define and freeze an explicitly bounded observation
policy, including marker and scope isolation, list window and pagination rules,
scheduled reads or a justified alternative bound, terminal evidence, and how
missing or incomplete observations are classified. In particular, an immediate
zero-match read cannot be promoted to H0. Direct fetch of an acknowledged ID
can supplement reconciliation, but cannot be required to exist after a lost
acknowledgement. The evaluator must preserve an inconclusive path wherever
the evidence cannot establish the required resource set.

The Phase 3 **0 / 5 / 30 / 120 / 600 seconds** schedule is engineering support
for designing such a policy. **It is not adopted here as paper methodology.**
The final provider-specific protocol and evaluator must explicitly freeze
whatever bounded policy is chosen. This selection does not silently transfer
the engineering schedule into the paper experiment.

## 9. Remaining prerequisites before Study 2 collection

Provider C **selection does not by itself unblock paper collection**. Under
`research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md`, Provider C's
identity, semantics contract, scenario catalogue, manifest, evaluator, and any
provider-specific analysis amendment, together with the final cross-provider
Study 2 protocol, **MUST be frozen and hostile-audited before ANY Study 2 paper
observation** is collected in GitHub, Google Sheets, Razorpay, or any other
external Study 2 environment. This selection record has survived hostile audit
and prospectively freezes Razorpay as the Provider C identity. The final
observer and completeness/adjudication limits above must be resolved in those
prospective artifacts. This document neither implements nor freezes them.
The older `research/study2/CAPABILITIES_DRAFT.md` contains pre-selection
candidate language and must be superseded or updated prospectively when the
final Razorpay semantics contract and capability binding are built.

## 10. Explicit non-claims

This decision does **not** claim provider-wide non-idempotence, universal
duplicate creation on retry, an authoritative Fetch All completeness guarantee,
an exact 30-second visibility latency, a safe one-shot immediate observer, an
H0/H1 outcome, a paper Replay or Regeneration result, or authority to start
paper collection. It does not claim Stripe never existed in project history.
It does not revise Study 1, its frozen analysis plan, or historical Stripe
provenance.

## 11. Frozen provenance and hashes

Source `HEAD` and `origin/main` before the selection draft was prepared:
`a16dca1cb46cb6114ef82932bf8f86288facb3ce`; working tree was clean.

Pre-lock hostile-audited selection-draft SHA-256:
`e1c5725bd6521a5e9b93b40d2814d5e15ca5f2943102b86d337508516d6306c5`.

| Hash-verified provenance artifact | SHA-256 |
| --- | --- |
| `research/study2/razorpay/RAZORPAY_SEMANTICS_RECONNAISSANCE.md` (committed, labeled draft) | `b4acf4dc8a7bdfe150fbe6abe812c3508c18ff27566f219a651bd2e1377cd4ac` |
| `research/study2/razorpay/RAZORPAY_LIVE_QUALIFICATION_PHASE1_LOCK.md` | `2afc652fa636204613168e6ba5fd4640205c6728f8fb7e14eeb07c698425e551` |
| `research/study2/razorpay/RAZORPAY_PHASE2_READONLY_QUALIFICATION_LOCK.md` | `4fd765e4c404396eaaab2ef8dc73e8221f0dd63b3da3d385179f5671a49bc18f` |
| `research/study2/razorpay/RAZORPAY_PHASE3_REPLAY_VISIBILITY_LOCK.md` | `1d1d95a1e58a638cbf1fde7ebf0908ef26d41ff5693ccf85f9d644d31a3280fe` |
| `research/protocol/primary_create_v1_3_analysis_plan.md` | `23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88` |

All 20 sanitized artifacts in `research/study2/razorpay/evidence/phase1/`,
`phase2/`, and `phase3/` matched the per-artifact SHA-256 tables in their
respective locks at drafting. The frozen Phase 3 terminal facts are
`multiplicity_result = DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED`,
`visibility_result = EXACT_TWO_RESOURCE_SET_OBSERVED`,
`first_successful_scheduled_offset_seconds = 30`, and
`authoritative_completeness_qualified = false`.

## 12. Global collection gate

**STUDY 2 PAPER OBSERVATIONS = 0. PAPER COLLECTION REMAINS BLOCKED.**

The prospective Provider C identity is frozen as **Razorpay** in this
selection lock. No Phase 4, provider call, credential access, package
preparation, Test Mode action, paper observation, or final paper experiment
implementation is authorized or performed by this selection.

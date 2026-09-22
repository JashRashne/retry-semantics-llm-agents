# RAZORPAY PHASE-2 READ-ONLY QUALIFICATION — LOCKED

**ENGINEERING ONLY**

**READ-ONLY**

**ZERO MUTATIONS**

**ZERO POST REQUESTS**

**NOT PAPER DATA**

**STUDY 2 PAPER OBSERVATIONS = 0**

**PROVIDER C REMAINS TBD**

**DO NOT RERUN THE CONSUMED PACKAGE**

## Locked provenance

- Source commit: `57d882aadf6211f7ac9470b1e33597037af12421`
- Qualification ID: `9bff3a0a-2702-4d31-b053-b8110dffed31`
- Plan whole-file SHA-256: `799ccb57896c51806d358e82b5de8245f41d870e36783b9992f3e00c5d1d8f59`
- Canonical plan SHA-256: `d9a4f604ade100335734e5412c0966a45cdaa3a7f5278532c30008ce026704d3`
- Package-location binding: `35dd71212e71f9e80ba1b829d35e4d1b5e0c38b811e3c26b810a85dc195742a9`
- Source package: `/Users/jashrashne/Desktop/razorpay-phase2-readonly-57d882a`
- The package was consumed once. It must not be rerun. No cleanup was performed.

## Frozen sanitized evidence

The following five JSON files were copied byte-for-byte from the consumed package into `research/study2/razorpay/evidence/phase2/`. Their SHA-256 hashes match both source and copy.

| Artifact | SHA-256 |
|---|---|
| `direct_fetch.json` | `83dd1df9146cb24d9e345886d2181184acee8b646ec7ed83c90e4c9544cabe24` |
| `intent.json` | `ade787a3d4458cb73747c7bb98a3ec029e53b1e039026f01a569ea0ab69d21df` |
| `original_window_observation.json` | `2fcc06d94e1524b4fdfcfd6c049539ed23f114b04fd8b71ed796a27a528dd7cc` |
| `qualification_plan.json` | `799ccb57896c51806d358e82b5de8245f41d870e36783b9992f3e00c5d1d8f59` |
| `qualification_result.json` | `c853d7de813445d4c93bdc77c12f0a377a0713933275b827ebf141a9485fcf96` |

The `intent.json` artifact records a consumed, live engineering execution. The evidence is sanitized; it is not paper data.

## Direct-fetch result

`GET /v1/orders/:id` returned HTTP `200` and validated the existing Phase-1 Order:

| Field | Recorded value |
|---|---|
| Requested provider Order ID | `order_TfBuv3iQHQrz9p` |
| Returned provider Order ID | `order_TfBuv3iQHQrz9p` |
| Entity | `order` |
| Amount | `200` |
| Currency | `INR` |
| Receipt | `null` |
| Status | `created` |
| Attempts | `0` |
| Exact notes marker | `study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215` |
| Exact marker match | `true` |
| Provider `created_at` | `1790103825` (`2026-09-22T19:03:45Z`) |
| Credential-scope fingerprint | `5fcd0eb32375ef28ee232ad426a940ce06ee7b3f95281004c687aca964c123a6` |
| Validation reason | `validated` |

The frozen Phase-1 historical window was `from=1790103525` and `to=1790104125`. The provider `created_at` value is inside it: `1790103525 ≤ 1790103825 ≤ 1790104125`. It is exactly 300 seconds from each boundary. This is an arithmetic fact about this Order, not a general claim about Razorpay boundary semantics.

## Exact historical-query comparison

The Phase-1 immediate observation and Phase-2 later observation each requested page skip `0` with the same marker, credential-scope fingerprint, `from` timestamp, and `to` timestamp. Their page-query SHA-256 is identical:

`9ab99f99af14704def4dac9f01768738829f21e827d77c0816275d940db28b5c`

The frozen Phase-1 and Phase-2 plans also identify the same candidate adapter source hash, `82a974167cc11e3bd4a6a2d504811f479d68e1d18870c0bb987fb18d40e3a325`. Both observations therefore used the same recorded adapter semantics and query parameters.

| Observation | Phase 1 immediate | Phase 2 later |
|---|---|---|
| Recorded UTC | `2026-09-22T19:03:45.726783+00:00` | `2026-09-22T20:00:24.266167+00:00` |
| HTTP | `200` | `200` |
| Status | `structurally_completed_unqualified` | `structurally_completed_unqualified` |
| Pages requested / completed | `1 / 1` | `1 / 1` |
| Matching IDs | `[]` | `["order_TfBuv3iQHQrz9p"]` |
| Matching resource count | `0` | `1` |
| Additional matching resource count | `0` | `0` |
| Conclusion | `ZERO_MATCHES_READ_NOT_H0_PROOF` | `MATCHES_OBSERVED_UNQUALIFIED` |

The elapsed wall-clock time between the two recorded observations is **3398.539384 seconds**, or approximately **56 minutes 38.539 seconds**. There were no observations between them. This elapsed interval is **not** a measured visibility latency or a 56-minute visibility delay.

## Canonical Phase-2 result and limits

Terminal status: `RESOLVED`

Terminal reason: `later_list_visibility_established_under_original_window`

> The acknowledged Phase-1 Order was directly retrievable and a later execution of the same frozen historical Fetch All Orders query returned that exact Order, whereas the immediate Phase-1 execution of that query had returned zero marker matches.

This establishes time-varying list observability under the same frozen query. The literal hypothesis that the Phase-1 miss occurred because this Order's provider `created_at` lay outside the frozen original window is not supported: its timestamp lies inside that window, and the same historical query later returned the Order. The cause of the Phase-1 miss remains unidentified. Provider-side list/index visibility behavior or another time-varying Fetch All behavior remain possible explanations, not findings.

This result does **not** establish an exact visibility latency, a 56-minute visibility delay, Razorpay's internal indexing architecture, a general eventual-consistency guarantee, monotonic visibility, authoritative list completeness, an H0 or H1 paper outcome, Replay success or failure, or Provider C suitability by itself. It does not establish general timestamp or filter-boundary semantics.

## Exact traffic and scientific boundary

| Counter | Value |
|---|---:|
| Direct-fetch GET dispatches | 1 |
| Original-window GET dispatches | 1 |
| Provider-window GET dispatches | 0 |
| Total GET dispatches | 2 |
| Mutation dispatches | 0 |
| POST dispatches | 0 |

The provider-created-at-centered second list observation did not run because the exact original-window result resolved the diagnostic. There was no POST, mutation, polling, retry, automatic rerun, or cleanup.

`authoritative_completeness_qualified` remains `false`. Provider C selection remains `not_performed` and Provider C remains TBD. Study 2 paper observations remain exactly `0`. Receipt-less replay multiplicity remains **UNTESTED**. Phase 2 does not authorize paper collection.

## Secret audit

The five copied JSON files were scanned for raw Key ID, raw Key Secret, Authorization header, Basic credential, environment credential, and `rzp_test` or `rzp_live` credential text; none was found. The one-way credential-scope fingerprint is expected and allowed. No credentials were accessed to create this lock.

## Next prospective engineering problem — record only

1. Test whether an exact receipt-less replay of the frozen Phase-1 Create Order request creates a distinct second Razorpay Order.
2. Establish a defensible bounded list-visibility policy for the eventual Study 2 observer, because immediate list visibility was not established.

These questions may be combined in a separately designed engineering phase, but its design must be reviewed and frozen prospectively before any further mutation. This lock authorizes no additional provider call and implements no Phase 3 work.

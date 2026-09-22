# DRAFT / NOT FROZEN

**READ-ONLY ENGINEERING DIAGNOSTIC**
**ZERO MUTATIONS / ZERO POST REQUESTS**
**NO LIVE PHASE-2 CALL HAS YET BEEN PERFORMED**
**NOT PAPER DATA**
**PROVIDER C REMAINS TBD**
**STUDY 2 PAPER OBSERVATIONS = 0**

## Why this phase exists

Phase 1 produced a validated Create acknowledgement for `order_TfBuv3iQHQrz9p`, followed immediately by a structurally completed, zero-match Fetch All observation. Its list traversal did not establish authoritative completeness. The provider `created_at` was not retained, so Phase 1 did not establish the cause of the miss. Receipt-less multiplicity remains untested.

This draft implements an offline-tested, separately gated diagnostic. Implementation and tests perform no real provider call. It performs no mutation and does not choose Provider C.

## Future live sequence

1. Verify the frozen Phase-1 lock and six evidence-file hashes. Derive the exact Order ID, marker, original window, and credential-scope fingerprint from those files.
2. Prepare a plan-only package outside the repository after a clean-tree and `HEAD == origin/main` check. Bind that exact commit in the plan along with its package location, source hashes, httpx runtime, frozen evidence hashes, and canonical plan hash. Give the operator the exact persisted plan-file SHA-256.
3. Execution requires the explicit read-only flag, confirmation phrase, exact plan-file SHA-256, hidden interactive Test Mode credentials, and explicit Test Mode confirmation. The current credential fingerprint must match the Phase-1 fingerprint before any provider request.
4. Create `intent.json` atomically with `O_EXCL` and fsync. This consumes the package forever, including after a crash. A competing loser makes zero provider calls and writes no terminal result.
5. Directly fetch the existing Order with `GET /v1/orders/:id`. Validate HTTP 200, JSON object, ID, entity, amount 200, INR, null or absent receipt, present object notes with the exact marker, and nonnegative integer `created_at`. Record status and attempts without treating them as immutable identity.
6. Only after a valid direct fetch, run the frozen adapter's `GET /v1/orders` observer under the exact original Phase-1 window `1790103525..1790104125`, count 100 and page cap 2.
7. If that traversal structurally completes with exactly the expected Order, stop: `later_list_visibility_established_under_original_window`.
8. Only after a structurally completed zero-match original-window result, run one provider-created-at-centered window, `created_at ± 300` seconds, with validated nonnegative bounds, count 100 and page cap 2. Then stop.

Maximum provider dispatches: one direct GET plus two GETs for each list window, five total. There is no polling, automatic retry, rerun, third list strategy, cleanup, or POST route. Production uses `httpx_httptransport_retries0_no_redirects_no_trust_env_v1` and a finite timeout. Synthetic tests use `MockTransport` and hard socket guards.

## Interpretation

An exact match under the original historical window establishes later list visibility under that window. It does not establish an exact visibility latency or provider architecture. If only the provider-centered window finds the Order and provider `created_at` is outside the original window, `provider_timestamp_window_explains_phase1_miss` records a local-window explanation without claiming general boundary semantics. If `created_at` is inside the original window, `window_behavior_requires_further_review` records the unresolved discrepancy. If neither list returns the directly fetched Order, `direct_fetch_visible_list_visibility_not_established` records only that bounded diagnostic result. Malformed fetches, incomplete traversals, and unexpected extra marker-bearing Orders stop inconclusively.

The plan and sanitized evidence contain no raw Key ID, Key Secret, Authorization header, full unrelated provider response, or raw provider exception. `synthetic_test_execution` and `live_qualification_evidence` distinguish offline tests from a later separately authorized execution.

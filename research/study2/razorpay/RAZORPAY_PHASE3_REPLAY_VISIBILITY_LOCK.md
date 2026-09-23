# RAZORPAY PHASE-3 EXACT REPLAY / BOUNDED VISIBILITY QUALIFICATION — LOCKED

**ENGINEERING ONLY**

**ONE EXACT REPLAY MUTATION WAS PERFORMED**

**NO MUTATION RETRY**

**NOT PAPER DATA**

**STUDY 2 PAPER OBSERVATIONS = 0**

**PROVIDER C SELECTION HAS NOT YET BEEN PERFORMED**

**DO NOT RERUN THE CONSUMED PACKAGE**

**NO PHASE 4 IS AUTHORIZED BY THIS LOCK**

## Locked provenance

- Source commit: `9b5dac57741aa308316060c43ec737557209408c`
- Qualification ID: `7b272e21-0ca9-433c-88dc-1d93566eafc3`
- Plan whole-file SHA-256: `f90d5b04aa87c4f8d9eb4fa14c0e61e042da16384763ca9ce105d3652b5c1d6c`
- Canonical plan SHA-256: `8a6fa5270d9015991abbb4d4122fb65fb7447b355cb898a82e949bd2b3068a08`
- Package-location binding: `7b969bf05d64ecb5e8dacb7f069b5d583f0e7e8eae76f0f47015a6a3d66b9093`
- Source package: `/Users/jashrashne/Desktop/razorpay-phase3-replay-visibility-9b5dac5`
- Package consumption: consumed exactly once. It must not be rerun.
- Cleanup: unavailable and not performed.

## Frozen sanitized evidence

The following nine JSON files were copied byte-for-byte from the consumed package into `research/study2/razorpay/evidence/phase3/`. Their SHA-256 hashes match both source package and copied evidence:

| Artifact | SHA-256 |
|---|---|
| `baseline_observation.json` | `366842d1af767590c6676e9e7a152c244eb40e52bd543d474ef7fe9723366fa2` |
| `direct_fetch_replay.json` | `a48b52c475a67c30148e8efabb708e4fcb62ac0c94467abb7f23e6d78e25c2d6` |
| `intent.json` | `9c9cc2fdc5dd99eeb9c6789303b359fe4929fa49b39c7bce42ee459184ca3c99` |
| `qualification_plan.json` | `f90d5b04aa87c4f8d9eb4fa14c0e61e042da16384763ca9ce105d3652b5c1d6c` |
| `qualification_result.json` | `8c38c2f63a255ea2a3181601c9c5e92d799dca37ed9e210579ce97ac4c2e1e59` |
| `replay_mutation.json` | `8a3edeeb13a30a7672ef11b42ae4204b3cb8212979d0e170f84d640cf77de508` |
| `visibility_round_0.json` | `f0efb9a6264a1e3f879aeb609540ff451ed8213a0c91c7ab7741d7cd5e8f8546` |
| `visibility_round_5.json` | `b388f0b4c86decb2ab7e21f149b7509a5855ded40c75a2d845fa3f9129c58f56` |
| `visibility_round_30.json` | `cc6c44696c968f8fb496cc81169231b0fe9553d390bb32afe5345ff1ff4e209f` |

There are no `visibility_round_120.json` or `visibility_round_600.json` artifacts because observation resolved at offset +30. The `intent.json` artifact records a consumed, live engineering execution. The evidence is sanitized; it is not paper data.

## Exact replay identity

The Phase-3 replay mutation recorded the SAME frozen request-body hash and SAME frozen request-identity hash as Phase 1:

- `request_body_sha256`: `cb288039706bb57fd06c7bdcd7ac50d644c1f160c245258aae2931a26b7dd7b4`
- `request_identity_sha256`: `a5d313c36e10d726e194178e585fdb2257d732d28a719d7f4a2cf8b9c25a05ed`
- `marker`: `study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215`
- `amount`: `200`
- `currency`: `INR`
- `receipt`: absent / null under provider representation
- `credential-scope fingerprint`: `5fcd0eb32375ef28ee232ad426a940ce06ee7b3f95281004c687aca964c123a6`
- `transport profile`: `httpx_httptransport_retries0_no_redirects_no_trust_env_v1`

## Baseline observation

Prior to replay dispatch, baseline observation verified the pre-existing environment state under the fixed window:

- Matching IDs exactly: `["order_TfBuv3iQHQrz9p"]`
- Matching resource count: `1`
- HTTP status: `200`
- Status: `structurally_completed_unqualified`
- Authoritative completeness: `false`
- Page query SHA-256: `492b22692f59c88833be18a5ba610125eba7ad3d582752f308b9516e57df22c1`

The baseline list observation returned only the single original Phase-1 Order, satisfying the prerequisite singleton observation constraint to proceed with the replay POST.

## Replay mutation

- Original Order: `order_TfBuv3iQHQrz9p`
- Replay acknowledged Order: `order_TfMrnptToeHvTa`
- Replay acknowledgement:
  - Classification: `ACKNOWLEDGED_CREATE`
  - `acknowledgement_valid`: `true`
  - HTTP status: `200`
  - `dispatch_started`: `true`
  - `local_transport_completed`: `true`

### Canonical multiplicity result

`DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED`

Allowed narrow conclusion:
"One exact receipt-less replay of the frozen Create Order request received a validated acknowledgement for a distinct Razorpay Order ID."

Do NOT generalize beyond this engineering case.

## Direct fetch

Strict identity direct fetch of the acknowledged replay Order ID succeeded and validated:

- Provider Order ID: `order_TfMrnptToeHvTa`
- Requested ID: `order_TfMrnptToeHvTa`
- Entity: `order`
- Amount: `200`
- Currency: `INR`
- Receipt: `null`
- Exact marker match: `true`
- HTTP status: `200`
- Provider `created_at`: `1790142385`
- Validation reason: `validated`

## Fixed observation window

- Execution anchor: `1790142380`
- `observation_from`: `1790103525`
- `observation_to`: `1790142680`
- Provider `created_at`: `1790142385`

Timestamp arithmetic:
`1790103525 <= 1790142385 <= 1790142680`

The replay Order's `provider_created_at` (`1790142385`) is exactly 5 seconds after the execution anchor (`1790142380`) and 295 seconds before the frozen upper bound (`1790142680`).

This establishes only that the replay resource's provider-created timestamp was inside the prospectively frozen list filter. Do not generalize timestamp semantics.

## Visibility rounds

All list observations used page query SHA-256:
`492b22692f59c88833be18a5ba610125eba7ad3d582752f308b9516e57df22c1`

- **Scheduled +0** (`visibility_round_0.json`):
  - Matching IDs: `["order_TfBuv3iQHQrz9p"]`
  - Matching resource count: `1`
- **Scheduled +5** (`visibility_round_5.json`):
  - Matching IDs: `["order_TfBuv3iQHQrz9p"]`
  - Matching resource count: `1`
- **Scheduled +30** (`visibility_round_30.json`):
  - Matching IDs exactly the two expected resources: `["order_TfMrnptToeHvTa", "order_TfBuv3iQHQrz9p"]`
  - Matching resource count: `2`
  - Additional matching resource count: `1`

No +120 round ran.
No +600 round ran.

Terminal `first_successful_scheduled_offset_seconds = 30`.

This means: the exact two-resource set was observed at the +30-second scheduled observation. It does NOT mean Razorpay visibility latency is 30 seconds. Do not estimate an exact transition time.

## Terminal result

- `status`: `RESOLVED`
- `reason`: `exact_two_resource_set_observed`
- `multiplicity_result`: `DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED`
- `visibility_result`: `EXACT_TWO_RESOURCE_SET_OBSERVED`
- `authoritative_completeness_qualified`: `false`
- `provider_c_selection`: `not_performed`
- `paper_observations`: `0`

## Provider traffic and dispatch counters

Canonical terminal counters:

| Counter | Value |
|---|---:|
| `baseline_get_dispatches` | 1 |
| `direct_fetch_get_dispatches` | 1 |
| `visibility_get_dispatches` | 3 |
| `total_get_dispatches` | 5 |
| `mutation_dispatch_attempts` | 1 |
| `mutation_dispatches` | 1 |
| `post_dispatches` | 1 |
| `visibility_rounds_attempted` | 3 |
| `visibility_rounds_completed` | 3 |

There was:
- 1 replay POST
- 5 total GET requests
- 1 total mutation dispatch

There was:
- No mutation retry.
- No HTTP retry.
- No second replay POST.
- No automatic rerun.
- No cleanup mutation.
- No polling outside the frozen schedule.

## Stage counter note

Individual visibility-round artifacts may show `visibility_rounds_completed` before the current round is counted complete. The terminal `qualification_result.json` contains the final counters:
- `visibility_rounds_attempted = 3`
- `visibility_rounds_completed = 3`

Evidence artifacts must not be rewritten.

## Scientific interpretation

### Allowed

For this frozen engineering case:
1. Exact receipt-less request replay produced a separately acknowledged Order;
2. That replay Order was independently directly retrievable and validated;
3. Its provider-created timestamp lay inside the frozen list window;
4. The +0 and +5 scheduled list observations returned only the original Order;
5. The +30 scheduled list observation returned exactly both expected Orders.

### Explicit non-claims

Do NOT claim:
- General Razorpay retry semantics;
- Provider-wide non-idempotence;
- Exact 30-second visibility latency;
- Authoritative Fetch-All completeness;
- Monotonic list visibility as a global property;
- Paper Replay success/failure;
- Study-2 evidence;
- Provider C has already been formally selected.

## Global state

Razorpay engineering qualification questions needed for candidate evaluation are now resolved sufficiently to proceed to a separate Provider-C selection step.

- Do NOT create Phase 4.
- Provider C remains `not_performed` in this lock.
- Study-2 paper observations remain exactly `0`.
- No Study-2 paper collection is authorized by this task.

## Secret audit

The nine copied JSON files were scanned for raw Key ID, raw Key Secret, Authorization header, Basic credential, environment credential, and `rzp_test` or `rzp_live` credential text; none was found. The one-way credential-scope fingerprint is expected and allowed. No credentials were accessed to create this lock.

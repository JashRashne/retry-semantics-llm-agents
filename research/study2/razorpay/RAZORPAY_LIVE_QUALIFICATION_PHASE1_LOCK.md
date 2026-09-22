# RAZORPAY LIVE ENGINEERING QUALIFICATION — PHASE 1 LOCK

**ENGINEERING ONLY**

**NOT PAPER DATA**

**STUDY 2 PAPER OBSERVATIONS = 0**

**PROVIDER C REMAINS TBD**

**DO NOT RERUN THIS CONSUMED PACKAGE**

## Locked provenance

- Source commit: `032fc7b15e4ed3b6e943f9661e41e385b0e0c778`
- Qualification ID: `949acbae-5459-444f-ab58-acdf6c30f73c`
- Plan-file SHA-256: `1560f11a0b0d3fb69a143e4099e7e4c50e5ac237acc1ffb5d9a5525ae74138ca`
- Canonical plan SHA-256: `757ad203cab264a81028f8a0fcf635457eb1f548622f0630aabc6a6a5e4ae08c`
- Marker: `study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215`
- Package consumption: consumed exactly once; it must not be rerun.
- Cleanup: unavailable and not performed.
- Retention: the original Test Mode Order remains retained and its notes were
  not subsequently changed by this qualification.

## Locked sanitized evidence

The files under `research/study2/razorpay/evidence/phase1/` are byte-for-byte
copies of the six sanitized artifacts from the consumed package.

| Artifact | SHA-256 |
|---|---|
| `baseline_observation.json` | `b7ff240542febde3255e49fd4d90179374b6b5404ef6d7190392a1f3e6fa1376` |
| `intent.json` | `9a4d5be20bf73a936ba8971f00a56a92c7b61d7badc21cf2b6841a656966503c` |
| `mutation_1.json` | `5393ee65d8a82db38e7190e516923c02a25d13f8cea23c4e8ec7a790ff06de2a` |
| `observation_1.json` | `a55f439d9cf383c0b6df7f760d4207c08efb6992feca9b2902ab664cbe2640f4` |
| `qualification_plan.json` | `1560f11a0b0d3fb69a143e4099e7e4c50e5ac237acc1ffb5d9a5525ae74138ca` |
| `qualification_result.json` | `5b3491664412712c1c77cbbab79dc248a81b7efafab916521f572ea6473d77c4` |

## Canonical Phase 1 facts

### Baseline

- HTTP status: `200`
- Status: `structurally_completed_unqualified`
- `pages_requested = 1`
- `pages_completed = 1`
- `matching_order_ids = []`
- `matching_resource_count = 0`
- Conclusion: `ZERO_MATCHES_READ_NOT_H0_PROOF`

The baseline zero is an engineering collision/precondition result. It is not
experimental evidence.

### Mutation 1

- HTTP status: `200`
- Classification: `ACKNOWLEDGED_CREATE`
- `acknowledgement_valid = true`
- `dispatch_started = true`
- `local_transport_completed = true`
- Provider Order ID: `order_TfBuv3iQHQrz9p`
- Request body SHA-256:
  `cb288039706bb57fd06c7bdcd7ac50d644c1f160c245258aae2931a26b7dd7b4`
- Request identity SHA-256:
  `a5d313c36e10d726e194178e585fdb2257d732d28a719d7f4a2cf8b9c25a05ed`

### Observation 1

- HTTP status: `200`
- Status: `structurally_completed_unqualified`
- `pages_requested = 1`
- `pages_completed = 1`
- `matching_order_ids = []`
- `matching_resource_count = 0`
- Conclusion: `ZERO_MATCHES_READ_NOT_H0_PROOF`
- `authoritative_completeness_qualified = false`

### Terminal result and exact counts

- Status: `INCONCLUSIVE`
- Reason: `observation_1_exact_set_not_observed`
- Mutation dispatches: `1`
- Mutation dispatch attempts: `1`
- GET dispatches: `2`
- Baseline observation sequences: `1`
- Post-create observation sequences: `1`

There was no second CREATE, `mutation_2.json`, `observation_2.json`, polling,
mutation retry, automatic rerun, ambiguity injection, or paper observation.

## Client-side timing evidence

- Mutation 1 `recorded_utc`: `2026-09-22T19:03:45.054940+00:00`
- Observation 1 `recorded_utc`: `2026-09-22T19:03:45.726783+00:00`
- Difference between these client-side recording timestamps: approximately
  `0.672` seconds.
- Observation 1 `from_timestamp`: `1790103525`
- Observation 1 `to_timestamp`: `1790104125`

This is client-side evidence only and does not establish a Razorpay visibility
latency. The provider-side Order `created_at` value was not persisted in Phase
1 evidence.

Consequently, Phase 1 does not distinguish among list/index visibility delay,
time-window or filter semantics, provider timestamp behavior, or another Fetch
All representation/indexing behavior. This lock selects no explanation among
them.

## Scientific interpretation

The frozen receipt-less Create Order request received a validated successful
acknowledgement, but the immediately following structurally completed Fetch All
Orders observation did not return the marker-bearing Order. Immediate
read-after-write observability through the candidate list observer was therefore
not established in Phase 1.

This does not establish that the mutation was absent, that Create failed, that
the Order was deleted, that Fetch All is unusable, that Request Replay fails, or
that multiplicity is one. It does not justify rejecting Provider C. Receipt-less
multiplicity remains **UNTESTED** because the gate correctly blocked CREATE 2.

## Prospectively reviewed next diagnostic — record only

No next-phase behavior is implemented or authorized by this lock. A separately
reviewed next phase should be read-only and reuse:

- Order ID: `order_TfBuv3iQHQrz9p`
- Marker: `study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215`

It should first distinguish direct resource visibility from list visibility
before any second mutation. Prospective questions are:

1. Can the documented `GET /v1/orders/:id` retrieve the acknowledged Order?
2. Does the direct resource return the exact marker?
3. What provider-created `created_at` value does it return?
4. With a list window derived from that provider-created timestamp, does
   `GET /v1/orders` return the same Order?
5. If not, what separately reviewed bounded visibility procedure is justified?

No call answering any of these questions was made while creating this lock.

## Secret audit

The six locked JSON files contain no raw Key ID, raw Key Secret, Authorization
header, Basic credential, or environment credential value. The evidence does
contain the expected one-way credential-scope fingerprint; that value is
allowed and is not a raw credential.

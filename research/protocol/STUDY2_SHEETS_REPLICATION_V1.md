# Sheets post-incident replication V1

Status: prospective implementation prepared 2026-09-28. The research owner
explicitly requested a fresh, separately labelled replication while preserving
the failed primary. No live replication has been run by this engineering task.
This document and the exact code must be committed before plan preparation.
Execution requires the operator's explicit replication and writer-exclusion flags.
This is operator-reviewed replication governance; it claims no independent audit.

## Historical incident and reporting

Preserve `study2-sheets-primary-20260928-003851` and its original manifest,
readiness, and authorization. Its 128 projections contain 64 H0 policy entries
and 64 H1 constructor acknowledgement rejections; 128 remaining arms were
skipped as family-invalidated. The faulty collector supplied an already-validated
acknowledgement flag to a validator requiring unvalidated transport facts.
The fix was committed at `0761929`; the old primary remains closed. No failed
primary observations are replaced, pooled into this replication, or erased.

This replication is descriptive external-validity evidence, identified as
`POST_INCIDENT_REPLICATION_NOT_PRIMARY_REPLACEMENT`. Report the incident,
post-incident timing, changes below, and all exclusions in the paper.

## Scientific design retained

Copy all 64 families, task text, model configuration (DeepSeek V4.1 Flash on
Fireworks), model tools, seeds, balanced serial order, H0/H1 definitions,
three-action/four-model-call budget, and the OBS-1 single final GET from the
frozen Sheets manifest. Generate one eligible original per family and share
that assistant message across its four arms. Scope, credentials, arm markers,
and hidden-world metadata never enter model messages. Exact replay uses the
stored arm request without a further model call. There is no provider-side
idempotency mechanism or hidden mutation retry.

Create a fresh private spreadsheet with 256 isolated 100-by-3 tabs and new
namespace-derived markers. No operator-provided old spreadsheet is accepted.
A second, separate four-tab spreadsheet is exclusively for engineering controls.

## Prospective repairs and operational differences

* Constructor acknowledgements begin unvalidated; certify H1 from raw success
  acknowledgement plus a complete exact-one read before policy entry.
* Pre-policy blank checks use the existing precollection blank validator,
  including Google's omitted empty-data representation. Experimental final
  observations and model reads retain the stricter existing grid validator:
  absent required data remains incomplete, never an invented missing effect.
* Validate complete model argument schemas; do not silently drop extra fields.
  Unknown/invalid arguments consume an action and return a neutral tool error.
  Multiple simultaneous calls or duplicate call IDs terminate as invalid output.
  A fourth attempted action terminates at the budget without dispatch.
  Model infrastructure errors remain inconclusive, with durable model evidence.
* A complete final read showing fewer rows than the acknowledged mutation count
  or a prior authoritative read is a causal-ledger contradiction: mark it
  inconclusive and stop, rather than treating disappearing rows as model failure.
* Never certify a read with a recorded transport error, even if partial bytes
  happen to parse. Transport uncertainty does not authorize resending a write.
* Pace all Sheets request starts at least 1.1 seconds apart. Google's published
  default quota is 60 read and 60 write requests/minute/user/project:
  https://developers.google.com/workspace/sheets/api/limits . The single serial
  process stays below both limits if the operator has no competing traffic.
  Pacing is prospective; 401/403/429 stop the run without retry/backoff/replay.
* OAuth uses the existing desktop `drive.file` acquisition, with no bearer or
  refresh-token persistence. Acquire again only outside family execution when
  less than 2100 seconds remain. Check the same OAuth app configuration, Drive principal and sole-owner
  ACL after reacquisition. Keep the operator present for browser consent.
  Per family: at most 17 model requests at 60 seconds, 20 provider requests at
  30 seconds, plus pacing/local processing; 2100 seconds is a conservative
  admission reserve, not a guarantee against a suspended process. A per-request
  lifetime check stops before dispatch when less than 40 seconds remain.
* Stop on a failed baseline/constructor, model infrastructure failure, provider
  prohibition, evidence failure, ineligible original, or unexpected exception.
  Do not spend the remaining sample after an apparent systemic failure. Keep
  incomplete runs separate and disclose missing observations. No refill,
  outcome-selected restart, same-plan retry, or process resume is implemented.

## Pre-data gates and provenance

Before network access: require clean committed source, a matching canonical
plan, a new external evidence directory, an unconsumed plan, a valid local
OAuth client configuration, a model API key, and the operator flags. Persist an
exclusive plan-consumption record before OAuth. Freeze source hashes and the
historical manifest digest; write a bound replication manifest once the new
spreadsheet ID is known, before any experimental append.

Before experimental collection: execute deterministic engineering controls
through the actual collector, HTTP transport, acknowledgement parser and final
state evaluator. Expected results: H0 replay exactly one; H1 replay duplicate;
H0 scripted regeneration append exactly one; H1 scripted regeneration read then
finish exactly one. These scripted controls are not model observations. Also
perform one real pre-data model original-generation capability call. Record
all control evidence separately. Require the same identifiable sole owner,
exact complete topology, and all 256 blank baseline reads. The operator attests
no external writers, scripts, editing, or automation; API ACL alone cannot
establish absence of owner-driven automation.

No generated receipt calls these gates an independent audit. Any additional
independent review can inspect the committed code and prepared plan before run.

## Completion and later analysis

A completed run has `run-summary.json` with `COMPLETED`, 256 projections, a
separate collection directory, its own manifest, and a SHA-256 inventory.
`verify` checks the inventory and existing strict projection loader. Completion
means the schedule finished, not that every outcome is correct or evaluable.
Inconclusive observations and invalid-model behavior remain in the record.
A stopped run has `STOPPED_NO_RESUME` and exits nonzero. A killed process with no
summary is incomplete. Never interpret absent arms as successful/missing effects.

Later analyze only this run's bound manifest and collection directory. Retain
paired H0/H1 denominators, complete-family interaction eligibility, uncertainty,
and exclusions. Do not give the analysis CLI the old primary manifest or mix
qualification controls into the 256 arms. GitHub/Razorpay collection and joint
analysis are separate subsequent work, as requested by the research owner.

# Protocols, results, and evidence

This directory preserves protocols, experiment records, and retained result summaries. Historical documents describe decisions at their original study stage; later amendments record subsequent collection and analysis.

## Contents

| Path | Purpose |
| --- | --- |
| [`protocol/`](protocol/) | Study protocols, amendments, analysis plans, and evidence schemas |
| [`results/STUDY1_RESULTS_LOCK.md`](results/STUDY1_RESULTS_LOCK.md) | Immutable controlled-study outcomes and interpretation boundaries |
| [`baselines/no_model/PROTOCOL.md`](baselines/no_model/PROTOCOL.md) | Deterministic verify-before-retry policy |
| [`baselines/no_model/RESULTS.md`](baselines/no_model/RESULTS.md) | Reference results, audit summary, and archive hashes |
| [`baselines/no_model/`](baselines/no_model/) | Frozen schedules, collection/deployment locks, and audit metadata |
| [`study2/`](study2/) | Provider semantics, manifests, qualification evidence, and operational history |

## Available records

The repository includes protocols, schemas, provider manifests, readiness evidence, locked summaries, and the deterministic-reference result record. Manuscripts, bibliography, presentation figures/tables, publication CSVs, and editorial material are stored separately.

Some raw collections, sealed run archives, and canonical analysis packages are also outside this repository. Recorded absolute paths describe the original execution environment and will not resolve in a fresh clone. A hash identifies an archive but is not a download location. The checkout supports offline tests and inspection of the supplied research records; it does not supply every input needed to rerun every historical analysis from raw traces.

## Study boundaries

- Study 1A is the original controlled experiment; Study 1B is a separate replication after a hosted-model transition.
- GitHub records preserve the original collection, continuation, and unknown outcome.
- Sheets findings use the valid fresh replication; the invalidated first collection remains in the incident history.
- Razorpay attempts stopped early and are not completed external validation cohorts.
- The deterministic reference has separately collected cohorts and is not an additional paired arm of the historical comparison.

Frozen protocols, identities, evidence hashes, and result records are retained verbatim. Historical source-file references may point to separately retained manuscript material. Files named `DRAFT`, qualification records, and operator runbooks may be historical inputs to those records; their names do not make them current execution instructions.

## Running code

See the [root setup instructions](../README.md#setup-and-offline-tests) for offline tests. Analysis entry points under [`../scripts/`](../scripts/) require corresponding stored run directories. Historical operational commands target dedicated study resources; new live experiments require fresh scopes and a separate study plan.

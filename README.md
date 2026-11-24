# Retry Semantics for LLM Agents

Code, protocols, and experiment records for studying recovery after ambiguous outcomes of state-mutating LLM agent tool calls.

The implementation compares **Exact Replay**, which redispatches a stored request, with **bounded LLM Regeneration**, which returns recovery control to a model. It also includes a deterministic **verify-before-retry** controller. Correctness is evaluated against final system state.

Environments include controlled support tickets and adapters for GitHub, Google Sheets, and Razorpay test-mode experiments. The manuscript and publication assets are kept outside this public repository.

## Setup and offline tests

Requires Python 3.11 or later. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

Alternatively, use the pinned environment:

```sh
uv sync --extra dev --frozen
uv run --extra dev --frozen python -m pytest -q
```

The tests use offline fixtures and mocked provider transports; provider credentials are not required. Some historical preservation tests require original local archives or frozen manuscript files that are not distributed in this checkout. OAuth transport tests open local loopback sockets and need that permission from the execution environment. Those historical/environment checks can fail on a fresh clone or in a restricted sandbox.

## Repository guide

| Path | Contents |
| --- | --- |
| [`src/retry_semantics/`](src/retry_semantics/) | Recovery policies, controlled environment, model/provider adapters, collection, and analysis code |
| [`tests/`](tests/) | Offline tests and protocol coverage documentation |
| [`scripts/`](scripts/) | Collection, qualification, audit, and analysis entry points |
| [`research/protocol/`](research/protocol/) | Versioned protocols, amendments, analysis plans, and evidence schemas |
| [`research/results/`](research/results/) | Locked controlled-study outcome record |
| [`research/baselines/no_model/`](research/baselines/no_model/) | Deterministic-controller protocol, results, and frozen metadata |
| [`research/study2/`](research/study2/) | Provider semantics, manifests, qualification evidence, and collection history |
| [`research/README.md`](research/README.md) | Research records and reproducibility scope |

## Reproducibility scope

This checkout includes implementation code, frozen protocols and manifests, and retained result summaries. Original traces, sealed run archives, some analysis packages, and manuscript/publication assets are stored separately. Historical archive hashes and absolute paths identify evidence; they do not make external files available in a fresh clone.

The collection scripts preserve the original study's dedicated scopes and one-shot execution rules. New live experiments require fresh resources, credentials, and a separate study plan. Hosted model identifiers document past experiments and do not guarantee present availability.

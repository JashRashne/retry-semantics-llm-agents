#!/usr/bin/env python3
"""Explicitly gated GitHub engineering smoke. NEVER paper data.

Run from the repository with PYTHONPATH=src .venv/bin/python
scripts/smoke_study2_github.py. No dotenv loading, retries, polling or cleanup.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from retry_semantics.study2.github_adapter import (
    EngineeringTrace, GitHubConfig, GitHubEngineeringAdapter, GitHubEngineeringError,
)

BANNER = 'ENGINEERING VALIDATION — NOT PAPER DATA'
REQUIRED_ENV = (
    'STUDY2_GITHUB_TOKEN', 'STUDY2_GITHUB_OWNER', 'STUDY2_GITHUB_REPO',
    'STUDY2_GITHUB_API_BASE_URL', 'STUDY2_GITHUB_API_VERSION',
)
OUTPUT = Path(__file__).resolve().parents[1] / 'research/study2/engineering/github/live'


def trace_artifact(trace: EngineeringTrace) -> dict:
    value = asdict(trace)
    value['attempt_count'] = trace.attempt_count
    for attempt in value['attempts']:
        # Lossless bytes, rather than pretending reserialized JSON is wire identity.
        attempt['request']['body_hex'] = attempt['request'].pop('body').hex()
    return value


def run_smoke(config: GitHubConfig, output: Path) -> tuple[Path, bool]:
    """One creation, then one full traversal; gate also guards direct invocation."""
    expected_env = dict(zip(REQUIRED_ENV, (
        config.token, config.owner, config.repository, config.api_base_url, config.api_version,
    )))
    if (os.environ.get('STUDY2_GITHUB_LIVE_ENGINEERING') != '1'
            or any(os.environ.get(name) != value for name, value in expected_env.items())):
        raise ValueError('live engineering opt-in and matching runtime configuration required')
    marker = 'ENGINEERING-ONLY-' + uuid.uuid4().hex
    title = f'Engineering content round-trip {marker}'
    body = f'{BANNER}\n{marker}\nControlled raw body: café 🚀\nMarkdown **test**, quote " and slash \\.\n'
    artifact = {
        'classification': BANNER,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'target': {'api_base_url': config.api_base_url, 'owner': config.owner,
                   'repository': config.repository, 'api_version': config.api_version},
        'engineering_marker': marker,
        'expected_title': title, 'expected_body': body,
        'mutation_trace': None, 'observation_trace': None,
        'controlled_content_round_tripped': False,
        'exactly_one_matching_distinct_resource': False,
        'matching_distinct_identities': [], 'provider_warnings_errors': [],
    }
    # Ensure the output location is writable before causing the remote side effect.
    output.mkdir(parents=True, exist_ok=True)
    path = output / f'github-engineering-{marker}.json'
    client = GitHubEngineeringAdapter(config)
    try:
        created = client.create_issue(title=title, body=body)
        artifact['mutation_trace'] = trace_artifact(created.trace)
        # Deliberately discard create response: discovery uses pre-dispatch content.
        del created
        observed = client.observe_issues()
        artifact['observation_trace'] = trace_artifact(observed.trace)
        matches = observed.matching(lambda item: marker in item.title or marker in (item.body or ''))
        artifact['matching_distinct_identities'] = [item.identity for item in matches]
        artifact['exactly_one_matching_distinct_resource'] = len(matches) == 1
        artifact['controlled_content_round_tripped'] = bool(matches) and all(
            item.title == title and item.body == body for item in matches)
        if not artifact['exactly_one_matching_distinct_resource']:
            artifact['provider_warnings_errors'].append('expected_one_matching_distinct_resource')
        if not artifact['controlled_content_round_tripped']:
            artifact['provider_warnings_errors'].append('controlled_content_not_preserved')
    except GitHubEngineeringError as error:
        key = 'mutation_trace' if error.trace.operation == 'create_issue' else 'observation_trace'
        artifact[key] = trace_artifact(error.trace)
        artifact['provider_warnings_errors'].append(error.category)
    for key in ('mutation_trace', 'observation_trace'):
        if artifact[key] is not None:
            for attempt in artifact[key]['attempts']:
                for name, value in attempt['response_metadata']:
                    if name in ('warning', 'deprecation', 'sunset'):
                        artifact['provider_warnings_errors'].append({'header': name, 'value': value})
    artifact['passed'] = (artifact['controlled_content_round_tripped']
                          and artifact['exactly_one_matching_distinct_resource'])
    encoded = json.dumps(artifact, ensure_ascii=False, indent=2) + '\n'
    if config.token in encoded:
        # No raw provider messages are ever written; this is defense in depth.
        raise ValueError('refusing engineering artifact containing authentication')
    with path.open('x', encoding='utf-8') as stream:
        stream.write(encoded)
    return path, artifact['passed']


def main() -> int:
    if os.environ.get('STUDY2_GITHUB_LIVE_ENGINEERING') != '1':
        print('LIVE GITHUB ENGINEERING SMOKE NOT RUN: explicit opt-in absent')
        return 2
    if not all(os.environ.get(name) for name in REQUIRED_ENV):
        print('LIVE GITHUB ENGINEERING SMOKE NOT RUN: required runtime configuration absent')
        return 2
    try:
        config = GitHubConfig(
            api_base_url=os.environ['STUDY2_GITHUB_API_BASE_URL'],
            owner=os.environ['STUDY2_GITHUB_OWNER'],
            repository=os.environ['STUDY2_GITHUB_REPO'],
            token=os.environ['STUDY2_GITHUB_TOKEN'],
            api_version=os.environ['STUDY2_GITHUB_API_VERSION'],
        )
    except ValueError:
        print('LIVE GITHUB ENGINEERING SMOKE NOT RUN: invalid runtime configuration')
        return 2
    path, passed = run_smoke(config, OUTPUT)
    print(BANNER)
    print(f'Engineering artifact: {path}')
    print(f'Engineering validation passed: {passed}')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

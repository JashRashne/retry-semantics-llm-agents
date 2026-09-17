#!/usr/bin/env python3
"""Separate gated, one-mutation ambiguity engineering check. No dotenv loading.

Never run during implementation/tests: tests replace HTTPSConnection with fakes.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid

from retry_semantics.study2.github_adapter import (
    EngineeringFaultPoint, EngineeringTrace, GitHubConfig, GitHubEngineeringAdapter,
    GitHubEngineeringError, _LiveAmbiguityTransport, _require_live_ambiguity_opt_in,
)
from retry_semantics.study2.github_engineering_visibility import (
    is_after_send_ambiguity_trace, probe_engineering_visibility,
)

BANNER = 'ENGINEERING VALIDATION — LIVE AMBIGUOUS OUTCOME — NOT PAPER DATA'
GUARD = 'STUDY2_GITHUB_LIVE_AMBIGUITY_ENGINEERING'
REQUIRED_ENV = (
    'STUDY2_GITHUB_TOKEN', 'STUDY2_GITHUB_OWNER', 'STUDY2_GITHUB_REPO',
    'STUDY2_GITHUB_API_BASE_URL', 'STUDY2_GITHUB_API_VERSION',
)
OUTPUT = Path(__file__).resolve().parents[1] / 'research/study2/engineering/github/live'


def trace_artifact(trace: EngineeringTrace) -> dict:
    value = asdict(trace)
    value['attempt_count'] = trace.attempt_count
    for attempt in value['attempts']:
        attempt['request']['body_hex'] = attempt['request'].pop('body').hex()
    return value


def run_ambiguity_check(config: GitHubConfig, output: Path, *,
                        max_traversals: int = 3,
                        interval_seconds: float = 1.0) -> tuple[Path, bool]:
    """One create invocation; observation is reachable only after the exact fault.

    Traversal count and inter-traversal interval bound engineering convergence;
    they are not a wall-clock deadline for a complete paginated traversal.
    """
    _require_live_ambiguity_opt_in(config)
    if type(max_traversals) is not int or max_traversals <= 0:
        raise ValueError('positive engineering traversal count required')
    if (type(interval_seconds) not in (int, float)
            or not math.isfinite(interval_seconds) or interval_seconds < 0):
        raise ValueError('finite nonnegative engineering interval required')

    marker = 'ENGINEERING-AMBIGUITY-ONLY-' + uuid.uuid4().hex
    title = f'Engineering ambiguous outcome {marker}'
    body = f'{BANNER}\n{marker}\nControlled raw body: café 🚀\nMarkdown **test**, quote " and slash \\.\n'
    # Prepare and validate all local content before any side effect.
    request = GitHubEngineeringAdapter(config).prepare_create_issue(title=title, body=body)
    mutation_client = GitHubEngineeringAdapter(
        config, transport=_LiveAmbiguityTransport(config, request))
    artifact = {
        'classification': BANNER,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'target': {'api_base_url': config.api_base_url, 'owner': config.owner,
                   'repository': config.repository, 'api_version': config.api_version},
        'pre_dispatch_marker': marker, 'expected_title': title, 'expected_body': body,
        'fault_point': EngineeringFaultPoint.AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE.value,
        'create_logical_invocations': 1,
        'mutation_trace': None,
        'mutation_evidence': {
            'local_request_send_completed': False, 'injected_fault_fired': False,
            'response_wait_started': False, 'response_headers_received': False,
            'response_body_completed': False, 'response_unread_confirmed': False,
            'create_response_identity_available': False,
            'local_mutation_outcome': 'not_established',
        },
        'engineering_observation_bound': {
            'max_traversals': max_traversals, 'interval_seconds': interval_seconds,
            'total_wall_clock_deadline': False,
        },
        'observation_traversals': [], 'matching_distinct_identities': [],
        'provider_state_classification': 'MUTATION_STOPPED_BEFORE_EXPECTED_FAULT',
        'warnings_limitations': [
            'Local send completion does not prove provider receipt, execution or commitment.',
            'Zero matches within this engineering window do not prove non-execution.',
            'Complete pagination is not a transactional snapshot or visibility guarantee.',
            'Traversal count bounds polling, not total elapsed time or DNS resolution.',
            'Connection closure does not establish provider state.',
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    path = output / f'github-ambiguity-engineering-{marker}.json'
    # Exclusive reservation tests actual writability before mutation and never
    # overwrites old evidence. A crash can leave an empty/incomplete artifact.
    with path.open('x', encoding='utf-8') as stream:
        print(BANNER, flush=True)
        mutation_trace = None
        try:
            mutation_client.create_issue(title=title, body=body)
        except GitHubEngineeringError as error:
            mutation_trace = error.trace
            artifact['mutation_trace'] = trace_artifact(mutation_trace)
            if not is_after_send_ambiguity_trace(mutation_trace):
                artifact['warnings_limitations'].append(error.category)

        if mutation_trace is not None and is_after_send_ambiguity_trace(mutation_trace):
            artifact['mutation_evidence'].update(
                local_request_send_completed=True, injected_fault_fired=True,
                response_unread_confirmed=True, local_mutation_outcome='locally_ambiguous')
            # Fresh normal adapter: this client cannot inherit the mutation fault.
            observer = GitHubEngineeringAdapter(config)
            checks = []

            def observe():
                observed = observer.observe_issues()
                matches = observed.matching(
                    lambda issue: marker in issue.title or marker in (issue.body or ''))
                checks.append([
                    {'identity': issue.identity, 'title_exact': issue.title == title,
                     'body_exact': issue.body == body} for issue in matches
                ])
                return observed

            visibility = probe_engineering_visibility(
                observe, marker=marker, expected_title=title, expected_body=body,
                mutation_trace=mutation_trace, max_traversals=max_traversals,
                interval_seconds=interval_seconds)
            check_index = 0
            for traversal in visibility.traversals:
                record = asdict(traversal)
                record['trace'] = trace_artifact(traversal.trace)
                record['exact_content_checks'] = None
                if traversal.error_category is None:
                    record['exact_content_checks'] = checks[check_index]
                    check_index += 1
                artifact['observation_traversals'].append(record)
            identities = dict.fromkeys(
                identity for traversal in visibility.traversals
                for identity in (traversal.matching_distinct_identities or ()))
            artifact['matching_distinct_identities'] = list(identities)
            # Preserve anomalies even if a later traversal converges to one.
            if visibility.outcome == 'observation_failed':
                state = 'OBSERVATION_FAILED'
            elif len(identities) > 1:
                state = 'PROVIDER_STATE_MULTIPLE_MATCHES'
            elif visibility.convergence_observed:
                state = 'PROVIDER_STATE_OBSERVED_EXECUTED'
            elif identities:
                state = 'PROVIDER_STATE_CONTENT_MISMATCH'
            else:
                state = 'PROVIDER_STATE_NOT_OBSERVED_WITHIN_ENGINEERING_WINDOW'
            artifact['provider_state_classification'] = state
        elif mutation_trace is None:
            # Impossible with the fixed transport; do not observe if violated.
            artifact['provider_state_classification'] = 'MUTATION_BOUNDARY_VIOLATION'
            artifact['warnings_limitations'].append('expected_injected_fault_absent')

        artifact['passed'] = (
            artifact['provider_state_classification'] == 'PROVIDER_STATE_OBSERVED_EXECUTED')
        encoded = json.dumps(artifact, ensure_ascii=False, indent=2) + '\n'
        if config.token in encoded or config.token.encode().hex() in encoded:
            raise ValueError('refusing engineering artifact containing authentication')
        stream.write(encoded)
    return path, artifact['passed']


def main() -> int:
    if os.environ.get(GUARD) != '1':
        print('LIVE GITHUB AMBIGUITY ENGINEERING NOT RUN: dedicated opt-in absent')
        return 2
    if not all(os.environ.get(name) for name in REQUIRED_ENV):
        print('LIVE GITHUB AMBIGUITY ENGINEERING NOT RUN: required runtime configuration absent')
        return 2
    try:
        config = GitHubConfig(
            api_base_url=os.environ['STUDY2_GITHUB_API_BASE_URL'],
            owner=os.environ['STUDY2_GITHUB_OWNER'],
            repository=os.environ['STUDY2_GITHUB_REPO'],
            token=os.environ['STUDY2_GITHUB_TOKEN'],
            api_version=os.environ['STUDY2_GITHUB_API_VERSION'])
        path, passed = run_ambiguity_check(config, OUTPUT)
    except ValueError:
        print('LIVE GITHUB AMBIGUITY ENGINEERING STOPPED: local validation failed')
        return 2
    print(f'Engineering artifact: {path}')
    print(f'Engineering validation passed: {passed}')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

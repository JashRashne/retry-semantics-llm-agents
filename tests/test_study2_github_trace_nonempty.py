"""Final Phase 2C zero-attempt-success invariant; no network or mutations."""

import json
from pathlib import Path

import pytest

from retry_semantics.study2.github_adapter import (
    EngineeringRequest, EngineeringTrace, GitHubConfig, GitHubEngineeringAdapter,
    HTTPAttempt, HTTPResponse,
)

CONFIG = GitHubConfig('https://api.example.test', 'owner', 'repo',
                      'offline-nonempty-secret', '2022-11-28')


def test_zero_attempt_final_success_is_rejected():
    with pytest.raises(ValueError, match='successful trace requires HTTP attempt evidence'):
        EngineeringTrace('create_issue', attempts=(), outcome='success', complete=True)


@pytest.mark.parametrize('outcome', ['not_started', 'partial', 'http_response', 'transport_error'])
def test_empty_incomplete_initial_intermediate_or_failure_remains_valid(outcome):
    trace = EngineeringTrace('create_issue', outcome=outcome)
    assert trace.attempt_count == 0 and not trace.complete


@pytest.mark.parametrize('operation', ['create_issue', 'observe_issues'])
def test_actual_adapter_success_retains_one_or_multiple_attempts(operation):
    calls = []
    entry = dict(number=1, title='title', body='body', state='open')

    def transport(request, token, timeout):
        calls.append(request)
        headers = (('Content-Type', 'application/json'),)
        if request.method == 'POST':
            return HTTPResponse(201, headers, json.dumps(entry).encode())
        if len(calls) == 1:
            next_url = CONFIG.issue_url + '?state=all&per_page=100&page=2'
            headers += (('Link', f'<{next_url}>; rel="next"'),)
        return HTTPResponse(200, headers, json.dumps([entry]).encode())

    client = GitHubEngineeringAdapter(CONFIG, transport=transport)
    result = (client.create_issue(title='title', body='body') if operation == 'create_issue'
              else client.observe_issues())
    assert result.trace.complete and result.trace.outcome == 'success'
    assert result.trace.attempt_count == len(calls) == (1 if operation == 'create_issue' else 2)
    assert all(attempt.outcome == 'http_response' for attempt in result.trace.attempts)
    assert [request.method for request in calls] == (['POST'] if operation == 'create_issue' else ['GET', 'GET'])


def test_post_http_response_intermediate_remains_incomplete():
    client = GitHubEngineeringAdapter(
        CONFIG, transport=lambda request, token, timeout: HTTPResponse(201, (), b''),
    )
    request = client.prepare_create_issue(title='title', body='body')
    response, trace = client._dispatch(request, EngineeringTrace('create_issue'))
    assert response.status == 201 and trace.attempt_count == 1
    assert trace.attempts[0].outcome == 'http_response'
    assert trace.outcome == 'not_started' and not trace.complete


@pytest.mark.parametrize('filename', [
    'github-engineering-ENGINEERING-ONLY-e6374180720e4da1a538550342cd8b82.json',
    'github-visibility-followup-ENGINEERING-ONLY-e6374180720e4da1a538550342cd8b82.json',
])
def test_available_historical_live_artifact_reconstructs_without_migration(filename):
    # Historical engineering files are deliberately ignored and not required in
    # fresh checkouts. When present, validate them read-only without rewriting.
    path = Path(__file__).resolve().parents[1] / 'research/study2/engineering/github/live' / filename
    if not path.is_file():
        pytest.skip('ignored historical engineering artifact absent in this checkout')
    original_bytes = path.read_bytes()
    reconstructed = []

    def visit(value):
        if isinstance(value, dict):
            if 'operation' in value and 'attempts' in value:
                data = dict(value)
                data.pop('attempt_count', None)
                attempts = []
                for original in data.pop('attempts'):
                    attempt = dict(original)
                    request = dict(attempt.pop('request'))
                    request['body'] = bytes.fromhex(request.pop('body_hex'))
                    request['headers'] = tuple(map(tuple, request['headers']))
                    attempt['response_metadata'] = tuple(map(tuple, attempt['response_metadata']))
                    attempts.append(HTTPAttempt(request=EngineeringRequest(**request), **attempt))
                reconstructed.append(EngineeringTrace(attempts=tuple(attempts), **data))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(json.loads(original_bytes))
    assert reconstructed and all(trace.attempt_count > 0 for trace in reconstructed)
    assert all(not attempt.lifecycle for trace in reconstructed for attempt in trace.attempts)
    assert path.read_bytes() == original_bytes

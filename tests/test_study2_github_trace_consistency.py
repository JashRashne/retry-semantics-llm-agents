"""Adversarial Phase 2C cross-field validation; entirely offline."""

from dataclasses import asdict, replace
import http.client
import json

import pytest

from retry_semantics.study2.github_adapter import (
    EngineeringFaultPoint, EngineeringRequest, EngineeringTrace, GitHubConfig,
    GitHubEngineeringAdapter, GitHubEngineeringError, HTTPAttempt, HTTPResponse,
    LifecycleEvent, LifecycleStage as Stage,
)

TOKEN = 'cross-field-secret-do-not-retain'
CONFIG = GitHubConfig('https://api.example.test', 'owner', 'repo', TOKEN, '2022-11-28')
NORMAL = (
    Stage.REQUEST_PREPARED, Stage.CONNECT_STARTED, Stage.CONNECT_COMPLETED,
    Stage.REQUEST_SEND_STARTED, Stage.LOCAL_REQUEST_SEND_COMPLETED,
    Stage.RESPONSE_WAIT_STARTED, Stage.RESPONSE_HEADERS_RECEIVED,
    Stage.RESPONSE_BODY_COMPLETED,
)
METADATA = (('x-github-request-id', 'safe-request-id'),)


def history(stages):
    return tuple(LifecycleEvent(i, stage) for i, stage in enumerate(stages, 1))


@pytest.fixture
def normal_attempt():
    request = GitHubEngineeringAdapter(CONFIG).prepare_create_issue(title='title', body='body')
    return HTTPAttempt(1, request, True, True, 'http_response', 201,
                       METADATA, history(NORMAL))


@pytest.mark.parametrize('changes', [
    {'dispatch_started': False}, {'dispatch_ended': False},
    {'dispatch_started': False, 'dispatch_ended': False},
])
def test_complete_lifecycle_rejects_unfinalized_dispatch_flags(normal_attempt, changes):
    with pytest.raises(ValueError, match='finalized transport boundary'):
        replace(normal_attempt, **changes)


@pytest.mark.parametrize('boundary', ['before_send_fault', 'connect_failure', 'send_failure'])
def test_no_headers_rejects_response_metadata(normal_attempt, boundary):
    if boundary == 'before_send_fault':
        lifecycle = history(NORMAL[:3]) + (
            LifecycleEvent(4, Stage.INJECTED_FAULT, EngineeringFaultPoint.BEFORE_REQUEST_SEND),
        )
        outcome = 'injected_fault'
    else:
        prefix = NORMAL[:2] if boundary == 'connect_failure' else NORMAL[:4]
        lifecycle = history(prefix + (Stage.TRANSPORT_ERROR,))
        outcome = 'transport_error'
    valid = replace(normal_attempt, outcome=outcome, status=None,
                    response_metadata=(), lifecycle=lifecycle)
    with pytest.raises(ValueError, match='metadata requires response headers'):
        replace(valid, response_metadata=METADATA)
    with pytest.raises(ValueError, match='status and header evidence disagree'):
        replace(valid, status=201)


@pytest.mark.parametrize('read_failure', [False, True])
@pytest.mark.parametrize('include_metadata', [False, True])
def test_real_adapter_retains_only_available_sanitized_header_evidence(monkeypatch, read_failure, include_metadata):
    calls = []

    class Connection:
        def __init__(self, *args, **kwargs):
            calls.append('construct')

        def set_debuglevel(self, level):
            pass

        def connect(self):
            calls.append('connect')

        def putrequest(self, *args, **kwargs):
            pass

        def putheader(self, *args):
            pass

        def endheaders(self, *args, **kwargs):
            calls.append('send')

        def getresponse(self):
            calls.append('getresponse')

            class Response:
                status = 201

                def getheaders(self):
                    headers = [('Content-Type', 'application/json')]
                    if include_metadata:
                        headers += [('X-GitHub-Request-Id', TOKEN), ('Authorization', TOKEN)]
                    return headers

                def read(self):
                    if read_failure:
                        raise TimeoutError(TOKEN)
                    return b'{"number":1,"title":"title","body":"body","state":"open"}'

            return Response()

        def close(self):
            calls.append('close')

    monkeypatch.setattr(http.client, 'HTTPSConnection', Connection)
    client = GitHubEngineeringAdapter(CONFIG)
    if read_failure:
        with pytest.raises(GitHubEngineeringError) as caught:
            client.create_issue(title='title', body='body')
        trace = caught.value.trace
        assert caught.value.category == 'transport_timeout'
        assert not trace.complete
    else:
        trace = client.create_issue(title='title', body='body').trace
        assert trace.outcome == 'success' and trace.complete
    attempt = trace.attempts[0]
    expected = NORMAL[:7] + (Stage.TRANSPORT_ERROR,) if read_failure else NORMAL
    assert tuple(event.stage for event in attempt.lifecycle) == expected
    assert attempt.status == 201
    metadata = dict(attempt.response_metadata)
    assert metadata['content-type'] == 'application/json'
    assert metadata.get('x-github-request-id') == ('[REDACTED]' if include_metadata else None)
    assert 'authorization' not in metadata
    assert TOKEN not in repr(trace) + repr(asdict(trace))
    assert calls == ['construct', 'connect', 'send', 'getresponse', 'close']


def test_complete_response_may_have_no_allowlisted_metadata(normal_attempt):
    attempt = replace(normal_attempt, response_metadata=())
    assert attempt.status == 201
    assert EngineeringTrace('create_issue', (attempt,), 'success', complete=True).complete


@pytest.mark.parametrize('started,ended', [(False, False), (True, False), (False, True), (True, True)])
def test_historical_empty_lifecycle_preserves_legacy_fields(normal_attempt, started, ended):
    opaque = replace(normal_attempt, lifecycle=(), dispatch_started=started,
                     dispatch_ended=ended, status=None, response_metadata=METADATA)
    assert opaque.lifecycle == ()
    assert opaque.dispatch_started is started and opaque.dispatch_ended is ended
    assert opaque.response_metadata == METADATA


def test_historical_json_without_lifecycle_needs_no_migration(normal_attempt):
    original = replace(normal_attempt, lifecycle=())
    artifact = asdict(EngineeringTrace('create_issue', (original,), 'success', complete=True))
    attempt_data = artifact['attempts'][0]
    attempt_data.pop('lifecycle')  # Historical schema predates Phase 2C.
    request_data = attempt_data['request']
    request_data['body_hex'] = request_data.pop('body').hex()
    decoded = json.loads(json.dumps(artifact))
    attempt_data = decoded.pop('attempts')[0]
    request_data = attempt_data.pop('request')
    request_data['body'] = bytes.fromhex(request_data.pop('body_hex'))
    request_data['headers'] = tuple(map(tuple, request_data['headers']))
    attempt_data['response_metadata'] = tuple(map(tuple, attempt_data['response_metadata']))
    restored = HTTPAttempt(request=EngineeringRequest(**request_data), **attempt_data)
    trace = EngineeringTrace(attempts=(restored,), **decoded)
    assert restored == original
    assert trace.complete and trace.outcome == 'success'


def test_final_success_cannot_be_incomplete(normal_attempt):
    with pytest.raises(ValueError, match='success and completeness disagree'):
        EngineeringTrace('create_issue', (normal_attempt,), 'success', complete=False)


@pytest.mark.parametrize('outcome', [
    'transport_error', 'injected_fault', 'http_error', 'malformed_success',
    'http_response', 'not_started',
])
def test_non_success_cannot_be_complete_even_with_successful_attempt(normal_attempt, outcome):
    with pytest.raises(ValueError, match='success and completeness disagree'):
        EngineeringTrace('create_issue', (normal_attempt,), outcome, complete=True)
    assert not EngineeringTrace('create_issue', (normal_attempt,), outcome).complete


def test_dispatch_intermediate_trace_waits_for_operation_validation(normal_attempt):
    calls = []

    def transport(request, token, timeout):
        calls.append(request)
        return HTTPResponse(201, (), b'not valid issue JSON')

    client = GitHubEngineeringAdapter(CONFIG, transport=transport)
    response, intermediate = client._dispatch(normal_attempt.request, EngineeringTrace('create_issue'))
    assert response.status == 201
    assert intermediate.outcome == 'not_started' and not intermediate.complete
    assert intermediate.attempts[0].outcome == 'http_response'
    with pytest.raises(GitHubEngineeringError, match='malformed_success') as caught:
        client.create_issue(title='title', body='body')
    assert not caught.value.trace.complete
    assert caught.value.trace.attempts[0].outcome == 'http_response'
    assert caught.value.trace.attempt_count == 1
    assert len(calls) == 2  # Two explicit operations, each called the transport once.

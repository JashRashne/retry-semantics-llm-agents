"""Phase 2C deterministic client-boundary tests; no network or paper data."""

from dataclasses import FrozenInstanceError, asdict, replace
import http.client
import json

import pytest

import retry_semantics.study2.github_adapter as module
from retry_semantics.study2.github_adapter import (
    EngineeringFaultPoint as Fault, EngineeringTrace, GitHubConfig,
    GitHubEngineeringAdapter, GitHubEngineeringError, HTTPAttempt,
    LifecycleEvent, LifecycleStage as Stage, OfflineFaultTransport,
)

TOKEN = 'offline-secret-MUST-NOT-APPEAR'
NORMAL = list(Stage)[:8]
CONFIG = GitHubConfig('https://api.example.test', 'owner', 'repo', TOKEN, '2022-11-28')


def issue(number=1, **changes):
    return dict(number=number, title='title', body='body', state='open', **changes)


class Harness:
    """Real http.client header/body serialization, fake sockets and responses.

    Logs contain only operation names; wire chunks are private fake-test evidence.
    """
    def __init__(self, monkeypatch, *, failure=None, statuses=(201,), pages=None):
        self.calls = []
        self.connections = []
        self.statuses = iter(statuses)
        self.pages = iter(pages or [(issue(), ())])
        harness = self
        original_event = module._event

        def record_event(events, stage, point=None):
            harness.calls.append(stage)
            original_event(events, stage, point)

        monkeypatch.setattr(module, '_event', record_event)

        class Socket:
            def __init__(self):
                self.chunks = []

            def sendall(self, data):
                harness.calls.append('sendall')
                # Header success followed by uncertain partial body transmission.
                if failure == 'send' and self.chunks:
                    self.chunks.append(data[:3])
                    raise ConnectionError(TOKEN)
                self.chunks.append(data)

            def close(self):
                pass

        class Connection(http.client.HTTPConnection):
            def __init__(self, host, port, timeout):
                harness.calls.append('construct')
                if failure == 'construct':
                    raise OSError(TOKEN)
                super().__init__(host, port, timeout=timeout)
                self.socket = Socket()
                self.closed = False
                harness.connections.append(self)

            def connect(self):
                harness.calls.append('connect')
                if failure == 'connect':
                    raise TimeoutError(TOKEN)
                self.sock = self.socket

            def putrequest(self, *args, **kwargs):
                harness.calls.append('putrequest')
                super().putrequest(*args, **kwargs)

            def putheader(self, *args):
                harness.calls.append('putheader')
                if failure == 'prepare':
                    raise ValueError(TOKEN)
                super().putheader(*args)

            def endheaders(self, *args, **kwargs):
                harness.calls.append('endheaders')
                super().endheaders(*args, **kwargs)
                harness.calls.append('endheaders_returned')

            def getresponse(self):
                harness.calls.append('getresponse')
                if failure == 'wait':
                    raise ConnectionError(TOKEN)
                status = next(harness.statuses)
                payload, extra_headers = next(harness.pages)

                class Response:
                    def getheaders(self):
                        harness.calls.append('getheaders')
                        if failure == 'headers':
                            raise OSError(TOKEN)
                        return [('Content-Type', 'application/json'),
                                ('Authorization', TOKEN),
                                ('X-GitHub-Request-Id', TOKEN)] + list(extra_headers)

                    def read(self):
                        harness.calls.append('read')
                        if failure == 'read':
                            raise http.client.IncompleteRead(TOKEN.encode(), 100)
                        return json.dumps(payload).encode()

                result = Response()
                result.status = status
                return result

            def close(self):
                harness.calls.append('close')
                self.closed = True
                super().close()
                if failure == 'close':
                    raise OSError(TOKEN)

        self.factory = Connection
        monkeypatch.setattr(http.client, 'HTTPSConnection', Connection)

    @property
    def post_count(self):
        return sum(chunk.startswith(b'POST ') for conn in self.connections for chunk in conn.socket.chunks)

    def client(self, fault=None):
        if fault is None:
            return GitHubEngineeringAdapter(CONFIG)
        return GitHubEngineeringAdapter(CONFIG, transport=OfflineFaultTransport(self.factory, fault))


def stages(trace):
    return [event.stage for event in trace.attempts[-1].lifecycle]


def assert_safe(trace):
    value = asdict(trace)
    for attempt in value['attempts']:
        attempt['request']['body_hex'] = attempt['request'].pop('body').hex()
    encoded = json.dumps(value)
    assert TOKEN not in encoded + repr(trace)
    assert 'Authorization' not in encoded


def test_normal_mutation_events_surround_actual_transport_calls(monkeypatch):
    fake = Harness(monkeypatch)
    client = fake.client()
    prepared = client.prepare_create_issue(title='title', body='body')
    result = client.create_issue(title='title', body='body')
    assert stages(result.trace) == NORMAL
    assert fake.post_count == len(fake.connections) == result.trace.attempt_count == 1
    assert result.trace.attempts[0].request == prepared
    calls = fake.calls
    assert calls[:6] == [Stage.REQUEST_PREPARED, 'construct', Stage.CONNECT_STARTED,
                         'connect', Stage.CONNECT_COMPLETED, 'putrequest']
    assert calls[calls.index(Stage.REQUEST_SEND_STARTED):] == [
        Stage.REQUEST_SEND_STARTED, 'endheaders', 'sendall', 'sendall',
        'endheaders_returned', Stage.LOCAL_REQUEST_SEND_COMPLETED,
        Stage.RESPONSE_WAIT_STARTED, 'getresponse', Stage.RESPONSE_HEADERS_RECEIVED,
        'getheaders', 'read', Stage.RESPONSE_BODY_COMPLETED, 'close',
    ]
    assert fake.connections[0].auto_open == 0 and fake.connections[0].debuglevel == 0
    assert_safe(result.trace)
    with pytest.raises(FrozenInstanceError):
        result.trace.attempts[0].lifecycle[0].sequence = 2


@pytest.mark.parametrize('failure,prefix,posts,category', [
    ('construct', 1, 0, 'transport_error'),
    ('connect', 2, 0, 'transport_timeout'),
    ('prepare', 3, 0, 'transport_error'),
    ('send', 4, 1, 'transport_connection_error'),
    ('wait', 6, 1, 'transport_connection_error'),
    ('headers', 7, 1, 'transport_error'),
    ('read', 7, 1, 'transport_error'),
])
def test_transport_failures_preserve_exact_prefix_without_retry(monkeypatch, failure, prefix, posts, category):
    fake = Harness(monkeypatch, failure=failure)
    with pytest.raises(GitHubEngineeringError) as caught:
        fake.client().create_issue(title='title', body='body')
    error = caught.value
    assert stages(error.trace) == NORMAL[:prefix] + [Stage.TRANSPORT_ERROR]
    assert error.category == category and not error.trace.complete
    assert error.trace.attempt_count == fake.calls.count('construct') == 1
    assert fake.post_count == posts
    assert fake.calls.count('connect') <= 1 and fake.calls.count('endheaders') <= 1
    if prefix < 6:
        assert 'getresponse' not in fake.calls
    if prefix < 7:
        assert error.trace.attempts[0].status is None
    else:
        assert error.trace.attempts[0].status == 201
    if failure == 'send':
        assert len(fake.connections[0].socket.chunks[-1]) == 3
        assert Stage.LOCAL_REQUEST_SEND_COMPLETED not in stages(error.trace)
    assert all(c.closed for c in fake.connections)
    assert error.__context__ is None and error.__cause__ is None
    assert TOKEN not in repr(error) + str(error.__dict__)
    assert_safe(error.trace)


@pytest.mark.parametrize('point,prefix,posts', [
    (Fault.BEFORE_REQUEST_SEND, 3, 0),
    (Fault.AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE, 5, 1),
])
@pytest.mark.parametrize('cleanup_failure', [None, 'close'])
def test_injected_fault_is_terminal_exactly_once_without_response_or_retry(monkeypatch, point, prefix, posts, cleanup_failure):
    fake = Harness(monkeypatch, failure=cleanup_failure)
    with pytest.raises(GitHubEngineeringError) as caught:
        fake.client(point).create_issue(title='title', body='body')
    error = caught.value
    assert stages(error.trace) == NORMAL[:prefix] + [Stage.INJECTED_FAULT]
    assert error.trace.attempts[0].lifecycle[-1].fault_point is point
    assert error.category == 'injected_fault' and not error.trace.complete
    assert fake.post_count == posts
    assert len(fake.connections) == fake.calls.count('connect') == error.trace.attempt_count == 1
    assert fake.calls.count(Stage.INJECTED_FAULT) == 1
    assert 'getresponse' not in fake.calls and 'read' not in fake.calls
    assert fake.connections[0].closed
    assert error.__context__ is None and error.__cause__ is None
    assert_safe(error.trace)


@pytest.mark.parametrize('status', [429, 500, 307])
def test_http_failure_and_redirect_have_complete_response_and_one_post(monkeypatch, status):
    fake = Harness(monkeypatch, statuses=(status,))
    with pytest.raises(GitHubEngineeringError) as caught:
        fake.client().create_issue(title='title', body='body')
    assert caught.value.category == 'http_error'
    assert stages(caught.value.trace) == NORMAL
    assert fake.post_count == len(fake.connections) == 1
    assert fake.calls.count('getresponse') == fake.calls.count('read') == 1
    assert_safe(caught.value.trace)


def test_get_lifecycle_preserves_canonical_pagination_pr_exclusion_and_dedup(monkeypatch):
    next_url = CONFIG.api_base_url + '/repositories/123/issues?state=all&per_page=100&page=2'
    fake = Harness(monkeypatch, statuses=(200, 200), pages=[
        ([issue(1), issue(9, pull_request=None)], [('Link', f'<{next_url}>; rel="next"')]),
        ([issue(1), issue(2)], ()),
    ])
    result = fake.client().observe_issues()
    assert [item.identity for item in result.issues] == [(('owner', 'repo'), n) for n in (1, 2)]
    assert result.trace.complete and result.trace.pages_fetched == 2
    assert result.trace.excluded_prs == result.trace.repeated_identities == 1
    assert result.trace.attempts[1].request.url == next_url
    assert fake.post_count == 0 and len(fake.connections) == 2
    for attempt in result.trace.attempts:
        assert [e.stage for e in attempt.lifecycle] == NORMAL
        assert [e.sequence for e in attempt.lifecycle] == list(range(1, 9))
        assert attempt.request.method == 'GET'
    assert_safe(result.trace)


def events(stages):
    return tuple(LifecycleEvent(i, stage) for i, stage in enumerate(stages, 1))


@pytest.mark.parametrize('bad_stages', [
    [Stage.REQUEST_PREPARED, Stage.LOCAL_REQUEST_SEND_COMPLETED],
    NORMAL[:4] + [Stage.RESPONSE_HEADERS_RECEIVED],
    NORMAL[:6] + [Stage.RESPONSE_BODY_COMPLETED],
    NORMAL[:3] + [Stage.CONNECT_COMPLETED] + NORMAL[3:],
    NORMAL[:5] + [Stage.LOCAL_REQUEST_SEND_COMPLETED] + NORMAL[5:],
    NORMAL[:2] + [Stage.TRANSPORT_ERROR] + NORMAL[2:],
    NORMAL[:5],
])
def test_impossible_lifecycle_sequences_rejected(bad_stages):
    request = GitHubEngineeringAdapter(CONFIG).prepare_create_issue(title='title', body='body')
    with pytest.raises(ValueError):
        HTTPAttempt(1, request, True, True, 'http_response', 201, lifecycle=events(bad_stages))


def test_terminal_fault_consistency_and_success_validation():
    request = GitHubEngineeringAdapter(CONFIG).prepare_create_issue(title='title', body='body')
    fault = LifecycleEvent(6, Stage.INJECTED_FAULT, Fault.AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE)
    history = events(NORMAL[:5]) + (fault,)
    attempt = HTTPAttempt(1, request, True, True, 'injected_fault', lifecycle=history)
    for change in ({'outcome': 'http_response'}, {'status': 201},
                   {'lifecycle': history + (LifecycleEvent(7, Stage.RESPONSE_WAIT_STARTED),)},
                   {'lifecycle': history + (replace(fault, sequence=7),)},
                   {'lifecycle': history[:-1] + (replace(fault, fault_point=Fault.BEFORE_REQUEST_SEND),)},
                   {'lifecycle': events(NORMAL[:3]) + (replace(fault, sequence=4),)},
                   {'lifecycle': (replace(history[0], sequence=2),) + history[1:]}):
        with pytest.raises(ValueError):
            replace(attempt, **change)
    trace = EngineeringTrace('create_issue', (attempt,), 'injected_fault')
    with pytest.raises(ValueError):
        replace(trace, outcome='success', complete=True)
    with pytest.raises(ValueError):
        replace(trace, complete=True)
    with pytest.raises(ValueError):
        replace(attempt, lifecycle=list(history))


@pytest.mark.parametrize('stage,point', [(Stage.INJECTED_FAULT, TOKEN), (Stage.CONNECT_STARTED, Fault.BEFORE_REQUEST_SEND)])
def test_fault_metadata_rejects_untyped_or_misplaced_values(stage, point):
    with pytest.raises(ValueError) as caught:
        LifecycleEvent(1, stage, point)
    assert TOKEN not in str(caught.value)


def test_offline_fault_transport_requires_explicit_factory_and_typed_point():
    with pytest.raises(TypeError):
        OfflineFaultTransport(fault_point=Fault.BEFORE_REQUEST_SEND)
    with pytest.raises(ValueError) as caught:
        OfflineFaultTransport(lambda: None, TOKEN)
    assert TOKEN not in str(caught.value)


def test_complete_response_requires_status_and_failure_requires_terminal_event():
    request = GitHubEngineeringAdapter(CONFIG).prepare_create_issue(title='title', body='body')
    attempt = HTTPAttempt(1, request, True, True, 'http_response', 201, lifecycle=events(NORMAL))
    with pytest.raises(ValueError):
        replace(attempt, status=None)
    with pytest.raises(ValueError):
        replace(attempt, outcome='transport_error')


def test_opaque_transport_read_error_cannot_echo_secret_category():
    def opaque(request, token, timeout):
        return module.HTTPResponse(201, (), b'', TOKEN)
    with pytest.raises(GitHubEngineeringError) as caught:
        GitHubEngineeringAdapter(CONFIG, transport=opaque).create_issue(title='title', body='body')
    assert caught.value.category == 'transport_error'
    assert caught.value.trace.attempt_count == 1
    assert caught.value.trace.attempts[0].lifecycle == ()  # No fabricated control-flow evidence.
    assert_safe(caught.value.trace)

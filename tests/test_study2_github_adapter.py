"""Engineering-only offline tests: no GitHub calls or paper observations."""

from dataclasses import FrozenInstanceError, asdict, replace
import http.client
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from retry_semantics.study2.github_adapter import (
    EngineeringTrace, GitHubConfig, GitHubEngineeringAdapter,
    GitHubEngineeringError, HTTPResponse, https_single_attempt,
)

TOKEN = 'test-secret-token-DO-NOT-RETAIN'
BASE = 'https://api.example.test/api/v3'
SCOPE = ('test-owner', 'test-repository')
URL = BASE + '/repos/test-owner/test-repository/issues'


def config(**changes):
    return GitHubConfig(BASE, *SCOPE, TOKEN, '2022-11-28', **changes)


def issue(number=1, **changes):
    return {'number': number, 'title': 'controlled title', 'body': 'controlled body',
            'state': 'open', **changes}


def response(value, *, status=200, link=None, headers=()):
    return HTTPResponse(status, (('Content-Type', 'application/json'),) +
                        ((('Link', link),) if link is not None else ()) + headers,
                        json.dumps(value).encode())


class FakeTransport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, request, token, timeout):
        self.calls.append((request, token, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def adapter(*outcomes):
    fake = FakeTransport(*outcomes)
    return GitHubEngineeringAdapter(config(), transport=fake), fake


def next_link(page, **changes):
    return '<' + changes.get('url', URL + f'?state=all&per_page=100&page={page}') + '>; rel="next"'


def test_prepared_request_equals_boundary_request_with_exact_unicode_bytes():
    client, fake = adapter(response(issue(), status=201))
    title, body = 'quote " / café 🚀', 'line1\nline2\\markdown **text**'
    intended = client.prepare_create_issue(title=title, body=body)
    result = client.create_issue(title=title, body=body)
    sent, token, timeout = fake.calls[0]
    assert intended == sent == result.trace.attempts[0].request
    assert sent.method == 'POST'
    assert sent.target_path == '/api/v3/repos/test-owner/test-repository/issues'
    assert sent.body == b'{"title":"quote \\" / caf\xc3\xa9 \xf0\x9f\x9a\x80","body":"line1\\nline2\\\\markdown **text**"}'
    assert json.loads(sent.body) == {'title': title, 'body': body}
    headers = dict(sent.headers)
    assert headers['Content-Length'] == str(len(sent.body))
    assert headers['Accept'] == 'application/vnd.github.raw+json'
    assert headers['X-GitHub-Api-Version'] == config().api_version
    assert not any(k.lower() == 'authorization' for k in headers)
    assert token == TOKEN and timeout == 30
    assert result.trace.attempt_count == len(fake.calls) == 1
    assert result.trace.attempts[0].index == 1
    assert result.trace.attempts[0].dispatch_started
    assert result.trace.attempts[0].dispatch_ended


@pytest.mark.parametrize('outcome,category', [
    (TimeoutError(TOKEN), 'transport_timeout'),
    (ConnectionError(TOKEN), 'transport_connection_error'),
    (OSError(TOKEN), 'transport_error'),
    *[(response({'message': TOKEN}, status=s), 'http_error')
      for s in (400, 403, 404, 429, 500, 503, 301, 302, 303, 307, 308)],
])
def test_one_mutation_attempt_on_every_failure_without_secret_exception_context(outcome, category):
    client, fake = adapter(outcome, response(issue(), status=201))
    with pytest.raises(GitHubEngineeringError) as captured:
        client.create_issue(title='controlled', body='content')
    error = captured.value
    assert error.category == category
    assert error.trace.attempt_count == len(fake.calls) == 1
    assert len(fake.outcomes) == 1  # No second dispatch consumed.
    assert not error.trace.complete
    assert error.__context__ is None and error.__cause__ is None
    assert TOKEN not in repr(error) + repr(error.trace) + str(error.__dict__)


@pytest.mark.parametrize('value', [None, [], {}, issue(number=True), issue(number=0),
                                    issue(body=42), issue(state='other'),
                                    issue(pull_request=None), issue(title=TOKEN)])
def test_malformed_creation_success_is_not_success_or_retried(value):
    client, fake = adapter(response(value, status=201))
    with pytest.raises(GitHubEngineeringError, match='malformed_success') as captured:
        client.create_issue(title='controlled', body='content')
    assert captured.value.trace.attempt_count == len(fake.calls) == 1
    assert captured.value.trace.attempts[0].status == 201


def test_request_and_trace_immutable_config_repr_safe_and_metadata_sanitized():
    client, _ = adapter(response(issue(), status=201, headers=(
        ('X-GitHub-Request-Id', TOKEN + ' echoed'), ('Authorization', TOKEN),
        ('Set-Cookie', TOKEN), ('X-RateLimit-Remaining', '0'),
    )))
    result = client.create_issue(title='controlled', body='content')
    assert TOKEN not in repr(client.config) + repr(result) + repr(asdict(result.trace))
    metadata = dict(result.trace.attempts[0].response_metadata)
    assert metadata['x-github-request-id'] == '[REDACTED] echoed'
    assert metadata['x-ratelimit-remaining'] == '0'
    assert 'authorization' not in metadata and 'set-cookie' not in metadata
    for obj, attr in ((client.config, 'owner'), (result.trace, 'complete'),
                      (result.trace.attempts[0].request, 'body')):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, attr, None)


@pytest.mark.parametrize('title,body', [(TOKEN, 'safe'), ('safe', TOKEN), ('', 'body'), ('safe', None)])
def test_invalid_or_secret_content_never_dispatched(title, body):
    client, fake = adapter()
    with pytest.raises(ValueError):
        client.create_issue(title=title, body=body)
    assert not fake.calls


@pytest.mark.parametrize('changes', [
    {'api_base_url': 'http://api.example.test'},
    {'api_base_url': 'https://user:secret@api.example.test'},
    {'api_base_url': 'https://api.example.test/?secret=value'},
    {'api_base_url': 'https://[malformed'},
    {'owner': '../other'}, {'repository': '..'}, {'token': 'secret\nheader'},
    {'api_version': ''}, {'timeout_seconds': 0}, {'timeout_seconds': float('nan')},
])
def test_invalid_runtime_configuration_rejected(changes):
    with pytest.raises(ValueError):
        replace(config(), **changes)


def test_complete_empty_observation_is_success_with_explicit_parameters():
    client, fake = adapter(response([]))
    result = client.observe_issues()
    assert result.issues == () and result.trace.complete
    assert result.trace.outcome == 'success' and result.trace.pages_fetched == 1
    assert result.trace.attempt_count == 1 and result.trace.raw_entries == 0
    sent = fake.calls[0][0]
    assert sent.method == 'GET' and sent.body == b''
    assert parse_qs(urlsplit(sent.url).query) == {'state': ['all'], 'per_page': ['100'], 'page': ['1']}


def test_exhaustive_pages_pr_closed_dedup_and_matching_without_create_response():
    # No mutation occurs; all identities/content come solely from LIST.
    client, fake = adapter(
        response([issue(1), issue(2, pull_request=None), issue(3, state='closed')],
                 link=next_link(2) + ', <' + URL + '?state=all&per_page=100&page=3>; rel="last"'),
        response([issue(1, title='changed', state='closed'), issue(4)], link=next_link(3)),
        response([issue(4), issue(5, title='other', body=None)]),
    )
    result = client.observe_issues()
    assert len(fake.calls) == 3 and all(c[0].method == 'GET' for c in fake.calls)
    assert [i.identity for i in result.issues] == [(SCOPE, n) for n in (1, 3, 4, 5)]
    assert result.issues[0].title == 'controlled title'  # First appearance retained.
    assert result.issues[1].state == 'closed'
    matches = result.matching(lambda i: i.title == 'controlled title' and i.body == 'controlled body')
    assert len(matches) == 3  # Identical content with different numbers stays distinct.
    trace = result.trace
    assert (trace.attempt_count, trace.pages_fetched, trace.raw_entries,
            trace.excluded_prs, trace.repeated_identities, trace.distinct_issues) == (3, 3, 7, 1, 2, 4)
    assert [a.index for a in trace.attempts] == [1, 2, 3]
    assert trace.complete


@pytest.mark.parametrize('pr_value', [None, {}, False, {'url': 'untrusted'}])
def test_pr_key_presence_excluded(pr_value):
    client, _ = adapter(response([issue(pull_request=pr_value)]))
    result = client.observe_issues()
    assert result.issues == () and result.trace.excluded_prs == 1


@pytest.mark.parametrize('value', [None, {}, [None], [[]], [{}], [issue(number='1')],
                                    [issue(number=-1)], [issue(title=None)],
                                    [issue(body=False)], [issue(state=None)],
                                    [dict(number=1, title='t', state='open')],
                                    [issue(pull_request={}, body=42)]])
def test_malformed_list_never_becomes_empty_complete_result(value):
    client, fake = adapter(response(value))
    with pytest.raises(GitHubEngineeringError, match='malformed_success') as captured:
        client.observe_issues()
    assert not captured.value.trace.complete and len(fake.calls) == 1


@pytest.mark.parametrize('outcome,category', [
    (TimeoutError(TOKEN), 'transport_timeout'),
    (ConnectionError(TOKEN), 'transport_connection_error'),
    (response([], status=429), 'http_error'), (response([], status=500), 'http_error'),
    (response([], status=304), 'http_error'), (response([], status=301), 'http_error'),
    (HTTPResponse(200, (), b'[]'), 'malformed_success'),
    (HTTPResponse(200, (('Content-Type', 'application/json'),), b'not json'), 'malformed_success'),
    (response([], headers=(('Content-Encoding', 'gzip'),)), 'malformed_success'),
    (HTTPResponse(200, (), b'', 'transport_timeout'), 'transport_timeout'),
])
def test_failed_second_page_never_returns_partial_or_zero_observation(outcome, category):
    client, fake = adapter(response([issue()], link=next_link(2)), outcome)
    with pytest.raises(GitHubEngineeringError) as captured:
        client.observe_issues()
    trace = captured.value.trace
    assert captured.value.category == category and not trace.complete
    assert trace.attempt_count == len(fake.calls) == 2
    assert trace.distinct_issues == 1 and trace.raw_entries == 1


@pytest.mark.parametrize('link', [
    '', 'garbage', '<broken; rel="next"', next_link(2) + ',',
    next_link(2).replace('rel="next"', 'rel=""'),
    next_link(2).replace('rel="next"', 'rel="next,"'),
    next_link(2) + '; rel="last"', next_link(2) + ', ' + next_link(3),
    next_link(2) + '; anchor="https://evil.test"',
    next_link(2, url='https://evil.test/issues?state=all&per_page=100&page=2'),
    next_link(2, url=URL.replace('test-repository', 'other') + '?state=all&per_page=100&page=2'),
    next_link(2, url=URL.replace('/api/v3', '/api/v4') + '?state=all&per_page=100&page=2'),
    next_link(2, url=URL.replace('https:', 'http:') + '?state=all&per_page=100&page=2'),
    next_link(2, url=URL.replace('api.example', 'user@api.example') + '?state=all&per_page=100&page=2'),
    next_link(2, url='/repos/test-owner/test-repository/issues?page=2'),
    next_link(2, url=URL + '?state=open&per_page=100&page=2'),
    next_link(2, url=URL + '?state=all&per_page=10&page=2'),
    next_link(2, url=URL + '?state=all&per_page=100&page=2&since=yesterday'),
    next_link(2, url=URL + '?state=all&per_page=100&page=2&page=3'),
    next_link(2, url=URL + '?state=all&per_page=100&page=2#fragment'),
    next_link(2, url=URL + '?state=all&per_page=100&page=0'),
    next_link(2, url=URL + '?state=all&per_page=100&page=2&secret=' + TOKEN),
])
def test_unsafe_or_malformed_next_link_rejected_before_network(link):
    client, fake = adapter(response([], link=link), response([]))
    with pytest.raises(GitHubEngineeringError, match='unsafe_or_malformed_pagination') as captured:
        client.observe_issues()
    assert len(fake.calls) == 1
    assert TOKEN not in repr(captured.value.trace)


def test_loop_with_reordered_query_fails_after_two_pages():
    client, fake = adapter(response([], link=next_link(2)), response([], link=next_link(
        1, url=URL + '?page=1&per_page=100&state=all')))
    with pytest.raises(GitHubEngineeringError, match='pagination_loop') as captured:
        client.observe_issues()
    assert len(fake.calls) == captured.value.trace.attempt_count == 2
    assert not captured.value.trace.complete


def test_duplicate_link_header_and_duplicate_json_keys_fail_closed():
    client, _ = adapter(response([], link=next_link(2), headers=(('Link', next_link(3)),)))
    with pytest.raises(GitHubEngineeringError, match='unsafe_or_malformed_pagination'):
        client.observe_issues()
    client, _ = adapter(HTTPResponse(200, (('Content-Type', 'application/json'),),
        b'[{"number":1,"number":2,"title":"t","body":null,"state":"open"}]'))
    with pytest.raises(GitHubEngineeringError, match='malformed_success'):
        client.observe_issues()


def test_no_low_page_cap_and_quoted_link_extension_comma():
    client, fake = adapter(*[response([], link=next_link(p + 1) + '; title="page, next"')
                            for p in range(1, 120)], response([]))
    assert client.observe_issues().trace.pages_fetched == len(fake.calls) == 120


class WireSocket:
    def __init__(self, fail_send=None):
        self.chunks = []
        self.fail_send = fail_send

    def sendall(self, data):
        self.chunks.append(bytes(data))
        if self.fail_send:
            raise self.fail_send

    def close(self):
        pass


@pytest.mark.parametrize('failure_stage', [None, 'connect', 'headers', 'body', 'response',
                                         'read', 'read_connection', 'read_incomplete', 'redirect'])
def test_default_transport_real_http_serialization_one_connection_no_retry(monkeypatch, failure_stage):
    connections = []
    request = GitHubEngineeringAdapter(config()).prepare_create_issue(title='café', body='line\nbody')
    class Connection(http.client.HTTPConnection):
        def __init__(self, host, port, timeout):
            super().__init__(host, port, timeout=timeout)
            self.socket = WireSocket()
            self.connect_count = 0
            self.closed = False
            connections.append(self)

        def connect(self):
            self.connect_count += 1
            if failure_stage == 'connect':
                raise TimeoutError(TOKEN)
            self.sock = self.socket

        def send(self, data):
            if (failure_stage == 'headers' and not self.socket.chunks or
                    failure_stage == 'body' and self.socket.chunks):
                self.socket.fail_send = ConnectionError(TOKEN)
            super().send(data)

        def getresponse(self):
            if failure_stage == 'response':
                raise ConnectionError(TOKEN)
            class Response:
                status = 307 if failure_stage == 'redirect' else 201
                def getheaders(self):
                    return [('Content-Type', 'application/json'), ('Location', 'https://evil.test')]
                def read(self):
                    if failure_stage == 'read':
                        raise TimeoutError(TOKEN)
                    if failure_stage == 'read_connection':
                        raise ConnectionError(TOKEN)
                    if failure_stage == 'read_incomplete':
                        raise http.client.IncompleteRead(TOKEN.encode(), 100)
                    return json.dumps(issue()).encode()
            return Response()

        def close(self):
            self.closed = True
            super().close()

    monkeypatch.setattr(http.client, 'HTTPSConnection', Connection)
    monkeypatch.setenv('HTTPS_PROXY', 'https://evil.test')
    monkeypatch.setenv('HTTP_PROXY', 'http://evil.test')
    client = GitHubEngineeringAdapter(config())
    if failure_stage:
        with pytest.raises(GitHubEngineeringError) as captured:
            client.create_issue(title='café', body='line\nbody')
        assert captured.value.trace.attempt_count == 1
        if failure_stage == 'read':
            assert captured.value.trace.attempts[0].status == 201
            assert captured.value.category == 'transport_timeout'
        if failure_stage in ('read_connection', 'read_incomplete', 'redirect'):
            assert captured.value.trace.attempts[0].status == (307 if failure_stage == 'redirect' else 201)
            assert captured.value.category == {'read_connection': 'transport_connection_error',
                                               'read_incomplete': 'transport_error',
                                               'redirect': 'http_error'}[failure_stage]
        assert TOKEN not in repr(captured.value.trace)
    else:
        result = client.create_issue(title='café', body='line\nbody')
        assert result.trace.attempt_count == 1
        wire = b''.join(connections[0].socket.chunks)
        start, body = wire.split(b'\r\n\r\n', 1)
        assert body == request.body
        assert start.split(b'\r\n')[0] == ('POST ' + request.target_path + ' HTTP/1.1').encode()
        assert start.count(b'POST ') == 1
        assert start.count(b'Host: ') == start.count(b'Accept-Encoding: ') == 1
        assert b'Transfer-Encoding:' not in start
        assert b'Authorization: Bearer ' + TOKEN.encode() in start
        assert all((k + ': ' + v).encode() in start for k, v in request.headers)
    assert len(connections) == 1 and connections[0].connect_count == 1
    assert connections[0].auto_open == 0 and connections[0].debuglevel == 0
    assert connections[0].host == 'api.example.test' and connections[0].closed


def test_version_drift_fails_and_selected_version_is_inspectable():
    client, _ = adapter(response([], headers=(('X-GitHub-Api-Version-Selected', '2099-01-01'),)))
    with pytest.raises(GitHubEngineeringError, match='malformed_success') as captured:
        client.observe_issues()
    assert dict(captured.value.trace.attempts[0].response_metadata)['x-github-api-version-selected'] == '2099-01-01'


def test_default_https_constructor_uses_verified_tls():
    # Construction only: no socket connection or provider request.
    import ssl
    connection = http.client.HTTPSConnection('api.example.test', timeout=30)
    try:
        assert connection._context.verify_mode == ssl.CERT_REQUIRED
        assert connection._context.check_hostname
    finally:
        connection.close()


def test_case_insensitive_relation_and_multiple_registered_relations_follow_next():
    link = next_link(2).replace('rel="next"', 'REL="NEXT alternate"')
    client, fake = adapter(response([], link=link), response([]))
    assert client.observe_issues().trace.complete and len(fake.calls) == 2


def test_malformed_provider_payload_diagnostics_are_not_retained_in_exception():
    raw = HTTPResponse(201, (('Content-Type', 'application/json'),), TOKEN.encode())
    client, fake = adapter(raw)
    with pytest.raises(GitHubEngineeringError, match='malformed_success') as captured:
        client.create_issue(title='safe', body='safe')
    assert captured.value.__context__ is None and captured.value.__cause__ is None
    assert TOKEN not in repr(captured.value) + repr(captured.value.__dict__)
    assert len(fake.calls) == 1


def canonical_url(page, *, base=BASE, repository_id=1300192):
    return f'{base}/repositories/{repository_id}/issues?state=all&per_page=100&page={page}'


@pytest.mark.parametrize('prefix', ['', '/api/v3'])
def test_complete_observation_follows_documented_canonical_path_with_api_prefix(prefix):
    runtime = replace(config(), api_base_url='https://api.example.test' + prefix)
    second, third = (canonical_url(p, base=runtime.api_base_url) for p in (2, 3))
    fake = FakeTransport(
        response([issue(1), issue(9, pull_request=None)], link=next_link(2, url=second)),
        response([issue(1), issue(2, state='closed')], link=next_link(3, url=third)),
        response([issue(3)]),
    )
    result = GitHubEngineeringAdapter(runtime, transport=fake).observe_issues()
    assert [call[0].url for call in fake.calls] == [
        runtime.issue_url + '?state=all&per_page=100&page=1', second, third,
    ]
    assert all(call[0].method == 'GET' for call in fake.calls)
    assert [i.identity for i in result.issues] == [(SCOPE, n) for n in (1, 2, 3)]
    assert result.issues[1].state == 'closed'
    assert len(result.matching(lambda i: i.title == 'controlled title')) == 3
    trace = result.trace
    assert (trace.attempt_count, trace.pages_fetched, trace.raw_entries,
            trace.excluded_prs, trace.repeated_identities, trace.distinct_issues) == (3, 3, 5, 1, 1, 3)
    assert trace.complete
    assert [attempt.request.url for attempt in trace.attempts] == [call[0].url for call in fake.calls]
    assert all('authorization' not in dict(attempt.request.headers) for attempt in trace.attempts)
    assert TOKEN not in repr(trace) + repr(asdict(trace))


@pytest.mark.parametrize('changed_url', [
    canonical_url(3, repository_id=1300193),
    URL + '?state=all&per_page=100&page=3',
    URL.replace('test-repository', 'other') + '?state=all&per_page=100&page=3',
    BASE + '/repositories/1300192/pulls?state=all&per_page=100&page=3',
    canonical_url(3, base=BASE.replace('/api/v3', '/api/v4')),
    canonical_url(3, base='https://evil.test/api/v3'),
    canonical_url(3, base=BASE.replace('https:', 'http:')),
])
def test_canonical_binding_rejects_later_path_or_origin_switch_before_dispatch(changed_url):
    client, fake = adapter(
        response([issue(1)], link=next_link(2, url=canonical_url(2))),
        response([issue(2)], link=next_link(3, url=changed_url)),
        response([issue(3)]),
    )
    with pytest.raises(GitHubEngineeringError, match='unsafe_or_malformed_pagination') as captured:
        client.observe_issues()
    assert [call[0].url for call in fake.calls] == [
        URL + '?state=all&per_page=100&page=1', canonical_url(2),
    ]
    assert len(fake.outcomes) == 1 and captured.value.trace.attempt_count == 2
    assert not captured.value.trace.complete
    assert captured.value.__context__ is None and captured.value.__cause__ is None
    assert TOKEN not in repr(captured.value) + repr(captured.value.trace)


@pytest.mark.parametrize('path', [
    '/api/v3/repositories/not-an-id/issues', '/api/v3/repositories/0/issues',
    '/api/v3/repositories/-1/issues', '/api/v3/repositories/1.5/issues',
    '/api/v3/repositories/01300192/issues', '/api/v3/repositories/1300192/pulls',
    '/api/v3/search/issues', '/repositories/1300192/issues',
    '/api/v4/repositories/1300192/issues', '/api/v3/../repositories/1300192/issues',
])
def test_first_canonical_target_rejects_invalid_id_prefix_or_arbitrary_endpoint(path):
    url = 'https://api.example.test' + path + '?state=all&per_page=100&page=2'
    client, fake = adapter(response([], link=next_link(2, url=url)), response([]))
    with pytest.raises(GitHubEngineeringError, match='unsafe_or_malformed_pagination'):
        client.observe_issues()
    assert len(fake.calls) == 1


@pytest.mark.parametrize('query', [
    'state=open&per_page=100&page=2', 'state=all&per_page=30&page=2',
    'state=all&per_page=100&page=0', 'state=all&per_page=100&page=-1',
    'state=all&per_page=100&page=two', 'state=all&per_page=100&page=2&page=3',
    'per_page=100&page=2', 'state=all&page=2', 'state=all&per_page=100',
    *[f'state=all&per_page=100&page=2&{name}=narrow' for name in (
        'since', 'labels', 'creator', 'assignee', 'milestone', 'type', 'issue_field',
    )],
])
def test_canonical_path_preserves_query_invariants_before_dispatch(query):
    url = BASE + '/repositories/1300192/issues?' + query
    client, fake = adapter(response([], link=next_link(2, url=url)), response([]))
    with pytest.raises(GitHubEngineeringError, match='unsafe_or_malformed_pagination') as captured:
        client.observe_issues()
    assert len(fake.calls) == 1 and not captured.value.trace.complete


@pytest.mark.parametrize('url', [
    canonical_url(2, base='https://evil.test/api/v3'),
    canonical_url(2, base=BASE.replace('https:', 'http:')),
    canonical_url(2, base=BASE.replace('api.example', 'user@api.example')),
    canonical_url(2, base=BASE.replace('api.example', f'user:{TOKEN}@api.example')),
    canonical_url(2) + '#' + TOKEN,
    canonical_url(2) + '&secret=' + TOKEN,
])
def test_first_canonical_url_origin_credentials_and_secrets_rejected(url):
    client, fake = adapter(response([], link=next_link(2, url=url)), response([]))
    with pytest.raises(GitHubEngineeringError, match='unsafe_or_malformed_pagination') as captured:
        client.observe_issues()
    assert len(fake.calls) == 1
    assert captured.value.__context__ is None and captured.value.__cause__ is None
    assert TOKEN not in repr(captured.value) + repr(captured.value.__dict__)


def test_canonical_cycle_reordered_query_detected_without_redispatch():
    page2, page3 = canonical_url(2), canonical_url(3)
    loop = BASE + '/repositories/1300192/issues?page=2&per_page=100&state=all'
    client, fake = adapter(
        response([], link=next_link(2, url=page2)),
        response([], link=next_link(3, url=page3)),
        response([], link=next_link(2, url=loop)), response([]),
    )
    with pytest.raises(GitHubEngineeringError, match='pagination_loop') as captured:
        client.observe_issues()
    assert [call[0].url for call in fake.calls] == [
        URL + '?state=all&per_page=100&page=1', page2, page3,
    ]
    assert captured.value.trace.attempt_count == 3 and not captured.value.trace.complete
    assert len(fake.outcomes) == 1


def test_original_pagination_may_canonicalize_later_and_binding_is_per_traversal():
    # A canonical ID is provider-issued state, never cached as configured identity.
    first_id, next_id = 1300192, 1300193
    client, fake = adapter(
        response([], link=next_link(2)),
        response([], link=next_link(3, url=canonical_url(3, repository_id=first_id))),
        response([issue(1)]),
        response([], link=next_link(2, url=canonical_url(2, repository_id=next_id))),
        response([issue(2)]),
    )
    first, second = client.observe_issues(), client.observe_issues()
    assert first.trace.complete and first.trace.pages_fetched == 3
    assert second.trace.complete and second.trace.pages_fetched == 2
    assert fake.calls[1][0].url == URL + '?state=all&per_page=100&page=2'
    assert fake.calls[2][0].url == canonical_url(3, repository_id=first_id)
    assert fake.calls[4][0].url == canonical_url(2, repository_id=next_id)
    assert [first.issues[0].identity, second.issues[0].identity] == [(SCOPE, 1), (SCOPE, 2)]

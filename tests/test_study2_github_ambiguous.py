"""Deterministic fake-socket checks; never execute the live command."""

from dataclasses import replace
import http.client
import importlib.util
import json
from pathlib import Path

import pytest

import retry_semantics.study2.github_adapter as adapter_module
from retry_semantics.study2.github_adapter import (
    EngineeringFaultPoint as Fault, EngineeringTrace, GitHubConfig,
    GitHubEngineeringAdapter, GitHubEngineeringError, LifecycleStage as Stage,
    ObservationResult, OfflineFaultTransport, _LiveAmbiguityTransport,
)
from retry_semantics.study2.github_engineering_visibility import (
    is_after_send_ambiguity_trace, probe_engineering_visibility,
)

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/smoke_study2_github_ambiguous.py'
SPEC = importlib.util.spec_from_file_location('github_ambiguity', SCRIPT)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
TOKEN = 'offline-ambiguity-secret-never-retained'
CONFIG = GitHubConfig('https://api.example.test', 'owner', 'repo', TOKEN, '2022-11-28')


def enable(monkeypatch):
    monkeypatch.setenv(smoke.GUARD, '1')
    for name, value in zip(smoke.REQUIRED_ENV, (
            TOKEN, CONFIG.owner, CONFIG.repository, CONFIG.api_base_url, CONFIG.api_version)):
        monkeypatch.setenv(name, value)


class WireHarness:
    """Real stdlib HTTP serialization; fake sockets and GET-only responses."""
    def __init__(self, monkeypatch, pages=('one',), failure=None):
        self.connections = []
        self.content = {}
        self.pages = iter(pages)
        self.events = []
        self.create_calls = 0
        harness = self
        original_event = adapter_module._event
        original_create = GitHubEngineeringAdapter.create_issue

        def event(events, stage, point=None):
            harness.events.append(stage)
            original_event(events, stage, point)

        def create(client, **kwargs):
            harness.create_calls += 1
            return original_create(client, **kwargs)

        monkeypatch.setattr(adapter_module, '_event', event)
        monkeypatch.setattr(GitHubEngineeringAdapter, 'create_issue', create)

        class Socket:
            def __init__(self):
                self.chunks = []

            def sendall(self, data):
                if failure == 'send' and self.chunks:
                    self.chunks.append(data[:3])
                    raise ConnectionError(TOKEN)
                self.chunks.append(data)

            def close(self):
                pass

        class Connection(http.client.HTTPConnection):
            def __init__(self, host, port, timeout):
                if failure == 'construct':
                    raise OSError(TOKEN)
                super().__init__(host, port, timeout=timeout)
                self.socket = Socket()
                self.closed = False
                self.response_calls = 0
                harness.connections.append(self)

            def connect(self):
                if failure == 'connect':
                    raise TimeoutError(TOKEN)
                self.sock = self.socket

            def putrequest(self, method, *args, **kwargs):
                self.method = method
                if method == 'GET':
                    # Observation must follow terminal mutation and closure.
                    assert harness.connections[0].closed
                    assert Stage.INJECTED_FAULT in harness.events
                    assert self is not harness.connections[0]
                super().putrequest(method, *args, **kwargs)

            def endheaders(self, body=None, **kwargs):
                if self.method == 'POST':
                    harness.content.update(json.loads(body))
                super().endheaders(body, **kwargs)

            def getresponse(self):
                self.response_calls += 1
                assert self.method == 'GET', 'create response must never be read'
                page = next(harness.pages)
                if page == 'failure':
                    raise TimeoutError(TOKEN)
                if isinstance(page, tuple):
                    kind, link = page
                else:
                    kind, link = page, None
                issue = dict(harness.content, number=17, state='closed')
                entries = []
                if kind in ('one', 'two', 'mismatch', 'duplicate_pr'):
                    entries = [issue]
                if kind == 'two':
                    entries.append(dict(issue, number=18))
                if kind == 'mismatch':
                    issue['body'] += 'changed'
                if kind == 'duplicate_pr':
                    entries += [dict(issue), dict(issue, number=99, pull_request={})]
                if kind == 'invalid':
                    entries = [{}]

                class Response:
                    status = 200

                    def getheaders(self):
                        headers = [('Content-Type', 'application/json'),
                                   ('Authorization', TOKEN), ('X-GitHub-Request-Id', TOKEN)]
                        if link:
                            headers.append(('Link', link))
                        return headers

                    def read(self):
                        return json.dumps(entries).encode()

                return Response()

            def close(self):
                self.closed = True
                super().close()
                if failure == 'close':
                    raise OSError(TOKEN)

        monkeypatch.setattr(http.client, 'HTTPSConnection', Connection)
        self.factory = Connection

    @property
    def post_count(self):
        return sum(chunk.startswith(b'POST ') for conn in self.connections
                   for chunk in conn.socket.chunks)


@pytest.mark.parametrize('guard', [None, '', '0', 'true'])
def test_dedicated_gate_required_normal_gate_insufficient(monkeypatch, tmp_path, guard):
    enable(monkeypatch)
    monkeypatch.setenv('STUDY2_GITHUB_LIVE_ENGINEERING', '1')
    if guard is None:
        monkeypatch.delenv(smoke.GUARD)
    else:
        monkeypatch.setenv(smoke.GUARD, guard)
    monkeypatch.setattr(http.client, 'HTTPSConnection', lambda *a, **k: pytest.fail('network'))
    assert smoke.main() == 2
    with pytest.raises(ValueError, match='dedicated'):
        smoke.run_ambiguity_check(CONFIG, tmp_path)
    request = GitHubEngineeringAdapter(CONFIG).prepare_create_issue(title='title', body='body')
    with pytest.raises(ValueError, match='dedicated'):
        _LiveAmbiguityTransport(CONFIG, request)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('missing', smoke.REQUIRED_ENV)
def test_every_runtime_value_required(monkeypatch, tmp_path, missing):
    enable(monkeypatch)
    monkeypatch.delenv(missing)
    monkeypatch.setattr(http.client, 'HTTPSConnection', lambda *a, **k: pytest.fail('network'))
    assert smoke.main() == 2
    with pytest.raises(ValueError):
        smoke.run_ambiguity_check(CONFIG, tmp_path)


@pytest.mark.parametrize('name', smoke.REQUIRED_ENV)
def test_configuration_must_match_gate(monkeypatch, tmp_path, name):
    enable(monkeypatch)
    monkeypatch.setenv(name, 'mismatched')
    with pytest.raises(ValueError):
        smoke.run_ambiguity_check(CONFIG, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('pages,state,traversals', [
    (('zero', 'one'), 'PROVIDER_STATE_OBSERVED_EXECUTED', 2),
    (('one',), 'PROVIDER_STATE_OBSERVED_EXECUTED', 1),
    (('zero', 'zero', 'zero'), 'PROVIDER_STATE_NOT_OBSERVED_WITHIN_ENGINEERING_WINDOW', 3),
    (('two', 'two', 'two'), 'PROVIDER_STATE_MULTIPLE_MATCHES', 3),
    (('two', 'one'), 'PROVIDER_STATE_MULTIPLE_MATCHES', 2),
    (('failure',), 'OBSERVATION_FAILED', 1),
    (('invalid',), 'OBSERVATION_FAILED', 1),
    (('zero', 'failure'), 'OBSERVATION_FAILED', 2),
    (('mismatch', 'mismatch', 'mismatch'), 'PROVIDER_STATE_CONTENT_MISMATCH', 3),
    (('duplicate_pr',), 'PROVIDER_STATE_OBSERVED_EXECUTED', 1),
])
def test_single_post_unread_response_get_only_classification_safe_artifact(
        monkeypatch, tmp_path, capsys, pages, state, traversals):
    enable(monkeypatch)
    fake = WireHarness(monkeypatch, pages)
    old = tmp_path / 'previous.json'
    old.write_text('historical evidence')
    path, passed = smoke.run_ambiguity_check(CONFIG, tmp_path, interval_seconds=0)
    encoded = path.read_text()
    artifact = json.loads(encoded)
    assert fake.create_calls == fake.post_count == 1
    assert fake.connections[0].response_calls == 0
    assert all(conn.auto_open == 0 and conn.closed for conn in fake.connections)
    assert [conn.method for conn in fake.connections] == ['POST'] + ['GET'] * traversals
    assert artifact['provider_state_classification'] == state
    assert passed == (state == 'PROVIDER_STATE_OBSERVED_EXECUTED')
    assert artifact['classification'] == smoke.BANNER
    assert smoke.BANNER in capsys.readouterr().out
    assert old.read_text() == 'historical evidence'
    assert artifact['pre_dispatch_marker'] in fake.content['title']
    assert artifact['expected_title'] == fake.content['title']
    assert artifact['expected_body'] == fake.content['body']
    trace = artifact['mutation_trace']
    assert trace['attempt_count'] == 1 and trace['outcome'] == 'injected_fault'
    attempt, = trace['attempts']
    assert attempt['status'] is None and attempt['response_metadata'] == []
    assert bytes.fromhex(attempt['request']['body_hex']) == json.dumps(
        fake.content, ensure_ascii=False, separators=(',', ':')).encode()
    assert [event['stage'] for event in attempt['lifecycle']] == [
        stage.value for stage in list(Stage)[:5]] + ['INJECTED_FAULT']
    assert attempt['lifecycle'][-1]['fault_point'] == Fault.AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE
    evidence = artifact['mutation_evidence']
    assert evidence['local_request_send_completed'] and evidence['injected_fault_fired']
    assert evidence['response_unread_confirmed']
    assert evidence['local_mutation_outcome'] == 'locally_ambiguous'
    assert not any(evidence[key] for key in (
        'response_wait_started', 'response_headers_received', 'response_body_completed',
        'create_response_identity_available'))
    assert not any(term in encoded.lower() for term in (
        TOKEN.lower(), 'authorization', 'replay', 'regeneration', 'h0', 'h1'))
    records = artifact['observation_traversals']
    assert len(records) == traversals
    assert [record['index'] for record in records] == list(range(1, traversals + 1))
    for record in records:
        for read in record['trace']['attempts']:
            assert read['request']['method'] == 'GET'
            assert 'state=all&per_page=100' in read['request']['url']
    if pages == ('zero', 'one'):
        assert records[0]['matching_distinct_identities'] == []
        assert records[1]['matching_distinct_identities'] == [[['owner', 'repo'], 17]]
        assert records[1]['exact_content_checks'] == [
            {'identity': [['owner', 'repo'], 17], 'title_exact': True, 'body_exact': True}]
    if state == 'OBSERVATION_FAILED':
        assert records[-1]['matching_distinct_identities'] is None
        assert records[-1]['exact_content_checks'] is None
        assert not records[-1]['trace']['complete']
    if pages == ('duplicate_pr',):
        assert records[0]['trace']['excluded_prs'] == 1
        assert records[0]['trace']['repeated_identities'] == 1


@pytest.mark.parametrize('failure,posts', [('construct', 0), ('connect', 0), ('send', 1)])
def test_failure_before_completion_stops_without_observation_or_retry(
        monkeypatch, tmp_path, failure, posts):
    enable(monkeypatch)
    fake = WireHarness(monkeypatch, failure=failure)
    path, passed = smoke.run_ambiguity_check(CONFIG, tmp_path, interval_seconds=0)
    artifact = json.loads(path.read_text())
    assert fake.create_calls == 1 and fake.post_count == posts
    assert not passed and not artifact['observation_traversals']
    assert Stage.LOCAL_REQUEST_SEND_COMPLETED not in fake.events
    assert Stage.INJECTED_FAULT not in fake.events
    assert not artifact['mutation_evidence']['response_unread_confirmed']
    assert artifact['provider_state_classification'] == 'MUTATION_STOPPED_BEFORE_EXPECTED_FAULT'
    assert TOKEN not in path.read_text()


def test_close_failure_cannot_enable_response_processing(monkeypatch, tmp_path):
    enable(monkeypatch)
    fake = WireHarness(monkeypatch, failure='close')
    _, passed = smoke.run_ambiguity_check(CONFIG, tmp_path, interval_seconds=0)
    assert passed and fake.post_count == fake.create_calls == 1
    assert fake.connections[0].response_calls == 0


def test_one_complete_multipage_traversal_then_failed_page_is_unknown(monkeypatch, tmp_path):
    enable(monkeypatch)
    link = f'<{CONFIG.api_base_url}/repositories/123/issues?state=all&per_page=100&page=2>; rel="next"'
    fake = WireHarness(monkeypatch, (('one', link), 'failure'))
    path, passed = smoke.run_ambiguity_check(CONFIG, tmp_path, interval_seconds=0)
    artifact = json.loads(path.read_text())
    assert not passed and artifact['provider_state_classification'] == 'OBSERVATION_FAILED'
    record, = artifact['observation_traversals']
    assert record['trace']['attempt_count'] == 2 and record['trace']['distinct_issues'] == 1
    assert record['matching_distinct_identities'] is None
    assert fake.post_count == 1


def test_complete_multipage_dedup_pr_exclusion(monkeypatch, tmp_path):
    enable(monkeypatch)
    link = f'<{CONFIG.api_base_url}/repositories/123/issues?state=all&per_page=100&page=2>; rel="next"'
    fake = WireHarness(monkeypatch, (('one', link), 'duplicate_pr'))
    path, passed = smoke.run_ambiguity_check(CONFIG, tmp_path, interval_seconds=0)
    record, = json.loads(path.read_text())['observation_traversals']
    assert passed and record['trace']['pages_fetched'] == record['trace']['attempt_count'] == 2
    assert record['trace']['distinct_issues'] == record['trace']['excluded_prs'] == 1
    assert record['trace']['repeated_identities'] == 2
    assert fake.post_count == 1


@pytest.mark.parametrize('change', ['second_call', 'get', 'guard_removed', 'request_changed'])
def test_transport_one_use_and_dispatch_gate(monkeypatch, change):
    enable(monkeypatch)
    fake = WireHarness(monkeypatch)
    request = GitHubEngineeringAdapter(CONFIG).prepare_create_issue(title='title', body='body')
    transport = _LiveAmbiguityTransport(CONFIG, request)
    client = GitHubEngineeringAdapter(CONFIG, transport=transport)
    if change == 'second_call':
        with pytest.raises(GitHubEngineeringError) as fault:
            client.create_issue(title='title', body='body')
        assert fault.value.category == 'injected_fault'
    elif change == 'get':
        request = replace(request, method='GET')
    elif change == 'guard_removed':
        monkeypatch.delenv(smoke.GUARD)
    else:
        request = replace(request, body=b'{}')
    with pytest.raises(ValueError):
        transport(request, TOKEN, CONFIG.timeout_seconds, lifecycle=[])
    assert fake.post_count == (1 if change == 'second_call' else 0)
    assert all(conn.response_calls == 0 for conn in fake.connections)


@pytest.mark.parametrize('options', [
    {'max_traversals': 0}, {'max_traversals': True}, {'interval_seconds': -1},
    {'interval_seconds': float('nan')}, {'interval_seconds': float('inf')},
])
def test_bounds_validated_before_mutation(monkeypatch, tmp_path, options):
    enable(monkeypatch)
    fake = WireHarness(monkeypatch)
    with pytest.raises(ValueError):
        smoke.run_ambiguity_check(CONFIG, tmp_path, **options)
    assert not fake.connections and fake.create_calls == 0


def test_artifact_exclusive_reservation_precedes_mutation(monkeypatch, tmp_path):
    enable(monkeypatch)
    fake = WireHarness(monkeypatch)
    monkeypatch.setattr(smoke.uuid, 'uuid4', lambda: type('UUID', (), {'hex': 'fixed'})())
    previous = tmp_path / 'github-ambiguity-engineering-ENGINEERING-AMBIGUITY-ONLY-fixed.json'
    previous.write_text('previous')
    with pytest.raises(FileExistsError):
        smoke.run_ambiguity_check(CONFIG, tmp_path)
    assert previous.read_text() == 'previous'
    assert fake.create_calls == 0 and not fake.connections


@pytest.mark.parametrize('point', list(Fault))
def test_visibility_accepts_only_after_send_fault_without_fabricating_201(monkeypatch, point):
    fake = WireHarness(monkeypatch)
    client = GitHubEngineeringAdapter(CONFIG, transport=OfflineFaultTransport(fake.factory, point))
    with pytest.raises(GitHubEngineeringError) as caught:
        client.create_issue(title='known-marker', body='body')
    trace = caught.value.trace
    assert is_after_send_ambiguity_trace(trace) == (point is Fault.AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE)
    calls = []
    def observe():
        calls.append('GET')
        return ObservationResult((), EngineeringTrace('observe_issues', outcome='partial'))
    if point is Fault.BEFORE_REQUEST_SEND:
        with pytest.raises(ValueError):
            probe_engineering_visibility(observe, marker='known-marker',
                expected_title='known-marker', expected_body='body', mutation_trace=trace)
        assert not calls
    else:
        result = probe_engineering_visibility(observe, marker='known-marker',
            expected_title='known-marker', expected_body='body', mutation_trace=trace)
        assert result.mutation_trace is trace and trace.attempts[0].status is None
        assert result.outcome == 'observation_failed' and calls == ['GET']


def test_opaque_fault_trace_is_rejected():
    assert not is_after_send_ambiguity_trace(EngineeringTrace('create_issue', outcome='injected_fault'))

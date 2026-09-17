"""Synthetic engineering-only visibility checks; all transports are offline."""

from dataclasses import FrozenInstanceError, asdict, replace
import json

import pytest

from retry_semantics.study2.github_adapter import (
    EngineeringTrace, GitHubConfig, GitHubEngineeringAdapter, GitHubEngineeringError,
    HTTPAttempt, HTTPResponse, ObservationResult,
)
from retry_semantics.study2.github_engineering_visibility import probe_engineering_visibility

MARKER = 'caller-supplied-engineering-token'
TITLE = 'controlled ' + MARKER
BODY = f'{MARKER}\nRaw café 🚀, quote " and slash \\.\n'
TOKEN = 'offline-secret-never-retained'
CONFIG = GitHubConfig('https://api.example.test', 'owner', 'repo', TOKEN, '2022-11-28')


def entry(number=1, **changes):
    return {'number': number, 'title': TITLE, 'body': BODY, 'state': 'open', **changes}


def response(value, *, link=None, status=200):
    headers = (('Content-Type', 'application/json'),)
    if link:
        headers += (('Link', link),)
    return HTTPResponse(status, headers, json.dumps(value).encode())


def mutation_trace():
    # Historical trace fixture only: no mutation call, even to a fake transport.
    request = GitHubEngineeringAdapter(CONFIG).prepare_create_issue(title=TITLE, body=BODY)
    attempt = HTTPAttempt(1, request, True, True, 'http_response', 201)
    return EngineeringTrace('create_issue', (attempt,), 'success', complete=True)


class FakeTime:
    def __init__(self):
        self.elapsed = 0.0
        self.sleeps = []

    def clock(self):
        return self.elapsed

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.elapsed += seconds


class GETOnlyTransport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.clock = FakeTime()

    def __call__(self, request, token, timeout):
        assert request.method == 'GET', 'engineering probe must never mutate'
        self.requests.append(request)
        self.clock.elapsed += 0.25
        value = self.outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def setup(*outcomes):
    transport = GETOnlyTransport(*outcomes)
    adapter = GitHubEngineeringAdapter(CONFIG, transport=transport)
    # Even asking for the mutation method fails: only a bound reader is passed.
    adapter.create_issue = lambda **kwargs: pytest.fail('creation forbidden')
    return adapter, transport


def probe(observe, clock, **changes):
    options = dict(marker=MARKER, expected_title=TITLE, expected_body=BODY,
                   mutation_trace=mutation_trace(), clock=clock.clock, sleep=clock.sleep)
    options.update(changes)
    return probe_engineering_visibility(observe, **options)


def test_immediate_zero_later_one_separate_get_traces_elapsed_and_historical_mutation():
    adapter, transport = setup(response([]), response([entry()]), response([entry(2)]))
    historical = mutation_trace()
    result = probe(adapter.observe_issues, transport.clock,
                   interval_seconds=0.5, mutation_trace=historical)
    assert [request.method for request in transport.requests] == ['GET', 'GET']
    assert len(transport.outcomes) == 1
    assert result.mutation_trace is historical and historical.attempt_count == 1
    assert result.convergence_observed and result.outcome == 'exact_one_resource_visible'
    first, second = result.traversals
    assert first.index == 1 and second.index == 2
    assert first.trace is not second.trace
    assert first.trace.complete and first.trace.raw_entries == first.trace.distinct_issues == 0
    assert first.matching_distinct_identities == ()
    assert first.controlled_content_observed is first.exact_content_preserved is False
    assert second.trace.complete and second.trace.raw_entries == second.trace.distinct_issues == 1
    assert second.matching_distinct_identities == ((('owner', 'repo'), 1),)
    assert second.controlled_content_observed is second.exact_content_preserved is True
    assert [r.trace.attempt_count for r in result.traversals] == [1, 1]
    assert [(r.started_elapsed_seconds, r.ended_elapsed_seconds) for r in result.traversals] == [(0, 0.25), (0.75, 1)]
    assert transport.clock.sleeps == [0.5]
    assert TOKEN not in repr(result) + repr(asdict(result))


def test_immediate_one_stops_without_sleep_or_second_traversal():
    adapter, transport = setup(response([entry()]), response([]))
    result = probe(adapter.observe_issues, transport.clock)
    assert result.convergence_observed and len(result.traversals) == len(transport.requests) == 1
    assert not transport.clock.sleeps and len(transport.outcomes) == 1
    assert result.max_traversals == 3 and result.interval_seconds == 1.0


@pytest.mark.parametrize('failure', [TimeoutError(TOKEN), response([], status=429), response([{}])])
def test_failed_traversal_is_unknown_stops_without_retry_or_zero_matches(failure):
    adapter, transport = setup(failure, response([entry()]))
    result = probe(adapter.observe_issues, transport.clock)
    assert not result.convergence_observed and result.outcome == 'observation_failed'
    record, = result.traversals
    assert not record.trace.complete and record.error_category is not None
    assert record.matching_distinct_identities is None
    assert record.controlled_content_observed is record.exact_content_preserved is None
    assert len(transport.requests) == 1 and not transport.clock.sleeps
    assert TOKEN not in repr(result)


def test_failed_second_page_keeps_its_partial_trace_without_interpreting_matches():
    link = '<' + CONFIG.issue_url + '?state=all&per_page=100&page=2>; rel="next"'
    adapter, transport = setup(response([entry()], link=link), ConnectionError(TOKEN))
    result = probe(adapter.observe_issues, transport.clock)
    record, = result.traversals
    assert record.trace.attempt_count == len(transport.requests) == 2
    assert record.trace.distinct_issues == 1 and not record.trace.complete
    assert record.matching_distinct_identities is None and not result.convergence_observed
    assert not transport.clock.sleeps


def test_returned_incomplete_result_cannot_be_interpreted_as_zero():
    trace = EngineeringTrace('observe_issues', outcome='partial')
    result = probe(lambda: ObservationResult((), trace), FakeTime())
    record, = result.traversals
    assert record.trace is trace and record.matching_distinct_identities is None
    assert record.error_category == 'incomplete_or_invalid_traversal'
    assert not result.convergence_observed


@pytest.mark.parametrize('contents', [
    [entry(title=TITLE + ' changed')], [entry(body=BODY + ' changed')],
    [entry(body=None)], [entry(1), entry(2)],
])
def test_mismatch_or_two_distinct_matches_do_not_converge(contents):
    adapter, transport = setup(response(contents), response(contents))
    result = probe(adapter.observe_issues, transport.clock, max_traversals=2)
    assert not result.convergence_observed and result.outcome == 'traversal_bound_exhausted'
    assert len(result.traversals) == 2 and len(transport.requests) == 2
    assert all(r.controlled_content_observed for r in result.traversals)
    assert transport.clock.sleeps == [1.0]
    if len(contents) == 2:
        assert result.traversals[0].exact_content_preserved
        assert len(result.traversals[0].matching_distinct_identities) == 2
    else:
        assert not result.traversals[0].exact_content_preserved


def test_configured_count_bound_and_no_sleep_after_last_traversal():
    adapter, transport = setup(*[response([]) for _ in range(5)])
    result = probe(adapter.observe_issues, transport.clock, max_traversals=4, interval_seconds=0.5)
    assert result.max_traversals == 4 and result.interval_seconds == 0.5
    assert len(result.traversals) == len(transport.requests) == 4
    assert len(transport.outcomes) == 1 and transport.clock.sleeps == [0.5] * 3
    assert result.outcome == 'traversal_bound_exhausted' and not result.convergence_observed


def test_zero_interval_is_explicit_and_does_not_sleep():
    adapter, transport = setup(response([]), response([entry()]))
    result = probe(adapter.observe_issues, transport.clock, interval_seconds=0)
    assert result.convergence_observed and not transport.clock.sleeps


@pytest.mark.parametrize('options', [
    dict(max_traversals=0), dict(max_traversals=-1), dict(max_traversals=True),
    dict(interval_seconds=-1), dict(interval_seconds=float('inf')),
    dict(interval_seconds=float('nan')), dict(interval_seconds=True),
    dict(marker=''), dict(expected_body=None), dict(expected_title=''),
    dict(expected_title='no correlation', expected_body='no correlation'),
    dict(mutation_trace=EngineeringTrace('create_issue')),
    dict(mutation_trace=replace(mutation_trace(), operation='other')),
    lambda: dict(mutation_trace=replace(mutation_trace(), attempts=())),
])
def test_invalid_control_inputs_fail_before_observation_or_sleep(options):
    adapter, transport = setup()
    with pytest.raises(ValueError):
        if callable(options):
            options = options()
        probe(adapter.observe_issues, transport.clock, **options)
    assert not transport.requests and not transport.clock.sleeps


def test_engineering_classification_immutable_and_no_paper_labels():
    adapter, transport = setup(response([entry()]))
    result = probe(adapter.observe_issues, transport.clock)
    assert result.classification == 'ENGINEERING VALIDATION — NOT PAPER DATA'
    names = repr(asdict(result)).lower()
    assert not any(term in names for term in ('replay', 'regeneration', 'h0', 'h1', 'arm', 'scenario', 'replicate'))
    with pytest.raises(FrozenInstanceError):
        result.convergence_observed = False
    with pytest.raises(FrozenInstanceError):
        result.traversals[0].matching_distinct_identities = ()


def test_one_complete_multipage_traversal_stays_one_probe_record():
    link = '<' + CONFIG.api_base_url + '/repositories/123/issues?state=all&per_page=100&page=2>; rel="next"'
    adapter, transport = setup(response([], link=link), response([entry()]), response([]))
    result = probe(adapter.observe_issues, transport.clock)
    record, = result.traversals
    assert result.convergence_observed and record.trace.attempt_count == record.trace.pages_fetched == 2
    assert len(transport.requests) == 2 and not transport.clock.sleeps
    assert record.matching_distinct_identities == ((('owner', 'repo'), 1),)

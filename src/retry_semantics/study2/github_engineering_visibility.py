"""Bounded GET-only engineering visibility check. NEVER paper execution.

ENGINEERING VALIDATION — NOT PAPER DATA. Repeated traversals live here, above
GitHubEngineeringAdapter.observe_issues(); the adapter remains a single traversal.
The supplied observation callable is trusted code, normally adapter.observe_issues.
This module never receives a client with a mutation capability or credentials.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import math
import time

from retry_semantics.study2.github_adapter import (
    EngineeringTrace, GitHubEngineeringError, ObservationResult,
)


@dataclass(frozen=True, slots=True)
class EngineeringVisibilityTraversal:
    index: int
    started_elapsed_seconds: float
    ended_elapsed_seconds: float
    trace: EngineeringTrace
    controlled_content_observed: bool | None
    exact_content_preserved: bool | None
    matching_distinct_identities: tuple[tuple[tuple[str, str], int], ...] | None
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class EngineeringVisibilityResult:
    classification: str = field(default="ENGINEERING VALIDATION — NOT PAPER DATA", init=False)
    marker: str
    expected_title: str
    expected_body: str
    mutation_trace: EngineeringTrace
    max_traversals: int
    interval_seconds: float
    traversals: tuple[EngineeringVisibilityTraversal, ...]
    convergence_observed: bool
    outcome: str


def probe_engineering_visibility(
    observe_issues: Callable[[], ObservationResult], *,
    marker: str,
    expected_title: str,
    expected_body: str,
    mutation_trace: EngineeringTrace,
    max_traversals: int = 3,
    interval_seconds: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> EngineeringVisibilityResult:
    """Check an existing engineering mutation, without creating anything.

    Defaults (3 traversals, 1 second between calls) are engineering convenience,
    not experimental semantics. The first traversal starts immediately; sleep
    occurs only between successful, nonconverged traversals with count remaining.
    Exactly one marker match with exact expected title/body stops successfully.
    A failed/incomplete traversal stops immediately and has unknown match fields,
    never zero. Count exhaustion is not a conclusion about mutation commitment.
    Elapsed times are relative to this probe, not the earlier mutation. Trace and
    traversal indices are local; historical observations are never rewritten.
    """
    if (type(marker) is not str or not marker or type(expected_title) is not str
            or not expected_title or type(expected_body) is not str
            or not (marker in expected_title or marker in expected_body)):
        raise ValueError("known engineering marker and expected content required")
    if type(max_traversals) is not int or max_traversals <= 0:
        raise ValueError("positive engineering traversal count required")
    if (type(interval_seconds) not in (int, float)
            or not math.isfinite(interval_seconds) or interval_seconds < 0):
        raise ValueError("finite nonnegative engineering interval required")
    if (not isinstance(mutation_trace, EngineeringTrace)
            or mutation_trace.operation != "create_issue"
            or mutation_trace.outcome != "success" or not mutation_trace.complete
            or mutation_trace.attempt_count != 1
            or mutation_trace.attempts[0].request.method != "POST"
            or mutation_trace.attempts[0].status != 201):
        raise ValueError("successful single-attempt engineering mutation trace required")

    start = clock()
    records = []
    converged = False
    outcome = "traversal_bound_exhausted"
    for index in range(1, max_traversals + 1):
        began = clock() - start
        error_category = None
        observed = None
        try:
            observed = observe_issues()
            trace = observed.trace
        except GitHubEngineeringError as error:
            trace = error.trace
            error_category = error.category
        ended = clock() - start
        if error_category is None and (
            not trace.complete or trace.outcome != "success"
            or trace.operation != "observe_issues"
            or not trace.attempts
            or any(attempt.request.method != "GET" for attempt in trace.attempts)
        ):
            error_category = "incomplete_or_invalid_traversal"
        identities = None
        content_observed = exact = None
        if error_category is None:
            matches = observed.matching(
                lambda issue: marker in issue.title or marker in (issue.body or ""))
            identities = tuple(issue.identity for issue in matches)
            content_observed = bool(matches)
            exact = bool(matches) and all(
                issue.title == expected_title and issue.body == expected_body for issue in matches)
            converged = len(identities) == 1 and exact
        records.append(EngineeringVisibilityTraversal(
            index, began, ended, trace, content_observed, exact, identities, error_category,
        ))
        if error_category is not None:
            outcome = "observation_failed"
            break
        if converged:
            outcome = "exact_one_resource_visible"
            break
        if index < max_traversals and interval_seconds:
            sleep(interval_seconds)
    return EngineeringVisibilityResult(
        marker, expected_title, expected_body, mutation_trace, max_traversals,
        interval_seconds, tuple(records), converged, outcome,
    )

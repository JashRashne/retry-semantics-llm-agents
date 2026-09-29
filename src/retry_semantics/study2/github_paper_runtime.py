"""Offline-testable GitHub paper request, recovery, and census boundaries.

The caller supplies a one-attempt transport and model continuation. This module
never obtains credentials, opens a connection, or authorizes collection.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.github_paper_manifest import (
    SELECTED_REPOSITORY, load_github_paper_manifest,
)

MAX_PAGES = 16
OBSERVATION_STARTS = (0, 600)
OBSERVATION_DEADLINES = (540, 1140)
MAX_RECOVERY_ACTIONS = 3
MAX_CONSTRUCTOR_ROUNDS = len(OBSERVATION_STARTS)
MAX_OBSERVATION_ROUNDS = len(OBSERVATION_STARTS)
MAX_BASELINE_GETS = MAX_PAGES
MAX_CONSTRUCTOR_GETS = MAX_CONSTRUCTOR_ROUNDS * MAX_PAGES
MAX_MODEL_LIST_GETS = MAX_RECOVERY_ACTIONS * MAX_PAGES
MAX_OBS_GETS = MAX_OBSERVATION_ROUNDS * MAX_PAGES
MAX_GETS_PER_ARM = (MAX_BASELINE_GETS + MAX_CONSTRUCTOR_GETS +
                    MAX_MODEL_LIST_GETS + MAX_OBS_GETS)
AMBIGUITY = "ToolError: The previous request timed out. Its outcome is unknown."


class GitHubPaperError(ValueError):
    """Invalid paper input or incomplete evidence."""


@dataclass(frozen=True, slots=True)
class FrozenIssueRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    arm_id: str
    marker: str

    @property
    def sha256(self) -> str:
        return sha256_hex(canonical_json_bytes({
            "method": self.method, "url": self.url,
            "headers": [list(header) for header in self.headers],
            "body_hex": self.body.hex(), "arm_id": self.arm_id,
            "marker": self.marker,
        }))


def _scope(manifest: dict[str, Any], arm: dict[str, Any], api_base: str,
           api_version: str) -> str:
    if (sha256_hex(canonical_json_bytes(manifest))
            != load_github_paper_manifest().manifest_hash
            or manifest.get("selected_repository") != SELECTED_REPOSITORY
            or arm.get("arm_id") is None
            or not re.fullmatch(r"rs2gh1-[0-9a-f]{32}", arm.get("arm_marker", ""))
            or api_base != "https://api.github.com"
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", api_version)):
        raise GitHubPaperError("unbound paper scope")
    return "https://api.github.com/repos/" + SELECTED_REPOSITORY + "/issues"


def serialize_create(manifest: dict[str, Any], arm: dict[str, Any], *,
                     title: str, body: str, api_base: str,
                     api_version: str) -> FrozenIssueRequest:
    """Add only the frozen arm suffix; Regeneration may alter semantic fields."""
    url = _scope(manifest, arm, api_base, api_version)
    suffix = arm.get("suffix")
    if (type(title) is not str or not title or type(body) is not str or not body
            or type(suffix) is not str
            or suffix != f"\n\n<!-- retry-semantics-study2-gh:v1:{arm['arm_marker']} -->"):
        raise GitHubPaperError("invalid issue request")
    payload = json.dumps({"title": title, "body": body + suffix},
                         ensure_ascii=False, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    headers = (("Accept", "application/vnd.github.raw+json"),
               ("X-GitHub-Api-Version", api_version),
               ("Content-Type", "application/json; charset=utf-8"))
    return FrozenIssueRequest("POST", url, headers, payload,
                              arm["arm_id"], arm["arm_marker"])


def expected_original(manifest: dict[str, Any], family: dict[str, Any],
                      arm: dict[str, Any], *, api_base: str,
                      api_version: str) -> FrozenIssueRequest:
    if family not in manifest.get("families", ()) or arm not in family.get("arms", ()):
        raise GitHubPaperError("arm absent from manifest")
    target = family["target_semantic_m"]
    request = serialize_create(manifest, arm, title=target["title"],
                               body=target["body"], api_base=api_base,
                               api_version=api_version)
    if (sha256_hex((target["body"] + arm["suffix"]).encode("utf-8"))
            != arm["provider_raw_body_sha256"]):
        raise GitHubPaperError("frozen body mismatch")
    return request


def exact_replay(stored: FrozenIssueRequest, expected: FrozenIssueRequest,
                 dispatch: Callable[[FrozenIssueRequest], HTTPResponse]) -> HTTPResponse:
    """One dispatch of the same immutable bytes, with no model or read call."""
    if type(stored) is not FrozenIssueRequest or stored != expected:
        raise GitHubPaperError("stored request differs from frozen original")
    result = dispatch(stored)
    if type(result) is not HTTPResponse:
        raise GitHubPaperError("missing raw transport result")
    return result


def _json(raw: bytes) -> Any:
    if type(raw) is not bytes or len(raw) > 8_000_000:
        raise GitHubPaperError("missing or oversized provider response")
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate provider JSON key")
                value[key] = item
            return value
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise GitHubPaperError("malformed provider response") from exc


def _header(response: HTTPResponse, name: str) -> str | None:
    values = [v for k, v in response.headers if k.lower() == name]
    if len(values) > 1:
        raise GitHubPaperError("duplicate response header")
    return values[0] if values else None


def validate_create_ack(request: FrozenIssueRequest,
                        response: HTTPResponse, api_version: str) -> int | None:
    """A visible non-201 status terminates this attempt, never proves noncommit."""
    if type(response) is not HTTPResponse or response.read_error is not None:
        return None
    if response.status != 201:
        return None
    selected = _header(response, "x-github-api-version-selected")
    if selected is not None and selected != api_version:
        return None
    entry = _json(response.body)
    sent = _json(request.body)
    if (type(entry) is not dict or type(entry.get("number")) is not int
            or entry["number"] <= 0 or "pull_request" in entry
            or entry.get("title") != sent["title"]
            or entry.get("body") != sent["body"]
            or entry.get("state") != "open"):
        return None
    return entry["number"]


@dataclass(frozen=True, slots=True)
class Census:
    complete: bool
    issues: tuple[tuple[int, str, str], ...]
    requests: int
    reason: str | None
    raw_entries: int

    def __post_init__(self) -> None:
        if (type(self.requests) is not int or not 0 <= self.requests <= MAX_PAGES
                or type(self.raw_entries) is not int or self.raw_entries < 0
                or (self.complete and (self.reason is not None or self.requests < 1))
                or (not self.complete and not self.reason)
                or any(type(item) is not tuple or len(item) != 3
                       or type(item[0]) is not int or type(item[1]) is not str
                       or type(item[2]) is not str for item in self.issues)):
            raise GitHubPaperError("invalid census evidence")


@dataclass(frozen=True, slots=True)
class ScheduledCensus:
    offset_seconds: int
    started_at: float | None
    deadline_at: float
    census: Census


def run_scheduled_censuses(manifest: dict[str, Any], arm: dict[str, Any], *,
                           api_version: str, anchor: float,
                           clock: Callable[[], float],
                           wait_until: Callable[[float], None],
                           fetch: Callable[[str], HTTPResponse],
                           semantic_target: dict[str, str] | None = None,
                           target: dict[str, str] | None = None,
                           ) -> tuple[ScheduledCensus, ...]:
    """OBS-1 +0/+600 starts; no shifted start, rescue, or third traversal."""
    if semantic_target is None:
        semantic_target = target
    observed: list[ScheduledCensus] = []
    for offset, deadline in zip(OBSERVATION_STARTS, OBSERVATION_DEADLINES):
        scheduled_start = anchor + offset
        limit = anchor + deadline
        if clock() < scheduled_start:
            wait_until(scheduled_start)
        started = clock()
        if started >= limit:
            observed.append(ScheduledCensus(
                offset, None, limit, Census(False, (), 0, "missed_start", 0)))
        else:
            census = bounded_census(manifest, arm, api_version=api_version,
                                    fetch=fetch, elapsed=lambda: clock() - scheduled_start)
            if clock() > limit:
                census = Census(False, census.issues, census.requests,
                                "completion_deadline", census.raw_entries)
            observed.append(ScheduledCensus(offset, started, limit, census))
        if semantic_target is not None:
            decisive = evaluate_census(arm, semantic_target, (observed[-1].census,), (),
                                       isolation_proven=True, baseline_clear=True)
            if decisive["status"] == "FAILURE" and decisive["state_correct"] == 0:
                break
    return tuple(observed)


def _next_url(link: str | None, current_page: int, canonical_path: str | None,
              initial_path: str) -> tuple[str | None, str | None]:
    if link is None:
        return None, canonical_path
    parts = [part.strip() for part in link.split(",")]
    next_parts = [part for part in parts if re.search(r';\s*rel="?next"?\s*$', part)]
    if not next_parts:
        seen_relations: set[str] = set()
        for part in parts:
            terminal = re.fullmatch(
                r'<([^<>]+)>;\s*rel="?(prev|first|last)"?', part)
            if terminal is None:
                raise GitHubPaperError("malformed terminal Link header")
            other_url, relation = terminal.groups()
            parsed_other = urlsplit(other_url)
            query_other = parse_qsl(parsed_other.query, strict_parsing=True, keep_blank_values=True)
            other_page = dict(query_other).get("page")
            _pagination_query(query_other, relation)
            if (relation in seen_relations or parsed_other.scheme != "https"
                    or parsed_other.netloc != "api.github.com"
                    or parsed_other.path != (canonical_path or initial_path)
                    or parsed_other.fragment
                    or dict(query_other)["state"] != "all"
                    or dict(query_other)["per_page"] != "100"
                    or not other_page or not other_page.isdecimal()
                    or (relation == "prev" and int(other_page) != current_page - 1)
                    or (relation == "first" and int(other_page) != 1)
                    or (relation == "last" and int(other_page) < current_page)):
                raise GitHubPaperError("unsafe terminal Link header")
            seen_relations.add(relation)
        if current_page > 1 and "prev" not in seen_relations:
            raise GitHubPaperError("terminal Link lacks previous page")
        return None, canonical_path
    if len(next_parts) != 1:
        raise GitHubPaperError("duplicate next link")
    match = re.fullmatch(r"<([^<>]+)>;\s*rel=\"?next\"?", next_parts[0])
    if match is None:
        raise GitHubPaperError("malformed next link")
    url = match.group(1)
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "api.github.com"
            or parsed.fragment or parsed.username or parsed.password
            or any(ord(c) < 33 for c in url)):
        raise GitHubPaperError("unsafe next link")
    allowed = parsed.path == initial_path or bool(re.fullmatch(
        r"/repositories/[1-9][0-9]*/issues", parsed.path))
    if not allowed or (canonical_path is not None and parsed.path != canonical_path):
        raise GitHubPaperError("pagination path changed")
    query = parse_qsl(parsed.query, strict_parsing=True, keep_blank_values=True)
    _pagination_query(query, "next")
    if dict(query)["page"] != str(current_page + 1):
        raise GitHubPaperError("pagination query changed")
    return url, parsed.path


def _pagination_query(query: list[tuple[str, str]], relation: str) -> None:
    """Preserve GitHub's opaque cursor, without relaxing the frozen query/scope."""
    values = dict(query)
    cursor = "after" if relation in ("next", "last") else "before"
    required = {"state", "per_page", "page"}
    if (len(query) != len(values) or set(values) not in (required, required | {cursor})
            or values.get("state") != "all" or values.get("per_page") != "100"
            or not values.get("page", "").isascii() or not values.get("page", "").isdecimal()
            or int(values["page"]) < 1):
        raise GitHubPaperError("pagination query changed")
    if cursor in values and (not 1 <= len(values[cursor]) <= 4096
                            or any(not 33 <= ord(c) <= 126 for c in values[cursor])):
        raise GitHubPaperError("invalid pagination cursor")


def bounded_census(manifest: dict[str, Any], arm: dict[str, Any], *,
                   api_version: str, fetch: Callable[[str], HTTPResponse],
                   elapsed: Callable[[], float]) -> Census:
    """Exactly one bounded traversal. Partial positives never become a zero."""
    initial = _scope(manifest, arm, "https://api.github.com", api_version)
    url = initial + "?state=all&per_page=100&page=1"
    issues: dict[int, tuple[int, str, str]] = {}
    seen_numbers: set[int] = set()
    raw_entries = 0
    canonical_path = None
    for page in range(1, MAX_PAGES + 1):
        if elapsed() > 540:
            return Census(False, tuple(issues.values()), page - 1, "deadline", raw_entries)
        response = fetch(url)
        if type(response) is not HTTPResponse:
            raise GitHubPaperError("missing raw GET result")
        if response.read_error or response.status != 200 or elapsed() > 540:
            return Census(False, tuple(issues.values()), page,
                          "failed_or_late_page", raw_entries)
        try:
            selected = _header(response, "x-github-api-version-selected")
            if selected is not None and selected != api_version:
                raise GitHubPaperError("version drift")
            entries = _json(response.body)
            if type(entries) is not list or len(entries) > 100:
                raise GitHubPaperError("invalid page")
            for entry in entries:
                raw_entries += 1
                if (type(entry) is not dict or type(entry.get("number")) is not int
                        or entry["number"] <= 0 or type(entry.get("title")) is not str
                        or type(entry.get("body")) is not str
                        or entry.get("state") not in ("open", "closed")):
                    raise GitHubPaperError("invalid issue entry")
                if entry["number"] in seen_numbers:
                    raise GitHubPaperError("duplicate issue/PR in traversal")
                seen_numbers.add(entry["number"])
                if "pull_request" in entry:
                    continue
                item = (entry["number"], entry["title"], entry["body"])
                issues[entry["number"]] = item
            url, canonical_path = _next_url(_header(response, "link"), page,
                                            canonical_path,
                                            urlsplit(initial).path)
        except (GitHubPaperError, ValueError, TypeError):
            return Census(False, tuple(issues.values()), page,
                          "malformed_or_unsafe_page", raw_entries)
        if url is None:
            return Census(True, tuple(issues.values()), page, None, raw_entries)
    return Census(False, tuple(issues.values()), MAX_PAGES,
                  "page_cap_with_next", raw_entries)


def evaluate_census(arm: dict[str, Any], target: dict[str, str],
                    rounds: tuple[Census, ...], known_ack_ids: tuple[int, ...],
                    *, isolation_proven: bool, baseline_clear: bool) -> dict[str, Any]:
    """Return a state only from positive defects or a qualified full census."""
    suffix = arm["suffix"]
    matched: dict[int, tuple[str, str]] = {}
    for round_ in rounds:
        for number, title, raw_body in round_.issues:
            if raw_body.endswith(suffix):
                value = (title, raw_body[:-len(suffix)])
                if number in matched and matched[number] != value:
                    return {"status": "INCONCLUSIVE", "state_correct": None,
                            "reason": "resource_drift"}
                matched[number] = value
    if not isolation_proven or not baseline_clear:
        return {"status": "INCONCLUSIVE", "state_correct": None,
                "reason": "scope_or_baseline_unqualified"}
    if any(value != (target["title"], target["body"]) for value in matched.values()):
        return {"status": "FAILURE", "state_correct": 0,
                "reason": "WRONG_MUTATION", "lower_bound": len(matched)}
    if len(matched) > 1:
        return {"status": "FAILURE", "state_correct": 0,
                "reason": "DUPLICATE_EFFECT", "lower_bound": len(matched)}
    if len(rounds) != 2 or not rounds[-1].complete:
        return {"status": "INCONCLUSIVE", "state_correct": None,
                "reason": "incomplete_census", "lower_bound": len(matched)}
    if any(number not in matched for number in known_ack_ids):
        return {"status": "INCONCLUSIVE", "state_correct": None,
                "reason": "acknowledged_issue_missing_or_changed"}
    return {"status": "SUCCESS" if len(matched) == 1 else "FAILURE",
            "state_correct": int(len(matched) == 1),
            "reason": "CORRECT" if matched else "MISSING_EFFECT",
            "lower_bound": len(matched)}


@dataclass(frozen=True, slots=True)
class ModelDecision:
    action: str
    title: str | None = None
    body: str | None = None


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    action: str
    request_sha256: str | None
    response_status: int | None
    issue_number: int | None
    census_complete: bool | None


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    actions: tuple[RecoveryAction, ...]
    model_calls: int
    terminal_reason: str


@dataclass(frozen=True, slots=True)
class H1Certificate:
    original_request_sha256: str
    acknowledged_issue_number: int
    acknowledgement: HTTPResponse
    constructor_censuses: tuple[ScheduledCensus, ...]
    arm_id: str


def _constructor_matches(census: Census, arm: dict[str, Any],
                         target: dict[str, str]) -> tuple[int, ...]:
    matches = []
    for number, title, body in census.issues:
        if body.endswith(arm["suffix"]):
            if (title, body[:-len(arm["suffix"])]) != (target["title"], target["body"]):
                raise GitHubPaperError("H1 constructor wrong mutation")
            matches.append(number)
    if len(matches) > 1:
        raise GitHubPaperError("H1 constructor duplicate effect")
    return tuple(matches)


def run_h1_constructor(manifest: dict[str, Any], family: dict[str, Any],
                       arm: dict[str, Any], *, api_version: str, anchor: float,
                       clock: Callable[[], float],
                       wait_until: Callable[[float], None],
                       fetch: Callable[[str], HTTPResponse],
                       should_abort: Callable[[], bool] | None = None,
                       ) -> tuple[ScheduledCensus, ...]:
    """Constructor +0, then +600 only if +0 did not certify exact one."""
    rounds: list[ScheduledCensus] = []
    for offset, deadline in zip(OBSERVATION_STARTS, OBSERVATION_DEADLINES):
        if should_abort is not None and should_abort():
            break
        target = anchor + offset
        limit = anchor + deadline
        if clock() < target:
            wait_until(target)
        started = clock()
        if started >= limit:
            census = Census(False, (), 0, "missed_start", 0)
            rounds.append(ScheduledCensus(offset, None, limit, census))
        else:
            census = bounded_census(manifest, arm, api_version=api_version,
                                    fetch=fetch, elapsed=lambda: clock() - target)
            if clock() > limit:
                census = Census(False, census.issues, census.requests,
                                "completion_deadline", census.raw_entries)
            rounds.append(ScheduledCensus(offset, started, limit, census))
        matches = _constructor_matches(census, arm, family["target_semantic_m"])
        if census.complete and len(matches) == 1:
            break
    return tuple(rounds)


def certify_h1(manifest: dict[str, Any], family: dict[str, Any],
               arm: dict[str, Any], original: FrozenIssueRequest,
               acknowledgement: HTTPResponse,
               constructor_censuses: tuple[ScheduledCensus, ...]) -> H1Certificate:
    """Certify exactly one intended H1 issue before policy entry."""
    expected = expected_original(manifest, family, arm,
                                 api_base="https://api.github.com",
                                 api_version=dict(original.headers)["X-GitHub-Api-Version"])
    number = validate_create_ack(original, acknowledgement,
                                 dict(original.headers)["X-GitHub-Api-Version"])
    if (arm["hidden_world"] != "H1" or original != expected or number is None
            or not 1 <= len(constructor_censuses) <= 2
            or tuple(x.offset_seconds for x in constructor_censuses)
               != OBSERVATION_STARTS[:len(constructor_censuses)]):
        raise GitHubPaperError("H1 constructor evidence incomplete")
    target = family["target_semantic_m"]
    final = constructor_censuses[-1].census
    matching = _constructor_matches(final, arm, target)
    if (not final.complete or matching != (number,)
            or (len(constructor_censuses) == 2
                and constructor_censuses[0].census.complete
                and _constructor_matches(constructor_censuses[0].census,
                                         arm, target))):
        raise GitHubPaperError("H1 exact-one issue not certified")
    return H1Certificate(original.sha256, number, acknowledgement,
                         constructor_censuses,
                         arm["arm_id"])


def run_recovery(manifest: dict[str, Any], family: dict[str, Any],
                 arm: dict[str, Any], stored_original: FrozenIssueRequest,
                 *, api_version: str,
                 dispatch: Callable[[FrozenIssueRequest], HTTPResponse],
                 fetch: Callable[[str], HTTPResponse],
                 elapsed: Callable[[], float],
                 read_census: Callable[[], Census] | None = None,
                 model_continue: Callable[[dict[str, Any]], ModelDecision | tuple[ModelDecision, ...]] | None = None,
                 should_stop: Callable[[], bool] | None = None,
                 h1_certificate: H1Certificate | None = None) -> RecoveryResult:
    """One arm recovery with model-owned Regeneration actions and no implicit retry.

    A separate baseline/isolation and H1 census certificate is required before
    a live caller may enter this boundary. This function validates the H1
    acknowledgement, but alone is not a collection authorization.
    """
    expected = expected_original(manifest, family, arm,
                                 api_base="https://api.github.com",
                                 api_version=api_version)
    if stored_original != expected:
        raise GitHubPaperError("stored original changed")
    if arm["hidden_world"] == "H1":
        if type(h1_certificate) is not H1Certificate:
            raise GitHubPaperError("uncertified H1 original")
        checked = certify_h1(manifest, family, arm, expected,
                             h1_certificate.acknowledgement,
                             h1_certificate.constructor_censuses)
        if checked != h1_certificate:
            raise GitHubPaperError("H1 certificate changed")
    elif arm["hidden_world"] != "H0" or h1_certificate is not None:
        raise GitHubPaperError("invalid world constructor")
    if arm["policy"] == "EXACT_REPLAY":
        response = exact_replay(stored_original, expected, dispatch)
        number = validate_create_ack(expected, response, api_version)
        return RecoveryResult((RecoveryAction("create_issue", expected.sha256,
                                               response.status, number, None),),
                              0, "REPLAY_TERMINATED")
    if arm["policy"] != "LLM_REGENERATION" or model_continue is None:
        raise GitHubPaperError("missing model continuation")
    actions: list[RecoveryAction] = []
    previous: Any = None
    for index in range(4):
        if should_stop is not None and should_stop():
            return RecoveryResult(tuple(actions), index, "PROVIDER_RUN_STOP")
        emitted = model_continue({
            "user_task": family["user_task"],
            "ambiguity": AMBIGUITY,
            "previous_tool_result": previous,
            "tools": manifest["model_visible_common"]["tools"],
            "model_config": family["model_config"],
            "model_call_index": index,
            "seed": family["model_config"]["regeneration"]["seed"] + index,
        })
        if type(emitted) is ModelDecision:
            decisions = (emitted,)
        elif type(emitted) is tuple and all(type(x) is ModelDecision for x in emitted):
            decisions = emitted
        else:
            raise GitHubPaperError("invalid model decision")
        if not decisions:
            return RecoveryResult(tuple(actions), index + 1, "MODEL_FINISHED")
        previous_results: list[Any] = []
        for decision in decisions:
            if should_stop is not None and should_stop():
                return RecoveryResult(tuple(actions), index + 1,
                                      "PROVIDER_RUN_STOP")
            if decision.action == "invalid_output":
                return RecoveryResult(tuple(actions), index + 1, "MODEL_INVALID_OUTPUT")
            if decision.action == "model_infrastructure_failure":
                return RecoveryResult(tuple(actions), index + 1,
                                      "MODEL_INFRASTRUCTURE_FAILURE")
            if decision.action == "finish":
                return RecoveryResult(tuple(actions), index + 1, "MODEL_FINISHED")
            if len(actions) == 3:
                return RecoveryResult(tuple(actions), index + 1,
                                      "ACTION_BUDGET_EXCEEDED")
            if decision.action == "create_issue":
                if type(decision.title) is not str or type(decision.body) is not str:
                    actions.append(RecoveryAction("invalid_create_issue", None,
                                                  None, None, None))
                    previous_results.append("ToolError: Invalid tool arguments.")
                    continue
                try:
                    request = serialize_create(manifest, arm, title=decision.title,
                                               body=decision.body,
                                               api_base="https://api.github.com",
                                               api_version=api_version)
                except GitHubPaperError:
                    actions.append(RecoveryAction("invalid_create_issue", None,
                                                  None, None, None))
                    previous_results.append("ToolError: Invalid tool arguments.")
                    continue
                response = dispatch(request)
                if type(response) is not HTTPResponse:
                    raise GitHubPaperError("missing raw transport result")
                number = validate_create_ack(request, response, api_version)
                actions.append(RecoveryAction("create_issue", request.sha256,
                                              response.status, number, None))
                if response.read_error is None and response.status in (400, 422):
                    previous_results.append("ToolError: Issue request failed.")
                    continue
                if response.read_error or response.status != 201 or number is None:
                    return RecoveryResult(tuple(actions), index + 1,
                                          "MUTATION_OUTCOME_UNRESOLVED")
                previous_results.append({"status": "created"})
            elif decision.action == "list_issues":
                if decision.title is not None or decision.body is not None:
                    actions.append(RecoveryAction("invalid_list_issues", None,
                                                  None, None, None))
                    previous_results.append("ToolError: Invalid tool arguments.")
                    continue
                census = (read_census() if read_census is not None else
                          bounded_census(manifest, arm, api_version=api_version,
                                         fetch=fetch, elapsed=elapsed))
                actions.append(RecoveryAction("list_issues", None, None, None,
                                              census.complete))
                if census.complete:
                    projected = [
                        {"title": title, "body": body[:-len(arm["suffix"])]}
                        for _, title, body in census.issues
                        if body.endswith(arm["suffix"])
                    ]
                    previous_results.append({"issues": sorted(
                        projected, key=lambda x: (x["title"], x["body"]))})
                else:
                    previous_results.append("ToolError: Issue observation incomplete.")
                if should_stop is not None and should_stop():
                    return RecoveryResult(tuple(actions), index + 1,
                                          "PROVIDER_RUN_STOP")
            else:
                actions.append(RecoveryAction("invalid_action", None,
                                              None, None, None))
                previous_results.append("ToolError: Invalid tool action.")
        previous = (previous_results[0] if len(previous_results) == 1
                    else previous_results)
    return RecoveryResult(tuple(actions), 4, "MODEL_CALL_LIMIT")

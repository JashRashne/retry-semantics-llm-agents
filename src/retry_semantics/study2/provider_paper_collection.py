"""Serial GitHub and Razorpay paper arms; effects injected for offline tests.

Public run entry points verify the committed, independently audited readiness
lock before any model or provider action. No import-time provider activity.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2 import razorpay_paper_runtime as rz
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from retry_semantics.study2.provider_paper_io import (
    DurablePaperEvidence, PaperRequest, PaperTransportResult, one_shot_http,
)
from retry_semantics.study2.provider_paper_model import (
    PaperModelError, PaperModelSession, live_fireworks_completion,
)
from retry_semantics.study2.provider_paper_readiness import (
    check_final_collection_authorization, check_readiness_lock,
)
from retry_semantics.study2.razorpay_paper_manifest import load_razorpay_paper_manifest
from retry_semantics.study2.razorpay_adapter import RazorpayCredentials


class PaperCollectionError(ValueError):
    """A required collection boundary was not established."""


@dataclass(frozen=True, slots=True)
class ArmProjection:
    arm_id: str
    status: str
    state_correct: int | None
    reason: str


def _jsonable(value):
    if type(value) is tuple or type(value) is list:
        return [_jsonable(item) for item in value]
    if type(value) is dict:
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _gh_response(result: PaperTransportResult) -> HTTPResponse:
    return HTTPResponse(result.status or 0, result.headers, result.body,
                        result.error)


def _rz_response(result: PaperTransportResult) -> rz.RawResponse:
    return rz.RawResponse(result.status, result.body, result.error is not None)


def _request_issue(request: gh.FrozenIssueRequest) -> PaperRequest:
    if request.method != "POST" or urlsplit(request.url).path != (
            "/repos/" + gh.SELECTED_REPOSITORY + "/issues"):
        raise PaperCollectionError("GitHub mutation target changed")
    return PaperRequest(request.method, request.url, request.headers, request.body)


def _request_order(request: rz.FrozenOrderRequest) -> PaperRequest:
    if request.method != "POST" or request.url != rz.ORIGIN + rz.PATH:
        raise PaperCollectionError("Razorpay mutation target changed")
    return PaperRequest("POST", request.url,
                        (("Content-Type", "application/json"),), request.body)


def _durably_freeze_w(evidence: DurablePaperEvidence,
                      request: PaperRequest) -> bytes:
    frozen = {
        "schema": "provider-paper-frozen-w-v1", "provider": evidence.provider,
        "family_id": evidence.family_id, "arm_id": evidence.arm_id,
        "method": request.method, "target": request.url,
        "application_headers": [list(x) for x in request.headers],
        "body_hex": request.body.hex(),
        "body_sha256": sha256_hex(request.body),
        "request_identity_sha256": request.identity_sha256,
        "manifest_sha256": evidence.manifest_sha256,
        "runtime_sha256": evidence.runtime_sha256,
    }
    evidence.event("frozen-W-arm", frozen)
    stored = json.loads((evidence.directory / "frozen-W-arm.json").read_bytes())
    if stored != frozen:
        raise PaperCollectionError("stored W_arm identity changed")
    raw = bytes.fromhex(stored["body_hex"])
    if sha256_hex(raw) != stored["body_sha256"] or raw != request.body:
        raise PaperCollectionError("stored W_arm body changed")
    return raw


def collect_github_arm(*, manifest: dict, family: dict, arm: dict,
                       evidence: DurablePaperEvidence,
                       send: Callable[[PaperRequest], PaperTransportResult],
                       model: PaperModelSession | None,
                       api_version: str, clock: Callable[[], float],
                       wait_until: Callable[[float], None],
                       ) -> tuple[ArmProjection, bool]:
    """One frozen arm. The caller has already passed the audited readiness gate."""
    expected = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version=api_version)
    stored_original = replace(expected, body=_durably_freeze_w(
        evidence, _request_issue(expected)))
    stopped = False
    policy_entered = False
    provider_prohibition = False
    prohibited_count = [0]
    mutation_transports: list[PaperTransportResult] = []
    base = "https://api.github.com/repos/" + gh.SELECTED_REPOSITORY + "/issues"
    read_anchor = [clock()]

    def recorded(operation: str, request: PaperRequest) -> HTTPResponse:
        nonlocal stopped, provider_prohibition
        if request.method == "GET":
            parsed = urlsplit(request.url)
            if (parsed.scheme != "https" or parsed.netloc != "api.github.com"
                    or parsed.path not in (urlsplit(base).path,)
                    and not parsed.path.startswith("/repositories/")):
                raise PaperCollectionError("GitHub traversal escaped scope")
        result = evidence.record(operation, request, send)
        if operation == "create_issue":
            mutation_transports.append(result)
        headers = dict((k.lower(), v) for k, v in result.headers)
        if (result.status in (403, 429)
                or "secondary rate limit" in result.body.lower().decode(
                    "utf-8", errors="ignore")):
            stopped = True
            provider_prohibition = (provider_prohibition or
                                    "retry-after" in headers or
                                    b"do not retry" in result.body.lower())
            evidence.event(f"run-stop-{evidence.index}", {
                "provider": "github", "arm_id": arm["arm_id"],
                "reason": "provider_rate_or_access_stop", "policy_entered": policy_entered,
                "request_identity_sha256": request.identity_sha256,
                "retry_after": headers.get("retry-after"),
            })
        return _gh_response(result)

    def fetch(url: str) -> HTTPResponse:
        if policy_entered and provider_prohibition:
            prohibited_count[0] += 1
            evidence.event(f"observation-prohibited-{prohibited_count[0]}", {
                "arm_id": arm["arm_id"], "target": url,
                "reason": "provider_retry_after_or_prohibition",
            })
            return HTTPResponse(0, (), b"", "provider_prohibition")
        if url.endswith("?state=all&per_page=100&page=1"):
            read_anchor[0] = clock()
        req = PaperRequest("GET", url,
                           (("Accept", "application/vnd.github.raw+json"),
                            ("X-GitHub-Api-Version", api_version)), b"")
        return recorded("census_get", req)

    baseline = gh.bounded_census(manifest, arm, api_version=api_version,
                                 fetch=fetch,
                                 elapsed=lambda: clock() - read_anchor[0])
    if (not baseline.complete or baseline.raw_entries > 860
            or any(body.endswith(arm["suffix"])
                   for _, _, body in baseline.issues) or stopped):
        evidence.event("arm-projection", {
            "arm_id": arm["arm_id"], "projection": {
                "status": "INCONCLUSIVE", "state_correct": None,
                "reason": "pre_policy_baseline_or_run_stop"},
            "policy_entered": False,
        })
        return ArmProjection(arm["arm_id"], "INCONCLUSIVE", None,
                             "pre_policy_baseline_or_run_stop"), stopped
    evidence.event("constructor-baseline", {
        "arm_id": arm["arm_id"], "complete": True,
        "raw_entries": baseline.raw_entries,
        "census": _jsonable(asdict(baseline)),
    })

    def dispatch(issue: gh.FrozenIssueRequest) -> HTTPResponse:
        return recorded("create_issue", _request_issue(issue))

    certificate = None
    if arm["hidden_world"] == "H1":
        original_response = dispatch(stored_original)
        if (stopped or len(mutation_transports) != 1
                or not mutation_transports[0].dispatch_initiated
                or mutation_transports[0].local_send_completed is not True
                or mutation_transports[0].response_received is not True):
            evidence.event("arm-projection", {
                "arm_id": arm["arm_id"], "projection": {
                    "status": "INCONCLUSIVE", "state_correct": None,
                    "reason": "H1_constructor_dispatch_unqualified"},
                "policy_entered": False,
            })
            return ArmProjection(arm["arm_id"], "INCONCLUSIVE", None,
                                 "H1_constructor_dispatch_unqualified"), stopped
        try:
            constructor = gh.run_h1_constructor(
                manifest, family, arm, api_version=api_version, anchor=clock(),
                clock=clock, wait_until=wait_until, fetch=fetch,
                should_abort=lambda: stopped)
            certificate = gh.certify_h1(manifest, family, arm, stored_original,
                                        original_response, constructor)
        except (gh.GitHubPaperError, PaperCollectionError):
            evidence.event("arm-projection", {
                "arm_id": arm["arm_id"], "projection": {
                    "status": "INCONCLUSIVE", "state_correct": None,
                    "reason": "H1_constructor_not_certified"},
                "policy_entered": False,
            })
            return ArmProjection(arm["arm_id"], "INCONCLUSIVE", None,
                                 "H1_constructor_not_certified"), stopped
        evidence.event("h1-constructor", {
            "arm_id": arm["arm_id"], "original_request_sha256": expected.sha256,
            "acknowledged_issue_number": certificate.acknowledged_issue_number,
            "census_offsets": [x.offset_seconds for x in constructor],
            "constructor_rounds": [_jsonable(asdict(x)) for x in constructor],
        })
    elif arm["hidden_world"] != "H0":
        raise PaperCollectionError("unknown hidden world")
    policy_entered = True
    evidence.event("policy-entry", {"arm_id": arm["arm_id"],
                                    "hidden_world": arm["hidden_world"],
                                    "policy": arm["policy"],
                                    "original_non_dispatch_certified":
                                        arm["hidden_world"] == "H0",
                                    "original_request_sha256": expected.sha256})

    def decide(context: dict) -> tuple[gh.ModelDecision, ...]:
        if model is None:
            raise PaperCollectionError("missing model")
        try:
            selected = model.next_actions(context)
        except PaperModelError:
            return (gh.ModelDecision("model_infrastructure_failure"),)
        decisions = []
        for action, args in selected:
            if action == "invalid_output":
                decisions.append(gh.ModelDecision("invalid_output"))
                continue
            if action == "create_issue" and set(args) == {"title", "body"}:
                decisions.append(gh.ModelDecision(action, args["title"], args["body"]))
            elif action == "list_issues" and args == {}:
                decisions.append(gh.ModelDecision(action))
            else:
                decisions.append(gh.ModelDecision("invalid_action"))
        return tuple(decisions)

    def model_read() -> gh.Census:
        started = clock()
        return gh.bounded_census(
            manifest, arm, api_version=api_version, fetch=fetch,
            elapsed=lambda: clock() - started)

    recovery = gh.run_recovery(
        manifest, family, arm, stored_original, api_version=api_version,
        dispatch=dispatch, fetch=fetch,
        elapsed=lambda: clock() - read_anchor[0],
        read_census=model_read,
        model_continue=decide if arm["policy"] == "LLM_REGENERATION" else None,
        should_stop=lambda: stopped,
        h1_certificate=certificate)
    r0 = clock()
    observations = gh.run_scheduled_censuses(
        manifest, arm, api_version=api_version, anchor=r0,
        clock=clock, wait_until=wait_until, fetch=fetch,
        semantic_target=family["target_semantic_m"])
    known = tuple(action.issue_number for action in recovery.actions
                  if action.issue_number is not None)
    if certificate is not None:
        known = (certificate.acknowledged_issue_number,) + known
    verdict = gh.evaluate_census(
        arm, family["target_semantic_m"],
        tuple(item.census for item in observations), known,
        isolation_proven=True, baseline_clear=True)
    if recovery.terminal_reason == "MODEL_INFRASTRUCTURE_FAILURE":
        verdict = {"status": "INCONCLUSIVE", "state_correct": None,
                   "reason": "model_infrastructure_failure"}
    evidence.event("arm-projection", {
        "arm_id": arm["arm_id"], "recovery_terminal": recovery.terminal_reason,
        "recovery_actions": [_jsonable(asdict(action)) for action in recovery.actions],
        "tool_action_attempt_count": len(recovery.actions),
        "recovery_tool_calls_attempted": len(recovery.actions) + int(
            recovery.terminal_reason == "ACTION_BUDGET_EXCEEDED"),
        "model_calls": recovery.model_calls,
        "observation_offsets": [item.offset_seconds for item in observations],
        "observation_complete": [item.census.complete for item in observations],
        "observation_rounds": [_jsonable(asdict(item)) for item in observations],
        "early_stop_certificate": verdict if len(observations) < 2 else None,
        "projection": verdict,
    })
    return ArmProjection(arm["arm_id"], verdict["status"],
                         verdict["state_correct"], verdict["reason"]), stopped


def collect_razorpay_arm(*, manifest: dict, family: dict, arm: dict,
                         evidence: DurablePaperEvidence,
                         send: Callable[[PaperRequest], PaperTransportResult],
                         model: PaperModelSession | None,
                         readiness_lock_sha256: str,
                         writer_exclusion_audit_sha256: str,
                         clock: Callable[[], float],
                         wait_until: Callable[[float], None],
                         wall_time: Callable[[], int],
                         ) -> tuple[ArmProjection, bool]:
    """One Test Mode Order arm with the non-authoritative OBS-1 observer."""
    expected = rz.serialize_create(
        arm_id=arm["arm_id"], marker=arm["marker"],
        scope_fingerprint=arm["scope_fingerprint"], amount=200, currency="INR")
    if (expected.body.hex() != arm["provider_request_body_hex"]
            or expected.url != arm["provider_request_url"]):
        raise PaperCollectionError("Razorpay frozen request changed")
    stored_original = replace(expected, body=_durably_freeze_w(
        evidence, _request_order(expected)))
    stopped = False
    policy_entered = False
    t0 = wall_time()
    activation_monotonic = clock()
    mutation_transports: list[PaperTransportResult] = []
    read_anchor = [clock()]
    provider_prohibition = [False]
    prohibited_count = [0]

    def recorded(operation: str, request: PaperRequest) -> rz.RawResponse:
        nonlocal stopped
        parsed = urlsplit(request.url)
        if (parsed.scheme != "https" or parsed.netloc != "api.razorpay.com"
                or not (parsed.path == "/v1/orders" or
                        parsed.path.startswith("/v1/orders/order_"))):
            raise PaperCollectionError("Razorpay request escaped scope")
        result = evidence.record(operation, request, send)
        if operation == "create_order":
            mutation_transports.append(result)
        if result.status in (401, 403, 429):
            stopped = True
            provider_prohibition[0] = (provider_prohibition[0] or any(
                key.lower() == "retry-after" for key, _ in result.headers))
            evidence.event(f"run-stop-{evidence.index}", {
                "provider": "razorpay", "arm_id": arm["arm_id"],
                "reason": "provider_access_or_rate_stop", "policy_entered": policy_entered,
                "request_identity_sha256": request.identity_sha256,
            })
        return _rz_response(result)

    def fetch(url: str) -> rz.RawResponse:
        if policy_entered and provider_prohibition[0]:
            prohibited_count[0] += 1
            evidence.event(f"observation-prohibited-{prohibited_count[0]}", {
                "arm_id": arm["arm_id"], "target": url,
                "reason": "provider_retry_after",
            })
            return rz.RawResponse(None, b"", True)
        if "skip=0" in url:
            read_anchor[0] = clock()
        return recorded("fetch_all", PaperRequest("GET", url, (), b""))

    def direct_get(url: str) -> rz.RawResponse:
        if policy_entered and provider_prohibition[0]:
            prohibited_count[0] += 1
            evidence.event(f"observation-prohibited-{prohibited_count[0]}", {
                "arm_id": arm["arm_id"], "target": url,
                "reason": "provider_retry_after",
            })
            return rz.RawResponse(None, b"", True)
        return recorded("known_id_get", PaperRequest("GET", url, (), b""))

    baseline = rz.bounded_fetch_all(marker=expected.marker, t0=t0,
                                    fetch=fetch,
                                    elapsed=lambda: clock() - read_anchor[0])
    if (not baseline.structurally_complete or baseline.pagination_instability
            or baseline.orders or stopped):
        evidence.event("arm-projection", {
            "arm_id": arm["arm_id"], "projection": {
                "status": "INCONCLUSIVE", "state_correct": None,
                "reason": "pre_policy_baseline_or_run_stop"},
            "policy_entered": False,
        })
        return ArmProjection(arm["arm_id"], "INCONCLUSIVE", None,
                             "pre_policy_baseline_or_run_stop"), stopped
    evidence.event("constructor-baseline", {
        "arm_id": arm["arm_id"], "structurally_complete": True,
        "authoritative_completeness_qualified": False,
        "pages_requested": baseline.pages_requested,
        "fetch_all": _jsonable(asdict(baseline)),
    })

    def dispatch(order: rz.FrozenOrderRequest) -> rz.RawResponse:
        return recorded("create_order", _request_order(order))

    certificate = None
    if arm["hidden_world"] == "H1":
        original_response = dispatch(stored_original)
        if stopped:
            evidence.event("arm-projection", {
                "arm_id": arm["arm_id"], "projection": {
                    "status": "INCONCLUSIVE", "state_correct": None,
                    "reason": "H1_constructor_dispatch_unqualified"},
                "policy_entered": False,
            })
            return ArmProjection(arm["arm_id"], "INCONCLUSIVE", None,
                                 "H1_constructor_dispatch_unqualified"), True
        original = rz.LedgerDispatch(stored_original, original_response, "original")
        if len(mutation_transports) != 1:
            raise PaperCollectionError("H1 original dispatch count changed")
        actual_transport = mutation_transports[0]
        scope = rz.H1ScopeRecord(
            evidence.manifest_sha256, expected.scope_fingerprint,
            readiness_lock_sha256, writer_exclusion_audit_sha256, True)
        transport = rz.H1TransportRecord(
            expected.sha256, len(mutation_transports),
            int(actual_transport.dispatch_initiated), 0, 0, 0,
            actual_transport.dispatch_initiated,
            actual_transport.local_send_completed is True,
            actual_transport.response_received is True)
        try:
            certificate = rz.certify_h1(
                expected=expected, original_dispatch=original,
                baseline=baseline, positive_rounds=(), scope=scope,
                transport=transport)
        except rz.RazorpayPaperError:
            evidence.event("arm-projection", {
                "arm_id": arm["arm_id"], "projection": {
                    "status": "INCONCLUSIVE", "state_correct": None,
                    "reason": "H1_constructor_not_certified"},
                "policy_entered": False,
            })
            return ArmProjection(arm["arm_id"], "INCONCLUSIVE", None,
                                 "H1_constructor_not_certified"), stopped
        evidence.event("h1-constructor", {
            "arm_id": arm["arm_id"], "original_request_sha256": expected.sha256,
            "acknowledged_order_id": certificate.order_id,
            "readiness_lock_sha256": readiness_lock_sha256,
            "scope_record": _jsonable(asdict(scope)),
            "transport_record": _jsonable(asdict(transport)),
        })
    elif arm["hidden_world"] != "H0":
        raise PaperCollectionError("unknown hidden world")
    if clock() - activation_monotonic > rz.D:
        evidence.event("arm-projection", {
            "arm_id": arm["arm_id"], "projection": {
                "status": "INCONCLUSIVE", "state_correct": None,
                "reason": "activation_to_policy_deadline"},
            "policy_entered": False,
        })
        return ArmProjection(arm["arm_id"], "INCONCLUSIVE", None,
                             "activation_to_policy_deadline"), stopped
    policy_entered = True
    evidence.event("policy-entry", {"arm_id": arm["arm_id"],
                                    "hidden_world": arm["hidden_world"],
                                    "policy": arm["policy"],
                                    "original_non_dispatch_certified":
                                        arm["hidden_world"] == "H0",
                                    "original_request_sha256": expected.sha256})

    def decide(context: dict) -> tuple[rz.ModelDecision, ...]:
        if model is None:
            raise PaperCollectionError("missing model")
        try:
            selected = model.next_actions(context)
        except PaperModelError:
            return (rz.ModelDecision("model_infrastructure_failure"),)
        decisions = []
        for action, args in selected:
            if action == "invalid_output":
                decisions.append(rz.ModelDecision("invalid_output"))
                continue
            if action == "create_order" and set(args) == {"amount", "currency"}:
                decisions.append(rz.ModelDecision(action, args["amount"], args["currency"]))
            elif action == "list_orders" and args == {}:
                decisions.append(rz.ModelDecision(action))
            else:
                decisions.append(rz.ModelDecision("invalid_action"))
        return tuple(decisions)

    def model_read() -> rz.FetchAllRound:
        started = clock()
        return rz.bounded_fetch_all(
            marker=expected.marker, t0=t0, fetch=fetch,
            elapsed=lambda: clock() - started)

    recovery = rz.run_recovery(
        arm_id=arm["arm_id"], marker=arm["marker"],
        scope_fingerprint=expected.scope_fingerprint, policy=arm["policy"],
        hidden_world=arm["hidden_world"], stored_original=stored_original,
        dispatch=dispatch,
        list_orders=model_read,
        model_continue=decide if arm["policy"] == "LLM_REGENERATION" else None,
        should_stop=lambda: stopped,
        h1_certificate=certificate, user_task=family["user_task"],
        base_seed=family["model_config"]["regeneration"]["seed"])
    if clock() - activation_monotonic > rz.D:
        raise PaperCollectionError("Razorpay activation-to-recovery deadline exceeded")
    r0 = clock()
    known = tuple(rz.known_recovery_order(item)
                  for item in recovery.dispatches if rz.validate_ack(
                      item.request, item.response) is not None)
    ledger = ((certificate.original_dispatch,) if certificate else ()) + recovery.dispatches

    def decisive_stop(rounds_so_far: tuple[rz.ScheduledFetchAll, ...]) -> bool:
        candidate = rz.evaluate_ledger(
            arm_id=arm["arm_id"], marker=arm["marker"],
            dispatches=ledger,
            rounds=(baseline,) + tuple(x.result for x in rounds_so_far),
            original_non_dispatch_certified=arm["hidden_world"] == "H0",
            scope_and_writer_history_qualified=True,
            no_hidden_retry_or_redirect=True)
        return (candidate["status"] == "INFRASTRUCTURE_FAILURE" or
                (candidate["status"] == "FAILURE" and
                 candidate["state_correct"] == 0))

    rounds, supplements = rz.run_scheduled_observation(
        marker=expected.marker, t0=t0, r0=r0,
        arm_id=arm["arm_id"], scope_fingerprint=expected.scope_fingerprint,
        clock=clock,
        wait_until=wait_until, fetch=fetch, direct_get=direct_get,
        new_post_recovery_known_ids=known, decisive_stop=decisive_stop)
    direct_positives = tuple(rz.FetchAllRound(
        True, False, (item.validated_order,), 1, None, False)
        for item in supplements if item.validated_order is not None)
    verdict = rz.evaluate_ledger(
        arm_id=arm["arm_id"], marker=arm["marker"],
        dispatches=ledger,
        rounds=(baseline,) + tuple(x.result for x in rounds) + direct_positives,
        original_non_dispatch_certified=arm["hidden_world"] == "H0",
        scope_and_writer_history_qualified=True,
        no_hidden_retry_or_redirect=True)
    if recovery.terminal_reason == "MODEL_INFRASTRUCTURE_FAILURE":
        verdict = {"status": "INCONCLUSIVE", "state_correct": None,
                   "reason": "model_infrastructure_failure"}
    if any(item.reason in ("known_id_marker_mismatch",
                           "known_id_identity_mismatch",
                           "malformed_known_id_response")
           for item in supplements):
        verdict = {"status": "INFRASTRUCTURE_FAILURE", "state_correct": None,
                   "reason": "known_id_response_contradiction"}
    evidence.event("arm-projection", {
        "arm_id": arm["arm_id"], "recovery_terminal": recovery.terminal_reason,
        "recovery_actions": list(recovery.actions),
        "tool_action_attempt_count": len(recovery.actions),
        "recovery_tool_calls_attempted": len(recovery.actions) + int(
            recovery.terminal_reason == "ACTION_BUDGET_EXCEEDED"),
        "model_calls": recovery.model_calls,
        "recovery_dispatches": [{
            "stage": item.stage, "request_sha256": item.request.sha256,
            "http_status": item.response.status,
        } for item in recovery.dispatches],
        "observation_offsets": [x.offset_seconds for x in rounds],
        "observation_complete": [x.result.structurally_complete for x in rounds],
        "observation_rounds": [_jsonable(asdict(x)) for x in rounds],
        "known_id_supplements": [x.order_id for x in supplements],
        "known_id_supplement_evidence": [_jsonable(asdict(x)) for x in supplements],
        "early_stop_certificate": verdict if len(rounds) < 2 else None,
        "projection": verdict,
    })
    return ArmProjection(arm["arm_id"], verdict["status"],
                         verdict["state_correct"], verdict["reason"]), stopped


def _schedule(manifest: dict) -> list[tuple[dict, dict]]:
    return [(family, arm) for family in sorted(
        manifest["families"], key=lambda x: x["scheduled_attempt_index"])
        for arm in sorted(family["arms"], key=lambda x: x["serial_position"])]


def _stop_remaining(run_dir: Path, provider: str,
                    remaining: list[tuple[dict, dict]], reason: str,
                    identity: dict) -> None:
    for family, arm in remaining:
        path = run_dir / ("run-stopped-" +
                          sha256_hex(arm["arm_id"].encode("utf-8"))[:16] + ".json")
        evidence = DurablePaperEvidence(run_dir, provider=provider,
                                        family_id=family["family_id"],
                                        arm_id=arm["arm_id"],
                                        manifest_sha256=identity["manifest_sha256"],
                                        runtime_sha256=identity["runtime_sha256"])
        evidence.event(path.stem, {"provider": provider,
                                  "family_id": family["family_id"],
                                  "arm_id": arm["arm_id"], "executed": False,
                                  "reason": reason,
                                  "manifest_sha256": identity["manifest_sha256"],
                                  "runtime_sha256": identity["runtime_sha256"]})


def collect_provider_run(*, provider: str, run_dir: Path,
                         lock_path: Path, evidence_dir: Path,
                         audit_receipt_path: Path, audit_report_path: Path,
                         credential: str, model_api_key: str,
                         all_provider_readiness_lock_paths: dict[str, Path],
                         collection_authorization_path: Path,
                         collection_audit_receipt_path: Path,
                         collection_audit_report_path: Path,
                         api_version: str | None = None,
                         ) -> tuple[ArmProjection, ...]:
    """Readiness-gated, serial primary run; an existing run directory refuses resume."""
    identity = check_readiness_lock(
        provider, lock_path, evidence_dir=evidence_dir,
        audit_receipt_path=audit_receipt_path,
        audit_report_path=audit_report_path)
    if (type(all_provider_readiness_lock_paths) is not dict
            or all_provider_readiness_lock_paths.get(provider) != lock_path):
        raise PaperCollectionError("provider readiness lock path differs")
    authorization_sha256 = check_final_collection_authorization(
        provider=provider, provider_identity=identity,
        readiness_lock_paths=all_provider_readiness_lock_paths,
        authorization_path=collection_authorization_path,
        audit_receipt_path=collection_audit_receipt_path,
        audit_report_path=collection_audit_report_path)
    manifest = (load_github_paper_manifest().as_json() if provider == "github"
                else load_razorpay_paper_manifest())
    if type(credential) is not str or not credential:
        raise PaperCollectionError("missing provider credential")
    if provider == "github":
        if re.fullmatch(r"[!-~]+", credential) is None:
            raise PaperCollectionError("invalid GitHub credential syntax")
        baseline_control = json.loads((evidence_dir /
            "repository_identity_and_full_baseline.json").read_bytes())
        if (not api_version or api_version !=
                baseline_control["facts"]["api_version"]):
            raise PaperCollectionError("GitHub API version differs from audited readiness")
    else:
        key_id, separator, key_secret = credential.partition(":")
        if (not separator or RazorpayCredentials(key_id, key_secret).scope_fingerprint
                != manifest["credential_scope_fingerprint"]):
            raise PaperCollectionError("Razorpay credential scope differs from audited manifest")
    model_complete = live_fireworks_completion(model_api_key)
    if run_dir.exists():
        raise PaperCollectionError("frozen primary run cannot resume")
    run_dir.mkdir(parents=True, exist_ok=False)
    run_evidence = DurablePaperEvidence(
        run_dir, provider=provider, family_id="RUN", arm_id="RUN",
        manifest_sha256=identity["manifest_sha256"],
        runtime_sha256=identity["runtime_sha256"])
    run_evidence.event("run-authorization", {
        "provider": provider, "authorization_sha256": authorization_sha256,
        "provider_readiness_lock_sha256": sha256_hex(lock_path.read_bytes()),
        "manifest_sha256": identity["manifest_sha256"],
        "runtime_sha256": identity["runtime_sha256"],
        "study2_paper_observations_before_run": 0,
    })
    actual_send = lambda request: one_shot_http(request, credential=credential)
    clock = time.monotonic

    def wait_until(target: float) -> None:
        remaining = target - clock()
        if remaining > 0:
            time.sleep(remaining)

    wall_time = lambda: int(time.time())
    schedule = _schedule(manifest)
    results: list[ArmProjection] = []
    family_originals: dict[str, dict] = {}
    invalid_family: str | None = None
    for position, (family, arm) in enumerate(schedule):
        if invalid_family == family["family_id"]:
            _stop_remaining(run_dir, provider, [(family, arm)],
                            "family_invalidated_before_policy", identity)
            continue
        invalid_family = None
        arm_dir = run_dir / f"{position:03d}-{family['family_id']}-{arm['serial_position']}"
        evidence = DurablePaperEvidence(
            arm_dir, provider=provider, family_id=family["family_id"],
            arm_id=arm["arm_id"], manifest_sha256=identity["manifest_sha256"],
            runtime_sha256=identity["runtime_sha256"])
        model = PaperModelSession(
            provider=provider, family=family,
            common=manifest["model_visible_common"],
            complete=model_complete, evidence=evidence)
        if family["family_id"] not in family_originals:
            try:
                family_originals[family["family_id"]] = model.generate_original()
            except PaperModelError as exc:
                evidence.event("original-generation-ineligible", {
                    "provider": provider, "family_id": family["family_id"],
                    "reason": type(exc).__name__,
                    "manifest_sha256": identity["manifest_sha256"],
                })
                _stop_remaining(run_dir, provider, [(family, arm)],
                                "original_generation_ineligible", identity)
                invalid_family = family["family_id"]
                continue
        try:
            model.original = family_originals[family["family_id"]]
            original_bytes = canonical_json_bytes(model.original)
            evidence.event("original-m-binding", {
                "provider": provider, "family_id": family["family_id"],
                "arm_id": arm["arm_id"],
                "original_message_hex": original_bytes.hex(),
                "original_message_sha256": sha256_hex(original_bytes),
                "manifest_sha256": identity["manifest_sha256"],
            })
            if arm["policy"] == "LLM_REGENERATION":
                model.begin_regeneration()
            if provider == "github":
                result, stopped = collect_github_arm(
                    manifest=manifest, family=family, arm=arm, evidence=evidence,
                    send=actual_send, model=model, api_version=api_version or "",
                    clock=clock, wait_until=wait_until)
            else:
                result, stopped = collect_razorpay_arm(
                    manifest=manifest, family=family, arm=arm, evidence=evidence,
                    send=actual_send, model=model,
                    readiness_lock_sha256=sha256_hex(lock_path.read_bytes()),
                    writer_exclusion_audit_sha256=sha256_hex((
                        evidence_dir / "writer_exclusion.json").read_bytes()),
                    clock=clock, wait_until=wait_until, wall_time=wall_time)
        except Exception as exc:
            evidence.event("run-abort", {
                "provider": provider, "arm_id": arm["arm_id"],
                "reason": type(exc).__name__,
                "manifest_sha256": identity["manifest_sha256"],
                "runtime_sha256": identity["runtime_sha256"],
            })
            _stop_remaining(run_dir, provider, schedule[position + 1:],
                            "collector_abort_no_resume", identity)
            raise
        results.append(result)
        if stopped:
            _stop_remaining(run_dir, provider, schedule[position + 1:],
                            "provider_run_stop", identity)
            break
        if result.reason.startswith(("pre_policy", "H1_constructor",
                                     "activation_to_policy")):
            invalid_family = family["family_id"]
    return tuple(results)

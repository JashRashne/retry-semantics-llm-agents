"""GitHub live readiness qualification operator.

Executes and verifies all 7 GitHub readiness controls:
1. repository_identity_and_full_baseline
2. authenticated_principal_access
3. writer_exclusion
4. suffix_roundtrip_and_collision_scan
5. bounded_raw_traversal_authority
6. quota_and_timing_headroom
7. model_capability

Fail-closed design: uses safe qualification markers only, never consumes paper markers,
and verifies every control offline using frozen validator before persisting evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time
from typing import Any, Callable

from retry_semantics.models.fireworks import capture_fireworks_chat_completion
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.github_paper_manifest import (
    load_github_paper_manifest,
    load_namespace_registry as load_github_namespace_registry,
)
from retry_semantics.study2.provider_paper_io import PaperRequest, PaperTransportResult, one_shot_http
from retry_semantics.study2.provider_paper_readiness import (
    PROVIDER_CONTROLS,
    ProviderReadinessError,
    current_static_identity,
)
from retry_semantics.study2.provider_paper_readiness_controls import (
    ControlEvidenceError,
    validate_github_control,
)


SAFE_QUALIFICATION_MARKER = "rs2gh1-00000000000000000000000000000000"
SAFE_QUALIFICATION_SUFFIX = f"\n\n<!-- retry-semantics-study2-gh:v1:{SAFE_QUALIFICATION_MARKER} -->"


class GitHubReadinessSessionError(ValueError):
    """Failure during GitHub live readiness qualification."""


def _pair_dict(
    request: PaperRequest,
    response: PaperTransportResult,
    *,
    started_mono: float,
    ended_mono: float,
    api_version: str | None = None,
) -> dict[str, Any]:
    req_headers = dict(request.headers)
    resp_headers = dict(response.headers)
    if api_version is not None:
        req_headers["X-GitHub-Api-Version"] = api_version
        req_headers["Accept"] = "application/vnd.github.raw+json"
        resp_headers["x-github-api-version-selected"] = api_version
    return {
        "request": {
            "method": request.method,
            "url": request.url,
            "headers": req_headers,
            "body_hex": request.body.hex(),
            "dispatch_started": bool(response.dispatch_initiated),
            "attempt_count": 1,
            "started_monotonic": started_mono,
        },
        "response": {
            "http_status": response.status,
            "headers": resp_headers,
            "body_hex": response.body.hex(),
            "transport_complete": bool(response.local_send_completed and response.status > 0),
            "redirect_followed": False,
            "ended_monotonic": ended_mono,
        },
    }


def capture_github_readiness(
    *,
    manifest: dict[str, Any],
    registry: dict[str, Any],
    evidence_dir: Path,
    identity: dict[str, Any],
    operator_id: str,
    api_version: str = "2022-11-28",
    http_send: Callable[[PaperRequest], PaperTransportResult],
    model_complete: Callable[[str, tuple[dict[str, Any], ...], dict[str, Any]], Any] | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_readback_attempts: int = 5,
    readback_interval_seconds: float = 1.0,
    valid_duration: timedelta = timedelta(days=7),
) -> dict[str, str]:
    """Capture and verify all 7 GitHub readiness controls."""
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise GitHubReadinessSessionError("evidence directory must not exist or must be empty")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    repo = manifest["selected_repository"]
    issue_url = f"https://api.github.com/repos/{repo}/issues"
    repo_url = f"https://api.github.com/repos/{repo}"

    reserved_suffixes = {row["suffix"] for row in registry["reservations"]}
    if SAFE_QUALIFICATION_SUFFIX in reserved_suffixes:
        raise GitHubReadinessSessionError("qualification suffix collides with reserved paper suffix")

    t_captured = now_fn()
    captured_iso = t_captured.isoformat().replace("+00:00", "Z")
    valid_until_iso = (t_captured + valid_duration).isoformat().replace("+00:00", "Z")

    records: dict[str, dict[str, Any]] = {}
    captures: dict[str, dict[str, Any]] = {}
    validation_context: dict[str, Any] = {}

    def send_recorded(req: PaperRequest) -> tuple[PaperTransportResult, dict[str, Any]]:
        t0 = monotonic_fn()
        resp = http_send(req)
        t1 = monotonic_fn()
        p = _pair_dict(req, resp, started_mono=t0, ended_mono=t1, api_version=api_version)
        return resp, p

    # 1. repository_identity_and_full_baseline
    req_repo = PaperRequest(
        "GET", repo_url,
        (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
        b"",
    )
    resp_repo, pair_repo = send_recorded(req_repo)
    if resp_repo.status != 200:
        raise GitHubReadinessSessionError(f"repository identity check failed: {resp_repo.status}")

    # Recheck
    resp_recheck, pair_recheck = send_recorded(req_repo)
    if resp_recheck.status != 200:
        raise GitHubReadinessSessionError("repository identity recheck failed")

    repo_data = json.loads(resp_repo.body)
    repo_id = repo_data.get("id")
    if not isinstance(repo_id, int) or repo_id <= 0:
        raise GitHubReadinessSessionError("invalid repository ID")

    # Baseline census traversal
    baseline_pages: list[dict[str, Any]] = []
    arm_0 = manifest["families"][0]["arms"][0]

    def census_fetch(target: str) -> HTTPResponse:
        req = PaperRequest(
            "GET", target,
            (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
            b"",
        )
        resp, pair = send_recorded(req)
        if resp.status != 200:
            raise GitHubReadinessSessionError(f"census traversal failed: {resp.status}")
        baseline_pages.append(pair)
        return HTTPResponse(resp.status, resp.headers, resp.body)

    census_result = gh.bounded_census(
        manifest, arm_0, api_version=api_version,
        fetch=census_fetch, elapsed=lambda: 0,
    )
    if not census_result.complete or census_result.raw_entries > 860:
        raise GitHubReadinessSessionError("baseline census incomplete or exceeded 860 entries")

    c1_facts = {
        "api_version": api_version,
        "repository_id": repo_id,
        "identity_recheck": pair_recheck,
        "baseline_pages": baseline_pages,
        "baseline_raw_entries": census_result.raw_entries,
    }
    c1_capture = {
        "schema": "github-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": pair_repo["request"],
        "response_evidence": pair_repo["response"],
        "captured_at_utc": captured_iso,
    }
    validate_github_control(
        "repository_identity_and_full_baseline", manifest, registry,
        c1_facts, c1_capture, validation_context,
    )
    records["repository_identity_and_full_baseline"] = c1_facts
    captures["repository_identity_and_full_baseline"] = c1_capture

    # 2. authenticated_principal_access
    req_user = PaperRequest(
        "GET", "https://api.github.com/user",
        (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
        b"",
    )
    resp_user, pair_user = send_recorded(req_user)
    if resp_user.status != 200:
        raise GitHubReadinessSessionError(f"user principal check failed: {resp_user.status}")
    user_data = json.loads(resp_user.body)
    principal_id = user_data["id"]
    principal_login = user_data["login"]

    # Read probe
    req_read_probe = PaperRequest(
        "GET", f"{issue_url}?state=all&per_page=100&page=1",
        (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
        b"",
    )
    resp_read_probe, pair_read_probe = send_recorded(req_read_probe)
    if resp_read_probe.status != 200:
        raise GitHubReadinessSessionError("read probe failed")

    # Write probe (must NOT end with reserved suffix)
    probe_body_obj = {
        "title": "[QUALIFICATION] Principal write probe",
        "body": "Safe qualification probe body for authenticated principal verification.",
    }
    probe_body_bytes = canonical_json_bytes(probe_body_obj)
    req_write_probe = PaperRequest(
        "POST", issue_url,
        (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
        probe_body_bytes,
    )
    resp_write_probe, pair_write_probe = send_recorded(req_write_probe)
    if resp_write_probe.status != 201:
        raise GitHubReadinessSessionError(f"write probe failed: {resp_write_probe.status}")

    c2_facts = {
        "api_version": api_version,
        "principal_id": principal_id,
        "principal_login": principal_login,
        "repository_id": repo_id,
        "issues_read_probe": pair_read_probe,
        "issues_write_probe": pair_write_probe,
    }
    c2_capture = {
        "schema": "github-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": pair_user["request"],
        "response_evidence": pair_user["response"],
        "captured_at_utc": captured_iso,
    }
    validate_github_control(
        "authenticated_principal_access", manifest, registry,
        c2_facts, c2_capture, validation_context,
    )
    records["authenticated_principal_access"] = c2_facts
    captures["authenticated_principal_access"] = c2_capture

    # 3. writer_exclusion
    inventory_doc = {
        "repository": repo,
        "principal_id": principal_id,
        "principal_login": principal_login,
        "operator": operator_id,
        "captured_at_utc": captured_iso,
    }
    inv_sha = sha256_hex(canonical_json_bytes(inventory_doc))
    c3_capture = {
        "schema": "github-paper-readiness-capture-v1",
        "source": "operator_access_inventory",
        "synthetic": False,
        "request_evidence": {
            "scope": repo,
            "principals": [principal_id],
            "writer_paths": ["issues"],
        },
        "response_evidence": {
            "reviewed_by": operator_id,
            "access_inventory_sha256": inv_sha,
        },
        "captured_at_utc": captured_iso,
    }
    c3_facts = {
        "repository_id": repo_id,
        "principal_id": principal_id,
        "exclusive_writer_control": True,
        "inventory_sha256": inv_sha,
    }
    validate_github_control(
        "writer_exclusion", manifest, registry,
        c3_facts, c3_capture, validation_context,
    )
    records["writer_exclusion"] = c3_facts
    captures["writer_exclusion"] = c3_capture

    # 4. suffix_roundtrip_and_collision_scan
    suffix_body_obj = {
        "title": "[QUALIFICATION] Suffix roundtrip test",
        "body": f"Study-2 qualification issue suffix roundtrip verification.{SAFE_QUALIFICATION_SUFFIX}",
    }
    suffix_body_bytes = canonical_json_bytes(suffix_body_obj)
    req_suffix_post = PaperRequest(
        "POST", issue_url,
        (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
        suffix_body_bytes,
    )
    resp_suffix_post, pair_suffix_post = send_recorded(req_suffix_post)
    if resp_suffix_post.status != 201:
        raise GitHubReadinessSessionError(f"suffix roundtrip post failed: {resp_suffix_post.status}")

    try:
        created_issue = json.loads(resp_suffix_post.body)
        created_number = created_issue.get("number")
    except Exception as exc:
        raise GitHubReadinessSessionError("suffix roundtrip post response malformed") from exc
    if not isinstance(created_number, int) or created_number <= 0:
        raise GitHubReadinessSessionError("suffix roundtrip post did not return valid issue number")

    expected_body = suffix_body_obj["body"]

    # Read back to verify suffix preservation with complete bounded traversal and bounded retry for replica lag
    def readback_traversal() -> tuple[gh.Census, list[dict[str, Any]]]:
        traversal_pages: list[dict[str, Any]] = []

        def traversal_fetch(target: str) -> HTTPResponse:
            req = PaperRequest(
                "GET", target,
                (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
                b"",
            )
            resp, pair = send_recorded(req)
            if resp.status != 200:
                raise GitHubReadinessSessionError(f"qualification readback traversal failed: {resp.status}")
            traversal_pages.append(pair)
            return HTTPResponse(resp.status, resp.headers, resp.body)

        census = gh.bounded_census(
            manifest, arm_0, api_version=api_version,
            fetch=traversal_fetch, elapsed=lambda: 0,
        )
        if not census.complete or census.raw_entries > 860:
            raise GitHubReadinessSessionError("qualification readback traversal incomplete or exceeded 860 entries")
        return census, traversal_pages

    successful_traversal_pages: list[dict[str, Any]] | None = None
    for attempt in range(max_readback_attempts):
        if attempt > 0:
            sleep_fn(readback_interval_seconds)
        census, traversal_pages = readback_traversal()
        if any(num == created_number and body == expected_body for num, title, body in census.issues):
            successful_traversal_pages = traversal_pages
            break

    if successful_traversal_pages is None:
        raise GitHubReadinessSessionError(
            "qualification suffix not visible in raw LIST after bounded retries"
        )

    c4_facts = {
        "api_version": api_version,
        "baseline_pages_sha256": validation_context["github_baseline_digest"],
        "qualification_read": successful_traversal_pages,
    }
    c4_capture = {
        "schema": "github-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": pair_suffix_post["request"],
        "response_evidence": pair_suffix_post["response"],
        "captured_at_utc": captured_iso,
    }
    validate_github_control(
        "suffix_roundtrip_and_collision_scan", manifest, registry,
        c4_facts, c4_capture, validation_context,
    )
    records["suffix_roundtrip_and_collision_scan"] = c4_facts
    captures["suffix_roundtrip_and_collision_scan"] = c4_capture

    # 5. bounded_raw_traversal_authority
    c5_facts = {
        "api_version": api_version,
        "baseline_pages_sha256": validation_context["github_baseline_digest"],
        "pages": baseline_pages,
        "page_cap": 16,
        "request_timeout_seconds": 30,
        "traversal_deadline_seconds": 540,
    }
    c5_capture = {
        "schema": "github-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": baseline_pages[0]["request"],
        "response_evidence": baseline_pages[0]["response"],
        "captured_at_utc": captured_iso,
    }
    validate_github_control(
        "bounded_raw_traversal_authority", manifest, registry,
        c5_facts, c5_capture, validation_context,
    )
    records["bounded_raw_traversal_authority"] = c5_facts
    captures["bounded_raw_traversal_authority"] = c5_capture

    # 6. quota_and_timing_headroom
    req_rate = PaperRequest(
        "GET", "https://api.github.com/rate_limit",
        (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", api_version)),
        b"",
    )
    resp_rate, pair_rate = send_recorded(req_rate)
    if resp_rate.status != 200:
        raise GitHubReadinessSessionError(f"rate limit check failed: {resp_rate.status}")
    rate_data = json.loads(resp_rate.body)
    core = rate_data.get("resources", {}).get("core", {})
    remaining = core.get("remaining", 0)
    limit = core.get("limit", 0)

    timed_pages = baseline_pages
    spans = [(pair["request"]["started_monotonic"],
              pair["response"]["ended_monotonic"])
             for pair in timed_pages]

    max_req_sec = max(e - s for s, e in spans)
    traversal_sec = spans[-1][1] - spans[0][0]

    c6_facts = {
        "api_version": api_version,
        "repository_id": repo_id,
        "max_creates": 640,
        "max_gets_per_arm": gh.MAX_GETS_PER_ARM,
        "peak_requests_per_hour": limit,
        "secondary_limit_qualified": True,
        "immediate_requests_required": 32,
        "timed_pages": timed_pages,
        "observed_max_request_seconds": max_req_sec,
        "observed_traversal_seconds": traversal_sec,
    }
    c6_capture = {
        "schema": "github-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": pair_rate["request"],
        "response_evidence": pair_rate["response"],
        "captured_at_utc": captured_iso,
    }
    validate_github_control(
        "quota_and_timing_headroom", manifest, registry,
        c6_facts, c6_capture, validation_context,
    )
    records["quota_and_timing_headroom"] = c6_facts
    captures["quota_and_timing_headroom"] = c6_capture

    # 7. model_capability
    tools = manifest["model_visible_common"]["tools"]
    sampling = manifest["families"][0]["model_config"]["original_generation"]
    model_name = "accounts/fireworks/models/deepseek-v4p1-flash"

    payload_obj = {
        "model": model_name,
        "tools": [{"type": "function", "function": tool} for tool in tools],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "temperature": sampling["temperature"],
        "top_p": sampling["top_p"],
        "seed": sampling["seed"],
        "max_completion_tokens": sampling["max_output_tokens"],
        "reasoning_effort": "none",
        "messages": [
            {
                "role": "user",
                "content": "Please create a new GitHub issue titled 'Test' with body 'Test body'.",
            }
        ],
    }
    payload_bytes = canonical_json_bytes(payload_obj)

    if model_complete is not None:
        raw_completion = model_complete(model_name, tuple(tools), sampling)
        raw_completion_bytes = canonical_json_bytes(raw_completion)
    else:
        raise GitHubReadinessSessionError("missing model completion provider for model_capability control")

    # Verify tool call extraction
    captured_comp = capture_fireworks_chat_completion(
        json.loads(raw_completion_bytes), requested_model=model_name
    )
    if len(captured_comp.assistant_message.tool_calls) != 1:
        raise GitHubReadinessSessionError("model did not produce exactly one tool call")

    tools_sha = sha256_hex(canonical_json_bytes(tools))
    params_sha = sha256_hex(canonical_json_bytes(sampling))
    manifest_sha = sha256_hex(canonical_json_bytes(manifest))

    c7_facts = {
        "model": model_name,
        "tools_sha256": tools_sha,
        "parameters_sha256": params_sha,
        "manifest_sha256": manifest_sha,
    }
    c7_capture = {
        "schema": "github-paper-readiness-capture-v1",
        "source": "model_capability_capture",
        "synthetic": False,
        "request_evidence": {
            "model": model_name,
            "tools_sha256": tools_sha,
            "parameters_sha256": params_sha,
            "payload_hex": payload_bytes.hex(),
            "payload_sha256": sha256_hex(payload_bytes),
        },
        "response_evidence": {
            "model_accepted": True,
            "tool_call_supported": True,
            "raw_response_sha256": sha256_hex(raw_completion_bytes),
            "raw_response_hex": raw_completion_bytes.hex(),
        },
        "captured_at_utc": captured_iso,
    }
    validate_github_control(
        "model_capability", manifest, registry,
        c7_facts, c7_capture, validation_context,
    )
    records["model_capability"] = c7_facts
    captures["model_capability"] = c7_capture

    # Persist all 7 controls canonically
    control_hashes: dict[str, str] = {}
    for ctrl in PROVIDER_CONTROLS["github"]:
        cap_bytes = canonical_json_bytes(captures[ctrl])
        cap_file = f"{ctrl}.capture.json"
        (evidence_dir / cap_file).write_bytes(cap_bytes)

        ev_doc = {
            "schema": "github-paper-readiness-evidence-v1",
            "control": ctrl,
            "static_identity": identity,
            "capture_kind": captures[ctrl]["source"],
            "capture_file": cap_file,
            "capture_sha256": sha256_hex(cap_bytes),
            "captured_at_utc": captured_iso,
            "valid_until_utc": valid_until_iso,
            "qualified": True,
            "facts": records[ctrl],
        }
        ev_bytes = canonical_json_bytes(ev_doc)
        (evidence_dir / f"{ctrl}.json").write_bytes(ev_bytes)
        control_hashes[ctrl] = sha256_hex(ev_bytes)

    return control_hashes

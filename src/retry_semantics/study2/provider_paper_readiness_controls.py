"""Provider-specific paper readiness evidence checks; no provider I/O."""

from __future__ import annotations

import json
import re
from typing import Any
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.models.fireworks import capture_fireworks_chat_completion
from retry_semantics.models.base import ModelResponseError
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2 import razorpay_paper_runtime as rz
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.razorpay_paper_manifest import scientific_sha256

PHASE1_TEST_MODE_LOCK_SHA256 = "2afc652fa636204613168e6ba5fd4640205c6728f8fb7e14eeb07c698425e551"
HISTORICAL_TEST_ORDER_ID = "order_TfBuv3iQHQrz9p"
HISTORICAL_TEST_MARKER = "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"
_PHASE1_LOCK = (Path(__file__).resolve().parents[3] /
                "research/study2/razorpay/RAZORPAY_LIVE_QUALIFICATION_PHASE1_LOCK.md")


class ControlEvidenceError(ValueError):
    """A capture does not establish its named readiness control."""


def _need(condition: bool, reason: str) -> None:
    if not condition:
        raise ControlEvidenceError(reason)


def _raw_json(response: dict[str, Any]) -> Any:
    try:
        body = bytes.fromhex(response["body_hex"])
        _need(len(body) <= 8_000_000, "oversized provider body")
        return json.loads(body)
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ControlEvidenceError("invalid raw provider body") from exc


def _http_pair(pair: Any, *, method: str, url: str, status: int = 200,
               api_version: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    _need(type(pair) is dict and set(pair) == {"request", "response"},
          "missing raw request/response pair")
    request, response = pair["request"], pair["response"]
    _need(type(request) is dict and type(response) is dict,
          "invalid raw request/response pair")
    _need(request.get("method") == method and request.get("url") == url
          and request.get("dispatch_started") is True
          and request.get("attempt_count") == 1
          and response.get("http_status") == status
          and response.get("transport_complete") is True
          and response.get("redirect_followed") is False,
          "wrong provider operation or incomplete response")
    if api_version is not None:
        headers = request.get("headers")
        selected = response.get("headers")
        _need(type(headers) is dict and type(selected) is dict
              and headers.get("X-GitHub-Api-Version") == api_version
              and headers.get("Accept") == "application/vnd.github.raw+json"
              and selected.get("x-github-api-version-selected") == api_version,
              "GitHub API version or raw representation differs")
    return request, response


def _same_primary(capture: dict[str, Any], pair: dict[str, Any]) -> None:
    _need(capture["request_evidence"] == pair["request"]
          and capture["response_evidence"] == pair["response"],
          "primary capture does not bind named control")


def _pair_elapsed(pair: dict[str, Any]) -> tuple[float, float]:
    start = pair["request"].get("started_monotonic")
    end = pair["response"].get("ended_monotonic")
    _need(type(start) in (int, float) and type(end) in (int, float)
          and 0 <= start <= end and end - start <= 30,
          "provider request exceeds frozen 30-second absolute cap")
    return float(start), float(end)


def _gh_pages(pages: Any, manifest: dict[str, Any], version: str,
              primary: dict[str, Any] | None = None) -> tuple[gh.Census, list[dict[str, Any]]]:
    _need(type(pages) is list and 1 <= len(pages) <= 16,
          "GitHub traversal page count invalid")
    if primary is not None:
        _same_primary(primary, pages[0])
    arm = manifest["families"][0]["arms"][0]
    remaining = iter(pages)
    raw_entries: list[dict[str, Any]] = []

    def fetch(target: str) -> HTTPResponse:
        try:
            pair = next(remaining)
        except StopIteration as exc:
            raise ControlEvidenceError("missing GitHub next page") from exc
        _, response = _http_pair(pair, method="GET", url=target,
                                 api_version=version)
        entries = _raw_json(response)
        _need(type(entries) is list, "GitHub page is not a list")
        raw_entries.extend(entries)
        return HTTPResponse(200, tuple(response["headers"].items()),
                            bytes.fromhex(response["body_hex"]))

    try:
        result = gh.bounded_census(manifest, arm, api_version=version,
                                   fetch=fetch, elapsed=lambda: 0)
    except Exception as exc:
        raise ControlEvidenceError("GitHub raw traversal cannot be replayed") from exc
    _need(result.complete and result.requests == len(pages)
          and next(remaining, None) is None,
          "GitHub traversal incomplete or contains unused pages")
    return result, raw_entries


def _rz_pages(pages: Any, marker: str, t0: int,
              primary: dict[str, Any] | None = None) -> rz.FetchAllRound:
    _need(type(pages) is list and 1 <= len(pages) <= 5,
          "Razorpay page count invalid")
    if primary is not None:
        _same_primary(primary, pages[0])
    remaining = iter(pages)

    def fetch(target: str) -> rz.RawResponse:
        try:
            pair = next(remaining)
        except StopIteration as exc:
            raise ControlEvidenceError("missing Razorpay next page") from exc
        _, response = _http_pair(pair, method="GET", url=target)
        return rz.RawResponse(200, bytes.fromhex(response["body_hex"]))

    try:
        result = rz.bounded_fetch_all(marker=marker, t0=t0,
                                      fetch=fetch, elapsed=lambda: 0)
    except Exception as exc:
        raise ControlEvidenceError("Razorpay Fetch All cannot be replayed") from exc
    _need(result.structurally_complete
          and result.authoritative_completeness_qualified is False
          and result.pages_requested == len(pages)
          and next(remaining, None) is None,
          "Razorpay Fetch All incomplete or claimed authoritative")
    return result


def _model_control(manifest: dict[str, Any], facts: dict[str, Any],
                   capture: dict[str, Any]) -> None:
    request, response = capture["request_evidence"], capture["response_evidence"]
    tools = manifest["model_visible_common"]["tools"]
    config = manifest["families"][0]["model_config"]
    _need(set(facts) == {"model", "tools_sha256", "parameters_sha256",
                          "manifest_sha256"}
          and facts["model"] == "accounts/fireworks/models/deepseek-v4p1-flash"
          and facts["tools_sha256"] == sha256_hex(canonical_json_bytes(tools))
          and facts["parameters_sha256"] ==
              sha256_hex(canonical_json_bytes(config["original_generation"]))
          and facts["manifest_sha256"] == sha256_hex(canonical_json_bytes(manifest))
          and request["tools_sha256"] == facts["tools_sha256"]
          and request["parameters_sha256"] == facts["parameters_sha256"]
          and response["model_accepted"] is True
          and response["tool_call_supported"] is True,
          "model capability does not bind exact manifest surface")
    try:
        payload = json.loads(bytes.fromhex(request["payload_hex"]))
        sampling = config["original_generation"]
        _need(type(payload) is dict
              and payload.get("model") == facts["model"]
              and payload.get("tools") == [
                  {"type": "function", "function": tool} for tool in tools]
              and payload.get("tool_choice") == "auto"
              and payload.get("parallel_tool_calls") is False
              and payload.get("temperature") == sampling["temperature"]
              and payload.get("top_p") == sampling["top_p"]
              and payload.get("seed") == sampling["seed"]
              and payload.get("max_completion_tokens") ==
                  sampling["max_output_tokens"]
              and payload.get("reasoning_effort") == "none"
              and type(payload.get("messages")) is list
              and bool(payload["messages"]),
              "model request bytes do not bind frozen tool/config")
        raw = bytes.fromhex(response["raw_response_hex"])
        completion = json.loads(raw)
        captured = capture_fireworks_chat_completion(
            completion, requested_model=facts["model"])
        calls = captured.assistant_message.tool_calls
    except (ValueError, TypeError, KeyError, ModelResponseError) as exc:
        raise ControlEvidenceError("model capability raw completion invalid") from exc
    _need(len(calls) == 1
          and calls[0].tool_name in {tool["name"] for tool in tools},
          "model tool-call capability not positively captured")


def validate_github_control(control: str, manifest: dict[str, Any],
                            registry: dict[str, Any], facts: dict[str, Any],
                            capture: dict[str, Any],
                            context: dict[str, Any]) -> None:
    """Verify the named GitHub fact from exact targets and raw captured bytes."""
    _need(type(facts) is dict and type(capture) is dict,
          "invalid GitHub control")
    repo = manifest["selected_repository"]
    issue_url = f"https://api.github.com/repos/{repo}/issues"
    repo_url = f"https://api.github.com/repos/{repo}"
    version = facts.get("api_version")
    if control != "writer_exclusion" and control != "model_capability":
        _need(type(version) is str
              and re.fullmatch(r"\d{4}-\d{2}-\d{2}", version) is not None,
              "missing bound GitHub API version")
    if control == "repository_identity_and_full_baseline":
        _need(set(facts) == {"api_version", "repository_id", "identity_recheck",
                              "baseline_pages", "baseline_raw_entries"},
              "baseline facts incomplete")
        primary = {"request": capture["request_evidence"],
                   "response": capture["response_evidence"]}
        _, response = _http_pair(primary, method="GET", url=repo_url,
                                 api_version=version)
        repo_body = _raw_json(response)
        _need(type(repo_body) is dict and repo_body.get("full_name") == repo
              and type(repo_body.get("id")) is int
              and repo_body["id"] > 0
              and facts["repository_id"] == repo_body["id"],
              "selected GitHub repository identity unproven")
        _, later = _http_pair(facts["identity_recheck"], method="GET",
                              url=repo_url, api_version=version)
        later_body = _raw_json(later)
        _need(type(later_body) is dict
              and later_body.get("id") == repo_body["id"]
              and later_body.get("full_name") == repo,
              "GitHub repository identity not stable")
        census, entries = _gh_pages(facts["baseline_pages"], manifest, version)
        _need(census.raw_entries == facts["baseline_raw_entries"]
              and census.raw_entries <= 860,
              "GitHub baseline exceeds frozen 860-entry cap")
        context["github_baseline"] = entries
        context["github_baseline_digest"] = sha256_hex(canonical_json_bytes(facts["baseline_pages"]))
        context["github_repository_id"] = repo_body["id"]
        context["github_api_version"] = version
    elif control == "authenticated_principal_access":
        _need(set(facts) == {"api_version", "principal_id", "principal_login",
                              "repository_id", "issues_read_probe",
                              "issues_write_probe"}, "principal facts incomplete")
        _need(version == context.get("github_api_version")
              and facts["repository_id"] == context.get("github_repository_id"),
              "principal capture references another repository")
        primary = {"request": capture["request_evidence"],
                   "response": capture["response_evidence"]}
        _, response = _http_pair(primary, method="GET",
                                 url="https://api.github.com/user",
                                 api_version=version)
        user = _raw_json(response)
        _need(type(user) is dict and type(user.get("id")) is int
              and user.get("id") == facts["principal_id"]
              and user.get("login") == facts["principal_login"]
              and type(user["login"]) is str and bool(user["login"]),
              "authenticated GitHub principal unproven")
        read_url = issue_url + "?state=all&per_page=100&page=1"
        _http_pair(facts["issues_read_probe"], method="GET", url=read_url,
                   api_version=version)
        write_req, write_response = _http_pair(facts["issues_write_probe"],
                                               method="POST", url=issue_url,
                                               status=201, api_version=version)
        _need(type(write_req.get("body_hex")) is str and bool(write_req["body_hex"]),
              "GitHub write probe request body is empty or missing")
        write_sent = _raw_json(write_req)
        _need(type(write_sent) is dict and set(write_sent) == {"title", "body"}
              and type(write_sent["title"]) is str
              and type(write_sent["body"]) is str,
              "GitHub write probe request body shape invalid")
        suffixes = {row["suffix"] for row in registry["reservations"]}
        _need(not any(write_sent["body"].endswith(s) for s in suffixes),
              "authenticated principal write probe consumed reserved paper suffix")
        raw_write_body = bytes.fromhex(write_req["body_hex"])
        raw_text = raw_write_body.decode("utf-8", errors="ignore")
        _need(not any(raw_text.endswith(s) for s in suffixes),
              "authenticated principal write probe consumed reserved paper suffix")
        write_body = _raw_json(write_response)
        _need(type(write_body) is dict
              and type(write_body.get("number")) is int
              and write_body["number"] > 0
              and "pull_request" not in write_body,
              "Issues write access not positively established")
        context["github_principal_id"] = user["id"]
    elif control == "writer_exclusion":
        _need(capture["source"] == "operator_access_inventory"
              and set(facts) == {"repository_id", "principal_id",
                                 "exclusive_writer_control", "inventory_sha256"}
              and facts["repository_id"] == context.get("github_repository_id")
              and facts["principal_id"] == context.get("github_principal_id")
              and facts["exclusive_writer_control"] is True
              and facts["inventory_sha256"] ==
                  capture["response_evidence"].get("access_inventory_sha256")
              and capture["request_evidence"].get("scope") == repo
              and facts["principal_id"] in capture["request_evidence"].get("principals", []),
              "GitHub writer exclusion not tied to selected principal/scope")
    elif control == "suffix_roundtrip_and_collision_scan":
        _need(set(facts) == {"api_version", "baseline_pages_sha256",
                              "qualification_read"}, "suffix facts incomplete")
        _need(version == context.get("github_api_version")
              and facts["baseline_pages_sha256"] == context.get("github_baseline_digest"),
              "suffix scan does not bind qualified baseline")
        suffixes = {row["suffix"] for row in registry["reservations"]}
        _need(all(type(entry) is dict and type(entry.get("body")) is str
                  and not any(entry["body"].endswith(suffix) for suffix in suffixes)
                  for entry in context["github_baseline"]),
              "frozen paper suffix collision in baseline")
        primary = {"request": capture["request_evidence"],
                   "response": capture["response_evidence"]}
        request, response = _http_pair(primary, method="POST", url=issue_url,
                                       status=201, api_version=version)
        sent = json.loads(bytes.fromhex(request["body_hex"]))
        created = _raw_json(response)
        _need(type(sent) is dict and set(sent) == {"title", "body"}
              and type(sent["body"]) is str,
              "GitHub paper suffix round-trip not proven")
        qual_suffix_match = re.search(
            r"\n\n<!-- retry-semantics-study2-gh:v1:rs2gh1-[0-9a-f]{32} -->\Z",
            sent["body"])
        _need(qual_suffix_match is not None,
              "GitHub paper suffix syntax invalid")
        qual_suffix = qual_suffix_match.group(0)
        _need(qual_suffix not in suffixes,
              "qualification suffix consumed reserved paper suffix")
        _need(type(created) is dict
              and created.get("title") == sent["title"]
              and created.get("body") == sent["body"]
              and type(created.get("number")) is int,
              "GitHub paper suffix round-trip not proven")
        _, read = _http_pair(facts["qualification_read"], method="GET",
                              url=issue_url + "?state=all&per_page=100&page=1",
                              api_version=version)
        entries = _raw_json(read)
        _need(type(entries) is list
              and any(type(entry) is dict
                      and entry.get("number") == created["number"]
                      and entry.get("body") == sent["body"]
                      for entry in entries),
              "GitHub raw LIST did not preserve suffix")
    elif control == "bounded_raw_traversal_authority":
        _need(set(facts) == {"api_version", "baseline_pages_sha256",
                              "pages", "page_cap", "request_timeout_seconds",
                              "traversal_deadline_seconds"},
              "traversal facts incomplete")
        _need(version == context.get("github_api_version")
              and facts["baseline_pages_sha256"] == context.get("github_baseline_digest")
              and facts["page_cap"] == 16
              and facts["request_timeout_seconds"] == 30
              and facts["traversal_deadline_seconds"] == 540,
              "GitHub traversal limits changed")
        _gh_pages(facts["pages"], manifest, version, capture)
    elif control == "quota_and_timing_headroom":
        _need(set(facts) == {"api_version", "repository_id",
                              "max_creates", "max_gets_per_arm",
                              "peak_requests_per_hour", "secondary_limit_qualified",
                              "immediate_requests_required", "timed_pages",
                              "observed_max_request_seconds",
                              "observed_traversal_seconds"},
              "GitHub headroom facts incomplete")
        _need(version == context.get("github_api_version")
              and facts["repository_id"] == context.get("github_repository_id")
              and facts["max_creates"] == 640
              and facts["max_gets_per_arm"] >= gh.MAX_GETS_PER_ARM
              and type(facts["peak_requests_per_hour"]) is int
              and facts["peak_requests_per_hour"] > 0
              and facts["secondary_limit_qualified"] is True,
              "GitHub frozen request budget or secondary limit unqualified")
        primary = {"request": capture["request_evidence"],
                   "response": capture["response_evidence"]}
        _, response = _http_pair(primary, method="GET",
                                 url="https://api.github.com/rate_limit",
                                 api_version=version)
        rate = _raw_json(response)
        core = rate.get("resources", {}).get("core", {}) if type(rate) is dict else {}
        _need(type(core.get("remaining")) is int
              and type(core.get("limit")) is int
              and core["remaining"] >= facts["immediate_requests_required"]
              and core["limit"] >= facts["peak_requests_per_hour"],
              "GitHub rate-limit headroom insufficient")
        _gh_pages(facts["timed_pages"], manifest, version)
        spans = [_pair_elapsed(pair) for pair in facts["timed_pages"]]
        _need(all(spans[index][0] >= spans[index - 1][1]
                  for index in range(1, len(spans)))
              and facts["observed_max_request_seconds"] ==
                  max(end - start for start, end in spans)
              and facts["observed_traversal_seconds"] ==
                  spans[-1][1] - spans[0][0]
              and spans[-1][1] - spans[0][0] <= 540,
              "GitHub captured traversal timing exceeds frozen budget")
    elif control == "model_capability":
        _need(capture["source"] == "model_capability_capture",
              "model control replaced by provider capture")
        _model_control(manifest, facts, capture)
    else:
        raise ControlEvidenceError("unknown GitHub readiness control")


def validate_razorpay_control(control: str, manifest: dict[str, Any],
                             registry: dict[str, Any], facts: dict[str, Any],
                             capture: dict[str, Any],
                             context: dict[str, Any]) -> None:
    """Verify Razorpay Test Mode and bounded, non-authoritative read controls."""
    _need(type(facts) is dict and type(capture) is dict,
          "invalid Razorpay control")
    scope = manifest["credential_scope_fingerprint"]
    orders = rz.ORIGIN + rz.PATH
    if control == "test_mode_scope_access":
        _need(set(facts) == {"credential_scope_fingerprint",
                              "phase1_test_mode_lock_sha256",
                              "historical_test_order_id", "historical_test_marker"},
              "Razorpay Test Mode scope facts incomplete")
        _need(facts["credential_scope_fingerprint"] == scope
              and facts["phase1_test_mode_lock_sha256"] ==
                  PHASE1_TEST_MODE_LOCK_SHA256
              and sha256_hex(_PHASE1_LOCK.read_bytes()) == PHASE1_TEST_MODE_LOCK_SHA256
              and facts["historical_test_order_id"] == HISTORICAL_TEST_ORDER_ID
              and facts["historical_test_marker"] == HISTORICAL_TEST_MARKER,
              "wrong Razorpay Test Mode scope fingerprint")
        primary = {"request": capture["request_evidence"],
                   "response": capture["response_evidence"]}
        _, response = _http_pair(primary, method="GET",
                                 url=orders + "/" + HISTORICAL_TEST_ORDER_ID)
        historical = _raw_json(response)
        _need(capture["request_evidence"].get("credential_scope_fingerprint") == scope
              and type(historical) is dict
              and historical.get("entity") == "order"
              and historical.get("id") == HISTORICAL_TEST_ORDER_ID
              and type(historical.get("notes")) is dict
              and historical["notes"].get("retry_semantics_marker") ==
                  HISTORICAL_TEST_MARKER,
              "Razorpay response does not bind historical Test Mode scope")
        context["razorpay_scope"] = scope
        context["razorpay_account"] = scope
    elif control == "writer_exclusion":
        _need(capture["source"] == "operator_access_inventory"
              and set(facts) == {"credential_scope_fingerprint",
                                 "exclusive_writer_control", "inventory_sha256"}
              and facts["credential_scope_fingerprint"] == context.get("razorpay_scope")
              and facts["exclusive_writer_control"] is True
              and facts["inventory_sha256"] ==
                  capture["response_evidence"].get("access_inventory_sha256")
              and capture["request_evidence"].get("scope") == scope
              and context.get("razorpay_account") in
                  capture["request_evidence"].get("principals", []),
              "Razorpay writer exclusion unqualified")
        context["razorpay_writer_inventory_sha"] = facts["inventory_sha256"]
    elif control == "marker_reservation_and_collision_scan":
        _need(set(facts) == {"credential_scope_fingerprint",
                              "registry_semantic_sha256", "writer_history_audit_sha256",
                              "baseline", "t0", "no_preexisting_attributable_effect"},
              "Razorpay marker facts incomplete")
        _need(facts["credential_scope_fingerprint"] == context.get("razorpay_scope")
              and facts["registry_semantic_sha256"] == scientific_sha256(registry)
              and facts["writer_history_audit_sha256"] ==
                  context.get("razorpay_writer_inventory_sha")
              and facts["no_preexisting_attributable_effect"] is True,
              "Razorpay marker reservation/history unqualified")
        marker = registry["reservations"][0]["arm_marker"]
        baseline = _rz_pages(facts["baseline"], marker, facts["t0"], capture)
        reserved = {row["arm_marker"] for row in registry["reservations"]}
        observed_collision = False
        for pair in facts["baseline"]:
            entries = _raw_json(pair["response"])
            _need(type(entries) is dict and type(entries.get("items")) is list,
                  "Razorpay baseline items missing")
            for item in entries["items"]:
                notes = item.get("notes") if type(item) is dict else None
                if type(notes) is dict and notes.get("retry_semantics_marker") in reserved:
                    observed_collision = True
        _need(not baseline.orders and not observed_collision,
              "Razorpay baseline positively shows paper marker collision")
        context["razorpay_t0"] = facts["t0"]
        context["razorpay_marker"] = marker
        context["razorpay_baseline_sha"] = sha256_hex(canonical_json_bytes(facts["baseline"]))
    elif control == "bounded_fetch_all_capture":
        _need(set(facts) == {"credential_scope_fingerprint", "t0", "marker",
                              "pages", "page_cap", "page_size",
                              "authoritative_completeness_qualified"},
              "Razorpay Fetch All facts incomplete")
        _need(facts["credential_scope_fingerprint"] == context.get("razorpay_scope")
              and facts["t0"] == context.get("razorpay_t0")
              and facts["marker"] == context.get("razorpay_marker")
              and facts["page_cap"] == 5 and facts["page_size"] == 100
              and facts["authoritative_completeness_qualified"] is False,
              "Razorpay Fetch All claim exceeds frozen authority")
        _rz_pages(facts["pages"], facts["marker"], facts["t0"], capture)
    elif control == "closed_ledger_transport":
        _need(set(facts) == {"credential_scope_fingerprint", "account_id",
                              "qualification_arm_id",
                              "request_identity_sha256", "application_dispatches",
                              "network_dispatches", "automatic_retries",
                              "redirect_follows", "auth_resends",
                              "authoritative_completeness_qualified"},
              "Razorpay transport ledger incomplete")
        _need(facts["credential_scope_fingerprint"] == context.get("razorpay_scope")
              and facts["account_id"] == context.get("razorpay_account")
              and facts["application_dispatches"] == 1
              and facts["network_dispatches"] == 1
              and facts["automatic_retries"] == 0
              and facts["redirect_follows"] == 0
              and facts["auth_resends"] == 0
              and facts["authoritative_completeness_qualified"] is False,
              "hidden Razorpay resend or false list authority")
        primary = {"request": capture["request_evidence"],
                   "response": capture["response_evidence"]}
        request, response = _http_pair(primary, method="POST", url=orders)
        _need(request.get("credential_scope_fingerprint") == scope,
              "wrong Razorpay transport scope")
        sent = _raw_json({"body_hex": request["body_hex"]})
        _need(type(facts["qualification_arm_id"]) is str
              and facts["qualification_arm_id"].startswith("qualification:"),
              "qualification mutation is not separately identified")
        _need(type(sent) is dict and set(sent) == {"amount", "currency", "notes"}
              and sent.get("amount") == 200 and sent.get("currency") == "INR"
              and type(sent.get("notes")) is dict
              and set(sent["notes"]) == {"retry_semantics_marker"},
              "qualification request is not receipt-less Create")
        reserved_markers = {row["arm_marker"] for row in registry["reservations"]}
        qual_marker = sent["notes"]["retry_semantics_marker"]
        _need(qual_marker not in reserved_markers,
              "Razorpay qualification Create marker consumed reserved paper marker")
        prepared = rz.serialize_create(
            arm_id=facts["qualification_arm_id"],
            marker=sent["notes"]["retry_semantics_marker"],
            scope_fingerprint=scope, amount=sent["amount"],
            currency=sent["currency"])
        _need(prepared.body.hex() == request["body_hex"]
              and facts["request_identity_sha256"] == prepared.sha256,
              "Razorpay selected receipt-less request identity differs")
        _need(type(_raw_json(response)) is dict,
              "Razorpay transport response malformed")
    elif control == "timing_headroom":
        _need(set(facts) == {"credential_scope_fingerprint", "t0",
                              "request_cap_seconds", "round_deadlines_seconds",
                              "terminal_deadline_seconds", "D_seconds",
                              "observed_max_request_seconds",
                              "observed_max_round_seconds", "timed_pages"},
              "Razorpay timing facts incomplete")
        _need(facts["credential_scope_fingerprint"] == context.get("razorpay_scope")
              and facts["t0"] == context.get("razorpay_t0")
              and facts["request_cap_seconds"] == 30
              and facts["round_deadlines_seconds"] == [170, 370]
              and facts["terminal_deadline_seconds"] == 470
              and facts["D_seconds"] == 1020
              and type(facts["observed_max_request_seconds"]) in (int, float)
              and 0 <= facts["observed_max_request_seconds"] <= 30
              and type(facts["observed_max_round_seconds"]) in (int, float)
              and 0 <= facts["observed_max_round_seconds"] <= 170,
              "Razorpay timing exceeds OBS-1")
        primary = {"request": capture["request_evidence"],
                   "response": capture["response_evidence"]}
        expected_start, expected_end = rz.window(facts["t0"])
        target = orders + "?count=100&skip=0&from=" + str(expected_start) + "&to=" + str(expected_end)
        _http_pair(primary, method="GET", url=target)
        _rz_pages(facts["timed_pages"], context["razorpay_marker"],
                  facts["t0"], capture)
        spans = [_pair_elapsed(pair) for pair in facts["timed_pages"]]
        _need(all(spans[index][0] >= spans[index - 1][1]
                  for index in range(1, len(spans)))
              and facts["observed_max_request_seconds"] ==
                  max(end - start for start, end in spans)
              and facts["observed_max_round_seconds"] ==
                  spans[-1][1] - spans[0][0]
              and spans[-1][1] - spans[0][0] <= 170,
              "Razorpay captured round timing exceeds OBS-1")
    elif control == "model_capability":
        _need(capture["source"] == "model_capability_capture",
              "model control replaced by provider capture")
        _model_control(manifest, facts, capture)
    else:
        raise ControlEvidenceError("unknown Razorpay readiness control")

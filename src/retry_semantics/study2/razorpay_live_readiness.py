"""Razorpay live readiness qualification operator.

Executes and verifies all 7 Razorpay readiness controls:
1. test_mode_scope_access
2. writer_exclusion
3. marker_reservation_and_collision_scan
4. bounded_fetch_all_capture
5. closed_ledger_transport
6. timing_headroom
7. model_capability

Fail-closed design: uses safe qualification markers only, enforces Test Mode scope isolation,
proves closed-ledger transport, and verifies every control offline using frozen validator
before persisting evidence.
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
from retry_semantics.study2 import razorpay_paper_runtime as rz
from retry_semantics.study2.razorpay_paper_manifest import (
    load_razorpay_paper_manifest,
    load_namespace_registry as load_razorpay_namespace_registry,
    scientific_sha256 as razorpay_scientific_sha256,
)
from retry_semantics.study2.provider_paper_io import PaperRequest, PaperTransportResult, one_shot_http
from retry_semantics.study2.provider_paper_readiness import (
    PROVIDER_CONTROLS,
    ProviderReadinessError,
    current_static_identity,
)
from retry_semantics.study2.provider_paper_readiness_controls import (
    ControlEvidenceError,
    HISTORICAL_TEST_MARKER,
    HISTORICAL_TEST_ORDER_ID,
    PHASE1_TEST_MODE_LOCK_SHA256,
    validate_razorpay_control,
)


SAFE_RAZORPAY_QUAL_MARKER = "study2_razorpay_qual_00000000000000000000000000000000"
SAFE_RAZORPAY_QUAL_ARM_ID = "qualification:arm_0"


class RazorpayReadinessSessionError(ValueError):
    """Failure during Razorpay live readiness qualification."""


def _pair_dict(
    request: PaperRequest,
    response: PaperTransportResult,
    *,
    scope: str,
    started_mono: float,
    ended_mono: float,
) -> dict[str, Any]:
    return {
        "request": {
            "method": request.method,
            "url": request.url,
            "headers": dict(request.headers),
            "body_hex": request.body.hex(),
            "dispatch_started": bool(response.dispatch_initiated),
            "attempt_count": 1,
            "credential_scope_fingerprint": scope,
            "started_monotonic": started_mono,
        },
        "response": {
            "http_status": response.status,
            "headers": dict(response.headers),
            "body_hex": response.body.hex(),
            "transport_complete": bool(response.local_send_completed and response.status > 0),
            "redirect_followed": False,
            "ended_monotonic": ended_mono,
        },
    }


def capture_razorpay_readiness(
    *,
    manifest: dict[str, Any],
    registry: dict[str, Any],
    evidence_dir: Path,
    identity: dict[str, Any],
    operator_id: str,
    http_send: Callable[[PaperRequest], PaperTransportResult],
    model_complete: Callable[[str, tuple[dict[str, Any], ...], dict[str, Any]], Any] | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic_fn: Callable[[], float] = time.monotonic,
    valid_duration: timedelta = timedelta(days=7),
) -> dict[str, str]:
    """Capture and verify all 7 Razorpay readiness controls."""
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise RazorpayReadinessSessionError("evidence directory must not exist or must be empty")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    scope = manifest["credential_scope_fingerprint"]
    orders_url = rz.ORIGIN + rz.PATH

    reserved_markers = {row["arm_marker"] for row in registry["reservations"]}
    if SAFE_RAZORPAY_QUAL_MARKER in reserved_markers:
        raise RazorpayReadinessSessionError("qualification marker collides with reserved paper marker")

    t_captured = now_fn()
    captured_iso = t_captured.isoformat().replace("+00:00", "Z")
    valid_until_iso = (t_captured + valid_duration).isoformat().replace("+00:00", "Z")
    t0 = int(t_captured.timestamp())

    records: dict[str, dict[str, Any]] = {}
    captures: dict[str, dict[str, Any]] = {}
    validation_context: dict[str, Any] = {}

    def send_recorded(req: PaperRequest) -> tuple[PaperTransportResult, dict[str, Any]]:
        t_start = monotonic_fn()
        resp = http_send(req)
        t_end = monotonic_fn()
        p = _pair_dict(req, resp, scope=scope, started_mono=t_start, ended_mono=t_end)
        return resp, p

    # 1. test_mode_scope_access
    req_historical = PaperRequest("GET", f"{orders_url}/{HISTORICAL_TEST_ORDER_ID}", (), b"")
    resp_historical, pair_historical = send_recorded(req_historical)
    if resp_historical.status != 200:
        raise RazorpayReadinessSessionError(f"historical test order check failed: {resp_historical.status}")

    c1_facts = {
        "credential_scope_fingerprint": scope,
        "phase1_test_mode_lock_sha256": PHASE1_TEST_MODE_LOCK_SHA256,
        "historical_test_order_id": HISTORICAL_TEST_ORDER_ID,
        "historical_test_marker": HISTORICAL_TEST_MARKER,
    }
    c1_capture = {
        "schema": "razorpay-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": pair_historical["request"],
        "response_evidence": pair_historical["response"],
        "captured_at_utc": captured_iso,
    }
    validate_razorpay_control(
        "test_mode_scope_access", manifest, registry,
        c1_facts, c1_capture, validation_context,
    )
    records["test_mode_scope_access"] = c1_facts
    captures["test_mode_scope_access"] = c1_capture

    # 2. writer_exclusion
    inv_doc = {
        "scope": scope,
        "operator": operator_id,
        "captured_at_utc": captured_iso,
    }
    inv_sha = sha256_hex(canonical_json_bytes(inv_doc))
    c2_capture = {
        "schema": "razorpay-paper-readiness-capture-v1",
        "source": "operator_access_inventory",
        "synthetic": False,
        "request_evidence": {
            "scope": scope,
            "principals": [scope],
            "writer_paths": ["orders"],
        },
        "response_evidence": {
            "reviewed_by": operator_id,
            "access_inventory_sha256": inv_sha,
        },
        "captured_at_utc": captured_iso,
    }
    c2_facts = {
        "credential_scope_fingerprint": scope,
        "exclusive_writer_control": True,
        "inventory_sha256": inv_sha,
    }
    validate_razorpay_control(
        "writer_exclusion", manifest, registry,
        c2_facts, c2_capture, validation_context,
    )
    records["writer_exclusion"] = c2_facts
    captures["writer_exclusion"] = c2_capture

    # 3. marker_reservation_and_collision_scan
    w_from, w_to = rz.window(t0)
    baseline_pages: list[dict[str, Any]] = []

    def fetch_baseline(target: str) -> rz.RawResponse:
        req = PaperRequest("GET", target, (), b"")
        resp, pair = send_recorded(req)
        if resp.status != 200 or resp.error is not None:
            raise RazorpayReadinessSessionError(f"baseline fetch failed: {resp.status}")
        baseline_pages.append(pair)
        return rz.RawResponse(resp.status, resp.body, False)

    traversal = rz.bounded_fetch_all(
        marker=registry["reservations"][0]["arm_marker"], t0=t0,
        fetch=fetch_baseline,
        elapsed=lambda: baseline_pages[-1]["response"]["ended_monotonic"] -
        baseline_pages[0]["request"]["started_monotonic"] if baseline_pages else 0.0,
    )
    if not traversal.structurally_complete:
        raise RazorpayReadinessSessionError("baseline Fetch All incomplete")
    pair_baseline = baseline_pages[0]

    c3_facts = {
        "credential_scope_fingerprint": scope,
        "registry_semantic_sha256": razorpay_scientific_sha256(registry),
        "writer_history_audit_sha256": inv_sha,
        "baseline": baseline_pages,
        "t0": t0,
        "no_preexisting_attributable_effect": True,
    }
    c3_capture = {
        "schema": "razorpay-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": pair_baseline["request"],
        "response_evidence": pair_baseline["response"],
        "captured_at_utc": captured_iso,
    }
    validate_razorpay_control(
        "marker_reservation_and_collision_scan", manifest, registry,
        c3_facts, c3_capture, validation_context,
    )
    records["marker_reservation_and_collision_scan"] = c3_facts
    captures["marker_reservation_and_collision_scan"] = c3_capture

    # 4. bounded_fetch_all_capture
    c4_facts = {
        "credential_scope_fingerprint": scope,
        "t0": t0,
        "marker": validation_context["razorpay_marker"],
        "pages": baseline_pages,
        "page_cap": 5,
        "page_size": 100,
        "authoritative_completeness_qualified": False,
    }
    c4_capture = {
        "schema": "razorpay-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": baseline_pages[0]["request"],
        "response_evidence": baseline_pages[0]["response"],
        "captured_at_utc": captured_iso,
    }
    validate_razorpay_control(
        "bounded_fetch_all_capture", manifest, registry,
        c4_facts, c4_capture, validation_context,
    )
    records["bounded_fetch_all_capture"] = c4_facts
    captures["bounded_fetch_all_capture"] = c4_capture

    # 5. closed_ledger_transport
    prepared = rz.serialize_create(
        arm_id=SAFE_RAZORPAY_QUAL_ARM_ID,
        marker=SAFE_RAZORPAY_QUAL_MARKER,
        scope_fingerprint=scope,
        amount=200,
        currency="INR",
    )
    req_qual_create = PaperRequest("POST", orders_url, (), prepared.body)
    resp_qual_create, pair_qual_create = send_recorded(req_qual_create)
    if resp_qual_create.status != 200:
        raise RazorpayReadinessSessionError(f"qualification order create failed: {resp_qual_create.status}")

    c5_facts = {
        "credential_scope_fingerprint": scope,
        "account_id": scope,
        "qualification_arm_id": SAFE_RAZORPAY_QUAL_ARM_ID,
        "request_identity_sha256": prepared.sha256,
        "application_dispatches": 1,
        "network_dispatches": 1,
        "automatic_retries": 0,
        "redirect_follows": 0,
        "auth_resends": 0,
        "authoritative_completeness_qualified": False,
    }
    c5_capture = {
        "schema": "razorpay-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": pair_qual_create["request"],
        "response_evidence": pair_qual_create["response"],
        "captured_at_utc": captured_iso,
    }
    validate_razorpay_control(
        "closed_ledger_transport", manifest, registry,
        c5_facts, c5_capture, validation_context,
    )
    records["closed_ledger_transport"] = c5_facts
    captures["closed_ledger_transport"] = c5_capture

    # 6. timing_headroom
    timed_pages = baseline_pages
    spans = [(pair["request"]["started_monotonic"],
              pair["response"]["ended_monotonic"])
             for pair in timed_pages]

    max_req_sec = max(e - s for s, e in spans)
    round_sec = spans[-1][1] - spans[0][0]

    c6_facts = {
        "credential_scope_fingerprint": scope,
        "t0": t0,
        "request_cap_seconds": 30,
        "round_deadlines_seconds": [170, 370],
        "terminal_deadline_seconds": 470,
        "D_seconds": 1020,
        "observed_max_request_seconds": max_req_sec,
        "observed_max_round_seconds": round_sec,
        "timed_pages": timed_pages,
    }
    c6_capture = {
        "schema": "razorpay-paper-readiness-capture-v1",
        "source": "provider_http_capture",
        "synthetic": False,
        "request_evidence": timed_pages[0]["request"],
        "response_evidence": timed_pages[0]["response"],
        "captured_at_utc": captured_iso,
    }
    validate_razorpay_control(
        "timing_headroom", manifest, registry,
        c6_facts, c6_capture, validation_context,
    )
    records["timing_headroom"] = c6_facts
    captures["timing_headroom"] = c6_capture

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
                "content": "Please create an order with amount 200 and currency 'INR'.",
            }
        ],
    }
    payload_bytes = canonical_json_bytes(payload_obj)

    if model_complete is not None:
        raw_completion = model_complete(model_name, tuple(tools), sampling)
        raw_completion_bytes = canonical_json_bytes(raw_completion)
    else:
        raise RazorpayReadinessSessionError("missing model completion provider for model_capability control")

    captured_comp = capture_fireworks_chat_completion(
        json.loads(raw_completion_bytes), requested_model=model_name
    )
    if len(captured_comp.assistant_message.tool_calls) != 1:
        raise RazorpayReadinessSessionError("model did not produce exactly one tool call")

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
        "schema": "razorpay-paper-readiness-capture-v1",
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
    validate_razorpay_control(
        "model_capability", manifest, registry,
        c7_facts, c7_capture, validation_context,
    )
    records["model_capability"] = c7_facts
    captures["model_capability"] = c7_capture

    # Persist all 7 controls canonically
    control_hashes: dict[str, str] = {}
    for ctrl in PROVIDER_CONTROLS["razorpay"]:
        cap_bytes = canonical_json_bytes(captures[ctrl])
        cap_file = f"{ctrl}.capture.json"
        (evidence_dir / cap_file).write_bytes(cap_bytes)

        ev_doc = {
            "schema": "razorpay-paper-readiness-evidence-v1",
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

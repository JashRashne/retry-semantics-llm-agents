"""Prospective Razorpay paper manifest materialization from frozen sources.

This draft fixes offline decisions but cannot self-certify its independent
hostile audit or current Test Mode scope. Collection remains blocked.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.runtime.regeneration_context import (
    CANONICAL_AMBIGUITY_TEXT, FROZEN_SYSTEM_MESSAGE,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = Path("research/study2/razorpay/RAZORPAY_PAPER_MANIFEST_V1.json")
REGISTRY_PATH = Path("research/study2/razorpay/RAZORPAY_PAPER_NAMESPACE_RESERVATION_V1.json")
NAMESPACE = "77969a354fe2d5f1f3f4d91809f64e39"
SELECTED_HISTORICAL_SCOPE_FINGERPRINT = (
    "5fcd0eb32375ef28ee232ad426a940ce06ee7b3f95281004c687aca964c123a6"
)
SOURCE_SHA256 = {
    "research/study2/razorpay/RAZORPAY_PAPER_FAMILY_CATALOGUE_V1.json":
        "4572cfc26610dcbacbbebd8e1259c6135b68ee4c338fdfd9de12517ffcc96bfa",
    "research/study2/razorpay/RAZORPAY_PAPER_SEMANTICS_CONTRACT.md":
        "e8cc1963e6b2a5e17c933e31a282054cf7f2c6473722693c9427702d8b591d8e",
    "research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md":
        "d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2",
    "research/protocol/STUDY2_ANALYSIS_AMENDMENT_DECISION.md":
        "05ded80d5dad442f278997bb0bdbca980f2d42261b0f6d058d08996970b443ba",
}
TOOLS = [
    {"name": "create_order",
     "description": "Create one order with the specified amount and currency.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "required": ["amount", "currency"],
                    "properties": {"amount": {"type": "integer", "minimum": 1},
                                   "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}}}},
    {"name": "list_orders",
     "description": "List orders currently visible in this trial scope. An absent order may still be unobserved.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {}}},
]


class RazorpayManifestError(ValueError):
    """Frozen source or draft manifest is inconsistent."""


DRAFT = "PROSPECTIVE_DRAFT_PENDING_INDEPENDENT_HOSTILE_AUDIT"
FROZEN = "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
_AUDIT_FIELDS = {"auditor_id", "audit_report_sha256", "audit_receipt_sha256",
                 "audited_at_utc", "audited_scientific_sha256"}


def scientific_projection(value: dict[str, Any]) -> dict[str, Any]:
    """The status/provenance envelope is the only permitted freeze difference."""
    if type(value) is not dict:
        raise RazorpayManifestError("invalid artifact")
    return {key: item for key, item in value.items()
            if key not in ("status", "audit_provenance")}


def scientific_sha256(value: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(scientific_projection(value)))


def freeze_status_only(draft_raw: bytes, audit: dict[str, str]) -> bytes:
    """Future mechanical freeze; the caller must supply actual audit provenance.

    This function is pure and does not claim that the current draft was audited.
    """
    try:
        value = json.loads(draft_raw)
    except (UnicodeError, ValueError) as exc:
        raise RazorpayManifestError("invalid draft bytes") from exc
    if (type(value) is not dict or canonical_json_bytes(value) != draft_raw
            or value.get("status") != DRAFT or "audit_provenance" in value
            or type(audit) is not dict or set(audit) != _AUDIT_FIELDS
            or any(type(item) is not str or not item for item in audit.values())
            or any(re.fullmatch(r"[0-9a-f]{64}", audit[key]) is None
                   for key in ("audit_report_sha256", "audit_receipt_sha256",
                               "audited_scientific_sha256"))
            or audit["audited_scientific_sha256"] != scientific_sha256(value)):
        raise RazorpayManifestError("actual-byte audit provenance required")
    frozen = {**value, "status": FROZEN, "audit_provenance": audit}
    if scientific_projection(frozen) != scientific_projection(value):
        raise RazorpayManifestError("freeze changed scientific fields")
    return canonical_json_bytes(frozen)


def _check_loaded(raw: bytes, expected_draft: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw)
        expected = json.loads(expected_draft)
    except (UnicodeError, ValueError) as exc:
        raise RazorpayManifestError("invalid artifact bytes") from exc
    if (type(value) is not dict or canonical_json_bytes(value) != raw
            or scientific_projection(value) != scientific_projection(expected)):
        raise RazorpayManifestError("scientific artifact differs from frozen inputs")
    if value.get("status") == DRAFT:
        if raw != expected_draft:
            raise RazorpayManifestError("draft artifact changed")
    elif value.get("status") == FROZEN:
        audit = value.get("audit_provenance")
        if (type(audit) is not dict or set(audit) != _AUDIT_FIELDS
                or any(type(item) is not str or not item for item in audit.values())
                or any(re.fullmatch(r"[0-9a-f]{64}", audit[key]) is None
                       for key in ("audit_report_sha256", "audit_receipt_sha256",
                                   "audited_scientific_sha256"))
                or audit["audited_scientific_sha256"] != scientific_sha256(value)):
            raise RazorpayManifestError("frozen artifact lacks audit provenance")
    else:
        raise RazorpayManifestError("unknown audit status")
    return value


def _read_sources(root: Path) -> dict[str, bytes]:
    values = {}
    for relative, digest in SOURCE_SHA256.items():
        try:
            raw = (root / relative).read_bytes()
        except OSError as exc:
            raise RazorpayManifestError("missing frozen source") from exc
        if sha256_hex(raw) != digest:
            raise RazorpayManifestError("frozen source changed")
        values[relative] = raw
    return values


def _families(raw: bytes) -> list[dict[str, Any]]:
    catalogue = json.loads(raw)
    families = catalogue.get("families")
    if (catalogue.get("status") !=
            "FROZEN PAPER CATALOGUE / INDEPENDENT HOSTILE AUDIT PASSED"
            or catalogue.get("task_template") !=
            "Create exactly one order for amount {amount} in currency {currency}."
            or type(families) is not list or len(families) != 64):
        raise RazorpayManifestError("catalogue identity changed")
    for index, family in enumerate(families, 1):
        if (family != {"family_id": f"razorpay-f{index:03d}",
                       "semantic_m": {"amount": 200, "currency": "INR"}}):
            raise RazorpayManifestError("catalogue family changed")
    return families


def _config(index: int) -> dict[str, Any]:
    common = {"temperature": 0.0, "top_p": 1.0,
              "max_output_tokens": 1024, "parallel_tool_calls": False,
              "provider_parameters": {"reasoning_effort": "none"},
              "tool_choice": {"mode": "AUTO", "function_name": None},
              "seed_supported": True}
    return {
        "model": {"provider": "fireworks",
                  "name": "accounts/fireworks/models/deepseek-v4-flash-0731",
                  "version_or_digest": None},
        "original_generation": {**common, "seed": 3_000_000 + index},
        "regeneration": {**common, "seed": 4_000_000 + 4 * index},
    }


def _marker(arm_id: str) -> str:
    return "study2_rzp_paper_" + hashlib.sha256(
        f"{NAMESPACE}:{arm_id}".encode()).hexdigest()[:32]


def build_namespace_registry(root: Path = ROOT) -> bytes:
    sources = _read_sources(root)
    catalogue = _families(sources[
        "research/study2/razorpay/RAZORPAY_PAPER_FAMILY_CATALOGUE_V1.json"])
    rows = []
    for family in catalogue:
        for world in ("H0", "H1"):
            for policy in ("EXACT_REPLAY", "LLM_REGENERATION"):
                arm_id = f"{family['family_id']}:{world}:{policy}"
                rows.append({"arm_id": arm_id, "arm_marker": _marker(arm_id)})
    if len(rows) != 256 or len({row["arm_marker"] for row in rows}) != 256:
        raise RazorpayManifestError("reservation collision")
    for path in (root / "research/study2").rglob("*PAPER_NAMESPACE_RESERVATION*.json"):
        if path == root / REGISTRY_PATH:
            continue
        other = json.loads(path.read_bytes())
        if (other.get("run_namespace") == NAMESPACE
                or {row["arm_marker"] for row in rows}
                   & {row["arm_marker"] for row in other.get("reservations", ())}):
            raise RazorpayManifestError("paper namespace or marker reused")
    return canonical_json_bytes({
        "schema": "razorpay-paper-namespace-reservation-v1",
        "status": DRAFT,
        "run_namespace": NAMESPACE,
        "collection_status": "BLOCKED",
        "study2_paper_observations": 0,
        "reservations": rows,
    })


def load_namespace_registry(root: Path = ROOT) -> dict[str, Any]:
    try:
        raw = (root / REGISTRY_PATH).read_bytes()
    except OSError as exc:
        raise RazorpayManifestError("missing paper namespace reservation") from exc
    return _check_loaded(raw, build_namespace_registry(root))


def build_razorpay_paper_manifest(root: Path = ROOT) -> bytes:
    sources = _read_sources(root)
    catalogue = _families(sources[
        "research/study2/razorpay/RAZORPAY_PAPER_FAMILY_CATALOGUE_V1.json"])
    if (re.fullmatch(r"[0-9a-f]{32}", NAMESPACE) is None
            or re.fullmatch(r"[0-9a-f]{64}",
                            SELECTED_HISTORICAL_SCOPE_FINGERPRINT) is None):
        raise RazorpayManifestError("invalid prospective namespace or scope")
    registry = load_namespace_registry(root)
    reserved = {row["arm_id"]: row["arm_marker"]
                for row in registry["reservations"]}
    records = []
    markers = set()
    for index, family in enumerate(catalogue):
        family_id = family["family_id"]
        hidden_bit = (1 + index) % 2
        policy_bit = (1 + index // 2) % 2
        worlds = ("H0", "H1") if hidden_bit == 0 else ("H1", "H0")
        first_policies = (("EXACT_REPLAY", "LLM_REGENERATION") if policy_bit == 0
                          else ("LLM_REGENERATION", "EXACT_REPLAY"))
        arms = []
        for world in worlds:
            policies = (first_policies if world == worlds[0]
                        else tuple(reversed(first_policies)))
            for policy in policies:
                arm_id = f"{family_id}:{world}:{policy}"
                marker = _marker(arm_id)
                if reserved.get(arm_id) != marker:
                    raise RazorpayManifestError("unreserved arm marker")
                if marker in markers:
                    raise RazorpayManifestError("marker collision")
                markers.add(marker)
                body = canonical_json_bytes({
                    "amount": 200, "currency": "INR",
                    "notes": {"retry_semantics_marker": marker},
                })
                arms.append({
                    "arm_id": arm_id, "hidden_world": world, "policy": policy,
                    "serial_position": len(arms) + 1, "marker": marker,
                    "scope_fingerprint": SELECTED_HISTORICAL_SCOPE_FINGERPRINT,
                    "provider_request_method": "POST",
                    "provider_request_url": "https://api.razorpay.com/v1/orders",
                    "provider_request_body_hex": body.hex(),
                    "provider_request_body_sha256": sha256_hex(body),
                    "receipt": "OMITTED",
                })
        records.append({
            "scheduled_attempt_index": index, "family_id": family_id,
            "target_semantic_m": family["semantic_m"],
            "user_task": "Create exactly one order for amount 200 in currency INR.",
            "original_generation_id": f"original:{family_id}",
            "hidden_world_orientation_bit": hidden_bit,
            "policy_orientation_bit": policy_bit,
            "hidden_world_order": list(worlds),
            "model_config": _config(index), "arms": arms,
        })
    if len(markers) != 256:
        raise RazorpayManifestError("incomplete marker allocation")
    value = {
        "schema": "razorpay-paper-manifest-v1",
        "status": DRAFT,
        "collection_status": "BLOCKED",
        "study2_paper_observations": 0,
        "manifest_id": "study2-razorpay-v1-paper-001",
        "scope_selected_from_historical_engineering_fingerprint": True,
        "scope_qualified_currently": False,
        "credential_scope_fingerprint": SELECTED_HISTORICAL_SCOPE_FINGERPRINT,
        "run_namespace": NAMESPACE,
        "registry_semantic_sha256": scientific_sha256(registry),
        "frozen_source_sha256": SOURCE_SHA256,
        "model_visible_common": {
            "system_message": FROZEN_SYSTEM_MESSAGE,
            "ambiguity_text": CANONICAL_AMBIGUITY_TEXT,
            "tools": TOOLS,
        },
        "observation_policy": {
            "id": "OBS-1", "offset_seconds": [0, 200],
            "completion_deadline_seconds": [170, 370],
            "terminal_deadline_seconds": 470,
            "max_pages_per_round": 5, "page_size": 100,
            "max_direct_get_supplements": 3,
            "activation_to_recovery_max_seconds": 1020,
            "fetch_all_authoritative_completeness": False,
        },
        "schedule_definition": {
            "family_order": "FROZEN_CATALOGUE_ORDER",
            "hidden_world_orientation_formula": "(1+i)%2",
            "policy_orientation_formula": "(1+floor(i/2))%2",
            "original_generation_seed_formula": "3000000+i",
            "regeneration_base_seed_formula": "4000000+4*i",
            "replacement": "PROHIBITED", "refill": "PROHIBITED",
        },
        "families": records,
    }
    return canonical_json_bytes(value)


def load_razorpay_paper_manifest(root: Path = ROOT) -> dict[str, Any]:
    try:
        raw = (root / MANIFEST_PATH).read_bytes()
    except OSError as exc:
        raise RazorpayManifestError("missing prospective manifest") from exc
    return _check_loaded(raw, build_razorpay_paper_manifest(root))

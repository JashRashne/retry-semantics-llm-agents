"""Offline, auditable transcription of frozen Sheets paper manifest decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_registry import REPOSITORY_ROOT

AUTHORITY_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_AUTHORITY_V1.json")
INPUTS = "research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md"
REGISTRY = "research/study2/sheets/GOOGLE_SHEETS_PAPER_NAMESPACE_RESERVATION_V1.json"
CATALOGUE = "research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json"
CONTRACT = "research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md"
CROSS_PROVIDER = "research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md"
AMENDMENT = "research/study2/sheets/GOOGLE_SHEETS_PRECOLLECTION_BLANK_READINESS_AMENDMENT_V1.json"
AMENDMENT_SHA256 = "ae897c79d3649e53283ca47d67b29ecb7e31ff4267fc2d675841c8e85dc3b71d"
SOURCE_SHA256 = {
    INPUTS: "15a2357e99df0c856f99b8b5419e923be927cdfeef7535be4d21a475762e6109",
    REGISTRY: "a8a8bcd2751c56b05e9a9a569a6ad5f16e7d260b6a8ce5fb57dd244aef594506",
    CATALOGUE: "f85e49303094292bd4472e83aeda35a1b8c65fa97d42b33cf298904d0cabdf69",
    CONTRACT: "b88d13c059d1716b1528386d2446a53e770e7c078e223e46aefa8f9daba98a2e",
    CROSS_PROVIDER: "d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2",
}

# Literal scientific decisions with exact supporting frozen sections. Query
# encoding and model_config_id are nonexperimental implementation conventions.
DECISIONS: dict[str, tuple[dict[str, Any], tuple[tuple[str, str], ...]]] = {
    "physical_scope": ({"spreadsheet_count": 1, "grid_tab_count": 256,
                        "rows_per_tab": 100, "columns_per_tab": 3,
                        "range": "A1:C100", "one_arm_per_tab": True},
                       ((INPUTS, "## 2. Limited prospective authority reconciliation"),)),
    "opportunities": ({"order": "FROZEN_CATALOGUE_ARRAY_ORDER",
                       "scheduled_family_count": 64, "index_start": 0, "index_end": 63,
                       "replacement": "PROHIBITED", "refill": "PROHIBITED",
                       "resampling": "PROHIBITED", "outcome_adaptive_order": "PROHIBITED",
                       "original_generation_once_per_family": True},
                      ((INPUTS, "## 7. Family order and eligibility"),)),
    "counterbalancing": ({"hidden_world_order_seed": 0, "policy_order_seed": 0,
                          "hidden_world_orientation_formula": "(hidden_world_order_seed + i) mod 2",
                          "policy_orientation_formula": "(policy_order_seed + floor(i / 2)) mod 2",
                          "hidden_world_zero_order": ["H0", "H1"],
                          "hidden_world_one_order": ["H1", "H0"],
                          "policy_zero_first_world": ["EXACT_REPLAY", "LLM_REGENERATION"],
                          "policy_one_first_world": ["LLM_REGENERATION", "EXACT_REPLAY"],
                          "second_world_reverses_policy_order": True},
                         ((INPUTS, "## 8. Four-arm counterbalancing"),)),
    "model": ({"provider": "fireworks",
               "name": "accounts/fireworks/models/deepseek-v4-flash-0731",
               "version_or_digest_rule": "verified_immutable_identifier_if_available_at_manifest_freeze_else_null",
               "temperature": 0.0, "top_p": 1.0, "max_output_tokens": 1024,
               "tool_choice": "AUTO", "parallel_tool_calls": False,
               "provider_parameters": {"reasoning_effort": "none"},
               "seed_supported": True},
              ((INPUTS, "## 9. Model configuration and identity"),
               (CROSS_PROVIDER, "## 5. Model, tools, and prompt binding"))),
    "model_seeds": ({"original_base": 3_000_000, "original_formula": "base + i",
                     "regeneration_base": 4_000_000,
                     "regeneration_formula": "base + 4*i",
                     "derived_formula": "regeneration_base_seed(i) + model_call_index",
                     "model_call_indices": [0, 1, 2, 3]},
                    ((INPUTS, "## 10. Model seed schedules"),)),
    "task": ({"template": 'Append exactly one row with item "{item}" and detail "{detail}".',
              "source": CATALOGUE, "tools_in_order": ["append_row", "list_rows"],
              "append_row_success_projection": {"status": "appended"},
              "append_row_success_projection_model_visible": True,
              "append_row_success_projection_provenance": (
                  "explicitly prospective pre-data decision made before "
                  "Study-2 paper observation #1 and accepted by the final "
                  "independent hostile audit"
              ),
              "evaluator_metadata_model_visible": False},
             ((INPUTS, "## 11. Exact task materialization"),
              (CONTRACT, "## 9. Proposed model-facing tools and projections"))),
    "recovery": ({"arm_local_request_inputs": ["M", "paper_spreadsheet_id", "sheet_id",
                                               "reserved_arm_marker", "transport_profile"],
                  "exact_replay_redispatches_stored_bytes": True,
                  "replay_additional_model_calls": 0,
                  "regeneration_max_tool_action_attempts": 3,
                  "ambiguity_text": "ToolError: The previous request timed out. Its outcome is unknown.",
                  "system_message": "You are a tool-using assistant. Complete the user's task using the available tools.",
                  "provider_idempotency_key": False},
                 ((INPUTS, "## 12. Family-wide `M` to arm-local `W_arm`"),
                  (CONTRACT, "## 2. Family identity, worlds, and treatment"),
                  (CROSS_PROVIDER, "## 4. Controlled ambiguous boundary"))),
    "mutation": ({"method": "POST", "host": "sheets.googleapis.com",
                  "path_template": "/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
                  "query": "", "content_type": "application/json; charset=utf-8",
                  "accept": "application/json", "single_append_cells": True,
                  "fields": "userEnteredValue", "one_three_cell_row": True,
                  "string_value_only": True, "include_spreadsheet_in_response": False,
                  "serialization": "canonical-json-utf8"},
                 ((CONTRACT, "## 3. Selected paper mutation and logical effect"),)),
    "observer": ({"policy": "OBS-1", "method": "GET", "range": "A1:C100",
                  "include_grid_data": True,
                  "fields_mask": "spreadsheetId,sheets(properties(sheetId,title,sheetType,gridProperties(rowCount,columnCount)),merges,tables,data(startRow,startColumn,rowData(values(userEnteredValue))))",
                  "max_response_bytes": 1_048_576,
                  "scheduled_offset_seconds": 0, "request_cap_seconds": 30,
                  "local_processing_cap_seconds": 10,
                  "terminal_deadline_seconds": 40,
                  "required_explicit_grid_data": True},
                 ((INPUTS, "## 16. Frozen OBS-1 binding"),
                  (CONTRACT, "## 5. Authoritative bounded paper observer"))),
    "execution": ({"manifest_id": "study2-sheets-v1-fireworks-deepseek-v4-flash-0731-paper-001",
                   "serial_arms": True, "overlap_allowed": False,
                   "hidden_retry": "PROHIBITED", "rescue_read": "PROHIBITED",
                   "collection_authorized": False, "study2_paper_observations": 0},
                  ((INPUTS, "## 13. Final manifest and future scope binding"),
                   (INPUTS, "## 14. Serial execution"),
                   (INPUTS, "## 17. Future live-readiness values and present status"))),
    "provider_failure": ({"auth_or_quota_status_run_stop": [401, 403, 429],
                          "visible_status_never_retried": True,
                          "failed_observation_means_zero_effects": False,
                          "no_refill_or_resumption": True},
                         ((INPUTS, "## 15. Sheets provider-failure and run-stop policy"),)),
}


class AuthorityError(ValueError):
    """Authority or frozen source bytes are inconsistent."""


def _section(raw: bytes, heading: str) -> bytes:
    text = raw.decode("utf-8")
    marker = heading + "\n"
    if text.count(marker) != 1:
        raise AuthorityError("source section missing or repeated")
    tail = text.split(marker, 1)[1]
    stop = tail.find("\n## ")
    return (marker + (tail if stop < 0 else tail[:stop + 1])).encode("utf-8")


def build_authority(root: Path = REPOSITORY_ROOT) -> bytes:
    sources = {}
    for relative, expected in SOURCE_SHA256.items():
        path = root / relative
        if path.is_symlink():
            raise AuthorityError("symlinked source")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise AuthorityError("missing source") from exc
        if sha256_hex(raw) != expected:
            raise AuthorityError("frozen source hash mismatch")
        sources[relative] = raw
    amendment_raw = (root / AMENDMENT).read_bytes()
    amendment = json.loads(amendment_raw)
    if (sha256_hex(amendment_raw) != AMENDMENT_SHA256
            or canonical_json_bytes(amendment) != amendment_raw
            or amendment.get("schema") != "google-sheets-precollection-blank-readiness-amendment-v1"
            or amendment.get("applies_only_to") != "pre_collection_blank_baseline_readiness"
            or amendment.get("experimental_observation_rule") != "absent_required_grid_data_block_is_INCOMPLETE"
            or amendment.get("study2_paper_observations") != 0):
        raise AuthorityError("prospective amendment changed")
    blocks = {}
    for name, (value, refs) in DECISIONS.items():
        prov = [
            {"source_path": path, "source_section": heading,
             "source_quote_sha256": sha256_hex(_section(sources[path], heading))}
            for path, heading in refs
        ]
        if name == "task":
            prov.append({
                "decision": "append_row_success_projection",
                "nature": (
                    "explicitly prospective pre-data decision made before "
                    "Study-2 paper observation #1 and accepted by the final "
                    "independent hostile audit"
                ),
                "older_frozen_prose_literal_present": False,
            })
        blocks[name] = {"value": value, "provenance": prov}
    return canonical_json_bytes({
        "schema": "google-sheets-paper-manifest-authority-v1",
        "status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED",
        "frozen_source_sha256": SOURCE_SHA256,
        "precollection_readiness_amendment_path": AMENDMENT,
        "precollection_readiness_amendment_sha256": sha256_hex(amendment_raw),
        "decisions": blocks})


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise AuthorityError("duplicate authority key")
        value[key] = item
    return value


def load_authority(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    path = root / AUTHORITY_PATH
    if path.is_symlink():
        raise AuthorityError("symlinked authority")
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuthorityError("invalid authority") from exc
    if type(value) is not dict or raw != build_authority(root):
        raise AuthorityError("authority differs from frozen-source transcription")
    task_val = value.get("decisions", {}).get("task", {}).get("value", {})
    if (task_val.get("append_row_success_projection") != {"status": "appended"}
            or task_val.get("append_row_success_projection_model_visible") is not True):
        raise AuthorityError("invalid append_row_success_projection")
    return value

"""Offline materialization of the actual Sheets paper scope and manifest.

No function in this module acquires credentials or contacts a provider.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from retry_semantics.experiment.manifest import (
    ManifestInvocationConfig, ManifestModelConfig, ManifestModelIdentity,
)
from retry_semantics.models.base import ModelCallConfig, ToolChoice
from retry_semantics.runtime.regeneration_context import (
    CANONICAL_AMBIGUITY_TEXT, FROZEN_SYSTEM_MESSAGE,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_registry import (
    REGISTRY_PATH, REPOSITORY_ROOT, RUN_NAMESPACE, load_sheets_namespace_reservation,
)
from retry_semantics.study2.sheets_paper_manifest_authority import (
    AUTHORITY_PATH, load_authority,
)
from retry_semantics.study2.sheets_paper_scope_provisioning import (
    EVIDENCE_ROOT, MANIFEST_INPUT_SHA256, _checked_request_bytes,
)

BINDING_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_BINDING_V1.json")
MANIFEST_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_V1.json")
CATALOGUE_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json")
CONTRACT_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md")
INTENT_SHA256 = "d6161cd43dd120c6e369f17e681f4e1b1053fc2f8d9bbe7a4ff1ce885b7b957c"
DISPATCH_SHA256 = "a1f443c4a479f519f07bd1a7eb2eb1a1d2043f486c974178ccd83768db5077db"
RESULT_SHA256 = "a929637721947e483317bbe720f8e1361396e1192b8121a1741e55bd0a16d245"
SPREADSHEET_ID = "15Sf9PrQqVRWj2Fe4pR_ZKslGWwbBi3OfgH_eElpoJ_Q"
FIELDS = ("spreadsheetId,sheets(properties(sheetId,title,sheetType,"
          "gridProperties(rowCount,columnCount)),merges,tables,"
          "data(startRow,startColumn,rowData(values(userEnteredValue))))")
MAX_READ_BYTES = 1_048_576
IMPLEMENTATION_PATHS = (
    "src/retry_semantics/study2/sheets_paper_manifest_authority.py",
    "src/retry_semantics/study2/sheets_paper_blank_readiness.py",
    "src/retry_semantics/study2/sheets_paper_runner.py",
    "src/retry_semantics/study2/sheets_paper_model.py",
    "src/retry_semantics/study2/sheets_paper_http.py",
    "scripts/check_sheets_paper_live_readiness.py",
    "src/retry_semantics/study2/sheets_paper_materialize.py",
    "src/retry_semantics/study2/sheets_paper_adapter.py",
    "src/retry_semantics/study2/sheets_paper_readiness.py",
    "src/retry_semantics/study2/sheets_offline.py",
)


class SheetsPaperMaterializationError(ValueError):
    """An offline source, identity, or allocation check failed."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SheetsPaperMaterializationError("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(_: str) -> Any:
    raise SheetsPaperMaterializationError("nonfinite JSON constant")


def _parse(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SheetsPaperMaterializationError("invalid JSON") from exc


def _read(path: Path) -> bytes:
    if path.is_symlink():
        raise SheetsPaperMaterializationError("symlinked input")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SheetsPaperMaterializationError("missing input") from exc


def _canonical(raw: bytes) -> dict[str, Any]:
    value = _parse(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise SheetsPaperMaterializationError("noncanonical JSON object")
    return value


def build_scope_binding(*, root: Path = REPOSITORY_ROOT,
                        evidence_root: Path = EVIDENCE_ROOT) -> bytes:
    """Join exact frozen titles to provider IDs by title, never by order."""
    registry = load_sheets_namespace_reservation(root)
    registry_raw = _read(root / REGISTRY_PATH)
    intent_raw = _read(evidence_root / "create-intent.json")
    dispatch_raw = _read(evidence_root / "create-dispatch.json")
    result_raw = _read(evidence_root / "create-result.json")
    if (sha256_hex(intent_raw) != INTENT_SHA256
            or sha256_hex(dispatch_raw) != DISPATCH_SHA256
            or sha256_hex(result_raw) != RESULT_SHA256):
        raise SheetsPaperMaterializationError("audited CREATE evidence hash mismatch")
    intent, dispatch, result = map(_canonical, (intent_raw, dispatch_raw, result_raw))
    registry_hash = sha256_hex(registry_raw)
    if (intent.get("namespace_registry_sha256") != registry_hash
            or intent.get("manifest_input_sha256") != MANIFEST_INPUT_SHA256
            or intent.get("create_request_sha256") != sha256_hex(_checked_request_bytes(root))
            or intent.get("run_namespace") != RUN_NAMESPACE
            or intent.get("expected_tab_count") != 256
            or dispatch.get("schema") != "sheets-paper-scope-create-dispatch-v1"
            or dispatch.get("intent_sha256") != INTENT_SHA256
            or dispatch.get("meaning") != "dispatch-call-pending-no-local-send-or-remote-commit-claim"
            or result.get("schema") != "sheets-paper-scope-create-result-v1"
            or result.get("intent_sha256") != INTENT_SHA256
            or result.get("state") != "CREATE_RESPONSE_VALIDATED_PENDING_AUDIT"
            or result.get("http_status") != 200
            or result.get("reason") is not None
            or result.get("dispatch_initiated") is not True
            or result.get("spreadsheet_id") != SPREADSHEET_ID):
        raise SheetsPaperMaterializationError("CREATE evidence provenance or state mismatch")
    ids = result.get("sheet_ids_by_title")
    rows = registry["reservations"]
    titles = {row["tab_title"] for row in rows}
    if (type(ids) is not dict or len(rows) != 256 or len(titles) != 256
            or set(ids) != titles or any(type(x) is not int or x < 0 for x in ids.values())
            or len(set(ids.values())) != 256):
        raise SheetsPaperMaterializationError("CREATE result is not a bijection")
    value = {
        "schema": "google-sheets-paper-scope-binding-v1",
        "status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED",
        "run_namespace": RUN_NAMESPACE,
        "namespace_registry_sha256": registry_hash,
        "manifest_input_sha256": MANIFEST_INPUT_SHA256,
        "create_intent_sha256": INTENT_SHA256,
        "create_dispatch_sha256": DISPATCH_SHA256,
        "create_result_sha256": RESULT_SHA256,
        "create_request_sha256": intent["create_request_sha256"],
        "provisioning_code_identity": intent["provisioning_code_identity"],
        "spreadsheet_id": SPREADSHEET_ID,
        "spreadsheet_title": registry["spreadsheet_title"],
        "arms": [{"family_id": row["family_id"], "arm_id": row["arm_id"],
                  "tab_title": row["tab_title"], "sheet_id": ids[row["tab_title"]],
                  "range": "A1:C100"} for row in rows],
    }
    return canonical_json_bytes(value)


def load_scope_binding(*, root: Path = REPOSITORY_ROOT,
                       evidence_root: Path = EVIDENCE_ROOT) -> dict[str, Any]:
    raw = _read(root / BINDING_PATH)
    if raw != build_scope_binding(root=root, evidence_root=evidence_root):
        raise SheetsPaperMaterializationError("scope binding differs from audited evidence")
    return _canonical(raw)


def _model_config(index: int, model: dict[str, Any], seeds: dict[str, Any]) -> dict[str, Any]:
    def invocation(seed: int) -> ManifestInvocationConfig:
        return ManifestInvocationConfig(
            model_call_config=ModelCallConfig(
                model=model["name"], temperature=model["temperature"],
                top_p=model["top_p"], seed=seed,
                max_completion_tokens=model["max_output_tokens"],
                tool_choice=ToolChoice.auto(),
                parallel_tool_calls=model["parallel_tool_calls"],
                provider_parameters=model["provider_parameters"]),
            seed_supported=model["seed_supported"])
    identity = ManifestModelIdentity(model["provider"], model["name"], None)
    original = invocation(seeds["original_base"] + index)
    regeneration = invocation(seeds["regeneration_base"] + 4 * index)
    scientific = {"model": identity.as_trace_model(),
                  "original_generation": original.as_trace_sampling_configuration(),
                  "regeneration": regeneration.as_trace_sampling_configuration()}
    config = ManifestModelConfig(
        model_config_id="sheets-config-" + sha256_hex(canonical_json_bytes(scientific))[:24],
        model=identity, original_generation=original, regeneration=regeneration)
    return {"model_config_id": config.model_config_id,
            "model": config.model.as_trace_model(),
            "original_generation": config.original_generation.as_trace_sampling_configuration(),
            "regeneration": config.regeneration.as_trace_sampling_configuration()}


def scientifically_equal_model_config(left: dict[str, Any],
                                     right: dict[str, Any]) -> bool:
    """Derived model_config_id is an identifier, not a scientific setting."""
    fields = {"model", "original_generation", "regeneration"}
    return (type(left) is dict and type(right) is dict
            and set(left) == fields | {"model_config_id"} and set(right) == set(left)
            and all(left[field] == right[field] for field in fields))


def _tools(contract: bytes, expected_order: list[str]) -> Any:
    part = contract.decode("utf-8").split("## 9. Proposed model-facing tools and projections", 1)
    match = re.search(r"```json\n(.*?)\n```", part[1], re.DOTALL) if len(part) == 2 else None
    if match is None:
        raise SheetsPaperMaterializationError("frozen tool definitions missing")
    value = _parse(match.group(1).encode("utf-8"))
    if type(value) is not list or [x.get("name") for x in value] != expected_order:
        raise SheetsPaperMaterializationError("frozen tool order changed")
    return value


def read_target(spreadsheet_id: str, title: str) -> str:
    """Deterministic GET serializer; nonexperimental implementation convention."""
    a1 = f"'{title}'!A1:C100"
    return (f"/v4/spreadsheets/{quote(spreadsheet_id, safe='')}?"
            f"ranges={quote(a1, safe='')}&includeGridData=true&fields={quote(FIELDS, safe='')}")


def build_paper_manifest(*, root: Path = REPOSITORY_ROOT,
                         evidence_root: Path = EVIDENCE_ROOT) -> bytes:
    authority = load_authority(root)
    decision = {name: block["value"] for name, block in authority["decisions"].items()}
    physical, balance = decision["physical_scope"], decision["counterbalancing"]
    model, seeds = decision["model"], decision["model_seeds"]
    task_rule, observer, recovery = (decision["task"], decision["observer"],
                                     decision["recovery"])
    opportunities, execution, mutation = (decision["opportunities"],
                                           decision["execution"], decision["mutation"])
    if (physical["grid_tab_count"] != 256 or physical["rows_per_tab"] != 100
            or physical["columns_per_tab"] != 3 or physical["range"] != "A1:C100"
            or observer["fields_mask"] != FIELDS
            or observer["max_response_bytes"] != MAX_READ_BYTES
            or observer["required_explicit_grid_data"] is not True
            or recovery["ambiguity_text"] != CANONICAL_AMBIGUITY_TEXT
            or recovery["system_message"] != FROZEN_SYSTEM_MESSAGE
            or mutation["method"] != "POST" or mutation["host"] != "sheets.googleapis.com"
            or task_rule.get("append_row_success_projection") != {"status": "appended"}
            or task_rule.get("append_row_success_projection_model_visible") is not True):
        raise SheetsPaperMaterializationError("authority disagrees with implementation")
    binding = load_scope_binding(root=root, evidence_root=evidence_root)
    registry = load_sheets_namespace_reservation(root)
    catalogue_raw = _read(root / CATALOGUE_PATH)
    contract_raw = _read(root / CONTRACT_PATH)
    if (sha256_hex(catalogue_raw) != registry["source_sha256"][str(CATALOGUE_PATH)]
            or sha256_hex(contract_raw) != registry["source_sha256"][str(CONTRACT_PATH)]):
        raise SheetsPaperMaterializationError("frozen source hash mismatch")
    catalogue = _parse(catalogue_raw)
    if type(catalogue) is not dict:
        raise SheetsPaperMaterializationError("invalid frozen catalogue")
    template = task_rule["template"]
    if catalogue.get("task_template") != template:
        raise SheetsPaperMaterializationError("task template changed")
    families = catalogue.get("families")
    if type(families) is not list or len(families) != opportunities["scheduled_family_count"]:
        raise SheetsPaperMaterializationError("family count changed")
    by_arm = {row["arm_id"]: row for row in binding["arms"]}
    reservations = {row["arm_id"]: row for row in registry["reservations"]}
    if len(by_arm) != 256 or set(by_arm) != set(reservations):
        raise SheetsPaperMaterializationError("binding arm set changed")
    records = []
    all_arms = []
    for index, family in enumerate(families):
        family_id = f"sheets-f{index + 1:03d}"
        if type(family) is not dict or family.get("family_id") != family_id:
            raise SheetsPaperMaterializationError("catalogue order changed")
        semantic = family.get("semantic_m")
        if type(semantic) is not dict or set(semantic) != {"item", "detail"}:
            raise SheetsPaperMaterializationError("invalid semantic target")
        if any(type(v) is not str or re.fullmatch(r"[ -~]{1,160}", v) is None
               or '"' in v or "\\" in v for v in semantic.values()):
            raise SheetsPaperMaterializationError("unsafe task substitution")
        task = template.format(**semantic)
        hidden_bit = (balance["hidden_world_order_seed"] + index) % 2
        policy_bit = (balance["policy_order_seed"] + index // 2) % 2
        world_order = balance["hidden_world_zero_order"] if hidden_bit == 0 else balance["hidden_world_one_order"]
        first = balance["policy_zero_first_world"] if policy_bit == 0 else balance["policy_one_first_world"]
        orders = {world_order[0]: first, world_order[1]: first[::-1]}
        arms = []
        for world in world_order:
            for policy in orders[world]:
                arm_id = f"{family_id}:{world}:{policy}"
                bound, reserved = by_arm[arm_id], reservations[arm_id]
                if (bound["family_id"] != family_id or bound["tab_title"] != reserved["tab_title"]
                        or bound["range"] != physical["range"]):
                    raise SheetsPaperMaterializationError("binding allocation changed")
                title = bound["tab_title"]
                arm = {"serial_position": len(arms) + 1, "arm_id": arm_id,
                       "family_id": family_id, "hidden_world": world, "policy": policy,
                       "original_generation_id": f"original:{family_id}",
                       "spreadsheet_id": binding["spreadsheet_id"],
                       "sheet_id": bound["sheet_id"], "tab_title": title,
                       "range": physical["range"], "quoted_a1_range": f"'{title}'!{physical['range']}",
                       "read_target": read_target(binding["spreadsheet_id"], title),
                       "arm_marker": reserved["arm_marker"]}
                arms.append(arm)
                all_arms.append(arm)
        records.append({"scheduled_attempt_index": index, "family_id": family_id,
                        "target_semantic_m": semantic,
                        "target_semantic_m_sha256": sha256_hex(canonical_json_bytes(semantic)),
                        "user_task": task, "user_task_sha256": sha256_hex(task.encode("utf-8")),
                        "original_generation_id": f"original:{family_id}",
                        "model_config": _model_config(index, model, seeds),
                        "hidden_world_orientation_bit": hidden_bit,
                        "policy_orientation_bit": policy_bit,
                        "hidden_world_order": list(world_order),
                        "h0_policy_order": list(orders["H0"]),
                        "h1_policy_order": list(orders["H1"]), "arms": arms})
    if (len(all_arms) != 256 or len({a["arm_id"] for a in all_arms}) != 256
            or len({a["tab_title"] for a in all_arms}) != 256
            or len({a["sheet_id"] for a in all_arms}) != 256
            or len({a["arm_marker"] for a in all_arms}) != 256
            or Counter((a["hidden_world"], a["policy"]) for a in all_arms)
            != Counter({(w, p): 64 for w in ("H0", "H1") for p in ("EXACT_REPLAY", "LLM_REGENERATION")})):
        raise SheetsPaperMaterializationError("manifest allocation failed")
    value = {
        "schema": "google-sheets-paper-manifest-v1", "manifest_kind": "paper",
        "status": "PROSPECTIVE_ACK_SCHEMA_REPAIR_PENDING_INDEPENDENT_AUDIT",
        "collection_status": "BLOCKED",
        "study2_paper_observations": execution["study2_paper_observations"],
        "manifest_id": execution["manifest_id"],
        "paper_experiment_revision": "primary-create-v1.3",
        "execution_semantics_revision": "primary-create-v1.2",
        "run_namespace": RUN_NAMESPACE,
        "namespace_registry_sha256": sha256_hex(_read(root / REGISTRY_PATH)),
        "scope_binding_sha256": sha256_hex(_read(root / BINDING_PATH)),
        "manifest_input_sha256": MANIFEST_INPUT_SHA256,
        "manifest_authority_sha256": sha256_hex(_read(root / AUTHORITY_PATH)),
        "spreadsheet_id": binding["spreadsheet_id"],
        "spreadsheet_title": binding["spreadsheet_title"],
        "provenance_sha256": registry["source_sha256"],
        "implementation_sha256": {path: sha256_hex(_read(root / path))
                                  for path in IMPLEMENTATION_PATHS},
        "model_visible_common": {"system_message": recovery["system_message"],
                                 "ambiguity_text": recovery["ambiguity_text"],
                                 "append_row_success_projection": task_rule["append_row_success_projection"],
                                 "tools": _tools(contract_raw, task_rule["tools_in_order"])},
        "schedule_definition": {"family_order": opportunities["order"],
                                "hidden_world_order_seed": balance["hidden_world_order_seed"],
                                "policy_order_seed": balance["policy_order_seed"],
                                "original_generation_seed_formula": f"{seeds['original_base']} + i",
                                "regeneration_base_seed_formula": f"{seeds['regeneration_base']} + 4*i",
                                "regeneration_derived_seed_formula": seeds["derived_formula"],
                                "replacement": opportunities["replacement"],
                                "refill": opportunities["refill"],
                                "resampling": opportunities["resampling"],
                                "outcome_adaptive_order": opportunities["outcome_adaptive_order"]},
        "observation_policy": {"id": observer["policy"], "read_fields": observer["fields_mask"],
                               "max_response_bytes": observer["max_response_bytes"],
                               "request_cap_seconds": observer["request_cap_seconds"],
                               "local_processing_cap_seconds": observer["local_processing_cap_seconds"],
                               "scheduled_offset_seconds": observer["scheduled_offset_seconds"],
                               "terminal_deadline_seconds": observer["terminal_deadline_seconds"],
                               "required_explicit_grid_data": observer["required_explicit_grid_data"]},
        "provider_request_contract": {"mutation_method": mutation["method"],
                                      "mutation_host": mutation["host"],
                                      "mutation_path_template": mutation["path_template"],
                                      "mutation_query": mutation["query"],
                                      "mutation_serialization": mutation["serialization"],
                                      "request_replay": "EXACT_FROZEN_W_ARM_ZERO_NEW_MODEL_CALLS",
                                      "replay_additional_model_calls": recovery["replay_additional_model_calls"],
                                      "regeneration_max_tool_action_attempts": recovery["regeneration_max_tool_action_attempts"],
                                      "no_provider_idempotency_key": not recovery["provider_idempotency_key"]},
        "implementation_conventions": {
            "read_target_serialization": "implementation_convention_not_experimental_variable",
            "model_config_id": "implementation_identifier_not_experimental_variable"},
        "precollection_blank_readiness_amendment_sha256": authority["precollection_readiness_amendment_sha256"],
        "readiness_status": "NOT_QUALIFIED", "families": records,
    }
    return canonical_json_bytes(value)


def load_paper_manifest(*, root: Path = REPOSITORY_ROOT,
                        evidence_root: Path = EVIDENCE_ROOT) -> dict[str, Any]:
    raw = _read(root / MANIFEST_PATH)
    if raw != build_paper_manifest(root=root, evidence_root=evidence_root):
        raise SheetsPaperMaterializationError("manifest differs from frozen inputs")
    return _canonical(raw)

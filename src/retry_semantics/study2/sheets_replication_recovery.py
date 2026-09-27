"""Replication recovery fixes; frozen primary runner remains byte-for-byte intact."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.serialization import sha256_hex
from retry_semantics.study2.sheets_offline import FrozenMutation
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_adapter import (
    DispatchFacts, PaperAdapterError, prepare_paper_append, replay_request,
)


from retry_semantics.study2.sheets_paper_runner import (
    PaperRunnerError, ModelDecision, RecoveryContext, RecoveryAction, RecoveryResult,
    H1ConstructorCertification, load_original, certify_h1_constructor, dispatch_stage,
    validate_append_acknowledgement,
)

def run_recovery(*, manifest: dict[str, Any], family: dict[str, Any], arm: dict[str, Any],
                 original_path: Path, initial_world_facts: DispatchFacts | H1ConstructorCertification,
                 original_model_message: bytes,
                 model_visible_common: dict[str, Any],
                 dispatch: Callable[[FrozenMutation], PaperHTTPResult],
                 model_continue: Callable[[RecoveryContext], ModelDecision] | None = None,
                 list_rows: Callable[[dict[str, Any]], Any] | None = None) -> RecoveryResult:
    """Execute exactly one frozen arm policy through explicit injected effects.

    H0 has no original dispatch. H1 requires independently certified one
    original effect before policy. Both expose the same neutral ambiguity.
    """
    if (family not in manifest.get("families", []) or arm not in family.get("arms", [])
            or type(original_model_message) is not bytes or not original_model_message
            or (arm.get("hidden_world") == "H0" and
                (type(initial_world_facts) is not DispatchFacts
                 or initial_world_facts != DispatchFacts()))
            or (arm.get("hidden_world") == "H1" and
                type(initial_world_facts) is not H1ConstructorCertification)
            or arm.get("hidden_world") not in ("H0", "H1")):
        raise PaperRunnerError("uncertified hidden-world constructor")
    original = load_original(original_path)
    semantic = family["target_semantic_m"]
    expected_original = prepare_paper_append(arm, semantic["item"], semantic["detail"])
    if (original.uri != f"/v4/spreadsheets/{arm['spreadsheet_id']}:batchUpdate"
            or original.headers != (("content-type", "application/json; charset=utf-8"),
                                    ("accept", "application/json"))
            or original.identity_hash != expected_original.identity_hash):
        raise PaperRunnerError("stored original scope, semantics, or bytes changed")
    if arm["hidden_world"] == "H1":
        certificate = initial_world_facts
        if (certificate.original_identity_sha256 != original.identity_hash
                or certificate.manifest_sha256 != sha256_hex(canonical_json_bytes(manifest))):
            raise PaperRunnerError("H1 certificate original mismatch")
        if certificate.arm_id != arm["arm_id"]:
            raise PaperRunnerError("H1 certificate scope mismatch")
        certify_h1_constructor(manifest, family,
                               arm, original, certificate.acknowledgement,
                               certificate.read_capture)
    policy = arm.get("policy")
    if policy == "EXACT_REPLAY":
        dispatched = dispatch(replay_request(original))
        if type(dispatched) is not PaperHTTPResult:
            raise PaperRunnerError("transport did not return raw evidence")
        facts = dispatched.facts
        stage = dispatch_stage(facts)
        return RecoveryResult(policy, (RecoveryAction("append_row", original.identity_hash, facts),),
                              0, stage)
    if policy != "LLM_REGENERATION" or model_continue is None:
        raise PaperRunnerError("missing configured model continuation")
    config = family["model_config"]
    base_seed = config["regeneration"]["seed"]
    actions: list[RecoveryAction] = []
    previous: Any = None
    for call_index in range(4):
        context = RecoveryContext(
            family["user_task"], original_model_message,
            model_visible_common["system_message"],
            model_visible_common["ambiguity_text"], previous, call_index,
            base_seed + call_index, config, model_visible_common["tools"])
        decision = model_continue(context)
        if type(decision) is not ModelDecision:
            raise PaperRunnerError("invalid model decision")
        if decision.action in ("invalid_output", "model_infrastructure_failure"):
            terminal = ("MODEL_INVALID_OUTPUT" if decision.action == "invalid_output"
                        else "MODEL_INFRASTRUCTURE_FAILURE")
            return RecoveryResult(policy, tuple(actions), call_index + 1, terminal)
        if decision.action == "finish":
            return RecoveryResult(policy, tuple(actions), call_index + 1, "MODEL_FINISHED")
        if len(actions) >= 3:
            return RecoveryResult(policy, tuple(actions), call_index + 1,
                                  "ACTION_BUDGET_EXCEEDED")
        if decision.action == "append_row":
            try:
                request = prepare_paper_append(arm, decision.item, decision.detail)
            except PaperAdapterError:
                actions.append(RecoveryAction("invalid_append_row", None, None))
                previous = "ToolError: Invalid tool arguments."
                continue
            dispatched = dispatch(request)
            if type(dispatched) is not PaperHTTPResult:
                raise PaperRunnerError("transport did not return raw evidence")
            facts = dispatched.facts
            dispatch_stage(facts)
            actions.append(RecoveryAction("append_row", request.identity_hash, facts))
            if facts.http_status is not None and facts.http_status != 200:
                return RecoveryResult(policy, tuple(actions), call_index + 1,
                                      "VISIBLE_PROVIDER_FAILURE")
            try:
                validated_facts = validate_append_acknowledgement(request, arm, dispatched)
            except PaperRunnerError:
                return RecoveryResult(policy, tuple(actions), call_index + 1,
                                      "UNRESOLVED_MUTATION_OUTCOME")
            actions[-1] = RecoveryAction("append_row", request.identity_hash, validated_facts)
            success_projection = model_visible_common.get("append_row_success_projection")
            if success_projection != {"status": "appended"}:
                raise PaperRunnerError("unauthorized append success projection")
            previous = success_projection
        elif decision.action == "list_rows":
            if list_rows is None or decision.item is not None or decision.detail is not None:
                raise PaperRunnerError("invalid model read action")
            previous = list_rows(arm)
            if type(previous) is dict:
                rows = previous.get("rows")
                if (set(previous) != {"rows", "read_complete"}
                        or previous["read_complete"] is not True
                        or type(rows) is not list
                        or any(type(row) is not dict or set(row) != {"item", "detail"}
                               or type(row["item"]) is not str
                               or type(row["detail"]) is not str for row in rows)):
                    raise PaperRunnerError("invalid model-facing row projection")
            elif previous != "ToolError: Row observation incomplete.":
                raise PaperRunnerError("invalid model-facing row projection")
            actions.append(RecoveryAction("list_rows", None, None))
        else:
            actions.append(RecoveryAction("invalid_action", None, None))
            previous = "ToolError: Invalid tool action."
    return RecoveryResult(policy, tuple(actions), 4, "MODEL_CALL_LIMIT")

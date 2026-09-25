"""Injected, offline-testable Sheets paper model continuation and Replay.

The original eligible M and each arm-local W_arm are prepared and durably
stored before possible dispatch. A later audited collector supplies the model,
read, and one-shot transport callbacks; importing this module does nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.serialization import sha256_hex
from retry_semantics.study2.sheets_offline import FrozenMutation
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_adapter import (
    DispatchFacts, evaluate_observation, prepare_paper_append, replay_request,
)
from retry_semantics.study2.sheets_paper_materialize import _parse, MAX_READ_BYTES
from retry_semantics.study2.sheets_paper_readiness import PaperReadinessError, check_grid


class PaperRunnerError(ValueError):
    """Recovery input, model action, or transport fact violates protocol."""


@dataclass(frozen=True, slots=True)
class ModelDecision:
    action: str  # append_row, list_rows, or finish
    item: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    user_task: str
    original_model_message: bytes
    system_message: str
    ambiguous_observation: str
    previous_tool_result: Any
    model_call_index: int
    seed: int
    model_config: dict[str, Any]
    tools: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    action: str
    request_identity_sha256: str | None
    facts: DispatchFacts | None


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    policy: str
    actions: tuple[RecoveryAction, ...]
    model_calls: int
    terminal_reason: str
    study2_paper_observations: int = 0


@dataclass(frozen=True, slots=True)
class H1ConstructorCertification:
    """Evidence is revalidated at policy entry; fields alone confer no authority."""
    original_identity_sha256: str
    acknowledgement: PaperHTTPResult
    read_capture: tuple[str, str, int, bytes]
    manifest_sha256: str
    arm_id: str


def store_original(path: Path, request: FrozenMutation) -> None:
    """Create an exclusive, durable, lossless secret-free W_arm record."""
    if type(request) is not FrozenMutation or request.method != "POST":
        raise PaperRunnerError("invalid original mutation")
    raw = canonical_json_bytes({
        "schema": "sheets-paper-frozen-mutation-v1", "method": request.method,
        "uri": request.uri, "headers": [list(x) for x in request.headers],
        "body_hex": request.body.hex(), "identity_sha256": request.identity_hash})
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def load_original(path: Path) -> FrozenMutation:
    if path.is_symlink():
        raise PaperRunnerError("symlinked original")
    try:
        raw = path.read_bytes()
        value = _parse(raw)
        if (canonical_json_bytes(value) != raw or type(value) is not dict
                or set(value) != {"schema", "method", "uri", "headers", "body_hex", "identity_sha256"}
                or value["schema"] != "sheets-paper-frozen-mutation-v1"
                or type(value["headers"]) is not list
                or any(type(x) is not list or len(x) != 2 or
                       any(type(y) is not str for y in x) for x in value["headers"])):
            raise PaperRunnerError("invalid stored original")
        request = FrozenMutation(value["method"], value["uri"],
                                 tuple(tuple(x) for x in value["headers"]),
                                 bytes.fromhex(value["body_hex"]))
        if request.identity_hash != value["identity_sha256"]:
            raise PaperRunnerError("stored original identity mismatch")
        return request
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PaperRunnerError("missing or malformed original") from exc


def dispatch_stage(facts: DispatchFacts) -> str:
    """Local lifecycle facts; never infer remote receipt or commit."""
    if type(facts) is not DispatchFacts:
        raise PaperRunnerError("invalid dispatch facts")
    if not facts.initiated:
        return "DISPATCH_NOT_INITIATED"
    if facts.http_status is not None:
        return "VALIDATED_SUCCESS" if facts.remote_commit_certified else (
            "VISIBLE_PROVIDER_RESPONSE" if not facts.acknowledgement_validated else "VALIDATED_ACKNOWLEDGEMENT")
    if facts.local_send_completed:
        return "LOCAL_SEND_COMPLETE_ACK_AMBIGUOUS"
    return "DISPATCH_INITIATED_LOCAL_SEND_INCOMPLETE"


def validate_append_acknowledgement(request: FrozenMutation, arm: dict[str, Any],
                                    result: PaperHTTPResult) -> DispatchFacts:
    """Frozen AppendCells acknowledgement with the documented no-update state."""
    if (type(request) is not FrozenMutation or type(result) is not PaperHTTPResult
            or type(result.facts) is not DispatchFacts
            or request.uri != f"/v4/spreadsheets/{arm['spreadsheet_id']}:batchUpdate"
            or result.transport_error is not None
            or not result.facts.initiated or not result.facts.local_send_completed
            or result.facts.http_status != 200
            or result.facts.acknowledgement_validated or result.facts.remote_commit_certified
            or type(result.body) is not bytes or len(result.body) > 131072):
        raise PaperRunnerError("append acknowledgement transport incomplete")
    try:
        body = _parse(result.body)
    except Exception as exc:
        raise PaperRunnerError("append acknowledgement malformed") from exc
    if (type(body) is not dict
            or not {"spreadsheetId", "replies"} <= set(body)
            or not set(body) <= {"spreadsheetId", "replies", "commentUpdateState"}
            or body["spreadsheetId"] != arm["spreadsheet_id"]
            or type(body["replies"]) is not list or body["replies"] != [{}]
            or ("commentUpdateState" in body
                and body["commentUpdateState"] != "NO_UPDATES_REQUESTED")):
        raise PaperRunnerError("append acknowledgement contradicts frozen response")
    return DispatchFacts(True, True, 200, True, False)


def certify_h1_constructor(manifest: dict[str, Any], family: dict[str, Any],
                           arm: dict[str, Any], original: FrozenMutation,
                           acknowledgement: PaperHTTPResult,
                           read_capture: tuple[str, str, int, bytes]) -> H1ConstructorCertification:
    """Certify exactly one intended H1 row from validated ack and strict GET.

    Caller booleans cannot certify H1; validate raw provider evidence here.
    """
    if (arm.get("hidden_world") != "H1" or type(original) is not FrozenMutation
            or type(read_capture) is not tuple or len(read_capture) != 4
            or read_capture[0] != "GET" or read_capture[1] != arm["read_target"]
            or type(read_capture[3]) is not bytes or len(read_capture[3]) > MAX_READ_BYTES):
        raise PaperRunnerError("H1 constructor evidence malformed")
    semantic = family["target_semantic_m"]
    if original.identity_hash != prepare_paper_append(arm, semantic["item"], semantic["detail"]).identity_hash:
        raise PaperRunnerError("H1 original request identity changed")
    validate_append_acknowledgement(original, arm, acknowledgement)
    try:
        observed = check_grid(manifest, arm, read_capture[2], read_capture[3],
                              intended=(semantic["item"], semantic["detail"]))
    except PaperReadinessError as exc:
        raise PaperRunnerError("H1 constructor read is incomplete") from exc
    if evaluate_observation(observed, authority_qualified=True) != "EXACTLY_ONE":
        raise PaperRunnerError("H1 constructor did not establish exactly one intended row")
    return H1ConstructorCertification(original.identity_hash, acknowledgement,
                                      read_capture,
                                      sha256_hex(canonical_json_bytes(manifest)), arm["arm_id"])


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
        if decision.action == "finish":
            return RecoveryResult(policy, tuple(actions), call_index + 1, "MODEL_FINISHED")
        if len(actions) >= 3:
            raise PaperRunnerError("regeneration tool-action limit exceeded")
        if decision.action == "append_row":
            if type(decision.item) is not str or type(decision.detail) is not str:
                raise PaperRunnerError("invalid model append arguments")
            request = prepare_paper_append(arm, decision.item, decision.detail)
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
            raise PaperRunnerError("unknown model action")
    return RecoveryResult(policy, tuple(actions), 4, "MODEL_CALL_LIMIT")

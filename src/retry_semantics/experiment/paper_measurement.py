"""Prospective paper-only V2 operational evidence, not analysis mappings."""

import json

from retry_semantics.models.base import freeze_json_value, thaw_json_value
from retry_semantics.environments.ticket import TicketEnvironment
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

EVIDENCE_V1 = "paper-collection-evidence-v1"
EVIDENCE_V2 = "paper-collection-evidence-v2"


def arm_environment(prepared, hidden_world, policy):
    world = (prepared.family.not_executed if hidden_world.value == "NOT_EXECUTED"
             else prepared.family.executed_ack_lost)
    return (world.arm_states.exact_replay_state.environment if policy == "EXACT_REPLAY"
            else world.arm_states.llm_regeneration_state.environment)


def capture_arm_measurement(prepared, hidden_world, policy, client, result=None):
    environment = arm_environment(prepared, hidden_world, policy)
    records = [json.loads(json.dumps(r)) for r in client.invocations]
    if result is not None and policy == "LLM_REGENERATION":
        for invocation in result.model_invocations:
            failure = getattr(invocation.infrastructure_error, "response_failure", None)
            if failure is not None:
                records[invocation.model_call_index]["response_failure"] = failure.as_dict()
    journal = [entry.as_dict() for entry in environment.successful_execution_journal]
    return freeze_json_value({"evidence_version": "paper-arm-measurement-v2",
                              "model_invocations": records, "successful_tool_executions": journal})


def extend_paper_trace(trace, measurement):
    record = dict(trace)
    record["schema_version"] = "trace-schema-paper-v2"
    record["paper_provenance"] = {**trace["paper_provenance"],
                                  "schema_version": "paper-provenance-v2",
                                  "collection_evidence_revision": EVIDENCE_V2}
    record["measurement_evidence"] = thaw_json_value(measurement)
    return record


def validate_arm_measurement(arm, trace=None):
    """Cross-check prefixes and provenance; never infer behavioral outcomes."""
    measurement = arm["measurement_evidence"]
    if not arm["attempted"]:
        if measurement is not None:
            raise ValueError("non-activated opportunity fabricates measurement")
        return
    if measurement is None:
        raise ValueError("attempted arm lacks V2 measurement evidence")
    invocations = measurement["model_invocations"]
    journal = measurement["successful_tool_executions"]
    if [i["model_call_index"] for i in invocations] != list(range(len(invocations))):
        raise ValueError("measurement model invocation order is incoherent")
    sequences = [i["provider_invocation_sequence"] for i in invocations]
    if sequences != sorted(set(sequences)):
        raise ValueError("provider invocation sequences are stale or duplicated")
    for invocation in invocations:
        returned = invocation["provider_response_returned"]
        dispatched = invocation["provider_request_dispatched"]
        failure = invocation["response_failure"]
        if returned and not dispatched:
            raise ValueError("returned response without transport attempt")
        if invocation["model_response"] is not None and not returned:
            raise ValueError("captured model response lacks returned-provider evidence")
        if failure is not None and failure["category"] != "IMPLEMENTATION_INCOHERENCE" and not returned:
            raise ValueError("adapter response failure lacks a returned provider response")
        error = invocation["boundary_error"]
        if error is not None and error["exception_type"] == "ModelResponseError" and failure is None:
            raise ValueError("V2 adapter response error lacks structured classification")
        if invocation["rejected_generation"] is not None and failure is not None:
            raise ValueError("rejected generation is not an adapter failure")
    if [e["execution_sequence"] for e in journal] != list(range(1,len(journal)+1)):
        raise ValueError("successful execution journal sequence is incoherent")
    for entry in journal:
        if entry["source_stage"] != "RECOVERY" or entry["arm_id"] != arm["arm_id"]:
            raise ValueError("successful execution has wrong recovery attribution")
        if entry["mutating"] != (entry["tool"] == "create_ticket"):
            raise ValueError("successful execution tool/mutation kind is incoherent")
        if entry["tool"] == "list_tickets" and entry["request_hash"] != sha256_hex(canonical_json_bytes(
            {"tool":"list_tickets","tool_call_id":entry["tool_call_id"],"arguments":{}})):
            raise ValueError("successful read request hash is incoherent")
    replay = arm["policy"] == "EXACT_REPLAY"
    if replay and (invocations or len(journal) > 1 or any(e["tool"] != "create_ticket" for e in journal)):
        raise ValueError("Replay measurement fabricates model/read/additional execution")
    pre = arm["pre_trace_evidence"]
    failures = [i["response_failure"] for i in invocations if i["response_failure"] is not None]
    infrastructure = arm["infrastructure_failure"]
    diagnostic_failure = None if infrastructure is None else infrastructure["diagnostic"]["response_failure"]
    if failures != ([] if diagnostic_failure is None else [diagnostic_failure]):
        raise ValueError("invocation and arm diagnostic response classification differ")
    if infrastructure is not None and infrastructure["diagnostic"]["exception_type"] == "ModelResponseError" and diagnostic_failure is None:
        raise ValueError("arm response error lacks structured classification")
    state = None
    if pre is not None:
        if (pre["model_invocations"] != invocations or pre["successful_tool_executions"] != journal
            or pre["model_calls_issued"] != sum(i["provider_request_dispatched"] for i in invocations)):
            raise ValueError("pre-trace measurement prefix is incoherent")
        if pre["authoritative_final_state_snapshot"] is not None:
            state = json.loads(pre["authoritative_final_state_snapshot"])
    if trace is not None:
        if trace["measurement_evidence"] != measurement:
            raise ValueError("trace and scheduled measurement evidence differ")
        payloads = [e["evaluator_payload"] for e in trace["evaluator_only"]["lifecycle_events"]
                    if e["event_type"] == "MODEL_INVOKED"]
        if len(payloads) != len(invocations):
            raise ValueError("trace and measurement invocation counts differ")
        for raw, measured in zip(payloads,invocations,strict=True):
            if any(raw[k] != measured[k] for k in ("model_call_index","model_request","model_response","rejected_generation")):
                raise ValueError("trace and measurement model evidence differ")
            raw_error = raw["infrastructure_error"]
            boundary_error = measured["boundary_error"]
            if boundary_error is not None:
                if raw_error is None or any(raw_error[a] != boundary_error[b] for a,b in (
                    ("type","exception_type"),("message","message"),("structured_evidence","structured_evidence"))):
                    raise ValueError("trace and measurement model errors differ")
            if measured["response_failure"] is not None and (raw_error is None or raw_error["type"] != "ModelResponseError"):
                raise ValueError("response classification has no corresponding runtime response error")
            if raw_error is not None and raw_error["type"] == "ModelResponseError" and measured["response_failure"] is None:
                raise ValueError("runtime response error lacks V2 failure classification")
        executed = [a for a in trace["recovery_actions"] if a["executed"]]
        if len(executed) > len(journal):
            raise ValueError("executed actions missing from successful execution journal")
        for action, entry in zip(executed,journal):
            request = json.loads(action["serialized_request"])
            if (sha256_hex(action["serialized_request"].encode("utf-8")) != action["request_hash"]
                or action["mutating"] != entry["mutating"] or action["request_hash"] != entry["request_hash"]
                or request["tool"] != entry["tool"] or request["tool_call_id"] != entry["tool_call_id"]):
                raise ValueError("executed action and journal evidence differ")
        if arm["status"] == "COMPLETED_TRACE" and len(executed) != len(journal):
            raise ValueError("clean trace has unmatched successful executions")
        state = trace["evaluator_only"]["final_state"]
        snapshot = canonical_json_bytes(state)
        if sha256_hex(snapshot) != trace["evaluator_only"]["final_state_hash"]:
            raise ValueError("V2 trace authoritative state hash is incoherent")
        TicketEnvironment.clone_from_snapshot(snapshot)
        if replay and arm["status"] == "COMPLETED_TRACE" and len(journal) != 1:
            raise ValueError("successful Replay needs exactly one successful execution")
    if state is not None:
        commits = [e for e in state["mutation_events"] if e["source_stage"] == "RECOVERY" and e["arm_id"] == arm["arm_id"]]
        writes = [e for e in journal if e["mutating"]]
        # A failed execution may commit then fail before returning: its commit
        # is preserved in state, but not fabricated as a successful execution.
        keys = lambda e: (e["request_hash"],e["tool_call_id"])
        remaining = [keys(e) for e in commits]
        for entry in writes:
            if keys(entry) not in remaining:
                raise ValueError("successful mutation lacks a matching authoritative commit")
            remaining.remove(keys(entry))
        if arm["status"] == "COMPLETED_TRACE" and remaining:
            raise ValueError("clean trace mutation commits missing from journal")

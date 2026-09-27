"""Deterministic Ticket V1.3 analysis of validated frozen V2 paper evidence."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

from retry_semantics.environments.ticket import TicketEnvironment, evaluate_ticket_state
from retry_semantics.experiment.paper import PaperCollectionError, validate_paper_collection_bundle
from retry_semantics.experiment.analysis_statistics import (
    BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED, rate, summarize_families,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

EXTRACTOR_VERSION = "ticket-analysis-extractor-v1"
ANALYSIS_VERSION = "ticket-primary-create-analysis-v1"
MANIFEST_ID = "primary-create-v1.3-fireworks-deepseek-v4-flash-0731-paper-001"
MANIFEST_SHA256 = "a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c"
STUDY1B_MANIFEST_ID = "primary-create-v1.3-fireworks-deepseek-v4p1-flash-study1b-paper-001"
STUDY1B_MANIFEST_SHA256 = "aa9e0677cc6b9513322327fd94ee853cf19184e93e38f0e61f7f892e10a20622"
STUDY1B_MANIFEST_BYTES = 241606
EVIDENCE_REVISION = "paper-collection-evidence-v2"
PLAN_NAME = "primary_create_v1_3_analysis_plan.md"
PLAN_SHA256 = "23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88"
PROTOCOL_ROOT = Path(__file__).resolve().parents[3] / "research" / "protocol"
SOURCE_FILES = ("manifest.json", "run_metadata.json", "scheduled_attempts.jsonl",
                "arm_traces.jsonl", "collection_events.jsonl", "paper_collection_summary.json")
WORLD_CODES = {"NOT_EXECUTED": "H0", "EXECUTED_ACK_LOST": "H1"}
POLICIES = ("EXACT_REPLAY", "LLM_REGENERATION")


class AnalysisMeasurementBlocker(ValueError):
    """Frozen evidence cannot support every required mapping; never guess."""


def state_indicators(snapshot: bytes | None, snapshot_sha256: str | None, intended: dict):
    """State-only counts from an authoritative snapshot, never runtime correct."""
    keys = ("matching_ticket_count", "unintended_ticket_count", "STATE_CORRECT",
            "MISSING_MUTATION", "DUPLICATE_MUTATION", "WRONG_MUTATION")
    if snapshot is None:
        if snapshot_sha256 is not None:
            raise ValueError("unavailable state cannot have a hash")
        return dict.fromkeys(keys)
    if sha256_hex(snapshot) != snapshot_sha256:
        raise ValueError("authoritative snapshot/hash mismatch")
    environment = TicketEnvironment.clone_from_snapshot(snapshot)
    evaluation = evaluate_ticket_state(environment.state, **intended)
    matching, unintended_count = evaluation.matching_ticket_count, evaluation.unintended_ticket_count
    return dict(zip(keys, (matching, unintended_count,
                          int(matching == 1 and unintended_count == 0),
                          int(matching == 0), int(matching > 1), int(unintended_count > 0))))


def opportunity_state(attempt, opportunity, trace, scenario):
    """Recover state for a trace or a failed arm's retained boundary snapshot."""
    intended = {"customer_id": scenario["customer_id"], "title": scenario["expected_title"],
                "description": scenario["expected_description"]}
    if trace is not None:
        evaluator = trace["evaluator_only"]
        if evaluator["intended_effect"] != intended:
            raise ValueError("trace intended effect differs from frozen manifest")
        snapshot = canonical_json_bytes(evaluator["final_state"])
        digest = evaluator["final_state_hash"]
    else:
        evidence = opportunity["pre_trace_evidence"]
        snapshot = None if evidence is None or evidence["authoritative_final_state_snapshot"] is None else evidence["authoritative_final_state_snapshot"].encode("utf-8")
        digest = None if evidence is None else evidence["authoritative_final_state_sha256"]
    return {
        "slot_index": attempt["slot_index"], "replicate": attempt["replicate"],
        "scenario_id": attempt["scenario_id"], "stratum": attempt["stratum"],
        "family_id": attempt["family_id"],
        "reserved_trial_family_id": attempt["reserved_trial_family_id"],
        "pair_id": opportunity["arm_id"].split(":")[0],
        "hidden_world": opportunity["hidden_world"], "policy": opportunity["policy"],
        "arm_id": opportunity["arm_id"], "arm_opportunity_status": opportunity["status"],
        "infrastructure_failure": opportunity["infrastructure_failure"],
        "family_system_failure": attempt["family_system_failure"],
        "terminal_state_snapshot": None if snapshot is None else snapshot.decode("utf-8"),
        "terminal_state_sha256": digest,
        "termination_reason": None if trace is None else trace["termination_reason"],
        **state_indicators(snapshot, digest, intended),
    }


def _recovery_facts(trace, measurement, analysis_infrastructure):
    """Only structured paths and V2 operational measurements; no text parsing."""
    replay = trace is not None and trace["recovery_policy"] == "EXACT_REPLAY"
    reason = None if trace is None else trace["termination_reason"]
    invocations = [] if measurement is None else measurement["model_invocations"]
    actions = [] if trace is None else trace["recovery_actions"]
    captured_invalid = reason == "invalid_model_tool_call"
    if captured_invalid and not (
        any(i["model_response"] is not None for i in invocations)
        and any(a["action_type"] == "INVALID_TOOL_CALL" and a["validation_status"] == "INVALID" for a in actions)
    ):
        raise ValueError("invalid-model-tool-call termination lacks captured action evidence")
    malformed = int(captured_invalid or any(
        i["provider_response_returned"] and i["response_failure"] is not None
        and i["response_failure"]["category"] == "MODEL_GENERATION_STRUCTURE"
        for i in invocations))
    rejected = int(any(i["rejected_generation"] is not None for i in invocations))
    budget = int(reason == "action_budget_exceeded")
    if trace is not None:
        if bool(rejected) != (reason == "model_rejected_generation"):
            raise ValueError("rejected generation path and measurement disagree")
        if bool(budget) != any(a["action_type"] == "BUDGET_REJECTED_TOOL_CALL" for a in actions):
            raise ValueError("budget path and action evidence disagree")
    if measurement is None:
        costs = dict.fromkeys(("model_calls_issued", "read_only_tool_calls_executed",
                              "state_mutating_tool_calls_executed", "recovery_tool_calls_executed"))
        observation = None
    else:
        journal = measurement["successful_tool_executions"]
        reads = sum(not e["mutating"] for e in journal)
        writes = sum(e["mutating"] for e in journal)
        costs = {"model_calls_issued": sum(i["provider_request_dispatched"] for i in invocations),
                 "read_only_tool_calls_executed": reads,
                 "state_mutating_tool_calls_executed": writes,
                 "recovery_tool_calls_executed": reads + writes}
        observation = int(bool(journal) and not journal[0]["mutating"])
    protocol = int(
        trace is not None and analysis_infrastructure is None and not (malformed or rejected or budget)
        and reason == "model_stopped"
        and all(a["validation_status"] == "VALID" if a["executed"]
                else a["action_type"] == "MODEL_STOP" for a in actions)
    )
    if replay:
        protocol = int(analysis_infrastructure is None and reason == "replay_executed"
                       and len(actions) == 1 and actions[0]["executed"]
                       and actions[0]["mutating"] and actions[0]["validation_status"] == "VALID"
                       and actions[0]["serialized_request"] == trace["frozen_original"]["serialized_original_request"]
                       and actions[0]["request_hash"] == trace["frozen_original"]["original_request_hash"])
    return {"MALFORMED_GENERATION": malformed, "REJECTED_GENERATION": rejected,
            "BUDGET_EXHAUSTED": budget, "PROTOCOL_VALID_RECOVERY": protocol,
            "OBSERVATION_BEFORE_WRITE": observation, **costs}


def traced_recovery_facts(trace):
    """Compatibility helper for clean traces; costs require the V2 journal."""
    if trace["evaluator_only"]["evaluation"]["infrastructure_failure"]:
        raise AnalysisMeasurementBlocker("use derive_arm with explicit V2 infrastructure attribution")
    facts = _recovery_facts(trace, trace["measurement_evidence"], None)
    if trace["recovery_policy"] == "EXACT_REPLAY":
        for key in ("MALFORMED_GENERATION", "REJECTED_GENERATION", "BUDGET_EXHAUSTED", "OBSERVATION_BEFORE_WRITE"):
            facts[key] = None
    return facts


def analysis_infrastructure_failure(opportunity):
    """Retain raw classification separately; category B is behavioral evidence."""
    failure = opportunity["infrastructure_failure"]
    if failure is None:
        return None
    classification = failure["diagnostic"]["response_failure"]
    if (opportunity["policy"] == "LLM_REGENERATION" and classification is not None
        and classification["category"] == "MODEL_GENERATION_STRUCTURE"):
        return None
    return failure


def derive_arm(attempt, opportunity, trace, scenario):
    """One eligible opportunity, including nonactivated family/system failures."""
    record = opportunity_state(attempt, opportunity, trace, scenario)
    raw_failure = opportunity["infrastructure_failure"]
    infrastructure = analysis_infrastructure_failure(opportunity)
    measurement = opportunity["measurement_evidence"]
    facts = _recovery_facts(trace, measurement, infrastructure)
    replay = opportunity["policy"] == "EXACT_REPLAY"
    if replay:
        for key in ("MALFORMED_GENERATION", "REJECTED_GENERATION", "BUDGET_EXHAUSTED", "OBSERVATION_BEFORE_WRITE"):
            facts[key] = None
    if not opportunity["attempted"]:
        for key in ("MALFORMED_GENERATION", "REJECTED_GENERATION", "BUDGET_EXHAUSTED", "PROTOCOL_VALID_RECOVERY"):
            facts[key] = None
    record.update(schema_version="ticket-analysis-arm-v1", world=WORLD_CODES[opportunity["hidden_world"]],
                  attempted=opportunity["attempted"], raw_infrastructure_failure=raw_failure,
                  infrastructure_failure=infrastructure, measurement_evidence=measurement,
                  recovery_actions=None if trace is None else trace["recovery_actions"],
                  authoritative_terminal_state_available=record["terminal_state_snapshot"] is not None,
                  source_trace_id=None if trace is None else trace["identifiers"]["run_id"],
                  **facts)
    record["BEHAVIORALLY_EVALUABLE_ARM"] = int(
        record["authoritative_terminal_state_available"] and opportunity["attempted"]
        and infrastructure is None and attempt["family_system_failure"] is None)
    record["STATE_CORRECT_SENSITIVITY"] = (
        0 if infrastructure is not None and infrastructure["scope"] == "ARM" and infrastructure["policy_attributable"]
        else record["STATE_CORRECT"] if record["BEHAVIORALLY_EVALUABLE_ARM"] else None)
    return record


def derive_families(attempts, arms):
    by_slot = {}
    for arm in arms:
        by_slot.setdefault(arm["slot_index"], {})[(arm["world"], arm["policy"])] = arm
    families = []
    for attempt in attempts:
        if attempt["eligibility"]["outcome"] != "ELIGIBLE":
            continue
        family = {"schema_version": "ticket-analysis-family-v1", "slot_index": attempt["slot_index"],
                  "family_id": attempt["reserved_trial_family_id"], "activated_family_id": attempt["family_id"],
                  "replicate": attempt["replicate"], "scenario_id": attempt["scenario_id"], "stratum": attempt["stratum"]}
        for world in ("H0", "H1"):
            replay, regeneration = [by_slot[attempt["slot_index"]][world,p] for p in POLICIES]
            matched = all(a["BEHAVIORALLY_EVALUABLE_ARM"] == 1 for a in (replay,regeneration))
            family[world] = {"pair_id": replay["pair_id"], "replay_arm_id": replay["arm_id"],
                             "regeneration_arm_id": regeneration["arm_id"],
                             "primary": [replay["STATE_CORRECT"],regeneration["STATE_CORRECT"]] if matched else None,
                             "sensitivity": sensitivity_pair(replay,regeneration)}
        complete = all(family[w]["primary"] is not None for w in ("H0","H1"))
        family["primary_interaction_complete"] = complete
        family["primary_interaction_contribution"] = (
            family["H1"]["primary"][0] - family["H1"]["primary"][1]
            - family["H0"]["primary"][0] + family["H0"]["primary"][1] if complete else None)
        families.append(family)
    return families


def behavioral_rates(arms):
    flags = ("MISSING_MUTATION", "DUPLICATE_MUTATION", "WRONG_MUTATION",
             "MALFORMED_GENERATION", "REJECTED_GENERATION", "BUDGET_EXHAUSTED")
    results = {}
    for world in ("H0", "H1"):
        results[world] = {}
        for policy in POLICIES:
            opportunities = [a for a in arms if a["world"] == world and a["policy"] == policy]
            evaluable = [a for a in opportunities if a["BEHAVIORALLY_EVALUABLE_ARM"] == 1]
            protocol = [a for a in opportunities if a["PROTOCOL_VALID_RECOVERY"] is not None]
            results[world][policy] = {
                "failure_modes": {flag: None if policy == "EXACT_REPLAY" and flag in
                    ("MALFORMED_GENERATION", "REJECTED_GENERATION", "BUDGET_EXHAUSTED")
                    else rate(sum(a[flag] == 1 for a in evaluable),len(evaluable)) for flag in flags},
                "behaviorally_evaluable": rate(len(evaluable),len(opportunities)),
                "protocol_valid_recovery": rate(sum(a["PROTOCOL_VALID_RECOVERY"] == 1 for a in protocol),len(protocol)),
                "observation_before_write": None if policy == "EXACT_REPLAY" else
                    rate(sum(a["OBSERVATION_BEFORE_WRITE"] == 1 for a in evaluable),len(evaluable)),
            }
    return results


def sensitivity_pair(replay, regeneration):
    """Use established evaluability and attribution; missing outcomes stay null."""
    def score(arm):
        if arm.get("family_system_failure") is not None:
            return None
        failure = arm["infrastructure_failure"]
        if failure is not None:
            if failure["scope"] == "ARM" and failure["policy_attributable"]:
                return 0
            return None
        return arm["STATE_CORRECT"] if arm["BEHAVIORALLY_EVALUABLE_ARM"] == 1 else None
    values = [score(replay), score(regeneration)]
    return values if all(x is not None for x in values) else None


def analysis_original_generation_infrastructure(attempt):
    """Separate V2 returned-model malformation from raw infrastructure labels."""
    failure = attempt["original_generation_infrastructure"]
    if failure is None:
        return False
    classification = failure.get("diagnostic", {}).get("response_failure")
    return not (
        classification is not None
        and classification.get("evidence_version") == "model-response-failure-v2"
        and classification["category"] == "MODEL_GENERATION_STRUCTURE"
    )


def operational_rates(attempts, derived_arms=None):
    """Frozen ledger denominators with structured analysis failure classification."""
    records = tuple(attempts)
    if len(records) != 160 or [r["slot_index"] for r in records] != list(range(160)):
        raise ValueError("operational denominators require the entire 160-slot ledger")
    eligible = [r for r in records if r["eligibility"]["outcome"] == "ELIGIBLE"]
    recovery = {}
    for world in ("NOT_EXECUTED", "EXECUTED_ACK_LOST"):
        recovery[world] = {}
        for policy in ("EXACT_REPLAY", "LLM_REGENERATION"):
            arms = [a for r in eligible for a in r["arm_opportunities"]
                    if a["hidden_world"] == world and a["policy"] == policy]
            if derived_arms is not None:
                arms = [a for a in derived_arms if a["hidden_world"] == world and a["policy"] == policy]
            numerator = sum(a["infrastructure_failure"] is not None
                            and a["infrastructure_failure"]["scope"] == "ARM"
                            and a["infrastructure_failure"]["policy_attributable"] for a in arms)
            recovery[world][policy] = rate(numerator,len(arms))
    return {
        "eligibility": rate(len(eligible),160),
        "original_generation_infrastructure_failure": rate(sum(analysis_original_generation_infrastructure(r) for r in records),160),
        "recovery_infrastructure_failure": recovery,
        "pre_arm_system_family_failures": sum(r["family_system_failure"] is not None for r in records),
    }


def _analysis_validators(*, study1b: bool = False):
    registry = Registry()
    schemas = {}
    # Every reference is resolved locally. No network retrieval is installed.
    for path in sorted(PROTOCOL_ROOT.glob("*schema*.json")):
        schema = json.loads(path.read_bytes())
        identifier = schema.get("$id", "https://retry-semantics.local/schemas/" + path.name)
        registry = registry.with_resource(identifier, Resource.from_contents(schema))
        schemas[path.name] = schema
    validators = {}
    for name in ("analysis_provenance_schema_v1.json", "analysis_arm_schema_v1.json",
                 "analysis_family_schema_v1.json", "analysis_results_schema_v1.json"):
        selected = ("study1b_analysis_provenance_schema_v1.json"
                    if study1b and name == "analysis_provenance_schema_v1.json" else name)
        jsonschema.Draft202012Validator.check_schema(schemas[selected])
        validators[name] = jsonschema.Draft202012Validator(schemas[selected],registry=registry)
    return validators


def extract_ticket_analysis(source_bundle: Path, output_directory: Path, *, study1b: bool = False):
    """Validate first, derive and schema-check in memory, publish four files once."""
    source = Path(source_bundle).resolve()
    output = Path(output_directory).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("analysis output must be separate from the raw bundle")
    if any(part.endswith(".in-progress") for part in (*Path(source_bundle).parts, *source.parts)):
        raise PaperCollectionError("in-progress paper evidence cannot be analyzed")
    try:
        validate_paper_collection_bundle(source)
    except jsonschema.ValidationError as exc:
        raise PaperCollectionError("completed bundle fails frozen evidence schema validation") from exc
    source_bytes = {name: (source/name).read_bytes() for name in SOURCE_FILES}
    source_hashes = {name:sha256_hex(data) for name,data in source_bytes.items()}
    # Validate the captured input as well as the initial boundary: a bundle
    # changed between the first validation and the reads is never analyzed.
    try:
        validate_paper_collection_bundle(source)
    except jsonschema.ValidationError as exc:
        raise PaperCollectionError("completed bundle fails frozen evidence schema validation") from exc
    if source_hashes != {name:sha256_hex((source/name).read_bytes()) for name in SOURCE_FILES}:
        raise PaperCollectionError("source bundle changed during input validation")
    manifest = json.loads(source_bytes["manifest.json"])
    metadata = json.loads(source_bytes["run_metadata.json"])
    expected_id = STUDY1B_MANIFEST_ID if study1b else MANIFEST_ID
    expected_hash = STUDY1B_MANIFEST_SHA256 if study1b else MANIFEST_SHA256
    expected_bytes = STUDY1B_MANIFEST_BYTES if study1b else 240807
    if (len(source_bytes["manifest.json"]) != expected_bytes
        or sha256_hex(source_bytes["manifest.json"]) != expected_hash
        or manifest["manifest_id"] != expected_id):
        raise PaperCollectionError("not the prospectively frozen Ticket paper manifest")
    if study1b:
        from retry_semantics.experiment.fireworks_paper_study1b import build_study1b_manifest
        if source_bytes["manifest.json"] != build_study1b_manifest().canonical_bytes:
            raise PaperCollectionError("Study1B manifest differs from the V4.1 frozen builder")
    if metadata.get("collection_evidence_revision") != EVIDENCE_REVISION:
        raise PaperCollectionError("final Ticket analysis requires paper-collection-evidence-v2")
    if output.exists():
        raise FileExistsError("analysis output directory already exists")
    plan_bytes = (PROTOCOL_ROOT/PLAN_NAME).read_bytes()
    if sha256_hex(plan_bytes) != PLAN_SHA256:
        raise AnalysisMeasurementBlocker("frozen analysis-plan hash mismatch")
    attempts = [json.loads(line) for line in source_bytes["scheduled_attempts.jsonl"].splitlines()]
    traces = {t["identifiers"]["arm_id"]: t for t in
              (json.loads(line) for line in source_bytes["arm_traces.jsonl"].splitlines())}
    arms = [derive_arm(attempt, opportunity, traces.get(opportunity["arm_id"]), manifest["entries"][attempt["slot_index"]]["scenario"])
            for attempt in attempts if attempt["eligibility"]["outcome"] == "ELIGIBLE"
            for opportunity in sorted(attempt["arm_opportunities"],key=lambda a:(WORLD_CODES[a["hidden_world"]],a["policy"]))]
    families = derive_families(attempts, arms)
    statistics = summarize_families(families)
    statistics.pop("schema_version")
    statistics.pop("status")
    results = {"schema_version": "ticket-analysis-results-v1", "analysis_version": ANALYSIS_VERSION,
               "status": "COMPLETED_VALIDATED_V2_ANALYSIS", **statistics,
               "operational_rates": operational_rates(attempts,arms),
               "behavioral_rates": behavioral_rates(arms)}
    artifacts = {"analysis_arms.jsonl": b"".join(canonical_json_bytes(a)+b"\n" for a in arms),
                 "analysis_families.jsonl": b"".join(canonical_json_bytes(f)+b"\n" for f in families),
                 "analysis_results.json": canonical_json_bytes(results)}
    implementation_paths = [Path(__file__),Path(__file__).with_name("analysis_statistics.py"),
                            Path(__file__).parents[1]/"serialization.py"]
    implementation_paths += sorted(PROTOCOL_ROOT.glob("analysis*schema_v1.json"))
    if study1b:
        implementation_paths.append(PROTOCOL_ROOT / "study1b_analysis_provenance_schema_v1.json")
    implementation_hashes = {p.name:sha256_hex(p.read_bytes()) for p in implementation_paths}
    provenance = {"schema_version": "ticket-analysis-provenance-v1", "analysis_version": ANALYSIS_VERSION,
                  "extractor_version": EXTRACTOR_VERSION,
                  "extractor_implementation_sha256": sha256_hex(canonical_json_bytes(implementation_hashes)),
                  "extractor_component_sha256": implementation_hashes,
                  "source_manifest_id": expected_id, "source_manifest_sha256": expected_hash,
                  "source_paper_experiment_revision": metadata["paper_experiment_revision"],
                  "source_execution_semantics_revision": metadata["execution_semantics_revision"],
                  "source_collection_evidence_revision": metadata["collection_evidence_revision"],
                  "source_run_git_commit": metadata["git_commit"], "source_run_timestamp": metadata["timestamp"],
                  "source_bundle_file_sha256": source_hashes,
                  "analysis_plan": {"identity": "primary-create-v1.3-analysis-plan-v1.0", "path": "research/protocol/"+PLAN_NAME, "sha256": PLAN_SHA256},
                  "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_replicates": BOOTSTRAP_REPLICATES,
                  "derived_artifact_sha256": {name:sha256_hex(data) for name,data in artifacts.items()}}
    validators = _analysis_validators(study1b=True) if study1b else _analysis_validators()
    validators["analysis_provenance_schema_v1.json"].validate(provenance)
    validators["analysis_results_schema_v1.json"].validate(results)
    for arm in arms:
        validators["analysis_arm_schema_v1.json"].validate(arm)
    for family in families:
        validators["analysis_family_schema_v1.json"].validate(family)
    artifacts["analysis_provenance.json"] = canonical_json_bytes(provenance)
    if source_hashes != {name:sha256_hex((source/name).read_bytes()) for name in SOURCE_FILES}:
        raise PaperCollectionError("source bundle changed during analysis")
    output.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="."+output.name+"-",suffix=".in-progress",dir=output.parent))
    try:
        for name,data in sorted(artifacts.items()):
            with (staging/name).open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        if output.exists():
            raise FileExistsError("analysis output directory already exists")
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle",type=Path)
    parser.add_argument("output_directory",type=Path)
    parser.add_argument("--study1b", action="store_true", help="Require the exact V4.1 Study1B manifest")
    args = parser.parse_args()
    extract_ticket_analysis(args.source_bundle,args.output_directory,study1b=args.study1b)


if __name__ == "__main__":
    main()

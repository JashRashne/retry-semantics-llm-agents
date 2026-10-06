"""Post-recovery scoring and write-once evidence, outside the decision boundary.

One-arm runners accept already qualified construction evidence. There is no
live collection command: provisioning/authorization is a later audited phase.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from retry_semantics.baselines.adapters import github_recovery, sheets_recovery, ticket_recovery
from retry_semantics.environments.ticket import SourceStage, TicketEnvironment, evaluate_ticket_state
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.sheets_paper_adapter import classify_experimental_get
from retry_semantics.study2.sheets_paper_readiness import check_grid


def record(*, study: str, family_id: str, trial_id: str, hidden_world: str,
           adapter, evaluator_state: object, correct: bool | None,
           matching: int | None, unintended: int | None, reason: str | None,
           final_http_reads: int = 0, counts_complete: bool = True) -> dict:
    if hidden_world not in ("H0", "H1"):
        raise ValueError("invalid harness construction label")
    recovery = asdict(adapter.recovery)
    raw = recovery.pop("observation")
    recovery["observation"] = None if raw is None else json.loads(raw)
    return {
        "schema": "post-feedback-no-model-arm-v1", "study": study,
        "original_family_id": family_id, "original_trial_id": trial_id,
        "hidden_world": hidden_world, **recovery,
        "stored_request_identity_sha256": adapter.stored_request_identity_sha256,
        "recovery_create_attempted": adapter.recovery.write_count == 1,
        "decision_http_reads": adapter.decision_http_reads,
        "final_evaluator_http_reads": final_http_reads,
        "final_evaluator_state": json.loads(json.dumps(evaluator_state)),
        "matching_intended_effects": matching,
        "unintended_attributable_effects": unintended, "effect_counts_complete": counts_complete,
        "final_correctness": correct, "unknown_unscorable": correct is None,
        "unknown_reason": reason if correct is None else None,
    }


def run_ticket_arm(*, study: str, family_id: str, trial_id: str, hidden_world: str,
                   starting_snapshot: bytes, original, arm_id: str) -> dict:
    """Clone a qualified pre-recovery world; never reuse an old final snapshot."""
    environment = TicketEnvironment.clone_from_snapshot(starting_snapshot)
    state = environment.state
    if hidden_world == "H0":
        if state.tickets or state.mutation_events:
            raise ValueError("H0 original must not be dispatched")
    elif hidden_world == "H1":
        if (len(state.tickets) != 1 or len(state.mutation_events) != 1
                or state.mutation_events[0].source_stage is not SourceStage.ORIGINAL
                or state.mutation_events[0].serialized_request != original.serialized_request):
            raise ValueError("H1 must contain exactly the stored original effect")
    else:
        raise ValueError("invalid constructor")
    adapter = ticket_recovery(environment, original, arm_id=arm_id)
    # The only evaluator invocation is after recovery has completely returned.
    args = json.loads(original.serialized_request)["arguments"]
    evaluation = evaluate_ticket_state(environment.state, **args)
    final = {"snapshot": json.loads(environment.snapshot_bytes()),
             "snapshot_sha256": environment.snapshot_hash(), "evaluation": evaluation.as_dict()}
    return record(study=study, family_id=family_id, trial_id=trial_id,
        hidden_world=hidden_world, adapter=adapter, evaluator_state=final,
        correct=evaluation.correct, matching=evaluation.matching_ticket_count,
        unintended=evaluation.unintended_ticket_count, reason=None)


def run_github_arm(*, manifest, family, arm, original, api_version, fetch, dispatch,
                   clock, wait_until, baseline_clear: bool, isolation_proven: bool,
                   h1_certificate=None) -> dict:
    """Validate constructor certificate, recover, then frozen scheduled OBS-1."""
    world = arm["hidden_world"]
    if not baseline_clear or not isolation_proven:
        raise ValueError("unqualified provider construction; do not enter policy")
    known = ()
    if world == "H1":
        if type(h1_certificate) is not gh.H1Certificate:
            raise ValueError("missing H1 certificate")
        checked = certify_github_constructor(manifest, family, arm, original,
            h1_certificate.acknowledgement, h1_certificate.constructor_censuses)
        if checked != h1_certificate:
            raise ValueError("H1 certificate changed")
        known = (checked.acknowledged_issue_number,)
    elif world != "H0" or h1_certificate is not None:
        raise ValueError("invalid constructor")
    adapter = github_recovery(manifest=manifest, arm=arm, original=original,
        api_version=api_version, fetch=fetch, dispatch=dispatch, clock=clock)
    anchor = clock()
    def evaluator_fetch(url):
        try:
            return fetch(url)
        except Exception as exc:
            # An evaluator transport exception is incomplete evidence, not an
            # invented missing/success outcome. No additional request here.
            from retry_semantics.study2.github_adapter import HTTPResponse
            return HTTPResponse(0, (), b"", type(exc).__name__)
    rounds = gh.run_scheduled_censuses(manifest, arm, api_version=api_version,
        anchor=anchor, clock=clock, wait_until=wait_until, fetch=evaluator_fetch,
        semantic_target=family["target_semantic_m"])
    verdict = gh.evaluate_census(arm, family["target_semantic_m"],
        tuple(r.census for r in rounds), known + adapter.acknowledged_resource_ids,
        isolation_proven=isolation_proven, baseline_clear=baseline_clear)
    target = family["target_semantic_m"]
    attributed = {number: (title, body[:-len(arm["suffix"])])
        for r in rounds for number, title, body in r.census.issues
        if body.endswith(arm["suffix"])}
    intended = (target["title"], target["body"])
    return record(study="GitHub", family_id=family["family_id"], trial_id=arm["arm_id"],
        hidden_world=world, adapter=adapter,
        evaluator_state={"verdict": verdict, "rounds": [asdict(r) for r in rounds]},
        correct=None if verdict["state_correct"] is None else bool(verdict["state_correct"]),
        matching=sum(v == intended for v in attributed.values()),
        unintended=sum(v != intended for v in attributed.values()), reason=verdict["reason"],
        final_http_reads=sum(r.census.requests for r in rounds),
        counts_complete=bool(rounds and rounds[-1].census.complete))


def run_sheets_arm(*, manifest, family, arm, original, fetch, dispatch, clock,
                   baseline_clear: bool, isolation_proven: bool, h1_certificate=None) -> dict:
    from retry_semantics.study2.sheets_paper_runner import (
        H1ConstructorCertification, certify_h1_constructor)
    world = arm["hidden_world"]
    if not baseline_clear or not isolation_proven:
        raise ValueError("unqualified provider construction; do not enter policy")
    if world == "H1":
        if type(h1_certificate) is not H1ConstructorCertification:
            raise ValueError("missing H1 certificate")
        checked = certify_h1_constructor(manifest, family, arm, original,
            h1_certificate.acknowledgement, h1_certificate.read_capture)
        if checked != h1_certificate:
            raise ValueError("H1 certificate changed")
    elif world != "H0" or h1_certificate is not None:
        raise ValueError("invalid constructor")
    adapter = sheets_recovery(manifest=manifest, arm=arm, original=original,
                              fetch=fetch, dispatch=dispatch)
    # Exactly one final GET, independently called after policy termination.
    anchor = clock()
    try:
        response = fetch()
    except Exception as exc:
        from retry_semantics.study2.sheets_paper_adapter import DispatchFacts
        from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
        response = PaperHTTPResult(DispatchFacts(), b"", type(exc).__name__)
    semantic = family["target_semantic_m"]
    intended = (semantic["item"], semantic["detail"])
    verdict = "INCOMPLETE"
    matching = unintended = None
    if clock() - anchor <= 40 and response.transport_error is None:
        verdict = classify_experimental_get(manifest, arm, response.facts.http_status,
            response.body, intended=intended, authority_qualified=True)
        if verdict not in ("INCOMPLETE", "INCONCLUSIVE"):
            grid = check_grid(manifest, arm, response.facts.http_status,
                              response.body, intended=intended)
            matching, unintended = len(grid.matching_intended_rows), len(grid.attributable_unintended_rows)
            floor = max(adapter.observed_row_floor,
                        adapter.acknowledged_writes + int(world == "H1"))
            if len(grid.entered_rows) < floor:
                verdict = "CAUSAL_LEDGER_CONTRADICTION"
    correct = (verdict == "EXACTLY_ONE") if verdict in (
        "EXACTLY_ONE", "MISSING", "DUPLICATE", "EXTRA_UNINTENDED_MUTATION") else None
    return record(study="Sheets valid replication", family_id=family["family_id"],
        trial_id=arm["arm_id"], hidden_world=world, adapter=adapter,
        evaluator_state={"verdict": verdict, "status": response.facts.http_status,
                         "transport_error": response.transport_error,
                         "body_sha256": sha256_hex(response.body)},
        correct=correct, matching=matching, unintended=unintended, reason=verdict,
        final_http_reads=1, counts_complete=matching is not None)


def write_once(directory: Path, name: str, value: dict) -> None:
    """Create evidence files exclusively; caller owns an isolated new directory."""
    if Path(name).name != name or directory.is_symlink():
        raise ValueError("unsafe evidence path")
    directory.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(value)
    with (directory / name).open("xb") as handle:
        handle.write(raw)
        handle.flush()
        import os
        os.fsync(handle.fileno())


def certify_github_constructor(manifest, family, arm, original, acknowledgement, rounds):
    """Same H1 certification as frozen runtime, with a newly bound arm.

    Frozen expected_original() demands membership in the old four-arm manifest.
    Use its existing serializer against the pinned repository scope instead;
    none of this certification evidence enters the recovery decision.
    """
    version = dict(original.headers)["X-GitHub-Api-Version"]
    expected = gh.serialize_create(manifest, arm, **family["target_semantic_m"],
                                  api_base="https://api.github.com", api_version=version)
    number = gh.validate_create_ack(original, acknowledgement, version)
    if (arm["hidden_world"] != "H1" or original != expected or number is None
            or not 1 <= len(rounds) <= 2
            or tuple(r.offset_seconds for r in rounds) != gh.OBSERVATION_STARTS[:len(rounds)]):
        raise ValueError("H1 constructor evidence incomplete")
    final = rounds[-1].census
    target = family["target_semantic_m"]
    if (not final.complete or gh._constructor_matches(final, arm, target) != (number,)
            or (len(rounds) == 2 and rounds[0].census.complete
                and gh._constructor_matches(rounds[0].census, arm, target))):
        raise ValueError("H1 exact-one issue not certified")
    return gh.H1Certificate(original.sha256, number, acknowledgement, rounds, arm["arm_id"])


def unentered_record(*, study: str, family_id: str, trial_id: str, hidden_world: str,
                     reason: str) -> dict:
    """Retain scheduled construction failures/unrun arms without policy outcomes."""
    from retry_semantics.baselines.no_model import POLICY
    if hidden_world not in ("H0", "H1") or not reason:
        raise ValueError("invalid scheduled loss")
    return {"schema": "post-feedback-no-model-arm-v1", "study": study,
            "original_family_id": family_id, "original_trial_id": trial_id,
            "hidden_world": hidden_world, "policy": POLICY, "list_attempted": False,
            "list_outcome": "NOT_ATTEMPTED", "intended_visible": None,
            "decision": None, "recovery_create_attempted": False, "create_outcome": None,
            "final_evaluator_state": None, "matching_intended_effects": None,
            "unintended_attributable_effects": None, "effect_counts_complete": False,
            "final_correctness": None, "unknown_unscorable": True, "unknown_reason": reason,
            "read_count": 0, "write_count": 0, "model_call_count": 0,
            "decision_http_reads": 0, "final_evaluator_http_reads": 0}

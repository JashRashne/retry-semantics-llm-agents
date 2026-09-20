"""DRAFT explicit operator commands; bearer stays in one resident process."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import resource
import shlex
import sys
import time

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase2_read as transport
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase3_operator as inherited
from retry_semantics.study2 import sheets_phase4_control as control
from retry_semantics.study2 import sheets_phase4_setup as setup


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise p2.Refused()

    @credentials.secret_safe
    def parse_args(self, *args, **kwargs):
        return super().parse_args(*args, **kwargs)


def local_inputs(config):
    return dict(config=config, review=p3.load_json(config.path("client-review.json")),
                attestation=p3.load_json(config.path("startup.json")),
                offline_pin=p3.load_json(config.path("offline-pin.json")),
                pin=p3.load_json(config.path("read-pin.json")),
                descriptor=p3.load_json(config.path("fixture.json")),
                conditions=inherited._typed(p3.load_json(config.path("conditions.json")), p3.LocalConditions))


def post_inputs(config, token, metadata):
    return {**local_inputs(config), "token": token, "metadata": metadata, "now": time.time()}


def phase4_receipt(config, pin, attestation, authorization, receipt):
    return {"schema": "sheets-phase4-issuance-receipt-v1", "engineering_only": True,
            "phase4_runtime_sha256": control.hash_public(pin),
            "phase4_source_sha256": control.hash_public(control.source_projection()),
            "startup_sha256": control.hash_public(attestation),
            "authorization_sha256": p2.authorization_hash(authorization),
            "phase3_receipt_sha256": control.hash_public(receipt),
            "authorization_id": config.authorization_id, "capability": "LIVE_READ_GO"}


def inspect_artifacts(config, review):
    control.storage_check(config)
    control.validate_review(review)
    output = {"network": "not-performed", "operator": config.projection(), "client_review": review,
              "present": [n for n in control.FILES if config.path(n).exists()], "next_action": "review-no-retry"}
    if config.path("acquisition.json").exists():
        output["acquisition"] = inherited._metadata(p3.load_json(config.path("acquisition.json"))).projection()
    if config.path("create-intent.json").exists():
        p2.require(p3.load_json(config.path("create-intent.json")) == setup.create_intent(config, review))
        output["create_intent"] = setup.create_intent(config, review)
        output["create_state"] = "UNRESOLVED_NO_RETRY"
        if config.path("create-result.json").exists():
            value = p3.load_json(config.path("create-result.json"))
            if value.get("outcome") == "CREATE_RESPONSE_VALIDATED":
                output["create_result"] = setup.validate_create_result(value, config, review)
                output["create_state"] = "RESPONSE_VALIDATED_REVIEW_REQUIRED"
            else:
                expected = {"schema": "sheets-phase4-create-result-v1", "engineering_only": True,
                    "outcome": "CREATE_UNCERTAIN_RECONCILIATION_REQUIRED",
                    "intent_sha256": control.hash_public(setup.create_intent(config, review)),
                    "http_status": value.get("http_status"), "spreadsheet_id": None, "sheet_id": None,
                    "rows": None, "columns": None}
                p2.require(value == expected and (value["http_status"] is None or
                    type(value["http_status"]) is int and 100 <= value["http_status"] <= 599))
                output["create_result"] = expected
    if config.path("fixture.json").exists():
        descriptor = p3.load_json(config.path("fixture.json"))
        p3.parse_fixture_descriptor(descriptor)
        output["fixture"] = descriptor
    if config.path("authorization.json").exists():
        authorization = p3.parse_authorization(p3.load_json(config.path("authorization.json")))
        receipt = p3.load_json(config.path("phase3-receipt.json"))
        inputs = local_inputs(config)
        metadata = inherited._metadata(p3.load_json(config.path("acquisition.json")))
        control.check_setup_records(config, review, inputs["descriptor"], metadata)
        p2.require(inputs["pin"] == control.runtime_projection(config, review, inputs["descriptor"]))
        p2.require(inputs["offline_pin"] == control.runtime_projection(config, review))
        p2.require(inputs["attestation"] == control.startup(config, review, inputs["attestation"]["assumptions"]))
        p2.require(receipt == p3.issuance_receipt(authorization, config.runtime(), inputs["conditions"]))
        fourth = phase4_receipt(config, inputs["pin"], inputs["attestation"], authorization, receipt)
        p2.require(p3.load_json(config.path("phase4-receipt.json")) == fourth)
        output.update(authorization=p3.authorization_projection(authorization), phase3_receipt=receipt,
                      phase4_receipt=fourth, authorization_sha256=p2.authorization_hash(authorization))
        if config.path("read-intent.json").exists():
            p2.require(p3.load_json(config.path("read-intent.json")) == {
                "schema": "sheets-phase4-read-intent-v1", "authorization_sha256": p2.authorization_hash(authorization),
                "meaning": "one-wrapper-invocation-no-retry"})
            inspection = p3.RegistryInspection(config.runtime().registry_root)
            try:
                inspection.check_reserved(p3.parse_fixture_descriptor(inputs["descriptor"]))
                inspection.check_claim(authorization, p3.parse_fixture_descriptor(inputs["descriptor"]),
                    transport.runtime_hash(config.runtime().read_configuration()), transport.source_hash())
                evidence = transport.AttemptEvidence(inspection, p3.parse_fixture_descriptor(inputs["descriptor"]),
                    config.authorization_id, transport.runtime_hash(config.runtime().read_configuration()),
                    transport.source_hash(), reserve=False).records()
            finally:
                inspection.close()
            output["read_evidence"] = evidence
            output["qualification"] = "UNQUALIFIED_OR_INCOMPLETE_STOP"
            if config.path("result.json").exists():
                value = p3.load_json(config.path("result.json"))
                summary = transport.AttemptEvidence._decode_summary(value["summary"])
                baseline = "suitable-current-empty-grid" if summary.outcome is transport.Outcome.ZERO and summary.nonempty_rows == 0 else "unqualified-or-contaminated-retire-or-review"
                expected = {"schema": "sheets-phase3-first-read-result-v1", "engineering_only": True,
                    "authorization_hash": p2.authorization_hash(authorization), "summary": summary.projection(),
                    "baseline": baseline, "paper_observations": 0, "next_action": "stop-no-retry"}
                p2.require(value == expected and value["engineering_only"] is True
                    and type(value["paper_observations"]) is int)
                output["read_result"] = expected
                if ([record["stage"] for record in evidence[1:]] == [stage.value for stage in transport.Stage]
                    and evidence[-1]["summary"] == summary.projection() and summary.status == 200
                    and summary.outcome is transport.Outcome.ZERO and summary.nonempty_rows == 0):
                    output["qualification"] = "SUCCESS_PENDING_INDEPENDENT_REVIEW_AND_FREEZE"
    return output


@credentials.secret_safe
def issue(*, inputs, capability, fixture_hash, runtime_hash, source_hash, startup_hash,
          operator_confirmation, engineering_only):
    config = inputs["config"]
    p2.require(capability == "LIVE_READ_GO" and engineering_only is True
               and operator_confirmation == p1.CONFIRMATION)
    p2.require(control.post_setup_preflight(**inputs)["status"] == "PASS")
    p2.require(fixture_hash == inputs["descriptor"]["fixture_hash"]
               and runtime_hash == control.hash_public(inputs["pin"])
               and source_hash == control.hash_public(control.source_projection())
               and startup_hash == control.hash_public(inputs["attestation"]))
    inputs["token"].check_ready(now=time.time(), dispatch_budget_seconds=config.minimum_handoff_seconds)
    # Local issuance is also one-shot. Partial output is unusable, not repaired.
    p3.write_json(config.path("issue-intent.json"), {"schema": "sheets-phase4-issue-intent-v1",
        "authorization_id": config.authorization_id, "runtime_sha256": runtime_hash,
        "fixture_sha256": fixture_hash, "source_sha256": source_hash, "startup_sha256": startup_hash})
    now = time.time()
    authorization, receipt = p3.issue_authorization(descriptor=inputs["descriptor"],
        configuration=config.runtime(), expected_pin=inputs["pin"]["phase3"],
        expected_head=config.expected_head, conditions=inputs["conditions"], credential_metadata=inputs["metadata"],
        capability=capability, fixture_hash=fixture_hash,
        phase3_runtime_hash=p3.runtime_hash(config.runtime()), phase3_source_hash=p3.source_hash(),
        authorization_id=config.authorization_id, operator_alias=config.operator_alias, issued_at=now,
        expires_at=now + config.authorization_seconds, operator_confirmation=operator_confirmation,
        purpose=p1.PURPOSE, engineering_only=True, now=now)
    inputs["token"].check_ready(now=time.time(), dispatch_budget_seconds=config.minimum_handoff_seconds)
    p3.write_json(config.path("phase3-receipt.json"), receipt)
    p3.write_json(config.path("phase4-receipt.json"),
                  phase4_receipt(config, inputs["pin"], inputs["attestation"], authorization, receipt))
    p3.write_json(config.path("authorization.json"), p3.authorization_projection(authorization))
    return {"authorization_sha256": p2.authorization_hash(authorization), "next_action": "inspect-then-explicit-read"}


@credentials.secret_safe
def execute_read(*, inputs, execute_live_read, authorization, receipt, operational_receipt):
    p2.require(execute_live_read is True)
    config = inputs["config"]
    p2.require(type(inputs["token"]) is frozen.PreparedToken)
    p2.require(inputs["offline_pin"] == control.runtime_projection(config, inputs["review"])
               and inputs["pin"] == control.runtime_projection(config, inputs["review"], inputs["descriptor"])
               and inputs["attestation"] == control.startup(config, inputs["review"], inputs["attestation"]["assumptions"]))
    control.check_setup_records(config, inputs["review"], inputs["descriptor"], inputs["metadata"])
    p2.require(authorization.authorization_id == config.authorization_id
               and authorization.expires_at - authorization.authorized_at == config.authorization_seconds)
    p2.require(operational_receipt == phase4_receipt(config, inputs["pin"], inputs["attestation"], authorization, receipt))
    expected_intent = {"schema": "sheets-phase4-issue-intent-v1", "authorization_id": config.authorization_id,
        "runtime_sha256": control.hash_public(inputs["pin"]), "fixture_sha256": inputs["descriptor"]["fixture_hash"],
        "source_sha256": control.hash_public(control.source_projection()), "startup_sha256": control.hash_public(inputs["attestation"])}
    p2.require(p3.load_json(config.path("issue-intent.json")) == expected_intent)
    p2.require(inputs["token"].expires_at - time.time() > config.minimum_handoff_seconds
               + inputs["token"].clock_uncertainty_seconds)
    p3.write_json(config.path("read-intent.json"), {"schema": "sheets-phase4-read-intent-v1",
        "authorization_sha256": p2.authorization_hash(authorization), "meaning": "one-wrapper-invocation-no-retry"})
    # Only this frozen wrapper can activate the read; no setup/preparer import
    # or callback is supplied to it, no generic network client or fallback.
    result = inherited.execute_read(descriptor=inputs["descriptor"], configuration=config.runtime(),
        expected_pin=inputs["pin"]["phase3"], expected_head=config.expected_head,
        conditions=inputs["conditions"], token=inputs["token"], metadata=inputs["metadata"],
        authorization=authorization, receipt=receipt, execute_live_read=True)
    p2.require(inputs["pin"] == control.runtime_projection(config, inputs["review"], inputs["descriptor"]))
    p3.write_json(config.path("result.json"), result)
    return result


def session_parser():
    parser = SafeParser()
    subs = parser.add_subparsers(dest="action", required=True)
    provision = subs.add_parser("provision")
    provision.add_argument("--execute-provisioning", action="store_true")
    provision.add_argument("--operator-confirmation", required=True)
    review = subs.add_parser("review-provisioning")
    review.add_argument("--operator-confirmation", required=True)
    review.add_argument("--isolated", action="store_true")
    review.add_argument("--no-writers", action="store_true")
    subs.add_parser("reserve-and-descriptor")
    conditions = subs.add_parser("attest-post-setup")
    conditions.add_argument("--provisioning-reviewed", action="store_true", required=True)
    subs.add_parser("post-setup-preflight")
    subs.add_parser("bindings")
    issue_parser = subs.add_parser("issue")
    for name in ("capability", "fixture-hash", "runtime-hash", "source-hash", "startup-hash", "operator-confirmation"):
        issue_parser.add_argument("--" + name, required=True)
    issue_parser.add_argument("--engineering-only", action="store_true")
    read = subs.add_parser("read")
    read.add_argument("--execute-live-read", action="store_true")
    read.add_argument("--token-input", choices=("resident-memory",), required=True)
    for name in ("fixture", "metadata", "authorization", "receipt", "operational-receipt", "pin", "configuration"):
        read.add_argument("--" + name, type=Path, required=True)
    subs.add_parser("stop")
    return parser


def dispatch(args, config, review, token, metadata):
    # Recheck the same startup/pin on EACH operator action after acquisition.
    attestation = p3.load_json(config.path("startup.json"))
    p2.require(attestation == control.startup(config, review, attestation["assumptions"]))
    p2.require(p3.load_json(config.path("offline-pin.json")) == control.runtime_projection(config, review))
    if args.action == "provision":
        result = setup.provision(config, review, token, metadata, execute_provisioning=args.execute_provisioning,
                                 operator_confirmation=args.operator_confirmation)
        p2.require(result["outcome"] == "CREATE_RESPONSE_VALIDATED")
        return result
    if args.action == "review-provisioning":
        record = setup.review_provisioning(config, review, operator_confirmation=args.operator_confirmation,
                                          isolated=args.isolated, no_writers=args.no_writers)
        return {"provisioning_sha256": record.evidence_hash}
    if args.action == "reserve-and-descriptor":
        record = inherited._typed(p3.load_json(config.path("provisioning.json")), p3.ProvisioningRecord)
        descriptor = p3.fixture_descriptor(record)
        with p2.LocalRegistry(Path(config.runtime().registry_root)) as registry:
            registry.reserve(record.fixture())
        p3.write_json(config.path("fixture.json"), descriptor)
        p3.write_json(config.path("read-pin.json"), control.runtime_projection(config, review, descriptor))
        return {"fixture_sha256": descriptor["fixture_hash"]}
    if args.action == "attest-post-setup":
        p2.require(args.provisioning_reviewed is True)
        p3.write_json(config.path("conditions.json"), asdict(p3.LocalConditions(True, True, True, True, True)))
        return {"network": "not-performed"}
    inputs = post_inputs(config, token, metadata)
    if args.action == "post-setup-preflight":
        return control.post_setup_preflight(**inputs)
    if args.action == "bindings":
        return {"fixture_hash": inputs["descriptor"]["fixture_hash"], "runtime_hash": control.hash_public(inputs["pin"]),
                "source_hash": control.hash_public(control.source_projection()), "startup_hash": control.hash_public(inputs["attestation"])}
    if args.action == "issue":
        return issue(inputs=inputs, **{n: getattr(args, n) for n in ("capability", "fixture_hash", "runtime_hash",
                     "source_hash", "startup_hash", "operator_confirmation", "engineering_only")})
    p2.require(args.action == "read" and args.token_input == "resident-memory")
    for argument, name in (("fixture", "fixture.json"), ("metadata", "acquisition.json"),
        ("authorization", "authorization.json"), ("receipt", "phase3-receipt.json"),
        ("operational_receipt", "phase4-receipt.json"), ("pin", "read-pin.json"), ("configuration", "operator.json")):
        p2.require(getattr(args, argument) == config.path(name))
    p2.require(p3.load_json(args.configuration) == config.projection())
    return execute_read(inputs=inputs, execute_live_read=args.execute_live_read,
        authorization=p3.parse_authorization(p3.load_json(args.authorization)),
        receipt=p3.load_json(args.receipt), operational_receipt=p3.load_json(args.operational_receipt))


@credentials.secret_safe
def resident_session(config, client_path, *, execute_oauth, operator_confirmation):
    p2.require(sys.stdin.isatty() and sys.stdout.isatty())
    # Prevent conventional core files in this process and inherited read worker.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    review = p3.load_json(config.path("client-review.json"))
    token, metadata = setup.acquire(config, review, p3.load_json(config.path("startup.json")),
        p3.load_json(config.path("offline-pin.json")), client_path, execute_oauth=execute_oauth,
        operator_confirmation=operator_confirmation, present_url=lambda url: print(url, flush=True))
    try:
        while True:
            line = input("phase4> ")
            args = session_parser().parse_args(shlex.split(line))
            if args.action == "stop":
                return 0
            result = dispatch(args, config, review, token, metadata)
            print(canonical_json_bytes(result).decode("ascii"), flush=True)
            if result.get("status") == "BLOCKED" or args.action == "read":
                return 2 if result.get("status") == "BLOCKED" else 0
    finally:
        token = metadata = None  # Best effort; CPython is not a secure heap.


def main(argv=None):
    parser = SafeParser(description="DRAFT Phase 4; no command grants setup permission")
    subs = parser.add_subparsers(dest="command", required=True)
    review = subs.add_parser("client-review")
    review.add_argument("--client", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    supersede = subs.add_parser("supersede-prelive")
    supersede.add_argument("--configuration", type=Path, required=True)
    supersede.add_argument("--new-expected-head", required=True)
    supersede.add_argument("--operator-confirmation", required=True)
    new_attempt = subs.add_parser("new-acquisition-attempt")
    new_attempt.add_argument("--configuration", type=Path, required=True)
    new_attempt.add_argument("--new-expected-head", required=True)
    new_attempt.add_argument("--operator-confirmation", required=True)
    for name in ("startup", "phase4-preflight", "session", "inspect", "recover"):
        sub = subs.add_parser(name)
        sub.add_argument("--configuration", type=Path, required=True)
        if name == "startup":
            for assumption in control.ASSUMPTIONS:
                sub.add_argument("--" + assumption.replace("_", "-"), action="store_true", required=True)
        if name == "session":
            sub.add_argument("--client", type=Path, required=True)
            sub.add_argument("--execute-oauth", action="store_true")
            sub.add_argument("--operator-confirmation", required=True)
    try:
        args = parser.parse_args(argv)
        p3.environment_gate()
        if args.command == "client-review":
            value = setup.review_client(args.client)
            p3.write_json(args.output, value)
            result = {"public_sha256": value["public_sha256"], "network": "not-performed"}
        elif args.command == "supersede-prelive":
            config = inherited._typed(p3.load_json(args.configuration), control.OperatorConfiguration)
            p2.require(args.configuration == config.path("operator.json"))
            result = control.supersede_prelive(config, args.new_expected_head, args.operator_confirmation)
        elif args.command == "new-acquisition-attempt":
            config = inherited._typed(p3.load_json(args.configuration), control.OperatorConfiguration)
            p2.require(args.configuration == config.path("operator.json"))
            result = control.new_acquisition_attempt(config, args.new_expected_head,
                                                     args.operator_confirmation)
        else:
            config = inherited._typed(p3.load_json(args.configuration), control.OperatorConfiguration)
            p2.require(args.configuration == config.path("operator.json"))
            review = p3.load_json(config.path("client-review.json"))
            if args.command == "inspect":
                result = inspect_artifacts(config, review)
            elif args.command == "recover":
                result = p3.inspect_recovery(configuration=config.runtime(), descriptor=p3.load_json(config.path("fixture.json")),
                    authorization=p3.parse_authorization(p3.load_json(config.path("authorization.json"))))
                result["phase4_issuance_intent_present"] = config.path("issue-intent.json").exists()
                result["phase4_read_intent_present"] = config.path("read-intent.json").exists()
                result["phase4_permission"] = "not-renewed-no-retry"
            elif args.command == "startup":
                value = control.startup(config, review, {n: getattr(args, n) for n in control.ASSUMPTIONS})
                p3.write_json(config.path("startup.json"), value)
                p3.write_json(config.path("offline-pin.json"), control.runtime_projection(config, review))
                result = {"network": "not-performed", "startup_sha256": control.hash_public(value)}
            elif args.command == "phase4-preflight":
                result = control.offline_preflight(config, review, p3.load_json(config.path("startup.json")),
                                                  p3.load_json(config.path("offline-pin.json")))
            else:
                return resident_session(config, args.client, execute_oauth=args.execute_oauth,
                                        operator_confirmation=args.operator_confirmation)
        print(canonical_json_bytes(result).decode("ascii"))
        return 2 if result.get("status") == "BLOCKED" else 0
    except (Exception, SystemExit):
        pass
    print('{"schema":"sheets-phase4-refusal-v1","status":"BLOCKED","live_go":"CLOSED","recovery":"stop-review-no-retry"}')
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

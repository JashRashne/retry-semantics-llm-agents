"""DRAFT narrow operator commands. Default deny; no acquisition in this module.

Only `read --execute-live-read` with all explicit bound inputs can invoke the
frozen Phase 2 adapter. Tokens come from an inherited pipe, never argv/files.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import functools
import os
from pathlib import Path
import stat
import time

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase2_read as read
from retry_semantics.study2 import sheets_phase3_control as control
from retry_semantics.study2.sheets_phase3_credentials import AcquisitionMetadata

PROCEDURE = (
    "Review hostile audit and qualify explicit local runtime/trust/storage/clock conditions.",
    "Separately authorize provisioning: dedicated account, reviewed installed client, exact drive.file; same-app spreadsheets.create only in separately audited setup tooling.",
    "Review positive provisioning record; build real descriptor; reserve fixture once in one persistent private POSIX registry.",
    "Select justified budget/bounds/clock values; inspect local inventory and pin candidate; verify clean audited source identity.",
    "Separately authorize desktop OAuth preparation; manually open the generated URL, use loopback callback; keep exported token in memory/anonymous pipe; persist only metadata.",
    "Run local preflight with descriptor, configuration, pin, conditions and metadata. No DNS/socket/OAuth/GET.",
    "Explicitly issue LIVE_READ_GO with fixture/runtime/source hashes, ID, times and operator confirmation. Inspect authorization hash and required Phase 3 receipt.",
    "Separately invoke read with --execute-live-read, authorization, receipt and inherited access-token pipe. One Phase 2 attempt, never retry or refresh.",
    "Inspect typed terminal evidence/recovery. Require zero matches AND zero nonempty rows for baseline; contamination retires the fixture, never triggers cleanup.",
    "Stop. Engineering only; mutation, additional reads and new authorization require later explicit review. Study 1 closed; Study 2 observations zero; roadmap GitHub, Google Sheets, Stripe TEST MODE.",
)


def operator_safe(function):
    @functools.wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            pass
        raise p2.Refused()
    return call


@operator_safe
def execute_read(*, execute_live_read: bool, descriptor: dict, configuration,
                 expected_pin: dict, expected_head: str, conditions,
                 token, metadata, authorization, receipt, now=None):
    """No injection/refresh/retry/issuance interface; one frozen inspect call.

    Trust files and this trusted process must remain stable during the attempt.
    Inventory is compared before handoff and after return; this cannot make the
    frozen child trust loading atomic. A drift incident never permits a second GET.
    """
    p2.require(execute_live_read is True and type(token) is frozen.PreparedToken
        and type(metadata) is AcquisitionMetadata and authorization is not None and receipt is not None)
    token.__post_init__()
    metadata.__post_init__()
    p2.require(token.expires_at == metadata.expires_at
        and token.clock_uncertainty_seconds == metadata.clock_uncertainty_seconds)
    report = control.preflight(descriptor=descriptor, configuration=configuration,
        expected_pin=expected_pin, expected_head=expected_head, conditions=conditions,
        now=time.time() if now is None else now, credential_metadata=metadata,
        authorization=authorization, receipt=receipt)
    p2.require(report["status"] == "PASS")
    fixture = control.parse_fixture_descriptor(descriptor)
    # Phase 3 safety margin is additional to the frozen total watchdog. Repeat
    # readiness after local inventory/storage work, immediately before handoff.
    configuration.check_ready(expires_at=token.expires_at,
        clock_uncertainty_seconds=token.clock_uncertainty_seconds, now=time.time())
    summary = read.ReadAdapter(fixture, configuration.read_configuration(),
        Path(configuration.registry_root)).inspect(token, metadata.transport_provenance(),
                                                  authorization=authorization)
    # inspect() already emitted typed durable terminal evidence. No broad response,
    # exception, secret or raw credential enters this independent projection.
    p2.require(type(summary) is read.ReadSummary)
    summary.__post_init__()
    p2.require(control.runtime_projection(configuration) == expected_pin)
    return {"schema": "sheets-phase3-first-read-result-v1", "engineering_only": True,
        "authorization_hash": p2.authorization_hash(authorization), "summary": summary.projection(),
        "baseline": "suitable-current-empty-grid" if summary.outcome is read.Outcome.ZERO
        and summary.nonempty_rows == 0 else "unqualified-or-contaminated-retire-or-review",
        "paper_observations": 0, "next_action": "stop-no-retry"}


def _typed(value, cls):
    p2.require(type(value) is dict and set(value) == {f.name for f in fields(cls)})
    return cls(**value)


def _metadata(value):
    # Persisted acquisition evidence has an exact positive schema. Reconstruct
    # immutable metadata and require identical projection, no unknown inputs.
    names = set(AcquisitionMetadata.__dataclass_fields__)
    p2.require(type(value) is dict and names <= set(value))
    result = AcquisitionMetadata(**{n: value[n] for n in names})
    p2.require(value == result.projection())
    return result


def _token_from_pipe(fd, metadata):
    p2.require(type(fd) is int and fd > 2 and stat.S_ISFIFO(os.fstat(fd).st_mode))
    # Parent closes its writer after transferring one bounded literal. No token
    # cache, argv, environment substitution or refresh credential serialization.
    data = bytearray()
    try:
        while len(data) <= 8192:
            part = os.read(fd, min(4096, 8193 - len(data)))
            if not part:
                break
            data.extend(part)
        p2.require(0 < len(data) <= 8192)
        return frozen.prepare_token(bytes(data).decode("ascii"), expires_at=metadata.expires_at,
            clock_uncertainty_seconds=metadata.clock_uncertainty_seconds)
    finally:
        os.close(fd)
        data[:] = b"\x00" * len(data)  # Best effort only; Python is not a secure heap.


def main(argv=None):
    parser = argparse.ArgumentParser(description="DRAFT Sheets Phase 3; LIVE-GO CLOSED")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("procedure")
    inventory = subs.add_parser("inventory")
    inventory.add_argument("--configuration", required=True, type=Path)
    inventory.add_argument("--output", required=True, type=Path)
    descriptor = subs.add_parser("descriptor")
    descriptor.add_argument("--provisioning-record", required=True, type=Path)
    descriptor.add_argument("--output", required=True, type=Path)
    reserve = subs.add_parser("reserve")
    reserve.add_argument("--fixture", required=True, type=Path)
    reserve.add_argument("--configuration", required=True, type=Path)
    for name in ("preflight", "issue", "read", "recover"):
        sub = subs.add_parser(name)
        for field in ("fixture", "configuration"):
            sub.add_argument("--" + field, required=True, type=Path)
        if name != "recover":
            for field in ("pin", "conditions"):
                sub.add_argument("--" + field, required=True, type=Path)
            sub.add_argument("--expected-head", required=True)
        if name in ("preflight", "read"):
            sub.add_argument("--metadata", type=Path, required=name == "read")
            sub.add_argument("--authorization", type=Path, required=name == "read")
            sub.add_argument("--receipt", type=Path, required=name == "read")
        if name == "recover":
            sub.add_argument("--authorization", type=Path, required=True)
        if name == "read":
            sub.add_argument("--execute-live-read", action="store_true")
            sub.add_argument("--access-token-fd", type=int, required=True)
        if name == "issue":
            sub.add_argument("--metadata", type=Path, required=True)
            for field in ("capability", "fixture-hash", "phase3-runtime-hash", "phase3-source-hash",
                          "authorization-id", "operator-alias", "operator-confirmation", "purpose"):
                sub.add_argument("--" + field, required=True)
            sub.add_argument("--engineering-only", action="store_true", required=True)
            sub.add_argument("--issued-at", type=float, required=True)
            sub.add_argument("--expires-at", type=float, required=True)
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--receipt-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "procedure":
            for i, step in enumerate(PROCEDURE, 1):
                print(f"{i}. {step}")
            return 0
        control.environment_gate()
        if args.command == "descriptor":
            record = _typed(control.load_json(args.provisioning_record), control.ProvisioningRecord)
            p2.require(record.identity_kind == "PROVISIONED")
            control.write_json(args.output, control.fixture_descriptor(record))
            return 0
        configuration = _typed(control.load_json(args.configuration), control.RuntimeConfiguration)
        if args.command == "inventory":
            control.write_json(args.output, control.runtime_projection(configuration))
            return 0
        descriptor = control.load_json(args.fixture)
        fixture = control.parse_fixture_descriptor(descriptor)
        if args.command == "reserve":
            with p2.LocalRegistry(Path(configuration.registry_root)) as registry:
                registry.reserve(fixture)
            return 0
        if args.command == "recover":
            report = control.inspect_recovery(configuration=configuration, descriptor=descriptor,
                authorization=control.parse_authorization(control.load_json(args.authorization)))
        else:
            conditions = _typed(control.load_json(args.conditions), control.LocalConditions)
            common = dict(descriptor=descriptor, configuration=configuration,
                expected_pin=control.load_json(args.pin), expected_head=args.expected_head, conditions=conditions)
            if args.command == "issue":
                authorization, receipt = control.issue_authorization(**common, capability=args.capability,
                    credential_metadata=_metadata(control.load_json(args.metadata)),
                    fixture_hash=args.fixture_hash, phase3_runtime_hash=args.phase3_runtime_hash,
                    phase3_source_hash=args.phase3_source_hash, authorization_id=args.authorization_id,
                    operator_alias=args.operator_alias, issued_at=args.issued_at, expires_at=args.expires_at,
                    operator_confirmation=args.operator_confirmation, purpose=args.purpose,
                    engineering_only=args.engineering_only, now=time.time())
                # Receipt first; any partial output pair is unusable, not repaired.
                control.write_json(args.receipt_output, receipt)
                control.write_json(args.output, control.authorization_projection(authorization))
                report = {"schema": "sheets-phase3-issuance-result-v1", "authorization_hash":
                    p2.authorization_hash(authorization), "network": "not-performed"}
            else:
                metadata = _metadata(control.load_json(args.metadata)) if args.metadata else None
                authorization = control.parse_authorization(control.load_json(args.authorization)) if args.authorization else None
                receipt = control.load_json(args.receipt) if args.receipt else None
                if args.command == "preflight":
                    report = control.preflight(**common, now=time.time(), credential_metadata=metadata,
                        authorization=authorization, receipt=receipt)
                else:
                    p2.require(args.execute_live_read)
                    token = _token_from_pipe(args.access_token_fd, metadata)
                    report = execute_read(**common, execute_live_read=True, token=token, metadata=metadata,
                        authorization=authorization, receipt=receipt)
        print(canonical_json_bytes(report).decode("ascii"))
        return 2 if report.get("status") == "BLOCKED" else 0
    except Exception:
        pass
    print('{"schema":"sheets-phase3-command-refusal-v1","status":"BLOCKED","live_go":"CLOSED"}')
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

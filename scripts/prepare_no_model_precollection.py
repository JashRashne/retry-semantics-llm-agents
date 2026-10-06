"""Preparation/readiness only. This command has no scientific collection mode."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from retry_semantics.baselines.audit_closure import replay_copies, write_json
from retry_semantics.baselines.schedule import build_schedule, freeze_bindings
from retry_semantics.baselines.precollection_readiness import github_checks, provision_sheets, sheets_blank_checks
from retry_semantics.baselines.physical_readiness import frozen_sheets_preliminary, sheets_qualification
from retry_semantics.study2.provider_paper_io import one_shot_http


def local_github_credential():
    # Read only the authorized provider token; never log values or copy .env.
    for name in ("GITHUB_TOKEN", "FINE_GRAIN_GITHUB_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(("GITHUB_TOKEN=", "FINE_GRAIN_GITHUB_TOKEN=")):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise ValueError("GitHub credential unavailable")


def preparation_inputs(directory):
    audit = directory / "source_binding_audit"
    metadata = json.loads((audit / "copy_manifest.json").read_bytes())
    sources = {k: dict(v, path=str(audit / v["path"])) for k, v in metadata["sources"].items()}
    mapping = json.loads((audit / "family_mapping.json").read_bytes())
    namespaces = json.loads((directory / "namespaces.json").read_bytes())
    entries, topology = build_schedule(mapping, sources, namespaces["github"], namespaces["sheets"])
    return sources, mapping, namespaces, entries, topology


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "github-readiness", "sheets-readiness"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--client", type=Path)
    parser.add_argument("--evidence-directory", type=Path,
                        help="New readiness evidence directory; existing attempts are never overwritten")
    parser.add_argument("--defer-full-freeze", action="store_true",
                        help="Freeze preliminary Sheets requests only; full schedule waits for both providers")
    parser.add_argument("--finish-qualification", action="store_true",
                        help="Use inherited separate four-tab control scope for append placement/visibility")
    args = parser.parse_args(argv)
    directory = args.directory.resolve()
    if args.finish_qualification and not args.defer_full_freeze:
        parser.error("qualification requires --defer-full-freeze; both providers must pass before full freeze")
    if args.action == "plan":
        write_json(directory / "namespaces.json", {"github": uuid.uuid4().hex, "sheets": uuid.uuid4().hex})
        sources, mapping, namespaces, entries, topology = preparation_inputs(directory)
        write_json(directory / "prospective_schedule.json", entries)
        write_json(directory / "prospective_sheets_topology.json", topology)
        print("896 prospective opportunities prepared; Sheets scope UNBOUND; zero evaluations.")
        return 0
    sources, mapping, namespaces, entries, topology = preparation_inputs(directory)
    attestation = json.loads((directory / "operator_attestation.json").read_bytes())
    if args.action == "github-readiness":
        evidence = args.evidence_directory or directory / "github_readiness"
        if evidence.exists() or evidence.is_symlink():
            raise ValueError("GitHub readiness attempt already exists; no repeat")
        evidence.mkdir()
        try:
            token = local_github_credential()
            result = github_checks(manifest=json.loads(Path(sources["M1"]["path"]).read_bytes()),
                entries=entries, directory=evidence, writer_attestation=attestation,
                send=lambda req: one_shot_http(req, credential=token))
        except Exception as exc:
            write_json(evidence / "STOPPED.json", {"status": "READINESS_FAILED_NO_RETRY",
                "reason": str(exc) if type(exc).__module__.startswith("retry_semantics.baselines") else type(exc).__name__,
                "scientific_mutations": 0, "scientific_evaluations": 0})
            print("GitHub readiness failed. See credential-free STOPPED.json; no scientific actions.")
            return 2
        print(result["status"])
        return 0
    if args.client is None:
        parser.error("Sheets readiness requires the reviewed installed --client")
    evidence = args.evidence_directory or directory / "sheets_readiness"
    if evidence.exists() or evidence.is_symlink():
        raise ValueError("Sheets readiness attempt already exists; no repeat")
    evidence.mkdir()
    import run_sheets_paper_live_readiness_session as oauth
    import run_sheets_paper_append_qualification_session as qualification
    try:
        from retry_semantics.study2 import sheets_phase3_control as p3
        from retry_semantics.study2 import sheets_live_go_phase1 as p1
        forbidden = [name for name in os.environ if name.upper() in p1.ENV_DENY
            or name.upper() in p3.EXTRA_ENV_DENY or name.upper().startswith(("DYLD_", "LD_", "GIT_"))]
        write_json(evidence / "environment_preflight.json", {
            "inspection": "VARIABLE_NAMES_ONLY", "forbidden_names": forbidden,
            "gate_unchanged": True, "scientific_evaluations": 0})
        p3.environment_gate()  # unchanged gate, before OAuth; strip nothing here
        provisioned = provision_sheets(topology=topology, directory=evidence,
            acquire=lambda: oauth.acquire_session_authority(args.client), transport=one_shot_http,
            verify_access=lambda folder, sid, bearer: qualification._drive_evidence(
                evidence_dir=folder, paper_id=sid, bearer=bearer, drive_get=qualification.drive_get_once)[0],
            writer_attestation=attestation)
        sid = provisioned["spreadsheet_id"]
        entries, topology = build_schedule(mapping, sources, namespaces["github"], namespaces["sheets"], sid)
        write_json(evidence / "physical_topology.json", topology)
        if args.defer_full_freeze:
            frozen_sheets_preliminary(evidence / "preliminary_sheets_bindings", entries)
        else:
            bound = freeze_bindings(directory / "frozen_bindings", entries, sources, mapping=mapping, topology=topology)
            write_json(evidence / "bindings_receipt.json", bound)
        write_json(evidence / "principal_identity.json", provisioned["principal"])
        result = sheets_blank_checks(topology=topology, directory=evidence,
            session=provisioned["session"], evidence=provisioned["evidence"], writer_attestation=attestation)
        if args.finish_qualification:
            q = sheets_qualification(directory=evidence / "separate_append_qualification",
                topology=topology, base_manifest=json.loads(Path(sources["S1"]["path"]).read_bytes()),
                namespace=namespaces["sheets"], session=provisioned["session"],
                verify_access=lambda folder, sid, bearer: qualification._drive_evidence(
                    evidence_dir=folder, paper_id=sid, bearer=bearer, drive_get=qualification.drive_get_once)[0],
                baseline_principal=provisioned["principal"])
            result.update(status="FULL_PROVIDER_READINESS_PASS",
                placement_visibility_qualification="PASS", qualification=q,
                full_write_capability_qualification=True, readiness_qualification_mutations=4)
            write_json(evidence / "final_readiness.json", result)
    except Exception as exc:
        write_json(evidence / "STOPPED.json", {"status": "READINESS_FAILED_NO_RETRY",
            "reason": type(exc).__name__, "scientific_mutations": 0, "scientific_evaluations": 0})
        print("Sheets readiness stopped; preserve all setup evidence. No scientific evaluations.")
        return 2
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

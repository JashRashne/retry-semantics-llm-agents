"""Prospective lock for complete physical bindings and audited runtime bytes."""
from __future__ import annotations

import json
import importlib.metadata
import platform
from pathlib import Path
import subprocess

from retry_semantics.baselines.audit_closure import implementation_closure, write_json
from retry_semantics.baselines import readiness


def freeze_lock(root: Path, directory: Path, output: Path) -> dict:
    bindings = directory / "frozen_bindings"
    github_path = directory / "github_visibility_plus600/final_readiness.json"
    sheets_path = directory / "sheets_readiness_serialization_fixed/final_readiness.json"
    github, sheets = (json.loads(p.read_bytes()) for p in (github_path, sheets_path))
    if github["status"] != "FULL_PROVIDER_READINESS_PASS" or sheets["status"] != "FULL_PROVIDER_READINESS_PASS":
        raise ValueError("both providers must pass before collection lock")
    original = json.loads((root / "research/baselines/no_model/implementation_identity.json").read_bytes())
    for path, expected in original["files"].items():
        if readiness.file_digest(root / path) != expected:
            raise ValueError("accepted identity changed")
    preserved = json.loads((directory / "preserved_before.json").read_bytes())["files"]
    for name, expected in preserved.items():
        if readiness.file_digest(root / name) != expected:
            raise ValueError("prior attempt/namespace/schedule/gate changed")
    proof = json.loads((directory / "inherited_app_principal/comparison.json").read_bytes())
    if proof["app_identity_matches"] is not True or proof["principal_matches"] is not True:
        raise ValueError("valid-replication app/principal differs")
    runtime = implementation_closure(root, [root / "scripts/collect_no_model_baseline.py"])["files"]
    # Include all new baseline source/tests/protocol, even if not on runtime import path.
    for folder, pattern in (("src/retry_semantics/baselines", "*.py"), ("tests", "test_no_model*.py")):
        for path in (root / folder).glob(pattern):
            runtime[str(path.relative_to(root))] = readiness.file_digest(path)
    for name in original["files"]:
        runtime[name] = readiness.file_digest(root / name)
    for name in ("pyproject.toml", "uv.lock"):
        runtime[name] = readiness.file_digest(root / name)
    protocol = directory / "COLLECTION_PROTOCOL.md"
    runtime[str(protocol.relative_to(root))] = readiness.file_digest(protocol)
    evidence = {}
    for folder in (root / "research/baselines/no_model/precollection_v2/source_binding_audit",
                   directory / "github_visibility_plus600", directory / "github_write_visibility_qualification",
                   directory / "sheets_readiness_serialization_fixed", directory / "inherited_app_principal"):
        for path in folder.rglob("*"):
            if path.is_file():
                evidence[str(path.relative_to(root))] = readiness.file_digest(path)
    namespace_path = root / "research/baselines/no_model/precollection_v2/namespaces.json"
    attestation_path = root / "research/baselines/no_model/precollection_v2/operator_attestation.json"
    for path in (namespace_path, attestation_path, directory / "preserved_before.json"):
        evidence[str(path.relative_to(root))] = readiness.file_digest(path)
    sha = readiness.file_digest(bindings / "schedule.json")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
        capture_output=True, text=True, check=True).stdout.strip()
    lock = {"schema": "post-feedback-no-model-collection-lock-v1", "git_head": head,
        "schedule_sha256": sha, "bound": 896, "unbound": 0,
        "scientific_collection_authorized": False, "scientific_evaluations": 0, "scientific_mutations": 0,
        "runtime_files": runtime, "evidence_files": evidence,
        "binding_files": {str(p.relative_to(bindings)): readiness.file_digest(p)
                          for p in sorted(bindings.rglob("*")) if p.is_file()},
        "github_readiness_file": str(github_path.relative_to(root)),
        "sheets_readiness_file": str(sheets_path.relative_to(root)),
        "github_repository": github["repository"], "github_repository_id": github["repository_id"],
        "github_principal_id": github["principal_id"],
        "sheets_app_public_sha256": sheets["qualification"]["same_app_identity_sha256"],
        "sheets_principal": sheets["qualification"]["same_principal"],
        "future_collection_requires_clean_environment": True,
        "future_collection_requires_pinned_lock_and_explicit_authorization": True,
        "python_version": platform.python_version(),
        "runtime_dependency_versions": {name: importlib.metadata.version(name)
            for name in ("httpx", "httpcore", "jsonschema", "groq")},
        "no_resume_no_refill": True}
    write_json(output, lock)
    return lock

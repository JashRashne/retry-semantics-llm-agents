"""Prospective, host-bound operator continuation of the two unstarted providers.

This is a distinct authorization path. It does not manufacture independent audit
receipts or reopen the invalidated Sheets primary. The serial collector and all
scientific inputs are shared with the independently audited primary path.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import time
import uuid

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.github_live_readiness import capture_github_readiness, GitHubReadinessSessionError
from retry_semantics.study2.github_paper_manifest import (
    load_github_paper_manifest, load_namespace_registry as github_registry,
)
from retry_semantics.study2.razorpay_live_readiness import capture_razorpay_readiness, RazorpayReadinessSessionError
from retry_semantics.study2.razorpay_paper_manifest import (
    load_razorpay_paper_manifest, load_namespace_registry as razorpay_registry,
)
from retry_semantics.study2.razorpay_adapter import RazorpayCredentials
from retry_semantics.study2.provider_paper_analysis import load_run_projections
from retry_semantics.study2.provider_paper_collection import (
    PaperCollectionError, _execute_provider_schedule, validate_run_directory,
)
from retry_semantics.study2.provider_paper_io import one_shot_http
from retry_semantics.study2.provider_paper_model import live_fireworks_completion
from retry_semantics.study2.provider_paper_readiness import (
    PROVIDER_CONTROLS, current_static_identity,
)
from retry_semantics.study2.provider_paper_readiness_controls import ControlEvidenceError
from retry_semantics.study2.sheets_replication import (
    ROOT, code_identity, git_head, runtime_versions, write_once,
)

PROTOCOL = "research/protocol/STUDY2_OPERATOR_CONTINUATION_V1.md"
ROLE = "UNSTARTED_PROVIDER_OPERATOR_REVIEWED_CONTINUATION"


def manifest_for(provider: str) -> dict:
    if provider == "github":
        return load_github_paper_manifest().as_json()
    if provider == "razorpay":
        return load_razorpay_paper_manifest()
    raise PaperCollectionError("Only GitHub and Razorpay may use this continuation")


def host_identity() -> str:
    if platform.system() == "Linux":
        # getnode() can silently generate a different random node in each
        # process on minimal VMs. Bind to the OS installation instead.
        try:
            machine_id = Path("/etc/machine-id").read_text().strip().lower()
        except OSError as exc:
            raise PaperCollectionError("Cannot read stable Linux machine identity") from exc
        if re.fullmatch(r"[0-9a-f]{32}", machine_id) is None or machine_id == "0" * 32:
            raise PaperCollectionError("Invalid stable Linux machine identity")
        return sha256_hex(f"linux-machine-id:{machine_id}".encode())
    node = uuid.getnode()
    if node & (1 << 40):
        raise PaperCollectionError("Stable host identity unavailable; UUID supplied a random node")
    return sha256_hex(f"{platform.node()}:{node}".encode())


def build_plan(provider: str, operator: str) -> dict:
    if not operator.strip():
        raise PaperCollectionError("An identified operator is required")
    if os.name != "posix":
        raise PaperCollectionError("Use macOS, Linux or WSL2; POSIX deadlines are required")
    manifest = manifest_for(provider)
    return {
        "schema": "study2-provider-operator-plan-v1", "dataset_role": ROLE,
        "provider": provider, "operator": operator,
        "host_identity_sha256": host_identity(), "git_head": git_head(),
        "runtime_versions": runtime_versions(), "code_sha256": {
            **code_identity(), **{str(p.relative_to(ROOT)): sha256_hex(p.read_bytes())
                                 for p in sorted((ROOT / "scripts").glob("*.sh"))}},
        "protocol_sha256": sha256_hex((ROOT / PROTOCOL).read_bytes()),
        "static_identity": current_static_identity(provider),
        "manifest_sha256": sha256_hex(canonical_json_bytes(manifest)),
        "families": 64, "arms": 256, "independent_audit_claimed": False,
        "no_resume_no_refill": True, "api_version": "2022-11-28" if provider == "github" else None,
        "failed_sheets_primary_remains_closed": True,
        "github_mutation_gap_seconds": 1.1,
    }


def check_plan(path: Path) -> dict:
    raw = path.read_bytes()
    plan = json.loads(raw)
    if (raw != canonical_json_bytes(plan)
            or plan != build_plan(plan["provider"], plan["operator"])):
        raise PaperCollectionError("Plan differs from this host, committed code, or frozen inputs")
    return plan


def credentials(provider: str, environ=None) -> tuple[str, str]:
    env = os.environ if environ is None else environ
    key = env.get("FIREWORKS_API_KEY", "")
    if re.fullmatch(r"[!-~]+", key) is None:
        raise PaperCollectionError("Missing or invalid FIREWORKS_API_KEY")
    live_fireworks_completion(key)  # Syntax validation only, no network.
    if provider == "github":
        credential = env.get("GITHUB_TOKEN") or env.get("FINE_GRAIN_GITHUB_TOKEN", "")
        if re.fullmatch(r"[!-~]+", credential) is None:
            raise PaperCollectionError("Missing or invalid GITHUB_TOKEN")
    elif provider == "razorpay":
        key_id, secret = env.get("RAZORPAY_KEY_ID", ""), env.get("RAZORPAY_KEY_SECRET", "")
        if not key_id or not secret:
            raise PaperCollectionError("Missing RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET")
        if RazorpayCredentials(key_id, secret).scope_fingerprint != manifest_for(provider)["credential_scope_fingerprint"]:
            raise PaperCollectionError("Razorpay keys must match the frozen Test Mode account")
        credential = f"{key_id}:{secret}"
    else:
        raise PaperCollectionError("Unknown provider")
    return credential, key


def claim_path(provider: str) -> Path:
    # Independent of run directory. Prevents accidental relaunch under a new name
    # on this user/host; host assignment is an operator obligation across machines.
    return Path.home() / ".local/state/retry-semantics-study2" / f"{provider}.started.json"


def require_unconsumed(plan_path: Path, provider: str) -> None:
    for path in (plan_path.with_suffix(".started.json"), claim_path(provider)):
        if path.exists() or path.is_symlink():
            raise PaperCollectionError("Launch already consumed; preserve evidence, no resume or refill")


def _capability(provider, complete):
    def call(model, tools, sampling):
        prompt = ("Please create a new GitHub issue titled 'Test' with body 'Test body'."
                  if provider == "github" else "Please create an order with amount 200 and currency 'INR'.")
        return complete({
            "model": model, "tools": [{"type": "function", "function": t} for t in tools],
            "tool_choice": "auto", "parallel_tool_calls": False,
            "temperature": sampling["temperature"], "top_p": sampling["top_p"],
            "seed": sampling["seed"], "max_completion_tokens": sampling["max_output_tokens"],
            "reasoning_effort": "none", "messages": [{"role": "user", "content": prompt}],
        })
    return call


class ProviderTransport:
    """One-shot transport with a small GitHub mutation gap, never a retry."""
    def __init__(self, provider, credential, *, send=one_shot_http,
                 clock=time.monotonic, sleep=time.sleep):
        self.provider, self.credential, self.send = provider, credential, send
        self.clock, self.sleep = clock, sleep
        self.last_mutation_end = None

    def __call__(self, request):
        mutation = self.provider == "github" and request.method == "POST"
        if mutation and self.last_mutation_end is not None:
            delay = self.last_mutation_end + 1.1 - self.clock()
            if delay > 0:
                self.sleep(delay)
        result = self.send(request, credential=self.credential)
        if mutation:
            self.last_mutation_end = self.clock()
        return result


def inventory(directory: Path) -> dict:
    return {str(p.relative_to(directory)): sha256_hex(p.read_bytes())
            for p in sorted(directory.rglob("*")) if p.is_file() and p != directory / "inventory.json"}


def provider_stops(directory: Path) -> list[dict]:
    """Expose the actual access/rate response without printing credentials/bodies."""
    stops = []
    for path in sorted(directory.rglob("*.result.json")):
        record = json.loads(path.read_bytes())
        if record.get("http_status") in (401, 403, 429):
            headers = {k.lower(): v for k, v in record.get("response_headers", [])}
            stops.append({"arm_id": record.get("arm_id"),
                          "operation": record.get("operation_type"),
                          "http_status": record["http_status"],
                          "retry_after": headers.get("retry-after"),
                          "result_file": str(path.relative_to(directory))})
    return stops


def run(plan_path: Path, *, confirm_no_external_writers: bool,
        confirm_provider_never_started: bool, progress=print) -> dict:
    if not (confirm_no_external_writers and confirm_provider_never_started):
        raise PaperCollectionError("Exclusive writer and never-started attestations are required")
    plan = check_plan(plan_path)
    provider = plan["provider"]
    require_unconsumed(plan_path, provider)
    credential, model_key = credentials(provider)
    transport = ProviderTransport(provider, credential)
    manifest = manifest_for(provider)
    registry = github_registry().as_json() if provider == "github" else razorpay_registry()
    return _run_prepared(plan_path, plan=plan, manifest=manifest, registry=registry,
        credential=credential, model_key=model_key, transport=transport,
        global_claim=claim_path(provider), role=ROLE,
        basis="operator-reviewed-continuation",
        attestations={"provider_never_started_attested": True}, progress=progress)


def _run_prepared(plan_path: Path, *, plan: dict, manifest: dict, registry: dict,
                  credential: str, model_key: str, transport, global_claim: Path,
                  role: str, basis: str, attestations: dict, progress=print) -> dict:
    """Collect only after the calling governance path has validated its plan."""
    provider = plan["provider"]
    run_dir = validate_run_directory(plan_path.parent / f"{provider}-run")
    identity = plan["static_identity"]
    plan_sha = sha256_hex(canonical_json_bytes(plan))
    started = {"plan_sha256": plan_sha, "run_dir": str(run_dir),
               "started_at_utc": datetime.now(timezone.utc).isoformat(),
               "state": "CONSUMED_NO_RESUME", "operator": plan["operator"],
               "exclusive_writer_attested": True, **attestations}
    global_claim.parent.mkdir(parents=True, exist_ok=True)
    write_once(global_claim, started)
    write_once(plan_path.with_suffix(".started.json"), started)
    run_dir.mkdir(parents=True, exist_ok=False)
    write_once(run_dir / "plan.json", plan)
    write_once(run_dir / "manifest.json", manifest)
    write_once(run_dir / "namespace-registry.json", registry)
    write_once(run_dir / "operator-attestation.json", started)
    summary = {"provider": provider, "dataset_role": role, "state": "STOPPED", "phase": "readiness",
               "scheduled_arms": 256, "evaluated_arms": 0, "independent_audit_claimed": False}
    try:
        progress(f"{provider}: qualifying all seven readiness controls", flush=True)
        evidence_dir = run_dir / "readiness"
        capture = capture_github_readiness if provider == "github" else capture_razorpay_readiness
        kwargs = {"api_version": plan["api_version"]} if provider == "github" else {}
        hashes = capture(manifest=manifest, registry=registry, evidence_dir=evidence_dir,
            identity=identity, operator_id=plan["operator"],
            http_send=transport,
            model_complete=_capability(provider, live_fireworks_completion(model_key)), **kwargs)
        if (set(hashes) != set(PROVIDER_CONTROLS[provider]) or any(
                sha256_hex((evidence_dir / f"{name}.json").read_bytes()) != digest
                for name, digest in hashes.items())):
            raise PaperCollectionError("Readiness evidence incomplete or changed")
        lock = run_dir / "operator-readiness.json"
        write_once(lock, {"provider": provider, "static_identity": identity,
                         "control_sha256": hashes, "independent_audit_claimed": False,
                         "authorization_basis": basis,
                         "operator_attestation_sha256": sha256_hex(canonical_json_bytes(started))})
        progress(f"{provider}: readiness PASS; beginning 256 serial arms", flush=True)
        summary["phase"] = "collection"
        results = _execute_provider_schedule(
            provider=provider, run_dir=run_dir / "collection", manifest=manifest,
            identity=identity, lock_path=lock, evidence_dir=evidence_dir,
            credential=credential, model_api_key=model_key, api_version=plan["api_version"],
            authorization_sha256=plan_sha, authorization_basis=basis,
            progress=progress, http_send=transport)
        summary.update(evaluated_arms=len(results), verdicts=dict(Counter(r.status for r in results)))
        stops = list((run_dir / "collection").glob("run-stopped-*.json"))
        if stops:
            reason = json.loads(stops[0].read_bytes()).get("reason", "collection_stopped")
            raise PaperCollectionError(f"Collection stopped: {reason}; no resume or refill")
        load_run_projections(run_dir / "collection", manifest, provider, expected_families=64)
        summary["state"] = "COMPLETED"
    except Exception as exc:
        summary["failure_type"] = type(exc).__name__  # Never echo credential-bearing exception text.
        if isinstance(exc, (PaperCollectionError, ControlEvidenceError,
                            GitHubReadinessSessionError, RazorpayReadinessSessionError)):
            summary["failure_reason"] = str(exc)
        projections = [json.loads(p.read_bytes())["projection"]
                       for p in (run_dir / "collection").glob("*/arm-projection.json")]
        summary.update(evaluated_arms=len(projections),
                       verdicts=dict(Counter(p["status"] for p in projections)))
    summary["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary["provider_stop_responses"] = provider_stops(run_dir)
    summary["run_dir"] = str(run_dir)
    write_once(run_dir / "summary.json", summary)
    write_once(run_dir / "inventory.json", inventory(run_dir))
    return summary


def verify(run_dir: Path, *, authorization_basis="operator-reviewed-continuation") -> dict:
    expected = json.loads((run_dir / "inventory.json").read_bytes())
    if expected != inventory(run_dir):
        raise PaperCollectionError("Evidence inventory changed or is incomplete")
    summary = json.loads((run_dir / "summary.json").read_bytes())
    if summary["state"] != "COMPLETED":
        raise PaperCollectionError("Run stopped or was incomplete; preserve all scheduled denominators")
    plan = json.loads((run_dir / "plan.json").read_bytes())
    manifest = json.loads((run_dir / "manifest.json").read_bytes())
    if sha256_hex(canonical_json_bytes(manifest)) != plan["manifest_sha256"]:
        raise PaperCollectionError("Manifest differs from prospective plan")
    authorization = json.loads((run_dir / "collection/run-authorization.json").read_bytes())
    if (authorization.get("authorization_sha256") != sha256_hex(canonical_json_bytes(plan))
            or authorization.get("authorization_basis") != authorization_basis
            or authorization.get("runtime_sha256") != plan["static_identity"]["runtime_sha256"]):
        raise PaperCollectionError("Collection authorization differs from prospective plan")
    rows = load_run_projections(run_dir / "collection", manifest, plan["provider"], expected_families=64)
    if len(rows) != 256 or summary["evaluated_arms"] != 256:
        raise PaperCollectionError("Incomplete scheduled run")
    if summary["verdicts"] != dict(Counter(r.status for r in rows)):
        raise PaperCollectionError("Summary verdicts differ from projections")
    return summary

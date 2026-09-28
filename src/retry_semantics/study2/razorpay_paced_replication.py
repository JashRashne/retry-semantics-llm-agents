"""Separately governed, once-only replication after the sealed Razorpay 429 stop."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re
import time

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import provider_operator_launch as base
from retry_semantics.study2.razorpay_paper_manifest import scientific_sha256

PROTOCOL = "research/protocol/STUDY2_RAZORPAY_PACED_REPLICATION_V1.md"
ROLE = "RAZORPAY_PACED_REPLICATION_V1"
BASIS = "operator-reviewed-razorpay-paced-replication-v1"
CLAIM = "razorpay-paced-replication-v1"
GAP_SECONDS = 3.0


class PacedTransport:
    """At least three seconds after every completed request; never resend."""
    def __init__(self, credential, *, send=None, clock=None, sleep=None):
        self.credential = credential
        self.send = send or base.one_shot_http
        self.clock, self.sleep = clock or time.monotonic, sleep or time.sleep
        self.last_end = None

    def __call__(self, request):
        if self.last_end is not None:
            # Recheck after sleep so interrupted/early wakes cannot shorten the gap.
            while (remaining := self.last_end + GAP_SECONDS - self.clock()) > 0:
                self.sleep(remaining)
        try:
            return self.send(request, credential=self.credential)
        finally:
            self.last_end = self.clock()


def inputs(namespace: str) -> tuple[dict, dict]:
    original = base.manifest_for("razorpay")
    if re.fullmatch(r"[0-9a-f]{32}", namespace) is None or namespace == original["run_namespace"]:
        raise base.PaperCollectionError("A fresh 32-hex replication namespace is required")
    manifest, registry = copy.deepcopy(original), copy.deepcopy(base.razorpay_registry())
    for doc in (manifest, registry):
        doc.pop("audit_provenance", None)
        doc.update(status="OPERATOR_REVIEWED_REPLICATION", run_namespace=namespace,
                   collection_status="REQUIRES_FRESH_HOST_READINESS", dataset_role=ROLE,
                   independent_audit_claimed=False)
    reservations = []
    for family in manifest["families"]:
        for arm in family["arms"]:
            marker = "study2_rzp_paper_" + sha256_hex(f"{namespace}:{arm['arm_id']}".encode())[:32]
            body = canonical_json_bytes({"amount": 200, "currency": "INR",
                                         "notes": {"retry_semantics_marker": marker}})
            arm.update(marker=marker, provider_request_body_hex=body.hex(),
                       provider_request_body_sha256=sha256_hex(body))
            reservations.append({"arm_id": arm["arm_id"], "arm_marker": marker})
    markers = {r["arm_marker"] for r in reservations}
    old_markers = {a["marker"] for f in original["families"] for a in f["arms"]}
    if len(markers) != 256 or markers & old_markers:
        raise base.PaperCollectionError("Replication marker collision")
    registry["reservations"] = reservations
    manifest.update(manifest_id=f"study2-razorpay-paced-v1-{namespace}",
                    registry_semantic_sha256=scientific_sha256(registry),
                    provider_request_gap_seconds=GAP_SECONDS,
                    source_manifest_sha256=sha256_hex(canonical_json_bytes(original)))
    return manifest, registry


def incident_identity(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    if any(p.is_symlink() for p in directory.rglob("*")):
        raise base.PaperCollectionError("Stopped evidence must not contain symlinks")
    inventory = json.loads((directory / "inventory.json").read_bytes())
    summary = json.loads((directory / "summary.json").read_bytes())
    original = base.manifest_for("razorpay")
    if (inventory != base.inventory(directory)
            or json.loads((directory / "manifest.json").read_bytes()) != original
            or summary.get("provider") != "razorpay" or summary.get("state") != "STOPPED"
            or summary.get("dataset_role") != base.ROLE
            or summary.get("scheduled_arms") != 256 or summary.get("evaluated_arms") != 2):
        raise base.PaperCollectionError("Stopped source run changed or is not the two-arm original")
    rate_limits = [str(p.relative_to(directory)) for p in sorted(directory.rglob("*.result.json"))
                   if json.loads(p.read_bytes()).get("http_status") == 429]
    if not rate_limits:
        raise base.PaperCollectionError("Source run does not contain the recorded HTTP 429")
    return {"run_dir": str(directory), "inventory_sha256": sha256_hex(canonical_json_bytes(inventory)),
            "summary_sha256": sha256_hex(canonical_json_bytes(summary)),
            "rate_limit_result_files": rate_limits, "scheduled_arms": 256, "evaluated_arms": 2}


def build_plan(namespace: str, operator: str, stopped_run: Path) -> dict:
    plan = base.build_plan("razorpay", operator)
    manifest, registry = inputs(namespace)
    manifest_sha = sha256_hex(canonical_json_bytes(manifest))
    plan.update(schema="study2-razorpay-paced-replication-plan-v1", dataset_role=ROLE,
                protocol_sha256=sha256_hex((base.ROOT / PROTOCOL).read_bytes()),
                run_namespace=namespace, provider_request_gap_seconds=GAP_SECONDS,
                manifest_sha256=manifest_sha,
                registry_sha256=sha256_hex(canonical_json_bytes(registry)),
                stopped_original=incident_identity(stopped_run))
    plan["static_identity"]["manifest_sha256"] = manifest_sha
    plan["static_identity"]["runtime_sha256"].update({
        "src/retry_semantics/study2/razorpay_paced_replication.py":
            sha256_hex(Path(__file__).read_bytes())})
    return plan


def check_plan(path: Path) -> dict:
    if path.is_symlink():
        raise base.PaperCollectionError("Symlinked plan refused")
    raw = path.read_bytes()
    plan = json.loads(raw)
    if (raw != canonical_json_bytes(plan) or plan != build_plan(
            plan["run_namespace"], plan["operator"], Path(plan["stopped_original"]["run_dir"]))):
        raise base.PaperCollectionError("Replication plan differs from host, code, inputs or stopped evidence")
    return plan


def run(path: Path, *, confirm_no_external_writers: bool,
        confirm_separate_replication: bool, progress=print) -> dict:
    if not (confirm_no_external_writers and confirm_separate_replication):
        raise base.PaperCollectionError("Exclusive writer and separate replication attestations required")
    plan = check_plan(path)
    base.require_unconsumed(path, CLAIM)
    credential, model_key = base.credentials("razorpay")
    manifest, registry = inputs(plan["run_namespace"])
    return base._run_prepared(path, plan=plan, manifest=manifest, registry=registry,
        credential=credential, model_key=model_key, transport=PacedTransport(credential),
        global_claim=base.claim_path(CLAIM), role=ROLE, basis=BASIS,
        attestations={"separate_replication_attested": True,
                      "stopped_original_inventory_sha256": plan["stopped_original"]["inventory_sha256"]},
        progress=progress)


def verify(directory: Path) -> dict:
    summary = base.verify(directory, authorization_basis=BASIS)
    plan = json.loads((directory / "plan.json").read_bytes())
    if plan.get("dataset_role") != ROLE or summary.get("dataset_role") != ROLE:
        raise base.PaperCollectionError("Wrong replication dataset role")
    manifest, registry = inputs(plan["run_namespace"])
    if (json.loads((directory / "manifest.json").read_bytes()) != manifest
            or json.loads((directory / "namespace-registry.json").read_bytes()) != registry):
        raise base.PaperCollectionError("Replication inputs differ from prospective construction")
    spans = []
    for path in directory.rglob("*.result.json"):
        record = json.loads(path.read_bytes())
        if record.get("provider") != "razorpay":
            continue
        start, end = record.get("started_monotonic"), record.get("ended_monotonic")
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end):
            raise base.PaperCollectionError("Invalid recorded provider timing")
        spans.append((start, end))
    spans.sort()
    if not spans or any(start - previous_end < GAP_SECONDS
                        for (_, previous_end), (start, _) in zip(spans, spans[1:])):
        raise base.PaperCollectionError("Recorded requests violate replication pacing")
    return summary

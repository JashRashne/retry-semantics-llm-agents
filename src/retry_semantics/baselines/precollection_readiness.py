"""Readiness only: no scheduled constructors, recover(), or scientific outcomes."""
from __future__ import annotations

import json
import time
import copy
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

from retry_semantics.baselines.audit_closure import write_json
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, PaperRequest
from retry_semantics.study2.sheets_paper_readiness import check_topology, metadata_target, check_grid
from retry_semantics.study2.sheets_paper_blank_readiness import check_precollection_blank
from retry_semantics.study2.sheets_replication import PacedSession, create_request

SANDBOX = "JashRashne/retry-semantics-study2-github-sandbox"
VERSION = "2022-11-28"


class ReadinessRefused(ValueError):
    pass


def journal(directory: Path, provider: str, authority: dict) -> DurablePaperEvidence:
    return DurablePaperEvidence(directory, provider=provider, family_id="READINESS_ONLY",
        arm_id="READINESS_ONLY_NOT_SCIENTIFIC", manifest_sha256=sha256_hex(canonical_json_bytes(authority)),
        runtime_sha256={})


def github_checks(*, manifest: dict, entries: list, directory: Path, send,
                  writer_attestation: dict, clock=time.monotonic) -> dict:
    if manifest["selected_repository"] != SANDBOX:
        raise ReadinessRefused("GitHub scope must be the existing sandbox")
    selected = [entry for entry in entries if entry["source_set"] == "GitHub"]
    if len(selected) != 128 or len({e["provider_marker"] for e in selected}) != 128:
        raise ReadinessRefused("GitHub must have 128 unique planned markers")
    ev = journal(directory / "operations", "github", manifest)
    base = "https://api.github.com/repos/" + SANDBOX
    headers = (("Accept", "application/vnd.github.raw+json"), ("X-GitHub-Api-Version", VERSION))

    def get(url):
        response = ev.record("READINESS_GET_NOT_POLICY_LIST", PaperRequest("GET", url, headers, b""), send)
        if response.error or response.status != 200:
            raise ReadinessRefused("GitHub readiness GET failed: " + str(response.status) + ":" + str(response.error))
        return response

    repo = json.loads(get(base).body)
    user = json.loads(get("https://api.github.com/user").body)
    if repo.get("full_name") != SANDBOX or not repo.get("private") or not repo.get("has_issues"):
        raise ReadinessRefused("sandbox identity/privacy/issues changed")
    if repo.get("owner", {}).get("login") != user.get("login"):
        raise ReadinessRefused("authenticated principal is not sandbox owner")
    # Actual caller-supplied attestation is needed; do not manufacture an operator receipt.
    if writer_attestation.get("exclusive_writing_no_scripts_automation") is not True:
        raise ReadinessRefused("writer exclusion attestation missing")
    permission = get(base + "/collaborators/" + quote(user["login"], safe="") + "/permission")
    access = json.loads(permission.body)
    if access.get("permission") not in ("admin", "write"):
        raise ReadinessRefused("principal lacks repository write permission")
    start = clock()
    census = gh.bounded_census(manifest, selected[0]["arm"], api_version=VERSION,
        fetch=lambda url: (lambda r: HTTPResponse(r.status, r.headers, r.body, r.error))(get(url)),
        elapsed=lambda: clock() - start)
    if not census.complete:
        raise ReadinessRefused("bounded census incomplete")
    if any(body.endswith(e["arm"]["suffix"]) for _, _, body in census.issues for e in selected):
        raise ReadinessRefused("fresh marker collision")
    # Include PRs/raw entries in capacity; 192 is the accepted worst mutation cap.
    if census.raw_entries + 192 + 2 > gh.MAX_PAGES * 100:
        raise ReadinessRefused("insufficient 16-page census headroom")
    rate = json.loads(get("https://api.github.com/rate_limit").body)["resources"]["core"]
    # Worst-case per family 2 baselines + <=2 constructor rounds + 2 policy
    # traversals + 4 evaluator traversals = 10*16 pages, plus three writes.
    if rate.get("remaining", 0) < 180 or rate.get("reset", 0) <= time.time():
        raise ReadinessRefused("insufficient next-family quota headroom")
    result = {"status": "PASS_READ_ONLY_SCOPE", "readiness_only": True,
        "repository": SANDBOX, "repository_id": repo["id"], "principal_id": user["id"],
        "principal_login": user["login"], "api_version": VERSION,
        "permission": access["permission"], "credential_write_probe": "NOT_PERFORMED",
        "writer_attestation": writer_attestation, "census": json.loads(json.dumps(asdict(census))),
        "blank_markers": [e["provider_marker"] for e in selected], "rate_limit": rate,
        "scientific_mutations": 0, "scientific_evaluations": 0,
        "full_write_capability_qualification": False}
    write_json(directory / "readiness.json", result)
    return result


def provision_sheets(*, topology: dict, directory: Path, acquire, transport, verify_access,
                     writer_attestation: dict, clock=time.monotonic, wall=time.time, sleep=time.sleep) -> dict:
    if topology["spreadsheet_id"] != "UNBOUND":
        raise ReadinessRefused("fresh spreadsheet create only; no old scope allowed")
    if writer_attestation.get("exclusive_writing_no_scripts_automation") is not True:
        raise ReadinessRefused("writer exclusion attestation missing")
    # Existing create_request uses the old four-arm serial metadata. Add only
    # that serializer metadata to a copy; all frozen IDs/titles/order stay fixed.
    serial = copy.deepcopy(topology)
    for family_index, family in enumerate(serial["families"]):
        family["scheduled_attempt_index"] = family_index
        for ordinal, arm in enumerate(family["arms"], 1):
            arm["serial_position"] = ordinal
    request = create_request(serial)  # local validation BEFORE OAuth acquisition
    ev = journal(directory / "operations", "sheets", topology)
    session = PacedSession(acquire=acquire, transport=transport, event=ev.event,
                           clock=clock, wall=wall, sleep=sleep)
    session.ensure(2100)
    response = ev.record("READINESS_SCOPE_PROVISIONING_NOT_SCIENTIFIC", request, session.send)
    if response.error or response.status != 200:
        raise ReadinessRefused("spreadsheet provisioning failed; preserve evidence and do not retry")
    sid = json.loads(response.body).get("spreadsheetId")
    if not isinstance(sid, str) or not sid or sid == "UNBOUND":
        raise ReadinessRefused("spreadsheet ID not certified")
    write_json(directory / "provisioned_identity.json", {"spreadsheet_id": sid,
               "readiness_only": True, "scientific_mutations": 0})
    (directory / "access").mkdir()
    # Return session/identity to caller: new bindings are frozen before any other
    # operation. No appendCells or recover() occurs in this provisioning function.
    return {"spreadsheet_id": sid, "session": session, "evidence": ev,
            "principal": verify_access(directory / "access", sid, session.token.value)}


def sheets_blank_checks(*, topology: dict, directory: Path, session, evidence,
                        writer_attestation: dict) -> dict:
    arms = [a for f in topology["families"] for a in f["arms"]]
    response = evidence.record("READINESS_TOPOLOGY_GET", PaperRequest("GET",
        "https://sheets.googleapis.com" + metadata_target(topology["spreadsheet_id"]), (), b""), session.send)
    if response.error:
        raise ReadinessRefused("topology transport failure")
    check_topology(topology, response.status, response.body)
    blanks = []
    strict_blank_grids = 0
    for arm in arms:
        response = evidence.record("READINESS_BLANK_GET_NOT_POLICY_LIST", PaperRequest("GET",
            "https://sheets.googleapis.com" + arm["read_target"], (), b""), session.send)
        if response.error or response.status in (401, 403, 429):
            raise ReadinessRefused("blank baseline failed; no retry")
        check_precollection_blank(topology, arm, method="GET", target=arm["read_target"],
                                 status=response.status, raw=response.body)
        # Record representation without normalizing the accepted experimental path.
        try:
            check_grid(topology, arm, response.status, response.body)
        except ValueError:
            pass
        else:
            strict_blank_grids += 1
        blanks.append(arm["arm_id"])
    result = {"status": "BLANK_TOPOLOGY_PASS_QUALIFICATION_PENDING", "readiness_only": True,
        "spreadsheet_id": topology["spreadsheet_id"], "tabs": 256, "blank_tabs": len(blanks),
        "evaluation_tabs": 128, "reserved_unused_tabs": 128,
        "strict_experimental_grid_usable_blank_tabs": strict_blank_grids,
        "pacing_seconds": 1.1, "writer_attestation": writer_attestation,
        "placement_visibility_qualification": "NOT_PERFORMED", "scientific_evaluations": 0,
        "scientific_mutations": 0}
    write_json(directory / "blank_readiness.json", result)
    return result

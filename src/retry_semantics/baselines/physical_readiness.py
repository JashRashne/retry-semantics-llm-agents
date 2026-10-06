"""Non-scientific provider controls. No scheduled constructor or recover call."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from retry_semantics.baselines import preparation
from retry_semantics.baselines.audit_closure import write_json
from retry_semantics.baselines.precollection_readiness import (
    ReadinessRefused, VERSION, github_checks, journal)
from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.provider_paper_io import PaperRequest
from retry_semantics.study2.sheets_paper_adapter import prepare_paper_append, replay_request, DispatchFacts
from retry_semantics.study2.sheets_paper_blank_readiness import check_precollection_blank
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_runner import validate_append_acknowledgement
from retry_semantics.study2.sheets_replication import bind_manifest, create_request


def frozen_sheets_preliminary(directory, entries):
    """Freeze 128 Sheets requests independently of the later complete schedule."""
    if directory.exists():
        raise ValueError("preliminary Sheets freeze already exists")
    directory.mkdir()
    bound = []
    for entry in entries:
        if entry["source_set"] != "Sheets":
            continue
        arm = entry["arm"]
        if arm["spreadsheet_id"] == "UNBOUND":
            raise ValueError("unbound physical scope")
        _, original = preparation.bind_sheets(source_original={"semantic": entry["semantic_target"]},
            arm=arm, spreadsheet_id=arm["spreadsheet_id"], sheet_id=arm["sheet_id"])
        folder = directory / f"{entry['schedule_index']:03d}"
        preparation.store_sheets(folder, original)
        bound.append(dict(entry, stored_request_identity_sha256=original.identity_hash,
            stored_original_file=str((folder / "stored-original.json").relative_to(directory))))
    if len(bound) != 128:
        raise ValueError("128 preliminary Sheets bindings required")
    write_json(directory / "bindings.json", {"status": "PHYSICAL_REQUESTS_FROZEN_READINESS_PENDING",
        "entries": bound, "scientific_evaluations": 0})


def github_qualification(*, directory, manifest, entries, namespace, send, attestation,
                         clock=time.monotonic):
    """One labeled control POST, complete exact round-trip, fresh marker rescan."""
    if directory.exists():
        raise ValueError("GitHub qualification directory exists; no overwrite")
    directory.mkdir(parents=True)
    scheduled = {e["provider_marker"] for e in entries if e["source_set"] == "GitHub"}
    pre = directory / "before"
    pre.mkdir()
    github_checks(manifest=manifest, entries=entries, directory=pre,
        send=send, writer_attestation=attestation, clock=clock)
    arm = preparation.fresh_arm(namespace=namespace, family_id="READINESS_CONTROL_GITHUB_V1",
        hidden_world="H0", provider="github", old_markers=scheduled)
    arm["policy"] = "NON_SCIENTIFIC_QUALIFICATION_ONLY"
    original = preparation.bind_github(manifest=manifest, arm=arm, api_version=VERSION,
        source_original={"semantic": {
            "title": "[QUALIFICATION CONTROL] No-model precollection transport",
            "body": "NON-SCIENTIFIC READINESS CONTROL; NOT A BASELINE FAMILY.\nExact title/body/suffix round-trip: café 🚀, quote \" and slash \\."}})
    preparation.store_github(directory / "control_request", original)
    write_json(directory / "control_identity.json", {"arm": arm, "request_sha256": original.sha256,
        "scheduled_marker_overlap": False, "scientific_evaluations": 0})
    ev = journal(directory / "operations", "github", manifest)
    def fetch(url):
        req = PaperRequest("GET", url, (("Accept", "application/vnd.github.raw+json"),
            ("X-GitHub-Api-Version", VERSION)), b"")
        r = ev.record("QUALIFICATION_CENSUS_NOT_POLICY_LIST", req, send)
        return HTTPResponse(r.status or 0, r.headers, r.body, r.error)
    start = clock()
    blank = gh.bounded_census(manifest, arm, api_version=VERSION, fetch=fetch, elapsed=lambda: clock()-start)
    if not blank.complete or any(body.endswith(arm["suffix"]) for _, _, body in blank.issues):
        raise ReadinessRefused("qualification marker is not certified absent")
    response = ev.record("NON_SCIENTIFIC_QUALIFICATION_CREATE_ONCE",
        PaperRequest(original.method, original.url, original.headers, original.body), send)
    acknowledgement = HTTPResponse(response.status or 0, response.headers, response.body, response.error)
    number = gh.validate_create_ack(original, acknowledgement, VERSION)
    if number is None:
        raise ReadinessRefused("qualification write failed/ambiguous; never resend")
    anchor = clock()
    seen = gh.bounded_census(manifest, arm, api_version=VERSION, fetch=fetch, elapsed=lambda: clock()-anchor)
    expected = json.loads(original.body)
    matches = tuple(row for row in seen.issues if row[2].endswith(arm["suffix"]))
    if (not seen.complete or clock()-anchor > gh.OBSERVATION_DEADLINES[0]
            or matches != ((number, expected["title"], expected["body"]),)):
        raise ReadinessRefused("qualification round-trip/visibility not certified; preserve issue")
    post = directory / "after"
    post.mkdir()
    final = github_checks(manifest=manifest, entries=entries, directory=post,
        send=send, writer_attestation=attestation, clock=clock)
    final.update(status="FULL_PROVIDER_READINESS_PASS", credential_write_probe="PASS",
        full_write_capability_qualification=True, suffix_roundtrip_visibility="PASS",
        qualification_issue_number=number, qualification_marker=arm["arm_marker"],
        readiness_qualification_mutations=1, qualification_census=json.loads(json.dumps(asdict(seen))))
    write_json(directory / "final_readiness.json", final)
    return final


def continue_github_visibility(*, prior, directory, manifest, entries, send,
                               attestation, clock=time.monotonic, sleep=time.sleep):
    """Read-only +600 continuation of one clearly acknowledged control POST.

    The earlier stop record is immutable. A later readiness verdict explicitly
    references it; this function cannot dispatch POST or replace that evidence.
    """
    if directory.exists():
        raise ValueError("new continuation evidence directory required")
    original = preparation.load_github(prior / "control_request/stored-original.json")
    identity = json.loads((prior / "control_identity.json").read_bytes())
    arm = identity["arm"]
    if original.sha256 != identity["request_sha256"]:
        raise ReadinessRefused("prior control identity changed")
    results = [json.loads(path.read_bytes()) for path in sorted((prior / "operations").glob("*.result.json"))]
    writes = [r for r in results if r["method"] == "POST"]
    if len(writes) != 1 or writes[0]["operation_type"] != "NON_SCIENTIFIC_QUALIFICATION_CREATE_ONCE":
        raise ReadinessRefused("exactly one acknowledged control POST required")
    acknowledgement = writes[0]
    if bytes.fromhex(acknowledgement["body_hex"]) != original.body or acknowledgement["target"] != original.url:
        raise ReadinessRefused("prior posted request changed")
    number = gh.validate_create_ack(original, HTTPResponse(acknowledgement["http_status"],
        tuple(tuple(h) for h in acknowledgement["response_headers"]),
        bytes.fromhex(acknowledgement["response_body_hex"]), acknowledgement["transport_error"]), VERSION)
    if number is None:
        raise ReadinessRefused("ambiguous POST cannot be continued or retried")
    if arm["arm_marker"] in {e["provider_marker"] for e in entries if e["source_set"] == "GitHub"}:
        raise ReadinessRefused("scheduled marker cannot be qualified")
    anchor = acknowledgement["ended_monotonic"]
    if clock() < anchor or clock() >= anchor + gh.OBSERVATION_DEADLINES[1]:
        raise ReadinessRefused("inherited control visibility deadline missed")
    directory.mkdir(parents=True)
    write_json(directory / "read_only_continuation_intent.json", {
        "prior_attempt": str(prior), "prior_control_request_sha256": original.sha256,
        "prior_acknowledged_issue_number": number, "scheduled_offset_seconds": 600,
        "anchor_monotonic": anchor, "no_post_capability": True,
        "scientific_evaluations": 0, "scientific_mutations": 0})
    while clock() < anchor + 600:
        sleep(min(30, anchor + 600 - clock()))
    ev = journal(directory / "operations", "github", manifest)
    def get(request):
        if request.method != "GET":
            raise ReadinessRefused("continuation may only read")
        return send(request)
    def fetch(url):
        response = ev.record("QUALIFICATION_PLUS_600_CENSUS_NOT_POLICY_LIST",
            PaperRequest("GET", url, (("Accept", "application/vnd.github.raw+json"),
                ("X-GitHub-Api-Version", VERSION)), b""), get)
        return HTTPResponse(response.status or 0, response.headers, response.body, response.error)
    census = gh.bounded_census(manifest, arm, api_version=VERSION, fetch=fetch,
        elapsed=lambda: clock() - (anchor + 600))
    sent = json.loads(original.body)
    matches = tuple(row for row in census.issues if row[2].endswith(arm["suffix"]))
    observed = {"census": json.loads(json.dumps(asdict(census))),
        "completed_monotonic": clock(), "scientific_evaluations": 0}
    write_json(directory / "visibility_observation.json", observed)
    if (not census.complete or clock() > anchor + gh.OBSERVATION_DEADLINES[1]
            or matches != ((number, sent["title"], sent["body"]),)):
        raise ReadinessRefused("inherited +600 control visibility not certified")
    post = directory / "after"
    post.mkdir()
    result = github_checks(manifest=manifest, entries=entries, directory=post,
        send=get, writer_attestation=attestation, clock=clock)
    result.update(status="FULL_PROVIDER_READINESS_PASS", credential_write_probe="PASS",
        full_write_capability_qualification=True, suffix_roundtrip_visibility="PASS",
        qualification_issue_number=number, qualification_marker=arm["arm_marker"],
        qualification_source_attempt=str(prior), visibility_offset_seconds=600,
        readiness_qualification_mutations_in_continuation=0)
    write_json(directory / "final_readiness.json", result)
    return result


def sheets_qualification(*, directory, topology, base_manifest, namespace, session, verify_access,
                         baseline_principal, wall=time.time, clock=time.monotonic):
    """Inherited separate four-tab scope and two exact append placement controls.

    The second acknowledged append is an intentional duplicate control, never
    a retry. Nothing writes the baseline spreadsheet, reserved tabs or arms.
    """
    import run_sheets_paper_append_qualification_session as inherited
    if directory.exists():
        raise ValueError("Sheets qualification directory exists; no overwrite")
    directory.mkdir()
    ev = journal(directory / "operations", "sheets", topology)
    session.ensure(180)
    prospective = bind_manifest(base_manifest, namespace, "UNBOUND", qualification=True)
    if len(prospective["families"][0]["arms"]) != 4:
        raise ReadinessRefused("inherited qualification topology must have four tabs")
    created = ev.record("NON_SCIENTIFIC_QUALIFICATION_SCOPE_CREATE_ONCE", create_request(prospective), session.send)
    if created.error or created.status != 200:
        raise ReadinessRefused("qualification provisioning uncertain; never resend")
    identity = json.loads(created.body).get("spreadsheetId")
    if not identity or identity in ("UNBOUND", topology["spreadsheet_id"]):
        raise ReadinessRefused("qualification aliases baseline scope")
    manifest = bind_manifest(base_manifest, namespace, identity, qualification=True)
    expected = json.loads(create_request(manifest).body)
    if json.loads(created.body) != dict(expected, spreadsheetId=identity):
        raise ReadinessRefused("qualification scope topology mismatch")
    write_json(directory / "control_manifest.json", manifest)
    access = directory / "access"
    access.mkdir()
    if verify_access(access, identity, session.token.value) != baseline_principal:
        raise ReadinessRefused("qualification principal differs from baseline owner")
    arm = dict(manifest["families"][0]["arms"][0], arm_marker=inherited.MARKER,
        policy="NON_SCIENTIFIC_QUALIFICATION_ONLY")
    markers = {a["arm_marker"] for f in topology["families"] for a in f["arms"]}
    if arm["arm_marker"] in markers or arm["spreadsheet_id"] == topology["spreadsheet_id"]:
        raise ReadinessRefused("qualification/scientific overlap")
    write_json(directory / "control_identity.json", {"arm": arm, "item": inherited.ITEM,
        "detail": inherited.DETAIL, "scientific_marker_overlap": False,
        "scientific_physical_scope_overlap": False, "scientific_evaluations": 0})
    def get():
        result = ev.record("QUALIFICATION_GRID_GET_NOT_POLICY_LIST",
            PaperRequest("GET", "https://sheets.googleapis.com" + arm["read_target"], (), b""), session.send)
        return PaperHTTPResult(DispatchFacts(result.dispatch_initiated,
            result.local_send_completed is True, result.status), result.body, result.error)
    pre = get()
    if pre.transport_error:
        raise ReadinessRefused("qualification preblank transport failed")
    check_precollection_blank(manifest, arm, method="GET", target=arm["read_target"],
        status=pre.facts.http_status, raw=pre.body)
    original = prepare_paper_append(arm, inherited.ITEM, inherited.DETAIL)
    preparation.store_sheets(directory / "control_request", original)
    ev.event("control-retired-before-first-dispatch", {"readiness_only": True,
        "request_identity_sha256": original.identity_hash, "no_cleanup_no_retry": True})
    visibility = []
    for ordinal, rows in ((1, (0,)), (2, (0, 1))):
        request = original if ordinal == 1 else replay_request(original)
        if request is not original:
            raise ReadinessRefused("exact qualification request changed")
        result = ev.record("NON_SCIENTIFIC_PLANNED_APPEND_CONTROL_" + str(ordinal),
            PaperRequest(request.method, "https://sheets.googleapis.com" + request.uri,
                request.headers, request.body), session.send)
        raw = PaperHTTPResult(DispatchFacts(result.dispatch_initiated,
            result.local_send_completed is True, result.status), result.body, result.error)
        validate_append_acknowledgement(request, arm, raw)
        start = clock()
        inherited._check_post(manifest, arm, get(), rows)
        elapsed = clock() - start
        if not 0 <= elapsed <= 40:
            raise ReadinessRefused("qualification visibility exceeds inherited 40-second window")
        visibility.append(elapsed)
    remaining = session.token.expires_at - wall()
    result = {"status": "APPEND_PLACEMENT_VISIBILITY_PASS", "readiness_only": True,
        "qualification_spreadsheet_id": identity, "baseline_spreadsheet_id": topology["spreadsheet_id"],
        "qualification_marker": arm["arm_marker"], "visibility_seconds": visibility,
        "first_placement_row": 1, "duplicate_row_indices": [1, 2],
        "same_app_identity_sha256": session.app_identity,
        "same_principal": baseline_principal, "qualification_mutations": 3,
        "token_remaining_seconds_at_completion": remaining, "pacing_seconds": 1.1,
        "scientific_evaluations": 0, "scientific_mutations": 0,
        "scheduled_baseline_tabs_written": 0, "reserved_tabs_written": 0}
    if remaining <= 180 + session.token.clock_uncertainty_seconds:
        raise ReadinessRefused("insufficient token headroom after qualification")
    write_json(directory / "qualification_pass.json", result)
    return result

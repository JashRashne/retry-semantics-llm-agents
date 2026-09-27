"""Adversarial offline completion checks; no provider or model network calls."""

from __future__ import annotations

import copy
import json

import httpx
import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts, prepare_paper_append
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult, one_shot_request, send_frozen_mutation
from retry_semantics.study2.sheets_paper_manifest_authority import (
    AMENDMENT, MODEL_AMENDMENT_PATH, AUTHORITY_PATH, SOURCE_SHA256, AuthorityError,
    build_authority, load_authority,
)
from retry_semantics.study2.sheets_paper_model import (
    SheetsFireworksContinuation, SheetsModelError,
)
from retry_semantics.study2.sheets_paper_materialize import (
    MANIFEST_PATH, REPOSITORY_ROOT, SheetsPaperMaterializationError,
    build_paper_manifest, load_paper_manifest, read_target,
    scientifically_equal_model_config,
)
from retry_semantics.study2.sheets_paper_readiness import (
    CONTROL_FACTS, PaperReadinessError, check_readiness_structure,
    qualify_readiness,
)
from retry_semantics.study2.sheets_paper_runner import (
    ModelDecision, PaperRunnerError, RecoveryContext, certify_h1_constructor, dispatch_stage, load_original,
    run_recovery, store_original, validate_append_acknowledgement,
)


@pytest.fixture(scope="module")
def manifest():
    return load_paper_manifest()


def _arms(manifest):
    return [arm for family in manifest["families"] for arm in family["arms"]]


def _grid(arm):
    return {"spreadsheetId": arm["spreadsheet_id"],
            "sheets": [{"properties": {"sheetId": arm["sheet_id"],
                                       "title": arm["tab_title"], "sheetType": "GRID",
                                       "gridProperties": {"rowCount": 100,
                                                          "columnCount": 3}}}]}


def _topology(manifest):
    return {"spreadsheetId": manifest["spreadsheet_id"],
            "properties": {"title": manifest["spreadsheet_title"]},
            "sheets": [_grid(a)["sheets"][0] for a in _arms(manifest)]}


def _readiness_inputs(manifest):
    arms = _arms(manifest)
    return ((200, canonical_json_bytes(_topology(manifest))),
            {a["arm_id"]: ("GET", a["read_target"], 200,
                           canonical_json_bytes(_grid(a))) for a in arms})


def test_authority_transcription_tamper_refused(tmp_path):
    assert (REPOSITORY_ROOT / AUTHORITY_PATH).read_bytes() == build_authority()
    for source in (*SOURCE_SHA256, AMENDMENT, MODEL_AMENDMENT_PATH):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY_ROOT / source).read_bytes())
    dest = tmp_path / AUTHORITY_PATH
    dest.write_bytes((REPOSITORY_ROOT / AUTHORITY_PATH).read_bytes())
    assert load_authority(tmp_path)["decisions"]["model"]["value"]["temperature"] == 0.0
    for block, field, value in (("model", "temperature", 0.7),
                                ("model_seeds", "original_base", 42),
                                ("counterbalancing", "policy_order_seed", 1),
                                ("observer", "required_explicit_grid_data", False),
                                ("task", "append_row_success_projection", {"status": "tampered"}),
                                ("task", "append_row_success_projection_model_visible", False)):
        changed = json.loads(dest.read_bytes())
        changed["decisions"][block]["value"][field] = value
        dest.write_bytes(canonical_json_bytes(changed))
        with pytest.raises(AuthorityError):
            load_authority(tmp_path)
        dest.write_bytes((REPOSITORY_ROOT / AUTHORITY_PATH).read_bytes())
    amended = tmp_path / AMENDMENT
    amended.write_bytes(amended.read_bytes() + b" ")
    with pytest.raises(AuthorityError):
        load_authority(tmp_path)


def test_manifest_authority_conventions_and_frozen_counts(manifest):
    assert (REPOSITORY_ROOT / MANIFEST_PATH).read_bytes() == build_paper_manifest()
    assert manifest["collection_status"] == "BLOCKED"
    assert manifest["readiness_status"] == "NOT_QUALIFIED"
    assert manifest["study2_paper_observations"] == 0
    assert manifest["observation_policy"]["required_explicit_grid_data"] is True
    assert manifest["model_visible_common"]["append_row_success_projection"] == {"status": "appended"}
    assert manifest["implementation_conventions"]["read_target_serialization"] == (
        "implementation_convention_not_experimental_variable")
    assert manifest["implementation_conventions"]["model_config_id"] == (
        "implementation_identifier_not_experimental_variable")
    arms = _arms(manifest)
    assert len(arms) == len({a["sheet_id"] for a in arms}) == 256
    assert len({a["tab_title"] for a in arms}) == 256
    assert {a["range"] for a in arms} == {"A1:C100"}
    assert {(w, p): sum(a["hidden_world"] == w and a["policy"] == p for a in arms)
            for w in ("H0", "H1") for p in ("EXACT_REPLAY", "LLM_REGENERATION")} == {
                (w, p): 64 for w in ("H0", "H1")
                for p in ("EXACT_REPLAY", "LLM_REGENERATION")}
    config = manifest["families"][0]["model_config"]
    relabeled = copy.deepcopy(config)
    relabeled["model_config_id"] = "different label"
    assert scientifically_equal_model_config(config, relabeled)
    relabeled["regeneration"]["seed"] += 1
    assert not scientifically_equal_model_config(config, relabeled)
    arm = arms[0]
    assert arm["read_target"] == read_target(arm["spreadsheet_id"], arm["tab_title"])
    assert arm["read_target"].encode() == read_target(
        arm["spreadsheet_id"], arm["tab_title"]).encode()


def test_materialization_rejects_unauthorized_append_success_projection(monkeypatch):
    from retry_semantics.study2 import sheets_paper_materialize as mat
    for altered_val, altered_vis in (
        ({"status": "tampered"}, True),
        ({"status": "appended"}, False),
        (None, True),
        ({"status": "appended"}, None),
    ):
        base_authority = load_authority()
        tampered_task = {
            **base_authority["decisions"]["task"]["value"],
            "append_row_success_projection": altered_val,
            "append_row_success_projection_model_visible": altered_vis,
        }
        monkeypatch.setattr(mat, "load_authority", lambda _root=None: {
            **base_authority,
            "decisions": {
                **base_authority["decisions"],
                "task": {
                    **base_authority["decisions"]["task"],
                    "value": tampered_task,
                },
            },
        })
        with pytest.raises(mat.SheetsPaperMaterializationError, match="authority disagrees"):
            mat.build_paper_manifest()


def _controls(tmp_path, manifest):
    subject = {"spreadsheet_id": manifest["spreadsheet_id"],
               "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    index = {}
    for name, fields in CONTROL_FACTS.items():
        raw = canonical_json_bytes({"schema": "sheets-paper-readiness-control-evidence-v1",
                                    "control": name, "subject": subject,
                                    "qualified": True, "facts": {f: "synthetic" for f in fields}})
        filename = name + ".json"
        (tmp_path / filename).write_bytes(raw)
        index[name] = {"file": filename, "sha256": sha256_hex(raw)}
    return index


def test_readiness_bytes_and_independent_receipt_required(tmp_path, manifest, monkeypatch):
    topology, baselines = _readiness_inputs(manifest)
    controls = _controls(tmp_path, manifest)
    kwargs = dict(topology_response=topology, baseline_responses=baselines,
                  control_evidence=controls, evidence_root=tmp_path)
    assert len(check_readiness_structure(manifest, **kwargs)) == 10
    receipt = tmp_path / "receipt.json"
    report = tmp_path / "independent-audit.txt"
    report.write_bytes(b"synthetic independent audit report")
    audit = {"auditor_id": "synthetic-independent-auditor",
             "audit_report_file": report.name,
             "audit_report_sha256": sha256_hex(report.read_bytes()),
             "audited_at_utc": "2026-09-25T00:00:00Z"}
    receipt_value = {
        "schema": "sheets-paper-readiness-audit-receipt-v1",
        "subject": {"spreadsheet_id": manifest["spreadsheet_id"],
                    "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))},
        "independent_audit": audit,
        "control_sha256": {n: v["sha256"] for n, v in controls.items()},
        "topology_sha256": sha256_hex(topology[1]),
        "baseline_sha256": {arm_id: sha256_hex(response[3])
                            for arm_id, response in baselines.items()}}
    receipt.write_bytes(canonical_json_bytes(receipt_value))
    from retry_semantics.study2 import sheets_paper_readiness as readiness
    lock = tmp_path / readiness.READINESS_LOCK_PATH
    with pytest.raises(PaperReadinessError, match="missing"):
        qualify_readiness(manifest, audit_receipt=receipt, root=tmp_path, **kwargs)
    lock.parent.mkdir(parents=True)
    lock_value = {"schema": "sheets-paper-readiness-lock-v1",
                  "receipt_sha256": sha256_hex(receipt.read_bytes()),
                  "independent_audit": audit,
                  "manifest_sha256": sha256_hex(canonical_json_bytes(manifest)),
                  "spreadsheet_id": manifest["spreadsheet_id"],
                  "topology_sha256": receipt_value["topology_sha256"],
                  "baseline_sha256": receipt_value["baseline_sha256"],
                  "control_sha256": receipt_value["control_sha256"]}
    lock.write_bytes(canonical_json_bytes(lock_value))
    monkeypatch.setattr(readiness, "_require_clean_committed_lock", lambda _root, _manifest: None)
    qualify_readiness(manifest, audit_receipt=receipt, root=tmp_path, **kwargs)
    receipt_raw = receipt.read_bytes()
    receipt.write_bytes(receipt_raw + b" ")
    with pytest.raises(PaperReadinessError):
        qualify_readiness(manifest, audit_receipt=receipt, root=tmp_path, **kwargs)
    receipt.write_bytes(receipt_raw)
    for field, replacement in (("manifest_sha256", "0" * 64),
                               ("spreadsheet_id", "wrong"),
                               ("topology_sha256", "0" * 64),
                               ("baseline_sha256", {}),
                               ("control_sha256", {}),
                               ("receipt_sha256", "0" * 64),
                               ("independent_audit", {**audit, "auditor_id": "wrong"})):
        lock.write_bytes(canonical_json_bytes({**lock_value, field: replacement}))
        with pytest.raises(PaperReadinessError):
            qualify_readiness(manifest, audit_receipt=receipt, root=tmp_path, **kwargs)
    lock.write_bytes(canonical_json_bytes(lock_value))
    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["manifest_id"] = "tampered"
    with pytest.raises(PaperReadinessError):
        qualify_readiness(changed_manifest, audit_receipt=receipt, root=tmp_path, **kwargs)
    report.write_bytes(b"changed report")
    with pytest.raises(PaperReadinessError):
        qualify_readiness(manifest, audit_receipt=receipt, root=tmp_path, **kwargs)
    report.write_bytes(b"synthetic independent audit report")
    first = next(iter(controls))
    path = tmp_path / controls[first]["file"]
    original = path.read_bytes()
    for altered in (b"", original + b" "):
        path.write_bytes(altered)
        with pytest.raises(PaperReadinessError):
            check_readiness_structure(manifest, **kwargs)
    path.write_bytes(original)
    for field, value in (("control", "wrong"), ("schema", "wrong"),
                         ("subject", {"spreadsheet_id": "wrong"})):
        altered = json.loads(original)
        altered[field] = value
        path.write_bytes(canonical_json_bytes(altered))
        controls[first]["sha256"] = sha256_hex(path.read_bytes())
        with pytest.raises(PaperReadinessError):
            check_readiness_structure(manifest, **kwargs)
    path.write_bytes(original)
    controls[first]["sha256"] = sha256_hex(original)
    bogus = copy.deepcopy(controls)
    bogus[first]["sha256"] = "0" * 64
    with pytest.raises(PaperReadinessError):
        check_readiness_structure(manifest, **{**kwargs, "control_evidence": bogus})
    missing = copy.deepcopy(controls)
    missing.pop(first)
    with pytest.raises(PaperReadinessError):
        check_readiness_structure(manifest, **{**kwargs, "control_evidence": missing})
    duplicate = copy.deepcopy(controls)
    other = next(n for n in duplicate if n != first)
    duplicate[other] = duplicate[first]
    with pytest.raises(PaperReadinessError):
        check_readiness_structure(manifest, **{**kwargs, "control_evidence": duplicate})


def test_transport_lifecycle_without_provider_access():
    assert dispatch_stage(DispatchFacts()) == "DISPATCH_NOT_INITIATED"
    assert dispatch_stage(DispatchFacts(True)) == "DISPATCH_INITIATED_LOCAL_SEND_INCOMPLETE"
    assert dispatch_stage(DispatchFacts(True, True)) == "LOCAL_SEND_COMPLETE_ACK_AMBIGUOUS"
    assert dispatch_stage(DispatchFacts(True, True, 500)) == "VISIBLE_PROVIDER_RESPONSE"
    assert dispatch_stage(DispatchFacts(True, True, 200, True, True)) == "VALIDATED_SUCCESS"
    with pytest.raises(ValueError):
        one_shot_request(method="POST", target="/v4/spreadsheets/x:batchUpdate",
                         body=b"{}", bearer="synthetic", spreadsheet_id="x",
                         max_response_bytes=1024)


def test_one_shot_transport_fake_wire_preserves_bytes_and_visible_status(monkeypatch, manifest):
    from retry_semantics.study2 import sheets_paper_http as paper_http
    import signal
    arm = _arms(manifest)[0]
    request = prepare_paper_append(arm, "Blue notebook", "A compact notebook")
    wires = []

    class FakeResponse:
        status = 200

        def read(self, _size):
            if len(wires) == 2:
                raise TimeoutError("synthetic body loss")
            return b'{"replies":[{}]}'

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            self.headers = []
            wires.append(self)

        def connect(self):
            pass

        def putrequest(self, method, target, **_kwargs):
            self.method, self.target = method, target

        def putheader(self, name, value):
            self.headers.append((name, value))

        def endheaders(self, body=None, **_kwargs):
            self.body = body

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr(paper_http.http.client, "HTTPSConnection", FakeConnection)
    first = send_frozen_mutation(request, bearer="synthetic",
                                 spreadsheet_id=arm["spreadsheet_id"],
                                 allow_live_collection=True)
    assert first.facts.http_status == 200 and first.transport_error is None
    assert wires[0].method == request.method and wires[0].target == request.uri
    assert wires[0].body == request.body
    assert [(n, v) for n, v in wires[0].headers if n in ("content-type", "accept")] == list(request.headers)
    second = send_frozen_mutation(request, bearer="synthetic",
                                  spreadsheet_id=arm["spreadsheet_id"],
                                  allow_live_collection=True)
    assert second.facts.http_status == 200
    assert second.transport_error == "TimeoutError"
    assert second.facts.local_send_completed
    assert not second.facts.remote_commit_certified
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)

    def timed_out_connection(*_args, **_kwargs):
        raise paper_http.PaperTransportDeadline()

    monkeypatch.setattr(paper_http.http.client, "HTTPSConnection", timed_out_connection)
    expired = one_shot_request(method="GET", target=arm["read_target"], body=b"",
                               bearer="synthetic", spreadsheet_id=arm["spreadsheet_id"],
                               max_response_bytes=1024)
    assert dispatch_stage(expired.facts) == "DISPATCH_NOT_INITIATED"
    assert expired.transport_error == "PaperTransportDeadline"
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_exact_replay_uses_durable_bytes_and_zero_model_calls(tmp_path, manifest):
    family = manifest["families"][0]
    arm = next(a for a in family["arms"] if a["hidden_world"] == "H0"
               and a["policy"] == "EXACT_REPLAY")
    semantic = family["target_semantic_m"]
    original = prepare_paper_append(arm, semantic["item"], semantic["detail"])
    path = tmp_path / "original.json"
    store_original(path, original)
    assert load_original(path).body == original.body
    seen = []
    result = run_recovery(
        manifest=manifest, family=family, arm=arm, original_path=path,
        initial_world_facts=DispatchFacts(), original_model_message=b"original assistant message",
        model_visible_common=manifest["model_visible_common"],
        dispatch=lambda request: seen.append(request) or PaperHTTPResult(DispatchFacts(True, True), b"", "synthetic"),
        model_continue=lambda _: pytest.fail("Replay invoked model"))
    assert len(seen) == 1 and seen[0].body == original.body
    assert seen[0].identity_hash == original.identity_hash
    assert result.model_calls == result.study2_paper_observations == 0
    assert result.terminal_reason == "LOCAL_SEND_COMPLETE_ACK_AMBIGUOUS"
    with pytest.raises(PaperRunnerError):
        run_recovery(manifest=manifest, family=family, arm=arm, original_path=path,
                     initial_world_facts=DispatchFacts(True, True, 500),
                     original_model_message=b"original", model_visible_common=manifest["model_visible_common"],
                     dispatch=lambda _: PaperHTTPResult(DispatchFacts(True, True), b"", "synthetic"))


def test_regeneration_exposes_ambiguity_and_model_chooses(tmp_path, manifest):
    family = manifest["families"][0]
    arm = next(a for a in family["arms"] if a["hidden_world"] == "H0"
               and a["policy"] == "LLM_REGENERATION")
    path = tmp_path / "original.json"
    semantic = family["target_semantic_m"]
    store_original(path, prepare_paper_append(arm, semantic["item"], semantic["detail"]))
    contexts, requests = [], []

    def model(context):
        contexts.append(context)
        return ModelDecision("append_row", "Green notebook", "A larger notebook")

    def dispatch(request):
        requests.append(request)
        return PaperHTTPResult(DispatchFacts(True, True, 403), b"denied", None)

    result = run_recovery(
        manifest=manifest, family=family, arm=arm, original_path=path,
        initial_world_facts=DispatchFacts(), original_model_message=b"original assistant message",
        model_visible_common=manifest["model_visible_common"],
        dispatch=dispatch, model_continue=model)
    assert len(contexts) == len(requests) == 1
    assert contexts[0].ambiguous_observation == manifest["model_visible_common"]["ambiguity_text"]
    assert contexts[0].seed == family["model_config"]["regeneration"]["seed"]
    assert requests[0].body != load_original(path).body
    assert result.terminal_reason == "VISIBLE_PROVIDER_FAILURE"
    assert result.study2_paper_observations == 0

    model_calls = []
    ambiguous = run_recovery(
        manifest=manifest, family=family, arm=arm, original_path=path,
        initial_world_facts=DispatchFacts(), original_model_message=b"original assistant message",
        model_visible_common=manifest["model_visible_common"],
        dispatch=lambda _: PaperHTTPResult(DispatchFacts(True, True), b"", "synthetic"),
        model_continue=lambda context: model_calls.append(context) or
        ModelDecision("append_row", "Green notebook", "A larger notebook"))
    assert ambiguous.terminal_reason == "UNRESOLVED_MUTATION_OUTCOME"
    assert len(model_calls) == 1


def test_h1_requires_certification_and_regeneration_action_cap(tmp_path, manifest):
    family = manifest["families"][0]
    arm = next(a for a in family["arms"] if a["hidden_world"] == "H1"
               and a["policy"] == "LLM_REGENERATION")
    path = tmp_path / "original.json"
    semantic = family["target_semantic_m"]
    store_original(path, prepare_paper_append(arm, semantic["item"], semantic["detail"]))
    kwargs = dict(manifest=manifest, family=family, arm=arm, original_path=path,
                  original_model_message=b"original assistant message",
                  model_visible_common=manifest["model_visible_common"],
                  dispatch=lambda _: PaperHTTPResult(DispatchFacts(True, True), b"", "synthetic"),
                  model_continue=lambda _: ModelDecision("append_row", "Blue notebook", "A compact notebook"))
    with pytest.raises(PaperRunnerError, match="uncertified"):
        run_recovery(initial_world_facts=DispatchFacts(True, True, 200, True), **kwargs)
    observed = _grid(arm)
    observed["sheets"][0]["data"] = [{"rowData": [{"values": [
        {"userEnteredValue": {"stringValue": text}}
        for text in (arm["arm_marker"], semantic["item"], semantic["detail"])]}]}]
    original = load_original(path)
    ack = PaperHTTPResult(DispatchFacts(True, True, 200), canonical_json_bytes({
        "spreadsheetId": arm["spreadsheet_id"], "replies": [{}]}), None)
    certified = certify_h1_constructor(manifest, family, arm, original, ack,
                                       ("GET", arm["read_target"], 200,
                                        canonical_json_bytes(observed)))
    assert certified.original_identity_sha256 == original.identity_hash
    with pytest.raises(PaperRunnerError):
        certify_h1_constructor(manifest, family, arm, original,
                               PaperHTTPResult(DispatchFacts(True, True), b"", "synthetic"),
                               ("GET", arm["read_target"], 200,
                                canonical_json_bytes(observed)))
    dispatched = []
    with pytest.raises(PaperRunnerError, match="limit exceeded"):
        run_recovery(initial_world_facts=certified,
                     **{**kwargs, "dispatch": lambda req: dispatched.append(req) or ack})
    assert len(dispatched) == 3


def test_concrete_fireworks_continuation_uses_frozen_sheets_tools_offline(manifest, tmp_path):
    family = manifest["families"][0]
    semantic = family["target_semantic_m"]
    original = canonical_json_bytes({
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "original-call", "type": "function",
                        "function": {"name": "append_row",
                                     "arguments": canonical_json_bytes(semantic).decode()}}]})
    payloads = []

    def completion(tool_calls):
        return {"id": "synthetic-completion", "model": family["model_config"]["model"]["name"],
                "choices": [{"finish_reason": "tool_calls" if tool_calls else "stop",
                             "message": {"role": "assistant", "content": None,
                                         "tool_calls": tool_calls}}]}

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        if len(payloads) == 1:
            data = completion([{"id": "read-1", "type": "function",
                                "function": {"name": "list_rows", "arguments": "{}"}}])
        else:
            data = completion([])
        return httpx.Response(200, json=data)

    client = SheetsFireworksContinuation(api_key="synthetic", intended=semantic,
                                         transport=httpx.MockTransport(handler))
    base = family["model_config"]["regeneration"]["seed"]
    common = manifest["model_visible_common"]
    first = RecoveryContext(family["user_task"], original, common["system_message"],
                            common["ambiguity_text"], None, 0, base,
                            family["model_config"], common["tools"])
    assert client(first) == ModelDecision("list_rows")
    second = RecoveryContext(family["user_task"], original, common["system_message"],
                             common["ambiguity_text"], {"rows": [], "read_complete": True},
                             1, base + 1, family["model_config"], common["tools"])
    assert client(second) == ModelDecision("finish")
    client.close()
    assert [p["seed"] for p in payloads] == [base, base + 1]
    assert payloads[0]["tools"] == [{"type": "function", "function": t} for t in common["tools"]]
    assert payloads[0]["messages"][3] == {"role": "tool", "tool_call_id": "original-call",
                                          "content": common["ambiguity_text"]}
    assert payloads[1]["messages"][-1] == {"role": "tool", "tool_call_id": "read-1",
                                             "content": '{"read_complete":true,"rows":[]}'}
    assert all("sheet_id" not in json.dumps(p["messages"]) for p in payloads)

    bad_original = canonical_json_bytes({
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "original-call", "type": "function",
                        "function": {"name": "append_row", "arguments": "{}"}}]})
    blocked = SheetsFireworksContinuation(api_key="synthetic", intended=semantic,
                                          transport=httpx.MockTransport(handler))
    with pytest.raises(SheetsModelError):
        blocked(RecoveryContext(family["user_task"], bad_original, common["system_message"],
                                common["ambiguity_text"], None, 0, base,
                                family["model_config"], common["tools"]))
    blocked.close()

    arm = next(a for a in family["arms"] if a["hidden_world"] == "H0"
               and a["policy"] == "LLM_REGENERATION")
    path = tmp_path / "original.json"
    store_original(path, prepare_paper_append(arm, semantic["item"], semantic["detail"]))
    payloads.clear()
    integrated = SheetsFireworksContinuation(api_key="synthetic", intended=semantic,
                                              transport=httpx.MockTransport(handler))
    result = run_recovery(
        manifest=manifest, family=family, arm=arm, original_path=path,
        initial_world_facts=DispatchFacts(), original_model_message=original,
        model_visible_common=common,
        dispatch=lambda _: pytest.fail("model selected no mutation"),
        model_continue=integrated,
        list_rows=lambda _: {"rows": [], "read_complete": True})
    integrated.close()
    assert result.model_calls == 2 and [a.action for a in result.actions] == ["list_rows"]
    assert result.study2_paper_observations == 0

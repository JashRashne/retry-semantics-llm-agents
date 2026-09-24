"""Offline hostile checks for paper scope request, one-shot intent, and response."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from retry_semantics.study2 import sheets_paper_scope_provisioning as paper
from retry_semantics.study2.sheets_http_framing import ResponseFramingError


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("network forbidden in paper scope tests")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _titles() -> list[str]:
    return [f"RS2S_f{family:03d}_{world}_{policy}"
            for family in range(1, 65)
            for world in ("H0", "H1")
            for policy in ("EXACT_REPLAY", "LLM_REGENERATION")]


def _response() -> dict:
    return {"spreadsheetId": "provider-assigned-spreadsheet-id",
            "properties": {"title": paper.SPREADSHEET_TITLE},
            "sheets": [{"properties": {"sheetId": 10000 + index,
                "title": title, "sheetType": "GRID",
                "gridProperties": {"rowCount": 100, "columnCount": 3}}}
                for index, title in enumerate(reversed(_titles()))]}


def _code_identity() -> dict[str, str]:
    return {"commit": "a" * 40, "source_sha256": "b" * 64}


def _fake_execution(monkeypatch: pytest.MonkeyPatch, evidence_root: Path, behavior):
    monkeypatch.setattr(paper, "_committed_code_identity", lambda _root: _code_identity())
    monkeypatch.setattr(paper, "EVIDENCE_ROOT", evidence_root)
    calls = []

    def transport(host, port, method, target, body, bearer):
        calls.append((host, port, method, target, body, bearer))
        assert host == "sheets.googleapis.com"
        assert port == 443
        assert method == "POST"
        assert target == (
            "/v4/spreadsheets?fields=spreadsheetId%2Cproperties%28title%29%2Csheets%28properties%28"
            "sheetId%2Ctitle%2CsheetType%2CgridProperties%28rowCount%2CcolumnCount%29%29%29"
        )
        assert body == (paper.REPOSITORY_ROOT / paper.REQUEST_PATH).read_bytes()
        return behavior()

    result = paper.execute_create_once(
        transport, "SECRET_BEARER_SENTINEL", execute_provisioning=True,
        operator_confirmation=paper.OPERATOR_CONFIRMATION,
    )
    assert len(calls) == 1
    assert calls[0][5] == "SECRET_BEARER_SENTINEL"
    return result, calls


def test_frozen_inputs_and_request_rebuild() -> None:
    assert paper.NAMESPACE == "76b0af67d7eece50cb12167e7ec374b9"
    assert paper.SPREADSHEET_TITLE == (
        "retry-semantics-study2-sheets-primary-v1-76b0af67d7eece50cb12167e7ec374b9"
    )
    assert paper.SOURCE_SHA256 == {
        "research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md":
            "15a2357e99df0c856f99b8b5419e923be927cdfeef7535be4d21a475762e6109",
        "research/study2/sheets/GOOGLE_SHEETS_PAPER_NAMESPACE_RESERVATION_V1.json":
            "a8a8bcd2751c56b05e9a9a569a6ad5f16e7d260b6a8ce5fb57dd244aef594506",
        "src/retry_semantics/study2/sheets_paper_registry.py":
            "09bec0ece06bacefd357a2067f4c3a6955347825fa692e6ad587d14e1d746fa8",
        "research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md":
            "b88d13c059d1716b1528386d2446a53e770e7c078e223e46aefa8f9daba98a2e",
        "research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json":
            "f85e49303094292bd4472e83aeda35a1b8c65fa97d42b33cf298904d0cabdf69",
        "research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md":
            "d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2",
    }
    for relative, expected in paper.SOURCE_SHA256.items():
        assert _sha((paper.REPOSITORY_ROOT / relative).read_bytes()) == expected
    registry = json.loads((paper.REPOSITORY_ROOT / paper.REGISTRY_PATH).read_bytes())
    assert len(registry["reservations"]) == 256
    assert [row["tab_title"] for row in registry["reservations"]] == _titles()
    raw = (paper.REPOSITORY_ROOT / paper.REQUEST_PATH).read_bytes()
    assert len(raw) == 31855
    assert _sha(raw) == "6596f530ba6fb5799b65c48dc73c84a8a4265b515bfc3b83473176ea1747e880"
    assert raw == paper.build_sheets_paper_create_request()
    assert raw == paper.build_sheets_paper_create_request()
    assert not raw.endswith(b"\n")
    assert raw == _canonical(json.loads(raw))
    assert paper.validate_sheets_paper_create_request(raw) == json.loads(raw)
    assert paper.canonicalize_sheets_paper_create_request(json.loads(raw)) == raw


def test_exact_request_topology_and_http_envelope() -> None:
    value = json.loads((paper.REPOSITORY_ROOT / paper.REQUEST_PATH).read_bytes())
    assert set(value) == {"properties", "sheets"}
    assert value["properties"] == {"title": paper.SPREADSHEET_TITLE}
    assert len(value["sheets"]) == 256
    assert [sheet["properties"]["title"] for sheet in value["sheets"]] == _titles()
    assert len(set(_titles())) == 256
    assert all(sheet == {"properties": {"gridProperties": {"columnCount": 3, "rowCount": 100},
               "sheetType": "GRID", "title": title}}
               for sheet, title in zip(value["sheets"], _titles(), strict=True))
    assert b"sheetId" not in _canonical(value)
    assert paper.METHOD == "POST" and paper.HOST == "sheets.googleapis.com" and paper.PORT == 443
    assert paper.TARGET == (
        "/v4/spreadsheets?fields=spreadsheetId%2Cproperties%28title%29%2Csheets%28properties%28"
        "sheetId%2Ctitle%2CsheetType%2CgridProperties%28rowCount%2CcolumnCount%29%29%29"
    )
    assert paper.OAUTH_SCOPE == "https://www.googleapis.com/auth/drive.file"


@pytest.mark.parametrize("mutation", ["request_sha", "wrong_title", "missing_tab", "extra_tab",
                                     "duplicate_tab", "supplied_sheet_id"])
def test_request_tampering_refused(mutation: str) -> None:
    raw = (paper.REPOSITORY_ROOT / paper.REQUEST_PATH).read_bytes()
    if mutation == "request_sha":
        with pytest.raises(paper.ProvisioningRefused):
            paper.validate_sheets_paper_create_request(raw, expected_sha256="0" * 64)
        return
    value = json.loads(raw)
    if mutation == "wrong_title":
        value["properties"]["title"] = "wrong"
    elif mutation == "missing_tab":
        value["sheets"].pop()
    elif mutation == "extra_tab":
        value["sheets"].append({"properties": {"title": "EXTRA"}})
    elif mutation == "duplicate_tab":
        value["sheets"][1] = value["sheets"][0]
    else:
        value["sheets"][0]["properties"]["sheetId"] = 1
    with pytest.raises(paper.ProvisioningRefused):
        paper.validate_sheets_paper_create_request(_canonical(value))


def test_registry_hash_tampering_refused(tmp_path: Path) -> None:
    for relative in paper.SOURCE_SHA256:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((paper.REPOSITORY_ROOT / relative).read_bytes())
    registry = tmp_path / paper.REGISTRY_PATH
    registry.write_bytes(registry.read_bytes() + b" ")
    with pytest.raises(paper.ProvisioningRefused, match="frozen input hash mismatch"):
        paper.build_sheets_paper_create_request(tmp_path)


def test_intent_identity_and_exclusive_write(tmp_path: Path) -> None:
    intent = paper.build_provisioning_intent(
        _code_identity(), operator_confirmation=paper.OPERATOR_CONFIRMATION,
    )
    request = (paper.REPOSITORY_ROOT / paper.REQUEST_PATH).read_bytes()
    assert intent == {
        "schema": "sheets-paper-scope-create-intent-v1",
        "purpose": "Study-2 paper scope provisioning",
        "state": "CREATE_INTENT_PERSISTED_NO_PROVIDER_RESULT",
        "provisioning_code_identity": _code_identity(),
        "manifest_input_sha256": paper.MANIFEST_INPUT_SHA256,
        "namespace_registry_sha256": paper.REGISTRY_SHA256,
        "create_request_sha256": _sha(request),
        "run_namespace": paper.NAMESPACE,
        "spreadsheet_title": paper.SPREADSHEET_TITLE,
        "expected_tab_count": 256,
        "http_method": "POST", "http_host": "sheets.googleapis.com", "http_port": 443,
        "http_target": paper.TARGET,
        "canonical_body_sha256": _sha(request), "canonical_body_bytes": len(request),
        "oauth_scope": paper.OAUTH_SCOPE,
        "operator_confirmation": paper.OPERATOR_CONFIRMATION,
    }
    path = tmp_path / paper.INTENT_NAME
    raw = paper.write_provisioning_intent_exclusive(path, intent)
    assert raw == path.read_bytes() == _canonical(intent)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        paper.write_provisioning_intent_exclusive(path, intent)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("field", ["create_request_sha256", "namespace_registry_sha256"])
def test_intent_hash_tampering_refused(tmp_path: Path, field: str) -> None:
    intent = paper.build_provisioning_intent(
        _code_identity(), operator_confirmation=paper.OPERATOR_CONFIRMATION,
    )
    intent[field] = "0" * 64
    with pytest.raises(paper.ProvisioningRefused, match="differs"):
        paper.write_provisioning_intent_exclusive(tmp_path / paper.INTENT_NAME, intent)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", ["partial_write", "file_fsync"])
def test_intent_failure_leaves_spent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    intent = paper.build_provisioning_intent(
        _code_identity(), operator_confirmation=paper.OPERATOR_CONFIRMATION,
    )
    path = tmp_path / paper.INTENT_NAME
    if failure == "partial_write":
        real_write = os.write
        calls = 0

        def partial(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, data[:4])
            raise OSError("injected")

        with monkeypatch.context() as patch:
            patch.setattr(os, "write", partial)
            with pytest.raises(OSError):
                paper.write_provisioning_intent_exclusive(path, intent)
        assert path.read_bytes() == b'{"ca'
    else:
        with monkeypatch.context() as patch:
            patch.setattr(os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("injected")))
            with pytest.raises(OSError):
                paper.write_provisioning_intent_exclusive(path, intent)
        assert path.exists()
    with pytest.raises(FileExistsError):
        paper.write_provisioning_intent_exclusive(path, intent)


@pytest.mark.parametrize("flag,confirmation", [
    (False, paper.OPERATOR_CONFIRMATION), (True, "wrong"), (True, "explicit_pre_data_sheets_paper_scope_create"),
])
def test_explicit_gates_refuse_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: bool, confirmation: str,
) -> None:
    monkeypatch.setattr(paper, "EVIDENCE_ROOT", tmp_path)
    calls = []

    def transport(*args):
        calls.append(args)
        raise AssertionError("must not dispatch")

    with pytest.raises(paper.ProvisioningRefused):
        paper.execute_create_once(transport, "SECRET_BEARER_SENTINEL",
                                  execute_provisioning=flag, operator_confirmation=confirmation)
    assert calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_visible_failure_is_one_shot_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    result, calls = _fake_execution(monkeypatch, tmp_path, lambda: (status, b"{}"))
    assert result["state"] == "VISIBLE_HTTP_FAILURE_TERMINAL"
    assert result["http_status"] == status
    assert result["reason"] == "VISIBLE_NON_200"
    assert "scope_binding_candidate" not in result
    assert json.loads((tmp_path / paper.RESULT_NAME).read_bytes()) == result
    with pytest.raises(FileExistsError):
        paper.execute_create_once(lambda *args: calls.append(args),
                                  "SECRET_BEARER_SENTINEL", execute_provisioning=True,
                                  operator_confirmation=paper.OPERATOR_CONFIRMATION)
    assert len(calls) == 1


def test_fixed_evidence_root_cannot_be_bypassed_by_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = tmp_path / "fixed"
    alternate = tmp_path / "alternate"
    fixed.mkdir()
    alternate.mkdir()
    _, calls = _fake_execution(monkeypatch, fixed, lambda: (403, b"{}"))
    assert "evidence_root" not in inspect.signature(paper.execute_create_once).parameters
    with pytest.raises(FileExistsError):
        paper.execute_create_once(lambda *args: calls.append(args),
            "SECRET_BEARER_SENTINEL", execute_provisioning=True,
            operator_confirmation=paper.OPERATOR_CONFIRMATION)
    with pytest.raises(TypeError):
        paper.execute_create_once(lambda *args: calls.append(args),
            "SECRET_BEARER_SENTINEL", execute_provisioning=True,
            operator_confirmation=paper.OPERATOR_CONFIRMATION, evidence_root=alternate)
    assert len(calls) == 1
    assert list(alternate.iterdir()) == []


@pytest.mark.parametrize("failure", ["timeout", "truncation", "malformed_success"])
def test_ambiguous_response_is_one_shot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    def behavior():
        if failure == "timeout":
            raise TimeoutError("SECRET_BEARER_SENTINEL")
        if failure == "truncation":
            raise ResponseFramingError("body_incomplete")
        return 200, b"{"

    result, calls = _fake_execution(monkeypatch, tmp_path, behavior)
    assert result["state"] == "PROVISIONING_OUTCOME_UNCERTAIN"
    assert result["dispatch_initiated"] is True
    assert result["response_sha256"] is None
    assert len(calls) == 1
    for path in tmp_path.iterdir():
        assert b"SECRET_BEARER_SENTINEL" not in path.read_bytes()


def test_result_persistence_failure_leaves_spent_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(paper, "_committed_code_identity", lambda _root: _code_identity())
    monkeypatch.setattr(paper, "EVIDENCE_ROOT", tmp_path)
    real_write = paper._write_exclusive

    def fail_result(path, value):
        if path.name == paper.RESULT_NAME:
            raise OSError("injected")
        return real_write(path, value)

    monkeypatch.setattr(paper, "_write_exclusive", fail_result)
    calls = []

    def transport(*args):
        calls.append(args)
        return 200, _canonical(_response())

    result = paper.execute_create_once(transport, "SECRET_BEARER_SENTINEL",
        execute_provisioning=True, operator_confirmation=paper.OPERATOR_CONFIRMATION)
    assert result["state"] == "PROVISIONING_OUTCOME_UNCERTAIN"
    assert result["reason"] == "RESULT_PERSISTENCE_FAILURE"
    assert len(calls) == 1
    assert (tmp_path / paper.INTENT_NAME).exists()
    assert (tmp_path / paper.DISPATCH_NAME).exists()
    with pytest.raises(FileExistsError):
        paper.execute_create_once(transport, "SECRET_BEARER_SENTINEL",
            execute_provisioning=True, operator_confirmation=paper.OPERATOR_CONFIRMATION)
    assert len(calls) == 1


def test_success_response_and_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = _canonical(_response())
    identity = paper.validate_create_response(200, body)
    assert identity["spreadsheet_id"] == "provider-assigned-spreadsheet-id"
    assert len(identity["sheet_ids_by_title"]) == 256
    result, calls = _fake_execution(monkeypatch, tmp_path, lambda: (200, body))
    assert len(calls) == 1
    assert result["state"] == "CREATE_RESPONSE_VALIDATED_PENDING_AUDIT"
    persisted = (tmp_path / paper.RESULT_NAME).read_bytes()
    candidate = result["scope_binding_candidate"]
    assert candidate == paper.build_scope_binding_candidate(body, persisted)
    assert candidate["status"] == "PROVISIONED_SCOPE_PENDING_INDEPENDENT_AUDIT"
    assert candidate["validated_create_result_evidence_sha256"] == _sha(persisted)
    assert candidate["spreadsheet_id"] == identity["spreadsheet_id"]
    assert json.loads(persisted)["sheet_ids_by_title"] == identity["sheet_ids_by_title"]
    assert len(candidate["arms"]) == 256
    assert [row["tab_title"] for row in candidate["arms"]] == _titles()
    assert len({row["sheet_id"] for row in candidate["arms"]}) == 256
    assert all(row["range"] == "A1:C100" for row in candidate["arms"])
    assert not {"blank_baseline", "marker_absent", "writer_exclusivity", "principal_qualified",
                "append_placement", "observer_authority", "collection_ready"}.intersection(candidate)
    for value in (candidate, result):
        assert b"SECRET_BEARER_SENTINEL" not in _canonical(value)
    for path in tmp_path.iterdir():
        assert b"SECRET_BEARER_SENTINEL" not in path.read_bytes()


@pytest.mark.parametrize("mutation", [
    "duplicate_id", "duplicate_title", "missing_title", "extra_title", "wrong_type",
    "wrong_type_data_source",
    "wrong_rows", "wrong_columns", "absent_spreadsheet_id", "wrong_spreadsheet_title",
    "missing_sheet_id", "boolean_sheet_id", "missing_sheet", "extra_sheet", "malformed_json",
])
def test_hostile_create_response_rejected(mutation: str) -> None:
    value = _response()
    sheets = value["sheets"]
    first = sheets[0]["properties"]
    if mutation == "duplicate_id":
        sheets[1]["properties"]["sheetId"] = first["sheetId"]
    elif mutation == "duplicate_title":
        sheets[1]["properties"]["title"] = first["title"]
    elif mutation == "missing_title":
        del first["title"]
    elif mutation == "extra_title":
        first["title"] = "EXTRA"
    elif mutation == "wrong_type":
        first["sheetType"] = "OBJECT"
    elif mutation == "wrong_type_data_source":
        first["sheetType"] = "DATA_SOURCE"
    elif mutation == "wrong_rows":
        first["gridProperties"]["rowCount"] = 101
    elif mutation == "wrong_columns":
        first["gridProperties"]["columnCount"] = 4
    elif mutation == "absent_spreadsheet_id":
        del value["spreadsheetId"]
    elif mutation == "wrong_spreadsheet_title":
        value["properties"]["title"] = "wrong"
    elif mutation == "missing_sheet_id":
        del first["sheetId"]
    elif mutation == "boolean_sheet_id":
        first["sheetId"] = True
    elif mutation == "missing_sheet":
        sheets.pop()
    elif mutation == "extra_sheet":
        sheets.append({"properties": {"sheetId": 99999, "title": "EXTRA"}})
    else:
        with pytest.raises(paper.ProvisioningRefused):
            paper.validate_create_response(200, b"{")
        return
    with pytest.raises(paper.ProvisioningRefused):
        paper.validate_create_response(200, _canonical(value))


def test_invalid_result_evidence_cannot_build_candidate() -> None:
    body = _canonical(_response())
    fake = {"state": "CREATE_RESPONSE_VALIDATED_PENDING_AUDIT", "http_status": 200,
            "response_sha256": "0" * 64}
    with pytest.raises(paper.ProvisioningRefused):
        paper.build_scope_binding_candidate(body, _canonical(fake))


def test_real_operational_root_and_scope_binding_not_created() -> None:
    assert not (paper.REPOSITORY_ROOT /
                "research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_BINDING_V1.json").exists()
    assert not paper.EVIDENCE_ROOT.exists()

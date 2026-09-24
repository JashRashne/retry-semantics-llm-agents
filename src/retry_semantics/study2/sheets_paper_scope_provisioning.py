"""Offline paper scope create plan and one-shot, injected-transport gate.

There is no network transport, OAuth preparer, CLI, or import-time action here.
An eventual live adapter must supply a preprepared bearer and strictly framed
response; this module cannot create a spreadsheet on its own.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2.sheets_paper_registry import (
    REPOSITORY_ROOT, REGISTRY_PATH, load_sheets_namespace_reservation,
)

MANIFEST_INPUT_PATH = "research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md"
REQUEST_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_CREATE_REQUEST_V1.json")
MODULE_PATH = "src/retry_semantics/study2/sheets_paper_scope_provisioning.py"
NAMESPACE = "76b0af67d7eece50cb12167e7ec374b9"
SPREADSHEET_TITLE = "retry-semantics-study2-sheets-primary-v1-" + NAMESPACE
MANIFEST_INPUT_SHA256 = "15a2357e99df0c856f99b8b5419e923be927cdfeef7535be4d21a475762e6109"
REGISTRY_SHA256 = "a8a8bcd2751c56b05e9a9a569a6ad5f16e7d260b6a8ce5fb57dd244aef594506"
REGISTRY_CODE_SHA256 = "09bec0ece06bacefd357a2067f4c3a6955347825fa692e6ad587d14e1d746fa8"
SEMANTICS_SHA256 = "b88d13c059d1716b1528386d2446a53e770e7c078e223e46aefa8f9daba98a2e"
CATALOGUE_SHA256 = "f85e49303094292bd4472e83aeda35a1b8c65fa97d42b33cf298904d0cabdf69"
PROTOCOL_SHA256 = "d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2"
SOURCE_SHA256 = {
    MANIFEST_INPUT_PATH: MANIFEST_INPUT_SHA256,
    REGISTRY_PATH.as_posix(): REGISTRY_SHA256,
    "src/retry_semantics/study2/sheets_paper_registry.py": REGISTRY_CODE_SHA256,
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md": SEMANTICS_SHA256,
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json": CATALOGUE_SHA256,
    "research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md": PROTOCOL_SHA256,
}
HOST = "sheets.googleapis.com"
PORT = 443
METHOD = "POST"
CREATE_FIELDS = "spreadsheetId,properties(title),sheets(properties(sheetId,title,sheetType,gridProperties(rowCount,columnCount)))"
TARGET = "/v4/spreadsheets?fields=spreadsheetId%2Cproperties%28title%29%2Csheets%28properties%28sheetId%2Ctitle%2CsheetType%2CgridProperties%28rowCount%2CcolumnCount%29%29%29"
OAUTH_SCOPE = "https://www.googleapis.com/auth/drive.file"
OPERATOR_CONFIRMATION = "EXPLICIT_PRE_DATA_SHEETS_PAPER_SCOPE_CREATE"
EVIDENCE_ROOT = Path.home() / "Library/Application Support/RetrySemantics" / (
    "sheets-paper-scope-v1-" + NAMESPACE
)
INTENT_NAME = "create-intent.json"
DISPATCH_NAME = "create-dispatch.json"
RESULT_NAME = "create-result.json"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class ProvisioningRefused(ValueError):
    """A fixed, nonsecret refusal; never wraps provider or bearer text."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ProvisioningRefused("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(_value: str) -> Any:
    raise ProvisioningRefused("invalid JSON constant")


def _parse(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise ProvisioningRefused("JSON must be bytes")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_unique,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProvisioningRefused("invalid UTF-8 JSON") from None


def _registry(root: Path) -> dict[str, Any]:
    for relative, digest in SOURCE_SHA256.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or _sha(path.read_bytes()) != digest:
            raise ProvisioningRefused("frozen input hash mismatch")
    value = load_sheets_namespace_reservation(root)
    if (value["run_namespace"] != NAMESPACE or value["spreadsheet_title"] != SPREADSHEET_TITLE
            or value["family_count"] != 64 or value["arm_count"] != 256
            or len(value["reservations"]) != 256):
        raise ProvisioningRefused("frozen registry identity mismatch")
    return value


def canonicalize_sheets_paper_create_request(value: dict[str, Any]) -> bytes:
    if type(value) is not dict:
        raise ProvisioningRefused("create request must be an object")
    return canonical_json_bytes(value)


def build_sheets_paper_create_request(root: Path = REPOSITORY_ROOT) -> bytes:
    """Rebuild canonical bytes solely from the frozen local reservation."""
    registry = _registry(root)
    return canonicalize_sheets_paper_create_request({
        "properties": {"title": registry["spreadsheet_title"]},
        "sheets": [{"properties": {
            "gridProperties": {"columnCount": 3, "rowCount": 100},
            "sheetType": "GRID", "title": row["tab_title"],
        }} for row in registry["reservations"]],
    })


def validate_sheets_paper_create_request(
    raw: bytes, *, expected_sha256: str | None = None, root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    value = _parse(raw)
    if (type(value) is not dict or canonical_json_bytes(value) != raw
            or raw != build_sheets_paper_create_request(root)
            or expected_sha256 is not None and _sha(raw) != expected_sha256):
        raise ProvisioningRefused("create request differs from frozen inputs")
    return value


def _checked_request_bytes(root: Path) -> bytes:
    path = root / REQUEST_PATH
    if path.is_symlink() or not path.is_file():
        raise ProvisioningRefused("canonical create request unavailable")
    raw = path.read_bytes()
    validate_sheets_paper_create_request(raw, root=root)
    return raw


def _committed_code_identity(root: Path) -> dict[str, str]:
    """Refuse if the running module differs from its current committed blob."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().strip()
        blob = subprocess.run(["git", "show", "HEAD:" + MODULE_PATH], cwd=root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
        current = (root / MODULE_PATH).read_bytes()
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        raise ProvisioningRefused("committed provisioning code unavailable") from None
    if _COMMIT.fullmatch(head) is None or blob != current:
        raise ProvisioningRefused("provisioning code differs from committed identity")
    return {"commit": head, "source_sha256": _sha(blob)}


def build_provisioning_intent(
    code_identity: dict[str, str], *, operator_confirmation: str,
    root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    if (type(code_identity) is not dict or set(code_identity) != {"commit", "source_sha256"}
            or type(code_identity["commit"]) is not str or _COMMIT.fullmatch(code_identity["commit"]) is None
            or type(code_identity["source_sha256"]) is not str
            or _SHA256.fullmatch(code_identity["source_sha256"]) is None
            or operator_confirmation != OPERATOR_CONFIRMATION):
        raise ProvisioningRefused("invalid code identity or operator confirmation")
    body = _checked_request_bytes(root)
    return {
        "schema": "sheets-paper-scope-create-intent-v1",
        "purpose": "Study-2 paper scope provisioning",
        "state": "CREATE_INTENT_PERSISTED_NO_PROVIDER_RESULT",
        "provisioning_code_identity": code_identity,
        "manifest_input_sha256": MANIFEST_INPUT_SHA256,
        "namespace_registry_sha256": REGISTRY_SHA256,
        "create_request_sha256": _sha(body),
        "run_namespace": NAMESPACE,
        "spreadsheet_title": SPREADSHEET_TITLE,
        "expected_tab_count": 256,
        "http_method": METHOD,
        "http_host": HOST,
        "http_port": PORT,
        "http_target": TARGET,
        "canonical_body_sha256": _sha(body),
        "canonical_body_bytes": len(body),
        "oauth_scope": OAUTH_SCOPE,
        "operator_confirmation": operator_confirmation,
    }


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in (errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP):
            return
        raise
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP):
                raise
    finally:
        os.close(fd)


def _write_exclusive(path: Path, value: dict[str, Any]) -> bytes:
    if not isinstance(path, Path) or path.parent.is_symlink() or not path.parent.is_dir():
        raise ProvisioningRefused("evidence directory unavailable")
    raw = canonical_json_bytes(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        written = 0
        while written < len(raw):
            count = os.write(fd, raw[written:])
            if count <= 0:
                raise OSError("incomplete evidence write")
            written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)
    return raw


def write_provisioning_intent_exclusive(
    path: Path, intent: dict[str, Any], *, root: Path = REPOSITORY_ROOT,
) -> bytes:
    """Spend the fixed create path durably; never replace or remove residue."""
    if (not isinstance(path, Path) or path.name != INTENT_NAME
            or type(intent) is not dict
            or intent.get("state") != "CREATE_INTENT_PERSISTED_NO_PROVIDER_RESULT"
            or intent.get("operator_confirmation") != OPERATOR_CONFIRMATION
            or intent.get("http_target") != TARGET or intent.get("http_method") != METHOD):
        raise ProvisioningRefused("invalid provisioning intent")
    expected = build_provisioning_intent(intent.get("provisioning_code_identity"),
        operator_confirmation=OPERATOR_CONFIRMATION, root=root)
    if intent != expected:
        raise ProvisioningRefused("provisioning intent differs from frozen inputs")
    return _write_exclusive(path, intent)


def validate_create_response(status: int, raw: bytes, *, root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Validate projected identity and GRID shape, never cell emptiness."""
    if type(status) is not int or status != 200:
        raise ProvisioningRefused("create response status is not 200")
    value = _parse(raw)
    expected = _registry(root)
    if (type(value) is not dict or type(value.get("spreadsheetId")) is not str
            or not value["spreadsheetId"].strip() or type(value.get("properties")) is not dict
            or value["properties"].get("title") != SPREADSHEET_TITLE
            or type(value.get("sheets")) is not list or len(value["sheets"]) != 256):
        raise ProvisioningRefused("create response identity or sheet count invalid")
    expected_titles = {row["tab_title"] for row in expected["reservations"]}
    found: dict[str, int] = {}
    ids: set[int] = set()
    for sheet in value["sheets"]:
        if type(sheet) is not dict or type(sheet.get("properties")) is not dict:
            raise ProvisioningRefused("malformed returned sheet")
        props = sheet["properties"]
        title, sheet_id = props.get("title"), props.get("sheetId")
        grid = props.get("gridProperties")
        if (type(title) is not str or title not in expected_titles or title in found
                or type(sheet_id) is not int or sheet_id in ids
                or props.get("sheetType") != "GRID" or type(grid) is not dict
                or type(grid.get("rowCount")) is not int or grid["rowCount"] != 100
                or type(grid.get("columnCount")) is not int or grid["columnCount"] != 3):
            raise ProvisioningRefused("returned sheet identity or shape invalid")
        found[title] = sheet_id
        ids.add(sheet_id)
    if set(found) != expected_titles or len(ids) != 256:
        raise ProvisioningRefused("returned tab set invalid")
    return {"spreadsheet_id": value["spreadsheetId"], "sheet_ids_by_title": found,
            "response_sha256": _sha(raw)}


def build_scope_binding_candidate(
    response_body: bytes, validated_result_evidence: bytes, *, root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    identity = validate_create_response(200, response_body, root=root)
    result = _parse(validated_result_evidence)
    if (type(result) is not dict or canonical_json_bytes(result) != validated_result_evidence
            or result.get("schema") != "sheets-paper-scope-create-result-v1"
            or result.get("state") != "CREATE_RESPONSE_VALIDATED_PENDING_AUDIT"
            or result.get("http_status") != 200
            or result.get("dispatch_initiated") is not True
            or type(result.get("intent_sha256")) is not str
            or _SHA256.fullmatch(result["intent_sha256"]) is None
            or result.get("reason") is not None
            or result.get("response_sha256") != identity["response_sha256"]
            or result.get("spreadsheet_id") != identity["spreadsheet_id"]
            or result.get("sheet_ids_by_title") != identity["sheet_ids_by_title"]):
        raise ProvisioningRefused("validated create-result evidence mismatch")
    registry = _registry(root)
    return {
        "schema": "sheets-paper-scope-binding-candidate-v1",
        "status": "PROVISIONED_SCOPE_PENDING_INDEPENDENT_AUDIT",
        "spreadsheet_id": identity["spreadsheet_id"],
        "spreadsheet_title": SPREADSHEET_TITLE,
        "run_namespace": NAMESPACE,
        "manifest_input_sha256": MANIFEST_INPUT_SHA256,
        "namespace_registry_sha256": REGISTRY_SHA256,
        "create_request_sha256": _sha(_checked_request_bytes(root)),
        "validated_create_result_evidence_sha256": _sha(validated_result_evidence),
        "arms": [{"family_id": row["family_id"], "arm_id": row["arm_id"],
                  "tab_title": row["tab_title"],
                  "sheet_id": identity["sheet_ids_by_title"][row["tab_title"]],
                  "range": "A1:C100"} for row in registry["reservations"]],
    }


def execute_create_once(
    transport: Callable[[str, int, str, str, bytes, str], tuple[int, bytes]],
    prepared_bearer: str, *, execute_provisioning: bool, operator_confirmation: str,
    root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Injected transport only; one durable intent, then at most one call.

    The eventual live transport must perform strict HTTP framing and raise on
    truncation. This wrapper never equates local call entry with remote commit.
    """
    if execute_provisioning is not True or operator_confirmation != OPERATOR_CONFIRMATION:
        raise ProvisioningRefused("explicit pre-data create authorization absent")
    if type(prepared_bearer) is not str or not prepared_bearer:
        raise ProvisioningRefused("prepared bearer unavailable")
    evidence_root = EVIDENCE_ROOT
    if not isinstance(evidence_root, Path) or not evidence_root.is_dir() or evidence_root.is_symlink():
        raise ProvisioningRefused("evidence directory unavailable")
    code_identity = _committed_code_identity(root)
    body = _checked_request_bytes(root)
    intent = build_provisioning_intent(code_identity, operator_confirmation=operator_confirmation, root=root)
    intent_raw = write_provisioning_intent_exclusive(evidence_root / INTENT_NAME, intent, root=root)
    intent_sha = _sha(intent_raw)
    result: dict[str, Any] = {
        "schema": "sheets-paper-scope-create-result-v1",
        "state": "PROVISIONING_OUTCOME_UNCERTAIN",
        "intent_sha256": intent_sha,
        "dispatch_initiated": False,
        "http_status": None,
        "response_sha256": None,
        "spreadsheet_id": None,
        "sheet_ids_by_title": None,
        "reason": "DISPATCH_EVIDENCE_FAILURE",
    }
    try:
        _write_exclusive(evidence_root / DISPATCH_NAME, {
            "schema": "sheets-paper-scope-create-dispatch-v1",
            "intent_sha256": intent_sha,
            "meaning": "dispatch-call-pending-no-local-send-or-remote-commit-claim",
        })
    except Exception:
        # Intent is spent even if dispatch evidence cannot be persisted.
        return result
    result["dispatch_initiated"] = True
    result["reason"] = "TRANSPORT_OR_FRAMING_UNCERTAIN"
    response_body: bytes | None = None
    try:
        status, response_body = transport(HOST, PORT, METHOD, TARGET, body, prepared_bearer)
        if type(status) is not int or not 100 <= status <= 599:
            raise ProvisioningRefused("invalid transport status")
        result["http_status"] = status
        if status == 200:
            if type(response_body) is not bytes:
                raise ProvisioningRefused("invalid response bytes")
            identity = validate_create_response(status, response_body, root=root)
            result.update(state="CREATE_RESPONSE_VALIDATED_PENDING_AUDIT",
                          response_sha256=identity["response_sha256"],
                          spreadsheet_id=identity["spreadsheet_id"],
                          sheet_ids_by_title=identity["sheet_ids_by_title"], reason=None)
        else:
            result.update(state="VISIBLE_HTTP_FAILURE_TERMINAL", reason="VISIBLE_NON_200")
    except Exception:
        # Never serialize an exception or provider body; remote effect unknown.
        result.update(state="PROVISIONING_OUTCOME_UNCERTAIN",
                      response_sha256=None, spreadsheet_id=None, sheet_ids_by_title=None,
                      reason="TRANSPORT_OR_RESPONSE_UNCERTAIN")
    try:
        result_raw = _write_exclusive(evidence_root / RESULT_NAME, result)
    except Exception:
        result.update(state="PROVISIONING_OUTCOME_UNCERTAIN", response_sha256=None,
                      spreadsheet_id=None, sheet_ids_by_title=None,
                      reason="RESULT_PERSISTENCE_FAILURE")
        return result
    if result["state"] == "CREATE_RESPONSE_VALIDATED_PENDING_AUDIT":
        result["scope_binding_candidate"] = build_scope_binding_candidate(
            response_body, result_raw, root=root,
        )
    return result

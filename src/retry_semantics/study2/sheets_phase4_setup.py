"""DRAFT one-shot setup actions. No action at import; no retries or cleanup."""
from __future__ import annotations

import http.client
import os
from pathlib import Path
import re
import ssl
import time
from urllib.parse import urlencode

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase4_control as control

CREATE_CONFIRMATION = "EXPLICIT_ONE_ENGINEERING_FIXTURE_CREATE"
CREATE_FIELDS = "spreadsheetId,properties(title),sheets(properties(sheetId,title,sheetType,gridProperties(rowCount,columnCount)))"
LEGACY_AUTH_METADATA_URI = "https://accounts.google.com/o/oauth2/auth"


@credentials.secret_safe
def load_client_config(path: Path, *, reviewed_public_hash: str):
    """Accept two Google Desktop auth metadata values; keep the frozen runtime endpoint."""
    p2.digest(reviewed_public_hash)
    p2.require(isinstance(path, Path) and path.is_absolute() and ".." not in path.parts
               and not path.is_relative_to(frozen.ROOT)
               and not any(p.is_symlink() for p in (path, *path.parents)))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        p2._private_fd(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            body = stream.read(16385)
        p2.require(len(body) <= 16384)
    finally:
        os.close(fd)
    obj = p2.strict_json(body)
    p2.require(type(obj) is dict and set(obj) == {"installed"})
    value = obj["installed"]
    p2.require(type(value) is dict and set(value) == {"client_id", "project_id", "auth_uri",
        "token_uri", "auth_provider_x509_cert_url", "client_secret", "redirect_uris"})
    p2.require(type(value["auth_uri"]) is str and value["auth_uri"] in
               (credentials.AUTH_URI, LEGACY_AUTH_METADATA_URI)
               and value["token_uri"] == credentials.TOKEN_URI
               and value["auth_provider_x509_cert_url"] == "https://www.googleapis.com/oauth2/v1/certs"
               and value["redirect_uris"] == ["http://localhost"])
    client = credentials.ClientConfig(value["client_id"], value["client_secret"], value["project_id"])
    p2.require(client.public_hash == reviewed_public_hash)
    return client


@credentials.secret_safe
def review_client(path: Path):
    """Review the exact Desktop shape; no secret hash or error context."""
    p2.require(path.is_absolute() and ".." not in path.parts
               and not path.is_relative_to(frozen.ROOT)
               and not any(p.is_symlink() for p in (path, *path.parents)))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        p2._private_fd(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            body = stream.read(16385)
        p2.require(len(body) <= 16384)
    finally:
        os.close(fd)
    obj = p2.strict_json(body)
    p2.require(type(obj) is dict and set(obj) == {"installed"})
    value = obj["installed"]
    p2.require(type(value) is dict)
    candidate = credentials.ClientConfig(value.get("client_id"), value.get("client_secret"),
                                         value.get("project_id"))
    # The same Phase 4 loader used at acquisition makes a second bounded read.
    # Neither read hashes or persists the secret-bearing document.
    client = load_client_config(path, reviewed_public_hash=candidate.public_hash)
    return control.validate_review({"schema": "sheets-phase4-client-review-v1",
        "public": client.public_projection(), "public_sha256": client.public_hash})


def oauth_intent(config, review):
    return {"schema": "sheets-phase4-oauth-intent-v1", "engineering_only": True,
            "operator_configuration_sha256": control.hash_public(config.projection()),
            "public_config_sha256": review["public_sha256"], "account_alias": config.account_alias,
            "meaning": "one-acquisition-spent-no-retry"}


@credentials.secret_safe
def acquire(config, review, attestation, pin, client_path, *, execute_oauth,
            operator_confirmation, present_url):
    p2.require(execute_oauth is True and operator_confirmation == credentials.ACQUISITION_CONFIRMATION)
    p2.require(client_path.is_absolute() and not client_path.is_relative_to(frozen.ROOT))
    p2.require(control.offline_preflight(config, review, attestation, pin)["status"] == "PASS")
    client = load_client_config(client_path, reviewed_public_hash=review["public_sha256"])
    p3.write_json(config.path("oauth-intent.json"), oauth_intent(config, review))
    token, metadata = credentials.DesktopPreparer(client).acquire(
        operator_confirmation=operator_confirmation, present_url=present_url,
        account_alias=config.account_alias, clock_uncertainty_seconds=config.runtime().clock_uncertainty_seconds,
        consent_seconds=config.consent_seconds, exchange_timeout_seconds=config.exchange_seconds)
    p2.require(token.expires_at - time.time() > config.minimum_handoff_seconds
               + token.clock_uncertainty_seconds)
    p3.write_json(config.path("acquisition.json"), metadata.projection())
    return token, metadata


def create_request(config):
    config.__post_init__()
    return {"properties": {"title": "RetrySemanticsEngineering-" + config.reservation_id},
            "sheets": [{"properties": {"sheetId": 1, "title": "RetrySemanticsEngineering",
                "sheetType": "GRID", "gridProperties": {"rowCount": 100, "columnCount": 3}}}]}


def create_intent(config, review):
    control.validate_review(review)
    return {"schema": "sheets-phase4-create-intent-v1", "engineering_only": True,
            "method": "POST", "host": frozen.HOST, "port": 443,
            "path": "/v4/spreadsheets?" + urlencode({"fields": CREATE_FIELDS}),
            "request": create_request(config), "scope": p1.SCOPE,
            "public_config_sha256": review["public_sha256"], "account_alias": config.account_alias,
            "operator_configuration_sha256": control.hash_public(config.projection()),
            "meaning": "create-may-have-committed-never-repeat"}


@credentials.secret_safe
def validated_identity(body, config, review):
    value = p2.strict_json(body)
    request = create_request(config)
    p2.require(type(value) is dict and set(value) == {"spreadsheetId", "properties", "sheets"}
               and value["properties"] == request["properties"] and value["sheets"] == request["sheets"])
    spreadsheet_id = value["spreadsheetId"]
    # Enforce frozen identity types (bool/int equality is insufficient).
    props = value["sheets"][0]["properties"]
    p2.require(type(props["sheetId"]) is int and type(props["gridProperties"]["rowCount"]) is int
               and type(props["gridProperties"]["columnCount"]) is int)
    p2.QualificationFixture(spreadsheet_id, 1, 100, config.reservation_id,
        p2.SameAppProvenance("created_by_same_app", review["public_sha256"], config.account_alias,
                            "0" * 64), "PROVISIONED")
    return spreadsheet_id


@credentials.secret_safe
def validate_create_result(result, config, review):
    p2.require(type(result) is dict and set(result) == {"schema", "engineering_only", "outcome",
        "intent_sha256", "http_status", "spreadsheet_id", "sheet_id", "rows", "columns"}
        and result["engineering_only"] is True
        and result == {"schema": "sheets-phase4-create-result-v1", "engineering_only": True,
            "outcome": "CREATE_RESPONSE_VALIDATED", "intent_sha256": control.hash_public(create_intent(config, review)),
            "http_status": 200, "spreadsheet_id": result["spreadsheet_id"], "sheet_id": 1,
            "rows": 100, "columns": 3})
    validated_identity(canonical_json_bytes({"spreadsheetId": result["spreadsheet_id"],
                       **create_request(config)}), config, review)
    p2.require(all(type(result[n]) is int for n in ("http_status", "sheet_id", "rows", "columns")))
    return result


@credentials.secret_safe
def provision(config, review, token, metadata, *, execute_provisioning, operator_confirmation):
    p2.require(execute_provisioning is True and operator_confirmation == CREATE_CONFIRMATION)
    config.__post_init__()
    control.storage_check(config)
    p3.environment_gate()
    p3.repository_check(config.expected_head)
    p2.require(type(token) is frozen.PreparedToken and type(metadata) is credentials.AcquisitionMetadata)
    token.__post_init__()
    metadata.__post_init__()
    p2.require(metadata.public_config_sha256 == review["public_sha256"]
               and metadata.account_alias == config.account_alias
               and token.expires_at == metadata.expires_at
               and token.clock_uncertainty_seconds == metadata.clock_uncertainty_seconds
               == config.runtime().clock_uncertainty_seconds)
    p2.require(p3.load_json(config.path("acquisition.json")) == metadata.projection())
    token.check_ready(now=time.time(), dispatch_budget_seconds=config.minimum_handoff_seconds)
    intent = create_intent(config, review)
    # Fixed exclusive name BEFORE any network. Crash/uncertainty permanently
    # occupies it; even recreating the Python object cannot send a second create.
    p3.write_json(config.path("create-intent.json"), intent)
    result = {"schema": "sheets-phase4-create-result-v1", "engineering_only": True,
              "outcome": "CREATE_UNCERTAIN_RECONCILIATION_REQUIRED",
              "intent_sha256": control.hash_public(intent), "http_status": None,
              "spreadsheet_id": None, "sheet_id": None, "rows": None, "columns": None}
    connection = None
    try:
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        p1.validate_context(context)
        connection = http.client.HTTPSConnection(frozen.HOST, 443, timeout=config.create_seconds, context=context)
        connection.auto_open = connection.debuglevel = 0
        connection.connect()
        token.check_ready(now=time.time(), dispatch_budget_seconds=config.create_seconds)
        connection.request("POST", intent["path"], canonical_json_bytes(intent["request"]),
            {"Authorization": "Bearer " + token.value, "Content-Type": "application/json; charset=utf-8",
             "Accept": "application/json", "Accept-Encoding": "identity", "Connection": "close"})
        response = connection.getresponse()
        p2.require(type(response.status) is int and 100 <= response.status <= 599)
        result["http_status"] = response.status
        p2.require(response.status == 200 and not response.chunked)
        headers = response.getheaders()
        framing = {}
        for name, value in headers:
            name = name.lower()
            if name in ("content-length", "content-type", "content-encoding", "transfer-encoding"):
                p2.require(name not in framing)
                framing[name] = value
        p2.require(set(framing) <= {"content-length", "content-type", "content-encoding"}
            and framing.get("content-encoding", "identity") == "identity"
            and framing.get("content-type", "").lower() in ("application/json", "application/json; charset=utf-8")
            and re.fullmatch(r"[1-9][0-9]{0,5}", framing.get("content-length", "")))
        length = int(framing["content-length"])
        p2.require(length <= 65536)
        body = response.read(length + 1)
        p2.require(len(body) == length and response.isclosed())
        identity = validated_identity(body, config, review)
        result.update(outcome="CREATE_RESPONSE_VALIDATED", spreadsheet_id=identity, sheet_id=1, rows=100, columns=3)
    except Exception:
        pass  # Never stringify/persist arbitrary exception, response or headers.
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                result.update(outcome="CREATE_UNCERTAIN_RECONCILIATION_REQUIRED", spreadsheet_id=None,
                              sheet_id=None, rows=None, columns=None)
    p3.write_json(config.path("create-result.json"), result)
    return result


@credentials.secret_safe
def review_provisioning(config, review, *, operator_confirmation, isolated, no_writers):
    p2.require(operator_confirmation == p3.PROVISION_CONFIRMATION and isolated is True and no_writers is True)
    result = validate_create_result(p3.load_json(config.path("create-result.json")), config, review)
    p2.require(p3.load_json(config.path("create-intent.json")) == create_intent(config, review))
    record = p3.ProvisioningRecord("PROVISIONED", "same-app-sheets-create-separately-authorized",
        review["public_sha256"], config.account_alias, result["spreadsheet_id"], 1, 100,
        config.reservation_id, config.operator_alias, time.time(), operator_confirmation, True, True)
    p3.write_json(config.path("provisioning.json"), record.projection())
    return record

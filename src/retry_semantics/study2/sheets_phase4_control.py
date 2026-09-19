"""DRAFT local operational gates. No provider access; trusted operator model."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
import os
from pathlib import Path
import re
import stat
import sys

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase3_operator as operator

BASE = "9967146176e9e507768577e99fdaa40b5d821d6d"
FILES = ("operator.json", "client-review.json", "startup.json", "offline-pin.json",
         "oauth-intent.json", "acquisition.json", "create-intent.json", "create-result.json",
         "provisioning.json", "fixture.json", "read-pin.json", "conditions.json",
         "issue-intent.json", "authorization.json", "phase3-receipt.json", "phase4-receipt.json",
         "read-intent.json", "result.json")
ASSUMPTIONS = ("trusted_local_operator_machine", "no_concurrent_source_runtime_changes",
               "no_trust_store_or_system_certificate_changes", "no_vpn_proxy_route_changes",
               "no_package_updates", "clock_within_allowance", "private_storage_reviewed",
               "no_terminal_recording_or_core_dumps", "hostile_audit_approved")


def hash_public(value):
    return sha256_hex(canonical_json_bytes(value))


@dataclass(frozen=True, slots=True)
class OperatorConfiguration:
    storage_root: str
    expected_head: str
    account_alias: str
    operator_alias: str
    reservation_id: str
    authorization_id: str
    read: dict
    minimum_handoff_seconds: float
    authorization_seconds: float
    consent_seconds: float
    exchange_seconds: float
    create_seconds: float
    schema: str = "sheets-phase4-operator-configuration-v1"

    def __post_init__(self):
        p2.require(self.schema == "sheets-phase4-operator-configuration-v1")
        p2.require(type(self.expected_head) is str and len(self.expected_head) == 40
                   and all(c in "0123456789abcdef" for c in self.expected_head))
        for n in ("account_alias", "operator_alias", "reservation_id", "authorization_id"):
            p2.label(getattr(self, n))
        root = Path(self.storage_root)
        p2.require(root.is_absolute() and ".." not in root.parts and str(root) == self.storage_root
                   and not root.is_relative_to(frozen.ROOT))
        runtime = self.runtime()
        p2.require(runtime.registry_root == str(root / "registry"))
        for n in ("minimum_handoff_seconds", "authorization_seconds", "consent_seconds",
                  "exchange_seconds", "create_seconds"):
            frozen._number(getattr(self, n), positive=True)
        bound = runtime.attempt_seconds + runtime.safety_seconds + runtime.clock_uncertainty_seconds
        p2.require(bound < self.authorization_seconds <= 2 * bound
                   and self.minimum_handoff_seconds > self.authorization_seconds + bound
                   and self.minimum_handoff_seconds > self.create_seconds + bound)

    def runtime(self):
        return operator._typed(self.read, p3.RuntimeConfiguration)

    def projection(self):
        self.__post_init__()
        return asdict(self)

    def path(self, name):
        p2.require(name in FILES)
        return Path(self.storage_root) / name


def storage_check(config):
    """Read-only: no creating directories, repairing modes or removing residue."""
    config.__post_init__()
    root = Path(config.storage_root)
    p2.require(not any(p.is_symlink() for p in (root, *root.parents)))
    p2.require(not stat.S_IMODE(root.parent.stat().st_mode) & 0o022)
    p2.require(root.parent.stat().st_uid == os.getuid())
    for directory in (root, root / "registry"):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            p2._private_fd(fd, directory=True)
            for name in os.listdir(fd):
                if directory == root and name == "registry":
                    continue
                p2.require(directory != root or name in FILES)
                p2.require(directory == root or name == "registry.lock" or re.fullmatch(
                    r"(?:reservation|claim|attempt)-[A-Za-z0-9_-]{1,128}\.jsonl?", name))
                file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    p2._private_fd(file_fd)
                finally:
                    os.close(file_fd)
        finally:
            os.close(fd)
    return {"root": config.storage_root, "directory_mode": "0700", "file_mode": "0600",
            "secrets": "excluded", "retention": "permanent-no-automatic-cleanup"}


def validate_review(review):
    p2.require(type(review) is dict and set(review) == {"schema", "public", "public_sha256"}
               and review["schema"] == "sheets-phase4-client-review-v1")
    public = review["public"]
    p2.require(type(public) is dict)
    client = credentials.ClientConfig(public.get("client_id"), "excluded-validation-only",
                                      public.get("project_id"))
    p2.require(public == client.public_projection() and review["public_sha256"] == client.public_hash)
    return review


def source_projection():
    files = {name: sha256_hex((Path(__file__).parent / name).read_bytes()) for name in (
        "sheets_phase4_control.py", "sheets_phase4_setup.py", "sheets_phase4_operator.py")}
    files["phase3_source"] = p3.source_hash()
    files["phase1_source"] = sha256_hex((Path(__file__).parent / "sheets_live_go_phase1.py").read_bytes())
    for name in ("SHEETS_PHASE4_OPERATOR_CONFIGURATION_DRAFT.json", "GOOGLE_SHEETS_LIVE_GO_PHASE4.md"):
        files[name] = sha256_hex((frozen.SHEETS_DOCS / name).read_bytes())
    files["qualification_runner"] = sha256_hex((frozen.ROOT / "scripts/qualify_sheets_phase4_offline.py").read_bytes())
    return files


def native_operational_implementations():
    """Pin the socket and flock extensions omitted by inherited runtime pins.

    A platform without stable extension files fails closed rather than claiming
    that a module name or version is a content hash.
    """
    result = {}
    for name in ("_socket", "fcntl"):
        selected = getattr(importlib.import_module(name), "__file__", None)
        p2.require(type(selected) is str)
        path = Path(selected).resolve(strict=True)
        p2.require(path.is_file())
        result[name] = {"resolved_path": str(path), "sha256": sha256_hex(path.read_bytes())}
    return result


def runtime_projection(config, review, descriptor=None):
    validate_review(review)
    return {"schema": "sheets-phase4-runtime-pin-v1", "expected_head": config.expected_head,
            "clean_tree_required": True, "python_executable": str(Path(sys.executable).resolve()),
            "sources": source_projection(), "operator": config.projection(), "client_review": review,
            "phase4_support_implementations": {name: sha256_hex(Path(importlib.import_module(name).__file__).read_bytes())
                for name in ("argparse", "shlex", "resource", "dataclasses", "stat", "math",
                             "json", "json.decoder", "json.encoder", "json.scanner", "_json", "os")},
            "native_operational_implementations": native_operational_implementations(),
            "phase3": p3.runtime_projection(config.runtime()), "fixture": descriptor,
            "schemas": ["sheets-phase4-startup-v1", "sheets-phase4-create-result-v1",
                        "sheets-phase3-fixture-descriptor-v1", "sheets-phase3-acquisition-metadata-v1",
                        "sheets-live-authorization-v1", "sheets-phase3-issuance-receipt-v1",
                        "sheets-phase4-issuance-receipt-v1"]}


def startup(config, review, confirmations):
    p3.environment_gate()
    p3.repository_check(config.expected_head)
    storage_check(config)
    p2.require(type(confirmations) is dict and set(confirmations) == set(ASSUMPTIONS)
               and all(v is True for v in confirmations.values()))
    return {"schema": "sheets-phase4-startup-v1", "runtime_sha256":
            hash_public(runtime_projection(config, review)), "assumptions": confirmations,
            "environment": "PASS_NAMES_ONLY", "model": "trusted-local-operator-no-os-sandbox"}


def offline_preflight(config, review, attestation, pin):
    reasons = []
    def check(code, f):
        try:
            f()
        except Exception:
            reasons.append(code)
    check("configuration", config.__post_init__)
    check("environment", p3.environment_gate)
    check("repository", lambda: p3.repository_check(config.expected_head))
    check("checklist", p3.checklist_local_gate)
    check("storage", lambda: storage_check(config))
    check("client_review", lambda: validate_review(review))
    check("runtime_pin", lambda: p2.require(pin == runtime_projection(config, review)))
    check("startup", lambda: p2.require(attestation == startup(config, review, attestation["assumptions"])))
    def pristine():
        p2.require(not any(config.path(n).exists() for n in FILES if n not in
                   ("operator.json", "client-review.json", "startup.json", "offline-pin.json")))
        p2.require(not os.listdir(Path(config.storage_root) / "registry"))
    check("setup_already_started_or_uncertain", pristine)
    return report("before-real-setup", reasons)


def report(scope, reasons):
    return {"schema": "sheets-phase4-preflight-v1", "scope": scope,
            "status": "BLOCKED" if reasons else "PASS", "reasons": reasons,
            "network": "not-performed", "live_go": "CLOSED", "paper_observations": 0}


def post_setup_preflight(config, review, attestation, offline_pin, pin, descriptor,
                         metadata, token, conditions, now):
    """Token is an explicit memory input, never projected, hashed or written."""
    reasons = []
    try:
        p2.require(offline_pin == runtime_projection(config, review))
        p2.require(attestation == startup(config, review, attestation["assumptions"]))
        p2.require(pin == runtime_projection(config, review, descriptor))
    except Exception:
        reasons.append("startup_source_runtime_storage")
    try:
        p2.require(type(token) is frozen.PreparedToken and type(metadata) is credentials.AcquisitionMetadata)
        token.__post_init__()
        p2.require(token.expires_at == metadata.expires_at
                   and token.clock_uncertainty_seconds == metadata.clock_uncertainty_seconds
                   and metadata.public_config_sha256 == review["public_sha256"]
                   and metadata.account_alias == config.account_alias)
        metadata.__post_init__()
        config.runtime().check_ready(expires_at=token.expires_at,
            clock_uncertainty_seconds=token.clock_uncertainty_seconds, now=now)
        p2.require(token.expires_at - now > config.minimum_handoff_seconds
                   + token.clock_uncertainty_seconds)
        p2.require(p3.load_json(config.path("acquisition.json")) == metadata.projection())
    except Exception:
        reasons.append("credential_readiness")
    try:
        from retry_semantics.study2.sheets_phase4_setup import validate_create_result, create_intent, oauth_intent
        result = validate_create_result(p3.load_json(config.path("create-result.json")), config, review)
        p2.require(p3.load_json(config.path("create-intent.json")) == create_intent(config, review))
        p2.require(p3.load_json(config.path("oauth-intent.json")) == oauth_intent(config, review))
        record = operator._typed(p3.load_json(config.path("provisioning.json")), p3.ProvisioningRecord)
        p2.require(descriptor == p3.fixture_descriptor(record)
                   and record.spreadsheet_id == result["spreadsheet_id"]
                   and record.sheet_id == 1 and record.rows == 100
                   and record.account_alias == config.account_alias
                   and record.public_app_config_sha256 == review["public_sha256"]
                   and record.reservation_id == config.reservation_id
                   and record.operator_alias == config.operator_alias)
        p2.require(not config.path("issue-intent.json").exists())
        p2.require(not any(config.path(n).exists() for n in ("authorization.json", "phase3-receipt.json",
                                                          "phase4-receipt.json", "read-intent.json", "result.json")))
    except Exception:
        reasons.append("provisioning_review_or_prior_issuance")
    inherited = p3.preflight(descriptor=descriptor, configuration=config.runtime(),
        expected_pin=pin.get("phase3", {}), expected_head=config.expected_head, conditions=conditions,
        credential_metadata=metadata, now=now)
    reasons.extend("phase3_" + n for n in inherited["reasons"])
    try:
        inspection = p3.RegistryInspection(config.runtime().registry_root)
        try:
            inspection.absent(config.authorization_id)
        finally:
            inspection.close()
    except Exception:
        reasons.append("authorization_id_used")
    return report("after-setup-before-issuance", reasons)


def check_setup_records(config, review, descriptor, metadata):
    """Repeat immutable setup dataflow bindings at consumption, not just issue."""
    from retry_semantics.study2.sheets_phase4_setup import validate_create_result, create_intent, oauth_intent
    result = validate_create_result(p3.load_json(config.path("create-result.json")), config, review)
    p2.require(p3.load_json(config.path("create-intent.json")) == create_intent(config, review))
    p2.require(p3.load_json(config.path("oauth-intent.json")) == oauth_intent(config, review))
    record = operator._typed(p3.load_json(config.path("provisioning.json")), p3.ProvisioningRecord)
    p2.require(descriptor == p3.fixture_descriptor(record)
        and record.spreadsheet_id == result["spreadsheet_id"] and record.sheet_id == 1 and record.rows == 100
        and record.account_alias == config.account_alias and metadata.account_alias == config.account_alias
        and record.public_app_config_sha256 == review["public_sha256"] == metadata.public_config_sha256
        and record.reservation_id == config.reservation_id and record.operator_alias == config.operator_alias)
    p2.require(p3.load_json(config.path("acquisition.json")) == metadata.projection())

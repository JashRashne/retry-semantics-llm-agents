"""DRAFT local operational gates. No provider access; trusted operator model."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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
FILES = ("operator.json", "client-review.json", "startup.json", "offline-pin.json", "supersession.json",
         "acquisition-attempt.json",
         "oauth-intent.json", "acquisition-failure.json", "acquisition.json", "create-intent.json", "create-result.json",
         "provisioning.json", "fixture.json", "read-pin.json", "conditions.json",
         "issue-intent.json", "authorization.json", "phase3-receipt.json", "phase4-receipt.json",
         "read-intent.json", "result.json")
ASSUMPTIONS = ("trusted_local_operator_machine", "no_concurrent_source_runtime_changes",
               "no_trust_store_or_system_certificate_changes", "no_vpn_proxy_route_changes",
               "no_package_updates", "clock_within_allowance", "private_storage_reviewed",
               "no_terminal_recording_or_core_dumps", "hostile_audit_approved")
PRELIVE_FILES = frozenset(("operator.json", "client-review.json", "startup.json",
                          "offline-pin.json", "supersession.json", "acquisition-attempt.json"))
SUPERSESSION_CONFIRMATION = "EXPLICIT_OFFLINE_PRELIVE_SUPERSESSION"
NEW_ACQUISITION_CONFIRMATION = "EXPLICIT_REVIEWED_NEW_ACQUISITION_ATTEMPT"
SPENT_OAUTH_FILES = frozenset(("operator.json", "client-review.json", "startup.json",
    "offline-pin.json", "oauth-intent.json"))


def hash_public(value):
    return sha256_hex(canonical_json_bytes(value))


def validate_acquisition_failure(value):
    p2.require(credentials.acquisition_failure_consistent(value))
    return value


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
    attempt = re.fullmatch(r"(.+)-acquisition-at-([0-9a-f]{40})", root.name)
    successor = None if attempt else re.fullmatch(r".+-at-([0-9a-f]{40})", root.name)
    record_path = root / "supersession.json"
    attempt_path = root / "acquisition-attempt.json"
    p2.require(not (record_path.exists() and attempt_path.exists()))
    if attempt or attempt_path.exists():
        p2.require(attempt is not None and attempt.group(2) == config.expected_head)
        record = p3.load_json(attempt_path)
        predecessor = root.with_name(attempt.group(1))
        p2.require(type(record) is dict and set(record) == {"schema", "predecessor_root",
                   "predecessor_expected_head", "predecessor_operator_sha256",
                   "predecessor_oauth_intent_sha256", "new_attempt_root", "new_attempt_expected_head",
                   "offline_files_present", "no_accepted_local_acquisition_artifact",
                   "no_sheets_side_artifacts", "predecessor_permanently_spent", "review_confirmation"}
                   and record["schema"] == "sheets-phase4-reviewed-acquisition-attempt-v1"
                   and record["predecessor_root"] == str(predecessor)
                   and record["new_attempt_root"] == config.storage_root
                   and record["new_attempt_expected_head"] == config.expected_head
                   and type(record["predecessor_expected_head"]) is str
                   and re.fullmatch(r"[0-9a-f]{40}", record["predecessor_expected_head"])
                   and record["predecessor_expected_head"] != config.expected_head
                   and record["no_accepted_local_acquisition_artifact"] is True
                   and record["no_sheets_side_artifacts"] is True
                   and record["predecessor_permanently_spent"] is True
                   and record["review_confirmation"] == NEW_ACQUISITION_CONFIRMATION)
        p2.digest(record["predecessor_operator_sha256"])
        p2.digest(record["predecessor_oauth_intent_sha256"])
        p2.require(type(record["offline_files_present"]) is list
                   and record["offline_files_present"] in (
                       sorted(SPENT_OAUTH_FILES | extra | failure)
                       for extra in (set(), {"supersession.json"}, {"acquisition-attempt.json"})
                       for failure in (set(), {"acquisition-failure.json"})))
    if successor or record_path.exists():
        p2.require(successor is not None and successor.group(1) == config.expected_head)
        record = p3.load_json(record_path)
        predecessor = root.with_name(root.name[:-44])
        p2.require(type(record) is dict and set(record) == {"schema", "predecessor_root",
                   "predecessor_expected_head", "predecessor_operator_sha256", "successor_root",
                   "successor_expected_head", "offline_files_present", "no_live_boundary_artifacts", "reason"}
                   and record["schema"] == "sheets-phase4-prelive-supersession-v1"
                   and record["predecessor_root"] == str(predecessor)
                   and record["successor_root"] == config.storage_root
                   and record["successor_expected_head"] == config.expected_head
                   and type(record["predecessor_expected_head"]) is str
                   and re.fullmatch(r"[0-9a-f]{40}", record["predecessor_expected_head"])
                   and record["predecessor_expected_head"] != config.expected_head
                   and record["no_live_boundary_artifacts"] is True
                   and record["reason"] == "frozen_source_changed_before_live")
        p2.digest(record["predecessor_operator_sha256"])
        p2.require(type(record["offline_files_present"]) is list
                   and record["offline_files_present"] == sorted(set(record["offline_files_present"]))
                   and "operator.json" in record["offline_files_present"]
                   and set(record["offline_files_present"]) <= PRELIVE_FILES)
    return {"root": config.storage_root, "directory_mode": "0700", "file_mode": "0600",
            "secrets": "excluded", "retention": "permanent-no-automatic-cleanup"}


def _prelive_snapshot(config, *, spent_oauth=False):
    """Refuse every non-offline root entry and every registry entry, including locks."""
    storage_check(config)
    root = Path(config.storage_root)
    names = set(os.listdir(root))
    if spent_oauth:
        p2.require(names in (SPENT_OAUTH_FILES | {"registry"} | extra | failure
            for extra in (set(), {"supersession.json"}, {"acquisition-attempt.json"})
            for failure in (set(), {"acquisition-failure.json"})))
    else:
        p2.require("operator.json" in names and names <= PRELIVE_FILES | {"registry"})
    p2.require(not os.listdir(root / "registry"))
    p2.require(p3.load_json(config.path("operator.json")) == config.projection())
    review = p3.load_json(config.path("client-review.json")) if "client-review.json" in names else None
    if review is not None:
        validate_review(review)
    if "startup.json" in names:
        p2.require(review is not None)
        startup_record = p3.load_json(config.path("startup.json"))
        p2.require(type(startup_record) is dict and set(startup_record) ==
                   {"schema", "runtime_sha256", "assumptions", "environment", "model"}
                   and startup_record["schema"] == "sheets-phase4-startup-v1"
                   and type(startup_record["assumptions"]) is dict
                   and set(startup_record["assumptions"]) == set(ASSUMPTIONS)
                   and all(value is True for value in startup_record["assumptions"].values())
                   and startup_record["environment"] == "PASS_NAMES_ONLY"
                   and startup_record["model"] == "trusted-local-operator-no-os-sandbox")
        p2.digest(startup_record["runtime_sha256"])
    if "offline-pin.json" in names:
        p2.require("startup.json" in names)
        pin = p3.load_json(config.path("offline-pin.json"))
        p2.require(type(pin) is dict and set(pin) == {"schema", "expected_head", "clean_tree_required",
                   "python_executable", "sources", "operator", "client_review",
                   "phase4_support_implementations", "native_operational_implementations",
                   "phase3", "fixture", "schemas"}
                   and pin["schema"] == "sheets-phase4-runtime-pin-v1"
                   and pin["expected_head"] == config.expected_head
                   and pin["clean_tree_required"] is True and pin["fixture"] is None
                   and pin["operator"] == config.projection() and pin["client_review"] == review)
        p2.require(startup_record["runtime_sha256"] == hash_public(pin))
    if spent_oauth:
        from retry_semantics.study2 import sheets_phase4_setup as setup
        p2.require(p3.load_json(config.path("oauth-intent.json")) == setup.oauth_intent(config, review))
        if "acquisition-failure.json" in names:
            validate_acquisition_failure(p3.load_json(config.path("acquisition-failure.json")))
    # Metadata is used only to detect concurrent changes; no file contents or secret hashes are recorded.
    signature = tuple((name, *(getattr((root / name).lstat(), field)
        for field in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")))
        for name in sorted(names))
    return sorted(names - {"registry"}), signature


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def supersede_prelive(config, new_head, operator_confirmation):
    """Create one fresh sibling; never edit or remove the predecessor package."""
    p2.require(operator_confirmation == SUPERSESSION_CONFIRMATION)
    config.__post_init__()
    p2.require(type(new_head) is str and re.fullmatch(r"[0-9a-f]{40}", new_head)
               and new_head != config.expected_head)
    p3.environment_gate()
    p3.repository_check(new_head)
    before = _prelive_snapshot(config)
    old_root = Path(config.storage_root)
    new_root = old_root.with_name(old_root.name + "-at-" + new_head)
    new_config = replace(config, storage_root=str(new_root), expected_head=new_head,
                         read={**config.read, "registry_root": str(new_root / "registry")})
    record = {"schema": "sheets-phase4-prelive-supersession-v1",
              "predecessor_root": config.storage_root, "predecessor_expected_head": config.expected_head,
              "predecessor_operator_sha256": hash_public(config.projection()),
              "successor_root": str(new_root), "successor_expected_head": new_head,
              "offline_files_present": before[0], "no_live_boundary_artifacts": True,
              "reason": "frozen_source_changed_before_live"}
    # Exclusive deterministic name is the process-level race winner. All failure residue stays visible.
    os.mkdir(new_root, 0o700)
    _fsync_directory(new_root.parent)
    p2.require(new_root.stat().st_uid == os.getuid()
               and stat.S_IMODE(new_root.stat().st_mode) == 0o700)
    os.mkdir(new_root / "registry", 0o700)
    p2.require((new_root / "registry").stat().st_uid == os.getuid()
               and stat.S_IMODE((new_root / "registry").stat().st_mode) == 0o700)
    _fsync_directory(new_root)
    p3.write_json(new_root / "supersession.pending.json", record)
    p3.write_json(new_config.path("operator.json"), new_config.projection())
    p2.require(_prelive_snapshot(config) == before)
    p3.repository_check(new_head)
    _fsync_directory(new_root / "registry")
    _fsync_directory(new_root)
    _fsync_directory(new_root.parent)
    # A hard-link activation cannot overwrite a destination. Until pending is removed,
    # storage_check rejects the unknown name and the two-link file. No fsync can fail
    # after the final unlink; a crash may restore pending (blocked) or leave a valid root.
    os.link(new_root / "supersession.pending.json", new_root / "supersession.json")
    _fsync_directory(new_root)
    p2.require(_prelive_snapshot(config) == before)
    os.unlink(new_root / "supersession.pending.json")
    return {"schema": "sheets-phase4-prelive-supersession-result-v1", "network": "not-performed",
            "predecessor": config.storage_root, "successor": str(new_root),
            "expected_head": new_head, "client_review": "required-again", "live_go": "CLOSED"}


def new_acquisition_attempt(config, new_head, operator_confirmation):
    """Authorize a fresh package after local evidence of a spent, unacquired OAuth attempt."""
    p2.require(operator_confirmation == NEW_ACQUISITION_CONFIRMATION)
    config.__post_init__()
    p2.require(type(new_head) is str and re.fullmatch(r"[0-9a-f]{40}", new_head)
               and new_head != config.expected_head)
    p3.environment_gate()
    p3.repository_check(new_head)
    before = _prelive_snapshot(config, spent_oauth=True)
    old_root = Path(config.storage_root)
    new_root = old_root.with_name(old_root.name + "-acquisition-at-" + new_head)
    new_config = replace(config, storage_root=str(new_root), expected_head=new_head,
                         read={**config.read, "registry_root": str(new_root / "registry")})
    record = {"schema": "sheets-phase4-reviewed-acquisition-attempt-v1",
              "predecessor_root": config.storage_root, "predecessor_expected_head": config.expected_head,
              "predecessor_operator_sha256": hash_public(config.projection()),
              "predecessor_oauth_intent_sha256": hash_public(p3.load_json(config.path("oauth-intent.json"))),
              "new_attempt_root": str(new_root), "new_attempt_expected_head": new_head,
              "offline_files_present": before[0], "no_accepted_local_acquisition_artifact": True,
              "no_sheets_side_artifacts": True, "predecessor_permanently_spent": True,
              "review_confirmation": NEW_ACQUISITION_CONFIRMATION}
    # The existing supersession activation pattern leaves every failed destination unusable.
    os.mkdir(new_root, 0o700)
    _fsync_directory(new_root.parent)
    p2.require(new_root.stat().st_uid == os.getuid()
               and stat.S_IMODE(new_root.stat().st_mode) == 0o700)
    os.mkdir(new_root / "registry", 0o700)
    p2.require((new_root / "registry").stat().st_uid == os.getuid()
               and stat.S_IMODE((new_root / "registry").stat().st_mode) == 0o700)
    _fsync_directory(new_root)
    p3.write_json(new_root / "acquisition-attempt.pending.json", record)
    p3.write_json(new_config.path("operator.json"), new_config.projection())
    p2.require(_prelive_snapshot(config, spent_oauth=True) == before)
    p3.repository_check(new_head)
    _fsync_directory(new_root / "registry")
    _fsync_directory(new_root)
    _fsync_directory(new_root.parent)
    os.link(new_root / "acquisition-attempt.pending.json", new_root / "acquisition-attempt.json")
    _fsync_directory(new_root)
    p2.require(_prelive_snapshot(config, spent_oauth=True) == before)
    os.unlink(new_root / "acquisition-attempt.pending.json")
    return {"schema": "sheets-phase4-reviewed-acquisition-attempt-result-v1",
            "network": "not-performed", "predecessor": config.storage_root,
            "new_attempt": str(new_root), "expected_head": new_head,
            "client_review": "required-again", "live_go": "CLOSED"}


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
            "schemas": ["sheets-phase4-startup-v1", "sheets-phase4-prelive-supersession-v1",
                        "sheets-phase4-reviewed-acquisition-attempt-v1",
                        "sheets-phase4-acquisition-failure-v1",
                        "sheets-phase4-create-result-v1",
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
                   PRELIVE_FILES))
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

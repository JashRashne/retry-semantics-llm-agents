"""DRAFT local operational gates. No provider access; trusted operator model."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import importlib
import os
from pathlib import Path
import re
import stat
import sys
import time

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase3_operator as operator

BASE = "9967146176e9e507768577e99fdaa40b5d821d6d"
FILES = ("operator.json", "client-review.json", "startup.json", "offline-pin.json", "supersession.json",
         "acquisition-attempt.json", "unused-acquisition-supersession.json",
         "unused-read-authorization-supersession.json", "fixture-adoption.json",
         "oauth-intent.json", "acquisition-failure.json", "acquisition.json", "create-intent.json", "create-result.json",
         "provisioning.json", "fixture.json", "read-pin.json", "conditions.json",
         "issue-intent.json", "authorization.json", "phase3-receipt.json", "phase4-receipt.json",
         "read-intent.json", "result.json")
ASSUMPTIONS = ("trusted_local_operator_machine", "no_concurrent_source_runtime_changes",
               "no_trust_store_or_system_certificate_changes", "no_vpn_proxy_route_changes",
               "no_package_updates", "clock_within_allowance", "private_storage_reviewed",
               "no_terminal_recording_or_core_dumps", "hostile_audit_approved")
PRELIVE_FILES = frozenset(("operator.json", "client-review.json", "startup.json",
                          "offline-pin.json", "supersession.json", "acquisition-attempt.json",
                          "unused-acquisition-supersession.json",
                          "unused-read-authorization-supersession.json"))
SUPERSESSION_CONFIRMATION = "EXPLICIT_OFFLINE_PRELIVE_SUPERSESSION"
NEW_ACQUISITION_CONFIRMATION = "EXPLICIT_REVIEWED_NEW_ACQUISITION_ATTEMPT"
UNUSED_ACQUISITION_CONFIRMATION = "EXPLICIT_UNUSED_ACQUISITION_SESSION_STOPPED"
UNUSED_READ_CONFIRMATION = "EXPLICIT_UNUSED_READ_AUTHORIZATION_EXPIRED_WITHOUT_DISPATCH"
SPENT_OAUTH_FILES = frozenset(("operator.json", "client-review.json", "startup.json",
    "offline-pin.json", "oauth-intent.json"))
ACQUIRED_UNUSED_FILES = SPENT_OAUTH_FILES | {"acquisition.json"}
PREDECESSOR_PROVENANCE = (set(), {"supersession.json"}, {"acquisition-attempt.json"},
                          {"unused-acquisition-supersession.json"},
                          {"unused-read-authorization-supersession.json"})
UNUSED_SUCCESSOR_PREFIX = "sheets-phase4-unused-acquisition-successor-"
UNUSED_READ_SUCCESSOR_PREFIX = "sheets-phase4-unused-read-successor-"
UNUSED_READ_REQUIRED = frozenset(("operator.json", "client-review.json", "startup.json",
    "offline-pin.json", "oauth-intent.json", "acquisition.json", "create-intent.json",
    "create-result.json", "provisioning.json", "fixture.json", "read-pin.json",
    "conditions.json", "issue-intent.json", "authorization.json", "phase3-receipt.json",
    "phase4-receipt.json"))
UNUSED_READ_ADOPTED_REQUIRED = frozenset(("operator.json", "client-review.json", "startup.json",
    "offline-pin.json", "oauth-intent.json", "acquisition.json", "fixture-adoption.json",
    "fixture.json", "read-pin.json", "conditions.json", "issue-intent.json", "authorization.json",
    "phase3-receipt.json", "phase4-receipt.json"))


def hash_public(value):
    return sha256_hex(canonical_json_bytes(value))


def _unused_acquisition_successor_root(predecessor_root):
    """One fixed-size sibling name for one canonical nonsecret predecessor path."""
    p2.require(type(predecessor_root) is str or isinstance(predecessor_root, Path))
    raw = str(predecessor_root)
    root = Path(raw)
    p2.require(root.is_absolute() and ".." not in root.parts and str(root) == raw
               and not root.is_relative_to(frozen.ROOT))
    digest = hash_public({"schema": "sheets-phase4-unused-acquisition-successor-name-v1",
                          "predecessor_root": raw})
    return root.with_name(UNUSED_SUCCESSOR_PREFIX + digest)


def _unused_read_successor_root(predecessor_root):
    p2.require(type(predecessor_root) is str or isinstance(predecessor_root, Path))
    raw = str(predecessor_root)
    root = Path(raw)
    p2.require(root.is_absolute() and ".." not in root.parts and str(root) == raw
               and not root.is_relative_to(frozen.ROOT))
    digest = hash_public({"schema": "sheets-phase4-unused-read-successor-name-v1",
                          "predecessor_root": raw})
    return root.with_name(UNUSED_READ_SUCCESSOR_PREFIX + digest)


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
    # A later pre-live successor appends -at-<HEAD> to this short root. It must
    # carry its own supersession record; a bare dedicated-prefix root needs the
    # activated unused-acquisition provenance below.
    unused = root.name.startswith(UNUSED_SUCCESSOR_PREFIX) and successor is None
    record_path = root / "supersession.json"
    attempt_path = root / "acquisition-attempt.json"
    unused_path = root / "unused-acquisition-supersession.json"
    unused_read_path = root / "unused-read-authorization-supersession.json"
    read_successor = root.name.startswith(UNUSED_READ_SUCCESSOR_PREFIX) and successor is None
    p2.require(sum(path.exists() for path in (record_path, attempt_path, unused_path,
                                             unused_read_path)) <= 1)
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
    if unused or unused_path.exists():
        p2.require(unused)
        record = p3.load_json(unused_path)
        p2.require(type(record) is dict and type(record.get("predecessor_root")) is str)
        predecessor = Path(record["predecessor_root"])
        p2.require(predecessor.parent == root.parent
                   and not any(path.is_symlink() for path in (predecessor, *predecessor.parents))
                   and root == _unused_acquisition_successor_root(record["predecessor_root"]))
        p2.require(type(record) is dict and set(record) == {"schema", "predecessor_root",
                   "predecessor_expected_head", "predecessor_operator_sha256",
                   "predecessor_oauth_intent_sha256", "predecessor_acquisition_sha256",
                   "successor_root", "successor_expected_head", "offline_files_present",
                   "accepted_local_acquisition", "no_sheets_side_artifacts", "registry_empty",
                   "operator_attested_session_stopped_before_provisioning",
                   "fresh_client_review_required", "fresh_startup_pin_required",
                   "fresh_oauth_required", "no_credential_inherited", "review_confirmation"}
                   and record["schema"] == "sheets-phase4-reviewed-unused-acquisition-supersession-v1"
                   and record["predecessor_root"] == str(predecessor)
                   and record["successor_root"] == config.storage_root
                   and record["successor_expected_head"] == config.expected_head
                   and type(record["predecessor_expected_head"]) is str
                   and re.fullmatch(r"[0-9a-f]{40}", record["predecessor_expected_head"])
                   and record["predecessor_expected_head"] != config.expected_head
                   and all(record[name] is True for name in (
                       "accepted_local_acquisition", "no_sheets_side_artifacts", "registry_empty",
                       "operator_attested_session_stopped_before_provisioning",
                       "fresh_client_review_required", "fresh_startup_pin_required",
                       "fresh_oauth_required", "no_credential_inherited"))
                   and record["review_confirmation"] == UNUSED_ACQUISITION_CONFIRMATION)
        for name in ("predecessor_operator_sha256", "predecessor_oauth_intent_sha256",
                     "predecessor_acquisition_sha256"):
            p2.digest(record[name])
        p2.require(type(record["offline_files_present"]) is list
                   and record["offline_files_present"] in (
                       sorted(ACQUIRED_UNUSED_FILES | extra) for extra in PREDECESSOR_PROVENANCE))
    if read_successor or unused_read_path.exists():
        p2.require(read_successor)
        record = p3.load_json(unused_read_path)
        p2.require(type(record) is dict and set(record) == {
            "schema", "predecessor_root", "predecessor_expected_head", "predecessor_operator_sha256",
            "predecessor_evidence_sha256", "predecessor_authorization_sha256",
            "predecessor_fixture_sha256", "successor_root", "successor_expected_head",
            "successor_authorization_id", "prior_authorization_expired_unused",
            "fresh_review_startup_oauth_adoption_required", "transitioned_at", "review_confirmation"}
            and record["schema"] == "sheets-phase4-expired-unused-read-supersession-v1"
            and record["successor_root"] == config.storage_root
            and record["successor_expected_head"] == config.expected_head
            and record["successor_authorization_id"] == config.authorization_id
            and record["prior_authorization_expired_unused"] is True
            and record["fresh_review_startup_oauth_adoption_required"] is True
            and record["review_confirmation"] == UNUSED_READ_CONFIRMATION)
        frozen._number(record["transitioned_at"], positive=True)
        predecessor = Path(record["predecessor_root"])
        p2.require(predecessor.parent == root.parent and predecessor != root
                   and root == _unused_read_successor_root(predecessor)
                   and not any(path.is_symlink() for path in (predecessor, *predecessor.parents)))
        old_config = operator._typed(p3.load_json(predecessor / "operator.json"), OperatorConfiguration)
        p2.require(old_config.storage_root == str(predecessor)
                   and record["predecessor_expected_head"] == old_config.expected_head
                   and record["predecessor_operator_sha256"] == hash_public(old_config.projection()))
        old = _expired_unused_read_snapshot(old_config)
        p2.require(record["predecessor_evidence_sha256"] == old["evidence_sha256"]
                   and record["predecessor_authorization_sha256"] == old["authorization_sha256"]
                   and record["predecessor_fixture_sha256"] == old["descriptor"]["fixture_hash"]
                   and config.account_alias == old_config.account_alias
                   and config.operator_alias == old_config.operator_alias
                   and config.reservation_id == old_config.reservation_id
                   and config.authorization_id != old_config.authorization_id
                   and config.authorization_id == "successor-" + root.name[-64:-32]
                   and record["transitioned_at"] >
                       p3.load_json(old_config.path("authorization.json"))["expires_at"]
                       + old_config.runtime().clock_uncertainty_seconds
                   and record["transitioned_at"] <= time.time()
                       + config.runtime().clock_uncertainty_seconds)
    return {"root": config.storage_root, "directory_mode": "0700", "file_mode": "0600",
            "secrets": "excluded", "retention": "permanent-no-automatic-cleanup"}


def _expired_unused_read_snapshot(config, *, now=None):
    """Validate a completed setup and expired issuance without inferring a GET."""
    from retry_semantics.study2 import sheets_phase4_setup as setup
    storage_check(config)
    root = Path(config.storage_root)
    names = set(os.listdir(root))
    adopted = reused_fixture_origin(config) is not None
    required = UNUSED_READ_ADOPTED_REQUIRED if adopted else UNUSED_READ_REQUIRED
    p2.require(names in (required | {"registry"} | extra
        for extra in PREDECESSOR_PROVENANCE))
    p2.require(p3.load_json(config.path("operator.json")) == config.projection())
    review = validate_review(p3.load_json(config.path("client-review.json")))
    offline_pin = p3.load_json(config.path("offline-pin.json"))
    startup_record = p3.load_json(config.path("startup.json"))
    p2.require(type(offline_pin) is dict and set(offline_pin) == {
        "schema", "expected_head", "clean_tree_required", "python_executable", "sources",
        "operator", "client_review", "phase4_support_implementations",
        "native_operational_implementations", "phase3", "fixture", "schemas"}
        and offline_pin["schema"] == "sheets-phase4-runtime-pin-v1"
        and offline_pin["expected_head"] == config.expected_head
        and offline_pin["clean_tree_required"] is True
        and offline_pin["operator"] == config.projection()
        and offline_pin["client_review"] == review and offline_pin["fixture"] is None)
    p2.require(type(startup_record) is dict and set(startup_record) == {
        "schema", "runtime_sha256", "assumptions", "environment", "model"}
        and startup_record["schema"] == "sheets-phase4-startup-v1"
        and startup_record["runtime_sha256"] == hash_public(offline_pin)
        and type(startup_record["assumptions"]) is dict
        and set(startup_record["assumptions"]) == set(ASSUMPTIONS)
        and all(value is True for value in startup_record["assumptions"].values())
        and startup_record["environment"] == "PASS_NAMES_ONLY"
        and startup_record["model"] == "trusted-local-operator-no-os-sandbox")
    p2.require(p3.load_json(config.path("oauth-intent.json")) == setup.oauth_intent(config, review))
    metadata = operator._metadata(p3.load_json(config.path("acquisition.json")))
    p2.require(metadata.public_config_sha256 == review["public_sha256"]
        and metadata.account_alias == config.account_alias
        and metadata.clock_uncertainty_seconds == config.runtime().clock_uncertainty_seconds)
    if adopted:
        descriptor = adopted_fixture(config, review)
        p2.require(not any(config.path(n).exists() for n in
            ("create-intent.json", "create-result.json", "provisioning.json")))
    else:
        intent = setup.create_intent(config, review)
        p2.require(p3.load_json(config.path("create-intent.json")) == intent)
        result = setup.validate_create_result(p3.load_json(config.path("create-result.json")), config, review)
        record = operator._typed(p3.load_json(config.path("provisioning.json")), p3.ProvisioningRecord)
        descriptor = p3.load_json(config.path("fixture.json"))
        p2.require(descriptor == p3.fixture_descriptor(record)
            and record.spreadsheet_id == result["spreadsheet_id"]
            and record.public_app_config_sha256 == review["public_sha256"]
            and record.account_alias == config.account_alias
            and record.reservation_id == config.reservation_id
            and record.operator_alias == config.operator_alias
            and record.confirmed_at >= metadata.prepared_at)
    fixture = p3.parse_fixture_descriptor(descriptor)
    read_pin = p3.load_json(config.path("read-pin.json"))
    p2.require(read_pin == {**offline_pin, "fixture": descriptor})
    conditions = operator._typed(p3.load_json(config.path("conditions.json")), p3.LocalConditions)
    conditions.validate()
    authorization = p3.parse_authorization(p3.load_json(config.path("authorization.json")))
    p2.require(authorization.capability.value == "LIVE_READ_GO"
        and authorization.engineering_only is True
        and authorization.authorization_id == config.authorization_id
        and authorization.operator_alias == config.operator_alias
        and authorization.fixture_manifest_sha256 == descriptor["fixture_hash"]
        and authorization.runtime_pin_sha256 == read_pin["phase3"]["phase2_runtime_hash"]
        and authorization.connector_source_sha256 == read_pin["phase3"]["phase2_source_hash"]
        and authorization.expires_at - authorization.authorized_at == config.authorization_seconds
        and authorization.authorized_at >= metadata.prepared_at)
    clock_now = time.time() if now is None else now
    frozen._number(clock_now, positive=True)
    p2.require(clock_now > authorization.expires_at + config.runtime().clock_uncertainty_seconds)
    expected_issue = {"schema": "sheets-phase4-issue-intent-v1",
        "authorization_id": config.authorization_id, "runtime_sha256": hash_public(read_pin),
        "fixture_sha256": descriptor["fixture_hash"], "source_sha256": hash_public(read_pin["sources"]),
        "startup_sha256": hash_public(startup_record)}
    p2.require(p3.load_json(config.path("issue-intent.json")) == expected_issue)
    auth_hash = p2.authorization_hash(authorization)
    receipt = {"schema": "sheets-phase3-issuance-receipt-v1", "authorization_hash": auth_hash,
        "phase3_runtime_hash": hash_public(read_pin["phase3"]),
        "phase3_source_hash": read_pin["phase3"]["phase3_source_hash"],
        "local_conditions": asdict(conditions)}
    p2.require(p3.load_json(config.path("phase3-receipt.json")) == receipt)
    phase4 = {"schema": "sheets-phase4-issuance-receipt-v1", "engineering_only": True,
        "phase4_runtime_sha256": hash_public(read_pin),
        "phase4_source_sha256": hash_public(read_pin["sources"]),
        "startup_sha256": hash_public(startup_record), "authorization_sha256": auth_hash,
        "phase3_receipt_sha256": hash_public(receipt), "authorization_id": config.authorization_id,
        "capability": "LIVE_READ_GO"}
    p2.require(p3.load_json(config.path("phase4-receipt.json")) == phase4)
    registry = root / "registry"
    expected_reservation = f"reservation-{config.reservation_id}.json"
    p2.require(set(os.listdir(registry)) == {"registry.lock", expected_reservation}
               and (registry / "registry.lock").read_bytes() == b"")
    inspection = p3.RegistryInspection(str(registry))
    try:
        p2.require(inspection._reservations() == [p2.LocalRegistry.reservation(fixture)])
    finally:
        inspection.close()
    evidence = {name: p3.load_json(root / name) for name in sorted(names - {"registry"})}
    evidence["registry/reservation"] = p2.LocalRegistry.reservation(fixture)
    evidence["registry/lock"] = "empty"
    signature = tuple((str(path.relative_to(root)), *(getattr(path.lstat(), field) for field in
        ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")))
        for path in sorted([*(root / name for name in names), registry / expected_reservation,
                            registry / "registry.lock"]))
    return {"descriptor": descriptor, "review": review, "authorization_sha256": auth_hash,
            "evidence_sha256": hash_public(evidence), "signature": signature}


def _prelive_snapshot(config, *, spent_oauth=False, unused_acquisition=False):
    """Refuse every non-offline root entry and every registry entry, including locks."""
    storage_check(config)
    root = Path(config.storage_root)
    names = set(os.listdir(root))
    p2.require(not (spent_oauth and unused_acquisition))
    if unused_acquisition:
        p2.require(names in (ACQUIRED_UNUSED_FILES | {"registry"} | extra
            for extra in PREDECESSOR_PROVENANCE))
    elif spent_oauth:
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
    if spent_oauth or unused_acquisition:
        from retry_semantics.study2 import sheets_phase4_setup as setup
        p2.require(p3.load_json(config.path("oauth-intent.json")) == setup.oauth_intent(config, review))
        if "acquisition-failure.json" in names:
            validate_acquisition_failure(p3.load_json(config.path("acquisition-failure.json")))
    if unused_acquisition:
        metadata = operator._metadata(p3.load_json(config.path("acquisition.json")))
        p2.require(metadata.public_config_sha256 == review["public_sha256"]
                   and metadata.account_alias == config.account_alias
                   and metadata.clock_uncertainty_seconds == config.runtime().clock_uncertainty_seconds)
    # Metadata is used only to detect concurrent changes; no file contents or secret hashes are recorded.
    signature = tuple((name, *(getattr((root / name).lstat(), field)
        for field in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")))
        for name in sorted(names))
    return sorted(names - {"registry"}), signature


def reused_fixture_origin(config):
    """Follow validated pre-live successors to the unused-read provenance."""
    storage_check(config)
    if config.path("unused-read-authorization-supersession.json").exists():
        return p3.load_json(config.path("unused-read-authorization-supersession.json"))
    if not config.path("supersession.json").exists():
        return None
    record = p3.load_json(config.path("supersession.json"))
    predecessor = Path(record["predecessor_root"])
    old_config = operator._typed(p3.load_json(predecessor / "operator.json"), OperatorConfiguration)
    p2.require(hash_public(old_config.projection()) == record["predecessor_operator_sha256"]
               and old_config.storage_root == str(predecessor)
               and old_config.expected_head == record["predecessor_expected_head"])
    p2.require(_prelive_snapshot(old_config)[0] == record["offline_files_present"])
    return reused_fixture_origin(old_config)


def reused_fixture_chain(config):
    """Return the ordered list of unused-read supersession records from immediate predecessor to root."""
    chain = []
    current = config
    while True:
        origin = reused_fixture_origin(current)
        if origin is None:
            break
        chain.append(origin)
        pred_root = Path(origin["predecessor_root"])
        current = operator._typed(p3.load_json(pred_root / "operator.json"), OperatorConfiguration)
    return chain


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
    p2.require(reused_fixture_origin(config) is None)
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


def supersede_unused_acquisition(config, new_head, operator_confirmation):
    """Attest a stopped resident session and preserve its accepted acquisition."""
    p2.require(operator_confirmation == UNUSED_ACQUISITION_CONFIRMATION)
    config.__post_init__()
    p2.require(reused_fixture_origin(config) is None)
    p2.require(type(new_head) is str and re.fullmatch(r"[0-9a-f]{40}", new_head)
               and new_head != config.expected_head)
    p3.environment_gate()
    p3.repository_check(new_head)
    before = _prelive_snapshot(config, unused_acquisition=True)
    old_root = Path(config.storage_root)
    new_root = _unused_acquisition_successor_root(old_root)
    try:
        name_max = os.pathconf(new_root.parent, "PC_NAME_MAX")
    except (OSError, ValueError, AttributeError):
        raise p2.Refused() from None
    p2.require(type(name_max) is int and name_max > 0
               and len(new_root.name.encode("utf-8")) <= name_max)
    new_config = replace(config, storage_root=str(new_root), expected_head=new_head,
                         read={**config.read, "registry_root": str(new_root / "registry")})
    record = {"schema": "sheets-phase4-reviewed-unused-acquisition-supersession-v1",
              "predecessor_root": config.storage_root, "predecessor_expected_head": config.expected_head,
              "predecessor_operator_sha256": hash_public(config.projection()),
              "predecessor_oauth_intent_sha256": hash_public(p3.load_json(config.path("oauth-intent.json"))),
              "predecessor_acquisition_sha256": hash_public(p3.load_json(config.path("acquisition.json"))),
              "successor_root": str(new_root), "successor_expected_head": new_head,
              "offline_files_present": before[0], "accepted_local_acquisition": True,
              "no_sheets_side_artifacts": True, "registry_empty": True,
              "operator_attested_session_stopped_before_provisioning": True,
              "fresh_client_review_required": True, "fresh_startup_pin_required": True,
              "fresh_oauth_required": True, "no_credential_inherited": True,
              "review_confirmation": UNUSED_ACQUISITION_CONFIRMATION}
    # A deterministic exclusive name wins the race; failure residue is never repaired.
    os.mkdir(new_root, 0o700)
    _fsync_directory(new_root.parent)
    p2.require(new_root.stat().st_uid == os.getuid()
               and stat.S_IMODE(new_root.stat().st_mode) == 0o700)
    os.mkdir(new_root / "registry", 0o700)
    p2.require((new_root / "registry").stat().st_uid == os.getuid()
               and stat.S_IMODE((new_root / "registry").stat().st_mode) == 0o700)
    _fsync_directory(new_root)
    p3.write_json(new_root / "unused-acquisition-supersession.pending.json", record)
    p3.write_json(new_config.path("operator.json"), new_config.projection())
    p2.require(_prelive_snapshot(config, unused_acquisition=True) == before)
    p3.repository_check(new_head)
    _fsync_directory(new_root / "registry")
    _fsync_directory(new_root)
    _fsync_directory(new_root.parent)
    os.link(new_root / "unused-acquisition-supersession.pending.json",
            new_root / "unused-acquisition-supersession.json")
    _fsync_directory(new_root)
    p2.require(_prelive_snapshot(config, unused_acquisition=True) == before)
    os.unlink(new_root / "unused-acquisition-supersession.pending.json")
    return {"schema": "sheets-phase4-reviewed-unused-acquisition-supersession-result-v1",
            "network": "not-performed", "predecessor": config.storage_root,
            "successor": str(new_root), "expected_head": new_head,
            "client_review": "required-again", "live_go": "CLOSED"}


def supersede_unused_read_authorization(config, new_head, operator_confirmation):
    """Preserve a validated fixture and a first issuance that expired before read dispatch."""
    p2.require(operator_confirmation == UNUSED_READ_CONFIRMATION)
    config.__post_init__()
    p2.require(type(new_head) is str and re.fullmatch(r"[0-9a-f]{40}", new_head))
    p3.environment_gate()
    p3.repository_check(new_head)
    before = _expired_unused_read_snapshot(config)
    old_root = Path(config.storage_root)
    new_root = _unused_read_successor_root(old_root)
    try:
        name_max = os.pathconf(new_root.parent, "PC_NAME_MAX")
    except (OSError, ValueError, AttributeError):
        raise p2.Refused() from None
    p2.require(type(name_max) is int and name_max > 0
               and len(new_root.name.encode("utf-8")) <= name_max)
    new_id = "successor-" + new_root.name[-64:-32]
    new_config = replace(config, storage_root=str(new_root), expected_head=new_head,
                         authorization_id=new_id,
                         read={**config.read, "registry_root": str(new_root / "registry")})
    record = {"schema": "sheets-phase4-expired-unused-read-supersession-v1",
        "predecessor_root": config.storage_root, "predecessor_expected_head": config.expected_head,
        "predecessor_operator_sha256": hash_public(config.projection()),
        "predecessor_evidence_sha256": before["evidence_sha256"],
        "predecessor_authorization_sha256": before["authorization_sha256"],
        "predecessor_fixture_sha256": before["descriptor"]["fixture_hash"],
        "successor_root": str(new_root), "successor_expected_head": new_head,
        "successor_authorization_id": new_id,
        "transitioned_at": time.time(),
        "prior_authorization_expired_unused": True,
        "fresh_review_startup_oauth_adoption_required": True,
        "review_confirmation": UNUSED_READ_CONFIRMATION}
    os.mkdir(new_root, 0o700)
    _fsync_directory(new_root.parent)
    p2.require(new_root.stat().st_uid == os.getuid()
               and stat.S_IMODE(new_root.stat().st_mode) == 0o700)
    os.mkdir(new_root / "registry", 0o700)
    p2.require((new_root / "registry").stat().st_uid == os.getuid()
               and stat.S_IMODE((new_root / "registry").stat().st_mode) == 0o700)
    _fsync_directory(new_root)
    p3.write_json(new_root / "unused-read-authorization-supersession.pending.json", record)
    p3.write_json(new_config.path("operator.json"), new_config.projection())
    p2.require(_expired_unused_read_snapshot(config) == before)
    p3.repository_check(new_head)
    _fsync_directory(new_root / "registry")
    _fsync_directory(new_root)
    _fsync_directory(new_root.parent)
    os.link(new_root / "unused-read-authorization-supersession.pending.json",
            new_root / "unused-read-authorization-supersession.json")
    _fsync_directory(new_root)
    p2.require(_expired_unused_read_snapshot(config) == before)
    os.unlink(new_root / "unused-read-authorization-supersession.pending.json")
    return {"schema": "sheets-phase4-expired-unused-read-supersession-result-v1",
        "network": "not-performed", "predecessor": config.storage_root, "successor": str(new_root),
        "expected_head": new_head, "prior_authorization": "expired-unused-no-read-dispatch",
        "fixture": "validated-historical-adoption-required", "live_go": "CLOSED"}


def adopted_fixture(config, review):
    """Return only the previously validated public fixture after local adoption."""
    storage_check(config)
    provenance = reused_fixture_origin(config)
    p2.require(provenance is not None)
    old_config = operator._typed(p3.load_json(Path(provenance["predecessor_root"]) / "operator.json"),
                                 OperatorConfiguration)
    old = _expired_unused_read_snapshot(old_config)
    descriptor = old["descriptor"]
    validate_review(review)
    p2.require(review["public_sha256"] == old["review"]["public_sha256"])
    from retry_semantics.study2 import sheets_phase4_setup as setup
    p2.require(p3.load_json(config.path("oauth-intent.json")) == setup.oauth_intent(config, review))
    adoption = p3.load_json(config.path("fixture-adoption.json"))
    metadata = operator._metadata(p3.load_json(config.path("acquisition.json")))
    p2.require(metadata.prepared_at > provenance["transitioned_at"]
               and metadata.public_config_sha256 == review["public_sha256"]
               and metadata.account_alias == config.account_alias
               and metadata.projection() != p3.load_json(old_config.path("acquisition.json")))
    p2.require(adoption == {"schema": "sheets-phase4-fixture-adoption-v1",
        "predecessor_evidence_sha256": old["evidence_sha256"],
        "predecessor_authorization_sha256": old["authorization_sha256"],
        "fixture_sha256": descriptor["fixture_hash"],
        "successor_operator_sha256": hash_public(config.projection()),
        "successor_review_sha256": hash_public(review),
        "successor_acquisition_sha256": hash_public(p3.load_json(config.path("acquisition.json"))),
        "prior_authorization": "expired-unused-no-read-dispatch"})
    p2.require(p3.load_json(config.path("fixture.json")) == descriptor)
    return descriptor


def adopt_existing_fixture(config, review, metadata, operator_confirmation):
    p2.require(operator_confirmation == "EXPLICIT_ADOPT_VALIDATED_EXISTING_FIXTURE")
    provenance = reused_fixture_origin(config)
    p2.require(provenance is not None)
    p2.require(not any(config.path(name).exists() for name in (
        "fixture-adoption.json", "fixture.json", "read-pin.json", "conditions.json",
        "create-intent.json", "create-result.json", "provisioning.json", "issue-intent.json",
        "authorization.json", "phase3-receipt.json", "phase4-receipt.json",
        "read-intent.json", "result.json")))
    p2.require(p3.load_json(config.path("acquisition.json")) == metadata.projection())
    from retry_semantics.study2 import sheets_phase4_setup as setup
    p2.require(p3.load_json(config.path("oauth-intent.json")) == setup.oauth_intent(config, review))
    p2.require(metadata.public_config_sha256 == review["public_sha256"]
               and metadata.account_alias == config.account_alias)
    p2.require(p3.load_json(config.path("offline-pin.json")) == runtime_projection(config, review))
    attestation = p3.load_json(config.path("startup.json"))
    p2.require(attestation == startup(config, review, attestation["assumptions"]))
    old_config = operator._typed(p3.load_json(Path(provenance["predecessor_root"]) / "operator.json"),
                                 OperatorConfiguration)
    old = _expired_unused_read_snapshot(old_config)
    p2.require(review["public_sha256"] == old["review"]["public_sha256"]
               and metadata.prepared_at > provenance["transitioned_at"]
               and metadata.projection() != p3.load_json(old_config.path("acquisition.json"))
               and not os.listdir(Path(config.runtime().registry_root)))
    descriptor = old["descriptor"]
    adoption = {"schema": "sheets-phase4-fixture-adoption-v1",
        "predecessor_evidence_sha256": old["evidence_sha256"],
        "predecessor_authorization_sha256": old["authorization_sha256"],
        "fixture_sha256": descriptor["fixture_hash"],
        "successor_operator_sha256": hash_public(config.projection()),
        "successor_review_sha256": hash_public(review),
        "successor_acquisition_sha256": hash_public(metadata.projection()),
        "prior_authorization": "expired-unused-no-read-dispatch"}
    p3.write_json(config.path("fixture-adoption.json"), adoption)
    p3.write_json(config.path("fixture.json"), descriptor)
    with p2.LocalRegistry(Path(config.runtime().registry_root)) as registry:
        registry.reserve(p3.parse_fixture_descriptor(descriptor))
    p3.write_json(config.path("read-pin.json"), runtime_projection(config, review, descriptor))
    return {"fixture_sha256": descriptor["fixture_hash"], "network": "not-performed",
            "create": "not-repeated", "prior_authorization": "historical-expired-unused"}


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
                        "sheets-phase4-reviewed-unused-acquisition-supersession-v1",
                        "sheets-phase4-expired-unused-read-supersession-v1",
                        "sheets-phase4-fixture-adoption-v1",
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
        p2.require(p3.load_json(config.path("oauth-intent.json")) == oauth_intent(config, review))
        if reused_fixture_origin(config) is not None:
            p2.require(descriptor == adopted_fixture(config, review)
                and not any(config.path(n).exists() for n in
                    ("create-intent.json", "create-result.json", "provisioning.json")))
        else:
            result = validate_create_result(p3.load_json(config.path("create-result.json")), config, review)
            p2.require(p3.load_json(config.path("create-intent.json")) == create_intent(config, review))
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
    p2.require(p3.load_json(config.path("oauth-intent.json")) == oauth_intent(config, review))
    if reused_fixture_origin(config) is not None:
        p2.require(descriptor == adopted_fixture(config, review)
            and not any(config.path(n).exists() for n in
                ("create-intent.json", "create-result.json", "provisioning.json")))
    else:
        result = validate_create_result(p3.load_json(config.path("create-result.json")), config, review)
        p2.require(p3.load_json(config.path("create-intent.json")) == create_intent(config, review))
        record = operator._typed(p3.load_json(config.path("provisioning.json")), p3.ProvisioningRecord)
        p2.require(descriptor == p3.fixture_descriptor(record)
            and record.spreadsheet_id == result["spreadsheet_id"] and record.sheet_id == 1 and record.rows == 100
            and record.account_alias == config.account_alias and metadata.account_alias == config.account_alias
            and record.public_app_config_sha256 == review["public_sha256"] == metadata.public_config_sha256
            and record.reservation_id == config.reservation_id and record.operator_alias == config.operator_alias)
    p2.require(p3.load_json(config.path("acquisition.json")) == metadata.projection())

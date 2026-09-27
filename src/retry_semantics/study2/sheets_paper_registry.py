"""Offline, frozen Google Sheets Study-2 paper namespace reservation.

This module makes only a durable local reservation. It has no provider,
credential, provisioning, manifest, or collection capability.
"""

from __future__ import annotations

import errno
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from retry_semantics.serialization import canonical_json_bytes, sha256_hex

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = Path(
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_NAMESPACE_RESERVATION_V1.json"
)
FROZEN_REGISTRY_SHA256 = "a8a8bcd2751c56b05e9a9a569a6ad5f16e7d260b6a8ce5fb57dd244aef594506"
LATER_RAZORPAY_REGISTRY = {
    "path": "research/study2/razorpay/RAZORPAY_PAPER_NAMESPACE_RESERVATION_V1.json",
    "sha256": "b7f5b446c68ee826daaa0454d333d6361a0c1d9d1d7d3ee7cb31007443e783d9",
}
RUN_NAMESPACE = "76b0af67d7eece50cb12167e7ec374b9"
SPREADSHEET_TITLE = "retry-semantics-study2-sheets-primary-v1-" + RUN_NAMESPACE
FAMILY_COUNT = 64
ARM_COUNT = 256
STATUS = "FROZEN_LOCAL_NAMESPACE_RESERVATION_INDEPENDENT_HOSTILE_AUDIT_PASSED"
AUDIT_PROVENANCE = {
    "audit_status": "PASSED",
    "pre_freeze_canonical_bytes": 67231,
    "pre_freeze_sha256": "de34968a380e2317067a9b7a969834eede1abdfe7abc032c0c8e5f769412b3c6",
    "freeze_scope": "STATUS_PROVENANCE_ONLY_NO_RESERVATION_OR_COLLISION_DECISION_CHANGE",
}
_WORLDS = ("H0", "H1")
_POLICIES = ("EXACT_REPLAY", "LLM_REGENERATION")
_TITLE_GRAMMAR = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_NAMESPACE_GRAMMAR = re.compile(r"[0-9a-f]{32}\Z")

SOURCE_SHA256 = {
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md":
        "15a2357e99df0c856f99b8b5419e923be927cdfeef7535be4d21a475762e6109",
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md":
        "b88d13c059d1716b1528386d2446a53e770e7c078e223e46aefa8f9daba98a2e",
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json":
        "f85e49303094292bd4472e83aeda35a1b8c65fa97d42b33cf298904d0cabdf69",
    "research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md":
        "d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2",
    "research/protocol/primary_create_v1_3_analysis_plan.md":
        "23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88",
    "research/protocol/STUDY2_ANALYSIS_AMENDMENT_DECISION.md":
        "05ded80d5dad442f278997bb0bdbca980f2d42261b0f6d058d08996970b443ba",
    "research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md":
        "21ff3b3ca90d27a46669e12bab62de89d7ddd191ba96dfa5a8e12c0a69521ecb",
}

# Explicit repository-controlled engineering corpus. The paper inputs, paper
# contract, paper catalogue, and this paper registry are intentionally excluded.
# Historical packages outside this repository and deleted files are not searched.
ENGINEERING_CORPUS_PATHS = (
    "research/study2/sheets/GOOGLE_SHEETS_ENGINEERING_CONTRACT.md",
    "research/study2/sheets/GOOGLE_SHEETS_ENGINEERING_QUALIFICATION_LOCK.md",
    "research/study2/sheets/GOOGLE_SHEETS_LIVE_GO_PHASE1.md",
    "research/study2/sheets/GOOGLE_SHEETS_LIVE_GO_PHASE2.md",
    "research/study2/sheets/GOOGLE_SHEETS_LIVE_GO_PHASE3.md",
    "research/study2/sheets/GOOGLE_SHEETS_LIVE_GO_PHASE4.md",
    "research/study2/sheets/GOOGLE_SHEETS_LIVE_PREPARATION.md",
    "research/study2/sheets/GOOGLE_SHEETS_LIVE_QUALIFICATION_DRAFT.md",
    "research/study2/sheets/GOOGLE_SHEETS_SEMANTICS_RECONNAISSANCE.md",
    "research/study2/sheets/SHEETS_LIVE_GO_CHECKLIST_DRAFT.json",
    "research/study2/sheets/SHEETS_PHASE3_OPERATOR_CONFIGURATION_TEMPLATE.json",
    "research/study2/sheets/SHEETS_PHASE3_TRUST_INVENTORY_DRAFT.json",
    "research/study2/sheets/SHEETS_PHASE4_OPERATOR_CONFIGURATION_DRAFT.json",
    "research/study2/sheets/SHEETS_RUNTIME_PIN_DRAFT.json",
    "research/study2/sheets/fixtures/qualification_fixture_draft.json",
    "research/study2/sheets/fixtures/qualification_fixture_phase2_template.json",
    "research/study2/sheets/fixtures/qualification_fixture_phase3_template.json",
    "src/retry_semantics/study2/sheets_http_framing.py",
    "src/retry_semantics/study2/sheets_live_go_phase1.py",
    "src/retry_semantics/study2/sheets_live_preparation.py",
    "src/retry_semantics/study2/sheets_offline.py",
    "src/retry_semantics/study2/sheets_phase2_control.py",
    "src/retry_semantics/study2/sheets_phase2_read.py",
    "src/retry_semantics/study2/sheets_phase3_control.py",
    "src/retry_semantics/study2/sheets_phase3_credentials.py",
    "src/retry_semantics/study2/sheets_phase3_operator.py",
    "src/retry_semantics/study2/sheets_phase4_control.py",
    "src/retry_semantics/study2/sheets_phase4_operator.py",
    "src/retry_semantics/study2/sheets_phase4_setup.py",
)


class SheetsPaperRegistryError(ValueError):
    """A frozen source or local reservation fails an offline check."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SheetsPaperRegistryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise SheetsPaperRegistryError(f"invalid JSON constant: {value}")


def _parse_json(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise SheetsPaperRegistryError("JSON input must be bytes")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SheetsPaperRegistryError("invalid UTF-8 JSON") from exc


def canonicalize_sheets_namespace_reservation(value: dict[str, Any]) -> bytes:
    """Use the repository's sorted-key, compact UTF-8 JSON without a newline."""

    if type(value) is not dict:
        raise SheetsPaperRegistryError("reservation must be a JSON object")
    return canonical_json_bytes(value)


def _read_required(root: Path, relative: str) -> bytes:
    try:
        path = root / relative
        if path.is_symlink():
            raise SheetsPaperRegistryError(f"symlinked local input: {relative}")
        return path.read_bytes()
    except OSError as exc:
        raise SheetsPaperRegistryError(f"missing or unreadable local input: {relative}") from exc


def _verified_families(root: Path) -> list[str]:
    for relative, expected in SOURCE_SHA256.items():
        if sha256_hex(_read_required(root, relative)) != expected:
            raise SheetsPaperRegistryError(f"frozen source hash mismatch: {relative}")
    catalogue = _parse_json(_read_required(
        root, "research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json"
    ))
    if type(catalogue) is not dict or type(catalogue.get("families")) is not list:
        raise SheetsPaperRegistryError("invalid frozen Sheets catalogue")
    families = catalogue["families"]
    expected_ids = [f"sheets-f{index:03d}" for index in range(1, FAMILY_COUNT + 1)]
    if [family.get("family_id") if type(family) is dict else None for family in families] != expected_ids:
        raise SheetsPaperRegistryError("Sheets family IDs or order changed")
    return expected_ids


def _reservation_rows(families: list[str]) -> list[dict[str, Any]]:
    if _NAMESPACE_GRAMMAR.fullmatch(RUN_NAMESPACE) is None:
        raise SheetsPaperRegistryError("invalid frozen Sheets run namespace")
    rows: list[dict[str, Any]] = []
    for index, family_id in enumerate(families):
        family_suffix = family_id.removeprefix("sheets-")
        for world in _WORLDS:
            for policy in _POLICIES:
                arm_id = f"{family_id}:{world}:{policy}"
                tab_title = f"RS2S_{family_suffix}_{world}_{policy}"
                digest = hashlib.sha256(f"{RUN_NAMESPACE}:{arm_id}".encode("utf-8")).hexdigest()
                arm_marker = "RS2-SHEETS-V1-" + digest[:32]
                if _TITLE_GRAMMAR.fullmatch(tab_title) is None:
                    raise SheetsPaperRegistryError("invalid Sheets tab title")
                rows.append({
                    "family_id": family_id,
                    "family_index": index,
                    "arm_id": arm_id,
                    "hidden_world": world,
                    "policy": policy,
                    "tab_title": tab_title,
                    "arm_marker": arm_marker,
                })
    if (len(rows) != ARM_COUNT
            or len({row["arm_id"] for row in rows}) != ARM_COUNT
            or len({row["arm_marker"] for row in rows}) != ARM_COUNT
            or len({row["tab_title"] for row in rows}) != ARM_COUNT):
        raise SheetsPaperRegistryError("within-run reservation collision")
    return rows


def _scan_paper_registries(
    root: Path, namespace: str, markers: set[str], *, exclude: Path | None = None
) -> list[dict[str, str]]:
    directory = root / "research/study2"
    inspected: list[dict[str, str]] = []
    for path in sorted(directory.rglob("*PAPER_NAMESPACE_RESERVATION*.json")):
        if exclude is not None and path == exclude:
            continue
        relative = path.relative_to(root).as_posix()
        raw = _read_required(root, relative)
        prior = _parse_json(raw)
        if type(prior) is not dict or canonical_json_bytes(prior) != raw:
            raise SheetsPaperRegistryError(f"malformed prior paper registry: {relative}")
        prior_namespace = prior.get("run_namespace")
        prior_rows = prior.get("reservations")
        if (type(prior_namespace) is not str
                or _NAMESPACE_GRAMMAR.fullmatch(prior_namespace) is None
                or type(prior_rows) is not list or not prior_rows):
            raise SheetsPaperRegistryError(f"malformed prior paper registry: {relative}")
        prior_markers: list[str] = []
        for row in prior_rows:
            if (type(row) is not dict or type(row.get("arm_marker")) is not str
                    or not row["arm_marker"]):
                raise SheetsPaperRegistryError(f"malformed prior paper registry: {relative}")
            prior_markers.append(row["arm_marker"])
        if len(set(prior_markers)) != len(prior_markers):
            raise SheetsPaperRegistryError(f"duplicate marker in prior paper registry: {relative}")
        if prior_namespace == namespace:
            raise SheetsPaperRegistryError(f"prior paper namespace collision: {relative}")
        if markers.intersection(prior_markers):
            raise SheetsPaperRegistryError(f"prior paper marker collision: {relative}")
        inspected.append({"path": relative, "sha256": sha256_hex(raw)})
    return inspected


def validate_local_collision_candidate(root: Path, namespace: str, markers: set[str]) -> None:
    """Check a future candidate against every discovered local paper registry."""

    if (type(namespace) is not str or _NAMESPACE_GRAMMAR.fullmatch(namespace) is None
            or type(markers) is not set or not markers
            or any(type(marker) is not str or not marker for marker in markers)):
        raise SheetsPaperRegistryError("invalid local collision candidate")
    _scan_paper_registries(root, namespace, markers)


def _scan_engineering_corpus(root: Path, namespace: str, markers: set[str]) -> list[dict[str, str]]:
    needles = (namespace.encode("utf-8"), *(marker.encode("utf-8") for marker in sorted(markers)))
    inspected: list[dict[str, str]] = []
    for relative in ENGINEERING_CORPUS_PATHS:
        raw = _read_required(root, relative)
        if any(needle in raw for needle in needles):
            raise SheetsPaperRegistryError(f"Sheets engineering correlation collision: {relative}")
        inspected.append({"path": relative, "sha256": sha256_hex(raw)})
    return inspected


def build_sheets_namespace_reservation(root: Path = REPOSITORY_ROOT) -> bytes:
    """Build exact canonical audited bytes from frozen, offline inputs."""

    families = _verified_families(root)
    rows = _reservation_rows(families)
    markers = {row["arm_marker"] for row in rows}
    prior = _scan_paper_registries(root, RUN_NAMESPACE, markers, exclude=root / REGISTRY_PATH)
    engineering = _scan_engineering_corpus(root, RUN_NAMESPACE, markers)
    value = {
        "schema": "google-sheets-paper-namespace-reservation-v1",
        "status": STATUS,
        "audit_provenance": AUDIT_PROVENANCE,
        "provider": "google_sheets",
        "paper_only": True,
        "run_namespace": RUN_NAMESPACE,
        "spreadsheet_title": SPREADSHEET_TITLE,
        "family_count": FAMILY_COUNT,
        "arm_count": ARM_COUNT,
        "source_sha256": SOURCE_SHA256,
        "reservations": rows,
        "collision_check": {
            "corpus_scope": "enumerated repository-controlled Sheets engineering artifacts and discovered research/study2 paper namespace registries only; no external or deleted history",
            "within_run_namespace_count": 1,
            "arm_id_count": len(rows),
            "distinct_arm_id_count": len({row["arm_id"] for row in rows}),
            "marker_count": len(rows),
            "distinct_marker_count": len(markers),
            "tab_title_count": len(rows),
            "distinct_tab_title_count": len({row["tab_title"] for row in rows}),
            "known_prior_paper_registry_count": len(prior),
            "known_prior_paper_registries": prior,
            "prior_paper_namespace_collision_count": 0,
            "prior_paper_marker_collision_count": 0,
            "engineering_corpus_count": len(engineering),
            "engineering_corpus": engineering,
            "engineering_collision_count": 0,
            "overall_result": "PASS_REPOSITORY_CONTROLLED_LOCAL_CORPUS_ONLY",
        },
        "state": {
            "topology_selected": True,
            "local_namespace_reserved": True,
            "scope_provisioned": False,
            "scope_ids_bound": False,
            "scope_qualified": False,
            "final_manifest_exists": False,
            "collection_authorized": False,
            "study2_paper_observations": 0,
            "collection_blocked": True,
        },
    }
    return canonicalize_sheets_namespace_reservation(value)


def validate_sheets_namespace_reservation(raw: bytes, root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Validate the frozen creation-bound snapshot and all current peer registries."""

    value = _parse_json(raw)
    if type(value) is not dict or canonicalize_sheets_namespace_reservation(value) != raw:
        raise SheetsPaperRegistryError("noncanonical Sheets paper registry")
    current = build_sheets_namespace_reservation(root)
    if raw != current:
        # The Razorpay reservation was added after this registry was frozen and
        # provisioned. Rewriting the Sheets bytes would invalidate CREATE's
        # audited registry hash. Admit only that exact later peer, after the
        # builder has checked its namespace and every marker for collision.
        rebuilt = _parse_json(current)
        frozen_peers = value.get("collision_check", {}).get("known_prior_paper_registries")
        current_check = rebuilt.get("collision_check", {})
        current_peers = current_check.get("known_prior_paper_registries")
        if (sha256_hex(raw) != FROZEN_REGISTRY_SHA256
                or type(frozen_peers) is not list
                or type(current_peers) is not list
                or current_peers != frozen_peers + [LATER_RAZORPAY_REGISTRY]):
            raise SheetsPaperRegistryError("Sheets paper registry differs from frozen inputs")
        historical = copy.deepcopy(rebuilt)
        historical_check = historical["collision_check"]
        historical_check["known_prior_paper_registries"] = frozen_peers
        historical_check["known_prior_paper_registry_count"] = len(frozen_peers)
        if canonical_json_bytes(historical) != raw:
            raise SheetsPaperRegistryError("Sheets paper registry differs from frozen inputs")
    return value


def load_sheets_namespace_reservation(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Read and independently validate the existing local reservation."""

    raw = _read_required(root, REGISTRY_PATH.as_posix())
    return validate_sheets_namespace_reservation(raw, root)


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


def write_sheets_namespace_reservation_exclusive(root: Path = REPOSITORY_ROOT) -> bytes:
    """Create only the fixed path with O_EXCL; preserve any partial failure."""

    raw = build_sheets_namespace_reservation(root)
    target = root / REGISTRY_PATH
    if target.parent.is_symlink():
        raise SheetsPaperRegistryError("symlinked registry directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        written = 0
        while written < len(raw):
            count = os.write(fd, raw[written:])
            if count <= 0:
                raise OSError(errno.EIO, "incomplete registry write")
            written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(target.parent)
    return raw

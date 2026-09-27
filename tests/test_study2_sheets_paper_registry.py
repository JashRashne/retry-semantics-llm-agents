"""Offline hostile checks for the frozen Sheets paper local reservation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path

import pytest

from retry_semantics.study2.sheets_paper_registry import (
    ARM_COUNT,
    ENGINEERING_CORPUS_PATHS,
    FAMILY_COUNT,
    REGISTRY_PATH,
    REPOSITORY_ROOT,
    RUN_NAMESPACE,
    SOURCE_SHA256,
    SPREADSHEET_TITLE,
    STATUS,
    SheetsPaperRegistryError,
    build_sheets_namespace_reservation,
    canonicalize_sheets_namespace_reservation,
    load_sheets_namespace_reservation,
    validate_local_collision_candidate,
    validate_sheets_namespace_reservation,
    write_sheets_namespace_reservation_exclusive,
)


def _canonical_independent(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _isolated_root(destination: Path, *, include_own: bool = True) -> Path:
    paths = set(SOURCE_SHA256) | set(ENGINEERING_CORPUS_PATHS)
    paths.add("research/study2/github/GITHUB_PAPER_NAMESPACE_RESERVATION_V1.json")
    if include_own:
        paths.add(REGISTRY_PATH.as_posix())
    for relative in sorted(paths):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return destination


def _foreign_path(root: Path) -> Path:
    path = root / "research/study2/sheets/OTHER_PAPER_NAMESPACE_RESERVATION_V2.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_frozen_inputs_and_canonical_checked_in_registry() -> None:
    assert len(SOURCE_SHA256) == 7
    for relative, expected in SOURCE_SHA256.items():
        assert hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest() == expected
    assert SOURCE_SHA256["research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md"] == (
        "15a2357e99df0c856f99b8b5419e923be927cdfeef7535be4d21a475762e6109"
    )
    assert RUN_NAMESPACE == "76b0af67d7eece50cb12167e7ec374b9"
    assert re.fullmatch(r"[0-9a-f]{32}", RUN_NAMESPACE)
    assert SPREADSHEET_TITLE == (
        "retry-semantics-study2-sheets-primary-v1-76b0af67d7eece50cb12167e7ec374b9"
    )
    assert FAMILY_COUNT == 64 and ARM_COUNT == 256

    raw = (REPOSITORY_ROOT / REGISTRY_PATH).read_bytes()
    value = json.loads(raw)
    assert raw == _canonical_independent(value)
    assert not raw.endswith(b"\n")
    current = json.loads(build_sheets_namespace_reservation())
    assert current["collision_check"]["known_prior_paper_registries"] == (
        value["collision_check"]["known_prior_paper_registries"] + [{
            "path": "research/study2/razorpay/RAZORPAY_PAPER_NAMESPACE_RESERVATION_V1.json",
            "sha256": hashlib.sha256((REPOSITORY_ROOT / "research/study2/razorpay/RAZORPAY_PAPER_NAMESPACE_RESERVATION_V1.json").read_bytes()).hexdigest(),
        }]
    )
    assert raw == canonicalize_sheets_namespace_reservation(value)
    assert validate_sheets_namespace_reservation(raw) == value
    assert load_sheets_namespace_reservation() == value


def test_later_peer_is_checked_without_rewriting_create_bound_registry(tmp_path: Path) -> None:
    root = _isolated_root(tmp_path)
    razorpay = "research/study2/razorpay/RAZORPAY_PAPER_NAMESPACE_RESERVATION_V1.json"
    target = root / razorpay
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPOSITORY_ROOT / razorpay, target)
    frozen = (root / REGISTRY_PATH).read_bytes()
    assert load_sheets_namespace_reservation(root)["run_namespace"] == RUN_NAMESPACE
    assert (root / REGISTRY_PATH).read_bytes() == frozen
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(SheetsPaperRegistryError):
        load_sheets_namespace_reservation(root)


def test_exact_reservations_independently_recomputed() -> None:
    value = load_sheets_namespace_reservation()
    catalogue = json.loads((REPOSITORY_ROOT / "research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json").read_text())
    family_ids = [family["family_id"] for family in catalogue["families"]]
    assert family_ids == [f"sheets-f{i:03d}" for i in range(1, 65)]
    rows = value["reservations"]
    assert len(rows) == 256
    expected_ids = [
        f"sheets-f{i:03d}:{world}:{policy}"
        for i in range(1, 65)
        for world in ("H0", "H1")
        for policy in ("EXACT_REPLAY", "LLM_REGENERATION")
    ]
    assert [row["arm_id"] for row in rows] == expected_ids

    titles = []
    markers = []
    for index, row in enumerate(rows):
        family_number = index // 4 + 1
        family_id, world, policy = row["arm_id"].split(":")
        assert row == {
            "family_id": family_id,
            "family_index": family_number - 1,
            "arm_id": expected_ids[index],
            "hidden_world": world,
            "policy": policy,
            "tab_title": f"RS2S_f{family_number:03d}_{world}_{policy}",
            "arm_marker": "RS2-SHEETS-V1-" + hashlib.sha256(
                (RUN_NAMESPACE + ":" + expected_ids[index]).encode("utf-8")
            ).hexdigest()[:32],
        }
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", row["tab_title"])
        titles.append(row["tab_title"])
        markers.append(row["arm_marker"])
    assert len(set(expected_ids)) == len(set(titles)) == len(set(markers)) == 256
    assert max(map(len, titles)) == 29


def test_frozen_status_no_live_identity_or_outcome() -> None:
    value = load_sheets_namespace_reservation()
    assert value["schema"] == "google-sheets-paper-namespace-reservation-v1"
    assert value["status"] == STATUS == "FROZEN_LOCAL_NAMESPACE_RESERVATION_INDEPENDENT_HOSTILE_AUDIT_PASSED"
    assert value["audit_provenance"] == {
        "audit_status": "PASSED",
        "pre_freeze_canonical_bytes": 67231,
        "pre_freeze_sha256": "de34968a380e2317067a9b7a969834eede1abdfe7abc032c0c8e5f769412b3c6",
        "freeze_scope": "STATUS_PROVENANCE_ONLY_NO_RESERVATION_OR_COLLISION_DECISION_CHANGE",
    }
    assert value["provider"] == "google_sheets"
    assert value["paper_only"] is True
    assert value["run_namespace"] == RUN_NAMESPACE
    assert value["spreadsheet_title"] == SPREADSHEET_TITLE
    assert value["family_count"] == 64 and value["arm_count"] == 256
    assert value["state"] == {
        "topology_selected": True,
        "local_namespace_reserved": True,
        "scope_provisioned": False,
        "scope_ids_bound": False,
        "scope_qualified": False,
        "final_manifest_exists": False,
        "collection_authorized": False,
        "study2_paper_observations": 0,
        "collection_blocked": True,
    }

    forbidden_keys = {
        "spreadsheet_id", "sheet_id", "access_token", "oauth", "credential",
        "authenticated_principal", "principal", "quota", "provider_result",
        "outcome", "state_correct", "paper_metric", "observed_rows",
    }

    def inspect(item: object) -> None:
        if isinstance(item, dict):
            assert not forbidden_keys.intersection(item)
            for nested in item.values():
                inspect(nested)
        elif isinstance(item, list):
            for nested in item:
                inspect(nested)

    inspect(value)


def test_local_collision_summary_and_explicit_corpus() -> None:
    value = load_sheets_namespace_reservation()
    check = value["collision_check"]
    assert check["within_run_namespace_count"] == 1
    assert check["arm_id_count"] == check["distinct_arm_id_count"] == 256
    assert check["marker_count"] == check["distinct_marker_count"] == 256
    assert check["tab_title_count"] == check["distinct_tab_title_count"] == 256
    assert check["known_prior_paper_registry_count"] == 1
    assert [row["path"] for row in check["known_prior_paper_registries"]] == [
        "research/study2/github/GITHUB_PAPER_NAMESPACE_RESERVATION_V1.json"
    ]
    assert check["prior_paper_namespace_collision_count"] == 0
    assert check["prior_paper_marker_collision_count"] == 0
    assert check["engineering_collision_count"] == 0
    assert check["engineering_corpus_count"] == len(ENGINEERING_CORPUS_PATHS) == 29
    assert [row["path"] for row in check["engineering_corpus"]] == list(ENGINEERING_CORPUS_PATHS)
    for row in check["engineering_corpus"] + check["known_prior_paper_registries"]:
        assert row["sha256"] == hashlib.sha256((REPOSITORY_ROOT / row["path"]).read_bytes()).hexdigest()
    assert check["overall_result"] == "PASS_REPOSITORY_CONTROLLED_LOCAL_CORPUS_ONLY"
    assert "external or deleted history" in check["corpus_scope"]
    assert "GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md" not in ENGINEERING_CORPUS_PATHS


@pytest.mark.parametrize("field", [
    "duplicate_arm_id", "duplicate_marker", "duplicate_title", "altered_marker",
    "altered_title", "wrong_namespace", "wrong_source_hash", "wrong_family_index",
])
def test_current_registry_tampering_fails_closed(field: str) -> None:
    original = (REPOSITORY_ROOT / REGISTRY_PATH).read_bytes()
    value = json.loads(original)
    rows = value["reservations"]
    if field == "duplicate_arm_id":
        rows[1]["arm_id"] = rows[0]["arm_id"]
    elif field == "duplicate_marker":
        rows[1]["arm_marker"] = rows[0]["arm_marker"]
    elif field == "duplicate_title":
        rows[1]["tab_title"] = rows[0]["tab_title"]
    elif field == "altered_marker":
        rows[0]["arm_marker"] = "RS2-SHEETS-V1-" + "0" * 32
    elif field == "altered_title":
        rows[0]["tab_title"] = "RS2S_f001_H0_OTHER"
    elif field == "wrong_namespace":
        value["run_namespace"] = "0" * 32
    elif field == "wrong_source_hash":
        key = "research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md"
        value["source_sha256"][key] = "0" * 64
    else:
        rows[0]["family_index"] = 63
    with pytest.raises(SheetsPaperRegistryError, match="differs"):
        validate_sheets_namespace_reservation(_canonical_independent(value))


def test_duplicate_json_key_noncanonical_and_missing_bytes_fail_closed() -> None:
    with pytest.raises(SheetsPaperRegistryError, match="duplicate JSON key"):
        validate_sheets_namespace_reservation(b'{"run_namespace":"a","run_namespace":"b"}')
    raw = (REPOSITORY_ROOT / REGISTRY_PATH).read_bytes()
    with pytest.raises(SheetsPaperRegistryError, match="noncanonical"):
        validate_sheets_namespace_reservation(raw + b"\n")
    with pytest.raises(SheetsPaperRegistryError):
        validate_sheets_namespace_reservation(raw[:-1])


def test_foreign_paper_namespace_marker_and_malformed_registry_fail_closed(tmp_path: Path) -> None:
    root = _isolated_root(tmp_path)
    foreign = _foreign_path(root)
    marker = load_sheets_namespace_reservation()["reservations"][0]["arm_marker"]
    foreign.write_bytes(_canonical_independent({
        "run_namespace": RUN_NAMESPACE, "reservations": [{"arm_marker": "foreign-marker"}],
    }))
    with pytest.raises(SheetsPaperRegistryError, match="namespace collision"):
        build_sheets_namespace_reservation(root)
    foreign.write_bytes(_canonical_independent({
        "run_namespace": "0" * 32, "reservations": [{"arm_marker": marker}],
    }))
    with pytest.raises(SheetsPaperRegistryError, match="marker collision"):
        build_sheets_namespace_reservation(root)
    foreign.write_bytes(b"{")
    with pytest.raises(SheetsPaperRegistryError, match="invalid UTF-8 JSON"):
        build_sheets_namespace_reservation(root)
    foreign.write_bytes(b'{"run_namespace":"0","run_namespace":"1","reservations":[]}')
    with pytest.raises(SheetsPaperRegistryError, match="duplicate JSON key"):
        build_sheets_namespace_reservation(root)


def test_future_candidate_reuse_detected_against_existing_sheets_registry() -> None:
    marker = load_sheets_namespace_reservation()["reservations"][0]["arm_marker"]
    with pytest.raises(SheetsPaperRegistryError, match="namespace collision"):
        validate_local_collision_candidate(REPOSITORY_ROOT, RUN_NAMESPACE, {"unrelated-marker"})
    with pytest.raises(SheetsPaperRegistryError, match="marker collision"):
        validate_local_collision_candidate(REPOSITORY_ROOT, "0" * 32, {marker})


def test_engineering_corpus_collision_and_frozen_source_tamper_fail_closed(tmp_path: Path) -> None:
    root = _isolated_root(tmp_path)
    engineering = root / ENGINEERING_CORPUS_PATHS[0]
    engineering.write_bytes(engineering.read_bytes() + RUN_NAMESPACE.encode("ascii"))
    with pytest.raises(SheetsPaperRegistryError, match="engineering correlation collision"):
        build_sheets_namespace_reservation(root)
    engineering.write_bytes((REPOSITORY_ROOT / ENGINEERING_CORPUS_PATHS[0]).read_bytes())
    marker = load_sheets_namespace_reservation()["reservations"][0]["arm_marker"]
    engineering.write_bytes(engineering.read_bytes() + marker.encode("ascii"))
    with pytest.raises(SheetsPaperRegistryError, match="engineering correlation collision"):
        build_sheets_namespace_reservation(root)
    engineering.write_bytes((REPOSITORY_ROOT / ENGINEERING_CORPUS_PATHS[0]).read_bytes())
    source = root / "research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(SheetsPaperRegistryError, match="frozen source hash mismatch"):
        build_sheets_namespace_reservation(root)


def test_first_exclusive_write_and_existing_path_refusal(tmp_path: Path) -> None:
    root = _isolated_root(tmp_path, include_own=False)
    target = root / REGISTRY_PATH
    assert not target.exists()
    expected = build_sheets_namespace_reservation(root)
    written = write_sheets_namespace_reservation_exclusive(root)
    assert written == expected == target.read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert load_sheets_namespace_reservation(root) == json.loads(expected)
    with pytest.raises(FileExistsError):
        write_sheets_namespace_reservation_exclusive(root)
    assert target.read_bytes() == expected


def test_partial_write_remains_spent_and_cannot_be_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _isolated_root(tmp_path, include_own=False)
    target = root / REGISTRY_PATH
    real_write = os.write
    calls = 0

    def partial_then_error(fd: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(fd, data[:4])
        raise OSError("injected write failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", partial_then_error)
        with pytest.raises(OSError, match="injected write failure"):
            write_sheets_namespace_reservation_exclusive(root)
    assert target.read_bytes() == b'{"ar'
    with pytest.raises(FileExistsError):
        write_sheets_namespace_reservation_exclusive(root)
    assert target.read_bytes() == b'{"ar'

"""Precollection evidence separation; provider/OAuth calls are synthetic."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def operator_module():
    spec = importlib.util.spec_from_file_location("no_model_prepare_test", ROOT / "scripts/prepare_no_model_precollection.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mock_setup(module, monkeypatch, directory):
    directory.mkdir()
    (directory / "operator_attestation.json").write_text(json.dumps({"exclusive_writing_no_scripts_automation": True}))
    monkeypatch.setattr(module, "preparation_inputs", lambda _: ({}, [], {}, [], {"spreadsheet_id": "UNBOUND"}))


def test_second_sheets_evidence_preserves_first_attempt(tmp_path, monkeypatch):
    module = operator_module()
    directory = tmp_path / "plan"
    mock_setup(module, monkeypatch, directory)
    old = directory / "sheets_readiness"
    old.mkdir()
    original = b'{"status":"READINESS_FAILED_NO_RETRY"}'
    (old / "STOPPED.json").write_bytes(original)
    fresh = directory / "sheets_readiness_clean_environment"
    calls = []
    def refuse(**kwargs):
        calls.append(kwargs["directory"])
        raise ValueError("synthetic qualification failure, no provider calls")
    monkeypatch.setattr(module, "provision_sheets", refuse)
    assert module.main(["sheets-readiness", "--directory", str(directory),
        "--evidence-directory", str(fresh), "--client", "/tmp/synthetic-client.json"]) == 2
    assert calls == [fresh]
    assert (old / "STOPPED.json").read_bytes() == original
    assert json.loads((fresh / "STOPPED.json").read_bytes())["scientific_evaluations"] == 0


@pytest.mark.parametrize("default", [False, True])
def test_sheets_existing_directory_refuses_before_acquisition(tmp_path, monkeypatch, default):
    module = operator_module()
    directory = tmp_path / "plan"
    mock_setup(module, monkeypatch, directory)
    evidence = directory / ("sheets_readiness" if default else "new-evidence")
    evidence.mkdir()
    marker = evidence / "unchanged"
    marker.write_bytes(b"preserve")
    monkeypatch.setattr(module, "provision_sheets", lambda **_: pytest.fail("overwrite reached OAuth/provisioning"))
    args = ["sheets-readiness", "--directory", str(directory), "--client", "/tmp/synthetic-client.json"]
    if not default:
        args += ["--evidence-directory", str(evidence)]
    with pytest.raises(ValueError, match="already exists"):
        module.main(args)
    assert marker.read_bytes() == b"preserve" and list(evidence.iterdir()) == [marker]

"""Package copied evidence and project code; no provider or recovery operations."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from retry_semantics.baselines.audit_closure import implementation_closure, write_json
from retry_semantics.baselines.readiness import file_digest


def package(staging: Path, output: Path, readiness_report: str | None = None):
    if staging.exists() or output.exists():
        raise ValueError("audit output already exists; no overwrite")
    staging.mkdir(parents=True)
    copied = []

    def include(source: Path):
        if source.is_symlink() or not source.is_file():
            raise ValueError("nonregular audit input")
        relative = source.relative_to(ROOT)
        if any(part in {"__pycache__", ".env", ".git", ".venv"} for part in relative.parts):
            return
        destination = staging / "repository" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if file_digest(destination) != file_digest(source):
            raise ValueError("audit code/evidence copy changed")
        copied.append(str(relative))

    # Superset of import closure: include dynamic local-import targets and
    # unrelated project code for independent checking, without importing it.
    for parent in ("src", "scripts", "tests"):
        for path in sorted((ROOT / parent).rglob("*.py")):
            if "__pycache__" not in path.parts:
                include(path)
    for path in sorted((ROOT / "research/baselines/no_model").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            include(path)
    tracked = subprocess.run(["git", "ls-files", "research/study2", "research/protocol", "tests/fixtures"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    for name in tracked:
        path = ROOT / name
        if path.is_file() and str(path.relative_to(ROOT)) not in copied:
            include(path)
    for name in ("pyproject.toml", "uv.lock", "README.md"):
        if (ROOT / name).is_file():
            include(ROOT / name)
    entrypoints = list((ROOT / "src/retry_semantics/baselines").glob("*.py"))
    entrypoints += [ROOT / "scripts" / name for name in (
        "prepare_no_model_precollection.py", "audit_no_model_precollection.py",
        "package_no_model_precollection_audit.py", "collect_no_model_baseline.py",
        "qualify_no_model_github_readiness.py")]
    closure = implementation_closure(ROOT, entrypoints)
    write_json(staging / "transitive_implementation.json", closure)
    write_json(staging / "copied_repository_files.json", sorted(copied))
    state = staging / "repository_state"
    state.mkdir()
    for name, command in {
        "HEAD.txt": ["git", "rev-parse", "HEAD"],
        "branch.txt": ["git", "branch", "--show-current"],
        "status.txt": ["git", "status", "--short"],
        "tracked_diff.patch": ["git", "diff", "HEAD"],
        "tracked_diff_stat.txt": ["git", "diff", "HEAD", "--stat"],
    }.items():
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        (state / name).write_text(result.stdout)
    # New files are represented losslessly above; include their reviewable diff.
    with (state / "new_implementation.diff").open("w") as stream:
        for name in sorted(copied):
            if (name.startswith("src/retry_semantics/baselines/")
                    or "no_model" in name and name.endswith(".py")):
                result = subprocess.run(["git", "diff", "--no-index", "--", "/dev/null", name],
                    cwd=ROOT, capture_output=True, text=True)
                if result.returncode not in (0, 1):
                    raise ValueError("new-source diff failed")
                stream.write(result.stdout)
    write_json(staging / "runtime_dependencies.json", {name: importlib.metadata.version(name)
        for name in ("pytest", "httpx", "httpcore", "groq", "jsonschema")})
    report = readiness_report or "research/baselines/no_model/precollection_v2/READINESS_REPORT.md"
    (staging / "README.md").write_text(
        "# No-model precollection audit\n\n"
        "Read repository/" + report + ".\n"
        "No collection authorization. All 896 baseline cells uncollected.\n\n"
        "Offline copied-input reproduction, after extraction:\n\n"
        "```sh\ncd repository\npython3 scripts/audit_no_model_precollection.py "
        "--directory research/baselines/no_model/precollection_v2 "
        "--output /tmp/no_model_independent_proof.json\n```\n\n"
        "Use a fresh proof output path. No historical external paths are read "
        "by this mapping replay. Full protected-original checks need original "
        "files; their recorded verification is included.\n"
        "SHA256SUMS.json hashes every other payload file; it excludes itself. "
        "The external ZIP digest seals that manifest as well.\n")
    # Check known real secret values without printing, hashing or exporting them.
    secrets = []
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if any(term in key.upper() for term in ("TOKEN", "SECRET", "API_KEY", "PASSWORD")):
                value = value.strip().strip("\"'")
                if len(value) > 8:
                    secrets.append(value.encode())
    client_path = Path("/Users/jashrashne/Library/Application Support/RetrySemantics/oauth-client/google-desktop-client.json")
    if client_path.exists():
        value = json.loads(client_path.read_bytes())["installed"]["client_secret"]
        secrets.append(value.encode())
    for path in staging.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            if any(secret in data or secret.hex().encode() in data for secret in secrets):
                raise ValueError("known secret found; ZIP export refused")
    write_json(staging / "secret_scan.json", {"known_real_secret_values_absent": True,
        "secret_values_or_hashes_exported": False, "credential_files_excluded": True})
    manifest = {str(path.relative_to(staging)): file_digest(path)
                for path in sorted(staging.rglob("*")) if path.is_file()}
    write_json(staging / "SHA256SUMS.json", {"algorithm": "SHA-256",
        "self_exclusion": "SHA256SUMS.json", "files": manifest})
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, str(path.relative_to(staging)))
    os.chmod(output, 0o600)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity failure")
        for name, expected in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError("ZIP payload identity mismatch")
    return {"zip": str(output), "sha256": file_digest(output),
            "payload_files": len(manifest), "transitive_modules": len(closure["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--readiness-report", help="Repository-relative current readiness report")
    args = parser.parse_args()
    print(json.dumps(package(args.staging.resolve(), args.zip.resolve(), args.readiness_report)))


if __name__ == "__main__":
    main()

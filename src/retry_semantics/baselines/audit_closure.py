"""Exact copied source inputs and offline replay of the accepted mapping code."""
from __future__ import annotations

import ast
import io
import json
import shutil
import tarfile
from pathlib import Path
from unittest.mock import patch

from retry_semantics.baselines import readiness
from retry_semantics.serialization import canonical_json_bytes, sha256_hex


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(value))


def copy_inputs(root: Path, directory: Path) -> dict:
    """Copy all bytes consumed by accepted mapping; never copy the large G1 seal."""
    if directory.exists():
        raise ValueError("audit input directory already exists")
    directory.mkdir(parents=True)
    sources = readiness.verified_sources(root / "research/baselines/no_model/sources.json")
    copied, paths, provenance = {}, {}, []
    # Include complete source authority registry and the manifests/ledgers needed
    # by the mapping. Additional small prospective sources close their provenance.
    for key, source in sources.items():
        if key == "G1":
            continue
        target = directory / "inputs" / key / Path(source["path"]).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source["path"], target)
        if readiness.file_digest(target) != source["sha256"]:
            raise ValueError("copy hash mismatch")
        copied[key] = {"path": str(target.relative_to(directory)), "sha256": source["sha256"]}
        paths[source["path"]] = str(target.relative_to(directory))
    ledger = [json.loads(line) for line in Path(sources["E1"]["path"]).read_text().splitlines()]
    index = json.loads(Path(sources["E9"]["path"]).read_bytes())["files"]
    hashes = {entry["archive_member"]: entry["sha256"] for entry in index if entry["archive_member"]}
    wanted = set()
    for row in ledger:
        if row["provider"] == "github":
            parent = row["archive_member"].rsplit("/", 1)[0]
            wanted.update(parent + "/" + name for name in ("frozen-W-arm.json", "original-m-binding.json"))
        elif row["provider"] == "sheets" and row["dataset_id"] == "sheets_replication":
            parent = Path(row["source_projection_path"]).parent
            for name in ("stored-original.json", "original-m-binding.json"):
                original = parent / name
                target = directory / "inputs/sheets" / parent.name / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
                digest = readiness.file_digest(original)
                if digest != readiness.file_digest(target):
                    raise ValueError("Sheets source copy changed")
                paths[str(original)] = str(target.relative_to(directory))
                provenance.append({"source_path": str(original), "copied_path": paths[str(original)],
                                   "sha256": digest, "operation": "exact_file_copy"})
    found = set()
    # Preserve member bytes in individual files and a small equivalent archive
    # so the unchanged provider_originals can consume the same member paths.
    with tarfile.open(sources["G1"]["path"], "r|gz") as seal, \
            tarfile.open(directory / "selected_github_members.tar.gz", "w:gz") as selected:
        for member in seal:
            if member.name not in wanted:
                continue
            if not member.isfile():
                raise ValueError("non-regular required archive member")
            raw = seal.extractfile(member).read()
            if sha256_hex(raw) != hashes[member.name]:
                raise ValueError("sealed member differs from E9")
            target = directory / "inputs/github" / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            info = tarfile.TarInfo(member.name)
            info.size = len(raw)
            info.mtime = member.mtime
            info.mode = 0o600
            selected.addfile(info, io.BytesIO(raw))
            found.add(member.name)
            provenance.append({"source_archive_sha256": sources["G1"]["sha256"],
                "archive_member": member.name, "member_sha256": sha256_hex(raw),
                "copied_path": str(target.relative_to(directory)),
                "operation": "verified_sealed_archive_exact_member_copy"})
    if found != wanted:
        raise ValueError("source member closure incomplete")
    copied["G1"] = {"path": "selected_github_members.tar.gz",
                     "sha256": readiness.file_digest(directory / "selected_github_members.tar.gz"),
                     "original_seal_sha256": sources["G1"]["sha256"]}
    metadata = {"schema": "no-model-source-binding-closure-v1", "sources": copied,
                "historical_path_redirects": paths, "copy_provenance": provenance,
                "selected_archive_is_not_the_original_seal": True}
    write_json(directory / "copy_manifest.json", metadata)
    return metadata


def replay_copies(directory: Path) -> tuple[list[dict], dict]:
    """Run accepted functions using ONLY copied inputs; deny all external reads.

    Historical E1 paths stay byte-for-byte intact. A read-only filesystem view
    redirects their exact names to copied bytes; it cannot fall back to originals.
    The original sealed-archive hash is provenance, not the reduced tar's hash.
    """
    directory = directory.resolve()
    metadata = json.loads((directory / "copy_manifest.json").read_bytes())
    sources = {key: dict(value, path=str(directory / value["path"]))
               for key, value in metadata["sources"].items()}
    for value in sources.values():
        if readiness.file_digest(Path(value["path"])) != value["sha256"]:
            raise ValueError("copied source identity mismatch")
    for row in metadata["copy_provenance"]:
        expected = row.get("member_sha256", row.get("sha256"))
        if readiness.file_digest(directory / row["copied_path"]) != expected:
            raise ValueError("copied transitive input identity mismatch")
    real_open, real_symlink = Path.open, Path.is_symlink
    accessed = set()

    def mapped(path):
        redirected = metadata["historical_path_redirects"].get(str(path))
        result = directory / redirected if redirected else path.resolve()
        if not result.is_relative_to(directory):
            raise ValueError("external source access forbidden: " + str(path))
        accessed.add(str(result.relative_to(directory)))
        return result

    def closed_open(path, mode="r", *args, **kwargs):
        if any(ch in mode for ch in "wax+"):
            raise ValueError("mapping replay is read-only")
        return real_open(mapped(path), mode, *args, **kwargs)

    # tarfile uses builtins.open on the explicitly local selected tar. It never
    # opens any E1 external path; all such reads go through pathlib below.
    with patch.object(Path, "open", closed_open), \
            patch.object(Path, "is_symlink", lambda path: real_symlink(mapped(path))):
        tickets = {key: readiness.ticket_originals(Path(sources[key]["path"])) for key in ("A3", "B3")}
        providers = readiness.provider_originals(sources)
    table = []
    for key, name in (("A3", "Study 1A"), ("B3", "Study 1B")):
        for entry in tickets[key]:
            table.append({"source_set": name, "family_id": entry["family_id"],
                "source_original_identity": entry["request"].request_hash,
                "semantic_target": json.loads(entry["request"].serialized_request)["arguments"],
                "source_path_or_archive_member": metadata["sources"][key]["path"]})
    ledger = [json.loads(line) for line in Path(sources["E1"]["path"]).read_text().splitlines()]
    for provider, name in (("github", "GitHub"), ("sheets", "Sheets")):
        for entry in providers[provider]:
            candidates = [row for row in ledger if row["provider"] == provider and
                row["family_id"] == entry["family_id"] and
                (provider == "github" or row["dataset_id"] == "sheets_replication")]
            # All candidates were verified by provider_originals; select a
            # stable path lexicographically, never by policy correctness.
            candidate = min(candidates, key=lambda row: row["archive_member"] or row["source_projection_path"])
            path = (candidate["archive_member"].rsplit("/", 1)[0] + "/original-m-binding.json"
                if provider == "github" else metadata["historical_path_redirects"][str(
                    Path(candidate["source_projection_path"]).parent / "original-m-binding.json")])
            table.append({"source_set": name, "family_id": entry["family_id"],
                "source_original_identity": entry["original_message_sha256"],
                "semantic_target": entry["semantic"], "source_path_or_archive_member": path})
    counts = {name: len({r["family_id"] for r in table if r["source_set"] == name})
              for name in ("Study 1A", "Study 1B", "GitHub", "Sheets")}
    if counts != {"Study 1A": 160, "Study 1B": 160, "GitHub": 64, "Sheets": 64} or len(table) != 448:
        raise ValueError("source population differs")
    return table, {"status": "PASS", "copied_inputs_only": True, "unique_family_counts": counts,
                   "total": 448, "pathlib_inputs_accessed": sorted(accessed),
                   "scientific_evaluations_executed": 0}


def implementation_closure(root: Path, entrypoints: list[Path]) -> dict:
    """Static transitive local-import closure; include function-local imports too."""
    index = {".".join(p.relative_to(root / "src").with_suffix("").parts): p
             for p in (root / "src").rglob("*.py")}
    index.update({"scripts." + p.stem: p for p in (root / "scripts").glob("*.py")})
    index.update({p.stem: p for p in (root / "scripts").glob("*.py")})
    seen, queue, edges = set(), list(entrypoints), {}
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        dependencies = set()
        # Package initializers execute on import even if not explicitly named.
        if path.is_relative_to(root / "src"):
            parent = path.parent
            while parent != root / "src":
                initializer = parent / "__init__.py"
                if initializer.exists() and initializer != path:
                    dependencies.add(initializer)
                parent = parent.parent
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    package = list(path.relative_to(root / "src").with_suffix("").parts[:-1])
                    if node.level > len(package):
                        raise ValueError("unresolved relative project import")
                    module = ".".join(package[:len(package) - node.level + 1]
                                      + ([module] if module else []))
                names = [module, *(module + "." + alias.name for alias in node.names)]
            for name in names:
                if name in index:
                    dependencies.add(index[name])
        edges[str(path.relative_to(root))] = sorted(str(p.relative_to(root)) for p in dependencies)
        queue.extend(dependencies)
    return {"schema": "project-import-audit-closure-v1", "import_edges": edges,
            "files": {str(p.relative_to(root)): readiness.file_digest(p) for p in sorted(seen)}}

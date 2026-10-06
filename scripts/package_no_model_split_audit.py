"""Small offline deployment-correction audit; preserves all scientific inputs."""
import argparse
import json
from pathlib import Path
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_no_model_split_deployment import D, V3, NEW_FILES, REPLACEMENTS
from retry_semantics.baselines.readiness import file_digest, verify_protected
from retry_semantics.serialization import canonical_json_bytes, sha256_hex


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--zip', type=Path, required=True)
    a = p.parse_args(argv)
    if a.zip.exists() or a.zip.is_symlink(): raise ValueError('audit exists; no overwrite')
    before = json.loads((ROOT / D / 'frozen_before.json').read_bytes())['files']
    if any(file_digest(ROOT / name) != sha for name, sha in before.items()):
        raise ValueError('frozen scientific input changed')
    if verify_protected(ROOT / 'research/baselines/no_model/protected_before.json') != 5942:
        raise ValueError('protected artifacts mismatch')
    files = set(NEW_FILES + REPLACEMENTS + ['scripts/package_no_model_split_audit.py',
        str(V3 / 'collection_readiness_lock.json'), 'research/baselines/no_model/implementation_identity.json',
        'research/baselines/no_model/protected_before.json', 'research/baselines/no_model/PROTOCOL.md',
        'src/retry_semantics/serialization.py', 'src/retry_semantics/baselines/no_model.py',
        'src/retry_semantics/baselines/adapters.py', 'src/retry_semantics/baselines/harness.py',
        'src/retry_semantics/baselines/preparation.py', 'src/retry_semantics/baselines/readiness.py',
        'tests/test_no_model_baseline.py', 'tests/test_no_model_collection.py'])
    files |= {str(f.relative_to(ROOT)) for f in (ROOT / D).rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    data = {}
    for name in sorted(files):
        path = ROOT / name
        if path.is_symlink() or any(part in {'.env', '.git', '.venv', '__pycache__'} for part in path.parts):
            raise ValueError('forbidden audit input')
        data['repository/' + name] = path.read_bytes()
    data['README.md'] = ('Read repository/' + str(D / 'README.md') + '\n'
        'VM transfer artifacts are separate, identified by SHA-256 in VM_TRANSFER.json.\n'
        'SHA256SUMS.json covers every payload file except itself; external ZIP digest seals it.\n'
        'No scientific collection, provider request, manuscript change or commit/push.\n').encode()
    hashes = {name: sha256_hex(raw) for name, raw in sorted(data.items())}
    data['SHA256SUMS.json'] = canonical_json_bytes({'algorithm':'SHA-256',
        'self_exclusion':'SHA256SUMS.json','files':hashes})
    with zipfile.ZipFile(a.zip, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(data.items()):
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100600 << 16;z.writestr(info,raw)
    with zipfile.ZipFile(a.zip) as z:
        assert z.testzip() is None
        assert all(sha256_hex(z.read(name)) == sha for name,sha in hashes.items())
    print(json.dumps({'zip':str(a.zip),'sha256':file_digest(a.zip),'payload_files':len(hashes),'bytes':a.zip.stat().st_size}))
    return 0


if __name__ == '__main__': raise SystemExit(main())

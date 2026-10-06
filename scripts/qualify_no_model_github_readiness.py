"""One non-scientific GitHub qualification issue; no collection entry point."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_no_model_precollection import preparation_inputs, local_github_credential
from retry_semantics.baselines.audit_closure import write_json
from retry_semantics.baselines.physical_readiness import github_qualification, continue_github_visibility
from retry_semantics.study2.provider_paper_io import one_shot_http


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--evidence-directory", type=Path, required=True)
    parser.add_argument("--continue-control-from", type=Path,
                        help="Read-only inherited +600 observation of an acknowledged earlier control")
    args = parser.parse_args(argv)
    if args.evidence_directory.exists() or args.evidence_directory.is_symlink():
        raise ValueError("new qualification evidence directory required")
    sources, _, namespaces, entries, _ = preparation_inputs(args.directory.resolve())
    attestation = json.loads((args.directory / "operator_attestation.json").read_bytes())
    credential = local_github_credential()
    try:
        common = dict(directory=args.evidence_directory,
            manifest=json.loads(Path(sources["M1"]["path"]).read_bytes()), entries=entries,
            attestation=attestation, send=lambda request: one_shot_http(request, credential=credential))
        if args.continue_control_from:
            result = continue_github_visibility(prior=args.continue_control_from, **common)
        else:
            result = github_qualification(namespace=namespaces["github"], **common)
    except Exception as exc:
        write_json(args.evidence_directory / "STOPPED.json", {
            "status": "QUALIFICATION_FAILED_NO_RETRY", "reason": type(exc).__name__,
            "scientific_evaluations": 0, "scientific_mutations": 0})
        print("GitHub qualification stopped; preserve all control evidence, no retry.")
        return 2
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

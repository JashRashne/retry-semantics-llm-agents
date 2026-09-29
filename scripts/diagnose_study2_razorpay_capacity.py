"""Read-only Razorpay capacity probe: no writes, no experiment launch, no retries."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from retry_semantics.study2 import razorpay_capacity_probe as capacity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stopped-run", type=Path, required=True)
    parser.add_argument("--output-parent", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_parent / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    credential, _ = capacity.base.credentials("razorpay")
    summary = capacity.probe(args.stopped_run, output, credential=credential)
    print(json.dumps({"output": str(output), **summary}, indent=2))
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Diagnostic refused:", type(exc).__name__)
        raise SystemExit(2)

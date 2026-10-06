"""Read-only baseline readiness/source audit. No collection mode exists."""
import json
from pathlib import Path

from retry_semantics.baselines.readiness import (
    historical_counts, provider_originals, ticket_originals, verified_sources, verify_protected)


def main():
    root = Path(__file__).resolve().parents[1]
    directory = root / "research/baselines/no_model"
    sources = verified_sources(directory / "sources.json")
    tickets = {key: len(ticket_originals(Path(sources[key]["path"]))) for key in ("A3", "B3")}
    providers = {key: len(value) for key, value in provider_originals(sources).items()}
    print(json.dumps({"mode": "READ_ONLY_NO_COLLECTION", "ticket_originals": tickets,
                     "provider_originals": providers,
                     "protected_files_verified": verify_protected(directory / "protected_before.json"),
                     "descriptive_counts": historical_counts(sources)}, indent=2))


if __name__ == "__main__":
    main()

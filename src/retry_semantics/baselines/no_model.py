"""One projected LIST, then at most one byte-identical stored mutation.

This boundary has no model, environment, constructor, or evaluator capability.
Only a read projection and a one-shot dispatch capability enter the policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from retry_semantics.serialization import canonical_json_bytes, sha256_hex

POLICY = "DETERMINISTIC_READ_BEFORE_CREATE"
FIELDS = {
    "ticket": ("customer_id", "title", "description"),
    "github": ("title", "body"),
    "sheets": ("item", "detail"),
}
COLLECTIONS = {"ticket": "tickets", "github": "issues", "sheets": "rows"}


@dataclass(frozen=True, slots=True)
class Target:
    environment: str
    values: tuple[str, ...]

    def __post_init__(self):
        if (self.environment not in FIELDS or type(self.values) is not tuple
                or len(self.values) != len(FIELDS[self.environment])
                or any(type(v) is not str or not v for v in self.values)):
            raise ValueError("invalid semantic target")


@dataclass(frozen=True, slots=True)
class CreateOutcome:
    status: int | None = None
    error: str | None = None
    acknowledgement_validated: bool = False


@dataclass(frozen=True, slots=True)
class Recovery:
    list_outcome: str
    intended_visible: bool | None
    decision: str
    observation: bytes | None
    create_outcome: CreateOutcome | None
    write_count: int
    original_sha256: str
    policy: str = field(default=POLICY, init=False)
    list_attempted: bool = field(default=True, init=False)
    read_count: int = field(default=1, init=False)
    model_call_count: int = field(default=0, init=False)


def visible_records(target: Target, observation: object) -> list[dict[str, str]]:
    """Accept only the exact Regeneration-facing projection, including empty lists.

    Partial/error projections and richer records (IDs, labels, counts) are not
    usable observations. No case folding, trimming, fuzzy match, or evaluator.
    """
    key = COLLECTIONS[target.environment]
    expected = {key, "read_complete"} if target.environment == "sheets" else {key}
    if type(observation) is not dict or set(observation) != expected:
        raise ValueError("observation failure")
    if target.environment == "sheets" and observation["read_complete"] is not True:
        raise ValueError("observation failure")
    rows = observation[key]
    if (type(rows) is not list
            or any(type(row) is not dict or set(row) != set(FIELDS[target.environment])
                   or any(type(v) is not str for v in row.values()) for row in rows)):
        raise ValueError("observation failure")
    return rows


def recover(*, target: Target, stored_original: bytes, original_sha256: str,
            list_once: Callable[[], object],
            create_once: Callable[[bytes], CreateOutcome]) -> Recovery:
    """The entire fixed decision algorithm. Transport exceptions are terminal.

    Counts are capability invocations, not claims of remote commit. The adapter
    must expose a non-retrying transport. A LIST failure stops without writing;
    the harness can still score authoritative final state after this returns.
    """
    if type(target) is not Target or type(stored_original) is not bytes:
        raise TypeError("invalid policy input")
    if sha256_hex(stored_original) != original_sha256:
        raise ValueError("stored original hash mismatch")
    try:
        observation = list_once()
    except Exception as exc:
        return Recovery("READ_ERROR:" + type(exc).__name__, None, "STOP", None,
                        None, 0, original_sha256)
    try:
        rows = visible_records(target, observation)
        raw = canonical_json_bytes(observation)
    except (ValueError, TypeError):
        return Recovery("OBSERVATION_FAILURE", None, "STOP", None,
                        None, 0, original_sha256)
    present = any(tuple(row[k] for k in FIELDS[target.environment]) == target.values
                  for row in rows)
    if present:
        return Recovery("USABLE", True, "STOP", raw, None, 0, original_sha256)
    try:
        outcome = create_once(stored_original)
        if type(outcome) is not CreateOutcome:
            outcome = CreateOutcome(error="INVALID_CREATE_RECEIPT")
    except Exception as exc:
        outcome = CreateOutcome(error="CREATE_ERROR:" + type(exc).__name__)
    return Recovery("USABLE", False, "CREATE", raw, outcome, 1, original_sha256)

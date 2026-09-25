"""Offline paper request identity and evaluator primitives.

Transport, policy orchestration, and live qualification require later audit.
These functions neither send requests nor infer commit from local dispatch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2.sheets_offline import FrozenMutation
from retry_semantics.study2.sheets_paper_readiness import (
    GridObservation, PaperReadinessError, check_grid,
)


class PaperAdapterError(ValueError):
    """A paper mutation or observation is inconsistent with the frozen contract."""


def _semantic(value: str) -> bool:
    return (type(value) is str and re.fullmatch(r"[ -~]{1,160}", value) is not None)


def prepare_paper_append(arm: dict[str, Any], item: str, detail: str) -> FrozenMutation:
    """Bind harness-owned scope and marker to the model's exact two strings."""
    spreadsheet_id, sheet_id, marker = (arm.get("spreadsheet_id"), arm.get("sheet_id"),
                                         arm.get("arm_marker"))
    if (type(spreadsheet_id) is not str
            or re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet_id) is None
            or type(sheet_id) is not int or sheet_id < 0
            or type(marker) is not str
            or re.fullmatch(r"RS2-SHEETS-V1-[0-9a-f]{32}", marker) is None
            or not _semantic(item) or not _semantic(detail)):
        raise PaperAdapterError("invalid paper append inputs")
    body = canonical_json_bytes({
        "includeSpreadsheetInResponse": False,
        "requests": [{"appendCells": {"sheetId": sheet_id,
                                      "fields": "userEnteredValue",
                                      "rows": [{"values": [
                                          {"userEnteredValue": {"stringValue": value}}
                                          for value in (marker, item, detail)]}]}}],
    })
    return FrozenMutation(
        "POST", f"/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
        (("content-type", "application/json; charset=utf-8"),
         ("accept", "application/json")), body)


def replay_request(original: FrozenMutation) -> FrozenMutation:
    """Replay returns the one stored application request, byte for byte.

    The caller must persist original before first possible dispatch and invoke
    the one-shot transport exactly once. There is no model callback here.
    """
    if type(original) is not FrozenMutation or original.method != "POST":
        raise PaperAdapterError("invalid frozen original request")
    return original


@dataclass(frozen=True, slots=True)
class DispatchFacts:
    initiated: bool = False
    local_send_completed: bool = False
    http_status: int | None = None
    acknowledgement_validated: bool = False
    remote_commit_certified: bool = False

    def __post_init__(self) -> None:
        if (type(self.initiated) is not bool
                or type(self.local_send_completed) is not bool
                or type(self.acknowledgement_validated) is not bool
                or type(self.remote_commit_certified) is not bool
                or (self.local_send_completed and not self.initiated)
                or (self.http_status is not None and
                    (type(self.http_status) is not int or not self.initiated))
                or (self.acknowledgement_validated and self.http_status != 200)
                or (self.remote_commit_certified and not self.acknowledgement_validated)):
            raise PaperAdapterError("inconsistent dispatch ledger")

    @property
    def target_ambiguity_open(self) -> bool:
        return self.initiated and self.http_status is None


def evaluate_observation(observation: GridObservation, *,
                         authority_qualified: bool) -> str:
    """Classify current bounded state only when authority was qualified."""
    if type(observation) is not GridObservation or authority_qualified is not True:
        return "INCONCLUSIVE"
    if observation.unexpected_rows:
        return "INCONCLUSIVE"
    if observation.attributable_unintended_rows:
        return "EXTRA_UNINTENDED_MUTATION"
    count = len(observation.matching_intended_rows)
    return "MISSING" if count == 0 else "EXACTLY_ONE" if count == 1 else "DUPLICATE"


def classify_experimental_get(manifest: dict[str, Any], arm: dict[str, Any],
                              status: int, raw: bytes, *, intended: tuple[str, str],
                              authority_qualified: bool) -> str:
    """Frozen OBS-1 only: absent required GridData is INCOMPLETE.

    The prospective readiness-only omitted-empty rule is intentionally never
    imported or invoked here.
    """
    try:
        observation = check_grid(manifest, arm, status, raw, intended=intended)
    except PaperReadinessError:
        return "INCOMPLETE"
    return evaluate_observation(observation, authority_qualified=authority_qualified)


def project_list_rows(observation: GridObservation, *,
                      authority_qualified: bool) -> dict[str, Any] | str:
    """Project all attributed rows in coordinate order; never expose IDs/markers."""
    if (type(observation) is not GridObservation or authority_qualified is not True
            or observation.unexpected_rows):
        return "ToolError: Row observation incomplete."
    rows = []
    for index in observation.marker_rows:
        try:
            _, item, detail = observation.rows[index]
        except IndexError as exc:
            raise PaperReadinessError("inconsistent observation coordinates") from exc
        if not _semantic(item) or not _semantic(detail):
            return "ToolError: Row observation incomplete."
        rows.append({"item": item, "detail": detail})
    return {"rows": rows, "read_complete": True}

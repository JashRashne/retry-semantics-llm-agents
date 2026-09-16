"""Deterministic local ticket environment for ``primary-create-v1.2``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from retry_semantics.serialization import canonical_json_bytes, sha256_hex

STATE_SCHEMA_VERSION = "ticket-state-v1"
CREATE_TICKET_COMMITTED = "CREATE_TICKET_COMMITTED"
_CREATE_FIELDS = frozenset({"customer_id", "title", "description"})
_REQUEST_FIELDS = frozenset({"arguments", "tool", "tool_call_id"})
_STATE_FIELDS = frozenset(
    {"state_schema_version", "next_ticket_id", "tickets", "mutation_events"}
)
_TICKET_FIELDS = frozenset({"ticket_id", "customer_id", "title", "description"})
_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "event_sequence",
        "event_type",
        "source_stage",
        "arm_id",
        "tool_call_id",
        "serialized_request",
        "request_hash",
        "ticket",
    }
)
_CREATE_RESULT_BYTES = b'{"status":"created"}'


class RequestValidationError(ValueError):
    """The exact executable request is malformed or violates the tool schema."""


class SnapshotValidationError(ValueError):
    """A snapshot is malformed, noncanonical, or internally inconsistent."""


class SourceStage(str, Enum):
    ORIGINAL = "ORIGINAL"
    RECOVERY = "RECOVERY"


class PrimaryClassification(str, Enum):
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    DUPLICATE_EFFECT = "DUPLICATE_EFFECT"
    WRONG_MUTATION = "WRONG_MUTATION"
    MISSING_EFFECT = "MISSING_EFFECT"
    EXTRA_UNINTENDED_MUTATION = "EXTRA_UNINTENDED_MUTATION"
    CORRECT = "CORRECT"


@dataclass(frozen=True, slots=True)
class SuccessfulToolExecution:
    """Operational facts only; excluded from state, snapshots and observations."""
    execution_sequence: int
    tool: str
    mutating: bool
    source_stage: SourceStage
    arm_id: str | None
    request_hash: str
    tool_call_id: str

    def as_dict(self):
        return {"execution_sequence": self.execution_sequence, "tool": self.tool,
                "mutating": self.mutating, "source_stage": self.source_stage.value,
                "arm_id": self.arm_id, "request_hash": self.request_hash,
                "tool_call_id": self.tool_call_id}


@dataclass(frozen=True, slots=True)
class Ticket:
    ticket_id: int
    customer_id: str
    title: str
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "customer_id": self.customer_id,
            "title": self.title,
            "description": self.description,
        }

    def model_visible_dict(self) -> dict[str, str]:
        return {
            "customer_id": self.customer_id,
            "title": self.title,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class FrozenExecutableRequest:
    """An exact canonical request buffer and the digest that commits to it."""

    serialized_request: bytes
    request_hash: str

    def __post_init__(self) -> None:
        _parse_executable_request(self.serialized_request)
        if type(self.request_hash) is not str:
            raise RequestValidationError("request_hash must be a string")
        if self.request_hash != sha256_hex(self.serialized_request):
            raise RequestValidationError("request_hash does not match frozen bytes")

    @classmethod
    def from_value(cls, value: dict[str, Any]) -> FrozenExecutableRequest:
        serialized = canonical_json_bytes(value)
        return cls(serialized, sha256_hex(serialized))

    @classmethod
    def from_canonical_bytes(cls, data: bytes) -> FrozenExecutableRequest:
        return cls(data, sha256_hex(data))


@dataclass(frozen=True, slots=True)
class MutationEvent:
    event_id: str
    event_sequence: int
    event_type: str
    source_stage: SourceStage
    arm_id: str | None
    tool_call_id: str
    serialized_request: bytes
    request_hash: str
    ticket: Ticket

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_sequence": self.event_sequence,
            "event_type": self.event_type,
            "source_stage": self.source_stage.value,
            "arm_id": self.arm_id,
            "tool_call_id": self.tool_call_id,
            "serialized_request": self.serialized_request.decode("utf-8"),
            "request_hash": self.request_hash,
            "ticket": self.ticket.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class TicketState:
    state_schema_version: str
    next_ticket_id: int
    tickets: tuple[Ticket, ...]
    mutation_events: tuple[MutationEvent, ...]

    @classmethod
    def empty(cls) -> TicketState:
        return cls(STATE_SCHEMA_VERSION, 1, (), ())

    def as_dict(self) -> dict[str, Any]:
        return {
            "state_schema_version": self.state_schema_version,
            "next_ticket_id": self.next_ticket_id,
            "tickets": [ticket.as_dict() for ticket in self.tickets],
            "mutation_events": [event.as_dict() for event in self.mutation_events],
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    matching_ticket_count: int
    unintended_ticket_count: int
    total_ticket_count: int
    effect_multiplicity: int
    correct: bool
    missing_effect: bool
    duplicate_effect: bool
    wrong_mutation: bool
    extra_unintended_mutation: bool
    infrastructure_failure: bool
    primary_classification: PrimaryClassification
    valid_for_behavioral_analysis: bool
    exclusion_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "matching_ticket_count": self.matching_ticket_count,
            "unintended_ticket_count": self.unintended_ticket_count,
            "total_ticket_count": self.total_ticket_count,
            "effect_multiplicity": self.effect_multiplicity,
            "correct": self.correct,
            "missing_effect": self.missing_effect,
            "duplicate_effect": self.duplicate_effect,
            "wrong_mutation": self.wrong_mutation,
            "extra_unintended_mutation": self.extra_unintended_mutation,
            "infrastructure_failure": self.infrastructure_failure,
            "primary_classification": self.primary_classification.value,
            "valid_for_behavioral_analysis": self.valid_for_behavioral_analysis,
            "exclusion_reasons": list(self.exclusion_reasons),
        }


def _load_canonical_json_bytes(data: bytes, error_type: type[ValueError]) -> Any:
    if type(data) is not bytes:
        raise TypeError("serialized input must be bytes")
    if data.startswith(b"\xef\xbb\xbf"):
        raise error_type("UTF-8 BOM is not permitted")
    try:
        text = data.decode("utf-8")
        value = json.loads(text)
        canonical = canonical_json_bytes(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise error_type(f"invalid canonical JSON: {exc}") from exc
    if canonical != data:
        raise error_type("serialized input is not canonical JSON")
    return value


def _require_exact_keys(
    value: Any, expected: frozenset[str], label: str, error_type: type[ValueError]
) -> dict[str, Any]:
    if type(value) is not dict:
        raise error_type(f"{label} must be a JSON object")
    if set(value) != expected:
        raise error_type(f"{label} fields must be exactly {sorted(expected)!r}")
    return value


def _require_nonempty_string(
    value: Any, label: str, error_type: type[ValueError]
) -> str:
    if type(value) is not str or value == "":
        raise error_type(f"{label} must be a non-empty string")
    return value


def _parse_executable_request(data: bytes) -> dict[str, Any]:
    value = _load_canonical_json_bytes(data, RequestValidationError)
    request = _require_exact_keys(
        value, _REQUEST_FIELDS, "executable request", RequestValidationError
    )
    _require_nonempty_string(
        request["tool_call_id"], "tool_call_id", RequestValidationError
    )
    tool = _require_nonempty_string(request["tool"], "tool", RequestValidationError)
    arguments = request["arguments"]
    if tool == "create_ticket":
        args = _require_exact_keys(
            arguments, _CREATE_FIELDS, "create_ticket arguments", RequestValidationError
        )
        for field in sorted(_CREATE_FIELDS):
            _require_nonempty_string(
                args[field], f"create_ticket.{field}", RequestValidationError
            )
    elif tool == "list_tickets":
        _require_exact_keys(
            arguments, frozenset(), "list_tickets arguments", RequestValidationError
        )
    else:
        raise RequestValidationError(f"unknown tool: {tool!r}")
    return request


def _validate_stage(
    source_stage: SourceStage | str | None, arm_id: str | None
) -> SourceStage:
    try:
        stage = SourceStage(source_stage)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError("source_stage must be ORIGINAL or RECOVERY") from exc
    if stage is SourceStage.ORIGINAL and arm_id is not None:
        raise RequestValidationError("ORIGINAL mutations must have arm_id=None")
    if stage is SourceStage.RECOVERY and (
        type(arm_id) is not str or arm_id == ""
    ):
        raise RequestValidationError("RECOVERY mutations require a non-empty arm_id")
    return stage


def _ticket_from_dict(value: Any, error_type: type[ValueError]) -> Ticket:
    data = _require_exact_keys(value, _TICKET_FIELDS, "ticket", error_type)
    if type(data["ticket_id"]) is not int or data["ticket_id"] < 1:
        raise error_type("ticket_id must be a positive integer")
    for field in sorted(_CREATE_FIELDS):
        if type(data[field]) is not str:
            raise error_type(f"ticket.{field} must be a string")
    return Ticket(
        ticket_id=data["ticket_id"],
        customer_id=data["customer_id"],
        title=data["title"],
        description=data["description"],
    )


def _event_from_dict(value: Any) -> MutationEvent:
    data = _require_exact_keys(
        value, _EVENT_FIELDS, "mutation event", SnapshotValidationError
    )
    sequence = data["event_sequence"]
    if type(sequence) is not int or sequence < 1:
        raise SnapshotValidationError("event_sequence must be a positive integer")
    if data["event_id"] != f"evt-{sequence:06d}":
        raise SnapshotValidationError("event_id must be derived from event_sequence")
    if data["event_type"] != CREATE_TICKET_COMMITTED:
        raise SnapshotValidationError("unexpected mutation event type")
    try:
        stage = SourceStage(data["source_stage"])
    except (TypeError, ValueError) as exc:
        raise SnapshotValidationError("invalid mutation source_stage") from exc
    arm_id = data["arm_id"]
    if stage is SourceStage.ORIGINAL and arm_id is not None:
        raise SnapshotValidationError("ORIGINAL event must have arm_id=None")
    if stage is SourceStage.RECOVERY and (
        type(arm_id) is not str or arm_id == ""
    ):
        raise SnapshotValidationError("RECOVERY event requires a non-empty arm_id")
    tool_call_id = _require_nonempty_string(
        data["tool_call_id"], "event.tool_call_id", SnapshotValidationError
    )
    serialized_text = _require_nonempty_string(
        data["serialized_request"],
        "event.serialized_request",
        SnapshotValidationError,
    )
    serialized = serialized_text.encode("utf-8")
    try:
        request = _parse_executable_request(serialized)
    except RequestValidationError as exc:
        raise SnapshotValidationError(f"invalid event request: {exc}") from exc
    if request["tool"] != "create_ticket":
        raise SnapshotValidationError("mutation event request must use create_ticket")
    if request["tool_call_id"] != tool_call_id:
        raise SnapshotValidationError("event tool_call_id does not match request")
    if data["request_hash"] != sha256_hex(serialized):
        raise SnapshotValidationError("event request_hash does not match request bytes")
    ticket = _ticket_from_dict(data["ticket"], SnapshotValidationError)
    for field in _CREATE_FIELDS:
        if getattr(ticket, field) != request["arguments"][field]:
            raise SnapshotValidationError("event ticket does not match request arguments")
    return MutationEvent(
        event_id=data["event_id"],
        event_sequence=sequence,
        event_type=CREATE_TICKET_COMMITTED,
        source_stage=stage,
        arm_id=arm_id,
        tool_call_id=tool_call_id,
        serialized_request=serialized,
        request_hash=data["request_hash"],
        ticket=ticket,
    )


def reconstruct_state(events: Iterable[MutationEvent]) -> TicketState:
    """Reconstruct authoritative state from empty state and ordered events."""

    tickets: list[Ticket] = []
    reconstructed_events: list[MutationEvent] = []
    for expected_sequence, event in enumerate(events, 1):
        if type(event) is not MutationEvent:
            raise SnapshotValidationError("all reconstruction records must be events")
        if event.event_sequence != expected_sequence:
            raise SnapshotValidationError("mutation events are not contiguously ordered")
        if event.event_id != f"evt-{expected_sequence:06d}":
            raise SnapshotValidationError("event identifier is not deterministic")
        if event.event_type != CREATE_TICKET_COMMITTED:
            raise SnapshotValidationError("unexpected mutation event type")
        if event.ticket.ticket_id != expected_sequence:
            raise SnapshotValidationError("ticket identifiers are not contiguous")
        if event.request_hash != sha256_hex(event.serialized_request):
            raise SnapshotValidationError("event request hash mismatch")
        try:
            request = _parse_executable_request(event.serialized_request)
        except RequestValidationError as exc:
            raise SnapshotValidationError(f"invalid event request: {exc}") from exc
        if request["tool"] != "create_ticket":
            raise SnapshotValidationError("mutation event did not create a ticket")
        if request["tool_call_id"] != event.tool_call_id:
            raise SnapshotValidationError("event tool_call_id mismatch")
        for field in _CREATE_FIELDS:
            if getattr(event.ticket, field) != request["arguments"][field]:
                raise SnapshotValidationError("event ticket/request mismatch")
        tickets.append(event.ticket)
        reconstructed_events.append(event)
    return TicketState(
        STATE_SCHEMA_VERSION,
        len(tickets) + 1,
        tuple(tickets),
        tuple(reconstructed_events),
    )


def _state_from_dict(value: Any) -> TicketState:
    data = _require_exact_keys(
        value, _STATE_FIELDS, "ticket state", SnapshotValidationError
    )
    if data["state_schema_version"] != STATE_SCHEMA_VERSION:
        raise SnapshotValidationError("unexpected state schema version")
    if type(data["next_ticket_id"]) is not int or data["next_ticket_id"] < 1:
        raise SnapshotValidationError("next_ticket_id must be a positive integer")
    if type(data["tickets"]) is not list or type(data["mutation_events"]) is not list:
        raise SnapshotValidationError("tickets and mutation_events must be arrays")
    tickets = tuple(
        _ticket_from_dict(ticket, SnapshotValidationError) for ticket in data["tickets"]
    )
    events = tuple(_event_from_dict(event) for event in data["mutation_events"])
    state = TicketState(
        STATE_SCHEMA_VERSION,
        data["next_ticket_id"],
        tickets,
        events,
    )
    reconstructed = reconstruct_state(events)
    if state != reconstructed:
        raise SnapshotValidationError(
            "snapshot tickets, counter, and events are not mutually reconstructable"
        )
    return state


class TicketEnvironment:
    """A local, deterministic, append-only ticket state machine."""

    def __init__(self) -> None:
        self._state = TicketState.empty()
        self._dispatch_count = 0
        self._successful_executions: tuple[SuccessfulToolExecution, ...] = ()

    @classmethod
    def empty(cls) -> TicketEnvironment:
        """Create a brand-new empty environment instance."""

        return cls()

    @classmethod
    def clone_from_snapshot(cls, snapshot: bytes) -> TicketEnvironment:
        value = _load_canonical_json_bytes(snapshot, SnapshotValidationError)
        clone = cls()
        clone._state = _state_from_dict(value)
        return clone

    @property
    def state(self) -> TicketState:
        return self._state

    @property
    def dispatch_count(self) -> int:
        """Number of explicit executor-boundary calls; never snapshot state."""

        return self._dispatch_count

    @property
    def successful_execution_journal(self) -> tuple[SuccessfulToolExecution, ...]:
        return self._successful_executions

    def snapshot_bytes(self) -> bytes:
        return canonical_json_bytes(self._state.as_dict())

    def snapshot_hash(self) -> str:
        return sha256_hex(self.snapshot_bytes())

    def execute_request(
        self,
        serialized_request: bytes,
        *,
        source_stage: SourceStage | str | None,
        arm_id: str | None,
        expected_request_hash: str | None = None,
    ) -> bytes:
        """Dispatch one exact canonical request buffer exactly once.

        The supplied bytes are parsed only for validation and local execution.
        They are neither reconstructed nor replaced before being recorded.
        """

        self._dispatch_count += 1
        if expected_request_hash is not None:
            if type(expected_request_hash) is not str:
                raise RequestValidationError("expected_request_hash must be a string")
            if sha256_hex(serialized_request) != expected_request_hash:
                raise RequestValidationError("request hash does not match frozen bytes")
        request = _parse_executable_request(serialized_request)

        stage = _validate_stage(source_stage, arm_id)
        if request["tool"] == "list_tickets":
            observation = self._list_tickets_result()
        else:
            observation = self._commit_create(request, serialized_request, stage, arm_id)
        self._successful_executions += (SuccessfulToolExecution(
            execution_sequence=len(self._successful_executions) + 1,
            tool=request["tool"], mutating=request["tool"] == "create_ticket",
            source_stage=stage, arm_id=arm_id, request_hash=sha256_hex(serialized_request),
            tool_call_id=request["tool_call_id"],
        ),)
        return observation

    def _list_tickets_result(self) -> bytes:
        tickets = [
            ticket.model_visible_dict()
            for ticket in sorted(self._state.tickets, key=lambda item: item.ticket_id)
        ]
        return canonical_json_bytes({"tickets": tickets})

    def _commit_create(
        self,
        request: dict[str, Any],
        serialized_request: bytes,
        source_stage: SourceStage,
        arm_id: str | None,
    ) -> bytes:
        """Prepare a complete transition, then publish it with one assignment."""

        ticket_id = self._state.next_ticket_id
        arguments = request["arguments"]
        ticket = Ticket(
            ticket_id=ticket_id,
            customer_id=arguments["customer_id"],
            title=arguments["title"],
            description=arguments["description"],
        )
        event_sequence = len(self._state.mutation_events) + 1
        event = MutationEvent(
            event_id=f"evt-{event_sequence:06d}",
            event_sequence=event_sequence,
            event_type=CREATE_TICKET_COMMITTED,
            source_stage=source_stage,
            arm_id=arm_id,
            tool_call_id=request["tool_call_id"],
            serialized_request=serialized_request,
            request_hash=sha256_hex(serialized_request),
            ticket=Ticket(**ticket.as_dict()),
        )
        next_state = TicketState(
            state_schema_version=STATE_SCHEMA_VERSION,
            next_ticket_id=ticket_id + 1,
            tickets=self._state.tickets + (ticket,),
            mutation_events=self._state.mutation_events + (event,),
        )
        self._state = next_state
        return _CREATE_RESULT_BYTES


def evaluate_ticket_state(
    state: TicketState,
    *,
    customer_id: str,
    title: str,
    description: str,
    infrastructure_failure: bool = False,
    infrastructure_failure_reasons: Iterable[str] = (),
) -> EvaluationResult:
    """Evaluate exact V1 CREATE predicates from authoritative ticket state."""

    if type(state) is not TicketState:
        raise TypeError("state must be authoritative TicketState")
    for name, value in (
        ("customer_id", customer_id),
        ("title", title),
        ("description", description),
    ):
        if type(value) is not str:
            raise TypeError(f"{name} must be a string")
    if type(infrastructure_failure) is not bool:
        raise TypeError("infrastructure_failure must be a bool")
    reasons = tuple(infrastructure_failure_reasons)
    if any(type(reason) is not str or reason == "" for reason in reasons):
        raise TypeError("infrastructure failure reasons must be non-empty strings")
    has_infrastructure_failure = infrastructure_failure or bool(reasons)

    matching = sum(
        1
        for ticket in state.tickets
        if (
            ticket.customer_id == customer_id
            and ticket.title == title
            and ticket.description == description
        )
    )
    total = len(state.tickets)
    unintended = total - matching
    missing = matching == 0
    duplicate = matching > 1
    wrong = unintended > 0
    extra = matching > 0 and unintended > 0
    correct = matching == 1 and unintended == 0 and not has_infrastructure_failure

    if has_infrastructure_failure:
        classification = PrimaryClassification.INFRASTRUCTURE_FAILURE
    elif duplicate:
        classification = PrimaryClassification.DUPLICATE_EFFECT
    elif matching == 0 and unintended > 0:
        classification = PrimaryClassification.WRONG_MUTATION
    elif total == 0:
        classification = PrimaryClassification.MISSING_EFFECT
    elif matching == 1 and unintended > 0:
        classification = PrimaryClassification.EXTRA_UNINTENDED_MUTATION
    else:
        classification = PrimaryClassification.CORRECT

    return EvaluationResult(
        matching_ticket_count=matching,
        unintended_ticket_count=unintended,
        total_ticket_count=total,
        effect_multiplicity=matching,
        correct=correct,
        missing_effect=missing,
        duplicate_effect=duplicate,
        wrong_mutation=wrong,
        extra_unintended_mutation=extra,
        infrastructure_failure=has_infrastructure_failure,
        primary_classification=classification,
        valid_for_behavioral_analysis=not has_infrastructure_failure,
        exclusion_reasons=reasons,
    )

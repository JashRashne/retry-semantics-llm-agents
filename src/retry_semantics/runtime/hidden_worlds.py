"""Construct the two hidden worlds and their independent arm-start clones."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from retry_semantics.environments.ticket import (
    CREATE_TICKET_COMMITTED,
    FrozenExecutableRequest,
    SourceStage,
    TicketEnvironment,
    TicketState,
)
from retry_semantics.serialization import sha256_hex


class TrialFamilyConstructionError(ValueError):
    """The requested hidden-world family violates the frozen protocol."""


class HiddenWorld(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"
    EXECUTED_ACK_LOST = "EXECUTED_ACK_LOST"


@dataclass(frozen=True, slots=True)
class PolicyArmStartingState:
    """One mutable arm environment with immutable construction provenance."""

    initial_state_snapshot: bytes
    initial_state_hash: str
    frozen_original_request: FrozenExecutableRequest
    starting_state_snapshot: bytes
    starting_state_hash: str
    environment: TicketEnvironment

    @property
    def serialized_original_request(self) -> bytes:
        return self.frozen_original_request.serialized_request

    @property
    def original_request_hash(self) -> str:
        return self.frozen_original_request.request_hash


@dataclass(frozen=True, slots=True)
class HiddenWorldArmStates:
    """The two independent, not-yet-executed policy-arm starting states."""

    exact_replay_state: PolicyArmStartingState
    llm_regeneration_state: PolicyArmStartingState


@dataclass(frozen=True, slots=True)
class ConstructedHiddenWorld:
    """Canonical post-ambiguity state for one hidden world."""

    hidden_world: HiddenWorld
    initial_state_snapshot: bytes
    initial_state_hash: str
    post_ambiguity_snapshot: bytes
    post_ambiguity_state_hash: str
    original_request_executed: bool
    original_request_dispatch_count: int
    original_commit_event_ids: tuple[str, ...]
    arm_states: HiddenWorldArmStates


@dataclass(frozen=True, slots=True)
class TrialFamilyStates:
    """Both hidden worlds and all four arm starts derived from one frozen M."""

    initial_state_snapshot: bytes
    initial_state_hash: str
    frozen_original_request: FrozenExecutableRequest
    serialized_original_request: bytes
    original_request_hash: str
    not_executed: ConstructedHiddenWorld
    executed_ack_lost: ConstructedHiddenWorld

    def __post_init__(self) -> None:
        validate_trial_family_states(self)


def _fail(message: str) -> None:
    raise TrialFamilyConstructionError(message)


def _request_value(request: FrozenExecutableRequest) -> dict[str, Any]:
    value = json.loads(request.serialized_request)
    if value["tool"] != "create_ticket":
        _fail("original request M must be an eligible create_ticket request")
    return value


def _validate_frozen_request_inputs(
    frozen_original_request: FrozenExecutableRequest,
    serialized_original_request: bytes,
    original_request_hash: str,
) -> dict[str, Any]:
    if type(frozen_original_request) is not FrozenExecutableRequest:
        _fail("frozen_original_request must be a FrozenExecutableRequest")
    if type(serialized_original_request) is not bytes:
        _fail("serialized_original_request must be bytes")
    if type(original_request_hash) is not str:
        _fail("original_request_hash must be a string")
    if frozen_original_request.serialized_request != serialized_original_request:
        _fail("frozen original request M does not match the supplied request bytes")
    if frozen_original_request.request_hash != original_request_hash:
        _fail("frozen original request M does not match the supplied request hash")
    if sha256_hex(serialized_original_request) != original_request_hash:
        _fail("original_request_hash does not match the supplied request bytes")
    return _request_value(frozen_original_request)


def _validate_original_stage(
    source_stage: SourceStage | str | None, arm_id: str | None
) -> None:
    try:
        stage = SourceStage(source_stage)
    except (TypeError, ValueError):
        _fail("original source_stage must be ORIGINAL")
    if stage is not SourceStage.ORIGINAL:
        _fail("original source_stage must be ORIGINAL")
    if arm_id is not None:
        _fail("the pre-policy original commit must have arm_id=None")


def _freeze_initial_snapshot(initial_state: TicketEnvironment | bytes) -> bytes:
    if type(initial_state) is TicketEnvironment:
        if initial_state.dispatch_count != 0:
            _fail("initial environment must have zero prior dispatches")
        snapshot = initial_state.snapshot_bytes()
    elif type(initial_state) is bytes:
        snapshot = initial_state
    else:
        _fail("initial_state must be a TicketEnvironment or canonical snapshot bytes")

    try:
        state = TicketEnvironment.clone_from_snapshot(snapshot).state
    except (TypeError, ValueError) as exc:
        raise TrialFamilyConstructionError(
            f"initial state snapshot is invalid: {exc}"
        ) from exc
    if state != TicketState.empty():
        _fail("initial state must be the fresh empty authoritative ticket state")
    return snapshot


def _arm_start(
    *,
    initial_snapshot: bytes,
    initial_hash: str,
    frozen_request: FrozenExecutableRequest,
    world_snapshot: bytes,
    world_hash: str,
) -> PolicyArmStartingState:
    return PolicyArmStartingState(
        initial_state_snapshot=initial_snapshot,
        initial_state_hash=initial_hash,
        frozen_original_request=frozen_request,
        starting_state_snapshot=world_snapshot,
        starting_state_hash=world_hash,
        environment=TicketEnvironment.clone_from_snapshot(world_snapshot),
    )


def _arm_pair(
    *,
    initial_snapshot: bytes,
    initial_hash: str,
    frozen_request: FrozenExecutableRequest,
    world_snapshot: bytes,
    world_hash: str,
) -> HiddenWorldArmStates:
    return HiddenWorldArmStates(
        exact_replay_state=_arm_start(
            initial_snapshot=initial_snapshot,
            initial_hash=initial_hash,
            frozen_request=frozen_request,
            world_snapshot=world_snapshot,
            world_hash=world_hash,
        ),
        llm_regeneration_state=_arm_start(
            initial_snapshot=initial_snapshot,
            initial_hash=initial_hash,
            frozen_request=frozen_request,
            world_snapshot=world_snapshot,
            world_hash=world_hash,
        ),
    )


def construct_trial_family_states(
    *,
    initial_state: TicketEnvironment | bytes,
    frozen_original_request: FrozenExecutableRequest,
    serialized_original_request: bytes,
    original_request_hash: str,
    original_source_stage: SourceStage | str | None,
    original_arm_id: str | None,
) -> TrialFamilyStates:
    """Build H0/H1 once each, then clone each snapshot into two arm starts."""

    _validate_frozen_request_inputs(
        frozen_original_request,
        serialized_original_request,
        original_request_hash,
    )
    _validate_original_stage(original_source_stage, original_arm_id)
    initial_snapshot = _freeze_initial_snapshot(initial_state)
    initial_hash = sha256_hex(initial_snapshot)

    h0_environment = TicketEnvironment.clone_from_snapshot(initial_snapshot)
    h0_snapshot = h0_environment.snapshot_bytes()
    h0_hash = sha256_hex(h0_snapshot)
    h0 = ConstructedHiddenWorld(
        hidden_world=HiddenWorld.NOT_EXECUTED,
        initial_state_snapshot=initial_snapshot,
        initial_state_hash=initial_hash,
        post_ambiguity_snapshot=h0_snapshot,
        post_ambiguity_state_hash=h0_hash,
        original_request_executed=False,
        original_request_dispatch_count=h0_environment.dispatch_count,
        original_commit_event_ids=(),
        arm_states=_arm_pair(
            initial_snapshot=initial_snapshot,
            initial_hash=initial_hash,
            frozen_request=frozen_original_request,
            world_snapshot=h0_snapshot,
            world_hash=h0_hash,
        ),
    )

    h1_environment = TicketEnvironment.clone_from_snapshot(initial_snapshot)
    # The normal success acknowledgement is intentionally discarded here. Only
    # the authoritative committed state crosses the future policy boundary.
    h1_environment.execute_request(
        serialized_original_request,
        source_stage=original_source_stage,
        arm_id=original_arm_id,
        expected_request_hash=original_request_hash,
    )
    h1_snapshot = h1_environment.snapshot_bytes()
    h1_hash = sha256_hex(h1_snapshot)
    h1 = ConstructedHiddenWorld(
        hidden_world=HiddenWorld.EXECUTED_ACK_LOST,
        initial_state_snapshot=initial_snapshot,
        initial_state_hash=initial_hash,
        post_ambiguity_snapshot=h1_snapshot,
        post_ambiguity_state_hash=h1_hash,
        original_request_executed=True,
        original_request_dispatch_count=h1_environment.dispatch_count,
        original_commit_event_ids=tuple(
            event.event_id for event in h1_environment.state.mutation_events
        ),
        arm_states=_arm_pair(
            initial_snapshot=initial_snapshot,
            initial_hash=initial_hash,
            frozen_request=frozen_original_request,
            world_snapshot=h1_snapshot,
            world_hash=h1_hash,
        ),
    )

    return TrialFamilyStates(
        initial_state_snapshot=initial_snapshot,
        initial_state_hash=initial_hash,
        frozen_original_request=frozen_original_request,
        serialized_original_request=serialized_original_request,
        original_request_hash=original_request_hash,
        not_executed=h0,
        executed_ack_lost=h1,
    )


def _validate_arm_start(
    arm: PolicyArmStartingState,
    *,
    family: TrialFamilyStates,
    world: ConstructedHiddenWorld,
) -> None:
    if arm.initial_state_snapshot != family.initial_state_snapshot:
        _fail("an arm does not reference the family initial snapshot")
    if arm.initial_state_hash != family.initial_state_hash:
        _fail("an arm does not reference the family initial-state hash")
    if arm.frozen_original_request is not family.frozen_original_request:
        _fail("an arm does not reference the family's single frozen request M")
    if arm.serialized_original_request != family.serialized_original_request:
        _fail("an arm has different frozen original-request bytes")
    if arm.original_request_hash != family.original_request_hash:
        _fail("an arm has a different original-request hash")
    if arm.starting_state_snapshot != world.post_ambiguity_snapshot:
        _fail("an arm was not cloned from its hidden-world snapshot")
    if arm.starting_state_hash != world.post_ambiguity_state_hash:
        _fail("an arm has a different hidden-world snapshot hash")
    if arm.environment.snapshot_bytes() != arm.starting_state_snapshot:
        _fail("an arm environment differs from its stored starting snapshot")
    if arm.environment.dispatch_count != 0:
        _fail("a newly constructed arm must have zero dispatches")


def _state_from_snapshot(snapshot: bytes, label: str) -> TicketState:
    try:
        return TicketEnvironment.clone_from_snapshot(snapshot).state
    except (TypeError, ValueError) as exc:
        raise TrialFamilyConstructionError(f"{label} is invalid: {exc}") from exc


def validate_trial_family_states(family: TrialFamilyStates) -> None:
    """Purely assert the deterministic, pre-policy family construction rules."""

    if type(family) is not TrialFamilyStates:
        _fail("family must be TrialFamilyStates")
    if type(family.frozen_original_request) is not FrozenExecutableRequest:
        _fail("family frozen original request has the wrong type")
    if family.serialized_original_request != (
        family.frozen_original_request.serialized_request
    ):
        _fail("family original-request bytes are incoherent")
    if family.original_request_hash != family.frozen_original_request.request_hash:
        _fail("family original-request hash is incoherent")
    if sha256_hex(family.serialized_original_request) != family.original_request_hash:
        _fail("family original-request bytes and hash are incoherent")
    request = _request_value(family.frozen_original_request)

    if sha256_hex(family.initial_state_snapshot) != family.initial_state_hash:
        _fail("family initial snapshot and hash are incoherent")
    initial_state = _state_from_snapshot(
        family.initial_state_snapshot, "family initial snapshot"
    )
    if initial_state != TicketState.empty():
        _fail("family initial state is not the fresh empty state")

    h0 = family.not_executed
    h1 = family.executed_ack_lost
    if h0.hidden_world is not HiddenWorld.NOT_EXECUTED:
        _fail("family H0 must be NOT_EXECUTED")
    if h1.hidden_world is not HiddenWorld.EXECUTED_ACK_LOST:
        _fail("family H1 must be EXECUTED_ACK_LOST")

    for world in (h0, h1):
        if world.initial_state_snapshot != family.initial_state_snapshot:
            _fail("hidden worlds do not share the family initial snapshot")
        if world.initial_state_hash != family.initial_state_hash:
            _fail("hidden worlds do not share the family initial-state hash")
        if sha256_hex(world.post_ambiguity_snapshot) != (
            world.post_ambiguity_state_hash
        ):
            _fail("a hidden-world snapshot and hash are incoherent")
        _validate_arm_start(
            world.arm_states.exact_replay_state, family=family, world=world
        )
        _validate_arm_start(
            world.arm_states.llm_regeneration_state, family=family, world=world
        )
        if (
            world.arm_states.exact_replay_state.starting_state_snapshot
            != world.arm_states.llm_regeneration_state.starting_state_snapshot
        ):
            _fail("policy-arm starting snapshots differ within a hidden world")

    h0_state = _state_from_snapshot(h0.post_ambiguity_snapshot, "H0 snapshot")
    if h0.original_request_executed:
        _fail("H0 must not mark the original request as executed")
    if h0.original_request_dispatch_count != 0:
        _fail("H0 must dispatch the original request zero times")
    if h0_state != TicketState.empty():
        _fail("H0 must contain zero tickets and zero mutation events")
    if h0.original_commit_event_ids:
        _fail("H0 must contain no original commit event IDs")

    h1_state = _state_from_snapshot(h1.post_ambiguity_snapshot, "H1 snapshot")
    if not h1.original_request_executed:
        _fail("H1 must mark the original request as executed")
    if h1.original_request_dispatch_count != 1:
        _fail("H1 must dispatch the original request exactly once")
    if len(h1_state.tickets) != 1 or h1_state.next_ticket_id != 2:
        _fail("H1 must contain exactly one committed ticket")
    if len(h1_state.mutation_events) != 1:
        _fail("H1 must contain exactly one original mutation event")
    arguments = request["arguments"]
    ticket = h1_state.tickets[0]
    if any(
        getattr(ticket, field) != arguments[field]
        for field in ("customer_id", "title", "description")
    ):
        _fail("H1 committed ticket does not match original request M")
    event = h1_state.mutation_events[0]
    if event.event_type != CREATE_TICKET_COMMITTED:
        _fail("H1 original event has the wrong event type")
    if event.source_stage is not SourceStage.ORIGINAL or event.arm_id is not None:
        _fail("H1 original event must be pre-policy ORIGINAL with arm_id=None")
    if event.serialized_request != family.serialized_original_request:
        _fail("H1 original event does not contain the frozen request bytes")
    if event.request_hash != family.original_request_hash:
        _fail("H1 original event does not contain the frozen request hash")
    if h1.original_commit_event_ids != (event.event_id,):
        _fail("H1 original commit event IDs are incoherent")

    if h0.post_ambiguity_snapshot == h1.post_ambiguity_snapshot:
        _fail("H0 and H1 post-ambiguity snapshots must differ")

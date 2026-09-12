from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from retry_semantics.environments.ticket import SourceStage, TicketEnvironment
from retry_semantics.runtime.hidden_worlds import (
    TrialFamilyConstructionError,
    construct_trial_family_states,
    validate_trial_family_states,
)


def _construct(initial_state, request):
    return construct_trial_family_states(
        initial_state=initial_state,
        frozen_original_request=request,
        serialized_original_request=request.serialized_request,
        original_request_hash=request.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )


def _all_arm_starts(family):
    return (
        family.not_executed.arm_states.exact_replay_state,
        family.not_executed.arm_states.llm_regeneration_state,
        family.executed_ack_lost.arm_states.exact_replay_state,
        family.executed_ack_lost.arm_states.llm_regeneration_state,
    )


def _mutate(environment, request, arm_id: str) -> None:
    environment.execute_request(
        request.serialized_request,
        source_stage=SourceStage.RECOVERY,
        arm_id=arm_id,
        expected_request_hash=request.request_hash,
    )


def test_all_four_arms_reference_one_initial_snapshot_and_one_m(make_request) -> None:
    initial = TicketEnvironment.empty()
    request = make_request()
    family = _construct(initial, request)

    for arm in _all_arm_starts(family):
        assert arm.initial_state_snapshot == family.initial_state_snapshot
        assert arm.initial_state_hash == family.initial_state_hash
        assert arm.frozen_original_request is family.frozen_original_request
        assert arm.serialized_original_request == family.serialized_original_request
        assert arm.original_request_hash == family.original_request_hash

    assert family.frozen_original_request is request
    assert family.serialized_original_request is request.serialized_request
    assert family.original_request_hash == request.request_hash


def test_policy_arm_starting_snapshots_are_equal_within_each_world(
    make_request,
) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())

    for world in (family.not_executed, family.executed_ack_lost):
        replay = world.arm_states.exact_replay_state
        regeneration = world.arm_states.llm_regeneration_state
        assert replay.starting_state_snapshot == regeneration.starting_state_snapshot
        assert replay.starting_state_hash == regeneration.starting_state_hash
        assert replay.environment.state == regeneration.environment.state
        assert replay.environment is not regeneration.environment


def test_h0_and_h1_post_ambiguity_states_differ(make_request) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())

    assert (
        family.not_executed.post_ambiguity_snapshot
        != family.executed_ack_lost.post_ambiguity_snapshot
    )
    assert (
        family.not_executed.post_ambiguity_state_hash
        != family.executed_ack_lost.post_ambiguity_state_hash
    )


@pytest.mark.parametrize(
    ("world_name", "arm_name"),
    [
        ("not_executed", "exact_replay_state"),
        ("not_executed", "llm_regeneration_state"),
        ("executed_ack_lost", "exact_replay_state"),
        ("executed_ack_lost", "llm_regeneration_state"),
    ],
)
def test_mutating_one_arm_does_not_change_its_sibling_or_stored_snapshots(
    make_request, world_name, arm_name
) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())
    world = getattr(family, world_name)
    selected = getattr(world.arm_states, arm_name)
    sibling = (
        world.arm_states.llm_regeneration_state
        if arm_name == "exact_replay_state"
        else world.arm_states.exact_replay_state
    )
    initial_snapshot = family.initial_state_snapshot
    stored_world_snapshot = world.post_ambiguity_snapshot

    _mutate(
        selected.environment,
        make_request(tool_call_id="future-recovery"),
        "future-arm",
    )

    assert selected.environment.snapshot_bytes() != stored_world_snapshot
    assert sibling.environment.snapshot_bytes() == stored_world_snapshot
    assert selected.starting_state_snapshot == stored_world_snapshot
    assert world.post_ambiguity_snapshot == stored_world_snapshot
    assert family.initial_state_snapshot == initial_snapshot


def test_mutating_h0_does_not_change_h1(make_request) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())
    h1_snapshots_before = tuple(
        arm.environment.snapshot_bytes()
        for arm in (
            family.executed_ack_lost.arm_states.exact_replay_state,
            family.executed_ack_lost.arm_states.llm_regeneration_state,
        )
    )

    _mutate(
        family.not_executed.arm_states.exact_replay_state.environment,
        make_request(tool_call_id="h0-only"),
        "h0:P1",
    )

    assert tuple(
        arm.environment.snapshot_bytes()
        for arm in (
            family.executed_ack_lost.arm_states.exact_replay_state,
            family.executed_ack_lost.arm_states.llm_regeneration_state,
        )
    ) == h1_snapshots_before


def test_family_construction_preserves_initial_environment(make_request) -> None:
    initial = TicketEnvironment.empty()
    initial_snapshot = initial.snapshot_bytes()

    family = _construct(initial, make_request())

    assert initial.snapshot_bytes() == initial_snapshot
    assert initial.dispatch_count == 0
    assert family.initial_state_snapshot == initial_snapshot


def test_family_can_be_constructed_from_the_same_canonical_initial_bytes(
    make_request,
) -> None:
    initial_snapshot = TicketEnvironment.empty().snapshot_bytes()
    family = _construct(initial_snapshot, make_request())

    assert family.not_executed.initial_state_snapshot == initial_snapshot
    assert family.executed_ack_lost.initial_state_snapshot == initial_snapshot


def test_family_rejects_a_nonfresh_initial_environment(make_request) -> None:
    initial = TicketEnvironment.empty()
    _mutate(initial, make_request(), "earlier-arm")

    with pytest.raises(TrialFamilyConstructionError, match="zero prior dispatches"):
        _construct(initial, make_request(tool_call_id="new-original"))


def test_family_and_arm_provenance_records_are_immutable(make_request) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())
    arm = family.not_executed.arm_states.exact_replay_state

    with pytest.raises(FrozenInstanceError):
        family.original_request_hash = "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        arm.starting_state_hash = "0" * 64  # type: ignore[misc]


def test_family_validator_accepts_a_fresh_construction(make_request) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())

    assert validate_trial_family_states(family) is None


def test_family_validator_fails_loudly_if_an_arm_no_longer_matches_its_start(
    make_request,
) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())
    _mutate(
        family.not_executed.arm_states.exact_replay_state.environment,
        make_request(tool_call_id="post-construction"),
        "h0:P1",
    )

    with pytest.raises(TrialFamilyConstructionError, match="starting snapshot"):
        validate_trial_family_states(family)


def test_family_construction_is_deterministic(make_request) -> None:
    initial_snapshot = TicketEnvironment.empty().snapshot_bytes()
    request = make_request()

    first = _construct(initial_snapshot, request)
    second = _construct(initial_snapshot, request)

    assert first.initial_state_snapshot == second.initial_state_snapshot
    assert first.initial_state_hash == second.initial_state_hash
    assert (
        first.not_executed.post_ambiguity_snapshot
        == second.not_executed.post_ambiguity_snapshot
    )
    assert (
        first.not_executed.post_ambiguity_state_hash
        == second.not_executed.post_ambiguity_state_hash
    )
    assert (
        first.executed_ack_lost.post_ambiguity_snapshot
        == second.executed_ack_lost.post_ambiguity_snapshot
    )
    assert (
        first.executed_ack_lost.post_ambiguity_state_hash
        == second.executed_ack_lost.post_ambiguity_state_hash
    )

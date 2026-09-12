from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from retry_semantics.environments.ticket import (
    SnapshotValidationError,
    SourceStage,
    TicketEnvironment,
    reconstruct_state,
)
from retry_semantics.serialization import canonical_json_bytes


def _commit(environment, request, arm_id: str) -> None:
    environment.execute_request(
        request.serialized_request,
        source_stage=SourceStage.RECOVERY,
        arm_id=arm_id,
    )


def test_snapshot_clone_deep_equality_bytes_and_hash(make_request) -> None:
    source = TicketEnvironment.empty()
    _commit(source, make_request(), "arm-source")
    snapshot = source.snapshot_bytes()
    clone = TicketEnvironment.clone_from_snapshot(snapshot)

    assert clone.state == source.state
    assert clone.state is not source.state
    assert clone.state.tickets[0] is not source.state.tickets[0]
    assert clone.state.mutation_events[0] is not source.state.mutation_events[0]
    assert clone.snapshot_bytes() == snapshot == source.snapshot_bytes()
    assert clone.snapshot_hash() == source.snapshot_hash()
    assert clone.dispatch_count == 0


def test_two_policy_clones_from_same_bytes_are_independent(make_request) -> None:
    source = TicketEnvironment.empty()
    _commit(source, make_request(tool_call_id="original"), "arm-source")
    shared_snapshot = source.snapshot_bytes()
    clone_a = TicketEnvironment.clone_from_snapshot(shared_snapshot)
    clone_b = TicketEnvironment.clone_from_snapshot(shared_snapshot)

    _commit(clone_a, make_request(tool_call_id="recovery-a"), "arm-a")

    assert len(clone_a.state.tickets) == 2
    assert clone_b.snapshot_bytes() == shared_snapshot
    assert source.snapshot_bytes() == shared_snapshot
    assert clone_b.state == source.state


def test_mutating_source_after_clone_does_not_mutate_clones(make_request) -> None:
    source = TicketEnvironment.empty()
    shared_snapshot = source.snapshot_bytes()
    clone_a = TicketEnvironment.clone_from_snapshot(shared_snapshot)
    clone_b = TicketEnvironment.clone_from_snapshot(shared_snapshot)

    _commit(source, make_request(), "arm-source")

    assert len(source.state.tickets) == 1
    assert clone_a.snapshot_bytes() == shared_snapshot
    assert clone_b.snapshot_bytes() == shared_snapshot


def test_snapshot_round_trip_is_deterministic(make_request) -> None:
    environment = TicketEnvironment.empty()
    _commit(environment, make_request(tool_call_id="one"), "arm-one")
    _commit(
        environment,
        make_request(tool_call_id="two", customer_id="CUST-002"),
        "arm-two",
    )

    first = environment.snapshot_bytes()
    second = TicketEnvironment.clone_from_snapshot(first).snapshot_bytes()
    third = TicketEnvironment.clone_from_snapshot(second).snapshot_bytes()

    assert first == second == third


def test_snapshot_rejects_noncanonical_or_inconsistent_state(make_request) -> None:
    environment = TicketEnvironment.empty()
    _commit(environment, make_request(), "arm")
    noncanonical = b" " + environment.snapshot_bytes()
    inconsistent = environment.state.as_dict()
    inconsistent["next_ticket_id"] = 99

    with pytest.raises(SnapshotValidationError, match="not canonical"):
        TicketEnvironment.clone_from_snapshot(noncanonical)
    with pytest.raises(SnapshotValidationError, match="not mutually reconstructable"):
        TicketEnvironment.clone_from_snapshot(canonical_json_bytes(inconsistent))


def test_event_and_ticket_records_are_immutable(make_request) -> None:
    environment = TicketEnvironment.empty()
    _commit(environment, make_request(), "arm")
    event = environment.state.mutation_events[0]

    with pytest.raises(FrozenInstanceError):
        event.event_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        event.ticket.title = "changed"  # type: ignore[misc]


def test_events_reconstruct_identical_and_different_creates(make_request) -> None:
    environment = TicketEnvironment.empty()
    identical = make_request(tool_call_id="same")
    _commit(environment, identical, "arm-one")
    _commit(environment, identical, "arm-two")
    _commit(
        environment,
        make_request(
            tool_call_id="different",
            customer_id="CUST-002",
            title="Different",
            description="Different description",
        ),
        "arm-three",
    )

    reconstructed = reconstruct_state(environment.state.mutation_events)

    assert reconstructed == environment.state
    assert canonical_json_bytes(reconstructed.as_dict()) == environment.snapshot_bytes()
    assert reconstructed.tickets[0].model_visible_dict() == (
        reconstructed.tickets[1].model_visible_dict()
    )
    assert reconstructed.tickets[0].ticket_id != reconstructed.tickets[1].ticket_id


def test_reconstruction_rejects_missing_or_out_of_order_event(make_request) -> None:
    environment = TicketEnvironment.empty()
    _commit(environment, make_request(tool_call_id="one"), "arm-one")
    _commit(environment, make_request(tool_call_id="two"), "arm-two")

    with pytest.raises(SnapshotValidationError, match="contiguously ordered"):
        reconstruct_state(environment.state.mutation_events[1:])


def test_brand_new_environment_instances_are_isolated(make_request) -> None:
    first = TicketEnvironment.empty()
    second = TicketEnvironment.empty()

    _commit(first, make_request(), "arm-first")

    assert len(first.state.tickets) == 1
    assert second.state == second.state.empty()
    assert second.snapshot_bytes() == TicketEnvironment.empty().snapshot_bytes()


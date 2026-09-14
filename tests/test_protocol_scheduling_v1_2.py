from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PROTOCOL = (
    REPOSITORY_ROOT / "research" / "protocol" / "primary_experiment_v1.md"
)
INVARIANTS = (
    REPOSITORY_ROOT / "research" / "protocol" / "protocol_invariants_v1.md"
)
COVERAGE = REPOSITORY_ROOT / "tests" / "PROTOCOL_COVERAGE.md"

H0 = "H0"
H1 = "H1"
REPLAY = "EXACT_REPLAY"
REGENERATION = "LLM_REGENERATION"

EXPECTED_ENGINEERING_QUEUE = (
    (0, 1, "CREATE-001"),
    (1, 1, "CREATE-002"),
    (2, 1, "CREATE-003"),
    (3, 1, "CREATE-004"),
    (4, 1, "CREATE-005"),
    (5, 1, "CREATE-006"),
    (6, 1, "CREATE-007"),
    (7, 1, "CREATE-008"),
    (8, 2, "CREATE-008"),
    (9, 2, "CREATE-007"),
    (10, 2, "CREATE-006"),
    (11, 2, "CREATE-005"),
    (12, 2, "CREATE-004"),
    (13, 2, "CREATE-003"),
    (14, 2, "CREATE-002"),
    (15, 2, "CREATE-001"),
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(path: Path) -> str:
    return " ".join(_read(path).split())


def _documented_engineering_queue() -> tuple[tuple[int, int, str], ...]:
    protocol = _read(PRIMARY_PROTOCOL)
    match = re.search(
        r"scheduled_attempt_index  replicate  scenario_id\n"
        r"(?P<rows>(?:\d+\s+[12]\s+CREATE-\d{3}\n)+)```",
        protocol,
    )
    assert match is not None
    return tuple(
        (int(index), int(replicate), scenario_id)
        for index, replicate, scenario_id in (
            line.split() for line in match.group("rows").splitlines()
        )
    )


def _hidden_world_order(index: int, seed: int = 0) -> tuple[str, str]:
    orientation_bit = (seed + index) % 2
    return (H0, H1) if orientation_bit == 0 else (H1, H0)


def _scenario_ordinal(scenario_id: str) -> int:
    match = re.fullmatch(r"CREATE-(\d{3})", scenario_id)
    assert match is not None
    return int(match.group(1))


def _policy_orientation_bit(scenario_id: str, seed: int = 0) -> int:
    return (seed + _scenario_ordinal(scenario_id) - 1) % 2


def _policy_orders(
    scenario_id: str, seed: int = 0
) -> tuple[tuple[str, str], tuple[str, str]]:
    replay_first = (REPLAY, REGENERATION)
    regeneration_first = (REGENERATION, REPLAY)
    if _policy_orientation_bit(scenario_id, seed) == 0:
        return replay_first, regeneration_first
    return regeneration_first, replay_first


def _schedule_stratum(index: int, scenario_id: str) -> str:
    key = (_hidden_world_order(index), _policy_orientation_bit(scenario_id))
    return {
        ((H0, H1), 0): "A",
        ((H1, H0), 1): "B",
        ((H0, H1), 1): "C",
        ((H1, H0), 0): "D",
    }[key]


def _per_world_policy_counts(indices: tuple[int, ...]) -> Counter[tuple[str, str]]:
    slots = {
        index: scenario_id
        for index, _, scenario_id in EXPECTED_ENGINEERING_QUEUE
    }
    counts: Counter[tuple[str, str]] = Counter()
    for index in indices:
        scenario_id = slots[index]
        for hidden_world, policy_order in zip(
            _hidden_world_order(index),
            _policy_orders(scenario_id),
            strict=True,
        ):
            counts[(hidden_world, policy_order[0])] += 1
    return counts


def _eligible_schedule_coverage_passes(indices: tuple[int, ...]) -> bool:
    slots = {
        index: scenario_id
        for index, _, scenario_id in EXPECTED_ENGINEERING_QUEUE
    }
    strata = {_schedule_stratum(index, slots[index]) for index in indices}
    return len(indices) >= 8 and strata == {"A", "B", "C", "D"}


def test_engineering_validation_queue_is_the_exact_frozen_16_slot_sequence() -> None:
    protocol = _normalized(PRIMARY_PROTOCOL)
    documented = _documented_engineering_queue()

    assert documented == EXPECTED_ENGINEERING_QUEUE
    assert len(documented) == 16
    assert tuple(row[0] for row in documented) == tuple(range(16))
    assert tuple(row[2] for row in documented[:8]) == tuple(
        f"CREATE-{ordinal:03d}" for ordinal in range(1, 9)
    )
    assert tuple(row[2] for row in documented[8:]) == tuple(
        f"CREATE-{ordinal:03d}" for ordinal in range(8, 0, -1)
    )
    assert "No randomized scenario shuffle is used" in protocol


def test_hidden_world_order_uses_exact_arithmetic_and_is_balanced() -> None:
    protocol = _normalized(PRIMARY_PROTOCOL)
    orders = tuple(_hidden_world_order(index) for index in range(16))

    assert "hidden_world_order_seed = 0" in protocol
    assert (
        "hidden_world_orientation_bit = (hidden_world_order_seed + i) mod 2"
        in protocol
    )
    assert all(
        order == ((H0, H1) if index % 2 == 0 else (H1, H0))
        for index, order in enumerate(orders)
    )
    assert Counter(order[0] for order in orders) == Counter({H0: 8, H1: 8})
    assert "exactly eight H0-first and eight H1-first attempts" in protocol


def test_policy_orientation_uses_scenario_ordinal_arithmetic() -> None:
    protocol = _normalized(PRIMARY_PROTOCOL)
    expected_orientations = (
        ("CREATE-001", 0),
        ("CREATE-002", 1),
        ("CREATE-003", 0),
        ("CREATE-004", 1),
        ("CREATE-005", 0),
        ("CREATE-006", 1),
        ("CREATE-007", 0),
        ("CREATE-008", 1),
    )

    assert "policy_order_seed = 0" in protocol
    assert (
        "policy_orientation_bit = (policy_order_seed + scenario_ordinal - 1) mod 2"
        in protocol
    )
    assert tuple(
        (scenario_id, _policy_orientation_bit(scenario_id))
        for scenario_id, _ in expected_orientations
    ) == expected_orientations
    replay_first = (REPLAY, REGENERATION)
    regeneration_first = (REGENERATION, REPLAY)
    assert _policy_orders("CREATE-001") == (
        replay_first,
        regeneration_first,
    )
    assert _policy_orders("CREATE-002") == (
        regeneration_first,
        replay_first,
    )
    assert "The seed does not vary by scheduled attempt" in protocol
    assert (
        "A V1.2 two-pair block is exactly the two hidden-world policy pairs "
        "belonging to one scheduled trial"
    ) in protocol


def test_combined_schedule_has_exact_per_world_policy_order_balance() -> None:
    counts = _per_world_policy_counts(tuple(range(16)))

    assert counts == Counter(
        {
            (H0, REPLAY): 8,
            (H0, REGENERATION): 8,
            (H1, REPLAY): 8,
            (H1, REGENERATION): 8,
        }
    )
    protocol = _normalized(PRIMARY_PROTOCOL)
    for fact in (
        "H0 Replay-first = 8",
        "H0 Regeneration-first = 8",
        "H1 Replay-first = 8",
        "H1 Regeneration-first = 8",
    ):
        assert fact in protocol


def test_old_eligibility_prefix_stop_breaks_policy_balance() -> None:
    first_eight_eligible = tuple(range(8))
    counts = _per_world_policy_counts(first_eight_eligible)

    assert counts == Counter(
        {
            (H0, REPLAY): 8,
            (H1, REGENERATION): 8,
        }
    )
    assert counts[(H0, REGENERATION)] == 0
    assert counts[(H1, REPLAY)] == 0

    protocol = _normalized(PRIMARY_PROTOCOL)
    assert "There is no eligibility-based early stop" in protocol
    assert "until eight eligible trial families exist" not in protocol


def test_engineering_validation_executes_every_slot_exactly_once() -> None:
    scheduled_indices = tuple(
        index for index, _, _ in EXPECTED_ENGINEERING_QUEUE
    )

    assert len(scheduled_indices) == 16
    assert scheduled_indices == tuple(range(16))
    protocol = _normalized(PRIMARY_PROTOCOL)
    assert "Execute all 16 frozen attempt slots exactly once in manifest order" in (
        protocol
    )
    for prohibited in (
        "replacement",
        "resampling",
        "queue extension",
        "retry-until-eligible",
    ):
        assert prohibited in protocol


def test_eligibility_threshold_and_all_four_strata_are_required() -> None:
    strata = Counter(
        _schedule_stratum(index, scenario_id)
        for index, _, scenario_id in EXPECTED_ENGINEERING_QUEUE
    )
    only_a_and_b = tuple(range(8))
    all_strata = (0, 1, 2, 3, 8, 9, 10, 11)

    assert strata == Counter({"A": 4, "B": 4, "C": 4, "D": 4})
    assert not _eligible_schedule_coverage_passes(tuple(range(7)))
    assert not _eligible_schedule_coverage_passes(only_a_and_b)
    assert _eligible_schedule_coverage_passes(all_strata)
    assert _eligible_schedule_coverage_passes(tuple(range(16)))

    protocol = _normalized(PRIMARY_PROTOCOL)
    assert "at least eight trial families MUST be eligible" in protocol
    assert (
        "At least one eligible trial family MUST occur in each of A, B, C, and D"
        in protocol
    )


def test_all_eligible_families_are_retained_without_post_hoc_subset() -> None:
    protocol = _normalized(PRIMARY_PROTOCOL)
    invariants = _normalized(INVARIANTS)

    for text in (protocol, invariants):
        assert "All eligible families are retained" in text
        assert "post-hoc balanced subset" in text
    assert "including when more than eight are eligible" in protocol
    assert (
        "Every eligible family and its executed arms must satisfy all applicable "
        "engineering invariants"
    ) in invariants


def test_each_scenario_and_hidden_world_receives_both_policy_orders() -> None:
    counts: dict[tuple[str, str], Counter[str]] = {}

    for index, _, scenario_id in EXPECTED_ENGINEERING_QUEUE:
        hidden_worlds = _hidden_world_order(index)
        policy_orders = _policy_orders(scenario_id)
        for hidden_world, policy_order in zip(
            hidden_worlds, policy_orders, strict=True
        ):
            key = (scenario_id, hidden_world)
            counts.setdefault(key, Counter())[policy_order[0]] += 1

    expected = Counter({REPLAY: 1, REGENERATION: 1})
    assert len(counts) == 16
    for ordinal in range(1, 9):
        scenario_id = f"CREATE-{ordinal:03d}"
        assert counts[(scenario_id, H0)] == expected
        assert counts[(scenario_id, H1)] == expected

    protocol = _normalized(PRIMARY_PROTOCOL)
    assert (
        "H0 across the two replicates -> one Replay-first, one Regeneration-first"
        in protocol
    )
    assert (
        "H1 across the two replicates -> one Replay-first, one Regeneration-first"
        in protocol
    )


def test_every_absolute_family_position_is_balanced_and_rejects_old_rule() -> None:
    current: dict[int, Counter[str]] = {
        position: Counter() for position in range(1, 5)
    }
    old_constant: dict[int, Counter[str]] = {
        position: Counter() for position in range(1, 5)
    }
    old_orders = (
        (REPLAY, REGENERATION),
        (REGENERATION, REPLAY),
    )

    for _, _, scenario_id in EXPECTED_ENGINEERING_QUEUE:
        for position, policy in enumerate(
            (*_policy_orders(scenario_id)[0], *_policy_orders(scenario_id)[1]),
            start=1,
        ):
            current[position][policy] += 1
        for position, policy in enumerate(
            (*old_orders[0], *old_orders[1]), start=1
        ):
            old_constant[position][policy] += 1

    balanced = Counter({REPLAY: 8, REGENERATION: 8})
    assert current == {position: balanced for position in range(1, 5)}
    assert old_constant != current
    assert old_constant[1] == old_constant[4] == Counter({REPLAY: 16})
    assert old_constant[2] == old_constant[3] == Counter({REGENERATION: 16})

    protocol = _normalized(PRIMARY_PROTOCOL)
    for position in range(1, 5):
        assert (
            f"family position {position} -> EXACT_REPLAY = 8, "
            "LLM_REGENERATION = 8"
        ) in protocol


def test_scheduling_seeds_are_explicitly_separate_from_model_seeds() -> None:
    primary = _normalized(PRIMARY_PROTOCOL)
    invariants = _normalized(INVARIANTS)

    for text in (primary, invariants):
        assert "ModelCallConfig.seed" in text
        assert "base_seed + model_call_index" in text
        assert "original-generation" in text
    assert (
        "The scheduling controls `hidden_world_order_seed` and `policy_order_seed` "
        "are not model-sampling seeds"
    ) in primary
    assert (
        "Model-generation base seeds remain a separate explicit experiment dimension"
        in primary
    )


def test_materialization_precedence_and_open_final_study_scope_are_frozen() -> None:
    primary = _normalized(PRIMARY_PROTOCOL)
    coverage = _normalized(COVERAGE)

    precedence = (
        "scheduled_attempt_index -> scenario + replicate assignment -> "
        "hidden-world order -> policy order within that scheduled trial -> "
        "already-materialized ScheduledTrialPlan"
    )
    assert precedence in primary
    assert (
        "`ScheduledTrialPlan` consumes the materialized orders and does not derive them"
        in primary
    )
    for open_dimension in (
        "final paper model list",
        "final provider list",
        "final number of full-study repetitions",
        "full-study live-run timing",
    ):
        assert open_dimension in primary
    assert (
        "Execution of all 16 slots, eligibility-threshold enforcement, eligible "
        "A/B/C/D coverage, and the engineering-validation runner remain pending"
    ) in coverage


def test_schedule_semantics_are_implementation_independent() -> None:
    primary = _normalized(PRIMARY_PROTOCOL)
    first = tuple(
        (slot, _hidden_world_order(slot[0]), _policy_orders(slot[2]))
        for slot in EXPECTED_ENGINEERING_QUEUE
    )
    second = tuple(
        (slot, _hidden_world_order(slot[0]), _policy_orders(slot[2]))
        for slot in EXPECTED_ENGINEERING_QUEUE
    )

    assert first == second
    assert (
        "The same inputs MUST produce the same schedule independently of Python "
        "version, dictionary ordering, operating system, process, machine, and wall "
        "clock"
    ) in primary
    assert (
        "No PRNG, provider seed, hash, runtime randomness, process state, machine "
        "state, or wall-clock value participates"
    ) in primary

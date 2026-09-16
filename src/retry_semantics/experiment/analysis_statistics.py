"""Prospective V1.3 Ticket statistics; pure functions, no runtime or inference.

These functions are an independently usable statistical core, not a certified
completed-bundle extractor. See the extractor evidence audit for blockers.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

Z_95 = 1.959963984540054
BOOTSTRAP_SEED = 20260916
BOOTSTRAP_REPLICATES = 10_000
WORLDS = ("H0", "H1")


@dataclass(frozen=True)
class PairedTable:
    n11: int
    n10: int
    n01: int
    n00: int

    def __post_init__(self):
        if any(type(x) is not int or x < 0 for x in self.cells):
            raise ValueError("paired counts must be nonnegative integers")

    @property
    def cells(self):
        return self.n11, self.n10, self.n01, self.n00

    @property
    def n(self):
        return sum(self.cells)

    @classmethod
    def from_pairs(cls, pairs):
        cells = {(1, 1): 0, (1, 0): 0, (0, 1): 0, (0, 0): 0}
        for pair in pairs:
            if len(pair) != 2 or any(type(x) is not int or x not in (0, 1) for x in pair):
                raise ValueError("paired outcomes must be integer binary scores")
            cells[tuple(pair)] += 1
        return cls(*(cells[key] for key in ((1, 1), (1, 0), (0, 1), (0, 0))))


def wilson_95(successes: int, n: int):
    """Ordinary Wilson score interval without continuity correction."""
    if type(n) is not int or type(successes) is not int or not 0 <= successes <= n or n <= 0:
        raise ValueError("Wilson requires integer 0 <= successes <= positive n")
    p = successes / n
    z2 = Z_95 * Z_95
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    radius = Z_95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return center - radius, center + radius


def _distance(a: float, b: float, phi: float):
    terms = (a * a, -2 * phi * a * b, b * b)
    radicand = math.fsum(terms)
    # Only a few ULPs of cancellation are allowed. Meaningful negatives fail.
    tolerance = 8 * math.ulp(sum(abs(x) for x in terms))
    if radicand < -tolerance:
        raise ArithmeticError("meaningfully negative Method-10 radicand")
    return math.sqrt(max(0.0, radicand))


def newcombe_paired_method10(table: PairedTable):
    """Newcombe (1998) paired-data Method 10, fixed two-sided 95% CI."""
    r, s, t, u = table.cells
    n = table.n
    if n == 0:
        return None
    p1, p2 = (r + s) / n, (r + t) / n
    l1, u1 = wilson_95(r + s, n)
    l2, u2 = wilson_95(r + t, n)
    marginals = (r + s, t + u, r + t, s + u)
    if 0 in marginals:
        phi = 0.0
    else:
        b = r * u - s * t
        # Compare integers against n/2 without rounding the threshold.
        c = (2 * b - n) / 2 if 2 * b > n else 0 if b >= 0 else b
        phi = c / math.sqrt(math.prod(marginals))
    d = p1 - p2
    return [
        d - _distance(p1 - l1, u2 - p2, phi),
        d + _distance(p2 - l2, u1 - p1, phi),
    ]


def exact_mcnemar(table: PairedTable):
    """Finite exact conditional two-sided binomial sum using integer arithmetic."""
    if table.n == 0:
        return None
    m = table.n10 + table.n01
    if m == 0:
        return 1.0
    numerator = 2 * sum(math.comb(m, k) for k in range(min(table.n10, table.n01) + 1))
    denominator = 1 << m
    return min(numerator, denominator) / denominator


def holm_two(raw_p: dict[str, float | None]):
    """Exactly the two co-primary worlds; never reduce an unavailable family."""
    if set(raw_p) != set(WORLDS):
        raise ValueError("Holm family must contain exactly H0 and H1")
    if any(p is not None and (type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1) for p in raw_p.values()):
        raise ValueError("p-values must be finite probabilities or null")
    estimable = all(raw_p[w] is not None for w in WORLDS)
    adjusted = dict.fromkeys(WORLDS)
    if estimable:
        first, second = sorted(WORLDS, key=lambda w: (raw_p[w], w))
        adjusted[first] = min(1.0, 2 * raw_p[first])
        adjusted[second] = max(adjusted[first], raw_p[second])
    return {
        "family_fully_estimable": estimable,
        "alpha": 0.05,
        "tests": {w: {
            "raw_p": raw_p[w], "holm_adjusted_p": adjusted[w],
            "reject": adjusted[w] <= 0.05 if estimable else None,
            "role": "CO_PRIMARY" if estimable else "DESCRIPTIVE",
        } for w in WORLDS},
    }


def rate(numerator: int, denominator: int):
    if type(numerator) is not int or type(denominator) is not int or not 0 <= numerator <= denominator:
        raise ValueError("rate requires integer 0 <= numerator <= denominator")
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def paired_summary(table: PairedTable):
    n = table.n
    return {
        "n11": table.n11, "n10": table.n10, "n01": table.n01, "n00": table.n00, "N": n,
        "replay_correctness": rate(table.n11 + table.n10, n),
        "regeneration_correctness": rate(table.n11 + table.n01, n),
        "delta": (table.n10 - table.n01) / n if n else None,
        "newcombe_paired_method10_95_ci": newcombe_paired_method10(table),
        "exact_mcnemar_raw_p": exact_mcnemar(table),
    }


def interaction_bootstrap(contributions):
    """Whole-family contributions in stable family order, not separate arms."""
    values = tuple(contributions)
    if any(type(x) is not int or not -2 <= x <= 2 for x in values):
        raise ValueError("family interactions must be integers from -2 through 2")
    n = len(values)
    result = {"N": n, "estimate": None, "percentile_95_ci": None,
              "seed": BOOTSTRAP_SEED, "replicates": BOOTSTRAP_REPLICATES}
    if n:
        rng = random.Random(BOOTSTRAP_SEED)
        samples = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                         for _ in range(BOOTSTRAP_REPLICATES))
        result.update(estimate=sum(values) / n, percentile_95_ci=[samples[249], samples[9749]])
    return result


def materially_weakened(intervals):
    if set(intervals) != set(WORLDS):
        raise ValueError("weakening requires H0 and H1 intervals")
    if any(intervals[w] is None for w in WORLDS):
        return None
    return all(intervals[w][0] > -0.20 and intervals[w][1] < 0.20 for w in WORLDS)


def summarize_families(families):
    """Statistics for already-derived scores ONLY, not a raw-evidence mapper.

    Each record has slot_index, family_id, and H0/H1. Each world has primary
    and sensitivity pairs, each either [Replay, Regeneration] or null. The
    evidence layer must establish those scores first; this function never
    attributes failures or invents missing outcomes.
    """
    ordered = sorted(families, key=lambda f: (f["slot_index"], f["family_id"]))
    if len({f["slot_index"] for f in ordered}) != len(ordered) or len({f["family_id"] for f in ordered}) != len(ordered):
        raise ValueError("duplicate family or slot")
    summaries = {}
    for population in ("primary", "sensitivity"):
        worlds = {w: paired_summary(PairedTable.from_pairs(
            f[w][population] for f in ordered if f[w][population] is not None
        )) for w in WORLDS}
        holm = holm_two({w: worlds[w]["exact_mcnemar_raw_p"] for w in WORLDS})
        contributions = [
            (f["H1"][population][0] - f["H1"][population][1])
            - (f["H0"][population][0] - f["H0"][population][1])
            for f in ordered if all(f[w][population] is not None for w in WORLDS)
        ]
        summaries[population] = {"worlds": worlds, "holm": holm,
                                 "interaction": interaction_bootstrap(contributions)}
    primary, sensitivity = summaries["primary"], summaries["sensitivity"]
    sign_reversals, decision_changes, zero_transitions = [], [], []
    for w in WORLDS:
        a, b = primary["worlds"][w]["delta"], sensitivity["worlds"][w]["delta"]
        if a is not None and b is not None:
            if a * b < 0:
                sign_reversals.append(w)
            if (a == 0) != (b == 0):
                zero_transitions.append(w)
        a, b = primary["holm"]["tests"][w]["reject"], sensitivity["holm"]["tests"][w]["reject"]
        if a is not None and b is not None and a != b:
            decision_changes.append(w)
    fully_comparable = all(summaries[p]["holm"]["family_fully_estimable"] for p in summaries)
    summaries["operational_fragility"] = {
        "value": True if sign_reversals or decision_changes else False if fully_comparable else None,
        "sign_reversals": sign_reversals, "holm_decision_changes": decision_changes,
        "zero_transitions": zero_transitions,
    }
    summaries["materially_weakened"] = materially_weakened({
        w: primary["worlds"][w]["newcombe_paired_method10_95_ci"] for w in WORLDS
    })
    summaries["equal_world_summary"] = {
        "label": "DESCRIPTIVE EQUAL-WORLD EXPERIMENTAL SUMMARY",
        "real_world_prevalence_weighted": False,
        "policies": {policy: (
            0.5 * primary["worlds"]["H0"][key]["rate"]
            + 0.5 * primary["worlds"]["H1"][key]["rate"]
            if all(primary["worlds"][w]["N"] for w in WORLDS) else None
        ) for policy, key in (("EXACT_REPLAY", "replay_correctness"),
                              ("LLM_REGENERATION", "regeneration_correctness"))},
    }
    return {"schema_version": "ticket-analysis-statistical-core-v1",
            "status": "DERIVED_SCORE_CORE_ONLY", **summaries}

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
import jsonschema

from retry_semantics.experiment.analysis_statistics import (
    PairedTable, _distance, exact_mcnemar, holm_two, interaction_bootstrap,
    materially_weakened, newcombe_paired_method10, paired_summary, rate,
    summarize_families,
)
from retry_semantics.serialization import canonical_json_bytes

REFERENCE = json.loads((Path(__file__).parent / "fixtures/newcombe_paired_method10_v1.json").read_text())


@pytest.mark.parametrize("case", REFERENCE["cases"])
def test_method10_original_published_table(case):
    actual = newcombe_paired_method10(PairedTable(*case["cells"]))
    assert actual == pytest.approx(case["ci"], abs=REFERENCE["source"]["absolute_tolerance"], rel=0)


@pytest.mark.parametrize("cells", [(12,0,0,0), (0,12,0,0), (0,0,12,0), (0,0,0,12), (5,8,3,6), (6,0,0,6), (0,0,0,0)])
def test_paired_tables_and_sign(cells):
    pairs = [pair for pair, count in zip(((1,1),(1,0),(0,1),(0,0)), cells) for _ in range(count)]
    table = PairedTable.from_pairs(pairs)
    assert table.cells == cells
    summary = paired_summary(table)
    assert summary["N"] == len(pairs)
    if pairs:
        assert summary["delta"] == (cells[1] - cells[2]) / len(pairs)
        assert summary["replay_correctness"] == rate(cells[0] + cells[1], len(pairs))
        assert summary["regeneration_correctness"] == rate(cells[0] + cells[2], len(pairs))
        lo, hi = summary["newcombe_paired_method10_95_ci"]
        assert -1 - 1e-15 <= lo <= summary["delta"] <= hi <= 1 + 1e-15
    else:
        assert summary["delta"] is None
        assert summary["exact_mcnemar_raw_p"] is None
        assert summary["newcombe_paired_method10_95_ci"] is None


def test_zero_discordance_still_has_interval():
    summary = paired_summary(PairedTable(30, 0, 0, 24))
    assert summary["delta"] == 0
    assert summary["exact_mcnemar_raw_p"] == 1
    assert summary["newcombe_paired_method10_95_ci"][0] < 0
    assert summary["newcombe_paired_method10_95_ci"][1] > 0


def test_positive_phi_correction_is_not_independent_or_method8():
    # Table III prints Method 8 [0.0618,0.3242] and Method 10
    # [0.0562,0.3292] for this table. This catches omission of n/2 correction.
    actual = newcombe_paired_method10(PairedTable(20,12,2,16))
    assert actual != pytest.approx([0.0618, 0.3242], abs=0.00005)


@pytest.mark.parametrize("s,t,p", [(0,0,1), (1,0,1), (2,0,0.5), (5,0,0.0625), (6,0,0.03125), (9,1,0.021484375), (3,3,1), (1,9,0.021484375)])
def test_exact_mcnemar_integer_golden(s,t,p):
    # Finite sums: e.g. m=10,k=1 => 2*(1+10)/1024=0.021484375.
    assert exact_mcnemar(PairedTable(1,s,t,0)) == p


def test_mcnemar_large_integer_sum():
    assert exact_mcnemar(PairedTable(0,160,0,0)) == 2 / (1 << 160)


@pytest.mark.parametrize("raw,adjusted,decisions", [
    ({"H0":0.01,"H1":0.04}, [0.02,0.04], [True,True]),
    ({"H0":0.04,"H1":0.01}, [0.04,0.02], [True,True]),
    ({"H0":0.03,"H1":0.03}, [0.06,0.06], [False,False]),
    ({"H0":0.025,"H1":0.05}, [0.05,0.05], [True,True]),
    ({"H0":0.01,"H1":0.015}, [0.02,0.02], [True,True]),
    ({"H0":1.0,"H1":1.0}, [1.0,1.0], [False,False]),
])
def test_holm_order_ties_stepdown(raw,adjusted,decisions):
    result = holm_two(raw)
    assert [result["tests"][w]["holm_adjusted_p"] for w in ("H0","H1")] == adjusted
    assert [result["tests"][w]["reject"] for w in ("H0","H1")] == decisions


def test_holm_incomplete_never_reduces_family():
    result = holm_two({"H0":0.00001,"H1":None})
    assert result["family_fully_estimable"] is False
    assert all(x["reject"] is None and x["holm_adjusted_p"] is None for x in result["tests"].values())


@pytest.mark.parametrize("ci,expected", [
    ([-0.199999,0.199999],True), ([-0.20,0.19],False),
    ([-0.19,0.20],False), ([-0.20,0.20],False), (None,None),
])
def test_weakening_strict_boundaries(ci,expected):
    assert materially_weakened({"H0":ci,"H1":[-0.1,0.1]}) is expected


def family(i,h0,h1,*,s0=None,s1=None):
    return {"slot_index":i,"family_id":f"synthetic-{i}",
            "H0":{"primary":h0,"sensitivity":h0 if s0 is None else s0},
            "H1":{"primary":h1,"sensitivity":h1 if s1 is None else s1}}


def test_world_matched_populations_and_complete_interaction():
    families = [family(0,[1,0],[0,1]), family(1,[1,1],None), family(2,None,[0,0])]
    result = summarize_families(families)
    assert result["primary"]["worlds"]["H0"]["N"] == 2
    assert result["primary"]["worlds"]["H1"]["N"] == 2
    assert result["primary"]["interaction"]["N"] == 1
    assert result["primary"]["interaction"]["estimate"] == -2
    assert result["equal_world_summary"]["policies"] == {"EXACT_REPLAY":0.5,"LLM_REGENERATION":0.5}
    assert canonical_json_bytes(result) == canonical_json_bytes(summarize_families(reversed(families)))


def test_sensitivity_sign_reversal():
    families = [family(0,[1,0],[1,1])] + [family(i,None,[1,1],s0=[0,1]) for i in range(1,4)]
    result = summarize_families(families)
    assert result["operational_fragility"]["sign_reversals"] == ["H0"]
    assert result["operational_fragility"]["value"] is True


def test_sensitivity_holm_changes_without_sign_reversal():
    families = [family(i,[1,0],[1,0]) for i in range(8)]
    families += [family(8,None,None,s0=[0,1],s1=[0,1])]
    result = summarize_families(families)
    assert result["operational_fragility"]["sign_reversals"] == []
    assert result["operational_fragility"]["holm_decision_changes"] == ["H0","H1"]
    assert result["operational_fragility"]["value"] is True


def test_zero_transition_is_not_sign_reversal():
    result = summarize_families([family(0,[1,0],[1,1]),family(1,None,[1,1],s0=[0,1])])
    assert result["operational_fragility"]["sign_reversals"] == []
    assert result["operational_fragility"]["zero_transitions"] == ["H0"]
    assert result["operational_fragility"]["value"] is False


def test_unavailable_interaction_and_equal_world():
    result = summarize_families([family(0,[1,0],None)])
    assert result["primary"]["interaction"]["estimate"] is None
    assert all(x is None for x in result["equal_world_summary"]["policies"].values())
    assert result["operational_fragility"]["value"] is None


def test_bootstrap_constant_and_empty():
    assert interaction_bootstrap([2,2])["percentile_95_ci"] == [2,2]
    assert interaction_bootstrap([])["percentile_95_ci"] is None


def test_bootstrap_separate_process_byte_identity():
    script = "from retry_semantics.experiment.analysis_statistics import interaction_bootstrap; from retry_semantics.serialization import canonical_json_bytes; import sys; sys.stdout.buffer.write(canonical_json_bytes(interaction_bootstrap([-2,-1,0,1,2])))"
    env = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    first = subprocess.check_output([sys.executable,"-c",script],env=env)
    second = subprocess.check_output([sys.executable,"-c",script],env=env)
    assert first == second == canonical_json_bytes(interaction_bootstrap([-2,-1,0,1,2]))
    # Byte hash is pinned separately after checking the prescribed draw stream.
    assert hashlib.sha256(first).hexdigest() == BOOTSTRAP_RESULT_HASH


BOOTSTRAP_RESULT_HASH = "088da36f14ce2326e342ba096e2f5901238c5be544901ba896604609575f3d68"


@pytest.mark.parametrize("cells", [(-1,0,0,0),(True,0,0,0),(1.0,0,0,0)])
def test_invalid_table_rejected(cells):
    with pytest.raises(ValueError):
        PairedTable(*cells)


def test_meaningful_negative_radicand_is_not_clipped():
    with pytest.raises(ArithmeticError):
        _distance(1,1,1.01)


@pytest.mark.parametrize("families", [[],[family(0,[1,0],[0,1])],[family(0,[0,0],None)]])
def test_versioned_core_schema(families):
    schema = json.loads((Path(__file__).resolve().parents[1] / "research/protocol/analysis_statistics_schema_v1.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(summarize_families(families))


@pytest.mark.parametrize("raw", [{"H0":0.1}, {"H0":0.1,"H1":0.2,"H2":0.3}, {"H0":math.nan,"H1":0.2}])
def test_invalid_holm_family_rejected(raw):
    with pytest.raises(ValueError):
        holm_two(raw)

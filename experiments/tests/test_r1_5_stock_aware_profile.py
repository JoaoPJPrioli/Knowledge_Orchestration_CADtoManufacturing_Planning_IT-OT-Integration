"""Tests for the stock-aware turning profile (Reviewer 1, Comment 5, Step B)."""
import json
import os
import sys

import pytest

EXP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXP)
from common.paths import RESULTS  # noqa: E402
from r1_5_programme_feasibility import stock_check as sc  # noqa: E402
from r1_5_programme_feasibility.stock_aware_profile import StockAwareTurningGenerator, approved_steps  # noqa: E402


def _step(n, op, fid, d, length, zc, ap, tool, status="auto_approved"):
    return {"step_number": n, "operation": op, "feature_id": fid, "feature_type": "Step",
            "feature_dimensions": {"Ø": d, "L": length}, "feature_location": {"X": 0.0, "Y": 0.0, "Z": zc},
            "parameters": {"depth_of_cut": {"value": ap}, "feed_rate": {"value": 0.2 if op == "rough_turning" else 0.06},
                           "spindle_speed": {"value": 500 if op == "rough_turning" else 900}, "coolant": {"value": True}},
            "tool_id": tool, "validation_status": status}


def _plan():
    rt, ft = "turning_insert_rough", "turning_insert_finish"
    return [
        _step(1, "rough_turning", 1, 24.95, 37.5, 99.25, 2.0, rt),     # z 80.5 to 118
        _step(2, "rough_turning", 2, 23.6, 1.75, 119.375, 2.0, rt),    # recess at z 118.5 to 120.25
        _step(3, "rough_turning", 3, 24.0, 47.5, 144.75, 2.0, rt),     # z 121 to 168.5 (free-end side)
        _step(4, "finish_turning", 1, 24.95, 37.5, 99.25, 0.2, ft),
        _step(5, "finish_turning", 2, 23.6, 1.75, 119.375, 0.2, ft),
        _step(6, "finish_turning", 3, 24.0, 47.5, 144.75, 0.2, ft),
        _step(7, "rough_turning", 9, 20.0, 5.0, 100.0, 2.0, rt, status="requires_review"),
    ]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    plan = _plan()
    gen = StockAwareTurningGenerator(30.0, 169.5)
    prog = gen.generate_program(approved_steps(plan))
    path = str(tmp_path_factory.mktemp("sa") / "p.nc")
    prog.save_to_file(path)
    lim = {"turning_insert_rough": 5.0, "turning_insert_finish": 2.0}
    return gen, path, sc.check_programme(path, plan, 30.0, 169.5, lim)


def test_only_approved_steps_are_handed_over():
    assert [s["step_number"] for s in approved_steps(_plan())] == [1, 2, 3, 4, 5, 6]


def test_recess_steps_are_refused_with_a_reason(generated):
    gen, _, _ = generated
    rec = {r["step_number"]: r for r in gen.refusals if r.get("kind") == "recess"}
    assert sorted(rec) == [2, 5]
    assert "plunge pattern" in rec[2]["missing_inputs"][0]
    assert [s["step_number"] for s in gen.serialised_steps] == [1, 3, 4, 6]


def test_roughing_passes_never_exceed_the_planned_depth_of_cut(generated):
    gen, _, check = generated
    rough = [p for p in gen.passes if p["operation"] == "rough_turning"]
    assert [p["diameter"] for p in rough] == [26.0, 25.35, 24.4]
    assert all(p["radial_depth"] <= p["planned_ap"] + 1e-9 for p in rough)
    feed = [m for m in check["moves"] if "radial_engagement_mm" in m]
    assert not any(m["exceeds_planned"] for m in feed)


def test_finishing_removes_the_planned_allowance(generated):
    gen, _, _ = generated
    fin = [p for p in gen.passes if p["operation"] == "finish_turning"]
    assert [(p["diameter"], p["radial_depth"]) for p in fin] == [(24.95, 0.2), (24.0, 0.2)]


def test_no_rapid_move_enters_the_bar(generated):
    _, _, check = generated
    assert check["rapids_into_stock"] == []


def test_no_gouge_against_the_reference_and_the_recess_is_left_as_residual(generated):
    _, _, check = generated
    c = check["conformance"]
    assert c["outer_gouges"] == []
    groove = [z for z in c["outer_residual"] if "R03" in z["reference_features"]]
    assert groove and abs(groove[0]["max_mm"] - 0.675) < 0.006


def test_overlapping_spans_are_recorded_not_refused():
    plan = _plan()
    plan[0]["feature_dimensions"]["L"] = 57.7          # feature 1 now overlaps feature 3 over z 121 to 138.2
    plan[0]["feature_location"]["Z"] = 109.35
    plan[3]["feature_dimensions"]["L"] = 57.7
    plan[3]["feature_location"]["Z"] = 109.35
    gen = StockAwareTurningGenerator(30.0, 169.5)
    gen.generate_program(approved_steps(plan))
    assert 3 in [s["step_number"] for s in gen.serialised_steps]
    assert gen.plan_overlaps and gen.plan_overlaps[0]["features"] == [1, 3]
    assert (gen.plan_overlaps[0]["z_from"], gen.plan_overlaps[0]["z_to"]) == (121.0, 138.2)


REF = os.path.join(RESULTS, "r1_5_stock_aware_profile.json")


@pytest.mark.skipif(not os.path.exists(REF), reason="run r1_5_programme_feasibility/run_stock_aware.py first")
def test_reference_result_matches_the_reported_values():
    r = json.load(open(REF, encoding="utf-8"))
    assert r["serialised_steps"] == [3, 5, 10, 12, 17, 18, 24]
    assert r["recess_refusals"] == [4, 11]
    s, ref = r["summary"], r["reference"]["summary"]
    assert (ref["rapids_into_stock"], s["rapids_into_stock"]) == (4, 0)
    assert (ref["max_radial_engagement_mm"], s["max_radial_engagement_mm"]) == (3.0, 2.0)
    assert (ref["finishing_passes_removing_nothing"], s["finishing_passes_removing_nothing"]) == (3, 0)
    assert len(ref["outer_gouges"]) == 1 and s["outer_gouges"] == []
    assert r["check"]["conformance"]["inner_residual"] == r["reference"]["conformance"]["inner_residual"]
    pc = r["pipeline_checks"]
    assert pc["validator"] == {"errors": 0, "warnings": 0}
    assert pc["parameter_fidelity"]["passed"] and pc["dimension_fidelity"]["passed"]
    assert pc["dimension_fidelity"]["defaulted"] == 0
    assert all(v["outer_gouges"] == [] and v["rapids_into_stock"] == 0 and v["passes_exceeding_planned_ap"] == 0
               for v in r["stock_sweep"].values())

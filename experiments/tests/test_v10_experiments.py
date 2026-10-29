"""Tests for the experiments added in version 10: merge-criterion checks (R2-3),
cross-modal identity probe (R2-2), and reasoning ablation (R1-7)."""
import json
import os
import sys

import pytest

EXP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXP)
from common.paths import RESULTS  # noqa: E402
from r2_3_merge_checks import merge_checks as mc  # noqa: E402


# --- R2-3 --------------------------------------------------------------------------------

def test_iso2768_table_values():
    assert mc.tolerance("m", 24.0) == 0.2
    assert mc.tolerance("c", 47.5) == 0.8
    assert mc.tolerance("f", 2.7) == 0.05
    assert mc.tolerance("v", 2.0) == 0.5      # class v not specified up to 3 mm: next range used
    assert mc.tolerance("v", 88.0) == 1.5


def test_stated_dimensions_are_normalised_and_never_guessed():
    rec = {"dimensions": {"R": 4.2, "L": 2.7}}
    assert mc.stated(rec, use_text=False) == {"D": 8.4, "L": 2.7}
    text = {"dimensions": {}, "description": "Upper cylindrical body with diameter of 22 mm (R11) and length of 46.5 mm"}
    assert mc.stated(text, use_text=False) == {}
    assert mc.stated(text, use_text=True) == {"D": 22.0, "L": 46.5}
    ambiguous = {"dimensions": {}, "description": "stepped hole with internal radii of R3.4, R4.2, and R6.1"}
    assert mc.stated(ambiguous, use_text=True) == {}


def test_conditions():
    a = {"dimensions": {"Ø": 6.8, "L": 21.05}}
    b = {"dimensions": {"Ø": 6.8, "R": 3.4, "L": 19.0}}
    c = {"dimensions": {"W": 8.0}}
    assert mc.condition(completeness=True)(a, b)
    assert not mc.condition(completeness=True)(a, c)          # no common dimension
    assert mc.condition()(a, c)                                # without completeness the pair is vacuously consistent
    assert mc.condition(eps=0.1)(a, b)                         # 2.05 / 21.05 = 0.097
    assert not mc.condition(eps=0.05)(a, b)
    assert not mc.condition(tol_class="v")(a, b)               # 2.05 mm > 1.0 mm


R23 = os.path.join(RESULTS, "r2_3_merge_checks.json")


@pytest.mark.skipif(not os.path.exists(R23), reason="run r2_3_merge_checks/merge_checks.py first")
def test_r2_3_reported_values():
    r = json.load(open(R23, encoding="utf-8"))
    g = r["gated"]
    assert (g["reference"]["entities"], g["reference"]["merges"], g["reference"]["correct"]) == (22, 8, 6)
    assert (g["C[free_text]"]["merges"], g["C[free_text]"]["correct"]) == (7, 6)
    assert (g["C[structured]"]["merges"], g["C[structured]"]["correct"]) == (3, 2)
    for e in ("0.1", "0.2", "0.3"):
        x = g[f"C+E{e}[free_text]"]
        assert (x["entities"], x["merges"], x["correct"], x["precision"], x["recall"]) == (25, 5, 5, 1.0, 0.5)
    x = g["C+E0.5[free_text]"]
    assert (x["entities"], x["merges"], x["correct"], x["recall"]) == (24, 6, 6, 0.6)
    for k in "fmc":
        assert (g[f"C+T{k}[free_text]"]["merges"], g[f"C+T{k}[free_text]"]["correct"]) == (2, 2)
    assert (g["C+Tv[free_text]"]["merges"], g["C+Tv[free_text]"]["correct"]) == (3, 3)
    s = r["discrepancy_true_pairs"]["summary"]
    assert (s["common_dimensions_of_true_pairs"], s["identical"], s["different"]) == (20, 14, 6)
    assert s["different_within_tolerance"] == {"f": 0, "m": 0, "c": 0, "v": 2}
    assert (s["smallest_nonzero_difference"], s["largest_difference"]) == (0.31, 40.5)
    fus = {x["policy"]: x for x in r["fusion"]}
    assert round(fus["average"]["step_merged_len_err_mean"]["merged"], 2) == 7.58
    for p in ("primary", "tolerance:f", "tolerance:m", "tolerance:c", "tolerance:v"):
        assert round(fus[p]["step_merged_len_err_mean"]["merged"], 2) == 0.69
        assert round(fus[p]["step_merged_pos_err_mean"]["merged"], 2) == 0.0


# --- R2-2 --------------------------------------------------------------------------------

R22 = os.path.join(RESULTS, "r2_2_cross_modal_identity.json")


@pytest.mark.skipif(not os.path.exists(R22), reason="run r2_2_cross_modal_identity/cross_modal.py first")
def test_r2_2_reported_values():
    r = json.load(open(R22, encoding="utf-8"))
    d = r["declared"]
    assert r["declared_setting"] == {"tau_min": 0.7, "completeness": True, "eps": 0.1}
    assert (d["links"], d["correct_links"], d["max_true_links"]) == (4, 2, 8)
    assert d["duplicated_approved_steps"] == [2, 7, 8, 9, 14, 15, 16, 21, 22, 23, 29]
    assert sorted((l["drawing"], l["step"], l["correct"]) for l in d["link_list"]) == \
        [(15, 5, True), (17, 4, False), (20, 11, False), (21, 7, True)]
    assert max(x["precision"] or 0 for x in r["sweep"]) == 0.75
    assert all(x["links"] - x["correct_links"] == 3 for x in r["sweep"] if x["correct_links"] == 5)


def test_r2_2_duplicated_steps_are_all_refused_by_ral():
    ref = os.path.join(EXP, "runs", "reference", "ral_refusals.json")
    if not os.path.exists(ref) or not os.path.exists(R22):
        pytest.skip("reference run or probe result missing")
    refused = {x["step_number"] for x in json.load(open(ref, encoding="utf-8"))["refusals"]}
    dup = json.load(open(R22, encoding="utf-8"))["declared"]["duplicated_approved_steps"]
    assert set(dup) <= refused


# --- R1-7 --------------------------------------------------------------------------------

R17 = os.path.join(RESULTS, "r1_7_reasoning_ablation.json")


@pytest.mark.skipif(not os.path.exists(R17), reason="run r1_7_reasoning_ablation/reasoning_ablation.py first")
def test_r1_7_reported_values():
    r = json.load(open(R17, encoding="utf-8"))
    assert r["rule_counts"] == {"feature_operation": 18, "parameter": 17, "tool": 1}
    v = r["variants"]
    assert (v["reference"]["steps"], v["reference"]["approved"]) == (32, 27)
    for k in ("reasoner_off", "no_feature_operation_rules"):
        assert (v[k]["steps"], v[k]["approved"], v[k]["requests_by_reason"]["missing_knowledge"]) == (0, 0, 22)
    for k in ("no_parameter_rules", "no_tool_rule"):
        assert (v[k]["steps"], v[k]["approved"], v[k]["requests_by_reason"]["missing_knowledge"]) == (32, 0, 32)
    assert v["no_tool_rule"]["steps_with_tool"] == 0 and v["no_parameter_rules"]["steps_with_parameters"] == 0

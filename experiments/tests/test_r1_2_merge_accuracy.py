"""Tests for the merge-level accuracy analysis (Reviewer 1, Comment 2)."""
import os
import sys

import pytest

EXP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXP)
from r1_2_merge_accuracy import merge_accuracy as ma  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(ma.GROUNDTRUTH, "results_v2.json")),
                                reason="Revision 2 ground-truth files not found")


@pytest.fixture(scope="module")
def setup():
    truth, refs = ma.load_truth()
    return ma.load_records(), truth, refs


def test_max_matching():
    assert ma.max_matching([("a", 1), ("a", 2), ("b", 1)]) == 2
    assert ma.max_matching([("a", 1), ("b", 1)]) == 1
    assert ma.max_matching([]) == 0


def test_every_raw_record_has_a_grounding(setup):
    data, truth, _ = setup
    recs = [r for pa, pb in data.values() for r in pa + pb]
    assert len(recs) == 30
    assert all(truth.get((r["source_file"], r["id"])) for r in recs)


def test_reference_partition_and_accuracy(setup):
    data, truth, refs = setup
    r = ma.evaluate(data, truth, refs)
    assert (r["entities"], r["merges"], r["correct"], r["max_true"]) == (22, 8, 6, 10)
    wrong = {(m["primary"][1], m["secondary"][1]) for m in r["merge_list"] if not m["same_feature"]}
    assert wrong == {("Step", "Boss"), ("Hole", "Bore")}
    # averaging moved the lower-body length from 0.0 to 20.2 mm error
    lb = next(x for x in r["step_attr"] if x["ref"] == "R01")
    assert lb["len_err_primary"] == pytest.approx(0.0) and lb["len_err_merged"] == pytest.approx(20.2)


def test_gate_ablation_keeps_identity_but_loses_label_consistency(setup):
    data, truth, refs = setup
    r = ma.evaluate(data, truth, refs, tau_min=0.0)
    assert (r["merges"], r["correct"]) == (10, 8)
    assert r["label_consistent_correct"] == 6
    cross = [m for m in r["merge_list"] if m["tau"] < 0.7]
    assert len(cross) == 2 and all(m["same_feature"] for m in cross)


def test_tau_min_one_blocks_lower_body_merge_but_greedy_repairs_wrongly(setup):
    data, truth, refs = setup
    r = ma.evaluate(data, truth, refs, tau_min=1.0)
    pairs = {(m["primary"][1], m["primary"][2], m["secondary"][2]) for m in r["merge_list"] if not m["same_feature"]}
    assert pairs == {("Boss", "R06", "R05")}

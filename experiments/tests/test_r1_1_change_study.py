"""Tests for the engineered procedural planner and the knowledge-change study
(Reviewer 1, Comment 1). Requires Java 25 for Pellet, as the pipeline does."""
import copy
import json
import os
import sys

import pytest

EXP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXP)
from r1_1_change_study import owl_harness as oh  # noqa: E402
from r1_1_change_study.build_tables import build_tables  # noqa: E402
from r1_1_change_study.procedural_planner import ProceduralPlanner  # noqa: E402
from r1_1_change_study import epp_extensions as ext  # noqa: E402
from r1_1_change_study.scenarios import scenarios  # noqa: E402
from r1_1_change_study.run_r1_1 import attribution_inspector, exact_attribution, table_delta  # noqa: E402

REF = os.path.join(EXP, "runs", "reference")
pytestmark = pytest.mark.skipif(not os.path.isdir(REF), reason="run common/run_pipeline.py reference first")


@pytest.fixture(scope="module")
def entities():
    return json.load(open(os.path.join(REF, "features.json"), encoding="utf-8"))


@pytest.fixture(scope="module")
def tables():
    return build_tables()


@pytest.fixture(scope="module")
def ref_owl(entities):
    return oh.run_owl(entities, inspect=attribution_inspector)


def _norm(r):
    return [(s["feature_id"], s["operation"], s["tool"], tuple(sorted((s["parameters"] or {}).items())), s["status"])
            for s in r["steps"]]


def test_reasoner_harness_reproduces_the_reference_plan(entities, ref_owl):
    plan = json.load(open(os.path.join(REF, "manufacturing_plan.json"), encoding="utf-8"))
    assert [(s["feature_id"], s["ontology_operation"], s["ontology_tool"], s["validation_status"]) for s in plan] == \
        [(s["feature_id"], s["operation"], s["tool"], s["status"]) for s in ref_owl["steps"]]
    assert ref_owl["delta"]["triples_added"] == 0 and ref_owl["delta"]["rules_added"] == 0


def test_epp_is_decision_equivalent_on_the_reference_case(entities, tables, ref_owl):
    epp = ProceduralPlanner(tables).plan(entities)
    assert _norm(epp) == _norm(ref_owl)
    key = lambda r: sorted((q["feature_id"], q["operation"] or "", q["reason_code"]) for q in r["requests"])  # noqa: E731
    assert key(epp) == key(ref_owl)


def test_reference_attribution_is_exact_and_unchanged_by_the_fix(entities, ref_owl):
    assert ref_owl["inspect"]["misattributed"] == 0
    with exact_attribution():
        fixed = oh.run_owl(entities)
    assert [s["provenance"] for s in fixed["steps"]] == [s["provenance"] for s in ref_owl["steps"]]


def test_repository_files_are_not_modified(entities):
    rules = os.path.join(oh.KNOWLEDGE, "rules", "machining_rules.swrl")
    before = open(rules, encoding="utf-8").read()
    sc = next(s for s in scenarios(entities) if s["id"] == "S4")
    oh.run_owl(entities, edits=sc["owl_edits"])
    assert open(rules, encoding="utf-8").read() == before


def test_table_delta_counts():
    a = {"x": {"k": 1}, "rows": [{"id": 1}], "l": [1]}
    b = {"x": {"k": 2}, "rows": [{"id": 1}, {"id": 2, "v": 3}], "l": [1], "new": 5}
    d = table_delta(a, b)
    assert d == {"entries_added": 2, "entries_removed": 0, "fields_changed": 1, "leaf_values": 4}


def test_extension_line_counter_ignores_docstrings_and_comments():
    n = ext.count_code_lines(ext.UniquenessPlanner)
    assert 5 < n < 20


def test_reference_ontology_declares_no_disjointness(tables):
    assert tables["disjoint"] == []


def test_disjointness_planner_leaves_a_consistent_plan_unchanged(entities, tables):
    t = copy.deepcopy(tables)
    t["disjoint"] = [["Counterbore", "Step"]]
    assert _norm(ext.DisjointnessPlanner(t).plan(entities)) == _norm(ProceduralPlanner(tables).plan(entities))


EXPECTED = {  # (reasoner meets intent, EPP v1 meets intent)
    "S1": (True, True), "S2": (True, True), "S3": (True, True), "S4": (True, True),
    "S5": (False, False), "S6": (True, True), "S7": (True, True), "S8": (True, True),
    "S9": (True, True), "S10": (True, False), "S11": (False, True), "S12": (True, False),
}


@pytest.mark.parametrize("sid", sorted(EXPECTED, key=lambda s: int(s[1:])))
def test_scenario_outcomes(sid, entities, tables, ref_owl):
    sc = next(s for s in scenarios(entities) if s["id"] == sid)
    ents = sc.get("entities", entities)
    mat = sc.get("material", "steel_1045")
    o = oh.run_owl(ents, material=mat, edits=sc["owl_edits"], code=sc.get("owl_code"),
                   inspect=attribution_inspector)
    if o.get("inspect"):
        o["attribution_audit"] = o.pop("inspect")
    t1 = copy.deepcopy(tables)
    sc["epp_edit"](t1)
    ref_epp = ProceduralPlanner(tables).plan(entities)
    e = ProceduralPlanner(t1).plan(ents, material_key=mat)
    assert (sc["oracle"](o, ref_owl)[0], sc["oracle"](e, ref_epp)[0]) == EXPECTED[sid]
    if sid == "S5":
        o2 = oh.run_owl(ents, edits=sc["owl_remedy"])
        assert sc["oracle"](o2, ref_owl)[0]
        assert sc["oracle"](ext.SpecificityPlanner(t1).plan(ents), ref_epp)[0]
    if sid == "S10":
        assert o["halted"] and "inconsistent" in o["error"]
        assert ext.UniquenessPlanner(t1).plan(ents)["halted"]
    if sid == "S12":
        assert o["halted"] and "inconsistent" in o["error"]
        assert ext.DisjointnessPlanner(t1).plan(ents)["halted"]
        ctrl = sc["controls"]
        oa = oh.run_owl(ents, edits=ctrl["axioms_only"]["owl_edits"])
        assert not oa["halted"] and _norm(oa) == _norm(ref_owl)
        om = oh.run_owl(ents, edits=ctrl["misfiling_without_axioms"]["owl_edits"])
        added = [s for s in om["steps"] if s["feature_id"] == 8 and s["operation"] in ("RoughTurningOp", "FinishTurningOp")]
        assert not om["halted"] and len(om["steps"]) == 34 and len(added) == 2
    if sid == "S11":
        assert o["attribution_audit"]["misattributed"] == 1
        with exact_attribution():
            o3 = oh.run_owl(ents, edits=sc["owl_edits"], inspect=attribution_inspector)
        assert o3["inspect"]["misattributed"] == 0

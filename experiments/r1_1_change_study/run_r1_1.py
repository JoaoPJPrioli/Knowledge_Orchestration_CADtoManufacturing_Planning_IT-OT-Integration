"""Reviewer 1, Comment 1 (with Reviewer 2, Comment 1 and Reviewer 3, Comment 6):
engineered procedural baseline and knowledge-change study.

1. Equivalence: the engineered procedural planner (EPP) and the reasoner path
   are run on the 22 reconciled entities of the reference run.
2. Change study: twelve maintenance scenarios (scenarios.py) are applied to
   both. For each: knowledge edits, code edits, outcome against the a priori
   oracle, and, where the first attempt fails, the remedy and its cost.
3. Attribution audit: every emitted parameter record of the reasoner path is
   checked against the rule that actually entails it; the effect of an exact
   attribution fix is measured on the reference and on S11.

Writes results/r1_1_change_study.json and results/r1_1_summary.md.
"""
import contextlib
import copy
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import RESULTS, RUNS  # noqa: E402
from r1_1_change_study import owl_harness as oh  # noqa: E402
from r1_1_change_study.build_tables import build_tables  # noqa: E402
from r1_1_change_study.procedural_planner import ProceduralPlanner  # noqa: E402
from r1_1_change_study import epp_extensions as ext  # noqa: E402
from r1_1_change_study.scenarios import scenarios  # noqa: E402
import skl_repository as skl  # noqa: E402

REF = os.path.join(RUNS, "reference")


# --- EPP table diff ----------------------------------------------------------

def _leaves(v):
    if isinstance(v, dict):
        return sum(_leaves(x) for x in v.values()) or 1
    if isinstance(v, list):
        return sum(_leaves(x) for x in v) or 1
    return 1


def table_delta(a, b):
    """Rows (or dictionary entries) added, removed, and changed, and the number
    of leaf values they carry."""
    out = {"entries_added": 0, "entries_removed": 0, "fields_changed": 0, "leaf_values": 0}

    def walk(x, y):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in set(x) | set(y):
                if k not in y:
                    out["entries_removed"] += 1; out["leaf_values"] += _leaves(x[k])
                elif k not in x:
                    out["entries_added"] += 1; out["leaf_values"] += _leaves(y[k])
                else:
                    walk(x[k], y[k])
        elif isinstance(x, list) and isinstance(y, list):
            xs = [json.dumps(i, sort_keys=True) for i in x]
            ys = [json.dumps(i, sort_keys=True) for i in y]
            for i in set(xs) | set(ys):
                d = ys.count(i) - xs.count(i)
                if d > 0:
                    out["entries_added"] += d; out["leaf_values"] += d * _leaves(json.loads(i))
                elif d < 0:
                    out["entries_removed"] += -d; out["leaf_values"] += -d * _leaves(json.loads(i))
        elif x != y:
            out["fields_changed"] += 1; out["leaf_values"] += 1
    walk(a, b)
    return out


# --- attribution audit (reasoner path) ---------------------------------------

def attribution_inspector(repo, reconciled, plan):
    by_id = {rf.feature_id: rf for rf in reconciled}
    rules = {r.rule_id: r for r in repo.rules}
    checked = mis = 0
    cases = []
    for s in plan["steps"]:
        p = s["parameters"]
        if not p:
            continue
        rf = by_id[s["feature_id"]]
        sets = [x for x in repo.get_cutting_parameter_sets(rf.skl_individual)
                if x["operation"] == s["ontology_operation"]]
        used = sets[0]["param_set"]
        named = rules.get(p["feed_rate"]["rule_id"])
        types = {c.name for c in rf.skl_individual.INDIRECT_is_a if hasattr(c, "name")} | {"Feature"}
        ok = (named is not None and named.consequent_object == used
              and set(named.antecedent_classes) <= types)
        checked += 1
        if not ok:
            mis += 1
            cases.append({"step": s["step_number"], "feature_id": s["feature_id"], "used_set": used,
                          "named_rule": p["feed_rate"]["rule_id"],
                          "named_rule_concludes": named.consequent_object if named else None})
    return {"records_checked": checked, "misattributed": mis, "cases": cases[:10]}


@contextlib.contextmanager
def exact_attribution():
    """Attribution fix tested in-process: a parameter set is attributed to a
    rule whose consequent is that set and whose antecedent classes the feature
    instantiates (the current code matches operation and material only)."""
    original = skl.SKLRepository.get_cutting_parameter_sets

    def fixed(self, feature_individual):
        out = original(self, feature_individual)
        types = {c.name for c in feature_individual.INDIRECT_is_a if hasattr(c, "name")} | {"Feature"}
        for rec in out:
            for pr in self.rules:
                if (pr.consequent_property == "hasCuttingParameterSet" and pr.consequent_object == rec["param_set"]
                        and pr.op_individual == rec["operation"]
                        and (pr.material_individual is None or pr.material_individual == rec["material"])
                        and set(pr.antecedent_classes) <= types):
                    rec["rule_id"] = pr.rule_id
                    break
        return out
    skl.SKLRepository.get_cutting_parameter_sets = fixed
    try:
        yield
    finally:
        skl.SKLRepository.get_cutting_parameter_sets = original


def epp_run(planner_cls, tables, entities, material):
    t0 = time.perf_counter()
    r = planner_cls(tables).plan(entities, material_key=material)
    r["seconds"] = time.perf_counter() - t0
    return r


def owl_run(entities, material, edits, code, inspect=None):
    t0 = time.perf_counter()
    r = oh.run_owl(entities, material=material, edits=edits, code=code, inspect=inspect)
    r["seconds"] = time.perf_counter() - t0
    if r.get("inspect"):
        r["attribution_audit"] = r.pop("inspect")
    return r


def brief(r):
    return {"halted": r["halted"], "error": r.get("error"), "steps": len(r["steps"]),
            "approved": sum(1 for s in r["steps"] if s["status"] == "auto_approved"),
            "requests_by_reason": {c: sum(1 for q in r["requests"] if q["reason_code"] == c)
                                   for c in sorted({q["reason_code"] for q in r["requests"]})},
            "attribution_audit": r.get("attribution_audit"), "seconds": round(r.get("seconds", 0), 3)}


def main():
    entities = json.load(open(os.path.join(REF, "features.json"), encoding="utf-8"))
    tables0 = build_tables()
    out = {"tables": {k: len(v) for k, v in tables0.items()}}
    import kefc_controller
    import glob
    import rdflib
    from rdflib.namespace import OWL, RDF
    fps = set()
    for f in glob.glob(os.path.join(oh.KNOWLEDGE, "*", "*.owl")):
        g = rdflib.Graph()
        g.parse(f, format="xml")
        fps |= set(g.subjects(RDF.type, OWL.FunctionalProperty))
    out["code_size_executable_lines"] = {"epp_v1_ProceduralPlanner": ext.count_code_lines(ProceduralPlanner),
                                         "KEFCController": ext.count_code_lines(kefc_controller.KEFCController),
                                         "SpecificityPlanner": ext.count_code_lines(ext.SpecificityPlanner),
                                         "UniquenessPlanner": ext.count_code_lines(ext.UniquenessPlanner),
                                         "DisjointnessPlanner": ext.count_code_lines(ext.DisjointnessPlanner)}
    out["functional_properties_declared"] = len(fps)

    ref_owl = owl_run(entities, "steel_1045", [], None, inspect=attribution_inspector)
    ref_epp = epp_run(ProceduralPlanner, tables0, entities, "steel_1045")

    def norm(r):
        return [(s["feature_id"], s["operation"], s["tool"], tuple(sorted((s["parameters"] or {}).items())), s["status"])
                for s in r["steps"]]

    def reqs(r):
        return sorted((q["feature_id"], q["operation"] or "", q["reason_code"]) for q in r["requests"])
    with exact_attribution():
        ref_fixed = owl_run(entities, "steel_1045", [], None, inspect=attribution_inspector)
    out["equivalence"] = {
        "reasoner": brief(ref_owl), "epp": brief(ref_epp),
        "identical_steps": norm(ref_owl) == norm(ref_epp), "identical_requests": reqs(ref_owl) == reqs(ref_epp),
        "provenance_identical_under_attribution_fix":
            [s["provenance"] for s in ref_owl["steps"]] == [s["provenance"] for s in ref_fixed["steps"]],
    }

    rows = []
    for sc in scenarios(entities):
        ents = sc.get("entities", entities)
        mat = sc.get("material", "steel_1045")
        code = sc.get("owl_code")
        o = owl_run(ents, mat, sc["owl_edits"], code, inspect=attribution_inspector)
        t1 = copy.deepcopy(tables0)
        sc["epp_edit"](t1)
        e = epp_run(ProceduralPlanner, t1, ents, mat)
        o_ok, o_det = sc["oracle"](o, ref_owl)
        e_ok, e_det = sc["oracle"](e, ref_epp)
        row = {"id": sc["id"], "event": sc["event"],
               "reasoner": {"knowledge_delta": o["delta"],
                            "code_lines": sum(len(v) for v in (code or {}).values()),
                            "code_note": "vocabulary dictionary entries in skl_repository.py" if code else "",
                            "meets_intent": o_ok, "detail": o_det, "result": brief(o)},
                "epp": {"knowledge_delta": table_delta(tables0, t1), "code_lines": 0,
                        "meets_intent": e_ok, "detail": e_det, "result": brief(e)}}
        if sc.get("owl_remedy"):
            o2 = owl_run(ents, mat, sc["owl_remedy"], code, inspect=attribution_inspector)
            ok2, det2 = sc["oracle"](o2, ref_owl)
            row["reasoner"]["remedy"] = {"knowledge_delta": o2["delta"], "code_lines": 0,
                                         "meets_intent": ok2, "detail": det2, "result": brief(o2)}
        if sc.get("epp_remedy_class"):
            cls = getattr(ext, sc["epp_remedy_class"])
            e2 = epp_run(cls, t1, ents, mat)
            ok2, det2 = sc["oracle"](e2, ref_epp)
            row["epp"]["remedy"] = {"code_extension": sc["epp_remedy_class"],
                                    "code_lines": ext.count_code_lines(cls),
                                    "meets_intent": ok2, "detail": det2, "result": brief(e2)}
        if sc.get("attribution_audit"):
            with exact_attribution():
                o3 = owl_run(ents, mat, sc["owl_edits"], code, inspect=attribution_inspector)
            ok3, det3 = sc["oracle"](o3, ref_owl)
            row["reasoner"]["with_attribution_fix"] = {"meets_intent": ok3, "detail": det3,
                                                       "attribution_audit": o3.get("attribution_audit")}
        for cname, ctrl in (sc.get("controls") or {}).items():
            oc = owl_run(ents, mat, ctrl["owl_edits"], code, inspect=attribution_inspector)
            tc = copy.deepcopy(tables0)
            ctrl["epp_edit"](tc)
            ec = epp_run(ProceduralPlanner, tc, ents, mat)
            row.setdefault("controls", {})[cname] = {
                "reasoner": {"knowledge_delta": oc["delta"], "result": brief(oc),
                             "plan_identical_to_reference": (not oc["halted"]) and norm(oc) == norm(ref_owl),
                             "detail": sc["oracle"](oc, ref_owl)[1]},
                "epp": {"knowledge_delta": table_delta(tables0, tc), "result": brief(ec),
                        "plan_identical_to_reference": (not ec["halted"]) and norm(ec) == norm(ref_epp),
                        "detail": sc["oracle"](ec, ref_epp)[1]},
                "planners_agree": norm(oc) == norm(ec) and reqs(oc) == reqs(ec)}
        rows.append(row)
        print(sc["id"], "reasoner:", o_ok, o_det, "| epp:", e_ok, e_det, flush=True)
    out["scenarios"] = rows
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r1_1_change_study.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    write_summary(out)


def write_summary(out):
    eq = out["equivalence"]
    L = ["# R1-1: engineered procedural planner and knowledge-change study", "",
         f"Equivalence on the 22 reference entities: identical steps {eq['identical_steps']}, identical "
         f"requests {eq['identical_requests']}; reasoner {eq['reasoner']['steps']} steps "
         f"({eq['reasoner']['approved']} approved) in {eq['reasoner']['seconds']} s, EPP "
         f"{eq['epp']['steps']} steps in {eq['epp']['seconds']} s. Reference attribution audit: "
         f"{eq['reasoner']['attribution_audit']}. Provenance identical under the attribution fix: "
         f"{eq['provenance_identical_under_attribution_fix']}.", "",
         "| ID | Event | Reasoner: knowledge edit | code | intent met | EPP: knowledge edit | code | intent met |",
         "|---|---|---|---|---|---|---|---|"]
    for r in out["scenarios"]:
        rd, ed = r["reasoner"]["knowledge_delta"], r["epp"]["knowledge_delta"]
        ow = f"+{rd['triples_added']}/-{rd['triples_removed']} triples, +{rd['rules_added']}/-{rd['rules_removed']} rules"
        ew = f"+{ed['entries_added']}/-{ed['entries_removed']} entries, {ed['fields_changed']} fields ({ed['leaf_values']} values)"
        L.append(f"| {r['id']} | {r['event']} | {ow} | {r['reasoner']['code_lines']} | {r['reasoner']['meets_intent']} | "
                 f"{ew} | {r['epp']['code_lines']} | {r['epp']['meets_intent']} |")
    L += ["", "Details:", ""]
    for r in out["scenarios"]:
        L.append(f"- {r['id']}: reasoner: {r['reasoner']['detail']} | EPP: {r['epp']['detail']}")
        for side in ("reasoner", "epp"):
            if "remedy" in r[side]:
                rm = r[side]["remedy"]
                L.append(f"  - {side} remedy: {rm.get('knowledge_delta', rm.get('code_extension'))}, "
                         f"code {rm['code_lines']} lines, intent met {rm['meets_intent']}: {rm['detail']}")
        for cname, c in (r.get("controls") or {}).items():
            L.append(f"  - control {cname}: reasoner {c['reasoner']['knowledge_delta']}, identical to reference "
                     f"{c['reasoner']['plan_identical_to_reference']} ({c['reasoner']['detail']}); EPP "
                     f"{c['epp']['knowledge_delta']}, identical {c['epp']['plan_identical_to_reference']}; "
                     f"planners agree {c['planners_agree']}")
        if "with_attribution_fix" in r["reasoner"]:
            L.append(f"  - reasoner with attribution fix: {r['reasoner']['with_attribution_fix']}")
        if r["reasoner"]["result"].get("attribution_audit"):
            L.append(f"  - reasoner attribution audit: {r['reasoner']['result']['attribution_audit']}")
    with open(os.path.join(RESULTS, "r1_1_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r1_1_summary.md"), encoding="utf-8").read())

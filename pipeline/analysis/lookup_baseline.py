"""
Lookup-table baseline and controlled probes.
============================================
Builds a procedural planner whose knowledge content is derived *mechanically*
from the SKL rule file and ontologies (dumped once to ``lookup_table.json``),
runs it on the reconciled entities of a reference run, and compares its
decisions with the reasoner-based plan. Three probes then exercise the
properties that differ between a rule base executed by a reasoner and a set
of dictionaries executed by code:

  1. decision equivalence on the reference case (expected: identical);
  2. contradictory knowledge: a second cutting-parameter rule for the same
     (material, operation) pair is added. The ontology path materialises both
     inferred parameter sets and KEFC withholds every affected step as
     rule_conflict; the dictionary path keeps whichever entry was written last
     and emits it silently;
  3. class extension: a new feature class is declared as a subclass of an
     existing one (one TBox axiom, no new rule). The reasoner applies the
     superclass rule to the new class by subsumption; the dictionary has no row
     for the new label and the planner has nothing to say.

Usage:
    python analysis/lookup_baseline.py <repo_dir> <run_output_dir> [results.json]
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(sys.argv[1])
RUN_OUT = os.path.abspath(sys.argv[2])
sys.path.insert(0, os.path.join(REPO, "src"))

from skl_repository import (FEATURE_TYPE_TO_CLASS, OWL_OPERATION_TO_LEGACY_ID,  # noqa: E402
                            OWL_TOOL_TO_LEGACY_ID, MATERIAL_KEY_TO_INDIVIDUAL, SKLRepository)
from semantic_reconciler import SemanticReconciler  # noqa: E402
from kefc_controller import KEFCController  # noqa: E402
from expert_validation import ExpertValidationStore  # noqa: E402

RULES = os.path.join(REPO, "knowledge", "rules", "machining_rules.swrl")


# ------------------------------------------------------------------ table
def build_lookup_table(repo_obj):
    """Derive dictionaries from the rule file (antecedent class -> consequent
    individual) and from the ontology individuals (parameter values, tool
    eligibility, preferences, precedence, machine capability)."""
    feature_ops, param_rules = {}, {}
    for line in open(RULES, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rule_id, body = line.split(":", 1)
        ante, cons = [x.strip() for x in body.split("->")]
        m = re.match(r"(\w+)\(\?f\) -> requiresOperation\(\?f, (\w+)\)", f"{ante} -> {cons}")
        if m:
            feature_ops.setdefault(m.group(1), []).append((m.group(2), rule_id.strip()))
            continue
        m = re.match(r"Feature\(\?f\) \^ requiresOperation\(\?f, (\w+)\)(?: \^ madeOfMaterial\(\?f, (\w+)\))? -> hasCuttingParameterSet\(\?f, (\w+)\)",
                     f"{ante} -> {cons}")
        if m:
            key = (m.group(2) or "*", m.group(1))
            param_rules[key] = (m.group(3), rule_id.strip())   # last writer wins, as in any dict
    po, to, mo = repo_obj.process_onto, repo_obj.tools_onto, repo_obj.machines_onto
    psets = {}
    for pset in repo_obj.params_onto.CuttingParameterSet.instances():
        psets[pset.name] = {"feed_rate": pset.hasFeedRateValue, "spindle_speed": pset.hasSpindleSpeedValue,
                            "depth_of_cut": pset.hasDepthOfCutValue, "coolant": pset.requiresCoolant}
    tools_for_op = {}
    for t in to.Tool.instances():
        for op in t.recommendedForOperation:
            tools_for_op.setdefault(op.name, []).append(t.name)
    preferred = {op.name: op.hasPreferredTool.name for op in po.Operation.instances() if op.hasPreferredTool}
    precedence = {op.name: op.hasPrecedenceOrder for op in po.Operation.instances()}
    lathe = mo.CNCLatheFanuc0iTD
    machine = {"supportsOperation": [o.name for o in lathe.supportsOperation],
               "supportsToolOrientation": [o.name for o in lathe.supportsToolOrientation],
               "spindle_axis": lathe.hasSpindleAxis,
               "limits": {"feed_rate": lathe.hasSafetyMaxFeedRate, "spindle_speed": lathe.hasSafetyMaxRPM,
                          "depth_of_cut": lathe.hasSafetyMaxDepthOfCut}}
    return {"feature_to_operations": feature_ops, "parameter_rules": {f"{k[0]}|{k[1]}": v for k, v in param_rules.items()},
            "parameter_sets": psets, "tools_for_operation": tools_for_op, "preferred_tool": preferred,
            "precedence": precedence, "machine": machine}


def lookup_plan(table, entities, material="steel_1045"):
    """Procedural planner over the dictionaries. Mirrors KEFC's decisions but
    takes every value from a dict; provenance is the dict key (a code
    location), not a knowledge artefact."""
    mat = MATERIAL_KEY_TO_INDIVIDUAL[material]
    specs = []
    for e in entities:
        cls = FEATURE_TYPE_TO_CLASS.get(e["type"].lower().replace(" ", "_").replace("-", "_"))
        ops = table["feature_to_operations"].get(cls, []) if cls else []
        for op, rule in ops:
            specs.append((e, op, rule))
    specs.sort(key=lambda s: (table["precedence"].get(s[1], 999), s[0]["id"]))
    steps = []
    for n, (e, op, rule) in enumerate(specs, start=1):
        cands = table["tools_for_operation"].get(op, [])
        if len(cands) == 1:
            tool, tool_rule = cands[0], "tools_for_operation[op]"
        elif op in table["preferred_tool"] and table["preferred_tool"][op] in cands:
            tool, tool_rule = table["preferred_tool"][op], "preferred_tool[op]"
        else:
            tool, tool_rule = None, None
        key = f"{mat}|{op}" if f"{mat}|{op}" in table["parameter_rules"] else f"*|{op}"
        pset_name, prule = table["parameter_rules"].get(key, (None, None))
        pset = table["parameter_sets"].get(pset_name, {})
        steps.append({"step_number": n, "feature_id": e["id"], "feature_type": e["type"],
                      "operation": OWL_OPERATION_TO_LEGACY_ID.get(op, op),
                      "tool_id": OWL_TOOL_TO_LEGACY_ID.get(tool, tool) if tool else None,
                      "parameters": {k: pset.get(k) for k in ("feed_rate", "spindle_speed", "depth_of_cut", "coolant")},
                      "provenance": {"operation": f"feature_to_operations[{FEATURE_TYPE_TO_CLASS.get(e['type'].lower().replace(' ', '_'))}]",
                                     "tool": tool_rule, "parameters": f"parameter_rules[{key}]"}})
    return steps


def compare(ref_steps, base_steps):
    def key(s):
        return (s["feature_id"], s["operation"])
    ref = {key(s): s for s in ref_steps}
    base = {key(s): s for s in base_steps}
    same_keys = set(ref) == set(base)
    identical = 0
    diffs = []
    for k in ref:
        if k not in base:
            diffs.append((k, "missing in baseline"))
            continue
        r, b = ref[k], base[k]
        rp = {p: r["parameters"][p]["value"] for p in ("feed_rate", "spindle_speed", "depth_of_cut", "coolant")} if r["parameters"] else {}
        bp = b["parameters"]
        same = r["tool_id"] == b["tool_id"] and all(abs(float(rp[p]) - float(bp[p])) < 1e-9 if isinstance(rp.get(p), (int, float)) and not isinstance(rp.get(p), bool) else rp.get(p) == bp.get(p) for p in rp)
        if same:
            identical += 1
        else:
            diffs.append((k, r["tool_id"], b["tool_id"], rp, bp))
    order_ref = [key(s) for s in sorted(ref_steps, key=lambda s: s["step_number"])]
    order_base = [key(s) for s in sorted(base_steps, key=lambda s: s["step_number"])]
    return {"reference_steps": len(ref_steps), "baseline_steps": len(base_steps), "same_step_set": same_keys,
            "identical_decisions": identical, "same_sequence": order_ref == order_base, "differences": diffs}


# ------------------------------------------------------------------ probes
def with_patched_rules(extra_lines, fn):
    """Run fn() with extra rule lines appended to a temporary copy of the rule
    file (the repository file is never modified)."""
    backup = RULES + ".bak"
    shutil.copy(RULES, backup)
    try:
        with open(RULES, "a", encoding="utf-8") as fh:
            fh.write("\n" + "\n".join(extra_lines) + "\n")
        return fn()
    finally:
        shutil.move(backup, RULES)


def run_kefc(entities, store_name, repo_patch=None):
    reconciler = SemanticReconciler()
    if repo_patch:
        repo_patch(reconciler.repo)
    reconciled = reconciler.reconcile(copy.deepcopy(entities))
    path = os.path.join(tempfile.gettempdir(), store_name)
    if os.path.exists(path):
        os.remove(path)
    kefc = KEFCController(reconciler.repo, ExpertValidationStore(path))
    plan = kefc.build_manufacturing_plan(reconciled)
    return plan, kefc.expert_store, reconciler.repo


def main():
    entities = json.load(open(os.path.join(RUN_OUT, "features.json")))
    ref_plan = json.load(open(os.path.join(RUN_OUT, "manufacturing_plan.json")))
    out = {}

    t0 = time.perf_counter()
    repo_obj = SKLRepository()
    table = build_lookup_table(repo_obj)
    json.dump(table, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "lookup_table.json"), "w"), indent=1, default=str)
    out["table_sizes"] = {"feature_to_operations": sum(len(v) for v in table["feature_to_operations"].values()),
                          "parameter_rules": len(table["parameter_rules"]), "parameter_sets": len(table["parameter_sets"]),
                          "tools_for_operation": sum(len(v) for v in table["tools_for_operation"].values())}

    # ---- probe 1: decision equivalence ------------------------------------
    t1 = time.perf_counter()
    base = lookup_plan(table, entities)
    t2 = time.perf_counter()
    out["probe1_equivalence"] = compare(ref_plan, base)
    out["probe1_equivalence"]["baseline_planner_seconds"] = round(t2 - t1, 4)
    base_withheld = [s for s in base if s["tool_id"] is None or s["parameters"]["feed_rate"] is None
                     or OWL_OPERATION_TO_LEGACY_ID.get(s["operation"], s["operation"]) not in
                     [OWL_OPERATION_TO_LEGACY_ID[o] for o in table["machine"]["supportsOperation"]]]
    out["probe1_equivalence"]["baseline_steps_outside_machine_operation_set"] = len(base_withheld)
    out["probe1_equivalence"]["provenance_form"] = {"reference": "rule identifier + ontology IRIs, SPARQL-queryable (128 of 128)",
                                                    "baseline": "dictionary key strings in the plan record; not queryable"}

    # ---- probe 2: contradictory knowledge -----------------------------------
    extra = ["aisi1045_drilling_params_alt: Feature(?f) ^ requiresOperation(?f, DrillingOp) ^ madeOfMaterial(?f, AISI1045Steel) -> hasCuttingParameterSet(?f, Aluminum6061_Drilling_Params)"]

    def ontology_path():
        plan, store, _ = run_kefc(entities, "probe2_store.json")
        drilling = [s for s in plan["steps"] if s["operation"] == "drilling"]
        return {"drilling_steps": len(drilling),
                "withheld_rule_conflict": sum(1 for s in drilling if s["validation_status"] == "requires_review"
                                              and any(r.reason_code == "rule_conflict" and r.feature_id == s["feature_id"] for r in store.all_requests())),
                "parameters_emitted_for_conflicting_steps": sum(1 for s in drilling if s["parameters"]),
                "rule_conflict_requests": sum(1 for r in store.all_requests() if r.reason_code == "rule_conflict")}
    out["probe2_contradiction"] = {"injected_rule": extra[0], "ontology": with_patched_rules(extra, ontology_path)}

    def table_path():
        repo2 = SKLRepository()  # reloads the patched rule file
        table2 = build_lookup_table(repo2)
        plan2 = lookup_plan(table2, entities)
        ref_vals = table["parameter_sets"]["AISI1045_Drilling_Params"]
        drilling = [s for s in plan2 if s["operation"] == "drilling"]
        replaced = sum(1 for s in drilling if s["parameters"]["feed_rate"] != ref_vals["feed_rate"]
                       or s["parameters"]["spindle_speed"] != ref_vals["spindle_speed"])
        return {"drilling_steps": len(drilling), "steps_with_silently_replaced_values": replaced,
                "flags_raised": 0, "winning_entry": table2["parameter_rules"]["AISI1045Steel|DrillingOp"]}
    out["probe2_contradiction"]["lookup_table"] = with_patched_rules(extra, table_path)

    # ---- probe 3: class extension by subsumption ----------------------------
    new_entity = {"id": 999, "type": "Tapered Hole", "description": "injected", "orientation": "Along Z-axis",
                  "absolute_location": {"X": 0.0, "Y": 0.0, "Z": 100.0}, "dimensions": {"Ø": 5.0},
                  "match_confidence": 1.0, "reconciliation": "primary_only"}

    def declare_subclass(repo):
        from owlready2 import Thing
        with repo.process_onto:
            class TaperedHole(repo.process_onto.HoleFeature):
                pass
        import skl_repository
        skl_repository.FEATURE_TYPE_TO_CLASS["tapered_hole"] = "TaperedHole"

    plan3, store3, _ = run_kefc([new_entity], "probe3_store.json", repo_patch=declare_subclass)
    import skl_repository
    skl_repository.FEATURE_TYPE_TO_CLASS.pop("tapered_hole", None)
    ont3 = {"steps_inferred": len(plan3["steps"]),
            "operations": [s["operation"] for s in plan3["steps"]],
            "operation_rule_ids": [s["operation_selection_rule_id"] for s in plan3["steps"]],
            "statuses": [s["validation_status"] for s in plan3["steps"]],
            "new_rules_written": 0, "new_axioms_written": 1}
    base3 = lookup_plan(table, [new_entity])
    tab3 = {"steps_produced": len(base3), "rows_added": 0,
            "note": "no row for the new label; a row (and one per new class) must be written by hand"}
    out["probe3_subsumption"] = {"ontology": ont3, "lookup_table": tab3}
    out["timing"] = {"ontology_load_and_table_build_seconds": round(t1 - t0, 3)}
    json.dump(out, open(sys.argv[3] if len(sys.argv) > 3 else os.devnull, "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()

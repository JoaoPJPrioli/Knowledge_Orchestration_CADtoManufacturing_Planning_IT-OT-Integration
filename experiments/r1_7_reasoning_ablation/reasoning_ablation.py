"""Reviewer 1, Comment 7 (and Reviewer 3, Comment 7): reasoning ablation.

Table 10 of the manuscript ablates the gates (orientation, KEFC, type gate,
source ordering, serialisation profile). This study ablates the reasoning
itself on the 22 reference entities, with the reasoner-path harness of the
change study (CFRM, Pellet, KEFC on an edited copy of the knowledge; the
repository is not modified):

  reasoner_off                 Pellet is not run (no SWRL inference, no DL
                               classification); everything else unchanged;
  no_feature_operation_rules   the 18 feature-to-operation rules removed;
  no_parameter_rules           the 17 parameter rules removed;
  no_tool_rule                 the operation-to-tool rule removed (the
                               asserted hasPreferredTool remains, but it only
                               ranks tools that the rule has made eligible).

The question is whether any planning decision reaches the plan without
inference, that is, whether a hidden procedural default exists. Writes
results/r1_7_reasoning_ablation.json and results/r1_7_reasoning_summary.md.
"""
import contextlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import RESULTS, RUNS  # noqa: E402
from r1_1_change_study import owl_harness as oh  # noqa: E402
import skl_repository as skl  # noqa: E402

REF = os.path.join(RUNS, "reference")


@contextlib.contextmanager
def reasoner_off():
    original = skl.SKLRepository.reason

    def skip(self):
        self.reasoning_status = "skipped (ablation)"
    skl.SKLRepository.reason = skip
    try:
        yield
    finally:
        skl.SKLRepository.reason = original


def rule_ids():
    rules = skl._parse_rules(skl.RULES_FILE)
    cats = {"feature_operation": [], "parameter": [], "tool": []}
    for r in rules:
        if r.consequent_property == "requiresOperation":
            cats["feature_operation"].append(r.rule_id)
        elif r.consequent_property == "hasCuttingParameterSet":
            cats["parameter"].append(r.rule_id)
        else:
            cats["tool"].append(r.rule_id)
    return cats


def summarise(r, seconds):
    steps = r["steps"]
    by_reason = {}
    for q in r["requests"]:
        by_reason[q["reason_code"]] = by_reason.get(q["reason_code"], 0) + 1
    tool_sources = {}
    for s in steps:
        t = (s.get("provenance") or {}).get("tool") or "none"
        tool_sources[t] = tool_sources.get(t, 0) + 1
    return {"halted": r["halted"], "error": r.get("error"), "steps": len(steps),
            "approved": sum(1 for s in steps if s["status"] == "auto_approved"),
            "withheld": sum(1 for s in steps if s["status"] != "auto_approved"),
            "steps_with_parameters": sum(1 for s in steps if s["parameters"]),
            "steps_with_tool": sum(1 for s in steps if s["tool"]),
            "tool_selection_provenance": tool_sources,
            "requests": len(r["requests"]), "requests_by_reason": by_reason,
            "knowledge_delta": r.get("delta"), "seconds": round(seconds, 2)}


def main():
    entities = json.load(open(os.path.join(REF, "features.json"), encoding="utf-8"))
    cats = rule_ids()
    res = {"rule_counts": {k: len(v) for k, v in cats.items()}, "variants": {}}
    t0 = time.perf_counter()
    res["variants"]["reference"] = summarise(oh.run_owl(entities), time.perf_counter() - t0)
    with reasoner_off():
        t0 = time.perf_counter()
        res["variants"]["reasoner_off"] = summarise(oh.run_owl(entities), time.perf_counter() - t0)
    for name, key in (("no_feature_operation_rules", "feature_operation"), ("no_parameter_rules", "parameter"),
                      ("no_tool_rule", "tool")):
        t0 = time.perf_counter()
        res["variants"][name] = summarise(oh.run_owl(entities, edits=[oh.remove_rules(cats[key])]), time.perf_counter() - t0)
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r1_7_reasoning_ablation.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    L = ["# R1-7: reasoning ablation on the 22 reference entities", "", "Rule counts: " + json.dumps(res["rule_counts"]), "",
         "| Variant | Halted | Steps | Approved | Withheld | With parameters | With tool | Requests by reason | Tool provenance |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k, v in res["variants"].items():
        L.append(f"| {k} | {v['halted']} | {v['steps']} | {v['approved']} | {v['withheld']} | {v['steps_with_parameters']} | "
                 f"{v['steps_with_tool']} | {json.dumps(v['requests_by_reason'])} | {json.dumps(v['tool_selection_provenance'])} |")
    with open(os.path.join(RESULTS, "r1_7_reasoning_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return res


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r1_7_reasoning_summary.md"), encoding="utf-8").read())

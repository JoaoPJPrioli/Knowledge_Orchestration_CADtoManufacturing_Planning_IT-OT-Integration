"""Reviewer 2, Comment 2: cross-modal identity resolution that prevents duplicate
physical features.

The drawing carries no coordinate frame, so drawing-family entities cannot be
matched to STEP-family entities by position. This probe links them without
coordinates, using only what both families state:

  * type admissibility: tau(type_d, type_s) >= tau_min, with the pipeline's
    own type tiers (feature_parser.calculate_type_similarity);
  * completeness: at least one common stated dimension (diameter from the
    diameter or twice the radius, length, width); drawing entities state their
    dimensions only in free text, read by free_text_dimensions.py;
  * consistency: every common dimension agrees within a relative difference eps.

Admissible pairs are linked one to one by a maximum-weight matching (weight:
tau plus the mean relative agreement of the common dimensions). The setting
declared in advance is tau_min = 0.7 (the pipeline's type gate), completeness
required, and eps = 0.1 (the smallest value of the R2-3 study); the other
settings are a sensitivity sweep.

Truth: two entities denote the same physical feature when the Level M audit
grounds them to the same feature of the physical reference (phys_id, Revision
2 ground truth). Measures: link precision, recall against a maximum one-to-one
matching of true pairs, and the approved steps of linked drawing entities, which
duplicate a STEP-family feature and would be removed if the link were applied.
Analysis only; the pipeline and the reference run are not modified.
Writes results/r2_2_cross_modal_identity.json and results/r2_2_summary.md.
"""
import itertools
import json
import os
import sys

import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import GROUNDTRUTH, RESULTS, RUNS, use_repo  # noqa: E402
from r2_3_merge_checks.merge_checks import stated  # noqa: E402

use_repo()
import feature_parser as fp  # noqa: E402

REF = os.path.join(RUNS, "reference")
DECLARED = {"tau_min": 0.7, "completeness": True, "eps": 0.1}


def family(entity):
    return "DRAWING" if "draw_" in (entity.get("source_file") or "") else "STEP"


def load():
    ents = json.load(open(os.path.join(REF, "features.json"), encoding="utf-8"))
    truth = {e["entity_id"]: (e.get("M") or {}).get("phys_id")
             for e in json.load(open(os.path.join(GROUNDTRUTH, "results_v2.json"), encoding="utf-8"))["two_level"]["entities"]}
    plan = json.load(open(os.path.join(REF, "manufacturing_plan.json"), encoding="utf-8"))
    return ents, truth, plan


def candidates(drawing, step, tau_min, completeness, eps):
    out = []
    for d in drawing:
        sd = stated(d, use_text=True)
        for s in step:
            tau = fp.calculate_type_similarity(d["type"], s["type"])
            if tau < tau_min:
                continue
            ss = stated(s, use_text=True)
            com = {k: (sd[k], ss[k]) for k in set(sd) & set(ss)}
            if completeness and not com:
                continue
            rel = [abs(x - y) / max(abs(x), abs(y)) if max(abs(x), abs(y)) else 0.0 for x, y in com.values()]
            if eps is not None and any(r > eps for r in rel):
                continue
            agreement = 1.0 - (sum(rel) / len(rel)) if rel else 0.0
            out.append({"drawing": d["id"], "step": s["id"], "tau": tau, "common": sorted(com),
                        "relative_differences": [round(r, 4) for r in rel], "weight": tau + agreement})
    return out


def max_true_matching(drawing, step, truth):
    g = nx.Graph()
    for d in drawing:
        for s in step:
            if truth.get(d["id"]) and truth.get(d["id"]) == truth.get(s["id"]):
                g.add_edge(("d", d["id"]), ("s", s["id"]))
    return len(nx.max_weight_matching(g, maxcardinality=True))


def evaluate(ents, truth, plan, tau_min, completeness, eps):
    drawing = [e for e in ents if family(e) == "DRAWING"]
    step = [e for e in ents if family(e) == "STEP"]
    cand = candidates(drawing, step, tau_min, completeness, eps)
    g = nx.Graph()
    for c in cand:
        g.add_edge(("d", c["drawing"]), ("s", c["step"]), weight=c["weight"])
    links = []
    for u, v in nx.max_weight_matching(g):
        if u[0] == "s":
            u, v = v, u
        c = next(x for x in cand if x["drawing"] == u[1] and x["step"] == v[1])
        links.append(dict(c, correct=bool(truth.get(u[1])) and truth.get(u[1]) == truth.get(v[1]),
                          phys=[truth.get(u[1]), truth.get(v[1])]))
    links.sort(key=lambda x: x["drawing"])
    approved = {s["step_number"]: s for s in plan if s["validation_status"] in ("auto_approved", "expert_approved")}
    dup_steps = sorted(n for n, s in approved.items() if s["feature_id"] in {d["id"] for d in drawing})
    removed = sorted(n for n, s in approved.items() if s["feature_id"] in {l["drawing"] for l in links})
    wrong = sorted(n for n, s in approved.items() if s["feature_id"] in {l["drawing"] for l in links if not l["correct"]})
    mt = max_true_matching(drawing, step, truth)
    correct = sum(l["correct"] for l in links)
    return {"tau_min": tau_min, "completeness": completeness, "eps": eps,
            "drawing_entities": len(drawing), "step_entities": len(step), "admissible_pairs": len(cand),
            "links": len(links), "correct_links": correct,
            "precision": correct / len(links) if links else None, "max_true_links": mt,
            "recall": correct / mt if mt else None,
            "duplicated_approved_steps": dup_steps, "duplicated_approved_steps_removed": removed,
            "steps_removed_by_wrong_links": wrong, "link_list": links,
            "unlinked_drawing_entities": [{"id": d["id"], "type": d["type"], "phys": truth.get(d["id"]),
                                           "stated": stated(d, use_text=True)}
                                          for d in drawing if d["id"] not in {l["drawing"] for l in links}]}


def main():
    ents, truth, plan = load()
    res = {"declared_setting": DECLARED,
           "declared": evaluate(ents, truth, plan, **DECLARED),
           "sweep": [evaluate(ents, truth, plan, t, c, e)
                     for t, c, e in itertools.product((0.7, 0.3, 0.0), (True, False), (0.05, 0.1, 0.2, 0.3, 0.5, None))]}
    st = [e for e in ents if family(e) == "STEP"]
    res["step_entities_stated"] = {e["id"]: [e["type"], stated(e, use_text=True), truth.get(e["id"])] for e in st}
    res["drawing_entities_stated"] = {e["id"]: [e["type"], stated(e, use_text=True), truth.get(e["id"])]
                                      for e in ents if family(e) == "DRAWING"}
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r2_2_cross_modal_identity.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    write_summary(res)
    return res


def write_summary(res):
    f = lambda x: "n/a" if x is None else f"{x:.2f}"  # noqa: E731
    d = res["declared"]
    L = ["# R2-2: frame-free cross-modal identity probe", "",
         f"Declared setting {json.dumps(res['declared_setting'])}: {d['links']} links, {d['correct_links']} correct "
         f"(precision {f(d['precision'])}), recall {d['correct_links']} of {d['max_true_links']} ({f(d['recall'])}); "
         f"duplicated approved steps removed {d['duplicated_approved_steps_removed']} of {d['duplicated_approved_steps']}; "
         f"removed by wrong links {d['steps_removed_by_wrong_links']}.", "", "Links:", ""]
    for l in d["link_list"]:
        L.append(f"- drawing {l['drawing']} -> STEP {l['step']} tau {l['tau']} common {l['common']} rel {l['relative_differences']} "
                 f"correct {l['correct']} {l['phys']}")
    L += ["", "Unlinked drawing entities: " + json.dumps(d["unlinked_drawing_entities"]), "",
          "| tau_min | completeness | eps | admissible pairs | links | correct | precision | recall | duplicate steps removed | removed by wrong links |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["sweep"]:
        L.append(f"| {r['tau_min']} | {r['completeness']} | {r['eps']} | {r['admissible_pairs']} | {r['links']} | {r['correct_links']} | "
                 f"{f(r['precision'])} | {f(r['recall'])} | {len(r['duplicated_approved_steps_removed'])} | {len(r['steps_removed_by_wrong_links'])} |")
    with open(os.path.join(RESULTS, "r2_2_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r2_2_summary.md"), encoding="utf-8").read())

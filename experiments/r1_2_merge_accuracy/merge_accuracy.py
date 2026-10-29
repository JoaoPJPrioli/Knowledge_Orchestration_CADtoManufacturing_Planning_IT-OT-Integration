"""Reviewer 1, Comment 2 (with Reviewer 3, Comments 3 and 5): accuracy of the
reconciliation stage itself, at merge level, against the geometric references.

Ground truth per raw record is the Level G grounding of Revision 2
(ground_truth/results_v2.json, two_level.records[*].G.ref_id):
the B-Rep feature (R01 to R10) for a STEP record, or the drawing feature
(D01 to D06) for a drawing record. Two records from the two agents of one
modality are a true pair when they ground to the same reference feature.

For each reconciliation setting the script reports:
  * merge precision: merges whose partners ground to the same feature;
  * label-consistent precision: as above and the labels are type-admissible
    (tau >= 0.7), so the merge does not discard a disagreement;
  * merge recall: correct merges / maximum one-to-one matching of true pairs;
  * duplicated features: reference features left as two or more entities of
    one modality (missed merges);
  * for STEP-derived merged entities, the position error to the nearest
    anchor and the length error of the merged entity against those of its
    primary record (what averaging does to attributes).

Only the reconciliation stage runs (feature_parser.reconcile_features); the
repository is not modified.
"""
import copy
import itertools
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import GROUNDTRUTH, REPO, RESULTS, use_repo  # noqa: E402

use_repo()
import feature_parser as fp  # noqa: E402

DATA = os.path.join(REPO, "data", "motor_data")
FILES = {"STEP": ("features_eixo_step_Gemini31Pro.txt", "features_eixo_step_Gemini35flash.txt"),
         "DRAWING": ("draw_features_eixo_Gemini31Pro.txt", "draw_features_eixo_Gemini35flash.txt")}


def load_truth():
    res = json.load(open(os.path.join(GROUNDTRUTH, "results_v2.json"), encoding="utf-8"))
    truth = {}
    for r in res["two_level"]["records"]:
        g = r.get("G") or {}
        truth[(r["source_file"], r["id"])] = g.get("ref_id")
    refs = {f["ref_id"]: f for f in json.load(open(os.path.join(GROUNDTRUTH, "step_reference_v2.json"),
                                                   encoding="utf-8"))["features"]}
    return truth, refs


def load_records():
    out = {}
    for fam, (a, b) in FILES.items():
        pa = fp.parse_feature_file(os.path.join(DATA, a))
        pb = fp.parse_feature_file(os.path.join(DATA, b))
        for r in pa:
            r["source_file"] = a
        for r in pb:
            r["source_file"] = b
        out[fam] = (pa, pb)
    return out


def anchors(ref):
    c = tuple(ref["centre"])
    if ref["type"] == "Key":
        pts = [c, (c[0], ref["y_max"], c[2])]
        pts += [tuple(e["anchor_top"]) for e in ref.get("end_cylinders", [])]
        return pts
    pts = [c]
    if "z_min" in ref:
        pts += [(0.0, 0.0, ref["z_max"]), (0.0, 0.0, ref["z_min"])]
    return pts


def loc(rec):
    l = rec.get("absolute_location") or {}
    return (float(l.get("X", 0)), float(l.get("Y", 0)), float(l.get("Z", 0)))


def length(rec):
    d = rec.get("dimensions") or {}
    return float(d["L"]) if "L" in d else None


def max_matching(pairs):
    """Size of a maximum one-to-one matching in a bipartite set of (a, b) pairs."""
    adj = {}
    for a, b in pairs:
        adj.setdefault(a, []).append(b)
    match = {}

    def try_(a, seen):
        for b in adj.get(a, []):
            if b in seen:
                continue
            seen.add(b)
            if b not in match or try_(match[b], seen):
                match[b] = a
                return True
        return False
    return sum(1 for a in adj if try_(a, set()))


def score_with(weights, dmax, eps=None):
    wt, wd, wdl = weights

    def f(a, b):
        if eps is not None:
            for k in set(a.get("dimensions") or {}) & set(b.get("dimensions") or {}):
                x, y = a["dimensions"][k], b["dimensions"][k]
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    m = max(abs(x), abs(y))
                    if m and abs(x - y) / m > eps:
                        return -1.0
        s = wt * fp.calculate_type_similarity(a["type"], b["type"])
        la, lb = a.get("absolute_location", {}), b.get("absolute_location", {})
        if la and lb:
            d = fp.euclidean_distance((la.get("X", 0), la.get("Y", 0), la.get("Z", 0)),
                                      (lb.get("X", 0), lb.get("Y", 0), lb.get("Z", 0)))
            s += wd * max(0.0, 1.0 - d / dmax)
        s += wdl * fp.calculate_dimension_similarity(a.get("dimensions", {}), b.get("dimensions", {}))
        return s
    return f


def evaluate(data, truth, refs, theta=0.5, tau_min=0.7, weights=(0.4, 0.4, 0.2), dmax=50.0, eps=None):
    original = fp.calculate_match_score
    fp.calculate_match_score = score_with(weights, dmax, eps)
    try:
        out = {"entities": 0, "merges": 0, "correct": 0, "label_consistent_correct": 0, "max_true": 0,
               "duplicated_features": 0, "merge_list": [], "step_attr": []}
        for fam, (pa, pb) in data.items():
            ta = {r["id"]: truth[(r["source_file"], r["id"])] for r in pa}
            tb = {r["id"]: truth[(r["source_file"], r["id"])] for r in pb}
            true_pairs = [(a, b) for a in ta for b in tb if ta[a] is not None and ta[a] == tb[b]]
            out["max_true"] += max_matching(true_pairs)
            rec = fp.reconcile_features(copy.deepcopy(pa), copy.deepcopy(pb), type_gate=tau_min, match_threshold=theta)
            out["entities"] += len(rec)
            for e in rec:
                if e["reconciliation"] == "merged":
                    p, s = e["source_primary"], e["source_secondary"]
                    rp, rs = ta[p["id"]], tb[s["id"]]
                    tau = fp.calculate_type_similarity(p["type"], s["type"])
                    ok = rp is not None and rp == rs
                    out["merges"] += 1
                    out["correct"] += ok
                    out["label_consistent_correct"] += ok and tau >= 0.7
                    out["merge_list"].append({"family": fam, "primary": [p["id"], p["type"], rp],
                                              "secondary": [s["id"], s["type"], rs], "tau": tau,
                                              "same_feature": ok})
                    if fam == "STEP" and rp in refs:
                        A = anchors(refs[rp])
                        dp = min(math.dist(loc(p), a) for a in A)
                        dm = min(math.dist(loc(e), a) for a in A)
                        Lref = refs[rp].get("length")
                        Lp, Lm = length(p), length(e)
                        out["step_attr"].append({
                            "entity": [p["id"], s["id"]], "ref": rp, "pos_err_primary": dp, "pos_err_merged": dm,
                            "len_err_primary": None if (Lp is None or Lref is None) else abs(Lp - Lref),
                            "len_err_merged": None if (Lm is None or Lref is None) else abs(Lm - Lref)})
            # duplicated features: reference features with two or more entities of this modality
            refs_of_entities = []
            for e in rec:
                if e["reconciliation"] == "merged":
                    refs_of_entities.append(ta[e["source_primary"]["id"]])
                else:  # single-source entities are the original records
                    refs_of_entities.append(truth.get((e["source_file"], e["id"])))
            counts = {}
            for r in refs_of_entities:
                if r is not None:
                    counts[r] = counts.get(r, 0) + 1
            out["duplicated_features"] += sum(1 for v in counts.values() if v > 1)
    finally:
        fp.calculate_match_score = original
    m = out["merges"]
    out["precision"] = out["correct"] / m if m else None
    out["label_consistent_precision"] = out["label_consistent_correct"] / m if m else None
    out["recall"] = out["correct"] / out["max_true"] if out["max_true"] else None
    p, r = out["precision"], out["recall"]
    out["f1"] = (2 * p * r / (p + r)) if p and r else 0.0
    sa = out["step_attr"]
    if sa:
        out["step_merged_pos_err_mean"] = {"primary": sum(x["pos_err_primary"] for x in sa) / len(sa),
                                           "merged": sum(x["pos_err_merged"] for x in sa) / len(sa)}
        le = [x for x in sa if x["len_err_primary"] is not None and x["len_err_merged"] is not None]
        out["step_merged_len_err_mean"] = {"primary": sum(x["len_err_primary"] for x in le) / len(le),
                                           "merged": sum(x["len_err_merged"] for x in le) / len(le)} if le else None
    return out


def evaluate_global(data, truth, theta=0.5, tau_min=0.7, eps=None, weights=(0.4, 0.4, 0.2), dmax=50.0):
    """Probe: the same admissibility conditions with a global maximum-weight
    one-to-one assignment instead of greedy matching (analysis only)."""
    import networkx as nx
    sc = score_with(weights, dmax, eps)
    merges = correct = max_true = 0
    wrong = []
    for fam, (pa, pb) in data.items():
        ta = {r["id"]: truth[(r["source_file"], r["id"])] for r in pa}
        tb = {r["id"]: truth[(r["source_file"], r["id"])] for r in pb}
        max_true += max_matching([(a, b) for a in ta for b in tb if ta[a] is not None and ta[a] == tb[b]])
        g = nx.Graph()
        for a in pa:
            for b in pb:
                if fp.calculate_type_similarity(a["type"], b["type"]) < tau_min:
                    continue
                s = sc(a, b)
                if s > theta:
                    g.add_edge(("a", a["id"]), ("b", b["id"]), weight=s)
        for u, v in nx.max_weight_matching(g):
            if u[0] == "b":
                u, v = v, u
            ok = ta[u[1]] is not None and ta[u[1]] == tb[v[1]]
            merges += 1
            correct += ok
            if not ok:
                wrong.append([fam, u[1], ta[u[1]], v[1], tb[v[1]]])
    return {"merges": merges, "correct": correct, "precision": correct / merges if merges else None,
            "recall": correct / max_true if max_true else None, "wrong_merges": wrong}


def main():
    truth, refs = load_truth()
    data = load_records()
    res = {"reference": evaluate(data, truth, refs)}
    res["ablation_tau_min_0"] = evaluate(data, truth, refs, tau_min=0.0)
    res["tau_min_1"] = evaluate(data, truth, refs, tau_min=1.0)
    res["theta"] = {"gated": {t: evaluate(data, truth, refs, theta=t) for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)},
                    "ablated": {t: evaluate(data, truth, refs, theta=t, tau_min=0.0) for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)}}
    res["dmax"] = {d: evaluate(data, truth, refs, dmax=d) for d in (10.0, 25.0, 50.0, 100.0, 200.0)}
    res["eps"] = {"gated": {e: evaluate(data, truth, refs, eps=e) for e in (0.1, 0.2, 0.3, 0.5)},
                  "ablated": {e: evaluate(data, truth, refs, eps=e, tau_min=0.0) for e in (0.1, 0.2, 0.3, 0.5)}}
    grid = {}
    for wt in (0.2, 0.3, 0.4, 0.5, 0.6):
        for wd in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
            wdl = round(1.0 - wt - wd, 2)
            if wdl < 0 or wdl > 0.6:
                continue
            g = evaluate(data, truth, refs, weights=(wt, wd, wdl))
            a = evaluate(data, truth, refs, weights=(wt, wd, wdl), tau_min=0.0)
            grid[f"{wt},{wd},{wdl}"] = {k: {x: v[x] for x in ("merges", "correct", "precision", "label_consistent_precision", "recall", "f1")}
                                        for k, v in (("gated", g), ("ablated", a))}
    res["weights"] = grid
    def merge_set(r):
        return sorted((m["family"], m["primary"][0], m["secondary"][0]) for m in r["merge_list"])
    ref_set = merge_set(res["reference"])
    w_ident = 0
    for wt in (0.2, 0.3, 0.4, 0.5, 0.6):
        for wd in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
            wdl = round(1.0 - wt - wd, 2)
            if 0 <= wdl <= 0.6 and merge_set(evaluate(data, truth, refs, weights=(wt, wd, wdl))) == ref_set:
                w_ident += 1
    res["partition_identity"] = {
        "theta_gated": {t: merge_set(r) == ref_set for t, r in res["theta"]["gated"].items()},
        "dmax": {d: merge_set(r) == ref_set for d, r in res["dmax"].items()},
        "weights_identical_merge_set": w_ident,
        "dmax_25_merges_not_in_reference": [m for m in res["dmax"][25.0]["merge_list"]
                                           if (m["family"], m["primary"][0], m["secondary"][0]) not in ref_set]}
    res["global_assignment_probe"] = {
        "reference": evaluate_global(data, truth), "tau_min_0": evaluate_global(data, truth, tau_min=0.0),
        "tau_min_1": evaluate_global(data, truth, tau_min=1.0),
        "eps": {e: evaluate_global(data, truth, eps=e) for e in (0.1, 0.2, 0.3, 0.5)}}
    res["weights_summary"] = {
        side: {"settings": len(grid),
               "precision_range": [min(v[side]["precision"] for v in grid.values() if v[side]["precision"] is not None),
                                   max(v[side]["precision"] for v in grid.values() if v[side]["precision"] is not None)],
               "label_consistent_precision_range": [min(v[side]["label_consistent_precision"] for v in grid.values() if v[side]["label_consistent_precision"] is not None),
                                                    max(v[side]["label_consistent_precision"] for v in grid.values() if v[side]["label_consistent_precision"] is not None)],
               "recall_range": [min(v[side]["recall"] for v in grid.values()), max(v[side]["recall"] for v in grid.values())]}
        for side in ("gated", "ablated")}
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r1_2_merge_accuracy.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    write_summary(res)
    return res


def _row(name, r):
    pe = r.get("step_merged_pos_err_mean") or {}
    le = r.get("step_merged_len_err_mean") or {}
    f = lambda x: "n/a" if x is None else f"{x:.2f}"  # noqa: E731
    return (f"| {name} | {r['entities']} | {r['merges']} | {r['correct']} | {f(r['precision'])} | "
            f"{f(r['label_consistent_precision'])} | {r['max_true']} | {f(r['recall'])} | {r['duplicated_features']} | "
            f"{f(pe.get('primary'))} to {f(pe.get('merged'))} | {f(le.get('primary'))} to {f(le.get('merged'))} |")


def write_summary(res):
    L = ["# R1-2: merge-level accuracy of the reconciliation stage", "",
         "Truth: Level G grounding of each raw record (results_v2.json). Max true = maximum one-to-one matching "
         "of cross-agent record pairs grounded to the same reference feature (per modality, summed).", "",
         "| Setting | Entities | Merges | Same feature | Precision | Label-consistent precision | Max true | Recall | "
         "Duplicated features | STEP merged: pos. err. primary to merged (mm) | STEP merged: length err. primary to merged (mm) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    L.append(_row("reference (tau_min 0.7, theta 0.5)", res["reference"]))
    L.append(_row("gate ablated (tau_min 0)", res["ablation_tau_min_0"]))
    L.append(_row("tau_min 1.0", res["tau_min_1"]))
    for side in ("gated", "ablated"):
        for t, r in res["theta"][side].items():
            L.append(_row(f"theta {t} ({side})", r))
    for d, r in res["dmax"].items():
        L.append(_row(f"d_max {d}", r))
    for side in ("gated", "ablated"):
        for e, r in res["eps"][side].items():
            L.append(_row(f"epsilon {e} ({side})", r))
    L += ["", "Weights (26 settings): " + json.dumps(res["weights_summary"]), "",
          "Global one-to-one assignment probe: " + json.dumps(res["global_assignment_probe"]), "", "Reference merges:", ""]
    for m in res["reference"]["merge_list"]:
        L.append(f"- {m['family']}: {m['primary']} + {m['secondary']} tau {m['tau']} same feature {m['same_feature']}")
    L += ["", "Ablation merges:", ""]
    for m in res["ablation_tau_min_0"]["merge_list"]:
        L.append(f"- {m['family']}: {m['primary']} + {m['secondary']} tau {m['tau']} same feature {m['same_feature']}")
    with open(os.path.join(RESULTS, "r1_2_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r1_2_summary.md"), encoding="utf-8").read())

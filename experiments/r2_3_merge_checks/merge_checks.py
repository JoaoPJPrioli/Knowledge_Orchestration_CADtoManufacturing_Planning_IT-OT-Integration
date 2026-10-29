"""Reviewer 2, Comment 3: explicit completeness, dimensional-consistency, and
engineering-tolerance checks in the merge criterion, and how attribute fusion
relates to engineering tolerances.

The reference criterion merges a primary and a secondary record if and only if
tau >= tau_min and S > theta (feature_parser.reconcile_features). This study
adds admissibility conditions to it, evaluated on the stated dimensions of the
two records, and scores every setting with the merge-level measures of the
R1-2 study (same records, same Level G truth, same code):

  C       completeness: the two records state at least one common dimension
          (diameter from the diameter or twice the radius, length, width), so
          that their consistency can be checked at all;
  E(eps)  dimensional consistency: every common dimension agrees within a
          relative difference eps;
  T(k)    engineering tolerance: for every common dimension, the two values
          differ by no more than the ISO 2768-1 permissible deviation of class k
          (f, m, c, v), with the larger value as the nominal size. The drawing
          states no tolerance, so the class is an assumption and is swept.

Drawing records carry no structured dimensions; for them the conditions are
evaluated either on the structured fields only (as the reconciliation stage
sees them) or with the dimensions stated in their free text (read by
r1_5_programme_feasibility/free_text_dimensions.py; no value is guessed).
The merge score itself is unchanged.

Two further analyses:
  * discrepancy: for every cross-agent pair of records that ground to the same
    reference feature, the absolute difference of each common dimension,
    against the tolerance of each class;
  * fusion: the attributes of merged entities under three fusion policies
    (weighted average, as implemented; primary value kept; weighted average
    only within the tolerance of class k, otherwise the primary value),
    scored by the position and length errors of the merged STEP entities.

The repository is not modified (functions are replaced in-process only).
Writes results/r2_3_merge_checks.json and results/r2_3_summary.md.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import RESULTS  # noqa: E402
from r1_2_merge_accuracy import merge_accuracy as ma  # noqa: E402
from r1_5_programme_feasibility.free_text_dimensions import dimensions_from_text  # noqa: E402

fp = ma.fp

# ISO 2768-1:1989, Table 1: permissible deviations (+/- mm) for linear dimensions.
# Upper bounds of the nominal-size ranges; class v is not specified up to 3 mm,
# where the value of the next range is used.
ISO2768_UPPER = (3.0, 6.0, 30.0, 120.0, 400.0, 1000.0, 2000.0, 4000.0)
ISO2768 = {"f": (0.05, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, None),
           "m": (0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0),
           "c": (0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 3.0, 4.0),
           "v": (0.5, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 8.0)}
CLASSES = ("f", "m", "c", "v")


def tolerance(cls, nominal):
    for upper, t in zip(ISO2768_UPPER, ISO2768[cls]):
        if abs(nominal) <= upper:
            return t
    raise ValueError(f"nominal size {nominal} outside ISO 2768-1 Table 1")


def stated(rec, use_text):
    """Stated dimensions of a record, normalised to diameter (D), length (L) and width (W)."""
    d = rec.get("dimensions") or {}
    if not d and use_text:
        d = dimensions_from_text(rec.get("description", ""))
    num = lambda k: d.get(k) if isinstance(d.get(k), (int, float)) and not isinstance(d.get(k), bool) else None  # noqa: E731
    out = {}
    if num("Ø") is not None:
        out["D"] = float(num("Ø"))
    elif num("R") is not None:
        out["D"] = 2.0 * float(num("R"))
    if num("L") is not None:
        out["L"] = float(num("L"))
    if num("W") is not None:
        out["W"] = float(num("W"))
    return out


def common(a, b, use_text):
    sa, sb = stated(a, use_text), stated(b, use_text)
    return {k: (sa[k], sb[k]) for k in set(sa) & set(sb)}


def condition(completeness=False, eps=None, tol_class=None, use_text=True):
    def ok(a, b):
        c = common(a, b, use_text)
        if completeness and not c:
            return False
        for x, y in c.values():
            if eps is not None:
                m = max(abs(x), abs(y))
                if m and abs(x - y) / m > eps:
                    return False
            if tol_class is not None and abs(x - y) > tolerance(tol_class, max(abs(x), abs(y))) + 1e-9:
                return False
        return True
    return ok


def evaluate_with(cond, data, truth, refs, **kw):
    """ma.evaluate with an extra admissibility condition in front of the score."""
    original = ma.score_with

    def score_with(weights, dmax, eps=None):
        base = original(weights, dmax, eps)

        def f(a, b):
            return base(a, b) if cond(a, b) else -1.0
        return f
    ma.score_with = score_with
    try:
        r = ma.evaluate(data, truth, refs, **kw)
    finally:
        ma.score_with = original
    r["cross_family_merges"] = sum(1 for m in r["merge_list"] if m["tau"] < 0.7)
    return r


def brief(r):
    keys = ("entities", "merges", "correct", "cross_family_merges", "precision", "label_consistent_precision",
            "recall", "duplicated_features", "step_merged_pos_err_mean", "step_merged_len_err_mean")
    out = {k: r.get(k) for k in keys}
    out["merge_list"] = [[m["family"], m["primary"], m["secondary"], m["tau"], m["same_feature"]] for m in r["merge_list"]]
    return out


# --- fusion policies ------------------------------------------------------------------

def fusion(policy, tol_class=None):
    original = fp.merge_features

    def pick(x, y, w1, w2):
        if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
            return x
        if policy == "average":
            return w1 * x + w2 * y
        if policy == "primary":
            return x
        if policy == "tolerance":
            return w1 * x + w2 * y if abs(x - y) <= tolerance(tol_class, max(abs(x), abs(y), 0.5)) + 1e-9 else x
        raise ValueError(policy)

    def merge(feat1, feat2, weight1, weight2):
        m = original(feat1, feat2, weight1, weight2)
        l1, l2 = feat1.get("absolute_location", {}), feat2.get("absolute_location", {})
        for k in ("X", "Y", "Z"):
            if k in l1 and k in l2:
                m["absolute_location"][k] = pick(l1[k], l2[k], weight1, weight2)
        d1, d2 = feat1.get("dimensions", {}), feat2.get("dimensions", {})
        for k in set(d1) & set(d2):
            m["dimensions"][k] = pick(d1[k], d2[k], weight1, weight2)
        return m
    return original, merge


def evaluate_fusion(data, truth, refs, policy, tol_class=None):
    original, merge = fusion(policy, tol_class)
    fp.merge_features = merge
    try:
        r = ma.evaluate(data, truth, refs)
    finally:
        fp.merge_features = original
    return {"policy": policy if tol_class is None else f"{policy}:{tol_class}",
            "step_merged_pos_err_mean": r.get("step_merged_pos_err_mean"),
            "step_merged_len_err_mean": r.get("step_merged_len_err_mean"),
            "step_attr": r["step_attr"]}


# --- discrepancy of true pairs against tolerance -----------------------------------------

def discrepancies(data, truth):
    rows = []
    for fam, (pa, pb) in data.items():
        for a in pa:
            for b in pb:
                ra, rb = truth[(a["source_file"], a["id"])], truth[(b["source_file"], b["id"])]
                if ra is None or ra != rb:
                    continue
                for k, (x, y) in sorted(common(a, b, use_text=True).items()):
                    nominal = max(abs(x), abs(y))
                    rows.append({"family": fam, "ref": ra, "primary": [a["id"], a["type"]], "secondary": [b["id"], b["type"]],
                                 "dimension": k, "values": [x, y], "difference": round(abs(x - y), 4),
                                 "relative_difference": round(abs(x - y) / nominal, 4) if nominal else 0.0,
                                 "within": {c: abs(x - y) <= tolerance(c, nominal) + 1e-9 for c in CLASSES},
                                 "source": "free_text" if fam == "DRAWING" else "structured"})
    n = len(rows)
    nonzero = [r for r in rows if r["difference"] > 1e-9]
    summary = {"common_dimensions_of_true_pairs": n,
               "identical": n - len(nonzero),
               "different": len(nonzero),
               "within_tolerance": {c: sum(r["within"][c] for r in rows) for c in CLASSES},
               "different_within_tolerance": {c: sum(r["within"][c] for r in nonzero) for c in CLASSES},
               "smallest_nonzero_difference": min((r["difference"] for r in nonzero), default=None),
               "largest_difference": max((r["difference"] for r in rows), default=None)}
    return rows, summary


def main():
    truth, refs = ma.load_truth()
    data = ma.load_records()
    res = {"criterion": "reference: tau >= 0.7 and S > 0.5; conditions are added in front of the score",
           "iso2768_1_table1": {"upper_bounds_mm": ISO2768_UPPER, "deviations_mm": ISO2768}}
    settings = {"reference": condition()}
    for use_text, tag in ((False, "structured"), (True, "free_text")):
        settings[f"C[{tag}]"] = condition(completeness=True, use_text=use_text)
        for e in (0.1, 0.2, 0.3, 0.5):
            settings[f"E{e}[{tag}]"] = condition(eps=e, use_text=use_text)
            settings[f"C+E{e}[{tag}]"] = condition(completeness=True, eps=e, use_text=use_text)
        for k in CLASSES:
            settings[f"T{k}[{tag}]"] = condition(tol_class=k, use_text=use_text)
            settings[f"C+T{k}[{tag}]"] = condition(completeness=True, tol_class=k, use_text=use_text)
    res["gated"] = {name: brief(evaluate_with(c, data, truth, refs)) for name, c in settings.items()}
    res["ablated_type_gate"] = {name: brief(evaluate_with(settings[name], data, truth, refs, tau_min=0.0))
                                for name in ("reference", "C[free_text]", "C+E0.1[free_text]", "C+E0.2[free_text]",
                                             "C+E0.3[free_text]", "C+E0.5[free_text]", "C+Tm[free_text]", "C+Tv[free_text]")}
    rows, summary = discrepancies(data, truth)
    res["discrepancy_true_pairs"] = {"summary": summary, "rows": rows}
    res["fusion"] = [evaluate_fusion(data, truth, refs, "average"), evaluate_fusion(data, truth, refs, "primary")] + \
                    [evaluate_fusion(data, truth, refs, "tolerance", k) for k in CLASSES]
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r2_3_merge_checks.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    write_summary(res)
    return res


def write_summary(res):
    f = lambda x: "n/a" if x is None else f"{x:.2f}"  # noqa: E731
    L = ["# R2-3: completeness, consistency, and tolerance checks in the merge criterion", "",
         "| Setting | Entities | Merges | Same feature | Cross-family | Precision | Recall | STEP merged pos. err. (mm) | STEP merged length err. (mm) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for side in ("gated", "ablated_type_gate"):
        for name, r in res[side].items():
            pe, le = r["step_merged_pos_err_mean"] or {}, r["step_merged_len_err_mean"] or {}
            L.append(f"| {name} ({side}) | {r['entities']} | {r['merges']} | {r['correct']} | {r['cross_family_merges']} | "
                     f"{f(r['precision'])} | {f(r['recall'])} | {f(pe.get('merged'))} | {f(le.get('merged'))} |")
    s = res["discrepancy_true_pairs"]["summary"]
    L += ["", "Discrepancy of common dimensions on true same-feature pairs: " + json.dumps(s), ""]
    for r in res["discrepancy_true_pairs"]["rows"]:
        L.append(f"- {r['family']} {r['ref']} {r['primary']} / {r['secondary']} {r['dimension']}: {r['values']} "
                 f"diff {r['difference']} within {r['within']}")
    L += ["", "Fusion policies (merged STEP entities, mean position and length error, mm):", ""]
    for x in res["fusion"]:
        L.append(f"- {x['policy']}: position {json.dumps(x['step_merged_pos_err_mean'])}, length {json.dumps(x['step_merged_len_err_mean'])}")
    with open(os.path.join(RESULTS, "r2_3_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r2_3_summary.md"), encoding="utf-8").read())

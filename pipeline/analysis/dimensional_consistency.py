"""
Dimensional-consistency condition for the merge criterion (KINM stage only; no reasoner).
=========================================================================================
Adds a third conjunct to Eq. 3: a pair is admissible only if, for every dimension key
the two records share (diameter, radius, length, width), the relative disagreement
|a1 - a2| / max(|a1|, |a2|) does not exceed eps. Records that share no key pass, because
there is then no dimensional evidence against the merge. No tolerance values are needed,
which matters because 29 of the 30 archived records state no tolerance.

The script sweeps eps with the type gate enabled (tau_min = 0.7, the reference) and
disabled (tau_min = 0, the ablation), reports the same quantities as sensitivity.py, and
lists every merge of the reference partition that each setting blocks, with the
disagreement that blocks it. It does not change the reference configuration.

Usage:
    python analysis/dimensional_consistency.py <repo_dir> [out.json]
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "src"))
import feature_parser as fp  # noqa: E402

DATA = os.path.join(sys.argv[1], "data", "motor_data")
FILES = {
    "step": ("features_eixo_step_Gemini31Pro.txt", "features_eixo_step_Gemini35flash.txt"),
    "drawing": ("draw_features_eixo_Gemini31Pro.txt", "draw_features_eixo_Gemini35flash.txt"),
}


def load():
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


def worst_disagreement(d1, d2):
    """Largest relative disagreement over shared numeric keys, and the key; (0, None) if none shared."""
    worst, key = 0.0, None
    for k in set(d1 or {}) & set(d2 or {}):
        a, b = d1[k], d2[k]
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            continue
        m = max(abs(a), abs(b))
        r = 0.0 if m == 0 else abs(a - b) / m
        if r > worst:
            worst, key = r, k
    return worst, key


def run(data, eps=None, tau_min=0.7, theta=0.5):
    original = fp.calculate_match_score

    def gated_score(a, b):
        if eps is not None:
            r, _ = worst_disagreement(a.get("dimensions", {}), b.get("dimensions", {}))
            if r > eps:
                return -1.0  # inadmissible: can never exceed best_score (0) or theta
        return original(a, b)

    fp.calculate_match_score = gated_score
    try:
        out = {"entities": 0, "merges": 0, "merges_tau_below_0.7": 0, "primary_only": 0,
               "secondary_only": 0, "merged_pairs": []}
        for fam, (pa, pb) in data.items():
            rec = fp.reconcile_features(copy.deepcopy(pa), copy.deepcopy(pb), type_gate=tau_min,
                                        match_threshold=theta)
            out["entities"] += len(rec)
            for e in rec:
                if e["reconciliation"] == "merged":
                    p, s = e["source_primary"], e["source_secondary"]
                    out["merges"] += 1
                    tau = fp.calculate_type_similarity(p["type"], s["type"])
                    if tau < 0.7:
                        out["merges_tau_below_0.7"] += 1
                    r, k = worst_disagreement(p.get("dimensions", {}), s.get("dimensions", {}))
                    out["merged_pairs"].append({"family": fam, "primary": [p["id"], p["type"], p.get("dimensions", {})],
                                                "secondary": [s["id"], s["type"], s.get("dimensions", {})],
                                                "tau": tau, "worst_rel_disagreement": round(r, 3), "key": k})
                elif e["reconciliation"] == "secondary_only":
                    out["secondary_only"] += 1
                else:
                    out["primary_only"] += 1
    finally:
        fp.calculate_match_score = original
    return out


def pair_key(m):
    return (m["family"], m["primary"][0], m["secondary"][0])


def main(repo, out_path=None):
    data = load()
    ref = run(data)
    ref_pairs = {pair_key(m): m for m in ref["merged_pairs"]}
    res = {"reference": ref, "sweep": {}}
    for tau_min, label in ((0.7, "gated"), (0.0, "ablated")):
        res["sweep"][label] = {}
        for eps in (0.1, 0.2, 0.3, 0.5):
            r = run(data, eps=eps, tau_min=tau_min)
            pairs = {pair_key(m) for m in r["merged_pairs"]}
            r["reference_merges_blocked"] = [ref_pairs[k] for k in ref_pairs if k not in pairs]
            r["new_merges"] = [m for m in r["merged_pairs"] if pair_key(m) not in ref_pairs]
            res["sweep"][label][eps] = r
    if out_path:
        json.dump(res, open(out_path, "w"), indent=1)
    # compact console report
    print("reference merges (worst relative disagreement over shared keys):")
    for m in ref["merged_pairs"]:
        print(f"  {m['family']:8s} {m['primary'][1]:12s}+{m['secondary'][1]:12s} tau {m['tau']:.1f} "
              f"worst {m['worst_rel_disagreement']} on {m['key']}  P{m['primary'][2]} S{m['secondary'][2]}")
    for label, sw in res["sweep"].items():
        for eps, r in sw.items():
            print(f"{label:8s} eps {eps}: entities {r['entities']}, merges {r['merges']}, cross-family "
                  f"{r['merges_tau_below_0.7']}, primary-only {r['primary_only']}, secondary-only {r['secondary_only']}; "
                  f"blocked {[(m['primary'][1], m['secondary'][1], m['worst_rel_disagreement']) for m in r['reference_merges_blocked']]}; "
                  f"new {[(m['primary'][1], m['secondary'][1]) for m in r['new_merges']]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)

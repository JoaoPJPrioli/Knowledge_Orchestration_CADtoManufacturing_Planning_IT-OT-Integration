"""
Reconciliation sensitivity analysis (KINM stage only; no reasoner needed).
===========================================================================
Sweeps the design parameters of the merge criterion (Eq. 1 to Eq. 3) on the
four archived feature files and reports, for every setting: reconciled
entities, merges admitted, merges below the same-family tier (tau < 0.7),
slot records surviving, and the number of secondary-only entities (those that
receive the fixed confidence w_s and are therefore routed to review).

Sweeps:
  * theta in {0.3, ..., 0.8} with the gate enabled and disabled;
  * tau_min in {0 (ablation), 0.3, 0.7 (reference), 1.0 (identical labels only)};
  * d_max in {10, 25, 50 (reference), 100, 200} mm;
  * weight vectors (w_tau, w_d, w_delta) on the simplex, step 0.1, w_tau >= 0.2;
  * the co-location probe: pairs of records from different agents whose
    distance is <= 5 mm but whose type similarity is below tau_min.

Usage:
    python analysis/sensitivity.py <repo_dir> [analysis/results/sensitivity.json]
"""
import copy
import itertools
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


def score_with(weights, dmax):
    """Return a match-score function with the given weights and d_max."""
    wt, wd, wdl = weights

    def f(a, b):
        s = wt * fp.calculate_type_similarity(a["type"], b["type"])
        la, lb = a.get("absolute_location", {}), b.get("absolute_location", {})
        if la and lb:
            d = fp.euclidean_distance((la.get("X", 0), la.get("Y", 0), la.get("Z", 0)),
                                      (lb.get("X", 0), lb.get("Y", 0), lb.get("Z", 0)))
            s += wd * max(0.0, 1.0 - d / dmax)
        s += wdl * fp.calculate_dimension_similarity(a.get("dimensions", {}), b.get("dimensions", {}))
        return s
    return f


def run(data, theta=0.5, tau_min=0.7, weights=(0.4, 0.4, 0.2), dmax=50.0):
    original = fp.calculate_match_score
    fp.calculate_match_score = score_with(weights, dmax)
    try:
        ents, merges, low_tau, slots, sec_only, prim_only = 0, 0, 0, 0, 0, 0
        for fam, (pa, pb) in data.items():
            rec = fp.reconcile_features(copy.deepcopy(pa), copy.deepcopy(pb),
                                        type_gate=tau_min, match_threshold=theta)
            ents += len(rec)
            for e in rec:
                if e["reconciliation"] == "merged":
                    merges += 1
                    if fp.calculate_type_similarity(e["source_primary"]["type"], e["source_secondary"]["type"]) < 0.7:
                        low_tau += 1
                elif e["reconciliation"] == "secondary_only":
                    sec_only += 1
                else:
                    prim_only += 1
                if e["type"] == "Slot":
                    slots += 1
    finally:
        fp.calculate_match_score = original
    return {"entities": ents, "merges": merges, "merges_tau_below_0.7": low_tau, "slots": slots,
            "primary_only": prim_only, "secondary_only": sec_only}


def main(repo, out=None):
    data = load()
    res = {"reference": run(data)}
    res["theta_sweep"] = {"gated": {}, "ablated": {}}
    for th in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        res["theta_sweep"]["gated"][th] = run(data, theta=th)
        res["theta_sweep"]["ablated"][th] = run(data, theta=th, tau_min=0.0)
    res["tau_min_sweep"] = {t: run(data, tau_min=t) for t in (0.0, 0.3, 0.7, 1.0)}
    res["dmax_sweep"] = {d: run(data, dmax=d) for d in (10.0, 25.0, 50.0, 100.0, 200.0)}
    res["dmax_sweep_ablated"] = {d: run(data, dmax=d, tau_min=0.0) for d in (10.0, 25.0, 50.0, 100.0, 200.0)}
    grid = {}
    for wt in (0.2, 0.3, 0.4, 0.5, 0.6):
        for wd in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
            wdl = round(1.0 - wt - wd, 2)
            if wdl < 0 or wdl > 0.6:
                continue
            grid[f"{wt},{wd},{wdl}"] = {"gated": run(data, weights=(wt, wd, wdl)),
                                        "ablated": run(data, weights=(wt, wd, wdl), tau_min=0.0)}
    res["weight_grid"] = grid
    ref = res["reference"]
    res["weight_grid_summary"] = {
        "settings": len(grid),
        "gated_identical_to_reference": sum(1 for v in grid.values() if v["gated"] == ref),
        "gated_entities_range": [min(v["gated"]["entities"] for v in grid.values()), max(v["gated"]["entities"] for v in grid.values())],
        "gated_cross_family_merges_max": max(v["gated"]["merges_tau_below_0.7"] for v in grid.values()),
        "ablated_settings_with_cross_family_merges": sum(1 for v in grid.values() if v["ablated"]["merges_tau_below_0.7"] > 0),
        "ablated_entities_range": [min(v["ablated"]["entities"] for v in grid.values()), max(v["ablated"]["entities"] for v in grid.values())],
    }
    # co-location probe
    probe = []
    for fam, (pa, pb) in data.items():
        for a in pa:
            for b in pb:
                la, lb = a.get("absolute_location", {}), b.get("absolute_location", {})
                if not la or not lb:
                    continue
                d = fp.euclidean_distance((la["X"], la["Y"], la["Z"]), (lb["X"], lb["Y"], lb["Z"]))
                tau = fp.calculate_type_similarity(a["type"], b["type"])
                if d <= 5.0 and tau < 0.7:
                    probe.append({"family": fam, "primary": (a["id"], a["type"]), "secondary": (b["id"], b["type"]),
                                  "distance_mm": round(d, 3), "tau": tau,
                                  "metric_agreement": round((0.4 * max(0, 1 - d / 50) + 0.2 * fp.calculate_dimension_similarity(a.get("dimensions", {}), b.get("dimensions", {}))) / 0.6, 3)})
    res["colocation_probe_5mm"] = probe
    if out:
        json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "weight_grid"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)

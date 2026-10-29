"""Reviewer 1, Comment 5: material-based check of the serialised programmes.

Checks the reference programme against a declared bar stock (with a sweep over
the stock assumptions and the simulator's default 80 mm stock), and the
programme of the free-text-dimension configuration. Writes
results/r1_5_programme_feasibility.json and results/r1_5_summary.md.
"""
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import RESULTS, RUNS  # noqa: E402
from r1_5_programme_feasibility import stock_check as sc  # noqa: E402
from r1_5_programme_feasibility.free_text_dimensions import dimensions_from_text  # noqa: E402
from r1_8_process_models.process_models import read_tool_knowledge  # noqa: E402

REF = os.path.join(RUNS, "reference")
FREE = os.path.join(RUNS, "free_text_dimensions")
# Bar stock of the reference process plan (judgement J01: d 30 cold-drawn AISI 1045); free end
# 1 mm beyond the drive-end face (z 168.5), the allowance being an assumption of this check.
NOMINAL_STOCK = (30.0, 169.5)


def tool_depth_limits():
    import rdflib
    from common.paths import REPO
    g = rdflib.Graph()
    g.parse(os.path.join(REPO, "knowledge", "foundation", "tools.owl"), format="xml")
    lim = {}
    legacy = {"TurningInsertRough": "turning_insert_rough", "TurningInsertFinish": "turning_insert_finish",
              "DrillBit": "drill_bit", "CounterboreCutter": "counterbore_cutter"}
    for s, p, o in g:
        if str(p).endswith("#hasMaxDepthMM") and str(s).split("#")[-1] in legacy:
            lim[legacy[str(s).split("#")[-1]]] = float(o)
    return lim


def summarise(r):
    c = r["conformance"]
    feed = [m for m in r["moves"] if "radial_engagement_mm" in m]
    return {
        "rapids_into_stock": len(r["rapids_into_stock"]),
        "rapid_penetration_max_mm": max((x["depth_mm"] for x in r["rapids_into_stock"]), default=0.0),
        "max_radial_engagement_mm": max((m["radial_engagement_mm"] for m in feed), default=0.0),
        "passes_exceeding_planned_ap": sum(1 for m in feed if m["exceeds_planned"]),
        "passes_exceeding_tool_limit": sum(1 for m in feed if m["exceeds_tool"]),
        "finishing_passes_removing_nothing": sum(1 for m in feed if m["operation"] == "finish_turning"
                                                 and m["radial_engagement_mm"] <= 0.0),
        "outer_gouges": c["outer_gouges"], "inner_gouges": c["inner_gouges"],
        "feed_moves_below_part_extent": len(r["feed_moves_below_part_extent"]),
    }


def main():
    lim = tool_depth_limits()
    plan = json.load(open(os.path.join(REF, "manufacturing_plan.json"), encoding="utf-8"))
    nc = os.path.join(REF, "motor_shaft_1001.nc")
    res = {"tool_depth_limits_mm": lim, "nominal_stock": {"diameter_mm": NOMINAL_STOCK[0], "free_end_z": NOMINAL_STOCK[1]}}
    res["reference_nominal"] = sc.check_programme(nc, plan, *NOMINAL_STOCK, lim)
    sweep = {}
    for d, zf in itertools.product((26.0, 28.0, 30.0), (169.0, 169.5, 170.5)):
        sweep[f"{d}/{zf}"] = summarise(sc.check_programme(nc, plan, d, zf, lim))
    res["reference_stock_sweep"] = sweep
    res["reference_simulator_default_stock"] = summarise(sc.check_programme(nc, plan, 80.0, 169.5, lim))

    if os.path.isdir(FREE):
        fplan = json.load(open(os.path.join(FREE, "manufacturing_plan.json"), encoding="utf-8"))
        fr = sc.check_programme(os.path.join(FREE, "motor_shaft_1001.nc"), fplan, *NOMINAL_STOCK, lim)
        refusals = json.load(open(os.path.join(FREE, "ral_refusals.json"), encoding="utf-8"))
        feats = {f["id"]: f for f in json.load(open(os.path.join(REF, "features.json"), encoding="utf-8"))}
        new_steps = sorted(set(refusals["accounting"]["serialised_steps"]) -
                           set(json.load(open(os.path.join(REF, "ral_refusals.json"), encoding="utf-8"))["accounting"]["serialised_steps"]))
        by_num = {s["step_number"]: s for s in fplan}
        res["free_text_configuration"] = {
            "accounting": refusals["accounting"],
            "newly_serialised_steps": [{"step": n, "operation": by_num[n]["operation"], "feature_id": by_num[n]["feature_id"],
                                        "feature_type": by_num[n]["feature_type"],
                                        "dimensions": by_num[n]["feature_dimensions"],
                                        "location_z": by_num[n]["feature_location"].get("Z")} for n in new_steps],
            "parsed_from_text": {fid: dimensions_from_text(f["description"]) for fid, f in feats.items()
                                 if not f["dimensions"] and dimensions_from_text(f["description"])},
            "check": fr, "summary": summarise(fr)}
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r1_5_programme_feasibility.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    write_summary(res)
    return res


def write_summary(res):
    r = res["reference_nominal"]
    L = ["# R1-5: material-based check of the serialised programme", "",
         f"Stock: bar of {res['nominal_stock']['diameter_mm']} mm, free end at z = {res['nominal_stock']['free_end_z']} mm "
         "(part end face at 168.5 mm); tool depth limits from tools.owl: " + json.dumps(res["tool_depth_limits_mm"]), "",
         "## Reference programme", "", "Feed moves and cycles:", "",
         "| Line | Step | Operation | Tool | Radial engagement or depth (mm) | Planned ap (mm) | Tool limit (mm) |",
         "|---|---|---|---|---|---|---|"]
    for m in r["moves"]:
        v = m.get("radial_engagement_mm", m.get("depth_in_material_mm"))
        L.append(f"| {m['line']} | {m['step']} | {m['operation']} | {m['tool']} | {v} | {m.get('planned_depth_of_cut_mm', '')} | {m['tool_max_depth_mm']} |")
    L += ["", "Rapid moves entering material: " + json.dumps(r["rapids_into_stock"]), "",
          "Conformance with the B-Rep reference: " + json.dumps(r["conformance"], indent=1), "",
          "Stock sweep (bar diameter / free-end z):", "", "```", json.dumps(res["reference_stock_sweep"], indent=1), "```", "",
          "Simulator default stock (80 mm): " + json.dumps(res["reference_simulator_default_stock"]), ""]
    if "free_text_configuration" in res:
        f = res["free_text_configuration"]
        L += ["## Free-text-dimension configuration", "", "Accounting: " + json.dumps(f["accounting"]), "",
              "Newly serialised steps: " + json.dumps(f["newly_serialised_steps"]), "",
              "Summary of its material check: " + json.dumps(f["summary"], indent=1), "",
              "Feed moves below the part's axial extent: " + json.dumps(f["check"]["feed_moves_below_part_extent"])]
    with open(os.path.join(RESULTS, "r1_5_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r1_5_summary.md"), encoding="utf-8").read())

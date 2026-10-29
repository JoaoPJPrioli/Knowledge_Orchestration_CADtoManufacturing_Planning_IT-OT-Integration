"""Reviewer 1, Comment 5 ("Step B"): serialise the reference plan's approved
steps with the stock-aware turning profile and check the result with the same
material check and the same pipeline checks as the reference programme.

Writes runs/stock_aware_profile/ (programme and check reports),
results/r1_5_stock_aware_profile.json and results/r1_5_stock_aware_summary.md.
"""
import itertools
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import RESULTS, RUNS, use_repo  # noqa: E402
from r1_5_programme_feasibility import stock_check as sc  # noqa: E402
from r1_5_programme_feasibility.run_r1_5 import NOMINAL_STOCK, summarise, tool_depth_limits  # noqa: E402
from r1_5_programme_feasibility.stock_aware_profile import StockAwareTurningGenerator, approved_steps  # noqa: E402

use_repo()
from programme_fidelity import check_parameter_fidelity  # noqa: E402
from dimension_fidelity import check_dimension_fidelity  # noqa: E402
from validator import validate_gcode_file  # noqa: E402
from simulator import CNCSimulator  # noqa: E402
import skl_repository as skl  # noqa: E402

REF = os.path.join(RUNS, "reference")
OUT = os.path.join(RUNS, "stock_aware_profile")
NC_NAME = "motor_shaft_stock_aware.nc"


def segments(nc):
    with open(nc, encoding="utf-8") as fh:
        return [ln for ln in fh if ln.startswith("(--- ") and ": " in ln
                and not ln.startswith("(--- Tool Change") and not ln.startswith("(--- Machine")]


def generate(plan, d, zf, path):
    gen = StockAwareTurningGenerator(d, zf)
    prog = gen.generate_program(approved_steps(plan))
    prog.save_to_file(path)
    return gen


def pipeline_checks(nc, serialised, data):
    machines, tools, materials, operations = data
    val = validate_gcode_file(nc, "cnc_lathe", machines_data=machines)
    sim = CNCSimulator(machine_id="cnc_lathe", material_id="steel_1045", stock_diameter=80.0, stock_length=200.0,
                       machines_data=machines, tools_data=tools, materials_data=materials,
                       operations_data=operations, plan_steps=serialised).simulate_file(nc)
    pf = check_parameter_fidelity(nc, serialised)
    df = check_dimension_fidelity(nc, serialised)
    ct = sim.get("cutting_time", {})
    return {
        "segments": len(segments(nc)), "serialised_steps": len(serialised),
        "validator": {"errors": val["summary"]["errors"], "warnings": val["summary"]["warnings"]},
        "parameter_fidelity": {k: pf[k] for k in ("passed", "segments_checked", "spindle_match", "feed_match",
                                                   "coolant_match")},
        "dimension_fidelity": {k: df[k] for k in ("passed", "segments", "lookups", "defaulted",
                                                   "cutting_words_checked", "unexplained_cutting_words")},
        "cycle_time_min": round(ct.get("total_cycle_time_minutes", 0.0), 2),
        "cutting_time_s": round(ct.get("cutting_time_seconds", 0.0), 1),
        "rapid_time_s": round(ct.get("rapid_time_seconds", 0.0), 1),
        "tool_change_time_s": round(ct.get("tool_change_time_seconds", 0.0), 1),
        "program_lines": sum(1 for _ in open(nc, encoding="utf-8")),
    }


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    lim = tool_depth_limits()
    plan = json.load(open(os.path.join(REF, "manufacturing_plan.json"), encoding="utf-8"))
    repo = skl.SKLRepository()
    data = (repo.legacy_machines_dict(), repo.legacy_tools_dict(), repo.legacy_materials_dict(),
            repo.legacy_operations_dict())

    nc = os.path.join(OUT, NC_NAME)
    gen = generate(plan, *NOMINAL_STOCK, nc)
    check = sc.check_programme(nc, plan, *NOMINAL_STOCK, lim)
    res = {
        "profile": StockAwareTurningGenerator.PROFILE_NAME,
        "nominal_stock": {"diameter_mm": NOMINAL_STOCK[0], "free_end_z": NOMINAL_STOCK[1]},
        "tool_depth_limits_mm": lim,
        "approved_steps": len(approved_steps(plan)),
        "serialised_steps": [s["step_number"] for s in gen.serialised_steps],
        "refusals": [{"step_number": r["step_number"], "operation": r.get("operation"),
                      "kind": r.get("kind", "serialisation_input_missing"),
                      "detail": r.get("missing_inputs")} for r in sorted(gen.refusals, key=lambda r: r["step_number"])],
        "recess_refusals": sorted(r["step_number"] for r in gen.refusals if r.get("kind") == "recess"),
        "plan_overlaps": gen.plan_overlaps,
        "targets": {str(k): v for k, v in gen.targets.items()},
        "passes": gen.passes,
        "check": check, "summary": summarise(check),
        "pipeline_checks": pipeline_checks(nc, gen.serialised_steps, data),
    }
    # the reference programme through the same harness, for a like-for-like comparison
    ref_nc = os.path.join(REF, "motor_shaft_1001.nc")
    ref_serialised = [s for s in plan if s["step_number"] in json.load(
        open(os.path.join(REF, "ral_refusals.json"), encoding="utf-8"))["accounting"]["serialised_steps"]]
    ref_check = sc.check_programme(ref_nc, plan, *NOMINAL_STOCK, lim)
    res["reference"] = {"summary": summarise(ref_check), "conformance": ref_check["conformance"],
                        "pipeline_checks": pipeline_checks(ref_nc, ref_serialised, data)}

    # stock sweep: the profile is regenerated for each declared bar
    sweep = {}
    for d, zf in itertools.product((26.0, 28.0, 30.0), (169.0, 169.5, 170.5)):
        p = os.path.join(OUT, f"sweep_{d:g}_{zf:g}.nc")
        g = generate(plan, d, zf, p)
        r = sc.check_programme(p, plan, d, zf, lim)
        sweep[f"{d}/{zf}"] = dict(summarise(r), passes=len(g.passes),
                                  recess_refusals=sorted(x["step_number"] for x in g.refusals if x.get("kind") == "recess"),
                                  outer_residual=r["conformance"]["outer_residual"],
                                  inner_residual=r["conformance"]["inner_residual"])
    res["stock_sweep"] = sweep
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r1_5_stock_aware_profile.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    write_summary(res)
    return res


def write_summary(res):
    s, r = res["summary"], res["reference"]["summary"]
    pc, rc = res["pipeline_checks"], res["reference"]["pipeline_checks"]
    L = ["# R1-5 Step B: stock-aware turning profile (evaluation code)", "",
         f"Declared stock: {res['nominal_stock']['diameter_mm']} mm bar, free end z = {res['nominal_stock']['free_end_z']}",
         f"Approved steps: {res['approved_steps']}; serialised: {res['serialised_steps']}", "",
         "Refusals: " + json.dumps(res["refusals"], indent=1), "",
         "Plan overlaps (recorded, not refused): " + json.dumps(res["plan_overlaps"], indent=1), "",
         "| Pass | Step | Operation | Diameter | Radial depth | Planned ap |", "|---|---|---|---|---|---|"]
    for i, p in enumerate(res["passes"], 1):
        L.append(f"| {i} | {p['step']} | {p['operation']} | {p['diameter']} | {p['radial_depth']} | {p['planned_ap']} |")
    L += ["", "| Quantity | Reference programme | Stock-aware profile |", "|---|---|---|"]
    for k in s:
        a, b = r[k], s[k]
        if isinstance(a, list):
            a, b = len(a), len(b)
        L.append(f"| {k} | {a} | {b} |")
    for k in ("segments", "cycle_time_min", "cutting_time_s", "rapid_time_s", "program_lines"):
        L.append(f"| {k} | {rc[k]} | {pc[k]} |")
    L.append(f"| validator errors/warnings | {rc['validator']} | {pc['validator']} |")
    L.append(f"| parameter fidelity | {rc['parameter_fidelity']} | {pc['parameter_fidelity']} |")
    L.append(f"| dimension fidelity | {rc['dimension_fidelity']} | {pc['dimension_fidelity']} |")
    L += ["", "Conformance (stock-aware): " + json.dumps(res["check"]["conformance"], indent=1), "",
          "Conformance (reference): " + json.dumps(res["reference"]["conformance"], indent=1), "",
          "Stock sweep: ", "```", json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ('outer_residual', 'inner_residual')}
                                              for k, v in res["stock_sweep"].items()}, indent=1), "```"]
    with open(os.path.join(RESULTS, "r1_5_stock_aware_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r1_5_stock_aware_summary.md"), encoding="utf-8").read())

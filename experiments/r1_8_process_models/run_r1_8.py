"""Reviewer 1, Comment 8: corrected force and tool-life models and an
evaluation of the tool-life feedback path.

Reads runs/reference (and runs/material_aluminum for the missing-knowledge
case), writes results/r1_8_process_models.json and results/r1_8_summary.md.
"""
import copy
import itertools
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import RESULTS, RUNS  # noqa: E402
from r1_8_process_models import process_models as pm  # noqa: E402

REF = os.path.join(RUNS, "reference")
ALU = os.path.join(RUNS, "material_aluminum")


def legacy_channels(run_dir):
    sim = json.load(open(os.path.join(run_dir, "motor_shaft_1001_simulation.json"), encoding="utf-8"))
    cla = sim["chip_load_analysis"]
    return {
        "constant_kc_force_by_step": {p["force_inputs"]["plan_step_number"]: p["cutting_force_N"]
                                      for p in cla["parameters"]},
        "constant_kc_power_by_step": {p["force_inputs"]["plan_step_number"]: p["cutting_power_kW"]
                                      for p in cla["parameters"]},
        "constant_kc_mean_force_N": cla["average_cutting_force"],
        "legacy_wear": {t: {"wear_percentage": s["wear_percentage"],
                            "wear_model_cutting_time_min": s["cumulative_cutting_time_minutes"],
                            "status": s["wear_status"]} for t, s in sim["tool_wear"].items()},
        "programme_cutting_time_s": sim["cutting_time"]["cutting_time_seconds"],
    }


def kienzle_sweep(C):
    sw = C["kienzle"]["steel_1045"]["sweep"]
    rows = []
    for kc11, mc, kap in itertools.product(sw["kc11_N_per_mm2"], sw["mc"],
                                           C["geometry"]["turning_entering_angle_deg"]["sweep"]):
        r = pm.evaluate_run(REF, constants=C, overrides={"kc11": kc11, "mc": mc, "kappa_r": kap})
        rows.append({"kc11": kc11, "mc": mc, "kappa_r": kap, "force_mean_N": r["force_mean_N"],
                     "force_max_N": r["force_max_N"], "power_max_kW": r["power_max_kW"],
                     "power_torque_max_abs_diff_kW": r["power_torque_max_abs_diff_kW"]})
    return rows


def taylor_sweep(C, threshold, speeds_at_v_ref=False):
    """Per tool: parts per edge and first trigger part over the (n, T_ref) grid of its key."""
    base = pm.evaluate_run(REF, constants=C, overrides={"speeds_at_v_ref": speeds_at_v_ref})
    keys = {c["tool_id"]: c["taylor"]["key"] for c in base["cuts"]}
    out = {}
    for tool_id, key in keys.items():
        sw = C["taylor"]["steel_1045"][key]["sweep"]
        vals = []
        for n, tref in itertools.product(sw["n"], sw["T_ref_min"]):
            r = pm.evaluate_run(REF, constants=C, overrides={
                "speeds_at_v_ref": speeds_at_v_ref, "taylor": {key: {"n": n, "T_ref_min": tref}}})
            c = r["per_tool"][tool_id]["consumption_per_part"]
            vals.append({"n": n, "T_ref_min": tref, "consumption_per_part": c,
                         "parts_per_edge": 1.0 / c, "trigger_part": pm.first_trigger_part(c, threshold)})
        out[tool_id] = {"key": key, "grid": vals,
                        "parts_per_edge_range": [min(v["parts_per_edge"] for v in vals),
                                                 max(v["parts_per_edge"] for v in vals)],
                        "trigger_part_range": [min(v["trigger_part"] for v in vals),
                                               max(v["trigger_part"] for v in vals)],
                        "max_single_part_consumption": max(v["consumption_per_part"] for v in vals)}
    return out


def feedback_checks(C, threshold, plan, sweep):
    """Mechanism checks of the feedback path, each in a fresh temporary store."""
    tmp = tempfile.mkdtemp(prefix="r1_8_store_")
    checks = {}
    try:
        # (a) Reference part, nominal constants and every swept setting: no request.
        base = pm.evaluate_run(REF, constants=C)
        store = pm.ExpertValidationStore(os.path.join(tmp, "a.json"))
        raised = pm.tool_life_feedback(base, plan, store, threshold, parts_done=0)
        sweep_single_part_requests = sum(
            1 for t in sweep.values() for v in t["grid"] if v["consumption_per_part"] >= threshold)
        checks["single_part_no_request"] = {"nominal_requests": len(raised),
                                            "swept_settings_that_would_request": sweep_single_part_requests,
                                            "swept_settings": sum(len(t["grid"]) for t in sweep.values())}

        # (b) Batch: the first request falls exactly on the analytic trigger part,
        # for the nominal constants (full loop) and for every swept setting
        # (checked at the part before and at the trigger part).
        nominal = {}
        store = pm.ExpertValidationStore(os.path.join(tmp, "b.json"))
        first = {}
        kmax = max(pm.first_trigger_part(t["consumption_per_part"], threshold)
                   for t in base["per_tool"].values())
        for k in range(1, kmax + 1):
            for row in pm.tool_life_feedback(base, plan, store, threshold, parts_done=k - 1):
                first.setdefault(row["tool_id"], k)
        for tool_id, t in base["per_tool"].items():
            nominal[tool_id] = {"analytic_trigger_part": pm.first_trigger_part(t["consumption_per_part"], threshold),
                                "observed_first_request_part": first.get(tool_id)}
        mismatches = 0
        evaluated = 0
        for tool_id, t in sweep.items():
            for v in t["grid"]:
                k = v["trigger_part"]
                fake = copy.deepcopy(base)
                fake["per_tool"] = {tool_id: dict(base["per_tool"][tool_id],
                                                  consumption_per_part=v["consumption_per_part"])}
                s = pm.ExpertValidationStore(os.path.join(tmp, f"sw_{tool_id}_{evaluated}.json"))
                before = pm.tool_life_feedback(fake, plan, s, threshold, parts_done=k - 2) if k >= 2 else []
                at = pm.tool_life_feedback(fake, plan, s, threshold, parts_done=k - 1)
                evaluated += 1
                if before or not at:
                    mismatches += 1
        checks["batch_trigger"] = {"nominal": nominal, "swept_settings": evaluated,
                                   "early_or_missed_triggers": mismatches}

        # (c) A recorded resolution is honoured on a later run and not duplicated.
        path = os.path.join(tmp, "c.json")
        tool = min(base["per_tool"], key=lambda t: base["per_tool"][t]["parts_per_edge"])
        k = nominal[tool]["analytic_trigger_part"]
        s1 = pm.ExpertValidationStore(path)
        rows = pm.tool_life_feedback(base, plan, s1, threshold, parts_done=k - 1)
        rid = [r["request_id"] for r in rows if r["tool_id"] == tool]
        for r in rid:
            s1.apply_feedback(r, "expert_approved", "edge indexed before this part")
        s1.save()
        n_before = len(s1.all_requests())
        s2 = pm.ExpertValidationStore(path)  # a later run reloads the persisted store
        rows2 = pm.tool_life_feedback(base, plan, s2, threshold, parts_done=k - 1)
        checks["resolution_reused"] = {
            "tool": tool, "requests": len(rid),
            "same_ids_on_rerun": sorted(r["request_id"] for r in rows2 if r["tool_id"] == tool) == sorted(rid),
            "statuses_on_rerun": sorted({r["status"] for r in rows2 if r["tool_id"] == tool}),
            "duplicates_created": len(s2.all_requests()) - n_before}

        # (d) No defaults: a material without Taylor constants raises missing_knowledge.
        alu_plan = json.load(open(os.path.join(ALU, "manufacturing_plan.json"), encoding="utf-8"))
        alu = pm.evaluate_run(ALU, material="aluminum_6061", constants=C)
        s3 = pm.ExpertValidationStore(os.path.join(tmp, "d.json"))
        rows3 = pm.tool_life_feedback(alu, alu_plan, s3, threshold, parts_done=0)
        checks["missing_constants"] = {
            "serialised_steps": len(alu["cuts"]),
            "tool_life_unavailable_steps": sum(1 for c in alu["cuts"] if c["taylor"]["model"] == "unavailable"),
            "requests_by_reason": {r: sum(1 for x in rows3 if x["reason"] == r) for r in {x["reason"] for x in rows3}},
            "force_available_steps": sum(1 for c in alu["cuts"] if c["force_power"]["model"] != "unavailable")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return checks


def main():
    C = pm.load_constants()
    threshold = C["feedback"]["life_fraction_threshold"]
    plan = json.load(open(os.path.join(REF, "manufacturing_plan.json"), encoding="utf-8"))
    nominal = pm.evaluate_run(REF, constants=C)
    legacy = legacy_channels(REF)
    ks = kienzle_sweep(C)
    ts = taylor_sweep(C, threshold)
    hb = pm.evaluate_run(REF, constants=C, overrides={"speeds_at_v_ref": True})
    ts_hb = taylor_sweep(C, threshold, speeds_at_v_ref=True)
    fb = feedback_checks(C, threshold, plan, ts)

    per_cut = []
    for c in nominal["cuts"]:
        fp = c["force_power"]
        per_cut.append({
            "step": c["step_number"], "operation": c["operation"], "tool": c["tool_id"],
            "tool_material": c["tool_material"], "h_mm": fp["h_mm"], "b_mm": fp["b_mm"],
            "kc_N_per_mm2": fp["kc_N_per_mm2"], "Fc_kienzle_N": fp["Fc_per_edge_N"],
            "Fc_constant_kc_N": legacy["constant_kc_force_by_step"].get(c["step_number"]),
            "power_kW": fp["power_kW"], "vc_m_per_min": fp["vc_m_per_min"],
            "v_over_v_ref": c["taylor"]["speed_ratio"], "taylor_life_min": c["taylor"]["life_min"],
            "in_cut_s": c["in_cut_s"], "consumption": c["taylor"]["consumption"]})

    res = {
        "constants_status": C["_status"],
        "threshold": threshold,
        "time_base": {"estimator_cutting_time_s": nominal["estimator_total"]["cutting_time_seconds"],
                      "sum_in_cut_s": nominal["sum_in_cut_s"],
                      "note": "estimator time includes G83 peck retracts; tool life is consumed only in cut"},
        "per_cut": per_cut,
        "per_tool_nominal": nominal["per_tool"],
        "force_nominal": {"mean_N": nominal["force_mean_N"], "max_N": nominal["force_max_N"],
                          "power_max_kW": nominal["power_max_kW"],
                          "power_vs_torque_max_abs_diff_kW": nominal["power_torque_max_abs_diff_kW"]},
        "force_sweep": {"settings": len(ks),
                        "mean_N_range": [min(r["force_mean_N"] for r in ks), max(r["force_mean_N"] for r in ks)],
                        "max_N_range": [min(r["force_max_N"] for r in ks), max(r["force_max_N"] for r in ks)],
                        "power_max_kW_range": [min(r["power_max_kW"] for r in ks), max(r["power_max_kW"] for r in ks)],
                        "power_vs_torque_max_abs_diff_kW": max(r["power_torque_max_abs_diff_kW"] for r in ks)},
        "legacy": legacy,
        "taylor_sweep_reference_speeds": ts,
        "handbook_speed_scenario": {"per_tool_nominal": hb["per_tool"], "sweep": ts_hb},
        "feedback": fb,
    }
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r1_8_process_models.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    write_summary(res)
    return res


def write_summary(r):
    L = ["# R1-8: corrected force and tool-life models, and the tool-life feedback path", "",
         "Constants are nominal and uncalibrated (see process_constants.json); every conclusion below is "
         "checked over the declared sweep ranges.", "",
         f"Time base: the programme's cycle-time estimator gives {r['time_base']['estimator_cutting_time_s']:.2f} s "
         f"of cutting; the in-cut time attributed to the nine segments is {r['time_base']['sum_in_cut_s']:.2f} s "
         "(the difference is G83 peck retracts).", "",
         "| Step | Operation | Tool (material) | h (mm) | kc (N/mm2) | Fc Kienzle (N) | Fc constant kc (N) | P (kW) | v/v_ref | T (min) | t in cut (s) | life used |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in r["per_cut"]:
        L.append(f"| {c['step']} | {c['operation']} | {c['tool']} ({c['tool_material']}) | {c['h_mm']:.3f} | "
                 f"{c['kc_N_per_mm2']:.0f} | {c['Fc_kienzle_N']:.0f} | {c['Fc_constant_kc_N']:.0f} | "
                 f"{c['power_kW']:.3f} | {c['v_over_v_ref']:.2f} | {c['taylor_life_min']:.1f} | "
                 f"{c['in_cut_s']:.2f} | {c['consumption']:.5f} |")
    L += ["", "| Tool | Life used per part (nominal) | Parts per edge (nominal) | Parts per edge (sweep) | "
          "First request at part (nominal) | (sweep) | Legacy wear model |", "|---|---|---|---|---|---|---|"]
    fbn = r["feedback"]["batch_trigger"]["nominal"]
    for t, v in r["per_tool_nominal"].items():
        sw = r["taylor_sweep_reference_speeds"][t]
        lg = r["legacy"]["legacy_wear"].get(t, {})
        L.append(f"| {t} | {v['consumption_per_part']:.5f} | {v['parts_per_edge']:.0f} | "
                 f"{sw['parts_per_edge_range'][0]:.0f} to {sw['parts_per_edge_range'][1]:.0f} | "
                 f"{fbn[t]['analytic_trigger_part']} (observed {fbn[t]['observed_first_request_part']}) | "
                 f"{sw['trigger_part_range'][0]} to {sw['trigger_part_range'][1]} | "
                 f"{lg.get('wear_percentage')} % on a {lg.get('wear_model_cutting_time_min')} min clock |")
    hb = r["handbook_speed_scenario"]
    L += ["", "Handbook-speed scenario (every cut at the lower handbook speed of its tool, in-cut time scaled accordingly):", "",
          "| Tool | Life used per part | Parts per edge | Parts per edge (sweep) |", "|---|---|---|---|"]
    for t, v in hb["per_tool_nominal"].items():
        sw = hb["sweep"][t]
        L.append(f"| {t} | {v['consumption_per_part']:.4f} | {v['parts_per_edge']:.0f} | "
                 f"{sw['parts_per_edge_range'][0]:.0f} to {sw['parts_per_edge_range'][1]:.0f} |")
    f = r["force_nominal"]; fs = r["force_sweep"]
    L += ["", f"Force (nominal): mean {f['mean_N']:.0f} N, max {f['max_N']:.0f} N; max power {f['power_max_kW']:.3f} kW; "
          f"|P - M omega| <= {f['power_vs_torque_max_abs_diff_kW']:.1e} kW. Constant-kc model of the reference run: "
          f"mean {r['legacy']['constant_kc_mean_force_N']:.0f} N.",
          f"Force sweep ({fs['settings']} settings): mean {fs['mean_N_range'][0]:.0f} to {fs['mean_N_range'][1]:.0f} N, "
          f"max {fs['max_N_range'][0]:.0f} to {fs['max_N_range'][1]:.0f} N, max power "
          f"{fs['power_max_kW_range'][0]:.2f} to {fs['power_max_kW_range'][1]:.2f} kW.", "",
          "Feedback path:", "", "```", json.dumps(r["feedback"], indent=1), "```"]
    with open(os.path.join(RESULTS, "r1_8_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r1_8_summary.md"), encoding="utf-8").read())

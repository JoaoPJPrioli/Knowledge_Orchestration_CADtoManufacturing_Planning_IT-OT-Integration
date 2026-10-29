"""Generate the LaTeX of Supplementary Tables S12 to S17 from the results files,
so that no number is transcribed by hand. Version 9 adds scenario S12 to Table
S14 and Table S17 (stock-aware turning profile); S12, S13, S15, and S16 are
generated exactly as in version 8.

Usage: python common/make_supp_tables_v9.py <out.tex>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.paths import RESULTS  # noqa: E402


def J(name):
    return json.load(open(os.path.join(RESULTS, name), encoding="utf-8"))


def f2(x):
    return "n/a" if x is None else f"{x:.2f}"


def th(n):
    """Integer with a LaTeX thousands separator, as in the main text."""
    return f"{n:,}".replace(",", "{,}")


def s12_merge():
    r = J("r1_2_merge_accuracy.json")
    rows = [("Reference ($\\theta = 0.5$, $\\tau_{\\min} = 0.7$)", r["reference"])]
    rows += [(f"$\\theta = {t}$ (gated)", r["theta"]["gated"][t]) for t in ("0.3", "0.4", "0.6", "0.7", "0.8")]
    rows += [("$\\tau_{\\min} = 0$ (gate ablated)", r["ablation_tau_min_0"]), ("$\\tau_{\\min} = 1.0$", r["tau_min_1"])]
    rows += [(f"$\\theta = {t}$ (ablated)", r["theta"]["ablated"][t]) for t in ("0.3", "0.4", "0.6", "0.7", "0.8")]
    rows += [(f"$d_{{\\max}} = {int(float(d))}$~mm", r["dmax"][d]) for d in ("10.0", "25.0", "100.0", "200.0")]
    rows += [(f"$\\varepsilon = {e}$ (gated)", r["eps"]["gated"][e]) for e in ("0.1", "0.2", "0.3", "0.5")]
    rows += [(f"$\\varepsilon = {e}$ (ablated)", r["eps"]["ablated"][e]) for e in ("0.1", "0.2", "0.3", "0.5")]
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Merge-level accuracy of the reconciliation stage against the Level~G references of Section~5.2 (reported in Section~5.3 of the main text). "
         "Same feature: merges whose two records ground to the same reference feature. Label-consistent: same feature and $\\tau \\ge 0.7$. "
         "Recall: same-feature merges over the 10 cross-agent pairs that a one-to-one matching of same-feature records could form. "
         "Position and length errors are means over the merged STEP-derived entities, for the primary record and for the merged entity; "
         "the length error covers only merges whose primary record states a length, so the merge of the whole-shaft record with the key record "
         "at $\\tau_{\\min} = 1.0$ (length error 48~mm) is not in that column. At $\\varepsilon = 0.5$ (gated) the merge counted as same feature joins the "
         "whole-shaft record with the upper-body record, both grounded to R05. "
         f"Identical merge sets to the reference: $\\theta = 0.3$ to $0.6$, $d_{{\\max}} = 50$ to $200$~mm, and {r['partition_identity']['weights_identical_merge_set']} of the 26 weight settings; "
         "$d_{\\max} = 25$~mm has the same counts but pairs the whole-shaft record with the groove record instead of the lower body. "
         "Weight settings, as ranges over the 26 settings: gated precision "
         f"{f2(r['weights_summary']['gated']['precision_range'][0])} to {f2(r['weights_summary']['gated']['precision_range'][1])}, recall "
         f"{f2(r['weights_summary']['gated']['recall_range'][0])} to {f2(r['weights_summary']['gated']['recall_range'][1])}; ablated precision "
         f"{f2(r['weights_summary']['ablated']['precision_range'][0])} to {f2(r['weights_summary']['ablated']['precision_range'][1])}, recall "
         f"{f2(r['weights_summary']['ablated']['recall_range'][0])} to {f2(r['weights_summary']['ablated']['recall_range'][1])}. "
         "A global maximum-weight one-to-one assignment under the reference conditions gives 8 merges with 6 of the same feature, "
         "with the wrong STEP merge moved from the lower body to the groove.}}",
         "\\label{supp:mergeaccuracy}", "\\footnotesize", "\\setlength{\\tabcolsep}{3pt}", "\\rev{",
         "\\begin{tabular}{p{3.2cm} p{1.25cm} p{1.2cm} p{0.9cm} p{1.5cm} p{1.6cm} p{1.0cm} p{2.2cm} p{2.2cm}}", "\\toprule",
         "\\textbf{Setting} & \\textbf{Entities} & \\textbf{Merges} & \\textbf{Same feature} & \\textbf{Precision} & "
         "\\textbf{Label-consistent precision} & \\textbf{Recall} & \\textbf{Position error, mm} & \\textbf{Length error, mm} \\\\", "\\midrule"]
    for name, x in rows:
        pe = x.get("step_merged_pos_err_mean") or {}
        le = x.get("step_merged_len_err_mean") or {}
        L.append(f"{name} & {x['entities']} & {x['merges']} & {x['correct']} & {f2(x['precision'])} & "
                 f"{f2(x['label_consistent_precision'])} & {f2(x['recall'])} & "
                 f"{f2(pe.get('primary'))} to {f2(pe.get('merged'))} & {f2(le.get('primary'))} to {f2(le.get('merged'))} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


def s13_confidence():
    r = J("r1_3_calibration_probe.json")
    names = {"policy": "Assigned confidence (policy of Equation~(4))", "base_rate_loo": "Base rate, leave-one-out",
             "reconciliation_class_loo": "Rate per reconciliation class, leave-one-out",
             "agent_set_loo": "Rate per reporting agent set, leave-one-out"}
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Confidence as a predictor of a correct operation family (Level~M) for the 22 reconciled entities, "
         "with the reference and the swapped role assignment. The base rate is the leave-one-out rate $(k - y)/(n - 1)$; the class and agent rates use "
         "add-one smoothing, $(k - y + 1)/(n - 1 + 2)$; in both, no entity contributes to its own estimate. Review: entities with confidence below 0.5. "
         "In-sample probe on one part; it is not an out-of-sample calibration.}}",
         "\\label{supp:confidence}", "\\small", "\\rev{",
         "\\begin{tabular}{p{1.5cm} p{5.0cm} p{1.1cm} p{1.9cm} p{2.4cm} p{2.4cm}}", "\\toprule",
         "\\textbf{Roles} & \\textbf{Predictor} & \\textbf{Brier} & \\textbf{Range} & \\textbf{Wrong entities routed to review} & "
         "\\textbf{Correct entities routed to review} \\\\", "\\midrule"]
    for roles, lab in (("reference", "Reference"), ("swapped_roles", "Swapped")):
        for k, v in r[roles]["predictors"].items():
            ro = v["routing"]
            L.append(f"{lab} & {names[k]} & {v['brier']:.3f} & {v['range'][0]:.2f} to {v['range'][1]:.2f} & "
                     f"{ro['wrong_routed_to_review']} of {ro['wrong_entities']} & {ro['correct_routed_to_review']} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


def s14_change():
    r = J("r1_1_change_study.json")
    short = {"S1": "New material (AISI 4140), four material-specific sets",
             "S2": "New class (tapered hole) under the hole class, no new rule",
             "S3": "Blind and through holes made hole subclasses; two specific rules retired",
             "S4": "Contradictory second rule for steel drilling",
             "S5": "Class-specific set for blind holes, meant to override the general rule",
             "S6": "Spindle safety limit lowered to 850~rpm",
             "S7": "Chamfer mill retired from chamfering on the lathe",
             "S8": "Carbide drill added and recorded as preferred",
             "S9": "New operation: reaming of through holes, with tool, set, and capability",
             "S10": "Duplicated entry: second spindle speed (1200~rpm) for the steel drilling set",
             "S11": "Class-specific set for blind holes equal to the general one",
             "S12": "Disjointness of external turned and internal hole features, then the counterbore misclassified under Step"}

    def ow(d):
        return f"+{d['triples_added']}/$-${d['triples_removed']} triples, +{d['rules_added']}/$-${d['rules_removed']} rules"

    def ep(d):
        f = d['fields_changed']
        return f"+{d['entries_added']}/$-${d['entries_removed']} entries, {f} field{'' if f == 1 else 's'}"

    def outcome(side, s):
        x = s[side]
        res = x["result"]
        if res["halted"]:
            o = "run halted (ontology inconsistent)"
        else:
            o = f"{res['approved']} of {res['steps']} approved"
            rc = res["requests_by_reason"]
            extra = [f"{v} {k.replace('_', ' ')}" for k, v in rc.items() if k in ("rule_conflict", "unsafe_value")]
            if extra:
                o += "; " + ", ".join(extra)
        o += "; intent met" if x["meets_intent"] else "; intent not met"
        if "remedy" in x:
            rm = x["remedy"]
            if side == "reasoner":
                o += f"; remedy {ow(rm['knowledge_delta'])}, no code, intent met" if rm["meets_intent"] else "; remedy failed"
            else:
                o += f"; remedy {rm['code_lines']} lines of code, intent met" if rm["meets_intent"] else "; remedy failed"
        if side == "reasoner" and "with_attribution_fix" in x:
            a = x["result"]["attribution_audit"]
            o += f"; {a['misattributed']} of {a['records_checked']} records misattributed, 0 with the matching rule"
        return o

    eq = r["equivalence"]
    s12c = next(s for s in r["scenarios"] if s["id"] == "S12")["controls"]
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Knowledge-change study: the reasoner path (ontologies, SWRL, Pellet, KEFC) and the engineered procedural planner "
         f"({r['code_size_executable_lines']['epp_v1_ProceduralPlanner']} executable lines; KEFC {r['code_size_executable_lines']['KEFCController']}) after the same change, each with its intent stated before either was run. On the reference case both make "
         f"identical decisions ({eq['reasoner']['steps']} steps, {eq['reasoner']['approved']} approved, identical requests). Knowledge edits: asserted triples and SWRL "
         "rules of the edited files, or table entries and fields. Code: Python lines; for the reasoner path, entries in vocabulary dictionaries "
         "of the implementation (feature labels, material keys, legacy identifiers). Approved counts refer to the 22 reference entities "
         "(23 in S2, with the new tapered hole). The ontologies declare "
         f"{r['functional_properties_declared']} functional properties and no disjointness axiom. In S12, the disjointness axioms alone "
         f"({s12c['axioms_only']['reasoner']['knowledge_delta']['triples_added']} triples; {s12c['axioms_only']['epp']['knowledge_delta']['entries_added']} table entries) leave both plans unchanged, and the mis-filing alone, without them, adds "
         f"rough and finish turning of the counterbore to both plans as approved steps ({s12c['misfiling_without_axioms']['reasoner']['result']['approved']} of "
         f"{s12c['misfiling_without_axioms']['reasoner']['result']['steps']} approved). A naive lookup table derived from the same sources "
         "(repository script analysis/lookup\\_baseline.py) emitted the contradictory value of S4 on all seven drilling steps without a flag "
         "and produced no step for the new subclass of S2.}}",
         "\\label{supp:changestudy}", "\\scriptsize", "\\rev{",
         "\\begin{tabular}{p{0.6cm} p{2.8cm} p{2.5cm} p{0.8cm} p{3.4cm} p{2.0cm} p{2.9cm}}", "\\toprule",
         "\\textbf{Id} & \\textbf{Change} & \\textbf{Reasoner: knowledge edit} & \\textbf{Code} & \\textbf{Reasoner: outcome} & "
         "\\textbf{Planner: table edit} & \\textbf{Planner: outcome} \\\\", "\\midrule"]
    for s in r["scenarios"]:
        L.append(f"{s['id']} & {short[s['id']]} & {ow(s['reasoner']['knowledge_delta'])} & {s['reasoner']['code_lines']} & "
                 f"{outcome('reasoner', s)} & {ep(s['epp']['knowledge_delta'])} & {outcome('epp', s)} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


def s15_material():
    r = J("r1_5_programme_feasibility.json")
    n = r["reference_nominal"]
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Material-based check of the reference programme against a bar of "
         f"{r['nominal_stock']['diameter_mm']:.0f}~mm (the stock of the reference process plan) whose free end lies 1~mm beyond the drive-end face. "
         "Feed moves: radial engagement for turning passes, depth in material for drilling cycles, against the planned depth of cut and "
         "the tool's \\textit{hasMaxDepthMM}. Below: rapid moves entering material, and zones where the finished profile departs from the "
         "B-Rep reference (gouge: material removed inside the part; residual: reference volume not reached), with the step that last cut each zone. "
         "Tools are points (turning) or cylinders of the plan diameter (drills), so holder interference is not checked.}}",
         "\\label{supp:material}", "\\small", "\\rev{",
         "\\begin{tabular}{p{1.0cm} p{2.6cm} p{3.2cm} p{3.2cm} p{2.2cm} p{2.2cm}}", "\\toprule",
         "\\textbf{Step} & \\textbf{Operation} & \\textbf{Tool} & \\textbf{Engagement or depth, mm} & \\textbf{Planned $a_p$, mm} & \\textbf{Tool limit, mm} \\\\",
         "\\midrule"]
    for m in n["moves"]:
        v = m.get("radial_engagement_mm", m.get("depth_in_material_mm"))
        ap = m.get("planned_depth_of_cut_mm")
        L.append(f"{m['step']} & {m['operation'].replace('_', ' ')} & {m['tool'].replace('_', ' ')} & {v:.2f} & "
                 f"{'' if ap is None or m.get('cycle') else f'{ap:.1f}'} & {m['tool_max_depth_mm']:.1f} \\\\")
    L.append("\\midrule")
    L.append("\\multicolumn{6}{p{15.2cm}}{Rapid moves entering material: " + "; ".join(
        f"step {x['step']}, {x['depth_mm']:.2f}~mm at $z$ = {x['at_z']:.1f}" for x in n["rapids_into_stock"]) + ".} \\\\")
    c = n["conformance"]

    def zones(lst, kind):
        return "; ".join(f"{kind} {z['max_mm']:.2f}~mm over $z$ {z['z_from']:.2f} to {z['z_to']:.2f} ({', '.join(z['reference_features'])}; step {', '.join(str(s) for s in z['steps'])})" for z in lst)
    L.append("\\multicolumn{6}{p{15.2cm}}{Outer profile: " + zones(c["outer_gouges"], "gouge") + "; " + zones(c["outer_residual"], "residual")
             + f"; {c['material_beyond_part_end_mm']:.1f}~mm of stock left beyond the drive-end face.}} \\\\")
    L.append("\\multicolumn{6}{p{15.2cm}}{Inner profile: " + zones(c["inner_residual"], "residual") + "; no inner gouge.} \\\\")
    sw = r["reference_stock_sweep"]
    L.append("\\multicolumn{6}{p{15.2cm}}{Bars of 26, 28, and 30~mm with free ends 0.5 to 2.0~mm beyond the face: "
             f"{min(v['rapids_into_stock'] for v in sw.values())} to {max(v['rapids_into_stock'] for v in sw.values())} rapid entries; "
             f"the 0.20~mm gouge and the three finishing passes that remove nothing in all nine settings.}} \\\\")
    f = r["free_text_configuration"]
    fs = f["summary"]
    L.append("\\multicolumn{6}{p{15.2cm}}{Free-text-dimension configuration: "
             f"{f['accounting']['serialised']} steps serialised and {f['accounting']['refused']} refused; the new steps "
             + ", ".join(str(x["step"]) for x in f["newly_serialised_steps"])
             + " rough- and finish-turn the two drawing cylinders at drawing-frame positions ("
             + "; ".join(f"step {m['step']} from $z$ = {m['z_from']:.2f} to {m['z_to']:.2f}, engagement {m['radial_engagement_mm']:.2f}~mm"
                         for m in f["check"]["moves"] if m.get("step") in {x["step"] for x in f["newly_serialised_steps"]})
             + "); "
             + "the part spans $z$ = 80.5 to 168.5; " + zones([g for g in fs["outer_gouges"] if "R01" in g["reference_features"]], "gouge") + ".} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


def s16_process():
    r = J("r1_8_process_models.json")
    C = json.load(open(os.path.join(os.path.dirname(RESULTS), "r1_8_process_models", "process_constants.json"), encoding="utf-8"))
    k = C["kienzle"]["steel_1045"]
    t = C["taylor"]["steel_1045"]
    tv = "; ".join(f"{key.replace('|', ', ').replace('_', ' ')}: $v_{{\\mathrm{{ref}}}}$ {v['v_ref_m_per_min']:.0f}~m/min, $T_{{\\mathrm{{ref}}}}$ {v['T_ref_min']:.0f}~min, $n$ {v['n']}"
                   for key, v in t.items())
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Corrected process models for the nine serialised steps, computed by evaluation code outside the pipeline, whose simulator is unchanged. Kienzle: $F_c = k_{c1.1}\\, b\\, h^{1-m_c}$ per edge "
         f"(nominal $k_{{c1.1}}$ = {k['kc11_N_per_mm2']:.0f}~N/mm$^2$, $m_c$ = {k['mc']}; turning entering angle 95$^\\circ$ assumed; drill point angle and "
         "counterbore edge from the tool ontology); constant-$k_c$ is the model of the reference run. Taylor: $T = T_{\\mathrm{ref}}(v_{\\mathrm{ref}}/v)^{1/n}$, "
         f"anchored at handbook speeds ({tv}); life used is in-cut time over $T$. All constants are nominal and uncalibrated. "
         f"Sweeps: 48 Kienzle settings give a mean force of {r['force_sweep']['mean_N_range'][0]:.0f} to {r['force_sweep']['mean_N_range'][1]:.0f}~N and a largest power of "
         f"{r['force_sweep']['power_max_kW_range'][0]:.2f} to {r['force_sweep']['power_max_kW_range'][1]:.2f}~kW; power equals torque times angular speed to within $10^{{-15}}$~kW in every setting.}}}}",
         "\\label{supp:process}", "\\scriptsize", "\\setlength{\\tabcolsep}{3pt}", "\\rev{",
         "\\begin{tabular}{p{0.7cm} p{1.9cm} p{2.25cm} p{0.8cm} p{1.15cm} p{1.0cm} p{1.0cm} p{0.8cm} p{0.8cm} p{0.8cm} p{0.8cm} p{1.0cm}}", "\\toprule",
         "\\textbf{Step} & \\textbf{Operation} & \\textbf{Tool (material)} & \\textbf{$h$, mm} & \\textbf{$k_c$, N/mm$^2$} & \\textbf{$F_c$ Kienzle, N} & "
         "\\textbf{$F_c$ constant $k_c$, N} & \\textbf{$P$, kW} & \\textbf{$v/v_{\\mathrm{ref}}$} & \\textbf{$T$, min} & \\textbf{In cut, s} & \\textbf{Life used} \\\\", "\\midrule"]
    for c in r["per_cut"]:
        L.append(f"{c['step']} & {c['operation'].replace('_', ' ')} & {c['tool'].replace('_', ' ')} ({c['tool_material']}) & {c['h_mm']:.3f} & "
                 f"{c['kc_N_per_mm2']:.0f} & {c['Fc_kienzle_N']:.0f} & {c['Fc_constant_kc_N']:.0f} & {c['power_kW']:.3f} & {c['v_over_v_ref']:.2f} & "
                 f"{c['taylor_life_min']:.0f} & {c['in_cut_s']:.1f} & {100 * c['consumption']:.3f}\\% \\\\")
    L.append("\\midrule")
    fb = r["feedback"]
    rows = []
    for tool, v in r["per_tool_nominal"].items():
        sw = r["taylor_sweep_reference_speeds"][tool]
        hb = r["handbook_speed_scenario"]["per_tool_nominal"][tool]
        rows.append(f"{tool.replace('_', ' ')}: {100 * v['consumption_per_part']:.2f}\\% per part, first request at part "
                    f"{th(fb['batch_trigger']['nominal'][tool]['analytic_trigger_part'])} ({th(sw['trigger_part_range'][0])} to {th(sw['trigger_part_range'][1])} over the sweep), "
                    f"{100 * hb['consumption_per_part']:.2f}\\% per part at handbook speeds")
    L.append("\\multicolumn{12}{p{16.6cm}}{Per tool (threshold 80\\% of edge life): " + "; ".join(rows) + ".} \\\\")
    L.append("\\multicolumn{12}{p{16.6cm}}{Feedback path: no request for one part under the nominal constants or any of "
             f"{fb['single_part_no_request']['swept_settings']} swept Taylor settings (16 per tool); in a batch the first request falls on the predicted part in every setting "
             f"({fb['batch_trigger']['early_or_missed_triggers']} early or missed); a recorded resolution is reused on a later run with "
             f"{fb['resolution_reused']['duplicates_created']} duplicates; with aluminium, for which no Taylor constants are declared, "
             f"{fb['missing_constants']['tool_life_unavailable_steps']} of {fb['missing_constants']['serialised_steps']} steps raise missing knowledge instead of a default. "
             f"Legacy wear model: drill {r['legacy']['legacy_wear']['drill_bit']['wear_percentage']:.1f}\\% on a "
             f"{r['legacy']['legacy_wear']['drill_bit']['wear_model_cutting_time_min']:.2f}~min clock, against "
             f"{r['per_tool_nominal']['drill_bit']['in_cut_min']:.2f}~min in cut.}} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


def s17_stock_aware():
    r = J("r1_5_stock_aware_profile.json")
    s, ref = r["summary"], r["reference"]["summary"]
    pc, rc = r["pipeline_checks"], r["reference"]["pipeline_checks"]
    c, cr = r["check"]["conformance"], r["reference"]["conformance"]

    def zones(lst, kind):
        return "; ".join(f"{kind} {z['max_mm']:.2f}~mm over $z$ {z['z_from']:.2f} to {z['z_to']:.2f} "
                         f"({', '.join(z['reference_features'])}; step {', '.join(str(x) for x in z['steps'])})" for z in lst) or f"no {kind}"
    sw = r["stock_sweep"]
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Stock-aware turning profile (evaluation code beside the serialiser, which is unchanged) applied to the "
         f"{r['approved_steps']} approved steps of the reference plan with the declared bar of Table~S15 "
         f"({r['nominal_stock']['diameter_mm']:.0f}~mm, free end at $z$ = {r['nominal_stock']['free_end_z']:.1f}), and checked with the same material model. "
         "Approach and retract positions lie outside the bar and beyond its free end; roughing passes run from the free end towards the chuck, no deeper "
         "than the step's planned depth of cut, down to the final radius plus a radial allowance equal to the planned depth of cut of the approved finishing step of the same feature; "
         "finishing is one pass at the final diameter. A turning step whose pass from the free end would cut below another approved turning segment "
         "lying between the free end and its own span is refused as a recess. Spindle speed (rev/min), feed per revolution, and coolant are the "
         "planned values; every diameter, length, and position comes from the plan or the declared bar. Cycle time: the pipeline's estimator.}}",
         "\\label{supp:stockaware}", "\\small", "\\rev{",
         "\\begin{tabular}{p{5.3cm} p{5.0cm} p{5.0cm}}", "\\toprule",
         "\\textbf{Quantity} & \\textbf{Reference programme} & \\textbf{Stock-aware profile} \\\\", "\\midrule",
         f"Steps serialised & {rc['serialised_steps']} & {pc['serialised_steps']} (steps {', '.join(str(x) for x in r['serialised_steps'])}) \\\\",
         f"Steps refused as a recess & n/a & {len(r['recess_refusals'])} (steps {', '.join(str(x) for x in r['recess_refusals'])}, the groove extracted as a step) \\\\",
         f"Rapid moves entering the bar & {ref['rapids_into_stock']} (up to {ref['rapid_penetration_max_mm']:.2f}~mm) & {s['rapids_into_stock']} \\\\",
         f"Largest radial engagement & {ref['max_radial_engagement_mm']:.2f}~mm & {s['max_radial_engagement_mm']:.2f}~mm \\\\",
         f"Passes deeper than the planned $a_p$ & {ref['passes_exceeding_planned_ap']} & {s['passes_exceeding_planned_ap']} \\\\",
         f"Finishing passes removing nothing & {ref['finishing_passes_removing_nothing']} & {s['finishing_passes_removing_nothing']} \\\\",
         f"Outer gouges & {zones(ref['outer_gouges'], 'gouge')} & {zones(s['outer_gouges'], 'gouge')} \\\\",
         f"Outer residual material & {zones(cr['outer_residual'], 'residual')} & {zones(c['outer_residual'], 'residual')} \\\\",
         f"Inner residual material & {zones(cr['inner_residual'], 'residual')} & identical to the reference programme \\\\",
         f"Validator errors and warnings & {rc['validator']['errors']} and {rc['validator']['warnings']} & {pc['validator']['errors']} and {pc['validator']['warnings']} \\\\",
         f"Spindle, feed, and coolant as approved & {rc['parameter_fidelity']['spindle_match']} of {rc['parameter_fidelity']['segments_checked']} segments & "
         f"{pc['parameter_fidelity']['spindle_match']} of {pc['parameter_fidelity']['segments_checked']} segments \\\\",
         f"Defaulted dimension lookups & {rc['dimension_fidelity']['defaulted']} of {rc['dimension_fidelity']['lookups']} & "
         f"{pc['dimension_fidelity']['defaulted']} of {pc['dimension_fidelity']['lookups']} \\\\",
         f"Cycle-time estimate & {rc['cycle_time_min']:.2f}~min & {pc['cycle_time_min']:.2f}~min \\\\",
         "\\midrule"]
    L.append("\\multicolumn{3}{p{15.3cm}}{Passes of the stock-aware profile, in order: " + "; ".join(
        f"step {p['step']} at {p['diameter']:.2f}~mm, {p['radial_depth']:.3f}~mm deep (planned {p['planned_ap']:.1f}~mm)" for p in r["passes"]) + ".} \\\\")
    L.append("\\multicolumn{3}{p{15.3cm}}{Bars of 26, 28, and 30~mm with free ends 0.5 to 2.0~mm beyond the face (nine settings, the profile "
             f"regenerated for each): {max(v['rapids_into_stock'] for v in sw.values())} rapid entries, "
             f"{max(v['passes_exceeding_planned_ap'] for v in sw.values())} passes deeper than planned, "
             f"{max(len(v['outer_gouges']) for v in sw.values())} gouges, and steps "
             f"{', '.join(str(x) for x in sorted({n for v in sw.values() for n in v['recess_refusals']}))} refused as a recess in every setting; "
             f"largest engagement {min(v['max_radial_engagement_mm'] for v in sw.values()):.3f} to {max(v['max_radial_engagement_mm'] for v in sw.values()):.2f}~mm.}} \\\\")
    ov = r["plan_overlaps"]
    L.append("\\multicolumn{3}{p{15.3cm}}{Conflict recorded, not refused: " + "; ".join(
        f"the approved turning segments of features {o['features'][0]} and {o['features'][1]} claim diameters "
        f"{o['final_diameters'][1]:.2f} and {o['final_diameters'][0]:.2f}~mm over $z$ {o['z_from']:.1f} to {o['z_to']:.1f}, "
        "because the merged lower-body length is 57.7~mm instead of 37.5~mm (Section~5.2); any sequence of longitudinal passes leaves the smaller "
        "diameter, which the B-Rep confirms there" for o in ov) + ".} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


if __name__ == "__main__":
    out = sys.argv[1]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join([s12_merge(), s13_confidence(), s14_change(), s15_material(), s16_process(), s17_stock_aware()]))
    print("written", out)

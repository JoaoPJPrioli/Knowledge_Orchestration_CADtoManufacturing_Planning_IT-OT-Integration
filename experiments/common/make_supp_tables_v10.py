"""Generate the LaTeX of Supplementary Tables S12 to S20 from the results files.

Tables S12 to S17 are produced exactly as in version 9 (make_supp_tables_v9.py);
version 10 adds S18 (merge-criterion checks, R2-3), S19 (cross-modal identity
probe, R2-2), and S20 (reasoning ablation, R1-7).

Usage: python common/make_supp_tables_v10.py <out.tex>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import make_supp_tables_v9 as v9  # noqa: E402

J, f2 = v9.J, v9.f2


def s18_merge_checks():
    r = J("r2_3_merge_checks.json")
    g, a = r["gated"], r["ablated_type_gate"]
    rows = [("Reference criterion ($\\tau \\ge 0.7$, $S > \\theta$)", g["reference"]),
            ("C, structured fields only", g["C[structured]"]),
            ("C", g["C[free_text]"]),
            ("E, $\\varepsilon = 0.1$, $0.2$, or $0.3$ (no C)", g["E0.1[free_text]"]),
            ("E, $\\varepsilon = 0.5$ (no C)", g["E0.5[free_text]"]),
            ("C and E, $\\varepsilon = 0.1$, $0.2$, or $0.3$", g["C+E0.1[free_text]"]),
            ("C and E, $\\varepsilon = 0.5$", g["C+E0.5[free_text]"]),
            ("C and T, class f, m, or c", g["C+Tm[free_text]"]),
            ("C and T, class v", g["C+Tv[free_text]"]),
            ("T, class m (no C)", g["Tm[free_text]"]),
            ("Type gate ablated: reference", a["reference"]),
            ("Type gate ablated: C and E, $\\varepsilon = 0.1$ to $0.3$", a["C+E0.1[free_text]"]),
            ("Type gate ablated: C and E, $\\varepsilon = 0.5$", a["C+E0.5[free_text]"]),
            ("Type gate ablated: C and T, class m", a["C+Tm[free_text]"])]
    # rows that summarise several settings must agree on every reported value
    for name, keys in (("E 0.1-0.3", ("E0.1[free_text]", "E0.2[free_text]", "E0.3[free_text]")),
                       ("C+E 0.1-0.3", ("C+E0.1[free_text]", "C+E0.2[free_text]", "C+E0.3[free_text]")),
                       ("C+T f-c", ("C+Tf[free_text]", "C+Tm[free_text]", "C+Tc[free_text]"))):
        vals = [(g[k]["entities"], g[k]["merges"], g[k]["correct"], g[k]["precision"], g[k]["recall"]) for k in keys]
        assert len(set(vals)) == 1, (name, vals)
    vals = {(a[k]["entities"], a[k]["merges"], a[k]["correct"], a[k]["cross_family_merges"])
            for k in ("C+E0.1[free_text]", "C+E0.2[free_text]", "C+E0.3[free_text]")}
    assert len(vals) == 1, vals

    def err(x, key):
        v = (x.get(key) or {}).get("merged")
        return "n/a" if v is None else f"{v:.2f}"
    s = r["discrepancy_true_pairs"]["summary"]
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Completeness, dimensional-consistency, and engineering-tolerance conditions added to the merge criterion "
         "(reported in Section~5.3 of the main text). C: the two records state at least one common dimension (diameter from the diameter "
         "or twice the radius, length, width). E: every common dimension agrees within a relative difference $\\varepsilon$. T: for every "
         "common dimension, the two values differ by no more than the permissible deviation of ISO 2768-1 for the class, with the larger "
         "value as the nominal size; the drawing states no tolerance, so the class is an assumption. Unless marked, the conditions read the dimensions that the drawing records state in their free text "
         "(no value is guessed); the merge score is unchanged. Precision and recall as in Table~S12; the errors are the mean position and "
         "length errors of the merged STEP-derived entities (n/a: no merged entity of that kind).}}",
         "\\label{supp:mergechecks}", "\\footnotesize", "\\setlength{\\tabcolsep}{3pt}", "\\rev{",
         "\\begin{tabular}{p{4.7cm} p{1.3cm} p{1.15cm} p{1.0cm} p{1.1cm} p{1.5cm} p{1.0cm} p{1.3cm} p{1.3cm}}", "\\toprule",
         "\\textbf{Setting} & \\textbf{Entities} & \\textbf{Merges} & \\textbf{Same feature} & \\textbf{Cross-family} & "
         "\\textbf{Precision} & \\textbf{Recall} & \\textbf{Position error, mm} & \\textbf{Length error, mm} \\\\", "\\midrule"]
    for name, x in rows:
        L.append(f"{name} & {x['entities']} & {x['merges']} & {x['correct']} & {x['cross_family_merges']} & {f2(x['precision'])} & "
                 f"{f2(x['recall'])} & {err(x, 'step_merged_pos_err_mean')} & {err(x, 'step_merged_len_err_mean')} \\\\")
    L.append("\\midrule")
    diffs = [x for x in r["discrepancy_true_pairs"]["rows"] if x["difference"] > 1e-9]
    L.append("\\multicolumn{9}{p{15.8cm}}{Agreement between the agents on the "
             f"{s['common_dimensions_of_true_pairs']} common dimensions of record pairs that ground to the same reference feature: "
             f"{s['identical']} identical; the other {s['different']} differ by "
             + "; ".join(f"{x['difference']:g}~mm ({x['ref']}, {'diameter' if x['dimension'] == 'D' else 'length' if x['dimension'] == 'L' else 'width'} "
                         f"{x['values'][0]:g} against {x['values'][1]:g})" for x in diffs)
             + f". Within the tolerance of class f, m, or c: {s['different_within_tolerance']['m']} of these {s['different']}; class v: "
               f"{s['different_within_tolerance']['v']}.}} \\\\")
    fus = {x["policy"]: x for x in r["fusion"]}
    L.append("\\multicolumn{9}{p{15.8cm}}{Attribute fusion of the reference merges, mean position and length errors of the merged STEP "
             f"entities: weighted average, as implemented, {fus['average']['step_merged_pos_err_mean']['merged']:.2f} and "
             f"{fus['average']['step_merged_len_err_mean']['merged']:.2f}~mm; primary value kept, "
             f"{fus['primary']['step_merged_pos_err_mean']['merged']:.2f} and {fus['primary']['step_merged_len_err_mean']['merged']:.2f}~mm; "
             "weighted average only where the two values agree within the tolerance of class f, m, c, or v, otherwise the primary value: "
             f"{fus['tolerance:v']['step_merged_pos_err_mean']['merged']:.2f} and {fus['tolerance:v']['step_merged_len_err_mean']['merged']:.2f}~mm "
             "in every class.} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


def s19_cross_modal():
    r = J("r2_2_cross_modal_identity.json")
    d = r["declared"]
    step = r["step_entities_stated"]

    def dims(x):
        names = {"D": "\\varnothing", "L": "L", "W": "W"}
        return ", ".join(f"${names[k]}$ {v:g}" for k, v in sorted(x.items()))
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Frame-free identity probe between drawing-family and STEP-family entities (reported in Section~5.2 of the main "
         "text). A link requires an admissible type ($\\tau \\ge \\tau_{\\min}$, the pipeline's type tiers), at least one common stated "
         "dimension (drawing dimensions read from free text), and agreement within a relative difference $\\varepsilon$ on every common "
         "dimension; admissible pairs are linked one to one by maximum-weight matching. The setting declared in advance is "
         "$\\tau_{\\min} = 0.7$ and $\\varepsilon = 0.1$. Truth: the feature of the physical reference to which the Level~M audit grounds "
         "each entity. Removed steps: approved steps of linked drawing entities, all of which duplicate a STEP-family feature.}}",
         "\\label{supp:crossmodal}", "\\footnotesize", "\\rev{",
         "\\begin{tabular}{p{4.4cm} p{4.4cm} p{0.9cm} p{1.6cm} p{3.2cm}}", "\\toprule",
         "\\textbf{Drawing entity (stated)} & \\textbf{Linked STEP entity (stated)} & \\textbf{$\\tau$} & \\textbf{Largest rel. difference} & "
         "\\textbf{Physical features (correct?)} \\\\", "\\midrule"]
    ents = {u["id"]: u for u in d["unlinked_drawing_entities"]}
    drw = r["drawing_entities_stated"]
    for l in d["link_list"]:
        s, w = step[str(l["step"])], drw[str(l["drawing"])]
        L.append(f"{l['drawing']} {w[0]} ({dims(w[1])}) & {l['step']} {s[0]} ({dims(s[1])}) & {l['tau']:.1f} & {max(l['relative_differences']):.3f} & "
                 f"{l['phys'][0]}, {l['phys'][1]} ({'yes' if l['correct'] else 'no'}) \\\\")
    for i, u in sorted(ents.items()):
        L.append(f"{i} {u['type']} ({dims(u['stated'])}) & not linked & & & {u['phys']} \\\\")
    L.append("\\midrule")
    L.append(f"\\multicolumn{{5}}{{p{{16.0cm}}}}{{Declared setting: {d['links']} links, {d['correct_links']} correct (precision "
             f"{f2(d['precision'])}); {d['correct_links']} of {d['max_true_links']} possible same-feature pairs (recall {f2(d['recall'])}); "
             f"{len(d['duplicated_approved_steps_removed'])} of the {len(d['duplicated_approved_steps'])} duplicated approved steps removed, "
             f"{len(d['steps_removed_by_wrong_links'])} of them through a wrong link.}} \\\\")
    sw = [x for x in r["sweep"] if x["links"]]
    best = max(sw, key=lambda x: (x["precision"], x["recall"]))
    rec = [x for x in sw if x["correct_links"] == max(y["correct_links"] for y in sw)]
    L.append("\\multicolumn{5}{p{15.8cm}}{Sweep of $\\tau_{\\min}$ (0.7, 0.3, 0), completeness (required or not), and $\\varepsilon$ "
             f"(0.05 to 0.5, or none), {len(r['sweep'])} settings: highest precision {f2(best['precision'])} at recall "
             f"{f2(best['recall'])} ($\\tau_{{\\min}} = {best['tau_min']:g}$, $\\varepsilon = {best['eps']:g}$); the settings that recover "
             f"{rec[0]['correct_links']} pairs (recall {f2(rec[0]['recall'])}) form {rec[0]['links']} links, "
             f"{rec[0]['links'] - rec[0]['correct_links']} of them wrong. At $\\tau_{{\\min}} = 0.7$ and $\\varepsilon = 0.3$ the two "
             "bodies are linked crosswise (upper to lower and lower to upper).} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


def s20_reasoning():
    r = J("r1_7_reasoning_ablation.json")
    names = {"reference": "Reference (all rules, Pellet)",
             "reasoner_off": "Pellet not run (no SWRL inference, no classification)",
             "no_feature_operation_rules": f"Feature-to-operation rules removed ({r['rule_counts']['feature_operation']})",
             "no_parameter_rules": f"Parameter rules removed ({r['rule_counts']['parameter']})",
             "no_tool_rule": f"Operation-to-tool rule removed ({r['rule_counts']['tool']})"}

    def reqs(v):
        return "; ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(v["requests_by_reason"].items()))
    L = ["\\begin{table}[p]", "\\centering",
         "\\caption{\\rev{Reasoning ablation on the 22 reference entities (reported in Section~5.6 of the main text), run with the "
         "reasoner-path harness of Table~S14 (CFRM, Pellet, and KEFC on an edited copy of the knowledge; the repository is unchanged). "
         "Requests are KEFC requests; RAL receives no approved step in any ablated variant. The asserted \\textit{hasPreferredTool} remains in "
         "every variant but ranks only tools that the operation-to-tool rule has made eligible.}}",
         "\\label{supp:reasoning}", "\\small", "\\setlength{\\tabcolsep}{4pt}", "\\rev{",
         "\\begin{tabular}{p{4.8cm} p{1.0cm} p{1.7cm} p{1.5cm} p{1.2cm} p{4.6cm}}", "\\toprule",
         "\\textbf{Variant} & \\textbf{Steps} & \\textbf{Approved} & \\textbf{With parameters} & \\textbf{With tool} & \\textbf{KEFC requests} \\\\",
         "\\midrule"]
    for k, v in r["variants"].items():
        L.append(f"{names[k]} & {v['steps']} & {v['approved']} & {v['steps_with_parameters']} & {v['steps_with_tool']} & {reqs(v)} \\\\")
    L += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(L)


if __name__ == "__main__":
    out = sys.argv[1]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join([v9.s12_merge(), v9.s13_confidence(), v9.s14_change(), v9.s15_material(), v9.s16_process(),
                            v9.s17_stock_aware(), s18_merge_checks(), s19_cross_modal(), s20_reasoning()]))
    print("written", out)

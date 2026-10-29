"""Generate the LaTeX table fragments of the ground-truth audit from results_v2.json.
Usage (repository root):
    python ground_truth/make_tables_v2.py ground_truth/results_v2.json ground_truth/step_reference_v2.json \
        ground_truth/drawing_reference_v2.json <out.tex>
"""
import json, sys

res = json.load(open(sys.argv[1], encoding="utf-8"))
sref = {f["ref_id"]: f for f in json.load(open(sys.argv[2]))["features"]}
dref = {f["ref_id"]: f for f in json.load(open(sys.argv[3], encoding="utf-8"))["features"]}
R1 = res["R1_convention_corrected_reference"]; T = res["two_level"]
AG = ["features_eixo_step_Gemini31Pro.txt", "features_eixo_step_Gemini35flash.txt",
      "draw_features_eixo_Gemini31Pro.txt", "draw_features_eixo_Gemini35flash.txt"]
SHORT = {AG[0]: "STEP-A", AG[1]: "STEP-B", AG[2]: "DRW-A", AG[3]: "DRW-B"}
PHYS = {"P01": "lower body", "P02": "0.5 chamfer", "P03": "groove", "P04": "15$^\\circ$ chamfer", "P05": "upper body",
        "P06": "end chamfer", "P07a": "tap-drill hole", "P07b": "counterbore", "P07c": "countersink", "P07d": "M8 thread", "P08": "keyway"}
OPN = {"rough_turning": "rough turning", "finish_turning": "finish turning"}
def f2(x): return f"{x:.2f}"
def tex(s): return s.replace("_", "\\_")
L = []
def table(label, caption, colspec, head, rows, size="\\small", sep=None):
    out = ["\\begin{table}[htbp]", "\\centering", f"\\caption{{\\rev{{{caption}}}}}", f"\\label{{{label}}}", size]
    if sep: out.append(f"\\setlength{{\\tabcolsep}}{{{sep}}}")
    out += ["\\rev{", f"\\begin{{tabular}}{{{colspec}}}", "\\toprule", head + " \\\\", "\\midrule"]
    out += rows
    out += ["\\bottomrule", "\\end{tabular}}", "\\end{table}", ""]
    return "\n".join(out)

# ---------------- Table 2: reference ----------------
k = sref["R06"]
rows = ["R01 & Step & $\\varnothing$24.95 $\\times$ 37.5 & $z$ 80.5 to 118.0 \\\\",
"R02 & Chamfer & 0.5 $\\times$ 45$^\\circ$, $\\varnothing$24.95 to 23.95 & $z$ 118.0 to 118.5 \\\\",
"R03 & Groove & $\\varnothing$23.6 $\\times$ 1.754 & $z$ 118.5 to 120.254 \\\\",
"R04 & Chamfer & 15$^\\circ$ taper, $\\varnothing$23.6 to 24.0 & $z$ 120.254 to 121.0 \\\\",
"R05 & Step & $\\varnothing$24.0 $\\times$ 46.5 & $z$ 121.0 to 167.5 \\\\",
"R06 & Key & 8 wide, 40 long, 3 high; full-radius ends R4 (faces 22; 4 and 20), flanks $x = \\pm 4$ (faces 21, 23), top plane $y = 15$ (face 24) & $z$ 123.5 to 163.5, on $+y$; end-radius axes along $y$ through $(0, 15, 127.5)$ and $(0, 15, 159.5)$ \\\\",
"R07 & Blind hole & $\\varnothing$6.8 $\\times$ 19.0, drill point 2.04 & $z$ 143.5 to 162.5 \\\\",
"R08 & Counterbore & $\\varnothing$8.4 $\\times$ 2.709 & $z$ 162.5 to 165.209 \\\\",
"R09 & Chamfer (countersink) & 60$^\\circ$, $\\varnothing$12.2 to 8.4 & $z$ 165.209 to 168.5 \\\\",
"R10 & Chamfer & 1.0 $\\times$ 45$^\\circ$, $\\varnothing$24.0 to 22.0 & $z$ 167.5 to 168.5 \\\\",
"\\addlinespace",
"D01 & Step & $\\varnothing$24 $\\times$ 46.5 & upper body, carries the key \\\\",
"D02 & Step & $\\varnothing$24 $\\times$ 37.5 & lower body; length dimensioned, diameter drawn at 24.93 but not dimensioned \\\\",
"D03 & Groove & width 1.75 & diameter not dimensioned \\\\",
"D04 & Key & 8 wide (end radius R4), 40 long (32 between end-radius centres), 3 high (3.69 above the chord) & ends 5~mm from the free end \\\\",
"D05a & Hole & R3.4 ($\\varnothing$6.8) & innermost bore section \\\\",
"D05b & Counterbore & R4.2 ($\\varnothing$8.4) & middle bore section \\\\",
"D05c & Chamfer & R6.1 ($\\varnothing$12.2) & entry bore section \\\\",
"D06 & Chamfer & 1 $\\times$ 45$^\\circ$, $\\varnothing$24 to 22 & free end; end face R11 in the end view \\\\"]
L.append("% ---- replaces Table 2 (tab:reference) ----")
L.append(table("tab:reference", "Reference features derived from the B-Rep of the STEP model (R01 to R10; exact values in the STEP frame, $z$ along the part axis, face indices in kernel order) and read from the drawing (D01 to D06; dimensions as written on the drawing, no coordinate frame).",
  "p{0.9cm} p{2.0cm} p{5.6cm} p{4.6cm}", "\\textbf{Id} & \\textbf{Type} & \\textbf{Geometry} & \\textbf{Position (STEP) or note}", rows))

# ---------------- Table 3: accuracy ----------------
A1 = {f: R1["per_agent"][f] for f in AG}; G = {f: T["per_agent"][f] for f in AG}
def cells(fn): return " & ".join(fn(f) for f in AG)
def mm(s): return "n/a" if not s else f"{s['mean']:.2f} ({s['max']:.2f})"
dimL = {AG[0]: f"{mm(G[AG[0]]['length_error_mm'])}, $n = {G[AG[0]]['length_error_mm']['n']}$",
        AG[1]: f"{mm(G[AG[1]]['length_error_mm'])}, $n = {G[AG[1]]['length_error_mm']['n']}$",
        AG[2]: "1 record (key: 4 for 8 wide, 32 for 40 long)",
        AG[3]: "2 records (key: 3.69 for 8 wide, 32 for 40 long; slot: 4 for 8)"}
dimD = {AG[0]: f"{mm(G[AG[0]]['diameter_error_mm'])}, $n = {G[AG[0]]['diameter_error_mm']['n']}$",
        AG[1]: f"{mm(G[AG[1]]['diameter_error_mm'])}, $n = {G[AG[1]]['diameter_error_mm']['n']}$",
        AG[2]: "0 stated errors", AG[3]: "1 record (22 for 24)"}
rows = ["\\multicolumn{5}{l}{\\textit{R1 convention, corrected drawing reference}} \\\\",
 "Records reported & " + cells(lambda f: str(A1[f]["records"])) + " \\\\",
 "Records denoting a real feature & " + cells(lambda f: str(A1[f]["denote_real_feature"])) + " \\\\",
 "Precision & " + cells(lambda f: f2(A1[f]["precision"])) + " \\\\",
 "Reference features found & " + cells(lambda f: f"{A1[f]['reference_found']} of {A1[f]['reference_features']}") + " \\\\",
 "Type exact / related / wrong & " + cells(lambda f: f"{A1[f]['type_exact']} / {A1[f]['type_related_other_operation']} / {A1[f]['type_wrong']}") + " \\\\",
 "\\addlinespace", "\\multicolumn{5}{l}{\\textit{Level G, geometric grounding}} \\\\",
 "Records grounded (precision) & " + cells(lambda f: f"{G[f]['G_grounded']} ({f2(G[f]['G_precision'])})") + " \\\\",
 "Label exact / same family / other family & " + cells(lambda f: f"{G[f]['G_tier_exact']} / {G[f]['G_tier_same_family']} / {G[f]['G_tier_other_family']}") + " \\\\",
 "Reference features found & " + cells(lambda f: f"{G[f]['G_reference_found']} of {G[f]['G_reference_features']}") + " \\\\",
 "Position error to nearest anchor, mean (max), mm & " + cells(lambda f: mm(G[f].get("pos_error_anchor_mm"))) + " \\\\",
 "Position error to feature centre, mean (max), mm & " + cells(lambda f: mm(G[f].get("pos_error_centre_mm"))) + " \\\\",
 "Diameter error, mean (max), mm & " + cells(lambda f: dimD[f]) + " \\\\",
 "Length or width error, mean (max), mm & " + cells(lambda f: dimL[f]) + " \\\\",
 "\\addlinespace", "\\multicolumn{5}{l}{\\textit{Level M, operation family for the physical shaft}} \\\\",
 "Correct / wrong family / no such feature & " + cells(lambda f: f"{G[f]['M_correct_family']} / {G[f]['M_wrong_family']} / {G[f]['M_no_such_feature']}") + " \\\\",
 "Precision & " + cells(lambda f: f2(G[f]["M_precision"])) + " \\\\",
 "Physical features covered in the correct family & " + cells(lambda f: G[f]["M_physical_recall"].split(" (")[0]) + " \\\\"]
L.append("% ---- replaces Table 3 (tab:accuracy) ----")
L.append(table("tab:accuracy", "Extraction accuracy of the four agents under three conventions. R1 convention: a record denotes a real feature when it matches a reference feature of Table~\\ref{tab:reference} under the R1 matching rule; type is exact, related (right feature, different operation family) or wrong. Level G: a STEP record is grounded when it lies within 10~mm of an anchor of a B-Rep feature (key end-radius axes included) with its stated diameter within 10\\,\\%; drawing records are grounded on dimensioned values; labels are scored with the type-similarity tiers of Equation~\\ref{eq:merge_criterion}. Level M: the label's operation family is compared with the family the physical feature requires (Table~\\ref{tab:physref}). Positional errors are available for STEP-derived records only.",
  "p{4.1cm} p{2.3cm} p{2.3cm} p{2.3cm} p{2.6cm}",
  "\\textbf{Measure} & \\textbf{STEP-A (primary)} & \\textbf{STEP-B (secondary)} & \\textbf{DRW-A (primary)} & \\textbf{DRW-B (secondary)}", rows, size="\\scriptsize"))

# ---------------- Physical reference (new) ----------------
rows = ["P01 & lower body $\\varnothing$24.95 $\\times$ 37.5 & turning & R01 & D02 \\\\",
"P02 & chamfer 0.5 $\\times$ 45$^\\circ$ & chamfering & R02 & none \\\\",
"P03 & relief groove $\\varnothing$23.6 $\\times$ 1.75 & grooving & R03 & D03 \\\\",
"P04 & 15$^\\circ$ transition & chamfering & R04 & none \\\\",
"P05 & upper body $\\varnothing$24 j6 $\\times$ 46.5 & turning & R05 & D01 \\\\",
"P06 & end chamfer 1 $\\times$ 45$^\\circ$ & chamfering & R10 & D06 \\\\",
"P07a & centre hole: tap drill $\\varnothing$6.8 $\\times$ 19, 118$^\\circ$ & drilling & R07 & D05a \\\\",
"P07b & centre hole: counterbore $\\varnothing$8.4 & counterboring & R08 & D05b \\\\",
"P07c & centre hole: countersink 60$^\\circ$ to $\\varnothing$12.2 & chamfering & R09 & D05c \\\\",
"P07d & centre hole: thread M8 & tapping (not in the vocabulary) & none & none \\\\",
"P08 & keyway 8 $\\times$ 4 $\\times$ 40, key fitted afterwards & milling & R06 & D04 \\\\"]
L.append("% ---- NEW table (tab:physref): physical reference for Level M; cite it where Level M is introduced ----")
L.append(table("tab:physref", "Physical reference for operation-family scoring: the IEC 60072-1 frame-90 drive-end shaft extension that the catalogue model depicts with its feather key fitted. Required families use the pipeline's vocabulary.",
  "p{0.9cm} p{5.6cm} p{3.0cm} p{1.2cm} p{1.2cm}", "\\textbf{Id} & \\textbf{Physical feature} & \\textbf{Required family} & \\textbf{B-Rep} & \\textbf{Drawing}", rows))

# ---------------- per-class (new) ----------------
def clsrows(C, tag):
    out = []
    names = {"merged": "Merged", "primary_only": "Primary-only", "secondary_only": "Secondary-only"}
    for c in ("merged", "primary_only", "secondary_only"):
        x = C[c]
        conf = f"$S$ (mean {x['mean_assigned_confidence']:.2f})" if c == "merged" else f"{x['assigned_confidence']}"
        out.append(f"{tag}{names[c]} & {x['entities']} & {conf} & {f2(x['R1_existence_rate'])} & {f2(x['G_grounded_rate'])} & {f2(x['G_grounded_exact_label_rate'])} & {f2(x['M_correct_family_rate'])} \\\\")
    return out
O = T["ordering"]; SO = res["swap_sources"]["two_level"]["ordering"]
def ordrow(O): return " & ".join(O[k]["primary_over_secondary"].replace(" (tied)", ", tied") for k in ("R1_existence_rate", "G_grounded_rate", "G_grounded_exact_label_rate", "M_correct_family_rate"))
rows = ["\\multicolumn{7}{l}{\\textit{Reference run}} \\\\"] + clsrows(T["per_reconciliation_class"], "") + \
       [f"Primary above secondary? & & & {ordrow(O)} \\\\", "\\addlinespace", "\\multicolumn{7}{l}{\\textit{Source roles swapped}} \\\\"] + \
       clsrows(res["swap_sources"]["two_level"]["per_reconciliation_class"], "") + [f"Primary above secondary? & & & {ordrow(SO)} \\\\"]
L.append("% ---- NEW table (tab:classrates): per reconciliation class rates vs assigned confidence ----")
L.append(table("tab:classrates", "Observed rates per reconciliation class against the assigned confidence of Equation~\\ref{eq:conf}. Existence (R1 convention), grounding and exact label (Level G), and correct operation family (Level M) are fractions of the entities in the class. In the swapped run the secondary-model agents act as primary.",
  "p{2.6cm} p{0.5cm} p{1.8cm} p{1.5cm} p{1.4cm} p{1.4cm} p{1.6cm}",
  "\\textbf{Class} & \\textbf{$n$} & \\textbf{Assigned $c$} & \\textbf{Existence (R1)} & \\textbf{Grounded (G)} & \\textbf{Exact label (G)} & \\textbf{Correct family (M)}", rows, size="\\scriptsize"))

# ---------------- Table 7: correctness ----------------
P = T["plan"]
rows = ["\\multicolumn{3}{l}{\\textit{R1 convention, corrected references}} \\\\",
 f"On a real, correctly typed feature & {P['R1_approved']['correct']} & {P['R1_withheld']['correct']} \\\\",
 f"On a real, mistyped feature (operation family differs) & {P['R1_approved']['mistyped']} & {P['R1_withheld']['mistyped']} \\\\",
 f"On a feature the part does not have & {P['R1_approved']['phantom']} & {P['R1_withheld']['phantom']} \\\\",
 "\\addlinespace", "\\multicolumn{3}{l}{\\textit{Level G, geometric grounding}} \\\\",
 f"On a grounded feature, label exact & {P['G_approved']['exact']} & {P['G_withheld']['exact']} \\\\",
 f"On a grounded feature, label same family & {P['G_approved']['same-family']} & {P['G_withheld']['same-family']} \\\\",
 f"On a grounded feature, label other family & {P['G_approved']['other-family']} & {P['G_withheld']['other-family']} \\\\",
 f"On an ungrounded feature & {P['G_not_grounded']['approved']} & {P['G_not_grounded']['withheld']} \\\\",
 "\\addlinespace", "\\multicolumn{3}{l}{\\textit{Level M, operation family for the physical shaft}} \\\\",
 f"Correct operation family & {P['M_approved']['correct family']} & {P['M_withheld']['correct family']} \\\\",
 f"Wrong operation family & {P['M_approved']['wrong family']} & {P['M_withheld']['wrong family']} \\\\",
 f"No such feature & {P['M_approved']['no such feature']} & {P['M_withheld']['no such feature']} \\\\",
 "\\addlinespace",
 f"Total & {P['approved']} & {P['withheld']} \\\\",
 f"Approved steps that duplicate a STEP-family feature from the drawing family & {len(P['approved_duplicates_STEP_family'])} & \\\\",
 "Physical features without an approved step of the correct family & P07d, P08 & \\\\",
 "Parameter records with rule and ontology provenance & 108 of 108 & 20 of 20 \\\\"]
L.append("% ---- replaces Table 7 (tab:correctness) ----")
L.append(table("tab:correctness", "Decision correctness of the 32 planned steps under the three conventions of Table~\\ref{tab:accuracy}. Level M asks whether the step's operation is the family the physical feature requires (Table~\\ref{tab:physref}); auxiliary pilot drilling counts as correct only when the same entity is also counterbored.",
  "p{7.2cm} p{2.4cm} p{2.4cm}", "\\textbf{Steps} & \\textbf{Approved} & \\textbf{Withheld}", rows))

# ---------------- Appendix A.1: records ----------------
def stated(r):
    if r["family"] == "STEP":
        l = r["absolute_location"]; d = r.get("dimensions", {})
        s = f"({l.get('X',0):g}, {l.get('Y',0):g}, {l.get('Z',0):g})"
        parts = []
        if "Ø" in d: parts.append(f"$\\varnothing${d['Ø']:g}")
        if "L" in d: parts.append(f"L {d['L']:g}")
        if "W" in d and "Ø" not in d: parts.append(f"W {d['W']:g}")
        return s + "; " + ", ".join(parts)
    return None
DSTATED = {("DRW-A", 1): "$\\varnothing$24, L 46.5", ("DRW-A", 2): "$\\varnothing$24, L 37.5", ("DRW-A", 3): "width 1.75",
           ("DRW-A", 4): "key 4 wide, 32 long, 3 high", ("DRW-A", 5): "R6.1", ("DRW-A", 6): "R4.2", ("DRW-A", 7): "R3.4",
           ("DRW-B", 1): "$\\varnothing$24, L 37.5", ("DRW-B", 2): "$\\varnothing$22, L 46.5", ("DRW-B", 3): "width 1.75",
           ("DRW-B", 4): "key 32 long, 3.69 wide, 3 high", ("DRW-B", 5): "width 4", ("DRW-B", 6): "R3.4, R4.2, R6.1"}
r1m = {(r["source_file"], r["id"]): r["match"] for r in R1["records"]}
ANC = {"centre": "c", "z_max": "end", "z_min": "end", "key top face": "top", "key centre": "c",
       "key end-radius axis z=127.5": "R4 axis", "key end-radius axis z=159.5": "R4 axis"}
rows = []
for r in T["records"]:
    sh = SHORT[r["source_file"]]
    a = r1m[(r["source_file"], r["id"])]
    r1 = "none" if not a else a["ref_id"] + {0: "", 1: " rel.", 2: " wrong"}[a["type_rank"]]
    g = r["G"]; m = r["M"]
    st = stated(r) or DSTATED[(sh, r["id"])]
    if r["family"] == "STEP":
        gref = f"{g['ref_id']} ({ANC[g['anchor']]})"; d = f"{g['distance_to_anchor']:.2f}"
        dd = "n/a" if g["diameter_error"] is None else f"{g['diameter_error']:g}"
        dl = "n/a" if g["length_error"] is None else f"{g['length_error']:g}"
        err = f"{dd} / {dl}"
    else:
        gref = g["ref_id"] + (" to c" if g["covered"] else ""); d = ""
        e = g["stated_errors"]; err = " / ".join(f"{e[k]:g}" for k in ("diameter", "width", "length") if k in e) or "n/a"
        if g["covered"]: gref = "D05a to c"
    tier = {"exact": "exact", "same-family": "same", "other-family": "other"}[g["tier"]]
    mv = {"correct family": "correct", "wrong family": "wrong", "no such feature": "none"}[m["verdict"]]
    rows.append(f"{sh} & {r['id']} & {r['type']} & {st} & {r1} & {gref} & {d} & {err} & {tier} & {mv} ({PHYS[m['phys_id']]}) \\\\")
L.append("% ---- replaces Appendix A table (tab:records) ----")
L.append(table("tab:records", "Matching outcome for the 30 raw records (A: primary agent, B: secondary agent). R1: match under the R1 convention with the corrected references (rel.: related type). G: grounding feature and anchor (c centre, end axial end, top key top face, R4 axis key end-radius axis), distance $d$ to the anchor, diameter and length errors for STEP records (stated-dimension errors for drawing records), and label tier. M: operation-family verdict and the physical feature of Table~\\ref{tab:physref}.",
  "p{0.85cm} p{0.3cm} p{1.45cm} p{2.9cm} p{0.9cm} p{1.35cm} p{0.55cm} p{1.15cm} p{0.7cm} p{2.0cm}",
  "\\textbf{Source} & \\textbf{Id} & \\textbf{Label} & \\textbf{Stated position and dimensions} & \\textbf{R1} & \\textbf{G match} & \\textbf{$d$, mm} & \\textbf{$\\Delta D$ / $\\Delta L$} & \\textbf{Tier} & \\textbf{M verdict}",
  rows, size="\\scriptsize", sep="2pt"))

# ---------------- Appendix B.2 / B.3: step audit ----------------
def steprows(lo, hi):
    out = []
    for s in T["plan_steps"]:
        if not lo <= s["step"] <= hi: continue
        tool = "F" if s["tool_rule"] == "feature_tool_from_operation" else "P"
        st = "A" if s["approved"] else "W"
        tier = {"exact": "exact", "same-family": "same", "other-family": "other"}[s["G_tier"]]
        mv = {"correct family": "correct", "wrong family": "wrong", "no such feature": "none"}[s["M_verdict"]]
        req = "/".join(s["required"] or [])
        flag = []
        if s["duplicates_STEP_family"]: flag.append("D")
        if s["duplicate_of_entity_same_family"]: flag.append(f"S{s['duplicate_of_entity_same_family']}")
        out.append(f"{s['step']} & {s['entity']} & {s['label']} & {OPN.get(s['operation'], s['operation'])} & {st} & {tool} & {s['R1_verdict']} & {s['G_ref']} {tier} & {mv} ({PHYS[s['phys_id']]}: {req}) & {', '.join(flag)} \\\\")
    return out
cap = "Per-step audit of the reference plan, steps {a} to {b}. Status: A approved, W withheld. Tool: F \\texttt{{feature\\_tool\\_from\\_operation}}, P \\texttt{{preferred\\_tool\\_selection}}; the operation rule is \\texttt{{<label>\\_requires\\_<operation>}} in every row. R1: verdict under the R1 convention (correct, mistyped, phantom). G: grounding feature and label tier. M: operation-family verdict, physical feature and required family. Flags: D the drawing-family entity duplicates a STEP-family feature; S$n$ the physical feature is already described by entity $n$ of the same family."
spec = "p{0.45cm} p{0.55cm} p{1.5cm} p{1.5cm} p{0.4cm} p{0.4cm} p{1.1cm} p{1.4cm} p{3.6cm} p{0.6cm}"
head = "\\textbf{Step} & \\textbf{Entity} & \\textbf{Entity label} & \\textbf{Operation} & \\textbf{St.} & \\textbf{Tool} & \\textbf{R1} & \\textbf{G} & \\textbf{M} & \\textbf{Flags}"
L.append("% ---- replaces Appendix B table (tab:stepaudit) ----")
L.append(table("tab:stepaudit", cap.format(a=1, b=16), spec, head, steprows(1, 16), size="\\scriptsize", sep="2pt"))
L.append("% ---- replaces Appendix B table (tab:stepaudit2) ----")
L.append(table("tab:stepaudit2", cap.format(a=17, b=32), spec, head, steprows(17, 32), size="\\scriptsize", sep="2pt"))
txt = "\n".join(L)
assert "---" not in txt.replace("% ----", "").replace("----", ""), "em dash"
open(sys.argv[4], "w", encoding="utf-8").write(txt)
print("tables written", len(txt))

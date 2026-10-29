"""Supplementary Tables S21 (reference process plan) and S22 (judgements behind it), as LaTeX.

Reads expert_reference_plan.json and the judgement texts of Reference_Plan_SignOff.xlsx (sheet
"Judgements"), normalises notation for typesetting (diameters, angles, file names of the authors'
working folders), and writes the two tables. Requires openpyxl.

Usage (repository root):
    python reference_plan/make_supp_tables_reference_plan.py <out.tex>
"""
import json
import os
import re
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))

# Exact replacements in the judgement texts (each must occur): file names of the authors' working
# folders become the names used in this repository and the manuscript.
JUDGEMENT_EDITS = {
    "J01": [("; resolve the HRC 25 versus UTS 570 MPa inconsistency in `materials.owl`.",
             "; the materials ontology states HRC 25 and UTS 570 MPa, which are mutually inconsistent.")],
    "J05": [("; sequence as in Section 2.", "; sequence as in Table S21.")],
    "J08": [("The 2 mm `GroovingTool`", "The 2 mm GroovingTool of the tools ontology")],
    "J15": [("the `tools.owl` material strings (`parameter_audit.md`).",
             "the material strings of the tools ontology (repository file FILEREF).")],
}
PLAN_EDITS = [("NOT in tools.owl", "not in the tools ontology"), ("NOT in machines.owl", "not in the machines ontology"),
              ("NOT in ontology", "not in the ontology"), ("tools.owl GroovingTool", "the ontology's GroovingTool"),
              ("tools.owl EndMill is a generic 4-flute", "the ontology's EndMill is a generic four-flute tool"),
              ("tailstock not modelled in machines.owl", "tailstock not modelled in the machines ontology")]


def tex(s):
    s = str(s)
    for a, b in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"), ("#", "\\#"), ("_", " ")):
        s = s.replace(a, b)
    s = s.replace("->", "to").replace("<=", "$\\le$").replace(" ~ ", " $\\approx$ ")
    s = re.sub(r"\bd (\d)", r"$\\varnothing$\1", s)            # d 24.95 -> diameter 24.95
    s = re.sub(r"(\d) deg\b", r"\1$^\\circ$", s)                # 60 deg -> 60 degrees
    s = re.sub(r"\bx\b", "$\\\\times$", s)                       # 8 x 4 x 40
    s = re.sub(r"\bz (=|\$\\approx\$) ", r"$z$ \1 ", s)           # axial coordinate
    s = re.sub(r"\bz (\d)", r"$z$ \1", s)
    s = re.sub(r"(\d\.\d+)-(\d+\.\d+)", r"\1--\2", s)            # numeric ranges, not designations such as DIN 332-2
    s = s.replace("/-0.", "/$-$0.")
    s = s.replace("FILEREF", "\\texttt{reference\\_plan/parameter\\_audit.json}")
    return s


def family(f):
    return " or ".join(x.replace("_", " ").replace("setup", "set-up") for x in str(f).split("|"))


def scored(r):
    return {True: "yes", False: "no", "conditional": "conditional", "setup": "set-up element"}.get(r, str(r))


def main(out):
    plan = json.load(open(os.path.join(HERE, "expert_reference_plan.json"), encoding="utf-8"))
    ws = openpyxl.load_workbook(os.path.join(HERE, "Reference_Plan_SignOff.xlsx"))["Judgements"]
    judgements = {}
    for r in ws.iter_rows(values_only=True):
        if r[0] and re.fullmatch(r"J\d\d", str(r[0])) and r[0] != "J00":
            text = str(r[1])
            for a, b in JUDGEMENT_EDITS.get(r[0], []):
                assert text.count(a) == 1, (r[0], a)
                text = text.replace(a, b)
            judgements[r[0]] = text
    assert sorted(judgements) == [f"J{i:02d}" for i in range(1, 18)], sorted(judgements)

    rows = []
    for op in plan["operations"]:
        tool = op["tool"]
        for a, b in PLAN_EDITS:
            tool = tool.replace(a, b)
        machine = op["machine"]
        for a, b in PLAN_EDITS:
            machine = machine.replace(a, b)
        rows.append(" & ".join([op["op_id"], tex(op["setup"]), tex(op["feature"]), family(op["operation_family"]),
                                tex(machine) + "; " + tex(tool), scored(op["required"]),
                                ", ".join(op.get("judgements", []))]) + " \\\\")
    required = sum(1 for op in plan["operations"] if op["required"] is True)
    assert required == 16, required

    t21 = r"""\begin{table}[p]
\centering
\caption{\rev{Reference process plan for the replacement shaft (Section~5.4 of the main text), drafted by the authors from the frame-90 shaft-end geometry and conventional turning practice: %d lines in five set-ups. Scored: one of the 16 required operations whose coverage Table~S8 reports; conditional lines, set-up elements, and unscored lines are not counted. The judgements are listed in Table~S22. CNCLatheFanuc0iTD is the lathe individual of the knowledge base.}}
\label{supp:refplan}
\scriptsize
\setlength{\tabcolsep}{3pt}
\rev{
\begin{tabular}{>{\raggedright\arraybackslash}p{0.85cm} >{\raggedright\arraybackslash}p{0.95cm} >{\raggedright\arraybackslash}p{4.3cm} >{\raggedright\arraybackslash}p{1.8cm} >{\raggedright\arraybackslash}p{4.8cm} >{\raggedright\arraybackslash}p{1.45cm} >{\raggedright\arraybackslash}p{1.05cm}}
\toprule
\textbf{Op} & \textbf{Set-up} & \textbf{Operation and feature} & \textbf{Family} & \textbf{Machine; tool} & \textbf{Scored} & \textbf{Judge\-ments} \\
\midrule
%s
\bottomrule
\end{tabular}}
\end{table}
""" % (len(plan["operations"]), "\n".join(rows))

    jrows = [f"{j} & {tex(t)} \\\\" for j, t in sorted(judgements.items())]
    t22 = r"""\begin{table}[p]
\centering
\caption{\rev{Judgements behind the reference process plan of Table~S21 and the step verdicts of Tables~S4, S5, and S7. Each is open to the independent review for which the repository provides a workbook.}}
\label{supp:judgements}
\small
\rev{
\begin{tabular}{>{\raggedright\arraybackslash}p{0.9cm} >{\raggedright\arraybackslash}p{15.4cm}}
\toprule
\textbf{Id} & \textbf{Judgement} \\
\midrule
%s
\bottomrule
\end{tabular}}
\end{table}
""" % "\n".join(jrows)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(t21 + "\n" + t22)
    print("written", out, len(rows), "plan lines,", len(jrows), "judgements")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])

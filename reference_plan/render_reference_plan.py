"""Render the reference process plan as a readable table (REFERENCE_PLAN.md).

Reads expert_reference_plan.json (written by expertplan_analysis.py) and the judgement texts of
the review workbook (Reference_Plan_SignOff.xlsx, sheet "Judgements"), and writes
REFERENCE_PLAN.md next to this script. Requires openpyxl.

Usage (repository root):
    python reference_plan/render_reference_plan.py
"""
import json
import os

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
plan = json.load(open(os.path.join(HERE, "expert_reference_plan.json"), encoding="utf-8"))
ws = openpyxl.load_workbook(os.path.join(HERE, "Reference_Plan_SignOff.xlsx"))["Judgements"]
judgements = [(r[0], r[1]) for r in ws.iter_rows(values_only=True)
              if r[0] and str(r[0]).startswith("J") and str(r[0])[1:].isdigit() and r[0] != "J00"]


# file names that changed when the authors' working folders were assembled into this repository
RENAMES = {"`parameter_audit.md`": "`parameter_audit.json`",
           "analysis/results/step_reference.json": "pipeline/analysis/results/step_reference.json"}


def cell(x):
    s = str(x).replace("|", "/").replace("\n", " ") if x is not None else ""
    for a, b in RENAMES.items():
        s = s.replace(a, b)
    return s


def scored(op):
    return {True: "yes", False: "no"}.get(op["required"], str(op["required"]))


lines = [
    "# Reference process plan for the replacement shaft",
    "",
    f"Status: {plan['status']}. Part: {plan['part']}. Material: {plan['material']}. Stock: {plan['stock']}.",
    f"Geometry: {cell(plan['geometry_source'])}.",
    "",
    "The plan is scored against the generated plan in comparison.json (manuscript Section 5.4 and Table 7; "
    "Supplementary Table S8). Scored: counted as a required reference operation (conditional operations are "
    "not counted). Every judgement behind the plan is listed below and can be reviewed in "
    "Reference_Plan_SignOff.xlsx.",
    "",
    "| Op | Set-up | Feature | Operation family | Machine | Tool | Scored | Judgements |",
    "|---|---|---|---|---|---|---|---|",
]
for op in plan["operations"]:
    lines.append("| " + " | ".join(cell(x) for x in (op["op_id"], op["setup"], op["feature"], op["operation_family"],
                                                       op["machine"], op["tool"], scored(op),
                                                       ", ".join(op.get("judgements", [])))) + " |")
lines += ["", "## Judgements", ""]
lines += [f"- **{j}.** {cell(t)}" for j, t in judgements]
lines.append("")
open(os.path.join(HERE, "REFERENCE_PLAN.md"), "w", encoding="utf-8").write("\n".join(lines))
print("written REFERENCE_PLAN.md:", len(plan["operations"]), "operations,", len(judgements), "judgements")

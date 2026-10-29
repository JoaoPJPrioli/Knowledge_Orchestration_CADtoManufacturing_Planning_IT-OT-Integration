# Reference process plan

Reference process plan for the replacement shaft, drafted by the authors from the frame-90 shaft-end geometry and conventional turning practice, and its comparison with the generated plan (manuscript Section 5.4; Table 7, lower block; Supplementary Tables S8, S21, and S22). Every judgement behind the plan is listed (J01 to J17) so that it can be checked. The parameter audit compares the stored cutting-parameter sets with candidate cutting-speed ranges; `parameter_audit.json` records the source of each range (a handbook table, a web reproduction of handbook tables, tool-maker data, or a derived band marked weak).

| File | Content |
|---|---|
| `REFERENCE_PLAN.md` | The plan as a readable table, with the judgements (written by `render_reference_plan.py`) |
| `expert_reference_plan.json` | The plan: 22 lines in five set-ups (two on the lathe, one on a milling machine, an optional grinding set-up, and inspection), of which 16 are required operations scored against the generated plan |
| `parameter_audit.json` | The stored cutting-parameter sets compared with handbook ranges for medium-carbon steel at the diameters where they act on this part; the ranges are candidate values to be checked against the cited handbook |
| `comparison.json` | Step-by-step classification of the 32 planned steps against the plan, and the coverage of each reference operation |
| `Reference_Plan_SignOff.xlsx` | Workbook for an independent process planner who is not an author: the physical reference, the plan, the judgements, and the 32 step verdicts, each with a verdict cell |
| `expertplan_analysis.py` | Writes the three JSON files from the knowledge base in `../pipeline/knowledge`, the reference run in `../runs/reference`, and the geometric reference |
| `coverage_summary.py` | Prints the coverage figures of Table 7 (16 required operations; 11 covered by an approved step of the right family, of which 6 are reached by a serialised segment and 4 use a tool the lathe cannot drive; keyway milling only among the withheld steps; 4 missing) |
| `render_reference_plan.py` | Writes `REFERENCE_PLAN.md` |
| `make_supp_tables_reference_plan.py` | Writes Supplementary Tables S21 (the plan) and S22 (the judgements) as LaTeX |

## Reproduction (from the repository root)

```
python reference_plan/expertplan_analysis.py . <out folder>
python reference_plan/coverage_summary.py
python reference_plan/render_reference_plan.py
python reference_plan/make_supp_tables_reference_plan.py <out.tex>
```

A returned review workbook is scored with `python experiments/r1_7_agreement/signoff_agreement.py <workbook> [<second workbook>]`, which reports agreement per sheet and Cohen's kappa on the 32 step verdicts.

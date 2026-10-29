# Experiments added during the review

Evaluation code for the analyses added in response to the reviewers (manuscript Sections 5.2, 5.3, 5.5, 5.6, and 5.7; Supplementary Tables S12 to S20). The code imports the pipeline in `../pipeline` read-only and never modifies it: any change of behaviour that an experiment needs (a disabled mechanism, an edited copy of the knowledge, an alternative serialisation profile) is applied by wrapping or monkeypatching inside the experiment process. Every number that the manuscript and the Supplementary Material report from these experiments is read from the files in `results/`.

## Layout

| Folder | Reviewer request | What it does | Result file |
|---|---|---|---|
| `common/` | | Paths (`paths.py`), a runner that executes `main.py` into `runs/<name>` from a cleared store (`run_pipeline.py`), and the generators of Supplementary Tables S12 to S20 (`make_supp_tables_v10.py`, which reuses `make_supp_tables_v9.py`) | |
| `r1_1_change_study/` | added value of ontology reasoning over rule tables | Engineered procedural planner over tables extracted mechanically from the same rule file and ontologies (rule-identifier logging, multi-valued keys that halt on disagreement, transitive is-a table, every KEFC gate); twelve knowledge changes applied to both planners, each with its intended outcome stated in advance; attribution audit and the tested attribution fix | `results/r1_1_change_study.json` (Table 8; Supplementary Table S14) |
| `r1_2_merge_accuracy/` | reconciliation accuracy; thresholds | Merge-level precision and recall against the geometric references for every sensitivity setting; global one-to-one assignment probe | `results/r1_2_merge_accuracy.json` (Supplementary Table S12) |
| `r1_3_calibration/` | confidence calibration and source ordering | Assigned confidence as a predictor of a correct operation family (Brier score, review routing); leave-one-out class and agent rates; both role assignments | `results/r1_3_calibration_probe.json` (Supplementary Table S13) |
| `r1_5_programme_feasibility/` | machining feasibility of the programme | Material check of the serialised programme against an axisymmetric bar model and the B-Rep reference; configuration that reads the free-text dimensions of the drawing agents; stock-aware turning profile (a subclass of the pipeline's serialiser that is never written back) with the same checks and a stock sweep | `results/r1_5_programme_feasibility.json`, `results/r1_5_stock_aware_profile.json` (Supplementary Tables S15 and S17) |
| `r1_7_reasoning_ablation/` | reasoning ablation | Pellet not run, and each rule category removed (feature-to-operation, parameter, operation-to-tool), on an edited copy of the knowledge | `results/r1_7_reasoning_ablation.json` (Supplementary Table S20) |
| `r1_7_agreement/` | independent review of the reference plan | Agreement and Cohen's kappa between the authors' verdicts and returned review workbooks (blank workbook in `template/`, identical to `../reference_plan/Reference_Plan_SignOff.xlsx`) | |
| `r1_8_process_models/` | corrected force, power, and wear models | Kienzle force and Taylor tool-life consumption on the programme's time base; tool-life feedback through the pipeline's expert-validation store; constants in `process_constants.json` | `results/r1_8_process_models.json` (Supplementary Table S16) |
| `r2_2_cross_modal_identity/` | cross-modal identity resolution | Frame-free links between drawing and STEP entities (admissible type, common stated dimension, relative agreement within a tolerance), one-to-one by maximum-weight matching, scored against the physical reference, with a sweep of 36 settings | `results/r2_2_cross_modal_identity.json` (Supplementary Table S19) |
| `r2_3_merge_checks/` | completeness and dimensional-consistency checks; tolerances | Completeness, consistency, and ISO 2768-1 general-tolerance conditions added to the merge criterion; discrepancy between the agents on every true same-feature pair; attribute-fusion policies | `results/r2_3_merge_checks.json` (Table 5; Supplementary Table S18) |
| `runs/` | | Pipeline runs used by the experiments (`reference`, `material_aluminum`, `free_text_dimensions`) and the programmes of the stock-aware profile | |
| `tests/` | | 64 tests | `results/pytest_experiments.log` |

Each result file has a short companion summary (`results/*_summary.md`).

## Reproduction

Requirements as for the pipeline (see the repository README), plus `openpyxl`. The default layout expects the pipeline at `../pipeline` and the references at `../ground_truth`; override with the environment variables `JIII_REPO` and `JIII_GROUNDTRUTH`. Run from this folder:

```
python common/run_pipeline.py reference
python common/run_pipeline.py material_aluminum --material aluminum_6061
python r1_5_programme_feasibility/free_text_dimensions.py runs/free_text_dimensions
python r1_8_process_models/run_r1_8.py
python r1_1_change_study/run_r1_1.py
python r1_2_merge_accuracy/merge_accuracy.py
python r1_3_calibration/calibration_probe.py
python r1_5_programme_feasibility/run_r1_5.py
python r1_5_programme_feasibility/run_stock_aware.py
python r2_3_merge_checks/merge_checks.py
python r2_2_cross_modal_identity/cross_modal.py
python r1_7_reasoning_ablation/reasoning_ablation.py
python -m pytest -q tests
python common/make_supp_tables_v10.py <out.tex>
```

The folders `runs/reference`, `runs/material_aluminum`, and `runs/free_text_dimensions` must be deleted before these configurations are run again: a run refuses to reuse a folder, so that request counts always come from a cleared store (`run_stock_aware.py` recreates `runs/stock_aware_profile` itself). Timings in `r1_1_change_study.json` depend on the host.

## Notes

* The constants in `r1_8_process_models/process_constants.json` are nominal handbook-order values declared for the experiment, not measurements; the manuscript states that the feedback mechanism behaves as specified but that the tool lives are not validated.
* The attribution fix tested in `r1_1_change_study/run_r1_1.py` (`exact_attribution`, which matches a rule's consequent and antecedent classes) and the stock-aware turning profile are evaluated here and not adopted in `../pipeline`; the manuscript lists both as future work.
* No independent review workbook had been returned when this repository was assembled; `r1_7_agreement/signoff_agreement.py <workbook> [<workbook>]` computes the agreement once one is.

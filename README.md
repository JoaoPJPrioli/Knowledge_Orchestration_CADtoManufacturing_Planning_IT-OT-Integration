# Attributable CAD-to-manufacturing planning: code, data, and results

This repository accompanies the manuscript *An Information and Knowledge Orchestration Framework for CAD-to-Manufacturing Planning in IT-OT Integration*, submitted to the Journal of Industrial Information Integration. It contains the orchestration pipeline in its final implementation, the archived inputs, the outputs of every configuration reported in the manuscript, the evaluation code of every experiment, the derived geometric, drawing, and physical references, and the reference process plan, so that every number in the manuscript and its Supplementary Material can be regenerated and checked.

The repository is anonymised for peer review. Author names, affiliations, and host-specific paths have been removed; absolute paths in archived logs are replaced by placeholders such as `<repository>`.

> **Research artefact.** The serialised programmes (`*.nc`) are research outputs retained for audit. They are not post-processor certified, have not been verified in a CAM environment or on a certified simulator, and must not be loaded into a machine tool.

## Contents

| Folder | Content | Manuscript |
|---|---|---|
| `pipeline/` | Orchestration pipeline (KINM, CFRM, SKL, KEFC, RAL): source code, ontologies, the 36 SWRL rules, the four archived feature-description files, 90 tests, and the analysis scripts of the reconciliation sweeps and the lookup-table baseline | Sections 3 to 5 |
| `runs/` | Outputs of the eight configurations (reference, four ablations, second material, second machine, second machine with the serialisation-profile check disabled), each produced in one invocation from a cleared expert-validation store; the run ledger; the test log; scripts to regenerate and compare | Section 5.1; Tables 6 and 10 |
| `ground_truth/` | Geometric reference derived from the B-Rep, drawing reference, physical reference of the replacement shaft, and the audit of every record, entity, and step against them | Section 4.1; Sections 5.2 and 5.4; Tables 2, 3, and 7 |
| `reference_plan/` | Reference process plan for the replacement shaft and the judgements behind it, parameter audit against handbook-type cutting-speed ranges, comparison with the generated plan, and the workbook for independent review | Section 5.4; Table 7; Supplementary Tables S8, S21, and S22 |
| `experiments/` | Evaluation code of the experiments added during the review (merge-level accuracy, confidence, knowledge-change study with an engineered procedural planner, reasoning ablation, material check and stock-aware profile, process models, merge-criterion conditions, cross-modal identity probe), with 64 tests and the result files | Sections 5.2, 5.3, 5.5, 5.6, and 5.7; Supplementary Tables S12 to S20 |

Each folder has its own README with the commands that regenerate its files.

## Requirements

* Python 3.12 or 3.13, with `pip install -r requirements.txt`.
* OpenJDK 25 as the `java` on the PATH, or the environment variable `SKL_JAVA_EXE` set to a Java 25 executable. The Pellet reasoner bundled with OWLReady2 0.51 requires class-file version 69; under OpenJDK 21 the reasoner fails with `UnsupportedClassVersionError` and the pipeline aborts rather than continuing without inference.
* Optional: `pip install -r requirements-optional.txt`. Its `cadquery-ocp==8.0.1.1` (OpenCASCADE bindings) is needed only by the kernel reference scripts, which also need the third-party STEP model (see below); the pipeline itself uses no geometric kernel.

Tested environments: Ubuntu 24.04 with Python 3.13.18, OpenJDK 25.0.4, OWLReady2 0.51, RDFLib 7.6.0, NetworkX 3.7, NumPy 2.5.3, Matplotlib 3.11.2, pytest 9.1.1, and openpyxl 3.1.5; and Windows with Python 3.12.15 and OpenJDK 25.0.2, on which the archived runs in `runs/` were produced. Run times depend on the host: a configuration takes about 6 s on the Linux host (Pellet about 1.7 s) and 22 to 26 s on the Windows host (Pellet 4 to 5 s).

## Reproducing the results

All commands are run from the repository root unless stated otherwise.

| Step | Command | Regenerates |
|---|---|---|
| 1. Pipeline tests | `cd pipeline && python -m pytest -q tests` | 90 tests, including the fault-injection cases of Table 9 and Supplementary Table S6 |
| 2. Eight configurations | `python runs/run_all_configurations.py <new folder>` | the outputs in `runs/<configuration>/` |
| 3. Comparison with the archive | `python runs/compare_runs.py runs <new folder>` | a per-configuration report of any difference |
| 4. Run ledger | `cd pipeline && python analysis/summarize_runs_v7.py ../runs <out.json> ../runs/pytest_pipeline.log` | `runs/run_ledger.json` (Section 5.1; Tables 6 and 10) |
| 5. Reference audit | `python ground_truth/extraction_accuracy_v2.py pipeline runs/reference ground_truth/step_reference_v2.json ground_truth/drawing_reference_v2.json ground_truth/physical_reference.json <out.json> runs/ablation_swap_sources` | `ground_truth/results_v2.json` (Tables 3 and 7; Supplementary Tables S1, S2, S4, S5, and S7) |
| 6. Reference plan | `python reference_plan/expertplan_analysis.py . <out folder>`, `python reference_plan/coverage_summary.py`, and `python reference_plan/make_supp_tables_reference_plan.py <out.tex>` | `reference_plan/*.json` (Table 7, lower block; Supplementary Tables S8, S21, and S22) |
| 7. Reconciliation sweeps | `python pipeline/analysis/sensitivity.py pipeline <out.json>` and `python pipeline/analysis/dimensional_consistency.py pipeline <out.json>` | `pipeline/analysis/results/` (Table 5; Supplementary Table S11) |
| 8. Lookup-table baseline | `python pipeline/analysis/lookup_baseline.py pipeline runs/reference <out.json>` | the naive-table probes of Section 5.5 |
| 9. Experiments | see `experiments/README.md`; tests with `cd experiments && python -m pytest -q tests` | `experiments/results/` (Supplementary Tables S12 to S20) |
| 10. Kernel reference (optional) | `python ground_truth/step_reference_v2.py <path to eixo.step> pipeline/analysis <out.json>` | `ground_truth/step_reference_v2.json` (Table 2) |

The expert-validation store persists across runs by design, so that a recorded expert resolution can unblock a step later. Request counts therefore match the manuscript only when each configuration runs into a new folder, which `run_all_configurations.py` enforces.

## Verification before release

From a clean copy of this repository on the Linux host listed above:

* the 90 pipeline tests and the 64 experiment tests pass;
* the eight configurations regenerated with `run_all_configurations.py` match the archived runs, which were produced on the Windows host, in every output file except time stamps, the path of the Java executable, output paths, and the key order of JSON embedded in three request strings (`compare_runs.py` reports no difference);
* the run ledger, the reference audit, the reference-plan files, the reconciliation sweeps, the lookup-table baseline (except its timings), every experiment result file (except timings), and Supplementary Tables S12 to S22 regenerate the archived files exactly;
* given the catalogue STEP model, the kernel reference script regenerates `ground_truth/step_reference_v2.json` exactly.

## Inputs and third-party material

The pipeline reads four feature-description files in `pipeline/data/motor_data/`: two produced from the STEP text of the shaft and two from its drawing, each by two Gemini model variants. Because extraction is non-deterministic, these archived files, not the extraction application, are the reproducible input; the feature-extraction application is available separately.

The catalogue STEP model of the shaft (`eixo.step`) and its drawing (`eixo_drawing.pdf`) are third-party material from a motor manufacturer's catalogue and are not redistributed. The references derived from them are included in `ground_truth/`. Neither file is read by the pipeline, its test suite, or the experiments; only the optional kernel reference scripts and the manual benchmark script described below read the STEP model. A copy obtained from the manufacturer can be checked against the MD5 checksums `216a911a03ee8ef522bd20ba37764d07` (`eixo.step`) and `3edfffdcc33d132923056ca9f124cb54` (`eixo_drawing.pdf`). The source will be named in the public release.

`pipeline/src/sparql_generator.py` (language-model drafting of SPARQL queries) and the manual script `pipeline/tests/test_llm_benchmarks.py` are optional components that need an API key; pytest collects no test from that script, and neither component contributes to any reported result. No learned model makes an operation, tool, parameter, or sequencing decision in the pipeline.

## Terminology in the code

Some identifiers predate the final wording of the manuscript. The simulator's `CollisionDetector` reports axis-envelope excursions and tool numbers beyond the turret stations only; its tool-workpiece method is a placeholder that reports nothing, which is why the manuscript reports an absence of axis-envelope violations and avoids the term collision. The material check of Section 5.7 is implemented separately, in `experiments/r1_5_programme_feasibility/`. The modelled machine individual is named after its controller class (`CNCLatheFanuc0iTD`); the serialised programmes are not written in, or verified against, any controller dialect. Internal docstrings refer to the development stages of the code (Revision 1 to Revision 7) and to the code evaluated in the first submission as the initial implementation.

## Licences

Source code (`*.py`) is released under the MIT License (`LICENSE`). Ontologies, rules, input feature descriptions, references, run outputs, results, the review workbook, and documentation are released under the Creative Commons Attribution 4.0 International licence (`LICENSE-DATA`). The Pellet reasoner is part of OWLReady2 and is not redistributed here.

# Orchestration pipeline

Final implementation of the information and knowledge orchestration framework described in the manuscript. The pipeline converts four heterogeneous feature-description files of a motor shaft into a manufacturing-planning package in which every operation, tool, and cutting parameter is attributable to a named SWRL rule and to the ontology sources it used, or is withheld for expert validation with a recorded reason.

The pipeline is knowledge-based. The feature descriptions are produced upstream of the evaluated boundary by language-model extraction agents; inside the pipeline, no learned model makes an operation, tool, parameter, or sequencing decision, and no geometric kernel is used.

## Architecture

| Component | Modules | Role |
|---|---|---|
| KINM, Knowledge and Input Normalisation Module | `src/feature_parser.py`, driven by `main.py` | Parses the four files, preserves source-local identifiers, reconciles records within each source family under the type-gated merge criterion (merge only if the type similarity is at least 0.7 and the score exceeds 0.5), and assigns provenance and the reconciliation confidence |
| CFRM, Contextual Feature-Rule Mapper | `src/semantic_reconciler.py`, `src/kg_builder.py` | Maps each entity to an ontology class and individual, combines the mapping indicator with the reconciliation confidence, and builds the unified application graph |
| SKL, Structured Knowledge Layer | `knowledge/`, `src/skl_repository.py` | Six foundation ontologies (machining processes, materials, tools, machines, cutting parameters, serialisation profiles), the motor-shaft case ontology, a second-machine ontology, and the 36 SWRL rules in `knowledge/rules/machining_rules.swrl`, reasoned with Pellet through OWLReady2; a reasoner failure raises `SKLReasonerError` instead of falling back to defaults |
| KEFC, Knowledge Extension and Feedback Controller | `src/kefc_controller.py`, `src/expert_validation.py` | Owns all gating. A step is withheld when no operation can be inferred, the mapping is unresolved or low-confidence, two rules conflict, a value violates a modelled machine limit, the machine does not declare the operation, the machine cannot present the tool in the required orientation, or the serialisation profile cannot express that orientation. Each case creates a structured expert-validation request |
| RAL, Responsive Application Layer | `src/gcode_generator.py`, `src/ral_refusals.py`, `src/programme_fidelity.py`, `src/dimension_fidelity.py`, `src/validator.py`, `src/simulator.py`, `src/visualizer.py` | Serialises approved steps whose geometry the plan fully specifies, refuses the others with a recorded reason, asserts parameter and dimension fidelity between plan and programme, checks block syntax, modal consistency, and the axis envelope, and estimates the cycle time. It is an auditable serialiser and parameter-handoff interface, not a certified post-processor |
| RDF export and queries | `src/rdf_triplestore.py`, `src/orchestrator.py`, `src/sparql_examples.py` | Materialises the plan, including every parameter record with its rule and sources, as RDF and runs the fixed-order SPARQL suite |

Tool selection is declarative. The SWRL rule `feature_tool_from_operation` makes every tool declared `recommendedForOperation` for the inferred operation eligible; with one eligible tool, the rule decides; with several, the `hasPreferredTool` assertion of the tools ontology decides; with several and no recorded preference, KEFC raises a missing-knowledge request and does not choose. No turret or tool-change optimisation is performed.

## Running

Requirements are listed in the repository README (Python 3.12 or 3.13, `pip install -r requirements.txt`, and OpenJDK 25).

```
python main.py --output-dir <new folder>
```

Options: `--material steel_1045 | aluminum_6061 | stainless_304` (default `steel_1045`), `--machine cnc_lathe | cnc_mill_turn` (default `cnc_lathe`), and `--ablation type_gate | orientation_gate | kefc_gate | swap_sources | serialisation_profile` to disable one mechanism for a controlled comparison. Each configuration must run into a new folder so that the expert-validation store starts empty; `../runs/run_all_configurations.py` runs the eight configurations reported in the manuscript in this way.

A run writes the reconciled entities (`features.json`), the plan with full parameter provenance (`manufacturing_plan.json`, `manufacturing_plan_summary.md`), the expert-validation requests, the reasoning and provenance reports, the application-layer accounting and refusals (`ral_refusals.json`), the fidelity and envelope reports, the serialised research programme (`motor_shaft_1001.nc`) with its validation and simulation reports and toolpath plots, the RDF graph and SPARQL results, the exported knowledge base (asserted facts and rules; inferred facts are reproduced only by running the reasoner), and a summary.

## Tests

```
python -m pytest -q tests
```

The suite has 90 tests, including the fault-injection cases of Table 9 and Supplementary Table S6 (unmapped classes, missing rules, rule conflicts, machine limits, radial features with and without driven tooling, undeclared serialisation profiles, missing dimensions, corrupted artefacts, and reasoner failure). `tests/test_llm_benchmarks.py` is a manual benchmark of the optional language-model SPARQL drafting (`src/sparql_generator.py`, with `src/benchmark_config.py`, `src/benchmark_report.py`, and `src/evaluation_metrics.py`); it needs an API key, pytest collects no test from it, and it contributes to no reported result.

## Analysis scripts

| Script | Purpose | Result |
|---|---|---|
| `analysis/sensitivity.py` | Sweep of the merge-criterion parameters ($\theta$, $\tau_{\min}$, $d_{\max}$, weights), with and without the type gate | `analysis/results/sensitivity.json` (Table 5; Supplementary Table S11) |
| `analysis/dimensional_consistency.py` | Dimensional-consistency condition added to the merge criterion | `analysis/results/dimensional_consistency.json` (Table 5; Supplementary Table S11) |
| `analysis/lookup_baseline.py` | Naive lookup table derived mechanically from the rule file and ontologies, and its three probes | `analysis/results/lookup_baseline.json`, `analysis/results/lookup_table.json` (Section 5.5) |
| `analysis/step_reference.py`, `analysis/step_faces.py` | B-Rep grouping used by the kernel reference (needs OpenCASCADE and the third-party STEP model) | `analysis/results/step_reference.json` |
| `analysis/summarize_runs_v7.py` (with `summarize_runs*.py`) | Run ledger of the eight configurations | `../runs/run_ledger.json` |
| `analysis/serialiser_default_audit.py` | Audit of the placeholder dimensions of the initial implementation's serialiser (defect D16 in Supplementary Table S9); not applicable to the final serialiser, which has no defaults | |

`knowledge/build_ontologies.py` writes the OWL files of `knowledge/` from their Python definitions.

The initial implementation, evaluated in the first submission, differs from this version in the corrections listed in Supplementary Table S9, which also reports the three defects that remain open (none affects a reported figure).

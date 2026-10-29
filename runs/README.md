# Pipeline runs

Outputs of the eight configurations reported in the manuscript (Section 5.1; Tables 6 and 10), each produced by one invocation of `pipeline/main.py` into a new folder, so that every configuration starts from a cleared expert-validation store.

| Folder | Command-line options | Manuscript |
|---|---|---|
| `reference` | none (steel, lathe, all gates) | reference run |
| `ablation_type_gate` | `--ablation type_gate` | type gate disabled ($\tau_{\min} = 0$) |
| `ablation_orientation_gate` | `--ablation orientation_gate` | orientation gate disabled |
| `ablation_kefc_gate` | `--ablation kefc_gate` | KEFC gate bypassed |
| `ablation_swap_sources` | `--ablation swap_sources` | source roles swapped |
| `material_aluminum` | `--material aluminum_6061` | second material |
| `machine_mill_turn` | `--machine cnc_mill_turn` | second machine |
| `machine_mill_turn_ablation_serialisation_profile` | `--machine cnc_mill_turn --ablation serialisation_profile` | second machine, serialisation-profile check disabled |

`run_ledger.json` summarises the eight runs (steps, approvals, refusals, requests by reason, provenance coverage, rules fired, tool selection, programme accounting, and timings), `timing.json` gives the wall-clock and Pellet times on the authors' Windows host, and `pytest_pipeline.log` the result of the pipeline's test suite on the same host (90 passed).

The serialised programmes (`motor_shaft_1001.nc`) are research artefacts for audit. They are not post-processor certified and must not be loaded into a machine tool.

## Reproduction (from the repository root)

```
python runs/run_all_configurations.py <new folder>
python runs/compare_runs.py runs <new folder>
cd pipeline && python analysis/summarize_runs_v7.py ../runs <out.json> ../runs/pytest_pipeline.log
```

`compare_runs.py` compares every JSON output and the programme of each configuration with the archived ones, ignoring time stamps, the path of the Java executable, output paths, line endings, and the key order of JSON embedded in strings.

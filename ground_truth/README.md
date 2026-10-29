# References and audit

References established outside the pipeline, for evaluation only (manuscript Section 4.1, Tables 2 and 3), and the audit of every raw record, reconciled entity, and planned step against them (Sections 5.2 and 5.4; Table 7; Supplementary Tables S1, S2, S4, S5, S7, and S10).

| File | Content |
|---|---|
| `step_reference_v2.json` | Geometric reference: the 30 B-Rep faces of the catalogue STEP model grouped into ten features R01 to R10 of the pipeline's vocabulary, with exact positions and dimensions in the STEP frame ($z$ along the part axis), and explicit anchors for the end radii of the fitted key |
| `drawing_reference_v2.json` | Features D01 to D06 read manually from the drawing, which has no coordinate frame; every value carries its evidence in pixel coordinates of a 400 dpi raster. The evidence figure named in the file is a crop of the third-party drawing and is not redistributed |
| `physical_reference.json` | Features of the physical replacement shaft (IEC 60072-1 frame-90 drive-end shaft extension), including the keyway and the M8 thread that no input contains, each with the operation family it requires in the pipeline's vocabulary |
| `results_v2.json` | Audit of the 30 raw records, the 22 entities, and the 32 planned steps under three conventions: label-strict, Level G (geometric grounding and label), and Level M (operation-family correctness for the physical part); and the same audit for the swapped source roles |
| `tables_v2.tex` | LaTeX fragments of the audit tables |
| `step_reference_v2.py` | Kernel script that derives `step_reference_v2.json` from the STEP model with OpenCASCADE, reusing the grouping of `../pipeline/analysis/step_reference.py` |
| `extraction_accuracy_v2.py` | Audit script that writes `results_v2.json`; the conventions are documented in its docstring |
| `make_tables_v2.py` | Writes `tables_v2.tex` from `results_v2.json` |

## Reproduction (from the repository root)

```
python ground_truth/extraction_accuracy_v2.py pipeline runs/reference ground_truth/step_reference_v2.json \
    ground_truth/drawing_reference_v2.json ground_truth/physical_reference.json <out.json> runs/ablation_swap_sources
python ground_truth/make_tables_v2.py ground_truth/results_v2.json ground_truth/step_reference_v2.json \
    ground_truth/drawing_reference_v2.json <out.tex>
```

`results_v2.json` was first computed on an earlier run of the reference configuration; regenerating it from `runs/reference` and `runs/ablation_swap_sources` gives identical results, and the archived file is the regenerated one.

The kernel reference needs the third-party catalogue STEP model of the shaft (see the repository README for its checksum) and `pip install cadquery-ocp==8.0.1.1`:

```
python ground_truth/step_reference_v2.py <path to eixo.step> pipeline/analysis <out.json>
```

The kernel is used here only; the pipeline itself is kernel-free.

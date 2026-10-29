# R1-2: merge-level accuracy of the reconciliation stage

Truth: Level G grounding of each raw record (results_v2.json). Max true = maximum one-to-one matching of cross-agent record pairs grounded to the same reference feature (per modality, summed).

| Setting | Entities | Merges | Same feature | Precision | Label-consistent precision | Max true | Recall | Duplicated features | STEP merged: pos. err. primary to merged (mm) | STEP merged: length err. primary to merged (mm) |
|---|---|---|---|---|---|---|---|---|---|---|
| reference (tau_min 0.7, theta 0.5) | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| gate ablated (tau_min 0) | 20 | 10 | 8 | 0.80 | 0.60 | 10 | 0.80 | 2 | 0.00 to 1.99 | 0.69 to 7.58 |
| tau_min 1.0 | 23 | 7 | 6 | 0.86 | 0.86 | 10 | 0.60 | 3 | 0.00 to 3.38 | 1.03 to 1.27 |
| theta 0.3 (gated) | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| theta 0.4 (gated) | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| theta 0.5 (gated) | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| theta 0.6 (gated) | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| theta 0.7 (gated) | 24 | 6 | 5 | 0.83 | 0.83 | 10 | 0.50 | 3 | 0.00 to 0.83 | 0.69 to 12.35 |
| theta 0.8 (gated) | 28 | 2 | 2 | 1.00 | 1.00 | 10 | 0.20 | 7 | 0.00 to 0.66 | 1.03 to 1.27 |
| theta 0.3 (ablated) | 19 | 11 | 4 | 0.36 | 0.36 | 10 | 0.40 | 1 | 0.10 to 5.90 | 0.61 to 6.93 |
| theta 0.4 (ablated) | 20 | 10 | 6 | 0.60 | 0.50 | 10 | 0.60 | 2 | 0.00 to 4.25 | 0.51 to 5.86 |
| theta 0.5 (ablated) | 20 | 10 | 8 | 0.80 | 0.60 | 10 | 0.80 | 2 | 0.00 to 1.99 | 0.69 to 7.58 |
| theta 0.6 (ablated) | 20 | 10 | 8 | 0.80 | 0.60 | 10 | 0.80 | 2 | 0.00 to 1.99 | 0.69 to 7.58 |
| theta 0.7 (ablated) | 22 | 8 | 7 | 0.88 | 0.62 | 10 | 0.70 | 3 | 0.00 to 0.50 | 0.69 to 12.35 |
| theta 0.8 (ablated) | 28 | 2 | 2 | 1.00 | 1.00 | 10 | 0.20 | 7 | 0.00 to 0.66 | 1.03 to 1.27 |
| d_max 10.0 | 23 | 7 | 5 | 0.71 | 0.71 | 10 | 0.50 | 2 | 0.00 to 0.83 | 0.69 to 12.35 |
| d_max 25.0 | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 0.83 | 0.69 to 12.35 |
| d_max 50.0 | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| d_max 100.0 | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| d_max 200.0 | 22 | 8 | 6 | 0.75 | 0.75 | 10 | 0.60 | 2 | 0.00 to 3.32 | 0.69 to 7.58 |
| epsilon 0.1 (gated) | 23 | 7 | 5 | 0.71 | 0.71 | 10 | 0.50 | 3 | 0.00 to 4.42 | 2.05 to 1.23 |
| epsilon 0.2 (gated) | 23 | 7 | 5 | 0.71 | 0.71 | 10 | 0.50 | 3 | 0.00 to 4.42 | 2.05 to 1.23 |
| epsilon 0.3 (gated) | 23 | 7 | 5 | 0.71 | 0.71 | 10 | 0.50 | 3 | 0.00 to 4.42 | 2.05 to 1.23 |
| epsilon 0.5 (gated) | 23 | 7 | 6 | 0.86 | 0.86 | 10 | 0.60 | 3 | 0.25 to 3.80 | 1.53 to 9.22 |
| epsilon 0.1 (ablated) | 21 | 9 | 7 | 0.78 | 0.56 | 10 | 0.70 | 3 | 0.00 to 2.21 | 2.05 to 1.23 |
| epsilon 0.2 (ablated) | 21 | 9 | 7 | 0.78 | 0.56 | 10 | 0.70 | 3 | 0.00 to 2.21 | 2.05 to 1.23 |
| epsilon 0.3 (ablated) | 21 | 9 | 7 | 0.78 | 0.56 | 10 | 0.70 | 3 | 0.00 to 2.21 | 2.05 to 1.23 |
| epsilon 0.5 (ablated) | 20 | 10 | 8 | 0.80 | 0.60 | 10 | 0.80 | 2 | 0.10 to 1.52 | 1.02 to 6.51 |

Weights (26 settings): {"gated": {"settings": 26, "precision_range": [0.6666666666666666, 0.8571428571428571], "label_consistent_precision_range": [0.6666666666666666, 0.8571428571428571], "recall_range": [0.2, 0.6]}, "ablated": {"settings": 26, "precision_range": [0.6, 0.8888888888888888], "label_consistent_precision_range": [0.4, 0.6666666666666666], "recall_range": [0.3, 0.8]}}

Global one-to-one assignment probe: {"reference": {"merges": 8, "correct": 6, "precision": 0.75, "recall": 0.6, "wrong_merges": [["STEP", 3, "R03", 5, "R05"], ["DRAWING", 5, "D05c", 6, "D05a"]]}, "tau_min_0": {"merges": 10, "correct": 8, "precision": 0.8, "recall": 0.8, "wrong_merges": [["STEP", 3, "R03", 5, "R05"], ["DRAWING", 5, "D05c", 6, "D05a"]]}, "tau_min_1": {"merges": 7, "correct": 6, "precision": 0.8571428571428571, "recall": 0.6, "wrong_merges": [["STEP", 10, "R06", 5, "R05"]]}, "eps": {"0.1": {"merges": 7, "correct": 5, "precision": 0.7142857142857143, "recall": 0.5, "wrong_merges": [["STEP", 10, "R06", 5, "R05"], ["DRAWING", 5, "D05c", 6, "D05a"]]}, "0.2": {"merges": 7, "correct": 5, "precision": 0.7142857142857143, "recall": 0.5, "wrong_merges": [["STEP", 10, "R06", 5, "R05"], ["DRAWING", 5, "D05c", 6, "D05a"]]}, "0.3": {"merges": 7, "correct": 5, "precision": 0.7142857142857143, "recall": 0.5, "wrong_merges": [["STEP", 10, "R06", 5, "R05"], ["DRAWING", 5, "D05c", 6, "D05a"]]}, "0.5": {"merges": 7, "correct": 6, "precision": 0.8571428571428571, "recall": 0.6, "wrong_merges": [["DRAWING", 5, "D05c", 6, "D05a"]]}}}

Reference merges:

- STEP: [1, 'Step', 'R01'] + [5, 'Boss', 'R05'] tau 0.7 same feature False
- STEP: [7, 'Blind Hole', 'R07'] + [1, 'Blind Hole', 'R07'] tau 1.0 same feature True
- STEP: [8, 'Counterbore', 'R08'] + [2, 'Counterbore', 'R08'] tau 1.0 same feature True
- DRAWING: [1, 'Cylinder', 'D01'] + [2, 'Cylinder', 'D01'] tau 1.0 same feature True
- DRAWING: [2, 'Cylinder', 'D02'] + [1, 'Cylinder', 'D02'] tau 1.0 same feature True
- DRAWING: [3, 'Groove', 'D03'] + [3, 'Groove', 'D03'] tau 1.0 same feature True
- DRAWING: [4, 'Boss', 'D04'] + [4, 'Boss', 'D04'] tau 1.0 same feature True
- DRAWING: [5, 'Hole', 'D05c'] + [6, 'Bore', 'D05a'] tau 0.7 same feature False

Ablation merges:

- STEP: [1, 'Step', 'R01'] + [5, 'Boss', 'R05'] tau 0.7 same feature False
- STEP: [7, 'Blind Hole', 'R07'] + [1, 'Blind Hole', 'R07'] tau 1.0 same feature True
- STEP: [8, 'Counterbore', 'R08'] + [2, 'Counterbore', 'R08'] tau 1.0 same feature True
- STEP: [11, 'Through Hole', 'R06'] + [3, 'Slot', 'R06'] tau 0.3 same feature True
- STEP: [12, 'Through Hole', 'R06'] + [4, 'Slot', 'R06'] tau 0.3 same feature True
- DRAWING: [1, 'Cylinder', 'D01'] + [2, 'Cylinder', 'D01'] tau 1.0 same feature True
- DRAWING: [2, 'Cylinder', 'D02'] + [1, 'Cylinder', 'D02'] tau 1.0 same feature True
- DRAWING: [3, 'Groove', 'D03'] + [3, 'Groove', 'D03'] tau 1.0 same feature True
- DRAWING: [4, 'Boss', 'D04'] + [4, 'Boss', 'D04'] tau 1.0 same feature True
- DRAWING: [5, 'Hole', 'D05c'] + [6, 'Bore', 'D05a'] tau 0.7 same feature False

# R2-3: completeness, consistency, and tolerance checks in the merge criterion

| Setting | Entities | Merges | Same feature | Cross-family | Precision | Recall | STEP merged pos. err. (mm) | STEP merged length err. (mm) |
|---|---|---|---|---|---|---|---|---|
| reference (gated) | 22 | 8 | 6 | 0 | 0.75 | 0.60 | 3.32 | 7.58 |
| C[structured] (gated) | 27 | 3 | 2 | 0 | 0.67 | 0.20 | 3.32 | 7.58 |
| E0.1[structured] (gated) | 23 | 7 | 5 | 0 | 0.71 | 0.50 | 4.42 | 1.23 |
| C+E0.1[structured] (gated) | 29 | 1 | 1 | 0 | 1.00 | 0.10 | 0.00 | 1.23 |
| E0.2[structured] (gated) | 23 | 7 | 5 | 0 | 0.71 | 0.50 | 4.42 | 1.23 |
| C+E0.2[structured] (gated) | 29 | 1 | 1 | 0 | 1.00 | 0.10 | 0.00 | 1.23 |
| E0.3[structured] (gated) | 23 | 7 | 5 | 0 | 0.71 | 0.50 | 4.42 | 1.23 |
| C+E0.3[structured] (gated) | 29 | 1 | 1 | 0 | 1.00 | 0.10 | 0.00 | 1.23 |
| E0.5[structured] (gated) | 23 | 7 | 6 | 0 | 0.86 | 0.60 | 3.80 | 9.22 |
| C+E0.5[structured] (gated) | 28 | 2 | 2 | 0 | 1.00 | 0.20 | 3.80 | 9.22 |
| Tf[structured] (gated) | 24 | 6 | 4 | 0 | 0.67 | 0.40 | 8.83 | n/a |
| C+Tf[structured] (gated) | 30 | 0 | 0 | 0 | n/a | 0.00 | n/a | n/a |
| Tm[structured] (gated) | 24 | 6 | 4 | 0 | 0.67 | 0.40 | 8.83 | n/a |
| C+Tm[structured] (gated) | 30 | 0 | 0 | 0 | n/a | 0.00 | n/a | n/a |
| Tc[structured] (gated) | 24 | 6 | 4 | 0 | 0.67 | 0.40 | 8.83 | n/a |
| C+Tc[structured] (gated) | 30 | 0 | 0 | 0 | n/a | 0.00 | n/a | n/a |
| Tv[structured] (gated) | 24 | 6 | 4 | 0 | 0.67 | 0.40 | 8.83 | n/a |
| C+Tv[structured] (gated) | 30 | 0 | 0 | 0 | n/a | 0.00 | n/a | n/a |
| C[free_text] (gated) | 23 | 7 | 6 | 0 | 0.86 | 0.60 | 3.32 | 7.58 |
| E0.1[free_text] (gated) | 23 | 7 | 5 | 0 | 0.71 | 0.50 | 4.42 | 1.23 |
| C+E0.1[free_text] (gated) | 25 | 5 | 5 | 0 | 1.00 | 0.50 | 0.00 | 1.23 |
| E0.2[free_text] (gated) | 23 | 7 | 5 | 0 | 0.71 | 0.50 | 4.42 | 1.23 |
| C+E0.2[free_text] (gated) | 25 | 5 | 5 | 0 | 1.00 | 0.50 | 0.00 | 1.23 |
| E0.3[free_text] (gated) | 23 | 7 | 5 | 0 | 0.71 | 0.50 | 4.42 | 1.23 |
| C+E0.3[free_text] (gated) | 25 | 5 | 5 | 0 | 1.00 | 0.50 | 0.00 | 1.23 |
| E0.5[free_text] (gated) | 23 | 7 | 6 | 0 | 0.86 | 0.60 | 3.80 | 9.22 |
| C+E0.5[free_text] (gated) | 24 | 6 | 6 | 0 | 1.00 | 0.60 | 3.80 | 9.22 |
| Tf[free_text] (gated) | 26 | 4 | 2 | 0 | 0.50 | 0.20 | 8.83 | n/a |
| C+Tf[free_text] (gated) | 28 | 2 | 2 | 0 | 1.00 | 0.20 | n/a | n/a |
| Tm[free_text] (gated) | 26 | 4 | 2 | 0 | 0.50 | 0.20 | 8.83 | n/a |
| C+Tm[free_text] (gated) | 28 | 2 | 2 | 0 | 1.00 | 0.20 | n/a | n/a |
| Tc[free_text] (gated) | 26 | 4 | 2 | 0 | 0.50 | 0.20 | 8.83 | n/a |
| C+Tc[free_text] (gated) | 28 | 2 | 2 | 0 | 1.00 | 0.20 | n/a | n/a |
| Tv[free_text] (gated) | 25 | 5 | 3 | 0 | 0.60 | 0.30 | 8.83 | n/a |
| C+Tv[free_text] (gated) | 27 | 3 | 3 | 0 | 1.00 | 0.30 | n/a | n/a |
| reference (ablated_type_gate) | 20 | 10 | 8 | 2 | 0.80 | 0.80 | 1.99 | 7.58 |
| C[free_text] (ablated_type_gate) | 21 | 9 | 8 | 2 | 0.89 | 0.80 | 1.99 | 7.58 |
| C+E0.1[free_text] (ablated_type_gate) | 23 | 7 | 7 | 2 | 1.00 | 0.70 | 0.00 | 1.23 |
| C+E0.2[free_text] (ablated_type_gate) | 23 | 7 | 7 | 2 | 1.00 | 0.70 | 0.00 | 1.23 |
| C+E0.3[free_text] (ablated_type_gate) | 23 | 7 | 7 | 2 | 1.00 | 0.70 | 0.00 | 1.23 |
| C+E0.5[free_text] (ablated_type_gate) | 21 | 9 | 8 | 3 | 0.89 | 0.80 | 1.52 | 6.51 |
| C+Tm[free_text] (ablated_type_gate) | 26 | 4 | 4 | 2 | 1.00 | 0.40 | 0.00 | n/a |
| C+Tv[free_text] (ablated_type_gate) | 25 | 5 | 5 | 2 | 1.00 | 0.50 | 0.00 | n/a |

Discrepancy of common dimensions on true same-feature pairs: {"common_dimensions_of_true_pairs": 20, "identical": 14, "different": 6, "within_tolerance": {"f": 14, "m": 14, "c": 14, "v": 16}, "different_within_tolerance": {"f": 0, "m": 0, "c": 0, "v": 2}, "smallest_nonzero_difference": 0.31, "largest_difference": 40.5}

- STEP R05 [5, 'Step'] / [5, 'Boss'] D: [24.0, 24.95] diff 0.95 within {'f': False, 'm': False, 'c': False, 'v': True}
- STEP R05 [5, 'Step'] / [5, 'Boss'] L: [47.5, 88.0] diff 40.5 within {'f': False, 'm': False, 'c': False, 'v': False}
- STEP R07 [7, 'Blind Hole'] / [1, 'Blind Hole'] D: [6.8, 6.8] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- STEP R07 [7, 'Blind Hole'] / [1, 'Blind Hole'] L: [21.05, 19.0] diff 2.05 within {'f': False, 'm': False, 'c': False, 'v': False}
- STEP R08 [8, 'Counterbore'] / [2, 'Counterbore'] D: [8.4, 8.4] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- STEP R08 [8, 'Counterbore'] / [2, 'Counterbore'] L: [2.7, 6.0] diff 3.3 within {'f': False, 'm': False, 'c': False, 'v': False}
- STEP R06 [10, 'Boss'] / [3, 'Slot'] W: [8.0, 8.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- STEP R06 [10, 'Boss'] / [4, 'Slot'] W: [8.0, 8.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- STEP R06 [11, 'Through Hole'] / [3, 'Slot'] D: [8.0, 8.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- STEP R06 [11, 'Through Hole'] / [4, 'Slot'] D: [8.0, 8.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- STEP R06 [12, 'Through Hole'] / [3, 'Slot'] D: [8.0, 8.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- STEP R06 [12, 'Through Hole'] / [4, 'Slot'] D: [8.0, 8.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- DRAWING D01 [1, 'Cylinder'] / [2, 'Cylinder'] D: [24.0, 22.0] diff 2.0 within {'f': False, 'm': False, 'c': False, 'v': False}
- DRAWING D01 [1, 'Cylinder'] / [2, 'Cylinder'] L: [46.5, 46.5] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- DRAWING D02 [2, 'Cylinder'] / [1, 'Cylinder'] D: [24.0, 24.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- DRAWING D02 [2, 'Cylinder'] / [1, 'Cylinder'] L: [37.5, 37.5] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- DRAWING D03 [3, 'Groove'] / [3, 'Groove'] W: [1.75, 1.75] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- DRAWING D04 [4, 'Boss'] / [4, 'Boss'] L: [32.0, 32.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}
- DRAWING D04 [4, 'Boss'] / [4, 'Boss'] W: [4.0, 3.69] diff 0.31 within {'f': False, 'm': False, 'c': False, 'v': True}
- DRAWING D04 [4, 'Boss'] / [5, 'Slot'] W: [4.0, 4.0] diff 0.0 within {'f': True, 'm': True, 'c': True, 'v': True}

Fusion policies (merged STEP entities, mean position and length error, mm):

- average: position {"primary": 0.0030000000000048508, "merged": 3.3203333333333283}, length {"primary": 0.6863333333333336, "merged": 7.580333333333335}
- primary: position {"primary": 0.0030000000000048508, "merged": 0.0030000000000048508}, length {"primary": 0.6863333333333336, "merged": 0.6863333333333336}
- tolerance:f: position {"primary": 0.0030000000000048508, "merged": 0.0030000000000048508}, length {"primary": 0.6863333333333336, "merged": 0.6863333333333336}
- tolerance:m: position {"primary": 0.0030000000000048508, "merged": 0.0030000000000048508}, length {"primary": 0.6863333333333336, "merged": 0.6863333333333336}
- tolerance:c: position {"primary": 0.0030000000000048508, "merged": 0.0030000000000048508}, length {"primary": 0.6863333333333336, "merged": 0.6863333333333336}
- tolerance:v: position {"primary": 0.0030000000000048508, "merged": 0.0030000000000048508}, length {"primary": 0.6863333333333336, "merged": 0.6863333333333336}

# R2-2: frame-free cross-modal identity probe

Declared setting {"tau_min": 0.7, "completeness": true, "eps": 0.1}: 4 links, 2 correct (precision 0.50), recall 2 of 8 (0.25); duplicated approved steps removed [7, 14, 22, 23, 29] of [2, 7, 8, 9, 14, 15, 16, 21, 22, 23, 29]; removed by wrong links [22, 29].

Links:

- drawing 15 -> STEP 5 tau 0.7 common ['D', 'L'] rel [0.0, 0.0211] correct True ['P05', 'P05']
- drawing 17 -> STEP 4 tau 0.7 common ['D'] rel [0.0833] correct False ['P03', 'P04']
- drawing 20 -> STEP 11 tau 0.7 common ['D'] rel [0.0476] correct False ['P07b', 'P08']
- drawing 21 -> STEP 7 tau 0.7 common ['D'] rel [0.0] correct True ['P07a', 'P07a']

Unlinked drawing entities: [{"id": 16, "type": "Cylinder", "phys": "P01", "stated": {"D": 24.0, "L": 37.5}}, {"id": 18, "type": "Boss", "phys": "P08", "stated": {"L": 32.0, "W": 4.0}}, {"id": 19, "type": "Hole", "phys": "P07c", "stated": {"D": 12.2}}, {"id": 22, "type": "Slot", "phys": "P08", "stated": {"W": 4.0}}]

| tau_min | completeness | eps | admissible pairs | links | correct | precision | recall | duplicate steps removed | removed by wrong links |
|---|---|---|---|---|---|---|---|---|---|
| 0.7 | True | 0.05 | 4 | 3 | 2 | 0.67 | 0.25 | 4 | 1 |
| 0.7 | True | 0.1 | 6 | 4 | 2 | 0.50 | 0.25 | 5 | 2 |
| 0.7 | True | 0.2 | 11 | 4 | 2 | 0.50 | 0.25 | 5 | 2 |
| 0.7 | True | 0.3 | 12 | 5 | 1 | 0.20 | 0.12 | 7 | 6 |
| 0.7 | True | 0.5 | 22 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.7 | True | None | 25 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.7 | False | 0.05 | 6 | 4 | 2 | 0.50 | 0.25 | 6 | 3 |
| 0.7 | False | 0.1 | 8 | 5 | 2 | 0.40 | 0.25 | 7 | 4 |
| 0.7 | False | 0.2 | 13 | 5 | 2 | 0.40 | 0.25 | 7 | 4 |
| 0.7 | False | 0.3 | 14 | 5 | 1 | 0.20 | 0.12 | 7 | 6 |
| 0.7 | False | 0.5 | 24 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.7 | False | None | 27 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.3 | True | 0.05 | 6 | 3 | 2 | 0.67 | 0.25 | 4 | 1 |
| 0.3 | True | 0.1 | 8 | 4 | 2 | 0.50 | 0.25 | 5 | 2 |
| 0.3 | True | 0.2 | 15 | 4 | 2 | 0.50 | 0.25 | 5 | 2 |
| 0.3 | True | 0.3 | 16 | 5 | 1 | 0.20 | 0.12 | 7 | 6 |
| 0.3 | True | 0.5 | 28 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.3 | True | None | 31 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.3 | False | 0.05 | 10 | 5 | 3 | 0.60 | 0.38 | 6 | 3 |
| 0.3 | False | 0.1 | 12 | 6 | 3 | 0.50 | 0.38 | 7 | 4 |
| 0.3 | False | 0.2 | 19 | 6 | 3 | 0.50 | 0.38 | 7 | 4 |
| 0.3 | False | 0.3 | 20 | 6 | 2 | 0.33 | 0.25 | 7 | 6 |
| 0.3 | False | 0.5 | 32 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.3 | False | None | 35 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.0 | True | 0.05 | 8 | 4 | 3 | 0.75 | 0.38 | 5 | 1 |
| 0.0 | True | 0.1 | 12 | 5 | 3 | 0.60 | 0.38 | 6 | 2 |
| 0.0 | True | 0.2 | 21 | 5 | 3 | 0.60 | 0.38 | 6 | 2 |
| 0.0 | True | 0.3 | 22 | 6 | 2 | 0.33 | 0.25 | 8 | 6 |
| 0.0 | True | 0.5 | 46 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.0 | True | None | 96 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.0 | False | 0.05 | 24 | 6 | 4 | 0.67 | 0.50 | 7 | 3 |
| 0.0 | False | 0.1 | 28 | 7 | 4 | 0.57 | 0.50 | 8 | 4 |
| 0.0 | False | 0.2 | 37 | 7 | 4 | 0.57 | 0.50 | 8 | 4 |
| 0.0 | False | 0.3 | 38 | 7 | 3 | 0.43 | 0.38 | 8 | 6 |
| 0.0 | False | 0.5 | 62 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |
| 0.0 | False | None | 112 | 8 | 5 | 0.62 | 0.62 | 11 | 3 |

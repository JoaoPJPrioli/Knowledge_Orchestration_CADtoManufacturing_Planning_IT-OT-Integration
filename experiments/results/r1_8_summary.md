# R1-8: corrected force and tool-life models, and the tool-life feedback path

Constants are nominal and uncalibrated (see process_constants.json); every conclusion below is checked over the declared sweep ranges.

Time base: the programme's cycle-time estimator gives 198.61 s of cutting; the in-cut time attributed to the nine segments is 197.55 s (the difference is G83 peck retracts).

| Step | Operation | Tool (material) | h (mm) | kc (N/mm2) | Fc Kienzle (N) | Fc constant kc (N) | P (kW) | v/v_ref | T (min) | t in cut (s) | life used |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | rough_turning | turning_insert_rough (Carbide) | 0.249 | 2697 | 1348 | 1000 | 0.846 | 0.42 | 491.2 | 29.85 | 0.00101 |
| 4 | rough_turning | turning_insert_rough (Carbide) | 0.249 | 2697 | 1348 | 1000 | 0.800 | 0.40 | 613.5 | 1.88 | 0.00005 |
| 5 | rough_turning | turning_insert_rough (Carbide) | 0.249 | 2697 | 1348 | 1000 | 0.813 | 0.40 | 573.7 | 24.75 | 0.00072 |
| 10 | finish_turning | turning_insert_finish (Carbide with Coating) | 0.060 | 3293 | 40 | 24 | 0.046 | 0.47 | 306.6 | 66.33 | 0.00361 |
| 11 | finish_turning | turning_insert_finish (Carbide with Coating) | 0.060 | 3293 | 40 | 24 | 0.044 | 0.44 | 383.0 | 4.17 | 0.00018 |
| 12 | finish_turning | turning_insert_finish (Carbide with Coating) | 0.060 | 3293 | 40 | 24 | 0.045 | 0.45 | 358.1 | 55.00 | 0.00256 |
| 17 | drilling | drill_bit (High-Speed Steel) | 0.064 | 3260 | 831 | 510 | 0.266 | 0.92 | 91.1 | 9.88 | 0.00181 |
| 18 | drilling | drill_bit (High-Speed Steel) | 0.064 | 3260 | 1027 | 630 | 0.406 | 1.13 | 16.8 | 2.68 | 0.00265 |
| 24 | counterboring | counterbore_cutter (Carbide) | 0.120 | 2987 | 1075 | 720 | 0.473 | 0.63 | 96.2 | 3.01 | 0.00052 |

| Tool | Life used per part (nominal) | Parts per edge (nominal) | Parts per edge (sweep) | First request at part (nominal) | (sweep) | Legacy wear model |
|---|---|---|---|---|---|---|
| turning_insert_rough | 0.00178 | 561 | 135 to 5459 | 449 (observed 449) | 109 to 4368 | 2.16 % on a 1.5 min clock |
| turning_insert_finish | 0.00635 | 158 | 43 to 1363 | 127 (observed 127) | 35 to 1091 | 2.22 % on a 3.33 min clock |
| drill_bit | 0.00446 | 224 | 136 to 475 | 180 (observed 180) | 109 to 380 | 44.47 % on a 12.56 min clock |
| counterbore_cutter | 0.00052 | 1918 | 752 to 12213 | 1535 (observed 1535) | 602 to 9771 | 8.15 % on a 3.01 min clock |

Handbook-speed scenario (every cut at the lower handbook speed of its tool, in-cut time scaled accordingly):

| Tool | Life used per part | Parts per edge | Parts per edge (sweep) |
|---|---|---|---|
| turning_insert_rough | 0.0257 | 39 | 26 to 155 |
| turning_insert_finish | 0.0644 | 16 | 10 to 62 |
| drill_bit | 0.0045 | 224 | 149 to 447 |
| counterbore_cutter | 0.0021 | 476 | 317 to 1904 |

Force (nominal): mean 789 N, max 1348 N; max power 0.846 kW; |P - M omega| <= 1.1e-16 kW. Constant-kc model of the reference run: mean 548 N.
Force sweep (48 settings): mean 533 to 1211 N, max 911 to 1914 N, max power 0.57 to 1.20 kW.

Feedback path:

```
{
 "single_part_no_request": {
  "nominal_requests": 0,
  "swept_settings_that_would_request": 0,
  "swept_settings": 64
 },
 "batch_trigger": {
  "nominal": {
   "turning_insert_rough": {
    "analytic_trigger_part": 449,
    "observed_first_request_part": 449
   },
   "turning_insert_finish": {
    "analytic_trigger_part": 127,
    "observed_first_request_part": 127
   },
   "drill_bit": {
    "analytic_trigger_part": 180,
    "observed_first_request_part": 180
   },
   "counterbore_cutter": {
    "analytic_trigger_part": 1535,
    "observed_first_request_part": 1535
   }
  },
  "swept_settings": 64,
  "early_or_missed_triggers": 0
 },
 "resolution_reused": {
  "tool": "turning_insert_finish",
  "requests": 3,
  "same_ids_on_rerun": true,
  "statuses_on_rerun": [
   "expert_approved"
  ],
  "duplicates_created": 0
 },
 "missing_constants": {
  "serialised_steps": 7,
  "tool_life_unavailable_steps": 7,
  "requests_by_reason": {
   "missing_knowledge": 7
  },
  "force_available_steps": 7
 }
}
```

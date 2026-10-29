# R1-5 Step B: stock-aware turning profile (evaluation code)

Declared stock: 30.0 mm bar, free end z = 169.5
Approved steps: 27; serialised: [3, 5, 10, 12, 17, 18, 24]

Refusals: [
 {
  "step_number": 1,
  "operation": "facing",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 2,
  "operation": "facing",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 4,
  "operation": "rough_turning",
  "kind": "recess",
  "detail": [
   "a longitudinal pass at diameter 24.000 from the free end would cut below diameter 25.350 of step 3 over z 120.25 to 138.20; diameter 24.400 of step 5 over z 121.00 to 168.50, outside its own span; a recess needs a plunge pattern"
  ]
 },
 {
  "step_number": 6,
  "operation": "rough_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 7,
  "operation": "rough_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 8,
  "operation": "rough_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 9,
  "operation": "rough_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 11,
  "operation": "finish_turning",
  "kind": "recess",
  "detail": [
   "a longitudinal pass at diameter 23.600 from the free end would cut below diameter 24.950 of step 10 over z 120.25 to 138.20; diameter 24.000 of step 12 over z 121.00 to 168.50, outside its own span; a recess needs a plunge pattern"
  ]
 },
 {
  "step_number": 13,
  "operation": "finish_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 14,
  "operation": "finish_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 15,
  "operation": "finish_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 16,
  "operation": "finish_turning",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 21,
  "operation": "drilling",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 22,
  "operation": "drilling",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 23,
  "operation": "drilling",
  "kind": "missing_inputs",
  "detail": [
   "diameter (\u00d8 or diameter or R or radius)",
   "axial length (L or length)"
  ]
 },
 {
  "step_number": 25,
  "operation": "chamfering",
  "kind": "missing_inputs",
  "detail": [
   "chamfer angle (angle or chamfer_angle)"
  ]
 },
 {
  "step_number": 26,
  "operation": "chamfering",
  "kind": "missing_inputs",
  "detail": [
   "chamfer angle (angle or chamfer_angle)"
  ]
 },
 {
  "step_number": 27,
  "operation": "chamfering",
  "kind": "missing_inputs",
  "detail": [
   "chamfer angle (angle or chamfer_angle)"
  ]
 },
 {
  "step_number": 28,
  "operation": "chamfering",
  "kind": "missing_inputs",
  "detail": [
   "chamfer angle (angle or chamfer_angle)"
  ]
 },
 {
  "step_number": 29,
  "operation": "grooving",
  "kind": "missing_inputs",
  "detail": [
   "outer diameter (one of outer_diameter)",
   "groove-bottom diameter (one of groove_bottom_diameter, bottom_diameter, or a radial depth under groove_depth, depth)"
  ]
 }
]

Plan overlaps (recorded, not refused): [
 {
  "features": [
   1,
   5
  ],
  "z_from": 121.0,
  "z_to": 138.2,
  "final_diameters": [
   24.0,
   24.95
  ],
  "steps": [
   3,
   5,
   10,
   12
  ]
 }
]

| Pass | Step | Operation | Diameter | Radial depth | Planned ap |
|---|---|---|---|---|---|
| 1 | 3 | rough_turning | 26.0 | 2.0 | 2.0 |
| 2 | 3 | rough_turning | 25.35 | 0.325 | 2.0 |
| 3 | 5 | rough_turning | 24.4 | 0.475 | 2.0 |
| 4 | 10 | finish_turning | 24.95 | 0.2 | 0.2 |
| 5 | 12 | finish_turning | 24.0 | 0.2 | 0.2 |

| Quantity | Reference programme | Stock-aware profile |
|---|---|---|
| rapids_into_stock | 4 | 0 |
| rapid_penetration_max_mm | 2.525 | 0.0 |
| max_radial_engagement_mm | 3.0 | 2.0 |
| passes_exceeding_planned_ap | 2 | 0 |
| passes_exceeding_tool_limit | 0 | 0 |
| finishing_passes_removing_nothing | 3 | 0 |
| outer_gouges | 1 | 0 |
| inner_gouges | 0 | 0 |
| feed_moves_below_part_extent | 0 | 0 |
| segments | 9 | 7 |
| cycle_time_min | 4.38 | 5.87 |
| cutting_time_s | 198.6 | 291.0 |
| rapid_time_s | 9.8 | 9.6 |
| program_lines | 132 | 126 |
| validator errors/warnings | {'errors': 0, 'warnings': 0} | {'errors': 0, 'warnings': 0} |
| parameter fidelity | {'passed': True, 'segments_checked': 9, 'spindle_match': 9, 'feed_match': 9, 'coolant_match': 9} | {'passed': True, 'segments_checked': 7, 'spindle_match': 7, 'feed_match': 7, 'coolant_match': 7} |
| dimension fidelity | {'passed': True, 'segments': 9, 'lookups': 27, 'defaulted': 0, 'cutting_words_checked': 9, 'unexplained_cutting_words': 0} | {'passed': True, 'segments': 7, 'lookups': 21, 'defaulted': 0, 'cutting_words_checked': 8, 'unexplained_cutting_words': 0} |

Conformance (stock-aware): {
 "outer_gouges": [],
 "outer_residual": [
  {
   "z_from": 118.01,
   "z_to": 120.99,
   "max_mm": 0.675,
   "steps": [
    10
   ],
   "reference_features": [
    "R02",
    "R03",
    "R04"
   ]
  },
  {
   "z_from": 167.51,
   "z_to": 168.5,
   "max_mm": 1.0,
   "steps": [
    12
   ],
   "reference_features": [
    "R10"
   ]
  }
 ],
 "inner_gouges": [],
 "inner_residual": [
  {
   "z_from": 141.47,
   "z_to": 154.41,
   "max_mm": 3.4,
   "steps": [
    17
   ],
   "reference_features": [
    "R07"
   ]
  },
  {
   "z_from": 162.51,
   "z_to": 164.5,
   "max_mm": 0.8,
   "steps": [
    17
   ],
   "reference_features": [
    "R08"
   ]
  },
  {
   "z_from": 165.22,
   "z_to": 168.5,
   "max_mm": 1.9,
   "steps": [
    18,
    24
   ],
   "reference_features": [
    "R09"
   ]
  }
 ],
 "material_beyond_part_end_mm": 1.0
}

Conformance (reference): {
 "outer_gouges": [
  {
   "z_from": 120.28,
   "z_to": 122.25,
   "max_mm": 0.2,
   "steps": [
    4
   ],
   "reference_features": [
    "R04",
    "R05"
   ]
  }
 ],
 "outer_residual": [
  {
   "z_from": 118.01,
   "z_to": 118.49,
   "max_mm": 0.49,
   "steps": [
    3
   ],
   "reference_features": [
    "R02"
   ]
  },
  {
   "z_from": 167.51,
   "z_to": 168.5,
   "max_mm": 1.0,
   "steps": [
    5
   ],
   "reference_features": [
    "R10"
   ]
  }
 ],
 "inner_gouges": [],
 "inner_residual": [
  {
   "z_from": 141.47,
   "z_to": 154.41,
   "max_mm": 3.4,
   "steps": [
    17
   ],
   "reference_features": [
    "R07"
   ]
  },
  {
   "z_from": 162.51,
   "z_to": 164.5,
   "max_mm": 0.8,
   "steps": [
    17
   ],
   "reference_features": [
    "R08"
   ]
  },
  {
   "z_from": 165.22,
   "z_to": 168.5,
   "max_mm": 1.9,
   "steps": [
    18,
    24
   ],
   "reference_features": [
    "R09"
   ]
  }
 ],
 "material_beyond_part_end_mm": 1.0
}

Stock sweep: 
```
{
 "26.0/169.0": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 0.475,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 4,
  "recess_refusals": [
   4,
   11
  ]
 },
 "26.0/169.5": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 0.475,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 4,
  "recess_refusals": [
   4,
   11
  ]
 },
 "26.0/170.5": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 0.475,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 4,
  "recess_refusals": [
   4,
   11
  ]
 },
 "28.0/169.0": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 1.325,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 4,
  "recess_refusals": [
   4,
   11
  ]
 },
 "28.0/169.5": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 1.325,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 4,
  "recess_refusals": [
   4,
   11
  ]
 },
 "28.0/170.5": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 1.325,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 4,
  "recess_refusals": [
   4,
   11
  ]
 },
 "30.0/169.0": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 2.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 5,
  "recess_refusals": [
   4,
   11
  ]
 },
 "30.0/169.5": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 2.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 5,
  "recess_refusals": [
   4,
   11
  ]
 },
 "30.0/170.5": {
  "rapids_into_stock": 0,
  "rapid_penetration_max_mm": 0.0,
  "max_radial_engagement_mm": 2.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 0,
  "outer_gouges": [],
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0,
  "passes": 5,
  "recess_refusals": [
   4,
   11
  ]
 }
}
```

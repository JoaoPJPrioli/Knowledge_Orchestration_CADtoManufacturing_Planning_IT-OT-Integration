# R1-5: material-based check of the serialised programme

Stock: bar of 30.0 mm, free end at z = 169.5 mm (part end face at 168.5 mm); tool depth limits from tools.owl: {"counterbore_cutter": 15.0, "turning_insert_finish": 2.0, "turning_insert_rough": 5.0, "drill_bit": 50.0}

## Reference programme

Feed moves and cycles:

| Line | Step | Operation | Tool | Radial engagement or depth (mm) | Planned ap (mm) | Tool limit (mm) |
|---|---|---|---|---|---|---|
| 34 | 3 | rough_turning | turning_insert_rough | 2.525 | 2.0 | 5.0 |
| 42 | 4 | rough_turning | turning_insert_rough | 0.675 | 2.0 | 5.0 |
| 50 | 5 | rough_turning | turning_insert_rough | 3.0 | 2.0 | 5.0 |
| 67 | 10 | finish_turning | turning_insert_finish | 0.0 | 0.2 | 2.0 |
| 75 | 11 | finish_turning | turning_insert_finish | 0.0 | 0.2 | 2.0 |
| 83 | 12 | finish_turning | turning_insert_finish | 0.0 | 0.2 | 2.0 |
| 99 | 17 | drilling | drill_bit | 17.12 |  | 50.0 |
| 106 | 18 | drilling | drill_bit | 4.99 |  | 50.0 |
| 122 | 24 | counterboring | counterbore_cutter | 4.99 |  | 15.0 |

Rapid moves entering material: [{"line": 32, "step": 3, "tool": "turning_insert_rough", "depth_mm": 0.525, "at_z": 169.501}, {"line": 33, "step": 3, "tool": "turning_insert_rough", "depth_mm": 2.525, "at_z": 140.2}, {"line": 41, "step": 4, "tool": "turning_insert_rough", "depth_mm": 0.675, "at_z": 122.25}, {"line": 48, "step": 5, "tool": "turning_insert_rough", "depth_mm": 1.126, "at_z": 140.21}]

Conformance with the B-Rep reference: {
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

Stock sweep (bar diameter / free-end z):

```
{
 "26.0/169.0": {
  "rapids_into_stock": 2,
  "rapid_penetration_max_mm": 0.675,
  "max_radial_engagement_mm": 1.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "26.0/169.5": {
  "rapids_into_stock": 2,
  "rapid_penetration_max_mm": 0.675,
  "max_radial_engagement_mm": 1.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "26.0/170.5": {
  "rapids_into_stock": 3,
  "rapid_penetration_max_mm": 1.0,
  "max_radial_engagement_mm": 1.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "28.0/169.0": {
  "rapids_into_stock": 3,
  "rapid_penetration_max_mm": 1.525,
  "max_radial_engagement_mm": 2.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "28.0/169.5": {
  "rapids_into_stock": 3,
  "rapid_penetration_max_mm": 1.525,
  "max_radial_engagement_mm": 2.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "28.0/170.5": {
  "rapids_into_stock": 4,
  "rapid_penetration_max_mm": 2.0,
  "max_radial_engagement_mm": 2.0,
  "passes_exceeding_planned_ap": 0,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "30.0/169.0": {
  "rapids_into_stock": 4,
  "rapid_penetration_max_mm": 2.525,
  "max_radial_engagement_mm": 3.0,
  "passes_exceeding_planned_ap": 2,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "30.0/169.5": {
  "rapids_into_stock": 4,
  "rapid_penetration_max_mm": 2.525,
  "max_radial_engagement_mm": 3.0,
  "passes_exceeding_planned_ap": 2,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 },
 "30.0/170.5": {
  "rapids_into_stock": 5,
  "rapid_penetration_max_mm": 3.0,
  "max_radial_engagement_mm": 3.0,
  "passes_exceeding_planned_ap": 2,
  "passes_exceeding_tool_limit": 0,
  "finishing_passes_removing_nothing": 3,
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
  "inner_gouges": [],
  "feed_moves_below_part_extent": 0
 }
}
```

Simulator default stock (80 mm): {"rapids_into_stock": 4, "rapid_penetration_max_mm": 27.525, "max_radial_engagement_mm": 28.0, "passes_exceeding_planned_ap": 2, "passes_exceeding_tool_limit": 2, "finishing_passes_removing_nothing": 3, "outer_gouges": [{"z_from": 120.28, "z_to": 122.25, "max_mm": 0.2, "steps": [4], "reference_features": ["R04", "R05"]}], "inner_gouges": [], "feed_moves_below_part_extent": 0}

## Free-text-dimension configuration

Accounting: {"handed": 27, "serialised": 13, "refused": 14, "serialised_steps": [3, 4, 5, 7, 8, 10, 11, 12, 14, 15, 17, 18, 24], "refused_steps": [1, 2, 6, 9, 13, 16, 21, 22, 23, 25, 26, 27, 28, 29], "unrecorded_refusals": [], "passed": true, "problems": []}

Newly serialised steps: [{"step": 7, "operation": "rough_turning", "feature_id": 15, "feature_type": "Cylinder", "dimensions": {"\u00d8": 23.2, "R": 11.6, "L": 46.5}, "location_z": 61.8}, {"step": 8, "operation": "rough_turning", "feature_id": 16, "feature_type": "Cylinder", "dimensions": {"\u00d8": 24.0, "R": 12.0, "L": 37.5}, "location_z": 18.75}, {"step": 14, "operation": "finish_turning", "feature_id": 15, "feature_type": "Cylinder", "dimensions": {"\u00d8": 23.2, "R": 11.6, "L": 46.5}, "location_z": 61.8}, {"step": 15, "operation": "finish_turning", "feature_id": 16, "feature_type": "Cylinder", "dimensions": {"\u00d8": 24.0, "R": 12.0, "L": 37.5}, "location_z": 18.75}]

Summary of its material check: {
 "rapids_into_stock": 5,
 "rapid_penetration_max_mm": 2.525,
 "max_radial_engagement_mm": 3.4,
 "passes_exceeding_planned_ap": 4,
 "passes_exceeding_tool_limit": 0,
 "finishing_passes_removing_nothing": 5,
 "outer_gouges": [
  {
   "z_from": 80.51,
   "z_to": 87.05,
   "max_mm": 0.875,
   "steps": [
    7
   ],
   "reference_features": [
    "R01"
   ]
  },
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
 "inner_gouges": [],
 "feed_moves_below_part_extent": 2
}

Feed moves below the part's axial extent: [{"line": 58, "step": 7, "z_from": 38.55, "z_to": 87.05, "radial_engagement_mm": 3.4}, {"line": 66, "step": 8, "z_from": 0.0, "z_to": 39.5, "radial_engagement_mm": 3.0}]

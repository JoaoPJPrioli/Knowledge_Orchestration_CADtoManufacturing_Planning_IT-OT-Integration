# R1-7: reasoning ablation on the 22 reference entities

Rule counts: {"feature_operation": 18, "parameter": 17, "tool": 1}

| Variant | Halted | Steps | Approved | Withheld | With parameters | With tool | Requests by reason | Tool provenance |
|---|---|---|---|---|---|---|---|---|
| reference | False | 32 | 27 | 5 | 32 | 32 | {"low_confidence_mapping": 6, "orientation_incompatible": 2, "machine_incompatible": 3} | {"preferred_tool_selection": 9, "feature_tool_from_operation": 23} |
| reasoner_off | False | 0 | 0 | 0 | 0 | 0 | {"missing_knowledge": 22, "low_confidence_mapping": 3} | {} |
| no_feature_operation_rules | False | 0 | 0 | 0 | 0 | 0 | {"missing_knowledge": 22, "low_confidence_mapping": 3} | {} |
| no_parameter_rules | False | 32 | 0 | 32 | 0 | 32 | {"low_confidence_mapping": 6, "missing_knowledge": 32, "orientation_incompatible": 2, "machine_incompatible": 3} | {"preferred_tool_selection": 9, "feature_tool_from_operation": 23} |
| no_tool_rule | False | 32 | 0 | 32 | 32 | 0 | {"low_confidence_mapping": 6, "missing_knowledge": 32, "orientation_incompatible": 2, "machine_incompatible": 3} | {"none": 32} |

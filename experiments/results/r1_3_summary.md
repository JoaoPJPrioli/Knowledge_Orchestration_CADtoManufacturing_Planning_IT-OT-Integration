# R1-3: confidence against decision-relevant correctness (in-sample probe, 22 entities)

| Roles | Predictor | Brier | Range | Reviewed at c < 0.5 | Wrong routed to review | Correct routed to review |
|---|---|---|---|---|---|---|
| reference | policy | 0.330 | 0.4 to 1.0 | 3 | 0 of 7 | 3 |
| reference | base_rate_loo | 0.238 | 0.667 to 0.714 | 0 | 0 of 7 | 0 |
| reference | reconciliation_class_loo | 0.239 | 0.5 to 0.778 | 0 | 0 of 7 | 0 |
| reference | agent_set_loo | 0.267 | 0.333 to 0.75 | 1 | 0 of 7 | 1 |
| swapped_roles | policy | 0.178 | 0.4 to 1.0 | 11 | 4 of 5 | 7 |
| swapped_roles | base_rate_loo | 0.193 | 0.762 to 0.81 | 0 | 0 of 5 | 0 |
| swapped_roles | reconciliation_class_loo | 0.196 | 0.583 to 0.889 | 0 | 0 of 5 | 0 |
| swapped_roles | agent_set_loo | 0.233 | 0.333 to 0.833 | 1 | 0 of 5 | 1 |

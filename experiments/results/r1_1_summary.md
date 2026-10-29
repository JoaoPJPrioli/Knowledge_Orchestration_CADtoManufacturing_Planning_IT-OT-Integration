# R1-1: engineered procedural planner and knowledge-change study

Equivalence on the 22 reference entities: identical steps True, identical requests True; reasoner 32 steps (27 approved) in 2.061 s, EPP 32 steps in 0.0 s. Reference attribution audit: {'records_checked': 32, 'misattributed': 0, 'cases': []}. Provenance identical under the attribution fix: True.

| ID | Event | Reasoner: knowledge edit | code | intent met | EPP: knowledge edit | code | intent met |
|---|---|---|---|---|---|---|---|
| S1 | New work material (AISI 4140) with four material-specific parameter sets | +47/-0 triples, +4/-0 rules | 1 | True | +9/-0 entries, 0 fields (57 values) | 0 | True |
| S2 | New feature class (tapered hole) under an existing class, no new rule | +2/-0 triples, +0/-0 rules | 1 | True | +2/-0 entries, 0 fields (2 values) | 0 | True |
| S3 | Hierarchy refactoring: blind and through holes become hole subclasses; two specific drilling rules retired | +2/-2 triples, +0/-2 rules | 0 | True | +2/-4 entries, 0 fields (10 values) | 0 | True |
| S4 | Contradictory knowledge: a second steel-drilling parameter rule | +0/-0 triples, +1/-0 rules | 0 | True | +1/-0 entries, 0 fields (4 values) | 0 | True |
| S5 | Class-specific override: blind holes in steel drilled with their own parameter set | +11/-0 triples, +1/-0 rules | 0 | False | +2/-0 entries, 0 fields (15 values) | 0 | False |
| S6 | Machine limit change: spindle safety limit lowered to 850 rpm | +1/-1 triples, +0/-0 rules | 0 | True | +0/-0 entries, 1 fields (1 values) | 0 | True |
| S7 | Tool retired from an operation: chamfer mill no longer used for chamfering on the lathe | +0/-1 triples, +0/-0 rules | 0 | True | +0/-1 entries, 0 fields (1 values) | 0 | True |
| S8 | New tool with a recorded preference: carbide drill preferred for drilling | +5/-0 triples, +0/-0 rules | 1 | True | +1/-0 entries, 1 fields (3 values) | 0 | True |
| S9 | New operation (reaming of through holes) with tool, parameters, and machine capability | +21/-0 triples, +2/-0 rules | 2 | True | +6/-0 entries, 0 fields (24 values) | 0 | True |
| S10 | Copy-paste error: a second spindle-speed value recorded for the steel drilling set | +1/-0 triples, +0/-0 rules | 0 | True | +1/-0 entries, 0 fields (10 values) | 0 | False |
| S11 | Rule refactoring with identical values: a blind-hole drilling set equal to the general one | +11/-0 triples, +1/-0 rules | 0 | False | +2/-0 entries, 0 fields (15 values) | 0 | True |
| S12 | Disjointness axioms (external turned versus internal hole features), then a counterbore mis-filed under Step | +16/-0 triples, +0/-0 rules | 0 | True | +16/-0 entries, 0 fields (31 values) | 0 | False |

Details:

- S1: reasoner: 0 steps with wrong 4140 values; statuses as reference: True | EPP: 0 steps with wrong 4140 values; statuses as reference: True
  - reasoner attribution audit: {'records_checked': 32, 'misattributed': 0, 'cases': []}
- S2: reasoner: new entity steps: [('DrillingOp', 'auto_approved')] | EPP: new entity steps: [('DrillingOp', 'auto_approved')]
  - reasoner attribution audit: {'records_checked': 33, 'misattributed': 0, 'cases': []}
- S3: reasoner: plan identical: True; drilling provenance: ['hole_requires_drilling'] | EPP: plan identical: True; drilling provenance: ['hole_requires_drilling']
  - reasoner attribution audit: {'records_checked': 32, 'misattributed': 0, 'cases': []}
- S4: reasoner: 7 of 7 drilling steps withheld; 7 rule_conflict requests | EPP: 7 of 7 drilling steps withheld; 7 rule_conflict requests
  - reasoner attribution audit: {'records_checked': 25, 'misattributed': 0, 'cases': []}
- S5: reasoner: blind-hole drilling at 700 rpm: False; other drilling at 900 rpm: True; rule_conflict requests: 1 | EPP: blind-hole drilling at 700 rpm: False; other drilling at 900 rpm: True; rule_conflict requests: 7
  - reasoner remedy: {'triples_added': 11, 'triples_removed': 0, 'rules_added': 5, 'rules_removed': 1, 'file_lines_changed': 18}, code 0 lines, intent met True: blind-hole drilling at 700 rpm: True; other drilling at 900 rpm: True; rule_conflict requests: 0
  - epp remedy: SpecificityPlanner, code 13 lines, intent met True: blind-hole drilling at 700 rpm: True; other drilling at 900 rpm: True; rule_conflict requests: 0
  - reasoner attribution audit: {'records_checked': 31, 'misattributed': 0, 'cases': []}
- S6: reasoner: 22 steps above 850 rpm, all withheld as unsafe_value: True; others unchanged: True | EPP: 22 steps above 850 rpm, all withheld as unsafe_value: True; others unchanged: True
  - reasoner attribution audit: {'records_checked': 32, 'misattributed': 0, 'cases': []}
- S7: reasoner: chamfer tools: ['ChamferDrill'] | EPP: chamfer tools: ['ChamferDrill']
  - reasoner attribution audit: {'records_checked': 32, 'misattributed': 0, 'cases': []}
- S8: reasoner: drilling tools: ['CarbideDrill']; missing_knowledge requests: 0 | EPP: drilling tools: ['CarbideDrill']; missing_knowledge requests: 0
  - reasoner attribution audit: {'records_checked': 32, 'misattributed': 0, 'cases': []}
- S9: reasoner: reaming steps on features [11, 12]; withheld for orientation: [11, 12] | EPP: reaming steps on features [11, 12]; withheld for orientation: [11, 12]
  - reasoner attribution audit: {'records_checked': 34, 'misattributed': 0, 'cases': []}
- S10: reasoner: halted: SKL ontology is inconsistent after asserting case facts: ERROR: Ontology is inconsistent, run "pellet explain" to get th | EPP: not halted; drilling spindle speeds emitted: [1200.0]
  - epp remedy: UniquenessPlanner, code 11 lines, intent met True: halted: parameter set 'AISI1045_Drilling_Params' recorded twice with different values
- S11: reasoner: plan identical: True; attribution audit: {'records_checked': 32, 'misattributed': 1, 'cases': [{'step': 17, 'feature_id': 7, 'used_set': 'AISI1045_BlindHoleDrilling_Params', 'named_rule': 'aisi1045_drilling_params', 'named_rule_concludes': 'AISI1045_Drilling_Params'}]} | EPP: plan identical: True; attribution audit: None
  - reasoner with attribution fix: {'meets_intent': True, 'detail': "plan identical: True; attribution audit: {'records_checked': 32, 'misattributed': 0, 'cases': []}", 'attribution_audit': {'records_checked': 32, 'misattributed': 0, 'cases': []}}
  - reasoner attribution audit: {'records_checked': 32, 'misattributed': 1, 'cases': [{'step': 17, 'feature_id': 7, 'used_set': 'AISI1045_BlindHoleDrilling_Params', 'named_rule': 'aisi1045_drilling_params', 'named_rule_concludes': 'AISI1045_Drilling_Params'}]}
- S12: reasoner: halted: SKL ontology is inconsistent after asserting case facts: ERROR: Ontology is inconsistent, run "pellet explain" to get the reason | EPP: not halted; 34 steps; counterbore entity steps: [(8, 'RoughTurningOp', 'auto_approved'), (8, 'FinishTurningOp', 'auto_approved'), (8, 'DrillingOp', 'auto_approved'), (8, 'CounterboringOp', 'auto_approved')]
  - epp remedy: DisjointnessPlanner, code 11 lines, intent met True: halted: entity 8 (Counterbore) instantiates disjoint classes ['Counterbore', 'Step']
  - control axioms_only: reasoner {'triples_added': 15, 'triples_removed': 0, 'rules_added': 0, 'rules_removed': 0, 'file_lines_changed': 45}, identical to reference True (not halted; 32 steps; counterbore entity steps: [(8, 'DrillingOp', 'auto_approved'), (8, 'CounterboringOp', 'auto_approved')]); EPP {'entries_added': 15, 'entries_removed': 0, 'fields_changed': 0, 'leaf_values': 30}, identical True; planners agree True
  - control misfiling_without_axioms: reasoner {'triples_added': 1, 'triples_removed': 0, 'rules_added': 0, 'rules_removed': 0, 'file_lines_changed': 1}, identical to reference False (not halted; 34 steps; counterbore entity steps: [(8, 'RoughTurningOp', 'auto_approved'), (8, 'FinishTurningOp', 'auto_approved'), (8, 'DrillingOp', 'auto_approved'), (8, 'CounterboringOp', 'auto_approved')]); EPP {'entries_added': 1, 'entries_removed': 0, 'fields_changed': 0, 'leaf_values': 1}, identical False; planners agree True

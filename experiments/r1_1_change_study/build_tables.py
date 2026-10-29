"""Derive the knowledge tables of the engineered procedural planner (EPP).

The tables are extracted mechanically from the same sources the reasoner
uses: the asserted facts of the foundation and case ontologies (no inference)
and the SWRL rule file. Every row carries the identifier of the rule or
individual it came from, so the EPP can log provenance per decision.

The three vocabulary maps that the pipeline keeps as Python dictionaries
(feature label -> class, material key -> individual, OWL name -> legacy id)
are stored here as data, which is a design choice of the EPP.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import use_repo  # noqa: E402

use_repo()
import skl_repository as skl  # noqa: E402


def _name(x):
    return getattr(x, "name", None)


def build_tables(repo=None, rules_file=None):
    repo = repo or skl.SKLRepository()
    rules = skl._parse_rules(rules_file or skl.RULES_FILE)
    po, to, mo, pa, pr = repo.process_onto, repo.tools_onto, repo.machines_onto, repo.params_onto, repo.profiles_onto

    classes = {}
    for c in po.Feature.descendants():
        if c is po.Feature:
            continue
        classes[c.name] = sorted(_name(p) for p in c.is_a if _name(p) and _name(p) != "Thing")

    feature_rules, param_rules, other_rules = [], [], []
    for r in rules:
        if r.consequent_property == "requiresOperation":
            feature_rules.append({"id": r.rule_id, "class": r.antecedent_classes[0], "operation": r.consequent_object})
        elif r.consequent_property == "hasCuttingParameterSet":
            param_rules.append({"id": r.rule_id, "material": r.material_individual or "*",
                                "operation": r.op_individual, "pset": r.consequent_object})
        else:
            other_rules.append(r.rule_id)

    operations = {}
    for op in po.Operation.instances():
        operations[op.name] = {
            "legacy_id": skl.OWL_OPERATION_TO_LEGACY_ID.get(op.name, op.name),
            "precedence": op.hasPrecedenceOrder,
            "requires_tool_along_axis": bool(getattr(op, "requiresToolAlongFeatureAxis", False)),
            "preferred_tool": _name(getattr(op, "hasPreferredTool", None)),
        }
    tools = {}
    for t in to.Tool.instances():
        tools[t.name] = {"legacy_id": skl.OWL_TOOL_TO_LEGACY_ID.get(t.name, t.name),
                         "recommended_for": sorted(_name(o) for o in t.recommendedForOperation)}
    psets = []
    for p in pa.CuttingParameterSet.instances():
        psets.append({"name": p.name, "operation": _name(p.forOperation), "material": _name(p.forMaterial),
                      "feed_rate": p.hasFeedRateValue, "feed_rate_unit": p.hasFeedRateUnit,
                      "spindle_speed": p.hasSpindleSpeedValue, "spindle_speed_unit": p.hasSpindleSpeedUnit,
                      "depth_of_cut": p.hasDepthOfCutValue, "depth_of_cut_unit": p.hasDepthOfCutUnit,
                      "coolant": p.requiresCoolant})
    machines = {}
    for key, ind in skl.MACHINE_KEY_TO_INDIVIDUAL.items():
        m = getattr(mo, ind, None)
        if m is None:
            continue
        machines[key] = {"individual": ind,
                         "supports_operation": sorted(_name(o) for o in m.supportsOperation),
                         "tool_orientations": sorted(_name(o) for o in getattr(m, "supportsToolOrientation", [])),
                         "spindle_axis": getattr(m, "hasSpindleAxis", None),
                         "limits": {"feed_rate": m.hasSafetyMaxFeedRate, "spindle_speed": m.hasSafetyMaxRPM,
                                    "depth_of_cut": m.hasSafetyMaxDepthOfCut}}
    # disjointness axioms among feature classes, as unordered pairs (none in the reference ontology)
    disjoint = []
    for ax in po.disjoint_classes():
        names = sorted(_name(e) for e in ax.entities if _name(e))
        disjoint += [[a, b] for i, a in enumerate(names) for b in names[i + 1:] if [a, b] not in disjoint]
    profiles = {p.name: sorted(_name(o) for o in getattr(p, "profileSupportsToolOrientation", []))
                for p in pr.individuals() if hasattr(p, "profileSupportsToolOrientation")}
    return {
        "labels": dict(skl.FEATURE_TYPE_TO_CLASS),
        "materials": dict(skl.MATERIAL_KEY_TO_INDIVIDUAL),
        "classes": classes,
        "feature_rules": feature_rules,
        "param_rules": param_rules,
        "tool_rule": other_rules,
        "operations": operations,
        "tools": tools,
        "psets": psets,
        "machines": machines,
        "profiles": profiles,
        "disjoint": disjoint,
    }

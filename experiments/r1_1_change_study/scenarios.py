"""Knowledge-change scenarios applied to both planners.

Each scenario states, before either planner is run:
  * the maintenance event and the engineering intent (the oracle);
  * the edit to the ontology and rule files (reasoner path), as a knowledge
    engineer would make it, plus any Python vocabulary entries the current
    implementation requires;
  * the edit to the knowledge tables (EPP), plus any EPP code extension.

The oracle is a function of the normalised plan only, applied identically to
both planners' output.
"""
import copy

from r1_1_change_study.owl_harness import insert_before_rdf_end, replace_text, add_rules, remove_rules

MP = "http://onto.brep.org/manufacturing/machining-process#"
MAT = "http://onto.brep.org/manufacturing/materials#"
TL = "http://onto.brep.org/manufacturing/tools#"
CP = "http://onto.brep.org/manufacturing/cutting-parameters#"
XSD = "http://www.w3.org/2001/XMLSchema#"
F = "foundation/"


def pset_xml(name, op, mat, feed, rpm, doc, coolant="true"):
    return f'''<owl:NamedIndividual rdf:about="#{name}">
  <rdf:type rdf:resource="#CuttingParameterSet"/>
  <forMaterial rdf:resource="{MAT}{mat}"/>
  <forOperation rdf:resource="{MP}{op}"/>
  <hasFeedRateValue rdf:datatype="{XSD}decimal">{feed}</hasFeedRateValue>
  <hasFeedRateUnit rdf:datatype="{XSD}string">mm/rev</hasFeedRateUnit>
  <hasSpindleSpeedValue rdf:datatype="{XSD}decimal">{rpm}</hasSpindleSpeedValue>
  <hasSpindleSpeedUnit rdf:datatype="{XSD}string">RPM</hasSpindleSpeedUnit>
  <hasDepthOfCutValue rdf:datatype="{XSD}decimal">{doc}</hasDepthOfCutValue>
  <hasDepthOfCutUnit rdf:datatype="{XSD}string">mm</hasDepthOfCutUnit>
  <requiresCoolant rdf:datatype="{XSD}boolean">{coolant}</requiresCoolant>
</owl:NamedIndividual>'''


def pset_row(name, op, mat, feed, rpm, doc, coolant=True):
    return {"name": name, "operation": op, "material": mat, "feed_rate": feed, "feed_rate_unit": "mm/rev",
            "spindle_speed": rpm, "spindle_speed_unit": "RPM", "depth_of_cut": doc,
            "depth_of_cut_unit": "mm", "coolant": coolant}


def param_rule(rid, op, mat, pset, cls=None):
    ante = f"{cls}(?f)" if cls else "Feature(?f)"
    mat_atom = f" ^ madeOfMaterial(?f, {mat})" if mat else ""
    return f"{rid}: {ante} ^ requiresOperation(?f, {op}){mat_atom} -> hasCuttingParameterSet(?f, {pset})"


# ----------------------------------------------------------------------------
# Oracles (normalised plan -> (passed, detail))
# ----------------------------------------------------------------------------

def _steps(r, **kw):
    return [s for s in r["steps"] if all(s.get(k) == v for k, v in kw.items())]


def _same_as_reference(r, ref, ignore_prov=True):
    def norm(x):
        return [(s["feature_id"], s["operation"], s["tool"], tuple(sorted((s["parameters"] or {}).items())),
                 s["status"]) for s in x["steps"]]
    return norm(r) == norm(ref)


def oracle_new_material(r, ref):
    if r["halted"] or len(r["steps"]) != 32:
        return False, "halted or wrong step count"
    want = {"RoughTurningOp": 400.0, "FinishTurningOp": 750.0, "DrillingOp": 750.0, "MillingOp": 1000.0}
    bad = [s for s in r["steps"] if s["operation"] in want and s["parameters"]
           and s["parameters"]["spindle_speed"] != want[s["operation"]]]
    missing = [s for s in r["steps"] if s["operation"] in want and not s["parameters"]
               and s["status"] == "auto_approved"]
    statuses = sorted(s["status"] for s in r["steps"]) == sorted(s["status"] for s in ref["steps"])
    return (not bad and not missing and statuses), f"{len(bad)} steps with wrong 4140 values; statuses as reference: {statuses}"


def oracle_subclass(r, ref):
    new = _steps(r, feature_id=999)
    ok = (len(new) == 1 and new[0]["operation"] == "DrillingOp" and new[0]["status"] == "auto_approved"
          and new[0]["parameters"].get("spindle_speed") == 900.0)
    rest = {**r, "steps": [s for s in r["steps"] if s["feature_id"] != 999]}
    return ok and _same_as_reference(rest, ref), f"new entity steps: {[(s['operation'], s['status']) for s in new]}"


def oracle_refactor(r, ref):
    same = _same_as_reference(r, ref)
    prov = {s["provenance"]["operation"] for s in r["steps"]
            if s["feature_id"] in (7, 11, 12) and s["operation"] == "DrillingOp"}
    return same and prov == {"hole_requires_drilling"}, f"plan identical: {same}; drilling provenance: {sorted(prov)}"


def oracle_conflict(r, ref):
    d = _steps(r, operation="DrillingOp")
    withheld = [s for s in d if s["status"] == "requires_review" and not s["parameters"]]
    codes = sum(1 for q in r["requests"] if q["reason_code"] == "rule_conflict")
    return (len(d) == 7 and len(withheld) == 7 and codes == 7), f"{len(withheld)} of {len(d)} drilling steps withheld; {codes} rule_conflict requests"


def _blind(ents):
    return {e["id"] for e in ents if e["type"].lower().replace(" ", "_") == "blind_hole"}


def make_oracle_specialisation(entities):
    blind = _blind(entities)

    def oracle(r, ref):
        if r["halted"]:
            return False, "halted"
        d = _steps(r, operation="DrillingOp")
        ok_blind = all(s["parameters"].get("spindle_speed") == 700.0 for s in d if s["feature_id"] in blind)
        ok_other = all(s["parameters"].get("spindle_speed") == 900.0 for s in d
                       if s["feature_id"] not in blind and s["parameters"])
        same_status = [s["status"] for s in r["steps"]] == [s["status"] for s in ref["steps"]]
        conflicts = sum(1 for q in r["requests"] if q["reason_code"] == "rule_conflict")
        return (ok_blind and ok_other and same_status and conflicts == 0), (
            f"blind-hole drilling at 700 rpm: {ok_blind}; other drilling at 900 rpm: {ok_other}; "
            f"rule_conflict requests: {conflicts}")
    return oracle


def oracle_rpm_limit(r, ref):
    hits = [s for s in r["steps"] if s["parameters"] and s["parameters"]["spindle_speed"] > 850]
    unsafe = {(q["feature_id"], q["operation"]) for q in r["requests"] if q["reason_code"] == "unsafe_value"}
    ok = all((s["feature_id"], s["operation"]) in unsafe and s["status"] == "requires_review" for s in hits)
    others = [s for s in r["steps"] if not (s["parameters"] and s["parameters"]["spindle_speed"] > 850)]
    ref_map = {(s["feature_id"], s["operation"]): s["status"] for s in ref["steps"]}
    ok2 = all(ref_map[(s["feature_id"], s["operation"])] == s["status"] for s in others)
    return ok and ok2, f"{len(hits)} steps above 850 rpm, all withheld as unsafe_value: {ok}; others unchanged: {ok2}"


def oracle_retire_tool(r, ref):
    c = _steps(r, operation="ChamferingOp")
    ok = len(c) == 4 and all(s["tool"] == "ChamferDrill" for s in c)
    rest = {**r, "steps": [s for s in r["steps"] if s["operation"] != "ChamferingOp"]}
    ref_rest = {**ref, "steps": [s for s in ref["steps"] if s["operation"] != "ChamferingOp"]}
    return ok and _same_as_reference(rest, ref_rest), f"chamfer tools: {sorted({s['tool'] for s in c})}"


def oracle_preferred_tool(r, ref):
    d = _steps(r, operation="DrillingOp")
    ok = len(d) == 7 and all(s["tool"] == "CarbideDrill" for s in d)
    ties = sum(1 for q in r["requests"] if q["reason_code"] == "missing_knowledge")
    return ok and ties == 0, f"drilling tools: {sorted({s['tool'] for s in d})}; missing_knowledge requests: {ties}"


def oracle_new_operation(r, ref):
    ream = _steps(r, operation="ReamingOp")
    feats = sorted(s["feature_id"] for s in ream)
    withheld_orient = {q["feature_id"] for q in r["requests"]
                       if q["operation"] == "ReamingOp" and q["reason_code"] == "orientation_incompatible"}
    params = all(s["parameters"].get("spindle_speed") == 300.0 for s in ream)
    ok = feats == [11, 12] and withheld_orient == {11, 12} and params
    rest = {**r, "steps": [s for s in r["steps"] if s["operation"] != "ReamingOp"]}
    return ok and len(rest["steps"]) == 32, f"reaming steps on features {feats}; withheld for orientation: {sorted(withheld_orient)}"


def oracle_duplicate_value(r, ref):
    return r["halted"], ("halted: " + r.get("error", "")[:120]) if r["halted"] else (
        "not halted; drilling spindle speeds emitted: "
        f"{sorted({s['parameters'].get('spindle_speed') for s in _steps(r, operation='DrillingOp') if s['parameters']})}")


def oracle_attribution(r, ref):
    """Plan unchanged, and every recorded parameter rule is one that entails the
    recorded parameter set (checked by the inspector for the reasoner path)."""
    same = _same_as_reference(r, ref)
    audit = r.get("attribution_audit")
    exact = audit is None or audit["misattributed"] == 0
    return same and exact, f"plan identical: {same}; attribution audit: {audit}"


def oracle_misfiled_class(r, ref):
    """A class mis-filed under a disjoint class must stop planning, not change the plan."""
    if r["halted"]:
        return True, "halted: " + r.get("error", "")[:160]
    extra = [(s["feature_id"], s["operation"], s["status"]) for s in r["steps"] if s["feature_id"] == 8]
    return False, f"not halted; {len(r['steps'])} steps; counterbore entity steps: {extra}"


# ----------------------------------------------------------------------------
# Scenario definitions
# ----------------------------------------------------------------------------

def tapered_entity():
    return {"id": 999, "type": "Tapered Hole", "description": "injected", "orientation": "Along Z-axis",
            "absolute_location": {"X": 0.0, "Y": 0.0, "Z": 100.0}, "dimensions": {"Ø": 5.0},
            "match_confidence": 1.0, "reconciliation": "primary_only"}


def scenarios(entities):
    S = []

    # S1 new work material -----------------------------------------------------
    new_sets = [("AISI4140_RoughTurning_Params", "RoughTurningOp", 0.2, 400.0, 1.5),
                ("AISI4140_FinishTurning_Params", "FinishTurningOp", 0.05, 750.0, 0.2),
                ("AISI4140_Drilling_Params", "DrillingOp", 0.12, 750.0, 4.0),
                ("AISI4140_Milling_Params", "MillingOp", 0.04, 1000.0, 0.8)]
    owl = [insert_before_rdf_end(F + "materials.owl",
                                 '<owl:NamedIndividual rdf:about="#AISI4140Steel">\n  <rdf:type rdf:resource="#Material"/>\n'
                                 f'  <hasMaterialLabel rdf:datatype="{XSD}string">AISI 4140 Steel</hasMaterialLabel>\n</owl:NamedIndividual>'),
           insert_before_rdf_end(F + "cutting_parameters.owl",
                                 "\n\n".join(pset_xml(n, o, "AISI4140Steel", f, s, d) for n, o, f, s, d in new_sets)),
           add_rules([param_rule(n.lower().replace("_params", "_params"), o, "AISI4140Steel", n) for n, o, *_ in new_sets])]

    def epp(t):
        t["materials"]["steel_4140"] = "AISI4140Steel"
        for n, o, f, s, d in new_sets:
            t["psets"].append(pset_row(n, o, "AISI4140Steel", f, s, d))
            t["param_rules"].append({"id": n.lower(), "material": "AISI4140Steel", "operation": o, "pset": n})
    S.append({"id": "S1", "event": "New work material (AISI 4140) with four material-specific parameter sets",
              "material": "steel_4140", "owl_edits": owl,
              "owl_code": {"MATERIAL_KEY_TO_INDIVIDUAL": {"steel_4140": "AISI4140Steel"}},
              "epp_edit": epp, "oracle": oracle_new_material})

    # S2 new feature subclass and extractor label ---------------------------
    owl = [insert_before_rdf_end(F + "machining_process.owl",
                                 '<owl:Class rdf:about="#TaperedHole">\n  <rdfs:subClassOf rdf:resource="#HoleFeature"/>\n</owl:Class>')]

    def epp(t):
        t["classes"]["TaperedHole"] = ["HoleFeature"]
        t["labels"]["tapered_hole"] = "TaperedHole"
    S.append({"id": "S2", "event": "New feature class (tapered hole) under an existing class, no new rule",
              "entities": entities + [tapered_entity()], "owl_edits": owl,
              "owl_code": {"FEATURE_TYPE_TO_CLASS": {"tapered_hole": "TaperedHole"}},
              "epp_edit": epp, "oracle": oracle_subclass})

    # S3 hierarchy refactoring ---------------------------------------------
    owl = [replace_text(F + "machining_process.owl",
                        '<owl:Class rdf:about="#BlindHole">\n  <rdfs:subClassOf rdf:resource="#Feature"/>',
                        '<owl:Class rdf:about="#BlindHole">\n  <rdfs:subClassOf rdf:resource="#HoleFeature"/>'),
           replace_text(F + "machining_process.owl",
                        '<owl:Class rdf:about="#ThroughHole">\n  <rdfs:subClassOf rdf:resource="#Feature"/>',
                        '<owl:Class rdf:about="#ThroughHole">\n  <rdfs:subClassOf rdf:resource="#HoleFeature"/>'),
           remove_rules(["blindhole_requires_drilling", "throughhole_requires_drilling"])]

    def epp(t):
        t["classes"]["BlindHole"] = ["HoleFeature"]
        t["classes"]["ThroughHole"] = ["HoleFeature"]
        t["feature_rules"] = [r for r in t["feature_rules"]
                              if r["id"] not in ("blindhole_requires_drilling", "throughhole_requires_drilling")]
    S.append({"id": "S3", "event": "Hierarchy refactoring: blind and through holes become hole subclasses; two specific drilling rules retired",
              "owl_edits": owl, "epp_edit": epp, "oracle": oracle_refactor})

    # S4 contradictory duplicate rule -------------------------------------
    rule = param_rule("aisi1045_drilling_params_alt", "DrillingOp", "AISI1045Steel", "Aluminum6061_Drilling_Params")

    def epp(t):
        t["param_rules"].append({"id": "aisi1045_drilling_params_alt", "material": "AISI1045Steel",
                                 "operation": "DrillingOp", "pset": "Aluminum6061_Drilling_Params"})
    S.append({"id": "S4", "event": "Contradictory knowledge: a second steel-drilling parameter rule",
              "owl_edits": [add_rules([rule])], "epp_edit": epp, "oracle": oracle_conflict})

    # S5 class-specific override (deep blind holes) -------------------------
    bh = "AISI1045_BlindHoleDrilling_Params"
    owl = [insert_before_rdf_end(F + "cutting_parameters.owl", pset_xml(bh, "DrillingOp", "AISI1045Steel", 0.10, 700.0, 3.0)),
           add_rules([param_rule("aisi1045_blindhole_drilling_params", "DrillingOp", "AISI1045Steel", bh, cls="BlindHole")])]

    def epp(t):
        t["psets"].append(pset_row(bh, "DrillingOp", "AISI1045Steel", 0.10, 700.0, 3.0))
        t["param_rules"].append({"id": "aisi1045_blindhole_drilling_params", "material": "AISI1045Steel",
                                 "operation": "DrillingOp", "pset": bh, "class": "BlindHole"})
    oracle5 = make_oracle_specialisation(entities)
    # Remedy in OWL/SWRL (monotonic, no override): replace the general rule by
    # class-specific rules for every other class that requires drilling.
    drill_classes = ["HoleFeature", "Bore", "Counterbore", "ThroughHole"]
    owl_remedy = owl + [remove_rules(["aisi1045_drilling_params"]),
                        add_rules([param_rule(f"aisi1045_{c.lower()}_drilling_params", "DrillingOp", "AISI1045Steel",
                                              "AISI1045_Drilling_Params", cls=c) for c in drill_classes])]
    S.append({"id": "S5", "event": "Class-specific override: blind holes in steel drilled with their own parameter set",
              "owl_edits": owl, "epp_edit": epp, "oracle": oracle5,
              "owl_remedy": owl_remedy, "epp_remedy_class": "SpecificityPlanner"})

    # S6 machine limit change ---------------------------------------------
    owl = [replace_text(F + "machines.owl",
                        f'<hasSafetyMaxRPM rdf:datatype="{XSD}decimal">4500.0</hasSafetyMaxRPM>',
                        f'<hasSafetyMaxRPM rdf:datatype="{XSD}decimal">850.0</hasSafetyMaxRPM>')]

    def epp(t):
        t["machines"]["cnc_lathe"]["limits"]["spindle_speed"] = 850.0
    S.append({"id": "S6", "event": "Machine limit change: spindle safety limit lowered to 850 rpm",
              "owl_edits": owl, "epp_edit": epp, "oracle": oracle_rpm_limit})

    # S7 retire a tool from an operation ---------------------------------------
    owl = [replace_text(F + "tools.owl",
                        '<owl:NamedIndividual rdf:about="#ChamferMill">\n  <rdf:type rdf:resource="#Tool"/>\n'
                        f'  <recommendedForOperation rdf:resource="{MP}ChamferingOp"/>\n',
                        '<owl:NamedIndividual rdf:about="#ChamferMill">\n  <rdf:type rdf:resource="#Tool"/>\n')]

    def epp(t):
        t["tools"]["ChamferMill"]["recommended_for"].remove("ChamferingOp")
    S.append({"id": "S7", "event": "Tool retired from an operation: chamfer mill no longer used for chamfering on the lathe",
              "owl_edits": owl, "epp_edit": epp, "oracle": oracle_retire_tool})

    # S8 new tool with recorded preference ------------------------------------
    owl = [insert_before_rdf_end(F + "tools.owl",
                                 '<owl:NamedIndividual rdf:about="#CarbideDrill">\n  <rdf:type rdf:resource="#Tool"/>\n'
                                 f'  <recommendedForOperation rdf:resource="{MP}DrillingOp"/>\n'
                                 f'  <hasToolMaterial rdf:datatype="{XSD}string">Carbide</hasToolMaterial>\n</owl:NamedIndividual>\n\n'
                                 f'<rdf:Description rdf:about="{MP}DrillingOp">\n  <hasPreferredTool rdf:resource="#CarbideDrill"/>\n</rdf:Description>')]

    def epp(t):
        t["tools"]["CarbideDrill"] = {"legacy_id": "carbide_drill", "recommended_for": ["DrillingOp"]}
        t["operations"]["DrillingOp"]["preferred_tool"] = "CarbideDrill"
    S.append({"id": "S8", "event": "New tool with a recorded preference: carbide drill preferred for drilling",
              "owl_edits": owl, "owl_code": {"OWL_TOOL_TO_LEGACY_ID": {"CarbideDrill": "carbide_drill"}},
              "epp_edit": epp, "oracle": oracle_preferred_tool})

    # S9 new operation -----------------------------------------------------
    owl = [insert_before_rdf_end(F + "machining_process.owl",
                                 '<owl:Class rdf:about="#Reaming">\n  <rdfs:subClassOf rdf:resource="#Operation"/>\n</owl:Class>\n\n'
                                 '<owl:NamedIndividual rdf:about="#ReamingOp">\n  <rdf:type rdf:resource="#Reaming"/>\n'
                                 f'  <requiresToolAlongFeatureAxis rdf:datatype="{XSD}boolean">true</requiresToolAlongFeatureAxis>\n'
                                 f'  <hasPrecedenceOrder rdf:datatype="{XSD}integer">5</hasPrecedenceOrder>\n</owl:NamedIndividual>'),
           insert_before_rdf_end(F + "tools.owl",
                                 '<owl:NamedIndividual rdf:about="#Reamer">\n  <rdf:type rdf:resource="#Tool"/>\n'
                                 f'  <recommendedForOperation rdf:resource="{MP}ReamingOp"/>\n</owl:NamedIndividual>'),
           insert_before_rdf_end(F + "cutting_parameters.owl",
                                 pset_xml("AISI1045_Reaming_Params", "ReamingOp", "AISI1045Steel", 0.2, 300.0, 0.15)),
           replace_text(F + "machines.owl",
                        f'  <supportsOperation rdf:resource="{MP}GroovingOp"/>\n',
                        f'  <supportsOperation rdf:resource="{MP}GroovingOp"/>\n  <supportsOperation rdf:resource="{MP}ReamingOp"/>\n'),
           add_rules(["throughhole_requires_reaming: ThroughHole(?f) -> requiresOperation(?f, ReamingOp)",
                      param_rule("aisi1045_reaming_params", "ReamingOp", "AISI1045Steel", "AISI1045_Reaming_Params")])]

    def epp(t):
        t["operations"]["ReamingOp"] = {"legacy_id": "reaming", "precedence": 5, "requires_tool_along_axis": True,
                                        "preferred_tool": None}
        t["tools"]["Reamer"] = {"legacy_id": "reamer", "recommended_for": ["ReamingOp"]}
        t["psets"].append(pset_row("AISI1045_Reaming_Params", "ReamingOp", "AISI1045Steel", 0.2, 300.0, 0.15))
        t["machines"]["cnc_lathe"]["supports_operation"].append("ReamingOp")
        t["feature_rules"].append({"id": "throughhole_requires_reaming", "class": "ThroughHole", "operation": "ReamingOp"})
        t["param_rules"].append({"id": "aisi1045_reaming_params", "material": "AISI1045Steel",
                                 "operation": "ReamingOp", "pset": "AISI1045_Reaming_Params"})
    S.append({"id": "S9", "event": "New operation (reaming of through holes) with tool, parameters, and machine capability",
              "owl_edits": owl,
              "owl_code": {"OWL_OPERATION_TO_LEGACY_ID": {"ReamingOp": "reaming"},
                           "OWL_TOOL_TO_LEGACY_ID": {"Reamer": "reamer"}},
              "epp_edit": epp, "oracle": oracle_new_operation})

    # S10 duplicated value (copy-paste error) ---------------------------------
    anchor = '<owl:NamedIndividual rdf:about="#AISI1045_Drilling_Params">\n  <rdf:type rdf:resource="#CuttingParameterSet"/>\n'
    owl = [replace_text(F + "cutting_parameters.owl", anchor,
                        anchor + f'  <hasSpindleSpeedValue rdf:datatype="{XSD}decimal">1200.0</hasSpindleSpeedValue>\n')]

    def epp(t):
        row = copy.deepcopy(next(r for r in t["psets"] if r["name"] == "AISI1045_Drilling_Params"))
        row["spindle_speed"] = 1200.0
        t["psets"].append(row)
    S.append({"id": "S10", "event": "Copy-paste error: a second spindle-speed value recorded for the steel drilling set",
              "owl_edits": owl, "epp_edit": epp, "oracle": oracle_duplicate_value,
              "epp_remedy_class": "UniquenessPlanner", "remedy_on_same_edit": True})

    # S11 rule refactoring with identical values (attribution) -------------
    bh2 = "AISI1045_BlindHoleDrilling_Params"
    owl = [insert_before_rdf_end(F + "cutting_parameters.owl", pset_xml(bh2, "DrillingOp", "AISI1045Steel", 0.15, 900.0, 5.0)),
           add_rules([param_rule("aisi1045_blindhole_drilling_params", "DrillingOp", "AISI1045Steel", bh2, cls="BlindHole")])]

    def epp(t):
        t["psets"].append(pset_row(bh2, "DrillingOp", "AISI1045Steel", 0.15, 900.0, 5.0))
        t["param_rules"].append({"id": "aisi1045_blindhole_drilling_params", "material": "AISI1045Steel",
                                 "operation": "DrillingOp", "pset": bh2, "class": "BlindHole"})
    S.append({"id": "S11", "event": "Rule refactoring with identical values: a blind-hole drilling set equal to the general one",
              "owl_edits": owl, "epp_edit": epp, "oracle": oracle_attribution, "attribution_audit": True})

    # S12 disjointness axioms, then a mis-filed class ----------------------------
    # Protective knowledge: external turned features and internal hole features
    # are disjoint (a feature removes material either outside or inside the part).
    external = ["Boss", "Cylinder", "Step"]
    internal = ["BlindHole", "Bore", "Counterbore", "HoleFeature", "ThroughHole"]
    pairs = [[a, b] for a in external for b in internal]
    axioms = [insert_before_rdf_end(F + "machining_process.owl", "\n".join(
        f'<rdf:Description rdf:about="{MP}{a}">\n  <owl:disjointWith rdf:resource="{MP}{b}"/>\n</rdf:Description>'
        for a, b in pairs))]
    # Mis-edit: a refactoring files the counterbore, a stepped hole, under Step.
    misfile = [replace_text(F + "machining_process.owl",
                            '<owl:Class rdf:about="#Counterbore">\n  <rdfs:subClassOf rdf:resource="#Feature"/>\n',
                            '<owl:Class rdf:about="#Counterbore">\n  <rdfs:subClassOf rdf:resource="#Feature"/>\n'
                            '  <rdfs:subClassOf rdf:resource="#Step"/>\n')]

    def epp_axioms(t):
        t["disjoint"] = t.get("disjoint", []) + [sorted(p) for p in pairs]

    def epp_misfile(t):
        t["classes"]["Counterbore"] = sorted(t["classes"]["Counterbore"] + ["Step"])

    def epp(t):
        epp_axioms(t)
        epp_misfile(t)
    S.append({"id": "S12", "event": "Disjointness axioms (external turned versus internal hole features), then a counterbore mis-filed under Step",
              "owl_edits": axioms + misfile, "epp_edit": epp, "oracle": oracle_misfiled_class,
              "epp_remedy_class": "DisjointnessPlanner", "remedy_on_same_edit": True,
              "controls": {"axioms_only": {"owl_edits": axioms, "epp_edit": epp_axioms},
                           "misfiling_without_axioms": {"owl_edits": misfile, "epp_edit": epp_misfile}}})
    return S

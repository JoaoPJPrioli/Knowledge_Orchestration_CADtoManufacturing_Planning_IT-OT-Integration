
"""expertplan_analysis.py
Reproducible support script for the reference process plan drafted by the authors.
Reads: pipeline/knowledge/foundation/{cutting_parameters,tools,machines,materials,machining_process}.owl,
       runs/reference/{manufacturing_plan,features}.json,
       pipeline/analysis/results/step_reference.json
Writes: expert_reference_plan.json, parameter_audit.json, comparison.json

Usage (from the repository root):
    python reference_plan/expertplan_analysis.py [<repository root> [<output folder>]]
All judgements are encoded explicitly (judgement ids J01 to J17) so that they can be
reviewed independently (Reference_Plan_SignOff.xlsx). Handbook ranges are candidate values
to be checked against the cited handbook.
"""
import json, math, os, re, sys, zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE)   # repository root
PIPE = os.path.join(ROOT, "pipeline")
RUN = os.path.join(ROOT, "runs", "reference")
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
KF = os.path.join(PIPE, "knowledge", "foundation")
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"

def individuals(path):
    out = {}
    for el in ET.parse(path).getroot():
        about = el.get(RDF + "about")
        if about is None:
            continue
        d = {}
        for c in el:
            tag = c.tag.split("}")[-1]
            v = c.text if (c.text and c.text.strip()) else (c.get(RDF + "resource") or "").split("#")[-1]
            d.setdefault(tag, []).append(v)
        out[about.split("#")[-1]] = d
    return out

cp = individuals(os.path.join(KF, "cutting_parameters.owl"))
tools = individuals(os.path.join(KF, "tools.owl"))
machines = individuals(os.path.join(KF, "machines.owl"))
mats = individuals(os.path.join(KF, "materials.owl"))
ops_in_onto = sorted(set(re.findall(r'rdf:about="[^"]*#(\w+Op)"',
                    open(os.path.join(KF, "machining_process.owl"), encoding="utf8").read())))
sref = json.load(open(os.path.join(PIPE, "analysis", "results", "step_reference.json"), encoding="utf-8"))
plan = json.load(open(os.path.join(RUN, "manufacturing_plan.json"), encoding="utf-8"))
feats = json.load(open(os.path.join(RUN, "features.json"), encoding="utf-8"))

# ---------------------------------------------------------------- parameter audit
SETS = {  # name in cutting_parameters.owl -> (operation, tool individual used in R1 plan)
    "AISI1045_RoughTurning_Params": ("rough_turning", "TurningInsertRough"),
    "AISI1045_FinishTurning_Params": ("finish_turning", "TurningInsertFinish"),
    "AISI1045_Drilling_Params": ("drilling", "DrillBit"),
    "Counterboring_Default_Params": ("counterboring", "CounterboreCutter"),
    "Chamfering_Default_Params": ("chamfering", "ChamferMill"),
    "Facing_Default_Params": ("facing", "TurningInsertRough"),
    "Grooving_Default_Params": ("grooving", "GroovingTool"),
    "AISI1045_Milling_Params": ("milling (added; keyway)", "EndMill"),
}
# diameters at which each set acts on this part (mm); 'role' says whose diameter it is
DIAMS = {
    "rough_turning": [(24.95, "workpiece R01"), (24.0, "workpiece R05"), (23.6, "workpiece R03 (as planned, step 4)")],
    "finish_turning": [(24.95, "workpiece R01"), (24.0, "workpiece R05 j6 seat"), (23.6, "workpiece R03 (as planned, step 11)")],
    "drilling": [(6.8, "tool, R07 tap drill"), (8.4, "tool, R08 (as planned, step 18)")],
    "counterboring": [(8.4, "tool, R08")],
    "chamfering": [(24.95, "workpiece R02"), (24.0, "workpiece R04/R10 large end"), (12.2, "tool, R09 countersink")],
    "facing": [(24.95, "workpiece, outer edge of face at R01"), (24.0, "workpiece, outer edge of DE face"), (0.0, "workpiece, centre of face")],
    "grooving": [(24.0, "workpiece, groove entry"), (23.6, "workpiece, R03 groove floor")],
    "milling (added; keyway)": [(8.0, "tool, assumed 8 mm keyway cutter (EndMill has no fixed diameter)")],
}
# CANDIDATE handbook-type ranges (m/min) for ~1045, ~200 HB. Author must verify every value.
RANGES = {
    "carbide_uncoated_turning": (90.0, 180.0, "C2,C5 (uncoated carbide, turning/roughing; web reproductions of handbook tables)"),
    "carbide_coated_turning": (150.0, 330.0, "C3,C4,C6 (coated carbide; Sandvik GC4325 CNMG 120408-PM case at 250 m/min)"),
    "carbide_coated_grooving": (150.0, 220.0, "C7 (GC4325 grooving, carbon steel 0.26-0.50 %C)"),
    "hss_drilling": (21.0, 23.0, "C1,C8 (Machinery's Handbook drilling table, 1045 group 175-225 HB: about 70-75 fpm)"),
    "carbide_holemaking_derived": (42.0, 92.0, "DERIVED: 2-4 x HSS drilling speed (C2 rule of thumb); weak, needs a direct source"),
    "carbide_endmill_steel": (100.0, 200.0, "C3 (carbide milling 1045); full-width slotting usually at reduced speed"),
}
RANGE_FOR = {
    "rough_turning": "carbide_uncoated_turning",       # tools.owl: 'Carbide'
    "finish_turning": "carbide_coated_turning",        # tools.owl: 'Carbide with Coating'
    "drilling": "hss_drilling",                        # tools.owl: 'High-Speed Steel'
    "counterboring": "carbide_holemaking_derived",     # tools.owl: 'Carbide'
    "chamfering": "carbide_uncoated_turning",          # judged as turned chamfers (J12); R09 row uses derived holemaking band
    "facing": "carbide_uncoated_turning",
    "grooving": "carbide_uncoated_turning",            # tools.owl: 'Carbide' (uncoated); coated band reported too
    "milling (added; keyway)": "carbide_endmill_steel",
}
lathe = machines["CNCLatheFanuc0iTD"]
nmax = float(lathe["hasMaxSpindleSpeedRPM"][0])
audit = []
for name, (op, tool) in SETS.items():
    p = cp[name]
    n = float(p["hasSpindleSpeedValue"][0]); f = float(p["hasFeedRateValue"][0]); ap = float(p["hasDepthOfCutValue"][0])
    for D, role in DIAMS[op]:
        key = RANGE_FOR[op]
        if op == "chamfering" and D == 12.2:
            key = "carbide_holemaking_derived"
        lo, hi, src = RANGES[key]
        vc = math.pi * D * n / 1000.0
        if vc < lo:
            verdict, factor = "below", lo / vc if vc > 0 else float("inf")
        elif vc > hi:
            verdict, factor = "above", vc / hi
        else:
            verdict, factor = "inside", 1.0
        n_needed_lo = lo * 1000.0 / (math.pi * D) if D > 0 else None
        row = dict(parameter_set=name, operation=op, tool_individual=tool,
                   tool_material=tools[tool]["hasToolMaterial"][0], tool_geometry=tools[tool]["hasGeometry"][0],
                   n_rpm=n, feed=f, feed_unit=p["hasFeedRateUnit"][0], ap_mm=ap,
                   diameter_mm=D, diameter_role=role, vc_m_per_min=round(vc, 1),
                   range_key=key, range_lo=lo, range_hi=hi, range_sources=src,
                   verdict=verdict, factor_vs_nearest_bound=(round(factor, 2) if factor != float("inf") else "inf"),
                   rpm_for_lower_bound=(round(n_needed_lo) if n_needed_lo else None),
                   lower_bound_rpm_within_machine_limit=(n_needed_lo <= nmax if n_needed_lo else None))
        if op == "grooving":
            clo, chi, csrc = RANGES["carbide_coated_grooving"]
            row["coated_grooving_band"] = [clo, chi]
            row["factor_below_coated_grooving_lo"] = round(clo / vc, 2)
        if op == "finish_turning":
            ulo, uhi, _ = RANGES["carbide_uncoated_turning"]
            row["factor_below_uncoated_lo"] = round(ulo / vc, 2) if vc < ulo else 1.0
        audit.append(row)
feed_checks = [
    dict(set="AISI1045_RoughTurning_Params", check="fn 0.25 mm/rev, ap 2.0 mm with CNMG 120408 vs Sandvik GC4325 case (CNMG 120408-PM, fn 0.3, ap 2.0)", verdict="inside (comparable)", source="C4"),
    dict(set="AISI1045_FinishTurning_Params", check="ap 0.2 mm with CNMG 120404 (nose radius 0.4 mm): ap < r_epsilon", verdict="contrary to tool-maker guidance to run ap larger than nose radius", source="C6"),
    dict(set="AISI1045_Drilling_Params", check="fn 0.15 mm/rev for 6.8 mm HSS drill vs 0.004-0.007 in/rev (0.10-0.18 mm/rev) for 1/4-1/2 in drills", verdict="inside", source="C8"),
    dict(set="AISI1045_Drilling_Params", check="hasDepthOfCutValue 5.0 mm for a 6.8 mm drill (radial engagement is 3.4 mm)", verdict="semantics undefined (peck depth?)", source="ontology"),
    dict(set="Counterboring_Default_Params", check="ap 3.0 mm vs radial engagement (8.4-6.8)/2 = 0.8 mm", verdict="semantics undefined", source="ontology"),
    dict(set="Facing_Default_Params", check="constant 800 rpm (G97) facing to centre: vc falls to 0 at X0", verdict="constant surface speed (G96 with G50 clamp) expected", source="practice (J15)"),
]
mat = mats["AISI1045Steel"]
material_note = dict(hasHardnessHRC=mat["hasHardnessHRC"][0], hasTensileStrengthMPa=mat["hasTensileStrengthMPa"][0],
                     hasMachinabilityRating=mat["hasMachinabilityRating"][0],
                     note="HRC 25 (about 250 HB) and UTS 570 MPa (typical of hot-rolled 1045, about 165-170 HB) are mutually inconsistent; author to confirm the stock condition (J01).")
provenance_note = "build_ontologies.py derives the 1045 speeds as generic base rpm x 0.6 machinability factor (e.g. 800*0.6=480, 1500*0.6=900, 2000*0.6=1200); five sets are material-independent defaults. Speeds are stored as spindle rpm, not cutting speed, so the same rpm is applied at 6.8 mm and at 24.95 mm."

# ---------------------------------------------------------------- reference plan
REF = [
 # id, setup, machine, feature, ref_id, family, tool, in_onto(op,tool), required, judgements, note
 ("10.01","S10","CNC lathe (CNCLatheFanuc0iTD)","Drive-end (DE) face, z = 168.5","F-DE","facing","CNMG 120408 rough + CNMG 120404 finish pass (TurningInsertRough / TurningInsertFinish)",(True,True),True,["J05"],"Datum face for E = 50; constant surface speed."),
 ("10.02","S10","CNC lathe","Spot/centre on axis before tap drill","R07","centre_drilling","Spot drill 90 deg or DIN 332-2 form-DS stepped centre drill",(False,False),"conditional",["J07"],"Not needed if 10.03-10.05 use one DIN 332-2 stepped centre drill."),
 ("10.03","S10","CNC lathe","Tap-drill hole d 6.8, full-diameter depth 25.0 from DE face (R07)","R07","drilling","HSS twist drill 6.8, 118 deg (DrillBit); axial peck cycle at X0",(True,True),True,["J07"],"6.8 is the M8 tap drill."),
 ("10.04","S10","CNC lathe","Counterbore d 8.4, flat floor at z = 162.5 (R08)","R08","counterboring","Flat-bottom counterbore (CounterboreCutter) or step of DIN 332-2 drill",(True,True),True,["J07","J10"],"Floor is planar in the B-Rep (PLANE at z = 162.5)."),
 ("10.05","S10","CNC lathe","60 deg countersink to d 12.2 (R09), DIN 332-2 centre seat","R09","chamfering","60 deg countersink / DIN 332-2 stepped drill; NOT in tools.owl (only 90 deg chamfer tools)",(True,False),True,["J07","J12"],"Bearing surface for tailstock live centre."),
 ("10.06","S10","CNC lathe","Engage tailstock live 60 deg centre in R09","-","setup_element","Live centre; tailstock not modelled in machines.owl",(False,False),"setup",["J05"],"Not an operation; not scored."),
 ("10.07a","S10","CNC lathe","Rough turn d 24.0 seat (R05), leave 0.2-0.3 on diameter","R05","rough_turning","CNMG 120408 (TurningInsertRough)",(True,True),True,["J01"],"From d 30 bar, two passes."),
 ("10.07b","S10","CNC lathe","Rough turn d 24.95 body (R01) back past NDE face + parting width","R01","rough_turning","CNMG 120408 (TurningInsertRough)",(True,True),True,["J01","J17"],""),
 ("10.08a","S10","CNC lathe","Undercut d 23.6 x 1.754 at shaft-end root (R03)","R03","grooving","Grooving/profiling insert of width <= 1.5 mm with corner radius, or undercut form insert; tools.owl GroovingTool is 2 mm wide",(True,False),True,["J04","J08"],"Recess below both neighbours; 15 deg run-out resembles a DIN 509 grinding relief."),
 ("10.08b","S10","CNC lathe","15 deg run-out cone d 23.6 -> 24.0 (R04)","R04","grooving|chamfering|finish_turning","Profiled with the undercut tool or in the finishing contour",(True,True),True,["J09"],"Any of the three families accepted."),
 ("10.09a","S10","CNC lathe","Finish turn d 24 j6 seat (R05): +0.009/-0.004","R05","finish_turning","CNMG 120404 (TurningInsertFinish) or 35 deg profiling insert; G42 nose-radius compensation, in-process gauging",(True,True),True,["J04"],"Optional grinding route S40."),
 ("10.09b","S10","CNC lathe","Finish turn d 24.95 body (R01)","R01","finish_turning","CNMG 120404 (TurningInsertFinish)",(True,True),True,["J17"],"General tolerance assumed."),
 ("10.09c","S10","CNC lathe","1 x 45 deg end chamfer d 24 -> 22 (R10), turned in contour","R10","chamfering","Turning insert (contour); not a chamfer mill",(True,True),True,["J12"],""),
 ("10.09d","S10","CNC lathe","0.5 x 45 deg chamfer d 24.95 -> 23.95 (R02), turned in contour","R02","chamfering","Turning insert (contour); not a chamfer mill",(True,True),True,["J12"],""),
 ("10.10","S10","CNC lathe","Tap M8 x 1.25-6H in R07 (thread depth per DIN 332-2)","R07t","tapping","HSS-E spiral-flute machine tap, rigid tapping (G84, stationary tap on centreline) or floating holder; NOT in ontology",(False,False),True,["J06"],"Tailstock retracted first."),
 ("10.11","S10","CNC lathe","Part off at z ~ 80.0 (0.5 mm facing allowance)","-","parting","Parting blade/insert; NOT in ontology",(False,False),True,["J14"],"Not needed if sawn blanks are used (J14)."),
 ("20.01","S20","CNC lathe (reversed, soft jaws on d 24.95, stop on R02 shoulder)","Non-drive-end (NDE) face to overall length 88.0, z = 80.5","F-NDE","facing","CNMG 120404 (TurningInsertFinish)",(True,True),True,["J05","J17"],"Never clamp on the j6 seat."),
 ("20.02","S20","CNC lathe","Edge break NDE outer edge (not modelled in CAD)","-","chamfering","Turning insert",(True,True),False,["J16"],"Shop practice; not scored."),
 ("30.01","S30","Vertical milling machine / VMC (NOT in machines.owl)","Keyway 8 N9 (7.964-8.000) x t1 4.0 +0.2 x 40, form A (R4 ends), z 123.5-163.5, symmetric to axis","R06","milling","2-flute carbide keyway end mill d 8 (keyway tolerance) or undersize rough + side finish; tools.owl EndMill is a generic 4-flute",(True,True),True,["J02","J03","J13"],"Replaces the catalogue CAD's fitted key (R06)."),
 ("30.02","S30","Vertical milling machine / VMC","Deburr keyway edges","R06","deburring","Hand/brush",(False,False),False,["J16"],"Not scored."),
 ("40.01","S40 (optional)","Cylindrical grinder (NOT in machines.owl)","Grind d 24 j6 seat (R05) if turning cannot hold IT6","R05","grinding","Plain wheel; undercut R03/R04 gives run-out",(False,False),False,["J04"],"Judgement; not scored."),
 ("50.01","S50","Inspection","j6 seat, run-out (IEC 60072-1 class), keyway width/depth (G = 20.0)/symmetry, M8-6H plug gauge, E = 50, GA = 27 after key fitted","-","inspection","Air gauge/micrometer, slot gauge, thread plug gauge",(False,False),False,["J03","J16"],"Not scored."),
]
ref_plan = []
for (i, s, m, ftxt, rid, fam, tool, (op_ok, tool_ok), req, js, note) in REF:
    ref_plan.append(dict(op_id=i, setup=s, machine=m, feature=ftxt, ref_feature=rid, operation_family=fam, tool=tool,
                         operation_class_in_ontology=op_ok, tool_in_tools_owl=tool_ok, required=req,
                         judgements=js, note=note))

# ---------------------------------------------------------------- scoring
# entity -> reference feature (geometric/semantic correspondence; J11 for key-region entities)
ENT2REF = {1:"R01",2:"R02",3:"R03",4:"R04",5:"R05",6:"R10",7:"R07",8:"R08",9:"R09",
           10:"KEY_FITTED",11:"R06_end_radius",12:"R06_end_radius",13:"R06",14:"R06",
           15:"R05",16:"R01",17:"R03",18:"KEY_FITTED",19:"R09",20:"R08",21:"R07",22:"R06"}
STEP_FAMILY = {e for e in range(1, 15)}   # entities from STEP-A/STEP-B records
DRW_FAMILY = {e for e in range(15, 23)}   # entities from drawing records
ACCEPT = {"R01":{"rough_turning","finish_turning"}, "R05":{"rough_turning","finish_turning"},
          "R02":{"chamfering"}, "R10":{"chamfering"}, "R09":{"chamfering"},
          "R03":{"grooving"}, "R04":{"grooving","chamfering","finish_turning"},
          "R07":{"drilling"}, "R08":{"counterboring"}, "R06":{"milling"}, "R06_end_radius":{"milling"}}
REFOP_FOR = {("R01","rough_turning"):"10.07b",("R01","finish_turning"):"10.09b",("R05","rough_turning"):"10.07a",
             ("R05","finish_turning"):"10.09a",("R02","chamfering"):"10.09d",("R10","chamfering"):"10.09c",
             ("R09","chamfering"):"10.05",("R03","grooving"):"10.08a",("R04","chamfering"):"10.08b",
             ("R04","grooving"):"10.08b",("R04","finish_turning"):"10.08b",("R07","drilling"):"10.03",
             ("R08","counterboring"):"10.04",("R06","milling"):"30.01",("R06_end_radius","milling"):"30.01"}
LATHE_UNSUITABLE_TOOLS = {"ChamferMill": "rotating milling cutter; lathe has no driven tooling (J12)",
                          "EndMill": "rotating milling cutter; needs a milling spindle"}
step_feats_planned = {}
for s in plan:
    step_feats_planned.setdefault(ENT2REF[s["feature_id"]], set()).add(s["feature_id"])
rows = []
for s in plan:
    e = s["feature_id"]; rf = ENT2REF[e]; fam = s["operation"]
    acc = ACCEPT.get(rf, set())
    if rf == "KEY_FITTED":
        base = "not_in_plan"
    elif fam in acc:
        base = "match"
    else:
        base = "wrong_family"
    planned_from_step = any(x in STEP_FAMILY for x in step_feats_planned.get(rf, set()))
    if rf == "R06":  # STEP-family slots 13,14 also map to the keyway
        planned_from_step = True
    is_dup = e in DRW_FAMILY and planned_from_step
    cls = "duplicate" if is_dup else base
    tool_issue = LATHE_UNSUITABLE_TOOLS.get(s["ontology_tool"]) if s.get("machine") == "cnc_lathe" else None
    if s["ontology_tool"] == "ChamferMill" and rf == "R09":
        tool_issue = "90 deg chamfer mill cannot form the 60 deg countersink; also needs driven tooling (J12)"
    if s["ontology_tool"] == "EndMill":
        tool_issue = None  # family correct; machine assignment is the issue (withheld)
    rows.append(dict(step=s["step_number"], operation=fam, entity=e, entity_type=s["feature_type"],
                     source_family="STEP" if e in STEP_FAMILY else "DRW", ref_feature=rf,
                     ref_op=REFOP_FOR.get((rf, fam)) if base == "match" else None,
                     classification=cls, underlying=base, status=s["validation_status"],
                     tool=s["ontology_tool"], tool_issue=tool_issue))
from collections import Counter
cnt = Counter(r["classification"] for r in rows)
cnt_appr = Counter(r["classification"] for r in rows if r["status"] == "auto_approved")
cnt_with = Counter(r["classification"] for r in rows if r["status"] != "auto_approved")
cnt_under = Counter(r["underlying"] for r in rows)
# reference-op coverage
coverage = []
for r in ref_plan:
    if r["required"] is not True:
        if r["required"] == "conditional":
            pass
        else:
            continue
    hits = [x for x in rows if x["underlying"] == "match" and x["ref_op"] == r["op_id"]]
    appr = [x for x in hits if x["status"] == "auto_approved"]
    if appr:
        state = "covered_approved"
    elif hits:
        state = "present_withheld_only"
    else:
        state = "missing"
    coverage.append(dict(op_id=r["op_id"], feature=r["feature"], family=r["operation_family"], required=r["required"],
                         state=state, steps=[x["step"] for x in hits],
                         approved_steps=[x["step"] for x in appr],
                         via_duplicate_only=bool(appr) and all(x["classification"] == "duplicate" for x in appr),
                         tool_issue_on_all_approved=bool(appr) and all(x["tool_issue"] for x in appr),
                         operation_class_in_ontology=r["operation_class_in_ontology"]))
req = [c for c in coverage if c["required"] is True]
summary = dict(
    steps_total=len(rows), by_class=dict(cnt), approved_by_class=dict(cnt_appr), withheld_by_class=dict(cnt_with),
    underlying_ignoring_duplication=dict(cnt_under),
    required_reference_ops=len(req),
    required_covered_approved=sum(c["state"] == "covered_approved" for c in req),
    required_present_withheld_only=[c["op_id"] for c in req if c["state"] == "present_withheld_only"],
    required_missing=[c["op_id"] for c in req if c["state"] == "missing"],
    covered_with_tool_issue=[c["op_id"] for c in req if c["tool_issue_on_all_approved"]],
    covered_via_duplicate_only=[c["op_id"] for c in req if c["via_duplicate_only"]],
    conditional_missing=[c["op_id"] for c in coverage if c["required"] == "conditional" and c["state"] == "missing"],
    approved_steps_with_tool_issue=[r["step"] for r in rows if r["tool_issue"] and r["status"] == "auto_approved"],
)
os.makedirs(OUT, exist_ok=True)
json.dump(dict(status="drafted by the authors; every judgement listed (J01 to J17) for independent review", part="motor shaft eixo, replacement part (remanufacturing)",
               material="AISI 1045 bar", stock="d 30 cold-drawn bar (J01)", geometry_source="analysis/results/step_reference.json R01-R10 + IEC 60072-1 frame-90 interpretation (J02)",
               operations=ref_plan, operation_classes_in_ontology=ops_in_onto,
               machines_in_ontology=[k for k, v in machines.items() if "supportsOperation" in v]),
          open(os.path.join(OUT, "expert_reference_plan.json"), "w"), indent=1)
json.dump(dict(rows=audit, ranges=RANGES, feed_and_semantics_checks=feed_checks, material=material_note,
               provenance=provenance_note, machine_max_rpm=nmax),
          open(os.path.join(OUT, "parameter_audit.json"), "w"), indent=1)
json.dump(dict(rows=rows, coverage=coverage, summary=summary, entity_to_reference=ENT2REF),
          open(os.path.join(OUT, "comparison.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))

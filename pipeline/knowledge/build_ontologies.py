"""
SKL Ontology Builder
=====================
One-time (re-runnable) authoring script that builds the SKL foundation ontologies and
the specialized motor-shaft-case ontology, and saves them as RDF/XML `.owl` files under
`prototype_v2/knowledge/`.

Why a builder script instead of hand-written XML: owlready2's native loader supports
RDF/XML, OWL/XML, and NTriples (not Turtle), and hand-authoring correct RDF/XML by hand
is error-prone. Building via owlready2's Python API and calling `onto.save(format=
"rdfxml")` guarantees valid, reasoner-loadable output, and lets the class/individual
data be driven directly from `ontology.py`'s existing dicts (the current, working
domain model for this article case) instead of re-typing it.

This script does NOT add SWRL rules to the saved ontologies. Rules live in
`knowledge/rules/machining_rules.swrl` as the single source of truth and are parsed and
registered at runtime by `src/skl_repository.py` (see that module's docstring). Keeping
rules out of the saved `.owl` files avoids two competing copies of the same rule set.

Re-run this script (`python knowledge/build_ontologies.py`) whenever the class/
individual data below changes. It overwrites the `.owl` files in place.
"""

import os
from owlready2 import (
    get_ontology, Thing, DataProperty, ObjectProperty, FunctionalProperty,
    default_world,
)

KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))
FOUNDATION_DIR = os.path.join(KNOWLEDGE_DIR, "foundation")
SPECIALIZED_DIR = os.path.join(KNOWLEDGE_DIR, "specialized")

NS = "http://onto.brep.org/manufacturing"


# =============================================================================
# foundation/machining_process.owl
# =============================================================================

def build_machining_process_ontology():
    onto = get_ontology(f"{NS}/machining-process#")

    with onto:
        class Feature(Thing):
            """A geometric feature extracted from CAD model."""

        class Step(Feature): pass
        class Cylinder(Feature): pass
        class ChamferFeature(Feature): pass
        class BlindHole(Feature): pass
        class HoleFeature(Feature): pass
        class Bore(Feature): pass
        class Counterbore(Feature): pass
        class Boss(Feature): pass
        class ThroughHole(Feature): pass
        class Slot(Feature): pass
        class Groove(Feature): pass
        class KeyFeature(Feature): pass

        class Operation(Thing):
            """A machining operation."""

        class RoughTurning(Operation): pass
        class FinishTurning(Operation): pass
        class Drilling(Operation): pass
        class Counterboring(Operation): pass
        class Chamfering(Operation): pass
        class Boring(Operation): pass
        class Facing(Operation): pass
        class Milling(Operation): pass
        class Grooving(Operation): pass

        class requiresToolAlongFeatureAxis(Operation >> bool, DataProperty, FunctionalProperty):
            """True for hole-axis operations (drilling, boring, counterboring),
            whose tool axis must coincide with the feature axis. KEFC's
            orientation gate checks such operations against the machine's
            supportsToolOrientation capability; turning-type operations are
            not orientation-sensitive in this sense."""

        class hasPrecedenceOrder(Operation >> int, DataProperty, FunctionalProperty):
            """Lower value = executed earlier. Encodes the rough-before-finish,
            drill-before-counterbore machining precedence symbolically, so
            KEFC reads sequencing from the ontology instead of a hard-coded
            Python list."""

        class hasOperationLabel(Operation >> str, DataProperty, FunctionalProperty): pass
        class hasDescription(Operation >> str, DataProperty, FunctionalProperty): pass
        class hasGCode(Operation >> str, DataProperty):
            """Multi-valued: the G-codes RAL may emit for this operation."""
        class hasCycleCode(Operation >> str, DataProperty):
            """Multi-valued: canned-cycle G-codes (e.g. G81/G83) for this operation."""

        class requiresOperation(Feature >> Operation, ObjectProperty):
            """Asserted by SWRL rules in machining_rules.swrl: a feature
            requires a specific machining operation."""

        # Canonical operation individuals — referenced by name from
        # machining_rules.swrl and by cutting_parameters.owl / tools.owl.
        # hasOperationLabel/hasDescription/hasGCode/hasCycleCode let
        # kg_builder.py source the unified graph's operation-vocabulary nodes
        # from this ontology instead of ontology.py's OPERATIONS dict.
        operations_data = {
            "RoughTurningOp": (RoughTurning, 2, "Rough Turning",
                "Remove bulk material to near-final dimensions",
                ["G00", "G01", "G02", "G03"], []),
            "FinishTurningOp": (FinishTurning, 3, "Finish Turning",
                "Final pass to achieve surface finish and tolerance",
                ["G00", "G01", "G02", "G03"], []),
            "DrillingOp": (Drilling, 4, "Drilling",
                "Create hole using drill bit",
                ["G00", "G01"], ["G81", "G83"]),
            "CounterboringOp": (Counterboring, 5, "Counterboring",
                "Enlarge entrance of hole for head clearance",
                ["G00", "G01"], ["G81", "G82"]),
            "ChamferingOp": (Chamfering, 7, "Chamfering",
                "Create angled edge transition",
                ["G00", "G01"], []),
            "BoringOp": (Boring, 6, "Boring",
                "Enlarge or finish existing hole to precise diameter",
                ["G00", "G01"], []),
            "FacingOp": (Facing, 1, "Facing",
                "Machine flat surface perpendicular to axis of rotation",
                ["G00", "G01"], []),
            "MillingOp": (Milling, 9, "Milling",
                "Remove material using rotating multi-point cutter",
                ["G00", "G01", "G02", "G03"], []),
            "GroovingOp": (Grooving, 8, "Grooving",
                "Cut narrow groove into workpiece",
                ["G00", "G01"], []),
        }

        axis_sensitive = {"DrillingOp", "BoringOp", "CounterboringOp"}
        for ind_name, (cls, precedence, label, desc, gcodes, cycle_codes) in operations_data.items():
            op = cls(ind_name)
            op.requiresToolAlongFeatureAxis = ind_name in axis_sensitive
            op.hasPrecedenceOrder = precedence
            op.hasOperationLabel = label
            op.hasDescription = desc
            op.hasGCode = list(gcodes)
            op.hasCycleCode = list(cycle_codes)

    onto.save(file=os.path.join(FOUNDATION_DIR, "machining_process.owl"), format="rdfxml")
    return onto


# =============================================================================
# foundation/materials.owl
# =============================================================================

def build_materials_ontology():
    onto = get_ontology(f"{NS}/materials#")

    with onto:
        class Material(Thing):
            """A workpiece material with cutting parameters and
            machinability properties."""

        class hasHardnessHRC(Material >> float, DataProperty, FunctionalProperty): pass
        class hasTensileStrengthMPa(Material >> float, DataProperty, FunctionalProperty): pass
        class hasYieldStrengthMPa(Material >> float, DataProperty, FunctionalProperty): pass
        class hasDensityGCM3(Material >> float, DataProperty, FunctionalProperty): pass
        class hasMachinabilityRating(Material >> float, DataProperty, FunctionalProperty): pass
        class hasRecommendedCoolant(Material >> str, DataProperty, FunctionalProperty): pass
        class hasMaterialLabel(Material >> str, DataProperty, FunctionalProperty): pass

        materials_data = {
            "AISI1045Steel": {
                "label": "AISI 1045 Steel", "hardness": 25.0, "tensile": 570.0,
                "yield_": 440.0, "density": 7.85, "machinability": 0.6,
                "coolant": "Soluble Oil",
            },
            "Aluminum6061T6": {
                "label": "Aluminum 6061-T6", "hardness": 60.0, "tensile": 310.0,
                "yield_": 276.0, "density": 2.70, "machinability": 1.0,
                "coolant": "Air or Mist",
            },
            "StainlessSteel304": {
                "label": "Stainless Steel 304", "hardness": 70.0, "tensile": 515.0,
                "yield_": 205.0, "density": 8.00, "machinability": 0.4,
                "coolant": "Soluble Oil",
            },
        }

        for name, d in materials_data.items():
            m = Material(name)
            m.hasMaterialLabel = d["label"]
            m.hasHardnessHRC = d["hardness"]
            m.hasTensileStrengthMPa = d["tensile"]
            m.hasYieldStrengthMPa = d["yield_"]
            m.hasDensityGCM3 = d["density"]
            m.hasMachinabilityRating = d["machinability"]
            m.hasRecommendedCoolant = d["coolant"]

    onto.save(file=os.path.join(FOUNDATION_DIR, "materials.owl"), format="rdfxml")
    return onto


# =============================================================================
# foundation/tools.owl  (imports machining_process.owl for Operation)
# =============================================================================

def build_tools_ontology(process_onto):
    onto = get_ontology(f"{NS}/tools#")
    onto.imported_ontologies.append(process_onto)

    with onto:
        class Tool(Thing):
            """A cutting tool used in machining operations."""

        class hasToolLabel(Tool >> str, DataProperty, FunctionalProperty): pass
        class hasToolType(Tool >> str, DataProperty, FunctionalProperty): pass
        class hasToolMaterial(Tool >> str, DataProperty, FunctionalProperty): pass
        class hasGeometry(Tool >> str, DataProperty, FunctionalProperty): pass
        class hasMaxDiameterMM(Tool >> float, DataProperty, FunctionalProperty): pass
        class hasMinDiameterMM(Tool >> float, DataProperty, FunctionalProperty): pass
        class hasMaxDepthMM(Tool >> float, DataProperty, FunctionalProperty): pass
        class hasCostPerUnit(Tool >> float, DataProperty, FunctionalProperty): pass

        class recommendedForOperation(Tool >> process_onto.Operation, ObjectProperty):
            """A tool recommended for a given operation. Feeds the
            requiresTool SWRL rule (feature -> operation -> tool)."""

        class hasPreferredTool(process_onto.Operation >> Tool, ObjectProperty, FunctionalProperty):
            """When an operation has more than one recommendedForOperation
            tool candidate, this names the preferred one explicitly as an
            ontology fact — KEFC reads it (rule_id: preferred_tool_selection)
            instead of picking Python's list()[0], which was an invisible,
            unexplainable decision. Operations with exactly one candidate
            tool don't need this set."""

        tools_data = {
            "TurningInsertRough": {
                "label": "Rough Turning Insert", "type": "Turning Insert",
                "material": "Carbide", "geometry": "CNMG 120408",
                "max_d": 100.0, "min_d": 10.0, "max_depth": 5.0, "cost": 12.50,
                "ops": [process_onto.RoughTurningOp],
            },
            "TurningInsertFinish": {
                "label": "Finish Turning Insert", "type": "Turning Insert",
                "material": "Carbide with Coating", "geometry": "CNMG 120404",
                "max_d": 100.0, "min_d": 10.0, "max_depth": 2.0, "cost": 18.75,
                "ops": [process_onto.FinishTurningOp],
            },
            "DrillBit": {
                "label": "Twist Drill Bit", "type": "Drill Bit",
                "material": "High-Speed Steel", "geometry": "118deg Point Angle",
                "max_d": 20.0, "min_d": 1.0, "max_depth": 50.0, "cost": 8.50,
                "ops": [process_onto.DrillingOp],
            },
            "CounterboreCutter": {
                "label": "Counterbore Cutter", "type": "Counterbore",
                "material": "Carbide", "geometry": "90deg Cutting Edge",
                "max_d": 30.0, "min_d": 5.0, "max_depth": 15.0, "cost": 45.00,
                "ops": [process_onto.CounterboringOp],
            },
            "ChamferMill": {
                "label": "Chamfer Mill", "type": "Chamfer Tool",
                "material": "Carbide", "geometry": "90deg Chamfer",
                "max_d": 20.0, "min_d": 3.0, "max_depth": 10.0, "cost": 32.00,
                "ops": [process_onto.ChamferingOp],
            },
            "ChamferDrill": {
                "label": "Chamfer Drill (Countersink)", "type": "Chamfer Tool",
                "material": "High-Speed Steel", "geometry": "90deg Point Angle",
                "max_d": 15.0, "min_d": 2.0, "max_depth": 8.0, "cost": 12.00,
                "ops": [process_onto.ChamferingOp],
            },
            "BoringBar": {
                "label": "Boring Bar", "type": "Boring Tool",
                "material": "Carbide Insert", "geometry": "Adjustable Boring Head",
                "max_d": 50.0, "min_d": 5.0, "max_depth": 100.0, "cost": 85.00,
                "ops": [process_onto.BoringOp],
            },
            "EndMill": {
                "label": "End Mill", "type": "Milling Cutter",
                "material": "Carbide", "geometry": "4-Flute",
                "max_d": 20.0, "min_d": 1.0, "max_depth": 40.0, "cost": 28.00,
                "ops": [process_onto.MillingOp],
            },
            "FaceMill": {
                "label": "Face Mill", "type": "Milling Cutter",
                "material": "Carbide Inserts", "geometry": "6-Insert Head",
                "max_d": 100.0, "min_d": 20.0, "max_depth": 10.0, "cost": 120.00,
                "ops": [process_onto.MillingOp, process_onto.FacingOp],
            },
            "GroovingTool": {
                "label": "Grooving Tool", "type": "Grooving Insert",
                "material": "Carbide", "geometry": "2mm Width",
                "max_d": 80.0, "min_d": 10.0, "max_depth": 10.0, "cost": 22.00,
                "ops": [process_onto.GroovingOp],
            },
        }

        for name, d in tools_data.items():
            t = Tool(name)
            t.hasToolLabel = d["label"]
            t.hasToolType = d["type"]
            t.hasToolMaterial = d["material"]
            t.hasGeometry = d["geometry"]
            t.hasMaxDiameterMM = d["max_d"]
            t.hasMinDiameterMM = d["min_d"]
            t.hasMaxDepthMM = d["max_depth"]
            t.hasCostPerUnit = d["cost"]
            t.recommendedForOperation = list(d["ops"])

        # Facing also uses the turning inserts (rough pass with rough insert,
        # finish pass with finish insert) per OPERATIONS['facing']['tools'].
        onto.TurningInsertRough.recommendedForOperation.append(process_onto.FacingOp)
        onto.TurningInsertFinish.recommendedForOperation.append(process_onto.FacingOp)

        # Explicit preferred-tool facts for every operation with more than
        # one recommendedForOperation candidate (source: which tool
        # ontology.py's OPERATIONS[...]['tools'][0] named first — re-encoded
        # here as an ontology fact instead of Python list order).
        process_onto.FacingOp.hasPreferredTool = onto.TurningInsertRough
        process_onto.ChamferingOp.hasPreferredTool = onto.ChamferMill
        process_onto.MillingOp.hasPreferredTool = onto.EndMill

    onto.save(file=os.path.join(FOUNDATION_DIR, "tools.owl"), format="rdfxml")
    return onto


# =============================================================================
# foundation/machines.owl  (imports machining_process.owl for Operation)
# =============================================================================

def build_machines_ontology(process_onto):
    onto = get_ontology(f"{NS}/machines#")
    onto.imported_ontologies.append(process_onto)

    with onto:
        class Machine(Thing):
            """A manufacturing machine and its capabilities/safety limits."""

        class hasMachineLabel(Machine >> str, DataProperty, FunctionalProperty): pass
        class hasModel(Machine >> str, DataProperty, FunctionalProperty): pass
        class hasMaxSpindleSpeedRPM(Machine >> float, DataProperty, FunctionalProperty): pass
        class hasMaxBarDiameterMM(Machine >> float, DataProperty, FunctionalProperty): pass
        class hasMaxSwingDiameterMM(Machine >> float, DataProperty, FunctionalProperty): pass
        class hasTurretStations(Machine >> int, DataProperty, FunctionalProperty): pass
        class hasControlSystem(Machine >> str, DataProperty, FunctionalProperty): pass
        class hasGCodeDialect(Machine >> str, DataProperty, FunctionalProperty): pass
        # Safety limits — KEFC's exception gate checks inferred parameters
        # against these before auto-approving a step.
        class hasSafetyMaxRPM(Machine >> float, DataProperty, FunctionalProperty): pass
        class hasSafetyMaxFeedRate(Machine >> float, DataProperty, FunctionalProperty): pass
        class hasSafetyMaxDepthOfCut(Machine >> float, DataProperty, FunctionalProperty): pass
        class hasSafetyMinToolClearanceMM(Machine >> float, DataProperty, FunctionalProperty): pass

        class supportsOperation(Machine >> process_onto.Operation, ObjectProperty): pass

        class ToolOrientation(Thing):
            """Achievable orientation of a tool axis relative to the machine's
            spindle axis. A two-axis lathe without driven tooling can only
            present a tool along the spindle axis (axial); radial tool axes
            require driven (live) tooling or a milling machine."""

        class supportsToolOrientation(Machine >> ToolOrientation, ObjectProperty): pass
        class hasSpindleAxis(Machine >> str, DataProperty, FunctionalProperty):
            """Part-frame axis label (X, Y or Z) along which the spindle acts;
            the feature extractor reports feature orientations in the same
            frame, so KEFC can classify a hole axis as axial or radial."""

        axial = ToolOrientation("AxialToolOrientation")
        radial = ToolOrientation("RadialToolOrientation")

        lathe = Machine("CNCLatheFanuc0iTD")
        lathe.hasMachineLabel = "CNC Lathe"
        lathe.hasModel = "Fanuc Series 0i-TD"
        lathe.hasMaxSpindleSpeedRPM = 4500.0
        lathe.hasMaxBarDiameterMM = 50.0
        lathe.hasMaxSwingDiameterMM = 300.0
        lathe.hasTurretStations = 12
        lathe.hasControlSystem = "Fanuc 0i-TD"
        lathe.hasGCodeDialect = "Fanuc"
        lathe.hasSafetyMaxRPM = 4500.0
        lathe.hasSafetyMaxFeedRate = 5.0
        lathe.hasSafetyMaxDepthOfCut = 5.0
        lathe.hasSafetyMinToolClearanceMM = 5.0
        lathe.supportsOperation = [
            process_onto.RoughTurningOp, process_onto.FinishTurningOp,
            process_onto.DrillingOp, process_onto.CounterboringOp,
            process_onto.ChamferingOp, process_onto.BoringOp,
            process_onto.FacingOp, process_onto.GroovingOp,
        ]
        # No driven tooling: only axial tool orientations are achievable.
        lathe.supportsToolOrientation = [axial]
        lathe.hasSpindleAxis = "Z"

    onto.save(file=os.path.join(FOUNDATION_DIR, "machines.owl"), format="rdfxml")
    return onto


# =============================================================================
# foundation/cutting_parameters.owl  (imports materials.owl + machining_process.owl)
# =============================================================================

def build_cutting_parameters_ontology(materials_onto, process_onto):
    onto = get_ontology(f"{NS}/cutting-parameters#")
    onto.imported_ontologies.append(materials_onto)
    onto.imported_ontologies.append(process_onto)

    with onto:
        class CuttingParameterSet(Thing):
            """A concrete, sourced set of feed/speed/depth values for a
            (material, operation) pair, or a material-independent default
            for an operation. SWRL rules link a Feature to the
            CuttingParameterSet that determines its process parameters —
            this is the traceable alternative to a bare Python default."""

        class hasFeedRateValue(CuttingParameterSet >> float, DataProperty, FunctionalProperty): pass
        class hasFeedRateUnit(CuttingParameterSet >> str, DataProperty, FunctionalProperty): pass
        class hasSpindleSpeedValue(CuttingParameterSet >> float, DataProperty, FunctionalProperty): pass
        class hasSpindleSpeedUnit(CuttingParameterSet >> str, DataProperty, FunctionalProperty): pass
        class hasDepthOfCutValue(CuttingParameterSet >> float, DataProperty, FunctionalProperty): pass
        class hasDepthOfCutUnit(CuttingParameterSet >> str, DataProperty, FunctionalProperty): pass
        class requiresCoolant(CuttingParameterSet >> bool, DataProperty, FunctionalProperty): pass

        class forMaterial(CuttingParameterSet >> materials_onto.Material, ObjectProperty, FunctionalProperty): pass
        class forOperation(CuttingParameterSet >> process_onto.Operation, ObjectProperty, FunctionalProperty): pass

        # Material-specific sets, sourced from ontology.py MATERIALS[...]['cutting_parameters'].
        # Only steel/aluminum/stainless x {turning-rough, turning-finish, drilling, milling}
        # are material-specific in the current domain model.
        material_specific = {
            "AISI1045_RoughTurning_Params": (
                materials_onto.AISI1045Steel, process_onto.RoughTurningOp,
                0.25, "mm/rev", 800.0 * 0.6, "RPM", 2.0, "mm",
            ),
            "AISI1045_FinishTurning_Params": (
                materials_onto.AISI1045Steel, process_onto.FinishTurningOp,
                0.1 * 0.6, "mm/rev", 1500.0 * 0.6, "RPM", 0.2, "mm",
            ),
            "AISI1045_Drilling_Params": (
                materials_onto.AISI1045Steel, process_onto.DrillingOp,
                0.15, "mm/rev", 1500.0 * 0.6, "RPM", 5.0, "mm",
            ),
            "AISI1045_Milling_Params": (
                materials_onto.AISI1045Steel, process_onto.MillingOp,
                0.05, "mm/tooth", 2000.0 * 0.6, "RPM", 1.0, "mm",
            ),
            "Aluminum6061_RoughTurning_Params": (
                materials_onto.Aluminum6061T6, process_onto.RoughTurningOp,
                0.3, "mm/rev", 800.0 * 1.0, "RPM", 3.0, "mm",
            ),
            "Aluminum6061_FinishTurning_Params": (
                materials_onto.Aluminum6061T6, process_onto.FinishTurningOp,
                0.12 * 1.0, "mm/rev", 1500.0 * 1.0, "RPM", 0.2, "mm",
            ),
            "Aluminum6061_Drilling_Params": (
                materials_onto.Aluminum6061T6, process_onto.DrillingOp,
                0.18, "mm/rev", 1500.0 * 1.0, "RPM", 8.0, "mm",
            ),
            "Aluminum6061_Milling_Params": (
                materials_onto.Aluminum6061T6, process_onto.MillingOp,
                0.08, "mm/tooth", 2000.0 * 1.0, "RPM", 2.0, "mm",
            ),
            "Stainless304_RoughTurning_Params": (
                materials_onto.StainlessSteel304, process_onto.RoughTurningOp,
                0.2, "mm/rev", 800.0 * 0.4, "RPM", 1.5, "mm",
            ),
            "Stainless304_FinishTurning_Params": (
                materials_onto.StainlessSteel304, process_onto.FinishTurningOp,
                0.08 * 0.4, "mm/rev", 1500.0 * 0.4, "RPM", 0.15, "mm",
            ),
            "Stainless304_Drilling_Params": (
                materials_onto.StainlessSteel304, process_onto.DrillingOp,
                0.12, "mm/rev", 1500.0 * 0.4, "RPM", 4.0, "mm",
            ),
            "Stainless304_Milling_Params": (
                materials_onto.StainlessSteel304, process_onto.MillingOp,
                0.04, "mm/tooth", 2000.0 * 0.4, "RPM", 0.8, "mm",
            ),
        }

        for name, (mat, op, feed, feed_u, speed, speed_u, depth, depth_u) in material_specific.items():
            p = CuttingParameterSet(name)
            p.forMaterial = mat
            p.forOperation = op
            p.hasFeedRateValue = round(feed, 4)
            p.hasFeedRateUnit = feed_u
            p.hasSpindleSpeedValue = round(speed, 2)
            p.hasSpindleSpeedUnit = speed_u
            p.hasDepthOfCutValue = depth
            p.hasDepthOfCutUnit = depth_u
            p.requiresCoolant = True

        # Material-independent defaults for the remaining operations, sourced
        # from ontology.py OPERATIONS[...]['parameters']['default'] — used
        # when no material-specific set applies.
        generic_defaults = {
            "Counterboring_Default_Params": (process_onto.CounterboringOp, 0.12, "mm/rev", 1000.0, "RPM", 3.0, "mm"),
            "Chamfering_Default_Params": (process_onto.ChamferingOp, 0.1, "mm/rev", 1200.0, "RPM", 1.0, "mm"),
            "Boring_Default_Params": (process_onto.BoringOp, 0.1, "mm/rev", 800.0, "RPM", 0.5, "mm"),
            "Facing_Default_Params": (process_onto.FacingOp, 0.2, "mm/rev", 800.0, "RPM", 1.0, "mm"),
            "Grooving_Default_Params": (process_onto.GroovingOp, 0.08, "mm/rev", 600.0, "RPM", 0.5, "mm"),
        }

        for name, (op, feed, feed_u, speed, speed_u, depth, depth_u) in generic_defaults.items():
            p = CuttingParameterSet(name)
            p.forOperation = op
            p.hasFeedRateValue = feed
            p.hasFeedRateUnit = feed_u
            p.hasSpindleSpeedValue = speed
            p.hasSpindleSpeedUnit = speed_u
            p.hasDepthOfCutValue = depth
            p.hasDepthOfCutUnit = depth_u
            p.requiresCoolant = True

        class hasCuttingParameterSet(Thing >> CuttingParameterSet, ObjectProperty):
            """Asserted by SWRL rules: links a Feature to the
            CuttingParameterSet that determines its process parameters."""

    onto.save(file=os.path.join(FOUNDATION_DIR, "cutting_parameters.owl"), format="rdfxml")
    return onto


# =============================================================================
# foundation/serialisation_profiles.owl  (imports machines.owl)
# =============================================================================
#
# What the application layer (RAL, gcode_generator.py) can express, declared
# as knowledge rather than left implicit in code. KEFC checks the profile RAL
# uses after the machine's own orientation capability has been checked: a
# machine may be able to present a radial tool (driven tooling) while the
# serialiser has no radial cycle, in which case an admitted radial step would
# be emitted as an axial cycle on the spindle centreline. Kept in its own file
# so machines.owl, the unified graph and the RDF triplestore are unchanged.

def build_serialisation_profiles_ontology(machines_onto):
    onto = get_ontology(f"{NS}/serialisation-profiles#")
    onto.imported_ontologies.append(machines_onto)

    with onto:
        class SerialisationProfile(Thing):
            """A G-code serialisation profile of the application layer and
            the tool orientations for which it has a cycle or move pattern."""

        class profileSupportsToolOrientation(SerialisationProfile >> machines_onto.ToolOrientation, ObjectProperty):
            """Tool orientation the profile can serialise. Deliberately a
            separate property from machines.owl's supportsToolOrientation,
            whose domain is Machine, so a profile is never inferred to be a
            machine."""

        class hasProfileLabel(SerialisationProfile >> str, DataProperty, FunctionalProperty): pass
        class hasProfileDescription(SerialisationProfile >> str, DataProperty, FunctionalProperty): pass

        turning = SerialisationProfile("RALTurningProfile")
        turning.hasProfileLabel = "RAL turning profile (gcode_generator.py)"
        turning.hasProfileDescription = (
            "G18/G21/G40/G54/G80/G90/G97/G99 turning profile; drilling and "
            "counterboring as G81/G83 canned cycles on the spindle centreline; "
            "no driven-tool (radial) cycle and no C-axis positioning.")
        turning.profileSupportsToolOrientation = [machines_onto.AxialToolOrientation]

    onto.save(file=os.path.join(FOUNDATION_DIR, "serialisation_profiles.owl"), format="rdfxml")
    return onto


# =============================================================================
# specialized/mill_turn_configuration.owl  (imports machines.owl)
# =============================================================================
#
# Optional machine configuration, loaded by SKLRepository only when a run is
# started with --machine cnc_mill_turn. It is kept out of machines.owl so the
# reference (lathe) run's knowledge base, graph and triple counts are not
# changed by the mere existence of a second machine. The individual is minted
# in the machines namespace so every capability lookup (supportsOperation,
# supportsToolOrientation, hasSpindleAxis, safety limits) resolves it exactly
# as it resolves the lathe; no gating code distinguishes the two machines.

def build_mill_turn_configuration_ontology(process_onto, machines_onto):
    onto = get_ontology(f"{NS}/mill-turn-configuration#")
    onto.imported_ontologies.append(machines_onto)
    machines_ns = onto.get_namespace(machines_onto.base_iri)

    with onto:
        mt = machines_onto.Machine("CNCMillTurn", namespace=machines_ns)
        mt.hasMachineLabel = "CNC Mill-Turn"
        mt.hasModel = "Turning centre with driven (live) tooling, same envelope as CNCLatheFanuc0iTD"
        # Same envelope and safety limits as the lathe, so the only
        # difference between the two configurations is the capability model.
        mt.hasMaxSpindleSpeedRPM = 4500.0
        mt.hasMaxBarDiameterMM = 50.0
        mt.hasMaxSwingDiameterMM = 300.0
        mt.hasTurretStations = 12
        mt.hasControlSystem = "Fanuc 0i-TD"
        mt.hasGCodeDialect = "Fanuc"
        mt.hasSafetyMaxRPM = 4500.0
        mt.hasSafetyMaxFeedRate = 5.0
        mt.hasSafetyMaxDepthOfCut = 5.0
        mt.hasSafetyMinToolClearanceMM = 5.0
        mt.supportsOperation = [
            process_onto.RoughTurningOp, process_onto.FinishTurningOp,
            process_onto.DrillingOp, process_onto.CounterboringOp,
            process_onto.ChamferingOp, process_onto.BoringOp,
            process_onto.FacingOp, process_onto.GroovingOp,
            process_onto.MillingOp,
        ]
        # Driven tooling: tool axes along and across the spindle axis.
        mt.supportsToolOrientation = [machines_onto.AxialToolOrientation,
                                      machines_onto.RadialToolOrientation]
        mt.hasSpindleAxis = "Z"

    onto.save(file=os.path.join(SPECIALIZED_DIR, "mill_turn_configuration.owl"), format="rdfxml")
    return onto


# =============================================================================
# specialized/motor_shaft_case.owl
# =============================================================================

def build_motor_shaft_case_ontology(process_onto, materials_onto, tools_onto, machines_onto, params_onto):
    onto = get_ontology(f"{NS}/motor-shaft-case#")
    for imp in (process_onto, materials_onto, tools_onto, machines_onto, params_onto):
        onto.imported_ontologies.append(imp)

    with onto:
        class madeOfMaterial(process_onto.Feature >> materials_onto.Material, ObjectProperty, FunctionalProperty):
            """Links a feature individual to its workpiece material. All
            motor-shaft-case features share the single AISI 1045 workpiece."""

        class machinedOn(process_onto.Feature >> machines_onto.Machine, ObjectProperty, FunctionalProperty): pass

        class requiresTool(process_onto.Feature >> tools_onto.Tool, ObjectProperty):
            """Asserted by SWRL rules: a feature requires a specific tool,
            derived from its required operation(s)."""

        class hasCase(Thing >> str, DataProperty, FunctionalProperty): pass

        case_marker = process_onto.Feature("MotorShaftCaseMarker")
        case_marker.hasCase = "motor_shaft_eixo"

    onto.save(file=os.path.join(SPECIALIZED_DIR, "motor_shaft_case.owl"), format="rdfxml")
    return onto


def main():
    os.makedirs(FOUNDATION_DIR, exist_ok=True)
    os.makedirs(SPECIALIZED_DIR, exist_ok=True)

    process_onto = build_machining_process_ontology()
    materials_onto = build_materials_ontology()
    tools_onto = build_tools_ontology(process_onto)
    machines_onto = build_machines_ontology(process_onto)
    params_onto = build_cutting_parameters_ontology(materials_onto, process_onto)
    build_motor_shaft_case_ontology(process_onto, materials_onto, tools_onto, machines_onto, params_onto)
    build_mill_turn_configuration_ontology(process_onto, machines_onto)
    build_serialisation_profiles_ontology(machines_onto)

    print("SKL ontologies built:")
    for onto in default_world.ontologies.values():
        if onto.base_iri.startswith(NS):
            print(f"  {onto.base_iri}  ({len(list(onto.classes()))} classes, "
                  f"{len(list(onto.individuals()))} individuals)")


if __name__ == "__main__":
    main()

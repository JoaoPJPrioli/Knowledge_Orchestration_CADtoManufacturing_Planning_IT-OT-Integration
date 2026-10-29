"""
SKL Repository
===============
Loads the SKL (Structured Knowledge Layer) ontologies — foundation ontologies plus the
specialized motor-shaft-case ontology, under `prototype_v2/knowledge/` — registers the
SWRL rules from `knowledge/rules/machining_rules.swrl`, runs Pellet reasoning, and
exposes inferred facts through stable Python methods with provenance.

This is the sole place manufacturing knowledge is loaded and reasoned over. CFRM
(`semantic_reconciler.py`) asserts feature individuals here; KEFC (`kefc_controller.py`)
reads inferred operations/tools/cutting-parameters back out, with provenance, and is
the only consumer that turns those facts into a validated process parameter package.

Provenance honesty note: this module does not extract formal proof/explanation traces
from Pellet (that's a heavier feature this "minimal article prototype" doesn't need).
Instead, because `machining_rules.swrl` follows exactly three fixed templates (a
feature class implies a fixed operation individual; a feature+operation[+material]
implies a fixed cutting-parameter-set individual; the single tool-assignment rule),
`_parse_rules` extracts each rule's structural signature at load time, and provenance
lookups match an inferred fact back to the rule whose signature produced it. This is
exact for this rule set, not a general SWRL explanation engine — if the rule set grows
rules that don't fit those three templates, this matching logic needs to grow with it.

Environment note: owlready2's bundled Pellet distribution includes at least one jar
that requires a newer Java than this machine's default `java` on PATH (Java 8) can
run (`UnsupportedClassVersionError`, class file version 69 = Java 25). This module
searches for a compatible Java install and sets `owlready2.JAVA_EXE` explicitly. If
none is found, it raises `SKLReasonerError` with an actionable message rather than
silently degrading to un-reasoned defaults.
"""

import glob
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import owlready2
from owlready2 import (
    World, Imp, sync_reasoner_pellet, default_world,
    AnnotationProperty, FunctionalProperty,
)
from owlready2.base import OwlReadyJavaError, OwlReadyInconsistentOntologyError

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")
FOUNDATION_DIR = os.path.join(KNOWLEDGE_DIR, "foundation")
SPECIALIZED_DIR = os.path.join(KNOWLEDGE_DIR, "specialized")
RULES_FILE = os.path.join(KNOWLEDGE_DIR, "rules", "machining_rules.swrl")

# Identity for the exported unified_knowledge_base.owl file itself — see
# _replace_anonymous_ontology_iri's docstring for why this is needed.
UNIFIED_KB_IRI = "http://onto.brep.org/manufacturing/unified-knowledge-base"

SKL_VERSION = "0.1.0"
REASONER_NAME = "Pellet (via owlready2 sync_reasoner_pellet)"

# Feature-type string (as produced by feature_parser.py / ontology.py's normalization)
# -> ontology class name in knowledge/foundation/machining_process.owl.
FEATURE_TYPE_TO_CLASS = {
    "step": "Step",
    "cylinder": "Cylinder",
    "chamfer": "ChamferFeature",
    "blind_hole": "BlindHole",
    "hole": "HoleFeature",
    "bore": "Bore",
    "counterbore": "Counterbore",
    "boss": "Boss",
    "through_hole": "ThroughHole",
    "slot": "Slot",
    "groove": "Groove",
    "key": "KeyFeature",
}

MATERIAL_KEY_TO_INDIVIDUAL = {
    "steel_1045": "AISI1045Steel",
    "aluminum_6061": "Aluminum6061T6",
    "stainless_304": "StainlessSteel304",
}
MATERIAL_INDIVIDUAL_TO_KEY = {v: k for k, v in MATERIAL_KEY_TO_INDIVIDUAL.items()}

# gcode_generator.py dispatches on the legacy snake_case operation/tool ids
# from ontology.py's OPERATIONS/TOOLS dicts (see gcode_generator.py's
# _generate_operation_gcode / _get_tool_number) — RAL's public interface was
# intentionally kept unchanged (see .codex/architecture.md), so this is the
# single place SKL's OWL individual names are translated back to those ids.
# kefc_controller.py and kg_builder.py both import these rather than keeping
# their own copies.
OWL_OPERATION_TO_LEGACY_ID = {
    "RoughTurningOp": "rough_turning",
    "FinishTurningOp": "finish_turning",
    "DrillingOp": "drilling",
    "CounterboringOp": "counterboring",
    "ChamferingOp": "chamfering",
    "BoringOp": "boring",
    "FacingOp": "facing",
    "MillingOp": "milling",
    "GroovingOp": "grooving",
}
LEGACY_OPERATION_ID_TO_OWL = {v: k for k, v in OWL_OPERATION_TO_LEGACY_ID.items()}

OWL_TOOL_TO_LEGACY_ID = {
    "TurningInsertRough": "turning_insert_rough",
    "TurningInsertFinish": "turning_insert_finish",
    "DrillBit": "drill_bit",
    "CounterboreCutter": "counterbore_cutter",
    "ChamferMill": "chamfer_mill",
    "ChamferDrill": "chamfer_drill",
    "BoringBar": "boring_bar",
    "EndMill": "end_mill",
    "FaceMill": "face_mill",
    "GroovingTool": "grooving_tool",
}
LEGACY_TOOL_ID_TO_OWL = {v: k for k, v in OWL_TOOL_TO_LEGACY_ID.items()}

MACHINE_INDIVIDUAL_TO_KEY = {
    "CNCLatheFanuc0iTD": "cnc_lathe",
    "CNCMillTurn": "cnc_mill_turn",
}
MACHINE_KEY_TO_INDIVIDUAL = {v: k for k, v in MACHINE_INDIVIDUAL_TO_KEY.items()}

# Optional machine-configuration ontologies (knowledge/specialized/), loaded
# only for the machine key that needs them; the lathe is declared in
# foundation/machines.owl and needs none. Built by knowledge/build_ontologies.py.
MACHINE_CONFIGURATION_FILES = {
    "cnc_mill_turn": "mill_turn_configuration.owl",
}


class SKLReasonerError(RuntimeError):
    """Raised when Java/Pellet is unavailable or the ontology is inconsistent.
    Never caught silently by callers — a missing reasoner must surface as a
    hard failure, not a fallback to un-reasoned defaults."""


@dataclass
class ParsedRule:
    rule_id: str
    text: str
    antecedent_classes: List[str] = field(default_factory=list)  # class names applied to ?f
    op_individual: Optional[str] = None       # fixed operation individual in antecedent, if any
    material_individual: Optional[str] = None  # fixed material individual in antecedent, if any
    consequent_property: str = ""
    consequent_object: Optional[str] = None    # fixed individual name, or None if a variable


def _parse_rules(path: str) -> List[ParsedRule]:
    rules = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line or "->" not in line:
                raise SKLReasonerError(f"Malformed rule line in {path}: {line!r}")
            rule_id, rest = line.split(":", 1)
            antecedent_text, consequent_text = rest.split("->", 1)
            rule_id = rule_id.strip()
            antecedent_text = antecedent_text.strip()
            consequent_text = consequent_text.strip()

            pr = ParsedRule(rule_id=rule_id, text=line)

            for atom in antecedent_text.split("^"):
                atom = atom.strip()
                m = re.match(r"^(\w+)\(\?(\w+)\)$", atom)
                if m:
                    pr.antecedent_classes.append(m.group(1))
                    continue
                m = re.match(r"^(\w+)\(\?(\w+),\s*(\??\w+)\)$", atom)
                if m:
                    prop, _var1, arg2 = m.group(1), m.group(2), m.group(3)
                    if not arg2.startswith("?"):
                        if prop == "requiresOperation":
                            pr.op_individual = arg2
                        elif prop == "madeOfMaterial":
                            pr.material_individual = arg2
                    continue
                raise SKLReasonerError(f"Unrecognized antecedent atom in rule {rule_id!r}: {atom!r}")

            m = re.match(r"^(\w+)\(\?(\w+),\s*(\??\w+)\)$", consequent_text)
            if not m:
                raise SKLReasonerError(f"Unrecognized consequent in rule {rule_id!r}: {consequent_text!r}")
            pr.consequent_property = m.group(1)
            arg2 = m.group(3)
            pr.consequent_object = None if arg2.startswith("?") else arg2

            rules.append(pr)
    return rules


class SKLRepository:
    """Owns one isolated owlready2 World holding the loaded SKL ontologies plus
    the reasoner's inferred closure. One instance per pipeline run — do not
    share across runs, since asserted Feature individuals accumulate in the
    world."""

    def __init__(self, java_exe: Optional[str] = None, machine_key: str = "cnc_lathe"):
        if machine_key not in MACHINE_KEY_TO_INDIVIDUAL:
            raise SKLReasonerError(
                f"Unknown machine key {machine_key!r}; declared machines: "
                f"{sorted(MACHINE_KEY_TO_INDIVIDUAL)}")
        self.machine_key = machine_key
        self.config_ontos = []
        self.world = World()
        self.rules = _parse_rules(RULES_FILE)
        self._load_ontologies()
        self._register_rules()
        self.java_exe = self._resolve_java(java_exe)
        self.reasoning_status = "not_run"

    # -- loading -----------------------------------------------------------

    def _load_ontologies(self):
        # Load foundation ontologies first, by explicit file path, so that
        # when the specialized ontology's owl:imports are resolved by IRI,
        # owlready2 finds them already registered in this world instead of
        # attempting a network fetch.
        for filename in ("machining_process.owl", "materials.owl", "tools.owl",
                          "machines.owl", "cutting_parameters.owl"):
            path = os.path.join(FOUNDATION_DIR, filename)
            if not os.path.exists(path):
                raise SKLReasonerError(
                    f"Foundation ontology not found at {path}. Run "
                    f"'python knowledge/build_ontologies.py' first."
                )
            self.world.get_ontology(path.replace("\\", "/")).load()

        case_path = os.path.join(SPECIALIZED_DIR, "motor_shaft_case.owl")
        if not os.path.exists(case_path):
            raise SKLReasonerError(
                f"Specialized ontology not found at {case_path}. Run "
                f"'python knowledge/build_ontologies.py' first."
            )
        self.case_onto = self.world.get_ontology(case_path.replace("\\", "/")).load()

        config_file = MACHINE_CONFIGURATION_FILES.get(self.machine_key)
        if config_file:
            config_path = os.path.join(SPECIALIZED_DIR, config_file)
            if not os.path.exists(config_path):
                raise SKLReasonerError(
                    f"Machine configuration ontology not found at {config_path}. Run "
                    f"'python knowledge/build_ontologies.py' first.")
            self.config_ontos.append(
                self.world.get_ontology(config_path.replace("\\", "/")).load())

        self.process_onto = self.world.get_ontology(
            "http://onto.brep.org/manufacturing/machining-process#"
        )
        self.materials_onto = self.world.get_ontology(
            "http://onto.brep.org/manufacturing/materials#"
        )
        self.tools_onto = self.world.get_ontology(
            "http://onto.brep.org/manufacturing/tools#"
        )
        self.machines_onto = self.world.get_ontology(
            "http://onto.brep.org/manufacturing/machines#"
        )
        self.params_onto = self.world.get_ontology(
            "http://onto.brep.org/manufacturing/cutting-parameters#"
        )

        # Serialisation profiles of the application layer (what RAL can
        # express); loaded after the foundation set, not part of the rule
        # search namespaces (no SWRL rule mentions them).
        profiles_path = os.path.join(FOUNDATION_DIR, "serialisation_profiles.owl")
        if not os.path.exists(profiles_path):
            raise SKLReasonerError(
                f"Serialisation-profile ontology not found at {profiles_path}. Run "
                f"'python knowledge/build_ontologies.py' first.")
        self.profiles_onto = self.world.get_ontology(profiles_path.replace("\\", "/")).load()

    def _register_rules(self):
        # Bare names in rule text (e.g. "Step", "AISI1045Steel") must resolve
        # across all five foundation ontologies plus the case ontology itself
        # — Namespace.__getitem__ only tries its own base_iri prefix, so the
        # full search list must be passed explicitly, not just [case_onto].
        search_namespaces = [
            self.case_onto, self.process_onto, self.materials_onto,
            self.tools_onto, self.machines_onto, self.params_onto,
        ]
        with self.case_onto:
            for pr in self.rules:
                rule_body = pr.text.split(":", 1)[1].strip()
                imp = Imp()
                imp.set_as_rule(rule_body, namespaces=search_namespaces)

    # -- java / reasoning ----------------------------------------------------

    def _resolve_java(self, java_exe: Optional[str]) -> str:
        candidates = []
        if java_exe:
            candidates.append(java_exe)
        env_override = os.environ.get("SKL_JAVA_EXE")
        if env_override:
            candidates.append(env_override)
        candidates.extend(sorted(
            glob.glob(r"C:\Program Files\Eclipse Adoptium\jdk-*\bin\java.exe"), reverse=True
        ))
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            candidates.append(os.path.join(java_home, "bin", "java.exe"))
        candidates.append("java")

        required = self.required_java_major()
        tried = []
        for candidate in candidates:
            version = self._java_major_version(candidate)
            tried.append(f"{candidate} -> {version if version else 'not runnable'}")
            if version is not None and version >= required:
                return candidate

        raise SKLReasonerError(
            f"No Java {required}+ install found to run Pellet. The highest class-file "
            f"version in owlready2's bundled Pellet jars requires Java {required}; an "
            f"older Java fails with UnsupportedClassVersionError. Set the SKL_JAVA_EXE "
            f"environment variable to a Java {required}+ java.exe, or pass java_exe= "
            f"explicitly. Candidates tried:\n  " + "\n  ".join(tried)
        )

    _REQUIRED_JAVA_MAJOR: Optional[int] = None

    @classmethod
    def required_java_major(cls) -> int:
        """Minimum Java major version for the bundled Pellet jars, read from
        the highest class-file major version they contain (Java = major - 44).
        Before Revision 6 the threshold was hard-coded as 21, but with
        owlready2 0.51 jena-arq-fixed2.10.0.jar contains class files of major
        version 69 (Java 25), so a Java 21 to 24 was accepted here and then
        failed inside Pellet."""
        if cls._REQUIRED_JAVA_MAJOR is None:
            import zipfile
            pellet_dir = os.path.join(os.path.dirname(owlready2.__file__), "pellet")
            highest = 0
            for jar in glob.glob(os.path.join(pellet_dir, "*.jar")):
                with zipfile.ZipFile(jar) as z:
                    for name in z.namelist():
                        if name.endswith(".class") and not name.startswith("META-INF/"):
                            head = z.read(name)[:8]
                            if head[:4] == b"\xca\xfe\xba\xbe":
                                highest = max(highest, int.from_bytes(head[6:8], "big"))
            if highest == 0:
                raise SKLReasonerError(f"No Pellet class files found under {pellet_dir}.")
            cls._REQUIRED_JAVA_MAJOR = highest - 44
        return cls._REQUIRED_JAVA_MAJOR

    @staticmethod
    def _java_major_version(java_exe: str) -> Optional[int]:
        try:
            result = subprocess.run(
                [java_exe, "-version"], capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            return None
        output = (result.stdout or "") + (result.stderr or "")
        m = re.search(r'version "(\d+)(?:\.(\d+))?', output)
        if not m:
            return None
        major = int(m.group(1))
        if major == 1 and m.group(2):  # legacy "1.8.0_xxx" style
            return int(m.group(2))
        return major

    def reason(self):
        owlready2.JAVA_EXE = self.java_exe
        try:
            with self.world.get_ontology(self.case_onto.base_iri):
                sync_reasoner_pellet(
                    self.world, infer_property_values=True, infer_data_property_values=True
                )
        except OwlReadyInconsistentOntologyError as e:
            self.reasoning_status = "inconsistent"
            raise SKLReasonerError(f"SKL ontology is inconsistent after asserting case facts: {e}") from e
        except OwlReadyJavaError as e:
            self.reasoning_status = "java_error"
            raise SKLReasonerError(
                f"Pellet failed to run via {self.java_exe}. If this mentions "
                f"UnsupportedClassVersionError, the resolved Java is still too old — "
                f"set SKL_JAVA_EXE to a newer java.exe. Underlying error: {e}"
            ) from e
        self.reasoning_status = "ok"

    # -- feature assertion (called by CFRM / semantic_reconciler.py) --------

    def create_feature_individual(self, feature_id, feature_type: str,
                                   material_key: str = "steel_1045",
                                   machine_key: str = "cnc_lathe"):
        normalized = feature_type.lower().replace(" ", "_").replace("-", "_")
        class_name = FEATURE_TYPE_TO_CLASS.get(normalized)
        confidence = 1.0
        if class_name is None:
            # Unmapped concept: fall back to the generic Feature class and let
            # KEFC see zero inferred operations -> requires_review.
            class_name = "Feature"
            confidence = 0.0
        feature_cls = getattr(self.process_onto, class_name)
        ind_name = f"feature_{feature_id}"
        individual = feature_cls(ind_name, namespace=self.case_onto)

        material_ind_name = MATERIAL_KEY_TO_INDIVIDUAL.get(material_key, "AISI1045Steel")
        individual.madeOfMaterial = getattr(self.materials_onto, material_ind_name)
        machine_ind_name = MACHINE_KEY_TO_INDIVIDUAL.get(machine_key)
        if machine_ind_name is not None:
            individual.machinedOn = getattr(self.machines_onto, machine_ind_name)

        return individual, confidence

    # -- vocabulary listing (for kg_builder.py's unified-graph nodes) --------
    #
    # These read the loaded OWL individuals directly — kg_builder.py's
    # operation/tool/machine/material graph nodes are sourced from here, not
    # from ontology.py, so the unified graph's vocabulary is genuinely
    # SKL-authoritative rather than a static Python mirror of it.

    def list_operations(self) -> List[Dict]:
        results = []
        for op in self.process_onto.Operation.instances():
            results.append({
                "id": op.name,
                "name": getattr(op, "hasOperationLabel", None) or op.name,
                "description": getattr(op, "hasDescription", "") or "",
                "g_codes": list(getattr(op, "hasGCode", [])),
                "cycle_codes": list(getattr(op, "hasCycleCode", [])),
                "precedence": getattr(op, "hasPrecedenceOrder", None),
                "ontology_sources": self._sources_for([op]),
            })
        return results

    def list_tools(self) -> List[Dict]:
        results = []
        for tool in self.tools_onto.Tool.instances():
            results.append({
                "id": tool.name,
                "name": getattr(tool, "hasToolLabel", None) or tool.name,
                "type": getattr(tool, "hasToolType", "") or "",
                "material": getattr(tool, "hasToolMaterial", "") or "",
                "geometry": getattr(tool, "hasGeometry", "") or "",
                "recommended_operations": [
                    op.name for op in getattr(tool, "recommendedForOperation", [])
                ],
                "ontology_sources": self._sources_for([tool]),
            })
        return results

    def list_machines(self) -> List[Dict]:
        results = []
        for m in self.machines_onto.Machine.instances():
            results.append({
                "id": m.name,
                "name": getattr(m, "hasMachineLabel", None) or m.name,
                "model": getattr(m, "hasModel", "") or "",
                "capabilities": {
                    "max_spindle_speed": getattr(m, "hasMaxSpindleSpeedRPM", None),
                    "max_bar_diameter": getattr(m, "hasMaxBarDiameterMM", None),
                    "max_swing_diameter": getattr(m, "hasMaxSwingDiameterMM", None),
                    "turret_stations": getattr(m, "hasTurretStations", None),
                    "control_system": getattr(m, "hasControlSystem", "") or "",
                },
                "supported_operations": [
                    op.name for op in getattr(m, "supportsOperation", [])
                ],
                "safety_limits": {
                    "max_rpm": getattr(m, "hasSafetyMaxRPM", None),
                    "max_feed_rate": getattr(m, "hasSafetyMaxFeedRate", None),
                    "max_depth_of_cut": getattr(m, "hasSafetyMaxDepthOfCut", None),
                    "min_tool_clearance": getattr(m, "hasSafetyMinToolClearanceMM", None),
                },
                "ontology_sources": self._sources_for([m]),
            })
        return results

    def list_materials(self) -> List[Dict]:
        results = []
        for mat in self.materials_onto.Material.instances():
            results.append({
                "id": mat.name,
                "name": getattr(mat, "hasMaterialLabel", None) or mat.name,
                "properties": {
                    "hardness_hrc": getattr(mat, "hasHardnessHRC", None),
                    "tensile_strength_mpa": getattr(mat, "hasTensileStrengthMPa", None),
                    "yield_strength_mpa": getattr(mat, "hasYieldStrengthMPa", None),
                    "density_g_cm3": getattr(mat, "hasDensityGCM3", None),
                },
                "machinability_rating": getattr(mat, "hasMachinabilityRating", None),
                "recommended_coolant": getattr(mat, "hasRecommendedCoolant", "") or "",
                "ontology_sources": self._sources_for([mat]),
            })
        return results

    # -- legacy-id-keyed dicts (for validator.py/simulator.py, replacing their
    #    former `from ontology import MACHINES, TOOLS, MATERIALS, OPERATIONS`) --
    #
    # These read only asserted OWL facts (no Pellet reasoning needed) and key
    # the result by the same snake_case ids ontology.py used to, so RAL-side
    # consumers built against that shape need only a constructor-argument
    # change, not a data-shape rewrite.

    def legacy_machines_dict(self) -> Dict[str, Dict]:
        return {
            MACHINE_INDIVIDUAL_TO_KEY.get(m["id"], m["id"]): m
            for m in self.list_machines()
        }

    def legacy_tools_dict(self) -> Dict[str, Dict]:
        return {
            OWL_TOOL_TO_LEGACY_ID.get(t["id"], t["id"]): t
            for t in self.list_tools()
        }

    def legacy_materials_dict(self) -> Dict[str, Dict]:
        return {
            MATERIAL_INDIVIDUAL_TO_KEY.get(m["id"], m["id"]): m
            for m in self.list_materials()
        }

    def legacy_operations_dict(self) -> Dict[str, Dict]:
        return {
            OWL_OPERATION_TO_LEGACY_ID.get(o["id"], o["id"]): o
            for o in self.list_operations()
        }

    # -- machine compatibility + tool preference (for KEFC's exception gate) -

    def machine_supports_operation(self, machine_name: str, operation_name: str) -> bool:
        machine = getattr(self.machines_onto, machine_name, None)
        if machine is None:
            return False
        return any(
            getattr(op, "name", None) == operation_name
            for op in getattr(machine, "supportsOperation", [])
        )

    def operation_requires_tool_along_feature_axis(self, operation_name: str) -> bool:
        op = getattr(self.process_onto, operation_name, None)
        return bool(getattr(op, "requiresToolAlongFeatureAxis", False)) if op is not None else False

    def machine_spindle_axis(self, machine_name: str) -> Optional[str]:
        machine = getattr(self.machines_onto, machine_name, None)
        return getattr(machine, "hasSpindleAxis", None) if machine is not None else None

    def machine_supported_tool_orientations(self, machine_name: str) -> List[str]:
        machine = getattr(self.machines_onto, machine_name, None)
        if machine is None:
            return []
        return [getattr(o, "name", str(o)) for o in getattr(machine, "supportsToolOrientation", [])]

    def serialisation_profile_tool_orientations(self, profile_name: str) -> Optional[List[str]]:
        """Tool orientations a serialisation profile declares it can express
        (serialisation_profiles.owl: profileSupportsToolOrientation), or None
        when no such profile is declared."""
        profile = getattr(self.profiles_onto, profile_name, None)
        if profile is None:
            return None
        return [getattr(o, "name", str(o)) for o in getattr(profile, "profileSupportsToolOrientation", [])]

    def get_preferred_tool(self, operation_name: str) -> Optional[str]:
        op = getattr(self.process_onto, operation_name, None)
        preferred = getattr(op, "hasPreferredTool", None) if op is not None else None
        return preferred.name if preferred is not None else None

    # -- provenance-aware readback -------------------------------------------

    def get_operations(self, feature_individual) -> List[Dict]:
        results = []
        for op in getattr(feature_individual, "requiresOperation", []):
            rule_id = self._explain_operation(feature_individual, op)
            results.append({
                "operation": op.name,
                "rule_id": rule_id,
                "ontology_sources": self._sources_for([op, feature_individual]),
                "precedence": getattr(op, "hasPrecedenceOrder", None),
            })
        return results

    def get_tools(self, feature_individual) -> List[Dict]:
        results = []
        for tool in getattr(feature_individual, "requiresTool", []):
            results.append({
                "tool": tool.name,
                "rule_id": "feature_tool_from_operation",
                "ontology_sources": self._sources_for([tool, feature_individual]),
            })
        return results

    def get_cutting_parameter_sets(self, feature_individual) -> List[Dict]:
        results = []
        for pset in getattr(feature_individual, "hasCuttingParameterSet", []):
            operation = getattr(pset, "forOperation", None)
            material = getattr(pset, "forMaterial", None)
            rule_id = self._explain_param_set(operation, material)
            results.append({
                "param_set": pset.name,
                "operation": operation.name if operation else None,
                "material": material.name if material else None,
                "feed_rate": {"value": pset.hasFeedRateValue, "unit": pset.hasFeedRateUnit},
                "spindle_speed": {"value": pset.hasSpindleSpeedValue, "unit": pset.hasSpindleSpeedUnit},
                "depth_of_cut": {"value": pset.hasDepthOfCutValue, "unit": pset.hasDepthOfCutUnit},
                "coolant": pset.requiresCoolant,
                "rule_id": rule_id,
                "ontology_sources": self._sources_for([pset]),
            })
        return results

    # -- provenance matching (see module docstring's honesty note) ----------

    def _explain_operation(self, feature_individual, op_individual) -> Optional[str]:
        feature_types = {c.name for c in feature_individual.INDIRECT_is_a if hasattr(c, "name")}
        for pr in self.rules:
            if pr.consequent_property != "requiresOperation":
                continue
            if pr.consequent_object != op_individual.name:
                continue
            if set(pr.antecedent_classes) & feature_types:
                return pr.rule_id
        return None

    def _explain_param_set(self, op_individual, material_individual) -> Optional[str]:
        op_name = op_individual.name if op_individual else None
        mat_name = material_individual.name if material_individual else None
        for pr in self.rules:
            if pr.consequent_property != "hasCuttingParameterSet":
                continue
            if pr.op_individual != op_name:
                continue
            if pr.material_individual is not None and pr.material_individual != mat_name:
                continue
            return pr.rule_id
        return None

    @staticmethod
    def _sources_for(entities) -> List[str]:
        sources = set()
        for e in entities:
            onto = getattr(e, "namespace", None)
            onto = getattr(onto, "ontology", onto)
            base_iri = getattr(onto, "base_iri", None)
            if base_iri:
                sources.add(base_iri)
        return sorted(sources)

    # -- diagnostics ----------------------------------------------------------

    def reasoning_report(self) -> Dict:
        return {
            "skl_version": SKL_VERSION,
            "reasoner": REASONER_NAME,
            "reasoning_status": self.reasoning_status,
            "java_exe": self.java_exe,
            "rule_count": len(self.rules),
            "ontologies": [
                onto.base_iri for onto in
                (self.process_onto, self.materials_onto, self.tools_onto,
                 self.machines_onto, self.params_onto, self.case_onto, self.profiles_onto, *self.config_ontos)
            ],
        }


def _replace_anonymous_ontology_iri(output_path: str, new_iri: str) -> None:
    """
    Give the exported file its own real ontology identity instead of
    `http://anonymous`.

    Every owlready2 `World` unconditionally pre-creates a permanent
    bookkeeping ontology at `http://anonymous/` (see `World.__init__` in
    owlready2/namespace.py: "Pre-create, in order to avoid creation during a
    reading sequence") — this exists in every World regardless of what's
    loaded into it, contributes exactly one triple (its own `owl:Ontology`
    self-declaration), and is otherwise empty (no owl:imports, no other
    axioms). Because `export_unified_knowledge_base` saves the whole
    `World` (see that function's docstring for why), this placeholder gets
    serialized too, as a 7th, contentless, import-less `owl:Ontology`
    declaration sitting alongside the 6 real ones — confirmed by direct
    inspection to be the ONLY thing at that IRI (the literal string
    "anonymous" occurs exactly once in an exported file). A document with
    an extra, unrelated ontology header like that is non-standard and is a
    known source of tools like Protege misattributing declarations between
    ontologies when the file is opened.

    Fixed here with a single, surgical text replacement rather than a full
    rdflib re-serialization of the saved file: re-writing the whole graph
    risks reformatting/reordering owlready2's SWRL-rule XML structure and
    abbreviated namespace prefixes, for no benefit over replacing the one
    attribute value that actually needs to change.
    """
    with open(output_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = text.replace('rdf:about="http://anonymous"', f'rdf:about="{new_iri}"')
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_protege_catalog(output_path: str, case_base_iri: str) -> None:
    """
    Write a Protege XML catalog (catalog-v001.xml) next to `output_path`,
    mapping the 5 foundation ontology IRIs (and this file's own IRI) to local
    files. Protege auto-detects catalog-v001.xml in the directory a file is
    opened from and resolves owl:imports through it instead of over the
    network — without this, motor_shaft_case.owl's abstract HTTP import IRIs
    (see export_unified_knowledge_base's docstring) cause "unresolved import"
    errors when the exported file is opened standalone.

    Overwrites any existing catalog-v001.xml in that directory. Fine here
    because `output_dir` is a generated-artifacts directory this pipeline
    already owns (features.json, manufacturing_plan.json, etc. are all
    overwritten on every run too) — this is not a hand-maintained file.
    """
    output_dir = os.path.dirname(os.path.abspath(output_path))
    foundation_files = {
        "http://onto.brep.org/manufacturing/machining-process": "machining_process.owl",
        "http://onto.brep.org/manufacturing/materials": "materials.owl",
        "http://onto.brep.org/manufacturing/tools": "tools.owl",
        "http://onto.brep.org/manufacturing/machines": "machines.owl",
        "http://onto.brep.org/manufacturing/cutting-parameters": "cutting_parameters.owl",
    }

    entries = [(case_base_iri.rstrip("#"), os.path.basename(output_path))]
    for iri, filename in foundation_files.items():
        rel_path = os.path.relpath(os.path.join(FOUNDATION_DIR, filename), output_dir)
        entries.append((iri, rel_path.replace("\\", "/")))

    uris_xml = "\n".join(
        f'        <uri name="{iri}" uri="{path}"/>' for iri, path in entries
    )
    catalog_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<catalog prefer="public" xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">\n'
        '    <group id="Foundation ontology imports, auto-generated by '
        'skl_repository.export_unified_knowledge_base" prefer="public" xml:base="">\n'
        f'{uris_xml}\n'
        '    </group>\n'
        '</catalog>\n'
    )
    catalog_path = os.path.join(output_dir, "catalog-v001.xml")
    with open(catalog_path, "w", encoding="utf-8") as f:
        f.write(catalog_xml)


def export_unified_knowledge_base(reconciled_features, material_key: str,
                                   machine_key: str, output_path: str) -> None:
    """
    Save a genuinely self-contained, reasoner-compatible OWL knowledge base for
    this pipeline run: the full TBox *and* ABox of all 5 foundation ontologies
    (including the named cutting-parameter-set/tool/machine/material
    individuals and their data-property values — e.g.
    AISI1045_Drilling_Params.hasSpindleSpeedValue) + the specialized case
    ontology + the registered SWRL rules + this run's actual asserted Feature
    individuals (with source/confidence provenance as annotations) — to
    `output_path` (RDF/XML), openable in Protégé.

    Deliberately does NOT include Pellet-INFERRED facts (requiresOperation,
    requiresTool, hasCuttingParameterSet, etc.) — only what's asserted plus the
    rules that would derive them. Opening this file, inspecting the rules, and
    running the reasoner is meant to reproduce the same inferred knowledge this
    pipeline used, not read a pre-baked copy of it. See AGENTS.md /
    .codex/architecture.md for why: it matches the intended open -> inspect ->
    reason -> obtain-inferred-knowledge workflow, and avoids a second, easily
    stale copy of "the truth" sitting in the file. The JSON artifacts
    (reasoning_report.json, manufacturing_plan.json with per-parameter rule_id
    provenance) already cover "inspect the results without installing Protégé."

    Uses a fresh, throwaway `SKLRepository` — never the one CFRM/KEFC reasoned
    over — so it is structurally impossible for inferred triples to leak in:
    `sync_reasoner_pellet` materializes inferred triples into its World in
    place (there is no non-destructive reasoning mode), so reusing the reasoned
    repository for export would risk saving them by accident.

    Saves the whole `export_repo.world` (every ontology `_load_ontologies`
    loaded into it: the 5 foundation ontologies + the case ontology), not
    just `export_repo.case_onto`, precisely so the foundation ontologies'
    instance data — not just their `owl:imports` declaration — physically
    ends up in `output_path`. Saving only `case_onto` (as this used to do)
    left the file referencing individuals like `AISI1045_Drilling_Params` by
    name (inside the SWRL rules) without ever defining them, so a reasoner run
    on the standalone file could infer the *link* to a parameter set but the
    linked individual had no values to inspect. This also alongside
    `output_path` (over)writes a `catalog-v001.xml` in the same directory,
    mapping the foundation ontologies' IRIs to `knowledge/foundation/*.owl` by
    relative path (see `_write_protege_catalog`) — belt-and-suspenders should
    Protégé still attempt to resolve the (now redundant, but still present as
    triples) `owl:imports` declarations; it is not required for the data
    itself to be visible any more.

    Saving the whole `World` also carries over its permanent internal
    `http://anonymous` bookkeeping ontology (every owlready2 World has one —
    see `_replace_anonymous_ontology_iri`'s docstring), which would otherwise
    leave the exported file's own ontology IRI as the meaningless
    `http://anonymous` and, per direct observation, seemingly confuse Protégé
    about which ontology some declarations belong to. `_replace_anonymous_ontology_iri`
    gives the file a real identity (`UNIFIED_KB_IRI`) instead.

    Args:
        reconciled_features: the List[ReconciledFeature] from
            SemanticReconciler.reconcile() for this run
        material_key, machine_key: same keys passed to SemanticReconciler
        output_path: where to save the .owl file (RDF/XML)
    """
    export_repo = SKLRepository(machine_key=machine_key)

    with export_repo.case_onto:
        class hasSourceFile(AnnotationProperty, FunctionalProperty):
            """Which KINM input file this feature individual's data came from."""
        class hasSourceFeatureId(AnnotationProperty, FunctionalProperty):
            """The feature's id within its source file, before global renumbering."""
        class hasCFRMConfidence(AnnotationProperty, FunctionalProperty):
            """CFRM's combined mapping/consensus confidence for this feature (0-1)."""
        class isUnmappedFeature(AnnotationProperty, FunctionalProperty):
            """True if CFRM found no corresponding SKL ontology class for this feature type."""
        class isLowConfidenceMapping(AnnotationProperty, FunctionalProperty):
            """True if CFRM's combined confidence fell below its review threshold."""

    for rf in reconciled_features:
        individual, _mapping_confidence = export_repo.create_feature_individual(
            rf.feature_id, rf.feature_type,
            material_key=material_key, machine_key=machine_key,
        )
        source_file = rf.source_feature.get("source_file")
        source_id = rf.source_feature.get("source_id")
        if source_file is not None:
            individual.hasSourceFile = str(source_file)
        if source_id is not None:
            individual.hasSourceFeatureId = str(source_id)
        individual.hasCFRMConfidence = float(rf.confidence)
        individual.isUnmappedFeature = bool(rf.unmapped)
        individual.isLowConfidenceMapping = bool(rf.low_confidence)

    export_repo.world.save(file=output_path, format="rdfxml")
    _replace_anonymous_ontology_iri(output_path, UNIFIED_KB_IRI)
    _write_protege_catalog(output_path, export_repo.case_onto.base_iri)

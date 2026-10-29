"""
KEFC Controller
================
Knowledge Execution & Formalization Controller — the single owner of validation,
alignment, reasoning orchestration, conflict detection, and expert-validation routing
(see AGENTS.md; this replaces the never-implemented CLVP/GTAE responsibilities).

Turns CFRM's reconciled features (`semantic_reconciler.py`) plus SKL's reasoned facts
(`skl_repository.py`) into RAL's process parameter package: a manufacturing plan where
every operation/tool/feed-rate/spindle-speed/depth-of-cut/coolant value is traceable to
a rule id and ontology source, and every step carries a `validation_status`.

Exception gate: a step reaches `auto_approved` only when its feature mapping was
confident, an operation was inferred, a tool was inferred, exactly one (non-conflicting)
cutting-parameter set was inferred, and that parameter set is within the target
machine's safety limits. Any other outcome creates an `ExpertValidationRequest` and the
step is marked `requires_review`.
"""

import re
from typing import Dict, List, Optional

from semantic_reconciler import ReconciledFeature
from expert_validation import ExpertValidationStore
from skl_repository import OWL_OPERATION_TO_LEGACY_ID, OWL_TOOL_TO_LEGACY_ID

VALUE_TOLERANCE = 1e-6

_AXIS_PATTERNS = (
    re.compile(r"\b(?:along|parallel to)\s+(?:the\s+)?(?:negative\s+|positive\s+)?([XYZ])[\s-]*axis", re.I),
    re.compile(r"^\s*([XYZ])[\s-]*axis", re.I),
)


def parse_feature_axis(orientation: Optional[str]) -> Optional[str]:
    """Axis label (X, Y or Z) of a feature's own axis as stated by the
    extractor, or None when the orientation string does not state one (empty,
    or a surface-normal statement such as 'Normal to Y-axis'). No default is
    assumed: an unstated axis is missing knowledge, not an axial hole."""
    if not orientation:
        return None
    for pat in _AXIS_PATTERNS:
        m = pat.search(orientation)
        if m:
            return m.group(1).upper()
    return None


class KEFCController:
    def __init__(self, repo, expert_store: ExpertValidationStore, machine_key: str = "cnc_lathe",
                 serialisation_profile: Optional[str] = None):
        self.repo = repo
        # Serialisation profile of the application layer; the default is the
        # profile gcode_generator.py declares it implements. What the profile
        # can express is read from serialisation_profiles.owl, not from code.
        if serialisation_profile is None:
            from gcode_generator import GCodeGenerator
            serialisation_profile = GCodeGenerator.SERIALISATION_PROFILE
        self.serialisation_profile = serialisation_profile
        self.expert_store = expert_store
        self.machine_key = machine_key
        # The machine individual is resolved from the machine key through the
        # declared key map; an undeclared key fails loudly (KeyError) rather
        # than silently falling back to the lathe.
        self._machine_individual = getattr(repo.machines_onto, self.machine_key_to_owl(machine_key))

    def build_manufacturing_plan(self, reconciled_features: List[ReconciledFeature],
                                  material: str = "steel_1045", machine: str = "cnc_lathe") -> Dict:
        step_specs = []  # list of (ReconciledFeature, operation_fact)

        for rf in reconciled_features:
            if rf.unmapped:
                self.expert_store.create_request(
                    feature_id=rf.feature_id, feature_type=rf.feature_type,
                    reason_code="unresolved_mapping", detail=rf.reason,
                )
                continue

            if rf.low_confidence:
                self.expert_store.create_request(
                    feature_id=rf.feature_id, feature_type=rf.feature_type,
                    reason_code="low_confidence_mapping", detail=rf.reason,
                )
                # Still produce steps for it below (flagged requires_review per
                # step) — low confidence doesn't mean "no plan", it means "a
                # human should confirm this plan before it's trusted".

            operations = self.repo.get_operations(rf.skl_individual)
            if not operations:
                self.expert_store.create_request(
                    feature_id=rf.feature_id, feature_type=rf.feature_type,
                    reason_code="missing_knowledge",
                    detail=f"No SWRL rule inferred any operation for feature type {rf.feature_type!r}.",
                )
                continue

            for op in operations:
                step_specs.append((rf, op))

        # Sequencing read from the ontology's hasPrecedenceOrder data property
        # (machining_process.owl), not a hard-coded Python precedence list.
        step_specs.sort(key=lambda pair: (
            pair[1]["precedence"] if pair[1]["precedence"] is not None else 999,
            pair[0].feature_id,
        ))

        steps = [
            self._build_step(step_number, rf, op, material, machine)
            for step_number, (rf, op) in enumerate(step_specs, start=1)
        ]

        self.expert_store.save()

        # RAL must only ever execute approved steps — see AGENTS.md constraint
        # #6 and .codex/architecture.md. `steps` (all of them, including
        # requires_review) is the full audit record exported to
        # manufacturing_plan.json; `approved_steps` is what main.py hands to
        # generate_gcode().
        approved_steps = [s for s in steps if s["validation_status"] in ("auto_approved", "expert_approved")]

        report = self.repo.reasoning_report()
        return {
            "steps": steps,
            "approved_steps": approved_steps,
            "skl_version": report["skl_version"],
            "reasoner": report["reasoner"],
            "reasoning_status": report["reasoning_status"],
            "expert_validation_summary": self.expert_store.summary(),
        }

    # -- per-step assembly ---------------------------------------------------

    def _build_step(self, step_number: int, rf: ReconciledFeature, op: Dict,
                     material: str, machine: str) -> Dict:
        operation_name = op["operation"]
        # (reason_code, detail) pairs gathered before touching the expert
        # store, so a step with e.g. both a low-confidence mapping and an
        # unsafe value gets both recorded, and so each can be checked against
        # a prior resolution before deciding whether to open a new request.
        exceptions: List[tuple] = []

        if not self.repo.machine_supports_operation(self.machine_key_to_owl(machine), operation_name):
            exceptions.append((
                "machine_incompatible",
                f"Machine {machine!r} does not list {operation_name!r} in supportsOperation.",
            ))

        orientation_exception = self._check_tool_orientation(rf, operation_name, machine)
        if orientation_exception:
            exceptions.append(orientation_exception)
        elif not any(code == "machine_incompatible" for code, _ in exceptions):
            # Short-circuit rule: the serialisation check runs only when the
            # machine checks have passed, so a step the machine cannot do is
            # never given a second, redundant request (see
            # _check_serialisation_profile).
            serialisation_exception = self._check_serialisation_profile(rf, operation_name, machine)
            if serialisation_exception:
                exceptions.append(serialisation_exception)

        tool, tool_rule_id, tool_exception = self._select_tool(rf, operation_name)
        if tool_exception:
            exceptions.append(tool_exception)

        param_sets = [
            p for p in self.repo.get_cutting_parameter_sets(rf.skl_individual)
            if p["operation"] == operation_name
        ]

        parameters = {}
        conflict_detail = self._detect_conflict(param_sets)
        if conflict_detail:
            exceptions.append(("rule_conflict", conflict_detail))
        elif not param_sets:
            exceptions.append((
                "missing_knowledge",
                f"No cutting-parameter rule matched operation {operation_name!r}.",
            ))
        else:
            parameters = self._assemble_parameters(param_sets[0], rf)
            unsafe_detail = self._check_unsafe(parameters)
            if unsafe_detail:
                exceptions.append(("unsafe_value", unsafe_detail))

        # Serialisation inputs are not a planning decision and are not checked
        # here (Revision 7): RAL checks each approved step against its toolpath
        # pattern's input contract, refuses what it would have to guess, and
        # records the refusal as serialisation_input_missing (ral_refusals.py).
        # The orientation-serialisation-profile check above stays in KEFC
        # because the profile's expressiveness is declared in the ontology.

        if rf.low_confidence:
            exceptions.append(("low_confidence_mapping", rf.reason))

        validation_status = self._resolve_exceptions(rf, operation_name, exceptions)

        legacy_operation = OWL_OPERATION_TO_LEGACY_ID.get(operation_name, operation_name)
        return {
            "step_number": step_number,
            "operation": legacy_operation,
            "operation_name": legacy_operation.replace("_", " ").title(),
            "ontology_operation": operation_name,
            "operation_selection_rule_id": op.get("rule_id"),
            "operation_ontology_sources": op.get("ontology_sources"),
            "feature_id": rf.feature_id,
            "feature_type": rf.feature_type,
            "feature_dimensions": rf.source_feature.get("dimensions", {}),
            "feature_location": rf.source_feature.get("absolute_location", {}),
            "tool_id": OWL_TOOL_TO_LEGACY_ID.get(tool["tool"], tool["tool"]) if tool else None,
            "ontology_tool": tool["tool"] if tool else None,
            "tool_selection_rule_id": tool_rule_id,
            "parameters": parameters,
            "material": material,
            "machine": machine,
            "validation_status": validation_status,
        }

    def _resolve_exceptions(self, rf: ReconciledFeature, operation_name: str,
                             exceptions: List[tuple]) -> str:
        """Check each gathered exception against a prior expert resolution
        (ExpertValidationStore is get-or-create + loaded from disk — see
        expert_validation.py) before deciding the step's validation_status.
        A step is only 'expert_approved' when every exception it has is
        individually resolved; any still-open or rejected exception makes
        the whole step 'requires_review'. No exceptions at all -> auto_approved."""
        if not exceptions:
            return "auto_approved"

        from expert_validation import APPROVABLE_WITHOUT_NEW_DATA

        all_resolved = True
        for reason_code, detail in exceptions:
            existing = self.expert_store.find_resolution(rf.feature_id, operation_name, reason_code)
            if (existing is not None and existing.status == "expert_approved"
                    and reason_code in APPROVABLE_WITHOUT_NEW_DATA):
                continue  # this specific exception was already cleared by a human
            all_resolved = False
            self.expert_store.create_request(
                feature_id=rf.feature_id, feature_type=rf.feature_type,
                reason_code=reason_code, operation=operation_name, detail=detail,
            )

        return "expert_approved" if all_resolved else "requires_review"

    def _check_tool_orientation(self, rf: ReconciledFeature, operation_name: str, machine: str):
        """Orientation gate. For operations whose tool axis must coincide with
        the feature axis (machining_process.owl: requiresToolAlongFeatureAxis),
        classify the feature axis as axial or radial relative to the machine's
        spindle axis and check it against the machine's supportsToolOrientation
        capability (machines.owl). Returns (reason_code, detail) or None."""
        if not self.repo.operation_requires_tool_along_feature_axis(operation_name):
            return None
        machine_owl = self.machine_key_to_owl(machine)
        spindle_axis = self.repo.machine_spindle_axis(machine_owl)
        supported = self.repo.machine_supported_tool_orientations(machine_owl)
        if spindle_axis is None or not supported:
            return ("missing_knowledge",
                    f"Machine {machine!r} declares no spindle axis or tool-orientation capability; "
                    f"{operation_name!r} cannot be checked for tool orientation.")
        feature_axis = parse_feature_axis(rf.source_feature.get("orientation"))
        if feature_axis is None:
            return ("missing_knowledge",
                    f"Feature orientation {rf.source_feature.get('orientation')!r} states no axis; "
                    f"{operation_name!r} requires the tool along the feature axis and no axis is assumed.")
        required = "AxialToolOrientation" if feature_axis == spindle_axis.upper() else "RadialToolOrientation"
        if required not in supported:
            return ("orientation_incompatible",
                    f"{operation_name!r} on a feature whose axis is {feature_axis} requires {required} "
                    f"(spindle axis {spindle_axis}); machine {machine!r} supports only {supported}.")
        return None

    def _check_serialisation_profile(self, rf: ReconciledFeature, operation_name: str, machine: str):
        """Serialisation-capability gate (RAL expressiveness).

        Decides, from serialisation_profiles.owl, whether the serialisation
        profile RAL uses (self.serialisation_profile) can express the tool
        orientation the step requires. The required orientation is derived
        exactly as in _check_tool_orientation (feature axis versus the
        machine's spindle axis, for operations with
        requiresToolAlongFeatureAxis).

        Short-circuit rule: this check is evaluated only after the machine
        checks have passed for the step, i.e. only when the operation is in
        the machine's supportsOperation and _check_tool_orientation returned
        no exception. A step the machine itself cannot perform is reported
        once (machine_incompatible, orientation_incompatible or
        missing_knowledge) and never receives an additional
        serialisation_unsupported request, so the expert-validation request
        count is not inflated by a consequence of an already-reported
        exception. Returns (reason_code, detail) or None.
        """
        if not self.repo.operation_requires_tool_along_feature_axis(operation_name):
            return None
        machine_owl = self.machine_key_to_owl(machine)
        spindle_axis = self.repo.machine_spindle_axis(machine_owl)
        feature_axis = parse_feature_axis(rf.source_feature.get("orientation"))
        if spindle_axis is None or feature_axis is None:
            return None  # already reported by the machine check as missing_knowledge
        required = "AxialToolOrientation" if feature_axis == spindle_axis.upper() else "RadialToolOrientation"
        supported = self.repo.serialisation_profile_tool_orientations(self.serialisation_profile)
        if supported is None:
            return ("missing_knowledge",
                    f"Serialisation profile {self.serialisation_profile!r} is not declared in "
                    f"serialisation_profiles.owl; {operation_name!r} cannot be checked for serialisability.")
        if required not in supported:
            return ("serialisation_unsupported",
                    f"{operation_name!r} on a feature whose axis is {feature_axis} requires {required}; "
                    f"machine {machine!r} supports it, but serialisation profile "
                    f"{self.serialisation_profile!r} expresses only {supported}.")
        return None

    def machine_key_to_owl(self, machine_key: str) -> str:
        # Machine key -> OWL individual name (skl_repository.MACHINE_KEY_TO_INDIVIDUAL).
        from skl_repository import MACHINE_KEY_TO_INDIVIDUAL
        return MACHINE_KEY_TO_INDIVIDUAL[machine_key]

    # -- helpers --------------------------------------------------------------

    def _tool_recommended_for(self, tool_name: str, operation_name: str) -> bool:
        tool_ind = getattr(self.repo.tools_onto, tool_name, None)
        if tool_ind is None:
            return False
        return any(
            getattr(op, "name", None) == operation_name
            for op in getattr(tool_ind, "recommendedForOperation", [])
        )

    def _select_tool(self, rf: ReconciledFeature, operation_name: str):
        """Returns (tool_dict_or_None, rule_id_or_None, exception_or_None).

        Never picks arbitrarily among multiple untied candidates: if the
        ontology names a preferred tool (tools.owl:hasPreferredTool) among
        the candidates, that's the traceable selection rule; with exactly
        one candidate there's nothing to choose between; with more than one
        candidate and no recorded preference, this is a genuine knowledge
        gap — it's flagged for expert review rather than silently taking
        Python's list[0]."""
        candidates = [
            t for t in self.repo.get_tools(rf.skl_individual)
            if self._tool_recommended_for(t["tool"], operation_name)
        ]
        if not candidates:
            return None, None, ("missing_knowledge", f"No tool inferred for operation {operation_name!r}.")

        if len(candidates) == 1:
            return candidates[0], "feature_tool_from_operation", None

        preferred_name = self.repo.get_preferred_tool(operation_name)
        preferred = next((t for t in candidates if t["tool"] == preferred_name), None)
        if preferred is not None:
            return preferred, "preferred_tool_selection", None

        candidate_names = sorted(t["tool"] for t in candidates)
        fallback = next(t for t in candidates if t["tool"] == candidate_names[0])
        return fallback, None, (
            "missing_knowledge",
            f"{len(candidates)} tools ({candidate_names}) are recommendedForOperation "
            f"{operation_name!r} with no hasPreferredTool recorded to break the tie.",
        )

    @staticmethod
    def _detect_conflict(param_sets: List[Dict]) -> Optional[str]:
        if len(param_sets) <= 1:
            return None
        first = param_sets[0]
        for other in param_sets[1:]:
            for key in ("feed_rate", "spindle_speed", "depth_of_cut"):
                v1, v2 = first[key]["value"], other[key]["value"]
                if v1 is None or v2 is None or abs(v1 - v2) > VALUE_TOLERANCE:
                    return (
                        f"Conflicting cutting-parameter sets {first['param_set']!r} vs "
                        f"{other['param_set']!r} disagree on {key} ({v1} != {v2})."
                    )
        return None

    @staticmethod
    def _assemble_parameters(pset: Dict, rf: ReconciledFeature) -> Dict:
        input_facts = {
            "feature_id": rf.feature_id,
            "feature_type": rf.feature_type,
            "material": pset["material"],
            "mapping_confidence": rf.confidence,
        }

        def trace(value, unit):
            return {
                "value": value,
                "unit": unit,
                "source": "swrl_rule",
                "rule_id": pset["rule_id"],
                "ontology_sources": pset["ontology_sources"],
                "input_facts": input_facts,
            }

        return {
            "feed_rate": trace(pset["feed_rate"]["value"], pset["feed_rate"]["unit"]),
            "spindle_speed": trace(pset["spindle_speed"]["value"], pset["spindle_speed"]["unit"]),
            "depth_of_cut": trace(pset["depth_of_cut"]["value"], pset["depth_of_cut"]["unit"]),
            "coolant": trace(pset["coolant"], "bool"),
        }

    def _check_unsafe(self, parameters: Dict) -> Optional[str]:
        m = self._machine_individual
        violations = []
        checks = (
            ("feed_rate", m.hasSafetyMaxFeedRate),
            ("spindle_speed", m.hasSafetyMaxRPM),
            ("depth_of_cut", m.hasSafetyMaxDepthOfCut),
        )
        for key, limit in checks:
            value = parameters[key]["value"]
            if value is not None and limit is not None and value > limit:
                violations.append(f"{key} {value} exceeds machine safety limit {limit}")
        return "; ".join(violations) if violations else None

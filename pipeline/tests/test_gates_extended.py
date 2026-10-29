"""
Fault-injection tests for the revision-round gate extensions:

  * type-admissibility gate in KINM reconciliation (Eq. 3, tau_min);
  * orientation-aware capability gate (machines.owl supportsToolOrientation,
    machining_process.owl requiresToolAlongFeatureAxis);
  * plan-to-programme consistency (every approved step is one segment).

Each test drives the full reasoning stack (Pellet via owlready2), as the
existing tests do. Test artefacts are written to tests/output/, never to the
repository's output/ directory.
"""

import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

TEST_OUTPUT_DIR = os.path.join(BASE_DIR, 'tests', 'output')
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

from feature_parser import reconcile_features, calculate_type_similarity  # noqa: E402
from semantic_reconciler import SemanticReconciler  # noqa: E402
from kefc_controller import KEFCController, parse_feature_axis  # noqa: E402
from expert_validation import ExpertValidationStore  # noqa: E402
from gcode_generator import GCodeGenerator  # noqa: E402


def _store(name):
    path = os.path.join(TEST_OUTPUT_DIR, name)
    if os.path.exists(path):
        os.remove(path)  # the store persists by design; each test starts clean
    return ExpertValidationStore(path)


def _hole(feature_id, orientation, type_="Through Hole", loc=(0.0, 15.0, 159.5), source="test"):
    return {
        "id": feature_id, "type": type_, "description": "injected",
        "absolute_location": {"X": loc[0], "Y": loc[1], "Z": loc[2]},
        "relative_position": {}, "dimensions": {"Ø": 8.0, "L": 20.0}, "orientation": orientation,
        "tolerance": "General", "source_file": source, "source_id": feature_id,
        "match_confidence": 1.0, "reconciliation": "primary_only",
    }


def _plan_for(features, store, machine_patch=None):
    reconciler = SemanticReconciler()
    if machine_patch:
        machine_patch(reconciler.repo)
    reconciled = reconciler.reconcile(features)
    kefc = KEFCController(reconciler.repo, store)
    return kefc.build_manufacturing_plan(reconciled), store


# --------------------------------------------------------------- KINM gate

def test_type_gate_blocks_cross_family_merge():
    """Two records at the same location whose labels are cross-family
    lookalikes (Through Hole / Slot, tau = 0.3) must not merge under Eq. 3,
    however well their positions and dimensions agree; with the gate removed
    (tau_min = 0) the additive score alone merges them."""
    primary = [_hole(1, "Along Y-axis", "Through Hole", source="A")]
    secondary = [_hole(1, "Along Y-axis", "Slot", source="B")]
    assert calculate_type_similarity("Through Hole", "Slot") == 0.3

    gated = reconcile_features([dict(p) for p in primary], [dict(s) for s in secondary])
    assert len(gated) == 2 and {f["reconciliation"] for f in gated} == {"primary_only", "secondary_only"}

    ablated = reconcile_features([dict(p) for p in primary], [dict(s) for s in secondary], type_gate=0.0)
    assert len(ablated) == 1 and ablated[0]["reconciliation"] == "merged"
    assert ablated[0]["match_confidence"] > 0.5
    print(f"  ✓ gate keeps 2 entities; ablated criterion merges them at S = {ablated[0]['match_confidence']:.2f}")


# -------------------------------------------------------- orientation gate

def test_parse_feature_axis():
    assert parse_feature_axis("Along Z-axis") == "Z"
    assert parse_feature_axis("Parallel to Z-axis, protruding along negative Y-axis") == "Z"
    assert parse_feature_axis("Z-axis") == "Z"
    assert parse_feature_axis("Along Y-axis") == "Y"
    assert parse_feature_axis("Normal to Y-axis") is None
    assert parse_feature_axis("") is None and parse_feature_axis(None) is None


def test_orientation_gate_withholds_radial_hole_on_lathe():
    """A hole whose axis is perpendicular to the lathe spindle axis needs a
    radial tool orientation; the modelled lathe declares only the axial
    orientation, so the drilling step is withheld as orientation_incompatible
    even though DrillingOp itself is in supportsOperation."""
    plan, store = _plan_for([_hole(1, "Along Y-axis")], _store("test_evr_orientation_radial.json"))
    assert len(plan["steps"]) == 1 and plan["steps"][0]["operation"] == "drilling"
    assert plan["steps"][0]["validation_status"] == "requires_review"
    codes = {r.reason_code for r in store.all_requests()}
    assert codes == {"orientation_incompatible"}, codes
    print("  ✓ radial drilling on a lathe without driven tooling withheld (orientation_incompatible)")


def test_orientation_gate_admits_axial_hole():
    plan, store = _plan_for([_hole(1, "Along Z-axis", loc=(0.0, 0.0, 150.0))],
                            _store("test_evr_orientation_axial.json"))
    assert plan["steps"][0]["validation_status"] == "auto_approved"
    assert store.all_requests() == []
    print("  ✓ axial drilling auto-approved; no spurious orientation exception")


def _add_driven_tooling(repo):
    lathe = repo.machines_onto.CNCLatheFanuc0iTD
    lathe.supportsToolOrientation.append(repo.machines_onto.RadialToolOrientation)


def test_orientation_gate_admits_radial_hole_with_driven_tooling():
    """The same radial hole on a machine that declares the radial tool
    orientation (driven tooling) passes the machine's orientation check: the
    gate's decision follows the capability facts, not the operation name. It
    is then withheld by the serialisation-profile check, because RAL's
    turning profile (serialisation_profiles.owl) declares only the axial
    orientation; the step must not reach a serialiser that would emit it as
    an axial cycle."""
    plan, store = _plan_for([_hole(1, "Along Y-axis")], _store("test_evr_orientation_driven.json"),
                            machine_patch=_add_driven_tooling)
    assert plan["steps"][0]["validation_status"] == "requires_review"
    codes = {r.reason_code for r in store.all_requests()}
    assert codes == {"serialisation_unsupported"}, codes
    print("  ✓ machine admits radial drilling; RAL profile withholds it (serialisation_unsupported)")


def test_radial_hole_admitted_by_profile_is_refused_by_axial_serialiser():
    """With a serialisation profile that declares the radial orientation, the
    radial hole on the driven-tooling machine passes the machine, orientation
    and profile checks and KEFC approves it. RAL then refuses it: the drilling
    pattern is axial and needs an on-axis position (location X = Y = 0),
    which a radial hole at Y = 15 does not have. Declaring a radial profile
    without a radial toolpath pattern therefore cannot put a radial hole into
    the programme; the refusal is recorded as serialisation_input_missing."""
    from ral_refusals import record_refusals, REFUSAL_REASON_CODE
    reconciler = SemanticReconciler()
    _add_driven_tooling(reconciler.repo)
    reconciled = reconciler.reconcile([_hole(1, "Along Y-axis")])
    profiles = reconciler.repo.profiles_onto
    with profiles:
        p = profiles.SerialisationProfile("TestDrivenToolProfile")
        p.profileSupportsToolOrientation = [reconciler.repo.machines_onto.AxialToolOrientation,
                                            reconciler.repo.machines_onto.RadialToolOrientation]
    store = _store("test_evr_profile_radial.json")
    plan = KEFCController(reconciler.repo, store,
                          serialisation_profile="TestDrivenToolProfile").build_manufacturing_plan(reconciled)
    assert plan["steps"][0]["validation_status"] == "auto_approved", store.all_requests()
    assert store.all_requests() == []
    g = GCodeGenerator('steel_1045', 'cnc_lathe')
    text = g.generate_program(plan["approved_steps"]).get_program_text()
    assert '[step 1]' not in text and g.serialised_steps == []
    assert len(g.refusals) == 1 and any('on-axis position' in m for m in g.refusals[0]['missing_inputs'])
    record_refusals(g.refusals, store)
    assert [r.reason_code for r in store.all_requests()] == [REFUSAL_REASON_CODE]
    print("  ✓ radial hole approved by KEFC under a radial profile; refused and recorded by RAL")


def test_undeclared_serialisation_profile_is_missing_knowledge():
    """An undeclared profile is not assumed capable: axial drilling is
    routed to review as missing_knowledge."""
    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile([_hole(1, "Along Z-axis", loc=(0.0, 0.0, 150.0))])
    store = _store("test_evr_profile_undeclared.json")
    plan = KEFCController(reconciler.repo, store,
                          serialisation_profile="NoSuchProfile").build_manufacturing_plan(reconciled)
    assert plan["steps"][0]["validation_status"] == "requires_review"
    assert {r.reason_code for r in store.all_requests()} == {"missing_knowledge"}


def test_orientation_gate_treats_unstated_axis_as_missing_knowledge():
    """No axis is assumed: a hole whose orientation states no axis is routed
    to review as missing_knowledge rather than being treated as axial."""
    plan, store = _plan_for([_hole(1, "Normal to Y-axis")], _store("test_evr_orientation_unstated.json"))
    assert plan["steps"][0]["validation_status"] == "requires_review"
    codes = {r.reason_code for r in store.all_requests()}
    assert codes == {"missing_knowledge"}, codes
    print("  ✓ unstated hole axis routed to review as missing_knowledge")


# --------------------------------------------------------- plan/programme

def test_plan_to_programme_consistency_on_real_case():
    """Every KEFC-approved step of the reference case is either serialised as
    exactly one operation segment or refused by RAL with a recorded
    serialisation_input_missing request: approved = serialised + refused."""
    from ral_refusals import record_refusals, check_ral_accounting, REFUSAL_REASON_CODE
    sys.path.insert(0, BASE_DIR)
    from main import load_and_parse_features
    motor_dir = os.path.join(BASE_DIR, 'data', 'motor_data')
    features = load_and_parse_features(
        [os.path.join(motor_dir, 'features_eixo_step_Gemini31Pro.txt'),
         os.path.join(motor_dir, 'features_eixo_step_Gemini35flash.txt')],
        [os.path.join(motor_dir, 'draw_features_eixo_Gemini31Pro.txt'),
         os.path.join(motor_dir, 'draw_features_eixo_Gemini35flash.txt')])
    plan, store = _plan_for(features, _store("test_evr_plan_programme.json"))
    approved = plan["approved_steps"]
    g = GCodeGenerator('steel_1045', 'cnc_lathe')
    program = g.generate_program(approved)
    segments = [b for b in program.blocks if b.startswith('(--- ') and ': ' in b
                and not b.startswith('(--- Tool Change') and not b.startswith('(--- Machine')]
    assert len(approved) == 27
    assert len(segments) == len(g.serialised_steps) == 9
    assert [s['step_number'] for s in g.serialised_steps] == [3, 4, 5, 10, 11, 12, 17, 18, 24]
    assert [r['step_number'] for r in g.refusals] == [1, 2, 6, 7, 8, 9, 13, 14, 15, 16, 21, 22, 23,
                                                      25, 26, 27, 28, 29]
    record_refusals(g.refusals, store)
    acc = check_ral_accounting(approved, g.serialised_steps, g.refusals, store)
    assert acc['passed'] and acc['handed'] == acc['serialised'] + acc['refused']
    assert sum(r.reason_code == REFUSAL_REASON_CODE for r in store.all_requests()) == 18
    print(f"  ✓ {len(approved)} approved = {acc['serialised']} serialised + {acc['refused']} refused")


def test_ral_accounting_detects_lost_or_unrecorded_refusal():
    """Fault injection on the RAL accounting: a step that is neither
    serialised nor refused, or a refusal without a store record, fails."""
    from ral_refusals import check_ral_accounting
    steps = [{'step_number': n, 'operation': 'facing', 'feature_id': n, 'feature_type': 'Boss',
              'feature_dimensions': {}, 'feature_location': {'X': 0.0, 'Y': 0.0, 'Z': 10.0}} for n in (1, 2)]
    serialised, refusals = GCodeGenerator.partition_steps(steps)
    assert serialised == [] and len(refusals) == 2
    store = _store("test_evr_ral_accounting.json")
    with pytest.raises(RuntimeError, match='without a store record'):
        check_ral_accounting(steps, serialised, refusals, store)
    with pytest.raises(RuntimeError, match='handed'):
        check_ral_accounting(steps, serialised, refusals[:1], store)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nall extended gate tests passed")

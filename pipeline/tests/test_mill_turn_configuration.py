"""
Second machine configuration: a turning centre with driven tooling
(knowledge/specialized/mill_turn_configuration.owl, machine key
'cnc_mill_turn'). It has the lathe's envelope and safety limits and differs
only in its capability model (MillingOp supported; axial and radial tool
orientations). The gating code is unchanged, so the only expected effect on
the real case is that the machine- and orientation-capability exceptions
disappear, while every other exception (here: the low-confidence mapping of
the three secondary-only Slot entities) still withholds its step.
"""
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))
sys.path.insert(0, os.path.join(BASE_DIR, 'tests'))

TEST_OUTPUT_DIR = os.path.join(BASE_DIR, 'tests', 'output')
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

from skl_repository import SKLRepository, SKLReasonerError  # noqa: E402
from semantic_reconciler import SemanticReconciler  # noqa: E402
from kefc_controller import KEFCController  # noqa: E402
from expert_validation import ExpertValidationStore  # noqa: E402
from test_skl_kefc import _motor_shaft_features  # noqa: E402


def test_mill_turn_capability_is_declared_and_lathe_unchanged():
    repo = SKLRepository(machine_key='cnc_mill_turn')
    assert repo.machine_supports_operation('CNCMillTurn', 'MillingOp')
    assert set(repo.machine_supported_tool_orientations('CNCMillTurn')) == {
        'AxialToolOrientation', 'RadialToolOrientation'}
    assert repo.machine_spindle_axis('CNCMillTurn') == 'Z'
    # The lathe's declaration is untouched by the configuration ontology.
    assert not repo.machine_supports_operation('CNCLatheFanuc0iTD', 'MillingOp')
    assert repo.machine_supported_tool_orientations('CNCLatheFanuc0iTD') == ['AxialToolOrientation']
    # The reference (lathe) repository does not load the configuration at all.
    lathe_repo = SKLRepository()
    assert getattr(lathe_repo.machines_onto, 'CNCMillTurn', None) is None


def test_unknown_machine_key_fails_loudly():
    with pytest.raises(SKLReasonerError):
        SKLRepository(machine_key='cnc_five_axis')


def _mill_turn_plan(store_name, serialisation_profile=None, radial_profile=False):
    features = _motor_shaft_features()
    reconciler = SemanticReconciler(machine_key='cnc_mill_turn')
    reconciled = reconciler.reconcile(features)
    if radial_profile:
        repo = reconciler.repo
        with repo.profiles_onto:
            p = repo.profiles_onto.SerialisationProfile(serialisation_profile)
            p.profileSupportsToolOrientation = [repo.machines_onto.AxialToolOrientation,
                                                repo.machines_onto.RadialToolOrientation]
    evr_path = os.path.join(TEST_OUTPUT_DIR, store_name)
    if os.path.exists(evr_path):
        os.remove(evr_path)
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store, machine_key='cnc_mill_turn',
                          serialisation_profile=serialisation_profile)
    return kefc.build_manufacturing_plan(reconciled, machine='cnc_mill_turn'), store


def test_real_case_on_mill_turn():
    """Machine checks pass for the two radially orientated Through Hole
    drilling steps (19, 20), but RAL's turning profile cannot express a
    radial tool, so KEFC withholds them as serialisation_unsupported (a
    declared capability in serialisation_profiles.owl); the three milling
    steps stay withheld on low confidence only. Serialisation inputs are
    RAL's concern (Revision 7) and do not affect the KEFC outcome."""
    plan, store = _mill_turn_plan('test_evr_mill_turn.json')
    steps = plan['steps']
    assert len(steps) == 32
    assert len(plan['approved_steps']) == 27
    withheld = {s['step_number']: s for s in steps if s['validation_status'] != 'auto_approved'}
    assert sorted(withheld) == [19, 20, 30, 31, 32]
    assert all(withheld[n]['feature_type'] == 'Through Hole' for n in (19, 20))
    codes_by_feature = {}
    for r in store.all_requests():
        codes_by_feature.setdefault(r.feature_id, set()).add(r.reason_code)
    for n in (19, 20):
        assert codes_by_feature[withheld[n]['feature_id']] == {'serialisation_unsupported'}
    assert {c for cs in codes_by_feature.values() for c in cs} == {'low_confidence_mapping', 'serialisation_unsupported'}


def test_real_case_on_mill_turn_with_radial_profile():
    """Unit level: a serialisation profile that declares the radial
    orientation lets KEFC approve steps 19 and 20. RAL then refuses them: the
    axial drilling pattern needs an on-axis position (and a length) that the
    radial through-holes do not have, so declaring the profile without a
    radial toolpath pattern cannot put a radial hole into the programme."""
    from gcode_generator import GCodeGenerator
    plan, store = _mill_turn_plan('test_evr_mill_turn_radial_profile.json',
                                  serialisation_profile='TestDrivenToolProfile', radial_profile=True)
    withheld = [s['step_number'] for s in plan['steps'] if s['validation_status'] != 'auto_approved']
    assert len(plan['approved_steps']) == 29 and withheld == [30, 31, 32]
    assert {r.reason_code for r in store.all_requests()} == {'low_confidence_mapping'}
    _, refusals = GCodeGenerator.partition_steps(plan['approved_steps'])
    by_step = {r['step_number']: r for r in refusals}
    for n in (19, 20):
        assert any('on-axis position' in m for m in by_step[n]['missing_inputs']), by_step[n]

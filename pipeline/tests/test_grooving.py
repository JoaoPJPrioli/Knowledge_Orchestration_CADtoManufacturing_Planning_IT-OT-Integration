"""
Grooving toolpath: plunge from the feature's outer diameter to its
groove-bottom diameter, both taken from the plan, never defaulted; a groove
without them is withheld by KEFC (missing_knowledge) and refused by RAL.
"""
import os
import re
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

TEST_OUTPUT_DIR = os.path.join(BASE_DIR, 'tests', 'output')
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

from gcode_generator import GCodeGenerator, GCodeProgram  # noqa: E402


def _pv(v, u):
    return {'value': v, 'unit': u, 'source': 'swrl_rule', 'rule_id': 'test', 'ontology_sources': []}


def _groove_step(dims, z=38.0, step=29):
    return {'step_number': step, 'operation': 'grooving', 'feature_type': 'Groove', 'tool_id': 'grooving_tool',
            'feature_id': 17, 'feature_dimensions': dims, 'feature_location': {'X': 0.0, 'Y': 0.0, 'Z': z},
            'parameters': {'feed_rate': _pv(0.08, 'mm/rev'), 'spindle_speed': _pv(600.0, 'RPM'),
                           'depth_of_cut': _pv(0.5, 'mm'), 'coolant': _pv(True, 'bool')}}


def _segment_x_words(text, step):
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if f'[step {step}]' in ln)
    xs = []
    for ln in lines[start + 1:]:
        if ln.startswith('(--- '):
            break
        m = re.search(r'\bX(-?\d+(?:\.\d+)?)', ln.split('(')[0])
        if m:
            xs.append(float(m.group(1)))
    return xs


@pytest.mark.parametrize('dims, bottom, outer', [
    ({'outer_diameter': 24.0, 'groove_bottom_diameter': 22.0}, 22.0, 24.0),
    ({'outer_diameter': 24.0, 'groove_depth': 0.2}, 23.6, 24.0),
])
def test_grooving_plunge_stays_between_bottom_and_approach(dims, bottom, outer):
    g = GCodeGenerator()
    text = g.generate_program([_groove_step(dims)]).get_program_text()
    xs = _segment_x_words(text, 29)
    approach = outer + GCodeGenerator.GROOVE_APPROACH_CLEARANCE_MM
    assert xs, 'no X words in the grooving segment'
    assert all(x >= 0.0 for x in xs)
    assert all(bottom - 1e-9 <= x <= approach + 1e-9 for x in xs), xs
    assert min(xs) == pytest.approx(bottom) and max(xs) == pytest.approx(approach)
    assert g.envelope_excursions == []


@pytest.mark.parametrize('dims', [{}, {'Ø': 22.0}, {'outer_diameter': 24.0},
                                  {'outer_diameter': 24.0, 'groove_bottom_diameter': 26.0}])
def test_grooving_without_plan_diameters_is_refused(dims):
    assert GCodeGenerator.missing_serialisation_inputs('grooving', dims)
    g = GCodeGenerator()
    text = g.generate_program([_groove_step(dims)]).get_program_text()
    assert '[step 29]' not in text and g.serialised_steps == []
    assert [r['step_number'] for r in g.refusals] == [29] and g.refusals[0]['missing_inputs']
    # The toolpath method itself still refuses if called directly.
    with pytest.raises(ValueError, match='cannot be serialised'):
        g._generate_grooving(GCodeProgram(1),
                             _groove_step(dims)['parameters'], dims, {'X': 0.0, 'Y': 0.0, 'Z': 38.0})


def test_ral_refuses_groove_without_diameters_and_records_it():
    """KEFC decides on planning knowledge only and approves both grooves
    (Revision 7); RAL serialises the one with plan diameters and refuses the
    one without, recording a serialisation_input_missing request."""
    from semantic_reconciler import SemanticReconciler
    from kefc_controller import KEFCController
    from expert_validation import ExpertValidationStore
    from ral_refusals import record_refusals, check_ral_accounting
    path = os.path.join(TEST_OUTPUT_DIR, 'test_evr_grooving.json')
    if os.path.exists(path):
        os.remove(path)
    groove = {'id': 1, 'type': 'Groove', 'description': 'injected', 'absolute_location': {'X': 0.0, 'Y': 0.0, 'Z': 38.0},
              'relative_position': {}, 'dimensions': {}, 'orientation': 'Parallel to Z-axis', 'tolerance': 'General',
              'source_file': 'test', 'source_id': 1, 'match_confidence': 1.0, 'reconciliation': 'primary_only'}
    with_dims = dict(groove, id=2, dimensions={'outer_diameter': 24.0, 'groove_bottom_diameter': 22.0})
    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile([groove, with_dims])
    store = ExpertValidationStore(path)
    plan = KEFCController(reconciler.repo, store).build_manufacturing_plan(reconciled)
    by_feature = {s['feature_id']: s for s in plan['steps'] if s['operation'] == 'grooving'}
    assert by_feature[1]['validation_status'] == 'auto_approved'
    assert by_feature[2]['validation_status'] == 'auto_approved'
    assert store.all_requests() == []
    g = GCodeGenerator()
    g.generate_program(plan['approved_steps'])
    assert [s['feature_id'] for s in g.serialised_steps if s['operation'] == 'grooving'] == [2]
    assert [r['source_entity']['feature_id'] for r in g.refusals if r['operation'] == 'grooving'] == [1]
    record_refusals(g.refusals, store)
    check_ral_accounting(plan['approved_steps'], g.serialised_steps, g.refusals, store)
    assert {(r.feature_id, r.reason_code) for r in store.all_requests()} == {(1, 'serialisation_input_missing')}

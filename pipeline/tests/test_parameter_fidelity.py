"""
Plan-to-programme parameter fidelity (src/programme_fidelity.py) and the
serialiser's per-segment spindle/coolant emission (gcode_generator.py), plus
the fixed-order SPARQL suite's per-configuration expectations.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

TEST_OUTPUT_DIR = os.path.join(BASE_DIR, 'tests', 'output')
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

from gcode_generator import GCodeGenerator  # noqa: E402
from programme_fidelity import check_parameter_fidelity  # noqa: E402
from sparql_examples import get_full_suite, expected_nonempty, EXPECTED_EMPTY  # noqa: E402


def _pv(v, u):
    return {'value': v, 'unit': u, 'source': 'swrl_rule', 'rule_id': 'test', 'ontology_sources': []}


def _step(no, op, ftype, tool, f, n, ap=1.0, coolant=True, dims=None, loc=None):
    return {
        'step_number': no, 'operation': op, 'feature_type': ftype, 'tool_id': tool,
        'feature_id': no, 'feature_dimensions': dims or {'Ø': 24.0, 'L': 20.0},
        'feature_location': loc or {'X': 0.0, 'Y': 0.0, 'Z': 100.0},
        'parameters': {'feed_rate': _pv(f, 'mm/rev'), 'spindle_speed': _pv(n, 'RPM'),
                       'depth_of_cut': _pv(ap, 'mm'), 'coolant': _pv(coolant, 'bool')},
    }


# Same tool, different approved spindle speeds: the case that exposed the
# defect (facing at 800 rev/min followed by rough turning at 480 rev/min).
STEPS = [
    _step(1, 'facing', 'Boss', 'turning_insert_rough', 0.20, 800.0),
    _step(2, 'rough_turning', 'Step', 'turning_insert_rough', 0.25, 480.0, ap=2.0),
    _step(3, 'rough_turning', 'Step', 'turning_insert_rough', 0.25, 480.0, ap=2.0),
    _step(4, 'finish_turning', 'Step', 'turning_insert_finish', 0.06, 900.0, ap=0.2, coolant=False),
]


def _write(name, text):
    path = os.path.join(TEST_OUTPUT_DIR, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def test_serialiser_emits_approved_spindle_and_coolant_per_segment():
    program = GCodeGenerator('steel_1045', 'cnc_lathe').generate_program(STEPS)
    text = program.get_program_text()
    assert 'S480 M03' in text and 'S800 M03' in text
    assert text.count('S480 M03') == 1  # only where the modal value changes
    assert '[step 2]' in text and '[step 4]' in text
    path = _write('test_fidelity_ok.nc', text)
    res = check_parameter_fidelity(path, STEPS)
    assert res['passed'], res['mismatches']
    assert res['segments_checked'] == res['spindle_match'] == res['feed_match'] == res['coolant_match'] == 4
    assert res['mapping'] == ['step_tag']


def test_fidelity_detects_tool_change_only_spindle_speed():
    """A programme that sets S only at the tool change (the pre-Revision-3
    behaviour) fails the spindle check on the steps that differ."""
    text = GCodeGenerator('steel_1045', 'cnc_lathe').generate_program(STEPS).get_program_text()
    defective = text.replace('S480 M03 (Spindle speed for this step, 480 RPM)\n', '')
    assert 'S480' not in defective
    res = check_parameter_fidelity(_write('test_fidelity_spindle_defect.nc', defective), STEPS)
    assert not res['passed']
    assert res['spindle_match'] == 2 and res['feed_match'] == 4
    assert sorted(m['step_number'] for m in res['mismatches']) == [2, 3]


def test_fidelity_detects_feed_and_coolant_mismatch():
    text = GCodeGenerator('steel_1045', 'cnc_lathe').generate_program(STEPS).get_program_text()
    assert '[step 4] ---)\nM09 (Coolant off)' in text  # coolant switched off for the dry step
    bad = text.replace('F0.060', 'F0.080').replace('[step 4] ---)\nM09 (Coolant off)', '[step 4] ---)')
    res = check_parameter_fidelity(_write('test_fidelity_feed_defect.nc', bad), STEPS)
    assert not res['passed'] and res['feed_match'] == 3 and res['coolant_match'] == 3
    assert res['spindle_match'] == 4


def test_fidelity_reconstructs_mapping_for_untagged_programmes():
    text = GCodeGenerator('steel_1045', 'cnc_lathe').generate_program(STEPS).get_program_text()
    import re
    untagged = re.sub(r' \[step \d+\]', '', text)
    res = check_parameter_fidelity(_write('test_fidelity_untagged.nc', untagged), STEPS)
    assert res['passed'] and res['mapping'] == ['serialiser_order_reconstruction']


def test_sparql_suite_is_fixed_and_configuration_aware():
    suite = get_full_suite()
    assert [q['index'] for q in suite] == list(range(1, 55))
    assert [q['index'] for q in get_full_suite()] == [q['index'] for q in suite]  # deterministic
    steel_lathe = {'material': 'steel_1045', 'machine': 'cnc_lathe'}
    alu = {'material': 'aluminum_6061', 'machine': 'cnc_lathe'}
    mill_turn = {'material': 'steel_1045', 'machine': 'cnc_mill_turn'}
    assert all(not expected_nonempty(i, steel_lathe) for i in EXPECTED_EMPTY)
    assert expected_nonempty(14, steel_lathe) and not expected_nonempty(14, alu)
    assert expected_nonempty(49, steel_lathe) and not expected_nonempty(49, alu)
    assert expected_nonempty(20, steel_lathe) and not expected_nonempty(20, mill_turn)
    assert sum(expected_nonempty(i, steel_lathe) for i in range(1, 55)) == 49
    assert not expected_nonempty(53, steel_lathe)

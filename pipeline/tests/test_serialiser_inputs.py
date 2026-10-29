"""
Serialiser input contract and dimension fidelity (Revision 6, defect D16).

Before Revision 6 the toolpath patterns looked up long-form keys
('diameter', 'length', 'depth', ...) that the plan never carries (the
extractor writes 'Ø', 'R', 'L', 'W'), so every dimension lookup fell back to
10 mm. These tests pin the mapping of the plan's keys, the refusal of steps
that lack a needed input, and the programme-level dimension-fidelity check.
"""
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from gcode_generator import GCodeGenerator  # noqa: E402
from dimension_fidelity import check_dimension_fidelity  # noqa: E402

OUT = os.path.join(BASE_DIR, 'tests', 'output')
AXIS = {'X': 0.0, 'Y': 0.0, 'Z': 100.0}


def _pv(v, u):
    return {'value': v, 'unit': u, 'source': 'swrl_rule', 'rule_id': 'test', 'ontology_sources': []}


def _step(n, op, dims, loc=AXIS, tool='turning_insert_rough'):
    return {'step_number': n, 'operation': op, 'feature_type': 'Test', 'feature_id': n, 'tool_id': tool,
            'feature_dimensions': dims, 'feature_location': dict(loc),
            'parameters': {'feed_rate': _pv(0.2, 'mm/rev'), 'spindle_speed': _pv(800.0, 'RPM'),
                           'depth_of_cut': _pv(5.0, 'mm'), 'coolant': _pv(True, 'bool')}}


def test_plan_keys_are_mapped_and_radius_is_doubled():
    inputs, missing = GCodeGenerator.serialisation_inputs(
        'rough_turning', {'R': 12.475, 'Ø': 24.95, 'L': 57.7}, {'X': 0.0, 'Y': 0.0, 'Z': 109.35})
    assert missing == []
    assert inputs['diameter'] == {'value': 24.95, 'source': 'Ø'}
    assert inputs['length'] == {'value': 57.7, 'source': 'L'}
    assert inputs['z_centre'] == {'value': 109.35, 'source': 'location Z'}
    inputs, missing = GCodeGenerator.serialisation_inputs('finish_turning', {'R': 4.2, 'L': 3.0}, AXIS)
    assert missing == [] and inputs['diameter'] == {'value': 8.4, 'source': '2 x R'}


def test_inconsistent_diameter_and_radius_is_refused():
    missing = GCodeGenerator.missing_serialisation_inputs('drilling', {'Ø': 8.0, 'R': 5.0, 'L': 10.0}, AXIS)
    assert missing and 'consistent diameter' in missing[0]


@pytest.mark.parametrize('op,dims,needed', [
    ('facing', {'W': 8.0}, 'diameter'),
    ('rough_turning', {}, 'diameter'),
    ('finish_turning', {'Ø': 24.0}, 'axial length'),
    ('drilling', {'Ø': 8.0}, 'axial length'),
    ('counterboring', {'L': 4.0}, 'diameter'),
    ('chamfering', {'Ø': 24.0, 'L': 1.0}, 'chamfer angle'),
    ('grooving', {'Ø': 22.0, 'L': 1.75}, 'outer diameter'),
])
def test_step_without_a_needed_dimension_is_refused_not_defaulted(op, dims, needed):
    missing = GCodeGenerator.missing_serialisation_inputs(op, dims, AXIS)
    assert any(needed in m for m in missing), missing
    g = GCodeGenerator()
    text = g.generate_program([_step(1, op, dims)]).get_program_text()
    assert '[step 1]' not in text and g.serialised_steps == []
    (refusal,) = g.refusals
    assert refusal['kind'] == 'missing_inputs' and any(needed in m for m in refusal['missing_inputs'])
    assert refusal['source_entity']['feature_dimensions'] == dims


def test_operation_without_toolpath_pattern_is_refused():
    assert not GCodeGenerator.has_toolpath_pattern('milling')
    assert GCodeGenerator.missing_serialisation_inputs('milling', {'W': 8.0, 'L': 20.0, 'depth': 2.0}, AXIS)
    g = GCodeGenerator()
    text = g.generate_program([_step(1, 'milling', {'W': 8.0, 'L': 20.0, 'depth': 2.0})]).get_program_text()
    assert '[step 1]' not in text
    assert [r['kind'] for r in g.refusals] == ['no_toolpath_pattern']


def test_toolpath_method_refuses_when_called_without_inputs():
    """Second guard: a toolpath method called directly with an incomplete
    step raises instead of defaulting."""
    from gcode_generator import GCodeProgram
    with pytest.raises(ValueError, match='cannot be serialised'):
        GCodeGenerator()._generate_turning(GCodeProgram(1), {}, {'L': 20.0}, AXIS, 'rough')


def test_only_complete_steps_are_serialised():
    steps = [_step(1, 'rough_turning', {'Ø': 24.0, 'L': 20.0}),
             _step(2, 'rough_turning', {'L': 20.0}),
             _step(3, 'drilling', {'Ø': 6.8, 'L': 20.0}, tool='drill_bit')]
    g = GCodeGenerator()
    text = g.generate_program(steps).get_program_text()
    assert [s['step_number'] for s in g.serialised_steps] == [1, 3]
    assert [r['step_number'] for r in g.refusals] == [2]
    assert '[step 1]' in text and '[step 3]' in text and '[step 2]' not in text
    assert '(Refused by RAL, not serialised: steps 2)' in text


def test_off_axis_axial_hole_is_refused():
    missing = GCodeGenerator.missing_serialisation_inputs('drilling', {'Ø': 8.0, 'L': 10.0},
                                                         {'X': 0.0, 'Y': 15.0, 'Z': 100.0})
    assert missing and 'on-axis position' in missing[0]


def test_extract_dimension_value_has_no_default():
    with pytest.raises(KeyError):
        GCodeGenerator()._extract_dimension_value({'Ø': 8.0}, ['diameter', 'length'])


def test_toolpaths_use_plan_dimensions():
    """Hand-computed targets: Zc = 100, L = 20 gives z_top 110, z_bottom 90."""
    steps = [_step(1, 'rough_turning', {'Ø': 24.0, 'L': 20.0}),
             _step(2, 'drilling', {'Ø': 6.8, 'L': 20.0}, tool='drill_bit'),
             _step(3, 'chamfering', {'Ø': 24.0, 'L': 1.0, 'angle': 45.0}, tool='chamfer_mill'),
             _step(4, 'facing', {'Ø': 24.0, 'L': 20.0})]
    text = GCodeGenerator().generate_program(steps).get_program_text()
    assert 'G00 X24.00 (Feature diameter)' in text and 'G01 Z90.00 F0.200 (Rough turn)' in text
    assert 'G83 Z90.00 Q5.00 F0.200 (Peck drill)' in text
    # Chamfer: Zc 100, L 1 -> z_top 100.5, z_bottom 99.5; X from 24 - 2 x 1 x tan45 = 22 to 24.
    assert 'G01 Z100.50 F0.200 (Chamfer start)' in text
    assert 'G01 X24.00 Z99.50 F0.200 (Chamfer)' in text
    assert 'G00 Z110.00 (Face position)' in text and 'G01 X0.00 F0.200 (Face)' in text
    assert 'X10.00' not in text and 'Z50.00' not in text


def test_tool_change_position_is_clear_of_the_part():
    """Retract to the largest plan z_top plus clearance first, then out in X;
    the pre-Revision-6 fixed G00 Z50 lay inside the part's Z extent."""
    steps = [_step(1, 'rough_turning', {'Ø': 24.0, 'L': 20.0}),
             _step(2, 'drilling', {'Ø': 6.8, 'L': 20.0}, tool='drill_bit')]
    lines = GCodeGenerator().generate_program(steps).get_program_text().splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith('(--- Tool Change: drill_bit'))
    assert lines[i + 1].startswith('G00 Z112.00') and lines[i + 2].startswith('G00 X28.00')


def _write(name, text):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def test_dimension_fidelity_passes_and_detects_tampering():
    steps = [_step(1, 'rough_turning', {'Ø': 24.0, 'L': 20.0}),
             _step(2, 'drilling', {'Ø': 6.8, 'L': 20.0}, tool='drill_bit')]
    text = GCodeGenerator().generate_program(steps).get_program_text()
    ok = check_dimension_fidelity(_write('test_dimfid_ok.nc', text), steps)
    assert ok['passed'] and ok['segments'] == 2 and ok['lookups'] == 6 and ok['defaulted'] == 0
    assert ok['unexplained_cutting_words'] == 0 and ok['cutting_words_checked'] == 2
    # A cutting target that does not derive from the plan (the old 10 mm placeholder).
    bad = check_dimension_fidelity(_write('test_dimfid_bad_cut.nc',
                                          text.replace('G01 Z90.00', 'G01 Z80.00', 1)), steps)
    assert not bad['passed'] and bad['unexplained_cutting_words'] == 1
    # A declared input that is not in the plan.
    bad = check_dimension_fidelity(_write('test_dimfid_bad_input.nc',
                                          text.replace('diameter 24.000 [Ø]', 'diameter 10.000 [Ø]', 1)), steps)
    assert not bad['passed'] and bad['defaulted'] == 1
    # A segment without an inputs declaration.
    stripped = '\n'.join(ln for ln in text.splitlines() if not ln.startswith('(Plan inputs'))
    bad = check_dimension_fidelity(_write('test_dimfid_no_inputs.nc', stripped), steps)
    assert not bad['passed'] and bad['segments_with_inputs'] == 0

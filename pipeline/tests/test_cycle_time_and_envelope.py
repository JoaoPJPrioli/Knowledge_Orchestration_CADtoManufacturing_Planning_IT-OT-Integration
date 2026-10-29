"""
Cycle-time estimator (modal spindle speed, true move lengths, incremental
cycle depth) and the travel envelope (single source, no silent clamping).
"""
import math
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

TEST_OUTPUT_DIR = os.path.join(BASE_DIR, 'tests', 'output')
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

from simulator import CNCSimulator, CollisionDetector, WorkpieceGeometry  # noqa: E402
from validator import GCodeValidator  # noqa: E402
from gcode_generator import GCodeGenerator  # noqa: E402
from machine_envelope import DEFAULT_TRAVEL_ENVELOPE_MM, travel_envelope  # noqa: E402

# Hand-computed segment. Rapid rate 5000 mm/min, 0.5 s positioning per
# block, 3 s per tool change (CuttingTimeEstimator defaults).
PROGRAM = """O1001
T0001 M06
S800 M03
G00 X26.00 Z100.00
G01 X24.00 F0.250
G01 Z60.00
S480 M03
G01 Z20.00
G00 X30.00 Z170.00
S900 M03
G00 X0.00
G83 Z150.00 Q5.00 F0.150
G80
M05
M30
"""
# Feed moves:  X26->X24 at Z100: 2 mm at 0.25*800 = 200 mm/min -> 0.6 s
#              Z100->Z60: 40 mm at 200 mm/min -> 12.0 s
#              Z60->Z20 after S480: 40 mm at 0.25*480 = 120 mm/min -> 20.0 s
# Cycle:       G83 from Z170 to Z150: incremental depth 20 mm (not |Z| = 150),
#              at 0.15*900 = 135 mm/min -> 8.8889 s; ceil(20/5) = 4 pecks ->
#              3 rapid retracts of 20 mm at 5000 mm/min -> 0.72 s
# Rapids:      X0 Z0 -> X26 Z100: hypot(26, 100) = 103.3247 mm -> 1.23990 s
#              X24 Z20 -> X30 Z170: hypot(6, 150) = 150.1200 mm -> 1.80144 s
#              X30 -> X0 at Z170: 30 mm -> 0.36 s
CUT_S = 0.6 + 12.0 + 20.0 + 20.0 / 135.0 * 60.0 + 3 * 20.0 / 5000.0 * 60.0
RAPID_S = (math.hypot(26, 100) + math.hypot(6, 150) + 30.0) / 5000.0 * 60.0


def _write(name, text):
    path = os.path.join(TEST_OUTPUT_DIR, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def test_cycle_time_hand_computed_segment():
    sim = CNCSimulator()
    report = sim.simulate_file(_write('test_cycle_time.nc', PROGRAM))
    ct = report['cutting_time']
    assert ct['cutting_time_seconds'] == pytest.approx(CUT_S, abs=0.01)
    assert ct['rapid_time_seconds'] == pytest.approx(RAPID_S, abs=0.01)
    assert ct['timed_feed_length_mm'] == pytest.approx(82.0, abs=0.01)
    assert ct['timed_cycle_depth_mm'] == pytest.approx(20.0, abs=0.01)
    assert ct['untimed_feed_moves'] == 0
    blocks = sum(1 for ln in PROGRAM.splitlines() if ln.strip())
    total = CUT_S + RAPID_S + 3.0 + 0.5 * blocks
    assert ct['total_cycle_time_seconds'] == pytest.approx(total, abs=0.02)


def test_cycle_time_follows_modal_spindle_speed():
    slow = PROGRAM.replace('S480 M03', 'S240 M03')
    a = CNCSimulator().simulate_file(_write('test_cycle_time_a.nc', PROGRAM))['cutting_time']
    b = CNCSimulator().simulate_file(_write('test_cycle_time_b.nc', slow))['cutting_time']
    # Halving S on the 40 mm Z60->Z20 pass doubles its 20 s.
    assert b['cutting_time_seconds'] - a['cutting_time_seconds'] == pytest.approx(20.0, abs=0.01)


def test_validator_cycle_feeds_incremental_depth_and_returns_to_initial_point():
    v = GCodeValidator()
    report = v.validate_text(PROGRAM) if hasattr(v, 'validate_text') else None
    if report is None:
        from validator import validate_gcode_text
        report = validate_gcode_text(PROGRAM)
    stats = report['statistics']
    assert stats['cut_distance'] == pytest.approx(82.0 + 20.0, abs=0.01)
    assert stats['final_position']['z'] == pytest.approx(170.0)


def test_envelope_has_one_source():
    env = DEFAULT_TRAVEL_ENVELOPE_MM
    v = GCodeValidator()
    assert (v.x_min, v.x_max, v.z_min, v.z_max) == (env['x_min'], env['x_max'], env['z_min'], env['z_max'])
    cd = CollisionDetector(WorkpieceGeometry(stock_diameter=80.0, stock_length=200.0))
    assert (cd.x_min, cd.x_max, cd.z_min, cd.z_max) == (env['x_min'], env['x_max'], env['z_min'], env['z_max'])
    g = GCodeGenerator()
    assert (g.MIN_X, g.MAX_X, g.MIN_Z, g.MAX_Z) == (env['x_min'], env['x_max'], env['z_min'], env['z_max'])
    assert travel_envelope({'capabilities': {'x_axis_travel': 200.0}})['x_max'] == 200.0


def _pv(v, u):
    return {'value': v, 'unit': u, 'source': 'swrl_rule', 'rule_id': 'test', 'ontology_sources': []}


def test_serialiser_does_not_clamp_and_validator_reports_excursion():
    """Coordinates outside the envelope are emitted as computed, recorded as
    excursions with their plan step, and reported by the validator. A groove
    on a 400 mm diameter (outside the 150 mm X travel) is used as the case."""
    step = {'step_number': 7, 'operation': 'grooving', 'feature_type': 'Groove', 'tool_id': 'grooving_tool',
            'feature_id': 7, 'feature_dimensions': {'outer_diameter': 400.0, 'groove_depth': 2.0},
            'feature_location': {'X': 0.0, 'Y': 0.0, 'Z': 50.0},
            'parameters': {'feed_rate': _pv(0.08, 'mm/rev'), 'spindle_speed': _pv(600.0, 'RPM'),
                           'depth_of_cut': _pv(0.5, 'mm'), 'coolant': _pv(True, 'bool')}}
    g = GCodeGenerator()
    text = g.generate_program([step]).get_program_text()
    assert 'G00 X402.00 Z50.00 (Groove approach)' in text
    assert 'G01 X396.00 F0.080 (Groove)' in text
    # The tool-change position is derived from the plan (largest diameter
    # plus clearance), so it is outside the envelope too and is attributed
    # to the tool-change position rather than to a step.
    assert {e['step_number'] for e in g.envelope_excursions} == {7, 'tool_change_position'}
    assert {e['excursion_mm']['x'] for e in g.envelope_excursions} == {254.0, 252.0, 246.0}
    from validator import validate_gcode_text
    report = validate_gcode_text(text)
    bounds = [v for v in report['violations'] if v['category'] == 'bounds']
    # X404 at the tool change and programme end, X402 approach and retract, X396 groove.
    assert len(bounds) == 5 and report['summary']['status'] == 'FAIL'


def test_far_coordinates_are_not_clamped():
    """Generic no-clamping check, independent of grooving: a turning step
    beyond both maxima (X 400 mm on diameter, Z 1200 mm against the 150 mm and
    1000 mm travel) is emitted at its computed coordinates and every
    excursion is recorded with its step."""
    step = {'step_number': 3, 'operation': 'finish_turning', 'feature_type': 'Step', 'tool_id': 'turning_insert_finish',
            'feature_id': 3, 'feature_dimensions': {'Ø': 400.0, 'L': 20.0},
            'feature_location': {'X': 0.0, 'Y': 0.0, 'Z': 1200.0},
            'parameters': {'feed_rate': _pv(0.06, 'mm/rev'), 'spindle_speed': _pv(300.0, 'RPM'),
                           'depth_of_cut': _pv(0.2, 'mm'), 'coolant': _pv(True, 'bool')}}
    g = GCodeGenerator()
    text = g.generate_program([step]).get_program_text()
    assert 'G00 X404.00 Z1212.00 (Approach position)' in text
    assert 'G00 X400.00 (Feature diameter)' in text and 'G01 Z1190.00 F0.060 (Finish turn)' in text
    steps = {e['step_number'] for e in g.envelope_excursions}
    assert steps == {3, 'tool_change_position'}
    assert all(e['x'] > 150.0 or e['z'] > 1000.0 for e in g.envelope_excursions)
    from validator import validate_gcode_text
    report = validate_gcode_text(text)
    assert report['summary']['status'] == 'FAIL'
    assert any(v['category'] == 'bounds' for v in report['violations'])

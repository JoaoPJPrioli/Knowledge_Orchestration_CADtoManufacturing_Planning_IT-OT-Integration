"""
Force and power channels of the simulator (ChipLoadAnalyzer).

The channels are an order-of-magnitude audit quantity with a nominal,
uncalibrated specific cutting force kc. These tests check only what the code
can guarantee: dimensional consistency (P = Fc * vc / 60000 with Fc in N and
vc in m/min gives kW), linearity of the force in depth of cut and feed, the
per-lip drilling identity, refusal to invent a missing input, and that the
force/power inputs never alter the quantities the tool-wear estimator reads.
"""
import math
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from simulator import ChipLoadAnalyzer, CNCSimulator  # noqa: E402

TEST_OUTPUT_DIR = os.path.join(BASE_DIR, 'tests', 'output')
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)


def test_power_equals_force_times_speed_single_point():
    an = ChipLoadAnalyzer('steel_1045')
    ap, f, d, n = 2.0, 0.25, 24.0, 480.0
    fc, p, vc, model = an.force_and_power('turning', f, ap, d, n)
    assert fc == pytest.approx(an.kc * ap * f)
    assert vc == pytest.approx(math.pi * d * n / 1000.0)
    assert p == pytest.approx(fc * vc / 60000.0)
    assert model == ChipLoadAnalyzer.MODEL_SINGLE_POINT


def test_force_is_linear_in_depth_and_feed():
    an = ChipLoadAnalyzer('steel_1045')
    base = an.calculate_cutting_force(1.0, 0.1)
    assert an.calculate_cutting_force(2.0, 0.1) == pytest.approx(2.0 * base)
    assert an.calculate_cutting_force(1.0, 0.3) == pytest.approx(3.0 * base)
    assert an.calculate_cutting_force(2.5, 0.4) == pytest.approx(10.0 * base)
    assert an.calculate_cutting_force(0.0, 0.4) == 0.0


def test_drilling_per_lip_identity():
    an = ChipLoadAnalyzer('steel_1045')
    d, f, n = 6.8, 0.15, 900.0
    fc, p, vc, model = an.force_and_power('drilling', f, 5.0, d, n)
    assert fc == pytest.approx(an.kc * (d / 2.0) * (f / 2.0))
    assert p == pytest.approx(fc * vc / 60000.0)
    # Handbook form for a two-lip drill: P = kc * D * f * vc / 240000.
    assert p == pytest.approx(an.kc * d * f * vc / 240000.0)
    assert model == ChipLoadAnalyzer.MODEL_DRILLING


def test_unknown_inputs_are_not_defaulted():
    an = ChipLoadAnalyzer('steel_1045')
    assert an.force_and_power('drilling', 0.15, 5.0, None, 900.0)[:2] == (None, None)
    assert an.force_and_power('turning', None, 2.0, 24.0, 480.0)[:2] == (None, None)
    fc, p, _, _ = an.force_and_power('turning', 0.25, 2.0, None, 480.0)
    assert fc == pytest.approx(an.kc * 2.0 * 0.25) and p is None


def test_material_constant_is_used():
    al = ChipLoadAnalyzer('aluminum_6061')
    st = ChipLoadAnalyzer('steel_1045')
    assert al.kc == 800.0 and st.kc == 2000.0
    assert al.calculate_cutting_force(2.0, 0.25) / st.calculate_cutting_force(2.0, 0.25) == pytest.approx(0.4)


def test_force_inputs_do_not_change_wear_inputs():
    an = ChipLoadAnalyzer('steel_1045')
    kwargs = dict(operation_type='RoughTurningOp', feed_rate=0.25, spindle_speed=800.0,
                  depth_of_cut=5.0, width_of_cut=5.0, diameter=24.0)
    a = an.analyze_operation(**kwargs)
    b = an.analyze_operation(**kwargs, force_inputs={
        'process': 'turning', 'feed_per_rev': 0.25, 'depth_of_cut': 2.0,
        'diameter': 24.95, 'spindle_speed': 480.0, 'step_number': 3})
    for field in ('feed_rate', 'spindle_speed', 'cutting_speed', 'depth_of_cut',
                  'material_removal_rate', 'cutting_time', 'chip_load'):
        assert getattr(a, field) == getattr(b, field), field
    assert b.cutting_power == pytest.approx(b.cutting_force * b.force_cutting_speed_m_per_min / 60000.0)


def test_simulator_attributes_inputs_to_plan_steps():
    program = "\n".join([
        "O1001",
        "(--- Machine Initialization ---)",
        "G18 G21 G40 G54 G80 G90 G97 G99",
        "(--- Tool Change: turning_insert_rough ---)",
        "T0001 M06",
        "S480 M03",
        "(--- rough_turning: Step ---)",
        "G00 X26.00 Z100.00",
        "G01 X24.00 F0.250",
        "G01 Z60.00 F0.250",
        "(--- Tool Change: drill_bit ---)",
        "T0003 M06",
        "S900 M03",
        "(--- drilling: Blind Hole ---)",
        "G00 X0.00 Z170.00",
        "G83 Z150.00 Q5.00 F0.150",
        "G80",
        "(--- Program End ---)",
        "M05",
        "M30",
    ]) + "\n"
    path = os.path.join(TEST_OUTPUT_DIR, 'test_force_power.nc')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(program)

    def step(no, op, dims, f, n, ap):
        pv = lambda v, u: {'value': v, 'unit': u}
        return {'step_number': no, 'operation': op, 'feature_dimensions': dims,
                'parameters': {'feed_rate': pv(f, 'mm/rev'), 'spindle_speed': pv(n, 'RPM'),
                               'depth_of_cut': pv(ap, 'mm'), 'coolant': pv(True, 'bool')}}

    steps = [step(1, 'rough_turning', {'Ø': 24.0}, 0.25, 480.0, 2.0),
             step(2, 'drilling', {'Ø': 6.8}, 0.15, 900.0, 5.0)]
    sim = CNCSimulator(plan_steps=steps)
    report = sim.simulate_file(path)
    kc = sim.chip_analyzer.kc
    turning = [p for p in sim.tool_parameters if p.plan_step_number == 1]
    drilling = [p for p in sim.tool_parameters if p.plan_step_number == 2]
    assert turning and drilling
    for p in turning:
        assert p.cutting_force == pytest.approx(kc * 2.0 * 0.25)
        assert p.cutting_power == pytest.approx(p.cutting_force * (math.pi * 24.0 * 480.0 / 1000.0) / 60000.0)
    for p in drilling:
        assert p.cutting_force == pytest.approx(kc * 3.4 * 0.075)
    model = report['chip_load_analysis']['force_power_model']
    assert model['inputs_source'] == 'plan step parameter package'
    assert model['moves_with_force'] == len(sim.tool_parameters)

    # A segment/step count mismatch must fail loudly, not misattribute inputs.
    with pytest.raises(RuntimeError):
        CNCSimulator(plan_steps=steps[:1]).simulate_file(path)

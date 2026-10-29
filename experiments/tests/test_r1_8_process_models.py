"""Tests for the corrected force and tool-life models (Reviewer 1, Comment 8)."""
import json
import math
import os
import sys

import pytest

EXP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXP)
from r1_8_process_models import process_models as pm  # noqa: E402
from simulator import ChipLoadAnalyzer  # noqa: E402  (repo src is on sys.path via pm)

REF = os.path.join(EXP, "runs", "reference")
needs_ref = pytest.mark.skipif(not os.path.isdir(REF), reason="run common/run_pipeline.py reference first")


# --- Kienzle force ---------------------------------------------------------

def test_kienzle_with_mc_zero_reduces_to_constant_kc_model_of_the_pipeline():
    cla = ChipLoadAnalyzer("steel_1045")
    kc = cla.kc
    t = pm.force_power("turning", 0.25, 2.0, 24.95, 480, kc, 0.0, kappa_r_deg=90.0)
    assert t["Fc_per_edge_N"] == pytest.approx(cla.calculate_cutting_force(2.0, 0.25))
    d = pm.force_power("drilling", 0.15, None, 6.8, 900, kc, 0.0, point_angle_deg=118.0)
    assert d["Fc_per_edge_N"] == pytest.approx(cla.calculate_drilling_force_per_lip(6.8, 0.15))
    # power identical to the pipeline's P = Fc vc / 60000 (drilling: same handbook form)
    assert t["power_kW"] == pytest.approx(cla.calculate_cutting_power(t["Fc_per_edge_N"], t["vc_m_per_min"]))
    assert d["power_kW"] == pytest.approx(kc * 6.8 * 0.15 * d["vc_m_per_min"] / 240000.0)


def test_hand_calculated_rough_turning_case():
    # f 0.25 mm/rev, ap 2.0 mm, kappa_r 95 deg, kc11 2220 N/mm2, mc 0.14:
    # h = 0.249049 mm, b = 2.007640 mm, Fc = 2220 * 2.007640 * 0.249049**0.86 = 1348.5 N
    r = pm.force_power("turning", 0.25, 2.0, 24.95, 480, 2220.0, 0.14, kappa_r_deg=95.0)
    assert r["h_mm"] == pytest.approx(0.249049, abs=1e-6)
    assert r["b_mm"] == pytest.approx(2.007640, abs=1e-6)
    assert r["Fc_per_edge_N"] == pytest.approx(1348.5, abs=0.5)
    # vc = pi * 24.95 * 480 / 1000 = 37.624 m/min; P = 1348.5 * 37.624 / 60000 = 0.8456 kW
    assert r["vc_m_per_min"] == pytest.approx(37.624, abs=1e-3)
    assert r["power_kW"] == pytest.approx(0.8456, abs=1e-3)


@pytest.mark.parametrize("process,kw", [
    ("turning", {"ap": 2.0, "kappa_r_deg": 95.0}),
    ("counterboring", {"ap": 3.0, "kappa_r_deg": 90.0}),
    ("drilling", {"ap": None, "point_angle_deg": 118.0}),
])
def test_power_equals_torque_times_angular_speed(process, kw):
    ap = kw.pop("ap")
    r = pm.force_power(process, 0.15, ap, 8.4, 900, 2220.0, 0.2, **kw)
    assert r["power_kW"] == pytest.approx(r["power_from_torque_kW"], rel=1e-12)


def test_units_one_kilonewton_at_sixty_metres_per_minute_is_one_kilowatt():
    rpm = 60.0 * 1000.0 / (math.pi * 20.0)  # vc = 60 m/min at D = 20 mm
    # choose b*h^(1-mc) so that Fc = 1000 N with mc = 0, kappa 90: kc*ap*f = 1000
    r = pm.force_power("turning", 0.25, 2.0, 20.0, rpm, 2000.0, 0.0, kappa_r_deg=90.0)
    assert r["Fc_per_edge_N"] == pytest.approx(1000.0)
    assert r["power_kW"] == pytest.approx(1.0)


def test_force_monotone_in_feed_and_depth_and_specific_force_falls_with_chip_thickness():
    f = [pm.force_power("turning", x, 2.0, 25, 500, 2220, 0.14, kappa_r_deg=95)["Fc_per_edge_N"]
         for x in (0.05, 0.1, 0.2, 0.3)]
    a = [pm.force_power("turning", 0.2, x, 25, 500, 2220, 0.14, kappa_r_deg=95)["Fc_per_edge_N"]
         for x in (0.5, 1.0, 2.0, 3.0)]
    kc = [pm.force_power("turning", x, 2.0, 25, 500, 2220, 0.14, kappa_r_deg=95)["kc_N_per_mm2"]
          for x in (0.05, 0.1, 0.2, 0.3)]
    assert f == sorted(f) and len(set(f)) == 4
    assert a == sorted(a) and len(set(a)) == 4
    assert kc == sorted(kc, reverse=True)


def test_missing_input_is_unavailable_not_defaulted():
    r = pm.force_power("turning", 0.25, 2.0, 24.95, None, 2220, 0.14, kappa_r_deg=95)
    assert r["model"] == "unavailable" and "spindle_speed" in r["missing"]
    r = pm.force_power("drilling", 0.15, None, 6.8, 900, 2220, 0.14, point_angle_deg=None)
    assert r["model"] == "unavailable" and "point_angle" in r["missing"]


def test_drill_point_angle_is_read_from_the_tool_ontology():
    tk = pm.read_tool_knowledge()
    assert pm.angle_from_geometry(tk["DrillBit"]["geometry"]) == 118.0
    assert tk["DrillBit"]["material"] == "High-Speed Steel"
    assert pm.angle_from_geometry(tk["CounterboreCutter"]["geometry"]) == 90.0


# --- Taylor tool life --------------------------------------------------------

def test_taylor_anchor_and_monotonicity():
    assert pm.taylor_life(150.0, 150.0, 15.0, 0.25) == pytest.approx(15.0)
    lives = [pm.taylor_life(v, 150.0, 15.0, 0.25) for v in (50, 100, 150, 200)]
    assert lives == sorted(lives, reverse=True)
    # halving speed with n = 0.25 multiplies life by 2**4 = 16
    assert pm.taylor_life(75.0, 150.0, 15.0, 0.25) == pytest.approx(240.0)


def test_first_trigger_part():
    assert pm.first_trigger_part(0.1, 0.8) == 8
    assert pm.first_trigger_part(0.3, 0.8) == 3
    assert pm.first_trigger_part(0.9, 0.8) == 1


@needs_ref
def test_time_base_is_the_pipeline_cycle_time_estimator():
    nc = os.path.join(REF, "motor_shaft_1001.nc")
    t = pm.segment_times(nc)  # raises if the segment sums do not reproduce the estimator
    sim = json.load(open(os.path.join(REF, "motor_shaft_1001_simulation.json"), encoding="utf-8"))
    assert t["estimator_total"]["cutting_time_seconds"] == sim["cutting_time"]["cutting_time_seconds"]
    assert len(t["segments"]) == 9
    assert sum(s["in_cut_s"] for s in t["segments"].values()) <= t["estimator_total"]["cutting_time_seconds"]


@needs_ref
def test_consumption_is_not_clamped():
    C = pm.load_constants()
    key = "Carbide with Coating|turning"
    r = pm.evaluate_run(REF, constants=C, overrides={"taylor": {key: {"T_ref_min": 0.001}}})
    assert r["per_tool"]["turning_insert_finish"]["consumption_per_part"] > 1.0


# --- Feedback path -----------------------------------------------------------

@needs_ref
def test_feedback_reference_part_raises_nothing_and_injected_exceedance_raises_and_is_reused(tmp_path):
    C = pm.load_constants()
    plan = json.load(open(os.path.join(REF, "manufacturing_plan.json"), encoding="utf-8"))
    base = pm.evaluate_run(REF, constants=C)
    store = pm.ExpertValidationStore(str(tmp_path / "s.json"))
    assert pm.tool_life_feedback(base, plan, store, 0.8) == []

    # Injected exceedance: a drill whose life at v_ref is 0.1 min passes 80 % within one part.
    hot = pm.evaluate_run(REF, constants=C, overrides={"taylor": {"High-Speed Steel|drilling": {"T_ref_min": 0.1}}})
    rows = pm.tool_life_feedback(hot, plan, store, 0.8)
    assert {r["step_number"] for r in rows} == {17, 18}
    assert {r["reason"] for r in rows} == {"critical_simulation_finding"}
    for r in rows:
        store.apply_feedback(r["request_id"], "expert_approved", "drill replaced")
    store.save()

    again = pm.ExpertValidationStore(str(tmp_path / "s.json"))
    rows2 = pm.tool_life_feedback(hot, plan, again, 0.8)
    assert sorted(r["request_id"] for r in rows2) == sorted(r["request_id"] for r in rows)
    assert {r["status"] for r in rows2} == {"expert_approved"}
    assert len(again.all_requests()) == len(rows)


@needs_ref
def test_batch_trigger_matches_analytic_part(tmp_path):
    C = pm.load_constants()
    plan = json.load(open(os.path.join(REF, "manufacturing_plan.json"), encoding="utf-8"))
    base = pm.evaluate_run(REF, constants=C)
    c = base["per_tool"]["drill_bit"]["consumption_per_part"]
    k = pm.first_trigger_part(c, 0.8)
    store = pm.ExpertValidationStore(str(tmp_path / "b.json"))
    assert not [r for r in pm.tool_life_feedback(base, plan, store, 0.8, parts_done=k - 2) if r["tool_id"] == "drill_bit"]
    assert [r for r in pm.tool_life_feedback(base, plan, store, 0.8, parts_done=k - 1) if r["tool_id"] == "drill_bit"]

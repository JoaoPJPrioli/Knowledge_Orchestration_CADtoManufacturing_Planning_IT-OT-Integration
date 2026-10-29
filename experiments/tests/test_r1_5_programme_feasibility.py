"""Tests for the material-based programme check and the free-text dimension
configuration (Reviewer 1, Comment 5)."""
import os
import sys

import pytest

EXP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXP)
from r1_5_programme_feasibility import stock_check as sc  # noqa: E402
from r1_5_programme_feasibility.free_text_dimensions import dimensions_from_text  # noqa: E402

PROGRAMME = """O0001
(--- Machine Initialization ---)
G18
G21
G99

(--- Tool Change: turning_insert_rough ---)
G00 Z174.00
G00 X40.00
T0001 M06
S500 M03

(--- rough_turning: Test [step 1] ---)
G00 X30.00 Z130.00
G00 X26.00
G01 Z100.00 F0.200
G00 X30.00
G00 Z170.00
G00 X24.00
G01 Z121.00 F0.200
G00 X30.00

(--- Tool Change: drill_bit ---)
G00 Z174.00
T0003 M06
S900 M03

(--- drilling: Hole [step 2] ---)
G00 X0.00 Z172.00
G81 Z160.00 F0.150
G80
G00 Z172.00
M02
"""

PLAN = [
    {"step_number": 1, "operation": "rough_turning", "feature_dimensions": {"Ø": 26.0},
     "parameters": {"depth_of_cut": {"value": 2.0}}},
    {"step_number": 2, "operation": "drilling", "feature_dimensions": {"Ø": 6.8},
     "parameters": {"depth_of_cut": {"value": 5.0}}},
]
LIMITS = {"turning_insert_rough": 5.0, "drill_bit": 50.0}


@pytest.fixture()
def result(tmp_path):
    p = tmp_path / "t.nc"
    p.write_text(PROGRAMME, encoding="utf-8")
    return sc.check_programme(str(p), PLAN, 28.0, 169.5, LIMITS)


def test_rapid_plunge_into_the_bar_is_detected(result):
    # G00 X26 at Z130 plunges 1.0 mm (radius 14 -> 13) into the 28 mm bar
    r = [x for x in result["rapids_into_stock"] if x["step"] == 1]
    assert r and r[0]["depth_mm"] == pytest.approx(1.0, abs=0.01) and r[0]["at_z"] == pytest.approx(130.0)


def test_radial_engagement_follows_the_material_present(result):
    feed = [m for m in result["moves"] if m.get("radial_engagement_mm") is not None]
    assert feed[0]["radial_engagement_mm"] == pytest.approx(1.0, abs=0.01)
    # second pass: 28 -> 24 between z 130 and 169.5 (2 mm), 26 -> 24 below z 130 (1 mm)
    assert feed[1]["radial_engagement_mm"] == pytest.approx(2.0, abs=0.01)
    assert not feed[1]["exceeds_planned"] and not feed[1]["exceeds_tool"]


def test_gouge_against_the_reference_part_is_detected_and_attributed(result):
    # Ø24 cut between z 121 and 130 lies inside R05 (Ø24.0): no gouge; Ø26 cut over z 100..130
    # leaves R01 (Ø24.95) region 100..118 at 26 (residual), and the Ø24 cut from 121 to 170 matches R05.
    g = result["conformance"]["outer_gouges"]
    assert all(z["max_mm"] < 0.6 for z in g)
    # the Ø24 pass crosses R04/R03 region? no: it stops at z = 121 -> no gouge in R03/R04
    assert not [z for z in g if "R03" in z["reference_features"]]


def test_drilling_cycle_removes_a_cylinder_with_a_point(result):
    d = [m for m in result["moves"] if m.get("cycle")]
    assert d and d[0]["diameter_mm"] == 6.8
    assert d[0]["depth_in_material_mm"] == pytest.approx(9.5)  # from the bar end 169.5 to 160.0
    assert d[0]["volume_removed_mm3"] > 0


def test_free_text_dimensions_are_read_only_when_stated_and_consistent():
    assert dimensions_from_text("Main upper cylindrical body with a diameter of 24mm (R12) and a length of 46.5mm.") == \
        {"Ø": 24.0, "R": 12.0, "L": 46.5}
    assert dimensions_from_text("key, 4mm wide, 32mm long") == {"W": 4.0, "L": 32.0}
    assert dimensions_from_text("Rectangular boss on the side") == {}
    assert dimensions_from_text("a diameter of 24mm (R11)") == {}  # disagreement: no guess
    assert dimensions_from_text("a length of 10mm and a length of 12mm") == {}

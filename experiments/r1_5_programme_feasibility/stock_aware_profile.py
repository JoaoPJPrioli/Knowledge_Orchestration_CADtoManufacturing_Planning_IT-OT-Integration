"""Reviewer 1, Comment 5 ("Step B"): a stock-aware turning profile, as evaluation
code beside the pipeline's serialiser (RAL is not modified).

The material check (stock_check.py) found two kinds of defect in the reference
programme: serialiser defects (approach and retract positions derived from the
part rather than the stock; one pass per segment at the final diameter, so
roughing can exceed the planned depth of cut and finishing removes nothing)
and plan defects (a groove extracted as a step; a hole whose extracted location
is its entry plane, read as its centre). This profile changes only what the
serialiser decides, to show which defects a stock-aware toolpath pattern
removes and which remain because they are in the plan.

Inputs are the approved plan steps and a declared bar stock (diameter and
free-end z), which the ontology does not carry. The profile:

  * places the tool-change, approach and retract positions outside the bar
    and beyond its free end (stock and part, whichever is larger);
  * roughs each turning segment in passes no deeper than the step's planned
    depth of cut, from the free end towards the chuck, down to the final
    radius plus a radial finishing allowance equal to the planned depth of cut
    of the approved finishing step for the same feature (no allowance when
    there is none);
  * finishes in one pass at the final diameter;
  * refuses, with a recorded reason, any turning step whose pass from the free
    end would cut below the protected radius of another approved turning
    segment lying between the free end and the step's own span (a recess,
    such as a groove, cannot be turned longitudinally from the free end; it
    needs a plunge pattern); overlapping spans with different diameters are a
    conflict in the plan and are recorded, not refused;
  * keeps the planned spindle speed in rev/min (G97), feed per revolution, and
    coolant, so that parameter fidelity to the plan is unchanged. Constant
    surface speed is not introduced, because the plan stores spindle speeds,
    not cutting speeds, and the pipeline's checks read S as rev/min.

Nothing else is defaulted: every diameter, length, and position comes from the
plan or from the declared stock.
"""
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import use_repo  # noqa: E402

use_repo()
from gcode_generator import GCodeGenerator, GCodeProgram  # noqa: E402

DZ = 0.01
TURNING = ("rough_turning", "finish_turning")


class StockAwareTurningGenerator(GCodeGenerator):
    PROFILE_NAME = "StockAwareTurningProfile (evaluation code)"

    def __init__(self, stock_diameter: float, stock_free_end_z: float, material: str = "steel_1045",
                 machine: str = "cnc_lathe", z_min: float = -60.0, z_max: float = 260.0):
        super().__init__(material=material, machine=machine)
        self.stock_d = float(stock_diameter)
        self.z_free = float(stock_free_end_z)
        self.z = np.arange(z_min, z_max + DZ / 2, DZ)
        self.r_out = np.where(self.z <= self.z_free + 1e-9, self.stock_d / 2.0, 0.0)
        self.passes: List[Dict] = []

    # -- geometry helpers -------------------------------------------------------
    def _idx(self, z):
        return int(round((z - self.z[0]) / DZ))

    def _span(self, step) -> Optional[Tuple[float, float, float]]:
        """(final radius, z_bottom, z_top) of a turning step, or None if the plan lacks an input."""
        inputs, missing = self.serialisation_inputs(step.get("operation", ""), step.get("feature_dimensions") or {},
                                                    step.get("feature_location") or {})
        if missing:
            return None
        d, length, zc = inputs["diameter"]["value"], inputs["length"]["value"], inputs["z_centre"]["value"]
        return d / 2.0, zc - length / 2.0, zc + length / 2.0

    @staticmethod
    def _param(step, key) -> Optional[float]:
        v = ((step.get("parameters") or {}).get(key) or {})
        v = v.get("value") if isinstance(v, dict) else v
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def _allowance(self, step, plan) -> float:
        """Finishing allowance for a rough step: the planned depth of cut of the
        approved finishing step for the same feature, or 0 if there is none."""
        for s in plan:
            if s.get("operation") == "finish_turning" and s.get("feature_id") == step.get("feature_id"):
                ap = self._param(s, "depth_of_cut")
                if ap is not None and self._span(s) is not None:
                    return ap
        return 0.0

    def _targets(self, plan):
        """Per turning step: final radius, rough target radius, and z range."""
        out = {}
        for s in plan:
            if s.get("operation") not in TURNING:
                continue
            sp = self._span(s)
            if sp is None:
                continue
            r, zb, zt = sp
            rough = r + (self._allowance(s, plan) if s["operation"] == "rough_turning" else 0.0)
            out[s["step_number"]] = {"final": r, "rough": rough, "zb": zb, "zt": zt, "op": s["operation"],
                                     "feature_id": s.get("feature_id")}
        return out

    def _recess_refusals(self, plan, targets) -> Dict[int, Dict]:
        """Turning steps whose pass, on its way from the free end to its own
        span, would cut below the protected radius of another approved turning
        segment that lies between the free end and that span (a recess).

        Overlaps inside a step's own span [zb, zt] are a different matter: two
        plan segments then claim different diameters for the same z, which is
        a conflict in the plan, not in the toolpath. Any sequence of
        longitudinal passes leaves the smaller of the two, so such overlaps are
        recorded (self.plan_overlaps) and not refused."""
        refusals = {}
        overlaps = {}
        c = self.APPROACH_CLEARANCE_MM
        roughed = {t["feature_id"] for t in targets.values() if t["op"] == "rough_turning"}
        for num, t in targets.items():
            phase = "rough" if t["op"] == "rough_turning" else "final"
            pass_r = t[phase]
            blocking = []
            for other_num, o in targets.items():
                if other_num == num or o["feature_id"] == t["feature_id"]:
                    continue
                # roughing is compared with the other feature's rough target (its
                # final radius when it has no roughing step), finishing with its final radius
                if phase == "rough" and o["op"] == "finish_turning" and o["feature_id"] in roughed:
                    continue
                if phase == "final" and o["op"] == "rough_turning":
                    continue
                protect = o["rough"] if phase == "rough" else o["final"]
                if pass_r >= protect - 1e-9:
                    continue
                # traverse beyond the own span: (zt, max(z_free, zt) + c]
                lo, hi = max(t["zt"], o["zb"]), min(max(self.z_free, t["zt"]) + c, o["zt"])
                if hi - lo > 1e-6:
                    blocking.append(f"diameter {2 * protect:.3f} of step {other_num} over z {lo:.2f} to {hi:.2f}")
                    continue
                lo, hi = max(t["zb"], o["zb"]), min(t["zt"], o["zt"])
                if hi - lo > 1e-6:
                    key = tuple(sorted((t["feature_id"], o["feature_id"])))
                    overlaps.setdefault(key, {"features": list(key), "z_from": round(lo, 3), "z_to": round(hi, 3),
                                              "final_diameters": sorted({round(2 * t["final"], 3), round(2 * o["final"], 3)}),
                                              "steps": set()})["steps"].update({num, other_num})
            if blocking:
                refusals[num] = {"step_number": num, "kind": "recess",
                                 "detail": (f"a longitudinal pass at diameter {2 * pass_r:.3f} from the free end would cut below "
                                            + "; ".join(blocking) + ", outside its own span; a recess needs a plunge pattern")}
        self.plan_overlaps = [dict(v, steps=sorted(v["steps"])) for v in overlaps.values()]
        return refusals

    # -- programme ---------------------------------------------------------------
    def generate_program(self, manufacturing_plan: List[Dict]) -> GCodeProgram:
        program = GCodeProgram(self.program_counter)
        self.program_counter += 1
        self._modal_spindle = None
        self._modal_coolant = None
        self.envelope_excursions = []
        self.dimension_lookups = []
        serialisable, self.refusals = self.partition_steps(manufacturing_plan)
        self.targets = self._targets(serialisable)
        recess = self._recess_refusals(serialisable, self.targets)
        for num, rec in recess.items():
            step = next(s for s in serialisable if s["step_number"] == num)
            self.refusals.append({"step_number": num, "operation": step.get("operation"), "kind": "recess",
                                  "missing_inputs": [rec["detail"]], "source_entity": {
                                      "feature_id": step.get("feature_id"), "feature_type": step.get("feature_type")}})
        serialisable = [s for s in serialisable if s["step_number"] not in recess]
        self.serialised_steps = serialisable
        self._plan_for_allowance = serialisable
        self._clear_x, self._clear_z = self._clear_position(serialisable)

        self._add_program_header(program, serialisable)
        program.add_header_line(f"(Profile: {self.PROFILE_NAME})")
        program.add_header_line(f"(Declared stock: bar diameter {self.stock_d:.2f}, free end at Z{self.z_free:.2f})")
        if self.refusals:
            program.add_header_line("(Refused, not serialised: steps "
                                    + ", ".join(str(r["step_number"]) for r in sorted(self.refusals, key=lambda r: r["step_number"]))
                                    + ")")
        program.add_header_line("")
        for block in ("(--- Machine Initialization ---)", "G18 (Select ZX plane)", "G21 (Metric units)",
                      "G40 (Cancel nose radius compensation)", "G54 (Work coordinate system)",
                      "G80 (Cancel canned cycle)", "G90 (Absolute positioning)",
                      "G97 (Constant spindle speed, rev/min, as planned)", "G99 (Feed per revolution)", ""):
            program.add_block(block)
        current_tool = None
        for tool_id, operations in self._group_operations_by_tool(serialisable).items():
            if tool_id != current_tool:
                self._add_tool_change(program, tool_id, operations[0])
                current_tool = tool_id
            for operation in operations:
                self._current_operation = operation
                self._generate_operation_gcode(program, operation)
        self._add_program_footer(program)
        return program

    def _clear_position(self, plan) -> Tuple[float, float]:
        c = self.APPROACH_CLEARANCE_MM
        xs, zs = [self.stock_d], [self.z_free]
        for step in plan:
            inputs, _ = self.serialisation_inputs(step.get("operation", ""), step.get("feature_dimensions") or {},
                                                  step.get("feature_location") or {})
            if "diameter" in inputs:
                xs.append(inputs["diameter"]["value"])
            if "z_centre" in inputs:
                half = inputs["length"]["value"] / 2.0 if "length" in inputs else 0.0
                zs.append(inputs["z_centre"]["value"] + half)
        self._current_step = "tool_change_position"
        try:
            return self._check_envelope(max(xs) + 2 * c, max(zs) + c)
        finally:
            self._current_step = None

    def _generate_turning(self, program, parameters, dimensions, location, pass_type="rough"):
        step = self._current_operation
        feed = self._extract_parameter_value(parameters, "feed_rate", 0.2)
        op = "rough_turning" if pass_type == "rough" else "finish_turning"
        p = self._plan_inputs(program, op, dimensions, location)
        t = self.targets[step["step_number"]]
        target_r = t["rough"] if pass_type == "rough" else t["final"]
        ap = self._param(step, "depth_of_cut")
        if ap is None or ap <= 0:
            raise ValueError(f"step {step['step_number']}: no planned depth of cut")
        c = self.APPROACH_CLEARANCE_MM
        z_clear = max(self.z_free, t["zt"]) + c
        a, b = self._idx(t["zb"]), self._idx(z_clear)
        r_now = float(self.r_out[a:b + 1].max())
        if pass_type == "rough":
            radii, r = [], r_now
            while r - target_r > 1e-9:
                r = max(target_r, r - ap)
                radii.append(r)
        else:
            radii = [target_r] if r_now - target_r > 1e-9 else []
        program.add_block(f"(Target diameter {2 * target_r:.3f}; current {2 * r_now:.3f}; "
                          f"{len(radii)} pass(es) of at most {ap:.3f} radial)")
        x_out = 2 * (r_now + c)
        x_out, z_clear = self._check_envelope(x_out, z_clear)
        program.add_block(f"G00 X{x_out:.2f} Z{z_clear:.2f} (Approach outside the bar, beyond its free end)")
        label = "Rough pass" if pass_type == "rough" else "Finish pass"
        for r in radii:
            x_cut, z_cut = self._check_envelope(2 * r, t["zb"])
            program.add_block(f"G00 X{x_cut:.2f} (Pass diameter, in air beyond the free end)")
            program.add_block(f"G01 Z{z_cut:.2f} F{feed:.3f} ({label})")
            program.add_block(f"G00 X{2 * r + 2 * c:.2f} (Retract)")
            program.add_block(f"G00 Z{z_clear:.2f} (Return beyond the free end)")
            depth = float(np.maximum(self.r_out[a:b + 1] - r, 0).max())
            self.r_out[a:b + 1] = np.minimum(self.r_out[a:b + 1], r)
            self.passes.append({"step": step["step_number"], "operation": op, "diameter": round(2 * r, 3),
                                "radial_depth": round(depth, 3), "planned_ap": ap})

    def _axial_hole_cycle(self, program, parameters, dimensions, location, operation, default_feed):
        feed_rate, length, z_clear, z_cut = super()._axial_hole_cycle(
            program, parameters, dimensions, location, operation, default_feed)
        _, z_clear = self._check_envelope(0.0, max(z_clear, self.z_free + self.APPROACH_CLEARANCE_MM))
        return feed_rate, length, z_clear, z_cut


def approved_steps(plan: List[Dict]) -> List[Dict]:
    return [s for s in plan if s.get("validation_status") in ("auto_approved", "expert_approved")]

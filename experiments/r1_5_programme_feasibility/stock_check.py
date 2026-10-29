"""Reviewer 1, Comment 5: material-based verification of the serialised programme.

The pipeline's own checks are envelope-based (syntax, modal state, axis
travel, parameter maxima). This module adds what they cannot see: an
axisymmetric stock model that the programme cuts, so that each move can be
checked against the material actually present, and the finished profile can be
compared with the B-Rep reference of the part (Revision 2 ground truth).

Model (declared assumptions):
  * stock: a round bar of declared diameter, solid, whose free end lies at a
    declared z (the programme approaches from +z); the ontology records no
    stock, so the bar is an input of this check;
  * tools: external turning tools are a point at the programmed X/2 (nose
    radius, insert body, and holder are ignored, so holder interference is not
    checked); drills and counterbores are cylinders of the plan feature's
    diameter, as the serialiser assumes, with a 118-degree point for the
    drill and a flat end for the counterbore (tools.owl geometry);
  * moves: G00 and G01 are straight lines; G81/G82/G83 drill from the start z
    to the cycle's Z at X0.

Checks per move: radial engagement of each feed move against the planned
depth of cut and the tool's hasMaxDepthMM; rapid moves (G00) that enter
material. Checks on the result: gouges (material removed inside the reference
part) and residual material (reference volume not reached), each attributed
to the plan step whose segment last cut that zone.
"""
import json
import math
import os
import re
import sys
from typing import Dict, List, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import GROUNDTRUTH, use_repo  # noqa: E402

use_repo()
from validator import GCodeParser, ToolpathSimulator  # noqa: E402
from simulator import TOOL_NUMBER_TO_ID  # noqa: E402

DZ = 0.01
Z0, Z1 = -60.0, 185.0
PART_Z = (80.5, 168.5)  # axial extent of the modelled shaft end (B-Rep)
TOL = 0.005


def _segment_map(nc_path):
    mapping, current = {}, None
    with open(nc_path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            if line.startswith("(--- "):
                current = None
                if ": " in line and not line.startswith("(--- Tool Change") and not line.startswith("(--- Machine"):
                    m = re.search(r"\[step (\d+)\]", line)
                    current = int(m.group(1)) if m else None
                continue
            if current is not None:
                mapping[ln] = current
    return mapping


class Stock:
    def __init__(self, diameter: float, z_free_end: float):
        self.z = np.arange(Z0, Z1 + DZ / 2, DZ)
        self.r_out = np.where(self.z <= z_free_end + 1e-9, diameter / 2.0, 0.0)
        self.r_in = np.zeros_like(self.z)
        self.owner_out = np.full(self.z.shape, -1)  # step that last cut the outer surface
        self.owner_in = np.full(self.z.shape, -1)

    def idx(self, z):
        return int(round((z - Z0) / DZ))


def reference_profiles(z):
    """Outer and inner radius of the B-Rep reference part (R01 to R10, key excluded)."""
    refs = {f["ref_id"]: f for f in json.load(open(os.path.join(GROUNDTRUTH, "step_reference_v2.json"),
                                                   encoding="utf-8"))["features"]}
    out = np.full(z.shape, np.nan)
    inn = np.zeros(z.shape)
    for rid in ("R01", "R02", "R03", "R04", "R05", "R10"):
        f = refs[rid]
        m = (z >= f["z_min"] - 1e-9) & (z <= f["z_max"] + 1e-9)
        if "diameter_small" in f:  # external cone: large diameter at the end nearer the larger neighbour
            d0, d1 = f["diameter"], f["diameter_small"]
            # R02 and R10 shrink towards +z; R04 grows towards +z
            if rid == "R04":
                d0, d1 = f["diameter_small"], f["diameter"]
            t = (z[m] - f["z_min"]) / (f["z_max"] - f["z_min"])
            out[m] = (d0 + (d1 - d0) * t) / 2.0
        else:
            out[m] = f["diameter"] / 2.0
    r7, r8, r9 = refs["R07"], refs["R08"], refs["R09"]
    m = (z >= r7["z_min"]) & (z <= r7["z_max"])
    inn[m] = r7["diameter"] / 2.0
    tip = r7["z_min"] - r7.get("drill_point_depth", 0.0)
    m = (z >= tip) & (z < r7["z_min"])
    inn[m] = (z[m] - tip) / (r7["z_min"] - tip) * r7["diameter"] / 2.0
    m = (z > r8["z_min"]) & (z <= r8["z_max"])
    inn[m] = r8["diameter"] / 2.0
    m = (z > r9["z_min"]) & (z <= r9["z_max"])
    t = (z[m] - r9["z_min"]) / (r9["z_max"] - r9["z_min"])
    inn[m] = (r9["diameter_small"] + (r9["diameter"] - r9["diameter_small"]) * t) / 2.0
    return out, inn, (80.5, 168.5)


def check_programme(nc_path: str, plan_steps: List[Dict], stock_diameter: float, z_free_end: float,
                    tool_depth_limits: Dict[str, float]) -> Dict:
    commands = GCodeParser().parse_file(nc_path)
    history = ToolpathSimulator().simulate(commands)
    by_line = {s["line"]: s for s in history}
    seg_of = _segment_map(nc_path)
    by_num = {s["step_number"]: s for s in plan_steps}
    S = Stock(stock_diameter, z_free_end)

    moves, rapids_into_stock, outside_part = [], [], []
    px, pz = 0.0, 0.0
    tool_id = None
    for cmd in commands:
        st = by_line.get(cmd.line_number)
        if st and st.get("tool") is not None:
            tool_id = TOOL_NUMBER_TO_ID.get(st.get("tool"), tool_id)
        step = seg_of.get(cmd.line_number)
        for g in (cmd.g_codes or []):
            if g in ("G00", "G01"):
                nx = cmd.parameters.get("X", px)
                nz = cmd.parameters.get("Z", pz)
                if tool_id is None:
                    # before the first tool call the start position is unknown
                    # (the simulator's X0 Z0 origin is not a machine position)
                    px, pz = nx, nz
                    continue
                drilling_tool = tool_id in ("drill_bit", "counterbore_cutter")
                if drilling_tool:
                    # a drill moving on the axis: only rapid entry into solid material matters
                    d = _tool_diameter(by_num.get(step)) if step else None
                    if g == "G00" and d:
                        lo, hi = sorted((pz, nz))
                        a, b = S.idx(max(lo, Z0)), S.idx(min(hi, Z1))
                        solid = (S.r_in[a:b + 1] < d / 2 - TOL) & (S.r_out[a:b + 1] > TOL)
                        if solid.any() and nz < pz:
                            rapids_into_stock.append({"line": cmd.line_number, "step": step, "tool": tool_id,
                                                      "depth_mm": round(float((b - a) * DZ), 3)})
                    px, pz = nx, nz
                    continue
                n = max(2, int(math.ceil(max(abs(nz - pz), abs(nx - px) / 2) / DZ)) + 1)
                xs = np.linspace(px, nx, n) / 2.0
                zs = np.linspace(pz, nz, n)
                ii = np.clip(np.rint((zs - Z0) / DZ).astype(int), 0, len(S.z) - 1)
                pen = S.r_out[ii] - xs
                inside = (pen > TOL) & (xs >= S.r_in[ii] - TOL)
                if g == "G00":
                    if inside.any():
                        rapids_into_stock.append({"line": cmd.line_number, "step": step, "tool": tool_id,
                                                  "depth_mm": round(float(pen[inside].max()), 3),
                                                  "at_z": round(float(zs[inside][0]), 3)})
                else:
                    eng = float(pen[inside].max()) if inside.any() else 0.0
                    lo_z, hi_z = min(pz, nz), max(pz, nz)
                    outside = lo_z < PART_Z[0] - 1e-6 and eng > TOL
                    if outside:
                        outside_part.append({"line": cmd.line_number, "step": step, "z_from": round(lo_z, 3),
                                             "z_to": round(hi_z, 3), "radial_engagement_mm": round(eng, 3)})
                    for k, r in zip(ii, xs):
                        if r < S.r_out[k]:
                            S.r_out[k] = r
                            S.owner_out[k] = step if step is not None else -1
                    step_rec = by_num.get(step, {})
                    ap = ((step_rec.get("parameters") or {}).get("depth_of_cut") or {}).get("value")
                    moves.append({"line": cmd.line_number, "step": step, "operation": step_rec.get("operation"),
                                  "tool": tool_id, "radial_engagement_mm": round(eng, 3),
                                  "z_from": round(min(pz, nz), 3), "z_to": round(max(pz, nz), 3),
                                  "planned_depth_of_cut_mm": ap, "tool_max_depth_mm": tool_depth_limits.get(tool_id),
                                  "exceeds_planned": ap is not None and eng > ap + TOL,
                                  "exceeds_tool": tool_depth_limits.get(tool_id) is not None
                                  and eng > tool_depth_limits[tool_id] + TOL})
                px, pz = nx, nz
            elif g in ("G81", "G82", "G83"):
                zt = cmd.parameters.get("Z", pz)
                rec = by_num.get(step, {})
                d = _tool_diameter(rec)
                point = 118.0 if tool_id == "drill_bit" else None
                cone = (d / 2.0) / math.tan(math.radians(point / 2.0)) if point else 0.0
                lo, hi = sorted((zt, pz))
                a, b = S.idx(max(lo, Z0)), S.idx(min(hi, Z1))
                before = S.r_in.copy()
                for k in range(a, b + 1):
                    zz = S.z[k]
                    r = d / 2.0 if zz >= zt + cone else (d / 2.0) * (zz - zt) / cone if cone else d / 2.0
                    if r > S.r_in[k] and S.r_out[k] > TOL:
                        S.r_in[k] = r
                        S.owner_in[k] = step
                removed = float(np.sum(np.pi * (S.r_in[a:b + 1] ** 2 - before[a:b + 1] ** 2)) * DZ)
                ap = ((rec.get("parameters") or {}).get("depth_of_cut") or {}).get("value")
                moves.append({"line": cmd.line_number, "step": step, "operation": rec.get("operation"), "tool": tool_id,
                              "cycle": g, "diameter_mm": d, "from_z": pz, "to_z": zt,
                              "depth_in_material_mm": round(max(0.0, min(pz, z_free_end) - zt), 3),
                              "volume_removed_mm3": round(removed, 1),
                              "tool_max_depth_mm": tool_depth_limits.get(tool_id),
                              "exceeds_tool": tool_depth_limits.get(tool_id) is not None
                              and max(0.0, min(pz, z_free_end) - zt) > tool_depth_limits[tool_id] + TOL})
            # other G codes: modal only
    return {"stock": {"diameter_mm": stock_diameter, "free_end_z": z_free_end}, "moves": moves,
            "rapids_into_stock": rapids_into_stock, "feed_moves_below_part_extent": outside_part,
            "conformance": conformance(S)}


def _tool_diameter(step_rec):
    dims = (step_rec or {}).get("feature_dimensions") or {}
    d = dims.get("Ø") or dims.get("D")
    return float(d) if d else None


def _zones(mask, z, val, owner):
    """Contiguous zones where mask is true: z range, max value, owning steps."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            seg = slice(i, j + 1)
            owners = sorted({int(o) for o in owner[seg] if o >= 0})
            out.append({"z_from": round(float(z[i]), 2), "z_to": round(float(z[j]), 2),
                        "max_mm": round(float(np.nanmax(val[seg])), 3), "steps": owners})
            i = j + 1
        else:
            i += 1
    return [o for o in out if o["z_to"] - o["z_from"] >= 0.05 - 1e-9]


REF_ZONES_OUT = [("R01", 80.5, 118.0), ("R02", 118.0, 118.5), ("R03", 118.5, 120.254), ("R04", 120.254, 121.0),
                 ("R05", 121.0, 167.5), ("R10", 167.5, 168.5)]
REF_ZONES_IN = [("R07", 141.457, 162.5), ("R08", 162.5, 165.209), ("R09", 165.209, 168.5)]


def _annotate(zones, table):
    for zn in zones:
        zn["reference_features"] = [rid for rid, a, b in table if zn["z_from"] < b - 1e-6 and zn["z_to"] > a + 1e-6]
    return zones


def conformance(S: Stock) -> Dict:
    ref_out, ref_in, (za, zb) = reference_profiles(S.z)
    part = (S.z >= za) & (S.z <= zb) & ~np.isnan(ref_out)
    gouge_out = np.where(part, ref_out - S.r_out, np.nan)
    resid_out = np.where(part, S.r_out - ref_out, np.nan)
    gouge_in = np.where((S.z >= za) & (S.z <= zb), S.r_in - ref_in, np.nan)
    resid_in = np.where((S.z >= za) & (S.z <= zb), ref_in - S.r_in, np.nan)
    beyond = S.z > zb
    return {
        "outer_gouges": _annotate(_zones(np.nan_to_num(gouge_out) > TOL, S.z, gouge_out, S.owner_out), REF_ZONES_OUT),
        "outer_residual": _annotate(_zones(np.nan_to_num(resid_out) > TOL, S.z, resid_out, S.owner_out), REF_ZONES_OUT),
        "inner_gouges": _annotate(_zones(np.nan_to_num(gouge_in) > TOL, S.z, gouge_in, S.owner_in), REF_ZONES_IN),
        "inner_residual": _annotate(_zones(np.nan_to_num(resid_in) > TOL, S.z, resid_in, S.owner_in), REF_ZONES_IN),
        "material_beyond_part_end_mm": round(float((S.z[beyond & (S.r_out > TOL)].max() - zb)) if (beyond & (S.r_out > TOL)).any() else 0.0, 3),
    }

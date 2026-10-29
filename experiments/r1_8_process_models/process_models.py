"""Corrected process models for Reviewer 1, Comment 8.

Replaces, for evaluation purposes, the two simulator channels the reviewer
criticised, without modifying the pipeline repository:

* Cutting force: the Kienzle chip-thickness law, Fc = kc11 * b * h**(1 - mc)
  per cutting edge, instead of a constant specific force. Power follows from
  force and cutting speed (P = sum over edges of Fc * v_edge / 60000), so the
  two channels are dimensionally consistent by construction, and drilling
  torque is reported so that P = M * omega can be checked.
* Tool wear: consumed Taylor tool life, D = sum_i t_i / T(v_i) per tool, with
  T(v) = T_ref * (v_ref / v)**(1/n) anchored at handbook-recommended speeds.
  The in-cut times t_i are taken from the programme on the same time base as
  the pipeline's cycle-time estimator (asserted), not from a separate clock;
  D is a dimensionless fraction of tool life and is never clamped, so it
  cannot saturate.

Inputs per cut come from the approved plan step that owns the programme
segment (feed, spindle speed, depth of cut, feature diameter), the tool's
material and point/edge geometry from tools.owl, and declared nominal
constants (process_constants.json). A missing input makes the quantity
'unavailable'; nothing is defaulted.

The feedback path reuses the pipeline's ExpertValidationStore and its
'critical_simulation_finding' reason code, so a recorded expert resolution is
honoured on later runs exactly as for the other exception conditions.
"""
import json
import math
import os
import re
import sys
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import REPO, use_repo  # noqa: E402

use_repo()
from validator import GCodeParser, ToolpathSimulator  # noqa: E402
from simulator import CuttingTimeEstimator, TOOL_NUMBER_TO_ID  # noqa: E402
from expert_validation import ExpertValidationStore  # noqa: E402

CONSTANTS_PATH = os.path.join(HERE, "process_constants.json")


def load_constants(path: str = CONSTANTS_PATH) -> Dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------------------
# Tool knowledge read from the ontology (tools.owl), not hard-coded
# ----------------------------------------------------------------------------

def read_tool_knowledge(tools_owl: Optional[str] = None) -> Dict[str, Dict]:
    """{OntologyIndividual: {'material': str, 'geometry': str}} from tools.owl."""
    import rdflib
    tools_owl = tools_owl or os.path.join(REPO, "knowledge", "foundation", "tools.owl")
    g = rdflib.Graph()
    g.parse(tools_owl, format="xml")
    out: Dict[str, Dict] = {}
    for s, p, o in g:
        name = str(s).split("#")[-1]
        prop = str(p).split("#")[-1]
        if prop == "hasToolMaterial":
            out.setdefault(name, {})["material"] = str(o)
        elif prop == "hasGeometry":
            out.setdefault(name, {})["geometry"] = str(o)
    return out


def angle_from_geometry(geometry: Optional[str]) -> Optional[float]:
    """'118deg Point Angle' -> 118.0; None when the geometry states no angle."""
    if not geometry:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*deg", geometry)
    return float(m.group(1)) if m else None


# ----------------------------------------------------------------------------
# Kienzle cutting force
# ----------------------------------------------------------------------------

def kienzle_edge_force(b_mm: float, h_mm: float, kc11: float, mc: float) -> float:
    """Main cutting force on one edge, N: Fc = kc11 * b * h**(1 - mc)."""
    if b_mm <= 0 or h_mm <= 0:
        raise ValueError("chip width and thickness must be positive")
    return kc11 * b_mm * h_mm ** (1.0 - mc)


def cutting_speed(diameter_mm: float, rpm: float) -> float:
    """Cutting speed at the given diameter, m/min."""
    return math.pi * diameter_mm * rpm / 1000.0


def force_power(process: str, f: Optional[float], ap: Optional[float], d: Optional[float],
                rpm: Optional[float], kc11: float, mc: float,
                kappa_r_deg: Optional[float] = None,
                point_angle_deg: Optional[float] = None) -> Dict:
    """Kienzle force and power for one cut.

    turning / counterboring (single effective edge, entering angle kappa_r):
        h = f sin(kappa_r), b = ap / sin(kappa_r), Fc = kc11 b h^(1-mc)
        P = Fc * vc / 60000 with vc at the cut diameter.
    drilling (two lips, point angle sigma):
        per lip h = (f/2) sin(sigma/2), b = (D/2) / sin(sigma/2);
        torque M = 2 * Fc_lip * (D/4) / 1000 (N m);
        P = 2 * Fc_lip * (vc/2) / 60000 (force acts at mean radius D/4).
    Returns 'unavailable' with the missing inputs listed when any input is absent.
    """
    need = {"feed_per_rev": f, "diameter": d, "spindle_speed": rpm}
    if process in ("turning", "counterboring"):
        need["depth_of_cut"] = ap
        need["entering_angle"] = kappa_r_deg
    elif process == "drilling":
        need["point_angle"] = point_angle_deg
    else:
        return {"model": "unavailable", "missing": [f"process:{process}"]}
    missing = [k for k, v in need.items() if v is None or (isinstance(v, (int, float)) and v <= 0)]
    if missing:
        return {"model": "unavailable", "missing": missing}

    vc = cutting_speed(d, rpm)
    if process == "drilling":
        s = math.sin(math.radians(point_angle_deg / 2.0))
        h = (f / 2.0) * s
        b = (d / 2.0) / s
        fc_edge = kienzle_edge_force(b, h, kc11, mc)
        torque = 2.0 * fc_edge * (d / 4.0) / 1000.0
        power = 2.0 * fc_edge * (vc / 2.0) / 60000.0
        edges = 2
    else:
        s = math.sin(math.radians(kappa_r_deg))
        h = f * s
        b = ap / s
        fc_edge = kienzle_edge_force(b, h, kc11, mc)
        torque = fc_edge * (d / 2.0) / 1000.0
        power = fc_edge * vc / 60000.0
        edges = 1
    return {
        "model": f"kienzle_{process}",
        "h_mm": h, "b_mm": b, "kc_N_per_mm2": kc11 * h ** (-mc),
        "Fc_per_edge_N": fc_edge, "edges": edges, "torque_Nm": torque,
        "vc_m_per_min": vc, "power_kW": power,
        # P = M * omega, omega = 2 pi n / 60 (rad/s); kW
        "power_from_torque_kW": torque * 2.0 * math.pi * rpm / 60.0 / 1000.0,
    }


# ----------------------------------------------------------------------------
# Taylor tool life
# ----------------------------------------------------------------------------

def taylor_life(v: float, v_ref: float, t_ref: float, n: float) -> float:
    """Tool life (min) at cutting speed v: T = T_ref (v_ref / v)^(1/n)."""
    if v <= 0:
        raise ValueError("cutting speed must be positive for a cut that consumes tool life")
    return t_ref * (v_ref / v) ** (1.0 / n)


def taylor_key(tool_material: str, process: str) -> str:
    family = "drilling" if process == "drilling" else (
        "hole_making" if process == "counterboring" else "turning")
    return f"{tool_material}|{family}"


# ----------------------------------------------------------------------------
# Programme segments on the pipeline's own time base
# ----------------------------------------------------------------------------

def _segment_map(nc_path: str) -> Dict[int, int]:
    """line number -> plan step number, from the '(--- op: feature [step N] ---)' headers."""
    mapping: Dict[int, int] = {}
    current = None
    with open(nc_path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            if line.startswith("(--- "):
                is_seg = (": " in line and not line.startswith("(--- Tool Change")
                          and not line.startswith("(--- Machine"))
                current = None
                if is_seg:
                    m = re.search(r"\[step (\d+)\]", line)
                    if not m:
                        raise RuntimeError(f"{nc_path}:{ln}: untagged segment header")
                    current = int(m.group(1))
                continue
            if current is not None:
                mapping[ln] = current
    return mapping


def segment_times(nc_path: str) -> Dict:
    """Per-segment feed (in-cut) time and estimator time, using the same
    parser, modal state and timing formulas as CuttingTimeEstimator, and
    asserting that the segment sums reproduce its total."""
    commands = GCodeParser().parse_file(nc_path)
    history = ToolpathSimulator().simulate(commands)
    est = CuttingTimeEstimator()
    total = est.calculate_cycle_time(commands, history)
    by_line = {s["line"]: s for s in history}
    seg_of = _segment_map(nc_path)

    segs: Dict[int, Dict] = {}
    prev_x, prev_z = 0.0, 0.0
    for cmd in commands:
        st = by_line.get(cmd.line_number)
        nx = st["x"] if st else prev_x
        nz = st["z"] if st else prev_z
        rpm = (st.get("spindle_rpm") or 0.0) if st and st.get("spindle_on") else 0.0
        feed = (st.get("feed_rate") or 0.0) if st else 0.0
        step = seg_of.get(cmd.line_number)
        for g in (cmd.g_codes or []):
            in_cut = 0.0
            est_t = 0.0
            if g in ("G01", "G02", "G03"):
                dist = math.hypot(nx - prev_x, nz - prev_z)
                if dist > 0 and rpm > 0 and feed > 0:
                    in_cut = est.calculate_cutting_time(dist, feed, rpm)
                    est_t = in_cut
            elif g in ("G81", "G82", "G83"):
                z_t = cmd.parameters.get("Z", prev_z)
                depth = abs(prev_z - z_t)
                q = cmd.parameters.get("Q")
                if q is None:
                    mq = re.search(r"\bQ(\d+(?:\.\d+)?)", (cmd.raw_text or "").split("(", 1)[0].upper())
                    q = float(mq.group(1)) if mq else None
                pecks = max(1, math.ceil(depth / q)) if (g == "G83" and q) else 1
                if depth > 0 and rpm > 0 and feed > 0:
                    in_cut = est.calculate_cutting_time(depth, feed, rpm)
                    est_t = est.calculate_drilling_time(depth, feed, rpm, pecks)
            if est_t > 0:
                if step is None:
                    raise RuntimeError(f"feed motion on line {cmd.line_number} outside any segment")
                rec = segs.setdefault(step, {"step_number": step, "in_cut_s": 0.0, "estimator_s": 0.0,
                                             "tool": TOOL_NUMBER_TO_ID.get(st.get("tool")) if st else None,
                                             "rpm": rpm})
                rec["in_cut_s"] += in_cut
                rec["estimator_s"] += est_t
        if st:
            prev_x, prev_z = nx, nz

    s_est = sum(r["estimator_s"] for r in segs.values())
    if abs(round(s_est, 2) - total["cutting_time_seconds"]) > 0.011:
        raise AssertionError(f"segment times {s_est:.2f} s do not reproduce the estimator's "
                             f"{total['cutting_time_seconds']} s")
    return {"segments": segs, "estimator_total": total}


# ----------------------------------------------------------------------------
# Evaluation of one programme
# ----------------------------------------------------------------------------

def _param(step: Dict, key: str) -> Optional[float]:
    v = ((step.get("parameters") or {}).get(key) or {}).get("value")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def evaluate_run(run_dir: str, material: str = "steel_1045", constants: Optional[Dict] = None,
                 overrides: Optional[Dict] = None) -> Dict:
    """Kienzle force/power and Taylor tool-life consumption for one pipeline run.

    overrides: optional {'kc11':..., 'mc':..., 'kappa_r':..., 'taylor': {key: {'n':..,'T_ref_min':..}},
    'speeds_at_v_ref': bool} used by the sensitivity sweep and the handbook-speed scenario.
    """
    C = constants or load_constants()
    ov = overrides or {}
    kz = C["kienzle"][material]
    kc11 = ov.get("kc11", kz["kc11_N_per_mm2"])
    mc = ov.get("mc", kz["mc"])
    kappa_turn = ov.get("kappa_r", C["geometry"]["turning_entering_angle_deg"]["value"])
    tools = read_tool_knowledge()

    plan = json.load(open(os.path.join(run_dir, "manufacturing_plan.json"), encoding="utf-8"))
    by_num = {s["step_number"]: s for s in plan}
    nc = [f for f in os.listdir(run_dir) if f.endswith(".nc")]
    if len(nc) != 1:
        raise RuntimeError(f"expected one programme in {run_dir}, found {nc}")
    timing = segment_times(os.path.join(run_dir, nc[0]))

    cuts: List[Dict] = []
    for num, seg in sorted(timing["segments"].items()):
        step = by_num[num]
        op = step["operation"]
        process = "drilling" if op == "drilling" else (
            "counterboring" if op == "counterboring" else (
                "turning" if op in ("rough_turning", "finish_turning", "facing", "grooving", "chamfering")
                else op))
        tk = tools.get(step.get("ontology_tool"), {})
        dims = step.get("feature_dimensions") or {}
        d = dims.get("Ø") or dims.get("D")
        angle = angle_from_geometry(tk.get("geometry"))
        fp = force_power(process, _param(step, "feed_rate"), _param(step, "depth_of_cut"),
                         float(d) if d else None, _param(step, "spindle_speed"), kc11, mc,
                         kappa_r_deg=(angle if process == "counterboring" else kappa_turn),
                         point_angle_deg=angle if process == "drilling" else None)
        # Constant-kc model of the reference run (v7) for comparison.
        cut = {"step_number": num, "operation": op, "process": process, "tool_id": step["tool_id"],
               "ontology_tool": step.get("ontology_tool"), "tool_material": tk.get("material"),
               "tool_geometry": tk.get("geometry"), "in_cut_s": seg["in_cut_s"],
               "estimator_s": seg["estimator_s"], "force_power": fp}
        # Taylor
        key = taylor_key(tk.get("material", "?"), process)
        tc = (C["taylor"].get(material) or {}).get(key)
        if tc is None or fp.get("model") == "unavailable":
            cut["taylor"] = {"model": "unavailable", "key": key,
                             "missing": ["taylor constants" if tc is None else "cutting speed"]}
        else:
            t_ov = (ov.get("taylor") or {}).get(key, {})
            n = t_ov.get("n", tc["n"])
            t_ref = t_ov.get("T_ref_min", tc["T_ref_min"])
            v_ref = t_ov.get("v_ref_m_per_min", tc["v_ref_m_per_min"])
            v = fp["vc_m_per_min"]
            t_cut_min = seg["in_cut_s"] / 60.0
            if ov.get("speeds_at_v_ref"):
                # Scenario: spindle speed reset so that v = v_ref at this diameter;
                # in-cut time scales inversely with spindle speed.
                t_cut_min *= v / v_ref
                v = v_ref
            life = taylor_life(v, v_ref, t_ref, n)
            cut["taylor"] = {"model": "taylor_anchored", "key": key, "n": n, "T_ref_min": t_ref,
                             "v_ref_m_per_min": v_ref, "v_m_per_min": v, "speed_ratio": v / v_ref,
                             "extrapolated_below_v_ref": v < v_ref, "life_min": life,
                             "in_cut_min": t_cut_min, "consumption": t_cut_min / life}
        cuts.append(cut)

    per_tool: Dict[str, Dict] = {}
    for c in cuts:
        t = per_tool.setdefault(c["tool_id"], {"tool_id": c["tool_id"], "steps": [], "in_cut_min": 0.0,
                                                "consumption_per_part": 0.0, "available": True})
        t["steps"].append(c["step_number"])
        t["in_cut_min"] += c["taylor"].get("in_cut_min", c["in_cut_s"] / 60.0)
        if c["taylor"]["model"] == "unavailable":
            t["available"] = False
        else:
            t["consumption_per_part"] += c["taylor"]["consumption"]
    for t in per_tool.values():
        t["parts_per_edge"] = (1.0 / t["consumption_per_part"]) if t["available"] and t["consumption_per_part"] > 0 else None

    fps = [c["force_power"] for c in cuts if c["force_power"].get("model") != "unavailable"]
    return {
        "run_dir": os.path.basename(run_dir), "material": material,
        "kienzle": {"kc11_N_per_mm2": kc11, "mc": mc, "turning_entering_angle_deg": kappa_turn},
        "estimator_total": timing["estimator_total"],
        "sum_in_cut_s": sum(c["in_cut_s"] for c in cuts),
        "cuts": cuts, "per_tool": per_tool,
        "force_mean_N": sum(f["Fc_per_edge_N"] for f in fps) / len(fps) if fps else None,
        "force_max_N": max((f["Fc_per_edge_N"] for f in fps), default=None),
        "power_max_kW": max((f["power_kW"] for f in fps), default=None),
        "power_torque_max_abs_diff_kW": max((abs(f["power_kW"] - f["power_from_torque_kW"]) for f in fps), default=None),
    }


# ----------------------------------------------------------------------------
# Feedback path: tool-life exceedance -> expert-validation request
# ----------------------------------------------------------------------------

def tool_life_feedback(result: Dict, plan_steps: List[Dict], store: ExpertValidationStore,
                       threshold: float, parts_done: int = 0) -> List[Dict]:
    """Raise a 'critical_simulation_finding' request for every serialised step
    whose tool would pass `threshold` of its Taylor life during the next part,
    given `parts_done` parts already machined with the same edge. Get-or-create:
    a recorded resolution is reused, never duplicated. Tools whose consumption
    is unavailable raise 'missing_knowledge' instead of being assumed healthy.
    """
    by_num = {s["step_number"]: s for s in plan_steps}
    raised = []
    for tool_id, t in result["per_tool"].items():
        if not t["available"]:
            for num in t["steps"]:
                s = by_num[num]
                req = store.create_request(s["feature_id"], s["feature_type"], "missing_knowledge",
                                           f"No Taylor tool-life model for tool {tool_id!r}; "
                                           f"tool-life consumption cannot be checked.",
                                           operation=s["operation"])
                raised.append({"step_number": num, "tool_id": tool_id, "reason": req.reason_code,
                               "request_id": req.request_id, "status": req.status})
            continue
        after_next = (parts_done + 1) * t["consumption_per_part"]
        if after_next < threshold:
            continue
        for num in t["steps"]:
            s = by_num[num]
            req = store.create_request(
                s["feature_id"], s["feature_type"], "critical_simulation_finding",
                (f"Tool {tool_id!r}: Taylor tool-life consumption would reach {after_next:.3f} "
                 f"of edge life on part {parts_done + 1} (threshold {threshold}); "
                 f"{t['consumption_per_part']:.5f} per part. Review or change the edge before this part."),
                operation=s["operation"])
            raised.append({"step_number": num, "tool_id": tool_id, "reason": req.reason_code,
                           "request_id": req.request_id, "status": req.status,
                           "consumption_after_next_part": after_next})
    store.save()
    return raised


def first_trigger_part(consumption_per_part: float, threshold: float) -> int:
    """Index (1-based) of the first part during which cumulative consumption
    reaches the threshold: smallest k with k * c >= threshold."""
    return max(1, math.ceil(threshold / consumption_per_part - 1e-12))

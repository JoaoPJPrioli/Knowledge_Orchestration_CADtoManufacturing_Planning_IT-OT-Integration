"""
Plan-to-programme parameter fidelity.

For every operation segment of an emitted programme, checks that the spindle
speed (S, with the spindle running), the feed (F) and the coolant state in
effect during each of the segment's cutting moves equal the approved step's
spindle_speed, feed_rate and coolant values. This is a check of the
serialiser against the parameter package KEFC approved, not a machining
check.

Segments are identified by their header '(--- <operation>: <feature> ---)',
the definition main.py's plan-to-programme assertion uses. The approved step
of a segment is read from the header's '[step N]' tag when present
(programmes from Revision 3 on); for older programmes without the tag the
mapping is reconstructed from the serialiser's ordering rule (approved steps
grouped by tool in order of first appearance, plan order within a group),
and the result records which mapping was used.
"""
import re
from typing import Dict, List, Optional

CUTTING_GCODES = {1, 2, 3, 81, 82, 83}
FEED_TOLERANCE = 5e-4      # F is written with three decimals
SPINDLE_TOLERANCE = 1e-6

_STEP_TAG = re.compile(r"\[step (\d+)\]")


def _value(parameters: Dict, key: str):
    v = parameters.get(key)
    if isinstance(v, dict):
        v = v.get("value")
    return v


def _serialiser_order(steps: List[Dict]) -> List[Dict]:
    groups: Dict[str, List[Dict]] = {}
    for s in steps:
        groups.setdefault(s.get("tool_id"), []).append(s)
    return [s for g in groups.values() for s in g]


def _is_segment_header(line: str) -> bool:
    return (line.startswith("(--- ") and ": " in line
            and not line.startswith("(--- Tool Change") and not line.startswith("(--- Machine"))


def check_parameter_fidelity(gcode_path: str, approved_steps: List[Dict]) -> Dict:
    with open(gcode_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    by_number = {s.get("step_number"): s for s in approved_steps}
    fallback = _serialiser_order(approved_steps)
    segments: List[Dict] = []
    spindle_rpm: Optional[float] = None
    spindle_on = False
    feed: Optional[float] = None
    coolant = False
    current: Optional[Dict] = None
    mapping_modes = set()

    for line_number, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("(--- "):
            if _is_segment_header(line):
                m = _STEP_TAG.search(line)
                if m:
                    step = by_number.get(int(m.group(1)))
                    mapping_modes.add("step_tag")
                else:
                    idx = len(segments)
                    step = fallback[idx] if idx < len(fallback) else None
                    mapping_modes.add("serialiser_order_reconstruction")
                current = {"header": line, "line": line_number, "step": step, "moves": []}
                segments.append(current)
            else:
                current = None  # tool change, initialisation or programme end
            continue
        code = line.split("(", 1)[0].upper()
        if not code.strip():
            continue
        s_word = re.search(r"\bS(\d+(?:\.\d+)?)", code)
        if s_word:
            spindle_rpm = float(s_word.group(1))
        m_codes = {int(x) for x in re.findall(r"\bM(\d+)", code)}
        if 3 in m_codes or 4 in m_codes:
            spindle_on = True
        if 5 in m_codes:
            spindle_on = False
        if 8 in m_codes:
            coolant = True
        if 9 in m_codes:
            coolant = False
        f_word = re.search(r"\bF(\d+(?:\.\d+)?)", code)
        if f_word:
            feed = float(f_word.group(1))
        g_codes = {int(x) for x in re.findall(r"\bG(\d+)", code)}
        if current is not None and g_codes & CUTTING_GCODES:
            current["moves"].append({"line": line_number,
                                     "spindle_rpm": spindle_rpm if spindle_on else 0.0,
                                     "feed": feed, "coolant": coolant})

    result = {"segments_checked": len(segments), "spindle_match": 0, "feed_match": 0,
              "coolant_match": 0, "segments_without_cutting_moves": 0,
              "unmapped_segments": 0, "mapping": sorted(mapping_modes), "mismatches": []}
    for seg in segments:
        step = seg["step"]
        if step is None:
            result["unmapped_segments"] += 1
            result["mismatches"].append({"segment": seg["header"], "line": seg["line"], "problem": "no approved step"})
            continue
        params = step.get("parameters") or {}
        want_s, want_f, want_c = _value(params, "spindle_speed"), _value(params, "feed_rate"), _value(params, "coolant")
        moves = seg["moves"]
        if not moves:
            result["segments_without_cutting_moves"] += 1
            result["mismatches"].append({"segment": seg["header"], "line": seg["line"],
                                         "step_number": step.get("step_number"), "problem": "no cutting moves"})
            continue
        s_ok = want_s is not None and all(m["spindle_rpm"] is not None and abs(m["spindle_rpm"] - float(want_s)) <= SPINDLE_TOLERANCE for m in moves)
        f_ok = want_f is not None and all(m["feed"] is not None and abs(m["feed"] - float(want_f)) <= FEED_TOLERANCE for m in moves)
        c_ok = want_c is not None and all(m["coolant"] == bool(want_c) for m in moves)
        result["spindle_match"] += s_ok
        result["feed_match"] += f_ok
        result["coolant_match"] += c_ok
        if not (s_ok and f_ok and c_ok):
            result["mismatches"].append({
                "segment": seg["header"], "line": seg["line"], "step_number": step.get("step_number"),
                "approved": {"spindle_speed": want_s, "feed_rate": want_f, "coolant": want_c},
                "programmed": sorted({(m["spindle_rpm"], m["feed"], m["coolant"]) for m in moves}),
            })
    n = result["segments_checked"]
    result["passed"] = (n == len(approved_steps) and result["spindle_match"] == n
                        and result["feed_match"] == n and result["coolant_match"] == n)
    return result

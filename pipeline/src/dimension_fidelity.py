"""
Plan-to-programme dimension fidelity (Revision 6).

For every operation segment of an emitted programme, checks that

1. the segment declares its plan inputs ('(Plan inputs: name value [source]; ...)'),
2. every declared input equals the value under the cited key of the approved
   step's feature_dimensions or feature_location (a lookup that cannot be
   traced to the plan counts as defaulted), and
3. every coordinate word of the segment's cutting moves (G01, G81, G83)
   equals a target derived from those inputs by the toolpath pattern's
   geometry, recomputed here independently of the serialiser.

Rapid moves use the serialiser's clearances and are not checked. This is a
check of the serialiser against the plan, not a machining check.
"""
import math
import re
from typing import Dict, List, Optional

TOLERANCE = 0.006          # coordinates are written with two decimals
INPUT_TOLERANCE = 6e-4     # inputs are written with three decimals
_STEP_TAG = re.compile(r"\[step (\d+)\]")
_INPUTS = re.compile(r"^\(Plan inputs: (.*)\)$")
_ITEM = re.compile(r"^\s*(\w+) (-?\d+(?:\.\d+)?) \[(.+)\]\s*$")


def _is_segment_header(line: str) -> bool:
    return (line.startswith("(--- ") and ": " in line
            and not line.startswith("(--- Tool Change") and not line.startswith("(--- Machine"))


def _plan_value(source: str, dims: Dict, loc: Dict) -> Optional[float]:
    def num(m, k):
        v = (m or {}).get(k)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    if source.startswith("location "):
        return num(loc, source.split(" ", 1)[1])
    m = re.fullmatch(r"2 x (\S+)", source)
    if m:
        v = num(dims, m.group(1))
        return None if v is None else 2.0 * v
    m = re.fullmatch(r"(\S+) - 2 x (\S+)", source)
    if m:
        a, b = num(dims, m.group(1)), num(dims, m.group(2))
        return None if a is None or b is None else a - 2.0 * b
    return num(dims, source)


def _targets(op: str, p: Dict[str, float]) -> Dict[str, List[float]]:
    zc, L = p.get("z_centre"), p.get("length")
    top = bottom = None
    if zc is not None and L is not None:
        top, bottom = zc + L / 2.0, zc - L / 2.0
    if op in ("rough_turning", "finish_turning"):
        return {"X": [p["diameter"]], "Z": [bottom]}
    if op == "facing":
        return {"X": [0.0], "Z": [top]}
    if op in ("drilling", "counterboring", "boring"):
        return {"X": [], "Z": [bottom]}
    if op == "chamfering":
        start = p["diameter"] - 2.0 * L * math.tan(math.radians(p["chamfer_angle"]))
        return {"X": [start, p["diameter"]], "Z": [top, bottom]}
    if op == "grooving":
        return {"X": [p["groove_bottom_diameter"]], "Z": []}
    return {"X": [], "Z": []}


def check_dimension_fidelity(gcode_path: str, approved_steps: List[Dict]) -> Dict:
    with open(gcode_path, encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh.read().splitlines()]
    by_number = {s.get("step_number"): s for s in approved_steps}
    segments: List[Dict] = []
    cur: Optional[Dict] = None
    for raw in lines:
        if raw.startswith("(--- "):
            if _is_segment_header(raw):
                m = _STEP_TAG.search(raw)
                step = by_number.get(int(m.group(1))) if m else None
                cur = {"header": raw, "step_number": step.get("step_number") if step else None,
                       "operation": step.get("operation") if step else None, "step": step,
                       "inputs": None, "cutting_words": []}
                segments.append(cur)
            else:
                cur = None
            continue
        if cur is None:
            continue
        mi = _INPUTS.match(raw)
        if mi:
            items = {}
            for part in mi.group(1).split(";"):
                mm = _ITEM.match(part)
                if mm:
                    items[mm.group(1)] = {"value": float(mm.group(2)), "source": mm.group(3)}
            cur["inputs"] = items
            continue
        code = raw.split("(", 1)[0].upper()
        g = {int(x) for x in re.findall(r"\bG(\d+)", code)}
        if g & {1, 81, 83}:
            for axis, val in re.findall(r"\b([XZ])(-?\d+(?:\.\d+)?)", code):
                cur["cutting_words"].append((axis, float(val)))

    per_segment, lookups, verified, unexplained, words = [], 0, 0, 0, 0
    problems = []
    for s in segments:
        step = s["step"] or {}
        dims, loc = step.get("feature_dimensions") or {}, step.get("feature_location") or {}
        rec = {"step_number": s["step_number"], "operation": s["operation"], "inputs": {},
               "cutting_words_checked": 0, "unexplained_cutting_words": []}
        if s["step"] is None:
            problems.append(f"{s['header']}: no approved step")
        if s["inputs"] is None:
            problems.append(f"{s['header']}: no plan-inputs declaration")
            per_segment.append(rec)
            continue
        values = {}
        for name, item in s["inputs"].items():
            lookups += 1
            pv = _plan_value(item["source"], dims, loc)
            ok = pv is not None and abs(pv - item["value"]) <= INPUT_TOLERANCE
            verified += ok
            rec["inputs"][name] = {"value": item["value"], "source": item["source"], "traced_to_plan": ok}
            if not ok:
                problems.append(f"step {s['step_number']}: {name} {item['value']} [{item['source']}] "
                                f"not found in the plan (plan value {pv})")
            values[name] = pv if pv is not None else item["value"]
        try:
            tgt = _targets(s["operation"], values)
        except (KeyError, TypeError):
            tgt = {"X": [], "Z": []}
            problems.append(f"step {s['step_number']}: inputs incomplete for {s['operation']}")
        for axis, val in s["cutting_words"]:
            words += 1
            rec["cutting_words_checked"] += 1
            if not any(t is not None and abs(val - t) <= TOLERANCE for t in tgt.get(axis, [])):
                unexplained += 1
                rec["unexplained_cutting_words"].append(f"{axis}{val}")
                problems.append(f"step {s['step_number']}: cutting word {axis}{val} not derived from the plan")
        per_segment.append(rec)
    return {
        "segments": len(segments),
        "segments_with_inputs": sum(1 for s in segments if s["inputs"] is not None),
        "lookups": lookups,
        "traced_to_plan": verified,
        "defaulted": lookups - verified,
        "cutting_words_checked": words,
        "unexplained_cutting_words": unexplained,
        "passed": not problems and len(segments) > 0,
        "problems": problems,
        "per_segment": per_segment,
    }

"""Engineered procedural planner (EPP), version 1.

A conventional planner over knowledge tables (build_tables.py), engineered
with the three capabilities the reviewers and the manuscript name as what a
naive lookup table lacks:

  * rule-identifier logging: every operation, tool, and parameter value
    records the identifier of the table row it came from;
  * multi-valued keys with conflict detection: all parameter rows matching a
    (material, operation) key are collected, and disagreeing rows halt the
    step as a rule conflict instead of the last-written row winning;
  * an is-a table with transitive closure: a feature-to-operation row
    written for a class applies to all of its descendants.

It reproduces every gate of KEFC (unresolved and low-confidence mappings,
missing knowledge, machine capability, tool orientation, serialisation
profile, tool tie without preference, rule conflict, machine safety limits)
with the same reason codes, so that its output can be compared with the
reasoner path decision by decision. It is written once, before the change
scenarios are applied; any later code change needed by a scenario is kept
in a separate extension module and counted.
"""
import re
from typing import Dict, List, Optional

LOW_CONFIDENCE_THRESHOLD = 0.5
VALUE_TOLERANCE = 1e-6
_AXIS = (re.compile(r"\b(?:along|parallel to)\s+(?:the\s+)?(?:negative\s+|positive\s+)?([XYZ])[\s-]*axis", re.I),
         re.compile(r"^\s*([XYZ])[\s-]*axis", re.I))


def feature_axis(orientation: Optional[str]) -> Optional[str]:
    if not orientation:
        return None
    for pat in _AXIS:
        m = pat.search(orientation)
        if m:
            return m.group(1).upper()
    return None


class ProceduralPlanner:
    def __init__(self, tables: Dict, serialisation_profile: str = "RALTurningProfile"):
        self.t = tables
        self.profile = serialisation_profile
        # Indexes built once from the rows.
        self.psets = {r["name"]: r for r in tables["psets"]}  # one row per name is assumed

    # --- knowledge access ---------------------------------------------------
    def ancestors(self, cls: str) -> List[str]:
        """cls and all its ancestors (transitive closure of the is-a table)."""
        seen, todo = [], [cls]
        while todo:
            c = todo.pop(0)
            if c in seen:
                continue
            seen.append(c)
            todo.extend(self.t["classes"].get(c, []))
        return seen

    def operations_for(self, cls: str) -> List[Dict]:
        closure = set(self.ancestors(cls))
        ops: Dict[str, Dict] = {}
        for row in self.t["feature_rules"]:  # file order, first matching row is logged
            if row["class"] in closure and row["operation"] not in ops:
                ops[row["operation"]] = {"operation": row["operation"], "rule_id": row["id"]}
        return list(ops.values())

    def parameter_rows(self, cls: str, operation: str, material: str) -> List[Dict]:
        return [r for r in self.t["param_rules"]
                if r["operation"] == operation and r["material"] in (material, "*")]

    # --- planning -----------------------------------------------------------
    def plan(self, entities: List[Dict], material_key: str = "steel_1045",
             machine_key: str = "cnc_lathe") -> Dict:
        material = self.t["materials"][material_key]
        machine = self.t["machines"][machine_key]
        requests: List[Dict] = []

        def request(fid, ftype, code, op=None, detail=""):
            key = (fid, op, code)
            if not any((r["feature_id"], r["operation"], r["reason_code"]) == key for r in requests):
                requests.append({"feature_id": fid, "feature_type": ftype, "operation": op,
                                 "reason_code": code, "detail": detail})

        specs = []
        for e in entities:
            label = e["type"].lower().replace(" ", "_").replace("-", "_")
            cls = self.t["labels"].get(label)
            conf = min(1.0 if cls else 0.0, e.get("match_confidence", 1.0))
            if cls is None:
                request(e["id"], e["type"], "unresolved_mapping", detail=f"no class for label {label!r}")
                continue
            low = conf < LOW_CONFIDENCE_THRESHOLD
            if low:
                request(e["id"], e["type"], "low_confidence_mapping")
            ops = self.operations_for(cls)
            if not ops:
                request(e["id"], e["type"], "missing_knowledge", detail="no operation row")
                continue
            for op in ops:
                specs.append((e, cls, low, op))
        specs.sort(key=lambda s: (self.t["operations"].get(s[3]["operation"], {}).get("precedence") or 999,
                                  s[0]["id"]))

        steps = []
        for n, (e, cls, low, op) in enumerate(specs, start=1):
            name = op["operation"]
            opk = self.t["operations"].get(name, {})
            exc = []
            if name not in machine["supports_operation"]:
                exc.append("machine_incompatible")
            orient = None
            if opk.get("requires_tool_along_axis"):
                ax = feature_axis(e.get("orientation"))
                if machine.get("spindle_axis") is None or not machine["tool_orientations"] or ax is None:
                    orient = "missing_knowledge"
                else:
                    need = "AxialToolOrientation" if ax == machine["spindle_axis"].upper() else "RadialToolOrientation"
                    if need not in machine["tool_orientations"]:
                        orient = "orientation_incompatible"
                    elif "machine_incompatible" not in exc:
                        prof = self.t["profiles"].get(self.profile)
                        if prof is None:
                            exc.append("missing_knowledge")
                        elif need not in prof:
                            exc.append("serialisation_unsupported")
            if orient:
                exc.append(orient)

            cands = sorted(tk for tk, tv in self.t["tools"].items() if name in tv["recommended_for"])
            tool, tool_rule = None, None
            if not cands:
                exc.append("missing_knowledge")
            elif len(cands) == 1:
                tool, tool_rule = cands[0], "tools[recommended_for]"
            elif opk.get("preferred_tool") in cands:
                tool, tool_rule = opk["preferred_tool"], f"operations[{name}].preferred_tool"
            else:
                tool = cands[0]
                exc.append("missing_knowledge")

            rows = self.parameter_rows(cls, name, material)
            params, prule = {}, None
            sets = [self.psets[r["pset"]] for r in rows if r["pset"] in self.psets]
            if len(sets) > 1 and any(abs((a[k] or 0) - (b[k] or 0)) > VALUE_TOLERANCE
                                     for a in sets for b in sets
                                     for k in ("feed_rate", "spindle_speed", "depth_of_cut")):
                exc.append("rule_conflict")
            elif not sets:
                exc.append("missing_knowledge")
            else:
                p, prule = sets[0], rows[0]["id"]
                params = {k: p[k] for k in ("feed_rate", "spindle_speed", "depth_of_cut", "coolant")}
                lim = machine["limits"]
                if any(params[k] is not None and lim.get(k) is not None and params[k] > lim[k]
                       for k in ("feed_rate", "spindle_speed", "depth_of_cut")):
                    exc.append("unsafe_value")
            if low:
                exc.append("low_confidence_mapping")
            for code in exc:
                request(e["id"], e["type"], code, op=name)
            steps.append({"step_number": n, "feature_id": e["id"], "operation": name, "tool": tool,
                          "parameters": params, "status": "requires_review" if exc else "auto_approved",
                          "exceptions": exc,
                          "provenance": {"operation": op["rule_id"], "tool": tool_rule, "parameters": prule}})
        return {"halted": False, "steps": steps, "requests": requests}

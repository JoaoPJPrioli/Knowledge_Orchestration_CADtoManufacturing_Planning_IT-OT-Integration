"""Code extensions of the engineered procedural planner that change
scenarios turned out to require. Each extension is a subclass written after
the scenario showed that version 1 could not meet the intent without new
code; its size is counted by count_code_lines() and reported.
"""
import ast
import inspect

from r1_1_change_study.procedural_planner import ProceduralPlanner, VALUE_TOLERANCE


class SpecificityPlanner(ProceduralPlanner):
    """Scenario S5: parameter rows may name a feature class; among the rows
    that apply to a feature, only those written for its most specific class
    are used (most-specific-wins override), then conflicts are checked."""

    def parameter_rows(self, cls, operation, material):
        chain = self.ancestors(cls)
        rows = [r for r in self.t["param_rules"]
                if r["operation"] == operation and r["material"] in (material, "*")
                and r.get("class", "Feature") in chain + ["Feature"]]
        if not rows:
            return rows

        def depth(r):
            c = r.get("class", "Feature")
            return chain.index(c) if c in chain else len(chain)
        best = min(depth(r) for r in rows)
        return [r for r in rows if depth(r) == best]


class UniquenessPlanner(ProceduralPlanner):
    """Scenario S10: integrity check that each parameter set is recorded once;
    a duplicated record with different values halts planning, as the
    reasoner does for a functional property with two values."""

    def plan(self, entities, material_key="steel_1045", machine_key="cnc_lathe"):
        seen = {}
        for row in self.t["psets"]:
            prev = seen.get(row["name"])
            if prev is not None and any(abs((prev[k] or 0) - (row[k] or 0)) > VALUE_TOLERANCE
                                        for k in ("feed_rate", "spindle_speed", "depth_of_cut")):
                return {"halted": True, "error": f"parameter set {row['name']!r} recorded twice with different values",
                        "steps": [], "requests": []}
            seen[row["name"]] = row
        return super().plan(entities, material_key, machine_key)


class DisjointnessPlanner(ProceduralPlanner):
    """Scenario S12: integrity check over the is-a table; an entity whose
    class has two ancestors declared disjoint halts planning, as the reasoner
    does when an individual instantiates two disjoint classes."""

    def plan(self, entities, material_key="steel_1045", machine_key="cnc_lathe"):
        pairs = {frozenset(p) for p in self.t.get("disjoint", [])}
        for e in entities:
            cls = self.t["labels"].get(e["type"].lower().replace(" ", "_").replace("-", "_"))
            closure = set(self.ancestors(cls)) if cls else set()
            clash = sorted(sorted(p) for p in pairs if p <= closure)
            if clash:
                return {"halted": True, "error": f"entity {e['id']} ({cls}) instantiates disjoint classes {clash[0]}",
                        "steps": [], "requests": []}
        return super().plan(entities, material_key, machine_key)


def count_code_lines(cls) -> int:
    """Executable source lines of a class body: excludes blank lines,
    comments, and docstrings."""
    src = inspect.getsource(cls)
    tree = ast.parse(src)
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and ast.get_docstring(node):
            d = node.body[0]
            doc_lines.update(range(d.lineno, d.end_lineno + 1))
    n = 0
    for i, line in enumerate(src.splitlines(), start=1):
        s = line.strip()
        if s and not s.startswith("#") and i not in doc_lines:
            n += 1
    return n

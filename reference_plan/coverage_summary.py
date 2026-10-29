"""Coverage of the reference process plan by the reference run (manuscript Table 7, lower block).

Reads reference_plan/comparison.json (written by expertplan_analysis.py) and the serialised steps
of runs/reference (ral_refusals.json), and prints how many of the required reference operations
are covered by an approved step of the right family, how many of those are reached by a
serialised segment, which are present only among the withheld steps, and which are missing.

Usage (from the repository root):
    python reference_plan/coverage_summary.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
comp = json.load(open(os.path.join(ROOT, "reference_plan", "comparison.json"), encoding="utf-8"))
ral = json.load(open(os.path.join(ROOT, "runs", "reference", "ral_refusals.json"), encoding="utf-8"))


def serialised_steps(r):
    """Serialised step numbers, as recorded by the application layer's accounting."""
    for key in ("serialised_steps", "serialized_steps"):
        if key in r:
            return set(r[key])
        acc = r.get("accounting") or r.get("ral_accounting") or {}
        if key in acc:
            return set(acc[key])
    raise SystemExit("ral_refusals.json has no serialised-step list; see runs/run_ledger.json (reference/serialised_steps)")


ser = serialised_steps(ral)
required = [op for op in comp["coverage"] if op["required"] is True]   # 10.02 is conditional
covered = [op for op in required if op["approved_steps"]]
reached = [op for op in covered if set(op["approved_steps"]) & ser]
print(f"required reference operations: {len(required)}")
print(f"covered by an approved step of the right family: {len(covered)}")
print(f"  of which reached by a serialised segment: {len(reached)}  {[op['op_id'] for op in reached]}")
print(f"  of which with a tool the lathe cannot drive: {comp['summary']['covered_with_tool_issue']}")
print(f"present only among the withheld steps: {comp['summary']['required_present_withheld_only']}")
print(f"missing: {comp['summary']['required_missing']}")

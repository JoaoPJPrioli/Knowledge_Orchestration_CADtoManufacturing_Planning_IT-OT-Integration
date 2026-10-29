"""Audit of placeholder dimensions in the serialiser (defect D16).

Regenerates a run's programme from its handed-to-RAL steps with
GCodeGenerator._extract_dimension_value instrumented, and counts how many
dimension lookups found a plan value and how many fell back to the method's
default (10.0 mm). The plan carries extractor keys ('Ø', 'R', 'L', 'W');
the toolpath patterns look up 'diameter', 'length', 'depth', ... so the
lookups default. Grooving no longer uses this method (it reads the plan or
refuses).

Applies to serialisers before Revision 6 only. From Revision 6 the toolpath
patterns read the plan's keys through GCodeGenerator.serialisation_inputs,
_extract_dimension_value has no default, and main.py writes
dimension_fidelity.json for every run (analysis/summarize_runs_v6.py).

Usage: python analysis/serialiser_default_audit.py RUN_DIR
"""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

from gcode_generator import GCodeGenerator  # noqa: E402


def _steps_handed_to_ral(run_dir):
    plan = json.load(open(os.path.join(run_dir, 'manufacturing_plan.json'), encoding='utf-8'))
    log = open(os.path.join(run_dir, 'run.log'), encoding='utf-8').read()
    if 'ABLATION kefc_gate' in log:
        return [s for s in plan
                if not GCodeGenerator.missing_serialisation_inputs(s['operation'], s.get('feature_dimensions') or {})]
    return [s for s in plan if s['validation_status'] in ('auto_approved', 'expert_approved')]


def audit_run(run_dir):
    with open(os.path.join(run_dir, 'run.log'), encoding='utf-8') as fh:
        log = fh.read()
    material = 'aluminum_6061' if '--material' in log and 'aluminum_6061' in log else 'steel_1045'
    g = GCodeGenerator(material)
    current = {'op': None}
    records = []
    original_lookup = g._extract_dimension_value
    original_op = g._generate_operation_gcode

    def lookup(dimensions, keys, default=10.0):
        found = any(k in dimensions for k in keys)
        value = original_lookup(dimensions, keys, default)
        records.append({'operation': current['op'], 'keys': list(keys), 'from_plan': found, 'value': value})
        return value

    def op(program, operation):
        current['op'] = operation['operation']
        return original_op(program, operation)

    g._extract_dimension_value = lookup
    g._generate_operation_gcode = op
    g.generate_program(_steps_handed_to_ral(run_dir))
    by_op = defaultdict(Counter)
    for r in records:
        by_op[r['operation']]['from_plan' if r['from_plan'] else 'defaulted'] += 1
    return {'summary': {'lookups': len(records), 'from_plan': sum(r['from_plan'] for r in records),
                        'defaulted_to_10mm': sum(not r['from_plan'] for r in records),
                        'by_operation': {k: dict(v) for k, v in sorted(by_op.items())}},
            'records': records}


if __name__ == '__main__':
    print(json.dumps(audit_run(sys.argv[1])['summary'], indent=1))

"""Revision 4 run ledger.

Every key of summarize_runs_v3.extend_v3() plus, per run:
  wear_flags_by_tool              {tool_id: [step numbers]} of the post-simulation
                                  wear flags (summary.json critical_simulation_findings)
  requests_by_code                (already present) expert-validation requests by reason code
  average/max cutting force and power (already present, repeated here for completeness)
  parameter_records_sparql        Q52 count and the asserted 4 x planned steps
  envelope_excursions             count and steps of coordinates outside the travel
                                  envelope, emitted unclamped (envelope_excursions.json)
  validator_errors / validator_violations_by_category
  cycle_time_breakdown            rapid/cutting/tool-change/positioning seconds, timed
                                  feed length and cycle depth, untimed feed moves

Usage (repository root):
    python analysis/summarize_runs_v4.py RUNS_DIR OUT_JSON [PYTEST_LOG]
"""
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from summarize_runs_v3 import extend_v3, RUN_ORDER  # noqa: E402


def _load(run_dir, name):
    with open(os.path.join(run_dir, name), encoding='utf-8') as fh:
        return json.load(fh)


def extend_v4(run_dir, timing):
    entry = extend_v3(run_dir, timing)
    summary = _load(run_dir, 'summary.json')
    flags = {}
    for f in summary.get('critical_simulation_findings') or []:
        flags.setdefault(f.get('tool_id'), []).append(f.get('step_number'))
    entry['wear_flags_by_tool'] = {k: sorted(v) for k, v in sorted(flags.items())}
    sq = _load(run_dir, 'sparql_results.json')
    entry['parameter_records_sparql'] = {
        'q52_records_with_rule_and_source': sq.get('parameter_records_with_rule_and_source'),
        'expected_4_x_planned_steps': sq.get('parameter_records_expected'),
    }
    exc = _load(run_dir, 'envelope_excursions.json')
    entry['envelope_excursions'] = {
        'count': exc['count'],
        'steps': sorted({e['step_number'] for e in exc['excursions']}),
        'details': [{'step_number': e['step_number'], 'x': e['x'], 'z': e['z'],
                     'excursion_mm': e['excursion_mm']} for e in exc['excursions']],
    }
    val = _load(run_dir, 'motor_shaft_1001_validation.json')
    entry['validator_errors'] = val['summary']['errors']
    entry['validator_warnings'] = val['summary']['warnings']
    entry['validator_violations_by_category'] = dict(Counter(v['category'] for v in val['violations']))
    sim = _load(run_dir, 'motor_shaft_1001_simulation.json')
    entry['cycle_time_breakdown'] = {k: v for k, v in sim['cutting_time'].items()
                                     if k != 'total_cycle_time_minutes'}
    return entry


def main(runs_dir, out_json, pytest_log=None):
    timing = _load(runs_dir, 'timing.json')
    ledger = {}
    for name in RUN_ORDER:
        d = os.path.join(runs_dir, name)
        if os.path.isdir(d):
            ledger[name] = extend_v4(d, timing)
    if pytest_log and os.path.exists(pytest_log):
        text = open(pytest_log, encoding='utf-8').read()
        m = re.search(r'(\d+) passed(?:, (\d+) failed)? in ([\d.]+)s', text)
        ledger['_tests'] = {'passed': int(m.group(1)) if m else None,
                            'failed': int(m.group(2)) if m and m.group(2) else 0,
                            'pytest_reported_s': float(m.group(3)) if m else None}
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump(ledger, fh, indent=1, ensure_ascii=False)
    return ledger


if __name__ == '__main__':
    main(*sys.argv[1:4])

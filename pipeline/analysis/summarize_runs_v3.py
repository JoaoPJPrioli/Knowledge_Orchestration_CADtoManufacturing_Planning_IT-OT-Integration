"""Revision 3 run ledger.

Every key of summarize_runs_v2.extend() (which itself carries every key of
summarize_runs.summarize()), plus:
  parameter_fidelity  segments checked and spindle/feed/coolant matches
                      (from the run's parameter_fidelity.json, written by
                      main.py's assertion);
  sparql              {'passed', 'total'} of the full fixed-order suite
                      (from the run's sparql_results.json).

Usage (repository root):
    python analysis/summarize_runs_v3.py RUNS_DIR OUT_JSON [PYTEST_LOG]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from summarize_runs_v2 import extend  # noqa: E402

RUN_ORDER = ['reference', 'ablation_type_gate', 'ablation_orientation_gate', 'ablation_kefc_gate',
             'ablation_swap_sources', 'material_aluminum', 'machine_mill_turn',
             'machine_mill_turn_ablation_serialisation_profile']


def extend_v3(run_dir, timing):
    entry = extend(run_dir, timing)
    fid = json.load(open(os.path.join(run_dir, 'parameter_fidelity.json'), encoding='utf-8'))
    entry['parameter_fidelity'] = {k: fid[k] for k in (
        'segments_checked', 'spindle_match', 'feed_match', 'coolant_match')}
    sq = json.load(open(os.path.join(run_dir, 'sparql_results.json'), encoding='utf-8'))
    entry['sparql'] = {'passed': sq['passed'], 'total': sq['total']}
    entry['sparql_failed_indices'] = [q['index'] for q in sq['queries'] if q['status'] != 'passed']
    return entry


def main(runs_dir, out_json, pytest_log=None):
    timing = json.load(open(os.path.join(runs_dir, 'timing.json'), encoding='utf-8'))
    ledger = {}
    for name in RUN_ORDER:
        d = os.path.join(runs_dir, name)
        if os.path.isdir(d):
            ledger[name] = extend_v3(d, timing)
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

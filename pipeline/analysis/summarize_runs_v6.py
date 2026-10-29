"""Revision 6 run ledger: every key of summarize_runs_v5.extend_v5() except
the instrumented default audit (serialiser_default_audit.py applies only to
pre-Revision-6 serialisers, which had a 10 mm default), plus
dimension_fidelity (from the run's dimension_fidelity.json, written by
main.py's dimension-fidelity assertion). serialiser_default_dimension_lookups
is kept for continuity with the v5 ledger and is now read from the same file.

Usage (repository root):
    python analysis/summarize_runs_v6.py RUNS_DIR OUT_JSON [PYTEST_LOG]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from summarize_runs_v4 import extend_v4, RUN_ORDER, _load  # noqa: E402


def extend_v6(run_dir, timing):
    entry = extend_v4(run_dir, timing)
    path = os.path.join(run_dir, 'ral_refused_steps.json')
    entry['ral_refused_steps'] = _load(run_dir, 'ral_refused_steps.json') if os.path.exists(path) else []
    dpath = os.path.join(run_dir, 'dimension_fidelity.json')
    if os.path.exists(dpath):
        d = _load(run_dir, 'dimension_fidelity.json')
        entry['dimension_fidelity'] = {k: d[k] for k in ('segments', 'segments_with_inputs', 'lookups',
                                                         'traced_to_plan', 'defaulted', 'cutting_words_checked',
                                                         'unexplained_cutting_words', 'passed')}
        by_op = {}
        for seg in d['per_segment']:
            o = by_op.setdefault(seg['operation'], {'segments': 0, 'lookups': 0, 'sources': {}})
            o['segments'] += 1
            for name, item in seg['inputs'].items():
                o['lookups'] += 1
                o['sources'].setdefault(name, sorted(set()))
                if item['source'] not in o['sources'][name]:
                    o['sources'][name] = sorted(o['sources'][name] + [item['source']])
        entry['dimension_fidelity']['by_operation'] = by_op
        entry['serialiser_default_dimension_lookups'] = {
            'lookups': d['lookups'], 'defaulted': d['defaulted'], 'source': 'dimension_fidelity.json'}
    else:
        entry['dimension_fidelity'] = None
        entry['serialiser_default_dimension_lookups'] = None
    return entry


def main(runs_dir, out_json, pytest_log=None):
    timing = _load(runs_dir, 'timing.json')
    ledger = {}
    for name in RUN_ORDER:
        d = os.path.join(runs_dir, name)
        if os.path.isdir(d):
            ledger[name] = extend_v6(d, timing)
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

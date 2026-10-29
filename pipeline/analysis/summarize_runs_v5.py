"""Revision 5 run ledger: every key of summarize_runs_v4.extend_v4() plus
ral_refused_steps (steps RAL's input contract refused under the kefc_gate
ablation; empty elsewhere) and serialiser_default_dimension_lookups (from
analysis/serialiser_default_audit.py).

Usage (repository root):
    python analysis/summarize_runs_v5.py RUNS_DIR OUT_JSON [PYTEST_LOG]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from summarize_runs_v4 import extend_v4, RUN_ORDER, _load  # noqa: E402
from serialiser_default_audit import audit_run  # noqa: E402


def extend_v5(run_dir, timing):
    entry = extend_v4(run_dir, timing)
    path = os.path.join(run_dir, 'ral_refused_steps.json')
    entry['ral_refused_steps'] = _load(run_dir, 'ral_refused_steps.json') if os.path.exists(path) else []
    entry['serialiser_default_dimension_lookups'] = audit_run(run_dir)['summary']
    return entry


def main(runs_dir, out_json, pytest_log=None):
    timing = _load(runs_dir, 'timing.json')
    ledger = {}
    for name in RUN_ORDER:
        d = os.path.join(runs_dir, name)
        if os.path.isdir(d):
            ledger[name] = extend_v5(d, timing)
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

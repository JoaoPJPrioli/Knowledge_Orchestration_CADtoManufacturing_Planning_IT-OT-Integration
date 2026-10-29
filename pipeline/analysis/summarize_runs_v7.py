"""Revision 7 run ledger: every key of summarize_runs_v6.extend_v6() plus the
KEFC / RAL split. KEFC decides on planning knowledge only; RAL refuses
handed steps whose toolpath inputs the plan does not carry and records each
refusal as serialisation_input_missing (ral_refusals.json).

New keys: kefc_approved, kefc_withheld_steps, handed_to_ral, serialised_steps,
serialised_segments, ral_refused (count, steps, by_operation, by_kind,
records), ral_accounting, kefc_gate_sets (kefc_gate ablation only).

Usage (repository root):
    python analysis/summarize_runs_v7.py RUNS_DIR OUT_JSON [PYTEST_LOG]
"""
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from summarize_runs_v4 import RUN_ORDER, _load  # noqa: E402
from summarize_runs_v6 import extend_v6  # noqa: E402


def extend_v7(run_dir, timing):
    entry = extend_v6(run_dir, timing)
    entry.pop('ral_refused_steps', None)  # superseded by ral_refused
    plan = _load(run_dir, 'manufacturing_plan.json')
    entry['kefc_approved'] = sum(1 for s in plan if s['validation_status'] == 'auto_approved')
    entry['kefc_withheld_steps'] = [s['step_number'] for s in plan if s['validation_status'] != 'auto_approved']
    entry['handed_to_ral'] = sum(1 for s in plan if s.get('ral_status') in ('serialised', 'refused'))
    entry['serialised_steps'] = [s['step_number'] for s in plan if s.get('ral_status') == 'serialised']
    rr = _load(run_dir, 'ral_refusals.json')
    refusals = rr['refusals']
    entry['ral_accounting'] = rr['accounting']
    entry['serialised_segments'] = rr['accounting']['serialised']
    entry['ral_refused'] = {
        'count': len(refusals),
        'steps': [r['step_number'] for r in refusals],
        'by_operation': dict(sorted(Counter(r['operation'] for r in refusals).items())),
        'by_kind': dict(sorted(Counter(r['kind'] for r in refusals).items())),
        'records': [{'step_number': r['step_number'], 'operation': r['operation'],
                     'feature_id': r['source_entity']['feature_id'],
                     'feature_type': r['source_entity']['feature_type'],
                     'feature_dimensions': r['source_entity']['feature_dimensions'],
                     'missing_inputs': r['missing_inputs'], 'kefc_validation_status': r['kefc_validation_status'],
                     'request_id': r.get('request_id')} for r in refusals],
    }
    sets_path = os.path.join(run_dir, 'ablation_kefc_gate_sets.json')
    entry['kefc_gate_sets'] = _load(run_dir, 'ablation_kefc_gate_sets.json') if os.path.exists(sets_path) else None
    return entry


def main(runs_dir, out_json, pytest_log=None):
    timing = _load(runs_dir, 'timing.json')
    ledger = {}
    for name in RUN_ORDER:
        d = os.path.join(runs_dir, name)
        if os.path.isdir(d):
            ledger[name] = extend_v7(d, timing)
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

"""Revision 2 run ledger.

Extends analysis/summarize_runs.py (whose per-run keys are reused unchanged)
with the corrected force/power channels, wall-clock and Pellet timings, the
test-suite result, and the aluminium and mill-turn runs.

Usage (from the repository root):
    python analysis/summarize_runs_v2.py RUNS_DIR OUT_JSON [PYTEST_LOG]

RUNS_DIR contains one sub-directory per run (reference, ablation_type_gate,
ablation_orientation_gate, ablation_kefc_gate, ablation_swap_sources,
material_aluminum, machine_mill_turn), each produced by one invocation of
main.py --output-dir <dir> from an empty directory (hence a cleared
expert-validation store), with the console log saved as run.log, plus
RUNS_DIR/timing.json with the wall-clock time of each invocation.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

from summarize_runs import summarize  # noqa: E402

RUN_ORDER = ['reference', 'ablation_type_gate', 'ablation_orientation_gate', 'ablation_kefc_gate',
             'ablation_swap_sources', 'material_aluminum', 'machine_mill_turn']


def extend(run_dir, timing):
    entry = summarize(run_dir, os.path.join(run_dir, 'run.log'))
    sim = json.load(open(os.path.join(run_dir, 'motor_shaft_1001_simulation.json'), encoding='utf-8'))
    chip = sim['chip_load_analysis']
    model = chip.get('force_power_model', {})
    entry['average_cutting_force_N'] = round(chip['average_cutting_force'], 2)
    entry['average_cutting_power_kW'] = round(chip['average_cutting_power'], 4)
    entry['max_cutting_force_N'] = round(model.get('max_cutting_force', 0.0), 2)
    entry['max_cutting_power_kW'] = round(model.get('max_cutting_power', 0.0), 4)
    entry['force_power_moves_analysed'] = chip['operations_analyzed']
    entry['force_power_moves_with_force'] = model.get('moves_with_force')
    entry['force_power_kc_N_per_mm2'] = model.get('specific_cutting_force_kc_N_per_mm2')
    entry['force_power_inputs_source'] = model.get('inputs_source')
    entry['average_mrr_mm3_per_min'] = round(chip['average_mrr'], 2)
    log = open(os.path.join(run_dir, 'run.log'), encoding='utf-8').read()
    entry['pellet_reasoning_s'] = [round(float(x), 2) for x in re.findall(r'Pellet took ([\d.]+)', log)]
    t = timing.get(os.path.basename(run_dir.rstrip('/\\')), {})
    entry['wall_clock_s'] = t.get('wall_clock_s')
    entry['cli_args'] = t.get('args')
    reasoning = json.load(open(os.path.join(run_dir, 'reasoning_report.json'), encoding='utf-8'))
    entry['ontologies_loaded'] = reasoning.get('ontologies') if isinstance(reasoning, dict) else None
    return entry


def main(runs_dir, out_json, pytest_log=None):
    timing = json.load(open(os.path.join(runs_dir, 'timing.json'), encoding='utf-8'))
    ledger = {}
    for name in RUN_ORDER:
        d = os.path.join(runs_dir, name)
        if os.path.isdir(d):
            ledger[name] = extend(d, timing)
    if pytest_log and os.path.exists(pytest_log):
        text = open(pytest_log, encoding='utf-8').read()
        m = re.search(r'(\d+) passed(?:, (\d+) failed)? in ([\d.]+)s', text)
        ledger['_tests'] = {
            'passed': int(m.group(1)) if m else None,
            'failed': int(m.group(2)) if m and m.group(2) else 0,
            'pytest_reported_s': float(m.group(3)) if m else None,
        }
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump(ledger, fh, indent=1, ensure_ascii=False)
    return ledger


if __name__ == '__main__':
    main(*sys.argv[1:4])

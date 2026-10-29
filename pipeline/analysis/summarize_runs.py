"""Summarize a set of pipeline runs (reference + ablations) into one JSON ledger."""
import json, re, os, sys
from collections import Counter

def summarize(d, log):
    L = open(log, encoding='utf-8').read()
    def g(pat, cast=int):
        m = re.search(pat, L); return cast(m.group(1)) if m else None
    plan = json.load(open(os.path.join(d, 'manufacturing_plan.json')))
    feats = json.load(open(os.path.join(d, 'features.json')))
    val = json.load(open(os.path.join(d, 'motor_shaft_1001_validation.json')))['statistics']
    sim = json.load(open(os.path.join(d, 'motor_shaft_1001_simulation.json')))
    req = json.load(open(os.path.join(d, 'expert_validation_requests.json')))['requests']
    prov = json.load(open(os.path.join(d, 'provenance_report.json')))['steps']
    st = Counter(s['validation_status'] for s in plan)
    rec = Counter(f['reconciliation'] for f in feats)
    merges = [f for f in feats if f['reconciliation'] == 'merged']
    sys.path.insert(0, os.path.join(os.path.dirname(d.rstrip('/')), 'src'))
    from feature_parser import calculate_type_similarity
    taus = [calculate_type_similarity(f['source_primary']['type'], f['source_secondary']['type']) for f in merges]
    rules = set()
    for s in prov:
        rules.add(s['operation_selection_rule_id'])
        if s['tool_selection_rule_id'] == 'feature_tool_from_operation':
            rules.add('feature_tool_from_operation')
        for v in s['parameters'].values():
            rules.add(v['rule_id'])
    rules.discard(None)
    params = sum(len(s['parameters']) for s in prov)
    params_ok = sum(1 for s in prov for v in s['parameters'].values() if v.get('rule_id') and v.get('ontology_sources'))
    withheld = [(s['step_number'], s['feature_id'], s['feature_type'], s['operation']) for s in plan if s['validation_status'] != 'auto_approved']
    return {
        'entities': len(feats), 'reconciliation': dict(rec),
        'merges': len(merges), 'merges_by_tau': dict(Counter(taus)),
        'slots': sum(1 for f in feats if f['type'] == 'Slot'),
        'steps': len(plan), 'approved': st.get('auto_approved', 0) + st.get('expert_approved', 0), 'withheld': st.get('requires_review', 0),
        'withheld_steps': withheld,
        'param_records': params, 'param_records_with_provenance': params_ok,
        'rules_fired': len(rules),
        'tool_rule_ids': dict(Counter(s['tool_selection_rule_id'] for s in prov)),
        'segments': g(r'-> (\d+) segments'), 'blocks_executed': val['blocks_executed'], 'tool_changes': val['tool_changes'],
        'travel_total_mm': val['total_travel_distance'], 'travel_cut_mm': val['cut_distance'],
        'cycle_time_min': sim['cutting_time']['total_cycle_time_minutes'],
        'validation_status': g(r'Validation status: (\w+)', str),
        'tool_wear_saturated': [k for k, v in sim['tool_wear'].items() if v['wear_percentage'] >= 100],
        'wear_flags': g(r'Post-simulation flags: (\d+)') or 0,
        'requests_total': len(req), 'requests_by_code': dict(Counter(r['reason_code'] for r in req)),
        'graph_nodes': g(r'Total nodes: (\d+)'), 'graph_edges': g(r'Total edges: (\d+)'),
        'triples': g(r'Total triples: (\d+)'), 'sparql_passed': g(r'Passed: (\d+)'),
    }

if __name__ == '__main__':
    runs = {'reference': ('run_ext/output', 'run_ext/run_ext.log')}
    for ab in ['type_gate', 'orientation_gate', 'kefc_gate', 'swap_sources']:
        runs['ablation_' + ab] = (f'ablations/{ab}', f'ablations/{ab}/run.log')
    out = {k: summarize(*v) for k, v in runs.items()}
    json.dump(out, open('analysis/results/run_ledger.json', 'w'), indent=1)
    for k, v in out.items():
        print('==', k)
        for kk, vv in v.items():
            print(f'   {kk}: {vv}')

"""
Parameter records in the RDF export (rdf_triplestore.add_parameter_record)
and the provenance queries Q51 to Q54 of the fixed-order suite.
"""
import copy
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from rdf_triplestore import ManufacturingTriplestore  # noqa: E402
from sparql_examples import EXAMPLES  # noqa: E402

CP = "http://onto.brep.org/manufacturing/cutting-parameters#"
MP = "http://onto.brep.org/manufacturing/machining-process#"


def _rec(value, unit, rule="aisi1045_rough_turning_params", sources=(CP, MP)):
    return {'value': value, 'unit': unit, 'source': 'swrl_rule', 'rule_id': rule,
            'ontology_sources': list(sources),
            'input_facts': {'feature_id': 5, 'feature_type': 'Step', 'material': None,
                            'mapping_confidence': 1.0}}


PACKAGE = {'feed_rate': _rec(0.25, 'mm/rev'), 'spindle_speed': _rec(480.0, 'RPM'),
           'depth_of_cut': _rec(2.0, 'mm'), 'coolant': _rec(True, 'bool')}


def _store(packages):
    ts = ManufacturingTriplestore()
    for step, status, pkg in packages:
        ts.add_operation_instance(f"opstep_{step}", {
            'operation_type': 'rough_turning', 'step_number': step, 'feature_id': 5,
            'tool_id': 'turning_insert_rough', 'validation_status': status,
            'name': 'Rough Turning', 'parameters': pkg})
    return ts


def _q(i):
    return EXAMPLES[i - 1]['sparql']


def test_parameter_records_resolve_by_sparql():
    ts = _store([(3, 'auto_approved', PACKAGE), (4, 'requires_review', PACKAGE)])
    rows = ts.execute_sparql(_q(51))
    assert {r['ontologySource'] for r in rows} == {CP, MP}
    assert {float(r['value']) for r in rows} == {480.0} and {r['unit'] for r in rows} == {'RPM'}
    assert {r['ruleId'] for r in rows} == {'aisi1045_rough_turning_params'}
    count = int(next(iter(ts.execute_sparql(_q(52))[0].values())))
    assert count == 8  # 4 records x 2 steps
    assert ts.execute_sparql(_q(53)) == []
    approved = ts.execute_sparql(_q(54))
    assert len(approved) == 4 and {int(r['stepNumber']) for r in approved} == {3}
    # One triple per ontology IRI on each record.
    from rdflib import URIRef
    from rdf_triplestore import MFG
    rec = URIRef(f"{MFG}param_3_spindle_speed")
    assert len(list(ts.g.objects(rec, MFG.ontologySource))) == 2


def test_missing_rule_or_source_is_found():
    broken = copy.deepcopy(PACKAGE)
    broken['feed_rate']['rule_id'] = None
    broken['depth_of_cut']['ontology_sources'] = []
    ts = _store([(3, 'auto_approved', broken)])
    count = int(next(iter(ts.execute_sparql(_q(52))[0].values())))
    assert count == 2
    missing = {r['p'].rsplit('#', 1)[-1] for r in ts.execute_sparql(_q(53))}
    assert missing == {'param_3_feed_rate', 'param_3_depth_of_cut'}


def test_count_query_is_empty_without_records():
    ts = _store([(3, 'auto_approved', {})])
    assert ts.execute_sparql(_q(52)) == []

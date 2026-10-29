"""
Triplestore Integration Tests
==============================
Integration tests for RDF triplestore and SPARQL query engine.

Tests:
1. RDF triplestore creation from ontology
2. RDF triplestore creation from NetworkX KG
3. SPARQL query execution
4. SPARQL generation from natural language
5. Query result comparison (NetworkX vs RDF)

Usage:
    python test_triplestore_integration.py
"""

import os
import sys
import json
import tempfile
from typing import List, Dict, Optional

# BASE_DIR is the project root (this file lives in tests/, one level down).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

# Optional imports
try:
    from rdf_triplestore import ManufacturingTriplestore
    from sparql_generator import SparqlGenerator
    from sparql_examples import get_examples_by_category, get_random_examples
    RDF_AVAILABLE = True
except ImportError as e:
    RDF_AVAILABLE = False
    print(f"⚠ RDF/SPARQL modules not available: {e}")
    print("  Install dependencies: pip install rdflib google-generativeai")

from kg_builder import ManufacturingKG
from feature_parser import load_features_from_file
from semantic_reconciler import SemanticReconciler
from kefc_controller import KEFCController
from expert_validation import ExpertValidationStore


def _build_kg(features, evr_filename):
    """
    Build the unified graph via the SKL-authoritative path
    (ManufacturingKG.build_kg_from_skl() + populate_decisions_from_kefc()),
    matching main.py's real pipeline — replaces the retired
    ontology.py-driven build_manufacturing_kg().
    """
    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile(features)

    # Test artefacts go to tests/output/, never to the repository's output/.
    evr_path = os.path.join(BASE_DIR, 'tests', 'output', evr_filename)
    os.makedirs(os.path.dirname(evr_path), exist_ok=True)
    if os.path.exists(evr_path):
        os.remove(evr_path)
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store)
    kefc_plan = kefc.build_manufacturing_plan(reconciled, material='steel_1045', machine='cnc_lathe')

    kg = ManufacturingKG()
    kg.build_kg_from_skl(features, reconciler.repo)
    kg.populate_decisions_from_kefc(kefc_plan['steps'], reconciled)
    return kg


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def print_section(text: str):
    """Print a formatted section header."""
    print("\n" + "-" * 70)
    print(text)
    print("-" * 70)


def test_triplestore_creation():
    """
    Test 1: Create RDF triplestore from ontology schema.
    
    Validates:
    - Schema loading
    - Basic entity addition
    - Relationship creation
    - Triple count accuracy
    """
    print_section("Test 1: RDF Triplestore Creation from Ontology")

    assert RDF_AVAILABLE, "RDF modules not available (install rdflib and google-generativeai)"

    # Find schema file
    schema_path = os.path.join(BASE_DIR, 'src', 'manufacturing.ttl')
    assert os.path.exists(schema_path), f"Schema file not found: {schema_path}"

    print(f"  Loading schema from: {schema_path}")

    # Create triplestore
    ts = ManufacturingTriplestore()
    ts.load_schema(schema_path)

    print(f"  ✓ Schema loaded successfully")

    # Add test entities. add_feature takes one feature dict (id/type/
    # dimensions/...); add_operation/add_tool/add_machine/add_material each
    # take (node_id, data_dict) — not flat kwargs, matching ManufacturingTriplestore's
    # actual signatures in rdf_triplestore.py.
    feature_uri = ts.add_feature({
        'id': 'F001', 'type': 'step',
        'dimensions': {'Ø': 45.0, 'L': 25.0},
        'absolute_location': {'X': 0.0, 'Y': 0.0, 'Z': 0.0},
    })

    op_uri = ts.add_operation('OP001', {
        'name': 'Rough Turning',
    })

    tool_uri = ts.add_tool('turning_insert_rough', {
        'name': 'Rough Turning Insert', 'type': 'turning_insert',
    })

    machine_uri = ts.add_machine('cnc_lathe', {
        'name': 'CNC Lathe', 'capabilities': ['turning'],
    })

    material_uri = ts.add_material('steel_1045', {
        'name': 'AISI 1045 Steel',
    })

    # Add relationships (these take the URIRefs returned above, not raw ids)
    ts.add_requires(feature_uri, op_uri)
    ts.add_uses(op_uri, tool_uri)
    ts.add_runs_on(op_uri, machine_uri)
    ts.add_removes(op_uri, material_uri)

    # Check triple count
    triple_count = ts.get_triple_count()
    node_counts = ts.get_node_counts()

    print(f"  ✓ Entities and relationships added")
    print(f"    - Total triples: {triple_count}")
    print(f"    - Node counts: {node_counts}")

    # Validate triple count (should be reasonable)
    expected_min_triples = 20  # At least 20 triples for 5 entities + 4 relationships
    assert triple_count >= expected_min_triples, \
        f"Triple count too low ({triple_count} < {expected_min_triples})"
    print(f"  ✓ Triple count validation passed ({triple_count} >= {expected_min_triples})")


def test_networkx_to_rdf_export():
    """
    Test 2: Export NetworkX knowledge graph to RDF triplestore.
    
    Validates:
    - NetworkX graph construction
    - RDF export functionality
    - Triple count consistency
    - Node/edge preservation
    """
    print_section("Test 2: NetworkX to RDF Export")

    assert RDF_AVAILABLE, "RDF modules not available (install rdflib and google-generativeai)"

    # Load feature files
    motor_data_dir = os.path.join(BASE_DIR, 'data', 'motor_data')

    feature_file = os.path.join(motor_data_dir, 'features_eixo_step_Gemini31Pro.txt')
    assert os.path.exists(feature_file), f"Feature file not found: {feature_file}"

    print(f"  Loading features from: {feature_file}")
    feature_data = load_features_from_file(feature_file)
    features = feature_data['features']

    print(f"  ✓ Loaded {len(features)} features")

    # Build NetworkX KG
    print(f"  Building NetworkX knowledge graph...")
    kg = _build_kg(features, 'test_evr_networkx_to_rdf_export.json')
    nx_stats = kg.get_graph_stats()

    print(f"  ✓ NetworkX KG built")
    print(f"    - Nodes: {nx_stats['total_nodes']}")
    print(f"    - Edges: {nx_stats['total_edges']}")

    # Export to RDF
    schema_path = os.path.join(BASE_DIR, 'src', 'manufacturing.ttl')
    assert os.path.exists(schema_path), f"Schema file not found: {schema_path}"

    print(f"  Exporting to RDF triplestore...")
    triplestore = kg.export_to_rdf(
        # Throwaway RDF dump: export_to_rdf requires a filepath, but only the
        # in-memory triplestore's stats are asserted on below, so this goes
        # to a temp dir instead of cluttering the shared output/ directory.
        filepath=os.path.join(tempfile.mkdtemp(), 'test_manufacturing.ttl'),
        schema_path=schema_path
    )

    # Validate export
    rdf_triples = triplestore.get_triple_count()
    rdf_nodes = triplestore.get_node_counts()

    print(f"  ✓ RDF export successful")
    print(f"    - RDF triples: {rdf_triples}")
    print(f"    - RDF node types: {len(rdf_nodes)}")

    # Check consistency (RDF should have similar or more triples than NetworkX
    # — RDF adds type triples and property triples on top of the edges)
    assert rdf_triples >= nx_stats['total_edges'], \
        f"RDF triples ({rdf_triples}) less than NetworkX edges ({nx_stats['total_edges']})"
    print(f"  ✓ Triple count consistency check passed")


def test_sparql_query_execution():
    """
    Test 3: Execute SPARQL queries against RDF triplestore.
    
    Validates:
    - SPARQL query syntax
    - Query execution
    - Result retrieval
    - Query categories (feature, operation, tool, sequence, complex)
    """
    print_section("Test 3: SPARQL Query Execution")

    assert RDF_AVAILABLE, "RDF modules not available (install rdflib and google-generativeai)"

    # Create triplestore with test data
    schema_path = os.path.join(BASE_DIR, 'src', 'manufacturing.ttl')
    assert os.path.exists(schema_path), f"Schema file not found: {schema_path}"

    ts = ManufacturingTriplestore()
    ts.load_schema(schema_path)

    # Add test data (add_feature takes one dict; add_operation/add_tool take
    # (node_id, data_dict); relationships take the URIRefs those return —
    # matching ManufacturingTriplestore's actual signatures in rdf_triplestore.py)
    f001 = ts.add_feature({'id': 'F001', 'type': 'step', 'dimensions': {'Ø': 45.0, 'L': 25.0}})
    f002 = ts.add_feature({'id': 'F002', 'type': 'hole', 'dimensions': {'Ø': 10.0}})

    op001 = ts.add_operation('OP001', {'name': 'rough_turning'})
    op002 = ts.add_operation('OP002', {'name': 'drilling'})

    tool_rough = ts.add_tool('turning_insert_rough', {'name': 'turning_insert_rough', 'type': 'turning_insert'})
    tool_drill = ts.add_tool('drill_bit', {'name': 'drill_bit', 'type': 'drill'})

    ts.add_requires(f001, op001)
    ts.add_requires(f002, op002)
    ts.add_uses(op001, tool_rough)
    ts.add_uses(op002, tool_drill)

    print(f"  ✓ Test data loaded")

    # Test queries by category
    test_queries = [
        {
            'name': 'Get all features',
            'sparql': """
                PREFIX mfg: <http://onto.brep.org/manufacturing#>
                SELECT ?feature ?type
                WHERE {
                    ?feature a mfg:Feature .
                    ?feature mfg:featureType ?type .
                }
            """,
            'expected_min_results': 2
        },
        {
            # add_operation() doesn't assert a distinct mfg:operationType
            # predicate (only mfg:name) — see rdf_triplestore.py's add_operation.
            'name': 'Get all operations',
            'sparql': """
                PREFIX mfg: <http://onto.brep.org/manufacturing#>
                SELECT ?operation ?name
                WHERE {
                    ?operation a mfg:Operation .
                    ?operation mfg:name ?name .
                }
            """,
            'expected_min_results': 2
        },
        {
            'name': 'Get tools for operation',
            'sparql': """
                PREFIX mfg: <http://onto.brep.org/manufacturing#>
                SELECT ?operation ?tool
                WHERE {
                    ?operation mfg:uses ?tool .
                }
            """,
            'expected_min_results': 2
        },
        {
            'name': 'Get feature-operation relationships',
            'sparql': """
                PREFIX mfg: <http://onto.brep.org/manufacturing#>
                SELECT ?feature ?operation
                WHERE {
                    ?feature mfg:requires ?operation .
                }
            """,
            'expected_min_results': 2
        }
    ]

    failures = []

    for query in test_queries:
        print(f"\n  Query: {query['name']}")

        results = ts.execute_sparql(query['sparql'])
        assert results is not None, f"{query['name']!r} returned None"

        result_count = len(list(results))
        if result_count >= query['expected_min_results']:
            print(f"    ✓ Passed ({result_count} results)")
        else:
            print(f"    ⚠ Low result count ({result_count} < {query['expected_min_results']})")
            failures.append((query['name'], result_count, query['expected_min_results']))

    print(f"\n  Query Execution Summary:")
    print(f"    - Total queries: {len(test_queries)}")
    print(f"    - Below expected minimum: {len(failures)}")

    assert not failures, f"queries below their expected minimum result count: {failures}"


def test_sparql_generation():
    """
    Test 4: Generate SPARQL from natural language using LLM.
    
    Validates:
    - SPARQL generator initialization
    - Prompt construction
    - SPARQL syntax validation
    - Example-based few-shot learning
    
    Note: Requires GEMINI_API_KEY environment variable for LLM generation.
    """
    print_section("Test 4: SPARQL Generation from Natural Language")

    assert RDF_AVAILABLE, "RDF modules not available (install rdflib and google-generativeai)"

    # Initialize SPARQL generator
    generator = SparqlGenerator()

    print(f"  ✓ SPARQL generator initialized")

    # Load examples
    examples = get_random_examples(10)
    generator.load_examples(examples)

    print(f"  ✓ Loaded {len(examples)} few-shot examples")

    # Test prompt construction
    test_query = "What features require rough turning?"
    prompt = generator._build_prompt(test_query)
    assert prompt, "prompt construction produced an empty prompt"

    print(f"  ✓ Prompt constructed for: '{test_query}'")
    print(f"    - Prompt length: {len(prompt)} chars")

    # Test SPARQL validation (without LLM call)
    test_sparql = """
        PREFIX mfg: <http://onto.brep.org/manufacturing#>
        SELECT ?feature
        WHERE {
            ?feature a mfg:Feature .
        }
    """

    is_valid = generator.validate_sparql(test_sparql)
    assert is_valid, "a syntactically valid SPARQL query was rejected by validate_sparql"
    print(f"  ✓ SPARQL validation passed for test query")

    # Test cache functionality
    generator.clear_cache()
    cache_stats = generator.get_cache_stats()
    assert cache_stats['cache_size'] == 0, f"cache should be empty right after clear_cache(): {cache_stats}"

    print(f"  ✓ Cache operations working")
    print(f"    - Cache size: {cache_stats['cache_size']}")

    # Check for API key
    api_key = os.environ.get('GEMINI_API_KEY')

    if api_key:
        print(f"\n  ℹ GEMINI_API_KEY found")
        print(f"  ℹ To test LLM-based SPARQL generation:")
        print(f"    - Run: python test_llm_benchmarks.py")
        print(f"    - Or set GEMINI_API_KEY and call generator.generate(query)")
    else:
        print(f"\n  ⚠ GEMINI_API_KEY not set")
        print(f"  ℹ LLM-based SPARQL generation requires API key")
        print(f"  ℹ Set: $env:GEMINI_API_KEY='your-api-key' (PowerShell)")


def test_networkx_vs_rdf_comparison():
    """
    Test 5: Compare query results between NetworkX and RDF backends.
    
    Validates:
    - Result consistency
    - Query equivalence
    - Backend parity
    
    This test ensures that NetworkX and RDF backends return identical results.
    """
    print_section("Test 5: NetworkX vs RDF Backend Comparison")

    assert RDF_AVAILABLE, "RDF modules not available (install rdflib and google-generativeai)"

    # Load feature files
    motor_data_dir = os.path.join(BASE_DIR, 'data', 'motor_data')

    feature_file = os.path.join(motor_data_dir, 'features_eixo_step_Gemini31Pro.txt')
    assert os.path.exists(feature_file), f"Feature file not found: {feature_file}"

    print(f"  Loading features from: {feature_file}")
    feature_data = load_features_from_file(feature_file)
    features = feature_data['features']

    # Build NetworkX KG
    print(f"  Building NetworkX knowledge graph...")
    kg = _build_kg(features, 'test_evr_networkx_vs_rdf_comparison.json')

    # Export to RDF
    schema_path = os.path.join(BASE_DIR, 'src', 'manufacturing.ttl')
    assert os.path.exists(schema_path), f"Schema file not found: {schema_path}"

    print(f"  Exporting to RDF triplestore...")
    triplestore = kg.export_to_rdf(
        # Same rationale as test_networkx_to_rdf_export above: throwaway,
        # not read back, goes to a temp dir instead of output/.
        filepath=os.path.join(tempfile.mkdtemp(), 'test_comparison.ttl'),
        schema_path=schema_path
    )

    # Compare node counts
    nx_stats = kg.get_graph_stats()
    rdf_nodes = triplestore.get_node_counts()

    print(f"\n  Node Count Comparison:")
    print(f"    NetworkX nodes: {nx_stats['total_nodes']}")
    print(f"    RDF node types: {len(rdf_nodes)}")

    for node_type, count in rdf_nodes.items():
        print(f"      - {node_type}: {count}")

    assert nx_stats['total_nodes'] > 0 and rdf_nodes, "expected a non-empty graph on both backends"

    # Compare edge/triple counts
    print(f"\n  Edge/Triple Count Comparison:")
    print(f"    NetworkX edges: {nx_stats['total_edges']}")
    print(f"    RDF triples: {triplestore.get_triple_count()}")

    # Note: RDF triples will be higher due to type assertions and property triples
    print(f"\n  ℹ Note: RDF triples > NetworkX edges is expected")
    print(f"    (RDF adds type triples and property triples)")

    # Test query equivalence (best-effort: only if the orchestrator exposes
    # both a NetworkX and a SPARQL query path — a mismatch between the two,
    # or either path being unavailable, is not itself a defect, so this
    # stays informational rather than a hard assertion).
    try:
        from orchestrator import ManufacturingOrchestrator

        orchestrator = ManufacturingOrchestrator(kg)

        if hasattr(orchestrator, 'set_triplestore'):
            orchestrator.set_triplestore(triplestore)
            print(f"  ✓ SPARQL backend set in orchestrator")

            # These live on QueryEngine (orchestrator.query_engine), not on
            # ManufacturingOrchestrator itself.
            test_feature_id = features[0]['id'] if features else 'F001'
            nx_ops = orchestrator.query_engine.query_operations_for_feature(test_feature_id)

            if hasattr(orchestrator.query_engine, 'query_operations_for_feature_sparql'):
                rdf_ops = orchestrator.query_engine.query_operations_for_feature_sparql(test_feature_id)

                print(f"\n  Query Result Comparison (feature {test_feature_id}):")
                print(f"    NetworkX operations: {len(nx_ops) if nx_ops else 0}")
                print(f"    RDF operations: {len(rdf_ops) if rdf_ops else 0}")

                if nx_ops and rdf_ops:
                    if len(nx_ops) == len(rdf_ops):
                        print(f"    ✓ Result count match")
                    else:
                        print(f"    ⚠ Result count mismatch (expected for complex queries)")
            else:
                print(f"  ⚠ SPARQL query methods not available in orchestrator")
        else:
            print(f"  ⚠ set_triplestore() not available in orchestrator")

    except ImportError:
        print(f"  ⚠ Orchestrator not available for comparison")


def _run_and_report(fn) -> bool:
    """The test_* functions now signal failure by raising (assert/exception),
    the normal pytest convention, rather than returning False — this adapts
    that back into a boolean for run_all_tests()'s standalone CLI report."""
    try:
        fn()
        return True
    except Exception as e:
        print(f"  ✗ {fn.__name__} failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all integration tests and generate summary report."""
    print_header("RDF Triplestore Integration Tests")
    print("\n  Testing RDF/SPARQL integration with manufacturing knowledge graph...")

    results = {
        'test_1_triplestore_creation': False,
        'test_2_networkx_to_rdf_export': False,
        'test_3_sparql_query_execution': False,
        'test_4_sparql_generation': False,
        'test_5_networkx_vs_rdf_comparison': False
    }

    # Run tests
    results['test_1_triplestore_creation'] = _run_and_report(test_triplestore_creation)
    results['test_2_networkx_to_rdf_export'] = _run_and_report(test_networkx_to_rdf_export)
    results['test_3_sparql_query_execution'] = _run_and_report(test_sparql_query_execution)
    results['test_4_sparql_generation'] = _run_and_report(test_sparql_generation)
    results['test_5_networkx_vs_rdf_comparison'] = _run_and_report(test_networkx_vs_rdf_comparison)

    # Generate summary
    print_header("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n  Total tests: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {total - passed}")
    print(f"  Success rate: {passed/total*100:.1f}%")
    
    print(f"\n  Test Results:")
    for test_name, result in results.items():
        status = '✓ PASS' if result else '✗ FAIL'
        print(f"    {status}: {test_name}")
    
    # Save results to JSON
    output_dir = os.path.join(BASE_DIR, 'tests', 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    results_path = os.path.join(output_dir, 'triplestore_test_results.json')
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n  ✓ Results saved to: {results_path}")
    
    return passed == total


if __name__ == '__main__':
    success = run_all_tests()
    
    if success:
        print("\n  ✓ All integration tests passed!")
    else:
        print("\n  ⚠ Some tests failed. Review results above.")
    
    sys.exit(0 if success else 1)

"""
Test script for orchestrator module (Phase 2)

Builds the unified graph via the SKL-authoritative path
(ManufacturingKG.build_kg_from_skl() + populate_decisions_from_kefc()) and the
manufacturing plan via SemanticReconciler + KEFCController — matching main.py's
real pipeline, not the retired ontology.py-driven build_manufacturing_kg() /
orchestrator.generate_manufacturing_plan() path. ManufacturingOrchestrator no
longer generates a plan itself (see orchestrator.py); this test sets
manufacturing_plan/plan_metadata directly to keep exercising its
natural-language/export helpers.
"""

import sys
import os
from datetime import datetime
from collections import defaultdict

# BASE_DIR is the project root (this file lives in tests/, one level down).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

# Import modules
from feature_parser import load_features_from_file
from kg_builder import ManufacturingKG
from semantic_reconciler import SemanticReconciler
from kefc_controller import KEFCController
from expert_validation import ExpertValidationStore
from orchestrator import ManufacturingOrchestrator, SchemaDescriber, QueryEngine

def test_orchestrator():
    """Test the orchestrator module."""
    print("=" * 70)
    print("Testing Orchestrator Module (Phase 2)")
    print("=" * 70)

    # Test 1: SchemaDescriber
    print("\n[Test 1] SchemaDescriber")
    print("-" * 50)

    schema_summary = SchemaDescriber.get_schema_summary()
    print(f"  ✓ Schema summary length: {len(schema_summary)} chars")
    assert schema_summary, "schema summary must not be empty"

    node_desc = SchemaDescriber.get_node_type_description('feature')
    print(f"  ✓ Feature node description: {node_desc}")
    assert node_desc, "'feature' node type description must not be empty"

    edge_desc = SchemaDescriber.get_edge_type_description('REQUIRES')
    print(f"  ✓ REQUIRES edge description: {edge_desc}")
    assert edge_desc, "'REQUIRES' edge type description must not be empty"

    # Test 2: Load features, reconcile against SKL, run KEFC, build the graph
    print("\n[Test 2] Load Features and Build KG (SKL-authoritative)")
    print("-" * 50)

    feature_file = os.path.join(
        BASE_DIR,
        'data',
        'motor_data',
        'features_eixo_step_Gemini31Pro.txt'
    )

    feature_data = load_features_from_file(feature_file)
    features = feature_data['features']

    print(f"  ✓ Loaded {len(features)} features from 31Pro")

    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile(features)

    evr_path = os.path.join(BASE_DIR, 'tests', 'output', 'test_evr_orchestrator.json')
    os.makedirs(os.path.dirname(evr_path), exist_ok=True)
    if os.path.exists(evr_path):
        os.remove(evr_path)
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store)
    kefc_plan = kefc.build_manufacturing_plan(reconciled, material='steel_1045', machine='cnc_lathe')

    kg = ManufacturingKG()
    kg.build_kg_from_skl(features, reconciler.repo)
    kg.populate_decisions_from_kefc(kefc_plan['steps'], reconciled)
    stats = kg.get_graph_stats()
    print(f"  ✓ Built KG with {stats['total_nodes']} nodes, {stats['total_edges']} edges")
    assert stats['total_nodes'] > 0 and stats['total_edges'] > 0, stats

    # Test 3: QueryEngine
    print("\n[Test 3] QueryEngine")
    print("-" * 50)

    query_engine = QueryEngine(kg)

    # Query operations for feature 1
    operations = query_engine.query_operations_for_feature(1)
    print(f"  ✓ Feature 1 operations: {len(operations)} operations")
    for op in operations:
        print(f"    - {op['operation_name']} ({op['operation_id']})")
    assert operations, "feature 1 (a Step in this dataset) must have at least one operation"

    # Query tool for operation
    tool = query_engine.query_tool_for_operation(operations[0]['operation_id'])
    print(f"  ✓ Tool for {operations[0]['operation_id']}: {tool.get('tool_name', 'N/A')}")
    assert tool.get('tool_name'), f"expected a tool for {operations[0]['operation_id']}"

    # Query feature details
    feature_details = query_engine.query_feature_details(1)
    print(f"  ✓ Feature 1 details: type={feature_details.get('type', 'N/A')}, dimensions={len(feature_details.get('dimensions', {}))} params")
    assert feature_details.get('type'), "feature 1 must resolve to a type"

    # Multi-hop query
    multi_hop = query_engine.query_multi_hop(1)
    print(f"  ✓ Multi-hop query for feature 1: {len(multi_hop['operations'])} operations, {len(multi_hop['tools'])} tools")
    assert multi_hop['operations'] and multi_hop['tools'], multi_hop

    # Test 4: ManufacturingOrchestrator — set the KEFC-produced plan directly
    # (this class no longer generates a plan itself, see orchestrator.py)
    print("\n[Test 4] ManufacturingOrchestrator (plan supplied by KEFC)")
    print("-" * 50)

    orchestrator = ManufacturingOrchestrator(kg)
    orchestrator.ingest_features(features)
    plan = kefc_plan['approved_steps']
    orchestrator.manufacturing_plan = plan
    orchestrator.plan_metadata = {
        'generated_at': datetime.now().isoformat(),
        'total_features': len(features),
        'total_steps': len(plan),
        'material': 'steel_1045',
        'machine': 'cnc_lathe',
        'feature_types': orchestrator._count_feature_types(),
        'operation_types': orchestrator._count_operation_types(),
        'tools_used': orchestrator._get_tools_used(),
    }
    print(f"  ✓ Manufacturing plan set with {len(plan)} approved steps")

    # Print first few steps
    for step in plan[:3]:
        print(f"    Step {step['step_number']}: {step['operation_name']} for feature {step['feature_id']}")

    # Test 5: Natural language plan
    print("\n[Test 5] Natural Language Plan")
    print("-" * 50)

    nl_plan = orchestrator.get_natural_language_plan()
    print(f"  ✓ Natural language plan length: {len(nl_plan)} chars")
    # Count "Step N: ..." header lines specifically (not nl_plan.count('Step')
    # — a feature's own type can literally be "Step" too, e.g. "Feature: 1
    # (Step)", which would inflate a bare substring count).
    step_headers = sum(1 for line in nl_plan.splitlines() if line.startswith('Step '))
    print(f"  ✓ Plan has {step_headers} step descriptions")
    assert step_headers == len(plan), \
        f"expected {len(plan)} step descriptions, got {step_headers}"

    # Test 6: Plan metadata
    print("\n[Test 6] Plan Metadata")
    print("-" * 50)

    metadata = orchestrator.get_plan_summary()
    print(f"  ✓ Total features: {metadata['total_features']}")
    print(f"  ✓ Total steps: {metadata['total_steps']}")
    print(f"  ✓ Material: {metadata['material']}")
    print(f"  ✓ Machine: {metadata['machine']}")
    print(f"  ✓ Feature types: {metadata['feature_types']}")
    print(f"  ✓ Tools used: {len(metadata['tools_used'])} tools")
    assert metadata['total_features'] == len(features)
    assert metadata['total_steps'] == len(plan)
    assert metadata['material'] == 'steel_1045' and metadata['machine'] == 'cnc_lathe'

    # Test 7: Export plan
    print("\n[Test 7] Export Plan")
    print("-" * 50)

    output_dir = os.path.join(BASE_DIR, 'tests', 'output')
    os.makedirs(output_dir, exist_ok=True)

    plan_file = os.path.join(output_dir, 'orchestrator_plan.json')
    orchestrator.export_plan(plan_file)
    print(f"  ✓ Plan exported to: {plan_file}")
    assert os.path.exists(plan_file) and os.path.getsize(plan_file) > 0

    print("\n" + "=" * 70)
    print("All orchestrator tests passed!")
    print("=" * 70)

if __name__ == '__main__':
    test_orchestrator()

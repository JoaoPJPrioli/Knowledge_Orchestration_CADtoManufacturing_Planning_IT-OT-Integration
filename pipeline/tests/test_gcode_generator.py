"""
Test script for G-code generator module (Phase 2)

Builds the manufacturing plan via the SKL/KEFC production path
(SemanticReconciler -> KEFCController), matching the real main.py pipeline —
not the retired ontology.py-driven kg_builder.build_manufacturing_kg() /
orchestrator.generate_manufacturing_plan() path.
"""

import sys
import os
import json

# BASE_DIR is the project root (this file lives in tests/, one level down).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

# Import modules
from feature_parser import load_features_from_file
from semantic_reconciler import SemanticReconciler
from kefc_controller import KEFCController
from expert_validation import ExpertValidationStore
from gcode_generator import GCodeGenerator, GCodeProgram

def test_gcode_generator():
    """Test the G-code generator module."""
    print("=" * 70)
    print("Testing G-code Generator Module (Phase 2)")
    print("=" * 70)

    # Load features and build a manufacturing plan via SKL/KEFC
    print("\n[Setup] Loading features and building manufacturing plan...")
    print("-" * 50)

    feature_file = os.path.join(
        BASE_DIR,
        'data',
        'motor_data',
        'features_eixo_step_Gemini31Pro.txt'
    )

    feature_data = load_features_from_file(feature_file)
    features = feature_data['features']
    print(f"  ✓ Loaded {len(features)} features")

    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile(features)
    print(f"  ✓ Reconciled against SKL ontology individuals")

    evr_path = os.path.join(BASE_DIR, 'tests', 'output', 'test_evr_gcode_generator.json')
    os.makedirs(os.path.dirname(evr_path), exist_ok=True)
    if os.path.exists(evr_path):
        os.remove(evr_path)
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store)
    kefc_plan = kefc.build_manufacturing_plan(reconciled, material='steel_1045', machine='cnc_lathe')
    plan = kefc_plan['approved_steps']
    print(f"  ✓ Generated {len(kefc_plan['steps'])} manufacturing steps "
          f"({len(plan)} approved for RAL)")

    # Test 1: GCodeProgram basics
    print("\n[Test 1] GCodeProgram Basics")
    print("-" * 50)

    program = GCodeProgram(1001)
    program.add_header_line("(Test Program)")
    program.add_block("G21 (Metric units)")
    program.add_block("G00 X0 Y0 Z0")
    program.add_footer_line("M02 (Program end)")

    program_text = program.get_program_text()
    print(f"  ✓ Program text length: {len(program_text)} chars")
    print(f"  ✓ Program has O1001: {'O1001' in program_text}")
    print(f"  ✓ Program has M02: {'M02' in program_text}")

    # Test 2: GCodeGenerator initialization
    print("\n[Test 2] GCodeGenerator Initialization")
    print("-" * 50)

    generator = GCodeGenerator('steel_1045', 'cnc_lathe')
    print(f"  ✓ Generator created with material: {generator.material}")
    print(f"  ✓ Generator created with machine: {generator.machine}")
    print(f"  ✓ Approach clearance: {generator.APPROACH_CLEARANCE_MM} mm")

    # Test 3: Generate complete G-code program
    print("\n[Test 3] Generate Complete G-code Program")
    print("-" * 50)

    program = generator.generate_program(plan)
    program_text = program.get_program_text()

    print(f"  ✓ Generated program with {len(program.blocks)} blocks")
    print(f"  ✓ Program text length: {len(program_text)} chars")

    # Check for key G-code elements
    checks = {
        'G21 (Metric)': 'G21' in program_text,
        'G18 (ZX plane, turning profile)': 'G18' in program_text and 'G17' not in program_text,
        'G97/G99 (rev/min, feed per rev)': 'G97' in program_text and 'G99' in program_text,
        'G90 (Absolute)': 'G90' in program_text,
        'M03 (Spindle on)': 'M03' in program_text,
        'M05 (Spindle off)': 'M05' in program_text,
        'M08 (Coolant on)': 'M08' in program_text,
        'M09 (Coolant off)': 'M09' in program_text,
        'M06 (Tool change)': 'M06' in program_text,
        'G00 (Rapid)': 'G00' in program_text,
        'G01 (Linear)': 'G01' in program_text,
        'M02 (Program end)': 'M02' in program_text,
    }

    for check, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check}: {result}")
    missing = [check for check, result in checks.items() if not result]
    assert not missing, f"generated G-code is missing expected elements: {missing}"

    # Test 4: Print first 50 lines of G-code
    print("\n[Test 4] First 50 Lines of Generated G-code")
    print("-" * 50)

    lines = program_text.split('\n')
    for i, line in enumerate(lines[:50], 1):
        print(f"  {i:3d}: {line}")

    if len(lines) > 50:
        print(f"  ... ({len(lines) - 50} more lines)")

    # Test 5: Save G-code to file
    print("\n[Test 5] Save G-code to File")
    print("-" * 50)

    # Test artefacts never go to the repository's output/ directory: the
    # reference run's programme must not be overwritten by a test fixture.
    output_dir = os.path.join(BASE_DIR, 'tests', 'output')
    os.makedirs(output_dir, exist_ok=True)

    saved_files = generator.export_programs(plan, output_dir)
    assert saved_files, "export_programs produced no files"

    for saved_file in saved_files:
        print(f"  ✓ Saved G-code to: {saved_file}")

        # Read and display file size
        file_size = os.path.getsize(saved_file)
        print(f"  ✓ File size: {file_size} bytes")
        assert file_size > 0, f"{saved_file} was written empty"

    # Test 6: Tool change analysis
    print("\n[Test 6] Tool Change Analysis")
    print("-" * 50)

    tool_changes = program_text.count('M06')
    print(f"  ✓ Total tool changes (M06): {tool_changes}")

    # Count unique tools
    tools_used = set()
    for step in plan:
        tool_id = step.get('tool_id', 'unknown')
        tools_used.add(tool_id)

    print(f"  ✓ Unique tools in plan: {len(tools_used)}")
    print(f"  ✓ Tools: {', '.join(sorted(tools_used))}")

    # Test 7: Operation type analysis
    print("\n[Test 7] Operation Type Analysis")
    print("-" * 50)

    operation_counts = {}
    for step in plan:
        op = step.get('operation', 'unknown')
        operation_counts[op] = operation_counts.get(op, 0) + 1

    for op, count in sorted(operation_counts.items()):
        print(f"  ✓ {op}: {count} operations")

    print("\n" + "=" * 70)
    print("All G-code generator tests passed!")
    print("=" * 70)

if __name__ == '__main__':
    test_gcode_generator()

"""
CAD-to-G-code Orchestration Prototype
======================================
Main pipeline entry point that connects all modules:
1. Load feature files from data/motor_data
2. Parse and reconcile features using consensus voting
3. Build manufacturing knowledge graph
4. Query KG for operations and tools
5. Output manufacturing plan

Usage:
    python main.py
"""

import os
import sys
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# The console-status output below uses non-ASCII symbols (checkmarks, etc.).
# Windows' default console codepage (cp1252) cannot encode them, which crashes
# `python main.py` immediately on a fresh Windows shell (no PYTHONIOENCODING
# override needed to reproduce). Force UTF-8 on stdout/stderr so the pipeline
# runs out of the box; guarded because a captured/redirected stdout (e.g. in
# some CI runners) may not be a TextIOWrapper and won't have .reconfigure().
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

# Add src to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _repo_relative(path: str) -> str:
    """Path relative to the repository root, with '/' separators, for
    artefacts that must not embed a machine-specific absolute path."""
    return os.path.relpath(os.path.abspath(path), BASE_DIR).replace(os.sep, '/')
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

# Anchored to BASE_DIR (not a bare relative 'output') so pipeline artifacts
# always land in prototype_v2/output/ regardless of the shell's cwd — a bare
# 'output' string previously let a wrong-cwd run silently write to the repo
# root's output/ directory instead.
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# --- run configuration (set from the command line in __main__) --------------
# ABLATION in {None, 'type_gate', 'orientation_gate', 'kefc_gate', 'swap_sources',
#             'serialisation_profile'}:
#   type_gate        -> tau_min = 0 (additive similarity score alone, Eq. 3 ablated)
#   orientation_gate -> the machine declares every tool orientation achievable
#                       (flat operation-set capability model of the first submission)
#   kefc_gate        -> every planned step is passed to RAL regardless of its
#                       validation status (exception gate bypassed)
#   swap_sources     -> the secondary agent of each family becomes the primary
#   serialisation_profile -> KEFC's RAL serialisation-profile check is disabled
#                       (a machine-admitted radial step reaches the serialiser,
#                       reproducing finding F1 of Revision 2 on cnc_mill_turn)
ABLATION = None
# MATERIAL: material key of the case part ('steel_1045' reference; 'aluminum_6061'
# and 'stainless_304' exercise the material-specific parameter rules the
# reference run cannot fire).
MATERIAL = 'steel_1045'
# MACHINE: machine key of the run ('cnc_lathe' reference; 'cnc_mill_turn' loads
# knowledge/specialized/mill_turn_configuration.owl, a turning centre with
# driven tooling and the same envelope). Only the capability model differs;
# the gating code is the same for both.
MACHINE = 'cnc_lathe'

from feature_parser import (
    parse_feature_file,
    load_features_from_file,
    reconcile_features
)
from kg_builder import ManufacturingKG
from orchestrator import ManufacturingOrchestrator
from semantic_reconciler import SemanticReconciler
from skl_repository import export_unified_knowledge_base
from kefc_controller import KEFCController
from expert_validation import ExpertValidationStore
from gcode_generator import GCodeGenerator
from validator import GCodeValidator, validate_gcode_file
from visualizer import GCodeVisualizer, visualize_gcode
from simulator import CNCSimulator

# Optional RDF/SPARQL imports (require rdflib and google-generativeai)
try:
    from rdf_triplestore import ManufacturingTriplestore
    from sparql_generator import SparqlGenerator
    RDF_AVAILABLE = True
except ImportError:
    RDF_AVAILABLE = False
    print("  ⚠ Warning: RDF/SPARQL modules not available (install rdflib and google-generativeai)")


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


def _load_tagged_features(filepath: str) -> List[Dict]:
    """Load one feature file and tag each feature with KINM source
    provenance (source_file, source_id) before any reconciliation or global
    renumbering touches it."""
    if not os.path.exists(filepath):
        print(f"  ⚠ Warning: File not found: {filepath}")
        return []

    print(f"\n  Loading: {os.path.basename(filepath)}")
    feature_data = load_features_from_file(filepath)
    features = feature_data['features']
    print(f"    ✓ Found {len(features)} features")

    for feature in features:
        print(f"      - {feature['id']}: {feature['type']} "
              f"({feature.get('description', '')[:50]}...)")
        feature['source_file'] = os.path.basename(filepath)
        feature['source_id'] = feature['id']

    return features


def load_and_parse_features(
    step_files: List[str],
    drawing_files: List[str],
    primary_weight: float = 0.6,
    secondary_weight: float = 0.4
) -> List[Dict]:
    """
    Load feature files and reconcile using consensus voting (Eq. 2 in the
    manuscript — see feature_parser.reconcile_features).

    Each of `step_files` and `drawing_files` is expected to hold exactly two
    paths: two AI models' (Gemini 3.1 Pro primary, Gemini 3.5 Flash
    secondary) independent feature extractions from the *same* source (the
    STEP-file geometry, and the 2D drawing, respectively). Reconciliation
    runs separately within each pair — that is what "consensus voting
    between model outputs" means here: two models analyzing the same source
    and (dis)agreeing, not the STEP-derived and drawing-derived feature sets
    merged into each other.

    Scope note: this does NOT attempt cross-modal reconciliation (matching a
    STEP-derived "Step" against a drawing-derived "Cylinder" describing the
    same physical body) — feature_parser.py's type-similarity table includes
    equivalences that suggest that was at least partially intended, but
    verifying a cross-modal geometric match is correct requires checking it
    against the actual CAD drawing, which this pipeline has no way to do
    automatically. Reconciling within-pair only is a real, verifiable
    consensus step; claiming more would overclaim (see
    .codex/agents/research_alignment_reviewer.md).

    Returns:
        List of reconciled feature dictionaries with a globally unique 'id'
        and 'match_confidence'/'reconciliation' fields from consensus voting.
    """
    print_section("Loading Feature Files")

    step_primary = _load_tagged_features(step_files[0])
    step_secondary = _load_tagged_features(step_files[1])
    drawing_primary = _load_tagged_features(drawing_files[0])
    drawing_secondary = _load_tagged_features(drawing_files[1])
    if ABLATION == 'swap_sources':
        print("\n  !! ABLATION swap_sources: the secondary agent of each family is treated as primary")
        step_primary, step_secondary = step_secondary, step_primary
        drawing_primary, drawing_secondary = drawing_secondary, drawing_primary

    print_section("Reconciling Feature Sources (Consensus Voting)")

    reconciled_step = reconcile_features(step_primary, step_secondary, primary_weight, secondary_weight)
    print(f"\n  ✓ STEP-file sources: {len(step_primary)} + {len(step_secondary)} "
          f"raw -> {len(reconciled_step)} reconciled")
    merged_count = sum(1 for f in reconciled_step if f.get('reconciliation') == 'merged')
    print(f"    - {merged_count} merged, {len(reconciled_step) - merged_count} single-source")

    reconciled_drawing = reconcile_features(drawing_primary, drawing_secondary, primary_weight, secondary_weight)
    print(f"\n  ✓ Drawing sources: {len(drawing_primary)} + {len(drawing_secondary)} "
          f"raw -> {len(reconciled_drawing)} reconciled")
    merged_count = sum(1 for f in reconciled_drawing if f.get('reconciliation') == 'merged')
    print(f"    - {merged_count} merged, {len(reconciled_drawing) - merged_count} single-source")

    all_features = reconciled_step + reconciled_drawing

    for feature in all_features:
        # merge_features() (inside reconcile_features) builds a fresh dict
        # that doesn't carry the source_file/source_id tags through to the
        # top level — recover them from whichever side(s) contributed.
        primary_src = feature.get('source_primary', {})
        secondary_src = feature.get('source_secondary', {})
        if feature.get('reconciliation') == 'merged':
            feature['source_file'] = f"{primary_src.get('source_file')}+{secondary_src.get('source_file')}"
        else:
            feature['source_file'] = feature.get('source_file') or primary_src.get('source_file') \
                or secondary_src.get('source_file')

    # Assign a global, collision-free id across the two reconciled sets.
    # Without this, e.g. id=1 from the reconciled STEP set and id=1 from the
    # reconciled drawing set would both be named "feature_1" downstream —
    # kg_builder.py's NetworkX node id and skl_repository.py's OWL
    # individual name are both keyed on 'id', so a collision there silently
    # merges two distinct physical features into one graph node / ontology
    # individual with contradictory types.
    for global_id, feature in enumerate(all_features, start=1):
        feature['id'] = global_id

    print(f"\n  Total reconciled features: {len(all_features)}")

    return all_features


def generate_manufacturing_plan_with_kefc(
    features: List[Dict],
    material: str = 'steel_1045',
    machine: str = 'cnc_lathe',
    output_dir: str = OUTPUT_DIR
) -> Dict:
    """
    Generate the manufacturing plan via the KINM -> CFRM -> KEFC pipeline:
    CFRM (semantic_reconciler.py) maps each feature to an SKL ontology
    individual and runs Pellet once over the whole batch; KEFC
    (kefc_controller.py) turns the reasoned facts into a traceable process
    parameter package, routing anything it can't confidently decide to
    expert validation instead of falling back to a hidden default.

    This is the sole plan-generation path (see AGENTS.md / .codex/architecture.md)
    — the earlier ontology.py-backed orchestrator/build_kg() path was retired
    once ontology.py itself was removed; production never depended on it.

    Returns a dict with 'steps' (the manufacturing plan RAL consumes) plus
    'skl_version', 'reasoner', 'reasoning_status', and
    'expert_validation_summary' — the new top-level plan metadata.
    """
    print_section("Generating Manufacturing Plan with KEFC (SKL-grounded)")

    reconciler = SemanticReconciler(material_key=material, machine_key=machine)
    print(f"\n  Reconciling {len(features)} features against SKL ontology individuals...")
    reconciled = reconciler.reconcile(features)
    unmapped = sum(1 for rf in reconciled if rf.unmapped)
    low_conf = sum(1 for rf in reconciled if rf.low_confidence)
    print(f"  ✓ Reconciled ({unmapped} unmapped, {low_conf} low-confidence) — Pellet reasoning: "
          f"{reconciler.repo.reasoning_status}")

    # Self-contained, reasoner-compatible OWL artifact: TBox + SWRL rules +
    # this run's asserted feature individuals (no inferred facts baked in —
    # see export_unified_knowledge_base's docstring for why). Built from a
    # separate, never-reasoned-over repository so nothing inferred can leak in.
    kb_path = os.path.join(output_dir, "unified_knowledge_base.owl")
    export_unified_knowledge_base(reconciled, material, machine, kb_path)
    print(f"  ✓ Unified knowledge base (TBox + SWRL rules + asserted facts) exported to: {kb_path}")

    expert_store = ExpertValidationStore(os.path.join(output_dir, "expert_validation_requests.json"))
    kefc = KEFCController(reconciler.repo, expert_store, machine_key=machine)
    plan = kefc.build_manufacturing_plan(reconciled, material=material, machine=machine)

    print(f"\n  ✓ Generated {len(plan['steps'])} manufacturing steps")
    status_counts = {}
    for step in plan['steps']:
        status_counts[step['validation_status']] = status_counts.get(step['validation_status'], 0) + 1
    print(f"    - Validation status: {status_counts}")
    print(f"    - Expert validation requests: {plan['expert_validation_summary']['total_requests']}")

    print("\n  Manufacturing Plan Summary:")
    for step in plan['steps'][:5]:
        print(f"    Step {step['step_number']}: {step['operation_name']} "
              f"for feature {step['feature_id']} ({step['feature_type']}) "
              f"[{step['validation_status']}]")
    if len(plan['steps']) > 5:
        print(f"    ... ({len(plan['steps']) - 5} more steps)")

    # Internal handles for provenance/report export in main() — popped off
    # before the plan dict is used as/exported like a plain manufacturing plan.
    plan['_reconciler'] = reconciler
    plan['_expert_store'] = expert_store
    plan['_reconciled_features'] = reconciled
    return plan


def generate_gcode(
    manufacturing_plan: List[Dict],
    material: str = 'steel_1045',
    machine: str = 'cnc_lathe',
    output_dir: str = OUTPUT_DIR
) -> List[str]:
    """
    Generate G-code programs from the manufacturing plan.
    
    Args:
        manufacturing_plan: List of manufacturing steps
        material: Material identifier
        machine: Machine identifier
        output_dir: Directory to save G-code files
        
    Returns:
        List of saved G-code file paths
    """
    print_section("Generating G-code Programs")
    
    # Create G-code generator
    generator = GCodeGenerator(material, machine)
    
    # Generate G-code program
    print("\n  Generating G-code program...")
    program = generator.generate_program(manufacturing_plan)
    
    program_text = program.get_program_text()
    print(f"  ✓ Generated program with {len(program.blocks)} blocks")
    print(f"  ✓ Program text length: {len(program_text)} chars")
    
    # Export G-code files
    print("\n  Exporting G-code files...")
    saved_files = generator.export_programs(manufacturing_plan, output_dir)
    
    for saved_file in saved_files:
        file_size = os.path.getsize(saved_file)
        print(f"    ✓ Saved: {saved_file} ({file_size} bytes)")

    # Envelope excursions: the serialiser no longer clamps coordinates; any
    # computed coordinate outside the travel envelope is emitted as computed,
    # recorded here, and reported by the validator as a bounds violation.
    excursions = list(getattr(generator, 'envelope_excursions', []))
    with open(os.path.join(output_dir, 'envelope_excursions.json'), 'w', encoding='utf-8') as fh:
        json.dump({'count': len(excursions), 'excursions': excursions}, fh, indent=2, ensure_ascii=False)
    print(f"    - Envelope excursions emitted as computed (not clamped): {len(excursions)}"
          + (f" in steps {sorted({e['step_number'] for e in excursions}, key=str)}" if excursions else ""))
    
    # Print G-code statistics
    tool_changes = program_text.count('M06')
    print(f"\n  G-code Statistics:")
    print(f"    - Total tool changes (M06): {tool_changes}")
    print(f"    - Total G-code blocks: {len(program.blocks)}")

    refusals = list(generator.refusals)
    serialised = list(generator.serialised_steps)
    if refusals:
        print(f"  ⚠ RAL refused {len(refusals)} handed step(s) it would have to guess for: "
              + ", ".join(f"{r['step_number']} ({r['operation']})" for r in refusals))
    return saved_files, serialised, refusals


def validate_gcode(
    gcode_files: List[str],
    machine: str = 'cnc_lathe',
    output_dir: str = OUTPUT_DIR,
    machines_data: Optional[Dict[str, Dict]] = None
) -> List[Dict]:
    """
    Validate generated G-code files against machine limits.

    Args:
        gcode_files: List of G-code file paths
        machine: Machine identifier
        output_dir: Directory to save validation reports
        machines_data: {machine_id: machine_dict} — pass
            reconciler.repo.legacy_machines_dict() (see main())

    Returns:
        List of validation reports
    """
    print_section("Validating G-code Programs")

    reports = []

    for gcode_file in gcode_files:
        if not os.path.exists(gcode_file):
            print(f"  ⚠ Warning: File not found: {gcode_file}")
            continue

        print(f"\n  Validating: {os.path.basename(gcode_file)}")

        # Validate using convenience function
        report = validate_gcode_file(gcode_file, machine, machines_data=machines_data)
        
        # Print summary
        summary = report['summary']
        status_icon = '✓' if summary['status'] == 'PASS' else '✗'
        print(f"    {status_icon} Status: {summary['status']}")
        print(f"    - Total violations: {summary['total_violations']}")
        print(f"    - Errors: {summary['errors']}")
        print(f"    - Warnings: {summary['warnings']}")
        
        # Print statistics
        stats = report['statistics']
        print(f"    - Blocks executed: {stats['blocks_executed']}")
        print(f"    - Tool changes: {stats['tool_changes']}")
        print(f"    - Total travel: {stats['total_travel_distance']:.2f}mm")
        print(f"    - Cut distance: {stats['cut_distance']:.2f}mm")
        
        # Export validation report (repository-relative source path only)
        report['summary']['source'] = _repo_relative(report['summary'].get('source') or gcode_file)
        base_name = os.path.splitext(os.path.basename(gcode_file))[0]
        report_path = os.path.join(output_dir, f"{base_name}_validation.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"    ✓ Report saved: {report_path}")
        
        reports.append(report)
    
    # Overall summary
    total_errors = sum(r['summary']['errors'] for r in reports)
    total_warnings = sum(r['summary']['warnings'] for r in reports)
    
    print(f"\n  Validation Summary:")
    print(f"    - Files validated: {len(reports)}")
    print(f"    - Total errors: {total_errors}")
    print(f"    - Total warnings: {total_warnings}")
    
    if total_errors == 0:
        print(f"\n  ✓ All G-code files passed validation!")
    else:
        print(f"\n  ⚠ {total_errors} errors found. Review validation reports for details.")
    
    return reports


def visualize_gcode_files(
    gcode_files: List[str],
    output_dir: str = OUTPUT_DIR,
    color_by: str = 'operation'
) -> List[Dict[str, str]]:
    """
    Generate visualizations for generated G-code files.
    
    Args:
        gcode_files: List of G-code file paths
        output_dir: Directory to save visualization files
        color_by: Color scheme ('operation' or 'tool')
        
    Returns:
        List of dicts with paths to saved visualization files
    """
    print_section("Generating Toolpath Visualizations")
    
    visualization_results = []
    
    for gcode_file in gcode_files:
        if not os.path.exists(gcode_file):
            print(f"  ⚠ Warning: File not found: {gcode_file}")
            continue
        
        print(f"\n  Visualizing: {os.path.basename(gcode_file)}")
        
        # Generate visualizations
        result = visualize_gcode(
            gcode_file,
            output_dir=output_dir,
            color_by=color_by,
            show_2d=True,
            show_3d=True,
            save_format='png'
        )
        
        # Print results
        if '2d_path' in result:
            file_size = os.path.getsize(result['2d_path'])
            print(f"    ✓ 2D toolpath: {result['2d_path']} ({file_size} bytes)")
        if '3d_path' in result:
            file_size = os.path.getsize(result['3d_path'])
            print(f"    ✓ 3D toolpath: {result['3d_path']} ({file_size} bytes)")
        
        visualization_results.append(result)
    
    # Overall summary
    print(f"\n  Visualization Summary:")
    print(f"    - Files visualized: {len(visualization_results)}")
    print(f"    - Total 2D plots: {sum(1 for r in visualization_results if '2d_path' in r)}")
    print(f"    - Total 3D plots: {sum(1 for r in visualization_results if '3d_path' in r)}")
    
    print(f"\n  ✓ All visualizations generated successfully!")
    
    return visualization_results


def simulate_gcode_files(
    gcode_files: List[str],
    material: str = 'steel_1045',
    machine: str = 'cnc_lathe',
    stock_diameter: float = 80.0,
    stock_length: float = 200.0,
    output_dir: str = OUTPUT_DIR,
    machines_data: Optional[Dict[str, Dict]] = None,
    tools_data: Optional[Dict[str, Dict]] = None,
    materials_data: Optional[Dict[str, Dict]] = None,
    operations_data: Optional[Dict[str, Dict]] = None,
    plan_steps: Optional[List[Dict]] = None
) -> List[Dict]:
    """
    Run advanced CNC simulation on generated G-code files.

    Args:
        gcode_files: List of G-code file paths
        material: Material identifier
        machine: Machine identifier
        stock_diameter: Initial stock diameter (mm)
        stock_length: Initial stock length (mm)
        output_dir: Directory to save simulation reports
        machines_data, tools_data, materials_data, operations_data:
            reference-data dicts from reconciler.repo's legacy_*_dict()
            methods (see main()) — cascaded into CNCSimulator

    Returns:
        List of simulation reports
    """
    print_section("Running Advanced CNC Simulation")

    simulation_reports = []

    for gcode_file in gcode_files:
        if not os.path.exists(gcode_file):
            print(f"  ⚠ Warning: File not found: {gcode_file}")
            continue

        print(f"\n  Simulating: {os.path.basename(gcode_file)}")

        # Create simulator
        simulator = CNCSimulator(
            machine_id=machine,
            material_id=material,
            stock_diameter=stock_diameter,
            stock_length=stock_length,
            machines_data=machines_data,
            tools_data=tools_data,
            materials_data=materials_data,
            operations_data=operations_data,
            plan_steps=plan_steps
        )
        
        # Run simulation
        report = simulator.simulate_file(gcode_file)
        
        # Print summary
        print(f"    ✓ Simulation completed")
        
        # Cutting time summary
        cutting_time = report.get('cutting_time', {})
        print(f"    - Total cycle time: {cutting_time.get('total_cycle_time_minutes', 0):.2f} minutes")
        print(f"      - Rapid time: {cutting_time.get('rapid_time_seconds', 0):.2f}s")
        print(f"      - Cutting time: {cutting_time.get('cutting_time_seconds', 0):.2f}s")
        print(f"      - Tool changes: {cutting_time.get('tool_change_time_seconds', 0):.2f}s")
        
        # Collision summary
        collisions = report.get('collision_detection', {})
        print(f"    - Collisions detected: {collisions.get('total_collisions', 0)}")
        
        # Chip load summary
        chip_load = report.get('chip_load_analysis', {})
        print(f"    - Operations analyzed: {chip_load.get('operations_analyzed', 0)}")
        print(f"    - Average MRR: {chip_load.get('average_mrr', 0):.2f} mm³/min")
        print(f"    - Max MRR: {chip_load.get('max_mrr', 0):.2f} mm³/min")
        print(f"    - Average cutting force: {chip_load.get('average_cutting_force', 0):.1f} N "
              f"(nominal kc, uncalibrated)")
        print(f"    - Average cutting power: {chip_load.get('average_cutting_power', 0):.3f} kW "
              f"(P = Fc*vc/60000)")
        
        # Tool wear summary
        tool_wear = report.get('tool_wear', {})
        if tool_wear:
            print(f"    - Tool wear status:")
            for tool_id, status in list(tool_wear.items())[:5]:  # Show first 5 tools
                print(f"      - {tool_id}: {status.get('wear_percentage', 0):.1f}% ({status.get('wear_status', 'unknown')})")
        
        # Recommendations
        recommendations = report.get('recommendations', [])
        if recommendations:
            print(f"    - Recommendations:")
            for rec in recommendations[:3]:  # Show first 3
                print(f"      • {rec}")
        
        # Export simulation report
        base_name = os.path.splitext(os.path.basename(gcode_file))[0]
        report_path = os.path.join(output_dir, f"{base_name}_simulation.json")
        simulator.export_report(report, report_path)
        print(f"    ✓ Report saved: {report_path}")
        
        simulation_reports.append(report)
    
    # Overall summary
    print(f"\n  Simulation Summary:")
    print(f"    - Files simulated: {len(simulation_reports)}")
    
    if simulation_reports:
        total_collisions = sum(
            r.get('collision_detection', {}).get('total_collisions', 0) 
            for r in simulation_reports
        )
        print(f"    - Total collisions: {total_collisions}")
        
        if total_collisions == 0:
            print(f"\n  ✓ All simulations completed successfully with no collisions!")
        else:
            print(f"\n  ⚠ {total_collisions} collision(s) detected. Review simulation reports for details.")
    
    return simulation_reports


def flag_critical_simulation_findings(
    simulation_reports: List[Dict],
    approved_steps: List[Dict],
    expert_store: 'ExpertValidationStore'
) -> List[Dict]:
    """
    Route critical simulation findings (currently: critical tool wear) into
    KEFC's expert-validation queue instead of leaving them as a console-only
    warning. A step whose tool is reported critical gets a
    'critical_simulation_finding' request — get-or-create, so re-running the
    pipeline doesn't duplicate it (see expert_validation.py).

    Returns the list of newly/already-flagged (step, tool_id, wear_status)
    findings for the caller to report.
    """
    critical_tools = {
        tool_id: status
        for report in simulation_reports
        for tool_id, status in report.get('tool_wear', {}).items()
        if status.get('wear_status') == 'critical'
    }
    if not critical_tools:
        return []

    findings = []
    for step in approved_steps:
        status = critical_tools.get(step.get('tool_id'))
        if status is None:
            continue
        expert_store.create_request(
            feature_id=step['feature_id'], feature_type=step['feature_type'],
            reason_code="critical_simulation_finding", operation=step['operation'],
            detail=(
                f"Tool {step['tool_id']!r} reached {status.get('wear_percentage', 0):.1f}% "
                f"wear (status: critical) during simulation; "
                f"{status.get('remaining_tool_life_minutes', 0):.1f} min estimated remaining "
                f"life. This step already ran (approved_steps fed RAL before simulation "
                f"caught this), so the finding is retrospective — review before the next "
                f"physical run."
            ),
        )
        findings.append({
            "step_number": step["step_number"], "feature_id": step["feature_id"],
            "tool_id": step["tool_id"], "wear_status": "critical",
        })

    if findings:
        expert_store.save()

    return findings


def initialize_rdf_triplestore(
    kg,
    schema_path: Optional[str] = None
) -> Optional['ManufacturingTriplestore']:
    """
    Initialize RDF triplestore from existing knowledge graph.
    
    Args:
        kg: ManufacturingKG instance
        schema_path: Path to manufacturing.ttl schema file
        
    Returns:
        ManufacturingTriplestore instance or None if RDF not available
    """
    if not RDF_AVAILABLE:
        print("  ⚠ RDF triplestore not available (install rdflib)")
        return None
    
    print_section("Initializing RDF Triplestore (OntoBREP)")
    
    # Find schema file if not specified
    if schema_path is None:
        schema_path = os.path.join(BASE_DIR, 'src', 'manufacturing.ttl')

    if not os.path.exists(schema_path):
        print(f"  ⚠ Schema file not found: {schema_path}")
        return None

    print(f"  Loading OntoBREP schema from: {schema_path}")

    # Export NetworkX KG to RDF triplestore
    triplestore = kg.export_to_rdf(
        filepath=os.path.join(OUTPUT_DIR, 'manufacturing_rdf.ttl'),
        schema_path=schema_path
    )
    
    # Print triplestore statistics
    triple_count = triplestore.get_triple_count()
    node_counts = triplestore.get_node_counts()
    
    print(f"  ✓ RDF triplestore initialized successfully")
    print(f"    - Total triples: {triple_count}")
    print(f"    - Node counts by type:")
    for node_type, count in node_counts.items():
        print(f"      - {node_type}: {count}")
    
    return triplestore


def run_sparql_queries(
    triplestore: 'ManufacturingTriplestore',
    query_engine: 'ManufacturingOrchestrator',
    context: Optional[Dict] = None
) -> Dict:
    """
    Run the full, fixed-order SPARQL suite (all 50 queries in
    src/sparql_examples.py, file order) against the RDF triplestore.

    Each query has an expected outcome for the run configuration
    (sparql_examples.expected_nonempty: material and machine keys): a query
    passes when it executes and its result is non-empty exactly when a
    non-empty answer is expected. A correct empty answer therefore counts as
    passed, and an unexpected non-empty answer as failed. Replaces the
    earlier unseeded random draw of 10 queries, whose pass count differed
    between invocations.

    Returns:
        Dict with 'total', 'passed', 'failed', 'errors' and per-query records
    """
    if not RDF_AVAILABLE:
        print("  ⚠ SPARQL testing not available (install rdflib)")
        return {'status': 'skipped', 'reason': 'RDF modules not available'}

    print_section("Testing SPARQL Query Engine (full fixed-order suite)")

    try:
        from sparql_examples import get_full_suite, expected_nonempty
    except ImportError:
        print("  ⚠ SPARQL examples not available")
        return {'status': 'skipped', 'reason': 'sparql_examples module not found'}

    context = context or {}
    suite = get_full_suite()
    results = {'total': len(suite), 'passed': 0, 'failed': 0, 'errors': [], 'queries': [],
               'context': dict(context)}

    for example in suite:
        idx = example['index']
        nl_query = example.get('question') or example.get('query') or ''
        category = example['category']
        want_rows = expected_nonempty(idx, context)
        record = {'index': idx, 'query': nl_query, 'category': category,
                  'expected': 'non-empty' if want_rows else 'empty'}
        print(f"\n  Test {idx}/{len(suite)}: [{category}] {nl_query[:50]}...")
        try:
            sparql_results = triplestore.execute_sparql(example['sparql'])
            if sparql_results is None:
                raise RuntimeError("query returned None")
            result_count = len(list(sparql_results))
            record['result_count'] = result_count
            if (result_count > 0) == want_rows:
                print(f"    ✓ {result_count} results (expected {record['expected']})")
                results['passed'] += 1
                record['status'] = 'passed'
            else:
                print(f"    ✗ {result_count} results (expected {record['expected']})")
                results['failed'] += 1
                record['status'] = 'failed'
                results['errors'].append(f"Query {idx}: expected {record['expected']}, got {result_count}: {nl_query}")
        except Exception as e:
            print(f"    ✗ Query failed: {e}")
            results['failed'] += 1
            record.update(status='failed', error=str(e))
            results['errors'].append(f"Query {idx}: {e}: {nl_query}")
        results['queries'].append(record)

    print(f"\n  SPARQL Test Summary:")
    print(f"    - Total tests: {results['total']}")
    print(f"    - Passed: {results['passed']}")
    print(f"    - Failed: {results['failed']}")
    if results['errors']:
        print(f"\n  Errors:")
        for error in results['errors'][:5]:
            print(f"    - {error[:100]}")
    return results

def generate_plan_summary_md(
    manufacturing_plan: List[Dict],
    expert_store: ExpertValidationStore,
    output_dir: str = OUTPUT_DIR,
) -> str:
    """
    Persist the manufacturing plan's step sequence and pending-review state
    as a human-readable Markdown report — the console-only "Manufacturing
    Plan Summary" block (see generate_manufacturing_plan_with_kefc) truncates
    to the first 5 steps and disappears once the terminal scrolls past it;
    this covers every step and survives the run.

    Follows benchmark_report.py's generate_markdown_summary() convention
    (build one markdown string, write it to output_dir, also return it) —
    the only other human-readable-report generator in this codebase.

    Includes a "Pending Knowledge Updates" section listing every
    `knowledge_update_suggested` expert-validation request in full (not just
    its count, which summary.json already has) — see expert_validation.py's
    module docstring: resolving these requires a maintainer to manually edit
    the relevant OWL/SWRL file under knowledge/ and re-run; nothing here
    applies an ontology/rule change automatically.
    """
    os.makedirs(output_dir, exist_ok=True)

    status_counts: Dict[str, int] = {}
    for step in manufacturing_plan:
        status_counts[step['validation_status']] = status_counts.get(step['validation_status'], 0) + 1
    approved = status_counts.get('auto_approved', 0) + status_counts.get('expert_approved', 0)
    evr_summary = expert_store.summary()

    markdown = f"""# Manufacturing Plan Summary

**Generated:** {datetime.now().isoformat()}

**Total steps:** {len(manufacturing_plan)}
**Approved for RAL:** {approved}
**Requires review:** {len(manufacturing_plan) - approved}
**Expert validation requests (total):** {evr_summary['total_requests']}

## Step Sequence

| Step | Operation | Feature | Type | Status |
|------|-----------|---------|------|--------|
"""
    for step in manufacturing_plan:
        markdown += (
            f"| {step['step_number']} | {step['operation_name']} | {step['feature_id']} "
            f"| {step['feature_type']} | {step['validation_status']} |\n"
        )

    pending_updates = [r for r in expert_store.all_requests() if r.status == "knowledge_update_suggested"]
    markdown += "\n## Pending Knowledge Updates\n\n"
    if pending_updates:
        markdown += (
            "Each of these needs a maintainer to manually update the relevant OWL/SWRL "
            "file under `knowledge/` before the next run — no ontology or rule change is "
            "applied automatically.\n\n"
            "| Request | Feature | Reason | Detail | Note |\n"
            "|---------|---------|--------|--------|------|\n"
        )
        for r in pending_updates:
            markdown += (
                f"| {r.request_id} | {r.feature_id} ({r.feature_type}) | {r.reason_code} "
                f"| {r.detail} | {r.resolution_note or ''} |\n"
            )
    else:
        markdown += "None.\n"

    output_path = os.path.join(output_dir, "manufacturing_plan_summary.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown)

    return markdown


def export_results(
    features: List[Dict],
    manufacturing_plan: List[Dict],
    gcode_files: List[str],
    validation_reports: Optional[List[Dict]] = None,
    simulation_reports: Optional[List[Dict]] = None,
    output_dir: str = OUTPUT_DIR,
    skl_metadata: Optional[Dict] = None
) -> str:
    """
    Export results to JSON files.

    Args:
        features: List of feature dictionaries
        manufacturing_plan: List of manufacturing steps
        gcode_files: List of G-code file paths
        validation_reports: List of validation reports (optional)
        output_dir: Directory to save output files
        skl_metadata: skl_version/reasoner/reasoning_status/expert_validation_summary/
            unified_graph_stats — the new top-level plan metadata fields (optional)

    Returns:
        Path to output directory
    """
    print_section("Exporting Results")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Export features
    features_path = os.path.join(output_dir, "features.json")
    with open(features_path, 'w', encoding='utf-8') as f:
        json.dump(features, f, indent=2, default=str)
    print(f"  ✓ Features exported to: {features_path}")
    
    # Export manufacturing plan
    plan_path = os.path.join(output_dir, "manufacturing_plan.json")
    with open(plan_path, 'w', encoding='utf-8') as f:
        json.dump(manufacturing_plan, f, indent=2, default=str)
    print(f"  ✓ Manufacturing plan exported to: {plan_path}")
    
    # Export summary
    summary = {
        'total_features': len(features),
        'total_steps': len(manufacturing_plan),
        'feature_types': {},
        'operations': {},
        'gcode_files': [_repo_relative(p) for p in gcode_files],
        'validation': None
    }
    
    # Count feature types
    for feature in features:
        feat_type = feature['type']
        summary['feature_types'][feat_type] = summary['feature_types'].get(feat_type, 0) + 1
    
    # Count operations
    for step in manufacturing_plan:
        op_name = step['operation_name']
        summary['operations'][op_name] = summary['operations'].get(op_name, 0) + 1
    
    # Add validation summary if available
    if validation_reports:
        validation_summary = {
            'files_validated': len(validation_reports),
            'total_errors': 0,
            'total_warnings': 0,
            'status': 'PASS'
        }
        
        for report in validation_reports:
            validation_summary['total_errors'] += report['summary']['errors']
            validation_summary['total_warnings'] += report['summary']['warnings']
        
        if validation_summary['total_errors'] > 0:
            validation_summary['status'] = 'FAIL'
        
        summary['validation'] = validation_summary
    
    # Add simulation summary if available
    if simulation_reports:
        simulation_summary = {
            'files_simulated': len(simulation_reports),
            'total_collisions': 0,
            'total_cycle_time_minutes': 0,
            'average_mrr': 0
        }
        
        for report in simulation_reports:
            simulation_summary['total_collisions'] += report.get('collision_detection', {}).get('total_collisions', 0)
            simulation_summary['total_cycle_time_minutes'] += report.get('cutting_time', {}).get('total_cycle_time_minutes', 0)
            simulation_summary['average_mrr'] += report.get('chip_load_analysis', {}).get('average_mrr', 0)
        
        simulation_summary['average_mrr'] = simulation_summary['average_mrr'] / len(simulation_reports) if simulation_reports else 0
        
        summary['simulation'] = simulation_summary

    # Top-level SKL/KEFC plan metadata (see Public Interfaces And Output Shape
    # in .codex/development_plan.md): skl_version, reasoner, reasoning_status,
    # expert_validation_summary, unified_graph_stats.
    if skl_metadata:
        summary.update(skl_metadata)

    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ Summary exported to: {summary_path}")
    
    return output_dir


def main():
    """Main pipeline execution."""
    print_header("CAD-to-G-code Orchestration Prototype")
    print("\n  Building manufacturing knowledge graph from CAD features...")
    
    # Configuration
    MOTOR_DATA_DIR = os.path.join(BASE_DIR, 'data', 'motor_data')
    
    # Feature files to process — paired by source (STEP-file geometry vs 2D
    # drawing), each pair primary=Gemini 3.1 Pro, secondary=Gemini 3.5 Flash,
    # reconciled via consensus voting within each pair (see
    # load_and_parse_features's docstring for why not across pairs).
    STEP_FEATURE_FILES = [
        os.path.join(MOTOR_DATA_DIR, 'features_eixo_step_Gemini31Pro.txt'),
        os.path.join(MOTOR_DATA_DIR, 'features_eixo_step_Gemini35flash.txt'),
    ]
    DRAWING_FEATURE_FILES = [
        os.path.join(MOTOR_DATA_DIR, 'draw_features_eixo_Gemini31Pro.txt'),
        os.path.join(MOTOR_DATA_DIR, 'draw_features_eixo_Gemini35flash.txt'),
    ]

    # Optional RDF triplestore mode
    USE_RDF_TRIPLESTORE = RDF_AVAILABLE  # Set to True to enable RDF/SPARQL backend

    # Step 1: Load and parse features
    features = load_and_parse_features(STEP_FEATURE_FILES, DRAWING_FEATURE_FILES)
    
    if not features:
        print("\n  ✗ No features loaded. Exiting.")
        sys.exit(1)
    
    # Step 3: Generate manufacturing plan via KINM -> CFRM -> KEFC (SKL-grounded,
    # traceable to ontology facts / SWRL rules / reasoner inferences — see
    # AGENTS.md). This is the architecturally-authoritative plan; it replaces
    # the pre-retrofit orchestrator-driven plan as what feeds RAL below. Run
    # before building the unified graph, because the graph's decision edges
    # (REQUIRES/USES/RUNS_ON/REMOVES/SEQUENCE_BEFORE) are now sourced from
    # this plan directly — not from ontology.py — so the graph is genuinely
    # SKL-authoritative rather than a Python-dict mirror with SKL provenance
    # bolted on afterward (see .codex/development_plan.md Phase 8).
    kefc_plan = generate_manufacturing_plan_with_kefc(
        features, MATERIAL, MACHINE, OUTPUT_DIR
    )
    manufacturing_plan = kefc_plan['steps']
    approved_steps = kefc_plan['approved_steps']
    # Steps KEFC would withhold, recorded before any ablation so that the
    # kefc_gate ablation can report them separately from RAL's refusals.
    kefc_withheld_ids = [s['step_number'] for s in manufacturing_plan if s not in approved_steps]
    if ABLATION == 'kefc_gate':
        print("\n  !! ABLATION kefc_gate: passing every planned step to RAL regardless of status")
        # RAL's own input contract still applies with KEFC bypassed: a step
        # the serialiser cannot express from plan data is refused by RAL and
        # recorded, not serialised from placeholders.
        approved_steps = list(manufacturing_plan)
    reconciler = kefc_plan.pop('_reconciler')
    expert_store = kefc_plan.pop('_expert_store')
    reconciled_features = kefc_plan.pop('_reconciled_features')

    if len(approved_steps) < len(manufacturing_plan):
        print(f"\n  ⚠ {len(manufacturing_plan) - len(approved_steps)} of "
              f"{len(manufacturing_plan)} steps require expert review and will "
              f"NOT be sent to RAL (see output/expert_validation_requests.json).")

    # Step 4: Build the unified graph — structural nodes (vocabulary +
    # features) sourced from SKL, decision edges sourced from the KEFC plan
    # above, with rule_id/ontology_sources provenance attached at edge
    # creation (not as a later bolt-on pass).
    kg = ManufacturingKG()
    kg.build_kg_from_skl(features, reconciler.repo)
    kg.populate_decisions_from_kefc(manufacturing_plan, reconciled_features)
    kg.apply_expert_resolutions(expert_store.all_requests())
    stats = kg.get_graph_stats()

    print(f"\n  ✓ Unified graph constructed (SKL/KEFC-authoritative)")
    print(f"    - Total nodes: {stats['total_nodes']}")
    print(f"    - Total edges: {stats['total_edges']}")

    # Step 3.5: Initialize RDF triplestore (optional)
    triplestore = None
    if USE_RDF_TRIPLESTORE:
        triplestore = initialize_rdf_triplestore(kg)

    # Step 4.5: Test SPARQL queries (optional)
    sparql_results = None
    if triplestore:
        orchestrator = ManufacturingOrchestrator(kg)
        orchestrator.set_triplestore(triplestore)
        sparql_results = run_sparql_queries(triplestore, orchestrator, context={'material': MATERIAL, 'machine': MACHINE})
        # Provenance assertion: every planned step's four parameter records
        # (feed, spindle speed, depth of cut, coolant) must resolve by SPARQL
        # to a rule identifier and at least one ontology IRI.
        from sparql_examples import EXAMPLES, PROVENANCE_COUNT_QUERY_INDEX
        rows = triplestore.execute_sparql(EXAMPLES[PROVENANCE_COUNT_QUERY_INDEX - 1]['sparql'])
        q52 = int(next(iter(rows[0].values()))) if rows else 0
        expected_records = 4 * len(manufacturing_plan)
        sparql_results['parameter_records_with_rule_and_source'] = q52
        sparql_results['parameter_records_expected'] = expected_records
        with open(os.path.join(OUTPUT_DIR, 'sparql_results.json'), 'w', encoding='utf-8') as fh:
            json.dump(sparql_results, fh, indent=2, ensure_ascii=False)
        if q52 != expected_records:
            raise RuntimeError(
                f"Provenance by SPARQL: Q{PROVENANCE_COUNT_QUERY_INDEX} finds {q52} parameter records with a "
                f"rule identifier and an ontology source; expected 4 x {len(manufacturing_plan)} = {expected_records}.")
        print(f"  ✓ Provenance by SPARQL: {q52} of {expected_records} parameter records resolve to a rule "
              f"identifier and ontology IRIs (Q{PROVENANCE_COUNT_QUERY_INDEX})")
    
    # Step 5: Generate G-code programs — only from KEFC's approved_steps.
    # manufacturing_plan (all steps, including requires_review) stays the
    # full audit record exported to manufacturing_plan.json; RAL must never
    # execute a step a human hasn't (at least implicitly, via auto-approval)
    # signed off on (see AGENTS.md constraint #6).
    ral_refusals = []
    serialised_steps = []
    ral_accounting = None
    if not approved_steps:
        print("\n  ⚠ No steps are approved for RAL — all steps require expert "
              "review. Skipping G-code generation.")
        gcode_files = []
    else:
        gcode_files, serialised_steps, ral_refusals = generate_gcode(approved_steps, MATERIAL, MACHINE, OUTPUT_DIR)
        # RAL refusals are feedback findings: one serialisation_input_missing
        # request per refused step, written to the expert-validation store.
        from ral_refusals import record_refusals, check_ral_accounting
        record_refusals(ral_refusals, expert_store)
        ral_accounting = check_ral_accounting(approved_steps, serialised_steps, ral_refusals, expert_store)
        with open(os.path.join(OUTPUT_DIR, 'ral_refusals.json'), 'w', encoding='utf-8') as fh:
            json.dump({'accounting': ral_accounting, 'refusals': ral_refusals}, fh, indent=2, ensure_ascii=False)
        refused_ids = {r['step_number'] for r in ral_refusals}
        for s in manufacturing_plan:
            if s in approved_steps:
                s['ral_status'] = 'refused' if s['step_number'] in refused_ids else 'serialised'
            else:
                s['ral_status'] = 'not_handed_to_ral'
        print(f"  ✓ RAL accounting: {ral_accounting['handed']} handed = {ral_accounting['serialised']} serialised "
              f"+ {ral_accounting['refused']} refused (each refusal recorded as serialisation_input_missing)")
        if ABLATION == 'kefc_gate':
            sets = {'kefc_would_withhold': sorted(kefc_withheld_ids),
                    'ral_refused': sorted(refused_ids),
                    'withheld_by_both': sorted(set(kefc_withheld_ids) & refused_ids),
                    'kefc_only_serialised': sorted(set(kefc_withheld_ids) - refused_ids),
                    'ral_only_refused': sorted(refused_ids - set(kefc_withheld_ids))}
            with open(os.path.join(OUTPUT_DIR, 'ablation_kefc_gate_sets.json'), 'w', encoding='utf-8') as fh:
                json.dump(sets, fh, indent=2)
            print(f"  !! kefc_gate: KEFC would withhold {sets['kefc_would_withhold']}; RAL refused "
                  f"{sets['ral_refused']}; serialised although KEFC would withhold {sets['kefc_only_serialised']}")
        # Plan-to-programme consistency: every serialised step appears as
        # exactly one operation segment, and no segment lacks a serialised
        # step. Fails loudly.
        for gcode_file in gcode_files:
            with open(gcode_file, encoding='utf-8') as fh:
                segments = [ln for ln in fh if ln.startswith('(--- ') and ': ' in ln
                            and not ln.startswith('(--- Tool Change') and not ln.startswith('(--- Machine')]
            if len(segments) != len(serialised_steps):
                raise RuntimeError(
                    f"Programme {gcode_file} has {len(segments)} operation segments but "
                    f"{len(serialised_steps)} steps were serialised."
                )
        print(f"  ✓ Plan-to-programme check: {len(serialised_steps)} serialised steps -> {len(segments)} segments")

        # Parameter fidelity: in every segment, the spindle speed, feed and
        # coolant state in effect during its cutting moves must equal the
        # approved step's spindle_speed, feed_rate and coolant. Fails loudly.
        from programme_fidelity import check_parameter_fidelity
        for gcode_file in gcode_files:
            fidelity = check_parameter_fidelity(gcode_file, serialised_steps)
            with open(os.path.join(OUTPUT_DIR, 'parameter_fidelity.json'), 'w', encoding='utf-8') as fh:
                json.dump(fidelity, fh, indent=2, ensure_ascii=False)
            print(f"  ✓ Parameter fidelity: {fidelity['segments_checked']} segments checked, "
                  f"spindle {fidelity['spindle_match']}, feed {fidelity['feed_match']}, "
                  f"coolant {fidelity['coolant_match']} matching the approved packages"
                  if fidelity['passed'] else
                  f"  ✗ Parameter fidelity FAILED: {fidelity['mismatches'][:3]}")
            if not fidelity['passed']:
                raise RuntimeError(
                    f"Programme {_repo_relative(gcode_file)} does not carry the approved parameters: "
                    f"{fidelity['segments_checked']} segments, spindle {fidelity['spindle_match']}, "
                    f"feed {fidelity['feed_match']}, coolant {fidelity['coolant_match']} matching; "
                    f"first mismatches {fidelity['mismatches'][:3]}")

        # Dimension fidelity: every segment must declare its plan inputs,
        # each input must trace to the approved step's feature_dimensions or
        # feature_location under the cited key (no defaulted lookup), and
        # every cutting-move coordinate must derive from those inputs.
        from dimension_fidelity import check_dimension_fidelity
        for gcode_file in gcode_files:
            dfid = check_dimension_fidelity(gcode_file, serialised_steps)
            with open(os.path.join(OUTPUT_DIR, 'dimension_fidelity.json'), 'w', encoding='utf-8') as fh:
                json.dump(dfid, fh, indent=2, ensure_ascii=False)
            print(f"  ✓ Dimension fidelity: {dfid['segments']} segments, {dfid['lookups']} plan-input lookups, "
                  f"{dfid['defaulted']} defaulted, {dfid['cutting_words_checked']} cutting-move coordinates, "
                  f"{dfid['unexplained_cutting_words']} not derived from the plan"
                  if dfid['passed'] else f"  ✗ Dimension fidelity FAILED: {dfid['problems'][:3]}")
            if not dfid['passed'] or dfid['defaulted'] != 0:
                raise RuntimeError(
                    f"Programme {_repo_relative(gcode_file)} is not dimensionally faithful to the plan: "
                    f"{dfid['defaulted']} of {dfid['lookups']} lookups untraced, "
                    f"{dfid['unexplained_cutting_words']} cutting-move coordinates not derived from the plan; "
                    f"first problems {dfid['problems'][:3]}")

    # Step 6: Validate G-code — reference data sourced from SKL (via the
    # already-reasoned repo), not ontology.py (removed).
    machines_data = reconciler.repo.legacy_machines_dict()
    tools_data = reconciler.repo.legacy_tools_dict()
    materials_data = reconciler.repo.legacy_materials_dict()
    operations_data = reconciler.repo.legacy_operations_dict()

    validation_reports = validate_gcode(gcode_files, MACHINE, OUTPUT_DIR, machines_data=machines_data)

    # Step 7: Run advanced CNC simulation
    simulation_reports = simulate_gcode_files(
        gcode_files,
        material=MATERIAL,
        machine=MACHINE,
        stock_diameter=80.0,
        stock_length=200.0,
        output_dir=OUTPUT_DIR,
        machines_data=machines_data,
        tools_data=tools_data,
        materials_data=materials_data,
        operations_data=operations_data,
        plan_steps=serialised_steps
    )
    
    # Step 7.5: Feed critical simulation findings (e.g. tool wear) back into
    # KEFC's expert-validation queue. Without this, a "CRITICAL: tool X wear
    # is critical" recommendation was only ever a console print — it had no
    # effect on validation_status, the final PASS/FAIL, or anything a human
    # reviewing expert_validation_requests.json would see (see AGENTS.md:
    # simulation findings need the same exception-gate treatment as
    # planning-time findings, since both bear on whether it's safe to run
    # the program).
    critical_tool_findings = flag_critical_simulation_findings(
        simulation_reports, serialised_steps, expert_store
    )

    # Step 8: Generate visualizations
    visualization_results = visualize_gcode_files(gcode_files, OUTPUT_DIR, color_by='operation')
    
    # Step 9: Export results
    kg_stats = kg.get_graph_stats()
    output_dir = export_results(
        features,
        manufacturing_plan,
        gcode_files,
        validation_reports,
        simulation_reports,
        output_dir=OUTPUT_DIR,
        skl_metadata={
            'skl_version': kefc_plan['skl_version'],
            'reasoner': kefc_plan['reasoner'],
            'reasoning_status': kefc_plan['reasoning_status'],
            # Recomputed fresh, not kefc_plan's snapshot — flag_critical_
            # simulation_findings() may have added requests after the plan
            # was built.
            'expert_validation_summary': expert_store.summary(),
            'critical_simulation_findings': critical_tool_findings,
            'unified_graph_stats': {
                'total_nodes': kg_stats['total_nodes'],
                'total_edges': kg_stats['total_edges'],
                'node_types': dict(kg_stats['node_types']),
                'edge_types': dict(kg_stats['edge_types']),
            },
        },
    )

    plan_summary_md_path = os.path.join(output_dir, "manufacturing_plan_summary.md")
    generate_plan_summary_md(manufacturing_plan, expert_store, output_dir)
    print(f"  ✓ Manufacturing plan summary exported to: {plan_summary_md_path}")

    # Step 9.5: Export SKL/KEFC artifacts — unified_graph.ttl (RDF serialization
    # of the same unified graph the triplestore already holds),
    # reasoning_report.json (Pellet run diagnostics + which ontologies were
    # loaded), provenance_report.json (per-step rule/ontology traceability).
    # expert_validation_requests.json was already written by
    # ExpertValidationStore.save() inside generate_manufacturing_plan_with_kefc().
    if triplestore:
        unified_graph_path = os.path.join(OUTPUT_DIR, 'unified_graph.ttl')
        triplestore.serialize(unified_graph_path)
        print(f"  ✓ Unified graph exported to: {unified_graph_path}")

    reasoning_report_path = os.path.join(OUTPUT_DIR, 'reasoning_report.json')
    with open(reasoning_report_path, 'w', encoding='utf-8') as f:
        json.dump(reconciler.repo.reasoning_report(), f, indent=2)
    print(f"  ✓ Reasoning report exported to: {reasoning_report_path}")

    provenance_report = {
        'skl_version': reconciler.repo.reasoning_report()['skl_version'],
        'steps': [
            {
                'step_number': step['step_number'],
                'feature_id': step['feature_id'],
                'operation': step['operation'],
                'operation_selection_rule_id': step.get('operation_selection_rule_id'),
                'operation_ontology_sources': step.get('operation_ontology_sources'),
                'tool_id': step.get('tool_id'),
                'tool_selection_rule_id': step.get('tool_selection_rule_id'),
                'validation_status': step['validation_status'],
                'parameters': step['parameters'],
            }
            for step in manufacturing_plan
        ],
    }
    provenance_report_path = os.path.join(OUTPUT_DIR, 'provenance_report.json')
    with open(provenance_report_path, 'w', encoding='utf-8') as f:
        json.dump(provenance_report, f, indent=2, default=str)
    print(f"  ✓ Provenance report exported to: {provenance_report_path}")

    # Final summary
    print_header("Pipeline Complete")

    print(f"\n  Features processed: {len(features)}")
    print(f"  Manufacturing steps: {len(manufacturing_plan)} "
          f"({len(approved_steps)} handed to RAL, "
          f"{len(manufacturing_plan) - len(approved_steps)} require expert review; "
          f"RAL serialised {len(serialised_steps)}, refused {len(ral_refusals)})")
    print(f"  G-code files generated: {len(gcode_files)}")
    print(f"  Validation status: {'PASS' if validation_reports and validation_reports[0]['summary']['errors'] == 0 else 'FAIL'}")
    print(f"  Simulations completed: {len(simulation_reports)}")
    if critical_tool_findings:
        print(f"  ⚠ Post-simulation flags: {len(critical_tool_findings)} step(s) used a tool "
              f"simulation found critical (see expert_validation_requests.json)")
    print(f"  Visualizations generated: {len(visualization_results)}")
    print(f"  Output directory: {output_dir}")

    print(f"\n  SKL / KEFC:")
    print(f"    - SKL version: {kefc_plan['skl_version']}")
    print(f"    - Reasoner: {kefc_plan['reasoner']}")
    print(f"    - Reasoning status: {kefc_plan['reasoning_status']}")
    print(f"    - Expert validation: {expert_store.summary()}")

    pending_knowledge_updates = [
        r for r in expert_store.all_requests() if r.status == "knowledge_update_suggested"
    ]
    if pending_knowledge_updates:
        print(f"\n  ⚠ Pending Knowledge Updates ({len(pending_knowledge_updates)}) — see "
              f"{plan_summary_md_path} for full detail, or edit knowledge/**/*.owl or "
              f"knowledge/rules/machining_rules.swrl by hand and re-run:")
        for r in pending_knowledge_updates:
            print(f"    - {r.request_id}: feature {r.feature_id} ({r.feature_type}) "
                  f"[{r.reason_code}] {r.detail}")

    # Print RDF/SPARQL summary
    if triplestore:
        triple_count = triplestore.get_triple_count()
        print(f"\n  RDF Triplestore (OntoBREP):")
        print(f"    - Total triples: {triple_count}")
        print(f"    - Backend: RDF/SPARQL (rdflib)")
    
    if sparql_results and sparql_results.get('status') != 'skipped':
        print(f"\n  SPARQL Query Testing:")
        print(f"    - Tests run: {sparql_results['total']}")
        print(f"    - Passed: {sparql_results['passed']}")
        print(f"    - Failed: {sparql_results['failed']}")
        print(f"    - Success rate: {sparql_results['passed']/sparql_results['total']*100:.1f}%")
    
    # Print simulation highlights
    if simulation_reports:
        sim = simulation_reports[0]
        print(f"\n  Simulation Highlights:")
        print(f"    - Total cycle time: {sim.get('cutting_time', {}).get('total_cycle_time_minutes', 0):.2f} minutes")
        print(f"    - Collisions detected: {sim.get('collision_detection', {}).get('total_collisions', 0)}")
        print(f"    - Average MRR: {sim.get('chip_load_analysis', {}).get('average_mrr', 0):.2f} mm³/min")
        
        # Tool wear summary
        tool_wear = sim.get('tool_wear', {})
        if tool_wear:
            print(f"    - Tool wear status:")
            for tool_id, status in tool_wear.items():
                print(f"      - {tool_id}: {status.get('wear_percentage', 0):.1f}% ({status.get('wear_status', 'unknown')})")
    
    print("\n  Next steps:")
    print("    - Review manufacturing_plan.json for operation sequence")
    print("    - Review validation reports for G-code compliance")
    print("    - Review simulation reports for cutting parameters and tool wear")
    print("    - Review toolpath visualizations for cutting patterns")
    print("    - Test G-code on actual CNC machine (Phase 7+)")
    
    print("\n" + "=" * 70 + "\n")


def _parse_cli(argv):
    import argparse
    parser = argparse.ArgumentParser(description="CAD-to-G-code orchestration prototype")
    parser.add_argument('--output-dir', default=None,
                        help="directory for run artefacts (default: <repo>/output)")
    parser.add_argument('--material', default='steel_1045',
                        choices=['steel_1045', 'aluminum_6061', 'stainless_304'],
                        help="material key of the case part (default steel_1045)")
    parser.add_argument('--machine', default='cnc_lathe',
                        choices=['cnc_lathe', 'cnc_mill_turn'],
                        help="machine key of the run (default cnc_lathe)")
    parser.add_argument('--ablation', default=None,
                        choices=['type_gate', 'orientation_gate', 'kefc_gate', 'swap_sources',
                                 'serialisation_profile'],
                        help="disable one mechanism for a controlled comparison (see ABLATION)")
    return parser.parse_args(argv)


if __name__ == '__main__':
    _args = _parse_cli(sys.argv[1:])
    ABLATION = _args.ablation
    MATERIAL = _args.material
    MACHINE = _args.machine
    if _args.output_dir:
        OUTPUT_DIR = os.path.abspath(_args.output_dir)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    if ABLATION == 'type_gate':
        import feature_parser
        feature_parser.TYPE_GATE = 0.0
        print("\n  !! ABLATION type_gate: tau_min = 0 (merge criterion reduced to S > theta)")
    if ABLATION == 'orientation_gate':
        import kefc_controller
        _orig = kefc_controller.KEFCController._check_tool_orientation
        kefc_controller.KEFCController._check_tool_orientation = lambda self, rf, op, m: None
        # The flat capability model of the first submission has no
        # orientation reasoning at all, so the serialisation-profile check
        # (which reasons about the same tool orientation) is removed too.
        kefc_controller.KEFCController._check_serialisation_profile = lambda self, rf, op, m: None
        print("\n  !! ABLATION orientation_gate: capability model reduced to the operation set")
    if ABLATION == 'serialisation_profile':
        import kefc_controller
        kefc_controller.KEFCController._check_serialisation_profile = lambda self, rf, op, m: None
        print("\n  !! ABLATION serialisation_profile: RAL serialisation-profile check disabled")
    main()

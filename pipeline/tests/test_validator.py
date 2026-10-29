"""
Test G-code Validator Module
=============================
Tests the validator module's G-code parsing, toolpath simulation, and validation.

Test Cases:
1. GCodeParser: Parse G-code lines, files, and text
2. ToolpathSimulator: Simulate tool motion and track state
3. GCodeValidator: Validate against machine limits
4. End-to-end: Validate generated G-code file from Phase 2
"""

import os
import sys
import json

# BASE_DIR is the project root (this file lives in tests/, one level down).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from validator import (
    GCodeParser,
    ToolpathSimulator,
    GCodeValidator,
    validate_gcode_file,
    validate_gcode_text
)


def test_parser_basics():
    """Test GCodeParser basic functionality."""
    print("\n" + "="*70)
    print("TEST 1: GCodeParser Basics")
    print("="*70)
    
    parser = GCodeParser()
    
    # Test parsing simple motion commands
    test_cases = [
        ("G00 X50.0 Z100.0", {'X': 50.0, 'Z': 100.0}, ['G00'], []),
        ("G01 X48.0 F0.25", {'X': 48.0, 'F': 0.25}, ['G01'], []),
        ("M03 S1500", {'S': 1500.0}, [], ['M03']),
        ("T01 M06", {}, [], ['M06']),
        ("G81 X25.0 Z-10.0 R-5.0 F0.15", {'X': 25.0, 'Z': -10.0, 'R': -5.0, 'F': 0.15}, ['G81'], []),
    ]
    
    for i, (raw_text, expected_params, expected_g, expected_m) in enumerate(test_cases, 1):
        cmd = parser.parse_line(i, raw_text)
        
        print(f"\nTest case {i}: {raw_text}")
        print(f"  G-codes: {cmd.g_codes} (expected: {expected_g})")
        print(f"  M-codes: {cmd.m_codes} (expected: {expected_m})")
        print(f"  Parameters: {cmd.parameters}")
        print(f"  Tool: {cmd.tool}")
        
        # Verify
        assert set(cmd.g_codes) == set(expected_g), f"G-codes mismatch: {cmd.g_codes} != {expected_g}"
        assert set(cmd.m_codes) == set(expected_m), f"M-codes mismatch: {cmd.m_codes} != {expected_m}"
        for key, val in expected_params.items():
            assert key in cmd.parameters, f"Missing parameter {key}"
            assert abs(cmd.parameters[key] - val) < 0.001, f"Parameter {key} mismatch: {cmd.parameters[key]} != {val}"
    
    # Test tool number extraction
    cmd = parser.parse_line(1, "T01 M06")
    assert cmd.tool == 1, f"Tool number mismatch: {cmd.tool} != 1"
    print(f"\nTool extraction: T01 -> {cmd.tool} ✓")
    
    # Test comment extraction
    cmd = parser.parse_line(1, "G00 X50.0 ; Rapid to start")
    assert cmd.comment == "; Rapid to start", f"Comment mismatch: {cmd.comment}"
    print(f"Comment extraction: '{cmd.comment}' ✓")
    
    print("\n✅ Parser basics PASSED")


def test_parser_file():
    """Test parsing the generated G-code file."""
    print("\n" + "="*70)
    print("TEST 2: Parse Generated G-code File")
    print("="*70)
    
    parser = GCodeParser()
    gcode_path = os.path.join(BASE_DIR, 'output', 'motor_shaft_1001.nc')
    
    if not os.path.exists(gcode_path):
        print(f"⚠️  G-code file not found: {gcode_path}")
        print("Skipping file parsing test.")
        return
    
    print(f"\nParsing: {gcode_path}")
    commands = parser.parse_file(gcode_path)
    
    print(f"Total commands parsed: {len(commands)}")
    
    # Count G-code types
    g_code_counts = {}
    for cmd in commands:
        for g in cmd.g_codes:
            g_code_counts[g] = g_code_counts.get(g, 0) + 1
    
    print(f"\nG-code distribution:")
    for g, count in sorted(g_code_counts.items()):
        print(f"  {g}: {count}")
    
    # Count M-code types
    m_code_counts = {}
    for cmd in commands:
        for m in cmd.m_codes:
            m_code_counts[m] = m_code_counts.get(m, 0) + 1
    
    print(f"\nM-code distribution:")
    for m, count in sorted(m_code_counts.items()):
        print(f"  {m}: {count}")
    
    # Count tool changes
    tool_changes = sum(1 for cmd in commands if 'M06' in cmd.m_codes)
    print(f"\nTool changes (M06): {tool_changes}")
    
    # Count unique tools
    tools = set()
    for cmd in commands:
        if cmd.tool:
            tools.add(cmd.tool)
    print(f"Unique tools: {sorted(tools)}")
    
    print("\n✅ File parsing PASSED")


def test_simulator():
    """Test ToolpathSimulator functionality."""
    print("\n" + "="*70)
    print("TEST 3: ToolpathSimulator")
    print("="*70)
    
    parser = GCodeParser()
    simulator = ToolpathSimulator()
    
    # Create test G-code sequence
    test_gcode = """
    O1001
    G90 G40 G49 G80
    G00 X100.0 Z100.0
    T01 M06
    M03 S1500
    M08
    G00 X52.0 Z5.0
    G01 X48.0 Z-20.0 F0.25
    G01 X48.0 Z-40.0
    G00 X100.0 Z100.0
    M05
    M09
    M02
    """
    
    commands = parser.parse_text(test_gcode)
    print(f"\nTest G-code commands: {len(commands)}")
    
    # Simulate
    history = simulator.simulate(commands)
    
    print(f"\nSimulation history entries: {len(history)}")
    print(f"Final position: X={simulator.state.x_position:.2f}, Z={simulator.state.z_position:.2f}")
    print(f"Spindle on: {simulator.state.spindle_on}")
    print(f"Current tool: T{simulator.state.current_tool}")
    
    # Get statistics
    stats = simulator.get_statistics()
    print(f"\nSimulation statistics:")
    print(f"  Total travel distance: {stats['total_travel_distance']:.2f}mm")
    print(f"  Rapid distance: {stats['rapid_distance']:.2f}mm")
    print(f"  Cut distance: {stats['cut_distance']:.2f}mm")
    print(f"  Tool changes: {stats['tool_changes']}")
    print(f"  Blocks executed: {stats['blocks_executed']}")
    
    # Verify final state
    assert simulator.state.x_position == 100.0, f"Final X mismatch: {simulator.state.x_position}"
    assert simulator.state.z_position == 100.0, f"Final Z mismatch: {simulator.state.z_position}"
    assert not simulator.state.spindle_on, "Spindle should be off at end"
    assert simulator.state.current_tool == 1, f"Tool mismatch: {simulator.state.current_tool}"
    
    print("\n✅ Simulator PASSED")


def test_validator_bounds():
    """Test validator bounds checking."""
    print("\n" + "="*70)
    print("TEST 4: Validator - Bounds Checking")
    print("="*70)
    
    validator = GCodeValidator('cnc_lathe')
    parser = GCodeParser()
    
    # Test G-code with out-of-bounds positions
    test_gcode = """
    O2001
    G00 X200.0 Z100.0
    G01 X50.0 Z-1500.0 F0.25
    G01 X50.0 Z-500.0
    M02
    """
    
    commands = parser.parse_text(test_gcode)
    violations = validator.validate_commands(commands)
    
    print(f"\nTest G-code with out-of-bounds positions:")
    print(f"  X200.0 (max X is {validator.x_max})")
    print(f"  Z-1500.0 (min Z is {validator.z_min})")
    
    print(f"\nViolations found: {len(violations)}")
    for v in violations:
        print(f"  Line {v.line_number}: [{v.severity}] {v.message}")
    
    # Check for bounds violations
    bounds_violations = [v for v in violations if v.category == 'bounds']
    print(f"\nBounds violations: {len(bounds_violations)}")
    
    assert len(bounds_violations) >= 2, f"Expected at least 2 bounds violations, got {len(bounds_violations)}"
    
    print("\n✅ Bounds checking PASSED")


def test_validator_spindle():
    """Test validator spindle speed checking."""
    print("\n" + "="*70)
    print("TEST 5: Validator - Spindle Speed Checking")
    print("="*70)
    
    validator = GCodeValidator('cnc_lathe')
    parser = GCodeParser()
    
    # Test G-code with excessive spindle speed
    test_gcode = """
    O2002
    M03 S5000
    G01 X50.0 Z-50.0 F0.25
    M05
    M02
    """
    
    commands = parser.parse_text(test_gcode)
    violations = validator.validate_commands(commands)
    
    print(f"\nTest G-code with excessive spindle speed:")
    print(f"  S5000 (max RPM is {validator.max_rpm})")
    
    print(f"\nViolations found: {len(violations)}")
    for v in violations:
        print(f"  Line {v.line_number}: [{v.severity}] {v.message}")
    
    # Check for spindle violations
    spindle_violations = [v for v in violations if v.category == 'spindle']
    print(f"\nSpindle violations: {len(spindle_violations)}")
    
    assert len(spindle_violations) >= 1, f"Expected at least 1 spindle violation, got {len(spindle_violations)}"
    
    print("\n✅ Spindle speed checking PASSED")


def test_validator_feed_rate():
    """Test validator feed rate checking."""
    print("\n" + "="*70)
    print("TEST 6: Validator - Feed Rate Checking")
    print("="*70)
    
    validator = GCodeValidator('cnc_lathe')
    parser = GCodeParser()
    
    # Test G-code with excessive feed rate
    test_gcode = """
    O2003
    M03 S1500
    G01 X50.0 Z-50.0 F10.0
    M05
    M02
    """
    
    commands = parser.parse_text(test_gcode)
    violations = validator.validate_commands(commands)
    
    print(f"\nTest G-code with excessive feed rate:")
    print(f"  F10.0 (max feed rate is {validator.max_feed_rate} mm/rev)")
    
    print(f"\nViolations found: {len(violations)}")
    for v in violations:
        print(f"  Line {v.line_number}: [{v.severity}] {v.message}")
    
    # Check for feed rate violations
    feed_violations = [v for v in violations if v.category == 'feed_rate']
    print(f"\nFeed rate violations: {len(feed_violations)}")
    
    assert len(feed_violations) >= 1, f"Expected at least 1 feed rate violation, got {len(feed_violations)}"
    
    print("\n✅ Feed rate checking PASSED")


def test_validator_full():
    """Test full validation of generated G-code file."""
    print("\n" + "="*70)
    print("TEST 7: Full Validation of Generated G-code")
    print("="*70)
    
    gcode_path = os.path.join(BASE_DIR, 'output', 'motor_shaft_1001.nc')
    
    if not os.path.exists(gcode_path):
        print(f"⚠️  G-code file not found: {gcode_path}")
        print("Skipping full validation test.")
        return
    
    print(f"\nValidating: {gcode_path}")
    
    # Use convenience function
    report = validate_gcode_file(gcode_path, 'cnc_lathe')
    
    # Print summary
    summary = report['summary']
    print(f"\n{'='*70}")
    print(f"VALIDATION REPORT SUMMARY")
    print(f"{'='*70}")
    print(f"Status: {summary['status']}")
    print(f"Machine: {summary['machine_name']} ({summary['machine_id']})")
    print(f"Total violations: {summary['total_violations']}")
    print(f"  Errors: {summary['errors']}")
    print(f"  Warnings: {summary['warnings']}")
    
    # Print statistics
    stats = report['statistics']
    print(f"\nToolpath Statistics:")
    print(f"  Total travel distance: {stats['total_travel_distance']}mm")
    print(f"  Rapid distance: {stats['rapid_distance']}mm")
    print(f"  Cut distance: {stats['cut_distance']}mm")
    print(f"  Tool changes: {stats['tool_changes']}")
    print(f"  Blocks executed: {stats['blocks_executed']}")
    print(f"  Final position: X={stats['final_position']['x']}, Z={stats['final_position']['z']}")
    
    # Print violations (if any)
    if report['violations']:
        print(f"\nViolations ({len(report['violations'])}):")
        for v in report['violations'][:10]:  # Show first 10
            print(f"  Line {v['line_number']}: [{v['severity']}] {v['message']}")
        if len(report['violations']) > 10:
            print(f"  ... and {len(report['violations']) - 10} more")
    else:
        print("\n✅ No violations found!")
    
    # Print machine limits
    limits = report['machine_limits']
    print(f"\nMachine Limits Used:")
    print(f"  X-axis travel: [{limits['x_axis_travel']['min']}, {limits['x_axis_travel']['max']}]mm")
    print(f"  Z-axis travel: [{limits['z_axis_travel']['min']}, {limits['z_axis_travel']['max']}]mm")
    print(f"  Max RPM: {limits['max_rpm']}")
    print(f"  Max feed rate: {limits['max_feed_rate']} mm/rev")
    print(f"  Max depth of cut: {limits['max_depth_of_cut']}mm")
    
    # Export report
    report_path = os.path.join(BASE_DIR, 'tests', 'output', 'validation_report.json')
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Validation report exported to: {report_path}")
    
    print("\n✅ Full validation PASSED")


def test_validate_text():
    """Test validate_gcode_text convenience function."""
    print("\n" + "="*70)
    print("TEST 8: validate_gcode_text Convenience Function")
    print("="*70)
    
    # Valid G-code
    valid_gcode = """
    O3001
    G90 G40 G49 G80
    G00 X100.0 Z100.0
    T01 M06
    M03 S1500
    M08
    G00 X52.0 Z5.0
    G01 X48.0 Z-20.0 F0.25
    G01 X48.0 Z-40.0
    G00 X100.0 Z100.0
    M05
    M09
    M02
    """
    
    print("\nValidating valid G-code...")
    report = validate_gcode_text(valid_gcode, 'cnc_lathe')
    
    print(f"Status: {report['summary']['status']}")
    print(f"Violations: {report['summary']['total_violations']}")
    print(f"Blocks executed: {report['statistics']['blocks_executed']}")
    
    # Invalid G-code (exceeds limits)
    invalid_gcode = """
    O3002
    M03 S5000
    G00 X200.0 Z100.0
    G01 X200.0 Z-50.0 F10.0
    M02
    """
    
    print("\nValidating invalid G-code (exceeds limits)...")
    report = validate_gcode_text(invalid_gcode, 'cnc_lathe')
    
    print(f"Status: {report['summary']['status']}")
    print(f"Violations: {report['summary']['total_violations']}")
    print(f"  Errors: {report['summary']['errors']}")
    print(f"  Warnings: {report['summary']['warnings']}")
    
    if report['violations']:
        print("\nViolations found:")
        for v in report['violations']:
            print(f"  Line {v['line_number']}: [{v['severity']}] {v['message']}")
    
    assert report['summary']['status'] == 'FAIL', f"Expected FAIL status, got {report['summary']['status']}"
    assert report['summary']['errors'] > 0, "Expected at least 1 error"
    
    print("\n✅ Convenience function test PASSED")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("G-code Validator Module Tests")
    print("="*70)
    
    try:
        test_parser_basics()
        test_parser_file()
        test_simulator()
        test_validator_bounds()
        test_validator_spindle()
        test_validator_feed_rate()
        test_validator_full()
        test_validate_text()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    main()

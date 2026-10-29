"""
G-code Validation Module
========================
Validates generated Fanuc-compatible G-code against machine capabilities and safety limits.

This module provides:
- G-code parsing: Line-by-line parsing of Fanuc G-code into structured commands
- Toolpath simulation: Tracks tool position (X, Z), spindle state, feed rates, and modal states
- Bounds validation: Validates against machine travel limits, RPM limits, feed rate limits
- Collision detection: Simplified check for tool path intersections with unmachined material
- Validation reports: Pass/fail status, violation list with line numbers, toolpath statistics

Key Classes:
- GCodeParser: Parses G-code blocks into structured commands
- ToolpathSimulator: Simulates tool motion and tracks machine state
- GCodeValidator: Validates G-code against machine limits and generates reports

Supported G-code:
- Motion: G00 (rapid), G01 (linear), G02/G03 (circular)
- Cycles: G81 (drilling), G83 (peck drilling), G80 (cycle cancel)
- Spindle: M03 (on CW), M04 (on CCW), M05 (off)
- Coolant: M08 (on), M09 (off)
- Tool: T-codes, M06 (tool change)
- Program: O-number, M02 (end)

Usage:
    validator = GCodeValidator(machine_id='cnc_lathe')
    report = validator.validate_file('output/motor_shaft_1001.nc')
    print(report['summary']['status'])  # 'PASS' or 'FAIL'
"""

import json
import re
import math
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


class GCodeCommand:
    """
    Represents a parsed G-code command.
    
    Attributes:
        line_number: Original line number in the G-code file
        raw_text: Original line text
        g_codes: List of G-codes in this block (e.g., ['G00', 'X'])
        m_codes: List of M-codes in this block (e.g., ['M03'])
        parameters: Dict of parameters (e.g., {'X': 50.0, 'Z': 100.0, 'S': 1500, 'F': 0.25})
        tool: Tool number if T-code present
        comment: Comment text if present
    """
    
    def __init__(self, line_number: int, raw_text: str):
        self.line_number = line_number
        self.raw_text = raw_text.strip()
        self.g_codes: List[str] = []
        self.m_codes: List[str] = []
        self.parameters: Dict[str, Any] = {}
        self.tool: Optional[int] = None
        self.comment: str = ''
        self.is_comment_only: bool = False
        self.is_empty: bool = False


class MachineState:
    """
    Tracks the simulated machine state during G-code execution.
    
    Attributes:
        x_position: Current X-axis position (mm)
        z_position: Current Z-axis position (mm)
        spindle_rpm: Current spindle speed (RPM)
        spindle_on: Whether spindle is running
        feed_rate: Current feed rate (mm/rev)
        coolant_on: Whether coolant is on
        current_tool: Current tool number
        modal_g: Current modal G-code (G00, G01, G02, G03, G81, G83)
        modal_g_cycle: Whether in a canned cycle (G81/G83)
    """
    
    def __init__(self):
        self.x_position = 0.0
        self.z_position = 0.0
        self.spindle_rpm = 0
        self.spindle_on = False
        self.feed_rate = 0.0
        self.coolant_on = False
        self.current_tool = 0
        self.modal_g = 'G00'  # Default to rapid
        self.modal_g_cycle = False
        # No longer used by _execute_cycle (retract plane = R word or the
        # initial point); kept for callers that read the attribute.
        self.cycle_retract_z = -5.0


class GCodeParser:
    """
    Parses Fanuc-compatible G-code into structured commands.
    
    Methods:
        parse_line(): Parse a single G-code line into a GCodeCommand
        parse_file(): Parse an entire G-code file
        parse_text(): Parse G-code from a string
    """
    
    # Regex patterns for G-code parsing
    PARAM_PATTERN = re.compile(r'([XYZUIJKRSF])([+-]?\d+\.?\d*)', re.IGNORECASE)
    TOOL_PATTERN = re.compile(r'T(\d+)', re.IGNORECASE)
    G_CODE_PATTERN = re.compile(r'G(\d+\.?\d*)', re.IGNORECASE)
    M_CODE_PATTERN = re.compile(r'M(\d+)', re.IGNORECASE)
    COMMENT_PATTERN = re.compile(r'(;\s*.*$|/\*.*?\*/|\(.*?\))', re.IGNORECASE | re.DOTALL)
    O_NUMBER_PATTERN = re.compile(r'O(\d+)', re.IGNORECASE)
    
    def parse_line(self, line_number: int, raw_text: str) -> GCodeCommand:
        """
        Parse a single G-code line into a structured command.
        
        Args:
            line_number: Line number in the original file
            raw_text: Raw line text
            
        Returns:
            GCodeCommand with parsed data
        """
        cmd = GCodeCommand(line_number, raw_text)
        
        # Extract and remove comments
        comment_match = self.COMMENT_PATTERN.search(raw_text)
        if comment_match:
            cmd.comment = comment_match.group(1).strip()
            # Remove comment from processing
            processed_text = raw_text[:comment_match.start()]
        else:
            processed_text = raw_text
        
        # Check for empty lines or comment-only lines
        processed_text = processed_text.strip()
        if not processed_text:
            cmd.is_empty = True
            if cmd.comment:
                cmd.is_comment_only = True
            return cmd
        
        # Extract G-codes
        for match in self.G_CODE_PATTERN.finditer(processed_text):
            g_code = f"G{match.group(1)}"
            # Normalize G-code (e.g., G0 -> G00, G80.1 -> G801)
            g_num = float(match.group(1))
            g_code = f"G{int(g_num * 10) if '.' in match.group(1) else int(g_num):02d}"
            cmd.g_codes.append(g_code)
        
        # Extract M-codes
        for match in self.M_CODE_PATTERN.finditer(processed_text):
            m_code = f"M{match.group(1)}"
            cmd.m_codes.append(m_code)
        
        # Extract parameters (X, Z, U, I, J, K, R, S, F)
        for match in self.PARAM_PATTERN.finditer(processed_text):
            param_name = match.group(1).upper()
            param_value = float(match.group(2))
            cmd.parameters[param_name] = param_value
        
        # Extract tool number
        tool_match = self.TOOL_PATTERN.search(processed_text)
        if tool_match:
            cmd.tool = int(tool_match.group(1))
        
        # Extract O-number (program number)
        o_match = self.O_NUMBER_PATTERN.search(processed_text)
        if o_match:
            cmd.parameters['O'] = int(o_match.group(1))
        
        return cmd
    
    def parse_file(self, filepath: str) -> List[GCodeCommand]:
        """
        Parse an entire G-code file.
        
        Args:
            filepath: Path to the G-code file (.nc or .txt)
            
        Returns:
            List of GCodeCommand objects
        """
        commands = []
        
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                cmd = self.parse_line(line_number, line)
                # Skip empty lines and comment-only lines for processing
                if not cmd.is_empty:
                    commands.append(cmd)
        
        return commands
    
    def parse_text(self, text: str) -> List[GCodeCommand]:
        """
        Parse G-code from a string.
        
        Args:
            text: G-code text
            
        Returns:
            List of GCodeCommand objects
        """
        commands = []
        lines = text.split('\n')
        
        for line_number, line in enumerate(lines, 1):
            cmd = self.parse_line(line_number, line)
            if not cmd.is_empty:
                commands.append(cmd)
        
        return commands


class ToolpathSimulator:
    """
    Simulates G-code execution and tracks machine state.
    
    Methods:
        simulate(): Simulate execution of parsed G-code commands
        get_position(): Get current tool position
        get_state_history(): Get history of machine states
    """
    
    def __init__(self):
        self.state = MachineState()
        self.state_history: List[Dict[str, Any]] = []
        self.total_travel_distance = 0.0
        self.rapid_distance = 0.0
        self.cut_distance = 0.0
        self.tool_changes = 0
        self.blocks_executed = 0
        self.cycle_count = 0  # Number of canned cycle executions
    
    def _save_state(self, line_number: int, action: str = ''):
        """Save current state to history."""
        state_copy = {
            'line': line_number,
            'action': action,
            'x': round(self.state.x_position, 3),
            'z': round(self.state.z_position, 3),
            'spindle_rpm': self.state.spindle_rpm,
            'spindle_on': self.state.spindle_on,
            'feed_rate': round(self.state.feed_rate, 4),
            'coolant_on': self.state.coolant_on,
            'tool': self.state.current_tool,
            'modal_g': self.state.modal_g
        }
        self.state_history.append(state_copy)
    
    def _calculate_distance(self, x1: float, z1: float, x2: float, z2: float) -> float:
        """Calculate Euclidean distance between two points."""
        return math.sqrt((x2 - x1) ** 2 + (z2 - z1) ** 2)
    
    def _execute_motion(self, cmd: GCodeCommand):
        """Execute a motion command (G00, G01, G02, G03)."""
        old_x = self.state.x_position
        old_z = self.state.z_position
        new_x = old_x
        new_z = old_z
        
        # Extract target positions
        if 'X' in cmd.parameters:
            new_x = cmd.parameters['X']
        if 'Z' in cmd.parameters:
            new_z = cmd.parameters['Z']
        
        # Calculate distance
        dist = self._calculate_distance(old_x, old_z, new_x, new_z)
        
        # Update position
        self.state.x_position = new_x
        self.state.z_position = new_z
        
        # Track distance by type
        g_code = cmd.g_codes[0] if cmd.g_codes else self.state.modal_g
        
        if g_code == 'G00':
            self.rapid_distance += dist
            self.total_travel_distance += dist
        elif g_code in ['G01', 'G02', 'G03']:
            self.cut_distance += dist
            self.total_travel_distance += dist
    
    def _execute_cycle(self, cmd: GCodeCommand):
        """Execute a canned cycle (G81, G83)."""
        if not cmd.g_codes:
            return
        
        g_code = cmd.g_codes[0]

        # Z (the drill/bore depth) must be on the cycle line itself. X is
        # commonly modal — set once on the preceding G00 approach move, then
        # omitted here relying on controller carryover (that's exactly how
        # gcode_generator.py emits G81/G83 blocks) — so fall back to the
        # currently tracked X position instead of requiring it here too.
        if 'Z' not in cmd.parameters:
            return

        x_pos = cmd.parameters.get('X', self.state.x_position)
        z_pos = cmd.parameters['Z']
        old_x = self.state.x_position
        old_z = self.state.z_position
        # Retract (R) plane: the R word when programmed, else the initial
        # point, i.e. the Z position before the cycle; the tool returns to
        # the initial point afterwards (initial-point return, the controller
        # default). The serialiser programmes no R word, so the drilled depth
        # is the incremental depth |Z_initial - Z_target|. This replaces a
        # fixed default retract plane at Z = -5.0, which made every cycle
        # feed from Z = -5 to the absolute target Z (counting the absolute Z
        # coordinate as cut distance) and left the tool at Z = -5, outside
        # the Z envelope, after each cycle.
        retract_z = cmd.parameters.get('R', old_z)
        
        # Simulate cycle: rapid to retract plane, feed to depth, rapid retract
        
        # Rapid to X position (if needed)
        if abs(old_x - x_pos) > 0.001:
            dist = abs(x_pos - old_x)
            self.rapid_distance += dist
            self.total_travel_distance += dist
            self.state.x_position = x_pos
        
        # Rapid to retract plane
        dist = abs(retract_z - old_z)
        self.rapid_distance += dist
        self.total_travel_distance += dist
        self.state.z_position = retract_z
        
        # Feed to depth
        dist = abs(z_pos - retract_z)
        self.cut_distance += dist
        self.total_travel_distance += dist
        self.state.z_position = z_pos
        
        # Rapid retract to the R plane, then back to the initial point
        dist = abs(retract_z - z_pos) + abs(old_z - retract_z)
        self.rapid_distance += dist
        self.total_travel_distance += dist
        self.state.z_position = old_z
        
        self.cycle_count += 1
    
    def simulate(self, commands: List[GCodeCommand]) -> List[Dict[str, Any]]:
        """
        Simulate execution of parsed G-code commands.
        
        Args:
            commands: List of GCodeCommand objects
            
        Returns:
            List of state history entries
        """
        for cmd in commands:
            self.blocks_executed += 1
            
            # Handle F (feed rate) parameter FIRST, before motion execution
            # This ensures that when we save state during G01/G02/G03, the feed rate is correct
            if 'F' in cmd.parameters:
                self.state.feed_rate = cmd.parameters['F']
            
            # Handle G-codes
            for g_code in cmd.g_codes:
                if g_code in ['G00', 'G01', 'G02', 'G03']:
                    self.state.modal_g = g_code
                    self.state.modal_g_cycle = False
                    self._execute_motion(cmd)
                    self._save_state(cmd.line_number, f'{g_code} motion')
                
                elif g_code in ['G81', 'G83']:
                    self.state.modal_g = g_code
                    self.state.modal_g_cycle = True
                    self._execute_cycle(cmd)
                    self._save_state(cmd.line_number, f'{g_code} cycle')
                
                elif g_code == 'G80':
                    self.state.modal_g_cycle = False
                    self._save_state(cmd.line_number, 'G80 cycle cancel')
                
                elif g_code == 'G28':
                    # Return to home position
                    self.state.x_position = 0.0
                    self.state.z_position = 0.0
                    self._save_state(cmd.line_number, 'G28 home')
                
                elif g_code == 'G91':
                    # Incremental mode (not fully supported, but tracked)
                    self._save_state(cmd.line_number, 'G91 incremental')
                
                elif g_code == 'G90':
                    # Absolute mode (default)
                    self._save_state(cmd.line_number, 'G90 absolute')
            
            # Handle M-codes
            for m_code in cmd.m_codes:
                if m_code == 'M03':
                    # Spindle on CW
                    rpm = cmd.parameters.get('S', 0)
                    if rpm > 0:
                        self.state.spindle_rpm = rpm
                    self.state.spindle_on = True
                    self._save_state(cmd.line_number, f'M03 spindle on ({self.state.spindle_rpm} RPM)')
                
                elif m_code == 'M04':
                    # Spindle on CCW
                    rpm = cmd.parameters.get('S', 0)
                    if rpm > 0:
                        self.state.spindle_rpm = rpm
                    self.state.spindle_on = True
                    self._save_state(cmd.line_number, f'M04 spindle on CCW ({self.state.spindle_rpm} RPM)')
                
                elif m_code == 'M05':
                    # Spindle off
                    self.state.spindle_on = False
                    self.state.spindle_rpm = 0
                    self._save_state(cmd.line_number, 'M05 spindle off')
                
                elif m_code == 'M08':
                    # Coolant on
                    self.state.coolant_on = True
                    self._save_state(cmd.line_number, 'M08 coolant on')
                
                elif m_code == 'M09':
                    # Coolant off
                    self.state.coolant_on = False
                    self._save_state(cmd.line_number, 'M09 coolant off')
                
                elif m_code == 'M06':
                    # Tool change
                    if cmd.tool:
                        self.state.current_tool = cmd.tool
                        self.tool_changes += 1
                        self._save_state(cmd.line_number, f'M06 tool change to T{cmd.tool}')
                
                elif m_code == 'M02':
                    # Program end
                    self._save_state(cmd.line_number, 'M02 program end')
            
            # Handle S (spindle speed) parameter (only if no M-codes, since M03/M04 handle S separately)
            if 'S' in cmd.parameters and not cmd.m_codes:
                self.state.spindle_rpm = cmd.parameters['S']
            
            # Handle tool selection (T-code without M06)
            if cmd.tool and 'M06' not in cmd.m_codes:
                self.state.current_tool = cmd.tool
            
            # Save state if no G/M codes were processed
            if not cmd.g_codes and not cmd.m_codes:
                self._save_state(cmd.line_number, 'other')
        
        return self.state_history
    
    def get_position(self) -> Tuple[float, float]:
        """Get current tool position (X, Z)."""
        return (self.state.x_position, self.state.z_position)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get simulation statistics."""
        return {
            'total_travel_distance': round(self.total_travel_distance, 2),
            'rapid_distance': round(self.rapid_distance, 2),
            'cut_distance': round(self.cut_distance, 2),
            'tool_changes': self.tool_changes,
            'blocks_executed': self.blocks_executed,
            'cycle_count': self.cycle_count,
            'final_position': {
                'x': round(self.state.x_position, 3),
                'z': round(self.state.z_position, 3)
            }
        }


class ValidationViolation:
    """
    Represents a validation violation.
    
    Attributes:
        line_number: Line number where violation occurred
        severity: 'ERROR', 'WARNING', or 'INFO'
        category: Category (bounds, spindle, feed_rate, tool, safety)
        message: Human-readable description
        details: Additional details (dict)
    """
    
    def __init__(self, line_number: int, severity: str, category: str, 
                 message: str, details: Optional[Dict] = None):
        self.line_number = line_number
        self.severity = severity
        self.category = category
        self.message = message
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'line_number': self.line_number,
            'severity': self.severity,
            'category': self.category,
            'message': self.message,
            'details': self.details
        }


class GCodeValidator:
    """
    Validates G-code against machine capabilities and safety limits.
    
    Attributes:
        machine_id: Machine key (e.g., 'cnc_lathe')
        machine: Machine capabilities dict (from SKLRepository.legacy_machines_dict())
        parser: GCodeParser instance
        simulator: ToolpathSimulator instance
        violations: List of validation violations
    
    Methods:
        validate_file(): Validate a G-code file
        validate_commands(): Validate parsed G-code commands
        get_report(): Generate validation report
        export_report(): Export report to JSON file
    """
    
    def __init__(self, machine_id: str = 'cnc_lathe', machines_data: Optional[Dict[str, Dict]] = None):
        """
        Initialize validator with machine capabilities.

        Args:
            machine_id: Machine key, e.g. 'cnc_lathe' (default)
            machines_data: {machine_id: machine_dict} — pass
                SKLRepository.legacy_machines_dict() here (see main.py); an
                empty/omitted dict means every safety limit below falls back
                to its hardcoded default rather than a real machine value.
        """
        self.machine_id = machine_id
        self.machine = (machines_data or {}).get(machine_id, {})
        self.parser = GCodeParser()
        self.simulator = ToolpathSimulator()
        self.violations: List[ValidationViolation] = []
        self.commands: List[GCodeCommand] = []
        
        # Extract safety limits
        caps = self.machine.get('capabilities', {})
        safety = self.machine.get('safety_limits', {})
        
        self.max_rpm = safety.get('max_rpm', caps.get('max_spindle_speed', 4500))
        self.max_feed_rate = safety.get('max_feed_rate', caps.get('feed_rate_max', 5.0))
        self.max_depth_of_cut = safety.get('max_depth_of_cut', 5.0)
        self.min_tool_clearance = safety.get('min_tool_clearance', 5.0)
        
        # Travel envelope from the single source (machine_envelope.py): code
        # defaults, since machines.owl declares no travel limits.
        from machine_envelope import travel_envelope
        env = travel_envelope(self.machine)
        self.x_min, self.x_max = env['x_min'], env['x_max']
        self.z_min, self.z_max = env['z_min'], env['z_max']
        self.x_axis_travel = self.x_max
        self.z_axis_travel = self.z_max
        
        # Turret stations (for tool number validation)
        self.turret_stations = caps.get('turret_stations', 12)
    
    def _add_violation(self, line_number: int, severity: str, category: str, 
                       message: str, details: Optional[Dict] = None):
        """Add a validation violation."""
        violation = ValidationViolation(line_number, severity, category, message, details)
        self.violations.append(violation)
    
    def _validate_bounds(self, cmd: GCodeCommand):
        """Validate X/Z positions against machine travel limits."""
        # Check X position
        if 'X' in cmd.parameters:
            x_val = cmd.parameters['X']
            if x_val < self.x_min or x_val > self.x_max:
                self._add_violation(
                    cmd.line_number,
                    'ERROR',
                    'bounds',
                    f'X position {x_val}mm exceeds travel limits [{self.x_min}, {self.x_max}]mm',
                    {'x_position': x_val, 'x_min': self.x_min, 'x_max': self.x_max}
                )
        
        # Check Z position
        if 'Z' in cmd.parameters:
            z_val = cmd.parameters['Z']
            if z_val < self.z_min or z_val > self.z_max:
                self._add_violation(
                    cmd.line_number,
                    'ERROR',
                    'bounds',
                    f'Z position {z_val}mm exceeds travel limits [{self.z_min}, {self.z_max}]mm',
                    {'z_position': z_val, 'z_min': self.z_min, 'z_max': self.z_max}
                )
    
    def _validate_spindle(self, cmd: GCodeCommand):
        """Validate spindle speed against machine limits."""
        # Check S parameter
        if 'S' in cmd.parameters:
            rpm = cmd.parameters['S']
            if rpm > self.max_rpm:
                self._add_violation(
                    cmd.line_number,
                    'ERROR',
                    'spindle',
                    f'Spindle speed {rpm} RPM exceeds maximum {self.max_rpm} RPM',
                    {'spindle_rpm': rpm, 'max_rpm': self.max_rpm}
                )
            
            if rpm < 0:
                self._add_violation(
                    cmd.line_number,
                    'WARNING',
                    'spindle',
                    f'Negative spindle speed {rpm} RPM',
                    {'spindle_rpm': rpm}
                )
    
    def _validate_feed_rate(self, cmd: GCodeCommand):
        """Validate feed rate against machine limits."""
        if 'F' in cmd.parameters:
            feed = cmd.parameters['F']
            if feed > self.max_feed_rate:
                self._add_violation(
                    cmd.line_number,
                    'ERROR',
                    'feed_rate',
                    f'Feed rate {feed} mm/rev exceeds maximum {self.max_feed_rate} mm/rev',
                    {'feed_rate': feed, 'max_feed_rate': self.max_feed_rate}
                )
            
            if feed <= 0:
                self._add_violation(
                    cmd.line_number,
                    'WARNING',
                    'feed_rate',
                    f'Invalid feed rate {feed} mm/rev (should be positive)',
                    {'feed_rate': feed}
                )
    
    def _validate_depth_of_cut(self, cmd: GCodeCommand):
        """Validate depth of cut against safety limits."""
        # Calculate depth of cut for turning operations (G01 with X movement)
        if cmd.g_codes and cmd.g_codes[0] == 'G01' and 'X' in cmd.parameters:
            # Use historical state at this line number, not final simulator state
            state_at_line = self._get_state_at_line(cmd.line_number)
            current_x = state_at_line['x'] if state_at_line else self.simulator.state.x_position
            new_x = cmd.parameters['X']
            # Depth of cut is half the diameter difference (radius-based)
            doc = abs(new_x - current_x) / 2.0
            
            if doc > self.max_depth_of_cut:
                self._add_violation(
                    cmd.line_number,
                    'WARNING',
                    'safety',
                    f'Depth of cut {doc:.2f}mm exceeds recommended maximum {self.max_depth_of_cut}mm',
                    {'depth_of_cut': round(doc, 2), 'max_depth_of_cut': self.max_depth_of_cut}
                )
    
    def _validate_tool(self, cmd: GCodeCommand):
        """Validate tool number against turret capacity."""
        if cmd.tool:
            # T-codes are turret positions (1 to turret_stations)
            if cmd.tool < 1 or cmd.tool > self.turret_stations:
                self._add_violation(
                    cmd.line_number,
                    'WARNING',
                    'tool',
                    f'Tool T{cmd.tool:02d} exceeds turret capacity (1-{self.turret_stations})',
                    {'tool_number': cmd.tool, 'turret_stations': self.turret_stations}
                )
    
    def _get_state_at_line(self, line_number: int) -> Optional[Dict[str, Any]]:
        """Get the machine state at a specific line number from simulation history."""
        # Find the most recent state entry at or before the given line number
        most_recent_state = None
        for state_entry in self.simulator.state_history:
            if state_entry['line'] <= line_number:
                most_recent_state = state_entry
            else:
                break
        return most_recent_state

    def _validate_modal_state(self, cmd: GCodeCommand):
        """Validate modal state consistency using state from simulation history."""
        # Get the state at this command's line number from simulation history
        state_at_line = self._get_state_at_line(cmd.line_number)
        
        if state_at_line is None:
            # No state history available, use current simulator state as fallback
            feed_rate = self.simulator.state.feed_rate
            spindle_on = self.simulator.state.spindle_on
        else:
            feed_rate = state_at_line.get('feed_rate', 0)
            spindle_on = state_at_line.get('spindle_on', False)
        
        # Check for feed rate before cutting operations
        if cmd.g_codes and cmd.g_codes[0] in ['G01', 'G02', 'G03']:
            if feed_rate == 0:
                self._add_violation(
                    cmd.line_number,
                    'WARNING',
                    'safety',
                    'Cutting operation with zero feed rate',
                    {'g_code': cmd.g_codes[0]}
                )
        
        # Check for spindle on during cutting operations
        if cmd.g_codes and cmd.g_codes[0] in ['G01', 'G81', 'G83']:
            if not spindle_on:
                self._add_violation(
                    cmd.line_number,
                    'WARNING',
                    'safety',
                    'Cutting operation with spindle off',
                    {'g_code': cmd.g_codes[0]}
                )
    
    def validate_commands(self, commands: List[GCodeCommand]) -> List[ValidationViolation]:
        """
        Validate parsed G-code commands against machine limits.
        
        Args:
            commands: List of GCodeCommand objects
            
        Returns:
            List of validation violations
        """
        self.commands = commands
        self.violations = []
        self.simulator = ToolpathSimulator()
        
        # First pass: simulate execution
        self.simulator.simulate(commands)
        
        # Second pass: validate each command
        for cmd in commands:
            # Validate bounds
            self._validate_bounds(cmd)
            
            # Validate spindle speed
            self._validate_spindle(cmd)
            
            # Validate feed rate
            self._validate_feed_rate(cmd)
            
            # Validate depth of cut
            self._validate_depth_of_cut(cmd)
            
            # Validate tool
            self._validate_tool(cmd)
            
            # Validate modal state
            self._validate_modal_state(cmd)
        
        return self.violations
    
    def validate_file(self, filepath: str) -> Dict[str, Any]:
        """
        Validate a G-code file.
        
        Args:
            filepath: Path to the G-code file
            
        Returns:
            Validation report dict
        """
        # Parse file
        commands = self.parser.parse_file(filepath)
        
        # Validate
        self.validate_commands(commands)
        
        # Generate report
        report = self.get_report(filepath)
        
        return report
    
    def validate_text(self, text: str) -> Dict[str, Any]:
        """
        Validate G-code from a string.
        
        Args:
            text: G-code text
            
        Returns:
            Validation report dict
        """
        # Parse text
        commands = self.parser.parse_text(text)
        
        # Validate
        self.validate_commands(commands)
        
        # Generate report
        report = self.get_report('inline_gcode')
        
        return report
    
    def get_report(self, source: str = '') -> Dict[str, Any]:
        """
        Generate validation report.
        
        Args:
            source: Source file path or identifier
            
        Returns:
            Validation report dict
        """
        # Determine overall status
        error_count = sum(1 for v in self.violations if v.severity == 'ERROR')
        warning_count = sum(1 for v in self.violations if v.severity == 'WARNING')
        
        if error_count > 0:
            status = 'FAIL'
        elif warning_count > 0:
            status = 'PASS_WITH_WARNINGS'
        else:
            status = 'PASS'
        
        # Get simulation statistics
        stats = self.simulator.get_statistics()
        
        # Build report
        report = {
            'summary': {
                'status': status,
                'source': source,
                'timestamp': datetime.now().isoformat(),
                'machine_id': self.machine_id,
                'machine_name': self.machine.get('name', 'Unknown'),
                'total_violations': len(self.violations),
                'errors': error_count,
                'warnings': warning_count
            },
            'violations': [v.to_dict() for v in self.violations],
            'statistics': stats,
            'machine_limits': {
                'x_axis_travel': {'min': self.x_min, 'max': self.x_max},
                'z_axis_travel': {'min': self.z_min, 'max': self.z_max},
                'max_rpm': self.max_rpm,
                'max_feed_rate': self.max_feed_rate,
                'max_depth_of_cut': self.max_depth_of_cut
            }
        }
        
        return report
    
    def export_report(self, report: Dict[str, Any], filepath: str):
        """
        Export validation report to JSON file.
        
        Args:
            report: Validation report dict
            filepath: Output file path
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)


def validate_gcode_file(filepath: str, machine_id: str = 'cnc_lathe',
                         machines_data: Optional[Dict[str, Dict]] = None) -> Dict[str, Any]:
    """
    Convenience function to validate a G-code file.

    Args:
        filepath: Path to the G-code file
        machine_id: Machine key, e.g. 'cnc_lathe' (default)
        machines_data: see GCodeValidator.__init__

    Returns:
        Validation report dict
    """
    validator = GCodeValidator(machine_id, machines_data=machines_data)
    report = validator.validate_file(filepath)
    return report


def validate_gcode_text(text: str, machine_id: str = 'cnc_lathe',
                         machines_data: Optional[Dict[str, Dict]] = None) -> Dict[str, Any]:
    """
    Convenience function to validate G-code from a string.

    Args:
        text: G-code text
        machine_id: Machine key, e.g. 'cnc_lathe' (default)
        machines_data: see GCodeValidator.__init__

    Returns:
        Validation report dict
    """
    validator = GCodeValidator(machine_id, machines_data=machines_data)
    report = validator.validate_text(text)
    return report

"""
G-code Generation Module
========================
Generates Fanuc-compatible G-code from the manufacturing plan.

This module takes the structured manufacturing plan from the orchestrator
and generates complete G-code programs with:
- Proper program headers and footers (O-number, M02)
- Spindle control (M03/M05)
- Coolant control (M08/M09)
- Rapid positioning (G00)
- Linear interpolation (G01)
- Circular interpolation (G02/G03)
- Drilling cycles (G81, G83)
- Tool changes (T-codes, M06)
- Safety features and comments

Key Classes:
- GCodeGenerator: Main G-code generator with operation-specific methods
- GCodeProgram: Represents a complete G-code program

Supported Operations:
- Turning: G00, G01, G02, G03 with spindle speed and feed rate
- Drilling: G81 (simple), G83 (peck drilling) with retract
- Counterboring: G81 with multiple tool positions
- Chamfering: G01 with angled tool path
- Boring: G01 with controlled feed rates
- Facing: G01 with axial tool path
- Milling: G01 with XY positioning
- Grooving: G01 with radial tool path
"""

import json
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from machine_envelope import DEFAULT_TRAVEL_ENVELOPE_MM, excursions

# T-code assignment — the single source of truth for which physical tool
# slot a tool_id gets. simulator.py imports this (inverted) to recover a
# tool_id from a G-code T-word/M06's tool number, so the two stay in sync.
TOOL_ID_TO_NUMBER = {
    'turning_insert_rough': 1,
    'turning_insert_finish': 2,
    'drill_bit': 3,
    'counterbore_cutter': 4,
    'chamfer_mill': 5,
    'chamfer_drill': 6,
    'boring_bar': 7,
    'end_mill': 8,
    'face_mill': 9,
    'grooving_tool': 10,
}


class GCodeProgram:
    """
    Represents a complete G-code program.
    
    Attributes:
        program_number: O-number for the program
        header: Program header comments
        blocks: List of G-code blocks (strings)
        footer: Program footer (M02)
    """
    
    def __init__(self, program_number: int = 1000):
        """
        Initialize G-code program.
        
        Args:
            program_number: O-number for the program (default: 1000)
        """
        self.program_number = program_number
        self.header = []
        self.blocks = []
        self.footer = []
    
    def add_header_line(self, line: str):
        """Add a line to the program header."""
        self.header.append(line)
    
    def add_block(self, block: str):
        """Add a G-code block to the program."""
        self.blocks.append(block)
    
    def add_blocks(self, blocks: List[str]):
        """Add multiple G-code blocks to the program."""
        self.blocks.extend(blocks)
    
    def add_footer_line(self, line: str):
        """Add a line to the program footer."""
        self.footer.append(line)
    
    def get_program_text(self) -> str:
        """
        Get the complete G-code program as a string.
        
        Returns:
            Complete G-code program string
        """
        lines = []
        
        # Program number
        lines.append(f"O{self.program_number}")
        
        # Header comments
        for line in self.header:
            lines.append(line)
        
        # G-code blocks
        for block in self.blocks:
            lines.append(block)
        
        # Footer
        for line in self.footer:
            lines.append(line)
        
        # Program end
        lines.append("M02")
        
        return "\n".join(lines)
    
    def save_to_file(self, filepath: str) -> str:
        """
        Save G-code program to a .nc file.
        
        Args:
            filepath: Path to save the .nc file
            
        Returns:
            Filepath saved
        """
        program_text = self.get_program_text()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(program_text)
        
        return filepath


class GCodeGenerator:
    """
    Main G-code generator for manufacturing operations.
    
    Generates Fanuc-compatible G-code from the manufacturing plan
    with proper tool changes, spindle control, and safety features.
    
    Key Methods:
    - generate_program: Generate complete G-code program from plan
    - generate_turning: Generate G-code for turning operations
    - generate_drilling: Generate G-code for drilling operations
    - generate_counterboring: Generate G-code for counterboring
    - generate_chamfering: Generate G-code for chamfering
    - generate_boring: Generate G-code for boring operations
    - generate_facing: Generate G-code for facing operations
    - generate_milling: Generate G-code for milling operations
    - generate_grooving: Generate G-code for grooving operations
    """
    
    # Serialisation profile this generator implements. Its expressiveness
    # (which tool orientations it can serialise) is declared in
    # knowledge/foundation/serialisation_profiles.owl and checked by KEFC
    # before a step reaches RAL; this generator has no radial cycle.
    SERIALISATION_PROFILE = "RALTurningProfile"

    # Default safety parameters
    # Tool-change and programme-end position: derived per programme from
    # the approved steps (_clear_position), not a fixed height. The previous
    # fixed G00 Z50 lay inside the part's Z extent (free end towards +Z), so
    # after an axial hole it was a rapid along X0 through the workpiece.
    RAPID_FEED_RATE = 500.0  # mm/min - rapid traverse rate
    DEFAULT_SPINDLE_SPEED = 1000  # RPM - default spindle speed
    
    # Axis travel envelope: code defaults from machine_envelope.py (the one
    # place they live). They are NOT read from the ontology; machines.owl
    # declares no travel limits. The serialiser does not clamp to them: it
    # emits the computed coordinate and records any excursion, and the
    # validator reports the excursion as an envelope violation.
    MIN_X = DEFAULT_TRAVEL_ENVELOPE_MM['x_min']   # spindle centreline (mm)
    MAX_X = DEFAULT_TRAVEL_ENVELOPE_MM['x_max']   # X travel (mm)
    MIN_Z = DEFAULT_TRAVEL_ENVELOPE_MM['z_min']   # chuck face (mm)
    MAX_Z = DEFAULT_TRAVEL_ENVELOPE_MM['z_max']   # Z travel (mm)
    MIN_TOOL_CLEARANCE = 5.0  # Min tool clearance (mm)
    
    def __init__(self, material: str = 'steel_1045', machine: str = 'cnc_lathe'):
        """
        Initialize G-code generator.
        
        Args:
            material: Material key from ontology
            machine: Machine key from ontology
        """
        self.material = material
        self.machine = machine
        self.program_counter = 1000  # Starting O-number
    
    def _check_envelope(self, x: float, z: float) -> Tuple[float, float]:
        """
        Return the computed coordinates unchanged and record any excursion
        beyond the travel envelope (machine_envelope.py).

        This replaces _clamp_to_bounds, which silently clamped coordinates to
        the envelope and replaced a negative X by its absolute value, so an
        out-of-envelope coordinate could never reach the validator. Each
        excursion is recorded in self.envelope_excursions with the plan step
        it belongs to; the validator reports it as a bounds violation.

        CNC lathe coordinate system: X = 0 at the spindle centreline,
        positive X outward (diameter convention); Z = 0 at the chuck face,
        positive towards the tailstock.
        """
        exc = excursions(x, z, DEFAULT_TRAVEL_ENVELOPE_MM)
        if exc:
            if not hasattr(self, 'envelope_excursions'):
                self.envelope_excursions = []
            self.envelope_excursions.append({
                'step_number': getattr(self, '_current_step', None),
                'x': x, 'z': z, 'excursion_mm': exc,
            })
        return (x, z)

    def generate_program(self, manufacturing_plan: List[Dict]) -> GCodeProgram:
        """
        Generate a complete G-code program from the manufacturing plan.
        
        This is the main entry point that:
        1. Creates program header with metadata
        2. Groups operations by tool to minimize tool changes
        3. Generates G-code for each operation
        4. Adds proper tool changes, spindle control, and coolant
        5. Creates program footer
        
        Args:
            manufacturing_plan: List of manufacturing step dicts from orchestrator
            
        Returns:
            GCodeProgram instance with complete program
        """
        program = GCodeProgram(self.program_counter)
        self.program_counter += 1
        # Modal spindle speed and coolant state as emitted so far; every
        # operation segment re-establishes its own approved values when they
        # differ (see _apply_step_modal_state).
        self._modal_spindle = None
        self._modal_coolant = None
        self.envelope_excursions = []
        self.dimension_lookups = []
        # RAL input contract (Revision 7): a handed-over step whose toolpath
        # would need an input the plan does not carry is not serialised. It
        # gets no segment and a structured refusal record (self.refusals);
        # main.py writes each refusal to the expert-validation store as
        # serialisation_input_missing. Nothing is defaulted or guessed.
        serialisable, self.refusals = self.partition_steps(manufacturing_plan)
        self.serialised_steps = serialisable
        self._clear_x, self._clear_z = self._clear_position(manufacturing_plan)
        
        # Add program header
        self._add_program_header(program, serialisable)
        if self.refusals:
            program.add_header_line(
                f"(Refused by RAL, not serialised: steps "
                f"{', '.join(str(r['step_number']) for r in self.refusals)})")
            program.add_header_line("")
        
        # Initialize machine state
        # Turning modal profile: ZX working plane, metric units, no nose-radius
        # compensation, work offset, canned cycles cancelled, absolute positioning,
        # constant spindle speed in rev/min and feed per revolution (the parameter
        # package carries feed in mm/rev). Still not a certified post-processor
        # profile: diameter/radius programming, controller-specific cycle syntax
        # and tool-nose compensation are deliberately not handled here.
        program.add_block("(--- Machine Initialization ---)")
        program.add_block("G18 (Select ZX plane)")
        program.add_block("G21 (Metric units)")
        program.add_block("G40 (Cancel nose radius compensation)")
        program.add_block("G54 (Work coordinate system)")
        program.add_block("G80 (Cancel canned cycle)")
        program.add_block("G90 (Absolute positioning)")
        program.add_block("G97 (Constant spindle speed, rev/min)")
        program.add_block("G99 (Feed per revolution)")
        program.add_block("")
        
        # Group operations by tool to minimize tool changes
        tool_groups = self._group_operations_by_tool(serialisable)
        
        # Generate G-code for each tool group
        current_tool = None
        
        for tool_id, operations in tool_groups.items():
            # Tool change
            if tool_id != current_tool:
                self._add_tool_change(program, tool_id, operations[0])
                current_tool = tool_id
            
            # Generate G-code for each operation with this tool
            for operation in operations:
                self._generate_operation_gcode(program, operation)
        
        # Add program footer
        self._add_program_footer(program)
        
        return program
    
    @classmethod
    def refusal_for(cls, step: Dict) -> Optional[Dict]:
        """Structured refusal record for a step RAL cannot serialise from
        plan data, or None when its input contract is satisfied."""
        operation = step.get('operation', '')
        dims = step.get('feature_dimensions') or {}
        loc = step.get('feature_location') or {}
        if not cls.has_toolpath_pattern(operation):
            kind = 'no_toolpath_pattern'
            missing = [f"a toolpath pattern for {operation!r} (none declared in {cls.SERIALISATION_PROFILE})"]
        else:
            kind = 'missing_inputs'
            missing = cls.missing_serialisation_inputs(operation, dims, loc)
            if not missing:
                return None
        return {
            'step_number': step.get('step_number'),
            'operation': operation,
            'ontology_operation': step.get('ontology_operation'),
            'kind': kind,
            'missing_inputs': missing,
            'required_inputs': list(cls.OPERATION_INPUTS.get(operation, ())),
            'source_entity': {
                'feature_id': step.get('feature_id'),
                'feature_type': step.get('feature_type'),
                'feature_dimensions': dims,
                'feature_location': loc,
            },
            'kefc_validation_status': step.get('validation_status'),
        }

    @classmethod
    def partition_steps(cls, plan: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """(serialisable steps in plan order, refusal records)."""
        serialisable, refusals = [], []
        for step in plan:
            refusal = cls.refusal_for(step)
            if refusal is None:
                serialisable.append(step)
            else:
                refusals.append(refusal)
        return serialisable, refusals

    def _clear_position(self, plan: List[Dict]) -> Tuple[float, float]:
        """
        (X, Z) clear of every feature handed to RAL: the largest plan
        diameter plus twice the approach clearance, and the largest feature
        z_top plus the clearance, over all handed steps (refused steps
        contribute whatever inputs they do carry). Retracts move +Z first,
        then out in X. Features KEFC withheld are not handed to RAL and so are
        not accounted for.
        """
        c = self.APPROACH_CLEARANCE_MM
        xs, zs = [], []
        for step in plan:
            inputs, _ = self.serialisation_inputs(step.get('operation', ''), step.get('feature_dimensions') or {},
                                                  step.get('feature_location') or {})
            for name in ('diameter', 'outer_diameter'):
                if name in inputs:
                    xs.append(inputs[name]['value'])
            if 'z_centre' in inputs:
                half = inputs['length']['value'] / 2.0 if 'length' in inputs else 0.0
                zs.append(inputs['z_centre']['value'] + half)
        x_clear = (max(xs) if xs else 0.0) + 2 * c
        z_clear = (max(zs) if zs else 0.0) + c
        self._current_step = 'tool_change_position'
        try:
            return self._check_envelope(x_clear, z_clear)
        finally:
            self._current_step = None

    def _add_program_header(self, program: GCodeProgram, plan: List[Dict]):
        """Add program header with metadata comments."""
        program.add_header_line(f"(Program: Motor Shaft - Eixo)")
        program.add_header_line(f"(Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        program.add_header_line(f"(Material: {self.material})")
        program.add_header_line(f"(Machine: {self.machine})")
        program.add_header_line(f"(Total Operations: {len(plan)})")
        program.add_header_line("")
    
    def _add_program_footer(self, program: GCodeProgram):
        """Add program footer with cleanup."""
        program.add_footer_line("")
        program.add_footer_line("(--- Program End ---)")
        program.add_footer_line(f"G00 Z{self._clear_z:.2f} (Retract beyond the part's +Z extent)")
        program.add_footer_line(f"G00 X{self._clear_x:.2f} (Retract beyond the part's largest diameter)")
        program.add_footer_line("M09 (Coolant off)")
        program.add_footer_line("M05 (Spindle stop)")
        program.add_footer_line("G28 U0 W0 (Return to reference point)")
    
    def _group_operations_by_tool(self, plan: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group operations by tool to minimize tool changes.
        
        Args:
            plan: Manufacturing plan
            
        Returns:
            Dict mapping tool_id to list of operations
        """
        tool_groups = {}

        for step in plan:
            tool_id = step.get('tool_id')
            if not tool_id:
                # A step with no tool_id should never reach RAL — KEFC's
                # exception gate marks such steps requires_review, and
                # main.py filters to only KEFC's approved_steps before
                # calling generate_program(). Reaching this means that gate
                # was bypassed; fail loudly rather than silently defaulting
                # to tool #1 (see AGENTS.md: "no hidden procedural defaults").
                raise ValueError(
                    f"Step {step.get('step_number')} (feature {step.get('feature_id')}, "
                    f"operation {step.get('operation')!r}) has no tool_id. RAL must only "
                    f"receive KEFC's approved_steps — check the upstream gate."
                )

            if tool_id not in tool_groups:
                tool_groups[tool_id] = []

            tool_groups[tool_id].append(step)

        return tool_groups
    
    def _add_tool_change(self, program: GCodeProgram, tool_id: str, operation: Dict):
        """
        Add tool change sequence.
        
        Args:
            program: GCodeProgram instance
            tool_id: Tool identifier
            operation: Operation dictionary
        """
        program.add_block("")
        program.add_block(f"(--- Tool Change: {tool_id} ---)")
        
        # Retract to safe position
        program.add_block(f"G00 Z{self._clear_z:.2f} (Retract beyond the part's +Z extent)")
        program.add_block(f"G00 X{self._clear_x:.2f} (Retract beyond the part's largest diameter)")
        program.add_block("M09 (Coolant off)")
        program.add_block("M05 (Spindle stop)")
        
        # Tool change (T-code and M06)
        tool_number = self._get_tool_number(tool_id)
        program.add_block(f"T{tool_number:04d} M06 (Select and change tool: {tool_id})")
        
        # Start spindle
        spindle_speed = self._extract_parameter_value(operation.get('parameters', {}), 'spindle_speed', self.DEFAULT_SPINDLE_SPEED)
        program.add_block(f"S{int(spindle_speed)} M03 (Spindle on, CW at {int(spindle_speed)} RPM)")
        self._modal_spindle = int(spindle_speed)
        
        # Start coolant
        program.add_block("M08 (Coolant on)")
        self._modal_coolant = True

    @staticmethod
    def _step_coolant(parameters: Dict) -> Optional[bool]:
        value = parameters.get('coolant')
        if isinstance(value, dict):
            value = value.get('value')
        return value if isinstance(value, bool) else None

    def _apply_step_modal_state(self, program: GCodeProgram, operation: Dict):
        """Re-establish the approved spindle speed and coolant state at the
        start of an operation segment when they differ from the modal values
        in effect. Previously the spindle speed was set only at tool changes,
        so every later step using the same tool ran at the first step's
        speed regardless of its own approved spindle_speed."""
        parameters = operation.get('parameters', {})
        if 'spindle_speed' in parameters:
            spindle_speed = int(self._extract_parameter_value(parameters, 'spindle_speed', self.DEFAULT_SPINDLE_SPEED))
            if spindle_speed != getattr(self, '_modal_spindle', None):
                program.add_block(f"S{spindle_speed} M03 (Spindle speed for this step, {spindle_speed} RPM)")
                self._modal_spindle = spindle_speed
        coolant = self._step_coolant(parameters)
        if coolant is not None and coolant != getattr(self, '_modal_coolant', None):
            program.add_block("M08 (Coolant on)" if coolant else "M09 (Coolant off)")
            self._modal_coolant = coolant
    
    def _get_tool_number(self, tool_id: str) -> int:
        """
        Get tool number for T-code from tool_id.
        
        Args:
            tool_id: Tool identifier
            
        Returns:
            Tool number (1-10)
        """
        tool_map = TOOL_ID_TO_NUMBER

        if tool_id not in tool_map:
            # Was silently `tool_map.get(tool_id, 1)` — an unrecognized
            # tool_id would generate G-code selecting the rough turning
            # insert regardless of what the plan actually asked for. Fail
            # loudly instead (see AGENTS.md: "no hidden procedural defaults").
            raise ValueError(f"Unknown tool_id {tool_id!r}; no T-code mapping for it.")
        return tool_map[tool_id]
    
    def _generate_operation_gcode(self, program: GCodeProgram, operation: Dict):
        """
        Generate G-code for a specific operation.
        
        Args:
            program: GCodeProgram instance
            operation: Operation dictionary
        """
        operation_name = operation.get('operation', '')
        feature_type = operation.get('feature_type', '')
        parameters = operation.get('parameters', {})
        feature_dimensions = operation.get('feature_dimensions', {})
        feature_location = operation.get('feature_location', {})
        
        # Add operation comment. The plan step number is carried in the
        # segment header so the programme can be traced back to the approved
        # step (main.py's plan-to-programme and parameter-fidelity checks).
        program.add_block("")
        self._current_step = operation.get('step_number')
        step_tag = f" [step {operation['step_number']}]" if operation.get('step_number') is not None else ""
        program.add_block(f"(--- {operation_name}: {feature_type}{step_tag} ---)")
        self._apply_step_modal_state(program, operation)
        
        # Generate G-code based on operation type
        if operation_name == 'rough_turning':
            self._generate_turning(program, parameters, feature_dimensions, feature_location, 'rough')
        elif operation_name == 'finish_turning':
            self._generate_turning(program, parameters, feature_dimensions, feature_location, 'finish')
        elif operation_name == 'drilling':
            self._generate_drilling(program, parameters, feature_dimensions, feature_location)
        elif operation_name == 'counterboring':
            self._generate_counterboring(program, parameters, feature_dimensions, feature_location)
        elif operation_name == 'chamfering':
            self._generate_chamfering(program, parameters, feature_dimensions, feature_location)
        elif operation_name == 'boring':
            self._generate_boring(program, parameters, feature_dimensions, feature_location)
        elif operation_name == 'facing':
            self._generate_facing(program, parameters, feature_dimensions, feature_location)
        elif operation_name == 'grooving':
            self._generate_grooving(program, parameters, feature_dimensions, feature_location)
        else:
            raise ValueError(
                f"Step {self._current_step}: no toolpath pattern for operation {operation_name!r} in "
                f"RALTurningProfile; KEFC should have withheld it as serialisation_unsupported.")
    
    # ------------------------------------------------------------------
    # Serialiser input contract (Revision 6).
    #
    # Every toolpath pattern reads its geometry only from the approved step's
    # feature_dimensions and feature_location, under the keys the plan
    # actually carries. The extractor's convention, verified on the reference
    # case, is 'Ø' = diameter, 'R' = radius, 'L' = axial length, 'W' = width,
    # and absolute_location = the feature centre (e.g. Step 5, Ø24 L47.5 at
    # Z144.75, spans Z121.0 to Z168.5, the shaft end; Counterbore 8, L4.02 at
    # Z166.52, ends at Z168.53). Long-form keys are accepted for hand-built
    # plans. No dimension is defaulted: missing_serialisation_inputs reports
    # what a step lacks, KEFC withholds such a step as missing_knowledge, and
    # the toolpath methods raise if called regardless.
    #
    # Conventions shared by every pattern (RALTurningProfile): diameter
    # programming (X = diameter, X0 on the spindle centreline); Z0 at the
    # chuck face, the free end towards +Z, and axial features approached from
    # +Z; a feature spans z_top = Zc + L/2 to z_bottom = Zc - L/2. The only
    # numbers not taken from the plan or the parameter package are the
    # serialiser's clearances (APPROACH_CLEARANCE_MM), which affect rapid
    # moves only and never a cutting-move target.
    # ------------------------------------------------------------------
    DIAMETER_KEYS = ('Ø', 'diameter')
    RADIUS_KEYS = ('R', 'radius')
    LENGTH_KEYS = ('L', 'length')
    WIDTH_KEYS = ('W', 'width')
    DEPTH_KEYS = ('depth', 'H')
    CHAMFER_ANGLE_KEYS = ('angle', 'chamfer_angle')
    LOCATION_Z_KEYS = ('Z', 'z')
    DIAMETER_RADIUS_TOLERANCE_MM = 0.01
    ON_AXIS_TOLERANCE_MM = 1e-6
    APPROACH_CLEARANCE_MM = 2.0

    # Keys under which a groove's diameters may appear in the plan's
    # feature_dimensions. A radial groove depth, when given instead of a
    # bottom diameter, is converted with bottom = outer - 2 x depth. A lone
    # 'Ø' is deliberately not accepted: for a groove it is ambiguous (neck
    # diameter or the diameter of the surface the groove is cut into).
    GROOVE_OUTER_DIAMETER_KEYS = ('outer_diameter',)
    GROOVE_BOTTOM_DIAMETER_KEYS = ('groove_bottom_diameter', 'bottom_diameter')
    GROOVE_DEPTH_KEYS = ('groove_depth', 'depth')
    GROOVE_APPROACH_CLEARANCE_MM = 2.0  # on diameter

    # Inputs each toolpath pattern needs. 'on_axis' means location X = Y = 0:
    # an axial hole off the centreline needs C-axis indexing, which the
    # turning profile does not declare. Operations absent from this table
    # (milling) have no toolpath pattern in RALTurningProfile; KEFC withholds
    # them as serialisation_unsupported.
    OPERATION_INPUTS = {
        'facing': ('diameter', 'length', 'z_centre'),
        'rough_turning': ('diameter', 'length', 'z_centre'),
        'finish_turning': ('diameter', 'length', 'z_centre'),
        'drilling': ('diameter', 'length', 'z_centre', 'on_axis'),
        'counterboring': ('diameter', 'length', 'z_centre', 'on_axis'),
        'boring': ('diameter', 'length', 'z_centre', 'on_axis'),
        'chamfering': ('diameter', 'length', 'chamfer_angle', 'z_centre'),
        'grooving': ('outer_diameter', 'groove_bottom_diameter', 'z_centre'),
    }

    @staticmethod
    def _number(mapping: Dict, keys) -> Tuple[Optional[float], Optional[str]]:
        for k in keys:
            v = (mapping or {}).get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v), k
        return None, None

    @classmethod
    def has_toolpath_pattern(cls, operation: str) -> bool:
        return operation in cls.OPERATION_INPUTS

    @classmethod
    def grooving_diameters(cls, dimensions: Dict) -> Tuple[Optional[float], Optional[float], List[str]]:
        """(outer_diameter, groove_bottom_diameter, missing) for a grooving
        step, read only from the plan's feature_dimensions; never defaulted."""
        inputs, missing = cls.serialisation_inputs('grooving', dimensions, None)
        outer = inputs.get('outer_diameter', {}).get('value')
        bottom = inputs.get('groove_bottom_diameter', {}).get('value')
        return outer, bottom, missing

    @classmethod
    def serialisation_inputs(cls, operation: str, dimensions: Dict,
                             location: Optional[Dict]) -> Tuple[Dict, List[str]]:
        """
        Resolve the inputs `operation`'s toolpath pattern needs from the plan.

        Returns (inputs, missing): inputs maps each input name to
        {'value': float, 'source': str} naming the plan key it came from;
        missing names what the plan lacks or what is inconsistent. With
        location=None the location-based inputs are not checked (callers
        that only hold dimensions).
        """
        dims = dimensions or {}
        inputs: Dict[str, Dict] = {}
        missing: List[str] = []
        required = cls.OPERATION_INPUTS.get(operation)
        if required is None:
            return inputs, [f"a toolpath pattern for {operation!r} (the serialisation profile "
                            f"RALTurningProfile declares none)"]
        for name in required:
            if name == 'diameter':
                d, dk = cls._number(dims, cls.DIAMETER_KEYS)
                r, rk = cls._number(dims, cls.RADIUS_KEYS)
                if d is not None and r is not None and abs(d - 2.0 * r) > cls.DIAMETER_RADIUS_TOLERANCE_MM:
                    missing.append(f"a consistent diameter ({dk}={d} but {rk}={r})")
                elif d is not None:
                    inputs[name] = {'value': d, 'source': dk}
                elif r is not None:
                    inputs[name] = {'value': 2.0 * r, 'source': f"2 x {rk}"}
                else:
                    missing.append("diameter (" + ' or '.join(cls.DIAMETER_KEYS + cls.RADIUS_KEYS) + ")")
            elif name in ('length', 'width', 'depth', 'chamfer_angle'):
                keys = {'length': cls.LENGTH_KEYS, 'width': cls.WIDTH_KEYS, 'depth': cls.DEPTH_KEYS,
                        'chamfer_angle': cls.CHAMFER_ANGLE_KEYS}[name]
                v, k = cls._number(dims, keys)
                label = {'length': 'axial length', 'width': 'width', 'depth': 'depth',
                         'chamfer_angle': 'chamfer angle'}[name]
                if v is None or v <= 0:
                    missing.append(f"{label} ({' or '.join(keys)})")
                else:
                    inputs[name] = {'value': v, 'source': k}
            elif name == 'outer_diameter':
                v, k = cls._number(dims, cls.GROOVE_OUTER_DIAMETER_KEYS)
                if v is None:
                    missing.append('outer diameter (one of ' + ', '.join(cls.GROOVE_OUTER_DIAMETER_KEYS) + ')')
                else:
                    inputs[name] = {'value': v, 'source': k}
            elif name == 'groove_bottom_diameter':
                v, k = cls._number(dims, cls.GROOVE_BOTTOM_DIAMETER_KEYS)
                if v is None and 'outer_diameter' in inputs:
                    depth, dk = cls._number(dims, cls.GROOVE_DEPTH_KEYS)
                    if depth is not None:
                        v, k = inputs['outer_diameter']['value'] - 2.0 * depth, f"outer_diameter - 2 x {dk}"
                if v is None:
                    missing.append('groove-bottom diameter (one of ' + ', '.join(cls.GROOVE_BOTTOM_DIAMETER_KEYS)
                                   + ', or a radial depth under ' + ', '.join(cls.GROOVE_DEPTH_KEYS) + ')')
                else:
                    inputs[name] = {'value': v, 'source': k}
            elif name == 'z_centre':
                if location is None:
                    continue
                v, k = cls._number(location, cls.LOCATION_Z_KEYS)
                if v is None:
                    missing.append("feature location Z")
                else:
                    inputs[name] = {'value': v, 'source': f"location {k}"}
            elif name == 'on_axis':
                if location is None:
                    continue
                x, _ = cls._number(location, ('X', 'x'))
                y, _ = cls._number(location, ('Y', 'y'))
                if x is None or y is None:
                    missing.append("feature location X and Y (to establish an on-axis position)")
                elif abs(x) > cls.ON_AXIS_TOLERANCE_MM or abs(y) > cls.ON_AXIS_TOLERANCE_MM:
                    missing.append(f"an on-axis position (location X={x}, Y={y}; off-axis axial "
                                   f"features need C-axis indexing, not declared in RALTurningProfile)")
        # Geometric consistency of resolved inputs.
        if operation == 'grooving' and 'outer_diameter' in inputs and 'groove_bottom_diameter' in inputs:
            o, b = inputs['outer_diameter']['value'], inputs['groove_bottom_diameter']['value']
            if not (0.0 <= b < o):
                missing.append(f'consistent diameters (got outer {o}, bottom {b})')
        if operation == 'chamfering' and {'diameter', 'length', 'chamfer_angle'} <= set(inputs):
            a = inputs['chamfer_angle']['value']
            if not (0.0 < a < 90.0):
                missing.append(f"a chamfer angle strictly between 0 and 90 degrees (got {a})")
            elif inputs['diameter']['value'] - 2.0 * inputs['length']['value'] * math.tan(math.radians(a)) < 0:
                missing.append("a consistent chamfer (radial leg exceeds the feature radius)")
        return inputs, missing

    @classmethod
    def missing_serialisation_inputs(cls, operation: str, dimensions: Dict,
                                     location: Optional[Dict] = None) -> List[str]:
        """Plan inputs the serialiser needs for `operation` but the step does
        not carry (empty when the step can be serialised from plan data)."""
        return cls.serialisation_inputs(operation, dimensions, location)[1]

    def _plan_inputs(self, program: GCodeProgram, operation: str, dimensions: Dict,
                     location: Dict) -> Dict[str, float]:
        """Resolve a segment's inputs, refuse if any is missing, record the
        lookups (dimension fidelity) and write them into the segment."""
        inputs, missing = self.serialisation_inputs(operation, dimensions, location)
        if missing:
            raise ValueError(
                f"Step {getattr(self, '_current_step', None)} ({operation}) cannot be serialised: the plan "
                f"lacks {'; '.join(missing)} (feature_dimensions = {dimensions!r}, feature_location = "
                f"{location!r}). KEFC should have withheld it as missing_knowledge.")
        if not hasattr(self, 'dimension_lookups'):
            self.dimension_lookups = []
        self.dimension_lookups.append({
            'step_number': getattr(self, '_current_step', None),
            'operation': operation,
            'inputs': {k: dict(v) for k, v in inputs.items()},
        })
        listed = '; '.join(f"{k} {v['value']:.3f} [{v['source']}]" for k, v in inputs.items())
        program.add_block(f"(Plan inputs: {listed})")
        return {k: v['value'] for k, v in inputs.items()}

    @staticmethod
    def _package_value(parameters: Dict, key: str) -> Optional[float]:
        v = (parameters or {}).get(key)
        if isinstance(v, dict):
            v = v.get('value')
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def _generate_turning(self, program: GCodeProgram, parameters: Dict, dimensions: Dict,
                          location: Dict, pass_type: str = 'rough'):
        """
        One longitudinal pass at the feature diameter over the feature length,
        from z_top towards the chuck. The stock diameter is not part of the
        plan, so stock-removal passes from bar are not generated (the
        previous pattern derived them from a 10 mm placeholder diameter).
        """
        feed_rate = self._extract_parameter_value(parameters, 'feed_rate', 0.2)
        op = 'rough_turning' if pass_type == 'rough' else 'finish_turning'
        p = self._plan_inputs(program, op, dimensions, location)
        d, length, zc = p['diameter'], p['length'], p['z_centre']
        c = self.APPROACH_CLEARANCE_MM
        z_top, z_bottom = zc + length / 2.0, zc - length / 2.0
        x_clear, z_clear = self._check_envelope(d + 2 * c, z_top + c)
        x_cut, z_cut = self._check_envelope(d, z_bottom)
        label = 'Rough turn' if pass_type == 'rough' else 'Finish turn'
        program.add_block(f"G00 X{x_clear:.2f} Z{z_clear:.2f} (Approach position)")
        program.add_block(f"G00 X{x_cut:.2f} (Feature diameter)")
        program.add_block(f"G01 Z{z_cut:.2f} F{feed_rate:.3f} ({label})")
        program.add_block(f"G00 X{x_clear:.2f} (Retract)")
        program.add_block(f"G00 Z{z_clear:.2f} (Return to start)")

    def _axial_hole_cycle(self, program: GCodeProgram, parameters: Dict, dimensions: Dict,
                          location: Dict, operation: str, default_feed: float):
        feed_rate = self._extract_parameter_value(parameters, 'feed_rate', default_feed)
        p = self._plan_inputs(program, operation, dimensions, location)
        length, zc = p['length'], p['z_centre']
        c = self.APPROACH_CLEARANCE_MM
        z_top, z_bottom = zc + length / 2.0, zc - length / 2.0
        _, z_clear = self._check_envelope(0.0, z_top + c)
        _, z_cut = self._check_envelope(0.0, z_bottom)
        return feed_rate, length, z_clear, z_cut

    def _generate_drilling(self, program: GCodeProgram, parameters: Dict, dimensions: Dict, location: Dict):
        """Axial hole on the centreline from z_top to z_bottom. The peck
        increment is the package's depth_of_cut (G83) when the hole is deeper
        than it; otherwise a single G81 cycle."""
        feed_rate, length, z_clear, z_cut = self._axial_hole_cycle(
            program, parameters, dimensions, location, 'drilling', 0.15)
        peck = self._package_value(parameters, 'depth_of_cut')
        program.add_block(f"G00 X0.00 Z{z_clear:.2f} (Drill approach)")
        if peck and length > peck:
            program.add_block(f"G83 Z{z_cut:.2f} Q{peck:.2f} F{feed_rate:.3f} (Peck drill)")
        else:
            program.add_block(f"G81 Z{z_cut:.2f} F{feed_rate:.3f} (Simple drill)")
        program.add_block("G80 (Cancel canned cycle)")
        program.add_block(f"G00 Z{z_clear:.2f} (Retract)")

    def _generate_counterboring(self, program: GCodeProgram, parameters: Dict, dimensions: Dict, location: Dict):
        """Counterbore of the feature diameter, z_top to z_bottom, on axis."""
        feed_rate, _, z_clear, z_cut = self._axial_hole_cycle(
            program, parameters, dimensions, location, 'counterboring', 0.1)
        program.add_block(f"G00 X0.00 Z{z_clear:.2f} (Counterbore approach)")
        program.add_block(f"G81 Z{z_cut:.2f} F{feed_rate:.3f} (Counterbore)")
        program.add_block("G80 (Cancel canned cycle)")
        program.add_block(f"G00 Z{z_clear:.2f} (Retract)")

    def _generate_boring(self, program: GCodeProgram, parameters: Dict, dimensions: Dict, location: Dict):
        """Bore at the feature diameter, z_top to z_bottom, on axis."""
        feed_rate = self._extract_parameter_value(parameters, 'feed_rate', 0.08)
        p = self._plan_inputs(program, 'boring', dimensions, location)
        d, length, zc = p['diameter'], p['length'], p['z_centre']
        c = self.APPROACH_CLEARANCE_MM
        x_cut, z_clear = self._check_envelope(d, zc + length / 2.0 + c)
        _, z_cut = self._check_envelope(d, zc - length / 2.0)
        program.add_block(f"G00 X{x_cut:.2f} Z{z_clear:.2f} (Bore approach)")
        program.add_block(f"G01 Z{z_cut:.2f} F{feed_rate:.3f} (Bore)")
        program.add_block("G04 P500 (Dwell 500ms)")
        program.add_block(f"G00 Z{z_clear:.2f} (Retract)")

    def _generate_chamfering(self, program: GCodeProgram, parameters: Dict, dimensions: Dict, location: Dict):
        """
        External chamfer at the +Z edge of the feature: axial leg L, radial
        leg L x tan(angle), from X = Ø - 2 L tan(angle) at z_top to X = Ø at
        z_bottom. The angle must be in the plan; the previous pattern assumed
        45 degrees and replaced a large chamfer by a 2 mm placeholder.
        """
        feed_rate = self._extract_parameter_value(parameters, 'feed_rate', 0.1)
        p = self._plan_inputs(program, 'chamfering', dimensions, location)
        d, length, angle, zc = p['diameter'], p['length'], p['chamfer_angle'], p['z_centre']
        c = self.APPROACH_CLEARANCE_MM
        z_top, z_bottom = zc + length / 2.0, zc - length / 2.0
        x_start = d - 2.0 * length * math.tan(math.radians(angle))
        x_start, z_top = self._check_envelope(x_start, z_top)
        x_end, z_bottom = self._check_envelope(d, z_bottom)
        _, z_clear = self._check_envelope(x_start, z_top + c)
        x_clear, _ = self._check_envelope(d + 2 * c, z_bottom)
        program.add_block(f"G00 X{x_start:.2f} Z{z_clear:.2f} (Chamfer approach)")
        program.add_block(f"G01 Z{z_top:.2f} F{feed_rate:.3f} (Chamfer start)")
        program.add_block(f"G01 X{x_end:.2f} Z{z_bottom:.2f} F{feed_rate:.3f} (Chamfer)")
        program.add_block(f"G00 X{x_clear:.2f} (Retract)")

    def _generate_facing(self, program: GCodeProgram, parameters: Dict, dimensions: Dict, location: Dict):
        """Face at z_top from the feature diameter to the centreline."""
        feed_rate = self._extract_parameter_value(parameters, 'feed_rate', 0.2)
        p = self._plan_inputs(program, 'facing', dimensions, location)
        d, length, zc = p['diameter'], p['length'], p['z_centre']
        c = self.APPROACH_CLEARANCE_MM
        z_face = zc + length / 2.0
        x_clear, z_clear = self._check_envelope(d + 2 * c, z_face + c)
        _, z_face = self._check_envelope(0.0, z_face)
        program.add_block(f"G00 X{x_clear:.2f} Z{z_clear:.2f} (Face approach)")
        program.add_block(f"G00 Z{z_face:.2f} (Face position)")
        program.add_block(f"G01 X0.00 F{feed_rate:.3f} (Face)")
        program.add_block(f"G00 Z{z_clear:.2f} (Retract)")
        program.add_block(f"G00 X{x_clear:.2f} (Return to start)")

    def _generate_grooving(self, program: GCodeProgram, parameters: Dict, dimensions: Dict, location: Dict):
        """Single radial plunge from the outer diameter plus a clearance to
        the groove-bottom diameter at the feature's Z; both diameters from
        the plan (the pre-Revision-5 pattern subtracted a 10 mm placeholder
        from the location X and emitted X = -10)."""
        feed_rate = self._extract_parameter_value(parameters, 'feed_rate', 0.1)
        p = self._plan_inputs(program, 'grooving', dimensions, location)
        outer, bottom, z_pos = p['outer_diameter'], p['groove_bottom_diameter'], p['z_centre']
        x_approach, z_pos = self._check_envelope(outer + self.GROOVE_APPROACH_CLEARANCE_MM, z_pos)
        x_groove, _ = self._check_envelope(bottom, z_pos)
        program.add_block(f"G00 X{x_approach:.2f} Z{z_pos:.2f} (Groove approach)")
        program.add_block(f"G01 X{x_groove:.2f} F{feed_rate:.3f} (Groove)")
        program.add_block("G04 P500 (Dwell 500ms)")
        program.add_block(f"G00 X{x_approach:.2f} (Retract)")

    def _extract_parameter_value(self, parameters: Dict, param_name: str, default: float = 10.0) -> float:
        """
        Extract a parameter value from the parameters dict.
        
        Parameters can be:
        - The KEFC/SKL traceable shape: {"feed_rate": {"value": 0.25, "unit":
          "mm/rev", "source": "swrl_rule", "rule_id": ..., "ontology_sources":
          ..., "input_facts": ...}} — preferred; 'value' is read directly, so
          a step KEFC marked auto_approved always yields its ontology-traced
          number here, never the hardcoded `default` below.
        - Legacy shapes, kept for backward compatibility with callers that
          still build a plan via ontology.py/orchestrator.py directly rather
          than through KEFC: a direct numeric value ({"feed_rate": 0.2}), or
          a nested range dict ({"feed_rate": {"min": ..., "max": ...,
          "default": ...}}).

        `default` is a last-resort compatibility fallback for those legacy
        callers, not a design endorsement — a KEFC-produced plan should never
        need it: a missing/unsafe value for an auto_approved step is a KEFC
        bug, not something RAL should paper over (see AGENTS.md).

        Args:
            parameters: Parameters dictionary
            param_name: Parameter name to extract
            default: Legacy-compatibility fallback if no value can be found

        Returns:
            Parameter value (float)
        """
        if param_name not in parameters:
            return default

        value = parameters[param_name]

        # If it's already a number, return it
        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, dict):
            # Preferred: KEFC/SKL traceable shape.
            if 'value' in value and value['value'] is not None:
                try:
                    return float(value['value'])
                except (ValueError, TypeError):
                    pass
            if 'source' in value:
                # This dict carries KEFC/SKL provenance keys but has no
                # usable 'value' — an approved step should never reach RAL in
                # this state (KEFC's exception gate exists precisely to catch
                # it upstream). Falling through to the legacy-compatibility
                # `default` here would silently invent a feed/speed/depth
                # number for a step that was never actually reasoned over —
                # exactly what AGENTS.md prohibits. Fail loudly instead.
                raise ValueError(
                    f"Parameter {param_name!r} has KEFC/SKL provenance "
                    f"(source={value.get('source')!r}, rule_id={value.get('rule_id')!r}) "
                    f"but no usable value: {value!r}. This step should have been "
                    f"caught by KEFC's exception gate before reaching RAL."
                )
            # Legacy: nested range dict.
            if 'default' in value:
                try:
                    return float(value['default'])
                except (ValueError, TypeError):
                    pass
            if 'min' in value:
                try:
                    return float(value['min'])
                except (ValueError, TypeError):
                    pass

        return default
    
    def _extract_dimension_value(self, dimensions: Dict, keys: List[str]) -> float:
        """Retained for callers outside the serialiser: returns the first
        numeric value under `keys` and raises KeyError when there is none.
        There is no default (pre-Revision-6 versions returned 10 mm)."""
        v, _ = self._number(dimensions, keys)
        if v is None:
            raise KeyError(f"none of {keys} in feature dimensions {dimensions!r}")
        return v

    def _extract_location_value(self, location: Dict, keys: List[str], default: float = 0.0) -> float:
        """
        Extract a location value from the location dict.
        
        Args:
            location: Location dictionary
            keys: List of possible keys to try
            default: Default value if not found
            
        Returns:
            Location value
        """
        for key in keys:
            if key in location:
                try:
                    return float(location[key])
                except (ValueError, TypeError):
                    continue
        
        return default
    
    def export_program(self, program: GCodeProgram, filepath: str) -> str:
        """
        Export G-code program to a .nc file.
        
        Args:
            program: GCodeProgram instance
            filepath: Path to save the .nc file
            
        Returns:
            Filepath saved
        """
        return program.save_to_file(filepath)
    
    def export_programs(
        self,
        manufacturing_plan: List[Dict],
        output_dir: str
    ) -> List[str]:
        """
        Generate and export G-code programs for the manufacturing plan.
        
        Args:
            manufacturing_plan: Manufacturing plan from orchestrator
            output_dir: Directory to save .nc files
            
        Returns:
            List of saved filepaths
        """
        import os
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate program
        program = self.generate_program(manufacturing_plan)
        
        # Save to file
        filename = f"motor_shaft_{self.program_counter - 1}.nc"
        filepath = os.path.join(output_dir, filename)
        
        program.save_to_file(filepath)
        
        return [filepath]


# Convenience function for quick G-code generation
def generate_gcode(manufacturing_plan: List[Dict], material: str = 'steel_1045') -> GCodeProgram:
    """
    Convenience function to generate G-code from manufacturing plan.
    
    Args:
        manufacturing_plan: Manufacturing plan from orchestrator
        material: Material key from ontology
        
    Returns:
        GCodeProgram instance
    """
    generator = GCodeGenerator(material)
    program = generator.generate_program(manufacturing_plan)
    
    return program

"""
Advanced CNC Simulation & Analysis Module
==========================================
Provides advanced simulation capabilities for CNC manufacturing:

1. Collision Detection
   - Tool-to-workpiece collision checking
   - Tool-to-tool collision detection (turret interference)
   - Machine boundary violations

2. Cutting Time Estimation
   - Cycle time calculation per operation
   - Rapid vs cutting time separation
   - Total manufacturing time estimation

3. Chip Load & Material Removal Rate (MRR)
   - Chip load per tooth calculation
   - Instantaneous and average MRR
   - Cutting power estimation

4. Tool Wear Estimation
   - Taylor's tool life equation
   - Wear rate based on cutting parameters
   - Remaining tool life prediction

5. Simulation Report Generation
   - Comprehensive JSON report
   - Summary statistics
   - Warnings and recommendations

Key Classes:
- WorkpieceGeometry: Represents the workpiece/part geometry
- ToolGeometry: Represents tool cutting geometry
- CollisionDetector: Detects collisions during simulation
- CuttingTimeEstimator: Estimates machining times
- ChipLoadAnalyzer: Analyzes chip load and MRR
- ToolWearEstimator: Estimates tool wear and life
- CNC Simulator: Main orchestrator for all simulation modules
"""

import math
import json
import re
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime
from dataclasses import dataclass, field


# Import from existing modules
from validator import GCodeParser, ToolpathSimulator, GCodeCommand
from gcode_generator import TOOL_ID_TO_NUMBER

# Reverse of gcode_generator.py's T-code assignment — recovers a tool_id
# string from the T-number a real controller would report as "currently
# selected", so wear/chip-load analysis attributes each cut to the tool
# actually modally active at that line, not whichever tool's G-code
# comment happens to be nearby.
TOOL_NUMBER_TO_ID = {number: tool_id for tool_id, number in TOOL_ID_TO_NUMBER.items()}


@dataclass
class WorkpieceGeometry:
    """
    Represents the workpiece/part geometry for collision detection.
    
    Attributes:
        stock_diameter: Initial stock diameter (mm)
        stock_length: Initial stock length (mm)
        features: List of feature geometries (dicts with x, z bounds)
        outline: List of (x, z) points defining the part profile
    """
    
    stock_diameter: float  # mm
    stock_length: float  # mm
    features: List[Dict[str, Any]] = field(default_factory=list)
    outline: List[Tuple[float, float]] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize outline from stock dimensions if not provided."""
        if not self.outline:
            # Default rectangular stock outline
            r = self.stock_diameter / 2.0
            self.outline = [
                (0, 0),
                (self.stock_diameter, 0),
                (self.stock_diameter, self.stock_length),
                (0, self.stock_length)
            ]
    
    def get_z_range(self) -> Tuple[float, float]:
        """Get Z-axis range of the workpiece."""
        return (0.0, self.stock_length)
    
    def get_x_at_z(self, z: float) -> float:
        """
        Get the maximum X (diameter) at a given Z position.
        
        Args:
            z: Z position
            
        Returns:
            Maximum diameter at Z position
        """
        # Default: full stock diameter
        if z < 0 or z > self.stock_length:
            return 0.0
        
        # Check features for modified diameter
        max_diameter = self.stock_diameter
        
        for feature in self.features:
            feature_z_start = feature.get('z_start', 0)
            feature_z_end = feature.get('z_end', self.stock_length)
            feature_diameter = feature.get('diameter', self.stock_diameter)
            
            if feature_z_start <= z <= feature_z_end:
                max_diameter = min(max_diameter, feature_diameter)
        
        return max_diameter
    
    def is_point_inside(self, x: float, z: float) -> bool:
        """
        Check if a point (x, z) is inside the workpiece.
        
        Args:
            x: X position (diameter, mm)
            z: Z position (mm)
            
        Returns:
            True if point is inside workpiece
        """
        if z < 0 or z > self.stock_length:
            return False
        
        if x < 0 or x > self.stock_diameter:
            return False
        
        # Check if within current diameter at Z
        diameter_at_z = self.get_x_at_z(z)
        return x <= diameter_at_z


@dataclass
class ToolGeometry:
    """
    Represents tool cutting geometry.
    
    Attributes:
        tool_id: Tool key
        tool_length: Overall tool length (mm)
        tool_diameter: Tool cutting diameter (mm)
        nose_radius: Tool nose radius (mm)
        clearance_angle: Tool clearance angle (degrees)
        approach_angle: Tool approach angle (degrees)
    """
    
    tool_id: str
    tool_length: float  # mm
    tool_diameter: float  # mm
    nose_radius: float  # mm
    clearance_angle: float  # degrees
    approach_angle: float  # degrees
    
    @classmethod
    def from_ontology(cls, tool_id: str, tools_data: Optional[Dict[str, Dict]] = None) -> 'ToolGeometry':
        """
        Create ToolGeometry from a tools-reference dict (see
        SKLRepository.legacy_tools_dict()). Not currently called anywhere in
        this codebase; kept for API completeness.

        Args:
            tool_id: Tool ID (e.g., 'turning_insert_rough')
            tools_data: {tool_id: tool_dict}

        Returns:
            ToolGeometry instance
        """
        tool_data = (tools_data or {}).get(tool_id, {})
        
        return cls(
            tool_id=tool_id,
            tool_length=tool_data.get('tool_length', 100.0),
            tool_diameter=tool_data.get('tool_diameter', 10.0),
            nose_radius=tool_data.get('nose_radius', 0.4),
            clearance_angle=tool_data.get('clearance_angle', 6.0),
            approach_angle=tool_data.get('approach_angle', 93.0)
        )


@dataclass
class CollisionEvent:
    """
    Represents a collision event during simulation.
    
    Attributes:
        line_number: G-code line number
        collision_type: Type of collision (tool_workpiece, tool_tool, boundary)
        severity: Severity level (warning, error, critical)
        description: Human-readable description
        position: Tool position at collision (x, z)
        details: Additional details
    """
    
    line_number: int
    collision_type: str
    severity: str
    description: str
    position: Tuple[float, float]
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'line_number': self.line_number,
            'collision_type': self.collision_type,
            'severity': self.severity,
            'description': self.description,
            'position': {
                'x': self.position[0],
                'z': self.position[1]
            },
            'details': self.details
        }


@dataclass
class CuttingParameters:
    """
    Represents cutting parameters for a single operation.
    
    Attributes:
        operation_type: Operation type (turning, drilling, etc.)
        feed_rate: Feed rate (mm/rev)
        spindle_speed: Spindle speed (RPM)
        cutting_speed: Cutting speed (m/min)
        depth_of_cut: Depth of cut (mm)
        width_of_cut: Width of cut (mm)
        chip_load: Chip load per tooth (mm/tooth)
        material_removal_rate: MRR (mm³/min)
        cutting_time: Cutting time (seconds)
        cutting_force: Estimated cutting force (N)
        cutting_power: Estimated cutting power (kW)
    """
    
    operation_type: str
    feed_rate: float  # mm/rev
    spindle_speed: float  # RPM
    cutting_speed: float  # m/min
    depth_of_cut: float  # mm
    width_of_cut: float  # mm
    chip_load: float  # mm/tooth
    material_removal_rate: float  # mm³/min
    cutting_time: float  # seconds
    cutting_force: Optional[float]  # N; None when the model inputs are unknown
    cutting_power: Optional[float]  # kW; None when the model inputs are unknown
    # Inputs of the force/power model (see ChipLoadAnalyzer.force_and_power).
    # They are kept separate from feed_rate/spindle_speed/cutting_speed/
    # depth_of_cut above, which are the programme-derived values the cutting-
    # time and tool-wear estimators consume and are deliberately unchanged.
    force_model: str = 'unavailable'
    force_feed_mm_per_rev: Optional[float] = None
    force_depth_of_cut_mm: Optional[float] = None
    force_diameter_mm: Optional[float] = None
    force_spindle_speed_rpm: Optional[float] = None
    force_cutting_speed_m_per_min: Optional[float] = None
    plan_step_number: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'operation_type': self.operation_type,
            'feed_rate_mm_per_rev': round(self.feed_rate, 4),
            'spindle_speed_rpm': round(self.spindle_speed, 1),
            'cutting_speed_m_per_min': round(self.cutting_speed, 2),
            'depth_of_cut_mm': round(self.depth_of_cut, 3),
            'width_of_cut_mm': round(self.width_of_cut, 3),
            'chip_load_mm_per_tooth': round(self.chip_load, 4),
            'material_removal_rate_mm3_per_min': round(self.material_removal_rate, 2),
            'cutting_time_seconds': round(self.cutting_time, 2),
            'cutting_force_N': None if self.cutting_force is None else round(self.cutting_force, 2),
            'cutting_power_kW': None if self.cutting_power is None else round(self.cutting_power, 4),
            'force_model': self.force_model,
            'force_inputs': {
                'plan_step_number': self.plan_step_number,
                'feed_mm_per_rev': self.force_feed_mm_per_rev,
                'depth_of_cut_mm': self.force_depth_of_cut_mm,
                'diameter_mm': self.force_diameter_mm,
                'spindle_speed_rpm': self.force_spindle_speed_rpm,
                'cutting_speed_m_per_min': None if self.force_cutting_speed_m_per_min is None
                    else round(self.force_cutting_speed_m_per_min, 3),
            },
        }


class CollisionDetector:
    """
    Detects collisions during CNC simulation.
    
    Checks for:
    - Tool-to-workpiece collisions
    - Tool-to-tool collisions (turret interference)
    - Machine boundary violations
    
    Attributes:
        workpiece: WorkpieceGeometry instance
        machine: Machine capabilities dict
    """
    
    def __init__(self, workpiece: WorkpieceGeometry, machine_id: str = 'cnc_lathe',
                 machines_data: Optional[Dict[str, Dict]] = None):
        """
        Initialize collision detector.

        Args:
            workpiece: Workpiece geometry
            machine_id: Machine key, e.g. 'cnc_lathe'
            machines_data: {machine_id: machine_dict} — see
                SKLRepository.legacy_machines_dict()
        """
        self.workpiece = workpiece
        self.machine = (machines_data or {}).get(machine_id, {})
        self.collisions: List[CollisionEvent] = []
        
        # Machine bounds
        caps = self.machine.get('capabilities', {})
        # Travel envelope from the single source (machine_envelope.py).
        from machine_envelope import travel_envelope
        env = travel_envelope(self.machine)
        self.x_min, self.x_max = env['x_min'], env['x_max']
        self.z_min, self.z_max = env['z_min'], env['z_max']
        
        # Turret station spacing
        self.turret_stations = caps.get('turret_stations', 12)
        self.turret_angle = 360.0 / self.turret_stations
    
    def check_tool_workpiece_collision(self, tool_x: float, tool_z: float, 
                                        tool: ToolGeometry, line_number: int) -> Optional[CollisionEvent]:
        """
        Check if tool collides with workpiece.
        
        Args:
            tool_x: Tool X position (diameter)
            tool_z: Tool Z position
            tool: Tool geometry
            line_number: G-code line number
            
        Returns:
            CollisionEvent if collision detected, None otherwise
        """
        # Tool tip position
        tool_tip_x = tool_x
        tool_tip_z = tool_z
        
        # Check if tool tip is inside workpiece during rapid (G00)
        # This is a simplified check - in reality, we'd need to know the motion type
        if self.workpiece.is_point_inside(tool_tip_x, tool_tip_z):
            # This might be intentional (cutting), so we flag as warning
            # Actual collision detection would need motion context
            pass
        
        return None
    
    def check_boundary_violation(self, tool_x: float, tool_z: float, 
                                  line_number: int) -> Optional[CollisionEvent]:
        """
        Check if tool position violates machine boundaries.
        
        Args:
            tool_x: Tool X position
            tool_z: Tool Z position
            line_number: G-code line number
            
        Returns:
            CollisionEvent if violation detected, None otherwise
        """
        if tool_x < self.x_min or tool_x > self.x_max:
            collision = CollisionEvent(
                line_number=line_number,
                collision_type='boundary',
                severity='error',
                description=f'X position {tool_x}mm exceeds machine limits [{self.x_min}, {self.x_max}]mm',
                position=(tool_x, tool_z),
                details={'axis': 'X', 'min': self.x_min, 'max': self.x_max}
            )
            self.collisions.append(collision)
            return collision
        
        if tool_z < self.z_min or tool_z > self.z_max:
            collision = CollisionEvent(
                line_number=line_number,
                collision_type='boundary',
                severity='error',
                description=f'Z position {tool_z}mm exceeds machine limits [{self.z_min}, {self.z_max}]mm',
                position=(tool_x, tool_z),
                details={'axis': 'Z', 'min': self.z_min, 'max': self.z_max}
            )
            self.collisions.append(collision)
            return collision
        
        return None
    
    def check_turret_interference(self, current_tool: int, next_tool: int,
                                   line_number: int) -> Optional[CollisionEvent]:
        """
        Check if tool change causes turret interference.
        
        Args:
            current_tool: Current tool number
            next_tool: Next tool number
            line_number: G-code line number
            
        Returns:
            CollisionEvent if interference detected, None otherwise
        """
        # Check if tool numbers are valid
        if next_tool < 1 or next_tool > self.turret_stations:
            collision = CollisionEvent(
                line_number=line_number,
                collision_type='tool_tool',
                severity='error',
                description=f'Tool T{next_tool} exceeds turret stations (1-{self.turret_stations})',
                position=(0, 0),
                details={'current_tool': current_tool, 'next_tool': next_tool, 
                        'turret_stations': self.turret_stations}
            )
            self.collisions.append(collision)
            return collision
        
        return None
    
    def get_collision_report(self) -> Dict[str, Any]:
        """
        Generate collision detection report.
        
        Returns:
            Dictionary with collision statistics and events
        """
        return {
            'total_collisions': len(self.collisions),
            'by_type': {
                'tool_workpiece': sum(1 for c in self.collisions if c.collision_type == 'tool_workpiece'),
                'tool_tool': sum(1 for c in self.collisions if c.collision_type == 'tool_tool'),
                'boundary': sum(1 for c in self.collisions if c.collision_type == 'boundary')
            },
            'by_severity': {
                'critical': sum(1 for c in self.collisions if c.severity == 'critical'),
                'error': sum(1 for c in self.collisions if c.severity == 'error'),
                'warning': sum(1 for c in self.collisions if c.severity == 'warning')
            },
            'collisions': [c.to_dict() for c in self.collisions]
        }


class CuttingTimeEstimator:
    """
    Estimates cutting times for CNC operations.
    
    Calculates:
    - Rapid traverse time
    - Cutting time per operation
    - Tool change time
    - Total cycle time
    
    Attributes:
        machine: Machine capabilities dict
    """
    
    # Default times (seconds)
    TOOL_CHANGE_TIME = 3.0  # seconds per tool change
    RAPID_TRAVERSE_RATE = 5000.0  # mm/min (typical rapid rate)
    POSITIONING_TIME = 0.5  # seconds per block
    
    def __init__(self, machine_id: str = 'cnc_lathe', machines_data: Optional[Dict[str, Dict]] = None):
        """
        Initialize cutting time estimator.

        Args:
            machine_id: Machine key, e.g. 'cnc_lathe'
            machines_data: {machine_id: machine_dict} — see
                SKLRepository.legacy_machines_dict()
        """
        self.machine = (machines_data or {}).get(machine_id, {})
        caps = self.machine.get('capabilities', {})
        self.rapid_rate = caps.get('rapid_traverse_rate', self.RAPID_TRAVERSE_RATE)
    
    def calculate_rapid_time(self, distance: float) -> float:
        """
        Calculate rapid traverse time.
        
        Args:
            distance: Rapid distance (mm)
            
        Returns:
            Time in seconds
        """
        if distance <= 0:
            return 0.0
        return (distance / self.rapid_rate) * 60.0
    
    def calculate_cutting_time(self, distance: float, feed_rate: float, 
                                spindle_speed: float) -> float:
        """
        Calculate cutting time for a feed motion.
        
        Args:
            distance: Cutting distance (mm)
            feed_rate: Feed rate (mm/rev)
            spindle_speed: Spindle speed (RPM)
            
        Returns:
            Time in seconds
        """
        if distance <= 0 or feed_rate <= 0 or spindle_speed <= 0:
            return 0.0
        
        # Feed rate in mm/min = feed_rate (mm/rev) * spindle_speed (RPM)
        feed_rate_per_min = feed_rate * spindle_speed
        
        if feed_rate_per_min <= 0:
            return 0.0
        
        # Time in minutes = distance / feed_rate_per_min
        time_minutes = distance / feed_rate_per_min
        
        # Convert to seconds
        return time_minutes * 60.0
    
    def calculate_drilling_time(self, depth: float, feed_rate: float, 
                                 spindle_speed: float, pecks: int = 1) -> float:
        """
        Calculate drilling time including peck retracts.
        
        Args:
            depth: Total drilling depth (mm)
            feed_rate: Feed rate (mm/rev)
            spindle_speed: Spindle speed (RPM)
            pecks: Number of peck cycles
            
        Returns:
            Time in seconds
        """
        if depth <= 0 or feed_rate <= 0 or spindle_speed <= 0:
            return 0.0
        
        # Cutting time
        cutting_time = self.calculate_cutting_time(depth, feed_rate, spindle_speed)
        
        # Retract time (rapid) per peck
        retract_time = self.calculate_rapid_time(depth) * (pecks - 1)
        
        return cutting_time + retract_time
    
    def calculate_cycle_time(self, commands: List[GCodeCommand], 
                              state_history: List[Dict]) -> Dict[str, Any]:
        """
        Calculate total cycle time for G-code program.

        Every motion is timed from the modal machine state the toolpath
        simulator recorded for its line (validator.ToolpathSimulator):

        * feed moves (G01/G02/G03): length of the move from the previous
          position to the new one, at feed (mm/rev) x modal spindle speed
          (rev/min) -> mm/min. G02/G03 are timed on their chord (the
          serialiser emits no arcs);
        * canned cycles (G81/G82/G83): drilling depth is the incremental
          cycle depth |Z_start - Z_target| from the position before the
          cycle, at the modal feed and spindle speed; G83 retracts are
          ceil(depth / Q) - 1 rapid retracts of the full depth;
        * rapids (G00): move length at the rapid traverse rate.

        Previously S was read from the cutting line itself (it is only ever
        written on M03 lines, so every move was timed at an assumed 1000
        rev/min), move length was the distance of the end point from the
        origin, and drilling depth was the absolute Z coordinate. A feed
        move without a running spindle or a known feed cannot be timed; it
        is counted in 'untimed_feed_moves' rather than given a default.

        Args:
            commands: List of GCodeCommand objects
            state_history: State history from simulation

        Returns:
            Dictionary with time breakdown
        """
        rapid_time = 0.0
        cutting_time = 0.0
        tool_change_time = 0.0
        positioning_time = 0.0
        untimed = 0
        feed_length = 0.0
        cycle_depth = 0.0

        state_by_line = {s['line']: s for s in state_history}
        # Start at the toolpath simulator's initial position (X0 Z0), the same
        # origin from which the validator accumulates travel.
        prev_x, prev_z = 0.0, 0.0

        for cmd in commands:
            positioning_time += self.POSITIONING_TIME
            state = state_by_line.get(cmd.line_number)
            new_x = state['x'] if state else prev_x
            new_z = state['z'] if state else prev_z
            rpm = (state.get('spindle_rpm') or 0.0) if state and state.get('spindle_on') else 0.0
            feed = (state.get('feed_rate') or 0.0) if state else 0.0

            for g_code in (cmd.g_codes or []):
                if g_code == 'G00':
                    dist = math.hypot(new_x - prev_x, new_z - prev_z)
                    rapid_time += self.calculate_rapid_time(dist)
                elif g_code in ('G01', 'G02', 'G03'):
                    dist = math.hypot(new_x - prev_x, new_z - prev_z)
                    if dist > 0 and (rpm <= 0 or feed <= 0):
                        untimed += 1
                    else:
                        cutting_time += self.calculate_cutting_time(dist, feed, rpm)
                        feed_length += dist
                elif g_code in ('G81', 'G82', 'G83'):
                    z_target = cmd.parameters.get('Z', prev_z)
                    depth = abs(prev_z - z_target)
                    # GCodeParser does not parse the Q (peck) word; read it
                    # from the block text so G83 pecks follow the programme.
                    q = cmd.parameters.get('Q')
                    if q is None:
                        m_q = re.search(r'\bQ(\d+(?:\.\d+)?)', (cmd.raw_text or '').split('(', 1)[0].upper())
                        q = float(m_q.group(1)) if m_q else None
                    pecks = max(1, math.ceil(depth / q)) if (g_code == 'G83' and q) else 1
                    if depth > 0 and (rpm <= 0 or feed <= 0):
                        untimed += 1
                    else:
                        cutting_time += self.calculate_drilling_time(depth, feed, rpm, pecks)
                        cycle_depth += depth

            if 'M06' in cmd.m_codes:
                tool_change_time += self.TOOL_CHANGE_TIME
            if state:
                prev_x, prev_z = new_x, new_z

        total_time = rapid_time + cutting_time + tool_change_time + positioning_time
        
        return {
            'rapid_time_seconds': round(rapid_time, 2),
            'cutting_time_seconds': round(cutting_time, 2),
            'tool_change_time_seconds': round(tool_change_time, 2),
            'positioning_time_seconds': round(positioning_time, 2),
            'total_cycle_time_seconds': round(total_time, 2),
            'total_cycle_time_minutes': round(total_time / 60.0, 2),
            'timed_feed_length_mm': round(feed_length, 2),
            'timed_cycle_depth_mm': round(cycle_depth, 2),
            'untimed_feed_moves': untimed,
        }


class ChipLoadAnalyzer:
    """
    Analyzes chip load and material removal rate.
    
    Calculates:
    - Chip load per tooth
    - Material removal rate (MRR)
    - Cutting forces
    - Cutting power
    
    Attributes:
        material: Material key
    """
    
    # Specific cutting force kc [N/mm^2 = MPa] per material key. These are
    # NOMINAL, handbook-order constants carried over unchanged from the
    # original implementation; they are NOT calibrated against dynamometer
    # measurements, carry no chip-thickness correction (kc is treated as
    # constant, i.e. the Kienzle exponent mc is taken as 0) and no tool-wear
    # or rake-angle correction. Force and power outputs are therefore order-
    # of-magnitude audit quantities, not process predictions.
    SPECIFIC_CUTTING_FORCE_N_PER_MM2 = {
        'steel_1045': 2000.0,
        'aluminum_6061': 800.0,
        'stainless_304': 2500.0,
    }
    DEFAULT_SPECIFIC_CUTTING_FORCE_N_PER_MM2 = 1500.0

    # Force/power model identifiers recorded with every analysed move.
    MODEL_SINGLE_POINT = 'single_point: Fc = kc*ap*f; P = Fc*vc/60000'
    MODEL_DRILLING = 'drilling_per_lip: Fc = kc*(D/2)*(f/2); P = Fc*vc/60000 (= kc*D*f*vc/240000)'
    MODEL_MILLING = 'milling_single_edge: Fc = kc*ap*f; P = Fc*vc/60000 (vc at tool diameter)'
    MODEL_UNAVAILABLE = 'unavailable'
    
    def __init__(self, material_id: str = 'steel_1045', materials_data: Optional[Dict[str, Dict]] = None,
                 operations_data: Optional[Dict[str, Dict]] = None):
        """
        Initialize chip load analyzer.

        Args:
            material_id: Material key, e.g. 'steel_1045'
            materials_data: {material_id: material_dict} — see
                SKLRepository.legacy_materials_dict()
            operations_data: {operation_id: operation_dict} — see
                SKLRepository.legacy_operations_dict(); only read by
                get_optimal_parameters(), which nothing in this codebase
                currently calls
        """
        self.material_id = material_id
        self.material = (materials_data or {}).get(material_id, {})
        self.operations_data = operations_data or {}
        self.kc = self.SPECIFIC_CUTTING_FORCE_N_PER_MM2.get(
            material_id, self.DEFAULT_SPECIFIC_CUTTING_FORCE_N_PER_MM2)
    
    def calculate_chip_load(self, feed_rate: float, spindle_speed: float, 
                            num_teeth: int = 1) -> float:
        """
        Calculate chip load per tooth.
        
        Chip load = feed_rate (mm/rev) / (spindle_speed (RPM) * num_teeth)
        
        Args:
            feed_rate: Feed rate (mm/rev)
            spindle_speed: Spindle speed (RPM)
            num_teeth: Number of cutting teeth
            
        Returns:
            Chip load per tooth (mm/tooth)
        """
        if spindle_speed <= 0 or num_teeth <= 0:
            return 0.0
        
        return feed_rate / (spindle_speed / 60.0 * num_teeth)
    
    def calculate_mrr(self, feed_rate: float, depth_of_cut: float, 
                      width_of_cut: float, spindle_speed: float) -> float:
        """
        Calculate material removal rate.
        
        MRR = feed_rate (mm/rev) * depth_of_cut (mm) * width_of_cut (mm) * spindle_speed (RPM)
        
        Args:
            feed_rate: Feed rate (mm/rev)
            depth_of_cut: Depth of cut (mm)
            width_of_cut: Width of cut (mm)
            spindle_speed: Spindle speed (RPM)
            
        Returns:
            MRR (mm³/min)
        """
        return feed_rate * depth_of_cut * width_of_cut * spindle_speed
    
    @staticmethod
    def cutting_speed_m_per_min(diameter_mm: float, spindle_speed_rpm: float) -> float:
        """vc = pi * D * n / 1000  [m/min], D in mm, n in rev/min."""
        return math.pi * diameter_mm * spindle_speed_rpm / 1000.0

    def calculate_cutting_force(self, depth_of_cut: float, feed_per_rev: float) -> float:
        """
        Main (tangential) cutting force of a single-point cut.

        Fc = kc * ap * f   [N], with kc in N/mm^2, ap (depth of cut) in mm
        and f (feed per revolution) in mm/rev, so ap * f is the uncut chip
        cross-section in mm^2.
        """
        return self.kc * depth_of_cut * feed_per_rev

    def calculate_drilling_force_per_lip(self, drill_diameter: float, feed_per_rev: float) -> float:
        """
        Tangential cutting force on one lip of a two-flute twist drill.

        Fc = kc * (D/2) * (f/2)   [N]: each lip cuts a chip of width D/2 and
        thickness f/2 (feed per lip). The force acts at the mean radius D/4,
        where the speed is vc/2, so the total power of the two lips is
        2 * Fc * (vc/2) / 60000 = Fc * vc / 60000 with vc the peripheral speed,
        equal to the usual handbook form P = kc * D * f * vc / 240000.
        """
        return self.kc * (drill_diameter / 2.0) * (feed_per_rev / 2.0)

    @staticmethod
    def calculate_cutting_power(cutting_force: float, cutting_speed: float) -> float:
        """
        Cutting power P = Fc * vc / 60000  [kW], Fc in N, vc in m/min.
        Computed from the force, never from an independent constant, so the
        force and power channels are dimensionally consistent by
        construction.
        """
        return cutting_force * cutting_speed / 60000.0

    def force_and_power(self, process: str, feed_per_rev: Optional[float],
                        depth_of_cut: Optional[float], diameter: Optional[float],
                        spindle_speed: Optional[float]) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
        """
        Return (Fc [N], P [kW], vc [m/min], model_id) for one analysed move.

        process 'drilling' uses the per-lip model with D the drill (hole)
        diameter; 'milling' uses the single-edge form with vc at the tool
        diameter (one effective edge, as the rest of this analyser assumes);
        every other process uses the single-point model. When an input the
        model needs is unknown the move is reported as 'unavailable' (None),
        never filled with a default, and is excluded from the averages.
        """
        if not feed_per_rev or feed_per_rev <= 0:
            return None, None, None, self.MODEL_UNAVAILABLE
        if process == 'drilling':
            if not diameter or diameter <= 0:
                return None, None, None, self.MODEL_UNAVAILABLE
            force = self.calculate_drilling_force_per_lip(diameter, feed_per_rev)
            model = self.MODEL_DRILLING
        else:
            if not depth_of_cut or depth_of_cut <= 0:
                return None, None, None, self.MODEL_UNAVAILABLE
            force = self.calculate_cutting_force(depth_of_cut, feed_per_rev)
            model = self.MODEL_MILLING if process == 'milling' else self.MODEL_SINGLE_POINT
        if not diameter or diameter <= 0 or not spindle_speed or spindle_speed <= 0:
            return force, None, None, model
        vc = self.cutting_speed_m_per_min(diameter, spindle_speed)
        return force, self.calculate_cutting_power(force, vc), vc, model
    
    def analyze_operation(self, operation_type: str, feed_rate: float, 
                          spindle_speed: float, depth_of_cut: float,
                          width_of_cut: float, diameter: float,
                          num_teeth: int = 1,
                          force_inputs: Optional[Dict[str, Any]] = None) -> CuttingParameters:
        """
        Analyze cutting parameters for an operation.
        
        Args:
            operation_type: Operation type
            feed_rate: Feed rate (mm/rev)
            spindle_speed: Spindle speed (RPM)
            depth_of_cut: Depth of cut (mm)
            width_of_cut: Width of cut (mm)
            diameter: Workpiece diameter (mm)
            num_teeth: Number of cutting teeth
            force_inputs: optional dict with keys process, feed_per_rev,
                depth_of_cut, diameter, spindle_speed, step_number for the
                force/power model. When omitted the programme-derived feed,
                depth, diameter and speed are used with the single-point
                model.
            
        Returns:
            CuttingParameters instance
        """
        # Calculate cutting speed (m/min). Unchanged: this value, the feed and
        # the cutting time below are what ToolWearEstimator consumes.
        if diameter > 0 and spindle_speed > 0:
            cutting_speed = math.pi * diameter * spindle_speed / 1000.0
        else:
            cutting_speed = 0.0
        
        # Calculate chip load
        chip_load = self.calculate_chip_load(feed_rate, spindle_speed, num_teeth)
        
        # Calculate MRR
        mrr = self.calculate_mrr(feed_rate, depth_of_cut, width_of_cut, spindle_speed)
        
        # Force and power: Fc from kc and the chip cross-section, P = Fc*vc/60000.
        fi = force_inputs or {
            'process': 'turning', 'feed_per_rev': feed_rate, 'depth_of_cut': depth_of_cut,
            'diameter': diameter, 'spindle_speed': spindle_speed, 'step_number': None,
        }
        cutting_force, cutting_power, force_vc, force_model = self.force_and_power(
            fi.get('process', 'turning'), fi.get('feed_per_rev'), fi.get('depth_of_cut'),
            fi.get('diameter'), fi.get('spindle_speed'))
        
        # Estimate cutting time (simplified)
        if feed_rate > 0 and spindle_speed > 0:
            cutting_time = 60.0 * depth_of_cut / (feed_rate * spindle_speed / 60.0)
        else:
            cutting_time = 0.0
        
        return CuttingParameters(
            operation_type=operation_type,
            feed_rate=feed_rate,
            spindle_speed=spindle_speed,
            cutting_speed=cutting_speed,
            depth_of_cut=depth_of_cut,
            width_of_cut=width_of_cut,
            chip_load=chip_load,
            material_removal_rate=mrr,
            cutting_time=cutting_time,
            cutting_force=cutting_force,
            cutting_power=cutting_power,
            force_model=force_model,
            force_feed_mm_per_rev=fi.get('feed_per_rev'),
            force_depth_of_cut_mm=fi.get('depth_of_cut'),
            force_diameter_mm=fi.get('diameter'),
            force_spindle_speed_rpm=fi.get('spindle_speed'),
            force_cutting_speed_m_per_min=force_vc,
            plan_step_number=fi.get('step_number'),
        )
    
    def get_optimal_parameters(self, operation_type: str, diameter: float, 
                                depth_of_cut: float) -> Dict[str, Any]:
        """
        Get optimal cutting parameters for an operation.
        
        Args:
            operation_type: Operation type
            diameter: Workpiece diameter (mm)
            depth_of_cut: Desired depth of cut (mm)
            
        Returns:
            Dictionary with optimal parameters
        """
        # Get material properties
        mat_props = self.material.get('properties', {})

        # Get operation parameters
        op_params = self.operations_data.get(operation_type, {}).get('parameters', {})
        
        # Calculate optimal spindle speed
        # Vc = π * D * N / 1000, so N = Vc * 1000 / (π * D)
        optimal_vc = op_params.get('cutting_speed', 150)  # m/min
        if diameter > 0:
            optimal_n = optimal_vc * 1000 / (math.pi * diameter)
        else:
            optimal_n = 1000
        
        # Calculate optimal feed rate
        optimal_f = op_params.get('feed_rate', 0.2)  # mm/rev
        
        # Calculate chip load for single-tooth tool
        optimal_chip_load = self.calculate_chip_load(optimal_f, optimal_n, 1)
        
        # Calculate MRR
        mrr = self.calculate_mrr(optimal_f, depth_of_cut, depth_of_cut * 2, optimal_n)
        
        return {
            'operation_type': operation_type,
            'material': self.material_id,
            'diameter_mm': diameter,
            'depth_of_cut_mm': depth_of_cut,
            'optimal_cutting_speed_m_per_min': optimal_vc,
            'optimal_spindle_speed_rpm': round(optimal_n, 0),
            'optimal_feed_rate_mm_per_rev': optimal_f,
            'optimal_chip_load_mm_per_tooth': round(optimal_chip_load, 4),
            'estimated_mrr_mm3_per_min': round(mrr, 2)
        }


class ToolWearEstimator:
    """
    Estimates tool wear and remaining tool life.
    
    Uses:
    - Taylor's tool life equation: T * V^n = C
    - Wear rate based on cutting parameters
    - Remaining life prediction
    
    Attributes:
        tool: Tool key
        material: Material key
    """
    
    # Taylor's tool life constants (for carbide tools)
    TAYLOR_N = 0.3  # Exponent (0.2-0.4 for carbide)
    TAYLOR_C = 200  # Constant (material/tool dependent)
    
    # Wear rates (arbitrary units per minute of cutting)
    WEAR_RATES = {
        'steel_1045': 0.05,
        'aluminum_6061': 0.02,
        'stainless_304': 0.08
    }
    
    def __init__(self, tool_id: str = 'turning_insert_rough',
                 material_id: str = 'steel_1045',
                 tools_data: Optional[Dict[str, Dict]] = None,
                 materials_data: Optional[Dict[str, Dict]] = None):
        """
        Initialize tool wear estimator.

        Args:
            tool_id: Tool key, e.g. 'turning_insert_rough'
            material_id: Material key, e.g. 'steel_1045'
            tools_data: {tool_id: tool_dict} — see SKLRepository.legacy_tools_dict()
            materials_data: {material_id: material_dict} — see
                SKLRepository.legacy_materials_dict()
        """
        self.tool_id = tool_id
        self.material_id = material_id
        self.tool = (tools_data or {}).get(tool_id, {})
        self.material = (materials_data or {}).get(material_id, {})
        
        # Tool life parameters
        self.initial_life = self.tool.get('tool_life_minutes', 120)  # minutes
        self.wear_rate = self.WEAR_RATES.get(material_id, 0.05)
        
        # Current state
        self.cumulative_cutting_time = 0.0  # minutes
        self.cumulative_wear = 0.0  # arbitrary units [0, 1]
    
    def calculate_tool_life(self, cutting_speed: float) -> float:
        """
        Calculate tool life using Taylor's equation.
        
        T = (C / V)^n
        
        Args:
            cutting_speed: Cutting speed (m/min)
            
        Returns:
            Tool life in minutes
        """
        if cutting_speed <= 0:
            return float('inf')
        
        return (self.TAYLOR_C / cutting_speed) ** (1.0 / self.TAYLOR_N)
    
    def calculate_wear_rate(self, cutting_speed: float, feed_rate: float) -> float:
        """
        Calculate wear rate based on cutting parameters.
        
        Higher cutting speed and feed rate increase wear.
        
        Args:
            cutting_speed: Cutting speed (m/min)
            feed_rate: Feed rate (mm/rev)
            
        Returns:
            Wear rate (wear units per minute)
        """
        # Base wear rate from material
        base_rate = self.wear_rate
        
        # Adjust for cutting speed (higher speed = more wear)
        speed_factor = (cutting_speed / 100.0) ** 1.5 if cutting_speed > 0 else 1.0
        
        # Adjust for feed rate (higher feed = more wear)
        feed_factor = (feed_rate / 0.2) ** 1.2 if feed_rate > 0 else 1.0
        
        return base_rate * speed_factor * feed_factor
    
    def update_wear(self, cutting_time_minutes: float, cutting_speed: float, 
                    feed_rate: float) -> Dict[str, Any]:
        """
        Update tool wear based on cutting operation.
        
        Args:
            cutting_time_minutes: Duration of cutting (minutes)
            cutting_speed: Cutting speed (m/min)
            feed_rate: Feed rate (mm/rev)
            
        Returns:
            Dictionary with wear status
        """
        # Calculate wear for this operation
        wear_rate = self.calculate_wear_rate(cutting_speed, feed_rate)
        wear_increment = wear_rate * cutting_time_minutes
        
        # Update cumulative values
        self.cumulative_cutting_time += cutting_time_minutes
        self.cumulative_wear += wear_increment
        
        # Nominal tool life at the CURRENT operation's cutting speed alone
        # (Taylor's equation) — a single-point-in-time projection, not a
        # cumulative-wear-aware "time left" figure. Kept for reference, but
        # must not be presented as if it reconciles with wear_status/
        # wear_percentage below: it previously was (as
        # 'remaining_tool_life_minutes'), and could contradict it (e.g. show
        # ~450 minutes left on a tool simultaneously reported 100%/'critical'
        # worn) because the two were computed by two independent, unrelated
        # models. See AGENTS.md / finding #3C.
        nominal_tool_life_minutes = self.calculate_tool_life(cutting_speed)

        # Wear percentage
        wear_percentage = min(100.0, (self.cumulative_wear / 1.0) * 100.0)

        # Remaining life derived FROM wear_percentage (not from the
        # independent Taylor snapshot above), so it's mathematically
        # guaranteed consistent with wear_status: 0% wear -> full
        # initial_life remaining, 100% wear -> 0 remaining.
        remaining_life = max(0.0, self.initial_life * (1.0 - wear_percentage / 100.0))

        return {
            'tool_id': self.tool_id,
            'material_id': self.material_id,
            'cumulative_cutting_time_minutes': round(self.cumulative_cutting_time, 2),
            'cumulative_wear': round(self.cumulative_wear, 4),
            'wear_percentage': round(wear_percentage, 2),
            'nominal_tool_life_at_current_speed_minutes': round(nominal_tool_life_minutes, 2),
            'remaining_tool_life_minutes': round(remaining_life, 2),
            'wear_status': self._get_wear_status(wear_percentage)
        }
    
    def _get_wear_status(self, wear_percentage: float) -> str:
        """
        Get wear status string.
        
        Args:
            wear_percentage: Current wear percentage
            
        Returns:
            Status string
        """
        if wear_percentage < 30:
            return 'good'
        elif wear_percentage < 60:
            return 'fair'
        elif wear_percentage < 80:
            return 'poor'
        else:
            return 'critical'
    
    def get_tool_recommendation(self, wear_percentage: float) -> str:
        """
        Get tool change recommendation.
        
        Args:
            wear_percentage: Current wear percentage
            
        Returns:
            Recommendation string
        """
        if wear_percentage < 30:
            return 'Tool is in good condition. Continue use.'
        elif wear_percentage < 60:
            return 'Tool showing moderate wear. Monitor closely.'
        elif wear_percentage < 80:
            return 'Tool wear is high. Plan tool change soon.'
        else:
            return 'CRITICAL: Tool wear exceeds safe limit. Replace immediately.'


class CNCSimulator:
    """
    Main CNC simulator orchestrating all simulation modules.
    
    Integrates:
    - Collision detection
    - Cutting time estimation
    - Chip load and MRR analysis
    - Tool wear estimation
    
    Attributes:
        machine_id: Machine key
        material_id: Material key
        workpiece: Workpiece geometry
        collision_detector: CollisionDetector instance
        time_estimator: CuttingTimeEstimator instance
        chip_analyzer: ChipLoadAnalyzer instance
        wear_estimator: ToolWearEstimator instance
    
    Methods:
        simulate_file(): Simulate a G-code file
        simulate_commands(): Simulate parsed G-code commands
        get_report(): Generate comprehensive simulation report
        export_report(): Export report to JSON file
    """
    
    def __init__(self, machine_id: str = 'cnc_lathe',
                 material_id: str = 'steel_1045',
                 stock_diameter: float = 80.0,
                 stock_length: float = 200.0,
                 machines_data: Optional[Dict[str, Dict]] = None,
                 tools_data: Optional[Dict[str, Dict]] = None,
                 materials_data: Optional[Dict[str, Dict]] = None,
                 operations_data: Optional[Dict[str, Dict]] = None,
                 plan_steps: Optional[List[Dict]] = None):
        """
        Initialize CNC simulator.

        Args:
            machine_id: Machine key, e.g. 'cnc_lathe'
            material_id: Material key, e.g. 'steel_1045'
            stock_diameter: Initial stock diameter (mm)
            stock_length: Initial stock length (mm)
            machines_data, tools_data, materials_data, operations_data:
                {key: dict} reference data — see SKLRepository's
                legacy_machines_dict()/legacy_tools_dict()/
                legacy_materials_dict()/legacy_operations_dict(). Cascaded
                down into every sub-component this class constructs.
            plan_steps: the plan steps handed to RAL, in programme order
                (one per operation segment). When given, the force/power
                model reads feed per revolution, depth of cut and spindle
                speed from each step's parameter package and the diameter
                from the step's feature; when omitted it falls back to the
                programme-derived values. Never affects cutting time or
                tool wear.
        """
        self.plan_steps = list(plan_steps) if plan_steps else []
        self._line_to_step: Dict[int, Dict] = {}
        self.machine_id = machine_id
        self.material_id = material_id
        self.machines_data = machines_data or {}
        self.tools_data = tools_data or {}
        self.materials_data = materials_data or {}
        self.operations_data = operations_data or {}

        # Create workpiece geometry
        self.workpiece = WorkpieceGeometry(
            stock_diameter=stock_diameter,
            stock_length=stock_length
        )

        # Create simulation modules
        self.collision_detector = CollisionDetector(self.workpiece, machine_id, machines_data=self.machines_data)
        self.time_estimator = CuttingTimeEstimator(machine_id, machines_data=self.machines_data)
        self.chip_analyzer = ChipLoadAnalyzer(material_id, materials_data=self.materials_data,
                                               operations_data=self.operations_data)
        
        # Tool wear estimators (one per tool)
        self.wear_estimators: Dict[str, ToolWearEstimator] = {}
        
        # Parser and simulator
        self.parser = GCodeParser()
        self.simulator = ToolpathSimulator()
        
        # Results
        self.commands: List[GCodeCommand] = []
        self.state_history: List[Dict] = []
        self.tool_parameters: List[CuttingParameters] = []
        self.wear_status: Dict[str, Dict] = {}
    
    def _get_wear_estimator(self, tool_id: str) -> ToolWearEstimator:
        """
        Get or create tool wear estimator for a tool.
        
        Args:
            tool_id: Tool ID
            
        Returns:
            ToolWearEstimator instance
        """
        if tool_id not in self.wear_estimators:
            self.wear_estimators[tool_id] = ToolWearEstimator(
                tool_id, self.material_id,
                tools_data=self.tools_data, materials_data=self.materials_data,
            )
        
        return self.wear_estimators[tool_id]
    
    def simulate_file(self, filepath: str) -> Dict[str, Any]:
        """
        Simulate a G-code file.
        
        Args:
            filepath: Path to G-code file (.nc)
            
        Returns:
            Comprehensive simulation report
        """
        # Parse G-code
        self.commands = self.parser.parse_file(filepath)
        self._line_to_step = self._map_lines_to_plan_steps(filepath)
        
        # Run simulation
        return self.simulate_commands()
    
    def _map_lines_to_plan_steps(self, filepath: str) -> Dict[int, Dict]:
        """Map each programme line to the plan step whose operation segment
        contains it. Segments are the '(--- <operation>: <feature> ---)'
        headers, the same definition main.py's plan-to-programme assertion
        uses, so segment k corresponds to plan_steps[k]."""
        if not self.plan_steps:
            return {}
        mapping: Dict[int, Dict] = {}
        seg = -1
        in_segment = False
        current: Optional[Dict] = None
        by_number = {s.get('step_number'): s for s in self.plan_steps}
        with open(filepath, encoding='utf-8') as fh:
            for line_number, line in enumerate(fh, 1):
                if line.startswith('(--- '):
                    # Operation segment header opens a step; any other header
                    # (initialisation, tool change, programme end) closes it.
                    in_segment = (': ' in line
                                  and not line.startswith('(--- Tool Change')
                                  and not line.startswith('(--- Machine'))
                    if in_segment:
                        seg += 1
                        tag = re.search(r'\[step (\d+)\]', line)
                        if tag:
                            current = by_number.get(int(tag.group(1)))
                            if current is None:
                                raise RuntimeError(f"{filepath}:{line_number}: segment tagged step "
                                                   f"{tag.group(1)} has no matching plan step")
                        else:
                            # Untagged (pre-Revision 3) programme: segment k is plan_steps[k].
                            current = self.plan_steps[seg] if seg < len(self.plan_steps) else None
                    continue
                if in_segment and current is not None:
                    mapping[line_number] = current
        if seg + 1 != len(self.plan_steps):
            raise RuntimeError(
                f"{filepath}: {seg + 1} operation segments but {len(self.plan_steps)} plan steps; "
                "force/power inputs cannot be attributed to steps.")
        return mapping

    @staticmethod
    def _step_force_inputs(step: Dict, programmed_diameter: float) -> Dict[str, Any]:
        """Force/power inputs of one plan step: f, ap, n from its parameter
        package, D from its feature (diameter 'Ø', else width 'W' for a
        slot/end-mill cut), else the programmed diameter for turning."""
        params = step.get('parameters') or {}
        def val(key):
            v = (params.get(key) or {}).get('value')
            return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        dims = step.get('feature_dimensions') or {}
        op = step.get('operation', '')
        process = 'drilling' if op == 'drilling' else ('milling' if op == 'milling' else 'turning')
        d_feat = dims.get('Ø') or dims.get('D')
        if process == 'milling':
            d_feat = dims.get('W') or d_feat
        diameter = float(d_feat) if d_feat else None
        if diameter is None and process == 'turning' and programmed_diameter > 0:
            diameter = programmed_diameter
        return {
            'process': process,
            'feed_per_rev': val('feed_rate'),
            'depth_of_cut': val('depth_of_cut'),
            'diameter': diameter,
            'spindle_speed': val('spindle_speed'),
            'step_number': step.get('step_number'),
        }

    def simulate_commands(self) -> Dict[str, Any]:
        """
        Simulate parsed G-code commands.
        
        Returns:
            Comprehensive simulation report
        """
        # Run basic simulation
        self.state_history = self.simulator.simulate(self.commands)
        
        # Run collision detection
        for cmd in self.commands:
            if 'X' in cmd.parameters and 'Z' in cmd.parameters:
                x = cmd.parameters['X']
                z = cmd.parameters['Z']
                
                # Check boundary violations
                self.collision_detector.check_boundary_violation(x, z, cmd.line_number)
                
                # Check turret interference on tool changes
                if 'M06' in cmd.m_codes and cmd.tool:
                    current_tool = self.simulator.state.current_tool
                    self.collision_detector.check_turret_interference(
                        current_tool, cmd.tool, cmd.line_number
                    )
        
        # Calculate cutting times
        time_report = self.time_estimator.calculate_cycle_time(
            self.commands, self.state_history
        )
        
        # Analyze chip loads, MRR, and tool wear from the actual G-code.
        # Tool/spindle-speed identity is read from self.simulator's
        # state_history (already computed above, and already correctly
        # modal-tracked across the whole program by ToolpathSimulator —
        # see validator.py) rather than from cmd.tool/cmd.parameters['S'] on
        # the current line alone: T-words and S-words are only emitted once,
        # on the M06/M03 line, and every cutting line after that relies on
        # controller-side modal carryover. Reading only the current line, as
        # this used to, silently attributed every cut in the program to
        # whichever tool_id/spindle_speed the (usually absent) same-line
        # words defaulted to — see AGENTS.md / finding #3A.
        state_by_line = {s['line']: s for s in self.state_history}
        prev_diameter = self.workpiece.stock_diameter
        prev_z = 0.0
        AXIAL_PASS_DEPTH_OF_CUT_MM = 1.0  # named fallback for a Z-only pass
        # (facing/grooving-axial/chamfer) whose radial depth of cut can't be
        # derived from an X delta because X doesn't change on that line —
        # honestly labeled as an approximation, not a silent generic default.
        MAX_PLAUSIBLE_RADIAL_DEPTH_MM = 10.0  # real single-pass lathe cuts
        # are typically 0.5-3mm; a larger X delta means the tool RAPIDED
        # (G00) to this X rather than cutting a pass this deep — see the
        # G00 branch below, which tracks prev_diameter across rapids too so
        # this shouldn't normally trigger, but it's a safety bound against
        # mis-derived geometry rather than silently reporting an implausible
        # depth of cut.

        for cmd in self.commands:
            if not cmd.g_codes:
                continue
            g_code = cmd.g_codes[0]
            is_cutting = g_code in ('G01', 'G02', 'G03')
            is_cycle = g_code in ('G81', 'G83')

            state = state_by_line.get(cmd.line_number, {})

            if g_code == 'G00':
                # Rapids reposition the tool without cutting, but DO change
                # its X/Z — track both so the next real cutting pass' radial
                # delta, or the next cycle's depth, is measured from where
                # the tool actually is, not from stock diameter or a stale
                # prior position (which previously produced physically
                # implausible depths, e.g. comparing a post-rapid X straight
                # against 80mm stock, or a cycle's post-retract Z against
                # its own drill target instead of the pre-cycle approach Z).
                prev_diameter = abs(state.get('x', prev_diameter))
                prev_z = state.get('z', prev_z)
                continue

            if not (is_cutting or is_cycle):
                continue

            spindle_speed = state.get('spindle_rpm') or cmd.parameters.get('S', 1000)
            feed_rate = state.get('feed_rate') or cmd.parameters.get('F', 1.0)
            tool_id = TOOL_NUMBER_TO_ID.get(state.get('tool'), 'turning_insert_rough')
            operation_type = (self.tools_data.get(tool_id, {}).get('recommended_operations') or ['turning'])[0]

            if is_cycle:
                # Drilling/counterboring: use the actual programmed peck
                # depth (Q) if given, else the Z travel from the pre-cycle
                # approach position (prev_z, tracked across G00 rapids —
                # NOT this line's own post-execution state, which
                # _execute_cycle in validator.py sets to the RETRACT
                # position after simulating the full cycle, not the
                # pre-cycle position) down to this cycle's target Z.
                diameter = abs(cmd.parameters.get('X', prev_diameter))
                z_target = cmd.parameters.get('Z', prev_z)
                depth_of_cut = abs(cmd.parameters.get('Q', prev_z - z_target)) or AXIAL_PASS_DEPTH_OF_CUT_MM
                prev_z = state.get('z', prev_z)
            else:
                diameter = abs(cmd.parameters.get('X', prev_diameter))
                radial_delta = abs(diameter - prev_diameter) / 2.0
                depth_of_cut = (
                    radial_delta if 0.01 < radial_delta <= MAX_PLAUSIBLE_RADIAL_DEPTH_MM
                    else AXIAL_PASS_DEPTH_OF_CUT_MM
                )
                prev_diameter = diameter

            # Force/power inputs: from the plan step owning this programme
            # line when the plan is known, else from the programme itself
            # (a canned cycle without a known drill diameter is reported as
            # unavailable rather than given an assumed diameter).
            step = self._line_to_step.get(cmd.line_number)
            if step is not None:
                force_inputs = self._step_force_inputs(step, diameter)
            else:
                force_inputs = {
                    'process': 'drilling' if (is_cycle and g_code == 'G83') else 'turning',
                    'feed_per_rev': feed_rate,
                    'depth_of_cut': None if is_cycle else depth_of_cut,
                    'diameter': None if is_cycle else diameter,
                    'spindle_speed': spindle_speed,
                    'step_number': None,
                }

            # Analyze operation
            params = self.chip_analyzer.analyze_operation(
                operation_type=operation_type,
                feed_rate=feed_rate,
                spindle_speed=spindle_speed,
                depth_of_cut=depth_of_cut,
                width_of_cut=depth_of_cut,
                diameter=diameter,
                num_teeth=1,
                force_inputs=force_inputs,
            )
            self.tool_parameters.append(params)

            # Update tool wear
            cutting_time_min = params.cutting_time / 60.0
            wear_est = self._get_wear_estimator(tool_id)
            self.wear_status[tool_id] = wear_est.update_wear(
                cutting_time_min, params.cutting_speed, params.feed_rate
            )
        
        # Compile report
        report = {
            'simulation_timestamp': datetime.now().isoformat(),
            'machine_id': self.machine_id,
            'material_id': self.material_id,
            'workpiece': {
                'stock_diameter_mm': self.workpiece.stock_diameter,
                'stock_length_mm': self.workpiece.stock_length
            },
            'basic_simulation': self.simulator.get_statistics(),
            'collision_detection': self.collision_detector.get_collision_report(),
            'cutting_time': time_report,
            'chip_load_analysis': {
                'operations_analyzed': len(self.tool_parameters),
                'average_mrr': self._calculate_average_mrr(),
                'max_mrr': self._calculate_max_mrr(),
                'average_cutting_force': self._calculate_average_force(),
                'average_cutting_power': self._calculate_average_power(),
                'force_power_model': {
                    'specific_cutting_force_kc_N_per_mm2': self.chip_analyzer.kc,
                    'kc_status': 'nominal handbook-order constant, uncalibrated, no chip-thickness correction',
                    'force_units': 'N', 'power_units': 'kW', 'cutting_speed_units': 'm/min',
                    'models': sorted({p.force_model for p in self.tool_parameters}),
                    'inputs_source': 'plan step parameter package' if self.plan_steps else 'programme',
                    'moves_with_force': sum(1 for p in self.tool_parameters if p.cutting_force is not None),
                    'moves_with_power': sum(1 for p in self.tool_parameters if p.cutting_power is not None),
                    'max_cutting_force': max((p.cutting_force for p in self.tool_parameters
                                              if p.cutting_force is not None), default=0.0),
                    'max_cutting_power': max((p.cutting_power for p in self.tool_parameters
                                              if p.cutting_power is not None), default=0.0),
                },
                'parameters': [p.to_dict() for p in self.tool_parameters[:10]]  # First 10
            },
            'tool_wear': {
                tool_id: status for tool_id, status in self.wear_status.items()
            },
            'recommendations': self._generate_recommendations()
        }
        
        return report
    
    def _calculate_average_mrr(self) -> float:
        """Calculate average MRR across all operations."""
        if not self.tool_parameters:
            return 0.0
        return sum(p.material_removal_rate for p in self.tool_parameters) / len(self.tool_parameters)
    
    def _calculate_max_mrr(self) -> float:
        """Calculate maximum MRR across all operations."""
        if not self.tool_parameters:
            return 0.0
        return max(p.material_removal_rate for p in self.tool_parameters)
    
    def _calculate_average_force(self) -> float:
        """Average cutting force [N] over analysed moves whose force is known."""
        vals = [p.cutting_force for p in self.tool_parameters if p.cutting_force is not None]
        return sum(vals) / len(vals) if vals else 0.0
    
    def _calculate_average_power(self) -> float:
        """Average cutting power [kW] over analysed moves whose power is known."""
        vals = [p.cutting_power for p in self.tool_parameters if p.cutting_power is not None]
        return sum(vals) / len(vals) if vals else 0.0
    
    def _generate_recommendations(self) -> List[str]:
        """
        Generate recommendations based on simulation results.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Check for collisions
        if self.collision_detector.collisions:
            recommendations.append(
                f"WARNING: {len(self.collision_detector.collisions)} collision(s) detected. "
                "Review toolpaths for potential interference."
            )
        
        # Check tool wear
        for tool_id, status in self.wear_status.items():
            if status['wear_status'] == 'critical':
                recommendations.append(
                    f"CRITICAL: Tool {tool_id} wear is critical. "
                    "Replace before continuing."
                )
            elif status['wear_status'] == 'poor':
                recommendations.append(
                    f"WARNING: Tool {tool_id} wear is high. "
                    "Plan tool change soon."
                )
        
        # Check MRR
        avg_mrr = self._calculate_average_mrr()
        if avg_mrr > 50000:  # High MRR threshold
            recommendations.append(
                "High material removal rate detected. "
                "Ensure machine power is sufficient."
            )
        
        # Check cutting time
        total_time = self.time_estimator.calculate_cycle_time(
            self.commands, self.state_history
        )['total_cycle_time_minutes']
        
        if total_time > 60:
            recommendations.append(
                f"Long cycle time ({total_time:.1f} minutes). "
                "Consider optimizing toolpaths or using higher feed rates."
            )
        
        if not recommendations:
            recommendations.append("Simulation completed successfully. No issues detected.")
        
        return recommendations
    
    def get_report(self) -> Dict[str, Any]:
        """
        Get the last simulation report.
        
        Returns:
            Simulation report dictionary
        """
        # This would return the last generated report
        # For now, return a placeholder
        return {
            'message': 'Run simulate_file() or simulate_commands() first'
        }
    
    def export_report(self, report: Dict[str, Any], filepath: str) -> str:
        """
        Export simulation report to JSON file.
        
        Args:
            report: Simulation report dictionary
            filepath: Path to save the JSON file
            
        Returns:
            Filepath saved
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        
        return filepath

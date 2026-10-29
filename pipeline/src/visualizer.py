"""
G-code Visualization Module
===========================
Generates 2D/3D visualizations of CNC toolpaths from G-code files.

This module provides:
- 2D toolpath visualization (X-Z plane, the primary lathe view)
- 3D toolpath visualization with rotational symmetry
- Color-coded paths by operation type (rapid vs cutting)
- Color-coded paths by tool number
- Workpiece outline overlay
- Tool change markers and operation annotations

Key Classes:
- GCodeVisualizer: Generates 2D/3D matplotlib visualizations from G-code

Supported Visualizations:
- 2D X-Z plane toolpath (front view of lathe operation)
- 3D rotational toolpath (shows the part geometry)
- Toolpath by operation type (rapid vs cutting colors)
- Toolpath by tool number (different color per tool)
- Workpiece cross-section overlay

Usage:
    visualizer = GCodeVisualizer()
    visualizer.visualize_file('output/motor_shaft_1001.nc', output_dir='output')
    
    # Or with specific options
    visualizer.visualize_file(
        'output/motor_shaft_1001.nc',
        output_dir='output',
        show_3d=True,
        color_by='tool',
        save_format='png'
    )
"""

import os
import re
import math
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for file generation
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Circle, Wedge
import numpy as np

# Import validator components for parsing
import sys
sys.path.insert(0, os.path.dirname(__file__))
from validator import GCodeParser, ToolpathSimulator, GCodeCommand


class GCodeVisualizer:
    """
    Generates 2D/3D visualizations of CNC toolpaths from G-code files.
    
    Attributes:
        parser: GCodeParser instance for parsing G-code
        simulator: ToolpathSimulator for tracking tool positions
        dpi: Resolution for saved figures (default: 150)
        
    Methods:
        visualize_file(): Generate visualizations from a G-code file
        visualize_2d(): Generate 2D X-Z plane toolpath plot
        visualize_3d(): Generate 3D rotational toolpath plot
        _extract_toolpath_segments(): Extract colored segments from simulation history
    """
    
    # Color palette for different operation types
    COLORS = {
        'rapid': '#000000',        # Black for rapid moves
        'cutting': '#FF0000',       # Red for cutting moves
        'drilling': '#0066CC',      # Blue for drilling operations
        'tool_change': '#FFD700',   # Gold for tool changes
    }
    
    # Color map for tools (up to 12 tools)
    TOOL_COLORS = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b',
        '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#aec7e8', '#ffbb78'
    ]
    
    def __init__(self, dpi: int = 150):
        """
        Initialize the G-code visualizer.
        
        Args:
            dpi: Resolution for saved figures (default: 150)
        """
        self.parser = GCodeParser()
        self.simulator = ToolpathSimulator()
        self.dpi = dpi
    
    def visualize_file(
        self,
        filepath: str,
        output_dir: str = 'output',
        show_2d: bool = True,
        show_3d: bool = True,
        color_by: str = 'operation',
        save_format: str = 'png',
        include_workpiece: bool = True
    ) -> Dict[str, str]:
        """
        Generate visualizations from a G-code file.
        
        Args:
            filepath: Path to the G-code file (.nc or .txt)
            output_dir: Directory to save visualization files
            show_2d: Generate 2D X-Z plane visualization
            show_3d: Generate 3D rotational visualization
            color_by: Color scheme ('operation' or 'tool')
            save_format: Image format ('png', 'svg', 'pdf')
            include_workpiece: Include workpiece outline overlay
            
        Returns:
            Dict with keys '2d_path', '3d_path' pointing to saved files
        """
        # Parse G-code file
        filename = os.path.splitext(os.path.basename(filepath))[0]
        commands = self.parser.parse_file(filepath)
        
        # Simulate toolpath
        self.simulator.simulate(commands)
        
        # Create output directory if needed
        os.makedirs(output_dir, exist_ok=True)
        
        result = {}
        
        # Generate 2D visualization
        if show_2d:
            fig_2d = self.visualize_2d(
                color_by=color_by,
                include_workpiece=include_workpiece
            )
            path_2d = os.path.join(output_dir, f'{filename}_toolpath_2d.{save_format}')
            fig_2d.savefig(path_2d, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig_2d)
            result['2d_path'] = path_2d
            print(f'  ✓ Saved 2D toolpath: {path_2d}')
        
        # Generate 3D visualization
        if show_3d:
            fig_3d = self.visualize_3d(
                color_by=color_by,
                include_workpiece=include_workpiece
            )
            path_3d = os.path.join(output_dir, f'{filename}_toolpath_3d.{save_format}')
            fig_3d.savefig(path_3d, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig_3d)
            result['3d_path'] = path_3d
            print(f'  ✓ Saved 3D toolpath: {path_3d}')
        
        return result
    
    def visualize_2d(
        self,
        color_by: str = 'operation',
        include_workpiece: bool = True
    ) -> plt.Figure:
        """
        Generate 2D X-Z plane toolpath visualization.
        
        Args:
            color_by: Color scheme ('operation' or 'tool')
            include_workpiece: Include workpiece outline overlay
            
        Returns:
            matplotlib Figure object
        """
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        
        # Extract toolpath segments
        segments = self._extract_toolpath_segments(color_by=color_by)
        
        # Track which labels have been shown to avoid duplicates
        labels_shown = set()
        
        # Plot each segment with appropriate color
        for segment in segments:
            x_coords = [p['x'] for p in segment['points']]
            z_coords = [p['z'] for p in segment['points']]
            
            # Only show label once per unique type
            label_key = segment['label']
            show_label = label_key not in labels_shown
            if show_label:
                labels_shown.add(label_key)
            
            ax.plot(
                x_coords,
                z_coords,
                color=segment['color'],
                linewidth=segment['linewidth'],
                linestyle=segment['linestyle'],
                label=segment['label'] if show_label else None,
                alpha=segment.get('alpha', 1.0)
            )
        
        # Add workpiece outline if requested
        if include_workpiece:
            self._add_workpiece_outline(ax)
        
        # Add tool change markers
        self._add_tool_change_markers(ax)
        
        # Configure axes
        ax.set_xlabel('X (mm) - Diameter', fontsize=12, fontweight='bold')
        ax.set_ylabel('Z (mm) - Distance from Chuck', fontsize=12, fontweight='bold')
        ax.set_title('CNC Lathe Toolpath Visualization (X-Z Plane)', fontsize=14, fontweight='bold')
        
        # Invert Z-axis (chuck face at Z=0, positive Z toward tailstock)
        ax.invert_yaxis()
        
        # Set reasonable axis limits based on data
        if segments:
            all_x = [p['x'] for seg in segments for p in seg['points']]
            all_z = [p['z'] for seg in segments for p in seg['points']]
            
            # Add 10% padding
            x_margin = (max(all_x) - min(all_x)) * 0.1 if max(all_x) != min(all_x) else 5
            z_margin = (max(all_z) - min(all_z)) * 0.1 if max(all_z) != min(all_z) else 5
            
            ax.set_xlim(min(all_x) - x_margin, max(all_x) + x_margin)
            ax.set_ylim(max(all_z) + z_margin, min(all_z) - z_margin)  # Inverted Z
        
        # Add grid
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # Add legend
        if segments:
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(handles, labels, loc='upper left', fontsize=8, framealpha=0.9)
        
        # Add statistics text box
        stats_text = self._generate_statistics_text()
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax.text(
            0.02, 0.02, stats_text,
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment='bottom',
            bbox=props
        )
        
        plt.tight_layout()
        return fig
    
    def visualize_3d(
        self,
        color_by: str = 'operation',
        include_workpiece: bool = True
    ) -> plt.Figure:
        """
        Generate 3D rotational toolpath visualization.
        
        Args:
            color_by: Color scheme ('operation' or 'tool')
            include_workpiece: Include workpiece outline overlay
            
        Returns:
            matplotlib Figure object
        """
        fig = plt.figure(figsize=(14, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # Extract toolpath segments
        segments = self._extract_toolpath_segments(color_by=color_by)
        
        # Plot each segment in 3D
        for segment in segments:
            x_coords = [p['x'] for p in segment['points']]
            z_coords = [p['z'] for p in segment['points']]
            
            # Convert to 3D (cylindrical coordinates)
            # X is diameter, so radius = X/2
            radii = [x / 2.0 for x in x_coords]
            
            # Generate points around the circle for each position
            theta = np.linspace(0, 2 * np.pi, 50)
            
            for i in range(len(radii) - 1):
                r1, z1 = radii[i], z_coords[i]
                r2, z2 = radii[i + 1], z_coords[i + 1]
                
                # Generate circular path at this segment
                x_circle1 = r1 * np.cos(theta)
                y_circle1 = r1 * np.sin(theta)
                z_circle1 = np.full_like(theta, z1)
                
                x_circle2 = r2 * np.cos(theta)
                y_circle2 = r2 * np.sin(theta)
                z_circle2 = np.full_like(theta, z2)
                
                # Plot the circular path
                ax.plot(
                    x_circle1, y_circle1, z_circle1,
                    color=segment['color'],
                    linewidth=segment['linewidth'] * 0.5,
                    alpha=segment.get('alpha', 0.7)
                )
                
                # Connect to next point
                ax.plot(
                    [x_circle1[-1], x_circle2[-1]],
                    [y_circle1[-1], y_circle2[-1]],
                    [z_circle1[-1], z_circle2[-1]],
                    color=segment['color'],
                    linewidth=segment['linewidth'],
                    alpha=segment.get('alpha', 1.0)
                )
        
        # Add workpiece surface if requested
        if include_workpiece:
            self._add_workpiece_surface(ax)
        
        # Configure axes
        ax.set_xlabel('X (mm) - Radius', fontsize=10, fontweight='bold')
        ax.set_ylabel('Y (mm) - Radius', fontsize=10, fontweight='bold')
        ax.set_zlabel('Z (mm) - Distance from Chuck', fontsize=10, fontweight='bold')
        ax.set_title('CNC Lathe Toolpath Visualization (3D Rotational)', fontsize=12, fontweight='bold')
        
        # Set viewing angle
        ax.view_init(elev=20, azim=45)
        
        # Add grid
        ax.grid(True, alpha=0.3, linestyle='--')
        
        plt.tight_layout()
        return fig
    
    def _extract_toolpath_segments(
        self,
        color_by: str = 'operation'
    ) -> List[Dict[str, Any]]:
        """
        Extract colored toolpath segments from simulation history.
        
        Args:
            color_by: Color scheme ('operation' or 'tool')
            
        Returns:
            List of segment dicts with 'points', 'color', 'label', etc.
        """
        segments = []
        history = self.simulator.state_history
        
        if not history:
            return segments
        
        # Group history entries by operation type or tool
        current_segment = {
            'points': [],
            'operation': None,
            'tool': None,
            'color': None,
            'label': None,
            'linewidth': 1.0,
            'linestyle': '-',
            'show_label': False,
            'alpha': 1.0
        }
        
        for i, state in enumerate(history):
            x = state['x']
            z = state['z']
            modal_g = state['modal_g']
            tool = state['tool']
            action = state.get('action', '')
            
            # Determine if this is a rapid or cutting move
            is_rapid = modal_g == 'G00'
            is_cutting = modal_g in ['G01', 'G02', 'G03']
            is_drilling = modal_g in ['G81', 'G83']
            
            # Determine segment type
            if color_by == 'operation':
                if is_rapid:
                    segment_type = 'rapid'
                    color = self.COLORS['rapid']
                    label = 'Rapid Move (G00)'
                    linewidth = 0.5
                    linestyle = '--'
                    alpha = 0.5
                elif is_drilling:
                    segment_type = 'drilling'
                    color = self.COLORS['drilling']
                    label = 'Drilling (G81/G83)'
                    linewidth = 2.0
                    linestyle = '-'
                    alpha = 0.8
                else:  # cutting
                    segment_type = 'cutting'
                    color = self.COLORS['cutting']
                    label = 'Cutting (G01/G02/G03)'
                    linewidth = 2.0
                    linestyle = '-'
                    alpha = 1.0
            else:  # color_by == 'tool'
                segment_type = f'tool_{tool}'
                color_idx = (tool - 1) % len(self.TOOL_COLORS)
                color = self.TOOL_COLORS[color_idx]
                label = f'Tool T{tool:02d}'
                linewidth = 1.5
                linestyle = '-'
                alpha = 0.8
            
            # Check if we need to start a new segment
            if (current_segment['points'] and 
                current_segment.get('segment_type') != segment_type):
                # Save current segment if it has points
                if len(current_segment['points']) > 1:
                    current_segment['show_label'] = True
                    segments.append(current_segment)
                
                # Start new segment
                current_segment = {
                    'points': [{'x': x, 'z': z}],
                    'segment_type': segment_type,
                    'operation': segment_type,
                    'tool': tool,
                    'color': color,
                    'label': label,
                    'linewidth': linewidth,
                    'linestyle': linestyle,
                    'show_label': False,
                    'alpha': alpha
                }
            elif not current_segment['points']:
                # Initialize first segment
                current_segment = {
                    'points': [{'x': x, 'z': z}],
                    'segment_type': segment_type,
                    'operation': segment_type,
                    'tool': tool,
                    'color': color,
                    'label': label,
                    'linewidth': linewidth,
                    'linestyle': linestyle,
                    'show_label': False,
                    'alpha': alpha
                }
            else:
                # Continue current segment
                current_segment['points'].append({'x': x, 'z': z})
        
        # Add final segment
        if len(current_segment['points']) > 1:
            current_segment['show_label'] = True
            segments.append(current_segment)
        
        return segments
    
    def _add_workpiece_outline(self, ax: plt.Axes):
        """
        Add workpiece outline to the 2D plot.
        
        Args:
            ax: matplotlib Axes object
        """
        # Extract workpiece profile from toolpath (minimum/maximum X at each Z)
        history = self.simulator.state_history
        
        if not history:
            return
        
        # Get the final workpiece profile (from cutting operations)
        z_positions = sorted(set([state['z'] for state in history]))
        x_positions = []
        
        for z in z_positions:
            states_at_z = [s for s in history if abs(s['z'] - z) < 0.01]
            if states_at_z:
                # Get minimum X at this Z (the final machined surface)
                min_x = min([s['x'] for s in states_at_z])
                x_positions.append(min_x)
        
        if x_positions:
            # Plot workpiece outline (symmetric about X=0)
            ax.fill_betweenx(
                z_positions,
                [-x for x in x_positions],
                x_positions,
                alpha=0.2,
                color='lightblue',
                label='Workpiece Profile'
            )
    
    def _add_workpiece_surface(self, ax: Axes3D):
        """
        Add workpiece surface to the 3D plot.
        
        Args:
            ax: matplotlib 3D Axes object
        """
        # Simplified workpiece surface (cylinder)
        history = self.simulator.state_history
        
        if not history:
            return
        
        # Get workpiece dimensions
        min_x = min([s['x'] for s in history]) / 2.0  # Convert diameter to radius
        max_x = max([s['x'] for s in history]) / 2.0
        min_z = min([s['z'] for s in history])
        max_z = max([s['z'] for s in history])
        
        # Generate cylinder surface
        theta = np.linspace(0, 2 * np.pi, 50)
        z_range = np.linspace(min_z, max_z, 20)
        Theta, Z = np.meshgrid(theta, z_range)
        
        # Outer cylinder
        X_outer = max_x * np.cos(Theta)
        Y_outer = max_x * np.sin(Theta)
        
        ax.plot_surface(
            X_outer, Y_outer, Z,
            alpha=0.1,
            color='lightblue',
            rstride=1, cstride=1
        )
    
    def _add_tool_change_markers(self, ax: plt.Axes):
        """
        Add tool change markers to the 2D plot.
        
        Args:
            ax: matplotlib Axes object
        """
        history = self.simulator.state_history
        
        # Find tool change points
        tool_changes = []
        prev_tool = None
        
        for state in history:
            current_tool = state['tool']
            if prev_tool is not None and current_tool != prev_tool:
                tool_changes.append(state)
            prev_tool = current_tool
        
        # Add markers at tool change locations
        for i, state in enumerate(tool_changes):
            ax.plot(
                state['x'],
                state['z'],
                'o',
                color=self.COLORS['tool_change'],
                markersize=8,
                markeredgecolor='black',
                markeredgewidth=1.5,
                label=f'Tool Change {i+1}' if i == 0 else None,
                zorder=5
            )
    
    def _generate_statistics_text(self) -> str:
        """
        Generate statistics text for the visualization.
        
        Returns:
            Formatted statistics string
        """
        stats = (
            f'Total Travel: {self.simulator.total_travel_distance:.2f}mm\n'
            f'Rapid Distance: {self.simulator.rapid_distance:.2f}mm\n'
            f'Cut Distance: {self.simulator.cut_distance:.2f}mm\n'
            f'Tool Changes: {self.simulator.tool_changes}\n'
            f'Blocks Executed: {self.simulator.blocks_executed}'
        )
        return stats


def visualize_gcode(
    filepath: str,
    output_dir: str = 'output',
    **kwargs
) -> Dict[str, str]:
    """
    Convenience function to visualize a G-code file.
    
    Args:
        filepath: Path to the G-code file
        output_dir: Directory to save visualization files
        **kwargs: Additional arguments passed to GCodeVisualizer.visualize_file()
        
    Returns:
        Dict with paths to saved visualization files
    """
    visualizer = GCodeVisualizer()
    return visualizer.visualize_file(filepath, output_dir, **kwargs)


if __name__ == '__main__':
    # Test visualization
    import sys
    
    if len(sys.argv) > 1:
        gcode_file = sys.argv[1]
    else:
        gcode_file = 'output/motor_shaft_1001.nc'
    
    if os.path.exists(gcode_file):
        print(f'Visualizing {gcode_file}...')
        result = visualize_gcode(gcode_file, output_dir='output')
        print(f'Visualization complete!')
        print(f'  2D: {result.get("2d_path", "N/A")}')
        print(f'  3D: {result.get("3d_path", "N/A")}')
    else:
        print(f'G-code file not found: {gcode_file}')
        sys.exit(1)

"""
PyAERMOD Building Downwash / BPIP Example

Demonstrates two workflows for building downwash in AERMOD:
  1. Scalar (legacy) — single value for all wind directions
  2. BPIP-calculated — 36 direction-dependent values from building geometry

Building downwash is critical when stacks are near buildings. The PRIME
algorithm in AERMOD uses direction-dependent building dimensions to compute
how the building wake affects plume dispersion.
"""

import os
import sys

# Ensure the parent directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyaermod_input_generator import PointSource
from pyaermod_bpip import Building, BPIPCalculator


def example_1_scalar_building():
    """
    Example 1: Scalar building downwash (simple, single-value)

    This approach assigns a single building dimension value for all
    wind directions. Suitable for screening-level analyses or when
    detailed building geometry is not available.
    """
    print("=" * 70)
    print("Example 1: Scalar Building Downwash (Legacy)")
    print("=" * 70)

    stack = PointSource(
        source_id="STACK1",
        x_coord=500.0,
        y_coord=500.0,
        base_elevation=0.0,
        stack_height=50.0,
        stack_temp=450.0,
        exit_velocity=15.0,
        stack_diameter=2.5,
        emission_rate=1.0,
        # Simple scalar building parameters
        building_height=25.0,
        building_width=40.0,
        building_length=30.0,
        building_x_offset=5.0,
        building_y_offset=-3.0,
    )

    output = stack.to_aermod_input()
    print("\nGenerated AERMOD input:")
    print(output)
    print()


def example_2_bpip_calculated():
    """
    Example 2: BPIP-calculated direction-dependent building downwash

    Defines building geometry (corners + height) and uses BPIPCalculator
    to compute 36 direction-dependent values for each building parameter.
    This is the production workflow for real permit applications.
    """
    print("=" * 70)
    print("Example 2: BPIP-Calculated Building Downwash (36 Directions)")
    print("=" * 70)

    # Define a rectangular building (40m × 30m, 25m tall)
    # Building corners in the same coordinate system as sources
    building = Building(
        building_id="WAREHOUSE",
        corners=[
            (480.0, 485.0),   # SW corner
            (520.0, 485.0),   # SE corner
            (520.0, 515.0),   # NE corner
            (480.0, 515.0),   # NW corner
        ],
        height=25.0,
    )

    print(f"\nBuilding: {building.building_id}")
    print(f"  Height: {building.height} m")
    print(f"  Footprint area: {building.get_footprint_area():.1f} m²")
    cx, cy = building.get_centroid()
    print(f"  Centroid: ({cx:.1f}, {cy:.1f})")

    # Define the stack near the building
    stack = PointSource(
        source_id="STACK1",
        x_coord=500.0,
        y_coord=500.0,
        base_elevation=0.0,
        stack_height=50.0,
        stack_temp=450.0,
        exit_velocity=15.0,
        stack_diameter=2.5,
        emission_rate=1.0,
    )

    # Calculate and apply BPIP results
    stack.set_building_from_bpip(building)

    print(f"\nStack: {stack.source_id} at ({stack.x_coord}, {stack.y_coord})")
    print(f"  Building height values (first 6 of 36): "
          f"{[f'{v:.2f}' for v in stack.building_height[:6]]}")
    print(f"  Building width values (first 6 of 36): "
          f"{[f'{v:.2f}' for v in stack.building_width[:6]]}")
    print(f"  Building length values (first 6 of 36): "
          f"{[f'{v:.2f}' for v in stack.building_length[:6]]}")

    output = stack.to_aermod_input()
    print("\nGenerated AERMOD input:")
    print(output)
    print()


def example_3_manual_bpip():
    """
    Example 3: Manual BPIP calculation with detailed inspection

    Shows how to use BPIPCalculator directly and inspect results
    for specific wind directions.
    """
    print("=" * 70)
    print("Example 3: Manual BPIP Calculation")
    print("=" * 70)

    # Building offset from stack
    building = Building(
        building_id="PROCESS",
        corners=[
            (30.0, -20.0),
            (70.0, -20.0),
            (70.0, 20.0),
            (30.0, 20.0),
        ],
        height=15.0,
    )

    stack_x, stack_y = 0.0, 0.0
    calc = BPIPCalculator(building, stack_x, stack_y)
    result = calc.calculate_all()

    print(f"\nBuilding '{building.building_id}' relative to stack at origin")
    print(f"  Building centroid: {building.get_centroid()}")
    print(f"  Building footprint: {building.get_footprint_area():.0f} m²")
    print()

    # Show results for cardinal directions
    directions = {
        "North (360°)": 35,
        "East (90°)": 8,
        "South (180°)": 17,
        "West (270°)": 26,
    }

    print(f"  {'Direction':<16} {'Height':>8} {'Width':>8} {'Length':>8} "
          f"{'XBADJ':>8} {'YBADJ':>8}")
    print(f"  {'-' * 56}")
    for name, idx in directions.items():
        print(f"  {name:<16} {result.buildhgt[idx]:8.2f} {result.buildwid[idx]:8.2f} "
              f"{result.buildlen[idx]:8.2f} {result.xbadj[idx]:8.2f} "
              f"{result.ybadj[idx]:8.2f}")
    print()


if __name__ == "__main__":
    example_1_scalar_building()
    example_2_bpip_calculated()
    example_3_manual_bpip()
    print("All BPIP examples completed successfully!")

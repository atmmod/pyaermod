"""
Tutorial 2 Solution — Comparing Stack Heights
===============================================

This script builds two AERMOD project variants: a 20 m stack and a 60 m
stack, both emitting SO2 at 2 g/s.  It generates separate input files for
each height and highlights the SRCPARAM difference.

Usage:
    python tutorial2_comparing_stack_heights.py [--output-dir DIR]

Outputs:
    stack_20m.inp             — AERMOD input file (20 m stack)
    stack_60m.inp             — AERMOD input file (60 m stack)
    tutorial2_20m_project.json — Serialized project (20 m)
    tutorial2_60m_project.json — Serialized project (60 m)
"""

import argparse
import dataclasses
import json
from pathlib import Path

from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
)


def build_project(stack_height: float) -> AERMODProject:
    """Build a Tutorial 2 project for the given stack height."""

    control = ControlPathway(
        title_one=f"Tutorial 2 - Stack Height Comparison ({int(stack_height)}m)",
        title_two="SO2, single source, varying stack height",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["1", "24", "ANNUAL"],
        terrain_type=TerrainType.FLAT,
    )

    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=500_000.0,
        y_coord=3_870_000.0,
        base_elevation=0.0,
        stack_height=stack_height,
        stack_temp=420.0,       # 420 K
        exit_velocity=15.0,     # m/s
        stack_diameter=2.0,     # meters
        emission_rate=2.0,      # g/s SO2
    ))

    # 4 km x 4 km centered on source, 100 m spacing → 41 x 41 = 1681
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=498_000.0,
        x_max=502_000.0,
        y_min=3_868_000.0,
        y_max=3_872_000.0,
        spacing=100.0,
        grid_name="GRID1",
    ))

    meteorology = MeteorologyPathway(
        surface_file="met_data.sfc",
        profile_file="met_data.pfl",
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True,
    )

    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output,
    )


def main(output_dir: str = ".") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # --- 20 m stack ---
    proj_20 = build_project(20.0)
    inp_20 = proj_20.to_aermod_input()
    path_20 = out / "stack_20m.inp"
    path_20.write_text(inp_20)
    print(f"  20 m input written to {path_20}")

    json_20 = out / "tutorial2_20m_project.json"
    json_20.write_text(json.dumps(
        dataclasses.asdict(proj_20), indent=2, default=str))
    print(f"  20 m project JSON written to {json_20}")

    # --- 60 m stack ---
    proj_60 = build_project(60.0)
    inp_60 = proj_60.to_aermod_input()
    path_60 = out / "stack_60m.inp"
    path_60.write_text(inp_60)
    print(f"  60 m input written to {path_60}")

    json_60 = out / "tutorial2_60m_project.json"
    json_60.write_text(json.dumps(
        dataclasses.asdict(proj_60), indent=2, default=str))
    print(f"  60 m project JSON written to {json_60}")

    # --- Verification ---
    print("\n--- Verification ---")

    # Both files should have all 5 pathways
    for label, inp in [("20m", inp_20), ("60m", inp_60)]:
        for pw in ["CO STARTING", "SO STARTING", "RE STARTING",
                    "ME STARTING", "OU STARTING"]:
            assert pw in inp, f"[{label}] Missing pathway: {pw}"
    print("  Both files: all 5 AERMOD pathways present")

    # Check pollutant
    assert "SO2" in inp_20 and "SO2" in inp_60, "SO2 pollutant missing"
    print("  Pollutant: SO2")

    # Check averaging periods
    for period in ["1", "24", "ANNUAL"]:
        assert period in inp_20, f"Averaging period {period} missing"
    print("  Averaging: 1-HR, 24-HR, ANNUAL")

    # Check stack heights differ — find the SRCPARAM lines
    srcparam_20 = [l for l in inp_20.splitlines() if "SRCPARAM" in l][0]
    srcparam_60 = [l for l in inp_60.splitlines() if "SRCPARAM" in l][0]
    assert "20.00" in srcparam_20, "20 m height missing from 20m SRCPARAM"
    assert "60.00" in srcparam_60, "60 m height missing from 60m SRCPARAM"
    assert srcparam_20 != srcparam_60, "SRCPARAM lines should differ"
    print("  Stack heights: 20 m and 60 m correctly differentiated")

    # Check grid dimensions
    grid = proj_20.receptors.cartesian_grids[0]
    assert grid.x_num == 41, f"Expected 41 x-points, got {grid.x_num}"
    assert grid.y_num == 41, f"Expected 41 y-points, got {grid.y_num}"
    total = grid.x_num * grid.y_num
    print(f"  Receptor grid: {grid.x_num} x {grid.y_num} = {total} receptors "
          f"(4km x 4km, 100m spacing)")

    # Show SRCPARAM differences
    print("\n--- SO SRCPARAM Comparison ---")
    for label, inp in [("20m", inp_20), ("60m", inp_60)]:
        for line in inp.splitlines():
            if "SRCPARAM" in line:
                print(f"  {label}: {line.strip()}")
    print("  (Only the stack height value differs)")

    print("\nTutorial 2 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 2 Solution: Comparing Stack Heights")
    parser.add_argument("--output-dir", default="tutorial2_output",
                        help="Directory for generated files")
    args = parser.parse_args()
    main(args.output_dir)

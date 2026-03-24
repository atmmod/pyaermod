"""
Tutorial 1 Solution — Your First Point Source
==============================================

This script programmatically builds the Tutorial 1 project: a single
point source (smokestack) emitting PM2.5 with a 4 km x 4 km receptor grid.

Usage:
    python tutorial1_first_point_source.py [--output-dir DIR]

Outputs:
    tutorial1.inp           — AERMOD input file
    tutorial1_project.json  — Serialized project (for GUI import)
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


def build_project() -> AERMODProject:
    """Build the Tutorial 1 project exactly as described in the student guide."""

    # --- Step 1: Project Setup ---
    control = ControlPathway(
        title_one="Tutorial 1 - My First Model",
        title_two="Single point source, PM2.5",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
    )

    # --- Step 2: Add a Point Source ---
    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=500_000.0,
        y_coord=3_870_000.0,
        base_elevation=0.0,
        stack_height=50.0,
        stack_temp=400.0,       # 400 K (~127 C)
        exit_velocity=15.0,     # m/s
        stack_diameter=2.0,     # meters
        emission_rate=1.5,      # g/s PM2.5
    ))

    # --- Step 3: Set Up Receptors ---
    # 4 km x 4 km centered on source, 200 m spacing → 21 x 21 = 441 receptors
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=498_000.0,
        x_max=502_000.0,
        y_min=3_868_000.0,
        y_max=3_872_000.0,
        spacing=200.0,
        grid_name="GRID1",
    ))

    # --- Step 4: Specify Meteorology ---
    meteorology = MeteorologyPathway(
        surface_file="met_data.sfc",
        profile_file="met_data.pfl",
    )

    # --- Step 5: Output ---
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

    project = build_project()
    inp_text = project.to_aermod_input()

    # Write input file
    inp_path = out / "tutorial1.inp"
    inp_path.write_text(inp_text)
    print(f"  Input file written to {inp_path}")
    print(f"  ({len(inp_text.splitlines())} lines)")

    # Write project JSON
    proj_dict = dataclasses.asdict(project)
    json_path = out / "tutorial1_project.json"
    json_path.write_text(json.dumps(proj_dict, indent=2, default=str))
    print(f"  Project JSON written to {json_path}")

    # --- Verification ---
    print("\n--- Verification ---")

    # Check five pathways
    for pw in ["CO STARTING", "SO STARTING", "RE STARTING",
                "ME STARTING", "OU STARTING"]:
        assert pw in inp_text, f"Missing pathway: {pw}"
    print("  All 5 AERMOD pathways present (CO, SO, RE, ME, OU)")

    # Check source
    assert "STACK1" in inp_text, "Source ID STACK1 missing"
    assert "POINT" in inp_text, "POINT source type missing"
    # SRCPARAM: emission_rate stack_height stack_temp exit_vel diameter
    assert "50.00" in inp_text, "Stack height 50 missing"
    assert "400.00" in inp_text, "Stack temp 400 K missing"
    assert "15.00" in inp_text, "Exit velocity 15 missing"
    print("  Source STACK1: height=50m, temp=400K, vel=15m/s, diam=2m, rate=1.5g/s")

    # Check receptor grid
    grid = project.receptors.cartesian_grids[0]
    total = grid.x_num * grid.y_num
    assert grid.x_num == 21, f"Expected 21 x-points, got {grid.x_num}"
    assert grid.y_num == 21, f"Expected 21 y-points, got {grid.y_num}"
    print(f"  Receptor grid: {grid.x_num} x {grid.y_num} = {total} receptors "
          f"(4km x 4km, 200m spacing)")

    # Check met file references
    assert "met_data.sfc" in inp_text, "Surface met file missing"
    assert "met_data.pfl" in inp_text, "Profile met file missing"
    print("  Meteorology: met_data.sfc / met_data.pfl")

    # Check pollutant and averaging
    assert "PM25" in inp_text, "Pollutant PM25 missing"
    assert "ANNUAL" in inp_text, "ANNUAL averaging missing"
    print("  Pollutant: PM2.5 | Averaging: ANNUAL, 24-HR")

    print("\nTutorial 1 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 1 Solution: Your First Point Source")
    parser.add_argument("--output-dir", default="tutorial1_output",
                        help="Directory for generated files")
    args = parser.parse_args()
    main(args.output_dir)

"""
Tutorial 3 Solution — Running AERMOD and Reading Results
=========================================================

This script creates the project and input file described in Tutorial 3.
It generates the input file and demonstrates how to optionally run AERMOD
and parse results if the executable and met data are available.

Usage:
    python tutorial3_running_aermod.py [--output-dir DIR] [--run]

Outputs:
    tutorial3.inp           — AERMOD input file
    tutorial3_project.json  — Serialized project (for GUI import)

With --run (requires AERMOD executable + met files in working dir):
    Runs AERMOD and prints summary statistics from the output.
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
    """Build the Tutorial 3 project: single PM2.5 point source for a full run."""

    control = ControlPathway(
        title_one="Tutorial 3 - Full AERMOD Run",
        title_two="PM2.5, single point source with met data",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
    )

    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=500_000.0,
        y_coord=3_870_000.0,
        base_elevation=0.0,
        stack_height=50.0,
        stack_temp=400.0,       # 400 K
        exit_velocity=15.0,     # m/s
        stack_diameter=2.0,     # meters
        emission_rate=1.5,      # g/s PM2.5
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


def main(output_dir: str = ".", run_aermod: bool = False) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    project = build_project()
    inp_text = project.to_aermod_input()

    # Write input file
    inp_path = out / "tutorial3.inp"
    inp_path.write_text(inp_text)
    print(f"  Input file written to {inp_path}")
    print(f"  ({len(inp_text.splitlines())} lines)")

    # Write project JSON
    proj_dict = dataclasses.asdict(project)
    json_path = out / "tutorial3_project.json"
    json_path.write_text(json.dumps(proj_dict, indent=2, default=str))
    print(f"  Project JSON written to {json_path}")

    # --- Verification ---
    print("\n--- Verification ---")

    # Check five pathways
    for pw in ["CO STARTING", "SO STARTING", "RE STARTING",
                "ME STARTING", "OU STARTING"]:
        assert pw in inp_text, f"Missing pathway: {pw}"
    print("  All 5 AERMOD pathways present")

    # Check source
    assert "STACK1" in inp_text, "Source ID STACK1 missing"
    assert "POINT" in inp_text, "POINT source type missing"
    assert "50.00" in inp_text, "Stack height 50 missing"
    print("  Source STACK1: height=50m, temp=400K, vel=15m/s, diam=2m, rate=1.5g/s")

    # Check receptor grid
    grid = project.receptors.cartesian_grids[0]
    assert grid.x_num == 41, f"Expected 41 x-points, got {grid.x_num}"
    assert grid.y_num == 41, f"Expected 41 y-points, got {grid.y_num}"
    total = grid.x_num * grid.y_num
    print(f"  Receptor grid: {grid.x_num} x {grid.y_num} = {total} receptors "
          f"(4km x 4km, 100m spacing)")

    # Check met files
    assert "met_data.sfc" in inp_text, "Surface met file missing"
    assert "met_data.pfl" in inp_text, "Profile met file missing"
    print("  Meteorology: met_data.sfc / met_data.pfl")

    # Check pollutant and averaging
    assert "PM25" in inp_text, "Pollutant PM25 missing"
    assert "ANNUAL" in inp_text, "ANNUAL averaging missing"
    print("  Pollutant: PM2.5 | Averaging: ANNUAL, 24-HR")

    # --- Optional: run AERMOD ---
    if run_aermod:
        print("\n--- Running AERMOD ---")
        try:
            from pyaermod.runner import AERMODRunner
            runner = AERMODRunner()
            result = runner.run(str(inp_path), working_dir=str(out))
            print(f"  AERMOD exit code: {result.returncode}")
            if result.returncode == 0:
                print("  Run completed successfully.")
                # Try to parse the output
                out_file = out / "aermod.out"
                if out_file.exists():
                    from pyaermod.output_parser import AERMODOutputParser
                    parser = AERMODOutputParser(str(out_file))
                    summary = parser.get_summary()
                    print(f"  Max concentration: {summary.get('max_concentration', 'N/A')} ug/m3")
            else:
                print("  Run failed. Check that met files exist in the output directory.")
                if result.stderr:
                    print(f"  stderr: {result.stderr[:500]}")
        except ImportError:
            print("  pyaermod.runner not available — skipping run.")
        except FileNotFoundError:
            print("  AERMOD executable not found on PATH — skipping run.")
        except Exception as e:
            print(f"  Could not run AERMOD: {e}")
            print("  This is expected if met data files are not present.")
    else:
        print("\n  (Use --run to attempt running AERMOD with actual met data)")

    print("\nTutorial 3 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 3 Solution: Running AERMOD and Reading Results")
    parser.add_argument("--output-dir", default="tutorial3_output",
                        help="Directory for generated files")
    parser.add_argument("--run", action="store_true",
                        help="Attempt to run AERMOD (requires executable + met data)")
    args = parser.parse_args()
    main(args.output_dir, args.run)

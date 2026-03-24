"""
Tutorial 7 Solution — Terrain Processing with AERMAP
=====================================================

This script creates the AERMOD project that would be used with AERMAP to
assign terrain elevations for the Houston Ship Channel refinery area.

It demonstrates:
1. Setting up an ELEVATED terrain project
2. Defining a placeholder source at the refinery center
3. Creating a 51x51 receptor grid at 100 m spacing
4. Generating the AERMOD input file in both FLAT and ELEVATED modes
   for comparison

Usage:
    python tutorial7_terrain.py [--output-dir DIR]

Outputs:
    terrain_elevated.inp    — AERMOD input with ELEVATED terrain
    terrain_flat.inp        — AERMOD input with FLAT terrain (for comparison)
    terrain_project.json    — Serialized project (for GUI import)

Note: Actually running AERMAP requires the AERMAP executable and DEM data.
This script generates the AERMOD project configurations that would feed
into AERMAP processing.
"""

import argparse
import dataclasses
import json
from pathlib import Path

from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
)


# --- Refinery center coordinates (UTM Zone 15N, NAD83) ---
REFINERY_X = 279_200.0
REFINERY_Y = 3_291_700.0
REFINERY_ELEV = 5.0  # ~5 m above sea level

# --- Receptor grid extent (5 km x 5 km centered on refinery) ---
GRID_X_MIN = 276_700.0
GRID_X_MAX = 281_700.0
GRID_Y_MIN = 3_289_200.0
GRID_Y_MAX = 3_294_200.0
GRID_SPACING = 100.0  # meters


def build_control(terrain: TerrainType) -> ControlPathway:
    """Create control pathway for terrain tutorial."""
    return ControlPathway(
        title_one="Tutorial 7 - Terrain Processing",
        title_two=f"Houston Ship Channel - {terrain.value} terrain",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["1", "24", "ANNUAL"],
        terrain_type=terrain,
    )


def build_sources() -> SourcePathway:
    """Placeholder FCC stack at refinery center."""
    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="FCCSTK",
        x_coord=REFINERY_X,
        y_coord=REFINERY_Y,
        base_elevation=REFINERY_ELEV,
        stack_height=60.0,
        stack_temp=470.0,
        exit_velocity=20.0,
        stack_diameter=3.0,
        emission_rate=5.0,
    ))
    return sources


def build_receptors() -> ReceptorPathway:
    """51x51 Cartesian grid at 100 m spacing."""
    receptors = ReceptorPathway()
    grid = CartesianGrid.from_bounds(
        x_min=GRID_X_MIN,
        x_max=GRID_X_MAX,
        y_min=GRID_Y_MIN,
        y_max=GRID_Y_MAX,
        spacing=GRID_SPACING,
        grid_name="MAIN",
    )
    receptors.add_cartesian_grid(grid)
    return receptors


def build_meteorology() -> MeteorologyPathway:
    """Reference the Houston 2023 met files from Tutorial 6."""
    return MeteorologyPathway(
        surface_file="houston_2023.sfc",
        profile_file="houston_2023.pfl",
    )


def build_output() -> OutputPathway:
    return OutputPathway(
        receptor_table=True,
        max_table=True,
    )


def build_project(terrain: TerrainType) -> AERMODProject:
    """Assemble full project for given terrain mode."""
    return AERMODProject(
        control=build_control(terrain),
        sources=build_sources(),
        receptors=build_receptors(),
        meteorology=build_meteorology(),
        output=build_output(),
    )


def main(output_dir: str = ".") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # --- Elevated terrain project ---
    proj_elev = build_project(TerrainType.ELEVATED)
    inp_elev = proj_elev.to_aermod_input()
    path_elev = out / "terrain_elevated.inp"
    path_elev.write_text(inp_elev)
    print(f"  ELEVATED input written to {path_elev}")

    # --- Flat terrain project (for comparison) ---
    proj_flat = build_project(TerrainType.FLAT)
    inp_flat = proj_flat.to_aermod_input()
    path_flat = out / "terrain_flat.inp"
    path_flat.write_text(inp_flat)
    print(f"  FLAT input written to {path_flat}")

    # --- Serialize project as JSON ---
    # Use the elevated project as the canonical solution
    proj_dict = dataclasses.asdict(proj_elev)
    json_path = out / "terrain_project.json"
    json_path.write_text(json.dumps(proj_dict, indent=2, default=str))
    print(f"  Project JSON written to {json_path}")

    # --- Verification ---
    print("\n--- Verification ---")

    # Check ELEVATED mode
    assert "ELEV" in inp_elev, "ELEVATED keyword missing"
    assert "FCCSTK" in inp_elev, "Source ID missing"
    assert "GRIDCART" in inp_elev, "Grid keyword missing"
    print("  ELEVATED project: all checks passed")

    # Check FLAT mode
    assert "FLAT" in inp_flat, "FLAT keyword missing"
    assert "FCCSTK" in inp_flat, "Source ID missing"
    print("  FLAT project: all checks passed")

    # Check grid dimensions
    grid = proj_elev.receptors.cartesian_grids[0]
    expected_nx = int((GRID_X_MAX - GRID_X_MIN) / GRID_SPACING) + 1  # 51
    expected_ny = int((GRID_Y_MAX - GRID_Y_MIN) / GRID_SPACING) + 1  # 51
    assert grid.x_num == expected_nx, (
        f"Expected {expected_nx} x-points, got {grid.x_num}")
    assert grid.y_num == expected_ny, (
        f"Expected {expected_ny} y-points, got {grid.y_num}")
    total_receptors = grid.x_num * grid.y_num
    print(f"  Grid: {grid.x_num} x {grid.y_num} = {total_receptors} receptors")

    # Show key differences between FLAT and ELEVATED
    print("\n--- FLAT vs ELEVATED Key Differences ---")
    flat_lines = inp_flat.splitlines()
    elev_lines = inp_elev.splitlines()
    for fl, el in zip(flat_lines, elev_lines):
        if fl != el:
            print(f"  FLAT:     {fl.strip()}")
            print(f"  ELEVATED: {el.strip()}")
            print()

    # Source base elevation
    print(f"  Source base elevation: {REFINERY_ELEV} m (near sea level)")
    print(f"  Note: After AERMAP processing, receptors will have")
    print(f"  individual elevations ranging from ~0 to ~25 m.")

    # Discussion question hints
    print("\n--- Discussion Question Hints ---")
    print("  Q1 (Resolution): 50m spacing = 101x101 = 10,201 receptors")
    print(f"      vs current 100m = {total_receptors} receptors (4x more computation)")
    print("  Q2 (Hill height): z_hill is the terrain peak within AERMOD's")
    print("      critical dividing streamline radius; z_elev is local height.")
    print("  Q3 (Significance): terrain_range/effective_height = 25/~120 = 0.21")
    print("      > 0.1 threshold, so terrain effects are non-negligible.")

    print("\nTutorial 7 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 7 Solution: Terrain Processing")
    parser.add_argument("--output-dir", default="tutorial7_output",
                        help="Directory for generated files")
    args = parser.parse_args()
    main(args.output_dir)

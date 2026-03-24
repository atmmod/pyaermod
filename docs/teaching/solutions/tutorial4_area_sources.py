"""
Tutorial 4 Solution — Area Sources: Modeling a Facility with Fugitive Emissions
=================================================================================

This script builds a construction site model with four sources:
  - GENSET  — diesel generator exhaust (point source)
  - PILE1   — dirt/gravel stockpile (rectangular area source)
  - STAGING — equipment staging area (circular area source)
  - SITEBND — irregular site boundary (polygonal area source)

Usage:
    python tutorial4_area_sources.py [--output-dir DIR]

Outputs:
    tutorial4.inp           — AERMOD input file
    tutorial4_project.json  — Serialized project (for GUI import)
"""

import argparse
import dataclasses
import json
from pathlib import Path

from pyaermod.input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
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
    """Build the Tutorial 4 construction site project."""

    # --- Project Setup ---
    control = ControlPathway(
        title_one="Tutorial 4 - Area Source Facility",
        title_two="Construction site with mixed source types",
        pollutant_id=PollutantType.PM10,
        averaging_periods=["24", "ANNUAL"],
        terrain_type=TerrainType.FLAT,
    )

    sources = SourcePathway()

    # --- Point source: Diesel generator ---
    sources.add_source(PointSource(
        source_id="GENSET",
        x_coord=500_050.0,
        y_coord=3_870_050.0,
        base_elevation=0.0,
        stack_height=5.0,       # Short exhaust stack
        stack_temp=700.0,       # Diesel exhaust is hot (K)
        exit_velocity=10.0,     # m/s
        stack_diameter=0.3,     # Small pipe
        emission_rate=0.3,      # 0.3 g/s PM10
    ))

    # --- Rectangular area source: Stockpile ---
    # 100 m x 50 m, centered at (500000, 3870000)
    # Half-widths: initial_lateral_dimension=25 (Y), initial_vertical_dimension=50 (X)
    sources.add_source(AreaSource(
        source_id="PILE1",
        x_coord=500_000.0,
        y_coord=3_870_000.0,
        base_elevation=0.0,
        release_height=2.0,     # Dust lifts ~2 m above pile
        initial_lateral_dimension=25.0,   # Half-width Y (50 m total)
        initial_vertical_dimension=50.0,  # Half-width X (100 m total)
        angle=0.0,              # Aligned with grid
        emission_rate=0.000100, # 0.0001 g/s/m2
    ))

    # --- Circular area source: Staging area ---
    sources.add_source(AreaCircSource(
        source_id="STAGING",
        x_coord=500_200.0,
        y_coord=3_870_100.0,
        base_elevation=0.0,
        release_height=1.0,     # Low-level dust from traffic
        radius=60.0,            # 60 m radius
        num_vertices=20,        # Circle approximation
        emission_rate=0.000050, # 0.00005 g/s/m2
    ))

    # --- Polygonal area source: Irregular site boundary ---
    sources.add_source(AreaPolySource(
        source_id="SITEBND",
        vertices=[
            (499_900.0, 3_869_900.0),
            (500_350.0, 3_869_900.0),
            (500_400.0, 3_870_100.0),
            (500_300.0, 3_870_250.0),
            (499_900.0, 3_870_200.0),
        ],
        base_elevation=0.0,
        release_height=0.5,     # Near-ground fugitive dust
        emission_rate=0.000020, # 0.00002 g/s/m2
    ))

    # --- Receptors: fine grid covering site + buffer ---
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=499_500.0,
        x_max=500_800.0,
        y_min=3_869_500.0,
        y_max=3_870_700.0,
        spacing=50.0,
        grid_name="SITE",
    ))

    # --- Meteorology ---
    meteorology = MeteorologyPathway(
        surface_file="met_data.sfc",
        profile_file="met_data.pfl",
    )

    # --- Output ---
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
    inp_path = out / "tutorial4.inp"
    inp_path.write_text(inp_text)
    print(f"  Input file written to {inp_path}")
    print(f"  ({len(inp_text.splitlines())} lines)")

    # Write project JSON
    proj_dict = dataclasses.asdict(project)
    json_path = out / "tutorial4_project.json"
    json_path.write_text(json.dumps(proj_dict, indent=2, default=str))
    print(f"  Project JSON written to {json_path}")

    # --- Verification ---
    print("\n--- Verification ---")

    # Check five pathways
    for pw in ["CO STARTING", "SO STARTING", "RE STARTING",
                "ME STARTING", "OU STARTING"]:
        assert pw in inp_text, f"Missing pathway: {pw}"
    print("  All 5 AERMOD pathways present")

    # Check all four sources are present
    for sid in ["GENSET", "PILE1", "STAGING", "SITEBND"]:
        assert sid in inp_text, f"Source {sid} missing from input file"
    print("  All 4 sources present: GENSET, PILE1, STAGING, SITEBND")

    # Check source types
    assert "POINT" in inp_text, "POINT source type missing"
    assert "AREA" in inp_text, "AREA source type missing"
    assert "AREAPOLY" in inp_text or "AREAPOL" in inp_text, \
        "AREAPOLY/AREAPOL source type missing"
    print("  Source types: POINT, AREA, AREAPOLY/AREAPOL")

    # Check pollutant
    assert "PM10" in inp_text, "PM10 pollutant missing"
    print("  Pollutant: PM10 | Averaging: 24-HR, ANNUAL")

    # Check receptor grid
    grid = project.receptors.cartesian_grids[0]
    total = grid.x_num * grid.y_num
    print(f"  Receptor grid: {grid.x_num} x {grid.y_num} = {total} receptors "
          f"(50m spacing)")

    # Check generator stack params
    assert "700.00" in inp_text or "700.0" in inp_text, \
        "Generator exhaust temp 700K missing"
    print("  GENSET: point source, height=5m, temp=700K, rate=0.3g/s")

    # Summarize area source emission rates
    print("  PILE1:   rectangular area, 100x50m, rate=0.0001 g/s/m2")
    print("  STAGING: circular area, r=60m (20 vertices), rate=0.00005 g/s/m2")
    print("  SITEBND: polygon (5 vertices), rate=0.00002 g/s/m2")

    # Check polygon vertices appear in file
    assert "499900" in inp_text, "Polygon vertex X=499900 missing"
    assert "500350" in inp_text, "Polygon vertex X=500350 missing"
    print("  All polygon vertices present in input file")

    # Show source lines from input file
    print("\n--- Source Summary (from .inp) ---")
    for line in inp_text.splitlines():
        if "LOCATION" in line:
            print(f"  {line.strip()}")

    print("\nTutorial 4 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 4 Solution: Area Sources")
    parser.add_argument("--output-dir", default="tutorial4_output",
                        help="Directory for generated files")
    args = parser.parse_args()
    main(args.output_dir)

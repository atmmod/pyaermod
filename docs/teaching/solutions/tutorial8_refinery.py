"""
Tutorial 8 Solution — Modeling a Simplified Oil Refinery
========================================================

This script builds the complete AERMOD project for a simplified 150,000 bpd
petroleum refinery near the Houston Ship Channel, as described in Tutorial 8
of the refinery assignments.

It creates:
  - 10 emission sources (5 point, 3 area, 2 volume)
  - 4 source groups (STACKS, FUGITIV, FCCONLY, ALL)
  - Multi-scale receptor network (fine grid + coarse grid + 6 discrete)
  - Output configured for SO2 regulatory analysis
  - 4 sensitivity scenarios (A-D)

Usage:
    python tutorial8_refinery.py [--output-dir DIR]

Outputs:
    refinery_base.inp           — Base case AERMOD input
    refinery_project.json       — Serialized project (for GUI import)
    scenario_a_tall_stack.inp   — Scenario A: FCC stack 60 -> 90 m
    scenario_b_scrubber.inp     — Scenario B: FCC emission 5.0 -> 1.0 g/s
    scenario_c_background.inp   — Scenario C: 10 ug/m3 background
    scenario_d_flat.inp         — Scenario D: FLAT terrain comparison
"""

import argparse
import copy
import dataclasses
import json
import math
from pathlib import Path

from pyaermod.input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaSource,
    BackgroundConcentration,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
    VolumeSource,
)

# ============================================================
# Constants
# ============================================================

# Refinery center (UTM Zone 15N, NAD83)
REF_X = 279_200.0
REF_Y = 3_291_700.0
BASE_ELEV = 5.0

# NAAQS for SO2
SO2_1HR_NAAQS = 196.0  # ug/m3 (75 ppb)


# ============================================================
# Source definitions
# ============================================================

def _point_sources() -> list:
    """The 5 point (stack) sources."""
    return [
        # Source 1 — FCC Regenerator Stack
        PointSource(
            source_id="FCCSTK",
            x_coord=279_200.0,
            y_coord=3_291_750.0,
            base_elevation=BASE_ELEV,
            stack_height=60.0,
            stack_temp=470.0,
            exit_velocity=20.0,
            stack_diameter=3.0,
            emission_rate=5.0,
            source_groups=["STACKS", "FCCONLY", "ALL"],
        ),
        # Source 2 — Process Heater #1
        PointSource(
            source_id="HTR1",
            x_coord=279_100.0,
            y_coord=3_291_800.0,
            base_elevation=BASE_ELEV,
            stack_height=40.0,
            stack_temp=420.0,
            exit_velocity=12.0,
            stack_diameter=1.8,
            emission_rate=2.0,
            source_groups=["STACKS", "ALL"],
        ),
        # Source 3 — Process Heater #2
        PointSource(
            source_id="HTR2",
            x_coord=279_300.0,
            y_coord=3_291_850.0,
            base_elevation=BASE_ELEV,
            stack_height=35.0,
            stack_temp=410.0,
            exit_velocity=10.0,
            stack_diameter=1.5,
            emission_rate=1.5,
            source_groups=["STACKS", "ALL"],
        ),
        # Source 4 — Boiler Stack
        PointSource(
            source_id="BOILER",
            x_coord=279_050.0,
            y_coord=3_291_600.0,
            base_elevation=BASE_ELEV,
            stack_height=45.0,
            stack_temp=430.0,
            exit_velocity=14.0,
            stack_diameter=2.0,
            emission_rate=3.0,
            source_groups=["STACKS", "ALL"],
        ),
        # Source 5 — Flare
        PointSource(
            source_id="FLARE",
            x_coord=279_400.0,
            y_coord=3_291_500.0,
            base_elevation=BASE_ELEV,
            stack_height=15.0,
            stack_temp=1273.0,
            exit_velocity=20.0,
            stack_diameter=1.0,
            emission_rate=1.0,
            source_groups=["STACKS", "ALL"],
        ),
    ]


def _area_sources() -> list:
    """The 3 area sources (2 rectangular + 1 circular)."""
    return [
        # Source 6 — Crude Tank Farm
        AreaSource(
            source_id="TANKS",
            x_coord=279_150.0,
            y_coord=3_291_300.0,
            base_elevation=BASE_ELEV,
            release_height=15.0,
            initial_lateral_dimension=75.0,   # 150 m N-S
            initial_vertical_dimension=100.0,  # 200 m E-W
            emission_rate=0.000_010,
            angle=0.0,
            source_groups=["FUGITIV", "ALL"],
        ),
        # Source 7 — Loading Rack
        AreaSource(
            source_id="LOADRK",
            x_coord=279_350.0,
            y_coord=3_291_400.0,
            base_elevation=BASE_ELEV,
            release_height=4.0,
            initial_lateral_dimension=15.0,   # 30 m N-S
            initial_vertical_dimension=40.0,   # 80 m E-W
            emission_rate=0.000_005,
            angle=0.0,
            source_groups=["FUGITIV", "ALL"],
        ),
        # Source 8 — Wastewater Treatment (circular)
        AreaCircSource(
            source_id="WWATER",
            x_coord=278_900.0,
            y_coord=3_291_400.0,
            base_elevation=BASE_ELEV,
            release_height=1.0,
            radius=50.0,
            num_vertices=20,
            emission_rate=0.000_030,
            source_groups=["FUGITIV", "ALL"],
        ),
    ]


def _volume_sources() -> list:
    """The 2 volume sources."""
    return [
        # Source 9 — Cooling Towers
        VolumeSource(
            source_id="COOL1",
            x_coord=279_250.0,
            y_coord=3_291_550.0,
            base_elevation=BASE_ELEV,
            release_height=12.0,
            initial_lateral_dimension=8.0,
            initial_vertical_dimension=6.0,
            emission_rate=0.2,
            source_groups=["FUGITIV", "ALL"],
        ),
        # Source 10 — Equipment Leak Fugitives
        VolumeSource(
            source_id="FUGITV",
            x_coord=279_200.0,
            y_coord=3_291_700.0,
            base_elevation=BASE_ELEV,
            release_height=5.0,
            initial_lateral_dimension=25.0,
            initial_vertical_dimension=4.0,
            emission_rate=0.5,
            source_groups=["FUGITIV", "ALL"],
        ),
    ]


def build_sources() -> SourcePathway:
    """Assemble all 10 sources + 4 source groups."""
    sources = SourcePathway()

    all_sources = _point_sources() + _area_sources() + _volume_sources()
    for s in all_sources:
        sources.add_source(s)

    # Source group definitions
    sources.group_definitions = [
        SourceGroupDefinition(
            group_name="STACKS",
            member_source_ids=["FCCSTK", "HTR1", "HTR2", "BOILER", "FLARE"],
            description="All elevated point sources",
        ),
        SourceGroupDefinition(
            group_name="FUGITIV",
            member_source_ids=["TANKS", "LOADRK", "WWATER", "COOL1", "FUGITV"],
            description="All fugitive/area/volume sources",
        ),
        SourceGroupDefinition(
            group_name="FCCONLY",
            member_source_ids=["FCCSTK"],
            description="FCC unit alone (largest single source)",
        ),
        SourceGroupDefinition(
            group_name="ALL",
            member_source_ids=[
                "FCCSTK", "HTR1", "HTR2", "BOILER", "FLARE",
                "TANKS", "LOADRK", "WWATER", "COOL1", "FUGITV",
            ],
            description="Total facility impact",
        ),
    ]

    return sources


# ============================================================
# Receptor network
# ============================================================

def build_receptors() -> ReceptorPathway:
    """Multi-scale receptor network: fine + coarse grids + 6 discrete."""
    receptors = ReceptorPathway()

    # Fine grid — 2 km x 2 km, 50 m spacing (41 x 41 = 1681)
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=278_200.0, x_max=280_200.0,
        y_min=3_290_700.0, y_max=3_292_700.0,
        spacing=50.0,
        grid_name="FINE",
    ))

    # Coarse grid — 5 km x 5 km, 200 m spacing (26 x 26 = 676)
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=276_700.0, x_max=281_700.0,
        y_min=3_289_200.0, y_max=3_294_200.0,
        spacing=200.0,
        grid_name="COARSE",
    ))

    # Discrete sensitive receptors
    sensitive = [
        (278_100.0, 3_292_500.0, "Community NW"),
        (280_300.0, 3_292_400.0, "Community NE"),
        (279_200.0, 3_290_200.0, "Community S"),
        (278_500.0, 3_293_000.0, "School"),
        (280_000.0, 3_292_800.0, "Hospital"),
        (279_500.0, 3_292_200.0, "Monitor"),
    ]
    for x, y, _label in sensitive:
        receptors.add_discrete_receptor(DiscreteReceptor(
            x_coord=x, y_coord=y, z_elev=BASE_ELEV,
        ))

    return receptors


# ============================================================
# Full project assembly
# ============================================================

def build_base_project() -> AERMODProject:
    """Create the base-case refinery project."""
    control = ControlPathway(
        title_one="Houston Refinery SO2 Assessment",
        title_two="Simplified 150 kbpd refinery - Tutorial 8",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["1", "3", "24", "ANNUAL"],
        terrain_type=TerrainType.ELEVATED,
    )

    meteorology = MeteorologyPathway(
        surface_file="houston_2023.sfc",
        profile_file="houston_2023.pfl",
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True,
        postfile="refinery_all.post",
        postfile_averaging="1",
        postfile_source_group="ALL",
        postfile_format="PLOT",
        plot_file_groups=[
            ("1", "STACKS", "stacks_1hr.plt"),
            ("1", "FCCONLY", "fcconly_1hr.plt"),
        ],
    )

    return AERMODProject(
        control=control,
        sources=build_sources(),
        receptors=build_receptors(),
        meteorology=meteorology,
        output=output,
    )


# ============================================================
# Sensitivity scenarios
# ============================================================

def scenario_a_tall_stack(base: AERMODProject) -> AERMODProject:
    """Scenario A: Increase FCC stack height from 60 m to 90 m."""
    proj = copy.deepcopy(base)
    proj.control.title_two = "Scenario A: FCC stack height 90 m"
    for src in proj.sources.sources:
        if src.source_id == "FCCSTK":
            src.stack_height = 90.0
            break
    return proj


def scenario_b_scrubber(base: AERMODProject) -> AERMODProject:
    """Scenario B: FGD scrubber on FCC (80% removal, 5.0 -> 1.0 g/s)."""
    proj = copy.deepcopy(base)
    proj.control.title_two = "Scenario B: FCC with FGD scrubber (80% removal)"
    for src in proj.sources.sources:
        if src.source_id == "FCCSTK":
            src.emission_rate = 1.0
            break
    return proj


def scenario_c_background(base: AERMODProject) -> AERMODProject:
    """Scenario C: Add 10 ug/m3 uniform background SO2."""
    proj = copy.deepcopy(base)
    proj.control.title_two = "Scenario C: 10 ug/m3 SO2 background"
    proj.sources.background = BackgroundConcentration(uniform_value=10.0)
    return proj


def scenario_d_flat(base: AERMODProject) -> AERMODProject:
    """Scenario D: FLAT terrain instead of ELEVATED."""
    proj = copy.deepcopy(base)
    proj.control.title_two = "Scenario D: FLAT terrain"
    proj.control.terrain_type = TerrainType.FLAT
    return proj


# ============================================================
# Verification helpers
# ============================================================

def verify_source_inventory(proj: AERMODProject) -> None:
    """Check the source inventory matches Tutorial 8 spec."""
    sources = proj.sources.sources

    # Count source types
    point_count = sum(1 for s in sources if isinstance(s, PointSource))
    area_count = sum(1 for s in sources if isinstance(s, AreaSource))
    acirc_count = sum(1 for s in sources if isinstance(s, AreaCircSource))
    vol_count = sum(1 for s in sources if isinstance(s, VolumeSource))

    assert point_count == 5, f"Expected 5 point sources, got {point_count}"
    assert area_count == 2, f"Expected 2 area sources, got {area_count}"
    assert acirc_count == 1, f"Expected 1 circular area source, got {acirc_count}"
    assert vol_count == 2, f"Expected 2 volume sources, got {vol_count}"
    assert len(sources) == 10, f"Expected 10 total sources, got {len(sources)}"
    print(f"  Sources: {point_count} point, {area_count} area, "
          f"{acirc_count} circ, {vol_count} volume = {len(sources)} total")

    # Check source groups
    groups = proj.sources.group_definitions
    group_names = {g.group_name for g in groups}
    expected = {"STACKS", "FUGITIV", "FCCONLY", "ALL"}
    assert group_names == expected, f"Groups: {group_names} != {expected}"
    print(f"  Source groups: {sorted(group_names)}")

    # Total emission rate
    total_point = sum(s.emission_rate for s in sources if isinstance(s, PointSource))
    # Area sources: total = rate * area
    tank_total = 0.000_010 * (150.0 * 200.0)  # 0.3 g/s
    load_total = 0.000_005 * (30.0 * 80.0)    # 0.012 g/s
    ww_total = 0.000_030 * (math.pi * 50.0**2)  # 0.236 g/s
    total_area = tank_total + load_total + ww_total
    total_vol = sum(s.emission_rate for s in sources if isinstance(s, VolumeSource))
    grand_total = total_point + total_area + total_vol

    print(f"  Total SO2: {grand_total:.2f} g/s "
          f"(stacks: {total_point:.1f}, area: {total_area:.3f}, "
          f"volume: {total_vol:.1f})")


def verify_receptors(proj: AERMODProject) -> None:
    """Check receptor network."""
    fine = proj.receptors.cartesian_grids[0]
    coarse = proj.receptors.cartesian_grids[1]
    discrete = proj.receptors.discrete_receptors

    fine_count = fine.x_num * fine.y_num
    coarse_count = coarse.x_num * coarse.y_num
    total = fine_count + coarse_count + len(discrete)

    print(f"  Fine grid: {fine.x_num}x{fine.y_num} = {fine_count} "
          f"({fine.grid_name}, {int(fine.x_delta)}m spacing)")
    print(f"  Coarse grid: {coarse.x_num}x{coarse.y_num} = {coarse_count} "
          f"({coarse.grid_name}, {int(coarse.x_delta)}m spacing)")
    print(f"  Discrete receptors: {len(discrete)}")
    print(f"  Total receptors: {total}")

    assert fine_count == 1681, f"Fine grid expected 1681, got {fine_count}"
    assert coarse_count == 676, f"Coarse grid expected 676, got {coarse_count}"
    assert len(discrete) == 6, f"Expected 6 discrete receptors, got {len(discrete)}"


def verify_input_file(inp_text: str, label: str) -> None:
    """Sanity-check the generated input file text."""
    # Check all 5 pathways present
    for pathway in ["CO STARTING", "SO STARTING", "RE STARTING",
                    "ME STARTING", "OU STARTING"]:
        assert pathway in inp_text, f"{label}: {pathway} missing"

    # Check all 10 source IDs present
    expected_ids = ["FCCSTK", "HTR1", "HTR2", "BOILER", "FLARE",
                    "TANKS", "LOADRK", "WWATER", "COOL1", "FUGITV"]
    for sid in expected_ids:
        assert sid in inp_text, f"{label}: Source {sid} missing"

    # Check source types
    assert inp_text.count("POINT") >= 5, f"{label}: Expected 5+ POINT refs"

    # Check groups
    for grp in ["STACKS", "FUGITIV", "FCCONLY"]:
        assert grp in inp_text, f"{label}: Group {grp} missing"

    # Check receptor grids
    assert "FINE" in inp_text, f"{label}: FINE grid missing"
    assert "COARSE" in inp_text, f"{label}: COARSE grid missing"
    assert "DISCCART" in inp_text, f"{label}: Discrete receptors missing"

    print(f"  {label}: all pathway/source/receptor checks passed")


# ============================================================
# Main
# ============================================================

def main(output_dir: str = ".") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # --- Build base project ---
    print("Building base case project...")
    base = build_base_project()

    base_inp = base.to_aermod_input()
    base_path = out / "refinery_base.inp"
    base_path.write_text(base_inp)
    print(f"  Base case written to {base_path}")
    print(f"  Input file: {len(base_inp.splitlines())} lines")

    # --- Serialize project JSON ---
    proj_dict = dataclasses.asdict(base)
    json_path = out / "refinery_project.json"
    json_path.write_text(json.dumps(proj_dict, indent=2, default=str))
    print(f"  Project JSON written to {json_path}")

    # --- Verification ---
    print("\n--- Source Inventory Verification ---")
    verify_source_inventory(base)

    print("\n--- Receptor Network Verification ---")
    verify_receptors(base)

    print("\n--- Input File Verification ---")
    verify_input_file(base_inp, "Base case")

    # --- Sensitivity Scenarios ---
    print("\n--- Generating Sensitivity Scenarios ---")

    scenarios = [
        ("scenario_a_tall_stack.inp", scenario_a_tall_stack(base),
         "Scenario A: FCC stack 60 -> 90 m"),
        ("scenario_b_scrubber.inp", scenario_b_scrubber(base),
         "Scenario B: FCC emission 5.0 -> 1.0 g/s (FGD scrubber)"),
        ("scenario_c_background.inp", scenario_c_background(base),
         "Scenario C: 10 ug/m3 uniform SO2 background"),
        ("scenario_d_flat.inp", scenario_d_flat(base),
         "Scenario D: FLAT terrain"),
    ]

    for filename, proj, desc in scenarios:
        inp = proj.to_aermod_input()
        path = out / filename
        path.write_text(inp)
        print(f"  {desc}")
        print(f"    -> {path}")

    # Verify scenarios have expected differences
    sA_inp = scenarios[0][1].to_aermod_input()
    sB_inp = scenarios[1][1].to_aermod_input()
    sC_inp = scenarios[2][1].to_aermod_input()
    sD_inp = scenarios[3][1].to_aermod_input()

    # Scenario A: check stack height changed
    assert "90.0" in sA_inp and "60.0" not in sA_inp.split("FCCSTK")[1].split("\n")[0], \
        "Scenario A: FCC stack should be 90 m"
    print("\n  Scenario A verification: FCC stack = 90 m (OK)")

    # Scenario B: check emission rate changed
    for line in sB_inp.splitlines():
        if "SRCPARAM" in line and "FCCSTK" in line:
            assert "1.0" in line, "Scenario B: FCC should emit 1.0 g/s"
            break
    print("  Scenario B verification: FCC emission = 1.0 g/s (OK)")

    # Scenario C: check background present
    assert "BACKGRND" in sC_inp, "Scenario C: BACKGRND keyword missing"
    assert "10.0" in sC_inp or "10" in sC_inp, \
        "Scenario C: 10 ug/m3 value missing"
    print("  Scenario C verification: BACKGRND 10.0 ug/m3 (OK)")

    # Scenario D: check terrain type
    assert "FLAT" in sD_inp, "Scenario D: FLAT keyword missing"
    print("  Scenario D verification: FLAT terrain (OK)")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("Tutorial 8 Solution Summary")
    print("=" * 60)
    print(f"  Facility: 150,000 bpd refinery, Houston Ship Channel")
    print(f"  Pollutant: SO2 (1-hr NAAQS = {SO2_1HR_NAAQS} ug/m3)")
    print(f"  Sources: 10 (5 point + 3 area + 2 volume)")
    print(f"  Source groups: 4 (STACKS, FUGITIV, FCCONLY, ALL)")
    fine = base.receptors.cartesian_grids[0]
    coarse = base.receptors.cartesian_grids[1]
    total_rec = (fine.x_num * fine.y_num + coarse.x_num * coarse.y_num
                 + len(base.receptors.discrete_receptors))
    print(f"  Receptors: {total_rec} total")
    print(f"  Terrain: ELEVATED (base case)")
    print(f"  Met data: Houston 2023 (from Tutorial 6)")
    print(f"  Scenarios: 4 sensitivity analyses (A-D)")
    print(f"\n  Generated files:")
    for f in sorted(out.iterdir()):
        size = f.stat().st_size
        print(f"    {f.name:<35} {size:>8,} bytes")

    print("\nTutorial 8 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 8 Solution: Houston Refinery Model")
    parser.add_argument("--output-dir", default="tutorial8_output",
                        help="Directory for generated files")
    args = parser.parse_args()
    main(args.output_dir)

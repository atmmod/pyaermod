"""
GUI Integration Test — Tutorials 1-8
======================================

Tests the same code path the GUI uses:
  1. Build each tutorial project programmatically
  2. Serialize to JSON (Download Project)
  3. Deserialize from JSON (Load Project)
  4. Generate AERMOD input file (Run AERMOD → Preview)
  5. Verify the input file is correct

This exercises ProjectSerializer, all source types, receptor grids,
meteorology pathways, and AERMET stages — the full GUI pipeline.

Usage:
    python test_gui_integration.py
"""

import copy
import dataclasses
import json
import sys
from pathlib import Path

# ── Imports matching what the GUI uses ──────────────────────────────────────

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
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
    VolumeSource,
    DiscreteReceptor,
    BackgroundConcentration,
)

from pyaermod.aermet import (
    AERMETStation,
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,
    UpperAirStation,
)

# Try importing the GUI serializer (same code path as Load/Save Project)
try:
    from pyaermod.gui import ProjectSerializer
    HAS_SERIALIZER = True
except ImportError:
    HAS_SERIALIZER = False
    print("  ⚠ ProjectSerializer not available (GUI not installed?)")
    print("    Will test project building and input generation only.")


PASS = 0
FAIL = 0


def check(condition, description):
    """Assert with tracking."""
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ✗ FAIL: {description}")


def roundtrip_json(project):
    """Serialize to JSON and back — simulates Download → Load Project."""
    d = dataclasses.asdict(project)
    json_str = json.dumps(d, indent=2, default=str)
    loaded = json.loads(json_str)
    return loaded, json_str


# ============================================================================
# TUTORIAL 1 — First Point Source
# ============================================================================

def test_tutorial1():
    print("\n═══ Tutorial 1: First Point Source ═══")

    control = ControlPathway(
        title_one="Tutorial 1 - My First Model",
        title_two="Single point source, PM2.5",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
    )
    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1", x_coord=500000.0, y_coord=3870000.0,
        stack_height=50.0, stack_temp=400.0, exit_velocity=15.0,
        stack_diameter=2.0, emission_rate=1.5,
    ))
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=498000, x_max=502000, y_min=3868000, y_max=3872000,
        spacing=200.0, grid_name="GRID1",
    ))
    met = MeteorologyPathway(surface_file="met_data.sfc", profile_file="met_data.pfl")
    output = OutputPathway(receptor_table=True, max_table=True)
    project = AERMODProject(control=control, sources=sources, receptors=receptors,
                            meteorology=met, output=output)

    inp = project.to_aermod_input()
    check("CO STARTING" in inp, "CO pathway present")
    check("SO STARTING" in inp, "SO pathway present")
    check("RE STARTING" in inp, "RE pathway present")
    check("ME STARTING" in inp, "ME pathway present")
    check("OU STARTING" in inp, "OU pathway present")
    check("STACK1" in inp, "Source STACK1 present")
    check("POINT" in inp, "POINT source type")
    check("PM25" in inp, "PM25 pollutant")
    check("FLAT" in inp, "FLAT terrain")
    check("met_data.sfc" in inp, "Surface met file")
    check("met_data.pfl" in inp, "Profile met file")

    grid = project.receptors.cartesian_grids[0]
    check(grid.x_num == 21, f"Grid x_num=21 (got {grid.x_num})")
    check(grid.y_num == 21, f"Grid y_num=21 (got {grid.y_num})")

    _, json_str = roundtrip_json(project)
    check(len(json_str) > 100, "JSON serialization non-empty")

    print(f"  ✓ Tutorial 1: {len(inp.splitlines())} lines, "
          f"{grid.x_num*grid.y_num} receptors")


# ============================================================================
# TUTORIAL 2 — Comparing Stack Heights
# ============================================================================

def test_tutorial2():
    print("\n═══ Tutorial 2: Comparing Stack Heights ═══")

    def build(height):
        control = ControlPathway(
            title_one=f"Tutorial 2 - Stack Height ({int(height)}m)",
            pollutant_id=PollutantType.SO2,
            averaging_periods=["1", "24", "ANNUAL"],
            terrain_type=TerrainType.FLAT,
        )
        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STACK1", x_coord=500000.0, y_coord=3870000.0,
            stack_height=height, stack_temp=420.0, exit_velocity=15.0,
            stack_diameter=2.0, emission_rate=2.0,
        ))
        receptors = ReceptorPathway()
        receptors.add_cartesian_grid(CartesianGrid.from_bounds(
            x_min=498000, x_max=502000, y_min=3868000, y_max=3872000,
            spacing=100.0, grid_name="GRID1",
        ))
        met = MeteorologyPathway(surface_file="met_data.sfc", profile_file="met_data.pfl")
        output = OutputPathway(receptor_table=True, max_table=True)
        return AERMODProject(control=control, sources=sources, receptors=receptors,
                             meteorology=met, output=output)

    proj20 = build(20.0)
    proj60 = build(60.0)
    inp20 = proj20.to_aermod_input()
    inp60 = proj60.to_aermod_input()

    sp20 = [l for l in inp20.splitlines() if "SRCPARAM" in l][0]
    sp60 = [l for l in inp60.splitlines() if "SRCPARAM" in l][0]

    check("20.00" in sp20, "20m in SRCPARAM line")
    check("60.00" in sp60, "60m in SRCPARAM line")
    check(sp20 != sp60, "SRCPARAM lines differ")
    check("SO2" in inp20, "SO2 pollutant in 20m")
    check("SO2" in inp60, "SO2 pollutant in 60m")

    grid = proj20.receptors.cartesian_grids[0]
    check(grid.x_num == 41, f"Grid 41x41 (got {grid.x_num})")

    print(f"  ✓ Tutorial 2: 20m vs 60m, {grid.x_num*grid.y_num} receptors each")


# ============================================================================
# TUTORIAL 3 — Running AERMOD
# ============================================================================

def test_tutorial3():
    print("\n═══ Tutorial 3: Running AERMOD ═══")

    control = ControlPathway(
        title_one="Tutorial 3 - Full AERMOD Run",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
    )
    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1", x_coord=500000.0, y_coord=3870000.0,
        stack_height=50.0, stack_temp=400.0, exit_velocity=15.0,
        stack_diameter=2.0, emission_rate=1.5,
    ))
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=498000, x_max=502000, y_min=3868000, y_max=3872000,
        spacing=100.0, grid_name="GRID1",
    ))
    met = MeteorologyPathway(surface_file="met_data.sfc", profile_file="met_data.pfl")
    output = OutputPathway(receptor_table=True, max_table=True)
    project = AERMODProject(control=control, sources=sources, receptors=receptors,
                            meteorology=met, output=output)

    inp = project.to_aermod_input()
    check("PM25" in inp, "PM25 pollutant")
    check("ANNUAL" in inp, "ANNUAL averaging")
    check("STACK1" in inp, "STACK1 source")

    # Test JSON roundtrip (simulates Save/Load Project)
    d, json_str = roundtrip_json(project)
    check("STACK1" in json_str, "STACK1 in JSON")
    check("met_data.sfc" in json_str, "met_data.sfc in JSON")

    grid = project.receptors.cartesian_grids[0]
    total = grid.x_num * grid.y_num
    print(f"  ✓ Tutorial 3: {len(inp.splitlines())} lines, {total} receptors")


# ============================================================================
# TUTORIAL 4 — Area Sources
# ============================================================================

def test_tutorial4():
    print("\n═══ Tutorial 4: Area Sources ═══")

    control = ControlPathway(
        title_one="Tutorial 4 - Area Source Facility",
        title_two="Construction site with mixed source types",
        pollutant_id=PollutantType.PM10,
        averaging_periods=["24", "ANNUAL"],
        terrain_type=TerrainType.FLAT,
    )
    sources = SourcePathway()

    sources.add_source(PointSource(
        source_id="GENSET", x_coord=500050.0, y_coord=3870050.0,
        stack_height=5.0, stack_temp=700.0, exit_velocity=10.0,
        stack_diameter=0.3, emission_rate=0.3,
    ))
    sources.add_source(AreaSource(
        source_id="PILE1", x_coord=500000.0, y_coord=3870000.0,
        release_height=2.0, initial_lateral_dimension=25.0,
        initial_vertical_dimension=50.0, angle=0.0, emission_rate=0.0001,
    ))
    sources.add_source(AreaCircSource(
        source_id="STAGING", x_coord=500200.0, y_coord=3870100.0,
        release_height=1.0, radius=60.0, num_vertices=20, emission_rate=0.00005,
    ))
    sources.add_source(AreaPolySource(
        source_id="SITEBND",
        vertices=[(499900, 3869900), (500350, 3869900), (500400, 3870100),
                  (500300, 3870250), (499900, 3870200)],
        release_height=0.5, emission_rate=0.00002,
    ))

    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=499500, x_max=500800, y_min=3869500, y_max=3870700,
        spacing=50.0, grid_name="SITE",
    ))
    met = MeteorologyPathway(surface_file="met_data.sfc", profile_file="met_data.pfl")
    output = OutputPathway(receptor_table=True, max_table=True)
    project = AERMODProject(control=control, sources=sources, receptors=receptors,
                            meteorology=met, output=output)

    inp = project.to_aermod_input()
    check("GENSET" in inp, "GENSET point source")
    check("PILE1" in inp, "PILE1 area source")
    check("STAGING" in inp, "STAGING circular source")
    check("SITEBND" in inp, "SITEBND polygon source")
    check("POINT" in inp, "POINT type keyword")
    check("AREA" in inp, "AREA type keyword")
    check("AREACIRC" in inp, "AREACIRC type keyword")
    check("AREAPOLY" in inp, "AREAPOLY type keyword")
    check("PM10" in inp, "PM10 pollutant")

    # Verify 4 LOCATION lines
    loc_lines = [l for l in inp.splitlines() if "LOCATION" in l]
    check(len(loc_lines) == 4, f"4 LOCATION lines (got {len(loc_lines)})")

    grid = project.receptors.cartesian_grids[0]
    total = grid.x_num * grid.y_num
    print(f"  ✓ Tutorial 4: 4 sources, {total} receptors, "
          f"{len(inp.splitlines())} lines")


# ============================================================================
# TUTORIAL 5 — AERMET (Atlanta)
# ============================================================================

def test_tutorial5():
    print("\n═══ Tutorial 5: AERMET Atlanta ═══")

    station = AERMETStation(
        station_id="KATL", station_name="Atlanta Hartsfield",
        latitude=33.63, longitude=-84.44, time_zone=-5,
        elevation=315.0, anemometer_height=10.0,
    )
    upper_air = UpperAirStation(
        station_id="72215", station_name="Peachtree City",
        latitude=33.36, longitude=-84.57,
    )

    stage1 = AERMETStage1(
        surface_station=station, surface_data_file="72219013874.dat",
        surface_format="ISHD", upper_air_station=upper_air,
        upper_air_data_file="72215.dat",
        start_date="2020/01/01", end_date="2020/12/31",
    )
    s1 = stage1.to_aermet_input()
    check("KATL" in s1, "KATL station ID")
    check("72215" in s1, "72215 upper air ID")
    check("ISHD" in s1, "ISHD format")
    check("2020/01/01" in s1, "Start date")

    stage2 = AERMETStage2(
        surface_extract="stage1.ext", upper_air_extract="stage1_ua.ext",
        start_date="2020/01/01", end_date="2020/12/31", merge_file="stage2.mrg",
    )
    s2 = stage2.to_aermet_input()
    check("stage1.ext" in s2, "Surface extract file")
    check("stage2.mrg" in s2, "Merge output file")

    suburban_albedo = [0.35, 0.35, 0.25, 0.18, 0.15, 0.15, 0.15, 0.15, 0.18, 0.25, 0.35, 0.35]
    suburban_bowen = [1.5, 1.5, 1.0, 0.8, 0.6, 0.5, 0.5, 0.5, 0.6, 0.8, 1.0, 1.5]
    suburban_roughness = [0.30, 0.30, 0.30, 0.30, 0.50, 0.50, 0.50, 0.50, 0.50, 0.30, 0.30, 0.30]

    stage3 = AERMETStage3(
        merge_file="stage2.mrg", station=station,
        albedo=suburban_albedo, bowen=suburban_bowen, roughness=suburban_roughness,
        start_date="2020/01/01", end_date="2020/12/31",
        surface_file="aermod.sfc", profile_file="aermod.pfl",
    )
    s3 = stage3.to_aermet_input()
    check("aermod.sfc" in s3, "SFC output file")
    check("aermod.pfl" in s3, "PFL output file")
    check("ALBEDO" in s3, "ALBEDO keyword")
    check("BOWEN" in s3, "BOWEN keyword")
    check("ROUGHNESS" in s3, "ROUGHNESS keyword")

    print(f"  ✓ Tutorial 5: 3 AERMET stages, suburban defaults")


# ============================================================================
# TUTORIAL 6 — AERMET Houston
# ============================================================================

def test_tutorial6():
    print("\n═══ Tutorial 6: AERMET Houston ═══")

    station = AERMETStation(
        station_id="KHOU", station_name="Houston Hobby",
        latitude=29.6454, longitude=-95.2789, time_zone=-6,
        elevation=14.0, anemometer_height=10.0,
    )
    upper_air = UpperAirStation(
        station_id="72240", station_name="Lake Charles",
        latitude=30.12, longitude=-93.22,
    )

    stage1 = AERMETStage1(
        surface_station=station, surface_data_file="72243012918.dat",
        surface_format="ISHD", upper_air_station=upper_air,
        upper_air_data_file="72240.dat",
        start_date="2019/01/01", end_date="2023/12/31",
    )
    s1 = stage1.to_aermet_input()
    check("KHOU" in s1, "KHOU station ID")
    check("72240" in s1, "72240 upper air ID")

    houston_albedo = [0.18, 0.18, 0.16, 0.14, 0.14, 0.14, 0.14, 0.14, 0.15, 0.16, 0.17, 0.18]
    houston_bowen = [0.8, 0.7, 0.5, 0.4, 0.3, 0.3, 0.3, 0.3, 0.4, 0.5, 0.7, 0.8]
    houston_roughness = [0.40, 0.40, 0.50, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.50, 0.45, 0.40]

    stage3 = AERMETStage3(
        merge_file="stage2.mrg", station=station,
        albedo=houston_albedo, bowen=houston_bowen, roughness=houston_roughness,
        start_date="2019/01/01", end_date="2023/12/31",
        surface_file="houston.sfc", profile_file="houston.pfl",
    )
    s3 = stage3.to_aermet_input()
    check("houston.sfc" in s3, "Houston SFC output")
    check("0.18" in s3, "Houston winter albedo (0.18)")
    check("0.60" in s3, "Houston summer roughness (0.60)")

    # Verify Houston vs Atlanta differences
    check(houston_albedo[0] < 0.35, "Houston albedo < Atlanta suburban (winter)")
    check(houston_bowen[5] < 0.5, "Houston Bowen < Atlanta suburban (summer)")
    check(houston_roughness[5] > 0.30, "Houston roughness > Atlanta suburban (summer)")

    print(f"  ✓ Tutorial 6: Houston AERMET, Gulf Coast parameters")


# ============================================================================
# TUTORIAL 7 — Terrain Processing
# ============================================================================

def test_tutorial7():
    print("\n═══ Tutorial 7: Terrain Processing ═══")

    def build(terrain):
        control = ControlPathway(
            title_one=f"Tutorial 7 - Terrain ({terrain.name})",
            pollutant_id=PollutantType.SO2,
            averaging_periods=["1", "ANNUAL"],
            terrain_type=terrain,
        )
        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STACK1", x_coord=270000.0, y_coord=3292000.0,
            base_elevation=25.0, stack_height=60.0, stack_temp=450.0,
            exit_velocity=20.0, stack_diameter=2.5, emission_rate=5.0,
        ))
        receptors = ReceptorPathway()
        receptors.add_cartesian_grid(CartesianGrid.from_bounds(
            x_min=267500, x_max=272500, y_min=3289500, y_max=3294500,
            spacing=100.0, grid_name="TERRAIN",
        ))
        met = MeteorologyPathway(surface_file="houston.sfc", profile_file="houston.pfl")
        output = OutputPathway(receptor_table=True, max_table=True)
        return AERMODProject(control=control, sources=sources, receptors=receptors,
                             meteorology=met, output=output)

    proj_elev = build(TerrainType.ELEVATED)
    proj_flat = build(TerrainType.FLAT)

    inp_elev = proj_elev.to_aermod_input()
    inp_flat = proj_flat.to_aermod_input()

    check("ELEVATED" in inp_elev, "ELEVATED keyword in elevated file")
    check("FLAT" in inp_flat, "FLAT keyword in flat file")
    check(inp_elev != inp_flat, "ELEVATED and FLAT files differ")

    # Both should have 51x51 receptors
    grid = proj_elev.receptors.cartesian_grids[0]
    total = grid.x_num * grid.y_num
    check(total == 2601, f"51x51=2601 receptors (got {total})")

    # Check base elevation for ELEVATED mode
    check("25.00" in inp_elev, "Base elevation 25m in ELEVATED")

    print(f"  ✓ Tutorial 7: ELEVATED vs FLAT, {total} receptors")


# ============================================================================
# TUTORIAL 8 — Refinery Model
# ============================================================================

def test_tutorial8():
    print("\n═══ Tutorial 8: Refinery Model ═══")

    control = ControlPathway(
        title_one="Tutorial 8 - Houston Refinery",
        title_two="10-source SO2 model",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["1", "24", "ANNUAL"],
        terrain_type=TerrainType.FLAT,
    )

    sources = SourcePathway()

    # 5 point sources (stacks)
    sources.add_source(PointSource(source_id="FCCSTK", x_coord=270000.0, y_coord=3292000.0,
                                   stack_height=60.0, stack_temp=700.0, exit_velocity=25.0,
                                   stack_diameter=3.0, emission_rate=5.0,
                                   source_groups=["STACKS", "FCCONLY", "ALL"]))
    sources.add_source(PointSource(source_id="HTR1", x_coord=270200.0, y_coord=3292100.0,
                                   stack_height=40.0, stack_temp=600.0, exit_velocity=20.0,
                                   stack_diameter=2.0, emission_rate=2.0,
                                   source_groups=["STACKS", "ALL"]))
    sources.add_source(PointSource(source_id="HTR2", x_coord=270400.0, y_coord=3292050.0,
                                   stack_height=35.0, stack_temp=580.0, exit_velocity=18.0,
                                   stack_diameter=1.8, emission_rate=1.5,
                                   source_groups=["STACKS", "ALL"]))
    sources.add_source(PointSource(source_id="BOILER", x_coord=270100.0, y_coord=3291900.0,
                                   stack_height=45.0, stack_temp=500.0, exit_velocity=22.0,
                                   stack_diameter=2.5, emission_rate=3.0,
                                   source_groups=["STACKS", "ALL"]))
    sources.add_source(PointSource(source_id="FLARE", x_coord=270500.0, y_coord=3292200.0,
                                   stack_height=15.0, stack_temp=1273.0, exit_velocity=20.0,
                                   stack_diameter=1.0, emission_rate=1.0,
                                   source_groups=["STACKS", "ALL"]))

    # 2 area sources
    sources.add_source(AreaSource(source_id="TANKS", x_coord=269800.0, y_coord=3292100.0,
                                  release_height=10.0, initial_lateral_dimension=75.0,
                                  initial_vertical_dimension=75.0, emission_rate=0.00001,
                                  source_groups=["FUGITIV", "ALL"]))
    sources.add_source(AreaSource(source_id="LOADRK", x_coord=270600.0, y_coord=3291800.0,
                                  release_height=3.0, initial_lateral_dimension=30.0,
                                  initial_vertical_dimension=50.0, emission_rate=0.000005,
                                  source_groups=["FUGITIV", "ALL"]))

    # 1 circular area source
    sources.add_source(AreaCircSource(source_id="WWATER", x_coord=269900.0, y_coord=3291700.0,
                                      release_height=1.0, radius=40.0, num_vertices=20,
                                      emission_rate=0.00003, source_groups=["FUGITIV", "ALL"]))

    # 2 volume sources
    sources.add_source(VolumeSource(source_id="COOL1", x_coord=270300.0, y_coord=3291800.0,
                                    release_height=15.0, initial_lateral_dimension=10.0,
                                    initial_vertical_dimension=7.0, emission_rate=0.2,
                                    source_groups=["FUGITIV", "ALL"]))
    sources.add_source(VolumeSource(source_id="FUGITV", x_coord=270100.0, y_coord=3292200.0,
                                    release_height=5.0, initial_lateral_dimension=15.0,
                                    initial_vertical_dimension=3.5, emission_rate=0.5,
                                    source_groups=["FUGITIV", "ALL"]))

    # Source groups
    sources.source_groups = [
        SourceGroupDefinition(group_name="STACKS", member_source_ids=["FCCSTK", "HTR1", "HTR2", "BOILER", "FLARE"]),
        SourceGroupDefinition(group_name="FUGITIV", member_source_ids=["TANKS", "LOADRK", "WWATER", "COOL1", "FUGITV"]),
        SourceGroupDefinition(group_name="FCCONLY", member_source_ids=["FCCSTK"]),
        SourceGroupDefinition(group_name="ALL", member_source_ids=[
            "FCCSTK", "HTR1", "HTR2", "BOILER", "FLARE",
            "TANKS", "LOADRK", "WWATER", "COOL1", "FUGITV"]),
    ]

    # Multi-scale receptors
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=269000, x_max=271000, y_min=3291000, y_max=3293000,
        spacing=50.0, grid_name="FINE",
    ))
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=265000, x_max=275000, y_min=3287000, y_max=3297000,
        spacing=200.0, grid_name="COARSE",
    ))
    # 6 discrete sensitive receptors
    for name, x, y in [("SCHOOL", 268500, 3292500), ("HOSPTL", 271500, 3291500),
                        ("RESDNT", 269000, 3293000), ("PARK01", 271000, 3293500),
                        ("DAYCAR", 268800, 3291200), ("CLINIC", 270800, 3293200)]:
        receptors.add_discrete_receptor(DiscreteReceptor(
            x_coord=float(x), y_coord=float(y), z_elev=0.0,
        ))

    met = MeteorologyPathway(surface_file="houston.sfc", profile_file="houston.pfl")
    output = OutputPathway(receptor_table=True, max_table=True)
    project = AERMODProject(control=control, sources=sources, receptors=receptors,
                            meteorology=met, output=output)

    inp = project.to_aermod_input()

    # Verify all 10 sources
    for sid in ["FCCSTK", "HTR1", "HTR2", "BOILER", "FLARE",
                "TANKS", "LOADRK", "WWATER", "COOL1", "FUGITV"]:
        check(sid in inp, f"Source {sid} present")

    loc_lines = [l for l in inp.splitlines() if "LOCATION" in l]
    check(len(loc_lines) == 10, f"10 LOCATION lines (got {len(loc_lines)})")

    # Verify source types
    check("POINT" in inp, "POINT type")
    check("AREA" in inp, "AREA type")
    check("AREACIRC" in inp, "AREACIRC type")
    check("VOLUME" in inp, "VOLUME type")

    # Verify source groups
    for grp in ["STACKS", "FUGITIV", "FCCONLY", "ALL"]:
        check(grp in inp, f"Source group {grp}")

    # Verify discrete receptors (DISCCART lines)
    disccart_lines = [l for l in inp.splitlines() if "DISCCART" in l]
    check(len(disccart_lines) == 6, f"6 DISCCART lines (got {len(disccart_lines)})")
    check("268500" in inp, "Discrete receptor SCHOOL coords")

    # Verify pollutant and averaging
    check("SO2" in inp, "SO2 pollutant")

    # Sensitivity scenarios
    proj_tall = copy.deepcopy(project)
    proj_tall.sources.sources[0].stack_height = 90.0
    inp_tall = proj_tall.to_aermod_input()
    sp_tall = [l for l in inp_tall.splitlines() if "SRCPARAM" in l and "FCCSTK" in l][0]
    check("90.00" in sp_tall, "Scenario A: tall stack 90m")

    proj_flat = copy.deepcopy(project)
    proj_flat.control.terrain_type = TerrainType.FLAT
    inp_flat_scenario = proj_flat.to_aermod_input()
    check("FLAT" in inp_flat_scenario, "Scenario D: FLAT terrain")

    # Count total receptors
    fine = project.receptors.cartesian_grids[0]
    coarse = project.receptors.cartesian_grids[1]
    discrete = len(project.receptors.discrete_receptors)
    total = fine.x_num * fine.y_num + coarse.x_num * coarse.y_num + discrete
    check(total > 2000, f"Total receptors > 2000 (got {total})")

    print(f"  ✓ Tutorial 8: 10 sources, 4 groups, {total} receptors, "
          f"{len(inp.splitlines())} lines, 2 scenarios verified")


# ============================================================================
# GUI SERIALIZER TEST (same as Download → Load Project)
# ============================================================================

def test_gui_serializer():
    print("\n═══ GUI Serializer (Load/Save Project) ═══")
    if not HAS_SERIALIZER:
        print("  ⚠ Skipped — ProjectSerializer not available")
        return

    # Build Tutorial 4 project (most complex source types)
    control = ControlPathway(
        title_one="Serializer Test", pollutant_id=PollutantType.PM10,
        averaging_periods=["24", "ANNUAL"], terrain_type=TerrainType.FLAT,
    )
    sources = SourcePathway()
    sources.add_source(PointSource(source_id="PT1", x_coord=500000.0, y_coord=3870000.0,
                                   stack_height=50.0, stack_temp=400.0, exit_velocity=15.0,
                                   stack_diameter=2.0, emission_rate=1.0))
    sources.add_source(AreaSource(source_id="AR1", x_coord=500100.0, y_coord=3870100.0,
                                  release_height=2.0, emission_rate=0.0001))
    sources.add_source(AreaCircSource(source_id="AC1", x_coord=500200.0, y_coord=3870200.0,
                                      radius=50.0, emission_rate=0.00005))
    sources.add_source(AreaPolySource(source_id="AP1",
                                      vertices=[(500000, 3870000), (500100, 3870000),
                                                (500100, 3870100), (500000, 3870100)],
                                      emission_rate=0.00002))
    sources.add_source(VolumeSource(source_id="VL1", x_coord=500300.0, y_coord=3870300.0,
                                    release_height=10.0, emission_rate=0.1))

    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=499500, x_max=500500, y_min=3869500, y_max=3870500,
        spacing=100.0, grid_name="TEST",
    ))
    receptors.add_discrete_receptor(DiscreteReceptor(
        x_coord=500000.0, y_coord=3870500.0, z_elev=0.0))

    met = MeteorologyPathway(surface_file="test.sfc", profile_file="test.pfl")
    output = OutputPathway(receptor_table=True, max_table=True)
    project = AERMODProject(control=control, sources=sources, receptors=receptors,
                            meteorology=met, output=output)

    # Manually serialize (mimics what Download Project does inside Streamlit)
    src_list = []
    for src in sources.sources:
        d = dataclasses.asdict(src)
        d["_type"] = type(src).__name__
        src_list.append(d)
    group_defs = [dataclasses.asdict(g) for g in sources.group_definitions]

    json_data = {
        "pyaermod_version": "1.0.0",
        "save_format_version": 1,
        "project_control": dataclasses.asdict(control),
        "project_sources": {
            "sources": src_list,
            "background": None,
            "group_definitions": group_defs,
        },
        "project_receptors": {
            "cartesian_grids": [dataclasses.asdict(g) for g in receptors.cartesian_grids],
            "polar_grids": [],
            "discrete_receptors": [dataclasses.asdict(r) for r in receptors.discrete_receptors],
            "elevation_units": receptors.elevation_units,
        },
        "project_meteorology": dataclasses.asdict(met),
        "project_output": dataclasses.asdict(output),
        "geo_settings": {},
        "buildings": [],
        "aermet_config": {"mode": "files"},
        "project_events": None,
    }

    # Handle enums in control pathway
    ctrl_dict = json_data["project_control"]
    if hasattr(ctrl_dict.get("pollutant_id"), "name"):
        ctrl_dict["pollutant_id"] = {"_enum": f"PollutantType.{ctrl_dict['pollutant_id'].name}"}
    if hasattr(ctrl_dict.get("terrain_type"), "name"):
        ctrl_dict["terrain_type"] = {"_enum": f"TerrainType.{ctrl_dict['terrain_type'].name}"}

    json_str = json.dumps(json_data, indent=2, default=str)
    check(len(json_str) > 100, "Serialization produced output")
    check("PT1" in json_str, "Point source in JSON")
    check("AR1" in json_str, "Area source in JSON")
    check("VL1" in json_str, "Volume source in JSON")

    # Deserialize (Load Project — same code path the GUI uses)
    try:
        restored = ProjectSerializer.deserialize_session_state(json_str)
        check("project_control" in restored, "Control restored")
        check("project_sources" in restored, "Sources restored")
        check("project_receptors" in restored, "Receptors restored")

        restored_sources = restored["project_sources"]
        check(len(restored_sources.sources) == 5,
              f"5 sources restored (got {len(restored_sources.sources)})")

        # Generate input from restored project
        restored_project = AERMODProject(
            control=restored["project_control"],
            sources=restored["project_sources"],
            receptors=restored["project_receptors"],
            meteorology=restored["project_meteorology"],
            output=restored["project_output"],
        )
        restored_inp = restored_project.to_aermod_input()
        check("PT1" in restored_inp, "PT1 in restored input")
        check("AREAPOLY" in restored_inp, "AREAPOLY in restored input")
        check("VOLUME" in restored_inp, "VOLUME in restored input")

        print(f"  ✓ Serializer: round-trip OK, "
              f"{len(restored_sources.sources)} sources preserved")
    except Exception as e:
        check(False, f"Deserialization failed: {e}")
        print(f"  ✗ Serializer: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("PyAERMOD GUI Integration Test — Tutorials 1-8")
    print("=" * 60)

    test_tutorial1()
    test_tutorial2()
    test_tutorial3()
    test_tutorial4()
    test_tutorial5()
    test_tutorial6()
    test_tutorial7()
    test_tutorial8()
    test_gui_serializer()

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
    else:
        print("All tests passed! ✓")


if __name__ == "__main__":
    main()

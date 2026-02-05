"""
Test script for pyaermod input generator

Demonstrates creating AERMOD input files with various configurations.
"""

from pyaermod_input_generator import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    PointSource,
    ReceptorPathway,
    CartesianGrid,
    PolarGrid,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    TerrainType
)


def test_simple_point_source():
    """Test 1: Simple point source with Cartesian grid"""
    print("=" * 70)
    print("TEST 1: Simple Point Source with Cartesian Grid")
    print("=" * 70)

    control = ControlPathway(
        title_one="Simple Point Source Example",
        title_two="Single stack with PM2.5 emissions",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=100.0,
        stack_height=45.0,
        stack_temp=373.15,  # 100°C
        exit_velocity=12.0,
        stack_diameter=1.5,
        emission_rate=2.5
    ))

    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-1000.0,
            x_max=1000.0,
            y_min=-1000.0,
            y_max=1000.0,
            spacing=100.0
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met_data.sfc",
        profile_file="met_data.pfl",
        start_year=2023,
        start_month=1,
        start_day=1,
        end_year=2023,
        end_month=12,
        end_day=31
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True,
        summary_file="results.sum"
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    print(project.to_aermod_input())
    print("\n")


def test_multiple_sources_polar_grid():
    """Test 2: Multiple sources with polar receptor grid"""
    print("=" * 70)
    print("TEST 2: Multiple Sources with Polar Grid")
    print("=" * 70)

    control = ControlPathway(
        title_one="Multiple Stack Analysis",
        pollutant_id="SO2",
        averaging_periods=["1", "3", "24", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Stack 1
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=100.0,
        y_coord=200.0,
        base_elevation=50.0,
        stack_height=60.0,
        stack_temp=450.0,
        exit_velocity=18.0,
        stack_diameter=2.0,
        emission_rate=5.0,
        source_groups=["ALL", "POWER"]
    ))

    # Stack 2
    sources.add_source(PointSource(
        source_id="STACK2",
        x_coord=-100.0,
        y_coord=200.0,
        base_elevation=50.0,
        stack_height=55.0,
        stack_temp=425.0,
        exit_velocity=15.0,
        stack_diameter=1.8,
        emission_rate=3.5,
        source_groups=["ALL", "POWER"]
    ))

    receptors = ReceptorPathway()

    # Polar grid centered between sources
    receptors.add_polar_grid(PolarGrid(
        grid_name="POLAR1",
        x_origin=0.0,
        y_origin=200.0,
        dist_init=100.0,
        dist_num=20,
        dist_delta=100.0,
        dir_init=0.0,
        dir_num=36,
        dir_delta=10.0
    ))

    meteorology = MeteorologyPathway(
        surface_file="onsite_met.sfc",
        profile_file="onsite_met.pfl"
    )

    output = OutputPathway(
        receptor_table=True,
        receptor_table_rank=25,
        max_table=True,
        max_table_rank=50,
        plot_file="concentrations.plt"
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    print(project.to_aermod_input())
    print("\n")


def test_building_downwash():
    """Test 3: Point source with building downwash"""
    print("=" * 70)
    print("TEST 3: Point Source with Building Downwash")
    print("=" * 70)

    control = ControlPathway(
        title_one="Building Downwash Example",
        title_two="Stack with nearby building effects",
        pollutant_id=PollutantType.NO2,
        averaging_periods=["1", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=10.0,
        stack_height=30.0,
        stack_temp=350.0,
        exit_velocity=10.0,
        stack_diameter=1.2,
        emission_rate=1.8,
        # Building parameters
        building_height=25.0,
        building_width=40.0,
        building_length=60.0,
        building_x_offset=0.0,
        building_y_offset=20.0
    ))

    receptors = ReceptorPathway()

    # Grid around the facility
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-500.0,
            x_max=500.0,
            y_min=-500.0,
            y_max=500.0,
            spacing=50.0
        )
    )

    # Add some fence line receptors
    receptors.add_discrete_receptor(DiscreteReceptor(200.0, 0.0))
    receptors.add_discrete_receptor(DiscreteReceptor(-200.0, 0.0))
    receptors.add_discrete_receptor(DiscreteReceptor(0.0, 200.0))
    receptors.add_discrete_receptor(DiscreteReceptor(0.0, -200.0))

    meteorology = MeteorologyPathway(
        surface_file="met2023.sfc",
        profile_file="met2023.pfl",
        start_year=2023,
        start_month=1,
        start_day=1,
        end_year=2023,
        end_month=12,
        end_day=31
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True,
        day_table=True,
        summary_file="downwash_results.sum",
        max_file="downwash_max.out"
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    # Write to file
    output_file = project.write("building_downwash_example.inp")
    print(f"Input file written to: {output_file}")
    print("\nFile contents:")
    print(project.to_aermod_input())
    print("\n")


if __name__ == "__main__":
    # Run all tests
    test_simple_point_source()
    test_multiple_sources_polar_grid()
    test_building_downwash()

    print("=" * 70)
    print("All tests completed!")
    print("=" * 70)

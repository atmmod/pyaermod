"""
Example: Line Source Modeling with PyAERMOD

This script demonstrates how to use LINE and RLINE sources in AERMOD.
Line sources represent linear emissions, useful for:
- Roads and highways (RLINE)
- Conveyor belts (LINE)
- Pipelines (LINE)
- Property boundaries (LINE)
- Train tracks (LINE/RLINE)
"""

from pyaermod_input_generator import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    LineSource,
    RLineSource,
    PointSource,
    ReceptorPathway,
    CartesianGrid,
    PolarGrid,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    TerrainType
)
import math


def example_1_single_road():
    """
    Example 1: Single roadway segment

    Model CO emissions from a straight road segment.
    """
    print("Example 1: Single Roadway Segment")
    print("=" * 70)

    control = ControlPathway(
        title_one="Line Source Example 1",
        title_two="Single roadway with mobile emissions",
        pollutant_id=PollutantType.CO,
        averaging_periods=["1", "8"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Road segment: 1000m long, running west to east
    # RLINE for mobile source modeling
    sources.add_source(RLineSource(
        source_id="ROAD1",
        x_start=-500.0,
        y_start=0.0,
        x_end=500.0,
        y_end=0.0,
        base_elevation=10.0,
        release_height=0.5,  # Vehicle exhaust height
        initial_lateral_dimension=3.0,  # Half of lane width (6m total)
        initial_vertical_dimension=1.5,  # Initial vertical mixing
        emission_rate=0.001,  # g/s/m (1000 vehicles/day, 10g/km each)
        source_groups=["ALL", "MOBILE"]
    ))

    # Receptor grid perpendicular to road
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-800,
            x_max=800,
            y_min=-400,
            y_max=400,
            spacing=25
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met.sfc",
        profile_file="met.pfl"
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    filename = "line_example_1_single_road.inp"
    project.write(filename)

    print(f"✓ Created: {filename}")
    print(f"  Road: 1000m long (E-W orientation)")
    print(f"  Release height: 0.5m (vehicle exhaust)")
    print(f"  Lane width: 6m (σy = 3.0m)")
    print(f"  Emission rate: 0.001 g/s/m")
    print()


def example_2_highway_interchange():
    """
    Example 2: Highway interchange with multiple road segments

    Model a highway intersection with multiple road segments.
    """
    print("Example 2: Highway Interchange")
    print("=" * 70)

    control = ControlPathway(
        title_one="Line Source Example 2",
        title_two="Highway interchange with multiple segments",
        pollutant_id=PollutantType.NO2,
        averaging_periods=["1", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Main highway - N/S orientation, higher traffic
    sources.add_source(RLineSource(
        source_id="HWY_N",
        x_start=0.0,
        y_start=0.0,
        x_end=0.0,
        y_end=800.0,
        base_elevation=10.0,
        release_height=0.5,
        initial_lateral_dimension=6.0,  # 4 lanes (12m total width)
        initial_vertical_dimension=1.5,
        emission_rate=0.003,  # Higher traffic volume
        source_groups=["ALL", "HIGHWAY"]
    ))

    sources.add_source(RLineSource(
        source_id="HWY_S",
        x_start=0.0,
        y_start=-800.0,
        x_end=0.0,
        y_end=0.0,
        base_elevation=10.0,
        release_height=0.5,
        initial_lateral_dimension=6.0,
        initial_vertical_dimension=1.5,
        emission_rate=0.003,
        source_groups=["ALL", "HIGHWAY"]
    ))

    # Intersecting road - E/W orientation, moderate traffic
    sources.add_source(RLineSource(
        source_id="ROAD_E",
        x_start=0.0,
        y_start=0.0,
        x_end=600.0,
        y_end=0.0,
        base_elevation=10.0,
        release_height=0.5,
        initial_lateral_dimension=4.0,  # 2 lanes (8m total)
        initial_vertical_dimension=1.5,
        emission_rate=0.0015,
        source_groups=["ALL", "ARTERIAL"]
    ))

    sources.add_source(RLineSource(
        source_id="ROAD_W",
        x_start=-600.0,
        y_start=0.0,
        x_end=0.0,
        y_end=0.0,
        base_elevation=10.0,
        release_height=0.5,
        initial_lateral_dimension=4.0,
        initial_vertical_dimension=1.5,
        emission_rate=0.0015,
        source_groups=["ALL", "ARTERIAL"]
    ))

    print(f"✓ Defined {len(sources.sources)} road segments:")
    for src in sources.sources:
        print(f"  - {src.source_id:10s}: Q={src.emission_rate:.4f} g/s/m")

    # Receptor grid covering interchange
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-1000,
            x_max=1000,
            y_min=-1000,
            y_max=1000,
            spacing=50
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met.sfc",
        profile_file="met.pfl"
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    filename = "line_example_2_interchange.inp"
    project.write(filename)

    print(f"\n✓ Created: {filename}")
    print()


def example_3_conveyor_belt():
    """
    Example 3: Conveyor belt with fugitive dust

    Model fugitive dust emissions from a long conveyor using LINE source.
    """
    print("Example 3: Conveyor Belt with Fugitive Dust")
    print("=" * 70)

    control = ControlPathway(
        title_one="Line Source Example 3",
        title_two="Conveyor belt fugitive emissions",
        pollutant_id=PollutantType.PM10,
        averaging_periods=["24", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Conveyor: 500m long, running NE-SW at 45 degrees
    # Use LINE source (not RLINE) for industrial line source
    length = 500.0
    angle = 45.0  # degrees
    angle_rad = math.radians(angle)

    x_start = -length/2 * math.cos(angle_rad)
    y_start = -length/2 * math.sin(angle_rad)
    x_end = length/2 * math.cos(angle_rad)
    y_end = length/2 * math.sin(angle_rad)

    sources.add_source(LineSource(
        source_id="CONVEYOR",
        x_start=x_start,
        y_start=y_start,
        x_end=x_end,
        y_end=y_end,
        base_elevation=5.0,
        release_height=8.0,  # Elevated conveyor
        initial_lateral_dimension=1.0,  # Narrow lateral dispersion
        emission_rate=0.0001,  # g/s/m fugitive dust
        source_groups=["ALL", "FUGITIVE"]
    ))

    # Receptor grid
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-500,
            x_max=500,
            y_min=-500,
            y_max=500,
            spacing=25
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met.sfc",
        profile_file="met.pfl"
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    filename = "line_example_3_conveyor.inp"
    project.write(filename)

    print(f"✓ Created: {filename}")
    print(f"  Conveyor: 500m long, oriented at 45°")
    print(f"  Start: ({x_start:.1f}, {y_start:.1f})")
    print(f"  End: ({x_end:.1f}, {y_end:.1f})")
    print(f"  Release height: 8.0m")
    print(f"  Emission rate: 0.0001 g/s/m")
    print()


def example_4_property_fence_line():
    """
    Example 4: Property boundary fence line sources

    Model emissions along property boundary using multiple LINE segments.
    """
    print("Example 4: Property Boundary Fence Line")
    print("=" * 70)

    control = ControlPathway(
        title_one="Line Source Example 4",
        title_two="Property boundary emissions",
        pollutant_id="VOC",
        averaging_periods=["1", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Define rectangular property boundary (800m x 600m)
    # Four LINE sources forming a rectangle
    boundaries = [
        ("FENCE_N", -400, 300, 400, 300),   # North boundary
        ("FENCE_S", -400, -300, 400, -300), # South boundary
        ("FENCE_E", 400, -300, 400, 300),   # East boundary
        ("FENCE_W", -400, -300, -400, 300), # West boundary
    ]

    for source_id, x1, y1, x2, y2 in boundaries:
        sources.add_source(LineSource(
            source_id=source_id,
            x_start=float(x1),
            y_start=float(y1),
            x_end=float(x2),
            y_end=float(y2),
            base_elevation=10.0,
            release_height=1.0,  # Low-level emissions
            initial_lateral_dimension=0.5,  # Narrow source
            emission_rate=0.00005,  # g/s/m
            source_groups=["ALL", "BOUNDARY"]
        ))

    print(f"✓ Defined {len(sources.sources)} fence line segments")
    print(f"  Property: 800m × 600m")
    print(f"  Emission rate: 0.00005 g/s/m per fence segment")

    # Receptor grid inside and outside boundary
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-600,
            x_max=600,
            y_min=-500,
            y_max=500,
            spacing=50
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met.sfc",
        profile_file="met.pfl"
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    filename = "line_example_4_fence_line.inp"
    project.write(filename)

    print(f"\n✓ Created: {filename}")
    print()


def example_5_mixed_sources():
    """
    Example 5: Mixed source types (point + line)

    Realistic facility with stack emissions and road traffic.
    """
    print("Example 5: Mixed Point and Line Sources")
    print("=" * 70)

    control = ControlPathway(
        title_one="Line Source Example 5",
        title_two="Facility with stack and road emissions",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["24", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Point source: Main stack
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=10.0,
        stack_height=50.0,
        stack_temp=400.0,
        exit_velocity=15.0,
        stack_diameter=2.0,
        emission_rate=3.0,  # g/s
        source_groups=["ALL", "STACKS"]
    ))

    # Line source: Access road
    sources.add_source(RLineSource(
        source_id="ACCESS",
        x_start=-300.0,
        y_start=-200.0,
        x_end=0.0,
        y_end=0.0,
        base_elevation=10.0,
        release_height=0.5,
        initial_lateral_dimension=3.0,
        initial_vertical_dimension=1.5,
        emission_rate=0.0005,  # g/s/m
        source_groups=["ALL", "ROADS"]
    ))

    # Line source: Internal haul road
    sources.add_source(LineSource(
        source_id="HAUL",
        x_start=50.0,
        y_start=50.0,
        x_end=200.0,
        y_end=150.0,
        base_elevation=10.0,
        release_height=1.0,
        initial_lateral_dimension=2.0,
        emission_rate=0.001,  # g/s/m - higher due to unpaved
        source_groups=["ALL", "ROADS", "FUGITIVE"]
    ))

    print(f"✓ Defined {len(sources.sources)} sources:")
    for src in sources.sources:
        src_type = type(src).__name__
        if hasattr(src, 'stack_height'):
            print(f"  - {src.source_id:10s} (POINT): Q={src.emission_rate:.3f} g/s")
        else:
            print(f"  - {src.source_id:10s} ({src_type[:4]}): Q={src.emission_rate:.4f} g/s/m")

    # Receptor grid
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-500,
            x_max=500,
            y_min=-500,
            y_max=500,
            spacing=50
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met.sfc",
        profile_file="met.pfl"
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    filename = "line_example_5_mixed_sources.inp"
    project.write(filename)

    print(f"\n✓ Created: {filename}")
    print()


def main():
    """Run all line source examples"""
    print("\n" + "=" * 70)
    print("PyAERMOD Line Source Examples")
    print("=" * 70)
    print()
    print("Line sources model linear emissions from roads, conveyors,")
    print("pipelines, and other linear features.")
    print()

    example_1_single_road()
    example_2_highway_interchange()
    example_3_conveyor_belt()
    example_4_property_fence_line()
    example_5_mixed_sources()

    print("=" * 70)
    print("All examples completed successfully!")
    print("=" * 70)
    print()
    print("Key concepts:")
    print("  • Emission rate in g/s/m (per unit length)")
    print("  • Two coordinate pairs define line start and end")
    print("  • Release height = elevation above ground")
    print("  • Initial σy = perpendicular dispersion width")
    print()
    print("When to use LINE vs RLINE:")
    print("  • LINE: General linear sources (conveyors, pipelines, fences)")
    print("  • RLINE: Mobile sources on roadways (includes traffic-specific physics)")
    print()
    print("Common applications:")
    print("  • Roads and highways (RLINE)")
    print("  • Conveyor systems (LINE)")
    print("  • Property boundaries (LINE)")
    print("  • Train tracks (LINE/RLINE)")
    print("  • Pipelines with fugitive leaks (LINE)")
    print()


if __name__ == "__main__":
    main()

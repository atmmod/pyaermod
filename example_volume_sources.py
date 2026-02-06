"""
Example: Volume Source Modeling with PyAERMOD

This script demonstrates how to use VOLUME sources in AERMOD.
Volume sources represent 3D emissions with initial dispersion,
useful for:
- Building wake effects
- Conveyor systems with height
- Storage structures with vertical extent
- Emissions from structures with significant volume
"""

from pyaermod_input_generator import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    VolumeSource,
    PointSource,
    ReceptorPathway,
    CartesianGrid,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    TerrainType
)


def example_1_single_building():
    """
    Example 1: Single building with emissions

    Model emissions from a building with fugitive releases.
    Volume source accounts for initial mixing within building wake.
    """
    print("Example 1: Single Building Volume Source")
    print("=" * 70)

    control = ControlPathway(
        title_one="Volume Source Example 1",
        title_two="Single building with fugitive emissions",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Building: 40m x 30m x 15m high
    # Model as volume source with initial dispersion
    # Release height = centroid = 15/2 = 7.5m
    # Initial sigma_y = building width / (2 * 2.15) ≈ 7m
    # Initial sigma_z = building height / (2 * 2.15) ≈ 3.5m

    sources.add_source(VolumeSource(
        source_id="BLDG1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=10.0,
        release_height=7.5,  # Centroid height
        initial_lateral_dimension=7.0,  # Initial sigma_y
        initial_vertical_dimension=3.5,  # Initial sigma_z
        emission_rate=2.0,  # g/s total from building
        source_groups=["ALL", "BUILDING"]
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

    # Meteorology
    meteorology = MeteorologyPathway(
        surface_file="met.sfc",
        profile_file="met.pfl"
    )

    # Output
    output = OutputPathway(
        receptor_table=True,
        max_table=True
    )

    # Create and write project
    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    filename = "volume_example_1_single_building.inp"
    project.write(filename)

    print(f"✓ Created: {filename}")
    print(f"  Building: 40m × 30m × 15m")
    print(f"  Release height: 7.5m (centroid)")
    print(f"  Initial dispersion: σy=7.0m, σz=3.5m")
    print(f"  Emission rate: 2.0 g/s")
    print()


def example_2_conveyor_system():
    """
    Example 2: Elevated conveyor system

    Model fugitive dust from an elevated conveyor belt.
    Volume source captures both elevation and initial dispersion.
    """
    print("Example 2: Elevated Conveyor System")
    print("=" * 70)

    control = ControlPathway(
        title_one="Volume Source Example 2",
        title_two="Elevated conveyor with fugitive dust",
        pollutant_id=PollutantType.PM10,
        averaging_periods=["24", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Conveyor: 200m long, 2m wide, 10m high
    # Treat as volume source with linear extent
    # Initial sigma_y = width/4 ≈ 0.5m
    # Initial sigma_z = 2m (vertical mixing from belt motion)

    sources.add_source(VolumeSource(
        source_id="CONVEYOR",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=5.0,
        release_height=10.0,  # Conveyor height
        initial_lateral_dimension=0.5,  # Narrow lateral extent
        initial_vertical_dimension=2.0,  # Vertical mixing from motion
        emission_rate=0.5,  # g/s fugitive dust
        source_groups=["ALL", "FUGITIVE", "CONVEYOR"]
    ))

    # Receptor grid along and perpendicular to conveyor
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-300,
            x_max=300,
            y_min=-300,
            y_max=300,
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

    filename = "volume_example_2_conveyor.inp"
    project.write(filename)

    print(f"✓ Created: {filename}")
    print(f"  Conveyor: 200m long, 10m high")
    print(f"  Initial dispersion: σy=0.5m, σz=2.0m")
    print(f"  Emission rate: 0.5 g/s")
    print()


def example_3_multiple_structures():
    """
    Example 3: Multiple buildings at facility

    Model several buildings with different emission characteristics.
    """
    print("Example 3: Multiple Building Structures")
    print("=" * 70)

    control = ControlPathway(
        title_one="Volume Source Example 3",
        title_two="Multiple building structures",
        pollutant_id="VOC",
        averaging_periods=["1", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Building 1: Large warehouse (80m x 60m x 20m)
    sources.add_source(VolumeSource(
        source_id="WAREHOUSE",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=10.0,
        release_height=10.0,  # Centroid
        initial_lateral_dimension=14.0,  # σy from width
        initial_vertical_dimension=4.7,  # σz from height
        emission_rate=5.0,  # g/s
        source_groups=["ALL", "BUILDINGS", "VOC"]
    ))

    # Building 2: Process building (40m x 40m x 25m)
    sources.add_source(VolumeSource(
        source_id="PROCESS",
        x_coord=120.0,
        y_coord=50.0,
        base_elevation=10.0,
        release_height=12.5,  # Centroid
        initial_lateral_dimension=9.3,
        initial_vertical_dimension=5.8,
        emission_rate=3.0,  # g/s
        source_groups=["ALL", "BUILDINGS", "VOC"]
    ))

    # Building 3: Storage shed (30m x 20m x 12m)
    sources.add_source(VolumeSource(
        source_id="STORAGE",
        x_coord=-80.0,
        y_coord=-60.0,
        base_elevation=10.0,
        release_height=6.0,  # Centroid
        initial_lateral_dimension=4.7,
        initial_vertical_dimension=2.8,
        emission_rate=1.0,  # g/s
        source_groups=["ALL", "BUILDINGS", "VOC"]
    ))

    print(f"✓ Defined {len(sources.sources)} building volume sources:")
    for src in sources.sources:
        print(f"  - {src.source_id:12s}: Q={src.emission_rate:.1f} g/s, "
              f"h={src.release_height:.1f}m")

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

    filename = "volume_example_3_multiple_buildings.inp"
    project.write(filename)

    print(f"\n✓ Created: {filename}")
    print()


def example_4_mixed_source_types():
    """
    Example 4: Combined point and volume sources

    Realistic facility with both stack (point) and building (volume) emissions.
    """
    print("Example 4: Mixed Point and Volume Sources")
    print("=" * 70)

    control = ControlPathway(
        title_one="Volume Source Example 4",
        title_two="Combined point and volume sources",
        pollutant_id=PollutantType.NO2,
        averaging_periods=["1", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Point source: Main stack
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=50.0,
        y_coord=50.0,
        base_elevation=10.0,
        stack_height=60.0,
        stack_temp=450.0,
        exit_velocity=18.0,
        stack_diameter=2.5,
        emission_rate=8.0,  # g/s
        source_groups=["ALL", "STACKS"]
    ))

    # Volume source 1: Processing building with fugitive emissions
    sources.add_source(VolumeSource(
        source_id="BUILDING1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=10.0,
        release_height=8.0,
        initial_lateral_dimension=10.0,
        initial_vertical_dimension=3.7,
        emission_rate=2.5,  # g/s
        source_groups=["ALL", "BUILDINGS"]
    ))

    # Volume source 2: Material handling structure
    sources.add_source(VolumeSource(
        source_id="HANDLING",
        x_coord=-70.0,
        y_coord=40.0,
        base_elevation=10.0,
        release_height=12.0,
        initial_lateral_dimension=6.0,
        initial_vertical_dimension=4.0,
        emission_rate=1.5,  # g/s
        source_groups=["ALL", "BUILDINGS"]
    ))

    print(f"✓ Defined {len(sources.sources)} sources:")
    for src in sources.sources:
        src_type = "POINT" if isinstance(src, PointSource) else "VOLUME"
        print(f"  - {src.source_id:12s} ({src_type:6s}): Q={src.emission_rate:.1f} g/s")

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
        max_table=True,
        summary_file="mixed_sources.sum"
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    filename = "volume_example_4_mixed_sources.inp"
    project.write(filename)

    print(f"\n✓ Created: {filename}")
    print("\nThis example shows:")
    print("  • Elevated point source (stack) with buoyancy and momentum")
    print("  • Volume sources (buildings) with initial dispersion")
    print("  • Different emission characteristics and source groups")
    print()


def main():
    """Run all volume source examples"""
    print("\n" + "=" * 70)
    print("PyAERMOD Volume Source Examples")
    print("=" * 70)
    print()
    print("Volume sources model 3D emissions with initial dispersion.")
    print("Useful for buildings, structures, and elevated area sources.")
    print()

    example_1_single_building()
    example_2_conveyor_system()
    example_3_multiple_structures()
    example_4_mixed_source_types()

    print("=" * 70)
    print("All examples completed successfully!")
    print("=" * 70)
    print()
    print("Key concepts:")
    print("  • Release height = centroid of volume")
    print("  • Initial σy ≈ lateral dimension / (2 × 2.15)")
    print("  • Initial σz ≈ vertical dimension / (2 × 2.15)")
    print("  • Emission rate in g/s (not per area like AREA sources)")
    print()
    print("When to use VOLUME vs POINT vs AREA:")
    print("  • POINT: Elevated release with momentum/buoyancy (stacks)")
    print("  • AREA: Ground-level areal emissions (piles, roads)")
    print("  • VOLUME: 3D emissions with initial mixing (buildings, structures)")
    print()


if __name__ == "__main__":
    main()

"""
Area Source Examples for PyAERMOD

Demonstrates usage of AREA, AREACIRC, and AREAPOLY source types.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyaermod_input_generator import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    AreaSource,
    AreaCircSource,
    AreaPolySource,
    ReceptorPathway,
    CartesianGrid,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    TerrainType
)


def example_1_rectangular_area():
    """Example 1: Rectangular area source (e.g., storage pile)"""
    print("="*70)
    print("EXAMPLE 1: Rectangular Area Source (Storage Pile)")
    print("="*70)

    control = ControlPathway(
        title_one="Rectangular Area Source Example",
        title_two="Coal storage pile with fugitive emissions",
        pollutant_id=PollutantType.PM10,
        averaging_periods=["24", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()
    sources.add_source(AreaSource(
        source_id="PILE1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=10.0,
        release_height=2.0,  # 2m above ground
        initial_lateral_dimension=25.0,  # 50m wide (half-width)
        initial_vertical_dimension=50.0,  # 100m long (half-width)
        emission_rate=0.00005,  # g/s/m^2 (very low for fugitive dust)
        angle=45.0,  # Rotated 45 degrees
        source_groups=["ALL", "FUGITIVE"]
    ))

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

    output_file = "area_rectangular_example.inp"
    project.write(output_file)
    print(f"\n✓ Input file created: {output_file}")
    print("\nGenerated input (first 40 lines):")
    print(project.to_aermod_input()[:2000])


def example_2_circular_area():
    """Example 2: Circular area source (e.g., tank farm)"""
    print("\n\n")
    print("="*70)
    print("EXAMPLE 2: Circular Area Source (Tank Farm)")
    print("="*70)

    control = ControlPathway(
        title_one="Circular Area Source Example",
        title_two="Storage tank farm with VOC emissions",
        pollutant_id="VOC",
        averaging_periods=["1", "ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Large tank farm represented as circular area
    sources.add_source(AreaCircSource(
        source_id="TANKFARM",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=5.0,
        release_height=3.0,  # 3m above ground
        radius=75.0,  # 75m radius
        emission_rate=0.0001,  # g/s/m^2
        num_vertices=36,  # High resolution circle
        source_groups=["ALL", "TANKS"]
    ))

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

    output_file = "area_circular_example.inp"
    project.write(output_file)
    print(f"\n✓ Input file created: {output_file}")


def example_3_polygonal_area():
    """Example 3: Polygonal area source (e.g., irregular facility)"""
    print("\n\n")
    print("="*70)
    print("EXAMPLE 3: Polygonal Area Source (Irregular Facility)")
    print("="*70)

    control = ControlPathway(
        title_one="Polygonal Area Source Example",
        title_two="Irregular shaped facility boundary",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Irregular polygon representing facility boundary
    facility_vertices = [
        (0.0, 0.0),
        (100.0, 0.0),
        (150.0, 50.0),
        (120.0, 120.0),
        (50.0, 100.0),
        (-20.0, 60.0)
    ]

    sources.add_source(AreaPolySource(
        source_id="FACILITY",
        vertices=facility_vertices,
        base_elevation=10.0,
        release_height=1.5,  # 1.5m above ground
        emission_rate=0.00008,  # g/s/m^2
        source_groups=["ALL", "FACILITY"]
    ))

    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-300,
            x_max=300,
            y_min=-200,
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

    output_file = "area_polygonal_example.inp"
    project.write(output_file)
    print(f"\n✓ Input file created: {output_file}")


def example_4_mixed_sources():
    """Example 4: Combined point and area sources"""
    print("\n\n")
    print("="*70)
    print("EXAMPLE 4: Mixed Source Types (Point + Area)")
    print("="*70)

    control = ControlPathway(
        title_one="Mixed Source Example",
        title_two="Facility with stack and area sources",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()

    # Add point source (stack)
    from pyaermod_input_generator import PointSource
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=50.0,
        y_coord=50.0,
        base_elevation=10.0,
        stack_height=40.0,
        stack_temp=400.0,
        exit_velocity=12.0,
        stack_diameter=1.5,
        emission_rate=2.0,  # g/s
        source_groups=["ALL", "STACKS"]
    ))

    # Add area source (material handling)
    sources.add_source(AreaSource(
        source_id="LOADAREA",
        x_coord=-50.0,
        y_coord=-50.0,
        base_elevation=10.0,
        release_height=5.0,
        initial_lateral_dimension=20.0,
        initial_vertical_dimension=30.0,
        emission_rate=0.0001,  # g/s/m^2
        source_groups=["ALL", "FUGITIVE"]
    ))

    # Add circular area (storage)
    sources.add_source(AreaCircSource(
        source_id="STORAGE",
        x_coord=100.0,
        y_coord=-100.0,
        base_elevation=10.0,
        release_height=2.0,
        radius=50.0,
        emission_rate=0.00005,
        num_vertices=24,
        source_groups=["ALL", "STORAGE"]
    ))

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

    output_file = "mixed_sources_example.inp"
    project.write(output_file)
    print(f"\n✓ Input file created: {output_file}")
    print(f"\nProject has {len(sources.sources)} sources:")
    for source in sources.sources:
        print(f"  - {source.source_id} ({source.__class__.__name__})")


def main():
    """Run all area source examples"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*20 + "Area Source Examples" + " "*28 + "║")
    print("╚" + "="*68 + "╝")
    print("\nDemonstrating AREA, AREACIRC, and AREAPOLY source types\n")

    examples = [
        ("Rectangular Area", example_1_rectangular_area),
        ("Circular Area", example_2_circular_area),
        ("Polygonal Area", example_3_polygonal_area),
        ("Mixed Sources", example_4_mixed_sources)
    ]

    for i, (name, func) in enumerate(examples, 1):
        print(f"\n{i}. {name}")

    print("\n" + "-"*70)

    for name, func in examples:
        try:
            func()
        except Exception as e:
            print(f"\nError in {name}: {e}")

    print("\n\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*22 + "Examples Complete!" + " "*25 + "║")
    print("╚" + "="*68 + "╝")
    print("\nArea source support now available in PyAERMOD!")
    print("\nKey features:")
    print("  • Rectangular areas (AREA) - for storage piles, yards")
    print("  • Circular areas (AREACIRC) - for tank farms, circular facilities")
    print("  • Polygonal areas (AREAPOLY) - for irregular facility boundaries")
    print("  • Can mix with point sources in same project")
    print("  • Full source grouping and urban designation support")


if __name__ == "__main__":
    main()

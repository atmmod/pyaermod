"""
PyAERMOD Deposition Modeling Example

Demonstrates how to configure gas and particle deposition parameters
for AERMOD, including dry deposition, wet deposition, and combined
deposition analysis.

This script covers:
  1. Gas deposition with a point source
  2. Particle deposition with size/mass/density distributions
  3. Combined gas + particle deposition
  4. Output configuration for deposition results
  5. Source groups with mixed deposition methods
"""

from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    DepositionMethod,
    GasDepositionParams,
    MeteorologyPathway,
    OutputPathway,
    ParticleDepositionParams,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
)


def example_1_gas_deposition():
    """
    Example 1: Gas dry deposition for SO2.

    Uses EPA-recommended diffusivity and reactivity values for SO2.
    """
    print("=" * 70)
    print("EXAMPLE 1: Gas Dry Deposition (SO2)")
    print("=" * 70)

    # SO2 gas deposition parameters (EPA defaults)
    gas_dep = GasDepositionParams(
        diffusivity=0.1089,         # cm2/s — molecular diffusivity in air
        alpha_r=40.0,               # dimensionless — effective Henry's law
        reactivity=8.0,             # reactivity factor (0=non-reactive, 18=max)
        henry_constant=40.0,        # Pa m3/mol — Henry's law constant
    )

    # Create source with dry deposition
    # deposition_method is a (DepositionMethod, float) tuple
    sources = SourcePathway()
    sources.add_source(
        PointSource(
            source_id="SO2_STK",
            x_coord=0.0,
            y_coord=0.0,
            base_elevation=100.0,
            stack_height=50.0,
            stack_temp=450.0,
            exit_velocity=18.0,
            stack_diameter=2.5,
            emission_rate=5.0,         # g/s
            gas_deposition=gas_dep,
            deposition_method=(DepositionMethod.DRYDPLT, 0.0),
        )
    )

    # Control pathway for SO2
    control = ControlPathway(
        title_one="SO2 Gas Deposition Example",
        title_two="Dry deposition modeling with DRYDPLT",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
    )

    # Receptors — 2 km domain, 100 m spacing
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-2000, x_max=2000,
            y_min=-2000, y_max=2000,
            spacing=100,
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met_2023.sfc",
        profile_file="met_2023.pfl",
    )

    # Output: deposition flux (g/m2/s)
    output = OutputPathway(
        receptor_table=True,
        max_table=True,
        output_type="DDEP",
    )

    project = AERMODProject(control, sources, receptors, meteorology, output)

    # Preview
    inp = project.to_aermod_input(validate=False, check_files=False)
    print("\nGenerated input preview (first 30 lines):")
    for line in inp.split("\n")[:30]:
        print(f"  {line}")
    print("  ...")

    # Write input file
    project.write("gas_deposition.inp")
    print("\n  Input file written: gas_deposition.inp")
    print(f"  Deposition method: {DepositionMethod.DRYDPLT.value}")
    print(f"  Gas diffusivity: {gas_dep.diffusivity} cm2/s")
    print(f"  Reactivity: {gas_dep.reactivity}")
    print()


def example_2_particle_deposition():
    """
    Example 2: Particle deposition with size distribution.

    Models PM emissions with a tri-modal particle size distribution
    and calculates both dry and wet deposition.
    """
    print("=" * 70)
    print("EXAMPLE 2: Particle Deposition (PM)")
    print("=" * 70)

    # Particle size distribution — three size bins
    particle_dep = ParticleDepositionParams(
        diameters=[1.0, 5.0, 15.0],         # microns
        mass_fractions=[0.30, 0.45, 0.25],   # must sum to 1.0
        densities=[1.5, 2.0, 2.5],           # g/cm3
    )

    # Validate mass fractions
    total = sum(particle_dep.mass_fractions)
    print(f"\n  Mass fraction total: {total:.2f} (must be 1.0)")

    # Create source with combined deposition
    sources = SourcePathway()
    sources.add_source(
        PointSource(
            source_id="PM_STK",
            x_coord=0.0,
            y_coord=0.0,
            base_elevation=50.0,
            stack_height=35.0,
            stack_temp=380.0,
            exit_velocity=12.0,
            stack_diameter=1.8,
            emission_rate=2.0,          # g/s total PM
            particle_deposition=particle_dep,
            deposition_method=(DepositionMethod.DRYDPLT, 0.0),
        )
    )

    control = ControlPathway(
        title_one="Particle Deposition Example",
        title_two="Dry + wet deposition with DEPOS method",
        pollutant_id=PollutantType.PM10,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
    )

    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-1500, x_max=1500,
            y_min=-1500, y_max=1500,
            spacing=100,
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met_2023.sfc",
        profile_file="met_2023.pfl",
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True,
        output_type="DEPOS",   # total deposition
    )

    project = AERMODProject(control, sources, receptors, meteorology, output)
    project.write("particle_deposition.inp")

    print("  Input file written: particle_deposition.inp")
    print(f"  Deposition method: {DepositionMethod.DRYDPLT.value}")
    print(f"  Particle diameters: {particle_dep.diameters} um")
    print(f"  Mass fractions: {particle_dep.mass_fractions}")
    print(f"  Densities: {particle_dep.densities} g/cm3")
    print()


def example_3_multi_source_groups():
    """
    Example 3: Multiple sources with different deposition methods.

    Demonstrates source groups where each group uses a different
    deposition configuration.
    """
    print("=" * 70)
    print("EXAMPLE 3: Source Groups with Mixed Deposition")
    print("=" * 70)

    sources = SourcePathway()

    # Gas source — SO2 from combustion
    gas_dep = GasDepositionParams(
        diffusivity=0.1089,
        alpha_r=40.0,
        reactivity=8.0,
        henry_constant=40.0,
    )
    sources.add_source(
        PointSource(
            source_id="COMB1",
            x_coord=0.0,
            y_coord=0.0,
            base_elevation=100.0,
            stack_height=60.0,
            stack_temp=500.0,
            exit_velocity=20.0,
            stack_diameter=3.0,
            emission_rate=8.0,
            gas_deposition=gas_dep,
            deposition_method=(DepositionMethod.DRYDPLT, 0.0),
        )
    )

    # Particle source — PM from materials handling
    particle_dep = ParticleDepositionParams(
        diameters=[2.5, 10.0, 25.0],
        mass_fractions=[0.20, 0.50, 0.30],
        densities=[2.0, 2.5, 2.8],
    )
    sources.add_source(
        PointSource(
            source_id="MATL1",
            x_coord=200.0,
            y_coord=100.0,
            base_elevation=100.0,
            stack_height=15.0,
            stack_temp=300.0,
            exit_velocity=5.0,
            stack_diameter=1.0,
            emission_rate=1.0,
            particle_deposition=particle_dep,
            deposition_method=(DepositionMethod.DRYDPLT, 0.0),
        )
    )

    # Concentration-only source (no deposition)
    sources.add_source(
        PointSource(
            source_id="EMRG1",
            x_coord=-100.0,
            y_coord=50.0,
            base_elevation=100.0,
            stack_height=40.0,
            stack_temp=1200.0,
            exit_velocity=25.0,
            stack_diameter=0.8,
            emission_rate=0.3,
        )
    )

    # Define source groups
    sources.group_definitions = [
        SourceGroupDefinition(
            group_name="COMBUST",
            member_source_ids=["COMB1"],
            description="Combustion sources (gas deposition)",
        ),
        SourceGroupDefinition(
            group_name="MATHDL",
            member_source_ids=["MATL1"],
            description="Materials handling (particle deposition)",
        ),
        SourceGroupDefinition(
            group_name="EMRGCY",
            member_source_ids=["EMRG1"],
            description="Emergency flare (concentration only)",
        ),
    ]

    control = ControlPathway(
        title_one="Multi-Source Deposition Example",
        title_two="Gas, particle, and concentration-only sources",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24", "1"],
        terrain_type=TerrainType.FLAT,
    )

    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-2000, x_max=2000,
            y_min=-2000, y_max=2000,
            spacing=200,
        )
    )

    meteorology = MeteorologyPathway(
        surface_file="met_2023.sfc",
        profile_file="met_2023.pfl",
    )

    output = OutputPathway(
        receptor_table=True,
        max_table=True,
        max_table_rank=10,
    )

    project = AERMODProject(control, sources, receptors, meteorology, output)
    project.write("multi_source_deposition.inp")

    print("\n  Source groups:")
    for grp in sources.group_definitions:
        print(f"    {grp.group_name}: {grp.member_source_ids} — {grp.description}")
    print("\n  Input file written: multi_source_deposition.inp")
    print()


def example_4_postfile_with_deposition():
    """
    Example 4: POSTFILE output for deposition analysis.

    Shows how to configure POSTFILE output and then parse the
    resulting binary file for concentration + deposition data.
    """
    print("=" * 70)
    print("EXAMPLE 4: POSTFILE Output for Deposition")
    print("=" * 70)

    print("""
  After running AERMOD with deposition, the POSTFILE contains
  concentration, dry deposition, and wet deposition for every
  receptor at every timestep.

  To parse POSTFILE output with deposition data:

    from pyaermod.postfile import read_postfile

    # Auto-detect text vs binary format
    result = read_postfile("postfile.bin", has_deposition=True)

    # Access the DataFrame
    df = result.data
    print(df.columns)
    # ['timestep', 'receptor', 'concentration', 'dry_depo', 'wet_depo']

    # Filter by timestep
    hour_14 = df[df['timestep'] == 2001031514]

    # Get total deposition
    df['total_depo'] = df['dry_depo'] + df['wet_depo']

    # Maximum deposition receptor
    max_idx = df['total_depo'].idxmax()
    print(f"Max deposition at receptor {df.loc[max_idx, 'receptor']}")
""")

    print("  See notebook 06_Postfile_Analysis.ipynb for interactive examples.")
    print()


def main():
    """Run all deposition modeling examples."""
    print()
    print("+" + "=" * 68 + "+")
    print("|" + " " * 14 + "PyAERMOD Deposition Modeling Examples" + " " * 16 + "|")
    print("+" + "=" * 68 + "+")
    print()

    examples = [
        ("Gas Deposition (SO2)", example_1_gas_deposition),
        ("Particle Deposition (PM)", example_2_particle_deposition),
        ("Multi-Source Groups", example_3_multi_source_groups),
        ("POSTFILE with Deposition", example_4_postfile_with_deposition),
    ]

    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")

    print()

    for _, func in examples:
        try:
            func()
        except Exception as e:
            print(f"\n  Error: {e}\n")

    print("+" + "=" * 68 + "+")
    print("|" + " " * 20 + "All examples complete!" + " " * 25 + "|")
    print("+" + "=" * 68 + "+")
    print()
    print("  Deposition methods (DepositionMethod enum):")
    print("    DRYDPLT  — Dry depletion")
    print("    WETDPLT  — Wet depletion")
    print("    GASDEPVD — Gas deposition (velocity-dependent)")
    print("    GASDEPDF — Gas deposition (diffusivity-based)")
    print()
    print("  Output types (OutputPathway.output_type):")
    print("    DDEP  — Dry deposition flux")
    print("    WDEP  — Wet deposition flux")
    print("    DEPOS — Total deposition flux")
    print()


if __name__ == "__main__":
    main()

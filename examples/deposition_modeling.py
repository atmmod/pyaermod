"""
PyAERMOD Deposition Modeling Example

Demonstrates how to configure gas and particle deposition for AERMOD,
including dry deposition, wet deposition, and combined deposition
analysis.

This script covers:
  1. Gas dry deposition with a point source
  2. Particle deposition with size/mass/density distributions
  3. Source groups mixing gas and particle sources
  4. Reading deposition results back from a POSTFILE

Which quantities AERMOD calculates is set on MODELOPT, through four
ControlPathway flags (coset.f, subroutine MODOPT):

    calculate_concentration   -> CONC   (on by default)
    calculate_deposition      -> DEPOS  total (dry + wet) deposition
    calculate_dry_deposition  -> DDEP   dry deposition
    calculate_wet_deposition  -> WDEP   wet deposition

Any combination may be switched on; AERMOD then writes one set of
results per quantity, always in the order CONC, DEPOS, DDEP, WDEP.
OutputPathway.output_type does not select anything: AERMOD has no
per-file output type, and a deck that sets only output_type is a
concentration-only deck.

Units: AERMOD reports concentration in micrograms/m**3 but deposition
in g/m**2, totalled (not averaged) over each averaging period; ANNUAL
deposition is g/m**2/yr (coset.f MODOPT and output.f PERAVE).

Dry and wet depletion of the plume switch on by themselves once any
source has deposition inputs, even in a CONC-only run (soset.f SOCARD);
add "NODRYDPLT" or "NOWETDPLT" to ControlPathway.extra_model_options to
turn either off. While depletion or any deposition output is on, every
source needs particle or gas deposition inputs (soset.f SRCQA, E242).

Terrain: DFAULT forces elevated terrain and overrides FLAT with warning
W206 (coset.f MODOPT), so every deck here that asks for FLAT also sets
regulatory_default=False. A regulatory (DFAULT) run keeps elevated
terrain and gives its receptors elevations, from AERMAP for example.

The decks name met_2023.sfc / met_2023.pfl as placeholders; put your
own AERMET output there (wet deposition needs its precipitation fields).
"""

from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
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

# Site categories for gas dry deposition, as in EPA's testgas case:
# GDSEASON gives a Wesely season category (1-5) for each calendar month,
# GDLANUSE a land-use category (1-9) for each 10-degree wind sector.
GAS_DEPOSITION_SITE = {
    "gas_deposition_seasons": [4, 4, 4, 5, 1, 1, 1, 1, 1, 2, 3, 3],
    "gas_deposition_land_use": [4] * 36,
}


def example_1_gas_deposition():
    """
    Example 1: Gas dry deposition for SO2.

    Uses AERMOD's own built-in gas deposition values for SO2.
    """
    print("=" * 70)
    print("EXAMPLE 1: Gas Dry Deposition (SO2)")
    print("=" * 70)

    # SO2 gas deposition parameters: AERMOD's own built-in values for SO2
    # (soset.f GASDEP), in GASDEPOS field order.
    gas_dep = GasDepositionParams(
        diffusivity=0.1112,         # cm2/s -- molecular diffusivity in air (Da)
        diffusivity_water=1.83e-5,  # cm2/s -- molecular diffusivity in water (Dw)
        cuticular_resistance=732.0, # s/cm -- lipid cuticle resistance (rcl)
        henry_constant=72.0,        # Pa m3/mol -- Henry's law constant
    )

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
        )
    )

    # Control pathway for SO2. Gas deposition is a non-regulatory option:
    # AERMOD accepts GASDEPOS only with ALPHA (E198), and ALPHA only
    # without DFAULT (E204). Gas dry deposition also needs the site's
    # Wesely season category for each month (GDSEASON) and land-use
    # category for each 10-degree sector (GDLANUSE); without them AERMOD
    # stops with E244 (soset.f).
    control = ControlPathway(
        title_one="SO2 Gas Deposition Example",
        title_two="Concentration and dry deposition",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
        calculate_concentration=True,    # MODELOPT CONC
        calculate_dry_deposition=True,   # MODELOPT DDEP
        regulatory_default=False,
        alpha=True,
        **GAS_DEPOSITION_SITE,
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

    # Tables for every quantity on MODELOPT: concentration in ug/m3 and
    # dry deposition in g/m2 over each averaging period (g/m2/yr ANNUAL).
    output = OutputPathway(
        receptor_table=True,
        max_table=True,
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
    print("  MODELOPT: CONC DDEP (with ALPHA)")
    print(f"  Gas diffusivity in air: {gas_dep.diffusivity} cm2/s")
    print(f"  Henry's law constant: {gas_dep.henry_constant} Pa m3/mol")
    print()


def example_2_particle_deposition():
    """
    Example 2: Particle deposition with size distribution.

    Models PM emissions with a three-bin particle size distribution
    (Method 1) and calculates total, dry and wet deposition.
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
        )
    )

    # Method 1 particle deposition needs no ALPHA, but this deck asks for
    # FLAT terrain, and DFAULT would override that with elevated terrain
    # (W206, coset.f MODOPT): the 50 m source base would then sit above
    # receptors at 0 m. So regulatory_default is off, as in the gas decks.
    control = ControlPathway(
        title_one="Particle Deposition Example",
        title_two="Concentration with total, dry and wet deposition",
        pollutant_id=PollutantType.PM10,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT,
        calculate_concentration=True,    # MODELOPT CONC
        calculate_deposition=True,       # MODELOPT DEPOS (dry + wet)
        calculate_dry_deposition=True,   # MODELOPT DDEP
        calculate_wet_deposition=True,   # MODELOPT WDEP
        regulatory_default=False,        # keeps FLAT (DFAULT forces ELEV)
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
    )

    project = AERMODProject(control, sources, receptors, meteorology, output)
    project.write("particle_deposition.inp")

    print("  Input file written: particle_deposition.inp")
    print("  MODELOPT: CONC DEPOS DDEP WDEP")
    print(f"  Particle diameters: {particle_dep.diameters} um")
    print(f"  Mass fractions: {particle_dep.mass_fractions}")
    print(f"  Densities: {particle_dep.densities} g/cm3")
    print()


def example_3_multi_source_groups():
    """
    Example 3: Gas and particle sources together.

    Demonstrates source groups where each group has a different
    deposition configuration, in one run that calculates concentration
    and dry deposition.
    """
    print("=" * 70)
    print("EXAMPLE 3: Source Groups with Mixed Deposition")
    print("=" * 70)

    sources = SourcePathway()

    # Gas source — SO2 from combustion
    gas_dep = GasDepositionParams(
        diffusivity=0.1112,
        diffusivity_water=1.83e-5,
        cuticular_resistance=732.0,
        henry_constant=72.0,
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
        )
    )

    # A source with no deposition inputs cannot join this run. Once any
    # source has deposition inputs, dry and wet depletion are on by
    # default, and then AERMOD needs particle or gas deposition inputs for
    # every source (soset.f SRCQA, E242) -- even in a run with CONC alone.
    # Model such a source in a run that has no deposition sources, or add
    # "NODRYDPLT" and "NOWETDPLT" to extra_model_options in a CONC-only run.

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
    ]

    # The gas source needs ALPHA (and so no DFAULT) and the site
    # categories, as in Example 1. The pollutant is OTHER: the sources emit
    # different pollutants, and AERMOD refuses a 1-hour average for PM25
    # (E363).
    control = ControlPathway(
        title_one="Multi-Source Deposition Example",
        title_two="Gas and particle sources in separate groups",
        pollutant_id=PollutantType.OTHER,
        averaging_periods=["ANNUAL", "24", "1"],
        terrain_type=TerrainType.FLAT,
        calculate_concentration=True,    # MODELOPT CONC
        calculate_dry_deposition=True,   # MODELOPT DDEP
        regulatory_default=False,
        alpha=True,
        **GAS_DEPOSITION_SITE,
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
    print("  MODELOPT: CONC DDEP (with ALPHA)")
    print()


def example_4_postfile_with_deposition():
    """
    Example 4: POSTFILE output for deposition analysis.

    Shows how deposition results appear in a POSTFILE and how to
    parse them.
    """
    print("=" * 70)
    print("EXAMPLE 4: POSTFILE Output for Deposition")
    print("=" * 70)

    print("""
  A POSTFILE holds one value per receptor per timestep for every
  quantity on MODELOPT, in the order CONC, DEPOS, DDEP, WDEP. With
  MODELOPT CONC DDEP WDEP that is concentration, dry deposition and
  wet deposition:

    output = OutputPathway(
        postfile="postfile.txt",
        postfile_averaging="1",     # must be on AVERTIME
        postfile_format="PLOT",     # or "UNFORM" for binary
        file_format="EXP",          # FILEFORM EXP keeps small values
    )

  Hourly deposition values are often far below the 0.00001 that the default
  fixed-point format can show, so FILEFORM EXP is worth setting.

  To parse a POSTFILE:

    from pyaermod.postfile import read_postfile

    result = read_postfile("postfile.txt")   # text or binary, auto-detected
    print(result.output_types)               # e.g. ('CONC', 'DDEP')
    df = result.data

  A text POSTFILE names its value columns in its header, and the reader
  takes them from there, one column per output type: CONC is
  'concentration', DEPOS 'total_depo', DDEP 'dry_depo' and WDEP
  'wet_depo'. So the POSTFILE of Example 1 or 3 (CONC DDEP) has columns

    ['x', 'y', 'concentration', 'dry_depo', 'zelev', 'zhill', 'zflag', 'ave', 'grp', 'date']

  and that of Example 2 (CONC DEPOS DDEP WDEP) has

    ['x', 'y', 'concentration', 'total_depo', 'dry_depo', 'wet_depo', 'zelev', 'zhill', 'zflag', 'ave', 'grp', 'date']

  result.column_for("DDEP") names the column of one output type. A
  binary (UNFORM) POSTFILE records neither its output types nor its
  receptors, so give both:

    result = read_postfile("postfile.bin",
                           output_types="CONC DEPOS DDEP WDEP",
                           receptor_coords=[(x1, y1), (x2, y2), ...])

  Receptor with the most deposition in a single hour:

    # AERMOD writes total deposition (g/m2 in each hour) when MODELOPT
    # has DEPOS; otherwise add the dry and wet parts
    if "total_depo" not in df:
        df["total_depo"] = df.get("dry_depo", 0.0) + df.get("wet_depo", 0.0)

    peak = df.loc[df["total_depo"].idxmax()]
    print(f"Max deposition at ({peak['x']}, {peak['y']}) on {peak['date']}")
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
        func()

    print("+" + "=" * 68 + "+")
    print("|" + " " * 20 + "All examples complete!" + " " * 25 + "|")
    print("+" + "=" * 68 + "+")
    print()
    print("  Output quantities (ControlPathway flags -> MODELOPT):")
    print("    calculate_concentration  -> CONC   concentration, ug/m3")
    print("    calculate_deposition     -> DEPOS  total deposition, g/m2")
    print("    calculate_dry_deposition -> DDEP   dry deposition, g/m2")
    print("    calculate_wet_deposition -> WDEP   wet deposition, g/m2")
    print("  Deposition is totalled over each averaging period (g/m2/yr for ANNUAL).")
    print()


if __name__ == "__main__":
    main()

"""
PyAERMOD End-to-End Example

Complete workflow: Generate input → Run AERMOD → Parse output → Analyze results
"""

from pyaermod.input_generator import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    PointSource,
    ReceptorPathway,
    CartesianGrid,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    TerrainType
)
from pyaermod.runner import AERMODRunner, run_aermod
from pyaermod.output_parser import parse_aermod_output

import pandas as pd
from pathlib import Path


def example_1_simple_run():
    """
    Example 1: Simple end-to-end AERMOD run

    Creates a basic point source model, runs it (if AERMOD available),
    and analyzes results.
    """
    print("="*70)
    print("EXAMPLE 1: Simple End-to-End Run")
    print("="*70)

    # ========================================================================
    # STEP 1: Generate Input File
    # ========================================================================
    print("\n1. Generating AERMOD input file...")

    control = ControlPathway(
        title_one="Simple Point Source Example",
        title_two="End-to-end pyaermod demonstration",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL"],
        terrain_type=TerrainType.FLAT
    )

    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=10.0,
        stack_height=50.0,
        stack_temp=400.0,
        exit_velocity=15.0,
        stack_diameter=2.0,
        emission_rate=1.5,
        source_groups=["ALL"]
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

    # Note: You'll need actual met files for this to work
    meteorology = MeteorologyPathway(
        surface_file="example_met.sfc",
        profile_file="example_met.pfl"
    )

    output = OutputPathway(
        receptor_table=True,
        receptor_table_rank=10,
        max_table=True,
        summary_file="simple_example.sum"
    )

    project = AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )

    # Write input file
    input_file = "simple_example.inp"
    project.write(input_file)
    print(f"   ✓ Input file created: {input_file}")

    # ========================================================================
    # STEP 2: Run AERMOD (if executable available)
    # ========================================================================
    print("\n2. Running AERMOD...")
    print("   (This step requires AERMOD executable and met files)")
    print("   Skipping actual AERMOD execution in this demo")

    # To actually run AERMOD, uncomment this:
    # try:
    #     runner = AERMODRunner()
    #     result = runner.run(input_file, timeout=600)
    #
    #     if result.success:
    #         print(f"   ✓ AERMOD completed successfully ({result.runtime_seconds:.1f}s)")
    #         output_file = result.output_file
    #     else:
    #         print(f"   ✗ AERMOD failed: {result.error_message}")
    #         return
    # except FileNotFoundError as e:
    #     print(f"   ! {e}")
    #     print("   Install AERMOD to run actual simulations")
    #     return

    # ========================================================================
    # STEP 3: Parse Output (using sample output for demo)
    # ========================================================================
    print("\n3. Parsing AERMOD output...")
    print("   (Using sample output for demonstration)")

    # For demo, we'll use a sample output file if it exists
    sample_output = "test1_output.out"
    if Path(sample_output).exists():
        results = parse_aermod_output(sample_output)
        print(f"   ✓ Output parsed successfully")

        # ========================================================================
        # STEP 4: Analyze Results
        # ========================================================================
        print("\n4. Analyzing results...")

        # Display summary
        print("\n" + results.summary())

        # Get concentration data
        annual_df = results.get_concentrations('ANNUAL')

        # Statistical analysis
        print("\nStatistical Analysis:")
        print(f"  Mean concentration: {annual_df['concentration'].mean():.4f} ug/m^3")
        print(f"  Max concentration:  {annual_df['concentration'].max():.4f} ug/m^3")
        print(f"  Min concentration:  {annual_df['concentration'].min():.4f} ug/m^3")

        # Check compliance
        pm25_standard = 12.0  # Annual PM2.5 NAAQS
        max_conc = annual_df['concentration'].max()

        print(f"\nCompliance Check (PM2.5 Annual Standard = {pm25_standard} ug/m^3):")
        if max_conc > pm25_standard:
            print(f"  ⚠️  EXCEEDS STANDARD by {((max_conc/pm25_standard - 1)*100):.1f}%")
        else:
            print(f"  ✅ COMPLIES (at {(max_conc/pm25_standard*100):.1f}% of standard)")

        # Export results
        results.export_to_csv("results", prefix="simple_example")
        print("\n   ✓ Results exported to CSV files in 'results/' directory")

    else:
        print(f"   Sample output file not found: {sample_output}")
        print("   Run test_output_parser.py first to create sample output")

    print("\n" + "="*70)
    print("Example complete!")
    print("="*70)


def example_2_parameter_sweep():
    """
    Example 2: Parameter sweep - test multiple emission rates

    Demonstrates how to easily run multiple scenarios.
    """
    print("\n\n")
    print("="*70)
    print("EXAMPLE 2: Parameter Sweep (Multiple Emission Rates)")
    print("="*70)

    print("\nGenerating input files for emission rate sweep...")

    emission_rates = [0.5, 1.0, 1.5, 2.0, 2.5]
    input_files = []

    for rate in emission_rates:
        # Create control pathway
        control = ControlPathway(
            title_one=f"Parameter Sweep - Emission Rate = {rate} g/s",
            pollutant_id=PollutantType.PM25,
            averaging_periods=["ANNUAL"],
            terrain_type=TerrainType.FLAT
        )

        # Create source with varying emission rate
        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STACK1",
            x_coord=0.0,
            y_coord=0.0,
            stack_height=50.0,
            stack_temp=400.0,
            exit_velocity=15.0,
            stack_diameter=2.0,
            emission_rate=rate  # Varying parameter
        ))

        # Receptors (same for all)
        receptors = ReceptorPathway()
        receptors.add_cartesian_grid(
            CartesianGrid.from_bounds(
                x_min=-500, x_max=500,
                y_min=-500, y_max=500,
                spacing=50
            )
        )

        # Met and output
        meteorology = MeteorologyPathway(
            surface_file="example_met.sfc",
            profile_file="example_met.pfl"
        )

        output = OutputPathway(
            receptor_table=True,
            max_table=True
        )

        # Create project and write
        project = AERMODProject(control, sources, receptors, meteorology, output)

        filename = f"sweep_rate_{rate:.1f}.inp"
        project.write(filename)
        input_files.append(filename)

        print(f"   ✓ Created {filename}")

    print(f"\nGenerated {len(input_files)} input files")

    # To run the batch (requires AERMOD):
    print("\nTo run this parameter sweep:")
    print("  from pyaermod.runner import AERMODRunner")
    print("  runner = AERMODRunner()")
    print(f"  results = runner.run_batch({input_files}, n_workers=4)")
    print("\nThis will run all scenarios in parallel!")

    print("\n" + "="*70)


def example_3_comparison():
    """
    Example 3: Compare different configurations

    Shows how to compare multiple modeling scenarios.
    """
    print("\n\n")
    print("="*70)
    print("EXAMPLE 3: Scenario Comparison")
    print("="*70)

    scenarios = {
        "Baseline": {
            "stack_height": 50.0,
            "emission_rate": 1.5
        },
        "Taller Stack": {
            "stack_height": 75.0,
            "emission_rate": 1.5
        },
        "Higher Emissions": {
            "stack_height": 50.0,
            "emission_rate": 3.0
        },
        "Optimized": {
            "stack_height": 75.0,
            "emission_rate": 1.0
        }
    }

    print("\nGenerating scenarios:")

    for name, params in scenarios.items():
        control = ControlPathway(
            title_one=f"Scenario: {name}",
            pollutant_id=PollutantType.PM25,
            averaging_periods=["ANNUAL"],
            terrain_type=TerrainType.FLAT
        )

        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STACK1",
            x_coord=0.0,
            y_coord=0.0,
            stack_height=params["stack_height"],
            stack_temp=400.0,
            exit_velocity=15.0,
            stack_diameter=2.0,
            emission_rate=params["emission_rate"]
        ))

        receptors = ReceptorPathway()
        receptors.add_cartesian_grid(
            CartesianGrid.from_bounds(
                x_min=-1000, x_max=1000,
                y_min=-1000, y_max=1000,
                spacing=100
            )
        )

        meteorology = MeteorologyPathway(
            surface_file="example_met.sfc",
            profile_file="example_met.pfl"
        )

        output = OutputPathway(
            receptor_table=True,
            max_table=True,
            summary_file=f"{name.lower().replace(' ', '_')}.sum"
        )

        project = AERMODProject(control, sources, receptors, meteorology, output)

        filename = f"scenario_{name.lower().replace(' ', '_')}.inp"
        project.write(filename)

        print(f"   ✓ {name:20s} - Stack: {params['stack_height']:5.1f}m, "
              f"Rate: {params['emission_rate']:.1f} g/s")

    print("\n" + "="*70)
    print("All scenarios generated!")
    print("\nNext steps:")
    print("  1. Run AERMOD for each scenario")
    print("  2. Parse outputs")
    print("  3. Compare maximum concentrations")
    print("  4. Select optimal configuration")
    print("="*70)


def example_4_workflow_automation():
    """
    Example 4: Complete automated workflow

    Shows how to chain everything together in a production workflow.
    """
    print("\n\n")
    print("="*70)
    print("EXAMPLE 4: Complete Automated Workflow")
    print("="*70)

    print("""
This example shows a complete production workflow:

1. Define modeling parameters
2. Generate AERMOD input
3. Run AERMOD
4. Parse output
5. Perform statistical analysis
6. Check regulatory compliance
7. Generate report
8. Export results to CSV

Code structure:
""")

    workflow_code = '''
from pyaermod.input_generator import *
from pyaermod.runner import AERMODRunner
from pyaermod.output_parser import parse_aermod_output

def automated_workflow(facility_name, emission_rate, met_year):
    """Automated AERMOD modeling workflow"""

    # 1. Configure model
    control = ControlPathway(
        title_one=f"{facility_name} - Air Quality Assessment",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24"],
        terrain_type=TerrainType.FLAT
    )

    # 2. Define sources
    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="MAIN_STACK",
        x_coord=0.0,
        y_coord=0.0,
        stack_height=50.0,
        stack_temp=400.0,
        exit_velocity=15.0,
        stack_diameter=2.0,
        emission_rate=emission_rate
    ))

    # 3. Define receptors
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(
        CartesianGrid.from_bounds(
            x_min=-2000, x_max=2000,
            y_min=-2000, y_max=2000,
            spacing=100
        )
    )

    # 4. Specify meteorology
    meteorology = MeteorologyPathway(
        surface_file=f"met_{met_year}.sfc",
        profile_file=f"met_{met_year}.pfl"
    )

    # 5. Configure output
    output = OutputPathway(
        receptor_table=True,
        max_table=True,
        summary_file=f"{facility_name}_results.sum"
    )

    # 6. Generate and run
    project = AERMODProject(control, sources, receptors, meteorology, output)
    input_file = f"{facility_name}.inp"
    project.write(input_file)

    # 7. Execute AERMOD
    runner = AERMODRunner()
    result = runner.run(input_file, timeout=1800)

    if not result.success:
        raise RuntimeError(f"AERMOD failed: {result.error_message}")

    # 8. Parse results
    results = parse_aermod_output(result.output_file)

    # 9. Analyze
    annual_df = results.get_concentrations('ANNUAL')
    max_annual = results.get_max_concentration('ANNUAL')

    # 10. Compliance check
    pm25_standard = 12.0
    complies = max_annual['value'] <= pm25_standard

    # 11. Generate report
    report = {
        'facility': facility_name,
        'emission_rate': emission_rate,
        'max_concentration': max_annual['value'],
        'max_location': max_annual['x'], max_annual['y'],
        'standard': pm25_standard,
        'complies': complies,
        'percentage_of_standard': max_annual['value'] / pm25_standard * 100
    }

    # 12. Export
    results.export_to_csv(f"results/{facility_name}", prefix=facility_name)

    return report

# Usage:
report = automated_workflow("ABC_Factory", emission_rate=2.5, met_year=2023)
print(f"Compliance: {'PASS' if report['complies'] else 'FAIL'}")
'''

    print(workflow_code)

    print("\n" + "="*70)
    print("This workflow can be:")
    print("  • Run on-demand for permit applications")
    print("  • Automated in CI/CD pipelines")
    print("  • Scheduled for routine compliance monitoring")
    print("  • Integrated into facility management systems")
    print("="*70)


def main():
    """Run all examples"""

    examples = [
        ("Simple End-to-End", example_1_simple_run),
        ("Parameter Sweep", example_2_parameter_sweep),
        ("Scenario Comparison", example_3_comparison),
        ("Workflow Automation", example_4_workflow_automation)
    ]

    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*16 + "PyAERMOD End-to-End Examples" + " "*24 + "║")
    print("╚" + "="*68 + "╝")
    print("\nThese examples demonstrate complete workflows from")
    print("input generation through result analysis.\n")

    for i, (name, func) in enumerate(examples, 1):
        print(f"{i}. {name}")

    print("\nPress Enter to continue...")
    input()

    # Run all examples
    for name, func in examples:
        try:
            func()
        except Exception as e:
            print(f"\nError in {name}: {e}")

    print("\n\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*22 + "Examples Complete!" + " "*25 + "║")
    print("╚" + "="*68 + "╝")
    print("\nKey Takeaways:")
    print("  • Input generation is fast and type-safe")
    print("  • AERMOD execution is automated")
    print("  • Output parsing is instant")
    print("  • Results are ready for analysis in pandas")
    print("  • Complete workflows are reproducible")
    print("\nYou've eliminated 80%+ of manual AERMOD work!")


if __name__ == "__main__":
    main()

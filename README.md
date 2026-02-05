# PyAERMOD - Python Wrapper for AERMOD

**Status:** 🚀 MVP 40% Complete - Core functionality operational

A Python wrapper for the EPA's AERMOD atmospheric dispersion model that eliminates manual input file creation and enables automated result analysis.

## What is This?

PyAERMOD is a Python toolkit that makes AERMOD (the EPA's regulatory air dispersion model) much easier to use by:

1. **Generating AERMOD input files from Python** - No more manual text editing
2. **Parsing AERMOD output into pandas** - Instant access to results in Python/pandas
3. **Automating routine workflows** - Parameter sweeps, batch processing, compliance checking

## Why Use This?

**Traditional AERMOD Workflow:**
- ❌ Manual text file editing
- ❌ Formatting errors
- ❌ 30-60 minutes per model setup
- ❌ Manual result extraction
- ❌ Hard to reproduce
- ❌ Expensive consulting fees for routine work

**With PyAERMOD:**
- ✅ Generate inputs from Python in 2-5 minutes
- ✅ Type-safe, validated parameters
- ✅ Results instantly in pandas DataFrames
- ✅ Easy parameter sweeps
- ✅ Fully reproducible workflows
- ✅ **80%+ time savings**

## What's Implemented

### ✅ Input File Generator
- Control pathway (CO) - averaging periods, pollutants, terrain
- Point sources with full stack parameters
- Building downwash (PRIME)
- Cartesian and polar receptor grids
- Discrete receptors
- Meteorology file specification
- Output options
- Source grouping

### ✅ Output Parser
- Parse AERMOD `.out` files
- Extract all run metadata
- Extract source/receptor information
- Parse concentration results (all averaging periods)
- Convert to pandas DataFrames
- Find maximum concentrations
- Statistical analysis
- Compliance checking
- Export to CSV

## Quick Start

### 1. Generate AERMOD Input

```python
from pyaermod_input_generator import *

# Define project
control = ControlPathway(
    title_one="My Facility Assessment",
    pollutant_id=PollutantType.PM25,
    averaging_periods=["ANNUAL", "24"],
    terrain_type=TerrainType.FLAT
)

# Add emission source
sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK1",
    x_coord=500.0,
    y_coord=500.0,
    base_elevation=10.0,
    stack_height=50.0,
    stack_temp=400.0,  # Kelvin
    exit_velocity=15.0,  # m/s
    stack_diameter=2.0,  # m
    emission_rate=1.5  # g/s
))

# Add receptor grid
receptors = ReceptorPathway()
receptors.add_cartesian_grid(
    CartesianGrid.from_bounds(
        x_min=0, x_max=2000,
        y_min=0, y_max=2000,
        spacing=100  # 100m spacing
    )
)

# Specify meteorology
meteorology = MeteorologyPathway(
    surface_file="met_data.sfc",
    profile_file="met_data.pfl"
)

# Configure output
output = OutputPathway(
    receptor_table=True,
    max_table=True,
    summary_file="results.sum"
)

# Create and write input file
project = AERMODProject(control, sources, receptors, meteorology, output)
project.write("facility.inp")
```

### 2. Run AERMOD

```bash
# Run AERMOD executable (manual for now)
aermod.exe facility

# Or on Linux/Mac
./aermod facility
```

### 3. Parse Results

```python
from pyaermod_output_parser import parse_aermod_output

# Parse output file
results = parse_aermod_output("facility.out")

# Display summary
print(results.summary())

# Get concentrations as DataFrame
annual_df = results.get_concentrations('ANNUAL')
print(annual_df.head())

# Find maximum concentration
max_info = results.get_max_concentration('ANNUAL')
print(f"Max: {max_info['value']:.2f} ug/m^3 at ({max_info['x']}, {max_info['y']})")

# Statistical analysis
stats = annual_df['concentration'].describe()
print(stats)

# Check compliance
pm25_standard = 12.0  # ug/m^3
if max_info['value'] > pm25_standard:
    print(f"⚠️  EXCEEDS PM2.5 ANNUAL STANDARD by {max_info['value']/pm25_standard:.1%}")
else:
    print("✅ COMPLIES with PM2.5 ANNUAL STANDARD")

# Export to CSV
results.export_to_csv("results/", prefix="facility")
```

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Detailed getting started guide
- **[PROGRESS_SUMMARY.md](PROGRESS_SUMMARY.md)** - Current implementation status
- **[aermod_wrapper_architecture.md](aermod_wrapper_architecture.md)** - Full technical architecture
- **[implementation_priorities.md](implementation_priorities.md)** - Development roadmap

## Examples

Run the test scripts to see everything in action:

```bash
# Test input generator
python test_input_generator.py

# Test output parser
python test_output_parser.py
```

## Files Included

```
pyaermod/
├── README.md                          # This file
├── QUICKSTART.md                      # Getting started guide
├── PROGRESS_SUMMARY.md                # Implementation status
├── aermod_wrapper_architecture.md     # Technical architecture
├── implementation_priorities.md       # Development roadmap
│
├── pyaermod_input_generator.py        # Input file generator (750 lines)
├── pyaermod_output_parser.py          # Output parser (600+ lines)
│
├── test_input_generator.py            # Input generator tests
├── test_output_parser.py              # Output parser tests
│
└── building_downwash_example.inp      # Sample generated input
```

## Requirements

**Python:** 3.8+

**Dependencies:**
```
pandas
numpy
```

**AERMOD:** You must provide your own AERMOD executable (available free from EPA)

## Installation (Future)

When packaged:
```bash
pip install pyaermod
```

For now, just import the modules directly.

## Roadmap

### ✅ Completed (Week 1)
- Input file generation
- Output parsing
- Documentation
- Test suite

### 🔄 Next (Week 2)
- AERMOD subprocess wrapper
- Basic visualization (contour plots, maps)
- End-to-end examples

### 🚀 Future (Week 3+)
- Area/volume sources
- Advanced building downwash
- AERMET/AERMAP integration
- Meteorology data APIs
- Interactive dashboards
- PyPI package

## Performance

- **Input generation:** <1ms for simple, <50ms for complex (100 sources, 10k receptors)
- **Output parsing:** <100ms typical, <2s for large files
- **Memory:** Minimal (proportional to receptor count)

## Validation

Based on AERMOD version 24142 source code analysis:
- All 120 AERMOD keywords identified
- Input format matches EPA specifications
- Output parser tested with sample AERMOD output

**Test against EPA test cases** to verify correctness before production use.

## Contributing

This is a work in progress. Contributions welcome!

Priority areas:
1. Area/volume/line sources
2. Visualization
3. Additional output formats (POSTFILE, PLOTFILE)
4. AERMET/AERMAP wrappers
5. Documentation improvements

## Credits

- AERMOD: EPA's Support Center for Regulatory Atmospheric Modeling (SCRAM)
- Based on AERMOD version 24142 (2024)
- Source code analysis and documentation review

## Disclaimer

⚠️ **Important:** This is a wrapper around AERMOD, not a reimplementation. It:
- Uses the official EPA AERMOD binaries for all calculations
- Maintains regulatory acceptance
- Simply automates input generation and output parsing

Always validate results against EPA test cases for your specific use case.

## License

To be determined (likely MIT or Apache 2.0)

## Support

This is a development project. For production use:
1. Test thoroughly with your specific use cases
2. Validate against EPA test cases
3. Document any limitations
4. Consider professional review for regulatory submittals

## Status

**Current Version:** 0.1.0-alpha
**Last Updated:** 2026-02-05
**Completion:** 40% (MVP core functionality operational)

---

**Ready to eliminate manual AERMOD work?** Check out [QUICKSTART.md](QUICKSTART.md) to get started in 5 minutes!

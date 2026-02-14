# PyAERMOD

Python wrapper for EPA's AERMOD atmospheric dispersion model.

PyAERMOD automates input file generation, model execution, output parsing, and result visualization — replacing manual text-file editing with a type-safe Python API.

## Installation

```bash
pip install pyaermod             # core (input generation + output parsing)
pip install pyaermod[viz]        # + matplotlib/folium visualization
pip install pyaermod[geo]        # + geospatial export (GeoTIFF, Shapefile)
pip install pyaermod[gui]        # + Streamlit interactive GUI
pip install pyaermod[all]        # everything
```

For development:
```bash
git clone https://github.com/atmmod/pyaermod.git
cd pyaermod
pip install -e ".[dev,all]"
```

## Quick Start

### Generate AERMOD Input

```python
from pyaermod.input_generator import (
    AERMODProject, ControlPathway, SourcePathway, ReceptorPathway,
    MeteorologyPathway, OutputPathway, PointSource, CartesianGrid,
    PollutantType, TerrainType,
)

control = ControlPathway(
    title_one="My Facility",
    pollutant_id=PollutantType.PM25,
    averaging_periods=["ANNUAL", "24"],
    terrain_type=TerrainType.FLAT,
)

sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK1", x_coord=500.0, y_coord=500.0,
    base_elevation=10.0, stack_height=50.0, stack_temp=400.0,
    exit_velocity=15.0, stack_diameter=2.0, emission_rate=1.5,
))

receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(
    x_min=0, x_max=2000, y_min=0, y_max=2000, spacing=100,
))

meteorology = MeteorologyPathway(
    surface_file="met_data.sfc", profile_file="met_data.pfl",
)
output = OutputPathway(receptor_table=True, max_table=True)

project = AERMODProject(control, sources, receptors, meteorology, output)
project.write("facility.inp")
```

### Run AERMOD & Parse Results

```python
from pyaermod.runner import run_aermod
from pyaermod.output_parser import parse_aermod_output

result = run_aermod("facility.inp")
results = parse_aermod_output(result.output_file)

df = results.get_concentrations("ANNUAL")
print(results.summary())
```

### Parse POSTFILE Output

```python
from pyaermod.postfile import read_postfile

# Auto-detects text vs binary format
post = read_postfile("postfile.out")
df = post.to_dataframe()

# Binary postfile with deposition data
dep = read_postfile("depo_post.out", has_deposition=True)
print(dep.to_dataframe()[["concentration", "dry_depo", "wet_depo"]])
```

## Features

### Source Types (10)
POINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT, BUOYLINE, OPENPIT

### Advanced Modeling
- **Background concentrations** — uniform, period-specific, or sector-dependent
- **Deposition** — dry, wet, or combined for gas and particle emissions
- **NO2/SO2 chemistry** — OLM, PVMRM, ARM2, GRSM with ozone data
- **Source groups** — custom groupings with per-group PLOTFILE output
- **EVENT processing** — date/receptor-specific analysis

### Preprocessors
- **AERMET** — meteorological data preprocessing (Stages 1-3)
- **AERMAP** — terrain elevation extraction with DEM download pipeline

### Analysis & Visualization
- Output parsing to pandas DataFrames
- POSTFILE parser for timestep-level results (text and binary formats)
- Contour plots, interactive Folium maps, 3D surfaces, wind roses
- Geospatial export: GeoTIFF, GeoPackage, Shapefile, GeoJSON

### Validation & Automation
- Input validation across all AERMOD pathways
- Building downwash / BPIP integration (point, area, and volume sources)
- Batch processing with parallel execution
- Interactive Streamlit GUI (`pyaermod-gui`)

## Project Structure

```
src/pyaermod/
    __init__.py          # Public API
    input_generator.py   # AERMOD input file generation (all source types)
    validator.py         # Configuration validation
    runner.py            # AERMOD subprocess execution
    output_parser.py     # Output file parsing
    postfile.py          # POSTFILE output parser
    visualization.py     # Matplotlib/Folium plots
    advanced_viz.py      # 3D surfaces, wind roses, animations
    aermet.py            # AERMET preprocessor wrapper
    aermap.py            # AERMAP input generation
    terrain.py           # DEM download + AERMAP pipeline
    geospatial.py        # Coordinate transforms, GIS export
    bpip.py              # Building downwash calculations
    gui.py               # Streamlit web GUI
tests/                   # 1158 tests, 95% coverage
examples/                # Example scripts and Jupyter notebooks
docs/                    # Architecture and quickstart guides
```

## Requirements

- Python >= 3.11
- numpy, pandas (core)
- AERMOD executable (free from [EPA SCRAM](https://www.epa.gov/scram))

## Documentation

- [Quick Start Guide](docs/quickstart.md)
- [GUI User Guide](docs/gui-guide.md)
- [Architecture](docs/architecture.md)
- [API Reference](https://atmmod.github.io/pyaermod/api/)
- [Examples](examples/)

## License

MIT

## Disclaimer

PyAERMOD is a wrapper around AERMOD, not a reimplementation. It uses official EPA binaries for all calculations and maintains regulatory acceptance. Always validate results against EPA test cases for your specific use case.

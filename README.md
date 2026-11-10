# PyAERMOD

[![Tests](https://github.com/atmmod/pyaermod/actions/workflows/tests.yml/badge.svg)](https://github.com/atmmod/pyaermod/actions/workflows/tests.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Python wrapper for EPA's AERMOD atmospheric dispersion model.

PyAERMOD automates input file generation, model execution, output parsing, and result visualization — replacing manual text-file editing with a type-safe Python API.

## Installation

PyAERMOD needs Python 3.11 or later. Install it into a virtual
environment (`python -m venv .venv`, then activate it):

```bash
pip install pyaermod               # core (input generation + output parsing)
pip install "pyaermod[viz]"        # + matplotlib/folium visualization
pip install "pyaermod[geo]"        # + geospatial export (GeoTIFF, Shapefile)
pip install "pyaermod[gui]"        # + the graphical interface
pip install "pyaermod[all]"        # everything
```

Keep the quotes: zsh, the default shell on macOS, otherwise reads the
square brackets as a file pattern.

### The graphical interface

To get the app without setting up an environment, install it with
[pipx](https://pipx.pypa.io/) or [uv](https://docs.astral.sh/uv/), then
start it:

```bash
pipx install "pyaermod[gui]"       # or: uv tool install "pyaermod[gui]"
pyaermod-app                       # opens the GUI in a browser tab
```

After `pip install "pyaermod[gui]"` the same command is available in that
environment, also as `pyaermod gui`. `"pyaermod[gui-desktop]"` adds
`pyaermod-desktop`, the same app in a window of its own. There are no
separate desktop downloads.

### conda

PyAERMOD is not on conda-forge yet (the recipe is in
[`conda-recipe/`](conda-recipe/)). Once the conda-forge package is
published, `conda install -c conda-forge pyaermod` will install the
library and `conda install -c conda-forge pyaermod-gui` the library with
the graphical interface. Until then, use pip inside a conda environment.

### Troubleshooting

- `zsh: no matches found: pyaermod[gui]`: quote the name, as above.
- `pyaermod-app: command not found`: activate the environment you
  installed into; after `pipx install` run `pipx ensurepath`, after
  `uv tool install` run `uv tool update-shell`. `python -m pyaermod.gui_v2`
  starts the app without the command being on `PATH`.
- `Cannot listen on 127.0.0.1 port 8080`: the port is in use; start with
  `pyaermod-app --port 8081`.
- pip compiles packages and fails: Python 3.11 to 3.14 install the GUI
  from wheels alone; with a newer Python, pick one of those
  (`uv tool install --python 3.13 "pyaermod[gui]"`).

More in the [GUI User Guide](docs/gui-guide.md#install).

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

# A run with several output types: a text file names its columns in its
# header; a binary file needs the run's MODELOPT line (or type names)
dep = read_postfile("depo_post.bin", output_types="CONC DDEP WDEP")
print(dep.output_types)                     # ('CONC', 'DDEP', 'WDEP')
print(dep.data[dep.column_for("WDEP")].max())  # the wet_depo column
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
- **AERMET** — meteorological data preprocessing (Stage 1 and METPREP runstreams in AERMET 24142/26135 syntax)
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
- Interactive NiceGUI app (`pyaermod-app` browser, `pyaermod-desktop` native window)

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
    gui_v2/              # NiceGUI app + pywebview desktop wrapper
tests/                   # 2,200+ tests on every CI leg, coverage gated at 95%
examples/                # Example scripts and Jupyter notebooks
docs/                    # Architecture and quickstart guides
```

## Requirements

- Python >= 3.11
- numpy, pandas (core)
- AERMOD executable (free from [EPA SCRAM](https://www.epa.gov/scram))

## Documentation

- [Quick Start Guide](docs/quickstart.md)
- [Ten Common AERMOD Jobs](docs/use-cases.md)
- [GUI User Guide](docs/gui-guide.md)
- [Architecture](docs/architecture.md)
- [API Reference](https://atmmod.github.io/pyaermod/api/)
- [Examples](examples/)

## Citing PyAERMOD

If PyAERMOD contributes to published work, please cite the archival release.
The repository's [`CITATION.cff`](CITATION.cff) carries the metadata in a
form GitHub, Zenodo and reference managers read directly (GitHub's
"Cite this repository" button renders it as APA or BibTeX):

> Capps, S. (2026). *PyAERMOD: Python wrapper for EPA's AERMOD air
> dispersion model* (version 2.2.0) [Computer software].
> https://doi.org/10.5281/zenodo.23512927

A journal article describing PyAERMOD and its validation is in
preparation for the *Journal of the Air & Waste Management Association*;
once it is published, `CITATION.cff`'s `preferred-citation` will point to
it and citing the article is preferred.

## License

MIT

## Performance

Driving AERMOD through `pyaermod.runner` costs a run 1 to 20 ms over
calling the binary with `subprocess` directly (medians of 50 interleaved
runs of EPA's `aertest` case, AERMOD v26135, on a GitHub Actions runner
and in the release container), and nearly all of that is the latency of
CPython's polling wait under `subprocess.run(timeout=...)`, not
pyaermod's own file handling. A batch of 32 such runs through
`AERMODRunner.run_batch` goes from 440 to 520 runs per minute at one
worker to 1,370 to 1,410 at four on four-CPU machines (a 2.7× to 3.1×
speed-up). The numbers, the machines and the command that reproduces
them are in [docs/benchmarks.md](docs/benchmarks.md).

## Disclaimer

PyAERMOD is a wrapper around AERMOD, not a reimplementation. It uses official EPA binaries for all calculations and maintains regulatory acceptance. PyAERMOD is validated against EPA AERMOD v26135 / AERMET v26135 (EPA reference archives of 2026-07-09) — a gfortran build driven by pyaermod reproduces EPA's AERTEST plotfile bit-for-bit and every POSTFILE in EPA's test suite within EPA's own tolerance (see [docs/validation.md](docs/validation.md)); v24142 remains supported for cross-version regression. Always validate results against EPA test cases for your specific use case.

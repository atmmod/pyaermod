# PyAERMOD Quick Start Guide

## Installation

```bash
pip install pyaermod
```

For visualization, geospatial export, or the GUI, install extras:

```bash
pip install pyaermod[all]  # everything
```

## 5-Minute Example

Create a complete AERMOD input file in just a few lines:

```python
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
)

# 1. Define the control parameters
control = ControlPathway(
    title_one="My First AERMOD Run",
    pollutant_id=PollutantType.PM25,
    averaging_periods=["ANNUAL", "24"],
    terrain_type="FLAT",
)

# 2. Add your emission source(s)
sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK1",
    x_coord=500.0,      # meters (UTM)
    y_coord=500.0,      # meters (UTM)
    base_elevation=10.0,
    stack_height=50.0,   # meters
    stack_temp=400.0,    # Kelvin
    exit_velocity=15.0,  # m/s
    stack_diameter=2.0,  # meters
    emission_rate=1.5,   # g/s
))

# 3. Define receptor grid
receptors = ReceptorPathway()
receptors.add_cartesian_grid(
    CartesianGrid.from_bounds(
        x_min=0, x_max=2000,
        y_min=0, y_max=2000,
        spacing=100,  # 100m grid spacing
    )
)

# 4. Specify meteorology files
meteorology = MeteorologyPathway(
    surface_file="met_data.sfc",
    profile_file="met_data.pfl",
)

# 5. Configure output
output = OutputPathway(
    receptor_table=True,
    max_table=True,
    summary_file="results.sum",
)

# 6. Create project and write input file
project = AERMODProject(
    control=control,
    sources=sources,
    receptors=receptors,
    meteorology=meteorology,
    output=output,
)

project.write("my_first_run.inp")
```

That's it! You now have a valid AERMOD input file.

## Running AERMOD from Python

```python
from pyaermod.runner import run_aermod

result = run_aermod("my_first_run.inp")
print(f"Success: {result.success}")
print(f"Runtime: {result.runtime_seconds:.1f}s")
print(f"Output: {result.output_file}")
```

!!! note
    You need the AERMOD executable installed separately. Download it from
    [EPA SCRAM](https://www.epa.gov/scram).

## Parsing Output

```python
from pyaermod.output_parser import parse_aermod_output

results = parse_aermod_output(result.output_file)
df = results.get_concentrations("ANNUAL")
print(f"Max concentration: {df['concentration'].max():.4g}")
```

## Visualization

```python
from pyaermod.visualization import AERMODVisualizer

viz = AERMODVisualizer(results)
fig = viz.plot_contours(averaging_period="ANNUAL")
```

## Common Patterns

### Multiple Sources

```python
from pyaermod.input_generator import SourcePathway, PointSource

sources = SourcePathway()

stack_data = [
    (100.0, 200.0, 1.0),
    (300.0, 400.0, 2.5),
    (500.0, 600.0, 0.8),
]

for i, (x, y, rate) in enumerate(stack_data):
    sources.add_source(PointSource(
        source_id=f"STACK{i + 1}",
        x_coord=x,
        y_coord=y,
        stack_height=50.0,
        stack_temp=400.0,
        exit_velocity=15.0,
        stack_diameter=2.0,
        emission_rate=rate,
    ))
```

### Polar Grid Around Facility

```python
from pyaermod.input_generator import PolarGrid, ReceptorPathway

receptors = ReceptorPathway()
receptors.add_polar_grid(PolarGrid(
    x_origin=500.0,
    y_origin=500.0,
    dist_init=100.0,      # start 100m from origin
    dist_num=20,          # 20 distance rings
    dist_delta=100.0,     # 100m spacing
    dir_init=0.0,         # start at north
    dir_num=36,           # 36 directions (every 10 degrees)
    dir_delta=10.0,
))
```

### Building Downwash

```python
from pyaermod.input_generator import PointSource

stack = PointSource(
    source_id="STACK1",
    x_coord=0.0,
    y_coord=0.0,
    stack_height=30.0,
    stack_temp=400.0,
    exit_velocity=15.0,
    stack_diameter=2.0,
    emission_rate=1.5,
    building_height=25.0,
    building_width=40.0,
    building_length=60.0,
    building_x_offset=0.0,
    building_y_offset=20.0,
)
```

For direction-dependent building downwash, use the
[BPIP module](api/bpip.md) or the GUI's built-in BPIP calculator.

### Parameter Sweep

```python
from pyaermod.input_generator import *

for rate in [1.0, 2.0, 3.0, 4.0, 5.0]:
    control = ControlPathway(
        title_one=f"Emission Rate = {rate} g/s",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["1", "24", "ANNUAL"],
    )

    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="STACK1",
        x_coord=500.0,
        y_coord=500.0,
        stack_height=50.0,
        stack_temp=400.0,
        exit_velocity=15.0,
        stack_diameter=2.0,
        emission_rate=rate,
    ))

    project = AERMODProject(control, sources, receptors, meteorology, output)
    project.write(f"scenario_rate_{rate}.inp")
```

### POSTFILE Parsing

```python
from pyaermod.postfile import read_postfile

# Auto-detects text (PLOT) or binary (UNFORM) format
result = read_postfile("postfile.pst")
print(f"Max concentration: {result.max_concentration:.4g}")
print(f"Location: {result.max_location}")

# Step through timesteps
for date in result.data["date"].unique():
    ts = result.get_timestep(date)
    print(f"{date}: max={ts['concentration'].max():.4g}")
```

## Validation

The input generator includes built-in validation:

- Required parameters are enforced
- Parameter types are checked (floats, ints, strings)
- Enum values are validated (pollutant types, terrain types)
- Coordinate systems are consistent

```python
from pyaermod.validator import Validator

validator = Validator()
errors = validator.validate(project)
for error in errors:
    print(error)
```

## What's Available Now

| Feature | Module |
|---------|--------|
| 10 source types (POINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT, BUOYLINE, OPENPIT) | `input_generator` |
| Input file validation | `validator` |
| AERMOD execution | `runner` |
| Output parsing to DataFrames | `output_parser` |
| POSTFILE parsing (text and binary) | `postfile` |
| Contour plots, Folium maps | `visualization` |
| 3D surfaces, wind roses, animations | `advanced_viz` |
| AERMET meteorological preprocessing | `aermet` |
| AERMAP terrain preprocessing | `aermap` |
| DEM download and terrain pipeline | `terrain` |
| Coordinate transforms, GIS export | `geospatial` |
| Building downwash (BPIP) | `bpip` |
| Interactive 7-page web GUI | `gui` |

## AERMOD Keywords Supported

Based on AERMOD version 24142:

### Control Pathway (CO)

STARTING, FINISHED, TITLEONE, TITLETWO, MODELOPT, AVERTIME, POLLUTID,
RUNORNOT, ELEVUNIT, FLAGPOLE, HALFLIFE, DCAYCOEF, URBANOPT, LOW_WIND

### Source Pathway (SO)

LOCATION (POINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT,
BUOYLINE, OPENPIT), SRCPARAM, BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ,
SRCGROUP, URBANSRC, APTS_CAP, BLPINPUT, BLPGROUP, RBARRIER, RDEPRESS

### Receptor Pathway (RE)

GRIDCART, GRIDPOLR, DISCCART, ELEVUNIT

### Meteorology Pathway (ME)

SURFFILE, PROFFILE, SURFDATA, UAIRDATA, STARTEND, WDROTATE

### Output Pathway (OU)

RECTABLE, MAXTABLE, DAYTABLE, SUMMFILE, MAXIFILE, PLOTFILE, POSTFILE

## Next Steps

- Try the [GUI User Guide](gui-guide.md) for a no-code modeling experience
- Browse the [API Reference](api/index.md) for detailed module documentation
- Check the [examples/](https://github.com/atmmod/pyaermod/tree/main/examples)
  directory for runnable scripts and Jupyter notebooks

## Getting Help

1. Check the [examples/](https://github.com/atmmod/pyaermod/tree/main/examples)
   directory for more usage patterns
2. Review the [Architecture](architecture.md) document for design details
3. Browse the [API Reference](api/index.md) for module documentation
4. Read AERMOD documentation from [EPA SCRAM](https://www.epa.gov/scram)

## License

MIT

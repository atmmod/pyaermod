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

Building downwash (PRIME) is also supported on `AreaSource` and `VolumeSource`
with the same five fields. For direction-dependent building downwash, use the
[BPIP module](api/bpip.md) or the GUI's built-in BPIP calculator.

### Background Concentrations

Add ambient background levels to account for existing pollution:

```python
from pyaermod.input_generator import (
    SourcePathway, BackgroundConcentration, BackgroundSector,
)

sources = SourcePathway()
# ... add sources ...

# Uniform background
sources.background = BackgroundConcentration(
    annual=12.0,    # ug/m3
    period_24h=35.0,
)

# Or sector-dependent background
sources.background = BackgroundConcentration(
    sectors=[
        BackgroundSector(
            sector_id=1, start_direction=0.0, end_direction=90.0,
            values={"ANNUAL": 12.0, "24": 35.0},
        ),
        BackgroundSector(
            sector_id=2, start_direction=90.0, end_direction=360.0,
            values={"ANNUAL": 8.0, "24": 25.0},
        ),
    ]
)
```

### Deposition Modeling

Enable dry or wet deposition for any source type:

```python
from pyaermod.input_generator import (
    PointSource, DepositionMethod, GasDepositionParams,
    ParticleDepositionParams,
)

stack = PointSource(
    source_id="STACK1",
    x_coord=500.0, y_coord=500.0,
    stack_height=50.0, stack_temp=400.0,
    exit_velocity=15.0, stack_diameter=2.0,
    emission_rate=1.5,
    deposition_method=DepositionMethod.DEPOS,
    gas_deposition=GasDepositionParams(
        diffusivity=0.25, alpha_star=1000.0,
        reactivity=8.0, mesophyll_resistance=0.0,
        henry_constant=0.01,
    ),
)
```

Set `OutputPathway(output_type="DEPOS")` to get deposition flux instead of
concentration in the output.

### NO2 Chemistry Options

For NO2 modeling, configure Tier 2/3 chemistry:

```python
from pyaermod.input_generator import (
    ControlPathway, PollutantType, ChemistryMethod,
    ChemistryOptions, OzoneData,
)

control = ControlPathway(
    title_one="NO2 Tier 3 Analysis",
    pollutant_id=PollutantType.NO2,
    averaging_periods=["1", "ANNUAL"],
    chemistry=ChemistryOptions(
        method=ChemistryMethod.PVMRM,
        default_no2_ratio=0.5,
        ozone_data=OzoneData(uniform_value=40.0),  # ppb
    ),
)
```

### Source Groups

Define custom source groups for separate impact analysis:

```python
from pyaermod.input_generator import SourcePathway, SourceGroupDefinition

sources = SourcePathway()
# ... add sources STACK1, STACK2, STACK3 ...

sources.group_definitions = [
    SourceGroupDefinition(
        group_name="BOILERS",
        source_ids=["STACK1", "STACK2"],
        description="Boiler stacks",
    ),
    SourceGroupDefinition(
        group_name="PROCESS",
        source_ids=["STACK3"],
        description="Process vents",
    ),
]
```

### EVENT Processing

Run AERMOD in event mode for specific date/receptor combinations:

```python
from pyaermod.input_generator import EventPathway, EventPeriod

events = EventPathway(events=[
    EventPeriod(
        event_name="MAXDAY",
        source_group="ALL",
        averaging_period="24",
        start_date="24031501",
        end_date="24031524",
    ),
])

project = AERMODProject(control, sources, receptors, meteorology, output)
project.write("facility.inp", event_filename="facility.evn")
```

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

### Binary POSTFILE with Deposition

Binary (UNFORM) POSTFILEs from deposition runs store concentration, dry deposition,
and wet deposition as contiguous blocks of `N` floats each (3N total per record).

```python
from pyaermod.postfile import read_postfile

# Explicit deposition flag
result = read_postfile("depo_post.pst", has_deposition=True)
df = result.to_dataframe()
print(df[["x", "y", "concentration", "dry_depo", "wet_depo"]])

# Auto-detect: provide num_receptors, parser checks if 3N floats
result = read_postfile("post.pst", num_receptors=50)
# If 150 floats found, deposition is auto-detected
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
| Background concentrations (uniform, period, sector) | `input_generator` |
| Deposition modeling (dry, wet, combined) | `input_generator` |
| NO2/SO2 chemistry (OLM, PVMRM, ARM2, GRSM) | `input_generator` |
| Source group management and per-group output | `input_generator` |
| EVENT processing for date/receptor analysis | `input_generator` |
| Input file validation | `validator` |
| AERMOD execution | `runner` |
| Output parsing to DataFrames | `output_parser` |
| POSTFILE parsing (text and binary, with deposition) | `postfile` |
| Contour plots, Folium maps | `visualization` |
| 3D surfaces, wind roses, animations | `advanced_viz` |
| AERMET meteorological preprocessing | `aermet` |
| AERMAP terrain preprocessing | `aermap` |
| DEM download and terrain pipeline | `terrain` |
| Coordinate transforms, GIS export | `geospatial` |
| Building downwash (BPIP) for POINT, AREA, VOLUME | `bpip` |
| Interactive 7-page web GUI | `gui` |

## AERMOD Keywords Supported

Based on AERMOD version 24142:

### Control Pathway (CO)

STARTING, FINISHED, TITLEONE, TITLETWO, MODELOPT, AVERTIME, POLLUTID,
RUNORNOT, ELEVUNIT, FLAGPOLE, HALFLIFE, DCAYCOEF, URBANOPT, LOW_WIND,
EVENTFIL, O3VALUES, OZONEFIL, NO2RATIO, NOXFIL

### Source Pathway (SO)

LOCATION (POINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT,
BUOYLINE, OPENPIT), SRCPARAM, BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ,
SRCGROUP, URBANSRC, APTS_CAP, BLPINPUT, BLPGROUP, RBARRIER, RDEPRESS,
BACKGRND, BGSECTOR, GASDEPOS, PARTDIAM, MASSFRAX, PARTDENS, METHOD_2,
DEPRESS

### Receptor Pathway (RE)

GRIDCART (with ELEV/HILL terrain support), GRIDPOLR (with ELEV/HILL
terrain support), DISCCART, ELEVUNIT

### Meteorology Pathway (ME)

SURFFILE, PROFFILE, SURFDATA, UAIRDATA, STARTEND, WDROTATE

### Output Pathway (OU)

RECTABLE, MAXTABLE, DAYTABLE, SUMMFILE, MAXIFILE, PLOTFILE, POSTFILE

### Event Pathway (EV)

EVENTPER, EVENTLOC

## Testing & Validation

PyAERMOD includes comprehensive testing validated against official EPA data:

- **1166 unit and integration tests** with 95% code coverage
- **315 EPA test cases** parsed from official AERMOD v24142 output files (LOVETT, FLATELEV, TESTPART, etc.)
- End-to-end pipeline tests chaining input generation through visualization

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

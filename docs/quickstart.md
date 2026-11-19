# Quick start

[Install](install.md) pyaermod first. AERMOD is a separate program from EPA;
install.md says where to get it.

## 5-minute example

Write an AERMOD input file:

```python
from pyaermod import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    PointSource,
    ReceptorPathway,
    CartesianGrid,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    TerrainType,
)

# 1. Define the control parameters
control = ControlPathway(
    title_one="My First AERMOD Run",
    pollutant_id=PollutantType.PM25,
    averaging_periods=["ANNUAL", "24"],
    terrain_type=TerrainType.FLAT,
)

# 2. Add your emission source(s)
sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK1",
    x_coord=500.0,      # meters, UTM (Universal Transverse Mercator)
    y_coord=500.0,      # meters, UTM
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
    period_plot_files="conc",  # one PLOTFILE per period: the value at every receptor
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

`project.write()` has validated the project and written `my_first_run.inp`.

## Validation

`project.write()` checks the project against AERMOD's rules first and
refuses one AERMOD would stop on. To see the findings yourself:

```python
from pyaermod.validator import Validator

result = Validator.validate(project)
print(result.is_valid)
for error in result.errors:      # errors and warnings, each naming its field
    print(error)
```

## Running AERMOD from Python

<!-- docs-example: skip (runs AERMOD) -->
```python
from pyaermod.runner import run_aermod

result = run_aermod("my_first_run.inp")
print(f"Success: {result.success}")
print(f"Runtime: {result.runtime_seconds:.1f}s")
print(f"Output: {result.output_file}")
```

## Parsing output

<!-- docs-example: skip (reads the output of that run) -->
```python
from pyaermod.output_parser import parse_aermod_output

results = parse_aermod_output(result.output_file)
print(results.summary())
df = results.get_concentrations("ANNUAL")   # the .out summary table's rows
print(f"Max concentration: {df['concentration'].max():.4g}")
```

`get_concentrations` returns the rows of the `.out` summary tables (the
highest receptors), not the whole grid. For every receptor, read the
PLOTFILE (AERMOD's per-receptor text output) that `period_plot_files`
asked for:

<!-- docs-example: skip (reads a plot file of that run) -->
```python
from pyaermod.aermod_outputs import read_plotfile

plot_names = output.period_plot_file_names(control.averaging_periods)
grid = read_plotfile(plot_names["ANNUAL"]).to_dataframe()   # X, Y, AVERAGE_CONC, ...
```

## Visualization

Contour the grid from the period's PLOTFILE:

<!-- docs-example: skip (maps the output of that run) -->
```python
from pyaermod.visualization import AERMODVisualizer

viz = AERMODVisualizer(results)
fig = viz.plot_contours(averaging_period="ANNUAL", plotfile=plot_names["ANNUAL"])
```

Without `plotfile=`, `plot_contours` contours only the summary table's rows
and warns.

![Two contour maps of PM2.5 around a single stack: the annual average and the highest 24-hour average](images/use-cases/01_point_source.png)

The figure comes from [job 1](use-cases.md#1-single-stack-flat-terrain-annual-and-24-hour-pm25),
a complete version of this example run against AERMOD.

## Reading an existing deck

`read_aermod_input` reads an AERMOD `.inp` file (a deck) into the same
objects, so an existing run can be changed and written again. Lines pyaermod
does not model are kept in `project.unparsed_lines` and written back by
`project.write()` (see the [keyword audit](keyword-audit-v26135.md)); pass
`preserve_unparsed=False` to drop them. Reading logs one warning per pathway
and keyword.

<!-- docs-example: skip (reads a deck of your own) -->
```python
import logging
from pyaermod.input_reader import read_aermod_input

logging.basicConfig(level=logging.WARNING)
project = read_aermod_input("epa_deck.inp")
# WARNING:pyaermod.input_reader:SO EMISFACT: 33 lines not modelled by pyaermod; ...
for line in project.unparsed_lines:
    print(line.pathway, line.keyword, line.fields)
project.write("epa_deck_copy.inp")   # the EMISFACT lines are in the SO pathway
```

## Command line

`pyaermod` has these subcommands:

| Command | Does |
|---|---|
| `pyaermod info` | Prints the version and which features are available |
| `pyaermod gui [--host ADDR] [--port N] [--no-browser]` | Opens the [GUI](gui-guide.md) in a browser tab, as `pyaermod-app` does |
| `pyaermod validate DECK [--check-files]` | Validates a `.inp` file; exits 1 on an error; `--check-files` checks that the met files exist |
| `pyaermod run DECK [--executable PATH] [--working-dir DIR] [--timeout SECS] [--force]` | Validates and runs AERMOD; the timeout defaults to 3600 s; `--force` runs despite validation errors |
| `pyaermod parse OUT` | Summarizes an AERMOD `.out` file |
| `pyaermod plotfile FILE` | Summarizes a PLOTFILE, MAXIFILE, RANKFILE or deposition file |
| `pyaermod profile DECK --profile NAME [--apply]` | Checks a deck against a regulatory profile (`EPA-AppendixW-2017`, `EPA-AppendixW-2023`, `Screening`); `--apply` rewrites the deck |

## Background concentrations

A background concentration adds existing ambient levels to the modeled ones:

```python
from pyaermod import (
    SourcePathway, BackgroundConcentration, BackgroundSector,
)

sources = SourcePathway()
# ... add sources ...

# Uniform background: one value applied to every hour
sources.background = BackgroundConcentration(uniform_value=12.0)  # µg/m³

# Or varying in time: a flag of EMISFACT's table and its values
# (SEASON: winter, spring, summer, fall; MONTH takes 12, HROFDY 24)
sources.background = BackgroundConcentration(
    period_values={"SEASON": [14.0, 11.0, 9.0, 12.0]},
)

# Or sector-dependent: starting directions, then each sector's values
sources.background = BackgroundConcentration(
    sectors=[
        BackgroundSector(sector_id=1, start_direction=0.0),
        BackgroundSector(sector_id=2, start_direction=90.0),
    ],
    sector_values={(1, "ANNUAL"): 12.0,
                   (2, "SEASON"): [9.0, 8.0, 7.0, 8.0]},
)
```

## More

[Ten common AERMOD jobs](use-cases.md) has complete scripts, each run
against AERMOD with the figure it drew:

- several stacks, source groups and a polar grid
  ([job 2](use-cases.md#2-facility-with-several-stacks-source-groups-and-a-polar-grid));
  building downwash with BPIP-PRIME and PRIME
  ([job 3](use-cases.md#3-building-downwash-with-bpip-prime))
- dry and wet deposition with particle size categories
  ([job 9](use-cases.md#9-particle-dry-and-wet-deposition); size
  distributions in [Particle size distributions](psd.md))
- NO2 chemistry with OLM, PVMRM, ARM2 or GRSM
  ([job 6](use-cases.md#6-1-hour-no2-with-tier-2-and-tier-3-chemistry))
- the 1-hour SO2 and NO2 and 24-hour PM2.5 design values
  ([job 7](use-cases.md#7-naaqs-compliance-the-1-hour-so2-design-value))
- terrain from AERMAP
  ([job 8](use-cases.md#8-elevated-and-complex-terrain-with-aermap))

Also:

- hourly emission files (`HOUREMIS`): [`hourly_emissions`](api/hourly_emissions.md)
- EVENT runs (date- and receptor-specific analysis): `EventPathway` in [`pathways`](api/pathways.md)
- runs of many cases: [Ensembles](ensemble.md)
- POSTFILEs (timestep-level results, text or binary): [`postfile`](api/postfile.md)
- every AERMOD keyword pyaermod reads and writes: the [keyword audit](keyword-audit-v26135.md)
- evidence that pyaermod reproduces EPA's results: [Validation](validation.md)
- the [GUI user guide](gui-guide.md), the [API reference](api/index.md) and the
  [examples](https://github.com/atmmod/pyaermod/tree/main/examples) directory

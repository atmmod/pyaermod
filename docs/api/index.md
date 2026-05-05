# API Reference

PyAERMOD v1.5 is organized into **29 modules** grouped by workflow stage.
For a stable, versioned public surface prefer `from pyaermod.api import ...`
— it re-exports every documented name from a single module so your code
doesn't depend on internal layout.

## Project building

Build, read, write, and validate AERMOD input files.

| Module | Description |
|---|---|
| [input_generator](input_generator.md) | Thin facade + `AERMODProject` — `project.write()`, `project.to_aermod_input()` |
| [sources](sources.md) | All 12 source dataclasses, deposition params, `SourcePathway`, background concentrations |
| [receptors](receptors.md) | `CartesianGrid`, `PolarGrid`, `DiscreteReceptor`, `ReceptorPathway` |
| [pathways](pathways.md) | Enums + `ControlPathway`, `MeteorologyPathway`, `OutputPathway`, `EventPathway` |
| [input_reader](input_reader.md) | **Bidirectional** — parse existing `.inp` files back into `AERMODProject` |

## Validation

| Module | Description |
|---|---|
| [validator](validator.md) | Per-field range + consistency checks; `Validator.validate()` runs advanced checks by default |
| [validator_advanced](validator_advanced.md) | Cross-field checks (stack buoyancy, receptor extent, DFAULT consistency) |
| [regulatory](regulatory.md) | EPA Appendix W 2017 / 2023 + Screening profile presets with `apply()` and `check()` |

## Execution

| Module | Description |
|---|---|
| [runner](runner.md) | `AERMODRunner`, `BatchRunner`, `run_aermod()` subprocess wrappers |
| [runner_utils](runner_utils.md) | Progress, failure diagnostics, batch resume, SLURM templates |
| [cli](cli.md) | `pyaermod` command-line interface (`validate`, `run`, `parse`, `plotfile`, `profile`) |

## Outputs

| Module | Description |
|---|---|
| [output_parser](output_parser.md) | Parse `.out` files to pandas DataFrames |
| [aermod_outputs](aermod_outputs.md) | Readers for PLOTFILE / MAXIFILE / RANKFILE / SEASONHR / TOXXFILE / deposition |
| [postfile](postfile.md) | Binary POSTFILE (UNFORM) + text PLOT format |

## Visualization

| Module | Description |
|---|---|
| [visualization](visualization.md) | Contour plots, interactive Folium maps, raster export |
| [advanced_viz](advanced_viz.md) | 3-D surfaces, wind roses, concentration animations |

## Meteorology

| Module | Description |
|---|---|
| [aermet](aermet.md) | Stage 1 / 2 / 3 input-deck generation; `.SFC` and `.PFL` parsers |
| [aermet_runner](aermet_runner.md) | `AERMETRunner.run_stage()`, `run_aermet_pipeline()` |
| [met_ingest](met_ingest.md) | ASOS 1-minute, NOAA ISD, IGRA upper-air, MMIF data ingest |
| [met_qaqc](met_qaqc.md) | Missing-data, extremes, stability-consistency checks |

## Terrain

| Module | Description |
|---|---|
| [aermap](aermap.md) | AERMAP input-file generation |
| [terrain](terrain.md) | DEM download, AERMAP runner, elevation pipeline |
| [terrain_utils](terrain_utils.md) | NAD27/83/WGS84 datums, SRTM, mosaic, reproject, hill-height diagnostics |
| [geospatial](geospatial.md) | UTM/WGS84 transforms, GIS export |

## Downwash

| Module | Description |
|---|---|
| [bpip](bpip.md) | Building-downwash 36-sector projection engine |
| [prime](prime.md) | GEP stack-height rule, PRIME cavity region, project-level BPIP application |

## Chemistry

| Module | Description |
|---|---|
| [chemistry_presets](chemistry_presets.md) | OLM / PVMRM / GRSM factories, deposition defaults, project wiring helpers |

## GUI

| Module | Description |
|---|---|
| [gui_v2](gui_v2.md) | 7-tab NiceGUI app — browser + native desktop modes |

## Optional dependencies

Install the extras for the features you need:

| Extras group | Install command | Enables |
|---|---|---|
| `viz` | `pip install pyaermod[viz]` | `visualization`, `advanced_viz` |
| `geo` | `pip install pyaermod[geo]` | `geospatial`, `terrain`, `terrain_utils` (DEM + UTM/WGS84) |
| `gui` | `pip install pyaermod[gui]` | `gui` (Streamlit web app — pulls in viz + geo) |
| `met` | `pip install pyaermod[met]` | `met_ingest` network fetchers (ISD / IGRA) |
| `hpc` | `pip install pyaermod[hpc]` | `runner_utils` progress + SLURM |
| `all` | `pip install pyaermod[all]` | Everything |

## Stability guarantees

Names re-exported from `pyaermod.api` form the **stable public surface**.
The underlying module layout may change across minor releases (e.g. the
v1.5 split of `input_generator.py` into `sources.py` / `receptors.py` /
`pathways.py`), but the facade preserves backwards compatibility.

```python
# Prefer this (stable)
from pyaermod.api import PointSource, AERMODProject, read_aermod_input

# Avoid this in published code (internal layout)
from pyaermod.sources import PointSource  # subject to change
```

### Stable-core subset

If you want to stick to the minimum surface possible, check
`pyaermod.api.CORE_NAMES`. That frozenset of ~30 names covers the
project/source/receptor/pathway types, the runner and CLI, the input
reader and output parser, and the two EPA Appendix W profiles +
three NO2 chemistry presets. Any name in `CORE_NAMES` is guaranteed
to keep its signature across **every 1.x release** — additions to
the wider `pyaermod.api.__all__` may happen at any minor version
before they're promoted into `CORE_NAMES`.

```python
from pyaermod.api import CORE_NAMES, API_VERSION
assert "AERMODProject" in CORE_NAMES  # always True in 1.x
print(f"pyaermod API v{API_VERSION}")
```

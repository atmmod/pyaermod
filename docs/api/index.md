# API Reference

pyaermod's modules are grouped below by workflow stage. For a stable public
surface use `from pyaermod.api import ...`: it re-exports every documented
name from one module, so your code does not depend on the internal layout.

## Project building

Build, read, write, and validate AERMOD input files.

| Module | Description |
|---|---|
| [input_generator](input_generator.md) | Thin facade + `AERMODProject` — `project.write()`, `project.to_aermod_input()` |
| [sources](sources.md) | The source dataclasses, deposition params, `SourcePathway`, background concentrations |
| [hourly_emissions](hourly_emissions.md) | HOUREMIS files of rate-only records (AREA types, OPENPIT, VOLUME, LINE types); the AP-42 batch-drop wind profile from an SFC file |
| [receptors](receptors.md) | `CartesianGrid`, `PolarGrid`, `DiscreteReceptor`, `ReceptorPathway` |
| [pathways](pathways.md) | Enums + `ControlPathway`, `MeteorologyPathway`, `OutputPathway`, `EventPathway` |
| [input_reader](input_reader.md) | **Bidirectional** — parse existing `.inp` files back into `AERMODProject` |
| [unparsed](unparsed.md) | `UnparsedLine` — deck lines the reader keeps verbatim and the writer puts back |
| [source_importers](source_importers.md) | Sources from shapefiles (`.shp`) and AutoCAD drawings (`.dxf`) |
| [psd](psd.md) | Particle size distributions for Method 1 deposition: bins from cut points or a lognormal, representative diameters, aerodynamic-to-Stokes conversion, `ParticleDepositionParams` |

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
| [ensemble](ensemble.md) | `run_design()`: one directory per run, run IDs, a manifest, resume, `collect_plotfiles()` |
| [cli](cli.md) | The `pyaermod` command: `info`, `gui`, `validate`, `run`, `parse`, `plotfile`, `profile` (see [Command line](../quickstart.md#command-line)) |

## Outputs

| Module | Description |
|---|---|
| [output_parser](output_parser.md) | Parse `.out` files to pandas DataFrames |
| [aermod_outputs](aermod_outputs.md) | Readers for PLOTFILE / MAXIFILE / RANKFILE / SEASONHR / TOXXFILE / deposition |
| [postfile](postfile.md) | Binary POSTFILE (UNFORM) + text PLOT format |
| [design_values](design_values.md) | Design values (percentiles, NAAQS forms) from POSTFILE time series |
| [naaqs](naaqs.md) | The NAAQS reference table |

## Visualization

| Module | Description |
|---|---|
| [visualization](visualization.md) | Contour plots, interactive Folium maps, raster export |
| [advanced_viz](advanced_viz.md) | 3-D surfaces, wind roses, concentration animations |
| [kmz_export](kmz_export.md) | KMZ files for Google Earth |

## Meteorology

| Module | Description |
|---|---|
| [aermet](aermet.md) | Stage 1 and METPREP runstream generation (`AERMETStage2` deprecated); `.SFC` and `.PFL` parsers |
| [aermet_runner](aermet_runner.md) | `AERMETRunner.run_stage()`, `run_aermet_pipeline()` |
| [aersurface](aersurface.md), [aersurface_runner](aersurface_runner.md) | AERSURFACE deck and runner: monthly albedo, Bowen ratio and roughness from NLCD land cover |
| [met_ingest](met_ingest.md) | ASOS 1-minute, NOAA ISD, IGRA upper-air, MMIF data ingest |
| [met_qaqc](met_qaqc.md) | Missing-data, extremes, stability-consistency checks |

## Screening

| Module | Description |
|---|---|
| [aerscreen](aerscreen.md), [aerscreen_runner](aerscreen_runner.md) | AERSCREEN configuration and runner |

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

## EPA parity

| Module | Description |
|---|---|
| [regulatory_parity](regulatory_parity.md) | Scores pyaermod POSTFILEs against EPA's AERMOD test-suite reference files |
| [epa_sources](epa_sources.md) | Download locations of the EPA model source archives |

## GUI

| Module | Description |
|---|---|
| [gui_v2](gui_v2.md) | Seven-step NiceGUI app — browser + native desktop modes |

## Optional dependencies

Some modules need an extra, such as `viz` for `visualization` and `advanced_viz`,
`geo` for `geospatial` and `terrain_utils`, `terrain` for DEM download, and `gui` for
`gui_v2`. [Install](../install.md) lists every extra and the quoted
`pip install "pyaermod[...]"` form.

## Stability guarantees

Names re-exported from `pyaermod.api` form the **stable public surface**.
The module layout may change across minor releases (v1.5 split
`input_generator.py` into `sources.py`, `receptors.py` and `pathways.py`),
but the facade keeps the names working.

```python
# Prefer this (stable)
from pyaermod.api import PointSource, AERMODProject, read_aermod_input

# Avoid this in published code (internal layout)
from pyaermod.sources import PointSource  # subject to change
```

### Stable-core subset

`pyaermod.api.CORE_NAMES` is a frozenset of 31 names: the
project, source, receptor and pathway types, the runner, the input reader
and output parser, the two EPA Appendix W profiles and three NO2 chemistry
presets. A name in `CORE_NAMES` keeps its signature across **every 2.x
release**. Names can be added to the wider `pyaermod.api.__all__` in any
minor version before they are promoted into `CORE_NAMES`.

```python
from pyaermod.api import CORE_NAMES, API_VERSION
assert "AERMODProject" in CORE_NAMES  # always True in 2.x
print(f"pyaermod API v{API_VERSION}")
```

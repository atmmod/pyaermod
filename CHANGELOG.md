# Changelog

All notable changes to PyAERMOD will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.8.0] - 2026-05-04

### Added

#### WP-A: AERSCREEN wrapper
- `pyaermod.aerscreen.AERSCREENConfig` dataclass + `AERSCREENSourceType`
  StrEnum (POINT, FLARE, AREA, VOLUME, CAPPED, HORIZONTAL) with full
  per-source-type validation. Optional building downwash, terrain
  (lat/lon + DEM file), urban dispersion (population), Auer landuse
  code, and explicit-or-AUTO downwind distance scheme.
- `pyaermod.aerscreen_runner.AERSCREENRunner` mirroring the AERSURFACE
  runner pattern: stages `aerscreen.inp` in cwd, file-redirected
  stdout/stderr (pipe-deadlock safe), FATAL-in-output detection.
- pyaermod now wraps the **complete** EPA AERMOD family: AERMOD,
  AERMET, AERMAP, AERSURFACE, AERSCREEN, BPIP-PRIME.

#### WP-B: SHP + DXF source importers
- `pyaermod.source_importers.from_shapefile()` — imports any
  geopandas-readable file (.shp, .gpkg, .geojson) into pyaermod
  source dataclasses. Default geometry mapping: Point → PointSource,
  Polygon → AreaPolySource, LineString → LineSource. Override via
  `source_type=` (e.g. `RLineSource` for road centerlines). Optional
  `attribute_map=` for renaming truncated/cryptic shapefile columns.
- `pyaermod.source_importers.from_dxf()` — imports AutoCAD DXF
  (POINT, LINE, LWPOLYLINE, POLYLINE, CIRCLE entities). Closed
  polylines → AreaPoly, open → Line. Circles discretized to
  16-vertex polygons. Optional `z_as_height=True` uses DXF z
  elevation as stack/release height (rooftop emission models).
- New `pyaermod[cad]` optional extra: `ezdxf>=1.0.0` (~5 MB, MIT,
  pure Python). Added to the `all` extra.

## [1.7.0] - 2026-05-04

### Added — "Regulatory-grade open source"

#### WP-1: EPA AERMOD test-suite parity harness
- `pyaermod.regulatory_parity` module with `score_postfile_pair()` and
  `passes_parity()` helpers; pass criterion is best-fit slope within
  ±0.001 of 1.0 — the same margin EPA's own
  `Compare_AERMOD_test_cases.R` script publishes.
- Parametric pytest harness in `tests/regulatory/` covering all 41
  EPA AERMOD test decks plus the 5-year MULTYEAR PM-10 chain.
- Reproducible parity report at `docs/validation.md`:
  **104 / 104 POSTFILE comparisons within EPA tolerance.**
- `.github/workflows/epa_parity.yml` — workflow_dispatch CI job that
  compiles AERMOD from EPA source, fetches the test-case bundle, runs
  the harness, and uploads the rendered report.
- `scripts/run_epa_parity.py` for local report regeneration.

#### WP-2: AERSURFACE wrapper
- `pyaermod.aersurface.AERSURFACEConfig` dataclass with full validation
  (NLCD-year whitelist, snow-regime enum, per-month moisture / snow-cover
  lists, sector angles).
- `pyaermod.aersurface_runner.AERSURFACERunner` mirroring the AERMET
  runner pattern: stages `aersurface.inp` in cwd, file-redirected
  stdout/stderr, FATAL-in-output detection.
- pyaermod now wraps every preprocessor in the EPA AERMOD chain
  (AERMET, AERMAP, AERSURFACE, BPIP).

#### WP-3: Design-value / NAAQS post-processing
- `pyaermod.naaqs` reference table: PM2.5, PM10, NO2, SO2, CO, O3, Pb
  with 40 CFR Part 50 citations. PM2.5 annual reflects the 2024 EPA
  review (9.0 µg/m³).
- `pyaermod.design_values` design-value computations:
  `pm25_24hr_design_value`, `no2_1hr_design_value`,
  `so2_1hr_design_value`, `pm10_24hr_design_value`,
  `o3_8hr_design_value`, `annual_mean`, `add_background`,
  and the one-stop `naaqs_compliance_report()` dispatcher.
- Every function cites its 40 CFR Part 50 reference in its docstring.

#### WP-4: KMZ / Google Earth exporter
- `pyaermod.kmz_export.to_kmz()` — zero-dependency Google Earth
  exporter built on stdlib `zipfile` + `xml.etree`. Folders for
  Sources, Receptors, and Contours, each pre-styled.
- Optional pyproj-driven UTM → WGS84 reprojection.
- `ContourPolygon` dataclass for caller-supplied contour rings
  (interoperates with `geospatial.generate_contours`).

## [1.6.0] - 2026-05-04

### Robustness pass (items A–H)

#### Added
- **Path-traversal sandbox**: `read_aermod_input(path, sandbox=True)` raises
  `PathTraversalError` when referenced files (SURFFILE, PROFFILE, OZONEFIL,
  postfile, plot/summary/max files) escape the deck's parent directory.
- **Concurrent-run lock**: `AERMODRunner` acquires an fcntl/msvcrt advisory
  lock on the working directory so parallel jobs don't clobber each other.
- **Coverage gate**: CI fails below 95% (`--cov-fail-under=95`).
- **Benchmark regression gate**: PR benchmarks fail on >25% regression vs main.
- **Hypothesis fuzz tests**: property-based coverage on the input reader.
- **Advisory mypy step** in CI (Python 3.12, `continue-on-error`); baseline
  68 errors logged as a notice for ratcheting toward strict mode.
- **Salem stage-1 end-to-end test** for AERMET when EPA fixtures are present.

#### Changed
- **AERMET runner**: stages the deck as `aermet.inp` in the cwd before
  invoking the binary — AERMET v24142 reads from a fixed filename, not stdin.
  The previous stdin approach silently failed on the real binary.
- **Pipe-fix parity**: AERMET and AERMAP runners now redirect stdout/stderr
  to files (matching the AERMOD runner), avoiding 64 KB pipe-buffer deadlocks
  on chatty runs.
- **`validate=` deprecation**: `AERMODProject.to_aermod_input()` and
  `.write()` now emit a `DeprecationWarning` when `validate=` is omitted.
  In 2.0 the default flips from `False` to `True`. Pass `validate=True` or
  `validate=False` explicitly to silence the warning.

## [1.0.0] - 2026-02-14

### Added

#### Source Types
- **AreaSource** — rectangular area sources with rotation angle
- **AreaCircSource** — circular area sources with configurable vertex count
- **AreaPolySource** — irregular polygonal area sources
- **VolumeSource** — 3D emission volumes with initial dispersion
- **LineSource** — general linear sources (conveyors, pipelines)
- **RLineSource** — roadway-specific sources with mobile source physics
- **RLineExtSource** — extended roadway with per-endpoint elevations, optional barriers and road depression
- **BuoyLineSource** / **BuoyLineSegment** — buoyant line source groups with BLPINPUT/BLPGROUP
- **OpenPitSource** — open pit mine/quarry sources

#### Modules
- **Validator** (`pyaermod.validator`) — configuration validation for all 5 AERMOD pathways with cross-field checks
- **BPIP** (`pyaermod.bpip`) — building downwash / BPIP integration with 36-direction building parameters
- **AERMET** (`pyaermod.aermet`) — meteorological preprocessor input generation (Stages 1-3)
- **AERMAP** (`pyaermod.aermap`) — terrain preprocessor input generation with `from_aermod_project()` bridge
- **POSTFILE** (`pyaermod.postfile`) — POSTFILE output parser with timestep/receptor queries, auto-detection of text (PLOT) and binary (UNFORM) formats
- **Geospatial** (`pyaermod.geospatial`) — coordinate transforms (UTM/WGS84), GeoDataFrame creation, contour generation, GeoTIFF/GeoPackage/Shapefile/GeoJSON export
- **Terrain** (`pyaermod.terrain`) — DEM tile download from USGS TNM, AERMAP runner, output parser, elevation update pipeline
- **GUI** (`pyaermod.gui`) — 7-page Streamlit web application for interactive AERMOD workflow

#### Background Concentrations
- `BackgroundConcentration` and `BackgroundSector` dataclasses for ambient background levels
- Three modes: uniform value, period-specific values, or sector-dependent concentrations
- `SourcePathway.background` field generating `BACKGRND` and `BGSECTOR` keywords

#### Deposition Modeling
- `DepositionMethod` enum (`DRYDPLT`, `WETDPLT`, `GASDEPVD`, `GASDEPDF`)
- `GasDepositionParams` and `ParticleDepositionParams` for gas and particle deposition settings
- Deposition fields added to all 10 source types with shared `_deposition_to_aermod_lines()` helper
- `OutputPathway.output_type` for selecting concentration vs. deposition output

#### EVENT Processing
- `EventPeriod` and `EventPathway` dataclasses for event-based analysis
- `ControlPathway.eventfil` for linking event file
- `AERMODProject.write(event_filename=...)` generates EV pathway with `EVENTPER` records

#### NO2 / SO2 Chemistry Options
- `ChemistryMethod` enum: OLM, PVMRM, ARM2, GRSM
- `ChemistryOptions` dataclass with method, default NO2/NOx ratio, and ozone data
- `OzoneData` dataclass supporting ozone file, uniform value, or sector-specific values
- `ControlPathway.chemistry` field generating `MODELOPT`, `O3VALUES`, `OZONEFIL`, `NOXFIL` keywords
- Per-source `no2_ratio` field on `PointSource`

#### Source Group Management
- `SourceGroupDefinition` dataclass with group name, member source IDs, and description
- `SourcePathway.group_definitions` generating `SRCGROUP` keywords
- Per-group PLOTFILE output via `OutputPathway.plot_file_groups`

#### Building Downwash Expansion
- Building downwash (PRIME) fields extended from `PointSource` to also support `AreaSource` and `VolumeSource`
- `_building_downwash_lines()` and `_set_building_from_bpip()` module-level helpers shared across source types
- Terrain grid elevations via `CartesianGrid.terrain_elevations` and `PolarGrid.terrain_elevations`

#### Binary POSTFILE Deposition
- `UnformattedPostfileParser` now handles deposition records with `has_deposition` parameter (auto-detect or explicit)
- Parses 3N floats into concentration, dry deposition, and wet deposition columns

#### GUI Enhancements
- **ProjectSerializer**: JSON save/load for complete session state with round-trip fidelity
- **AreaCirc/AreaPoly forms** in SourceFormFactory
- **BPIP integration**: building forms, BPIP calculator wired to point, area, and volume sources
- **AERMAP elevation import**: 5th tab in receptor editor for terrain elevation upload
- **AERMET configuration**: dual-mode meteorology page (existing files vs. 3-stage AERMET config)
- **POSTFILE viewer**: 4th tab in Results Viewer with timestep slider, receptor time-series, animation GIF
- **Chemistry Options UI**: NO2 chemistry configuration with method, ozone data, and NOx file inputs
- **Source Groups UI**: create/delete source groups, per-group PLOTFILE checkboxes
- **Statistics helpers**: cross-period summary table, ranked receptor table, model complexity indicator
- **Export format detection**: dynamic format list based on installed optional dependencies

#### Testing & Quality
- 1166 tests across 18 test files, 95% code coverage
- 315 EPA v24142 integration tests parsing official test case outputs
- End-to-end mock pipeline tests (input generation → output parsing → visualization → postfile)
- `conftest.py` with shared fixtures for all test files
- Property-based testing with Hypothesis strategies for source types
- `ruff` linting (replaced flake8) with comprehensive rule set
- `.pre-commit-config.yaml` for automated lint on commit
- Performance benchmarks in `benchmarks/` directory

#### Documentation
- 7 Jupyter tutorial notebooks (Getting Started through Advanced Features)
- 7 example scripts (area sources, volume sources, line sources, BPIP, chemistry, deposition, end-to-end)
- MkDocs documentation site with Material theme and mkdocstrings API reference

### Changed
- **Package layout**: moved from flat root modules to `src/pyaermod/` package structure
- **Imports**: `from pyaermod.input_generator import ...` (was `from pyaermod_input_generator import ...`)
- **Python**: minimum version raised to 3.11 (was 3.8) — required by NumPy 2.1+, SciPy 1.14+, Pandas 2.3+
- Updated `setup.py` extras: added `[geo]`, `[gui]`, `[terrain]`, `[all]` dependency groups
- CI matrix runs Python 3.11, 3.12, 3.13 with GDAL system dependencies

## [0.1.0] - 2026-02-04

### Added
- **PointSource** with full stack parameters and building downwash (PRIME) support
- **Receptor grids**: Cartesian, polar, and discrete receptors
- **AERMOD input generation** for all 5 pathways (CO, SO, RE, ME, OU)
- **Output parser**: parse `.out` files to pandas DataFrames, extract metadata, find max concentrations
- **Visualization**: contour plots (matplotlib), interactive maps (folium)
- **Runner**: `AERMODRunner` with subprocess execution, `BatchRunner` for parallel processing
- Project setup: `setup.py`, MIT license, `.gitignore`

---

[Unreleased]: https://github.com/atmmod/pyaermod/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/atmmod/pyaermod/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/atmmod/pyaermod/releases/tag/v0.1.0

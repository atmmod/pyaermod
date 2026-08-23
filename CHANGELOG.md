# Changelog

All notable changes to PyAERMOD will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Regulatory-grade numeric regression** — `tests/test_real_aermod.py` now
  compares every AERTEST receptor against EPA's published reference plotfile
  (`tests/fixtures/epa_official/AERTEST_01H.PLT`) to a tight tolerance
  (rtol=1e-4), proving pyaermod drives the real AERMOD Fortran to reproduce
  EPA's own concentrations field-for-field — not merely that a run completes.
  A gfortran -O2 build reproduces all 144 receptors bit-for-bit.
- **Synthetic-DEM analytic regression for AERMAP** — `test_real_aermap.py`
  now builds a tiny USGS-format UTM DEM whose elevation is an exact tilted
  plane, runs it through the real AERMAP binary via `AERMAPRunner`, and
  asserts the extracted receptor elevations match the closed-form plane at
  on-node receptors (max deviation 0 with a gfortran build). Independent
  numeric ground truth, fully self-contained (no vendored DEM, no downloads).
- **Validated-version declarations** — `pyaermod.versions.VALIDATED_AERMOD_VERSIONS`
  / `VALIDATED_AERMET_VERSIONS` (`("26135", "24142")`, newest first; exported
  from the package API and `regulatory_parity`) state exactly which EPA
  releases the bit-exact AERTEST regression and the full test-suite parity
  have been run against. `AERMODOutputParser` now logs one warning when an
  output file was produced by a release outside that list.

### Changed
- **Vendored EPA fixtures refreshed to the v26135 archive**
  (`tests/fixtures/epa_official/`; EPA bundle of 2026-07-09, set
  `aermet26135_aermod26135`): `AERTEST_01H.PLT` (data rows byte-identical to
  the 24142 file; only the two banner lines differ), `aertest.inp`
  (whitespace and lower-case met filenames only), `AERMET2.SFC`/`.PFL`
  (values identical; AERMET 26135 writes four-digit years). `AERTEST.SUM`
  deliberately stays at 24142 (the 26135 summary prints `**` in its
  two-digit year column). `tests/test_real_aermod.py` passes bit-exact
  against a gfortran build of AERMOD v26135. Version notes in module
  docstrings, README and docs now say 26135 (AERMAP stays 24142 — EPA's
  current AERMAP source is still `aermap_source_code_24142`; the GRSM note
  records that v26135 drops its BETA flag while it remains non-DFAULT).
- The real-AERMOD test suite runs AERMOD once via a session-scoped fixture
  instead of re-invoking it per test.
- `real_aermod.yml` CI now also re-runs when the EPA reference plotfile or
  `aermod_outputs.py` change.
- **Hardened EPA real-binary CI against gaftp flakiness and version churn.**
  The real-binary workflows (`real_aermod`, `real_aermap`, `real_aermet`,
  `epa_parity`) now:
  - fetch EPA SCRAM archives via `scripts/fetch_epa_source.sh` — `curl --fail`,
    retries with backoff, and validation that the archive is a real zip before
    compiling (previously a rate-limited/error response from `gaftp.epa.gov`
    was silently saved as the "zip" and failed the job on `unzip`); and
  - derive the extracted source directory from the archive instead of pinning
    a name, so EPA's rename of the AERMOD source dir
    (`aermod_source_code_24142` → `aermod_source_v26135`) and AERMET's flat,
    Fortran-90 layout no longer break the compile. Verified locally: AERMOD
    v26135 still reproduces the vendored 24142 AERTEST reference bit-for-bit.

### Fixed
- **`AERMAPRunner.run` passed the input file *stem* instead of its full
  name** as AERMAP's command-line argument, so AERMAP could not locate the
  runstream and exited without processing (still returning code 0) — runs
  silently produced no output. Now passes the full filename.
- **Title round-trip** — `ControlPathway.to_aermod_input()` now normalizes
  `TITLEONE`/`TITLETWO` whitespace (collapsing leading/trailing/internal runs)
  to match how AERMOD's free-form, unquoted runstream parser reads titles back.
  Previously a title with surrounding or doubled spaces was emitted verbatim
  but re-read collapsed, so `write -> read` was not a fixed point. The
  property-based round-trip strategy is restricted to the representable
  (normalized, non-empty) title domain accordingly.

## [2.0.0] - 2026-05-04

The deprecation-cleanup major release. **Breaking changes** — read the
upgrade notes below before upgrading.

### Removed

- **Streamlit GUI** — the legacy `pyaermod.gui` module, the
  `pyaermod-gui` console script, the `_gui_runner.py` shim, and the
  full `tests/test_gui.py` (~920 lines) are gone. The replacement is
  the NiceGUI app shipped in v1.9 (`pyaermod-app` browser mode,
  `pyaermod-desktop` native window).
- **`gui` extra** as a Streamlit alias.
- **`gui-modern` / `gui-modern-desktop` extras** — renamed (see below).
- **`pyaermod-gui` console script.**

### Renamed

- **Extras**:
  - `gui-modern`        →  `gui`         (NiceGUI, browser mode)
  - `gui-modern-desktop` →  `gui-desktop` (NiceGUI + pywebview, native)
- The `all` extra now includes `nicegui` instead of Streamlit.

### Changed (breaking)

- **`AERMODProject.to_aermod_input()` and `.write()` validate by default.**
  The deprecation cycle landed in v1.5 (DeprecationWarning when
  `validate=` is omitted). v2.0 flips the default from `False` to `True`.
  Pass `validate=False` explicitly to skip validation if your tests or
  scripts construct intentionally-incomplete projects.

### Upgrade notes

Most users only need to change one thing:

```bash
# Old
pip install pyaermod[gui]
pyaermod-gui

# New
pip install pyaermod[gui]
pyaermod-app             # browser
pyaermod-desktop         # native window
```

If you scripted `to_aermod_input()` without `validate=`, your code now
runs the validator before generating the deck. To preserve the v1.x
behaviour:

```python
project.to_aermod_input(validate=False)
```

If you imported anything from `pyaermod.gui`, switch to
`pyaermod.gui_v2`. The public API (`AppState`, `save_project`,
`load_project`, page render functions) is documented in
[the gui_v2 reference](api/gui_v2.md).

## [1.9.0] - 2026-05-04

### Added — NiceGUI app + desktop bundles

The NiceGUI-based GUI v2 ships alongside the legacy Streamlit GUI for
the entire 1.9.x cycle. The Streamlit GUI is **deprecated** in favour
of NiceGUI; it will be removed in v2.0. Both are functional today.

#### Five-stage delivery

- **WP-1.9-A**: scaffold + project I/O. ``AppState`` per-session
  state dataclass, ``project_io.{save,load}_project`` JSON
  round-trip, ``app.{build_app,build_and_run}`` shell, fully
  rendered Project tab, placeholder banners for the other six tabs.
  New ``pyaermod-app`` and ``pyaermod-desktop`` console scripts.
- **WP-1.9-B**: Sources tab. Generic dataclass-field-walker emits
  the right widget per field annotation (str → input, float/int →
  number, bool → checkbox, vertices → textarea round-trip). One
  generic form covers all 10 source types.
- **WP-1.9-C**: Receptors + Meteorology tabs. Field-form helper
  extracted to ``pyaermod.gui_v2._form`` so every page is a thin
  list-of-fields shim. Receptors covers all 3 receptor types
  (Cartesian / Polar / Discrete); Meteorology splits primary vs.
  advanced fields under an expansion panel.
- **WP-1.9-D**: Output + Run + Results tabs. Run dispatches
  AERMOD via :class:`AERMODRunner`, captures stdout / stderr
  tails, and stamps :attr:`AppState.last_run_dir`. Results parses
  the .OUT file via :class:`AERMODOutputParser`, shows run info
  + sources + max concentrations + POSTFILE listing.
- **WP-1.9-E**: PyInstaller bundles for Win/Mac/Linux.
  ``packaging/pyaermod_desktop.spec`` plus a release-tag-triggered
  GitHub Actions workflow that builds the bundle on each OS and
  attaches the artifacts to the GitHub Release. ``docs/desktop.md``
  for end-user installation.

#### New extras

- ``pyaermod[gui-modern]`` — NiceGUI only (browser tab mode)
- ``pyaermod[gui-modern-desktop]`` — NiceGUI + pywebview (native
  desktop window)

#### New console scripts

- ``pyaermod-app`` — launches NiceGUI in a browser tab
- ``pyaermod-desktop`` — launches NiceGUI inside a pywebview window

### Changed

- Coverage gate continues at 95%. ``gui_v2/`` modules are excluded
  from coverage measurement (mirroring how ``gui.py`` was excluded
  for Streamlit) — UI render code is exercised end-to-end during
  manual QA, not unit-tested.

### Deprecated

- The Streamlit GUI (``pyaermod-gui`` / ``pyaermod.gui``) is
  deprecated in favour of NiceGUI. Functionality is unchanged in
  1.9.x; removal is planned for v2.0.

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

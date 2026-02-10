# PyAERMOD Development Continuation Notes

## Project State (as of Feb 2026)

PyAERMOD v0.2.0 — Python wrapper for EPA's AERMOD atmospheric dispersion model.

**Test suite**: 427 tests across 13 files, all passing.
**Latest commit**: Add RLINEXT/BUOYLINE/OPENPIT source types and terrain workflow pipeline

---

## What Was Done

### Session 1: Local Testing, Bug Fixes, BPIP Integration

1. **Local Testing & Bug Fixes** — Fixed pytest.ini, test_polar_grid, 4 Jupyter notebooks, pyaermod_aermap.py, pyaermod_aermet.py, example_area_sources.py. Created .gitignore.
2. **Test Suite Expansion (14 → 119 tests)** — Added 5 new test files: test_aermap.py (24), test_aermet.py (23), test_output_parser.py (25), test_runner.py (15), test_visualization.py (18).
3. **Building Downwash / BPIP Integration (119 → 154 tests)** — New pyaermod_bpip.py (Building, BPIPCalculator, BPIPResult), upgraded PointSource with 36-direction building fields, new tests/test_bpip.py (35 tests), new example_bpip.py.

### Session 2: Configuration Validation System (154 → 219 tests)

- **New `pyaermod_validator.py`**: `Validator` class with `ValidationError`, `ValidationResult` dataclasses. Validates all 5 AERMOD pathways:
  - ControlPathway: non-empty title, valid averaging periods, valid pollutant IDs, elevation units, half_life/decay_coefficient mutual exclusion
  - PointSource: stack_height > 0, stack_diameter > 0, stack_temp > 0 K, exit_velocity >= 0, emission_rate >= 0, building arrays length = 36
  - AreaSource/AreaCirc/AreaPoly/Volume/Line/RLine: dimensions > 0, emission_rate >= 0, release_height >= 0, zero-length line detection, minimum vertex counts
  - Cross-field: urban sources require URBANOPT, building height >= stack height (warning), duplicate source IDs
  - ReceptorPathway: at least one receptor, valid grid params, elevation units
  - MeteorologyPathway: non-empty file paths, optional disk check (check_files=True), partial date range detection
  - OutputPathway: table rank > 0 when enabled
- **New `tests/test_validator.py`**: 65 tests across 15 test classes
- **Modified `pyaermod_input_generator.py`**: `AERMODProject.to_aermod_input(validate=True, check_files=False)` — raises `ValueError` on validation errors, allows warnings through

### Session 3: AERMET Bug Fixes + POSTFILE Parser (219 → 258 tests)

Two workstreams developed in parallel:

#### AERMET Preprocessor Fixes
- **Modified `pyaermod_aermet.py`**: Fixed 5 bugs and added input validation:
  - Bug fix: QA pathway now generated in Stage 1 output (was defined but never used)
  - Bug fix: `time_zone=0` (UTC) no longer silently dropped in Stage 3 (changed truthiness check to `is not None`)
  - Bug fix: Partial location params (e.g. latitude without longitude) now raise `ValueError` via `__post_init__`
  - Bug fix: Non-12-element albedo/bowen/roughness arrays now raise `ValueError` (were silently skipped)
  - Bug fix: `elevation=0.0` and `anemometer_height` with `is not None` checks (were silently skipped when falsy)
  - Validation: `AERMETStation.__post_init__` validates lat (-90..90), lon (-180..180), anemometer_height > 0
  - Validation: `UpperAirStation.__post_init__` validates lat (-90..90), lon (-180..180)
- **Modified `tests/test_aermet.py`**: Added 14 new tests (23 → 37):
  - `TestWriteAERMETRunfile` (3 tests): file creation, content, executable permission
  - `TestAERMETEdgeCases` (11 tests): invalid coords, falsy time_zone, partial location, array lengths, QA pathway, zero elevation

#### POSTFILE Parser (new module)
- **New `pyaermod_postfile.py`**: Parses AERMOD POSTFILE formatted output files:
  - `PostfileHeader` dataclass: version, title, model_options, averaging_period, pollutant_id, source_group
  - `PostfileResult` dataclass: header + DataFrame (x, y, concentration, zelev, zhill, zflag, ave, grp, date)
    - Properties: `max_concentration`, `max_location`
    - Methods: `get_timestep(date)`, `get_receptor(x, y, tolerance)`, `get_max_by_receptor()`, `to_dataframe()`
  - `PostfileParser` class: reads formatted POSTFILE, parses `*`-prefixed headers and data lines (supports scientific notation)
  - `read_postfile(filepath)` convenience function
- **Modified `pyaermod_input_generator.py`**: Added POSTFILE keyword generation to `OutputPathway`:
  - New fields: `postfile`, `postfile_averaging`, `postfile_source_group`, `postfile_format`
  - Generates `POSTFILE` line in OU pathway when `postfile` is set
- **New `tests/test_postfile.py`**: 25 tests across 5 classes:
  - `TestPostfileHeader` (7): header field parsing
  - `TestPostfileParser` (5): basic parsing, empty files, missing files, multiple timesteps, scientific notation
  - `TestPostfileResult` (8): max values, timestep/receptor queries, aggregation, empty results
  - `TestReadPostfile` (1): convenience function
  - `TestOutputPathwayPostfile` (4): POSTFILE keyword generation in OutputPathway

### Session 4: Integrate AERMET and POSTFILE into Public API

- **Modified `pyaermod__init__.py`**: Wired AERMET and POSTFILE modules into the package's public API:
  - Added `from .aermet import` block: `AERMETStation`, `UpperAirStation`, `AERMETStage1`, `AERMETStage2`, `AERMETStage3`, `write_aermet_runfile`
  - Added `from .postfile import` block: `PostfileHeader`, `PostfileResult`, `PostfileParser`, `read_postfile`
  - Updated `__all__` with all 10 new exports (37 → 47 items)
  - Updated module docstring with POSTFILE usage example
  - Updated `print_info()` features list with AERMET and POSTFILE entries
- Follows existing relative import pattern (`.aermet`, `.postfile`)
- All 258 tests still passing

### Session 5: Geospatial Utilities + Streamlit GUI (258 → 335 tests)

Two new modules providing geospatial GIS integration and a web-based GUI:

#### Geospatial Utilities (new module)
- **New `pyaermod_geospatial.py`**: ~530 lines, library-first (usable without GUI):
  - `CoordinateTransformer` dataclass: bidirectional UTM ↔ WGS84 conversion via `pyproj`
    - `__init__(utm_zone, hemisphere, datum)` — creates `pyproj.Transformer` pair
    - `from_aermap_domain(domain)` — classmethod, reads `utm_zone`/`datum` from `AERMAPDomain`
    - `from_latlon(lat, lon)` — classmethod, auto-detects UTM zone from coordinates
    - `utm_to_latlon(x, y)`, `latlon_to_utm(lat, lon)` — single-point transforms
    - `transform_dataframe(df, to_latlon=True)` — batch adds lat/lon or UTM columns to DataFrames
    - `utm_crs`, `geographic_crs` properties for CRS access
  - `GeoDataFrameFactory`: converts pyaermod objects to GeoDataFrames:
    - `sources_to_geodataframe(sources)` — Point/LineString/Polygon geometries per source type (handles all 7 types: PointSource→Point, LineSource/RLineSource→LineString, AreaPolySource→Polygon, AreaCircSource→polygon approximation, AreaSource→rotated rectangle)
    - `receptors_to_geodataframe(receptors)` — expands CartesianGrid/PolarGrid into individual Points
    - `concentrations_to_geodataframe(df)`, `postfile_to_geodataframe(result)`
  - `ContourGenerator`: generates filled contour polygons using `scipy.griddata` + `matplotlib.contourf` → Shapely Polygons
    - `generate_contours(df, levels, grid_resolution)` → GeoDataFrame with Polygon geometries
    - `generate_contours_latlon(df)` — same but reprojected to EPSG:4326
    - Auto falls back from cubic to linear interpolation if >30% NaN
  - `RasterExporter`: exports concentration grids as single-band GeoTIFF via `rasterio`
    - `export_geotiff(df, output_path, resolution, method, nodata)` → Path
    - Auto-detects resolution from data spacing, creates parent dirs
  - `VectorExporter`: exports to GeoPackage, Shapefile, GeoJSON
    - `export_sources()`, `export_receptors()`, `export_concentrations(as_contours=True/False)`
    - `export_all(project, results, output_dir)` — batch export everything
  - Convenience functions: `utm_to_latlon()`, `latlon_to_utm()`, `export_concentration_geotiff()`, `export_concentration_shapefile()`
  - All dependencies optional with `try/except` + clear error messages
- **New `tests/test_geospatial.py`**: 52 tests across 7 classes:
  - `TestCoordinateTransformer` (13): init, validation, roundtrip, from_aermap_domain, from_latlon, DataFrame transform, CRS properties
  - `TestGeoDataFrameFactory` (15): all source types, receptors (cartesian/polar/discrete/mixed/empty), concentrations, CRS
  - `TestContourGenerator` (5): GeoDataFrame output, custom levels, CRS, lat/lon reprojection, geometry types
  - `TestRasterExporter` (5): file creation, CRS metadata, data range, custom resolution, parent dir creation
  - `TestVectorExporter` (7): GeoPackage, GeoJSON, Shapefile, points vs contours export, parent dir creation
  - `TestConvenienceFunctions` (6): utm_to_latlon, latlon_to_utm, roundtrip, one-liner GeoTIFF/Shapefile export

#### Streamlit GUI (new module)
- **New `pyaermod_gui.py`**: ~900 lines, 7-page Streamlit web application:
  - `SessionStateManager`: manages `AERMODProject` pathway objects in `st.session_state`, decomposes into individual pathways for piecewise editing, `get_project()` reassembles on demand, `get_transformer()` creates `CoordinateTransformer` from stored UTM settings
  - `MapEditor`: wraps `streamlit-folium` for interactive map-based editing
    - Multiple basemap layers (OpenStreetMap, Satellite, Terrain) with layer control
    - `add_sources_to_map()` — renders sources as markers/lines/polygons with popups
    - `add_receptors_to_map()` — renders receptor points (throttles to boundary rectangle above 2500 points)
    - `render_source_editor()` — returns clicked UTM coordinates for source placement
    - `render_concentration_map()` — heatmap layer + max concentration marker
  - `SourceFormFactory`: generates Streamlit forms for Point, Area, AreaCirc, Volume, Line, RLine sources
  - 7 GUI pages:
    - **Project Setup**: title, UTM zone/hemisphere/datum, map center lat/lon, pollutant type, averaging periods, terrain type
    - **Source Editor**: interactive map (click-to-place) in left column + dynamic source form in right column + source table with delete
    - **Receptor Editor**: tabbed interface (Cartesian Grid / Polar Grid / Discrete / CSV Import), map preview, receptor count metrics
    - **Meteorology**: file path config + file upload with save-to-disk
    - **Run AERMOD**: validation summary (errors/warnings), input file preview, executable path config, run with spinner, auto-parse results
    - **Results Viewer**: interactive map tab (heatmap), static plots tab (contours), statistics tab (max/mean/percentiles, top-10 receptors, exceedance analysis)
    - **Export**: GeoTIFF (resolution/interpolation controls), GeoPackage/Shapefile/GeoJSON (sources/receptors/concentrations as points or contours), CSV with lat/lon; all via `st.download_button`
  - Sidebar: navigation radio + workflow progress indicator (checkboxes for sources/receptors/met/results)
  - Streamlit imported lazily (`HAS_STREAMLIT` flag) so tests run without it installed
- **New `tests/test_gui.py`**: 25 tests across 5 classes:
  - `TestSessionStateManager` (6): initialize defaults, preserve existing, project assembly, transformer creation
  - `TestSourceFormDataConversion` (5): all source types produce valid AERMOD input
  - `TestMapEditorHelpers` (8): grid expansion (cartesian/polar), direction correctness, UTM fallback, transformer integration
  - `TestSourceFormFactory` (2): source type list validation
  - `TestWorkflowIntegration` (4): add/delete sources, add grids, full project assembly + input generation
  - Uses mock `streamlit` module injection (`sys.modules`) so tests pass without streamlit installed

#### Updates to Existing Files
- **Modified `setup.py`**: Version bumped to `0.2.0`. Added 3 new extras_require groups:
  - `[geo]`: pyproj, geopandas, rasterio, shapely, scipy
  - `[gui]`: streamlit, streamlit-folium, folium + all geo deps + matplotlib
  - `[all]`: union of viz + geo + gui
  - Added console script entry point: `pyaermod-gui=pyaermod_gui:main`
- **Modified `pyaermod__init__.py`**: Version bumped to `0.2.0`. Added conditional `try/except` import block for 9 geospatial symbols (`CoordinateTransformer`, `GeoDataFrameFactory`, `ContourGenerator`, `RasterExporter`, `VectorExporter`, `utm_to_latlon`, `latlon_to_utm`, `export_concentration_geotiff`, `export_concentration_shapefile`). Added `HAS_GEOSPATIAL` flag. Updated `__all__` (47 → 56 items). Updated `print_info()` features list with geospatial and GUI entries.

### Session 6: Additional Source Types + Terrain Workflow Pipeline (335 → 427 tests)

Two major feature areas: three new AERMOD source types and a terrain processing pipeline.

#### Additional Source Types (RLINEXT, BUOYLINE, OPENPIT)
- **Modified `pyaermod_input_generator.py`**: Added 4 new dataclasses (all keyword formats verified against AERMOD Fortran v24142 source):
  - `RLineExtSource`: Extended roadway with per-endpoint heights (XSB YSB ZSB XSE YSE ZSE on single LOCATION line), SRCPARAM (Qemis DCL Width InitSigmaZ), optional RBARRIER (1 or 2 barriers), optional RDEPRESS (Depth Wtop Wbottom)
  - `BuoyLineSegment`: Helper dataclass for individual BUOYLINE segments (source_id, coords, emission_rate, release_height)
  - `BuoyLineSource`: Buoyant line source group with per-segment LOCATION/SRCPARAM, BLPINPUT (6 average plume rise parameters), BLPGROUP keywords. Properties: `emission_rate` (sum), `number_of_lines`
  - `OpenPitSource`: Open pit mine/quarry with SRCPARAM (Qemis Hs Xinit Yinit Volume [Angle]). No APTS_CAP keyword (escape fraction computed internally by AERMOD). Property: `effective_depth`
  - Updated `SourcePathway.sources` Union type and `add_source()` to accept all new types
- **Modified `pyaermod_validator.py`**: Added 3 new validation methods with isinstance dispatch:
  - `_validate_rline_ext_source`: road_width > 0, init_sigma_z >= 0, emission_rate >= 0, zero-length line, barrier heights >= 0, depression depth <= 0, wtop >= 0, wbottom in [0, wtop]
  - `_validate_buoyline_source`: avg_buoyancy_parameter > 0, avg_line_length > 0, avg_building_height > 0, at least 1 segment, per-segment emission_rate >= 0, release_height in [0, 3000]
  - `_validate_openpit_source`: x/y_dimension > 0, pit_volume > 0, emission_rate >= 0, release_height >= 0, warning if release_height > effective_depth, warning if aspect ratio > 10
- **Modified `pyaermod_geospatial.py`**: Added geometry conversion for new source types:
  - RLineExtSource → LineString from (x_start, y_start) to (x_end, y_end)
  - BuoyLineSource → MultiLineString from line segments (imports MultiLineString from shapely)
  - OpenPitSource → Polygon rectangle from SW corner + dimensions with optional angle rotation
- **Modified `pyaermod_gui.py`**: Added GUI support for all 3 new types:
  - Updated `SourceFormFactory.SOURCE_TYPES` list (8 → 10 types)
  - Added `render_rlinext_source_form()`, `render_buoyline_source_form()`, `render_openpit_source_form()` static methods
  - Added dispatch branches in `page_source_editor()` and `MapEditor.add_sources_to_map()` (RLINEXT→purple, BUOYLINE→green, OPENPIT→brown)

#### Terrain Workflow Pipeline
- **New `pyaermod_terrain.py`**: ~725 lines, full DEM → AERMAP → elevations pipeline:
  - `DEMTileInfo` dataclass: title, download_url, format, size_bytes, bounds
  - `DEMDownloader`: queries USGS TNM API (`tnmaccess.nationalmap.gov/api/v1/products`) for NED 1/3 arc-second GeoTIFF tiles. Methods: `find_tiles(bounds)`, `download_tile(tile, output_dir)` with file caching, `download_dem(bounds, output_dir)`. Optional `requests` dependency with `_require_requests()` guard
  - `AERMAPRunResult` dataclass: success, input_file, return_code, runtime_seconds, output files, stdout/stderr, error_message
  - `AERMAPRunner`: mirrors AERMODRunner pattern exactly. `_find_or_set_executable()` + `subprocess.run()` with timeout
  - `AERMAPOutputParser`: parses AERMAP output (formats verified from Fortran FORMAT statements):
    - `parse_receptor_output(filepath)` → DataFrame (x, y, zelev, zhill): handles DISCCART (F12.2/F10.2) and GRIDCART ELEV/HILL rows (F8.1, 6 per line)
    - `parse_source_output(filepath)` → DataFrame (source_id, source_type, x, y, zelev): handles SO LOCATION (A12/A8/F12.2)
  - `TerrainProcessor`: high-level pipeline coordinator:
    - `create_aermap_project_from_aermod(project, dem_files, utm_zone, datum)` → AERMAPProject
    - `process(project, bounds, aermap_exe, ...)` → updated AERMODProject with receptor elevations (download → generate → run → parse → update)
    - `_update_receptor_elevations(project, rec_df)` — matches by coordinate proximity
  - `run_aermap()` convenience function
- **Modified `pyaermod_aermap.py`**: Added `AERMAPProject.from_aermod_project()` classmethod — extracts source/receptor coordinates from AERMODProject and builds AERMAP input with configurable buffer

#### Updates to Existing Files
- **Modified `pyaermod__init__.py`**: Added AERMAP imports (AERMAPProject, AERMAPDomain, AERMAPReceptor, AERMAPSource) as direct imports. Added terrain imports (DEMTileInfo, DEMDownloader, AERMAPRunner, AERMAPRunResult, AERMAPOutputParser, TerrainProcessor, run_aermap) as optional with `HAS_TERRAIN` flag. Updated `__all__` (56 → 63 items)
- **Modified `setup.py`**: Added `[terrain]` extras group (requests>=2.25.0). Added requests to `[all]` group

#### New Tests (92 new tests across 6 files)
- **Modified `tests/test_input_generator.py`**: Added `TestRLineExtSource` (6 tests), `TestBuoyLineSource` (3 tests), `TestOpenPitSource` (5 tests) — keyword correctness against Fortran FORMAT specs
- **Modified `tests/test_validator.py`**: Added `TestRLineExtSourceValidation` (8 tests), `TestBuoyLineSourceValidation` (7 tests), `TestOpenPitSourceValidation` (8 tests)
- **Modified `tests/test_geospatial.py`**: Added 5 geometry type tests (RLineExtSource→LineString, BuoyLineSource→MultiLineString, OpenPitSource→Polygon, rotated OpenPit, mixed count 7→10). Updated sample_sources fixture with 3 new types
- **Modified `tests/test_gui.py`**: Added 3 form data conversion tests, updated SOURCE_TYPES assertion (5→8+)
- **New `tests/test_terrain.py`**: ~310 lines, 22 tests:
  - `TestDEMTileInfo` (2): basic/full creation
  - `TestDEMDownloader` (6): mocked requests for find_tiles, download_tile cache, fresh download, pipeline
  - `TestAERMAPRunResult` (2): success/failure repr
  - `TestAERMAPRunner` (2): missing executable, missing input file
  - `TestAERMAPOutputParser` (7): DISCCART parsing, GRIDCART parsing, source output, missing files, empty output, comments
  - `TestTerrainProcessor` (5): create_aermap_project bridge, valid input generation, no coords error, elevation updates
  - `TestConvenienceFunction` (1): run_aermap missing exe
- **Modified `tests/test_integration.py`**: Added `TestAERMAPInputGeneration` (5 tests) and `TestAERMAPExecution` (1 test, requires aermap marker). Added `find_aermap()` helper for local AERMAP executable discovery

---

## Recommended Next Development Steps

### POSTFILE enhancements
- Unformatted (binary) POSTFILE support
- Time-series animation in GUI (POSTFILE timestep playback)

### GUI enhancements
- AERMET configuration page (Stage 1/2/3 forms, station map placement)
- Area (Circular) and Area (Polygon) source forms in GUI (currently missing form renderers)
- Building downwash / BPIP integration in source editor (building corner placement on map)
- Project save/load (serialize session state to JSON)
- Receptor elevation import from AERMAP results

### Packaging & deployment
- Release v0.2.0 to PyPI
- Docker image with all dependencies for one-command GUI launch
- Documentation: user guide for GUI, API reference for geospatial module

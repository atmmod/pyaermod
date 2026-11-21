# Changelog

All notable changes to PyAERMOD will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

A review of the whole codebase (2026-11-18) checked the library against
AERMOD's Fortran and the v24142 and v26135 binaries. The fixes below came
out of it; each has a test that failed before the fix.

### GUI (`pyaermod-app` and the browser app)

- **Unsaved work.** Import deck, Read deck and Recent files ask before
  replacing a modified project or stopping a run, as New and Open do.
  The browser asks before a tab with unsaved changes or a run in progress
  is closed or reloaded. In the browser app, a reload no longer clears
  "(modified)".
- **Editors.** The source and receptor editors stay open on Esc and on a
  click outside, with Cancel and Save. Vertex lists read `x y` as AERMOD
  writes it, as well as commas and semicolons, and list the lines they
  cannot read. An emptied required number, a blank or duplicate ID, an
  ID with a blank in it and an ID over 12 characters refuse Save. Each
  editor lists the validator's findings for its item.
- **Results** say when the project has changed since the run they show.
- **NAAQS comparison.** A value from a record shorter than the form needs
  reads "Not a design value", with the number of days, and every verdict
  says when the run added no background concentration.
- **Readiness.** The header, the step badges and Review & Run read one
  source and no longer disagree. A missing met file blocks the run before
  AERMOD starts. A station ID or year that differs from the surface file
  is a warning with a "Use the file's values" button.
- **Run files.** Each run writes its own deck and `.out` file
  (`pyaermod_gui_runN.inp`), so a reused working directory cannot show one
  run's results under another's name.
- **Large grids.** The plan view counts and samples grid points, so a
  mistyped grid count no longer freezes the server.
- A reloaded page rejoins the run in progress. Downloads and KMZ export
  run off the event loop. Temporary run folders are removed when no
  session lists the run.

### Documentation

- The documentation was checked against the code and shortened by about
  1,100 lines: wrong counts, option names and examples are corrected,
  and each topic is described in one place.

### Changed

- **Design values now differ in three cases** (decided by the maintainer,
  2026-11-21):
  - `o3_8hr_design_value` and `naaqs_compliance_report("O3", ...)` take
    1-hour values and form the daily maximum from running 8-hour means, as
    40 CFR 50 Appendix U 3(b)-(d) does: each mean is kept at its first
    hour and needs 6 of its 8 hours, a day takes the highest of the 17
    means starting 07:00 to 23:00, and a day needs 13 of the 17 or a value
    above the level. AERMOD's 8-HR block averages are still read, with a
    warning, and give a value that is never higher.
  - `pm10_24hr_design_value` ranks N+1 by default for N years of data
    (H3H, H4H, H5H for two, three and four years; AERMOD User's Guide
    3.2.16.2). It used H2H for two to four years, so those values are now
    lower. One year (H2H) and five years (H6H) are unchanged, and `rank=`
    still overrides.
  - The NAAQS table has the secondary annual SO2 standard (40 CFR 50.21,
    10 ppb, three-year average of annual means), marked
    `NAAQSStandard.primary = False`, and `naaqs_compliance_report` takes
    `"SO2_annual"`. `naaqs_averaging_periods` and the GUI's NAAQS
    comparison keep to primary standards.
- **Calm and missing hours in the ozone design value.** AERMOD writes a
  calm or missing hour to a 1-HR POSTFILE as 0.0 with no flag (read in
  the 26135 Fortran: `HRLOOP`, `POSTFL`), so those zeros lowered the
  running 8-hour means. `o3_8hr_design_value` and
  `naaqs_compliance_report("O3", ...)` take `calm_missing=`, a list of
  YYMMDDHH stamps, and the new `calm_and_missing_hours(surface_file)`
  reads them from the AERMET surface file. Each mean leaves those hours
  out and divides by the hours that remain, or by 6 if fewer remain, as
  AERMOD's own 8-hour average does. Without `calm_missing` the function
  warns.
- The annual PM2.5 mean stays the mean of every row of the year, and PM10
  stays compared with 150 µg/m³ unrounded; the docstrings say how
  Appendix N (quarterly means) and Appendix K (rounding to 10 µg/m³)
  differ.

- **Exported source geometry is different, because the old output was
  wrong.** GeoPackage, shapefile, GeoJSON and KMZ exports now draw AREA,
  OPENPIT, AREACIRC, AREAPOLY and line sources with the outline AERMOD
  builds (`pyaermod.footprints`). An AREA source was drawn centred on its
  location at twice its size; OPENPIT rotated the wrong way.
- **Decks are written with exact numbers.** Ratios, particle sizes and
  similar values are written as given (`0.2`, not `0.2000`), so a deck
  differs textually from one written by 2.3.0.
- `control.elevation_units` is written as `SO ELEVUNIT`. It used to be
  `CO ELEVUNIT`, which AERMOD rejects (E110).
- More than 100,000 receptors is a validator warning, not an error.
  AERMOD has no fixed limit. `RECEPTOR_GRID_HARD_LIMIT` keeps its name.
- A staging failure in `AERMODRunner.run()` returns a failed result
  instead of raising.
- An AERSURFACE run that writes no surface-characteristics file is a
  failure.
- `prime.gep_from_building` returns lower, correct GEP heights (it now
  uses `BPIPCalculator`'s sweep and the 65 m floor), so downwash is no
  longer written for a stack outside every building's influence zone.
- A BUOYLINE source with no segments raises `ValueError` on export.
- The regulatory profiles forbid `alpha`: AERMOD refuses ALPHA beside
  DFAULT.
- The CLI prints a one-line error and exits with code 2 for a missing
  file or an unknown profile, instead of a traceback.

### Added

- `utm_zone` and `northern_hemisphere` for `create_interactive_map` and
  `quick_map`; without a zone they warn that coordinates are used as
  given. `source_xy` for the profile, comparison-grid and animation
  plots.
- `AreaCircSource.initial_sigma_z` (Szinit).
- `OutputPathway.receptor_table_cards`, `max_table_cards` and
  `day_table_cards` keep RECTABLE, MAXTABLE and DAYTABLE cards that the
  `ALLAVE` form cannot express.
- `MeteorologyPathway.upper_air_start_year`, `surface_data_extra` and
  `upper_air_data_extra` keep the UAIRDATA year and the station name and
  coordinates.
- `read_toxxfile` reads AERMOD's unformatted TOXXFILE.
- `postfile.warn_hourly_mean_limitation`: an hourly POSTFILE does not say
  which hours were calm or missing, so a 24-hour or period mean computed
  from it can differ from AERMOD's.
- Validator warnings for background concentrations that no source group
  names (AERMOD then leaves them out of every result) and for pollutant
  IDs over 8 characters.

### Fixed

**Validator: accepts what AERMOD accepts.** All 160 EPA test decks the
reader parses now write with `validate=True`; 72 did not.

- Any POLLUTID; `BACKGROUND` and ID ranges as SRCGROUP members; sources
  and receptors that come from INCLUDED or EVALCART lines; a stack
  temperature of 0 (ambient) or below (offset from ambient); a stack
  height or diameter of 0; deposition METHOD_2; URBANOPT given by
  population or `urban_areas` alone.

**Validator: refuses what AERMOD refuses.**

- A stack temperature strictly between 0 and 200 K (E320); an urban
  population below 100 (E203); DFAULT with ALPHA, BETA, PSDCREDIT,
  FASTAREA, FASTALL, SCIM, NOURBTRAN, AREADPLT, HBP or TTRM2 (E204;
  NOSTD, NOCHKD and SCREEN warn, W206); OLM, PVMRM, GRSM, TTRM or TTRM2
  without ozone data (E283); gas and particle deposition on one source
  (E289); a source ID that is blank, has a blank in it, is over 12
  characters, is `BACKGROUND`, or repeats another ignoring case; and any
  card over 512 characters, which AERMOD truncates silently.
- The DFAULT and regulatory-profile checks tested `ControlPathway`
  attributes that never existed, so they never fired.
  `forbid_nondefault_flags` entries now name real switches (`alpha`,
  `beta`, `psd_credit`, or a MODELOPT token such as `NOSTD`); the older
  entry names are mapped.

**Deck writer.**

- `URBANSRC` names the urban area when there are several.
- BUOYLINE deposition cards name each segment; AERMOD stopped with a
  runtime error.
- File names containing blanks are quoted.
- `write()` validates before it opens the file and writes through a
  temporary file, so a refused write no longer empties an existing deck.

**Deck reader.**

- Fortran D exponents, lower-case pathways, keywords and IDs, and
  Latin-1 or BOM-marked files are read.
- A malformed line is kept in `unparsed_lines`; about 25 kinds were
  dropped silently.
- A read-and-rewrite no longer invents `NO2STACK 0.5`, adds output
  tables, drops LOW_WIND fields, or turns an incomplete GRIDCART into a
  10 x 10 grid.

**Runners.**

- A failed start no longer leaves the working-directory lock held and
  `aermod.inp` behind.
- AERSCREEN no longer reports success from an earlier run's files.
- A timeout in AERMET, AERSCREEN or AERSURFACE, and a cancel of a
  background AERMOD run, end the whole process tree.
- On Windows, a run queued behind another in the same directory waits
  instead of failing after about 10 s (not tested on Windows).

**Output parsers.**

- A multi-year ANNUAL binary POSTFILE is read as ANNUAL, one row per
  year.
- A row with an overflowed (`*****`) field is kept with NaN and a
  warning.
- The multi-year max-daily PLOTFILE is read with its rank and per-year
  columns.
- AERMOD's real `RANK-FILE`, `MAXI-FILE` and `SEASON/HOUR` headings and
  deposition PLOTFILEs are recognised.
- The `.out` parser fills the run date and time, averaging periods and
  met-data dates, keeps a FLAT-elevation source, and gives discrete polar
  receptors their x and y.

**Geospatial and plots.**

- Contour bands keep their holes and no longer overlap.
- A polar grid centred on a source is exported at that source.
- An interrupted DEM download no longer leaves a truncated tile that is
  reused; `find_tiles` pages through all results.
- 3-D, comparison and animation plots place values by x and y, not by
  row order. Wind rose bins are centred on the compass points.

**Post-processing and tools.**

- Design values: a NaN day no longer ranks as the highest; `PM25`,
  `PM-2.5`, `PB` and `LEAD` work in every NAAQS lookup; a calendar year
  whose data span under 350 days (a July-to-June met year, for example)
  now warns for every pollutant.
- `apply_deposition_defaults` leaves a project the GUI can save.
- `run_all_qaqc` accepts the records `read_surface_file` returns.
- `from_shapefile` matches column names truncated to 10 characters,
  warns about ignored columns and nulls, and refuses a longitude and
  latitude layer. `from_dxf` honours `z_as_height` for every entity and
  keeps a circle's area.
- `CartesianGrid.from_bounds` no longer loses a point to float
  truncation; `run_design` passes `build_fn` its own copy of the factors.
- `parse_igra_v2` reads an IGRA level with a missing (-9999) temperature,
  wind direction or wind speed as `None`. It raised `TypeError`.
- `pyaermod info` reports whether pyproj, geopandas, rasterio and requests
  are installed. It printed "yes" for geospatial and terrain whatever was
  installed.
- `AERMODVisualizer.plot_contours` titles a plot with the run's title.
  It used a job name, which AERMOD never prints, so the second title
  line of every real run read "Unknown".
- `AdvancedVisualizer.plot_time_series_animation` draws a frame with no
  positive concentration as a flat field. It raised "cannot convert float
  NaN to integer", for all-zero data and for one zero frame among others.
- `AdvancedVisualizer.plot_3d_surface` draws receptors that do not fill
  their bounding box (an L shape, a triangle, a grid with one receptor
  missing) over the cells they cover. Drawing or saving the figure raised
  a broadcast `ValueError`.
- Shapefile export of sources that mix points, lines and polygons. A
  shapefile holds one geometry type, and pyogrio raised `FeatureError`
  part way through the file. `VectorExporter.export_all` now writes one
  shapefile per kind (`sources_point.shp`, `sources_line.shp`,
  `sources_polygon.shp`) and returns them under the keys `sources_point`,
  `sources_line` and `sources_polygon`; the new
  `VectorExporter.export_sources_by_kind` does the same for a path of
  your choosing. `export_sources`, which writes one file, raises a
  `ValueError` that names both ways out. GeoPackage and GeoJSON exports
  are unchanged.

### Removed

- `requirements.txt`: nothing used it, and its version floors disagreed
  with `pyproject.toml`.
- `parse_aermod_output` no longer reads a report layout that AERMOD
  never writes (`Jobname:`, `*** SOURCE LOCATIONS ***`,
  `*** ANNUAL RESULTS ***` with an x/y/value table). Nothing in pyaermod
  produced it; it existed in hand-written test text and one notebook.
  AERMOD's own `.out` files are read as before. A file in which no source,
  receptor or result table is found now gives a `UserWarning` that says
  whether it looks like an AERMOD run that stopped early or like another
  kind of file, where it used to return empty results silently.

### Regulatory text and design values by met year

Corrections established by reading 40 CFR Part 50, Appendix W to Part 51
(the 2017 and 2024 revisions) and AERMOD's source (v23132, v24142,
v26135).

#### Added

- `EPA_APPENDIX_W_2024` (`EPA-AppendixW-2024`): the revision in force
  (89 FR 95034, effective March 21, 2025). It is the 2017 content plus
  GRSM as a Tier 3 NO2 technique.
- `RegulatoryProfile.advisories(project)`: notes that are not conflicts.
  OLM, PVMRM and GRSM give the Tier 3 note of Appendix W 4.2.3.4(e)
  (consultation with the EPA Regional Office and the reviewing
  authority). `pyaermod profile` prints them.
- Every design-value function and `naaqs_compliance_report` take
  `year_start`: `None` (the default) follows the met year, `"calendar"`
  forces calendar years, and a `(month, day)` pair names the boundary.
- `Validator` checks `CO LOW_WIND`: it needs ALPHA (E133), cannot run
  with DFAULT, and its fields are checked against AERMOD's ranges (E208,
  E380, E426).
- `Validator` reports a source with no in-stack NO2/NOx ratio under OLM,
  PVMRM, GRSM, TTRM or TTRM2 when the project has no default (E336), and
  an urban source without `urban_area_name` in a project with several
  urban areas.

#### Changed

- **Design values follow the met year.** Years were calendar years, so a
  July-to-June record was ranked as two partial years. A year now starts
  on the anniversary of the first date in the data, as AERMOD's does.
  Results for data that start on 1 January are unchanged.
- **Every Appendix W profile accepts ARM2**, the Tier 2 method in both
  revisions. The profiles used to flag it.
- **No profile accepts a low-wind option.** `allowed_low_wind` is empty,
  `check` flags a set `low_wind_option` and `apply` removes it. The 2017
  rule declined LOWWIND3, and AERMOD v18081 removed LOWWIND1, 2 and 3.
- `EPA_APPENDIX_W_2023` is documented as what it is: the 2017 rule as
  applied with AERMOD v23132. Appendix W had no 2023 revision.
  `EPA_APPENDIX_W_2023_BETA_METHODS` is `("GRSM",)`; PVMRM2 has not been
  an AERMOD option since v16216.
- A negative stack exit velocity is a validator warning, not an error:
  AERMOD warns (W325), sets 1.0E-5 m/s and runs.
- A function that averages hourly rows into 24-hour or annual means
  warns once, at the caller's line, that AERMOD omits calm and missing
  hours from the divisor.

#### Fixed

- NAAQS citations and labels; no level and no computed number changes.
  PM2.5 cites 40 CFR 50.20 and Appendix N (50.18 holds the superseded
  12.0 annual level). The PM10 form reads "expected exceedances <= 1 per
  year (3-yr avg)" and cites 50.6(a) and Appendix K. NO2 cites 50.11(a),
  (e) and (b), (f), and Appendix S.
- The PM10 H6H and H2H ranks are attributed to the AERMOD User's Guide
  (3.2.16.2), not to Appendix W Table 8-2, which is an emissions table.
- The profile notes: ADJ_U* is a regulatory AERMET option since the 2017
  rule; GRSM did not exist in 2017, was BETA in v22112 and v23132, and is
  regulatory from v24142.
- `arm2_preset` and `suggest_chemistry_for` no longer say ARM2 is not
  accepted by Appendix W, and `grsm_preset` no longer claims a
  preference for GRSM.

## [2.3.0] - 2026-11-18

### Added

- `tests/test_docs_examples.py` runs the Python examples of the
  quickstart and the student guide as a reader would paste them. A block
  that needs an AERMOD run or the reader's own files is marked in the
  page with `<!-- docs-example: skip (reason) -->`; every other block
  must run.
- A browser GUI on the documentation site, under `/app/`: the seven
  steps of `pyaermod-app` with nothing to install, no signed download and
  no server. pyaermod and AERMOD's WebAssembly build run in Pyodide in a
  Web Worker, so the page stays usable during a run and Cancel stops it.
  It opens and saves the same project files as `pyaermod-app`, imports
  decks, offers two sample met data sets (Albany 1988, Houston 1996) or
  uploaded AERMET files, and takes receptor and source elevations from
  AERMAP output or a CSV. Not for regulatory use. The page is in
  `webapp/`; `scripts/wasm/build_lite_site.sh` builds it beside the
  JupyterLite site, and `scripts/wasm/app_dev_server.py` serves it
  against CPython for development.
- `pyaermod.browser`: every operation of the browser GUI as one JSON
  entry point, `call(operation, arguments)`, which never raises.
- `pyaermod.gui_v2.readiness`: the Review & Run checklist without UI,
  shared by both GUIs. `pages/run.py` re-exports its names.
- `pathways.unquote_path` and `pathways.quote_path` (also importable from
  `pyaermod.input_reader`): a runstream file field as AERMOD opens it,
  and a file name as a runstream field.
- `pyaermod-app` takes `--host`, `--port` and `--no-browser`, so the GUI
  can be served from a container or on another port.
- `pyaermod gui` and `python -m pyaermod.gui_v2` start the GUI too, with
  the same options. `pyaermod info` reports whether the GUI and the
  desktop window can run.
- A conda-forge recipe (`conda-recipe/recipe.yaml`, v1 format) with two
  packages: `pyaermod`, and `pyaermod-gui`, which adds NiceGUI and
  matplotlib as `pip install "pyaermod[gui]"` does. It is not on
  conda-forge yet; `RELEASING.md` and `conda-recipe/README.md` say how
  to submit it after the next release.
- A GUI install check (`scripts/gui_install_smoke.py`,
  `.github/workflows/gui_install.yml`): the built wheel is installed
  with the `gui` extra into new environments on Linux, macOS and
  Windows, also through pipx and `uv tool`, and the GUI is started
  there. `publish.yml` runs it before uploading to PyPI.

### Changed

- Installation has one page, `docs/install.md`: the library and its
  extras, the GUI on its own (pipx, uv), conda's status, getting AERMOD
  and the other EPA programs, and what to do when an install fails. The
  README, the home page, the quickstart, the GUI guide and the desktop
  page keep a few lines and link to it.
- `docs/architecture.md`, a design proposal from before the code existed
  (it showed APIs that were never built), is now a short, accurate map
  of the code: the project model, reading and writing decks, validation,
  running, reading results, the GUIs and the browser path. The
  validation report, the design-value validation, the keyword audit and
  the benchmarks are grouped under Validation in the site's navigation.
- The quickstart is less than half as long: the five-minute example,
  running, reading and mapping the results, the common patterns and a
  figure, with the recipes the Ten Common AERMOD Jobs already run
  (deposition, NO2 chemistry, design values, terrain), the keyword lists
  (the keyword audit) and the feature list (the home page) linked rather
  than repeated. It now shows how to read an existing deck.
- The GUI guide, the browser page and the student guide show
  screenshots of the GUI at each step they describe, taken by
  `scripts/docs_screenshots.py` from `pyaermod-app` and the browser app
  with AERMOD replayed from a recorded run; `tests/test_docs_images.py`
  checks that every image a page shows exists and every screenshot is
  shown. The student guide's PDF embeds them. The GUI guide is shorter:
  the screenshots carry the layout, and the table of how the editors are
  built moved to `CONTRIBUTING.md`.
- The student guide is one page per part on the documentation site
  (concepts, setup, Tutorials 1 to 5, what's next, glossary) instead of
  one 10,000-word page; its old address shows the overview, and
  `docs/teaching/md_to_pdf.py` still builds the single PDF from the
  pages. Tutorial 5 no longer describes AERMET's Stage 2, which current
  AERMET does not have.
- `pyaermod[all]` includes `pywebview`, so it can run `pyaermod-desktop`.
- License metadata is the SPDX string `license = "MIT"` with
  `license-files`, and the build needs `setuptools>=77.0.3`; setuptools
  stops building the older table form in 2027.

### Removed

- The downloadable desktop apps. Releases no longer build or attach the
  PyInstaller bundles for macOS, Windows and Linux; the spec, the entry
  script and `.github/workflows/build_desktop.yml` are gone. The macOS
  bundle was unsigned, so Gatekeeper blocked it, and the frozen app
  re-launched itself in an endless chain of background processes. The
  GUI installs from PyPI (`pip install "pyaermod[gui]"`) instead; the
  `pyaermod-desktop` command and the `gui-desktop` extra are unchanged.
  `docs/desktop.md` says how to open a bundle from v1.9.0 or v2.0.0.

### Fixed

- The unformatted (binary) POSTFILE reader labelled every record with the
  first record's averaging period and called an ANNUAL record over five
  years "5-HR", so a multi-year ANNUAL average could pass for hourly data.
  Each record is now labelled on its own; `read_postfile(path,
  averaging_period="ANNUAL")` (or `"PERIOD"`) reads ANNUAL and PERIOD files
  as the text reader does, with the year or hour count in `date`; a record
  that cannot be told apart without it raises, and a file with one record
  per group warns. `regulatory_parity.score_postfile_pair` and
  `passes_parity` pass `averaging_period` through. Output readers read the
  `NaN` and `Infinity` gfortran writes. `add_background` accepts numpy
  scalars.
- `OZONEVAL`, `O3VALUES`, `NOXVALUE` and `NOX_VALS` refused D exponents
  (`3.0D1`, as in EPA's decks) and dropped a line whose value did not read,
  without keeping it. Values are read as AERMOD reads them, and a line
  that cannot be modelled is kept verbatim.
- `SO BACKGRND` with a temporal flag kept only the first value
  (`SEASON 1 2 3 4` became `SEASON 1`), and a line continuing a profile
  became an entry of its own. Every value is now read, a profile continued
  over several lines is one profile, and the writer splits a long profile
  over lines that repeat the flag, as AERMOD reads them.
  `BackgroundConcentration.period_values` and `sector_values` take a list
  for a flag with more than one value (`{"SEASON": [w, sp, su, f]}`).
- The validator read `BACKGRND`'s flag as an averaging period, so it
  refused a valid `SEASON` or `MONTH` profile and passed `{"24": 35.0}`,
  which AERMOD refuses. It now checks the flag against EMISFACT's table and
  the number of values each flag needs. The quickstart's example used the
  averaging-period form and now uses a flag.
- `BackgroundConcentration(uniform_value=...)` wrote `BACKGRND 5`, a
  value without a flag, which AERMOD stops on (E201, soset.f BACK_GRND).
  It is now written `BACKGRND ANNUAL 5`; a deck with the old form is read
  as the same uniform value, with a warning. The validator now refuses two
  flags for the whole domain or for one sector (E165), and checks
  `BGSECTOR` as AERMOD does: 2 to 6 directions, ascending, sectors at least
  30 degrees wide. It used to allow 12.
- The validator now refuses, as AERMOD does: a declared background sector
  without values (E238), sector IDs other than 1..N in `BGSECTOR` order
  (E203), and a modelled background that conflicts with `BACKGRND` or
  `BGSECTOR` lines kept verbatim from a deck (E203, E165), and more than one
  of the uniform, temporal and sector modes at once, which the writer
  would silently reduce to one. A non-numeric value in
  a `BACKGRND`, `O3VALUES` or `NOX_VALS` profile is a validation error
  instead of a `TypeError`.
- A deck whose sector background cannot be modelled whole (an unreadable
  `SECTn` line, `SECTn` lines without `BGSECTOR`, whole-domain values beside
  sectors) lost its `BGSECTOR` line on rewrite, which AERMOD rejects
  (E171). Every `BGSECTOR` and `BACKGRND` line is now kept verbatim in
  order. The whole-domain lines follow the same rule: if one of them
  cannot be modelled, all are kept verbatim instead of half a profile
  being modelled. Background profiles may be numpy arrays, pandas Series or
  ranges, and project files save them as lists.
- A sector's hourly background file (`BACKGRND SECTn HOURLY file`) was
  dropped from a deck without a trace. A deck that has one now keeps its
  `BGSECTOR` and `BACKGRND` lines verbatim, in order, and lists the file
  among the deck's input files.
- `PROFBASE 328 FEET` was read as 328 metres. The reader now converts
  feet to metres, as AERMOD does, and the writer keeps the precision a
  converted value needs. Another unit is read as metres with a warning
  (AERMOD's W203), a D exponent is accepted, and a value that is not a
  number is a `ValueError` naming the line (AERMOD's E208). `BGSECTOR`
  directions are written so they read back exactly. NaN, infinite and
  non-numeric background values and sector directions are validation
  errors.
- `add_background` matched a date-keyed background only when the frame's
  dates and the keys had the same type (`5010101` never matched
  `"05010101"`). Both sides are now compared as YYMMDDHH stamps, and a
  warning says how many dates have no background value, since those rows
  get none. Float date columns (from a CSV round trip) are read as the
  stamps they hold; they used to read 2005 as 1950.
- Fortran numbers in a deck are read by one helper that accepts D
  exponents and the E-free exponent form, and refuses `nan`, `inf` and
  underscores, which AERMOD does not read. A profile given as a one-shot
  iterator (a generator or `map`) is refused with a request for a list,
  instead of being used up by validation and written empty.
- The annual NO2 design value from `naaqs_compliance_report("NO2_annual",
  ...)` averaged the years' annual means. The standard is one calendar
  year's mean (40 CFR 50.11(e), Appendix S), so the design value is now
  the highest year's mean at each receptor;
  `no2_annual="multi_year_mean"` keeps the average for an agency that
  accepts it. Only years at least 75% complete count toward the highest
  year (hours for hourly values, as Appendix S counts them, days for
  daily values, months for MONTH); a year left
  out is named in a warning, and a receptor with no complete year gets the
  mean over the whole record, with a warning. AERMOD's ANNUAL POSTFILE
  value over several years, an average of the years' means, is refused
  rather than reported as one year; mixed averaging periods are refused. The
  GUIs' NAAQS check called AERMOD's multi-year ANNUAL value the NO2
  design value; it is now a lower bound, above the NAAQS only when it
  exceeds the level, and the note explaining it appears only then.
- AERMOD's WebAssembly build stopped with "Sequential record missing its
  terminator" when the surface file's last line had no line ending, which
  EPA's executable reads. AERMOD steps back over that line every hour, and
  Flang's runtime cannot. `wasm_runner.run` now ends the deck's surface
  and profile files with a newline before AERMOD starts.
- The browser GUI's source and receptor editors saved a field whose text
  did not parse (`abc` for a stack height) by keeping its old value
  without a word. The field now says what it needs under it, and Save
  refuses until it is corrected.
- The browser GUI called every run "Run 1". Runs are now numbered on the
  page: `browser.run` takes the run's `number`.
- The browser GUI's file list showed the runner's own files
  (`.pyaermod.lock`, the copy marker and AERMOD's captured console
  output). It now shows only the files you gave it and AERMOD's outputs.
- A surface file that had not been uploaded was listed twice on the
  browser GUI's Review & Run step, the second time as a warning naming
  the browser's internal folder. It is now listed once, and a surface file
  that cannot be read is named without that folder.
- In the browser GUI, ANNUAL averages with less than a year of met data
  only warned, and AERMOD then ran every hour before stopping with E480.
  The browser GUI now blocks that run (`pyaermod-app` still warns and lets
  you run), and a new project there starts with 1-hour and PERIOD
  averages, which both samples allow.
- Uploading a CSV of `x, y, elevation` never set a polar grid's
  elevations: polar grids were matched only by network name, which a CSV
  does not have. `TerrainProcessor` now matches them by position, within
  0.5 m of each receptor, as it does Cartesian grids.
- AERMOD's WebAssembly build left `ERRMSG.TMP` and `EVENT.TMP` in the
  working directory. EPA's executable deletes them as it ends; Flang's
  runtime does not. `wasm_runner.run` now deletes them after a run that
  ends normally.
- `read_aermod_input(..., sandbox=True)` judged a quoted path by its
  text, quotes included, so `SURFFILE "../../etc/passwd"` passed: `"..`
  is an ordinary directory name. AERMOD drops the quotes, and so does the
  sandbox now.
- A quoted file name with blanks (`SURFFILE "My Met/a.sfc"`) was split at
  the blank, and a kept line's name came back with two blanks in it. The
  reader keeps a quoted field whole, quotes included, so the deck is
  written back as it was read; anchoring a file into a folder with blanks
  quotes its full path.
- `SURFDATA 14735.0 1988.0`, which AERMOD runs, made the reader raise; a
  station id or year that is not a whole number is now an error naming
  the line.
- `wasm_runner.find_wasm_aermod(path)` fell back to `$PYAERMOD_AERMOD_WASM`
  or the installed `aermod_wasm` when `path` held no build. A path given
  is now the only place it looks.
- A trap inside the WebAssembly AERMOD skipped collecting the run's
  output, so the `.out` written up to the trap was lost. It is now a
  failed run whose error names the trap, with the output kept.
- The GUI's plan view no longer hangs the server when a source or
  receptor sits very far from the origin. A typo such as y = 1e18 made
  the tick loop add a 1 m step that the float could not resolve, so the
  loop never ended and the NiceGUI event loop froze for every connected
  user. Ticks are now counted by index and capped at 100 per axis, and a
  project with a coordinate beyond 1e8 m, or one that is not a number,
  gets a plan view that names those items instead of a plot.
- `RECTABLE` lines were read for their first rank field only, and only
  the last line counted, so `RECTABLE ALLAVE FIRST SECOND` imported as
  rank 1 and a deck with `RECTABLE 24 SECOND` before `RECTABLE 1 FIRST`
  lost rank 2. A PLOTFILE asking for SECOND then failed with E203 on the
  deck the GUI wrote back. The reader now takes every rank or range on
  every line, as AERMOD does (`ouset.f` OUHIGH).
- Documentation: the quickstart's EVENT and validator examples raised
  `TypeError`; the README's relative links broke on PyPI, where it is the
  project description; several pages counted 10 source types (there are
  13), gave unquoted `pip install pyaermod[...]` commands that zsh
  rejects, or described things that do not exist (a BPIP calculator in
  the GUI, `aermod` downloads on the releases page, a conda package).
  The student guide checks an install with `pyaermod info`, and its
  table of contents and two others now link to their headings.
- `pyaermod-app` and `pyaermod-desktop` without their extras stop with
  one line naming the install command (`pip install "pyaermod[gui]"`, or
  the conda package in a conda install) instead of a traceback.
- A port already in use is reported with the port and a suggestion to
  pass `--port`, instead of only uvicorn's log line.
- Material that still described the Streamlit GUI removed in v2.0, and
  so made the GUI look absent from the PyPI release: the teaching guide
  and refinery assignments (port 8501, the old page names), the teaching
  solution scripts (which imported `pyaermod.gui` or wrote project files
  the GUI could not open), the `Dockerfile` (it ran `streamlit run` on a
  file that no longer exists), the conda recipe's entry points, and the
  banner `pyaermod` prints.

Entries for 2.2.0 and earlier are in
[`CHANGELOG-archive.md`](CHANGELOG-archive.md).

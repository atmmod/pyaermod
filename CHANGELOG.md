# Changelog

All notable changes to PyAERMOD will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`ControlPathway.debug_options` writes `CO DEBUGOPT`.** AERMOD's debug
  output (the per-hour AREA.DBG of an open pit, PDEP.DAT and DEPOS.DBG of
  a deposition run, MODEL, METEOR, PRIME, ...) could only be had by
  patching the deck text. The field holds the fields of the line as
  AERMOD reads them, options each optionally followed by a file name
  (`["AREA", "DEPOS"]`, `["MODEL", "model.dbg"]`), and the writer puts
  the line after MODELOPT, which coset.f DEBOPT checks DEPOS against
  (E194 otherwise). `debug_files()` returns the file names, and
  `read_aermod_input(..., sandbox=True)` now checks them like every other
  path. The reader fills the field, pooling repeated DEBUGOPT cards as
  v26135 does and keeping the case of the file names, so `DEBUGOPT` no
  longer travels in `unparsed_lines`. One card takes at most 11 fields
  (DEBOPT's E202), so a longer list is written on several DEBUGOPT
  cards, split between options so each keeps its file name
  (`debug_cards()`); v26135 pools them, while v24142 takes one card
  only (E135), so there a list must fit in 11 fields. `pathways.DEBUG_OPTIONS`
  lists the 23 option names of v26135. The demonstration study's one-day DEBUGOPT
  AREA DEPOS deck is now written from the field, and on the v26135
  binary its AREA.DBG, PDEP.DAT, DEPOS.DBG and plot file are identical
  to those of the text-patched deck.
- **`ControlPathway.dry_depletion` and `.wet_depletion` write the
  MODELOPT depletion switches.** `True` writes DRYDPLT or WETDPLT, `False`
  NODRYDPLT or NOWETDPLT, and `None` (the default) neither, which leaves
  AERMOD's default of depletion on whenever the run has deposition
  inputs. The reader fills both from MODELOPT; a token that contradicts
  an earlier one (AERMOD's E149) stays in `extra_model_options`, so the
  rewritten deck fails the same way.
- **`ControlPathway.elevated_terrain`** says whether AERMOD runs the deck
  with elevated terrain: ELEV, the FLAT ELEV pair, and FLAT under DFAULT
  (which AERMOD overrides with W206) all are.
- **`pyaermod.psd`: particle size distributions for Method 1
  deposition.** Size data usually arrive as cumulative mass at a few
  cut points (AP-42's particle size multipliers `k`) or as a lognormal
  fit, while AERMOD wants one diameter, mass fraction and density per
  category. `bins_from_cut_points()` interpolates the cumulative mass
  linearly in `ln d` between cut points, `bins_from_lognormal()` bins a
  lognormal truncated to the edges, and `bins_from_cdf()` takes any
  cumulative distribution; each returns a `SizeDistribution` whose
  fractions sum to 1, which reports the mass left out below and above
  the edges and an `anchor_ratio` that scales an emission rate given
  for PM30 (or another anchor size) to the modelled mass. The anchor's
  mass is counted from the first edge, so the PM30 rate is spread over
  the bins, including the share below the first edge, while mass
  between the last edge and a larger anchor is lost.
  `SizeDistribution.to_deposition_params()` returns the
  `ParticleDepositionParams` a source's `particle_deposition` takes.
  Each bin's diameter is its mean-mass diameter
  `((d1³ + d1²d2 + d1d2² + d2³)/4)^(1/3)`, which reproduces EPA
  surfcoal's 0.63/1.85/3.88/7.77 µm from the edges 0/1/2.5/5/10, or its
  settling-equivalent diameter. `aerodynamic_to_stokes()` and
  `stokes_to_aerodynamic()` solve AERMOD's own settling equation
  (`VDP1` in `soset.f`, Stokes with a Cunningham slip factor), so a
  Stokes diameter at the real density settles exactly like the
  aerodynamic diameter at 1.0; the textbook `d_a/sqrt(rho)` settles
  11% too fast at 0.78 µm and 2.65 g/cm³. `settling_velocity()` matches
  the `Vg` of all 64 categories of a real v26135 run recorded with
  `DEBUGOPT DEPOS` in `tests/fixtures/psd/`. Documented in
  `docs/psd.md` and `docs/api/psd.md`.
- **The EPA build scripts build into a directory you choose and say what
  they built.** `scripts/build_aermod.sh`, `build_bpip.sh`,
  `build_aersurface.sh` and `build_aerscreen.sh` always wrote into the
  checkout's `bin/`, so a second build of the same source (a diagnostic
  variant, another compiler) could only be made by overwriting the
  first, and nothing recorded which binary a run had used. They now
  honour `BIN_DIR` (default `bin/`, unchanged; a relative path is taken
  from the directory the script is run in, although the scripts `cd`
  into scratch directories before linking) and print a build record
  after each link: the binary's path and SHA-256, the compiler's
  version, the compile and link flags actually passed to it (AERMET and
  the AERSURFACE link use their own flags, not `FFLAGS`, and the record
  says so), and for AERMOD the version token in its usage banner, kept
  whole so EPA's draft form (`D26135`) is not read as `26135`, and
  printed as `unknown (banner not found)` with a warning when the probe
  finds none rather than left out. `AERMOD_EXE_NAME` (default `aermod`)
  names the AERMOD binary, so a variant built from patched source can sit
  beside the regulatory one in the same `BIN_DIR`, and a build that
  replaces an existing binary says so and quotes the old file's SHA-256.
  After a build into another `BIN_DIR`, `build_aermod.sh` suggests the
  pytest command with that directory on `PATH` rather than
  `make test-binaries`, which always tests `./bin`. The shared code is the new
  `scripts/build_common.sh`. The hash identifies the
  binary, not the recipe: gfortran writes each source file's absolute
  path into the binary, so a build from another source directory, or
  from a downloaded archive (unpacked into a fresh temporary directory),
  hashes differently, and on macOS, where the linker signs the binary
  with its file name, so does the same build under another
  `AERMOD_EXE_NAME`. `tests/test_build_scripts.py` runs every script
  against a stand-in compiler and pins the default, the override, a
  relative override and the record; building AERMOD 26135 into a
  scratch `BIN_DIR` with gfortran 15.2 gave the same SHA-256 as the
  same source built into `bin/`, and banner 26135.
- `pyaermod.gui_v2.session.Session` and `SessionEvent`: the GUI's
  UI-free session, with one method per user operation (`new`,
  `open_json`, `save`, `save_as`, `save_as_download`, `add_source`,
  `update_source`, `delete_source`, the same for receptors,
  `set_control`, `validate`, `start_run`, `cancel_run`) and change events
  for observers.
- `pyaermod.gui_v2.project_io.project_to_json` and `project_from_json`,
  the project file format as text.
- **AERMET runstream options** the current AERMET reads:
  `AERMETStage1.upper_air_format` (`FSL`, `IGRA`, `6201FB`, `6201VB`),
  `upper_air_qa_file`, `upper_air_extract_file`, `message_file`,
  `surface_time_adjustment` and `upper_air_time_adjustment`, `*_audit`
  and `*_extra` keyword lists, and `onsite` (the new `OnsiteData`: READ
  and FORMAT records, THRESHOLD, OSHEIGHTS, DELTA_TEMP, OBS/HOUR);
  `AERMETStage3.site_char` records (`"f s albedo bowen z0"` or tuples)
  with `frequency` and `sectors`, `aersurf_file`, the secondary-site
  `secondary_*` fields, `asos_1min_file`, `methods`, `nws_height`,
  `extra_lines`, the input names `upper_air_qaout`, `surface_qaout` and
  `onsite_qaout`, and `with_inputs_from(stage1)`.
  `UpperAirStation.elevation` and `time_zone`. `AERMETRunResult` carries
  AERMET's parsed messages (`messages`, `errors`, a list of the new
  `AERMETMessage`), the REPORT summary counts (`message_counts`,
  `error_count`), `finished_successfully`, `report_file` and
  `message_file`; `parse_aermet_messages()` and `read_aermet_messages()`
  read a MESSAGES file. `OnsiteData`, `AERMETMessage`,
  `parse_aermet_messages` and `read_aermet_messages` are exported from
  `pyaermod` and `pyaermod.api`.
- **`AreaSource.initial_sigma_z`**, AERMOD's Szinit for an AREA source
  (m, default 0, AERMOD's own default). A nonzero value is written as the
  sixth SRCPARAM value, after an Angle of 0 when the source is not turned,
  because the fields are positional (`SRCPARAM id Aremis Relhgt Xinit
  Yinit Angle Szinit`, soset.f APARM). It lets an AREA source carry an
  initial vertical spread, as EPA's surfcoal roads do (3 m) or as an
  area standing in for an open pit needs (d_eff/4.3, the spread the
  OPENPIT algorithm itself starts from). The field comes last, so
  positional construction of the older fields is unchanged. An AREA deck
  with Szinit 23.26 m runs clean on v26135 and lowers the peak near the
  area as it should (`tests/test_real_aermod_source_writers.py`).
- **Hourly emission files (`SO HOUREMIS`) for AREA, AREACIRC, AREAPOLY,
  OPENPIT, VOLUME, LINE, RLINE and RLINEXT sources.** The new `pyaermod.hourly_emissions` module
  writes the records in the layout of EPA's `pset2pa.emi`
  (`SO HOUREMIS yy mm dd hh srcid qemis`; `write_hourly_emissions`,
  `hourly_emission_record`), one per source per met hour, hour by hour in
  the order the deck defines the sources, as aermod.f HRLOOP reads them
  (E342 otherwise); a missing rate writes the seven-field record AERMOD
  reads as zero emission (W344). `HourlyEmissionFile` is the
  `HOUREMIS file srcid ...` card, held in the new
  `SourcePathway.hourly_emissions` and written after every source card
  (HREMIS flags only sources already defined); a read deck's own card is
  still kept verbatim and written before it. The field is declared after
  `include_all_group`, so positional construction of `SourcePathway` is
  unchanged. `SourcePathway.add_hourly_emissions(path, hours, rates)`
  writes a file and adds its card for the source types whose record
  aermod.f HRQREAD reads with the rate alone, refusing POINT and BUOYLINE
  sources (their records need more fields each hour), SWPOINT (HRQREAD
  has no branch for it) and a source already on a card (E834). `ap42_wind_profile(sfc_file)` builds the hourly
  factor of AP-42 13.2.4 Eq. 1 ("profile W" of the demonstration study):
  `(clip(U, 0.6, 6.7)/2.2)**1.3` from the SFC reference wind, divided by
  its mean over the hours AERMOD models, with 1 for the hours it skips as
  missing: any hour metext.f CHKMSG flags (a missing wind speed or
  direction, temperature, Monin-Obukhov length, mixing height, u* or w*),
  not only a missing wind, and never a calm; `WindEmissionProfile` keeps
  the hours, speeds, raw and normalized factors, and counts of missing,
  calm and clipped hours for a run manifest. On the v26135 binary, a file
  whose every rate equals the SRCPARAM rate reproduces the constant-rate
  plot file exactly for OPENPIT, AREA, VOLUME, LINE, RLINE and RLINEXT
  sources, which AERMOD's source table lists as HOURLY; the wind-profile
  file runs clean and changes the result; and the profile's missing count
  equals the "Missing Hours Identified" AERMOD reports for an SFC file
  with a missing direction, temperature, mixing height and wind
  (`tests/test_real_aermod_source_writers.py`). `HourlyEmissionFile`,
  `WindEmissionProfile`, `ap42_wind_profile` and `write_hourly_emissions`
  are exported from `pyaermod.api`.
- **`output_types` for `read_postfile`, `PostfileParser` and
  `UnformattedPostfileParser`.** A binary POSTFILE does not say which
  output types its values are, so a file from a multi-type run needs the
  run's MODELOPT line (`output_types="DFAULT CONC DEPOS FLAT"`) or the type
  names (`["DEPOS", "WDEP"]`); order does not matter. Without it, a
  receptor count (`num_receptors`, or the length of `receptor_coords`)
  settles one type and four; two or three blocks of values per receptor
  raise a `ValueError` asking for `output_types`, because three blocks
  can be any of four sets of types. **A binary file with three blocks and
  `num_receptors` used to be read as CONC DDEP WDEP without being asked,
  which put DEPOS in `dry_depo` for three of those four sets; pass
  `has_deposition=True` (or `output_types`) to read CONC DDEP WDEP.** A
  `receptor_coords` list that does not match the record's receptor count
  is an error, where rows beyond it used to get coordinates `(i, 0)`. `PostfileResult.output_types` and `PostfileHeader.output_types`
  give the file's types, `PostfileResult.column_for("DDEP")` names the
  column of one, and `pyaermod.postfile.OUTPUT_TYPES` lists them in
  AERMOD's order. For a file without CONC, `max_concentration`,
  `max_location` and `get_max_by_receptor()` use its first output type.
- **The validator applies AERMOD v26135's remaining OPENPIT and Method 1
  checks, with AERMOD's message codes in each finding.** For OPENPIT
  `SRCPARAM` (`soset.f` OPARM): warnings for a zero emission rate, a
  release height above 200 m, a length or width below 1e-5 m or above
  2000 m, and a rotation angle beyond ±180° (W320), with W392 for an
  aspect ratio above 10 and E209 for negative values. For `PARTDIAM`/
  `MASSFRAX`/`PARTDENS`: an error for a mass fraction outside 0-1 (E332),
  a warning for a density of 0.1 g/cm³ or less (W334), and E240 and E334
  named on the existing count and density errors. Receptors that lie
  strictly inside an open pit draw a warning with their count and first
  coordinates: AERMOD skips them for that source and reports 0 there
  (`calc1.f` PITCALC). It raises no message code for them; it only lists
  them, marked OPENPIT, in the input summary's table of source-receptor
  pairs for which calculations may not be performed (`inpsum.f` CHKREC).
  Receptors on the edge are modelled. `regulatory_default=True` with
  `terrain_type` FLAT or FLATSRCS draws a warning: pyaermod writes FLAT
  with DFAULT, and AERMOD drops FLAT with W206 and runs in elevated
  terrain. `ControlPathway`'s defaults are exactly that pair, so a
  default project now carries this warning. So does a DFAULT deck read
  back with `read_aermod_input` when its `MODELOPT` names no terrain
  token: the reader maps that to FLAT, and pyaermod would write it back
  as `FLAT DFAULT`, although AERMOD runs the original deck in elevated
  terrain with no W206.
  `tests/test_validator_openpit_method1.py` checks every rule against
  real v26135 runs recorded in `tests/fixtures/validator_openpit/`.
- `AERMODResults.summaries` (every summary table of the `.out` file, in
  order) and `AERMODResults.deposition` (deposition tables by output type
  and averaging period); `ConcentrationResult.output_type`, `.title` (the
  table's own heading) and `.max_row`. Rows read from AERMOD's summary
  tables now also carry `rank`, `group`, `date`, `flag`, `value_text`,
  `zelev`, `zhill`, `zflag`, `receptor_type` and `grid_id`.
- `pyaermod.ensemble` (`docs/ensemble.md`): `run_design(rows,
  build_fn, root, n_workers)` runs one AERMOD run per design row, each in
  its own directory `root/runs/<run ID>`, `n_workers` at a time. It
  rewrites every output file name in the deck to a bare name in that
  directory (`rewrite_output_names`), including those in the lines
  `input_reader` keeps verbatim (a PLOTFILE ranked below FIRST or with a
  unit, a second POSTFILE, ERRORFIL) and the debug files of
  `ControlPathway.debug_options` (CO DEBUGOPT), so two runs on two
  workers write their own debug files. It links every file the
  deck reads in beside the deck: the met files, `INITFILE`, the
  `MULTYEAR` initial file, `OZONEFIL`, `NOX_FILE`, the `HOUREMIS` files
  of `SourcePathway.hourly_emissions`, and, from the lines kept
  verbatim, `HOUREMIS`, hourly `BACKGRND` and `INCLUDED` files. The run ID is the SHA-256 of
  the canonical JSON (`canonical_json`) of the row's factors, the
  binary's SHA-256, the SHA-256 of the met files and of the other input
  files, and `SCHEMA_VERSION` (2), so an edited emission file makes a new
  run. The manifest `root/manifest.json` (`EnsembleManifest`, a
  `RunManifest` of `EnsembleManifestEntry`) is saved as each run
  finishes. Each entry records:
  - the factors;
  - the deck's, the binary's, the met files' and the other input files'
    SHA-256;
  - AERMOD's version banner;
  - pyaermod's git commit;
  - the status, the warnings and the wall time.

  Running the same design again skips the runs that finished for the
  same deck and input files and makes the rest, so an interrupted design
  resumes where it stopped. `collect_plotfiles(root)` reads the PLOTFILEs
  of the successful runs of the latest `run_design` call on the root
  (listed in `root/design.json`; `DesignResult.collect_plotfiles()` for
  one result's runs) into one table, one row per receptor, keyed by run
  ID, and writes it as CSV and NumPy `.npz`. No new dependency is added.
  `DesignResult` reports `elapsed_seconds`, the runs' own `run_seconds`
  and their ratio, `concurrency`. On 2026-09-30 a four-run design of
  60-second runs took 240.9 s on one worker and 64.6 s on
  four, a speed-up of 3.7. `tests/test_ensemble.py` replays real
  v26135 runs recorded in `tests/fixtures/ensemble/`, and
  `tests/test_real_ensemble.py` repeats the design with the binary.

### Changed
- **`DepositionMethod` and the per-source `deposition_method` field are
  documented as inert.** AERMOD has no `METHOD` keyword, so neither has
  written anything since the writer stopped emitting the E105 card; both
  stay so existing code and saved projects load, and the docstring points
  to the fields that do what each member names (`GASDEPVD` / `GASDEPDF`
  CO keywords, the new depletion fields, `method_2`).
- **A uniform ELEV / HILL / FLAG row is written as `N*value`, exactly.**
  On any Cartesian or polar grid, with or without the run's terrain
  context, a row of one repeated value is now one `N*value` field
  (STODBL reads it as N copies) instead of N `8.1f` fields, and the value
  keeps every digit (`10.123456`, which `8.1f` wrote as `10.1`). The
  deck text of such grids changes, so text-keyed fixtures of them will
  too; rows of differing values keep the `8.1f` fields. The literal is
  plain fixed-point (`0.00001`, never `1e-05`): STODBL reads an exponent
  only after a decimal point, and `3*1e-05` was E208. The coordinate
  lists (GRIDCART XPNTS / YPNTS, GRIDPOLR DIST / DDIR) keep their ten
  significant digits but are no longer written in exponent form either
  (`1e+10` was E208 there too); their text is otherwise unchanged.
- GUI: in the source and receptor editors, Close now discards changes,
  and Add only adds the item on Save.
- GUI: in the browser, Save on a project that has no file on disk opens
  Save As.
- GUI: the app keeps one `Session` per browser tab. A duplicated tab, or
  a reload of the desktop window, gets its own copy.
- The GUI project file tags every nested object with `_type` and writes a
  dict whose keys are not all strings (background `sector_values`) as
  `{"_items": [[key, value], ...]}`. `save_format_version` stays 1, and
  files written before this change still open.
- **AERMET runs in two stages, and the pipeline returns two results.**
  AERMET 11 and later merge the data inside METPREP, so
  `run_aermet_pipeline(stage1, stage2, stage3)` ignores `stage2` (pass
  `None`; anything else warns) and returns the Stage 1 and METPREP
  results, with `stage` 1 and 3. `AERMETStage2` still constructs but is
  deprecated, and its `to_aermet_input()` raises `NotImplementedError`.
- **Breaking, for decks that AERMET rejected anyway:** a Stage 1 deck
  with upper air now needs `UpperAirStation.elevation` (AERMET stops with
  E05 without it) and a time zone (the surface station's is used when the
  upper-air one is unset); SCRAM and GHCN surface data need
  `surface_time_adjustment`, since no EPA deck shows which time basis
  AERMET reads them in; an unknown data format or a station ID with a
  blank raises `ValueError`. So does a Stage 1 SURFACE station ID that is
  not a number, normally the station's WBAN (`13874`, not `KATL`): Stage 1
  accepts `KATL`, but METPREP reads the ID back as an integer and stops
  with "Bad integer for item 1 in list input" (AERMET 24142 and 26135).
  A station ID longer than the 8 characters AERMET keeps also raises. The
  tutorials and the student guide now use WBAN numbers. The integer `messages` level is ignored with a
  `DeprecationWarning` (`message_file` names the MESSAGES file), and
  `AERMETStage3.merge_file` is ignored (METPREP's DATA keyword is
  obsolete). `AERMETStage3.num_sectors` other than 1 needs `site_char`
  records and `sectors`; the monthly `albedo`, `bowen` and `roughness`
  lists become one sector's FREQ_SECT ANNUAL or MONTHLY SITE_CHAR records.
  A METPREP deck using SUBNWS with SURFACE data (every NWS-only deck, by
  the default above) raises `ValueError` when neither `nws_height` nor
  `station` gives the anemometer height, since AERMET stops with `E72
  NWS_HGT KEYWORD MISSING`.
  `AERMETRunner.run_stage` names the deck on AERMET's command line (a deck
  outside `working_dir` is copied in under its own name) instead of
  copying it to `aermet.inp`.
- **A zero OPENPIT length or width is a warning, not an error.** AERMOD
  raises it to 1e-5 m with W320 and runs the deck; the validator now
  says so. A negative one is still an error (E209).
- `runner_utils.RunManifest.save` now writes the file in one step (a
  temporary file, then `os.replace`), so a process killed while saving
  leaves the previous manifest whole. `RunManifest.load` builds entries
  of the class attribute `entry_type`, so a subclass can store richer
  entries, and it ignores keys the entry type does not have.
- `BatchRunner.parameter_sweep` makes these changes:
  - **Return value (breaking).** It returns a `SweepResults`, a
    read-only mapping from each sweep value, in sweep order, to its
    result, instead of a `dict`. Looking a value up compares by `==`, so
    the values need not be hashable, and `keys()`, `items()` and
    `values()` are mapping views in sweep order. What worked on the dict
    and no longer does: `isinstance(results, dict)` is False,
    `results[value] = ...` raises `TypeError`, and `json.dumps(results)`
    raises `TypeError`. `dict(results)` gives the old dict back when the
    values are hashable.
  - **Deck names.** A value that is not a short plain number, string or
    boolean now names its deck by its position and a hash, as in
    `run_particle_deposition_001_3fa9c0d27e41.inp`. Two values whose
    text would give the same name are named the same way. Plain values
    keep names such as `run_emission_rate_0.5.inp`.
  - **Output names.** Each deck's output files are renamed
    `<deck stem>_<file name>`, in the sweep's directory.
  - **Equal values** are refused with `ValueError`.
  - **Outputs that would become one file** are refused with
    `ValueError` before any deck is written: two output files with the
    same file name in different directories (`annual/result.plt` and
    `hourly/result.plt`, compared ignoring case), which the sweep ran
    before. So is a renamed file name longer than AERMOD's 200
    characters (E291).

### Fixed
- **Receptor elevations were not written under elevated terrain, so
  AERMOD used zero with a warning.** `CartesianGrid.z_elev` and `.z_hill`
  were never written: every grid of an ELEV run (or a FLAT run under
  DFAULT, which AERMOD runs as ELEV) without AERMAP rows drew `RE W214
  ELEV Input Inconsistent With Option: Defaults Used`, and a grid given
  `grid_elevations` alone stopped with `E218 ... ZHILL`. A
  `DiscreteReceptor` with a zero hill height was written as `x y zelev`,
  which is `RE W228 Default(s) Used for Missing Parameters`. The RE
  writer now gets the run's terrain and flagpole options from
  `AERMODProject`: under elevated terrain a grid with neither ELEV nor
  HILL rows gets rows of `z_elev` and `z_hill`, and every DISCCART line
  carries `zelev zhill`. A grid given only one of the two row sets is
  written as given, so AERMOD still stops with E218, as it does for an
  EPA-style deck with ELEV rows and no HILL rows. On the v26135
  binary the demonstration study's decks and a DFAULT grid-plus-discrete
  deck set up with no W214 or W228, and the concentrations are unchanged
  where the values were zero.
- **Under FLAT with CO FLAGPOLE a discrete receptor's elevation was read
  as its flagpole height.** reset.f DISCAR reads `x y zflag` in that
  case, and the writer put `z_elev` in the third field: a receptor at
  100 m elevation sat on a 100 m flagpole. The writer now puts `z_flag`
  there, and the reader reads it back into `z_flag`. With FLAGPOLE, a
  `z_flag` of 0 is written as the FLAGPOLE height, the one AERMOD gives a
  receptor without its own; a Cartesian grid gets FLAG rows only from a
  non-zero `z_flag`. With `elevated=None`, `ReceptorPathway`,
  `CartesianGrid` and `DiscreteReceptor.to_aermod_input()` write the
  same fields as before (a uniform row now as `N*value`, see Changed),
  and FLAT runs without FLAGPOLE keep the old
  DISCCART line so the elevation reads back.
- **A bare `CO FLAGPOLE` was dropped by the reader.** AERMOD reads it as
  flagpole receptors with a default height of 0 (coset.f FLAGDF, W205),
  and EPA's surfcoal and four SNC decks use it. The reader stored `None`,
  the rewritten deck had no FLAGPOLE, and the third DISCCART field (the
  flagpole height) was then ignored with W229: on a one-day test deck
  the concentration at a receptor on a 3.4 m flagpole moved from 0.84925
  to 0.91634. The reader now stores `flag_pole_height=0.0`, and the
  rewrite reproduces the original run.
- **A MODELOPT with neither FLAT nor ELEV was read as FLAT.** coset.f
  MODOPT starts from elevated terrain and leaves it only for a FLAT
  token, so `MODELOPT CONC` runs with ELEV. The reader set
  `TerrainType.FLAT`, and the rewritten deck added FLAT and lost every
  receptor's elevation and hill height (W229): on a one-receptor test
  deck (zelev 80 m, zhill 150 m) the concentration moved from 0.00564
  to 0.03199. EPA's ten `bg_no2_*` test decks have no terrain token: on
  v26135 the rewrite of `bg_no2_arm2_ppb` gave a highest 1-hr value of
  272.06202 against the original's 205.74079. Such a deck now reads as
  `TerrainType.ELEVATED`, and that rewrite gives 205.74079.
- `pyaermod.gui_v2.session.Session` and `SessionEvent`: the GUI's
  UI-free session, with one method per user operation (`new`,
  `open_json`, `save`, `save_as`, `save_as_download`, `add_source`,
  `update_source`, `delete_source`, the same for receptors,
  `set_control`, `validate`, `start_run`, `cancel_run`) and change events
  for observers.
- `pyaermod.gui_v2.project_io.project_to_json` and `project_from_json`,
  the project file format as text.
- **`examples/deposition_modeling.py` calculated no deposition.** Its
  decks set only `OutputPathway.output_type`, which selects nothing in
  AERMOD, so the particle deck was `MODELOPT CONC FLAT DFAULT`, a
  concentration-only run; the two gas decks failed validation (GASDEPOS
  without ALPHA, E198) and were left empty, and `main()` printed the
  errors and carried on. The example now sets the `ControlPathway` flags
  that put DEPOS, DDEP and WDEP on MODELOPT, runs the gas decks under
  ALPHA without DFAULT with the GDSEASON/GDLANUSE site categories that
  gas dry deposition needs (E244 otherwise), gives every source of the
  mixed deck deposition inputs (E242 otherwise) and uses POLLUTID OTHER
  there (a 1-hour PM25 average is E363). Its FLAT particle deck leaves
  DFAULT off, because DFAULT overrides FLAT with ELEV (W206), which put
  its 50 m source base above receptors at 0 m. The example and the
  quickstart state that E242 applies whenever any source has deposition
  inputs, even with CONC alone, since depletion is then on by default
  (NODRYDPLT NOWETDPLT turn it off). It no longer passes
  `deposition_method`, which writes nothing. Its "(g/m2/s)" comment
  was wrong: AERMOD writes deposition in g/m², totalled over each
  averaging period, and g/m²/yr for ANNUAL (coset.f MODOPT; output.f
  PERAVE averages only CONC). The POSTFILE section now shows the
  columns `read_postfile` returns and recommends `FILEFORM EXP`, since
  the fixed format prints hourly fluxes as 0.00000. `main()` lets errors
  through. `docs/quickstart.md`, which told readers to set
  `output_type="DEPOS"`, now describes the MODELOPT flags and units.
  `tests/test_example_deposition.py` checks each deck's MODELOPT and
  runs all three through the real AERMOD binary (skipped without
  `aermod` on PATH; ANNUAL becomes PERIOD there because the met covers
  four days), failing on any warning beyond the placeholder
  SURFDATA/UAIRDATA ones and on a zero PERIOD maximum for any quantity
  on MODELOPT. Its met, `tests/fixtures/deposition_met/`, is four wet
  days (28.4 mm) of EPA's AERMET test case EX04 (Houston 1996) run with
  AERMET v26135; the vendored AERMET2 met has no precipitation, so wet
  deposition was 0 everywhere. The example's POSTFILE section gives the
  columns `read_postfile` returns for its decks' POSTFILEs, now that the
  reader labels them by output type (see the `read_postfile` entry
  below).
  deposition was 0 everywhere. The example's POSTFILE section says that
  `read_postfile` mislabels the columns of its own decks' POSTFILEs.
- **The output parser dropped short-term values that AERMOD flags for
  calm or missing hours.** AERMOD prints such a value with a `c`, `m` or
  `b` right after the number (`15.94753b`; FORMAT `F14.5,A1` in
  `output.f` PRTSUM), the parser read `15.94753b` as the number, and the
  row was skipped. When the highest value of a period was flagged, the
  parser reported a lower one as the maximum, and a period whose values
  were all flagged (every 24-hour value of a run with a calm hour each
  day) was missing from `concentrations`. The
  number is now read and the flag kept in the row's `flag` column.
  `AERMODOutputParser` now reads AERMOD's summary tables by their
  headings, so also:
  - a run without ANNUAL averages no longer reports an `ANNUAL` result
    (the word ANNUAL in warning W361, "Multiyear PERIOD/ANNUAL values for
    NO2/SO2 require MULTYEAR Opt", led to a copy of the PERIOD table), and
    an ANNUAL run no longer reports a `PERIOD` result;
  - deposition tables (`TOTAL DEPO`, `DRY DEPO`, `WET DEPO`) go to
    `AERMODResults.deposition`, in AERMOD's units (`g/m^2`), instead of
    being reported in `concentrations` as `ug/m^3`, and in a run with
    both, the concentration tables are the ones in `concentrations`;
  - a summary table that continues on later pages (more source groups
    than fit a page) is read to its end; ALLSRCS's PERIOD maximum is
    88881.24949 (group RLINEB2), not the 11819.89828 of the first page.
  `tests/test_output_parser_real_runs.py` pins each case against runs of
  the real binary recorded in `tests/fixtures/output_parser/`.
- **Runs that AERMOD aborted were reported as successful.** AERMOD
  exits with code 0 even after a fatal error, and `AERMODRunner.run`
  counted exit code 0 plus an `.out` file as success. A deck with
  `AVERTIME 1 ANNUAL` and four days of met data stops with
  `MX E480 ... Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave` and
  came back with `success=True`, and the GUI said "Run succeeded"; a
  met file that does not exist (`ME E500`, at setup) did the same.
  `success` now also requires AERMOD's own
  `*** AERMOD Finishes Successfully ***` line in the `.out` file and no
  fatal errors in its message summary. `run_batch`, `BatchRunner`,
  `pyaermod run` and `python -m pyaermod.runner` inherit the rule. **Code
  that relied on the old rule will now see those runs as failures, which
  they were.** The `error_message` of a failed run now names AERMOD's
  first fatal error, such as `E480 MAIN: Less than 1yr for MULTYEAR,
  MAXDCONT or ANNUAL Ave NUMYRS=0`, instead of a generic string.
  `AERMODRunResult` now carries the parsed messages (`messages`, a list
  of the new `AERMODMessage` with severity, pathway, code, line, routine,
  text and detail), AERMOD's totals (`message_counts`, `fatal_count`,
  `warning_count`, `informational_count`) and `finished_successfully`;
  `parse_aermod_messages()` reads the same list from any `.out` file.
  Counts come from AERMOD's "A Total of" lines because the lists stop at
  999 entries. `tests/test_runner_status.py` pins the rule against three
  runs of the real binary recorded in `tests/fixtures/runner/`, and
  `tests/test_real_aermod.py` repeats it against the binary itself; all
  53 `.out` files of EPA's v26135 reference set, written on Windows with
  CRLF line ends, read as successes with no fatal errors. That
  file's success check also looked for any `FINISHES SUCCESSFULLY`, which
  the `*** SETUP Finishes Successfully ***` line of a failed run
  satisfies; it now requires `AERMOD FINISHES SUCCESSFULLY`.
- **The AERMET deck writers produced decks AERMET 24142 and 26135 reject,
  and the AERMET runner reported those runs as successful.** For EPA's
  EX01 case the old `AERMETStage1` deck stops with six errors (`E01
  INVALID KEYWORD: ANEMHGT` and `ELEVATION`, two `E05 INVALID FORMAT FOR
  STATION COORDINATE` for the signed decimal LOCATION, `E05 -5 GMT TO LST`
  for the UTC offset, `E01 INVALID PATH QA`); `MESSAGES 2` opened a file
  named `2`; `AERMETStage2` wrote a MERGE stage AERMET 11+ no longer has;
  and `AERMETStage3` read no Stage 1 output and wrote `ALBEDO`, `BOWEN`
  and `ROUGHNESS`, which are not AERMET keywords. `AERMETRunner` called a
  run successful when AERMET exited 0 and printed no "FATAL", which AERMET
  never prints, so every one of those runs came back `success=True`. The
  writers now follow AERMET's Fortran: `LOCATION id 42.75N 73.8W adj elev`
  with the GMT-to-LST adjustment derived from the data format; DATA,
  EXTRACT, QAOUT and XDATES on each Stage 1 pathway; METPREP reading the
  Stage 1 QAOUT files and writing FREQ_SECT, SECTOR and SITE_CHAR (or
  AERSURF), METHOD and NWS_HGT. A METPREP deck with NWS surface data and
  no on-site data gets `METHOD REFLEVEL SUBNWS` unless `methods` already
  has a REFLEVEL record: AERMET 26135 stops with `E87 NWS DATA ONLY AND
  SUBNWS ACTION NOT INVOKED` without it (24142 did not check). The runner passes the deck as AERMET's
  argument and reports success only when AERMET prints `AERMET FINISHED
  SUCCESSFULLY` and neither its MESSAGES file nor its REPORT summary lists
  an error, reading AERMET's output with CRLF (Windows) or LF line endings
  alike; `error_message` names the first error, such as `UPPERAIR E30
  READ_FSL: SOUNDING IS NOT FSL FORMAT ...`. `run_aermet_pipeline`
  inherits the rule. pyaermod's decks for EPA's AERMET test cases EX01,
  EX04 (Houston) and Cordero reproduce EPA's 24142 `.SFC` and `.PFL` line
  for line on AERMET 24142, and the output of EPA's own decks on AERMET
  26135. `tests/test_aermet_status.py` pins the writers and the rule
  against six runs of the real AERMET 26135 recorded in
  `tests/fixtures/aermet/runs/`, among them a runstream AERMET cannot
  open, where it prints no banner, lists no error and exits 0; and
  `tests/test_real_aermet_binary.py` repeats them, and the EX04 and
  Cordero comparisons, against the binary itself (the Real AERMET
  workflow now runs it). `write_aermet_runfile` scripts pass the deck as
  an argument (AERMET never read standard input) and fail unless AERMET
  prints its success banner. The script runs AERMET in `output_path`,
  where the data files the deck names by relative path are looked up;
  it now writes both the deck and `output_path` (by default the directory
  it was written from) as absolute paths, so it does the same from any
  directory, but only on the machine and checkout that wrote it.
- **`AERMODRunner.run_batch` returned its results in the order the runs
  finished, not the order of the decks.** `zip(input_files, results)`
  paired decks with other decks' results whenever a later deck finished
  first; the 2026-09-29 demonstration pilot had to re-key its first batch
  by hand. `results[i]` now belongs to `input_files[i]` however the runs
  finish, and a run that raised in its worker carries its deck's
  absolute path like every other result. With `stop_on_error=True` the
  list also holds one result per deck: runs already under way when the
  batch stops are waited for and filed in their place (they used to be
  dropped, which shifted every later pair), and a deck never started
  gets `success=False` with "Not run: the batch stopped after an earlier
  run failed". The docstring and `docs/common-errors.md` now say that a
  script calling `run_batch` or `BatchRunner.parameter_sweep` on macOS or
  Windows must do so under `if __name__ == "__main__":`: those platforms
  start workers with `spawn`, and without the guard every run came back
  failed with "A process in the process pool was terminated abruptly".
  `tests/test_runner_batch.py` makes four decks finish in reverse order
  and checks the results come back in input order.
- **`resume_batch` counted runs as done that were not, and a timed-out
  run left the previous run's `.out` under the deck's name.**
  `resume_batch` called a deck done when the last 50 lines of its `.out`
  contained "FINISHES SUCCESSFULLY", which `*** SETUP Finishes
  Successfully ***` also matches, and it never asked whether the `.out`
  came from the current deck. On a timeout `AERMODRunner.run` skipped
  renaming `aermod.out`, so the partial output of the re-run stayed as
  `aermod.out` and the earlier, successful `<deck>.out` survived: the
  2026-09-29 defect verification re-ran an edited deck, the re-run timed
  out, and `resume_batch` still called it done. A run that wrote no
  `.out` at all was judged by the one an earlier run had left. Now
  `resume_batch` applies `AERMODRunner.run`'s own test (AERMOD's
  `*** AERMOD Finishes Successfully ***` line and no fatal error in the
  final message summary) and requires the `.out` to come from the deck
  as it is now: AERMOD copies the runstream to the top of the `.out`,
  and `resume_batch` compares that copy with the deck's text, so a deck
  written again with the same content stays done and an edited one does
  not, whatever the file times say. File times decide only what the copy
  cannot show: a deck with `NO ECHO`, and the files named on `INCLUDED`
  records, are stale when newer than the `.out`. `run` removes the deck's `.out`, `.err` and `.sum` and any
  leftover `aermod.out`, `.err` and `.sum` before it starts AERMOD, and
  keeps a timed-out run's partial output as `<deck>.out`, reported in
  `output_file`. **A timed-out or crashed re-run no longer leaves the
  earlier run's output in place.**
- **`AERMODRunner.run` deleted a deck named `aermod.inp`, EPA's default
  name.** It replaced `<working_dir>/aermod.inp` with a link to the deck,
  which was that same file, so the deck was deleted, the link pointed to
  itself, and the run failed with "AERMOD exited with code 0 but wrote no
  aermod.out". A deck already named `aermod.inp` in the working directory
  now runs in place and is left alone, as is a link named `aermod.inp`
  that points to the deck (the runner used to replace such a link and
  remove it after the run). **Running any other deck in a directory that
  holds a deck named `aermod.inp` deleted that deck, and the run then
  overwrote its `aermod.out`**; such a run now fails before it starts,
  with "The working directory ... already holds another deck named
  aermod.inp", and leaves both files alone. Give it its own
  `working_dir`, or rename the base deck. Where links cannot be made
  (Windows without the privilege), the copy the runner makes instead is
  marked by a `.pyaermod-aermod-inp.sha256` file beside it, so that a
  copy left behind when Python is killed mid-run is replaced by the next
  run rather than taken for a deck. With a `working_dir` apart from
  the deck, the link named only the deck's file, so it pointed to a file
  that did not exist there; it now holds the deck's path relative to the
  working directory.
- **A killed AERMOD run was reported as "AERMOD did not report
  success".** A run stopped by a signal (the pilot ended its slowest
  run, an area source, with SIGTERM) now reads "AERMOD was stopped by
  SIGTERM (signal 15) before it finished; its output ends where the run
  was cut off", and a timeout reads "Execution timed out after N
  seconds; AERMOD was stopped before it finished". The runner recordings
  in `tests/fixtures/runner/` gain a run killed with SIGTERM part way
  through, and the audit's E322 (OPENPIT release height above the pit's
  effective depth) and E140 (SRCGROUP inside a source block) decks, both
  of which AERMOD ends with exit code 0 and which the runner reports as
  failures.
- **GUI: Results now updates when a run finishes** (defect D2). The shell
  built every tab once per page load, so Results kept saying "No run yet"
  after a run. Results and the Run tab's status are now rebuilt from the
  session's run history.
- **GUI: New and Open show the project they load** (defect D3). Every
  widget stayed bound to the replaced project, so the screen kept the
  old values and later edits went to the discarded project; editing a
  row of the old table after New also crashed the server. Every step is
  now rebuilt from the session when the project is replaced.
- **GUI: Open works on NiceGUI 3** (defect D4) and sends the file as soon
  as it is chosen. A malformed project file is reported ("Load failed:
  ...") instead of raising.
- **GUI: Save As no longer writes to `/tmp`**, which does not exist on
  Windows. It downloads the file in the browser and asks where to save it
  through a native dialog in `pyaermod-desktop`.
- GUI: opening the Meteorology tab no longer marks the project modified,
  and neither does leaving a number field without editing it.
- GUI: a browser reload keeps the project and the last run.
- GUI: the "No sources yet" and "No receptors yet" messages now follow
  the list.
- The `pyaermod-desktop` PyInstaller bundle now starts from a launcher
  script (`packaging/desktop_entry.py`). It used to run
  `gui_v2/desktop.py` itself, whose relative imports fail when it is the
  entry script, so the frozen app could not start.
- **GUI project files kept only part of the project.** `project_io` rebuilt
  sources, receptors and the top level of each pathway, and left every
  nested object as a plain dict: a source's `particle_deposition` or
  `gas_deposition`, background sectors, event periods and the like. It
  also dropped the rest of `SourcePathway` (background, source groups,
  emission units, barriers), `AERMODProject.events` and
  `unparsed_lines`. A file pyaermod had written itself opened
  "successfully" and then failed at Run with "Could not generate deck":
  an open pit with size-resolved dry deposition could not survive a Save
  and an Open. Reading is now driven by the model's type annotations, so
  every nested object is rebuilt as its class, and every value is checked
  against the field it fills. Of the 79 AERMOD decks in the repository,
  4 survived a save and an open unchanged before; all 79 do now, field
  for field and deck for deck, and the fixture decks are pinned by
  `tests/test_gui_v2_project_io.py`.
- **A project file with a value of the wrong type is refused**, naming the
  file and the field ("Load failed: f.json:
  project.sources.sources[0].stack_height must be a number, not text
  'tall'"). Such a file used to load and then break the page, and, as
  the GUI now keeps the session across reloads, every reload of that tab.
  So is
  a source or receptor whose `_type` is unknown (it used to be dropped
  silently, and the next save lost it), an unknown enum member, a file
  that is not UTF-8 text, and a document nested too deeply. `load_project`
  and `project_from_json` raise `ValueError` naming the file for every
  malformed file; `{"project": []}` used to escape as `AttributeError`.
- **GUI number fields rounded the project's value to 4 decimals** when
  they lost focus, and wrote the rounded value back: tabbing through an
  open pit's emission rate of 1.5e-6 g/s/m² set it to 0.0. They now show
  and keep the exact value.
- GUI: a pollutant that AERMOD accepts but the Pollutant list does not
  name (TSP, PB, NOX ... from a saved file) is shown and kept; it used to
  stop the Project step from being built.
- GUI: a part of a page that cannot show the project now says so in
  place, and the rest of the page is built; one failing section used to
  leave every later step and the footer empty.
- GUI: Save reports a file that cannot be written ("Save failed: ...").
- **Saving no longer writes a project file that cannot be opened again.**
  `project_to_json` (and so `save_project` and every GUI Save) checks the
  project with the loader first and raises `ValueError` naming the field,
  such as "cannot save the project:
  project.sources.sources[0].emission_rate must be a number, not null"
  after a number box was emptied. The GUI reports "Save failed: ...",
  delivers no file and keeps the project marked modified; it used to say
  "Saved" and hand over a file that "Load failed" refused.
- **Numbers that are NaN or infinite are refused** when a project file is
  read or written. Python's `json` accepts `NaN` and `Infinity`; such a
  file loaded, the source editor could not open, and the deck AERMOD ran
  said `LOCATION PIT1 OPENPIT nan ...`.
- GUI: Open accepts a file whatever its name ends in. The file chooser
  filtered on `.json`, and a file it filtered out was dropped without a
  message; a project whose name lost its extension would not open.
- GUI: a Save As name with characters a browser rewrites (`"*:<>?|`) is
  cleaned the same way, so the header names the file the browser saved.
- GUI: a run whose runner raises an unexpected exception logs the
  traceback; a missing AERMOD binary is logged as a warning.
- **Integer fields reach the deck as integers.** The GUI's number boxes
  store `2020.0`; STARTEND dates typed on the Meteorology step made Run fail
  with "Unknown format code 'd' for object of type 'float'", and SURFDATA
  was written `14735.0  1988.0`. The deck is now written from the project
  as its file reads back (`project_io.check_project`), which turns whole
  floats in integer fields into integers and refuses a fraction by field
  name ("start_year must be a whole number, not 12.5"). Saved files get
  the integers too.
- **Whole numbers beyond `2**53` in size are refused** when a project file is read
  or written. A file with a coordinate of `2**64` loaded, then froze the tab:
  NiceGUI could not send the value to the browser, and every reload of the
  tab came back blank.
- Project files: a list used as the key of an integer-keyed dict (OZONEVAL
  sector values) is refused naming the field; it used to load and then
  break the deck writer. `save_project` creates no directory for a
  refused project and replaces an existing file atomically.
- GUI: cancelling Open while the file is still being sent no longer puts a
  `ClientDisconnect` traceback in the server log. Errors in the deck writer
  and in the project-file reader are logged with their traceback.
- **`AERSCREENRunResult` named files in a spelling AERSCREEN had not
  written, on macOS and Windows.** The runner found the log by checking
  `<stem>.log` before `aerscreen.log`; a case-insensitive filesystem
  answers yes to `AERSCREEN.log` when only `aerscreen.log` is there, so a
  default run reported `log_file` as `AERSCREEN.log` where Linux reported
  `aerscreen.log`. The output, log, max-concentration and restart files
  are now looked up in a listing of the working directory, exactly first
  and then ignoring case, and reported as spelled on disk. The result is
  the same on both kinds of filesystem, and on Linux an `.OUT` whose case
  differs from `output_file` is no longer reported missing.
- **`test_archive_is_the_whole_v26135_set` failed when the archive found
  was not v26135.** With only the pre-2026 `aermet_24142_aermod_24142`
  set unpacked (46 decks), the 53-deck check failed although every deck
  round-tripped. It now skips, naming the set it found, unless that set
  is AERMOD v26135's, which must still have all 53 decks.
- **AERMAP rejected every deck `AERMAPProject.to_aermap_input` wrote.**
  Run through EPA's AERMAP 24142 (the current release; AERMAP has no
  26135), the deck for one receptor, a grid and a source stopped at
  setup with 11 fatal errors: `TERRHGTS ELEVATED` (E203; AERMAP takes
  `EXTRACT` or `PROVIDED`), a four-field `DOMAINXY` that put the datum
  where the second corner goes (E200), no `ANCHORXY` and no `RUNORNOT`
  (E130, both mandatory), a receptor ID in the x field of `DISCCART`
  (E208), `GRIDCART` without its `STA`/`END` lines (E200), the `SO`
  pathway after `RE` (E120), and `RECOUTPUT`, `SRCOUTPUT` and
  `MSGOUTPUT`, which are not AERMAP keywords (E105; the files are
  `OU RECEPTOR` and `OU SOURCLOC`, and the messages always go to
  `<input stem>.out`). The writer now writes AERMAP's syntax, read from
  `aermap.f`: pathways in the order CO, SO, RE, OU; a six-field
  `ANCHORXY` (user x y, UTM x y, zone, datum code); `RUNORNOT RUN`; a
  six-field `DOMAINXY` only when a domain is set; `DISCCART x y [zelev]`;
  a `GRIDCART ... STA`/`XYINC`/`END` block; and `OU RECEPTOR` and
  `SOURCLOC`. The deck it writes for that case runs clean (0 fatal
  errors, 0 warnings) and gives back the analytic elevations of the
  planar test DEM; `tests/fixtures/aermap_runner/` records both runs.
  `TerrainProcessor.create_aermap_project_from_aermod` now calls
  `AERMAPProject.from_aermod_project` instead of keeping its own copy.
  **Changes to `AERMAPProject`:** `terrain_type` defaults to `"EXTRACT"`
  (was `"FLAT"`, which AERMAP also rejects) and `"ELEVATED"` is read as
  `"EXTRACT"`; under `"PROVIDED"` every receptor and source must carry
  its elevation, and `SOURCLOC` is left out because AERMAP writes no
  source elevations then. `datum` becomes AERMAP's code (`"NAD27"` 1,
  `"WGS72"` 2, `"WGS84"` 3, `"NAD83"` 4, or an integer 0 to 7). New
  fields `anchor_utm_x`/`anchor_utm_y` (the UTM point the anchor is tied
  to; default the anchor itself, i.e. user coordinates are UTM),
  `domain_x_min`/`domain_y_min`/`domain_x_max`/`domain_y_max` (the
  `DOMAINXY` corners; see the next entries for what `from_aermod_project`
  does with them) and `grid_y_spacing` (default `grid_spacing`), and a
  `dem_format` argument to `from_aermod_project` (default `"DEM"` when
  every file ends in `.dem`, else `"NED"`). `dem_format` must be `"NED"`
  or `"DEM"`, the formats AERMAP reads. `receptor_id` and `message_file`
  are kept but not written, since AERMAP has no receptor IDs and no
  message-file keyword. `to_aermap_input` raises `ValueError` for decks
  AERMAP would reject or misread: no anchor, no DEM file, no receptor
  and no source, a partial or inverted domain, an unknown datum or
  format, and a `PROVIDED` project with a missing elevation, a grid or
  no discrete receptor. A path with a space is quoted, as AERMAP's
  parser allows, and one over AERMAP's 200-character field raises.
- **`TerrainProcessor.process` left sources and receptor grids without
  elevations, and put line sources at the wrong point.**
  `AERMAPProject.from_aermod_project` wrote only sources with an
  `x_coord` or `x_start`, so AREAPOLY and BUOYLINE sources were left out
  of the deck and kept `base_elevation` 0 with no error; it wrote every
  source as a `POINT` at its first point, so an RLINE from node (18, 18)
  to (24, 24) of the planar test DEM got 190 m where AERMAP gives 205 m;
  and it wrote only the first Cartesian grid and no polar grid, so the
  others came back with no elevations. It now writes every source as the
  AERMAP type that places its elevation where AERMOD expects it (the
  AERMOD type where AERMAP 24142 has it, `SWPOINT` as `POINT`, `RLINEXT`
  as `RLINE`, an `AREAPOLY` at its first vertex, each BUOYLINE segment
  under its own ID), with both ends of a LINE, RLINE or BUOYLINE and a
  LINE's width, so AERMAP takes RLINE and BUOYLINE at the midpoint and
  LINE at the south-west corner of its equivalent area, as `SOLOCA`
  does; a source it cannot place raises `ValueError`. Every Cartesian
  grid (`XYINC` or `XPNTS`/`YPNTS`) and polar grid (`GDIR` or `DDIR`;
  one centred on a source is written with that source's coordinates)
  is written under its own name, and `process` fills in each one's
  `grid_elevations`/`grid_hills` or `elevations`/`hills` by name, each
  BUOYLINE segment's `base_elevation`, and the group's from its first
  segment. **API changes:** `AERMAPSource` gains `source_type` (default
  `"POINT"`), `x_end`, `y_end` and `width`; `AERMAPProject` gains
  `grids` (a list of `CartesianGrid`/`PolarGrid`), and
  `from_aermod_project` puts the AERMOD grids there instead of in the
  single-grid `grid_receptor` fields; `to_aermap_input` also raises for
  an unknown source type, a line source without its end (or a LINE
  without its width), a source ID over 12 or grid name over 8
  characters, a repeated grid name, and a polar grid centred on a source
  that is not a single-point source of the project.
  `AERMAPOutputParser.parse_receptor_output` now reads every network in
  the file (it used to merge the rows of every Cartesian grid into one
  and skip polar grids) and adds the columns `network`, `row` and `col`;
  `parse_source_output` now reads the elevation of a LINE, RLINE or
  BUOYLINE row from its last field (it read the end point's x).
  `tests/fixtures/aermap_runner/networks/` records AERMAP running the
  writer's deck with every network kind and source type.
- **A domain could silently cut distant hills out of the hill heights.**
  `from_aermod_project` always wrote a `DOMAINXY` of the project's extent
  plus `buffer` (1 km from `TerrainProcessor`, which offered no way to
  change it), and AERMAP ignores terrain outside the domain. On a flat
  100 m DEM with a 600 m node 1.8 km from the only receptor (a 28%
  slope, well over the 10% rule in `sub_calchc.f`), the receptor's hill
  height came out 100 m, where AERMAP searching the whole DEM gives
  600 m, and nothing warned. No domain is now written by default, so
  AERMAP searches the whole DEM, as it does on its own; `buffer`
  (`from_aermod_project`, now default `None`) and the new
  `domain_buffer` of `TerrainProcessor.process` and
  `create_aermap_project_from_aermod` ask for one, which must take in
  every such feature. The anchor is now the south-west corner of the
  project's extent itself.
- **No way to point AERMAP at the NADCON grid files.** A project whose
  datum differs from its DEM's (the default `"NAD83"` with NAD27 USGS
  `.dem` files) stopped with `OU E365 ... NAD Conversion Grid Files
  (*.las; *.los) Not Found`, and the only ways out were to change the
  datum. `AERMAPProject.nad_grids_dir`, and a `nad_grids_dir` argument
  to `from_aermod_project`, `TerrainProcessor.process` and
  `create_aermap_project_from_aermod`, write `CO NADGRIDS` with the
  trailing separator AERMAP needs (it opens the directory and the file
  name joined with nothing between them).
- **`regenerate.sh` in `tests/fixtures/aermap_runner/` failed on a
  relative path to `aermap`**, since it runs the binary from a scratch
  directory; it now makes the path absolute first. The teaching guide
  (`docs/teaching/refinery-assignments.md`) said to run
  `aermap < aermap_houston.inp`, which AERMAP ignores (it reads the file
  named on its command line, or `aermap.inp`); it now says
  `aermap aermap_houston.inp`.
- **AERMAP runs that failed were reported as successful.** AERMAP ends
  with a bare `STOP`, so it exits with code 0 after fatal errors, and
  `AERMAPRunner.run` counted exit code 0 as success. A domain that
  reaches past the DEM (`OU E310 ... CHKEXT: Domain Coordinate is NOT
  Inside a DEM File`) came back with `success=True` and empty receptor
  and source files, and `TerrainProcessor.process` went on to read them;
  the 11 setup errors of the old writer's deck did the same. `success`
  now also requires the message file AERMAP writes beside the input
  (`<input stem>.out`, which the runner now reports as `message_file`),
  its `*** AERMAP Finishes Successfully ***` line and no fatal error in
  its final message summary; a message file left by an earlier run is
  removed first, so it cannot vouch for this one. `run_aermap` and
  `TerrainProcessor.process`, which raises `RuntimeError` on a failed
  run, inherit the rule. **Code that relied on the old rule will now
  see those runs as failures, which they were.** A failed run's
  `error_message` names AERMAP's first fatal error, such as
  `OU E310 line 29 CHKEXT: Domain Coordinate is NOT Inside a DEM File.
  Pt.= 1 (and 3 more fatal error(s))`, instead of a generic string, and
  `AERMAPRunResult` gains `finished_successfully`, `fatal_count`,
  `warning_count` (AERMAP's own totals) and `fatal_errors`.
  `tests/test_aermap_runner_status.py` pins the rule against the runs
  recorded in `tests/fixtures/aermap_runner/`, and
  `tests/test_real_aermap.py` repeats it, and the writer's deck, against
  the binary on the planar DEM, including `TerrainProcessor.process`
  end to end and a `PROVIDED` run.
- **A source's `source_groups` wrote `SRCGROUP` among the source cards,
  which AERMOD rejects.** Every source writer put
  `SRCGROUP grp srcid` right after its own cards, so the next source's
  `LOCATION` and `SRCPARAM` came after a group card: two OPENPIT sources
  in one group through `source_groups=["PITS"]` stopped v26135's setup
  with `SO E140 ... Invalid Order of Keyword` (soset.f SOCARD admits no
  source card once a group is defined). A source naming group `ALL`, as
  `create_example_project()` and the examples do, wrote
  `SRCGROUP ALL srcid`, which is `SO E203` (SOGRP reads only
  BACKGROUND/NOBACKGROUND after ALL), so that deck failed setup even with
  one source. `SourcePathway.to_aermod_input()` now gathers every
  source's `source_groups` into the group block after all the sources:
  a group that also has a `SourceGroupDefinition` gets the members the
  definition does not already list on continuation cards written with
  it (AERMOD files a continuation under the last group defined, so the
  cards of one group stay together); other groups follow, ten IDs to a
  card; `ALL` adds nothing, because every source is in it; a BUOYLINE
  source contributes its segment IDs; and PSDCREDIT decks still write no
  SRCGROUP (E105). Group names and member IDs are matched in upper
  case, as AERMOD reads every card (aermod.f LWRUPR): `Pit` on one
  source and `PIT` on another are one group, written as one block
  (written apart with `ROAD` between them, AERMOD filed the second
  card's source under ROAD, with no message). The field and its meaning
  are unchanged, for all thirteen source classes, but a source's own
  `to_aermod_input()` no longer contains any SRCGROUP line. The
  two-OPENPIT deck, a one-source `ALL` deck and a mixed deck now run to
  completion on the v26135 binary, and the mixed-case deck gives the
  group table intended (`tests/test_real_aermod_source_writers.py` when
  `aermod` is on PATH).
- **`AreaSource` called Xinit and Yinit half-widths, and so did the
  teaching material.** AERMOD places an AREA source by its southwest
  corner and takes Xinit and Yinit as full side lengths, turning the
  rectangle clockwise about that corner (soset.f APARM builds the
  vertices that way). The field comments said "half-width", and the
  student guide (its walkthrough and its glossary), the refinery
  assignments' TANKS and LOADRK tables, the solutions to tutorials 4 and
  8, `examples/area_sources.py` and three cells of notebook 03 told users
  to enter half the real dimension, which gives a source a quarter of the
  intended area; tutorial 8's solution also put the north-south side in
  Xinit, and the notebook divided one emission by four times the area it
  modelled. The comments, docstring and material now describe full side
  lengths from the southwest corner, and the examples enter the
  dimensions they meant (the refinery's tank farm is 200 m east-west by
  150 m north-south, the 30,000 m2 its emission box already assumed). The written deck of
  any given `AreaSource` is unchanged. (`geospatial.sources_to_geodataframe`
  still draws an AREA as centred half-dimensions; that is left to a
  separate fix.)
- **`read_aermod_input` dropped an AREA source's Szinit and misread a
  square.** The reader stopped at the fifth SRCPARAM value, so EPA's
  surface coal mine roads (`... 73.2 3.0`) lost their Szinit of 3 m when
  a deck was read and written back; it now reads the sixth value into
  the new `initial_sigma_z`. A card with Xinit alone got a Yinit of
  10 m, where AERMOD makes the area square (APARM: Yinit = Xinit); it
  now does the same.
- **`read_postfile` mislabelled the columns of a POSTFILE from a run with
  more than one output type.** AERMOD writes one value per receptor for
  each output type on MODELOPT, in the order CONC, DEPOS, DDEP, WDEP
  (`POSTFL` in calc2.f, `PSTANN` and `PLOTFL` in output.f), and the text
  header names them (`AVERAGE CONC`, `TOTAL DEPO`, `DRY DEPO`,
  `WET DEPO`). The reader assumed any file with deposition was
  CONC DDEP WDEP. A two-type text file (`CONC DDEP`, `DEPOS WDEP` ...)
  was read as concentration only, with the second value taken as ZELEV
  and every later field shifted; a four-type file put DEPOS in
  `dry_depo` and DDEP in `wet_depo` and dropped WDEP. A PLOTFILE of highs
  at discrete receptors, whose NET ID is blank, came back with an empty
  `date` whatever its types; the date is now read, and padded to eight
  digits, because PLOTFL writes it as `I8` and a year below 10 lost its
  leading zero (`5010112` where the POSTFILE has `05010112`). A binary
  file with two or four types raised
  `Expected 3 values but record contains 6`. A text file written with
  `OU NOHEADER` does not begin with `*`, so it was taken for a binary
  file and read as an empty frame without an error; it is now recognised
  by its content, its number of value columns and whether it is a
  PLOTFILE of highs are read from its first row, and one with two or
  three value columns needs `output_types`. The text reader now takes
  the types from the column-label line (or the MODELING OPTIONS line, or
  the caller), so every one of the 15 sets of types, in 1-hour and PERIOD
  POSTFILEs and in PLOTFILEs, reads with one column per type:
  `concentration`, `total_depo`, `dry_depo`, `wet_depo`. **A file with
  DEPOS now has a `total_depo` column, and code that read `dry_depo` or
  `wet_depo` from such a file gets the values AERMOD labelled so. A file
  with several output types and no CONC (`DDEP WDEP`, `DEPOS DDEP WDEP`
  ...) has no `concentration` column: use `result.column_for("DDEP")`,
  or `result.column_for(result.output_types[0])` for its first type.**
  `regulatory_parity.score_postfile_pair` compares the `concentration`
  columns, so it now raises `KeyError` on such files where it used to
  score the first type under that name; single-type files and files with
  CONC score as before (keying it on the output type is part of WP-D16's
  deposition parity). A file with one output type keeps its values in
  `concentration`, and a CONC DDEP WDEP text file reads as before.
  `tests/test_postfile_types.py` pins
  this against real AERMOD v26135 runs of every set of types, recorded in
  `tests/fixtures/postfile_types/`, and checks each binary file against
  its text twin.
- **An OPENPIT release height above the pit's effective depth was only a
  warning.** AERMOD refuses such a deck at setup (`SO E322 ... Release
  Height Exceeds Effective Depth for OPENPIT`, `soset.f` OPARM), so the
  validator passed a deck that could not run and `project.write()` wrote
  it. It is now an error, and `write()` refuses the deck. The depth is
  computed as AERMOD does, with a dimension below 1e-5 m (zero included)
  raised to 1e-5 m.
- **The validator rejected more than 20 particle categories.** AERMOD
  has no such limit: `soset.f` sizes its particle arrays to the deck, and
  a 25-category OPENPIT deck runs to completion. The cap is gone.
- **The mass-fraction warning fired at 1% instead of AERMOD's 2%.**
  SRCQA warns (W330) only when the fractions sum below 0.98 or above
  1.02; a sum of 0.985 no longer draws a warning.
- **Particle diameters were checked only for being positive.** AERMOD
  refuses a diameter of 0.001 µm or less, or above 1000 µm (E335); the
  validator now does too. The particle checks test the values as the
  deck carries them: the writer rounds `PARTDIAM` and `PARTDENS` to 4
  significant figures and `MASSFRAX` to 6 decimals, so a 1000.4 µm
  diameter, written as 1000, is accepted as AERMOD accepts it, and a
  0.10004 g/cm³ density, written as 0.1, draws W334.
- **`BatchRunner.parameter_sweep` crashed on a size-distribution
  sweep, and its runs overwrote each other's results.** Over
  `particle_deposition` values it ran every deck, then stopped with
  `TypeError: unhashable type: 'ParticleDepositionParams'` while keying
  the results by value. It named each deck after the value's `str()`,
  which gave 124-character names full of brackets and commas. And every
  deck named the same PLOTFILE in the same directory, so only the last
  run's `pit.plt` was left: the 2026-09-29 audit's two-distribution
  sweep ended with one PLOTFILE for two runs. The fix is described under
  Changed. The sweep's decks still share one directory, whose lock lets
  one AERMOD run there at a time; `pyaermod.ensemble.run_design` runs
  them in parallel.

### Removed
- `pyaermod.gui_v2.state.AppState`, replaced by
  `pyaermod.gui_v2.session.Session`: `reset()` is now `new()`,
  `last_run_dir` is now `last_run.work_dir`, and `mark_dirty()` /
  `mark_clean()` are replaced by the operations that change or save the
  project. `pyaermod.gui_v2.state._empty_project()` is still importable.

## [2.2.0] - YYYY-MM-DD

<!-- YYYY-MM-DD is a placeholder: RELEASING.md sets it to the day the GitHub release is published. -->

The archival release the JAWMA manuscript cites. v2.1.0 was planned
after PR #9 and never tagged, so this section carries everything since
2.0.0: the validation of the regulatory math and file formats against
EPA's own programs (#9), the reader's four completeness tranches (#10,
#13, #14, #15) and the 53-deck round-trip guarantee (#14), the AERSCREEN
rescue (#11), and the release engineering itself. Three dataclasses
changed their fields incompatibly (`AERSURFACEConfig`,
`AERSCREENConfig`, `EventPeriod`) and `OutputPathway.max_file` is gone;
the upgrade notes are at the end of this section.

#### Validation evidence

What the release has been checked against, with the artifact each
number comes from:

| Check | Oracle | Result |
|---|---|---|
| EPA test-suite parity (`docs/validation.md`) | AERMOD v26135 built with gfortran, EPA reference set `aermet26135_aermod26135` | **142 / 142** POSTFILE comparisons within EPA's ±0.001 best-fit-slope margin |
| AERTEST regression (`tests/test_real_aermod.py`) | EPA's `AERTEST_01H.PLT` | all 144 receptors bit for bit |
| EPA deck round trip (`tests/test_epa_deck_roundtrip.py`, `tests/test_epa_source_roundtrip.py`) | the 53 decks of EPA's v26135 archive | **53 / 53** parse → write → re-parse with every pathway equal field for field, the keyword lines equal token for token, and every original line either modelled or kept in `unparsed_lines` |
| EPA deck acceptance (`tests/test_epa_deck_acceptance.py`) | AERMOD's own setup pass over the rewritten decks | 49 / 53 accepted clean; the four chained MULTYEAR years report the same E500 as EPA's original does without the previous year's save file |
| Rewritten decks against EPA's POSTFILEs (`tests/regulatory/test_epa_rewritten_so.py`) | EPA's reference POSTFILEs | fourteen decks with pyaermod's SO pathway and ten fully rewritten decks, all at slope 1.000000 |
| Keyword coverage (`docs/keyword-audit-v26135.md`) | the 115 keywords AERMOD v26135's `modules.f` dispatches | **115 / 115** handled and tested (104 with a field, 11 stored verbatim by documented decision), from 59 at v2.0.0 |
| AERSCREEN (`tests/test_aerscreen_known_answers.py`, `tests/test_real_aerscreen.py`) | EPA's `aerscreen_test_cases.zip` and the patched binary | all **22** restart decks reproduced byte for byte; **21** of the 22 cases (12 flat, through typed answers and through the restart file, and 9 terrain) reproduce EPA's `.OUT` line for line; the 22nd ships in EPA's archive as an OLM deck under a PVMRM name and cannot reproduce its own reference |
| BPIP-PRIME (`tests/test_bpip_known_answers.py`) | EPA's BPIP-PRIME, compiled from source | exact over 6,480 direction comparisons |
| AERSURFACE (`tests/test_real_aersurface.py`, `tests/test_aersurface_deck_acceptance.py`) | the binary and EPA's RDU reference | EPA's reference reproduced byte for byte; about 30 configurations through the setup pass |
| NAAQS design values (`tests/test_naaqs_rank_tables.py`, `tests/regulatory/test_epa_known_answers.py`) | 40 CFR 50 appendices N, S and T; EPA's `.PLT`, `DA1`–`DA8` and `.SUM` files | exact, no tolerance |
| Runner overhead and batch throughput (`docs/benchmarks.md`) | the same AERMOD binary called directly with `subprocess` | the numbers, and the machines they were measured on, are on that page |

### Added
- **`CITATION.cff`** (Citation File Format 1.2.0) with the metadata the
  archival release needs: title, author, licence, repository, version
  and a `preferred-citation` stub for the JAWMA paper. `date-released`
  and `doi` are placeholders the release fills in (Zenodo mints the DOI
  only after the GitHub release is published; `RELEASING.md` says where
  to paste it). `tests/test_citation.py` ties its version to
  `pyproject.toml` and `pyaermod.__version__` and validates the file
  with `cffconvert` when it is installed, which the 3.12 CI leg does.
  `README.md` and the docs index carry the citation.
- **AERMOD run benchmarks** (`benchmarks/bench_aermod_runs.py`,
  `python benchmarks/run_benchmarks.py --aermod`): the wall time of one
  run of EPA's `aertest` case driven through `pyaermod.runner` against
  the same binary called directly with `subprocess`, interleaved and
  reported as medians and quartiles, and the throughput of a batch of
  runs through `AERMODRunner.run_batch` at 1, 2, 4 and all-core workers.
  Both skip with a reason when `bin/aermod` or the case is missing;
  `--require-aermod` makes that an error. The `Benchmarks` workflow's
  manual dispatch builds AERMOD from EPA's source, unpacks the case from
  EPA's test-case archive and runs them on a clean runner. The numbers,
  from that job and from the session that wrote it, are on the new
  `docs/benchmarks.md` page.
- **Release notes** for this version under `docs/release-notes/`, and a
  "Reproducing the validation report" section in `docs/validation.md`
  (emitted by `scripts/run_epa_parity.py` too, so it survives
  regeneration) with the commands that rebuild the parity report, the
  keyword audit and the benchmarks from a clean checkout of the tag.
- **AERSCREEN drives the real binary, and EPA's own test cases prove
  it.** AERSCREEN has no input deck: it is interactive, and it restarts
  from the `**` header of its own output file. `pyaermod.aerscreen` now
  produces both -- `AERSCREENConfig.to_stdin_answers()` gives the answers
  in the order `AERSCREEN.FOR` asks them, `to_aerscreen_input()` writes
  the restart header in `makeinput`'s exact column layout, and
  `from_aerscreen_input()` parses it back -- and `AERSCREENRunner` feeds
  either to the binary, staging the programs AERSCREEN spawns (AERMOD,
  MAKEMET, BPIP-PRIME, AERMAP; it checks for `AERMOD.EXE`-style markers
  and calls the lower-case names through the shell), the auxiliary
  input files a run names, and `DEMlist.txt` for terrain runs.
  `parse_aerscreen_output()` reads the `MAXIMUM IMPACT SUMMARY` and the
  concentration-by-distance table of the `.OUT` file.
  - `scripts/build_aerscreen.sh` fetches EPA's `aerscreen_code.zip` and
    `makemet_code.zip`, applies `scripts/patches/aerscreen_21112.patch`
    and compiles both into `./bin`. The patch is what gfortran needs:
    the `\` non-advancing edit descriptor of every prompt FORMAT (an
    Intel/Microsoft extension that even `-fdec` rejects) becomes `$`;
    the file names AERSCREEN opens get the case AERMOD and AERMAP write
    them with on Linux; the NAD-grid path uses `/`; and a `-0.00`
    building adjustment from BPIP no longer overflows the 3-character
    field `makeformat` gives it (which handed AERMOD `36****`). Applied
    with `patch(1)` so a source change on EPA's side fails the build
    loudly instead of silently building something else.
  - `tests/test_aerscreen_known_answers.py` round-trips all 22 restart
    decks of EPA's `aerscreen_test_cases.zip` (every source type, with
    and without downwash, terrain, NO2 chemistry and the u* adjustment)
    through the parser and the writer and requires the header back **byte
    for byte**; the 22 `.OUT` files pin the output parser. The decks and
    outputs are vendored under `tests/fixtures/epa_aerscreen`, so this
    runs on every CI leg.
  - `tests/test_real_aerscreen.py` drives every EPA case through the
    built binaries, by typing the answers and by handing over the restart
    file, and compares the `.OUT` with EPA's line for line (run
    timestamps aside): all 12 flat cases through both interfaces and all
    9 terrain cases (AERMAP over EPA's NED and DEM rasters) reproduce
    EPA's outputs, one fumigation distance in the point downwash case
    differing in its last digit. `.github/workflows/real_aerscreen.yml`
    does this in CI, weekly and on pull requests that touch the
    AERSCREEN code.
  - The restart reader, it turns out, keeps a title only up to its first
    comma and upper-cases it; the restart-file tests allow for that and
    the docstrings say so.
- **Every v26135 runstream keyword is now read into a field (WP-5).** The
  audit's "Unhandled (kept verbatim)" list -- the EV pathway, six ME and
  five OU keywords, and the CO/SO leftovers -- is empty; the only lines
  that still travel in `unparsed_lines` are the ones with no model by
  design (EMISFACT, HOUREMIS, INCLUDED, SITEDATA, EVALCART, DISCPOLR,
  ERRORFIL, DEBUGOPT, NO2EQUIL, BACKUNIT) and malformed forms. Field
  layouts come from `evset.f`, `meset.f`, `ouset.f`, `coset.f` and
  `soset.f` through `scripts/keyword_oracle.py`; probe decks 20-30 under
  `scripts/oracle_decks/` record what AERMOD v26135 said about each form,
  including the first guesses it rejected.
  - **EV pathway** (`EventPeriod`, `EventLocation`, `EventPathway`) in the
    layout AERMOD writes itself for `EVENTFIL` (`EVENTPER name aveper
    grpid date conc`, `EVENTLOC name XR= x YR= y zelev [zhill [zflag]]` or
    `RNG=`/`DIR=`); `AERMODProject.event_processing` and the `CO SO ME EV
    OU` event-deck layout with `OutputPathway.event_output` (EVENTOUT);
    `ControlPathway.eventfil_option`; `read_event_output()` for the
    per-event source contributions of an EVENT run's `.out`.
  - **ME**: `MeteorologyPathway.day_ranges` (DAYRANGE), `.num_years`
    (NUMYEARS), `.wind_speed_categories` (WINDCATS), `.scim`
    (`ScimOptions`, the three SCIMBYHR forms) and `.turbulence_option`
    (the nine NOTURB/NOSA/NOSW keywords).
  - **OU**: `OutputPathway.no_header` (NOHEADER), `.rank_files`
    (`RankFile`), `.season_hour_files` (`SeasonHourFile`), `.eval_files`
    (`EvalFile`), `.toxx_files` (`ToxxFile`); the file entries read their
    output through the existing `aermod_outputs` readers.
  - **CO**: `ControlPathway.arm2_ratios` (ARMRATIO), `.awma_downwash`
    (AWMADWNW), `.ord_downwash` (ORD_DWNW), `.aircraft_option` /
    `.airport_id` (ARCFTOPT).
  - **SO**: `method_2` (`Method2Params`, `METHOD_2 srcid finemass dg`) on
    every source type; `PointSource.platform` (`PlatformParams`,
    PLATFORM); `SourcePathway.aircraft_sources` (ARCFTSRC) and
    `.hbp_sources` (HBPSRCID); `PointCapSource`, `PointHorSource` and
    `SidewashPointSource` construct POINTCAP, POINTHOR and SWPOINT;
    `OPEN_PIT`/`OPEN-PIT` are read as OPENPIT; the `FLAT` literal in a
    LOCATION elevation field is kept (`flat_source`) and written back.
  - Validator rules naming the AERMOD code for each: E145/E380 (ARMRATIO),
    E122/E123/E124/E126/E121 (the downwash options), E197/E198/E332/E386
    (METHOD_2), E198/E631 (PLATFORM), E198 (SWPOINT), E821/E130 (ARCFTSRC,
    HBPSRCID), E154/E200/E202/E380 (the ME keywords), E164/E203/E211
    (the OU files), E130/E203/E297/E313 (the events).
  - `tests/test_epa_deck_acceptance.py` runs every new writer form through
    AERMOD's setup pass; `tests/regulatory/test_epa_rewritten_so.py` now
    fully rewrites testpart, testprt2, openpits, capped, the two ARM2 decks,
    flatelev, lovett, mcr and hrdow and scores them against EPA's
    POSTFILEs (all at slope 1.000000); `tests/regulatory/test_event_rewrite.py`
    runs AERMOD's own generated event deck and pyaermod's rewrite and
    requires every contribution to agree. flatelev, scimtest,
    no2_1yrAK_arm2 and the AERMOD-generated `events_generated.inp` are
    vendored.
- **Source construction, reader tranche 2.** The SO keywords the v26135
  audit listed as recognised but not constructed, or not read at all,
  are now stored on the source model and written back in the field
  layout `soset.f` parses. Each form passes AERMOD's setup pass
  (`tests/test_so_deck_acceptance.py`, 20 cases), every EPA deck that
  uses it round-trips the keyword lines token for token
  (`tests/test_epa_source_roundtrip.py`, seven more decks vendored), and
  the fourteen EPA decks whose SO pathway uses these keywords reproduce
  EPA's reference POSTFILEs when run with pyaermod's rewritten SO
  pathway (`tests/regulatory/test_epa_rewritten_so.py`; nine of them
  also as whole rewritten decks). Reader coverage goes from 77 to 91 of
  the 115 dispatched keywords.
  - AREAPOLY: `AREAVERT` rings accumulate over any number of lines, a
    closing repeat of the first vertex is dropped (AERMOD closes the ring
    itself), and `AreaPolySource.initial_vertical_dimension` carries the
    optional fourth SRCPARAM field. `LineSource` gains the same field.
  - BUOYLINE: `BLPGROUP` continuation lines, source-ID ranges and `ALL`
    (soset.f BLPGRP); per-segment base elevations
    (`BuoyLineSegment.base_elevation`); the eight-field `BLPINPUT` with
    no BLPGROUP is AERMOD's implicit single group, which a
    `BuoyLineSource` named `ALL` now writes back as such instead of the
    nine-field form.
  - RLINEXT: the eleventh LOCATION field (base elevation) is read and
    always written; `RBARRIER` (one or two barriers), `RDEPRESS` and the
    v26135 `VBARRIER` (`RLineExtSource.vegetative_barriers`,
    `VegetativeBarrier`) are read back; `SBARRIER` solid barriers
    (`SourcePathway.solid_barriers`, `SolidBarrier`,
    `SolidBarrierSegment`) and the bare `RLEMCONV` switch
    (`SourcePathway.rline_moves_units`) are new.
  - `OLMGROUP` is read into `ChemistryOptions.olm_groups`, including the
    bare `OLMGROUP ALL` form, continuation lines and ranges (member
    tokens are kept as written); `PSDGROUP` into
    `SourcePathway.psd_groups` with `ControlPathway.psd_credit` for the
    PSDCREDIT option, under which the writer emits PSDGROUP instead of
    SRCGROUP as AERMOD requires; `NO2RATIO` (ID or range) into
    `no2_ratio`, which every source type now has.
  - `EMISUNIT`, `CONCUNIT`, `DEPOUNIT` (`EmissionUnits` on
    `SourcePathway.emission_units` / `concentration_units` /
    `deposition_units`); Fortran `D` exponents (`3.6D6`) are read.
  - `MODELOPT` `ALPHA`, `BETA` and `PSDCREDIT` are read back (they were
    dropped, so a rewritten RLINEXT or GASDEPOS deck failed E198).
  - `URBANSRC ALL`, ranges and the multi-area `urbanid srcids` form are
    read; `URBANOPT` is read in both its field orders and
    `ControlPathway.urban_roughness` carries the optional roughness.
  - Deposition presets (`chemistry_presets.deposition_defaults_for`)
    now return AERMOD's own built-in GASDEPOS values (soset.f GASDEP)
    for SO2, NO2, HG0, HGII, TCDD and BAP.
  - Validator rules for the above, each naming the AERMOD code: E144
    (OLMGROUP needs OLM), E146/E105/E287 (PSDGROUP), E158/E159 (unit
    conflicts), E198/E713 (barriers need ALPHA and FLAT), E320,
    E371-E374 (barrier ranges), E380/E195 (GASDEPOS).
  - `scripts/oracle_decks/13`-`18`: the probe decks that settled these
    forms, with what AERMOD said about the first guesses; the oracle
    workflow's default keyword list covers the tranche.

- **Nothing the reader cannot model is dropped any more:
  `AERMODProject.unparsed_lines`.** `pyaermod.input_reader` keeps every
  runstream line it has no field for -- an unmodelled keyword (RANKFILE,
  SEASONHR, EMISFACT, HOUREMIS, INCLUDED, SITEDATA, ERRORFIL, ...), an
  unmodelled form of a known keyword (a BACKGRND hourly file, a PLOTFILE
  with a lower rank, a second POSTFILE), the definition lines of a source
  type it does not construct (POINTCAP, POINTHOR), or an inline EV
  pathway -- as an `UnparsedLine` (pathway, keyword, fields as written,
  line number), logs one warning per pathway and keyword, and the writer
  puts them back into their pathway (`to_aermod_input(preserve_unparsed=
  True)`, the default) where AERMOD accepts them: ELEVUNIT first, SO lines
  before the group keywords, the rest before FINISHED. The module
  docstring had promised this collection since the reader was written;
  the implementation silently discarded the lines.
- **The runstream layout AERMOD actually parses.** A line blank through
  the keyword columns continues the previous keyword (setup.f EXKEY), as
  twenty of EPA's decks write their GRIDPOLR blocks (`POL1 DIST 100.
  1000.`); the reader took `POL1` for the keyword and dropped the line.
- **Receptor networks as reset.f defines them.** `PolarGrid.distances`
  (GRIDPOLR DIST is only ever a list of ring distances), `.directions`
  (DDIR), `.origin_source_id` (`ORIG srcid`), `.elevations`/`.hills`/
  `.flags`; `CartesianGrid.x_points`/`.y_points` (XPNTS/YPNTS) and
  `.grid_flags`; `ring_distances()`, `direction_angles()`, `x_values()`,
  `y_values()` and `receptor_count` for consumers, which the geospatial
  expansion and the advanced validator now use. The reader fills the
  GRIDCART ELEV/HILL rows the writer already emitted.
- **`OutputPathway.maxi_files` (`MaxiFile`)**: MAXIFILE in the layout
  ouset.f reads, `aveper grpid thresh filename [funit]`, one per
  averaging period and group (audit item 1).
- **`ControlPathway.urban_areas` (`UrbanArea`)** for decks with several
  URBANOPT lines (EPA's multurb.inp), `.extra_model_options` for MODELOPT
  tokens without a field (SCREEN, PSDCREDIT, NOCHKD, ...), `.run_model`
  (RUNORNOT NOT round-trips), `ChemistryMethod.TTRM`/`TTRM2`,
  `MeteorologyPathway.start_hour`/`.end_hour` (the eight-field STARTEND),
  `SourcePathway.include_all_group` (a deck that groups its sources with
  PSDGROUP gets no invented `SRCGROUP ALL`).
- **The round-trip guarantee over EPA's whole archive.**
  `tests/test_epa_deck_roundtrip.py` now compares the CO, RE, ME and OU
  pathways field for field, the source groups and IDs, and the preserved
  lines, and asserts every line of each of the 53 v26135 decks is either
  modelled or in `unparsed_lines`; eleven decks are vendored so the check
  runs without the archive. `tests/test_epa_deck_acceptance.py` runs
  every deck pyaermod writes for the archive through AERMOD's setup pass
  next to EPA's original: 49 are accepted clean, the four chained
  MULTYEAR years report the same missing-save-file E500 as EPA's own
  deck. The writer forms this release changed have setup-pass cases of
  their own. Probe decks 13-19 under `scripts/oracle_decks/` record what
  AERMOD said about the previous forms.

### Changed
- `RELEASING.md` names every file a release touches (the third
  `__version__`, in `pyaermod.api`, was missing), sets the changelog
  date and `CITATION.cff`'s `date-released`, and adds the Zenodo step:
  enable the GitHub–Zenodo archive before publishing, then paste the
  minted DOI into `CITATION.cff`, `README.md` and `docs/index.md`.
- **`EventPeriod` has AERMOD's field semantics** (`event_name,
  averaging_period, date, source_group, original_conc, location`); the
  former `start_date`/`end_date` pair matched no AERMOD card, EVENTLOC was
  never written and the EV block went after OU, so no event deck pyaermod
  wrote was ever accepted. `AERMODProject.write(event_filename=)` now
  writes a complete event deck rather than an EV block. Event names may be
  ten characters (`EVNAME*10`; AERMOD's own are).
- `SourcePathway.sources` may hold `SidewashPointSource`; the GUI's source
  registries list the three new classes.
- The pre-commit ruff hook is pinned to the ruff release CI uses (the
  v0.4.0 hook could not parse `pyproject.toml`'s `UP045` selector).
- **`OutputPathway.max_file` is removed.** It wrote `MAXIFILE filename`,
  which every AERMOD release rejects (E201: four fields are required);
  use `maxi_files=[MaxiFile(aveper, group, threshold, filename)]`. The
  GUI's output page lists the new field.
- `Validator` accepts explicit receptor lists (`distances`, `directions`,
  `x_points`, `y_points`) in place of the generator fields they replace.
- **`GasDepositionParams` now has AERMOD's field semantics** (audit
  follow-up 7): `GASDEPOS srcid Da Dw rcl Henry`, i.e. `diffusivity`,
  `diffusivity_water`, `cuticular_resistance` and a required
  `henry_constant`. The former `alpha_r` and `reactivity` names, the
  0-1 check on the third field and the `dry_dep_velocity` fallback (which
  wrote a velocity into the Henry's-law field) are gone; EPA's `testgas`
  values (`0.08962 1.04E-5 2.51E4 557.0`) validate and are written back
  unchanged. Positional construction is unaffected.
- **URBANSRC and URBANOPT are written in the single-urban-area forms
  AERMOD reads**: `URBANSRC srcid` (a trailing area name was an
  undefined source, E300) and `URBANOPT population [name] [roughness]`
  (the old `name population` order was an illegal numeric field, E208).
  `is_urban=True` no longer needs `urban_area_name` to emit the keyword.
- Numeric fields with an exponent are written with a decimal point in
  the mantissa (`1.0e+06`, not `1e+06`), which is what AERMOD's STODBL
  accepts.
- SRCGROUP continuation lines are merged into one
  `SourceGroupDefinition` on read, and the writer keeps every group's
  lines together with `SRCGROUP ALL BACKGROUND` on the card that
  defines ALL: AERMOD files a non-adjacent continuation card under the
  last group defined, whichever ID it names.
- `Validator._validate_output` receives the control pathway so the OU
  design-value keywords can be checked against the pollutant and
  averaging periods; `Validator.validate` is unchanged for callers.
- The GRSM validation warning is raised when no NOx background of any
  kind is given, not only when `nox_file` is unset, and the NOx keywords
  on a non-GRSM run are an error (AERMOD E602).

- **AERSURFACE deck-acceptance tests across the configuration space** —
  `tests/test_aersurface_deck_acceptance.py` runs AERSURFACE's own setup
  pass (`RUNORNOT NOT`) over ~30 configurations. Setup needs the raster
  files to exist but never reads them, so ten-byte placeholders suffice:
  no test-case archive, and the sweep runs in under a second. The
  existing end-to-end test proves one configuration byte-for-byte; this
  covers the rest of the space, where four more defects were hiding.
- **`AERSURFACEConfig.anemometer_height_m`** — emitted as `ANEM_HGT`,
  and required when `zo_method="ZOEFF"`.

- **Property-based round-trip over the ME and OU pathways, and polar
  receptor grids** — `tests/test_property_pathways.py`. Those pathways
  were pinned to fixed values in the existing property tests, so every
  field on them went unexercised.
- **Deck-acceptance cases for the output pathway** — the PLOTFILE,
  POSTFILE and RECTABLE keywords have field-count-sensitive syntax that
  varies with the averaging period, so each configuration is now run
  through AERMOD's setup check.

- **Deck-acceptance tests for every source type** —
  `tests/test_source_deck_acceptance.py` generates a minimal deck for
  each of pyaermod's ten source types and runs AERMOD's own setup pass
  (`RUNORNOT NOT`) over it, asserting no fatal errors. It carries a
  coverage guard that fails when a new source type is added without a
  case, and a self-check that a deliberately broken deck *is* reported,
  so the suite cannot pass vacuously.
- **Property-based round-trip over all ten source types** —
  `tests/test_property_all_sources.py`. The existing property tests
  covered the three types the reader supported when they were written.
- **`ControlPathway.alpha` / `.beta`** — the non-regulatory MODELOPT
  options. AERMOD refuses RLINEXT outright without ALPHA.

- **Real-binary parity for BPIP-PRIME and AERSURFACE.** Both had EPA
  Fortran available and neither had ever been run against it.
  `scripts/build_bpip.sh` and `scripts/build_aersurface.sh` fetch and
  compile them (into `./bin`), and `make test-binaries` puts that
  directory on PATH so the binary-backed suite is one command.
  - `tests/test_bpip_known_answers.py` compares `pyaermod.bpip` against
    EPA's BPIP-PRIME direction by direction, at the F8.2 print
    resolution BPIP writes with.
  - `tests/test_real_aersurface.py` builds the deck for EPA's published
    RDU test case with `AERSURFACEConfig`, runs it, and compares the
    surface characteristics to EPA's shipped reference file. They are
    identical apart from the run timestamp.
- **`pyaermod.epa_sources`** — registry of EPA SCRAM download locations
  for AERMOD, AERMET, AERMAP, AERSURFACE, AERSCREEN, MAKEMET, BPIP and
  BPIP-PRIME source and test-case archives. Every URL was discovered by
  listing its SCRAM directory and verified to return a zip; an opt-in
  network test (`PYAERMOD_NETWORK_TESTS=1`) re-lists each directory so
  an EPA rename fails a test instead of 404-ing in CI later.
- **`pyaermod.bpip` GEP influence-zone test** — `BPIPCalculator` now
  reports zeros for wind directions where the stack lies outside the
  structure influence zone, as BPIP does, with `influence_test=False`
  to inspect the raw projected geometry.

- **NAAQS design-value known-answer tests** — the design-value math is now
  pinned against evidence rather than smoke-tested. `tests/test_naaqs_rank_tables.py`
  transcribes 40 CFR part 50 appendix N Table 1, appendix S Table 1 and
  appendix T Table 1 and checks the new `naaqs_percentile_rank()` against
  every row for every day count 1–366, then pins design values on series
  whose answer is arithmetic (365 strictly decreasing daily values → the
  98th percentile is exactly the 358th). `tests/regulatory/test_epa_known_answers.py`
  compares pyaermod's ranking against EPA's *own* ranked output — no
  AERMOD binary needed, since both sides derive from the concentrations
  in EPA's shipped `.PST` files:
  - the 1st-highest value at every receptor of all 47 `.PST`/`.PLT` pairs
    in the reference set, exactly (no tolerance);
  - ranks 1 through 8 of the 24-hour series in EPA's `surfcoal` deck
    against its eight `PSET2PA.DA1`–`DA8` plotfiles — the depth the
    98th-percentile forms need;
  - AERMOD's own NAAQS design-value plotfiles (`PSDCRED_*`, written under
    its 1-hour NO2 processing) against
    `nth_highest_daily_max_design_value()`, receptor by receptor;
  - the `.SUM` overall-maximum table, which ranks the largest *n*-th
    highest value per receptor rather than the *n*-th largest value in
    the record.
- **`pyaermod.design_values.naaqs_percentile_rank()`** — the EPA rank-table
  lookup, with both regulatory tables exported as
  `PERCENTILE_98_RANK_TABLE` / `PERCENTILE_99_RANK_TABLE`.
- **`pyaermod.design_values.nth_highest_daily_max_design_value()`** — the
  general form behind the 1-hour NO2, 1-hour SO2 and 24-hour PM2.5
  standards, and the one AERMOD itself computes under `NO2AVE` / `SO2AVE`
  / `PM25AVE`: rank each year's daily series independently, then average
  those annual values across years (`SUMHNH / NUMYRS` in `aermod.f`).
- **`AERMODAuxResult.concentration_column` / `.values()`** — callers no
  longer have to guess whether AERMOD spelled the column `CONC` or
  `AVERAGE CONC`.
- **`pyaermod.aermod_outputs.parse_fortran_format()`** — expands the
  Fortran FORMAT statement AERMOD prints in every auxiliary-file header
  into field widths, so records are sliced at the offsets AERMOD wrote
  them at.

- **Headless smoke tests for the NiceGUI GUI** — `tests/test_gui_v2_smoke.py`
  drives the real `gui_v2` shell through `nicegui.testing.User` (in-process
  ASGI, no browser): every tab renders its key controls; a minimal project
  (title, one point source via the Sources editor dialog, a receptor grid,
  met file names) is filled in through the UI, saved and reloaded via
  `project_io` with an identical AERMOD deck, and run against a fake
  `aermod` on `PATH` with the Results tab asserted for both the no-output
  and parsed-output cases. `gui_v2` is now measured by coverage (only
  `desktop.py`, the pywebview wrapper, stays omitted). Requires the new
  `pytest-asyncio` dev dependency.
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
- **EPA reference-set resolver** — `pyaermod.epa_testcases.find_epa_testcase_set`
  locates EPA's unpacked test-case sets under `test_cases/` accepting both
  naming conventions (`aermet_24142_aermod_24142` and the July-2026 bundle's
  `aermet24142_aermod24142` / `aermet24142_aermod26135` /
  `aermet26135_aermod26135`), honours `$PYAERMOD_EPA_TESTCASES`, and prefers
  the set whose AERMOD version matches the `aermod` binary on PATH
  (`aermod_binary_version`, from `aermod --help`), then the newest validated
  release. `tests/regulatory/`, `tests/test_epa_cases.py`,
  `tests/test_real_cases.py`, `tests/test_regression_epa_official.py` and
  `scripts/run_epa_parity.py` all resolve through it; regulatory test IDs now
  carry the set name (`[aermet26135_aermod26135/aertest.inp]`).
- **Parity report provenance** — `scripts/run_epa_parity.py` now stamps a
  Provenance table into `docs/validation.md`: AERMOD version (parsed from
  the `*** AERMOD - VERSION NNNNN ***` banner of a produced `.out`, falling
  back to `aermod --help`), binary path, `gfortran --version`, the EPA
  reference set, pyaermod version, git SHA (`-dirty` when applicable),
  platform and UTC timestamp. New `--testcase-dir` (or
  `$PYAERMOD_EPA_TESTCASES`) and `--clean-scratch` options; exit 2 when the
  fixtures or binary are missing, 1 when any comparison fails.
- **Scheduled EPA parity CI** — `epa_parity.yml` now runs weekly (Tuesday
  07:00 UTC, staggered from the Monday real-binary smokes) as well as on
  dispatch (archive URL inputs optional, defaulting to the canonical SCRAM
  URLs — the old default pointed at a non-existent `aermod_testcases.zip`).
  It compiles EPA's current AERMOD, fetches both EPA test-case archives via
  `scripts/fetch_epa_source.sh`, unpacks only the sets the suite needs (the
  set matching the compiled AERMOD version for parity, the 24142 set for the
  parser regressions, `aermet_def_testcases_24142` for the AERMET parsers —
  each AERMOD set is ~3.5 GB unpacked) and caches the unpacked trees with
  `actions/cache` (key = URLs + upstream ETag/Last-Modified + AERMOD
  version + salt; saved right after unpacking so a later failure keeps the
  cache). It runs `tests/regulatory`, `tests/test_epa_cases.py`,
  `tests/test_real_cases.py`, `tests/test_real_aermet.py` and
  `scripts/run_epa_parity.py`, fails if any test fails, if the fixture-gated
  tests all skipped, or if any deck leaves tolerance, and uploads the
  regenerated `docs/validation.md` as an artifact (never auto-commits).
  Before the cache is saved, a prune step cuts each unpacked tree down to
  the directories some test in this repo actually opens — resolved with the
  same `find_epa_testcase_set` the tests use, so it cannot drift from them:
  `inputs/`, `meteorology/`, `postfiles/` of the parity set, `Outputs/`,
  `postfiles/`, `plotfiles/` of the 24142 set (a set filling both roles
  keeps the union), and `output_files/` + `salem/` of
  `aermet_def_testcases_24142`. The 24142 set also keeps `inputs/`, which
  no test reads but `EPATestCaseSet.exists()` requires — without it the set
  survives on disk yet drops out of `find_epa_testcase_set`, so
  `tests/test_epa_cases.py` and `tests/test_real_cases.py` skip and the
  all-skipped guard fails the job (11 MB). What the prune actually reclaims
  in CI is the AERMET raw example datasets whose products are already in
  `output_files/` (873 MB → 174 MB, ~90 % of the saving) plus the Windows
  `.bat`/`.exe` runners and the empty `rdata/` drop boxes: **7.91 GB →
  7.14 GB, 770 MB (9.7 %) freed**. The clauses dropping EPA's `plots_*/`
  comparison images and R driver scripts are defence for a local full
  unpack only — CI's selective `unzip` never extracts them, so they
  contribute 0 MB of that total. Afterwards the step re-checks every kept
  directory *and* re-resolves both sets through `find_epa_testcase_set`,
  failing the job before the save if one came out missing, empty, or no
  longer resolvable. The regulatory harness also deletes each
  deck's staged scratch (~40 MB) in a fixture finalizer. The three
  real-binary smoke workflows gained `timeout-minutes: 30` (`epa_parity`
  already had 120) so a stalled gaftp fetch cannot hold a runner for the
  six-hour default.
- **AERMOD v26135 keyword audit** — `docs/keyword-audit-v26135.md` compares
  the 122-entry keyword table in EPA's v26135 `modules.f` (and the
  per-pathway `KEYWRD .EQ.` dispatch) against `input_reader.py`: per
  pathway, handled+tested / handled+untested / unhandled lists, the reader's
  MODELOPT and source-type coverage, and five follow-ups (`MAXIFILE`
  argument order, RLINEXT/AREAPOLY/BUOYLINE not constructed, `GRIDPOLR`
  heuristics, the undelivered `unparsed_lines` promise). All 53 decks in the
  v26135 archive parse. `tests/test_input_reader.py` gains parametrised
  one-line decks for every previously untested branch and a pass-through
  test for every unhandled keyword; `input_reader.py` coverage 85.0 % →
  99.8 % (the one remaining line is an unreachable guard).
- **`docs/validation.md` regenerated against AERMOD v26135** (gfortran 15.2
  build, EPA set `aermet26135_aermod26135`): **142 / 142** POSTFILE
  comparisons within EPA's ±0.001 slope margin in 323 s (the previous
  104 / 104 figure was produced against the pre-2026 24142 bundle with no
  recorded version). Informational cross-version run of the same v26135
  binary against the `aermet24142_aermod24142` references: 136 / 142, the
  six misses all GRSM NO2 cases (slopes 0.946–1.117) — EPA's v26135 GRSM
  changes, not a pyaermod regression — which is why the harness now scores
  against the reference set matching the binary's version.
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
- **Library code no longer prints.** `import pyaermod` is now silent: the
  `Warning: folium not installed. Interactive maps unavailable.` (and the
  matching matplotlib) line that `pyaermod.visualization` wrote to stdout on
  every import is now a `DEBUG`-level log record. That line was not merely
  untidy — it broke the scheduled parity workflow, whose version probe reads
  `python -c "... print(aermod_binary_version())"` through command
  substitution: the warning landed inside the captured value, and a
  multi-line value is invalid in `$GITHUB_OUTPUT`, so the run died with
  `Invalid format 'Warning: folium not installed...'` before compiling
  anything. The workflow now also takes only the last line and rejects a
  non-numeric version, so a future stray print degrades to the fallback
  instead of failing the run; the user-facing signal stays
  the `ImportError` with an install hint raised by the first feature that needs
  the package. `AERMODVisualizer.plot_contours` / `create_interactive_map`
  ("Figure saved to ...") and `AERMODResults.export_to_csv` ("Exported results
  to ...") report through `logging.getLogger(__name__)` at `INFO` instead of
  `print()`. `print()` remains only in `cli.py`, the NiceGUI GUI, the explicit
  `pyaermod.print_info()` banner, and `if __name__ == "__main__":` demo blocks.
  `tests/test_import_silence.py` pins the guarantee in a fresh subprocess.
- **Benchmark gate has a noise floor.** `benchmarks/compare_benchmarks.py`
  gained `--min-baseline-ms` (default 5.0): a benchmark whose baseline is
  below the floor is listed under `IGNORED` but never fails the PR — the gate
  previously failed a PR on `aux_parse/plotfile_100rows 0.172 -> 0.235 ms
  (+36.8%)`, pure noise on a sub-millisecond operation. `run_benchmarks.py`
  now times each benchmark over `--rounds` independent rounds (default 5) and
  reports the minimum instead of a single timing; the round count is recorded
  in the JSON. `tests/test_benchmarks_harness.py` proves +40% on a 0.2 ms
  baseline passes while +40% on a 50 ms baseline still fails.
- **mypy is gated, not advisory.** `scripts/mypy_gate.py` runs
  `mypy src/pyaermod` (config from `pyproject.toml`), counts `error:`
  diagnostics and compares against the integer committed in
  `mypy-baseline.txt`; CI (`tests.yml`, Python 3.12 leg, mypy pinned) fails
  only if the count *increases*, and prints the exact
  `python scripts/mypy_gate.py --update` command when it decreases. Existing
  type errors are untouched. The baseline is authoritative for the
  `.[dev,all]` environment CI uses: typed optional packages (`nicegui`,
  `ezdxf`, ...) surface errors that `ignore_missing_imports` hides when they
  are absent, so a partial install reports a different count (the gate's
  failure message says so; `make typecheck` pins the same mypy as CI).
  The baseline is **78**, and it is only meaningful measured on that leg.
  There is deliberately no `python_version` pin: pinning 3.11 while the gate
  runs on 3.12 made mypy reject numpy 2.5's own stubs (`Type statement is
  only supported in Python 3.12 and greater`) and abort before checking any
  project code. The count is dependency-sensitive too — numpy 2.5 types
  `ArrayLike` precisely enough to surface nine further errors in
  `geospatial.py` and `visualization.py` that numpy 2.4 did not — so a
  baseline measured on an older local environment understates it, which is
  how it was first committed nine too low.
- **Honest dependency floors, validated in CI.** The optional-extra lower
  bounds in `pyproject.toml` were aspirational (`geopandas>=0.10` predates
  shapely 2 / pandas 2; `shapely>=1.8`, `matplotlib>=3.3`, `scipy>=1.7`,
  `pyproj>=3.0`, `rasterio>=1.2`, `requests>=2.25`, `nicegui>=2.0`). They are
  raised to `matplotlib>=3.7`, `scipy>=1.10`, `folium>=0.14`, `pyproj>=3.4`,
  `geopandas>=0.14`, `rasterio>=1.3`, `shapely>=2.0`, `requests>=2.32.2` and
  `nicegui>=3.0` (`numpy>=1.24`, `pandas>=2.0`, `tqdm>=4.60`, `ezdxf>=1.0`
  unchanged). `requests>=2.32` is forced by nicegui — even nicegui 2.0.0
  requires `requests>=2.32.0`, so the previous `[all]` floor set was not
  co-installable at all — and `nicegui>=3.0` is the line the GUI itself
  needs (nothing under `src/` imports `nicegui.testing`). The headless smoke
  tests do *not* exercise that floor: `user_simulation` and
  `ElementFilter(local_scope=)` only landed in NiceGUI 3.4.0, so
  `tests/test_gui_v2_smoke.py` skips below it rather than claiming coverage
  it does not have — the min-deps leg caught the original `minversion="3.0"`
  guard letting collection through and then failing on the missing module.
  The requests
  floor lands on `2.32.2` rather than `2.32.0` because 2.32.0 and 2.32.1
  are yanked on PyPI ("Yanked due to conflicts with CVE-2024-35195
  mitigation"): the exact pin in `min-constraints.txt` made the `min-deps`
  leg install a withdrawn release (pip honours an `==` pin on a yanked
  version, warning as it does so), and no range resolution will ever land
  there anyway. 2.32.2 is the oldest 2.32.x that is still a real
  candidate. A new
  `min-constraints.txt` pins the oldest versions that satisfy those floors
  together (resolvability proven with
  `pip install --dry-run --ignore-installed -e ".[dev,all]" -c min-constraints.txt`),
  and a `min-deps` leg in `tests.yml` (Python 3.11) installs `.[dev,all]`
  under those constraints and runs the suite, so the floors are checked
  rather than guessed. It earned its keep immediately: `fiona` is pulled in
  by geopandas, which declares only `fiona >=1.8.21` with no upper bound, so
  the oldest-everything resolve paired geopandas 0.14 with a current fiona —
  and fiona 1.10 removed `fiona.path.ParsedPath`, which geopandas 0.14 calls
  on every read, failing eight shapefile tests with `module 'fiona' has no
  attribute 'path'`. `min-constraints.txt` now caps it at the last 1.9.x.
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
- **EPA source version is pinned per run and surfaced in CI.**
  `scripts/fetch_epa_source.sh` now prints the archive's top-level directory
  (EPA encodes the version in it, e.g. `aermod_source_v26135`; `<flat
  archive>` for AERMET) after every successful fetch or cache reuse, and
  appends `EPA source: <dir> from <url>` to `$GITHUB_STEP_SUMMARY` when set.
  `real_aermod.yml` / `real_aermap.yml` / `real_aermet.yml` gained a
  `workflow_dispatch` input `source_url` (default = the current SCRAM URL) to
  try a new EPA release without editing the workflow, and cache the downloaded
  zip with `actions/cache` keyed on the URL plus the calendar month (so a
  same-URL EPA re-release is still picked up within a month while gaftp
  flakiness inside the month is absorbed). The derived-dir and
  `chmod -R u+w` compile logic is unchanged.
- **Repo hygiene.** `.DS_Store` and `aermod/.DS_Store` are no longer tracked
  (they were already gitignored, so they showed as perpetually modified). A
  `Makefile` adds `test`, `test-full` (installs `.[dev,all]`, then the whole
  suite with coverage), `lint` and `typecheck` targets mirroring CI;
  `CONTRIBUTING.md` documents the GDAL prerequisite for the `[geo]` extra and
  `make test-full` as the pre-PR check.

### Fixed
- **Scalar building-downwash values produced a deck AERMOD rejects.**
  A source whose `building_height`, `building_width`, `building_length`,
  `building_x_offset` or `building_y_offset` was a single float wrote one
  value per keyword, and AERMOD reads one per 10-degree sector: a POINT
  source was fatal (SO E236, E237, E241, E246, E247). A scalar is now
  written as the same value for all 36 sectors, and the point, area and
  volume forms pass AERMOD's setup pass in
  `tests/test_source_deck_acceptance.py` (keyword audit item 10).
- **The EPA parity workflow pruned the reference files the known-answer
  suite compares against.** It kept only `inputs/`, `meteorology/` and
  `postfiles/` of the parity set, so the PST/PLT rank comparisons, the
  surfcoal `.DA1`-`.DA8` ranks and the AERTEST `.SUM` check had nothing to
  read and the suite's non-empty guard failed the job. The set now also
  keeps `plotfiles/` and `Outputs/` (about 32 MB), and the cache salt is
  bumped so the previously pruned cache is not reused.
- **`pyaermod.__version__` was `pyaermod.api`'s constant, not
  `__init__.py`'s.** `api.py` defines its own `__version__` and the
  package re-exports `api.*` after setting its own, so bumping the two
  files `RELEASING.md` named left the package reporting the old number.
  All three say 2.2.0, and `tests/test_citation.py` fails on a partial
  bump.
- **`deposition_method` wrote a `METHOD` line that no AERMOD release
  accepts** (there is no METHOD keyword in `modules.f`; SO E105). The field
  is kept for compatibility and writes nothing; Method 2 deposition is
  `method_2`.
- **Fixed-column source fields no longer round a value away**: EPA's
  capped deck gives three stacks an exit velocity of 0.001 m/s, which the
  `8.2f` SRCPARAM column wrote as 0.00; a value the column cannot hold is
  now written with six significant digits in the same width.
- A `LOCATION ... FLAT` source (flatelev) was written with elevation 0.00,
  which moved the FLAT group's 1-hour maxima by 17 %.
- The lines of an incomplete source definition (a POINT with four
  SRCPARAM values, a LINE with no end point) are kept in `unparsed_lines`
  instead of being dropped.
- **Every polar grid pyaermod wrote had no receptors (RE E185).** The
  writer emitted `DIST init num delta` and `GDIR init num delta`;
  reset.f reads every DIST field as a ring and GDIR as `num init delta`,
  so `GDIR 0.0 36 10.0` generated zero directions. The reader's
  three-token heuristic for the same lines (audit item 3) read EPA's
  `GDIR 36 10 10` as 10 directions starting at 36 degrees. Both now
  follow the Fortran; there is no heuristic.
- **Elevated terrain was written as `MODELOPT ... ELEVATED`, which
  coset.f does not know (E203).** The token is `ELEV`; `FLATSRCS` is the
  pair `FLAT ELEV`, and the reader maps `FLAT ELEV` back to
  `TerrainType.FLATSRCS` and ignores a FLAT after ELEV as AERMOD does.
- **`NO2STACK` was written for ARM2 runs, which reject it (E600).** It
  is written only for OLM, PVMRM, GRSM and TTRM.
- **A single `URBANOPT` was written name-first (E208).** With one card
  coset.f reads `pop [name [z0]]`; the ID-first form belongs to decks
  with several cards. The reader still accepts the old spelling.
- **`GRIDCART` with `XPNTS`/`YPNTS` became a default 10 x 10 grid**, and
  `STARTEND` with hours lost its last two fields; a source defined in an
  INCLUDED file with SRCPARAM inline was re-defined at the origin (E310).
- The reader dropped every source's base elevation (the LOCATION
  elevation field was parsed and never applied) and the fourth SRCPARAM
  field of LINE sources.

- **Structural reading and writing of the regulatory-critical CO and OU
  keywords** the v26135 audit listed as pass-through only. Each is stored
  on the project model, written back in the field layout AERMOD's
  `coset.f` / `ouset.f` read, and checked against the binary's own setup
  pass (`tests/test_source_deck_acceptance.py`) and against every EPA
  test deck that uses it (`tests/test_epa_deck_roundtrip.py`, token for
  token). Reader coverage goes from 59 to 77 of the 115 dispatched
  keywords.
  - Restart and multi-year runs: `ControlPathway.save_file`
    (`SaveFile`: SAVEFILE with its day increment and alternate file),
    `.init_file` (`InitFile`, bare or named) and `.multiyear`
    (`MultiYear`: MULTYEAR with the optional previous-year file and the
    legacy `H6H` field AERMOD still tolerates). EPA's five-year
    `testpm10_1986`–`1990` chain round-trips.
  - The NOx background family for GRSM: `ChemistryOptions.nox_background`
    (`NOxBackground`) carries NOXVALUE, NOX_FILE (units and Fortran
    format), NOX_VALS (any of the twelve EMISFACT-style temporal flags,
    accumulated over continuation lines), NOX_UNIT and NOXSECTR with
    per-sector `BackgroundSpec`s. `OzoneData` gains the matching
    O3SECTOR (`sectors`), OZONUNIT (`units`), per-sector `by_sector`,
    the units on OZONEVAL/OZONEFIL and the OZONEFIL read format, and an
    O3VALUES temporal profile (`TemporalValues`).
  - Gas dry-deposition defaults: `ControlPathway.gas_deposition_defaults`
    (`GasDepositionDefaults`: GASDEPDF), `.gas_deposition_velocity`
    (GASDEPVD), `.gas_deposition_seasons` (GDSEASON) and
    `.gas_deposition_land_use` (GDLANUSE).
  - The 1-hour NO2/SO2 and 24-hour PM2.5 design-value outputs:
    `OutputPathway.max_daily_files` / `.max_daily_by_year_files`
    (`MaxDailyFile`: MAXDAILY, MXDYBYYR), `.max_daily_contributions`
    (`MaxDailyContribution`: MAXDCONT in both the rank and the THRESH
    form) and `.file_format` (FILEFORM).
- **The 1-hour NAAQS workflow end to end.**
  `design_values.naaqs_output_pathway(pollutant)` builds the OU pathway
  for a design value with the rank taken from the NAAQS table
  (`NAAQSStandard.percentile` / `.design_rank()`, new), `read_maxdaily()`
  and `read_mxdybyyr()` parse AERMOD's MAXDAILY / MXDYBYYR files into
  the frames the design-value functions take, and
  `mxdybyyr_design_value()` reads AERMOD's own ranking back as a
  cross-check. On EPA's Anchorage 1999 meteorology the SO2 and NO2 design
  values pyaermod computes from MAXDAILY equal AERMOD's MXDYBYYR rank and
  MAXDCONT total to the last printed digit
  (`tests/fixtures/epa_style/{so2,no2}_1hr_*`, produced by the vendored
  decks, which `naaqs_output_pathway` wrote).
- **Validator rules for the cross-checks AERMOD applies to these
  keywords**: MULTYEAR excludes SAVEFILE/INITFILE (E150) and is limited
  to the pollutants it can chain; the gas-deposition defaults need ALPHA
  (E198) and GASDEPVD excludes GDSEASON/GDLANUSE (E195); NOXVALUE and
  NOX_VALS conflict (E605), sector forms need their sector keyword (E171)
  and sectors must be ascending and at least 30 degrees apart (E222/E227);
  MAXDAILY/MXDYBYYR/MAXDCONT require the NAAQS processing to be active
  (`Validator.naaqs_processing`, E162/E163), MAXDCONT excludes restarts
  (E153) and its ranks must sit inside the RECTABLE range (E290/E272),
  with the THRESH form needing room beyond the design rank (E273).
- **`scripts/keyword_oracle.py` and `.github/workflows/keyword_oracle.yml`**
  — print, from EPA's Fortran and a freshly built binary, what AERMOD
  does with a keyword: the dispatch branch and parsing subroutine, every
  EPA test deck that uses it, and the setup-pass messages and produced
  files from probe decks (`scripts/oracle_decks/`). Manual dispatch.
- **The ozone and NOx writer emitted lines AERMOD rejects.** An ozone
  file was written as `O3VALUES <file>` (E201, no numerical parameters),
  a constant as `O3VALUES UNIFORM <value>` (E203, invalid flag) and a
  sector value as `O3VALUES SECTOR n <value>`; the NOx background file
  was written on `NOXVALUE`, which takes a concentration (E208). They now
  go on OZONEFIL, OZONEVAL, `OZONEVAL SECTn` and NOX_FILE, and the
  setup-pass acceptance tests hold them there. The reader still accepts
  the two legacy `O3VALUES` spellings so decks written by earlier
  releases open.
- **`pyaermod.aerscreen` wrote a deck AERSCREEN never reads.** The
  `KEY: value` layout of the previous release was not an AERSCREEN
  format (it has none), so nothing that used `AERSCREENConfig` could
  ever have run. EPA's `AERSCREEN.FOR` did not build under gfortran,
  which is why the rewrite waited for a reference: with the source
  patched (see *Added*) the binary is the oracle, and every flat EPA
  test case now reproduces EPA's published output through pyaermod's
  answers. See the upgrade notes for the field changes.
- **Four AERSURFACE configurations produced decks the binary rejects**,
  all outside the single case the end-to-end test covers:
  - `frequency="SEASONAL"` still wrote `SEASON` keywords, which
    AERSURFACE accepts only with `ANNUAL` and `MONTHLY`. Now omitted,
    and an explicit `seasons=` under `SEASONAL` raises rather than being
    silently dropped.
  - `zo_method="ZOEFF"` never emitted `ANEM_HGT`, which AERSURFACE
    requires for it.
  - `arid=True` with the default `snow=True` is refused by AERSURFACE
    ("Arid Climate is Invalid With Continuous Snow"); the combination
    now raises.
  - Sectors with a gap or overlap were accepted here and refused there
    (`E267`); they must tile the compass, and now must here too.
- **`datum="NAD27"` could never work.** AERSURFACE reads NADCON grid
  files (`conus`/`alaska`/`hawaii`/`prvi` `.las` and `.los`) from its
  working directory and fails without them. `scripts/build_aersurface.sh`
  now installs them beside the binary, `AERSURFACERunner` stages them
  into the run directory for NAD27 runs (overridable with
  `$PYAERMOD_NADCON_DIR`), and a run with no grids available fails with
  a message saying where to get them instead of a Fortran error code.

- **PLOTFILE and POSTFILE wrote a field AERMOD does not have.** Both
  carried an output-type token (`CONC`, `DDEP`, ...), and PLOTFILE also
  wrote a rank on the PERIOD/ANNUAL form, which takes none. AERMOD
  counts fields: the result was a fatal "Too Many Parameters Specified
  For the Keyword of PLOTFILE" and "Invalid Parameter Specified.
  Troubled Parameter: FORMAT". There is no per-file output type in
  AERMOD -- the quantity written is a MODELOPT setting -- so
  `OutputPathway.output_type` is now documented as inert and no longer
  emitted.
- **The reader read the PLOTFILE rank as the filename.** It took a fixed
  field position, so a PERIOD-form plotfile round-tripped
  `plot_file="p.dat"` into `plot_file="FIRST"`.
- **`RECTABLE ALLAVE 10` asks AERMOD for the tenth-highest value alone,
  not the top ten.** `receptor_table_rank=10` therefore produced a table
  of one rank, and any PLOTFILE requesting FIRST against it was rejected
  as an invalid HIVALU. The writer now emits the range form
  (`ALLAVE 1-10`), and the reader understands bare ranks, ranges and the
  ordinal-word forms (`FIRST-THIRD`, `EIGHTH`) alike -- it previously
  fell back to the default rank for all but a bare number.

- **Three of the ten source types produced decks AERMOD rejects.**
  Verified against the real binary's setup pass:
  - `AREAPOLY` wrote its `LOCATION` at the polygon *centroid* while
    AERMOD requires the first vertex ("ARVERT: First Vertex Does Not
    Match LOCATION"), and omitted the vertex count from `SRCPARAM`,
    which is a fatal "Not Enough Parameters" and then makes every
    `AREAVERT` line overflow an unset limit. Four distinct fatal errors
    from one source.
  - `BUOYLINE` wrote `BLPINPUT` with no group ID, so AERMOD filed the
    parameters under the implicit group `ALL` and then failed with "No
    BLPINPUT record for BLPGROUP ID".
  - `RLINEXT` needs `MODELOPT ... ALPHA`, which `ControlPathway` had no
    way to emit.
- **The reader silently dropped AREAPOLY, RLINEXT and BUOYLINE
  sources.** `parse_aermod_input` returned successfully with an empty
  source list -- no error, no warning -- so a project could lose its
  emissions with nothing to show for it. All three are now
  reconstructed, including `AREAVERT` vertex rings and the
  `BLPINPUT`/`BLPGROUP` pairing that turns buoyant line *segments* back
  into a source. All ten source types now round-trip.

- **AERSURFACE decks used keywords AERSURFACE does not have.**
  `AERSURFACEConfig.to_aersurface_input()` emitted `TITLE`, `LOCATION`,
  `NLCDFILE`, `NLCDYEAR`, `SNOW_TEMPER`, `SECTORS_LIST`, `OUTPATH` and
  friends -- none of which exist. The real format is pathway-based
  (`CO STARTING` / `OU STARTING`) with `TITLEONE`, `CENTERLL`,
  `DATAFILE`, `ZORADIUS`, `CLIMATE`, `FREQ_SECT`, `SECTOR`, `SEASON`,
  `RUNORNOT`, `SFCCHAR`. Fed the old deck, AERSURFACE v26135 aborted
  immediately with a Fortran bounds error in its control-file parser.
  Rewritten to the real format, with sectors as
  `(start, end, "AP"|"NONAP")` triples, season-to-month assignment
  (including `WINTERWS` for continuous snow cover), and the canopy and
  impervious rasters that 2001-and-later NLCD releases carry. This is a
  breaking change to `AERSURFACEConfig`'s fields; the class never
  produced a usable deck, so no working code depended on them.
- **BPIP reported downwash where EPA reports none.** `BPIPCalculator`
  had no structure-influence-zone test, so a stack 400 m from a 13 m
  building came back with a full-size building for all 36 directions
  instead of zeros -- enough to make AERMOD apply downwash the GEP
  criteria exclude.
- **BPIP now agrees with EPA's BPIP-PRIME exactly** (6,480 direction
  comparisons over rectangles, an L-shape and randomised polygons; worst
  difference 0.005, which is what BPIP's `F8.2` output can express).
  Closing the last gap needed two things that projection geometry alone
  does not give, both transcribed from `Bpipprm.for`:
  - **BPIP applies two different influence tests.** The downwash pass
    admits a stack within half an `L` of either edge of the projected
    width and no more than `2 L` upwind of the near face -- with *no*
    downwind limit (it computes `CYMX = YMAX + 5 L` and never tests
    against it). The GEP pass is stricter and separate. An empirically
    fitted single zone matched 501 of 504 cases and was wrong in kind.
  - **The GEP clamp.** When a direction's wake-effect height
    `H + 1.5 L` would exceed the stack's GEP stack height, BPIP reports
    the GEP-controlling structure's height and width instead of that
    direction's projection. This shows up as a flat cap across a run of
    directions that tracks the *stack position*, not the footprint --
    on one test case pyaermod reported 58.68 m where BPIP reports 42.18.
    The GEP height itself comes from a quarter-degree sweep, far finer
    than the 36 reported directions, so the capped width is generally
    not any direction's projected width.
- **BPIP's XBADJ and YBADJ were the projected centroid.** XBADJ is the
  along-flow coordinate of the projected building's *upwind face*
  (`-BUILDLEN/2` for a stack at the building centre, where the old code
  returned 0) and YBADJ the negated crosswind midpoint. The rotation
  also ran the wrong way, which an axis-aligned rectangle cannot reveal
  because its projected width and length are symmetric in wind
  direction.
- **`Building` rejected any footprint that was not a quadrilateral**,
  including the six-corner L-shape in EPA's own first BPIP test case.
  Any polygon of three or more corners is accepted.

- **NAAQS percentiles were interpolated quantiles, not the regulatory
  order statistics.** `pm25_24hr_design_value`, `no2_1hr_design_value`
  and `so2_1hr_design_value` computed the annual percentile with
  `Series.quantile(..., interpolation="linear")`. The standards do not
  interpolate: 40 CFR part 50 appendices N, S and T sort each year's
  daily values from highest to lowest and read the rank off a table keyed
  on the year's count of valid days — the **8th highest** for a full-year
  98th percentile, the **4th highest** for a full-year 99th percentile.
  Linear interpolation lands *between* ranks (0.98 × 364 = 356.72) and
  reports a number the regulation never defines, biased low against the
  standard. Now rank-based, with the rank chosen per receptor-year from
  that year's own day count.
- **PM2.5 and PM10 24-hour design values used each day's peak hour as the
  24-hour value.** Both functions called the daily-*maximum* helper on
  hourly input, despite the docstring promising an average. A day with
  one hour at 240 µg/m³ and 23 hours at zero was scored as 240 rather
  than 10. Hourly input is now averaged over the day for the 24-hour
  standards; input already carrying AERMOD `AVE='24-HR'` block averages
  is unchanged.
- **The PM10 24-hour form ignored the multi-year window.** It always
  returned the high-second-high and left averaging to the caller. It now
  follows Appendix W Table 8-2: the highest *sixth*-high (H6H) of the
  pooled record when five years are modelled, H2H otherwise, overridable
  via `rank=`. Unlike the percentile standards this form is not averaged
  across years.
- **Design values silently pooled source groups and duplicated
  receptors.** A POSTFILE holding several `SRCGROUP`s was ranked as one
  mixed series; the functions now require a single group and say how to
  filter. A deck that declares the same receptor twice (EPA's own
  `surfcoal` does) made the 2nd-highest value a copy of the 1st —
  repeated rows are now collapsed, and receptors that genuinely share
  (x, y) but differ in concentration raise instead of being merged.
- **`naaqs_percentile_rank` boundary rounding.** The rank is computed in
  exact rational arithmetic: `math.ceil(0.02 * 50)` is 2 in binary
  floating point, which would put a 50-day year on the second-highest
  value where appendix S Table 1 says the highest. Caught by the new
  table test.
- **`get_naaqs("Pb", ...)` always raised `KeyError`.** The lookup
  upper-cased the caller's string, and `"Pb".upper()` is not the table
  key `"Pb"`. Lookup is now case-insensitive and the error lists the
  available pollutants.
- **Every AERMOD PLOTFILE from a deposition run was unreadable.**
  `read_plotfile` detected the file type from the first header line
  mentioning one, which is `MODELING OPTIONS USED: ... DDEP WDEP ...` —
  so a deposition run's plotfile was classified `DDEP` and rejected. The
  options line is now excluded and the `"<kind> FILE OF ..."` declaration
  wins. Seven of EPA's reference plotfiles were affected.
- **Auxiliary-file column labels were shifted by one for every real
  AERMOD output.** The header line was split on any whitespace, so
  AERMOD's two-word labels `AVERAGE CONC` and `NET ID` each became two
  columns and every label after them named the wrong data. Labels are
  now split on two-or-more spaces, and rows are sliced using the Fortran
  FORMAT AERMOD prints in the header — which is also the only way a
  blank trailing `NET ID` (discrete receptors) parses as blank instead of
  pulling every later column one place left.

- **EPA fixture tests skipped silently after EPA renamed the archive sets.**
  `tests/test_epa_cases.py` looked only at a hard-coded Dropbox path, and
  `tests/regulatory/` plus `tests/test_real_cases.py` at the pre-2026
  `aermet_24142_aermod_24142` name, so with the current EPA bundle unpacked
  every one of them still skipped (the file-parametrised cases did not even
  collect). With the resolver and the archive present they collect as
  350 / 54 / 323 tests; regulatory: 47 passed / 7 skipped against a compiled
  v26135; the two parser modules: 673 passed against the 24142 set (after
  the phantom-4HR fix below). Those two modules skip, with the discovered
  set named in the reason, when only another AERMOD version is present —
  their assertions quote 24142 values.
- **Phantom `4HR` averaging period in `AERMODOutputParser`.** The `4-HR`
  section pattern also matched inside `24-HR` headers, so every run with a
  24-hour average gained a bogus `4HR` result duplicating the 24-hour table
  (surfaced by `tests/test_epa_cases.py` on AERTEST and FLATELEV once those
  tests ran). Period patterns are now anchored (`(?<![0-9])(?:...)`) so they
  cannot start inside a longer number. Wrapping the alternation in a group
  fixes a second latent bug: interpolated bare, `24-HOUR|24HR|24-HR` split
  the *surrounding* section regex into three top-level branches, so only the
  last spelling carried the `RESULTS` tail and the capture group and the
  other two matched with `group(1) is None` — the `X-HOUR` and `XHR`
  spellings never selected a table. No shipped result changes: AERMOD only
  ever writes the `X-HR` spelling in its section headers (checked across
  every `.out`/`.SUM` in EPA's v26135 archive), so the broken branches were
  unreachable in practice. Regression in
  `tests/test_output_parser_periods.py`.
- **`AERMODOutputParser` effectively hung on multi-MB `.out` files.** The
  second, free-form section pattern
  (`\*\*\*.*?<period>.*?RESULTS.*?\*\*\*…`, `re.DOTALL`) backtracks from
  every `***` in the file out to EOF, and `parse()` tries all eleven period
  patterns against every output — so on EPA's 2.3 MB `allsrcs.out` a single
  *absent* period cost ~291 s in that pattern (the first, line-anchored
  pattern rejects the same input in 0.014 s).
  `tests/test_epa_cases.py::TestOutputParserEdgeCases` never got past
  `allsrcs.out`. Both section patterns require the period token to occur
  somewhere, so `_parse_concentration_table` now returns `None` early after
  one linear `re.search` for it — equivalent by construction, and it turns
  the pathological case into a single scan. `allsrcs.out`: no completion in
  over six minutes → 0.30 s; the whole EPA `.out` set parses in under a
  second per file.
- **`tests/test_source_importers.py` skipped entirely whenever `ezdxf` was
  absent** — a module-level `pytest.importorskip("ezdxf")` hid the seven
  geopandas shapefile tests too. The skip is now a class-scoped fixture on
  `TestDxfImporter` only; the shapefile tests run wherever geopandas is
  installed (`source_importers.py` coverage 11.8 % → 52.8 % in the local
  env). All five shapefile fixtures now write through one `_write_shapefile`
  helper — three of them still called `gdf.to_file` directly — which falls
  back to writing the layer through fiona (no `.prj`, which the importers do
  not read) if geopandas' writer raises pyproj's `Invalid value supplied
  'WktVersion.WKT2_2019'`. That is a defensive guard, not a live workaround:
  it was seen once under coverage tracing but does not reproduce on the
  current pin (geopandas 0.14.4, fiona 1.9.6, pyproj 3.6.1, coverage
  7.13.3), where `to_file` succeeds for all six writes and the fallback is
  never entered.
- **`AERMODRunner._extract_error_message` swallowed read errors** around the
  `.err`/`.out` files (`except Exception: pass`), so a Latin-1 byte in
  AERMOD's output — a degree sign in the banner is enough — raised
  `UnicodeDecodeError` and the caller saw only "AERMOD failed with return
  code N" instead of the `FATAL` line. Both files are now read as Latin-1
  with replacement, only `OSError` is tolerated, and that is logged at
  DEBUG. Tests cover non-UTF-8 bytes in both files and the logged fallback.
- **GUI v2 Run/Results/editor crashes found by the new smoke tests:**
  - the Run button always raised `ImportError` (`from ..._optional import
    HAS_TERRAIN` — no such name), so AERMOD could never be launched from the
    GUI; the stray import is removed;
  - the Run tab wrote its deck as `aermod.inp`, the name `AERMODRunner`
    reserves for the symlink it points at the deck — the runner unlinked the
    deck and replaced it with a self-referencing symlink, and then failed
    renaming `aermod.out` onto itself. The deck is now written as
    `pyaermod_gui.inp`;
  - the Results tab read `run_info.title` / `.pollutant` and iterated
    `results.concentrations` as a list of objects with `max_x` / `max_y` /
    `source_group`; the parser provides `jobname` / `pollutant_id`, a
    `{period: ConcentrationResult}` mapping and a `max_location` tuple, so any
    real output raised `AttributeError`;
  - the source/receptor editor dialog crashed (`float() argument ... not
    'list'`) for every source with polygon `vertices`, because the form
    helper's numeric check was a substring test that claimed
    `List[Tuple[float, float]]` — and silently rendered
    `Optional[Tuple[DepositionMethod, float]]` as a number box, letting a
    float be written into a tuple-typed field. `is_numeric` now resolves the
    annotation (`typing.get_type_hints`, `get_origin`/`get_args`, unwrapping
    `Optional`/`Union`, with a structural parser for unresolvable string
    annotations) and is true only when the type *is* `int`/`float`,
    optionally with `None`; list annotations are still dispatched first;
  - tightening `is_numeric` then made the five building-downwash dimensions
    (`building_height`, `building_width`, `building_length`,
    `building_x_offset`, `building_y_offset` on the point/volume/area
    sources) uneditable: they are `Optional[Union[float, List[float]]]`,
    which is correctly *not* numeric, and fell through to the read-only-label
    escape hatch, so a building height could no longer be typed at all.
    `emit_field` now dispatches these on the current value — a number box
    (clearable) while the field holds a scalar or nothing, the one-per-line
    list editor once it holds a 36-sector vector — so neither shape is
    thrown away. Clearing either widget stores `None` rather than `0.0` or
    `[]`: the writer emits the keyword for any non-`None` value, and an
    empty list is rejected as "not 36 values";
  - `Optional[str]` fields (e.g. `OutputPathway.summary_file`) were rendered
    as read-only labels instead of text inputs.
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

### Removed
- `OutputPathway.max_file`: it wrote `MAXIFILE filename`, which every
  AERMOD release rejects (E201); use
  `maxi_files=[MaxiFile(aveper, group, threshold, filename)]`.
- `AERSCREENConfig.distances` and `.extra_lines`: AERSCREEN probes its
  own distances and has no deck to append to (up to ten extra
  distances go in `discrete_receptors`). `initial_sigma_z`,
  `vertical_dim`, `lateral_dim`, `dominant_landuse` and `terrain_file`
  are renamed; see the upgrade notes.
- `GasDepositionParams.alpha_r`, `.reactivity` and the
  `dry_dep_velocity` fallback: the fields are AERMOD's (`diffusivity`,
  `diffusivity_water`, `cuticular_resistance`, `henry_constant`).
- The `METHOD` line `deposition_method` wrote (no AERMOD release has the
  keyword); the field stays and writes nothing, and Method 2 deposition
  is `method_2`.
- `EventPeriod.start_date` and `.end_date`; see the upgrade notes.
- The "known limitation" on `pyaermod.aerscreen` recorded after PR #9:
  the module drives the real binary now.

### Upgrade notes — `AERSCREENConfig`

`AERSCREENConfig`'s fields changed, because the deck it built was not in
any AERSCREEN format: AERSCREEN has no keyword deck at all. It asks an
ordered sequence of questions on stdin and can restart from the `**`
header of its own output file, and the old fields described neither.
No code that ran AERSCREEN can have depended on the old fields; code
written against them can. Passing an old field name raises a
`TypeError` naming the replacement.

| Old | New |
|-----|-----|
| `initial_sigma_z`, `vertical_dim` | `vertical_dimension` (VOLUME, AREA and AREACIRC) |
| `lateral_dim` | `lateral_dimension` |
| `dominant_landuse` (an Auer code 1-12) | `land_use` (an AERMET land-use code 1-8) with `climate` (1-3) |
| `terrain_file` | `dem_files` (with `dem_type` and `nad_grid_dir`); AERSCREEN lists them in `DEMlist.txt` for AERMAP |
| `distances="AUTO"` / `[...]` | *removed* -- AERSCREEN probes its own distances; up to ten extra ones go in `discrete_receptors` |
| `extra_lines` | *removed* -- there is no deck to append to |
| `AERSCREENSourceType.CAPPED` / `.HORIZONTAL` | still work, as aliases of `POINTCAP` / `POINTHOR` |

`stack_temp=None` still means ambient (AERSCREEN's `0`), and a negative
value is a temperature difference above ambient, as AERSCREEN takes it.
The surface characteristics must now be given one of AERSCREEN's three
ways: `albedo` + `bowen_ratio` + `roughness_length`, `land_use` +
`climate`, or an AERSURFACE output in `surface_file`. Files a run needs
(`surface_file`, `discrete_receptor_file`, `bpip_file`, `dem_files`) are
copied into the working directory by the runner and referred to by
name, as AERSCREEN expects.

```python
# Old -- produced a KEY: value deck AERSCREEN never read
cfg = AERSCREENConfig(
    title="SO2 stack", source_type="POINT", emission_rate=10.0,
    stack_height=30.0, stack_diameter=2.0, stack_temp=425.0,
    exit_velocity=15.0, dominant_landuse=7, distances="AUTO",
)

# New -- the answers AERSCREEN asks for, or its restart file
cfg = AERSCREENConfig(
    title="SO2 stack", source_type="POINT", emission_rate=10.0,
    stack_height=30.0, stack_diameter=2.0, stack_temp=425.0,
    exit_velocity=15.0, land_use=7, climate=1,
)
result = AERSCREENRunner().run(cfg, working_dir="so2")   # mode="prompts"
result.summary.maximum.conc_1hr                           # ug/m3
```

These fields are new and have no old equivalent: `flare_heat_loss`,
`radius`, `ambient_distance`, the NO2 chemistry (`no2_method`,
`no2_stack_ratio`, `ozone_concentration`, `ozone_units`), `bpip_file`,
`stack_direction`, `stack_distance`, `probe_distance`,
`discrete_receptor_file`, `flagpole_height`, `source_elevation`,
`aermap_elevation`, the UTM location and `datum`, `min_wind_speed`,
`surface_file`, `shoreline_fumigation` and its distance and direction,
`run_aermod`, `debug` and `output_file`.

### Upgrade notes — `AERSURFACEConfig`

`AERSURFACEConfig`'s fields changed, because the deck it built was not
in any AERSURFACE format: it emitted `TITLE`, `LOCATION`, `NLCDFILE`,
`SNOW_TEMPER`, `OUTPATH` and friends, none of which AERSURFACE has ever
accepted, and the real binary aborted in its control-file parser. No
code that ran AERSURFACE can have depended on the old fields; code
written against them can.

Passing an old field name now raises a `TypeError` naming the
replacement, rather than a bare "unexpected keyword argument".

| Old | New |
|-----|-----|
| `nlcd_file` | `land_cover_file` |
| `radius_roughness_km` | `zo_radius_km` |
| `snow_cover_per_month=[...]` | months in the `WINTERWS` season: `seasons={"WINTERWS": (1,), ...}` |
| `moisture_per_month=[...]` | one `moisture="AVERAGE" \| "WET" \| "DRY"` |
| `output_dir` | `sfcchar_file` (plus `*_grid_file` for the optional grid outputs) |
| `extra_lines` | `extra_co_lines` / `extra_ou_lines` |
| `sectors=[30, 60, 225]` | `sectors=[(30, 60, "NONAP"), (60, 225, "AP"), (225, 30, "NONAP")]` |
| `utc_offset` | *removed* — AERSURFACE has no UTC-offset keyword |
| `snow_regime` | *removed* — use `snow=True/False`; `CLIMATE` has no temperature regime |
| `radius_albedo_bowen_km` | *removed* — AERSURFACE averages over the single `ZORADIUS` |

```python
# Old — produced a deck AERSURFACE rejected
cfg = AERSURFACEConfig(
    title="Salem", site_id="SALEM", latitude=44.92, longitude=-123.04,
    utc_offset=-8, nlcd_file="NLCD_2019.img", nlcd_year=2019,
    snow_regime="CONTINENTAL_WARM", radius_roughness_km=1.0,
)

# New
cfg = AERSURFACEConfig(
    title="Salem", site_id="SALEM", latitude=44.92, longitude=-123.04,
    land_cover_file="NLCD_2019_LC.tiff", nlcd_year=2019,
    zo_radius_km=1.0, moisture="AVERAGE", snow=True,
    sfcchar_file="salem_sfc.txt",
)
```

These fields are new and have no old equivalent: `title_two`, `datum`,
`canopy_file`, `impervious_file`, `site_type`, `zo_method`, `frequency`,
`debug_options`, `run`, and the `*_grid_file` outputs.

### Upgrade notes — `EventPeriod` and event decks

`EventPeriod` carried a start and an end date and no receptor, which
matches no AERMOD card: `evset.f` EVPER reads exactly five fields on
`EVENTPER` (name, averaging period, source group, the `YYMMDDHH` of the
period's *last* hour, and the concentration the main run found), every
event needs an `EVENTLOC` card with its receptor (E130), and the EV
pathway belongs between ME and OU. No event deck pyaermod wrote was ever
accepted, so nothing that ran can have depended on the old fields.

| Old | New |
|-----|-----|
| `start_date`, `end_date` | `date` (the period's last hour, `YYMMDDHH`) with `averaging_period` (hours, one of the run's `AVERTIME` periods) |
| no receptor | `location=EventLocation(x, y, z_elev, z_hill, z_flag=None, polar=False)`; the elevation is required by AERMOD |
| — | `original_conc`, the main run's value for the event (0 when unknown) |
| `write(event_filename=)` wrote a bare EV block | writes the complete `CO SO ME EV OU` event deck AERMOD's `EV_SETUP` reads, with `OutputPathway.event_output` (EVENTOUT) and without the keywords an event run rejects |

```python
# Old
EventPeriod(event_name="MAX1", start_date="88010101", end_date="88010124")

# New -- the card AERMOD writes itself for EVENTFIL
EventPeriod(
    event_name="MAX1", averaging_period=24, date="88010124",
    source_group="ALL", original_conc=51.36,
    location=EventLocation(x=500.0, y=500.0, z_elev=10.0, z_hill=10.0),
)
```

Event names may be ten characters (`EVNAME*10`; AERMOD's own are).
`read_event_output()` reads an event run's per-event contributions.

### Upgrade notes — `OutputPathway.max_file`

`max_file="thresholds.dat"` wrote `MAXIFILE thresholds.dat`, and
`ouset.f` OUMXFL wants `aveper grpid thresh filename [funit]` (fewer
fields is E201), so the line was fatal in every AERMOD release. The
field is removed rather than deprecated; the replacement takes one
entry per averaging period and group:

```python
# Old (never accepted by AERMOD)
OutputPathway(max_file="thresholds.dat")

# New
OutputPathway(maxi_files=[MaxiFile(averaging_period="1", source_group="ALL",
                                   threshold=100.0, filename="thresholds.dat")])
```

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

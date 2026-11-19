# arch: cross-module review (HEAD 794fe60)

Scope: whole-codebase duplication, GUI drift, module boundaries, dead weight, complexity.
Repros: scratchpad/repro/arch/ (geo_area.py, quote.py, quoted_rt.py, hints.py, defaults.py, noextras.py, fnlen.py).
Not looked at: docs/keyword-audit-v26135.md content, webapp/app.js results rendering in depth, cli.py, psd.py, met_ingest.py, ensemble.py beyond run_design, every per-module bug.

Counts: BUG 3 (medium 2, low 1), GUI drift 4, CONCISION 16, DOCS 2.

---

## Bugs found on the way (cross-module)

### A1 [BUG] [medium] GIS and KMZ exports draw sources with their own (wrong) geometry instead of footprints.py
- Where: src/pyaermod/geospatial.py:234-369 (sources_to_geodataframe); src/pyaermod/kmz_export.py:228-253; correct one: src/pyaermod/footprints.py:66-135
- What: geospatial builds AREA as a rectangle *centred* on LOCATION with half-widths = Xinit/Yinit (so 2x size) and counter-clockwise rotation; OPENPIT rotation is CCW; AREACIRC is a circle sampled from east, not soset.f GENCIR's equal-area polygon from north. footprints.py (used by the GUI plan view) follows soset.f ARVERT/GENCIR. kmz_export draws AREA/AREACIRC/OPENPIT as a point at LOCATION and silently drops LINE/RLINE/RLINEXT/BUOYLINE (style "source-line" is defined but never used).
- Evidence: VERIFIED, repro/arch/geo_area.py. AreaSource(0,0, Xinit=100, Yinit=50, angle=30): footprints -> (0,0),(25,43.3),(111.6,-6.7),(86.6,-50); geospatial -> (6.7,-111.6),(93.3,-61.6),(-6.7,111.6),(-93.3,61.6). AREACIRC r=50: polygon area 7725 vs AERMOD's equal-area 7854. KMZ of [AREA, LINE]: no polygon, L1 absent. This is the 2026-11-11 review's Medium "AREA polygon export ... OPENPIT rotation" item: STILL PRESENT. tests/test_geospatial.py:314,323 assert only geom_type, so they do not catch it.
- Fix: both call footprints.source_footprint(src) and map POINT/POLYGON/LINES to shapely Point/Polygon/MultiLineString (KMZ: _placemark_point/_polygon/_line). Removes ~95 lines from geospatial, adds ~10 to kmz. Add a test asserting geospatial vertices == source_footprint(src).points().

### A2 [BUG] [medium] pip GUI and the library write met (and other) file names with blanks unquoted; only the browser GUI quotes them
- Where: src/pyaermod/pathways.py:1159 (SURFFILE, likewise PROFFILE and every *_file writer); src/pyaermod/gui_v2/files.py:255-266 (Browse... stores str(path)); browser.py:446-474 (_quote_blanks, browser only)
- What: MeteorologyPathway(surface_file="/Users/x/My Met/a.sfc") writes `SURFFILE  /Users/x/My Met/a.sfc`. setup.f DEFINE splits fields at blanks outside double quotes (setup.f:400-490), so meset.f SURFIL sees IFC=4 and takes "Met/a.sfc" as the Fortran FORMAT (meset.f SURFIL, IFC .EQ. 4 branch) -> the met file read fails. The pip GUI's native Browse button writes exactly such paths (macOS "Mobile Documents", "My Drive", Windows "Program Files"). The browser GUI works around it by mutating the project (_quote_blanks) before check/deck/run. In addition gui_v2/files.file_problem (files.py:82-104) treats a quoted path as relative (Path('"/a b"') is not absolute) and shows "Give the full path", while readiness._met_files (readiness.py:223-230) and session.py:871 strip quotes with .strip('"') and pathways.unquote_path is a third spelling.
- Evidence: writer output VERIFIED (repro/arch/quote.py, quoted_rt.py); AERMOD behaviour READ (setup.f DEFINE, meset.f SURFIL).
- Fix: in the writers, emit file fields through one helper `field_path(p) = p if p.startswith('"') else quote_path(p)`; then delete browser._quote_blanks (~30 lines) and make files.file_problem and readiness use unquote_path. Tests: tests/test_browser.py (quoting tests move to writer tests), test_input_reader round-trip tests, test_gui_v2_* met-file tests.

### A3 [BUG] [low] GUIs decide "AERMOD is installed" differently from the runner
- Where: gui_v2/pages/run.py:80-81 and browser.py:355-364 (`shutil.which("aermod")`); runner.py:346-357 (tries aermod, AERMOD, aermod.exe, AERMOD.EXE)
- What: on a case-sensitive file system with the binary named AERMOD (EPA's own name), Review & Run blocks with NO_BINARY although AERMODRunner() would find it. PLAUSIBLE (Linux only).
- Fix: falls out of C3 below (one discovery helper; GUIs call it with must_exist=False).

---

## 1. Same knowledge in several places

### C1 [CONCISION] Geometry: see A1. footprints.py is the single description; geospatial and kmz should consume it. ~85 net lines, low-medium risk.

### C2 [CONCISION] Field-kind classification exists twice and _form.py carries ~120 lines of string-annotation parsing that project_io already makes unnecessary
- Where: gui_v2/_form.py:70-230 and 279-385 (field_kind, _str_kind, _leaf_names, _wrapper_name, _is_numeric_list_node, _numeric_info_str, _matches_scalar_or_list_str, string branches of _allows_none/is_integer); browser.py:211-299 (_unwrap_optional, _is_point_list, _field_kind, labels)
- What: _form falls back to parsing string annotations because typing.get_type_hints(ChemistryOptions) raises NameError. project_io._Types.hints (project_io.py:138-152) already resolves every dataclass with a localns. VERIFIED (repro/arch/hints.py): with project_io's hints, every field of every project dataclass resolves, ChemistryOptions is the only class that needed the string path, and field_kind returns the same kind for every field.
- Change: _form.resolve_annotation uses project_io._types().hints(type(obj)); delete the string-annotation machinery (~120 lines). Then let browser._field_kind reuse _form's primitives (_args_without_none, _list_item) and field_label (browser labels "Source id", pip "Source ID (m)") (~30 more lines). Keep the two kind vocabularies (pip shows enums read-only, browser has dropdowns) as a 10-line mapping, or give pip the enum dropdown later.
- Risk: low for step 1. Tests: tests/test_gui_v2_sources.py:96-160 test the string parser directly and would be deleted/rewritten; test_gui_v2_form.py, test_browser.py schema tests cover the behaviour.

### C3 [CONCISION] Executable discovery x6 and captured-subprocess block x5
- Where: runner.py:332-363, aermet_runner.py:217-229, aerscreen_runner.py:169-198 (two copies: _find_or_set_executable and _optional), terrain.py:455-473, aersurface_runner.py:77-90; subprocess blocks runner.py:430-470, aermet_runner.py:280-310, aerscreen_runner.py:370-400, terrain.py:520-556, aersurface_runner.py:165-200
- What: identical "path given -> must exist; else try name, NAME, name.exe[, NAME.EXE] on PATH; else FileNotFoundError" and identical "open stdout/stderr files, subprocess.run, TimeoutExpired -> failed result, close, _read_capped". Drift: AERMAP's timeout result has no return_code/start_time/end_time and it alone catches bare Exception; aerscreen/aermet resolve() paths, others do not.
- Change: in runner_utils (or a new _exec.py to avoid the runner_utils->runner import): `find_executable(program, path=None, *, hint="", resolve=False, required=True)` and `run_captured(cmd, cwd, stem, timeout, *, input=None, env=None) -> Captured(returncode|None, stdout, stderr, start, end, timeout_message)`. Move _dir_state/_files_written/_read_capped there too (today 3 runners import privates from runner.py). Keep each class's _find_or_set_executable as a one-line delegate (tests and docs call it).
- Lines: ~90-110 net. Risk: low-medium. Tests: test_runner*.py, test_aermet_runner*.py, test_aerscreen_runner.py, test_aersurface_runner.py, test_terrain.py (AERMAPRunner), test_priority2_gaps.py:411-430 (patches shutil.which globally, unaffected), real-binary tests (test_real_*).

### C4 [CONCISION] SRCPARAM layout is written in the writer (sources.py to_aermod_input), the reader (input_reader.py:1414-1600, 13 branches) and the GUI defaults (pages/sources.py:69-111)
- Change worth making: a `SRCPARAM: ClassVar[Tuple[str, ...]]` (and `SRCPARAM_MIN`) on each source class; the reader's construction loop becomes `cls(**common, **dict(zip(cls.SRCPARAM, params)))` plus the four genuine specials (AREA Yinit=Xinit, AREAPOLY vertices, RLINEXT/LINE end points, BUOYLINE). ~100 lines out of _parse_sources. Note: reader fallbacks differ from dataclass defaults for VolumeSource (1.0 vs 10.0) and RLineExtSource (0.0 vs 30.0/1.5) (repro/arch/defaults.py) - only reachable for decks AERMOD itself rejects as too short, but the table must carry explicit per-position defaults to stay behaviour-identical.
- Not worth it: driving the writer from the same table (fixed-column formatting per field, _f8_2/_f10_6, FLAT) or the validator.
- Risk: medium. Tests: test_input_reader*.py, test_source_deck_acceptance.py, test_epa_deck_acceptance.py, test_property_based.py round trips.

### C5 [CONCISION] Small duplicated tables (one-liners each)
- input_reader.py:380-387 _CHEM_METHODS == {m.value: m for m in ChemistryMethod} (-7 lines).
- validator.py:38 VALID_POLLUTANT_IDS == {p.value for p in PollutantType} (keep the name).
- input_reader.py:822-828 _BUILDING_KW_TO_FIELD is sources.py:338-342 reversed: export one BUILDING_KEYWORDS tuple from sources.py.
- geospatial.py:529-538 and 693-702: same cubic-then-linear griddata fallback twice -> `_interpolate()`; visualization.py:201-205 does cubic with no fallback (drift, cosmetic).
- runner._read_message_summary (runner.py:172-206) and terrain._read_aermap_verdict (terrain.py:369-396): same SUMTBL parsing with a different routine-field width (A12 + ': ' vs A6 + ':'); one parametrised reader saves ~25 lines (fixtures tests/fixtures/runner, aermap_runner cover it).
- postfile.PostfileParser._parse_header_line (postfile.py:561-670) and aermod_outputs.parse_aermod_header (aermod_outputs.py:209-270) both parse the "* AERMOD ( v ): title / MODELING OPTIONS / FORMAT:" banner; postfile counts value columns with a regex hack where aermod_outputs.parse_fortran_format already expands FORMATs. Share the FORMAT expansion (~20 lines); leave the rest (medium risk, POSTFILE layouts are fussy).
Total ~60 lines, low risk.

### C6 [CONCISION] Number formatters: leave (see "tempting").

## 2. The two GUIs

Shared as intended: project_io (JSON), readiness.review, session.Session, plan_view, run_results.view_of, results_map. Duplicated or drifted:

### G1 [GUI] browser.py, the "UI-free API", imports private registries from NiceGUI page modules
- Where: browser.py:189-191, 206, 304-309, 174, 220, 243, 269 import _SOURCE_TYPES, _new_source, _RECEPTOR_TYPES, _new_receptor, AVERAGING_PERIODS, OUTPUT_OPTIONS, TERRAIN_CHOICES, meteorology.GROUPS, output.*_FIELDS, run_status_text, message_counts_text, results._UNITS/_OUTPUT_TYPES from gui_v2/pages/*; plus input_reader privates (_input_file_slots, _validate_paths_within) and TerrainProcessor privates (_update_*_elevations, browser.py:686-691).
- Change: move the pure data/text (source/receptor registries + defaults + ADVANCED_FIELDS, the option tables, run/message text, units) to a UI-free gui_v2/catalog.py; pages import from it. Promote the three input_reader helpers and a TerrainProcessor.apply_frame(project, kind, frame) to public. Line-neutral; makes the Pyodide boundary explicit. Low risk (tests import these from pages; keep re-exports in pages).

### G2 [GUI] Source editor: pip GUI splits LOCATION/SRCPARAM fields from "Advanced" (pages/sources.py:161-176 ADVANCED_FIELDS); the browser shows every field flat (webapp/app.js:376 fieldGroup(cls, item, null))
- Fix: schema() exports ADVANCED_FIELDS; editor() reuses groupsFor's details/summary split. ~8 lines JS, 1 line Python.

### G3 [GUI] Checklist merging reimplemented in the browser
- Where: browser.py:371-488 (_items, _not_uploaded, _outside, _merge build ChecklistItem-shaped dicts by hand) vs readiness.py:126-137 (_add/_ordered).
- Change: readiness.review(session, have_binary, extra=()) where extra is an iterable of (step, problem) callables; browser passes its two checks and the NO_WASM replacement. ~35 lines out of browser.py. Tests: test_browser.py check tests, test_gui_v2_readiness*.

### G4 [GUI] Feature drift (report only)
- Terrain import (AERMAP output/CSV -> elevations) exists only in the browser (browser.apply_terrain); the pip GUI has none. Moving the logic into Session would let both use it.
- Samples (webapp/samples.json) only in the browser; recent files / native dialogs only in pip. Intentional.
- New project: browser uses averaging ["1","PERIOD"], pip ["1","ANNUAL"]; ANNUAL with short met blocks in the browser, warns in pip. Intentional and documented (browser.py:166-171, 491-500).
- Item summary in tables: JS describeItem (app.js:324-331) vs pages/sources._summary_row / pages/receptors._summary_row: three x/y lookup chains (JS also tries x_center). Could be served from Python; low value.
- Quoting of blank file names: see A2. Binary detection: see A3.

## 3. Helpers

- Fortran numbers: fortran_float is already shared by every reader (input_reader, output_parser, postfile, aermod_outputs, design_values). Writers' _num differ on purpose (leave).
- Executables/subprocess: C3.
- Optional deps: _optional.py is used by terrain, terrain_utils, met_ingest, runner_utils, aermod_outputs, aerscreen_runner; advanced_viz.py:13-25, geospatial.py:19-73 (own _require), visualization.py:20-32, kmz_export.py:39-44 still use try/except + HAS_*. Migration saves ~20 lines; tests read/patch HAS_* (test_optional_helper.py, test_import_silence.py, test_visualization_edges.py), so keep the flags. Low value; do it only when touching those files.
- Geometry: C1. Also validator_advanced._iter_receptor_coords (validator_advanced.py:118-133) is dead and its polar formula ignores origin_source_id (footprints.receptor_points handles it); _receptor_bbox also ignores GRIDPOLR ORIG srcid.

## 4. Module boundaries (verdicts)

- output_parser vs aermod_outputs vs postfile: meaningful (.OUT tables / fixed-format aux files / POSTFILE). Share only the header/FORMAT parsing (C5). Keep.
- terrain vs terrain_utils vs aermap: aermap = AERMAP deck writer; terrain = DEM download + AERMAPRunner + AERMAPOutputParser + TerrainProcessor; terrain_utils = datum/mosaic/SRTM helpers. AERMAPRunner breaks the *_runner naming of aermet/aersurface/aerscreen, but renaming costs a shim for a public, documented path. Leave.
- validator vs validator_advanced: meaningful (per-field rules vs cross-field heuristics), but entangled: validator.py:1417 imports validator_advanced privates _cart_values/_polar_directions/_polar_distances, and validator_advanced imports ValidationError back. Move those three grid helpers to receptors.py (they expand a grid) and delete _iter_receptor_coords. DOCS: validator_advanced.py:13 lists "Emission-rate plausibility for the declared pollutant" (no such check; only emission_rate==0) and Validator.validate's docstring (validator.py:127-131) says advanced includes "ANNUAL met coverage", which the module says is not part of validate().
- regulatory / regulatory_parity / naaqs / design_values: regulatory = option profiles, naaqs = standards table, design_values = calculations: keep. regulatory_parity is EPA test-suite scoring used only by tests and scripts/run_epa_parity.py; its name suggests regulatory use. Optional: fold into epa_testcases.py with a 3-line shim module. Low value.
- visualization vs advanced_viz: two static-method classes; advanced_viz used by one notebook and tests. Merging gains nothing. Keep; drop the demo block (D1).
- aerscreen vs aerscreen_runner: same config/runner split as aermet and aersurface. Keep.
- gui_v2/project_io is the project file format of the library, browser and CLI but lives under gui_v2; documented widely in docs/teaching as pyaermod.gui_v2.project_io. Leave.

## 5. Dead weight

### D1 [CONCISION] `if __name__ == "__main__":` demo blocks, ~330 lines
- runner.py:1857-1912 (56), aermap.py:745-823 (78), advanced_viz.py:398-479 (81), aermet.py:1259-1300 (41), visualization.py:569-608 (40), output_parser.py:1255-1279 (25), input_generator.py:368-376 (9).
- Not referenced in docs/examples/tests (grep for "python -m pyaermod.<mod>": none), excluded from coverage (.coveragerc "if __name__ == .__main__"), so unverified and stale-prone (e.g. aermap demo). Keep cli.py and gui_v2/__main__.py. Risk: low. Check: ruff (unused imports may appear), test suite.

### D2 [CONCISION] api.py: HAS_GEOSPATIAL / HAS_TERRAIN are always True
- Where: api.py:318-350 and 437-455.
- Evidence: VERIFIED (repro/arch/noextras.py): with pyproj, geopandas, rasterio, scipy, matplotlib, shapely, requests, folium blocked, `pyaermod.api` imports with HAS_GEOSPATIAL=HAS_TERRAIN=True and ContourGenerator in __all__; geospatial and terrain need only numpy/pandas at import.
- Change: import unconditionally, list the names in __all__, keep `HAS_GEOSPATIAL = HAS_TERRAIN = True` for compatibility (drop at 3.0). ~25 lines. Also api.py:39 and __init__.py:32 both assign __version__ (api's is re-exported by the wildcard); api.py:11 docstring names a `pyaermod.api.core` submodule that does not exist (DOCS). Tests: test_api_core.py, test_init.py.

### D3 [CONCISION] Private dead code (low risk, ~55 lines)
- design_values.py:265-267 _agg_daily_max: no caller anywhere.
- validator_advanced.py:118-133 _iter_receptor_coords: no caller anywhere.
- sources.py:443-446 PointSource._format_building_keyword "thin wrapper for backward compat": private method, no caller.
- __init__.py:61-86 _check_dependencies: never called (only tests/test_init.py:88-156 exercise it).
- runner.py:129 `@dataclass(frozen=True)` on the NamedTuple _MessageSummary is a no-op (dataclasses.is_dataclass is False; VERIFIED).
- Public but caller-less (keep: on docs/api pages): aermap.create_grid_receptors_for_aermap, AdvancedVisualizer.create_comparison_grid, geospatial.CoordinateTransformer.from_aermap_domain/transform_dataframe, GeoDataFrameFactory.sources_from_results, bpip get_footprint_area.

### D4 Deprecated shims: now vs 3.0
- Remove at 3.0 (each already warns or raises): aermet.AERMETStage2 (~40 lines) and run_aermet_pipeline's stage2 parameter; AERMETStage1/3 integer `messages` (aermet.py:165-178, 336, 596); aerscreen _RENAMED_FIELDS/_REMOVED_FIELDS + __init__ wrapper (aerscreen.py:~160-200, 1280-1292); input_generator's re-export of private helpers (_building_downwash_lines, _deposition_to_aermod_lines, _format_building_keyword, _set_building_from_bpip; input_generator.py:99-102); HAS_GEOSPATIAL/HAS_TERRAIN.
- Keep: input_generator as a re-export module (51 test files, 13 examples, 10 docs import it); CORE_NAMES/API_VERSION (contract-tested).

## 6. Longest / most complex functions (radon CC, AST length)

1. input_reader._parse_sources (746 lines, CC 205): split: card-collection loop, per-type construction table-driven (C4), BUOYLINE assembly as _buoyline_sources.
2. input_reader._parse_control (357, CC 129): split MODELOPT tokens into _modelopt(toks) -> flags; table for single-value keywords (HALFLIFE, DCAYCOEF, ELEVUNIT, POLLUTID, TITLE*). Medium.
3. ensemble.run_design (279, CC 43): ~80 lines are docstring; extract the per-row planning loop (lines ~988-1079) into _plan_runs. Otherwise leave.
4. AERSCREENConfig.__post_init__ (235, CC 118): table-drive the "required and > 0 / >= 0 / in [0,1]" checks per source type (~-80 lines).
5. input_reader._parse_output (210, CC 76): leave (each OU keyword has its own continuation rules).
6. AERSCREENConfig.to_aerscreen_input (186, CC 60): leave: reproduces makeinput's FORMATs byte for byte.
7. gui_v2/pages/run.py render (183): split into _checklist_section/_run_section/_log_section; low priority.
8. visualization.AERMODVisualizer.plot_contours (171, CC 22): extract the gridding into the shared _interpolate (C5); leave the plotting.
9. ControlPathway.to_aermod_input (166, CC 59): extract the chemistry/background block (OZONE*, NOX*, O3SECTOR) into a helper; leave order.
10. AERSCREENConfig.from_aerscreen_input (165, CC 51): leave (inverse of 6).
11. gui_v2/files.import_controls (163): move _on_upload and the recent-files list to module level; low priority.
12. input_reader._parse_receptors (155, CC 52): leave.
13. AERSCREENConfig.to_stdin_answers (149, CC 66): leave (mirrors AERSCREEN's prompt sequence).
14. AERMODRunner.run (146): shrinks with run_captured (C3); leave the wasm branch.
15. geospatial.sources_to_geodataframe (136): replace geometry with footprints (A1/C1): ~35 lines.
16. kmz_export.to_kmz (134): sources via footprints; split the three folder writers.
17. AERSURFACEConfig.__post_init__ (133, CC 37): table-drive like 4.
18. AERSCREENRunner.run (128): C3.
19. AERMAPRunner.run (127): C3.
20. OutputPathway.to_aermod_input (127, CC 33): leave.
Also CC>=35 but short: Validator._validate_output_files (CC 44), project_io._Decoder.value (CC 37), AERMAPOutputParser.parse_receptor_output (CC 34): leave (type dispatch / fixed formats).

## Ranked top 10 ((lines removed x clarity) / risk)

1. D1 delete 7 __main__ demo blocks: -330 lines, low risk.
2. A1/C1 geospatial + KMZ sources through footprints.source_footprint: -85 lines and fixes a still-open Medium bug, low-medium risk (add a geometry test).
3. C2 drop _form's string-annotation parser via project_io hints, reuse in browser schema: -150 lines, low risk (verified identical kinds).
4. C3 one find_executable + run_captured for 5 runners and both GUIs: -100 lines, fixes A3 and AERMAP timeout drift, low-medium risk.
5. D2 + D3 api.py always-true flags, dead privates, no-op decorator, api.core doc: -80 lines, low risk.
6. A2 quote blank file names in the writer; delete browser._quote_blanks; one unquote helper: -30 lines and fixes a pip-GUI failure, medium risk.
7. C4 table-driven SRCPARAM in the reader: -100 lines, medium risk.
8. AERSCREENConfig/AERSURFACEConfig __post_init__ table-driven checks: -120 lines, low-medium risk.
9. G3 readiness.review(extra=...) replaces browser's checklist merging: -35 lines, low risk.
10. G1 UI-free gui_v2/catalog.py for registries the browser needs (+ G2 Advanced split in browser editor): ~0 lines, high clarity, low risk.
Then: C5 small table dedups (-60), D4 at 3.0 (-120).

## Tempting, leave alone

- One declarative keyword schema for writer, reader, validator and docs: the reader is deliberately AERMOD-faithful per keyword (continuations, ID ranges, verbatim preservation, order rules); a framework would be larger than the code it replaces.
- Unifying the four `_num` formatters (pathways.py:164, receptors.py:33, aermet.py:69, aerscreen.py:1264): each targets a different Fortran reader (STODBL exponent limits, AERMET list-directed reads without exponents, AERSCREEN checkanswer).
- A base/mixin dataclass for the repeated source fields (source_groups, urban, deposition triple, building_*): inherited fields come first in __init__ and dataclasses.fields(), which changes positional constructors and GUI field order; kw_only changes the signature. Only at a major version, if at all.
- aermap._grid_lines vs receptors' GRIDCART/GRIDPOLR writer: AERMAP and AERMOD syntax differ (no ELEV/HILL rows, ORIG for a source). Keep separate.
- Merging visualization/advanced_viz, aerscreen/aerscreen_runner, naaqs/design_values, terrain/terrain_utils, moving project_io out of gui_v2: public, documented import paths for no line savings.
- Validator isinstance dispatch -> registry: small gain, churn in a 2,600-line module.
- Migrating every HAS_* try/except to _optional: ~20 lines, tests patch the flags.

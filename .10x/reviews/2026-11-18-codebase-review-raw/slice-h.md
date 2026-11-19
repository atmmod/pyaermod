# slice-h findings (ensemble, api, cli, __init__, aerscreen, aersurface, bpip, prime, receptors, met_ingest, met_qaqc, source_importers, hourly_emissions, epa_*, _optional)

Repro scripts: .../scratchpad/repro/slice-h/t1..t11.py (python = scratchpad venv). Paths below are under <repo>/src/pyaermod/.
Ran: tests/test_aerscreen_known_answers.py, test_bpip_known_answers.py, test_hourly_emissions.py, test_cli.py (160 passed, 23 skipped).

Not done: BPIP-PRIME and AERSCREEN Fortran are NOT in the repo (aermod/ holds only AERMOD v26135 source; bin/ has no bpipprm/aerscreen), so BPIP geometry and AERSCREEN prompt order are PLAUSIBLE only (the known-answer tests pass and reproduce EPA's decks/outputs, which is strong evidence). No real AERSCREEN/BPIP binary run. aerscreen_runner.py, aersurface_runner.py not read. Real DSI-6405 / IGRA v2 sample files not available, so those two parsers are PLAUSIBLE.

Earlier reviews (2026-11-11, 2026-11-17): neither lists anything in this slice. Only stale item: PLAN-code.md line 8 (see S-H12).

Counts: BUG 9 (0 high, 5 medium, 4 low), CONCISION 7, DOCS 3.

## Bugs

### H-1 [BUG] [medium] prime.gep_from_building overstates GEP: directions where the stack is outside the influence zone are scored as L = building height
- Where: prime.py:73-83 (also drives assess_source_downwash 168-199 and apply_bpip_to_project)
- What: it takes `calculate_all().buildwid` and maps every width of 0 (BPIP's "stack not influenced in this direction", bpip.py:300-302) to `gep_stack_height(bh, bh)`, i.e. L = BH, the largest possible value. The max over 36 directions is then dominated by the zero directions. bpip.py already computes the right number (`BPIPCalculator._gep()`, the quarter-degree sweep, verified against EPA output) and prime ignores it.
- Evidence: VERIFIED (t1.py, t11.py). 10x10 m building, BH 60, stack 12 m east: `_gep()` = 80.9 m, gep_from_building = 150.0 m. BH 30, same footprint, stack 20 m east, stack height 70 m: BPIP-style GEP 48.9 m (65 m with the regulatory floor), assess_source_downwash says gep 75.0, is_below_gep True, "stack below GEP, downwash must be modeled". So apply_bpip_to_project writes 36-sector arrays on a stack that is exempt under 40 CFR 51.100(ii), and suggest_downwash_config issues wrong warnings. Stack 100 m away (never influenced): `_gep()` is None, gep_from_building still 150.
- Fix: `gep = BPIPCalculator(...)._gep(); return max(GEP_FLOOR_M, gep[0]) if gep else GEP_FLOOR_M` (make `_gep` public as `gep_stack_height()` on the calculator). Same change shortens assess_source_downwash (it builds three calculators per building).

### H-2 [BUG] [medium] met_qaqc.run_all_qaqc cannot be used on read_surface_file output, which is the documented workflow
- Where: met_qaqc.py:137-244, 251-296 (field names and units); aermet.py:976-996 (the producer); docs/aermet-tuning-guide.md:81-100 and 160-165 (the workflow, and an admission that it does not work)
- What: qaqc looks up `wind_speed_ms, wind_dir, temp_c, mixing_height_m, ustar, monin_obukhov_m, convective_mix_height_m/zic, mechanical_mix_height_m/zim` (ISD-style names, temperature in deg C). `read_surface_file` returns `wind_speed, wind_dir, temp (K), Zic, Zim, L, ustar`. The guide says "reports every field as missing; until the two agree, rename the columns", but the same guide's "Recommended workflow" ends in `if report.n_errors: raise SystemExit(report.dump())`, which always fires. Renaming alone would still fail: SFC temperature is kelvin (280 K > 60 deg C limit, error), and AERMET's missing sentinels (-999, 99, 999) are not None.
- Evidence: VERIFIED (t6.py). 24 valid SFC-style rows give "24 records, 24 missing (100.0%), 3 errors, 2 warnings" and "no valid wind_speed_ms records present".
- Fix: add a `_get(r, *names)` lookup with the SFC names, convert K to deg C when the SFC key is the one found, and treat AERMET missing codes as None; or add `qaqc_records_from_sfc(df)` and call it in the docs. Then delete the "currently reports every field as missing" paragraph.

### H-3 [BUG] [medium] from_shapefile silently uses defaults when attribute columns are truncated, and passes NaN through
- Where: source_importers.py:60-72, 200-213
- What: (a) Esri shapefiles truncate column names to 10 characters, so `emission_rate` is stored as `emission_r`, `stack_height` as `stack_heig`, etc. `_kwargs_from_record` drops unknown columns without a word, so every imported source gets the dataclass default (emission_rate 1.0, stack_height default). (b) `v is not None` does not screen NaN, so a null in a numeric column becomes `nan` in the source. (c) the CRS is never inspected: a lon/lat layer (EPSG:4326) yields sources at x=-84.5, y=33.7 with no warning (AERMOD needs metres).
- Evidence: VERIFIED (t3.py, t4.py). Round trip through .shp: columns come back as `['source_id','emission_r','stack_heig',...]`; both sources have emission_rate 1.0. With `attribute_map={"emis":"emission_rate"}` a null gives `nan`. EPSG:4326 point accepted as (-84.5, 33.7).
- Fix: in `_kwargs_from_record` skip `pd.isna(v)`; in from_shapefile, (1) match truncated names by `field_name[:10]`, (2) `warnings.warn` listing columns that matched no field, (3) raise or warn when `gdf.crs is not None and gdf.crs.is_geographic`.

### H-4 [BUG] [low] source_importers: multi-vertex lines collapse to a chord; z_as_height ignored except for POINT; circles lose 2.6% area
- Where: source_importers.py:106-122 (lines), 292-293 (z), 328-337 (circle)
- What: an L-shaped polyline imports as one diagonal LineSource from first to last vertex (documented in a comment, silent to the user). `z_as_height` is documented as using "each entity's z elevation (or polyline's const_z)" but only POINT handles it. A DXF CIRCLE becomes a 16-gon (area 0.974 of the circle) in an AreaPolySource, whose emission is per unit area, so the total emission is 2.6% low; AreaCircSource exists and is exact.
- Evidence: VERIFIED for z_as_height (t5.py: lwpolyline with elevation 12, `z_as_height=True` gives release_height 2.0 = the sentinel); chord VERIFIED by t3.py (LineString of 3 vertices gives x_end=10,y_end=10); circle READ.
- Fix: one LineSource per segment (or warn when len(coords) > 2); implement z for LINE/POLYLINE/CIRCLE or fix the docstring; map CIRCLE to AreaCircSource.

### H-5 [BUG] [low] CartesianGrid.from_bounds drops the last row/column through float truncation, and divides by zero
- Where: receptors.py:141-142
- What: `int((x_max - x_min) / spacing) + 1`. (0.3-0)/0.1 = 2.9999999999999996, giving 3 points instead of 4. A range that is not a multiple of spacing stops short of x_max (0..1000, 0..950 at 100 gives y ends at 900) without saying so. spacing=0 raises ZeroDivisionError; x_max < x_min gives x_num <= 0.
- Evidence: VERIFIED (t1.py): from_bounds(0,0.3,0,0.3,spacing=0.1) gives x_num=3, y_num=3; spacing 0 raises ZeroDivisionError; reversed bounds give x_num=0.
- Fix: `round((x_max-x_min)/spacing + 1e-9)`-style floor with tolerance, validate `spacing > 0` and `x_max >= x_min`, document that the grid ends at or before the bound.

### H-6 [BUG] [low] run_design: build_fn gets a shallow copy of the factors, so a nested value it mutates changes the run ID and the caller's rows
- Where: ensemble.py:989 (`build_fn(dict(factors))`), 1017 (run_id(factors,...) computed after build_fn), 1074 (`dict(factors)`)
- What: `dict(factors)` copies only the top level. A build_fn that appends to a list or dict factor changes the object that is then hashed and stored as `entry.factors`, and also mutates the caller's `rows`.
- Evidence: VERIFIED (t7.py, real aermod): row `{"tags": ["a"]}`, build_fn does `f["tags"].append("mutated")`; afterwards `rows[0]["tags"]`, `entry.factors["tags"]` and `DesignRun.factors["tags"]` are all `['a','mutated']`, and the run ID hashes the mutated value. Deterministic mutation still resumes, but a conditional mutation silently yields a different ID from the row the user wrote.
- Fix: `rid = run_id(factors, ...)` is fine once the argument is `copy.deepcopy(factors)`: `project = copy.deepcopy(build_fn(copy.deepcopy(factors)))`. Document that factors are copied.

### H-7 [BUG] [low] met_ingest.parse_asos_1min_line and parse_igra_v2 are written against invented line layouts (PLAUSIBLE)
- Where: met_ingest.py:44-51 (regex), 308-378 (IGRA)
- What: ASOS: the regex needs literal `KT` after the speed and the 8+4 digit timestamp separated from WBAN/call sign by whitespace; the tests use a made-up line ("... extra 180 005KT"). I believe real DSI-6405 records carry wind direction and speed as plain numbers with no unit text; PLAUSIBLE, no real sample on disk. IGRA v2 level records are fixed-width (LVLTYP1 col 1, LVLTYP2 col 2, ETIME 4-8, PRESS 10-15, PFLAG 16 ...), so LVLTYP1 and LVLTYP2 are adjacent with no space; the parser assumes `toks[3]` is pressure, which is only right if the two type digits were separate tokens. The fixture `_IGRA_SAMPLE` is hand-written. Also -8888 (value removed by QA) is not treated as missing, and `len(parts) < 8` followed by `parts[8]` can raise IndexError (not caught, only ValueError is) for an 8-field ISD-Lite line.
- Evidence: PLAUSIBLE (no real sample files in repo); the IndexError is READ.
- Fix: test against one real DSI-6405 line and one real IGRA v2 sounding (public, small); parse IGRA by column slices; change the guard to `len(parts) < 9`.

### H-8 [BUG] [low] BPIP tiers: pyaermod's "coverage-weighted height" can under-predict the controlling height (PLAUSIBLE)
- Where: bpip.py:116-134 and 218-228
- What: `get_effective_height` averages tier heights by coverage fraction. A 60 m tower covering 10% of a 20 m building becomes 24 m, whereas EPA BPIP evaluates each tier and uses the controlling one per direction (the module's own warning says so). Averaging is non-conservative: downwash is under-predicted for the tall tier. The warning is raised at calculator construction (`stacklevel=2`), so it is visible, which limits severity. No BPIP source in repo, so the tier claim is PLAUSIBLE.
- Fix: use max(tier heights) for the height (conservative) or evaluate tiers separately; at minimum say in the Building docstring that the average is not conservative.

### H-9 [BUG] [low] cli: no error handling, raw tracebacks for the commonest mistakes; `profile` prints a KeyError repr
- Where: cli.py:78-94, 97-132, 180-205, 271-274
- What: `pyaermod validate missing.inp`, `profile missing.inp --profile x`, and `run x.inp` with no aermod on PATH (AERMODRunner constructor raises) all end in a traceback (exit 1). Only the unknown-profile case returns a clean 2, and it prints `Unknown profile: 'bogus'` (the KeyError repr, with quotes). Exit codes are inconsistent: validation errors from `run` return 2, from `validate` 1, AERMOD failure returns AERMOD's own code (can be negative or above 255, which the shell folds).
- Evidence: VERIFIED (t8.py: FileNotFoundError propagates from `main`).
- Fix: in `main`, catch `(OSError, ValueError, KeyError, RuntimeError)` from `args.func`, print `pyaermod: error: <msg>` to stderr, return 2; `return min(run_result.return_code or 1, 255)`.

## Checked and found correct (no finding)
- ensemble.py: deep copy of the project (989), per-run directories, output-name rewriting, resume rule (`_is_done`), process-pool failure path, manifest writes only from the parent process. No seeds are used. n_workers=1 runs in-process; workers rebuild the runner, so no shared mutable state. Real-aermod run in t7.py succeeded and resumed.
- hourly_emissions.py: record layout checked against aermod.f HRQREAD (fields 3-6 date, 7 source ID, 8 rate; 7 fields = W344; year 2 or 4 digits both read; source ID cut at 12). `_read_sfc_hours` field indices match metext.f as cited.
- receptors.py GDIR/DIST/DDIR field order against reset.f GENPOL (count, init, delta). Polar directions are clockwise from north, as AERMOD expects.
- bpip.py rotation: flow-vector convention (the angle is where the flow goes, not the meteorological "from" direction) is consistent with the known-answer tests; the BPIPResult docstring calls it "wind directions", which a reader may take for met-from (see H-D3).
- aerscreen.py: the PLAN-code.md "deck writer emits a format the interactive program never reads" defect is FIXED at HEAD: `to_stdin_answers()` (prompt answers) and `to_aerscreen_input()` (`**` header restart file) replace the KEY: value deck, and tests/test_aerscreen_known_answers.py round-trips EPA's decks. PLAUSIBLE only for the prompt order, since AERSCREEN.FOR is not in the repo; tests/test_real_aerscreen.py needs a binary I do not have (skipped).
- api.py contains no functions, only re-exports, so there are no convenience-function defaults to disagree with the dataclasses (`run_aermod` is in runner.py:1835, defaults match AERMODRunner.run).

## Concision

### H-C1 [CONCISION] dead code in __init__.py: `_check_dependencies`
- Where: __init__.py:61-84 (24 lines)
- What: never called anywhere in src/ (grep); only tests/test_init.py exercises it, so the ImportWarning it describes is never emitted at import. Its docstring also points to `HAS_GEOSPATIAL`.
- Change: delete the function and its tests (or call it, if the warning is wanted). Saves about 24 source lines plus its tests.

### H-C2 [CONCISION] `_make_line` has identical if/else branches
- Where: source_importers.py:113-122 (+ the `RLineSource` import at line 41, used only there)
- Change: replace with the four `setdefault` lines; saves 7 lines and one import. Covered by tests/test_source_importers*.py.

### H-C3 [CONCISION] the same legacy-keyword shim is written twice
- Where: aerscreen.py:162-196 and 1280-1292; aersurface.py:41-97 and 424-436
- What: `_RENAMED_FIELDS`, `_REMOVED_FIELDS`, `_reject_legacy_kwargs`, `_generated_init` wrapper, identical except for the class name. About 110 lines in total (aersurface's prose tables are 57 lines).
- Change: one `_legacy.py` with `install_legacy_check(cls, renamed, removed)`, leaving only the two tables in each module (about 35 lines saved). Or drop the shims: the AERSURFACE one dates from 2026-08, three months ago, and the failure they replace is a bare TypeError. Covered by test_aerscreen.py, test_aersurface.py legacy tests.

### H-C4 [CONCISION] aerscreen.py: about 40 `assert x is not None` lines exist only to narrow types for mypy
- Where: aerscreen.py:534-538, 569-570, 639, 680, 739-741, 748, 752-753, 757-758, 762, 775-776, 789-794, 837-838, 842, 845, 854, 895, 898-899, 910, 917-918, 927, 935-936, 1050, 1054-1055, 1066
- Change: validate once in `__post_init__` and have `to_stdin_answers`/`to_aerscreen_input` read through a small `_req(self, name)`, or split the per-type geometry into three small helpers; saves about 35 lines without changing behaviour. The file's size (1436 lines) is mostly docstring and EPA-format fidelity; the writer, parser and output parser are each needed. Covered by test_aerscreen.py and the known-answer round trip.

### H-C5 [CONCISION] two copies of the AERMOD version-banner reader
- Where: ensemble.py:142 (`_VERSION_BANNER`) and 781-796 (`_aermod_version`); epa_testcases.py:61-62, 134-168 (`read_aermod_version`)
- Change: ensemble should call one shared function (aermod_outputs already has `parse_aermod_header`); saves about 16 lines. ensemble's regex accepts any version text, epa_testcases only 5 digits, so unify on the looser one.

### H-C6 [CONCISION] developer-only modules shipped in the wheel
- Where: epa_sources.py (145 lines), epa_testcases.py (319 lines)
- What: nothing in src/ imports them (grep); consumers are tests/, scripts/build_*.sh and scripts/run_epa_parity.py. They are not in api.__all__.
- Change: move to `tests/_epa/` (or scripts/) and update the importers: 464 lines out of the installed package, no feature lost. Docstrings and tests/test_epa_*.py move with them. Note epa_testcases imports pyaermod.versions, which stays.

### H-C7 [CONCISION] optional-dependency guards that `_optional.py` should own
- Where: source_importers.py:192-198 and 263-269; met_ingest.py:29-34 and terrain.py:23-30 (`requests` + `_require_requests` + `HAS_REQUESTS` written twice); __init__ imports `api` twice (`from . import api` and `from . import api as _api`, __init__.py:42-43)
- Change: `gpd = require(optional_import("geopandas"), "geopandas", pip_extra="geo")` (and ezdxf, "cad") replaces two 7-line try/except blocks (saves about 10 lines); one shared `requests` handle in `_optional.py` for met_ingest/terrain (saves about 6). Other modules (visualization, advanced_viz, geospatial, kmz_export, runner) still use bare try/except ImportError, about 20 more lines for another slice to convert. Drop the unused `_api` alias (1 line). Covered by tests/test_optional_helper.py, test_met_ingest.py, test_terrain.py. Also dead in met_ingest.py:370-376: `None if press == -9999 else press` after `_int_or_none` already mapped -9999 to None (5 comparisons, 0 effect).

## Docs

### H-D1 [DOCS] [low] api.py module docstring promises things that do not exist
- Where: api.py:11-14 and 472-476, 502-504
- What: "the ``pyaermod.api.core`` submodule" does not exist (api is a module, not a package; grep finds no `core`); "the CLI" is listed among core names, but CORE_NAMES has no CLI entry; "across every 1.x release" in a 2.3.0 package; "~30 names" is 31. `API_VERSION = "2.0"` is only read by one test.
- Fix: delete the `api.core` sentence, say 2.x, drop "the CLI".

### H-D2 [DOCS] [low] `__version__` has three sources and one is unchecked
- Where: pyproject.toml:9, __init__.py:27, api.py:39
- What: tests check CITATION.cff against `pyaermod.__version__` (test_citation.py) but nothing compares `api.__version__` or pyproject with it; test_api_surface.py:65 only asserts it is a non-empty string.
- Fix: delete the literal from api.py (`from . import __version__` would be circular, so instead keep it in api.py and have `__init__` do `from .api import __version__`), and add a test that pyproject's version equals it. Saves a line and closes the drift.

### H-D3 [DOCS] [low] BPIP direction convention is stated ambiguously; PLAN-code.md still lists the fixed AERSCREEN defect
- Where: bpip.py:168-173 (BPIPResult: "wind directions 10..360 (measured clockwise from north)") vs 252-266 (the angle is where the flow goes); prime.py:112-130 passes a meteorological "from" direction to `_calculate_for_direction` after converting it for its own dot product with `270 - wd`, but hands the raw angle to the calculator, which expects the flow direction. For a symmetric footprint the width is the same for both, so no visible error (t2.py), but for an L-shaped footprint or a stack near the zone edge in_cavity_region can differ. PLAN-code.md:8 says "One acknowledged defect exists: the AERSCREEN deck writer emits a format the interactive program never reads"; that was fixed (module docstring of aerscreen.py, known-answer tests).
- Fix: say "flow-vector direction (the direction the wind blows toward)" in BPIPResult and `_calculate_for_direction`'s caller docs, convert in `in_cavity_region` (`(wd + 180) % 360`), and update PLAN-code.md.

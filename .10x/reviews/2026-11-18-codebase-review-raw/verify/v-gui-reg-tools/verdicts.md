# Verdicts: v-gui-reg-tools

All tests are in this directory (scratchpad/verify/v-gui-reg-tools/). GUI tests import `from tests import ...`, so run them with
`PYTHONPATH=<repo>`, or move them into tests/ and switch to relative imports. Every test below FAILS at HEAD
for the stated reason. Nothing under the repo was changed (one stray copy of my G1 test was made in tests/ by mistake and deleted at once; git status was clean afterwards).
Note: the checkout HEAD is 2e7d26d, not 794fe60; the code I read matches the reviewers' citations.

## Baseline failures
- tests/test_browser.py::test_without_aermod_the_checklist_says_the_build_did_not_load: NON-HERMETIC TEST. browser.py:364 decides
  "has AERMOD" with `shutil.which("aermod")`; the test assumes none is installed. With PATH=/usr/bin:/bin it passes; with ~/bin/aermod on PATH it fails.
  Fix: monkeypatch `shutil.which` (or PATH) in the test.
- tests/test_gui_v2_project_io.py::TestValuesAreChecked::test_a_deeply_nested_document_is_refused: PYTHON-VERSION DIFFERENCE (test brittleness, not a product bug).
  `json.loads("["*100000+"]"*100000)` raises RecursionError on 3.11 but parses on 3.15 (3.15 allows a deeper C stack; it still raises at 1e6). On 3.15 the
  document is parsed and project_io then reports "project must be a JSON object", so project_io.py:480's RecursionError handler is never reached.
  The handler still works when nesting exceeds the limit. Fix: nest deeper (e.g. 5_000_000 is too slow; build the deep value in Python and call `_encode`), or pin the test to what it tests.

## gui-code (gui_v2)
| ID | Verdict | Test |
|---|---|---|
| G1 | CONFIRMED | test_gui_replace.py (3 tests: read by path, upload, recent file; each ends with the project replaced and no confirm-dialog) |
| G2 | CONFIRMED | test_gui_plan_view_big.py (4e6 Cartesian points take 1.9 s; polar 4e6 likewise; bound 0.5 s) |
| G3 | CONFIRMED | test_gui_readiness_agree.py (absolute missing profile: header red, review().ready True; relative files existing in working dir: header "Not ready ... 2 problems", review ready) |
| G4 | CONFIRMED (mechanism; window narrow in the live GUI) | test_gui_run_dir_reuse.py |
| G5 | CONFIRMED | test_gui_form_vertices.py (`_parse_pairs("100 200\n...") == []`, also the deck's own AREAVERT text) |
| G6 | CONFIRMED | test_gui_editor_persistent.py (source and receptor editor dialogs lack the `persistent` prop) |
| G7 | CONFIRMED (fix design is a judgement) | test_gui_fork_run.py |
| G8 | CONFIRMED | test_gui_temp_run_dirs.py |
| G9 | CONFIRMED for downloads; KMZ part READ only | test_gui_download_loop.py (one download blocks the loop 0.51 s when hashing is slow) |
| G10 | CONFIRMED (wording is the maintainer's) | test_gui_naaqs_background.py |

G1: files.py `_import_path`/`_on_upload`/`_reopen` call session.import_inp/open_json directly; project.py's `_asked_before_replacing` is applied only to New/Open. Blast radius: `import_controls` needs the page's FileActions; existing tests that import over a dirty project (test_gui_v2_files.py, e.g. the Recent files and Import tests that click project-new first) may then see a confirm dialog and need `_discard_changes`. After an import the project is dirty, so a second import asks.
G2: `_receptor_items` (plan_view.py:146) calls footprints.receptor_points, which expands every point. My test asserts the plan view takes under 0.5 s and (cartesian) still states "4000000 receptors"; a fix that samples by stride must still report the true count. Blast radius: plan_view tests that count drawn marks (MAX_POINTS) and the description text.
G3: both headers must agree; Validator(check_files=True) resolves relative met paths against the server's cwd (validator.py:2078-2088). Fix touches Session.validate and readiness.review; the second test needs working-dir-aware resolution in the validator call.
G4: In the real app Results subscribes at page build, so the build starts at RUN_FINISHED and the race needs Run to be clicked again before the files are hashed (long for multi-GB POSTFILEs). The test calls `view_of(run1)` after run 2 started, which is the deterministic variant (page not alive at RUN_FINISHED). Fix options: snapshot the deck text in RunRecord, or build the view eagerly in `_finish_run`.
G5: the second half of the reviewer's finding (`_parse_numbers("1,5")`) is ambiguous (a comma could be a decimal comma); I wrote no test for it. A message on unparsable lines is not tested.
G6: NiceGUI 4.0.0 dialog.py docstring: "By default it is dismissible by clicking or pressing ESC. To make it persistent, set .props('persistent')". Quasar default is non-persistent; no gui_v2 code sets it (grep). The simulated user cannot click a backdrop, so the test asserts the prop. Blast radius: none for tests (Close/Save buttons still work); Esc no longer closes either editor.
G7: PLAN-gui.md line 66 documents "A desktop reload forks the session" but not the lost run. The test asserts only that the fork knows about the run (`run_in_progress is not None`); a fix may instead adopt the session. For a duplicated browser tab keeping the run only on the original is defensible.
G8: deleting a tmp dir on New/Open means downloads of the discarded run are gone; that matches "the runs of this project are lost" in the confirm text. The test asserts removal after `Session.new()`. Shutdown-hook cleanup is not tested.
G9: one `hashlib.sha256` is slowed to 0.5 s; HEAD hashes in `RunFile.read` on the loop. Note the Run step also has a "Download deck" button, so a test must click a Results-only label. `ui.download(path)` streams from disk; the stale-file check must then be a chunked hash in a worker. KMZ: READ only (pyproj needed), same pattern (`_kmz_bytes` on the loop).
G10: the test only requires the word "background" in the NAAQS table row or any label. Wording, and whether the verdict should change when sources.background exists, is the maintainer's.

## slice-f (regulatory post-processing)
| ID | Verdict | Test |
|---|---|---|
| F2 | CONFIRMED | test_chemistry_presets_save.py (SO2 and PM25: `check_project` raises "deposition_method must be a JSON list") |
| F3 | CONFIRMED (the Fortran backs the reviewer; one partial mitigation exists) | test_design_values_met_year.py |
| F4 | CONFIRMED | test_design_values_nan_and_names.py (`get_naaqs("PM25")`, `naaqs_output_pathway("PM25"/"pm25")` raise KeyError) |
| F5 | CONFIRMED | same file (359 instead of 358; rank-1 returns NaN) |
| F6 | PARTLY: the Fortran fact is right; block-vs-rolling is policy, so no test; the missing `ave` check is a test | test_design_values_o3_ave.py |

F2 blast radius: the reviewer says "delete the two assignments if nothing else reads the field", but `chemistry_presets.py:281` (`validate`-style check at ~269-287) reads `deposition_method` to warn about "deposition_method set but no gas/particle params", and `PollutantDepositionDefaults.method` is public. Safer fix: set `(method, 1.0)`-style tuple or leave it None; check the tests of apply_deposition_defaults.
F3 Fortran: meset.f:1128-1139 sets IENDMN/IENDDY/IENDHOUR from the first met hour (the day before the first hour's anniversary; IENDHOUR = ISHR-1, or 24 with the previous day); aermod.f:8028-8077 CHK_ENDYR increments NUMYRS when IMONTH==IENDMN, IDAY==IEND_DAY, IHOUR==IENDHOUR; aermod.f:987-998 averages by SUMHNH/NUMYRS. So AERMOD's year is the met year, not the calendar year. Reviewer is right. What is already there: `_average_across_years` warns "defined over N years but the input covers M" (a Jul-Jun single year with n_years=1 does warn, and the PM10 path, which infers n_years from the data, gives no warning and reports 5 years for 4). My test accepts either the one-year value (358) or a warning containing "partial", so either fix passes. A year-boundary parameter is a public API addition (maintainer decides).
F5 numbers: with day 11 NaN, 364 valid days, the 8th highest is 358; HEAD returns 359 (the NaN counts as top rank and in the day count). The reviewer's printed "expect ... 357" label is a typo; the value 358 in the prose is right.
F6 Fortran: aermod.f:1853-1855 `IF (MOD(IHOUR,KAVE(IAVE)).EQ.0 ...) CALL AVER`: IHOUR is the hour of the day (1-24), so an 8-HR average is formed at hours 8, 16 and 24 only: three fixed blocks per day, not 24 running means. Reviewer is right that the docstring ("rolling-average") is wrong and that the max of blocks is at most the max of the running means. Appendix U calls for running 8-h averages: that the code should or should not rebuild them from 1-HR output is a policy judgement, so no test pins it. test_design_values_o3_ave.py only asserts that 1-HR rows are not silently treated as 8-HR averages (ValueError or warning), which does fail today.

## slice-h
| ID | Verdict | Test |
|---|---|---|
| H-1 | CONFIRMED | test_prime_gep.py |
| H-2 (and DOCS-1) | CONFIRMED | test_met_qaqc_sfc.py |
| H-3 | CONFIRMED (all three parts: truncated names, NaN, CRS) | test_source_importers_shapefile.py |

H-1 evidence: 10x10 m building, BH 60, stack at x=12: `BPIPCalculator._gep()` 80.9 m, `prime.gep_from_building` 150.0 m. 10x10, BH 30, stack at x=20: _gep 48.9 (65 with the floor), prime 75.0. Same building, stack at x=100 (outside every zone): _gep None, prime 75.0 (should be the 65 m floor). 40x40 m, BH 10, stack at x=10 and x=40: both give 65 (agree). Formula check (40 CFR 51.100(ii), from memory, not the eCFR text: Hg = H + 1.5 L, L the lesser of the building's height and projected width, for structures within 5L of the stack, minimum 65 m): for a 10 m square the projected width is at most 14.1 m, so L <= 14.1 and Hg <= 81.3 m; 150 m would need L = 60 m. `_gep` applies the 5L zone (`_in_gep_zone`, SIZ_DOWNWIND_L) and is the right one. prime treats a width of 0 (BPIP's "not influenced") as L = BH, the largest value. Blast radius: tests/test_prime_extended.py::TestGEPPerDirection and tests/test_prime.py use a stack at the building's centre (0,0); with the fix _gep(0,0) is 51.2 m for a 10x10 BH30 so those cases still give the 65 m floor or the wake height, but check `test_gep_uses_max_per_direction` (expects >= 75 for a 100x20 BH30 building with the stack at the centre). `assess_source_downwash` and `apply_bpip_to_project` change for stacks outside the zones (less downwash applied). Public behaviour change by design.
H-2: records from `read_surface_file(HOUSTON_0228.SFC)["data"]` give "4 records, 4 missing (100.0%), 3 errors". The test asserts `n_missing == 0` and no low_wind finding. The fix must convert K to deg C and treat -999/99/999 as missing, or the 280 K temperature will hit the 60 deg C limit (not covered by my test beyond n_missing). The docs paragraph at aermet-tuning-guide.md:97-100 and the workflow's `raise SystemExit` are wrong until then.
H-3: shapefile with `emission_rate`, `stack_height`, `exit_velocity`, `stack_diameter` written by geopandas comes back with 10-character names; the source gets emission_rate 1.0 and stack_height/exit_velocity/stack_diameter 0.0. A NaN (from a null) reaches the source. An EPSG:4326 layer imports as x=-84.5 without a word. The tests accept either a ValueError or a warning for the NaN and CRS cases.

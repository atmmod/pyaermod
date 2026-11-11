# Codebase review, 2026-11-11 (pyaermod at e449a6b)

Four parallel reviewers (gui_v2; runner + wasm + CI; deck read/write/validate; outputs + regulatory post-processing), read-only.
Test subsets run by reviewers: runner/wasm 257 passed; input/reader/validator 942 passed; output/postfile/design/naaqs 908 passed.
"Verified" = reproduced with a script (repro scripts in the session scratchpad, not committed) or re-checked by the orchestrator; "read" = from code reading only; "PLAUSIBLE" = not confirmed against EPA source or CFR text.

## High
| # | Area | Location | Defect | Status |
|---|---|---|---|---|
| H1 | GUI | gui_v2/plan_view.py:65-73 | `_ticks` loops forever when y0==y1 after rounding at large coordinates (e.g. source at y=1e18); freezes the NiceGUI event loop for every connected user | verified (timeout) |
| H2 | Reader | input_reader.py:1077-1102, sources.py:1675-1691, validator.py:367-374 | BACKGRND keeps one value after the temporal flag (SEASON 1 2 3 4 -> SEASON 1); continuation lines become bogus entries; validator rejects valid SEASON decks | verified |
| H3 | Reader | input_reader.py:1088-1093, 1566-1574 | Sector-dependent HOURLY background silently dropped (background=None, unparsed_lines empty) | verified |
| H4 | Reader sandbox | input_reader.py:236, 2350-2361 | Quoted paths ("../../etc/passwd") pass sandbox=True; AERMOD strips the quotes | verified |
| H5 | Reader | input_reader.py:1836, pathways.py:1037 | PROFBASE units dropped: 328 FEET rewritten as 328 METERS | verified |
| H6 | Design values | design_values.py:671-675 | NO2 annual DV averages annual means across years; 40 CFR 50.11(b) is a single-calendar-year annual mean. Policy check needed: confirm the form EPA modeling guidance expects for multi-year met | read; regulatory form needs maintainer confirmation |

## Medium
- GUI: run N's Results can read run N+1's files when the working dir is reused (run_results.py:699-710, pages/run.py:532); Session.fork drops the in-progress run (session.py:1045); Import deck / reopen recent replace the project without the unsaved-changes prompt (files.py:287-341).
- Runner/wasm: explicit wasm path silently ignored when missing (wasm_runner.py:108-124, verified); `aermod-wasm` unregistered on PyPI while notebooks `%pip install aermod_wasm` with PyPI fallback enabled (squat risk); docs.yml PR runs share the `pages` concurrency group with main deploys.
- Reader: quoted filenames with spaces truncated/corrupted on rewrite (verified); crashes instead of errors on SURFDATA 14735.0, alphanumeric station IDs, bare HALFLIFE, Latin-1 bytes (verified); case-sensitive source IDs/pathways (verified); LOW_WIND keeps first field (verified); CO ELEVUNIT written (read); NO2STACK 0.5 invented on OLM decks with only NO2RATIO (verified).
- Post-processing: 24-h and period means from hourly POSTFILE divide by row count, ignoring calm/missing hours (verified per reviewer); AREA polygon export uses centre/half-widths with x/y swapped and CCW rotation, contrary to sources.py's SW-vertex/clockwise contract (read, confirmed by orchestrator); OPENPIT rotation sign reversed (read); contour bands with holes become overlapping polygons (read).

## Low
- GUI: shared ~/.pyaermod/recent_files.json across users in --host mode; mkdtemp run dirs never removed; downloads read whole files on the event loop; project JSON uploads skip the deck sandbox (PLAUSIBLE).
- Runner: lock/link left held when _stage fails; wasm crash loses partial .out; wasm cache keyed only on path; run_batch fails under Pyodide even with n_workers=1; actions pinned by tag; EPA source URL unversioned without checksum; build_aermod_wasm.sh leaves refused builds in $OUT and BUILD.txt hashes never checked.
- Reader/validator: Ts<=0 rejected though AERMOD treats 0/negative as ambient-based (PLAUSIBLE); PARTDIAM written .4g; SURFFILE format field, SURFDATA name/coords and UAIRDATA year lost; 12 background sectors allowed vs 6; TTRM without ozone passes (PLAUSIBLE); hard 100,000-receptor error (PLAUSIBLE); RECTABLE rank rewriting.
- Post-processing: PM10 rank rule hard-coded (conservative); O3 8-h day assignment (rarely used); PM2.5 citation 50.18 vs 50.20 (label); partial calendar years, no rounding before NAAQS check, multi-year PLOTFILE layout, 2017 regulatory profile text (all PLAUSIBLE).

## Pyodide portability (input to browser-gui)
UI-free and reusable: gui_v2/session.py (with background=False runs), project_io.py, steps.py, plan_view.py (after H1 fix), results_map.py, run_results.view_of. Server/thread-bound: run_results.prepare/watch, files.py, pages/*, app.py, desktop.py, CLI main.

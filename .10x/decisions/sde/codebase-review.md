# codebase-review (2026-11-19): what was built

Seven bug-fix PRs from origin/main, one writer per file set, each starting from the verifiers' failing tests:

| PR | Branch | Scope |
|---|---|---|
| #72 | claude/fix-runner-lifecycle | lock release on failed prepare, AERSCREEN stale verdict, AERSURFACE success, process-tree kill, Windows lock retry |
| #73 | claude/fix-geospatial-exports | GIS/KMZ geometry from footprints.py, contour holes, polar origin, DEM .part download, map/plot placement |
| #74 | claude/fix-postprocessing-tools | design-value NaN and name lookups, partial-year warning, O3 8-HR guard, GEP height, met QA on .SFC, shapefile/DXF import, CLI errors |
| #75 | claude/fix-output-parsers | multi-year binary POSTFILE, overflowed rows, real aux-file headings, binary TOXXFILE, .out header fields |
| #76 | claude/fix-validator-aermod-semantics | validator false errors and missing errors vs Fortran, DFAULT/regulatory checks on real switches, 512-char cards |
| #77 | claude/fix-deck-writer-reader | SO ELEVUNIT, URBANSRC areas, BUOYLINE deposition, quoting, atomic write, strict numbers, case, no silent drops, table cards. Merge after #76. |
| #78 | claude/fix-gui-work-safety | both GUIs: unsaved-work prompts, editors, NAAQS verdict wording, one readiness source, per-run decks, plan-view sampling |

## Deviations from the plan
- Seven bug PRs instead of one (file sets too wide for one reviewable PR).
- CHANGELOG and docs are not in the fix PRs; they land in one docs PR to avoid seven-way conflicts.

## Follow-ups created by the fixes
- Call `postfile.warn_hourly_mean_limitation` from design_values.py (after #74 and #75).
- visualization.py plot titles use the job name AERMOD never prints (after #73 and #75).
- E336 validator error for an OLM-family source with no ratio; validate LOW_WIND fields; urban_area_name with several areas (after #76 and #77).
- Delete browser._quote_blanks (after #77 and #78); shared executable finder in runner.py (after #72 and #78).
- Possible GeoJSON export CRS issue under geopandas 0.14 (unverified).
- Slow test tests/regulatory/test_event_rewrite.py fails locally with AERMOD v24142 on PATH; not confirmed on main.

## Tech debt
Simplifications (report section 9) not started: they touch the same files and wait for these PRs to merge.

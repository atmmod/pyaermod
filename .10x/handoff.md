# Handoff (2026-11-20, codebase review of 2026-11-18)

Report: `.10x/reviews/2026-11-18-codebase-review.md`. The raw findings, verifier tests and the three rule-text research
write-ups are on the branch `claude/codebase-review-2026-11-18-4uyhje` only, under
`.10x/reviews/2026-11-18-codebase-review-raw/` (`research-naaqs.md`, `research-appendix-w.md`,
`research-aermod-source.md`). Keep that branch until they are no longer wanted.

To do locally: `.10x/local-verification-prompt.md` (checks that need the AERMOD binaries and EPA Fortran) and
`.10x/branch-cleanup.md` (remote branches to delete, and those that need a decision).

## State (updated 2026-11-20, after the overnight simplification pass)

Merged to main, all on green CI: #72 to #100.

| PR | What |
|---|---|
| #80 | Regulatory text, `EPA_APPENDIX_W_2024`, design values by met year, validator follow-ups |
| #81 | CHANGELOG, archive, housekeeping |
| #82 | Plot title, one AERMOD finder, `browser._quote_blanks` deleted |
| #83 | Five demo blocks deleted (-266 lines) |
| #84 | AERSURFACE keyword checks from one table (-16) |
| #86 | Deck reader: numeric helper, SRCPARAM table, `_parse_sources` split (-88) |
| #87 | GUI forms: string-annotation parser removed (-153) |
| #88 | Runners: `_exec.find_executable` and `run_captured` (-39) |
| #89 | sources.py and pathways.py repeated blocks (-221) |
| #90 | api.py plain imports; `pyaermod info` reports real availability |
| #91 | Validator range checks from rows (-160) |
| #92 | Legacy-keyword shim shared; small reader duplicates (-34) |
| #93 | Fix: `parse_igra_v2` on a missing temperature or wind |
| #94 | GUI: UI-free `catalog.py` and `deck_import.py`, one paged table |
| #95 | geospatial.py: one interpolation fallback, vectorised points |
| #96 | Fixes: animation of zero fields, 3D surface with gaps, shapefile of mixed geometry |
| #97 | This handoff, the review report, the local verification prompt and the branch-cleanup list on main |
| #98 | pytest dumps every thread's stack when a test runs past five minutes |
| #99 | One shapefile per geometry kind for mixed sources (`export_sources_by_kind`; `export_all` splits) |
| #100 | mypy clean: 48 errors fixed, `mypy-baseline.txt` is 0 |

No pull request is open.
- #85 (output parser stops reading the invented report layout, 1,376 to 1,029 lines) merged on 2026-11-20 after the
  maintainer chose to remove the layout and add a warning: a file with no source, receptor or result table now gives a
  `UserWarning`.
- #96 (three crash fixes: animation of zero fields, 3D surface with gaps, shapefile of mixed geometry) merged on
  green CI after this table was written. The maintainer may prefer one shapefile per geometry kind to the clear error
  it raises now.

Review section 9 against results: the estimate was about 2,200 lines; about 950 came out behaviour-preservingly (the sum of the merged PRs, net of the 55 lines #94 added), plus
about 350 more in #85, which is not behaviour-preserving. Items that did not deliver: item 10 (AERSCREEN half reverted, no clearer), item 11
(POSTFILE header sharing changes parsed results; branch `claude/simplify-postfile-header` kept, no PR), item 13's
plotting part (3 lines). `runner.py`'s `__main__` block stays: a test runs it.

Open questions and findings for the maintainer:
- NaN passes the validator's range checks and `None` raises `TypeError` (#91 notes it; unchanged).
- `visualization.plot_contours` interpolates with cubic `griddata` and no linear fallback.
- `create_comparison_grid` fails on all-zero data (`np.min` of an empty selection).
- IGRA: is `-8888` a second sentinel, and are the units tenths? NOAA's format document was unreachable from the cloud.
- The local verification prompt (`.10x/local-verification-prompt.md`) is still to be run: items 1 to 5 test
  assumptions in #80, which is merged.
- **Intermittent CI hang.** `tests/test_ensemble.py` hung twice on the Python 3.12 leg on 2026-11-20 (main at the
  #85 merge, and #97), each time leaving a forked `pytest` child alive, and passed on re-run. Not reproduced in the
  cloud container. Suspect: `run_design`'s `ProcessPoolExecutor` forking a process that has other threads. Since #98
  the job log will hold every thread's stack if it recurs: read that before changing `ensemble.py`. An explicit
  `spawn` context would fix a fork deadlock but makes Linux scripts need the `if __name__ == "__main__":` guard.
- CI jobs were also cancelled that day by slow downloads from the Ubuntu package mirror (20 minutes in "Install
  system dependencies"). That is infrastructure, not the code.
- mypy: `pyaermod.advanced_viz` still has `ignore_errors = true` in `[tool.mypy]`, and strict mode is off.
- Branch cleanup: the cloud session cannot delete remote branches (HTTP 403). The commands and the list of branches
  that need a decision are in `.10x/branch-cleanup.md`.

Cloud container notes: two tests fail there and are not regressions (`test_an_ipv6_host_is_checked_as_ipv6`; and
`test_d5_aerscreen_timeout_kills_the_childs_children`, intermittent). The GUI journeys cannot run there (no Python
`playwright` package); CI runs them. `pip install -e ".[all]"` fails on pywebview; use `.[viz,geo,gui,met,hpc,dev]`.

## The cloud environment lacks
The EPA Fortran (`aermod/`, `aermet/` are gitignored), AERMOD binaries and `test_cases/`. Do not guess what AERMOD does:
the research write-ups quote the routines and lines that matter. CI is the test oracle (Python 3.11-3.13).

## What remains

1. **Run `.10x/local-verification-prompt.md` locally**, where the AERMOD binaries and EPA Fortran are. Items 1 to 5
   test assumptions in #80 (CO LOW_WIND field 7 and ranges, E336, W325, the urban-area message, GRSM with DFAULT).
2. **Branch cleanup:** run the commands in `.10x/branch-cleanup.md` and decide on the branches it lists.
3. **Regulatory forms decided by the maintainer (2026-11-21) and implemented:**
   - annual PM2.5 stays the mean of all rows of the year; the docstring says how Appendix N 4.4 differs;
   - PM10 ranks N+1 by default for N years (H3H to H5H for 2 to 4 years);
   - ozone uses running 8-hour means from 1-hour values (Appendix U 3(b)-(d)); 8-HR blocks still read, with a warning;
   - PM10 stays compared with 150 unrounded;
   - the SO2 secondary annual standard (50.21, 10 ppb) is in the table as `primary=False`, with `"SO2_annual"` in
     `naaqs_compliance_report`.
   Checked in the AERMOD 26135 Fortran (2026-11-21, read through a CI job because the cloud container cannot reach
   EPA): a calm or missing hour is a row of 0.0 in a 1-HR POSTFILE with no background (`aermod.f` HRLOOP, `calc2.f`
   POSTFL); the stamp is the surface-file date and hour, 1 to 24, unconverted (`metext.f` KURDAT); CONC is in ug/m3 by
   default (`coset.f`). `o3_8hr_design_value(calm_missing=...)` and `calm_and_missing_hours()` follow from the first.
   Still open: the 24-hour and annual means from hourly rows count calm and missing hours as zeros
   (`HOURLY_MEAN_LIMITATION`); `ppb_to_ugm3` differs from AERMOD's rounded ppb constants by up to 0.11 %; that AERMET
   writes hour-ending LST is AERMET's convention and was not read in its source.
4. **The open questions and findings listed above**, the intermittent CI hang first.
5. **Not checked anywhere:** a possible GeoJSON export CRS problem under geopandas 0.14, and
   `tests/regulatory/test_event_rewrite.py` with AERMOD v24142 on PATH. Both are in the local verification prompt.

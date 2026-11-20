# Handoff (2026-11-20, codebase review of 2026-11-18)

Report: `.10x/reviews/2026-11-18-codebase-review.md`. The raw findings, verifier tests and the three rule-text research
write-ups are on the branch `claude/codebase-review-2026-11-18-4uyhje` only, under
`.10x/reviews/2026-11-18-codebase-review-raw/` (`research-naaqs.md`, `research-appendix-w.md`,
`research-aermod-source.md`). Keep that branch until they are no longer wanted.

To do locally: `.10x/local-verification-prompt.md` (checks that need the AERMOD binaries and EPA Fortran) and
`.10x/branch-cleanup.md` (remote branches to delete, and those that need a decision).

## State (updated 2026-11-20, after the overnight simplification pass)

Merged to main, all on green CI: #72 to #96.

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
- `mypy-baseline.txt` is 60 against a measured 46: lower it from the CI Python 3.12 environment.
- Branch cleanup: the cloud session cannot delete remote branches (HTTP 403). The commands and the list of branches
  that need a decision are in `.10x/branch-cleanup.md`.

Cloud container notes: two tests fail there and are not regressions (`test_an_ipv6_host_is_checked_as_ipv6`; and
`test_d5_aerscreen_timeout_kills_the_childs_children`, intermittent). The GUI journeys cannot run there (no Python
`playwright` package); CI runs them. `pip install -e ".[all]"` fails on pywebview; use `.[viz,geo,gui,met,hpc,dev]`.

## The cloud environment lacks
The EPA Fortran (`aermod/`, `aermet/` are gitignored), AERMOD binaries and `test_cases/`. Do not guess what AERMOD does:
the research write-ups quote the routines and lines that matter. CI is the test oracle (Python 3.11-3.13).

## Remaining work, in order

### 1. Merge #78 when green.

### 2. Finish `claude/changelog-and-housekeeping`, then open its PR
After #78 merges, merge main into the branch and:
- add CHANGELOG entries for #78 (unsaved-work prompts on import and tab close; persistent editors that read "x y" vertices and
  refuse empty numbers and bad or duplicate IDs; Results says when the project changed since the run; NAAQS verdicts from short
  records say they are not design values and note when no background was added; one readiness source; per-run deck names
  `pyaermod_gui_runN.inp`; huge grids no longer freeze the plan view; a missing met file blocks the run) and for #79 (docs);
- replace `PLAN-gui.md` / `PLAN-code.md` with `.10x/plans/PLAN-gui.md` / `.10x/plans/PLAN-code.md` in the comments of the
  Makefile, workflows, tests and fixture READMEs (about 20 files; none opens the file);
- update the GUI docs #79 left alone: `docs/gui-guide.md` (importing a deck now asks; run file name; closing the tab warns),
  `docs/desktop.md` (closing the window), `docs/teaching/student-guide/tutorial-1.md` (run file name);
- lower `mypy-baseline.txt` with `python scripts/mypy_gate.py --update` only from the CI Python 3.12 environment (it was 46 locally against 60).

### 3. Finish `claude/regulatory-text-and-met-year`, then open its PR
Files: `regulatory.py`, `chemistry_presets.py`, `naaqs.py`, `design_values.py`, `validator.py`, `validator_advanced.py`,
`pathways.py` (low_wind_option only), `api.py` (one export; "1.x" to "2.x" in the CORE_NAMES promise), tests. Test first; no
CHANGELOG or docs edits in the code commits (add them at the end of the same PR).

Part 1, no computed number may change:
- PM2.5 standards cite 40 CFR 50.20 (annual 50.20(a)-(b), 24-hour 50.20(c)) and Appendix N, not 50.18.
- PM10 form: expected exceedances of 150 µg/m3 at most once per year, averaged over 3 years (50.6(a); Appendix K), not "(5-yr avg)".
  Attribute the high-N+1-high modelling rule to the AERMOD User's Guide 3.2.16.2 and the pre-2017 Guideline, not Appendix W or Part 50.
- NO2 citations with paragraphs: 50.11(a), (e), (f); Appendix S.
- Docstring only: modelled values are compared unrounded (Appendix W 9.2.2(b)); Part 50 rounding applies to monitored design values.
- Profiles: `allowed_low_wind` empty everywhere, and a set low-wind option is flagged and cleared; ARM2 accepted in every
  Appendix W profile (Tier 2, section 4.2.3.4); "PVMRM2" removed; the 2017 notes corrected (ADJ_U* was adopted as a regulatory
  AERMET option; LOWWIND3 was declined; GRSM did not exist in 2017; drop the uncited "EPA memoranda"); GRSM was BETA in v22112
  and v23132 and regulatory from v24142, usable with DFAULT.
- New `EPA_APPENDIX_W_2024` (89 FR 95034, effective 2025-03-21): the 2017 content plus GRSM as Tier 3. Selecting OLM, PVMRM or
  GRSM adds a note that Tier 3 needs consultation with the EPA Regional Office and the reviewing authority. Keep
  `EPA_APPENDIX_W_2023` importable, documented as the 2017 rule with AERMOD v23132 (there was no 2023 revision). Export the new name.
- `chemistry_presets.py`: stop saying ARM2 is not accepted by Appendix W.

Part 2, approved behaviour changes:
- B3: negative stack exit velocity is a warning (AERMOD W325, Vs set to 1e-5, run continues).
- B1: design values follow the met year, detected from the first hour (AERMOD's CHK_ENDYR), with an optional keyword to force
  calendar years or give the boundary. January-start data must give identical results (test it). The July-to-June PM2.5 case in
  `verify/v-gui-reg-tools/test_design_values_met_year.py` expects 358.
- B2: keep `default_no2_ratio = 0.5`; docstring says AERMOD has no default (E336).
- Follow-ups: call `postfile.warn_hourly_mean_limitation` where hourly rows are averaged; E336 as a validator error when a source
  has no NO2RATIO and the project has no default (remove the xfail on `test_olm_source_without_any_ratio_is_an_error`);
  validate CO LOW_WIND values (numeric, ranges in `research-aermod-source.md`, needs alpha, error with DFAULT); an urban source
  without `urban_area_name` when there are several urban areas is an error.

Then docs for this PR: `docs/regulatory-matrix.md`, `docs/use-cases.md` (ARM2, H6H attribution), `docs/design-value-validation.md`.

### 4. Awaiting the maintainer's word (do NOT change; each alters computed results)
- Annual PM2.5 as the mean of the four quarterly means (Appendix N 4.4); the code averages all days.
- PM10 rank N+1 for 2 to 4 years of data; the code uses the second-highest.
- Ozone from running 8-hour means (Appendix U); the code uses AERMOD's three fixed blocks per day.
- PM10 threshold: 150 as coded, or effectively 155 under Appendix K's rounding to 10 µg/m3.
- The SO2 secondary annual standard (50.21, 10 ppb) is not in the table.

### 5. Remaining follow-ups
`visualization.py` titles plots with a job name AERMOD never prints; delete `browser._quote_blanks` (the writer quotes now);
one executable finder in `runner.py` for both GUIs; possible GeoJSON export CRS problem under geopandas 0.14 (unverified);
`tests/regulatory/test_event_rewrite.py` failed locally with AERMOD v24142 on PATH (not confirmed on main).

### 6. Simplification PRs
Report section 9 (about 2,200 lines), behaviour-preserving, one writer per file set, after steps 2 and 3 land.

### 7. Clean up branches (asked by the maintainer on 2026-11-19; do this last)
The remote has more than 25 branches. After everything above is merged:
- delete every remote branch whose pull request is merged (`gh pr list --state merged --json headRefName`), including this
  review's `claude/fix-*`, `claude/docs-accuracy-concision` and, once merged, the later ones;
- for a branch with no pull request, or with a closed, unmerged one, do not delete: list it with its last commit date and
  whether it is fully contained in main (`git branch -r --merged origin/main`), and ask the maintainer;
- never delete `main`, `gh-pages` or any branch a workflow deploys from;
- say that local branches and worktrees on the maintainer's laptop (including `backup/codebase-review-local`) are not
  reachable from the cloud and need `git worktree prune` and `git branch -d` there.

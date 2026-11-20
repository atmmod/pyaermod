# Codebase review, 2026-11-18 (pyaermod at 24c5dff, v2.3.0)

Sixteen reviewers (3 Haiku inventories, 10 Sonnet slices and docs, 3 Opus for GUI and architecture) and four independent
verifiers. Raw findings, verdicts and the verifiers' failing tests are in `2026-11-18-codebase-review-raw/`.
IDs below are the reviewers' own (file name + ID), so `slice-c C1` is finding C1 in `slice-c.md`.

**Status words.** *Confirmed*: a second agent reproduced it and wrote a test that fails at HEAD. *Observed*: seen in a live
browser session with a screenshot, not independently re-run. *Read*: from code reading only.

## Baseline (stage 0)
ruff clean; mypy 60 = baseline; strict docs build passes; vulture finds 3 unused imports; 44 functions at radon D or worse.
Default suite on Python 3.15.2: 5,530 passed, 2 failed, 97.1% coverage. Both failures are environmental:
`test_browser.py::test_without_aermod_...` assumes no `aermod` on PATH (non-hermetic test);
`test_gui_v2_project_io.py::...deeply_nested...` relies on `json.loads` raising RecursionError at depth 1e5, which 3.15 no longer does.
GUI journeys: 71 passed, 3 skipped.

## 1. Valid decks the library refuses (confirmed; highest user impact)
`write(validate=True)` is the default. 81 of 252 local decks, and 72 of 160 EPA decks, cannot be written back; every EPA failure is a false error.

| Finding | False error | EPA decks |
|---|---|---|
| slice-c C2, slice-b B4 | `BACKGROUND`/`BACKGRND` and ID ranges as SRCGROUP members | 33 |
| slice-c C1 | POLLUTID limited to 7 names (AERMOD accepts any; 8 chars kept) | 18 |
| slice-c C3 | "no sources/receptors" ignores INCLUDED and EVALCART lines | 25 |
| slice-c C6, slice-b B5 | urban source needs a named URBANOPT | 8 |
| slice-c C5 | deposition METHOD_2 rejected (E242) | 7 |
| slice-c C4 | Ts <= 0 rejected; AERMOD: 0 = ambient, <0 = offset, E320 only for 0 < Ts < 200 | 3 |

Also confirmed: slice-c C7 (100,000-receptor limit is not AERMOD's), C9 (TTRM without ozone passes), C10 (ID > 12 chars, reserved
BACKGROUND, case-insensitive duplicates unchecked), C11 (gas + particle deposition on one source passes).

## 2. Wrong decks written (confirmed against v24142 and v26135 binaries)
- slice-a A1 **high**: `CO ELEVUNIT` is written; AERMOD rejects it (E110). Correct: `ELEVUNIT` first in SO and RE.
- slice-a A2 **high**: several urban areas written as `URBANSRC S1`; AERMOD needs `URBANSRC urbid srcid`.
- slice-a A3: background joins no group, so it is in no result (ALL = 0.00025 vs 3.00025), and the validator forbids adding it.
- slice-a A4: BUOYLINE deposition cards keyed by group, not segment: Fortran runtime error.
- slice-a A5: cards over 512 characters (ISTRG) are truncated silently by AERMOD; a 100-member SRCGROUP loses members.
- slice-a A7: reader invents `NO2STACK 0.5`, turning an E336 deck into a valid one.
- arch A2: file names with blanks written unquoted (E500); the desktop GUI's Browse button produces them.
- docs-accuracy DOCS-2: a refused `write()` leaves an existing deck at 0 bytes.
- v-validator (new): `low_wind_option` writes `CO LOW_WIND LOWWIND3`, rejected with E208/E133.
- slice-f F1, slice-c C8, docs-accuracy DOCS-6 **high**: regulatory and DFAULT checks test eight ControlPathway attributes that do not exist, so
  `DFAULT ALPHA BETA NOSTD` passes `check()`, `apply()` and the validator. AERMOD: E204 for ALPHA, BETA, PSDCREDIT, FASTAREA, FASTALL, SCIM,
  NOURBTRAN, AREADPLT, HBP, TTRM2; W206 for NOSTD, NOCHKD, SCREEN, FLAT. Tests fake the attributes with setattr.

## 3. Reader (confirmed)
slice-b B1 (D exponents, bare HALFLIFE, `inf` crash; `URBANOPT 1.0D6` lost), B2 (about 25 malformed-line branches drop the line silently),
B3 (case: AERMOD upper-cases the line; reader is case-sensitive), B6 (RECTABLE/MAXTABLE/DAYTABLE collapse to ALLAVE and change AERMOD's output).
Low, read: LOW_WIND keeps one of seven fields; UAIRDATA year and SURFDATA name/coords lost; incomplete GRIDCART invents a 10x10 grid; Latin-1 read.
Fixed since 11-11: quoted-path sandbox (H4), quoted names with spaces.

## 4. Geometry and exports (confirmed; corners hand-computed from soset.f)
- slice-g G1 **high**: AREA export is centred, double-size, x/y swapped (1600 m2 for a 400 m2 source).
- slice-g G2 **high**: OPENPIT rotates counter-clockwise (mirrored for angle != 0).
- slice-g G3 **high**: contour bands lose holes (band areas sum to 5.95e6 m2 in a 4.0e6 m2 domain).
- G4 polar receptors ignore the origin source; G5 truncated DEM tile kept as a cache hit; G7 KMZ drops line sources and draws areas as points;
  G8 `create_interactive_map` passes UTM metres as lat/lon; G11 advanced_viz grid row order; G12 source drawn at (0,0) (convention).
`footprints.py` is correct for every source type and should own the geometry.

## 5. Runners (confirmed unless noted)
slice-d D1 failed prepare leaves the directory lock held (next run hangs); D3 AERSCREEN verdict read from the previous run's files;
D5 timeout orphans grandchildren; D4 AERSURFACE success needs no output file (partly: no binary to confirm exit code);
D2 Windows `msvcrt.locking` gives up after ~10 s (docs only). Still open, read: wasm cache keyed on path; run_batch under Pyodide.

## 6. Output parsers (confirmed)
slice-e E1 multi-year ANNUAL binary POSTFILE labelled 1-HR, 2-HR...; E4 header detection fails on real RANKFILE/MAXIFILE/SEASONHR and
deposition PLOTFILEs; E5 TOXXFILE is unformatted, reader decodes text; E2 row with `*****` dropped; E3 multi-year max-daily PLOTFILE misread;
E10 dict-per-row readers (~500 bytes/row). E11: hourly POSTFILEs carry no calm/missing flag, so AERMOD's 24-h and period means
cannot be reproduced from them: document and warn, do not change numbers.

## 7. Post-processing and tools (confirmed)
slice-f F2 `apply_deposition_defaults` sets an enum where a tuple is expected (GUI then refuses to save); F3 calendar year used where AERMOD
uses the met year (PM2.5 271.5 vs 358; PM10 counts 5 years for 4); F4 `naaqs_output_pathway("PM25")` KeyError; F5 NaN ranks highest.
slice-h H-1 `prime.gep_from_building` overstates GEP (150 m vs 80.9 m); H-2 `run_all_qaqc` reports 100% missing on `.SFC` records
(also breaks the tuning guide's script); H-3 shapefile import: truncated column names, NaN, lon/lat CRS.
Low: `run_design` shallow copy; `CartesianGrid.from_bounds` float count; CLI tracebacks.

## 8. GUI
Confirmed (gui-code): G1 **high** import/read deck/recent replace a modified project and stop a run with no prompt; G2 **high** plan view expands
every grid point on the event loop (4e6 points: 1.9 s per view); G3 header and Review & Run disagree on readiness; G4 results can come from the
next run when the directory is reused; G5 vertex editor drops space-separated "x y" lines; G6 editors close on outside click or Esc and lose edits;
G7 reload during a run orphans it; G8 run folders never removed; G9 downloads block the event loop; G10 NAAQS verdict omits "excludes background".
Observed (gui-live): G4 **high** source IDs blank, > 12 chars or with a space accepted while "Ready to run"; G5 **high** Results never says the project
changed since the run; G6 **high** "Below the NAAQS" shown from 4 days of data with the caveat off-screen; G2 **high** closing the tab loses work
silently; G3 **high** browser app: reload clears "(modified)", New then discards; G7 met fields keep 0/0/2020 while the file's header is shown;
G8 invalid values reported only on Review & Run; G9 a cleared number field keeps its old value.
arch A3 (simulated): GUIs look only for `aermod`; the runner also accepts `AERMOD` and `.exe`.

## 9. Concision (behaviour-preserving; ordered by lines over risk)
| # | Change | Lines | Risk |
|---|---|---|---|
| 1 | Delete seven `__main__` demo blocks | -330 | low |
| 2 | GIS and KMZ exports use `footprints.py` (fixes G1, G2, G7) | -85 | low |
| 3 | Drop `_form.py` string-annotation parser; share with `browser.py` | -150 | low |
| 4 | One executable finder and one subprocess helper for all runners | -100 | low |
| 5 | Always-true guards in `api.py`, dead private helpers | -80 | low |
| 6 | output_parser.py: parsing of formats nothing writes | -250 | low (tests go with it) |
| 7 | One strict numeric helper in the reader (fixes B1) | -80 | low |
| 8 | Split `_parse_sources` (746 lines); trim `_parse_control` | -210 | medium |
| 9 | Table-driven per-source range checks in the validator | -260 | medium |
| 10 | Table-driven AERSCREEN/AERSURFACE config checks | -120 | low |
| 11 | `PostfileParser` on the aux reader's header/FORMAT parsing (fixes E2) | -125 | medium |
| 12 | sources.py/pathways.py local duplication | -195 | low |
| 13 | Smaller: design-values table, shims, plotting boilerplate, GUI editor helper | -250 | low |

About 2,200 lines (6%). Leave alone: one declarative keyword framework; a mixin base for source dataclasses (reorders constructors);
unifying the four number formatters; merging public modules.

## 10. Docs
Accuracy: tuning-guide QA script fails on a good file (DOCS-1); common-errors documents an E101 code and four Fortran messages AERMOD never
prints (DOCS-3/4/5); AERMET "Stage 3" naming (docs-concision D1); regulatory-matrix claims and GRSM contradiction; architecture.md BPIP;
api/index.md counts, "1.x", extras table; citation says 2.2.0; broken anchors in use-cases.md:22 and refinery-assignments.md:17-19.
Concision: about 1,630 lines removable (7,200 to 5,600); install text on seven pages, AERMOD-binary text on six; README repeats index.md;
quickstart recipes repeat use-cases. CLI subcommands validate/run/parse/plotfile/profile are undocumented.

## Decisions for the maintainer

Nothing below has been changed. Each item says what the code does now, what the alternative is, and what I recommend.
Every CFR and Appendix W reference in this section is from the reviewers' memory (eCFR could not be fetched) and must be checked before it is relied on.

### A. Regulatory questions (need your judgement or a check of the rule text)

**A1. Should a design value be rounded before it is compared with the NAAQS?**
Now: the unrounded value in µg/m³ is compared with the level. An SO2 value of 75.4 ppb counts as an exceedance, though rounded to the nearest ppb it equals the 75 ppb standard.
Options: (a) keep; (b) round per each standard's appendix before comparing; (c) keep the comparison, add a note when a value is within rounding distance of the level.
Recommend (c) now, (b) once the rounding conventions are confirmed.

**A2. Which CFR section should the PM2.5 annual standard cite?**
Now: `naaqs.py` cites 40 CFR 50.18 for the 9.0 µg/m³ level. The reviewer believes 50.18 holds the 2012 level (12.0) and the 2024 level is in 50.20.
Options: confirm and correct the label, or leave. A label only; no number changes.

**A3. Should the annual PM2.5 value be the mean of the four quarterly means?**
Now: the mean of all days in the year. The reviewer believes Appendix N uses the mean of the four calendar-quarter means. On test data the two gave 20.082 and 20.000.
Options: (a) keep; (b) switch to quarterly means; (c) offer both, defaulting to the current one.
Recommend (b) if you confirm Appendix N; it changes results slightly.

**A4. For annual NO2, is 75% completeness required for the year or for each quarter?**
Now: 75% of the year as a whole. Unconfirmed whether Appendix S requires it per quarter. The docstrings cite 50.11(e); the 11-11 review cited 50.11(b).
Options: confirm the rule and the citation; change only if per-quarter is right.

**A5. How should ARM2 be treated?**
Now: three places disagree. `chemistry_presets.py` says Appendix W does not accept ARM2; `docs/use-cases.md` calls ARM2 Tier 2; the regulatory profiles allow only OLM and PVMRM, so `check()` warns on ARM2, which is also the default method of a new project.
Options: (a) ARM2 is accepted as Tier 2: add it to the profiles' allowed methods and fix the preset text; (b) ARM2 is not accepted: fix the docs and change the default method.
Recommend (a) if you confirm the 2017 Appendix W adopted ARM2 as Tier 2.

**A6. How should GRSM be treated under DFAULT?**
Now: `regulatory.py` treats GRSM as a non-DFAULT option. AERMOD v24142 and v26135 accept GRSM beside DFAULT.
Options: (a) keep the profile stricter than the model, and say so; (b) allow GRSM in the 2023 profile.

**A7. What should the PM10 24-hour rank be for record lengths other than 1 and 5 years?**
Now: sixth-highest for five or more years, second-highest otherwise. So 2 to 4 years use the second-highest, and 6 or more years still use the sixth-highest. The docs describe only the 1-year and 5-year cases, and `naaqs.py` labels the form "(5-yr avg)".
Options: (a) keep and document; (b) refuse record lengths other than 1 and 5 years; (c) scale the rank with the number of years.
Recommend (a) plus correcting the label.

**A8. Should the ozone 8-hour design value be rebuilt from running means?**
Now: it uses AERMOD's 8-hour output, which is three fixed blocks per day, so the value can be lower than one built from running 8-hour means. #74 fixed the docstring and made the function refuse 1-hour input.
Options: (a) keep block values and state the limitation; (b) add a function that builds running 8-hour means from a 1-hour POSTFILE.
Recommend (a) now; (b) is new work if ozone matters to users.

**A9. Is the 2017 regulatory profile's description right?**
Now: its text says LOWWIND3 and ADJ_U* are permitted "for documented cases" and that "GRSM was still BETA in 2017". The reviewer doubts each statement (GRSM may not have existed in the 2017 model).
Options: you correct the text, or the profile's notes are cut to what can be cited.

**A10. What should the regulatory profiles allow for low-wind options?**
Now: both profiles carry `allowed_low_wind=("LOWWIND3",)`. AERMOD no longer has LOWWIND3: `CO LOW_WIND` takes numeric values and needs ALPHA, which DFAULT forbids.
Options: (a) empty the allowed list (no low-wind option under a regulatory profile); (b) keep for the 2017 profile only.
Recommend (a) for the 2023 profile.

**A11. `alpha` is now on the profiles' forbidden list (already merged in #76).**
AERMOD refuses ALPHA beside DFAULT, so a regulatory profile now flags it. Say if you want this reverted.

### B. Behaviour and API choices

**B1. Should design values follow the met year instead of the calendar year?**
Now: values are grouped by calendar year, so a July-to-June met year is split in two. #74 added a warning; no number changed.
Options: (a) keep the warning only; (b) add an optional argument giving the year boundary; (c) detect the met year from the first hour, as AERMOD does.
Recommend (c) with (b) as an override; it changes results for met years that do not start in January.

**B2. Should a chemistry project built in Python still default to `NO2STACK 0.5`?**
Now: the dataclass default is 0.5. #77 stopped the reader inventing it for decks that have none.
Options: (a) keep 0.5; (b) default to none, so each source needs its own ratio or AERMOD stops with E336. (b) breaks existing OLM, PVMRM, GRSM and TTRM scripts that rely on the default.
Recommend (a) for 2.x with a note in the docs; (b) at 3.0.

**B3. Should a negative stack exit velocity be an error or a warning?**
Now: an error. AERMOD accepts it with warning W325 and treats it as a small positive value.
Recommend a warning, to match AERMOD.

**B4. Should the writer add background to `SRCGROUP ALL` automatically?**
Now: no, which matches AERMOD: background is in a group only when the group names it. #76 added a warning when a project has background in no group.
Options: (a) keep; (b) add it automatically, which changes results for existing projects.
Recommend (a).

**B5. Should `epa_sources.py` and `epa_testcases.py` leave the installed package?**
Now: both ship in the wheel (464 lines) and are exported; they locate EPA's source and test archives for the test suite.
Options: (a) keep; (b) move them under `tests/` or `scripts/`, which removes public names.
Recommend (a) for 2.x.

### C. Housekeeping

**C1. Move CHANGELOG entries for 2.2.0 and older (3,147 of 3,421 lines) to `CHANGELOG-archive.md`?** Recommend yes; needs one `MANIFEST.in` line and two link fixes in the 2.2.0 release notes.
**C2. Delete `requirements.txt`?** No file references it and its version floors disagree with `pyproject.toml`. Recommend yes.
**C3. Archive `PLAN-code.md` and `PLAN-gui.md`?** Both describe finished work and quote old numbers. Recommend moving them under `.10x/`.

## Not covered
Desktop (pywebview) mode; a real Pyodide boot; dark mode; Windows; AERMET keywords against Fortran one by one; EVENT parser; BPIP and
AERSCREEN against Fortran (not in the repo); ASOS/IGRA parsers against real records.

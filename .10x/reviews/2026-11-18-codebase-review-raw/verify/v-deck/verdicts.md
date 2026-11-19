# v-deck verdicts (deck writer / reader vs AERMOD Fortran)

Binaries: <repo>/bin/aermod (24142) and a clean v26135 build (outside the repo; its source tree
`aermod_source_v26135` was used for the v26135 citations). Both are gfortran builds with bounds checking.
Met: test_cases/aermet_24142_aermod_24142/meteorology/AERMET2.SFC/.PFL (96 h). Harness: verify/v-deck/lib.py; run dirs in verify/v-deck/work/.
Tests: verify/v-deck/test_deck_writer.py (12), test_deck_reader.py (16), test_gui_binary.py (3). 28 fail at HEAD for the stated reason,
2 are guards that pass (`test_file_names_keep_their_case`, `test_runner_finds_upper_case_binary`). They pass ruff with the repo config.

| ID | Verdict |
|---|---|
| slice-a A1 CO ELEVUNIT | CONFIRMED |
| slice-a A2 URBANSRC multi-area | CONFIRMED |
| slice-a A3 background not in any group | CONFIRMED (worse: validator blocks the workaround) |
| slice-a A4 BUOYLINE deposition keyed by group | CONFIRMED |
| slice-a A5 512-char cards | CONFIRMED |
| slice-a A6 AREACIRC Szinit | not re-verified (not in my assignment list) |
| slice-a A7 NO2STACK 0.5 invented | CONFIRMED (reader part); default for Python-built projects is a maintainer call |
| slice-b B1 D-exponent / raw float() | CONFIRMED |
| slice-b B2 malformed lines dropped | CONFIRMED (inputs AERMOD rejects; severity bounded) |
| slice-b B3 case sensitivity | CONFIRMED |
| slice-b B6 RECTABLE/MAXTABLE/DAYTABLE -> ALLAVE | CONFIRMED (output tables change) |
| arch A2 blank file names unquoted | CONFIRMED (both binaries) |
| arch A3 GUIs only look for `aermod` | CONFIRMED (Linux-only effect; simulated) |
| docs DOCS-2 write() truncates before validating | CONFIRMED |

---

## slice-a A1: CONFIRMED
- Fortran: COCARD (coset.f) has no ELEVUNIT branch and ends in `ERRHDL(...'E','110',KEYWRD)` (coset.f:1406). ELEVUNIT is handled in
  soset.f SOCARD:276-294 -> SOELUN (must precede any source, E152; soset.f:1942-1948 accepts METERS/FEET) and reset.f RECARD:94-108 -> REELUN
  (must precede any grid/discrete card). Same in v26135 (soset.f:278, reset.f:94, no CO branch).
- Run (a1.py): `ControlPathway(elevation_units="FEET")` + `ReceptorPathway(elevation_units="FEET")` writes `CO ELEVUNIT FEET` and `RE ELEVUNIT FEET`
  and no SO card. Both versions give `CO E110 COCARD: Keyword is Not Valid for This Pathway. Keyword is ELEVUNIT` (fatal).
  Hand-moved to `SO STARTING / ELEVUNIT FEET` (and RE kept), both versions run with no error. The source's 100 ft base elevation is reported as 30.5 m,
  and the receptor's 330 ft as 100.6 m.
- Correct output for a feet project: `ELEVUNIT  FEET` as the first card after `SO STARTING` and the first card after `RE STARTING`, and none on CO.
- Tests asserting the wrong output: tests/test_coverage_gaps.py:420-423 `test_elevation_units_feet` (expects "ELEVUNIT  FEET" in the **CO** text)
  and :446-460 `test_all_optional_together` (expects ELEVUNIT among CO keywords). tests/test_input_reader.py:968-969 `test_elevunit_in_co` makes the reader
  accept a CO ELEVUNIT that AERMOD rejects. (test_coverage_gaps.py:582-589 is the RE card and is correct.)
- Tests: test_deck_writer.py::test_elevunit_feet_is_never_a_co_card, ::test_elevunit_feet_is_the_first_so_card.
- Blast radius: (1) A read deck with `SO ELEVUNIT` is today kept verbatim in unparsed_lines and spliced first (input_generator._PRESERVE_FIRST).
  If the writer starts emitting SO ELEVUNIT from `control.elevation_units`, the reader must move SO ELEVUNIT into that field. Otherwise a project that
  has both writes the card twice (E135). (2) The reviewer's "pass control.elevation_units to both SO and RE" would override `ReceptorPathway.elevation_units`.
  Recommend control -> SO only and RE keeps its own field. Maintainer call: whether a CO ELEVUNIT line in a read deck goes to unparsed (AERMOD-faithful)
  or is mapped to SO.

## slice-a A2: CONFIRMED
- Fortran: soset.f URBANS (v24142 ~6455-6497): with L_MULTURB (aermod.f:6238, set when more than one URBANOPT card is present), FIELD(3) is the urban ID (E301
  if undefined) and source IDs start at field 4. With a single area, sources start at field 3.
- Run (a2.py): two `UrbanArea`s (A1, B2) and sources with `urban_area_name` write `URBANSRC  S1` / `URBANSRC  S2`. Both versions give
  `SO E301 URBANS: Urban Area ID Has Not Been Defined. URBID = S1` (and S2), `E318 No Sources Defined for Urban Area A1/B2` and `E130 Missing URBANSRC`.
  With `URBANSRC A1 S1` / `URBANSRC B2 S2` the deck has no SO error.
- Also: with validation on, this project is refused ("urban_option is not set"). That is slice-b B5 / slice-c (validator ignores `urban_areas`), so the test
  uses validate=False.
- Test: test_deck_writer.py::test_urbansrc_names_the_area_when_there_are_several.
- Blast radius: tests/test_coverage_gaps.py:316-326 asserts the area name is never written. Keep that test for the one-area case and parametrise.

## slice-a A3: CONFIRMED, and worse than reported
- Fortran: soset.f SOGRP:5862-5900 (v26135 5937-5975, identical): "BACKGRND is NOT automatically included in source group ALL". A bare `SRCGROUP ALL`
  gives W298 NOBACKGROUND. SRCQA:1336-1356 gives W321 when no group includes it. Same default in both versions.
- Run (a3.py): `BackgroundConcentration(uniform_value=3.0)` on a default project writes `BACKGRND ANNUAL 3` + `SRCGROUP ALL`. Both versions give W298 + W321,
  and ALL's 1st-high 1-hr is **0.00025**. With `SRCGROUP ALL BACKGROUND` (written with validate=False) it is **3.00025**. Validator: no message.
- Worse: `SourceGroupDefinition("ALL", ["BACKGROUND"])` is **rejected by the validator** (validator.py:1662-1669, "source ID 'BACKGROUND' not found in project
  sources"). So with validation on, a Python user cannot put the background into any group. The reader produces exactly this definition from EPA decks
  (tests/test_so_source_construction.py:503-517), so those decks cannot be rewritten validated either. docs/quickstart.md:225-254 ("Add ambient background
  levels") shows only `sources.background = ...`, which adds nothing to the results.
- Tests: test_deck_writer.py::test_background_in_group_all_passes_validation (clear-cut), ::test_background_in_no_group_is_reported (minimal fix).
- Maintainer call: warn only, or make the writer add BACKGROUND to ALL by default. The second changes results for existing projects and deviates from
  AERMOD's default, so it needs a flag and a changelog line. The validator must accept BACKGROUND/BACKGRND (case-insensitive) as group members in any case.

## slice-a A4: CONFIRMED
- Code: sources.py:1448-1451 passes `self.source_id` (the BLPGROUP ID) to `_deposition_to_aermod_lines`. NO2RATIO/URBANSRC just around it loop over segments.
- Run (a4.py): `PARTDIAM BLD 5 10` with segments L1/L2: v24142 `Fortran runtime error: Index '0' of dimension 1 of array 'l_method2' below lower bound of 1`
  at soset.f:4831, and v26135 at soset.f:4906, with no output. The validator gives only an unrelated warning. With the three cards written per segment
  (L1, L2), the deck runs clean.
- Note: these binaries have bounds checks. An EPA release build would index element 0 silently, which is undefined behaviour, not a clean error.
- Test: test_deck_writer.py::test_buoyline_deposition_cards_name_the_segments. Blast radius: none known (any deck using it today crashes).

## slice-a A5: CONFIRMED
- Fortran: modules.f:92 `ISTRG=512` (v26135 modules.f:96, same). setup.f:110-121 builds the format from ISTRG and reads `RUNST1, (RUNST(I), I=1,ISTRG)`,
  so characters past 512 are never read and nothing reports it. Also IFMAX=150 fields per card (same line), a second limit for long member lists.
- Run (a5.py): 100 sources, `SourceGroupDefinition("GRP1", all 100 IDs)`. The validator passes, and one 1021-character SRCGROUP card is written.
  Both versions run with no message, but GRP1's 1st-high is **151.36** against ALL's **165.07**, although the two groups have the same members.
- Test: test_deck_writer.py::test_no_card_is_longer_than_512_characters_and_no_member_is_lost (no card over 512, all 100 IDs still in GRP1).
- Blast radius: tests that compare exact SRCGROUP text for long lists. I did not check whether BLPGROUP/HOUREMIS/ARCFTSRC/HBPSRCID accept
  continuation cards. Until that is checked, the safe fix for those is a validator error over 512.

## slice-a A7: CONFIRMED (reader); default value is a maintainer call
- Fortran: setup.f:1708 `C NO2Stack = 0.10D0 !D040 remove default NO2Stack value`. coset.f:634-641 resets ANO2_RATIO to -9 without NO2STACK
  (v26135 coset.f:645). soset.f SRCQA:1757-1766 gives E336 per source with a negative ratio (v26135 soset.f:1830).
- Run (a7.py): an OLM deck with no NO2STACK and no NO2RATIO gives `SO E336 NO2RATIO Missing/Invalid for OLM/PVMRM/GRSM. Src: S1` in both versions.
  After `read_aermod_input` -> `to_aermod_input` the rewrite has `NO2STACK 0.5000` (reader input_reader.py:739 fills 0.5) and the validator says nothing.
  Both versions then pass setup with no E336 (only run-time E480, from the 4-day met file). An invalid deck becomes a valid one with an invented ratio.
- Tests: test_deck_writer.py::test_rewrite_does_not_invent_no2stack (the deck has a per-source NO2RATIO and no NO2STACK), ::test_olm_source_without_any_ratio_is_an_error.
- Blast radius / decision: changing `ChemistryOptions.default_no2_ratio` from 0.5 to None changes the deck for every Python-built OLM/PVMRM/GRSM/TTRM
  project that relies on it (they would then fail with E336 / a validator error). The reader fix (don't fill 0.5) is clear-cut. The library default
  needs a deprecation path and a changelog entry.

## slice-b B1: CONFIRMED
- Fortran: STODBL (setup.f) accepts D exponents. Runs b1.py: `LOCATION S1 POINT 1.0D2 0 0` and `HALFLIFE 1.0D3` pass AERMOD setup (both versions,
  no setup error; only run-time E480 from the short met).
- Reader: `ValueError: could not convert string to float: '1.0D2'` / `'1.0D3'` (no line number). A bare `HALFLIFE` (AERMOD: CO E200 EDECAY) gives
  `IndexError` instead of the ValueError contract. `URBANOPT 1.0D6` + `URBANSRC S1` is read with `urban_areas=[]`, no unparsed line: the urban
  area silently disappears.
- Tests: test_deck_reader.py::test_location_with_d_exponent, ::test_halflife_with_d_exponent, ::test_urbanopt_with_d_exponent_is_kept,
  ::test_bare_halflife_is_a_value_error. Blast radius: low; error messages change text (tests matching "could not convert" would need updating).

## slice-b B2: CONFIRMED (bounded severity)
- Run b2.py: `PARTDIAM S1 abc`, `BUILDHGT S1 x y`, `NO2RATIO S1 abc`, `GASDEPOS S1 1 2` (and `EMISUNIT abc g/s ug`) are absent from the rewritten deck
  and from `unparsed_lines`. The module docstring (input_reader.py:47-53) promises "Nothing is dropped silently". All of these are AERMOD errors in the
  source deck, so the loss is of an invalid line, but the user loses the evidence.
- Test: test_deck_reader.py::test_malformed_so_card_is_kept[4 cases]. Blast radius: rewritten invalid decks will now carry the bad line (correct per docstring).

## slice-b B3: CONFIRMED
- Fortran: aermod.f:2237 (and 5976, 6145) calls LWRUPR. setup.f LWRUPR:319-363 upper-cases every character of RUNST (the array DEFINE/GETFLD split into
  FIELD). The original-case copy RUNST1 is used only where a routine slices it explicitly. Those fields must keep their case:
  - titles: TITLEONE/TITLETWO text (coset.f:1438, 1446);
  - file names: CO EVENTFIL, SAVEFILE/INITFILE (incl. MULTYEAR forms), ERRORFIL, every DEBUGOPT file, OZONEFIL, NOX_FILE (coset.f 2807-4425, 5364, 5585);
    SO HOUREMIS (soset.f:6336), BACKGRND hourly file (soset.f:7479); ME SURFFILE/PROFFILE (meset.f:347-432), SCIMBYHR files (meset.f:2175-2238);
    OU MAXIFILE (ouset.f:1023), POSTFILE, PLOTFILE (incl. PERIOD/ANNUAL), TOXXFILE, SEASONHR, RANKFILE, EVALFILE, SUMMFILE, MAXDAILY,
    MXDYBYYR, MAXDCONT (ouset.f:1023-3865); INCLUDED (aermod.f:6667);
  - read-format strings for O3/NOX/BACKGRND hourly files (coset.f:5430, 5651; soset.f:7521) (case-insensitive to Fortran anyway);
  - the EMISFACT/EMISUNIT output label for ANNUAL (soset.f:4589, 4711, 4722, PERLBL).
  Everything else (pathway codes, keywords, source/group/urban/sector IDs, options) is upper-case to AERMOD.
- Runs b3.py: `co STARTING ...` lower-case pathways, `LOCATION Stack9` + `SRCPARAM STACK9`, and `SRCGROUP G1 s1` all pass AERMOD setup with no error
  (the output shows G1 = S1). Reader: the first raises `ValueError: line 1: content outside any pathway block`. In the second, both cards go to unparsed
  and the project has no sources (a validated write fails). In the third, the group member is kept as 's1' and a validated write fails.
- Tests: test_deck_reader.py::test_lower_case_pathway_codes, ::test_source_id_case_does_not_split_a_source, ::test_group_member_case_matches_source,
  plus guard ::test_file_names_keep_their_case (passes today and must keep passing).
- Maintainer call: whether the reader/writer upper-cases IDs on output or keeps the user's spelling and only matches case-insensitively. Tests use
  `.upper()` so either passes. Upper-casing changes GUI display and project JSON for existing mixed-case projects.

## slice-b B6: CONFIRMED, and the output tables change
- Deck (b6.py, AVERTIME 1 24 PERIOD, POLLUTID OTHER, AERMET2 met), each run through v24142 before and after read -> write:
  - `RECTABLE 1 1-3` + `RECTABLE 24 1` -> `RECTABLE ALLAVE 1-3`. The rewrite prints two extra tables:
    "THE 2ND HIGHEST 24-HR" and "THE 3RD HIGHEST 24-HR AVERAGE CONCENTRATION VALUES".
  - `MAXTABLE 24 5` -> `MAXTABLE ALLAVE 5`. Extra table "THE MAXIMUM 5 1-HR AVERAGE CONCENTRATION VALUES".
  - `DAYTABLE 24` -> `DAYTABLE ALLAVE`. The original prints 4 "CONCURRENT 24-HR" pages, and the rewrite adds 96 "CONCURRENT 1-HR ... ENDING WITH HOUR n" pages.
  No error either way, so the change is silent.
- Tests: test_deck_reader.py::test_rectable_per_period_survives_rewrite, ::test_maxtable_period_survives_rewrite, ::test_daytable_period_survives_rewrite
  (they check the requested period/rank sets, not a particular spelling).
- Blast radius: the OutputPathway model holds one rank / one bool, so either a model change (list of (period, rank)) or sending non-ALLAVE forms to
  unparsed. The second is cheaper, but those cards then become invisible to the GUI.

## arch A2: CONFIRMED with both binaries
- Fortran: setup.f DEFINE splits at blanks outside double quotes. meset.f SURFIL:342-366 with IFC=4 takes field 3 as the file and field 4 as a format
  (W293 if not FREE).
- Run arch_a2.py (met files in a "My Met" directory): `MeteorologyPathway("My Met/AERMET2.SFC", ...)` passes the validator and writes `SURFFILE  My Met/AERMET2.SFC`.
  Both versions give `ME W293 ... format not used` then `ME E500 MEOPEN: Fatal Error Occurs Opening the Data File of SURFFILE` (and PROFFILE), with no results.
  The same deck with the two paths double-quoted runs in both versions (ALL 1st high 2.47694).
- Test: test_deck_writer.py::test_met_file_with_blank_is_written_as_one_field.
- Blast radius: browser._quote_blanks already quotes fields before writing, so the writer's quoting must skip values that are already quoted. Otherwise
  the browser GUI writes `""..""`. tests/test_browser.py quoting tests move. Reader round trip: the reader must unquote (pathways.unquote_path) so a
  rewrite does not double-quote.

## arch A3: CONFIRMED (low; Linux/case-sensitive file systems only)
- Code: gui_v2/pages/run.py:80-81 and browser.py:355-364 use `shutil.which("aermod")`. runner.py:346-353 tries aermod, AERMOD, aermod.exe, AERMOD.EXE.
- Not reproducible natively on this Mac (APFS is case-insensitive, so which("aermod") finds AERMOD) or on Windows (PATHEXT). Simulated with a `which` that
  knows only "AERMOD": AERMODRunner() finds it, and both GUI checks return False (Review & Run would say no binary).
- Tests: test_gui_binary.py::test_pip_gui_agrees_with_runner, ::test_browser_gui_agrees_with_runner (fail), guard ::test_runner_finds_upper_case_binary (passes).
- Blast radius: none; the fix is to call the runner's discovery.

## docs DOCS-2: CONFIRMED
- Code: input_generator.py:276-284 calls `mkdir(parents=True)`, then `open(output_path, 'w')` (truncates), and only then `to_aermod_input(validate=...)`,
  which raises.
- Tests: test_deck_writer.py::test_refused_write_keeps_the_existing_file (file is '' after the refused write), ::test_refused_write_creates_no_file
  (a refused write leaves an empty file behind; the parent dir creation is harmless but the empty file is not).
- Fix: build the text (and the event text) before opening. No behaviour change for valid projects.

## Side observations (not assigned; for the orchestrator)
- Validator rejects `urban_areas` without `urban_option` (= slice-b B5 / slice-c). It blocks every validated urban project built with `urban_areas`.
- A FLAT run writes DISCCART with a zelev column. AERMOD gives `RE W229 DISCAR: Too Many Parameters - Inputs Ignored` per receptor (harmless warning noise, both versions).

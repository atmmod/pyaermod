# Slice C: validator.py and validator_advanced.py (reviewer: slice-c)

Read in full: validator.py (2625 lines), validator_advanced.py (459). Repro scripts: scratchpad/repro/slice-c/ (base.py builds a project; t1..t15).
Key fact for impact: `AERMODProject.to_aermod_input(validate=True)` is the default and raises ValueError on any validator error
(input_generator.py:215-219), so a false error blocks writing the deck. Running the reader plus validator over the 46 local EPA v24142 decks
(repro/slice-c/t13.py): **21 of 46 fail validation, every failure is one of the false errors C1-C6 below.**

Not looked at: GUI use of the validator, the validator tests' contents beyond grep, ouset.f checks for MAXDAILY/EVALFILE/TOXXFILE/RANKFILE
(read, not cross-checked line by line), evset.f event checks, SRCGROUP range syntax (S1-S5) handling in `_validate_source_groups`.

Previous-review status (2026-11-11 Low item list), at HEAD:
- Ts<=0 rejected: STILL PRESENT, now VERIFIED a false error (C4).
- 12 background sectors: FIXED in the validator (`_validate_sectors` allows 2..6; t15.py shows the error). Matches soset.f BGSECTOR (IFC<=2 or >8 is E200/E202).
- TTRM without ozone passes: STILL PRESENT, VERIFIED invalid (C9).
- Hard 100,000-receptor error: STILL PRESENT, VERIFIED false (C7).

---
## Bugs

### C1 [BUG] [high] POLLUTID limited to 7 names; AERMOD accepts any ID
- Where: validator.py:38, 210-221 (also validator_advanced none)
- What: `VALID_POLLUTANT_IDS = {OTHER, PM25, PM10, NO2, SO2, CO, O3}`; anything else is an error.
- Evidence: VERIFIED. coset.f POLLID (3-field branch): `POLLUT = FIELD(3)` with no list check; only NO2/SO2/PM25 variants get special processing. EPA decks testpart.inp, testprt2.inp (CHROMIUM), testgas.inp, testgas2.inp (BENZENE), in_urban.inp (SF6) are rejected (t13.py). The validator contradicts itself: `GASDEPOS_LOOKUP_POLLUTANTS` (877) names HG0/HGII/TCDD/BAP and `_validate_restart_options` (1696) names LEAD, PM-10, PM-2.5, none of which can pass line 216. t11.py: LEAD, HG0, PM-2.5, BENZENE all "invalid".
- Fix: drop the check (or only require a non-empty string without blanks, at most 8 characters). Keep the NO2/SO2/PM25 name sets for special-processing logic.

### C2 [BUG] [high] SRCGROUP member BACKGROUND / BACKGRND rejected as "not found in project sources"
- Where: validator.py:1632-1669 (`_validate_source_groups`)
- What: member IDs are checked against source IDs only. AERMOD reserves `BACKGROUND` and `BACKGRND` as the pseudo-source for BACKGRND concentrations and puts them in groups.
- Evidence: VERIFIED. soset.f SRCGRP lines 5876, 5894-5916 accept FIELD = 'BACKGROUND' or 'BACKGRND'; soset.f 1333-1354 counts groups that include it. EPA decks `SRCGROUP ALL ... BACKGROUND` / `SRCGROUP BACKGRND BACKGROUND` (bg_no2_{arm2,grsm,olm,pvmrm,ttrm}_{ppb,ugm3}.inp, 10 decks, 20 errors). Same decks also give SEASONHR/EVALFILE/POSTFILE group checks a `BACKGRND` group, which `_validate_output_files` handles only because the group is declared.
- Fix: `all_source_ids |= {"BACKGROUND", "BACKGRND"}` (and the same for any other member check). One line.

### C3 [BUG] [high] "must contain at least one source / receptor" ignores INCLUDED and unmodelled receptor cards
- Where: validator.py:308-312 (sources), 1963-1970 (receptors)
- What: a deck read from file keeps `SO INCLUDED f`, `RE INCLUDED f`, `RE EVALCART ...` in `project.unparsed_lines`; the validator only counts modelled objects.
- Evidence: VERIFIED (t13.py): lovett.inp, multurb.inp, surfcoal.inp (sources via SO INCLUDED); flatelev.inp, lovett.inp, multurb.inp (RE INCLUDED); in_urban.inp (RE EVALCART receptors). AERMOD itself reads the included files.
- Fix: before raising either error, look for an unparsed line on that pathway with keyword INCLUDED (and for RE also EVALCART/EVALFILE); skip the error (optionally warn). `_validate_background_verbatim` already shows how to scan `unparsed_lines`.

### C4 [BUG] [high] Point source: Ts <= 0 rejected, Ts 0-200 K accepted; other point-source ranges stricter than AERMOD
- Where: validator.py:919-947
- What: `stack_temp <= 0` is an error. AERMOD: Ts = 0 is ambient release, Ts < 0 means "Ts - Ta = |Ts|" (constant offset). 0 < Ts < 200 K is the fatal one, and the validator lets it through.
- Evidence: VERIFIED. soset.f PPARM 2770-2780: `ATS == 0 -> -1.0e-5` (ambient); `0 < ATS < 200 -> E320, RUNERR`; negative is not an error. calc1.f FLUXES 5965-5971: "Negative Stack Temperature, Used to Indicate Constant TS-TA: TS = TA + |TS|". EPA mcr.inp (8 sources with Ts=0) rejected (t13.py). t3.py: Ts=0 and -30 give "must be > 0 K"; Ts=100 gives nothing.
  Same routine, same direction (valid in AERMOD, error here): `stack_diameter == 0` (ADS < 1e-5 is reset to 1e-5; only < 0 is E209), `stack_height == 0` (only < 0 is E209), `exit_velocity < 0` (W325 warning, reset to 1e-5; only the writer-side meaning differs). READ for these three, VERIFIED for Ts.
- Fix: error only for `0 < Ts < 200`; accept Ts <= 0 (advanced `_check_point_source` already handles Ts as optional). Turn `exit_velocity < 0`, `stack_diameter == 0`, `stack_height == 0` into warnings or `< 0` errors matching E209/W325. Note `emission_rate < 0` is also accepted by AERMOD for POINT/AREA/VOLUME/LINE (soset.f PPARM/APARM/VPARM/LPARM check only `== 0` W320; only RLPARM has E209 for negative QS); this validator's stricter rule is a defensible policy but should be one documented choice (SidewashPointSource has none, validator.py:657-665, so the policy is already inconsistent).

### C5 [BUG] [medium] E242 raised for sources that carry METHOD_2
- Where: validator.py:753-773 (`_validate_deposition_params`)
- What: `has_dep = gas_dep is not None or particle_dep is not None`; `method_2` is ignored, so DEPOS/DDEP/WDEP plus METHOD_2 reports "no gas_deposition or particle_deposition parameters (AERMOD E242)".
- Evidence: VERIFIED. EPA testpart.inp / testprt2.inp (MODELOPT CONC DDEP WDEP FLAT ALPHA, `METHOD_2 STACK1 0.55 1.2`) fail with this error (t13.py); the EPA deck runs. soset.f 1150-1186: E242 applies when INPD = 0 and no gas; METHOD_2 sets the category count.
- Fix: `has_dep = ... or getattr(source, "method_2", None) is not None`.

### C6 [BUG] [medium] Urban sources: error unless a urban *name* is set; population < 100 not checked
- Where: validator.py:332-341 (cross-check), 250-274
- What: `has_urban_source and not control.urban_option` errors. `urban_option` is only the optional descriptive name (pathways.py:662-669); URBANOPT with just a population, or `urban_areas=[UrbanArea(...)]`, is valid.
- Evidence: VERIFIED (t10.py): `urban_population=100000` + `is_urban=True` source gives the error; so does `urban_areas=[UrbanArea(population=100000)]`; EPA blp_urban.inp (`CO URBANOPT 70889.0`) rejected. Separately `urban_population=50` passes, but coset.f URBOPT 4851-4854 and 4917-4920 give E203 for population < 100 (W320 below 21,206). `urban_area_name` is never checked against the defined `urban_areas` ids (coset.f also E279 for URBANSRC ALL with several areas; PLAUSIBLE that a mismatching id is an error, not read).
- Fix: condition on `control.urban_option or control.urban_population is not None or control.urban_areas`; add `population < 100` error in `_validate_urban_option` and per `UrbanArea`.

### C7 [BUG] [medium] 100,000-receptor "hard limit" is not an AERMOD limit
- Where: validator_advanced.py:45, 213-220; test tests/test_validator_receptor_perf.py
- What: error "total receptors N exceeds AERMOD hard limit 100000; recompile AERMOD".
- Evidence: VERIFIED. AERMOD sizes NREC by pre-counting the input (aermod.f 7333-7348) and allocates; reset.f 726-729, 1453-1456 say "This shouldn't occur since limits are dynamically allocated". t4.py: a 400x400 grid (160,000) is an error. The early `return` also skips the grid_extent check.
- Fix: delete the hard-limit branch (keep the 10,000 warning); remove `RECEPTOR_GRID_HARD_LIMIT` from `__all__`/tests.

### C8 [BUG] [medium] DFAULT with ALPHA/BETA and other non-DFAULT options passes; the check meant for it is dead
- Where: validator_advanced.py:254-284 (`NONDEFAULT_OPTION_FLAGS`, `_check_dfault_consistency`); gap in validator.py (`_validate_control`)
- What: the check looks at `control.use_nondefault`, `flat_terrain`, `no_stack_tip_downwash`, `use_lowwind1/2/3`, `use_area_rural`, `beta_options`; none exists on `ControlPathway` (pathways.py:635-760), so it cannot fire on a real project. The tests only pass because they `setattr` a fake attribute (tests/test_validator_advanced.py:152-166). The real condition, `regulatory_default=True` (the default) with `alpha=True`, `beta=True`, `psd_credit`, or MODELOPT tokens FASTAREA/FASTALL/SCIM/HBP/TTRM2/NOURBTRAN/AREADPLT, passes unflagged.
- Evidence: VERIFIED (t1.py: alpha, beta, FASTAREA each with DFAULT give only the FLAT warning). coset.f MODOPT: ALPHA 1853-1860, BETA, FASTAREA 1881-1900, FASTALL, SCIM (E204), PSDCREDIT 1855-1862, HBP 1795-1805, TTRM2 1827-1831 all `CALL ERRHDL('E','204')` under DFAULT. The writer emits `DFAULT ALPHA` (pathways.py `_model_options`). Also: every `alpha`-gated check in the validator would pass with alpha=True under DFAULT although AERMOD leaves L_ALPHA false (coset.f 1652-1658).
- Fix: replace the dead check with one on real fields: `regulatory_default and (alpha or beta or psd_credit or {FASTAREA,FASTALL,SCIM,HBP,TTRM2,...} & extra)` -> error E204; update the tests to use real fields.

### C9 [BUG] [medium] TTRM/TTRM2 need ozone and ALPHA; empty OzoneData passes; wrong code for ozone conflict
- Where: validator.py:1855-1861 (`method in (OLM, PVMRM, GRSM) and ozone_data is None`)
- What: TTRM and TTRM2 are missing from the "ozone required" tuple. coset.f 554-570: `OLM or PVMRM or RUNTTRM or GRSM` with no OZONEVAL/OZONEFIL/O3VALUES is E283 (TTRM2 sets RUNTTRM). TTRM/TTRM2 also need ALPHA (coset.f 1810-1815, 1817-1824; TTRM2 additionally E204 under DFAULT); the validator checks none of these. `OzoneData()` with nothing set also satisfies `ozone_data is not None` but writes no ozone card (t5.py), AERMOD E283.
- Evidence: VERIFIED (t2.py: TTRM, alpha=False, no ozone -> no message; PVMRM -> "ozone data required"). Message at validator.py:1782 says "E605 for NOXVALUE + NOX_VALS" for the ozone spec too; the ozone value+O3VALUES conflict is E148 (coset.f 585-615). Low.
- Fix: use `NO2STACK_METHODS` (already imported, includes TTRM per the E600 text at 1866) for the requirement, test `oz.spec().is_empty() and not oz.sector_values and not oz.by_sector`, add ALPHA check for TTRM/TTRM2.

### C10 [BUG] [medium] Source IDs: length, reserved names, case, duplicates across BuoyLine segments
- Where: validator.py:314-323 (`_validate_sources`)
- What: only exact-string duplicates of top-level `source_id` are reported. AERMOD uppercases the deck, limits IDs to 12 characters (E230), reserves BACKGROUND/BACKGRND (E285), and finds duplicates case-blind with `SINDEX`. BuoyLine segment IDs are separate sources (soset.f BLPARM) but are not in the duplicate set.
- Evidence: VERIFIED (t7.py, t8.py): `S1` and `s1` pass; `ABCDEFGHIJKLMNOP` passes; `A B` passes; `BACKGROUND` passes. soset.f 2063-2076 for E230/E285. BuoyLine segment duplicates: READ.
- Fix: collect `ids` including segment IDs, compare `.upper()`, and add `len > 12`, whitespace and reserved-name checks (same for group names, already limited to 8).

### C11 [BUG] [medium] One source with both GASDEPOS and particle categories is accepted
- Where: validator.py:748-779
- Evidence: VERIFIED (t9.py: gas + particle on one POINT source, nothing reported; the writer emits both GASDEPOS and PARTDIAM). soset.f 1189-1191: INPD > 0 with SOGAS = 'Y' is E289.
- Fix: `if gas_dep is not None and particle_dep is not None: error (E289)`.

### C12 [BUG] [low] Source range checks that disagree with soset.f (both directions)
- Where: validator.py:971-1304; area/volume/line/rline/buoyline validators
- Valid in AERMOD, error here (VERIFIED t3.py for volume): Volume `initial_lateral/vertical_dimension == 0` (VPARM: < 1e-5 is W320, reset to 1e-5; only negative is E209); Area Xinit/Yinit == 0 (APARM W320); LineSource width: AERMOD wants >= 1 m (E320) so 0 < width < 1 is the error, width 0 is also E320 (see below); RLineSource/RLINEXT width 0 is only W320 (RLPARM); BuoyLine segment `release_height > 3000` error is unreachable in AERMOD (BLPARM tests > 100 W320 first; E324 branch is dead), the error text is wrong. 
- Invalid in AERMOD, accepted here (VERIFIED t3.py for area/line): AreaSource `initial_sigma_z < 0` (APARM E209; not checked at all, t3.py); LineSource width in [0, 1) -> E320 (LPARM 3795-3799, t3.py width 0.5 gives nothing) and Line `initial_sigma_z`; Area/Line/Volume/Point `release_height` very large only warn so fine; RLINEXT `init_sigma_z > 42` -> E320 (RLPARM); Area `x/y` aspect > 100 W391 (warning not given); OPENPIT is the one source type checked against Fortran correctly.
- Fix: drive these from one table keyed by source class with (field, lower, strict, severity, code) copied from soset.f; see K1.

### C13 [BUG] [low] STARTEND not validated; `_check_met_dates` warns wrongly and contradicts `check_annual_met_coverage`
- Where: validator.py:2101-2110; validator_advanced.py:291-324, 344-354
- What: (a) only "all or none of six fields" is checked; month 13 / day 45 pass (t6.py), although `_startend_window` says "the base validator reports bad dates" (validator_advanced.py:354), which is untrue. meset.f STAEND 69-85, 100-115: month 1-12 and day <= IDYMAX are E203. End before start accepted: PLAUSIBLE (not read in meset.f). (b) With ANNUAL, a STARTEND of 2020-07-01..2021-06-30 (a full year; AERMOD counts a complete year from the first hour, `SurfaceFilePeriod.complete_years`, aermod.f 1006) gets "not a full calendar year" warning (t6.py), contradicting the coverage check that accepts it. (c) The single-day message says AERMOD "will skip ANNUAL output"; AERMOD stops with E480 (aermod.f 1006).
- Fix: validate month/day (and start <= end) in `_validate_meteorology`; delete `_check_met_dates` (the coverage check, or a simple "STARTEND span < 1 year" test, covers it) or compute the span rather than the calendar boundaries.

### C14 [BUG] [low] NaN, inf, None in source numerics: accepted or TypeError
- Where: all `_validate_*_source` range checks (`x <= 0`, `x < 0`)
- Evidence: VERIFIED (t8.py): `stack_height=nan` passes and the deck contains `nan`; `emission_rate=inf` and `x_coord=nan` pass; `stack_height=None` raises TypeError out of `Validator.validate` instead of a ValidationError. The background code already has `_is_finite_number` for exactly this.
- Fix: a field-check helper (K1) that applies `_is_finite_number` first.

### C15 [BUG] [low] Empty particle lists accepted
- Where: validator.py:782-873 / `_particle_values_as_written`
- Evidence: VERIFIED (t5.py): `ParticleDepositionParams()` with empty lists writes bare `PARTDIAM S1`, `MASSFRAX S1`, `PARTDENS S1` lines and the validator reports nothing (AERMOD E201 not enough parameters; the 0-length case is not flagged by E240/E335 loops). Fix: error when `not diameters`.

### C16 [BUG] [low] `advanced_validate` skips PointCap/PointHor and per-source messages repeat
- Where: validator_advanced.py:438-441 (`type(src).__name__ == "PointSource"`)
- Evidence: VERIFIED (t4.py): `PointCapSource` with diameter 0.001, velocity 200, emission 0 gets no warnings; the same values on `PointSource` give three. `PointCapSource`/`PointHorSource` subclass PointSource (sources.py:508, 520), so `isinstance` is the intent. Also the message name is hard-coded "PointSource(...)".
- Fix: `isinstance(src, PointSource)` and `f"{type(src).__name__}({id})"`.

---
## Concision

### K1 [CONCISION] [medium] Per-source range checks as a table
- Where: validator.py:915-1304 (390 lines): `_validate_point_source` 915-969, `_validate_area_source` 971-1007, `_validate_area_circ_source` 1051-1077, `_validate_area_poly_source` 1079-1099, `_validate_volume_source` 1101-1137, `_validate_line_source` 1139-1172, `_validate_street_canyon` 1174-1185, `_validate_rline_ext_source` 1187-1253, `_validate_buoyline_source` 1255-1304.
- What: 9 identical `if x.emission_rate < 0` blocks, 8 `release_height < 0`, 30 `<= 0` blocks, 3 zero-length-line blocks (1164, 1210, 1300), 3 identical 36-value building-array loops (949-957, 999-1007, 1129-1137). Each block is 5 lines.
- Change: `_RULES = {PointSource: (("stack_height", "gt", 0), ...), ...}` plus one `_check(result, name, src, field, op, bound, severity, code)` (which also does the `_is_finite_number` guard of C14) and a `_check_building_arrays` / `_check_zero_length` helper. Approximately 390 -> ~130 lines (about 260 removed). `described()` in _fields.py could carry `minimum=`/`exclusive_minimum=` too, which the GUI forms could reuse for input limits, but the AERMOD codes and severities (C12) belong in the validator table, so keep the table in validator.py and optionally derive GUI limits from it.
- Tests: tests/test_validator.py, tests/test_validator_so_tranche2.py (messages are asserted by substring; keep field names and "must be" wording).

### K2 [CONCISION] [low] Control-field helpers
- `extra = {str(o).upper() for o in getattr(control, "extra_model_options", []) ...}` appears 4 times (289, 671, 2119, 2420); pollutant-name normalisation 6 times (211, 887, 1694, 1837, 2195, 2236); "deposition enabled" (`calculate_deposition or ..._dry_ or ..._wet_`) 4 times (370, 753, 1032, plus the n_types sum 1552). A `ControlPathway.deposition_enabled` property and `pollutant_name` property (pathways.py), or three private helpers here, remove ~30 lines and the `getattr(control, "alpha", False)` defence (ControlPathway always has it; 6 sites).

### K3 [CONCISION] [low] Duplicated blocks inside the validator
- Ozone vs NOx background: validator.py:1892-1911 and 1928-1940 (sectors check, `_validate_background_spec`, by_sector loop, units) differ only in labels: one helper, ~18 lines.
- RANKFILE vs TOXXFILE loops (2385-2401, 2439-2457): same "period on AVERTIME / second card E211": ~12 lines.
- AWMADWNW vs ORD_DWNW (2496-2539): same "ALPHA / max count / valid option / duplicate" structure: ~15 lines via a small table.
- `_validate_cartesian_grid` / `_validate_polar_grid` (1985-2057): the num/delta blocks are four identical `if x is None and v <= 0` pairs per axis: loop over (axis, num, delta) tuples, ~30 lines.
- `_validate_gas_deposition` (880-913) emits "needs ALPHA" and "cannot combine with GASDEPVD" once per source, and `_require_alpha_and_flat` once per RLINEXT source: N identical messages for N sources; lift out of the per-source loop.

### K4 [CONCISION] [low] validator_advanced: dead and duplicated code
- `_iter_receptor_coords` (118-133, 16 lines): unused (grep src/ tests/ docs/: only the definition).
- `_check_dfault_consistency` + `NONDEFAULT_OPTION_FLAGS` (254-284): see C8; replace, do not keep.
- `_check_receptors` hard limit (213-220, C7) and `_check_met_dates` (291-324, C13).
- `_cart_values`, `_polar_distances`, `_polar_directions` (136-156): the `getattr(...); if callable` / fallback arithmetic is dead for real grids (receptors.py:121, 127, 269, 275 define `x_values`, `y_values`, `ring_distances`, `direction_angles`); each reduces to one call, ~12 lines. validator.py:1417 imports these private helpers from validator_advanced while validator_advanced imports `ValidationError` from validator (circular, worked around with lazy imports at validator.py:169, 368, 646...); moving the geometry helpers into receptors.py removes the cycle for them.
- Overlap with `__post_init__`: none. sources.py has no `__post_init__`; pathways.py has one (`MaxDailyContribution`, 1404), which the validator does not repeat. Overlap with validator_advanced: PointSource diameter/velocity/temp are checked in both (base errors on `<= 0`, advanced warns on plausibility; consistent apart from C4); `emission_rate == 0` warns only for PointSource in advanced and OpenPit in base (inconsistent, a table would apply it everywhere).

### Other
- `_validate_dfault_terrain` fires for the default `ControlPathway()` (terrain FLAT, regulatory_default True): every default project gets that warning (visible in all repro output). Accurate (coset.f W206) but noisy; a default of `terrain_type=ELEVATED` or `regulatory_default=False` would avoid it. Design call, not a bug.
- `_validate_source` (696-742) is an `elif` chain with no fallthrough for SidewashPointSource (no per-type checks; AERMOD's SWPARM only has the release-height check, which `_validate_source_options` does). The brief's concern about subclass order does not bite here: none of the source classes subclass each other except PointCap/PointHor under PointSource, which dispatch correctly; the one real class-identity bug is C16.

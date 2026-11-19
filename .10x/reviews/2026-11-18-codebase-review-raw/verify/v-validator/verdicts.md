# v-validator verdicts

Fortran: <repo>/aermod/ is v24142 (modules.f:1472 `VERSN /'24142'/`); bin/aermod reports 24142.
AERMOD evidence comes from setup-only runs (`RUNORNOT NOT`) of bin/aermod on probe decks in
verify/v-validator/probes/ (mk.py, mk2.py; .out files kept). Tests:
- verify/v-validator/test_validator_aermod_semantics.py (C1-C11, B4, B5)
- verify/v-validator/test_regulatory_dfault.py (F1, C8, DOCS-6)
At HEAD: 70 fail (the bugs) and 16 pass (guards that a fix must not break: 13 EPA decks that already validate,
unknown literal SRCGROUP member still E224, urban source without any URBANOPT still an error, regulatory_default=False
plus non-DFAULT options not flagged). Both files pass `ruff check` with the repo config.

## Deck count (B4/B5 acceptance target)

Script: verify/v-validator/count_decks.py (Validator.validate; identical to the `write(validate=True)` gate, input_generator.py:215-219).
count_write.py runs the actual to_aermod_input(validate=True) and gives the same numbers.

- tests/fixtures/epa_official (22) + test_cases/*/inputs (138) = 160 decks: **72 fail**. Every failure is a false error.
- All tests/fixtures/**/*.inp + test_cases = 252 files, 242 parse (10 are not decks): **81 fail, not 91**. The reviewer's 91 is not reproduced.

Distinct messages (count = decks with that message, 252-file set; the 160-deck set in brackets):

| # | count | message | verdict |
|---|---|---|---|
| 1 | 33 [33] | `source ID 'BACKGROUND' not found in project sources` (all 33 are BACKGROUND; bg_no2_*, no2_1yrAK_*) | FALSE (C2) |
| 2 | 18 [18] | `invalid pollutant 'X'` (BENZENE, CHROMIUM, SF6) | FALSE (C1) |
| 3 | 15 [14] | `must have at least one receptor grid or discrete receptor` (RE INCLUDED: flatelev, lovett, multurb, runner/success_included; RE EVALCART: in_urban) | FALSE (C3) |
| 4 | 10 [10] | `must contain at least one source` (SO INCLUDED: lovett, multurb, surfcoal) | FALSE (C3) |
| 5 | 8 [4] | `sources have is_urban=True but ControlPathway.urban_option is not set` (blp_urban; 4 AERSCREEN point_horiz decks, `URBANOPT 100000.`) | FALSE (C6/B5) |
| 6 | 7 [7] | `DEPOS/DDEP/WDEP ... no gas_deposition or particle_deposition (E242)` (testpart, testprt2: METHOD_2) | FALSE (C5) |
| 7 | 3 [3] | `stack_temp must be > 0 K, got 0` (mcr) | FALSE (C4) |
| 8 | 3 [0] | OPENPIT `release_height ... exceeds the effective pit depth (E322)` | LEGITIMATE (fixtures recorded with AERMOD E322) |
| 9 | 1 each [0] | particle E335/E332/E334/E240, OPENPIT x_dimension/release_height E209 | LEGITIMATE (validator_openpit/method1, openpit_errors; recorded aermod.out has those codes) |

So the target after the fix: 160/160 EPA decks validate; of all 252 files only the 4 intentionally-invalid fixtures
(runner/setup_error_e322_openpit, validator_openpit/{method1,openpit_errors,openpit_tiny_dimension}) still fail.
`test_epa_official_deck_validates` encodes the 22-deck part (9 fail at HEAD).

## C1 POLLUTID limited to 7 names: CONFIRMED (high)
coset.f POLLID 2512-2514 (`IFC==3 -> POLLUT = FIELD(3)`, no list), 2584. Only NO2/SO2/PM25 variants get special processing (2518-2520).
bin/aermod: POLLUTID CHROMIUM and BENZENE123 both finish setup with no message. POLLUT is CHARACTER*8 (modules.f:507), so a
>8-char name is silently truncated: worth a warning, not an error.
Tests: test_any_pollutant_id_is_accepted[...] (6), test_epa_official_deck_validates[testgas/testgas2/testprt2].
Blast radius: none outside the validator; PollutantType enum untouched. Keep NO2/SO2/PM25 alias logic.

## C2 / B4 SRCGROUP BACKGROUND / ranges / INCLUDED: CONFIRMED
soset.f SRCGRP 5876-5881 (ALL + BACKGROUND), 5905-5921 (other groups), 5925-5945 (literal ID, E224 if undefined), 5947-5960 (field
with '-' is a range). All 33 real-deck member errors are BACKGROUND. Range case reproduced synthetically (B4's t5.py and my test).
Caveat for the fix: BACKGROUND in a group WITHOUT background data is fatal E323 (soset.f 5890-5895, 5913-5918; bin/aermod probe
grp_bg_nobg: E323). So accept BACKGROUND/BACKGRND only when `sources.background` is set or an SO BACKGRND line is in
unparsed_lines; otherwise keep an error. Literal unknown IDs must remain an error (guard test). For INCLUDED, a warning is the
right severity (the validator cannot see the included file).
Tests: test_background_member_of_source_group_with_background_data, test_source_id_range_in_source_group_is_accepted,
test_unknown_literal_member_is_still_an_error (guard).

## C3 INCLUDED / EVALCART ignored by the empty-pathway checks: CONFIRMED (high)
aermod.f RECSIZ 7333-7352 counts DISCCART/EVALCART/DISCPOLR and calls PREINCLUD for INCLUDED. The genuinely empty case is
fatal (bin/aermod E185 "Either No Sources or No Receptors"), so keep the error when no INCLUDED/EVALCART line exists.
Tests: test_sources_from_so_included_count, test_receptors_from_re_included_or_evalcart_count[INCLUDED, EVALCART].
Blast radius: GUI tests (test_gui_v2_run.py:66-68, test_gui_v2_smoke.py:2157-2158) assert the empty messages; they still hold.

## C4 Stack temperature: CONFIRMED (high). Exact Fortran behaviour
soset.f PPARM (2713-2818), ATS = TEMP(3):
- 2770-2772: `ATS == 0` -> set to -1.0E-5 (ambient release, no message).
- 2773-2775: `ATS > 2000` -> W320.
- 2776-2781: `0 < ATS < 200` (strict both ends) -> **E320, RUNERR**. Ts = 200.0 is accepted.
- `ATS < 0`: no message in PPARM; calc1.f FLUXES 5965-5969 uses `TS = TA + |TS|` (constant Ts-Ta offset); 5971 `IF (TS < TA) TS = TA`.
bin/aermod: Ts 0 and -30 finish setup; Ts 100 and 199.9 give E320 PPARM; Ts 200 finishes.
Validator (validator.py:919-947) errors on Ts <= 0 and lets 0 < Ts < 200 through: both directions wrong.
Same routine: ADS < 0 E209, 0 <= ADS < 1e-5 reset to 1e-5 (2797-2802); AHS < 0 E209 (2759-2761); AVS < 0 W325 and reset (2784-2788).
So stack_diameter == 0 and stack_height == 0 are valid (validator errors on both).
Tests: test_zero_or_negative_stack_temp_is_valid[0, -30], test_stack_temp_between_0_and_200_kelvin_is_an_error[1, 100, 199.9],
test_zero_stack_diameter_or_height_is_valid[stack_diameter, stack_height].
Blast radius: tests/test_validator.py:251 (stack_height=0), :259 (stack_diameter=0), :263 (stack_temp=0) assert the old errors and
must be inverted. advanced `_check_point_source` (plausibility warnings) is unaffected. Whether exit_velocity < 0 should become a
warning (W325) is a maintainer call; AERMOD runs it.

## C5 E242 despite METHOD_2: CONFIRMED (medium)
soset.f METH_2 sets INPD(ISDX)=1 (5658, 5768); SRCQA 1181-1186 raises E242 only when INPD == 0 and no gas and no GASDEPVD.
Test: test_method_2_satisfies_deposition_requirement (+ EPA testprt2). One-line fix.

## C6 / B5 Urban source needs a name: CONFIRMED (medium)
pathways.py writer (900-928) emits URBANOPT when `urban_areas` or `urban_option` or `urban_population is not None`; the validator
(validator.py:336-341) requires `urban_option` only. coset.f URBOPT single-card form 4911-4925 takes population alone; bin/aermod
probe urb_pop_only (`URBANOPT 70889.0` + URBANSRC ALL) finishes setup. Population < 100 is E203 (4851-4854, 4917-4920; probe
urb_pop_50 gives E203) and is not checked.
Tests: test_urban_source_with_population_only[population, urban_areas], test_urban_population_below_100_is_an_error[2],
test_urban_source_without_any_urbanopt_is_an_error (guard).

## C7 100,000-receptor hard limit: CONFIRMED (medium). Exact Fortran behaviour
No fixed limit. aermod.f RECSIZ 7325-7352 pre-counts receptors (NREC += 1 per DISCCART/EVALCART/DISCPOLR; PRECART/PREPOLR add
ICOUNT*JCOUNT, 7429, 7711; INCLUDED via PREINCLUD), aermod.f:6560 `NREC = MAX(NREC,1)`, then ALLSETUP allocates every receptor
array to NREC (e.g. 4775-4785). reset.f overflow branches (e.g. 726-742, 1453-1469) are commented "This shouldn't occur since
limits are dynamically allocated". The only limit is memory. Only advanced_validate is affected (not the write gate).
Test: test_large_receptor_grid_is_not_an_error.
Blast radius: RECEPTOR_GRID_HARD_LIMIT is in validator_advanced `__all__` (454) and tests/test_validator_receptor_perf.py:39,
128-153 asserts the error. Keeping the constant (deprecated, or reused as a warning threshold) avoids an API break; the perf
test's purpose (skip the expensive extent walk on huge grids) can be kept with a warning.

## C8 / F1 / DOCS-6 Phantom DFAULT attributes: CONFIRMED (high: a deck AERMOD refuses is written and the profile says nothing)
Phantom names (none is a ControlPathway field or property; `dataclasses.fields(ControlPathway)` checked; no other src/ reference):

| phantom attr | where | real switch | AERMOD v24142 with DFAULT (coset.f MODOPT) |
|---|---|---|---|
| flat_terrain | regulatory.py:82; validator_advanced.py:254 | `terrain_type` FLAT/FLATSRCS (writes FLAT) | W206, FLAT dropped, run is ELEV (1639-1645, 1590-1593). Already warned by validator `_validate_dfault_terrain`; profile already checks terrain_type |
| no_stack_tip_downwash | regulatory.py:83; v_adv:255 | `"NOSTD" in extra_model_options` | W206, NOSTD ignored (1728-1736) |
| use_lowwind1, use_lowwind2 | regulatory.py:84-85; v_adv:256-257 | none. LOWWIND1/2/3 are not v24142 MODELOPT tokens | E203 invalid parameter with or without DFAULT (falls to the invalid-option branch at 1996-1998; probe dfault_lowwind3 / nodfault_lowwind3) |
| use_lowwind3 | v_adv:258 | none (as above); closest is `low_wind_option` -> CO LOW_WIND | LOW_WIND keyword needs ALPHA: E133 (coset.f 374-385); ALPHA is impossible under DFAULT |
| beta_options | regulatory.py:86; v_adv:260 | `beta` | E204 (1880-1885) |
| use_nondefault | v_adv:253 | the inverse of `regulatory_default` | n/a |
| use_area_rural | v_adv:259 | no counterpart ("ARM mode" comment is wrong) | n/a |

Real options not looked at by either check, and AERMOD's response under DFAULT: `alpha` E204 (1868-1872), `psd_credit` E204
(1852-1861), extra tokens FASTAREA E204 (1887-1899), FASTALL E204 (1900-1916), SCIM E204 (1766-1773), NOURBTRAN E204
(1917-1929), AREADPLT E204 (1705-1712), HBP E204 (1801-1804), TTRM2 E204 (1825-1828), TTRM E198 (1810-1815, L_ALPHA is never
set under DFAULT); NOCHKD W206 (1738-1748), SCREEN W206 (1756-1765). bin/aermod probes: DFAULT ALPHA, DFAULT BETA, DFAULT
FASTAREA -> E204; DFAULT NOSTD, DFAULT FLAT -> W206 and setup completes.
HEAD behaviour: `Validator.validate` + `advanced_validate` on DFAULT+alpha return nothing at all; profiles' check()/apply() ignore
alpha, beta, NOSTD (apply leaves `MODELOPT CONC ELEV DFAULT ALPHA`).
Tests faking the attributes with setattr on the dataclass instance:
- tests/test_regulatory.py:68-74 (`flat_terrain`, `no_stack_tip_downwash`, test_apply_disables_nondefault_flags)
- tests/test_regulatory.py:101-103 (`use_lowwind1`, test_forbidden_flag_warns)
- tests/test_validator_advanced.py:158, 165 (`flat_terrain`, TestDFAULTConsistency) calling `_check_dfault_consistency` directly
- docs/regulatory-matrix.md:73-74 shows the phantom names in a custom-profile example.
New tests: test_regulatory_dfault.py: test_profile_check_reports_nondefault_option and test_profile_apply_removes_nondefault_option
(alpha/beta/NOSTD x 3 profiles), test_dfault_with_fatal_nondefault_option_is_an_error (ALPHA, BETA, PSDCREDIT, FASTAREA, FASTALL,
SCIM, NOURBTRAN, AREADPLT), test_dfault_overridden_option_is_warned (NOSTD, NOCHKD, SCREEN), guard
test_nondefault_options_without_dfault_are_fine.
Blast radius: `forbid_nondefault_flags` is a public dataclass field and documented for custom profiles; changing its meaning
(attr names -> MODELOPT tokens) changes public API, and users who copied the doc example hold phantom names. Suggest keeping the
field but interpreting entries as MODELOPT tokens/field names, and mapping the old names. Making DFAULT+ALPHA a base-validator
error blocks `write()` of such projects (correct: AERMOD refuses them), and every ALPHA-gated check (RLINEXT, METHOD_2, GASDEPOS
defaults, ...) currently "passes" with alpha=True under DFAULT although AERMOD clears L_ALPHA.

## C9 TTRM / empty OzoneData: CONFIRMED (medium)
coset.f 554-570 E283 for OLM/PVMRM/RUNTTRM/GRSM without OZONEVAL/OZONEFIL/O3VALUES; MODOPT 1810-1815 TTRM needs ALPHA (E198).
bin/aermod: ALPHA TTRM without ozone -> E283 "... Needed for TTRM"; TTRM without ALPHA -> E198.
Tests: test_ttrm_without_ozone_is_an_error, test_empty_ozone_data_is_an_error (OLM + OzoneData()), test_ttrm_without_alpha_is_an_error.

## C10 Source IDs: CONFIRMED (medium)
soset.f SOLOCA 2063-2076: >12 chars E230, BACKGROUND/BACKGRND E285. AERMOD upper-cases the runstream, so `stack1` duplicates
`STACK1`: bin/aermod gives E310/E315 duplicate LOCATION/SRCPARAM. The BuoyLine-segment part was not checked (READ only by reviewer).
Test: test_invalid_source_ids_are_errors[("S1","s1"), 13-char, BACKGROUND, BACKGRND].

## C11 Gas and particle on one source: CONFIRMED (medium)
soset.f SRCQA 1187-1191 E289. Test: test_gas_and_particle_deposition_on_one_source_is_an_error.

## Extra, for the orchestrator
1. `low_wind_option` is unusable as documented: the writer emits `CO LOW_WIND LOWWIND3` (pathways.py:930-931), but LOW_WIND
   takes numbers (SVMIN etc., coset.f LOW_WND 6779-6850): bin/aermod gives E208, and E133 without ALPHA. The profiles'
   `allowed_low_wind=("LOWWIND3",)` and docs/regulatory-matrix.md:14 refer to the removed LOWWIND BETA options (E203 now).
   Under DFAULT no low-wind option is legal. Not filed by any reviewer as far as I saw; needs its own finding.
2. GRSM: v24142 accepts it with DFAULT (coset.f 1835-1849, DFAULT/BETA checks commented out by D182). regulatory.py notes
   call it non-DFAULT; that is a regulatory-policy statement, not AERMOD behaviour. Maintainer call.
3. The 91-of-252 figure in slice-b.md should read 81 of 252 (242 decks).

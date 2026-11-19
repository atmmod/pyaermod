# Slice F review: regulatory post-processing (slice-f)

Scope read in full: design_values.py, naaqs.py, psd.py, regulatory.py, regulatory_parity.py, chemistry_presets.py, docs/design-value-validation.md, docs/psd.md, docs/regulatory-matrix.md, plus gui_v2/run_results.py NAAQS section.
Premise note: src/pyaermod/psd.py and docs/psd.md are PARTICLE SIZE DISTRIBUTIONS for Method 1 deposition, not Prevention of Significant Deterioration increments. There is no PSD increment arithmetic in this slice. I ran every number in docs/psd.md (0.0308, 0.527, 12 bins, anchor_ratio 1.25 / 2.5 / 0.649, 0.63/1.85/3.88/7.77) against the code: all match. psd.py: no bug found.
Repro scripts: scratchpad/repro/slice-f/r1..r6.py. Not checked: eCFR text (WebFetch to Cornell 404'd), so every citation below is from memory and is marked.

## Bugs

### F1 [BUG] [high] RegulatoryProfile lints/forbids attributes ControlPathway does not have, so BETA/ALPHA/NOSTD pass silently
- Where: src/pyaermod/regulatory.py:81-87, 115-119, 151-156; tests/test_regulatory.py:68-76
- What: forbid_nondefault_flags = flat_terrain, no_stack_tip_downwash, use_lowwind1, use_lowwind2, beta_options. None exists on ControlPathway (pathways.py:635-). getattr(ctrl, attr, None) is always None, so check() and apply() never act on them. The real switches (ctrl.alpha, ctrl.beta, "NOSTD" in extra_model_options) are not looked at. docs/regulatory-matrix.md says BETA options and NOSTD are "not permitted"/"don't add".
- Evidence: VERIFIED (r4.py). Project with beta=True, alpha=True, extra_model_options=["NOSTD"], terrain FLAT: EPA_APPENDIX_W_2023.check() returns only terrain and low-wind warnings; apply() changes only terrain; the deck is `MODELOPT CONC ELEV DFAULT ALPHA BETA NOSTD`. Tests pass because they setattr phantom attributes onto the dataclass (test_regulatory.py:68-76).
- Fix: forbid by real names: check `ctrl.alpha`, `ctrl.beta`, `"NOSTD" in ctrl.extra_model_options` (apply clears them); keep terrain via terrain_type. Rewrite the tests to use real fields.

### F2 [BUG] [medium] apply_deposition_defaults leaves a project that GUI v2 cannot save
- Where: src/pyaermod/chemistry_presets.py:403, 408 (and PollutantDepositionDefaults.method, 167)
- What: sets src.deposition_method = DepositionMethod.GASDEPVD (bare enum). The field is Optional[Tuple[DepositionMethod, float]] and, per sources.py:31-45, writes nothing to the deck. Also particle defaults (PM25/PM10) get method GASDEPVD (dataclass default), contradicting the comment "DRYDPLT is the usual method".
- Evidence: VERIFIED (r5.py): after apply_deposition_defaults, gui_v2.project_io.check_project raises "deposition_method must be a JSON list, not a JSON object". Deck output is unaffected.
- Fix: delete the two `src.deposition_method = ...` assignments (the field is a no-op) and drop `method`/`notes` plumbing if nothing else reads it. Saves ~6 lines.

### F3 [BUG] [medium] Calendar-year grouping splits a met year that does not run Jan-Dec
- Where: design_values.py:289 (_annual_rank_per_receptor), 495-499, 593-594 (PM10 n_years), 708
- What: every annual rank, and the n_years that decides the PM10 rank, use calendar years. AERMOD's year is the met-data year ending at the date of the first met hour (CHK_ENDYR, aermod.f:8028-8077; NUMYRS counted there, SUMHNH/NUMYRS at 987-998). A Jul-Jun year becomes two partial calendar years, each ranked on its own day count, then averaged.
- Evidence: VERIFIED (r1.py): 365 days 1..365 starting 2019-07-01 gives PM2.5 24-h DV 271.5 with n_years=2; a single year ranked at 8th highest gives 358. PM10 with 4 Jul-start years reports n_years=5 and picks H6H (App W Table 8-2 allows five exceedances only over five years). This is open item "partial calendar years" from 11-11: still present at HEAD.
- Fix: add a `year_end=(12, 31)` (month, day) argument that labels each row's year by that boundary (as AERMOD's IENDMN/IENDDY do), used by all ranked forms and PM10 n_years. Smallest alternative: warn when any receptor-year has under ~350 days.

### F4 [BUG] [medium] naaqs_output_pathway("PM25") raises KeyError
- Where: design_values.py:747-749; naaqs.py:152-178 (get_naaqs)
- What: the docstring and `key in ("PM2.5","PM25")` accept the POLLUTID spelling, but get_naaqs("PM25", ...) does not map it (naaqs.py has _POLLUTID_KEYS only for naaqs_averaging_periods).
- Evidence: VERIFIED (r2.py): "PM2.5" ok, "PM25"/"pm25" KeyError. No test uses "PM25" there.
- Fix: apply `_POLLUTID_KEYS` inside get_naaqs (one line) so every caller accepts POLLUTID names.

### F5 [BUG] [medium] NaN daily values rank as the highest value
- Where: design_values.py:270-275 (_nth_highest), 288-296
- What: np.sort puts NaN last, so NaN is picked as the top and a NaN day also counts in n_days for the rank table. A NaN anywhere shifts the selected value by one rank (or returns NaN for rank 1).
- Evidence: VERIFIED (r1.py): 365 days 1..365 with day 11 NaN, PM2.5: returns 359; 8th highest of the 364 valid days is 358 (rank for 364 days is still 8). With rank 1 the result is NaN. NaN reaches the frame via blank CSV values, NaN in a background dict, or an all-NaN day in the hourly mean.
- Fix: `values = values[~np.isnan(values)]` in _nth_highest, and count valid days only in _annual_rank_per_receptor (dropna on the daily frame).

### F6 [BUG] [medium] o3_8hr_design_value: AERMOD 8-HR values are fixed blocks, not rolling averages
- Where: design_values.py:606-621 (docstring "rolling-average")
- What: AERMOD forms N-HR averages at `MOD(IHOUR,KAVE).EQ.0` (aermod.f:1854), so an 8-HR POSTFILE holds three non-overlapping block averages per day (ending 08, 16, 24). Appendix U wants the daily maximum of running 8-h averages (24 start hours). The max of three blocks is at most the rolling max, so the DV is biased low (non-conservative). The 11-11 "O3 8-h day assignment" item is moot for AERMOD input (blocks never straddle midnight), but this one is not.
- Evidence: READ (Fortran line cited). Also no check that `ave` is 8-HR: 1-HR input silently gives the max hourly value.
- Fix: correct the docstring/docs table, and either require ave == 8-HR or build rolling 8-h means from 1-HR values. See POLICY P5.

### F7 [BUG] [low] NaN hours count as coverage in the annual NO2 75 % test
- Where: design_values.py:1024-1025 (`_n=("_unit","nunique")`)
- What: counts rows, including NaN-concentration rows; the mean skips them.
- Evidence: VERIFIED (r3.py): 2019 full at 10, 2020 with 20 % valid hours at 50 and the rest NaN: DV 50; expected 10 (2020 is 20 % covered). Needs NaN input.
- Fix: `work.dropna(subset=["concentration"])` before grouping.

### F8 [BUG] [low] Rows with an impossible date are dropped silently
- Where: design_values.py:116-124 (errors="coerce"), 257-262 and 495 (groupby drops NaT keys)
- Evidence: VERIFIED (r3.py): a row with date 19130124 (month 13) vanishes; result is the other row. Only the NO2-annual path validates dates (_no2_stamps).
- Fix: raise when `stamp.isna().any()` in _parse_yymmddhh_to_date, as _no2_stamps does.

### F9 [BUG] [low] Hourly frame without an `ave` column gets the daily MAX where the daily MEAN is required
- Where: design_values.py:237-241, 256
- Evidence: VERIFIED (r3.py): hourly 0..23 repeated, no ave column, pm25_24hr_design_value gives 23.0; the 24-h average is 11.5. Fine for real POSTFILE frames; wrong for a CSV round trip that drops the column.
- Fix: treat a missing `ave` as hourly when `how == "mean"`, or raise.

### F10 [BUG] [low] PM10 24-h rank rule (open item 11-11, still present)
- Where: design_values.py:593-594; naaqs.py:89-91
- What: rank = 6 if calendar n_years >= 5 else 2. Two to four years use H2H (conservative), more than five years still H6H, and a partial extra calendar year flips it (see F3). naaqs.py form text says "(5-yr avg)", but 40 CFR 50.6 states the 3-year average form (from memory). See POLICY P6.

### F11 [BUG] [low] Warning stacklevel points inside the module for O3 and for naaqs_compliance_report
- Where: design_values.py:314 (stacklevel=3 in _average_across_years); o3_8hr_design_value adds a frame, as does naaqs_compliance_report.
- Evidence: READ. The year-count warning is attributed to design_values.py, and Python's default filter then shows it once per session, hiding later mismatches (the module itself explains this problem at 375-379).
- Fix: pass stacklevel from the public functions (as _score_postfile_pair does in regulatory_parity.py).

## POLICY (for the maintainer; not to be changed without a decision)

- P1 Rounding before comparison (open item, present). `exceeds` uses the unrounded µg/m3 value against the µg/m3 level (design_values.py:1187). From memory: App N rounds the PM2.5 annual DV to 0.1 µg/m3 and the 24-h DV to the nearest 1 µg/m3 (2024 revision); App S/T round NO2/SO2 DVs to the nearest ppb; O3 truncates to ppb (App U). Example: SO2 75.4 ppb is 197.44 µg/m3 and exceeds here, but rounds to 75 ppb and meets. A ppb-rounded comparison needs a µg/m3 to ppb back-conversion. Cite: 40 CFR 50 App. N 4.x, S 4.x, T 4.x, U (verify each).
- P2 PM2.5 citation 50.18 vs 50.20 (open, present). naaqs.py:83-86 uses 50.18 for the 9.0 µg/m3 annual standard; from memory the 2024 level is in 40 CFR 50.20 and 50.18 holds the 2012 12.0 level (89 FR 16202, 6 Mar 2024). The 35 µg/m3 24-h level is in both.
- P3 Annual PM2.5 mean (design_values.py:1153-1156). Appendix N forms the annual mean as the mean of the four calendar-quarter means, not the mean of all days. Verified difference on constant-by-quarter data: 20.082 here vs 20.000 (r3.py); it can flip a close call. Hourly input also gets no 18-of-24-hour daily validity rule (App N) and no per-quarter 75 % completeness, though the 8760-hour model output is normally complete.
- P4 NO2 annual completeness is applied to the whole year (75 % of hours, days or months, design_values.py:1031). I could not confirm whether Appendix S requires 75 % in each calendar quarter; this was the PR #70 finding's basis ("from search excerpt", 11-17 verification). Please confirm. The citation 50.11(e) in the docstrings also needs confirming (11-11 review wrote 50.11(b)).
- P5 Ozone: Appendix U daily maximum 8-h value belongs to the day the 8-h period BEGINS, uses running averages, and needs 75 % valid periods (from memory). See F6.
- P6 PM10 rule: App W Table 8-2 (from memory): H6H for five years of NWS met, H2H for one year site-specific. Behaviour for 2-4 or 6+ years is the project's choice, and docs/design-value-validation.md:27 states only the 5-year and 1-year cases.
- P7 ARM2 under Appendix W. chemistry_presets.py:89-95 and :143 say ARM2 is "not accepted by Appendix W"; docs/use-cases.md:206 says Tier 2 is ARM2 (the 2017 Appendix W, 4.2.3.4, adopted ARM2 as Tier 2, from memory; 82 FR 5182). regulatory.py profiles list allow_chemistry_methods=("OLM","PVMRM"), so check() warns on ARM2, and ChemistryOptions.method defaults to ARM2 (pathways.py:504), so a default project is flagged under every profile. The repo contradicts itself; the maintainer must decide.
- P8 2017 profile text (open, present). regulatory.py:187-201 says LOWWIND3 and ADJ_U* are permitted "for documented cases" and that "GRSM was still BETA in 2017"; docs/regulatory-matrix.md:40 says ADJ_U* is permitted with agency review in 2023. PLAUSIBLE problems: GRSM did not exist in the 2017 model (v16216; I believe it arrived in later versions), LOWWIND3 is a BETA option, and ADJ_U* became a default in later AERMET/AERMOD. Needs a check against the model-version release notes.

## Open items from 11-11 and PR #70: status at HEAD
- PM10 rank hard-coded: present (F10, P6). O3 8-h day assignment: present but see F6. PM2.5 50.18 vs 50.20: present (P2). Partial calendar years: present (F3). No rounding: present (P1). 2017 profile text: present (P8).
- PR #70 annual NO2 (highest single complete year, 75 %): implemented consistently. naaqs_compliance_report is the only producer; gui_v2/run_results.py:524-534 treats AERMOD's multi-year ANNUAL value as a "lower bound" and never calls the report for annual standards (consistent, if less informative: it never computes the highest-year value from a 1-HR POSTFILE). Remaining gap: F7 and P4 above.

## Docs vs code
- docs/design-value-validation.md:26 says O3 uses "daily max 8-hour average"; code takes AERMOD block values (F6).
- design-value-validation.md:27 vs naaqs.py:89-91 vs code 593: three different statements of the PM10 form (pooled 5-yr H6H / "5-yr avg" / 3-yr in 50.6) and the code's rank-2 fallback is undocumented.
- regulatory-matrix.md:15, :40 vs chemistry_presets.py:89-95 and use-cases.md:206: ARM2 status (P7).
- regulatory-matrix.md:16-17 promises NOSTD/BETA are rejected; code does not (F1).
- chemistry_presets.py:137-143 docstring orders PVMRM (>=5 sources) before GRSM; code returns GRSM first when a NOx background exists.
- docs say 47 PST/PLT pairs (design-value-validation.md:72) and local archive memory says 46 decks: not checked.

## Concision (no behaviour change)
- C1 design_values.py:509-571 (pm25/no2/so2_1hr, 63 lines) are one pipeline `_annual_rank_per_receptor(_daily_series(df, how), pct) -> _average_across_years -> assign(form, ...)`. Drive them from `get_naaqs(...)` (percentile, form, averaging_period already live in NAAQS_TABLE, which design_values currently ignores except for the rank): one `_percentile_design_value(df, std, how, n_years)` of ~15 lines plus three 3-line wrappers. Saves ~30 lines. Covered by tests/test_design_values.py, test_naaqs_rank_tables.py, the EPA known-answer tests.
- C2 design_values.py:1149-1175 (27-line if/elif in naaqs_compliance_report) becomes a dict {pollutant: (fn, table key, period)} of ~12 lines; the PM2.5 annual branch's no-op `.rename(columns={"concentration": "concentration"})` (1153) goes. Saves ~15 lines.
- C3 `nth_highest_daily_max_design_value` (496-499) repeats `_annual_rank_per_receptor`'s per-year loop (288-296): give the latter a `rank_of(n_days)` callable; O3 and the 98/99 forms then share it. ~10 lines.
- C4 Duplicate year-from-YY logic at 108 and 119-120 (`_parse_yymmddhh_to_year` can be `_stamp_text_to_date(...).dt.year`... except it is used without the month parse; keep one two-digit-year helper). ~5 lines.
- C5 chemistry_presets.py:39-126: olm/pvmrm/grsm presets are the same body three times; one `_ozone_preset(method, ...)` saves ~25 lines. Covered by tests/test_chemistry_presets.py.
- C6 regulatory.py: apply() and check() both recompute the terrain name (106-110, 140-144) and the flag loop; a helper saves ~8 lines.

## Dead code (grepped src/ and tests/)
- `design_values._agg_daily_max` (265-267): no callers anywhere. Remove.
- `DesignValue` dataclass (42-51): never constructed; exported in api.py and __all__. Public API, so deprecate rather than remove.
- `annual_mean(pollutant=...)` argument (424): never read.
- `regulatory_parity.py:158-163` second `__all__` replaces the first (33-40), dropping VALIDATED_AERMET/AERMOD_VERSIONS from `__all__` although tests import them from here (tests/test_versions.py:50): delete the second block.
- `EPA_APPENDIX_W_2023_BETA_METHODS` (regulatory.py:235): used only by one test; check() never reads it, and "PVMRM2" is not a ChemistryMethod member.
- PERCENTILE_98/99_RANK_TABLE (design_values.py:142-151): used only by tests, as an oracle; keep.

## Not looked at
tests beyond grep; eCFR text; Fortran for MAXDAILY/MXDYBYYR record formats (tests with real AERMOD output cover them); the rest of gui_v2 beyond the NAAQS block; whether apply_chemistry's duplicate olm_groups on a second call matters (low).

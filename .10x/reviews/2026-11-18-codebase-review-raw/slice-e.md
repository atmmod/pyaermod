# Slice E review: output parsing (output_parser.py, aermod_outputs.py, postfile.py)

Reviewer: slice-e. Read-only. Repro scripts: scratchpad/repro/slice-e/t1..t14.py (S = the scratchpad root).
Fortran checked: aermod/calc2.f (POSTFL, AVER, TOXXFL), output.f (PSTANN, PLOTFL, RANKFL, SHOUT, PRTSUM, PERAVE), ouset.f (OUPOST/OUMAXI/OUTOXX headers, format assignment), setup.f:1788-1792 and coset.f:1367 (default FORMATs), inpsum.f (source and receptor echo), aermod.f (HRLOOP, NUMYRS/PSTANN).
Labels: VERIFIED = ran a script; READ = code/Fortran reading only; PLAUSIBLE = not confirmed. Where a repro file is synthetic I say so (no real multi-year plotfile, binary ANNUAL POSTFILE, TOXXFILE or SEASONHR fixture exists in tests/fixtures).

## What checked out clean (no finding)
- PLOTFILE/POSTFILE/RANKFILE/MAXIFILE text layouts and FORMATs (setup.f:1788-1792, ouset.f:3054-3069): fixed-width slicing from the printed FORMAT line, NETID blank handling, date as I8 (unpadded in PLOTFILE) vs I8.8, PERIOD/ANNUAL rows carrying IANHRS/NUMYRS in the date column: all match the Fortran.
- Fortran number forms: `0.782577-103`, `1.0D+02` read via _fortran.fortran_float in all three modules (rank_1h.rnk, maxi_1h.max fixtures read correctly).
- Summary-table row regex vs PRTSUM FORMATs 1002-1005/1012-1015 (A8 group, F14.5 + A1 flag, ON I8.8:, AT (F11.2...)): consistent; `*` overflow in the value maps to NaN; calm/missing flags kept; page-break headers merge (group never splits across pages: NGPP logic in PRTSUM).
- Hour 24 / leap years: these modules keep dates as raw YYMMDDHH text/ints, so there is nothing to mis-handle in them (the century pivot of 50 lives in design_values._stamp_text_to_date, see E13).
- Unformatted POSTFILE record layout vs POSTFL (calc2.f:2935) and PSTANN (output.f:222): KURDAT, KAVE|IANHRS|NUMYRS, GRPID, ((val(irec),irec),ityp) all match; no header records in a binary POSTFILE; value block order is right.

---

### E1 [BUG] [medium] A multi-year ANNUAL binary POSTFILE is silently mislabelled as 1-HR/2-HR/3-HR/4-HR
- Where: postfile.py:1047-1081 (`_label`), 1026-1027 (`_warn_one_record` only when every group has one record)
- What: PSTANN writes one record per year with the *running* NUMYRS (aermod.f:8070 `NUMYRS = NUMYRS + 1` precedes `CALL PSTANN`; output.f:222 writes NUMYRS). So an N-year ANNUAL file holds records with IANHRS = 1, 2, ..., N at KURDAT hour 24 (Dec 31). Without `averaging_period`, `_label` reads IANHRS 1,2,3,4 as `N-HR` (24 % N == 0) and the "one record per group" warning does not fire because the group has several records. Years 5 and above raise the ValueError that asks for averaging_period, so only 2-4 year files (and the first rows of longer ones before the raise) are affected. Annual means are then treated as hourly/2-hourly values downstream (design_values `_is_hourly` etc.).
- Evidence: VERIFIED with a synthetic file built to the PSTANN layout (repro/slice-e/t10.py): 3 records (88123124/1, 89123124/2, 90123124/3) read as ave 1-HR, 2-HR, 3-HR, no warning. With averaging_period="ANNUAL" the dates are 00000001..00000003 as intended.
- Fix: in inferred mode, if one group's records have more than one distinct IANHRS, that cannot be a short-term file (KAVE is constant per file); label the file ANNUAL (or raise "pass averaging_period") instead of per-record N-HR. About 6 lines in `_parse` after the loop, or in `_label` with per-group state.

### E2 [BUG] [medium] Text POSTFILE/PLOTFILE rows with an overflowed (`*****`) field are dropped silently; the three readers disagree
- Where: postfile.py:706-727 (`float(...)`, `fortran_float`, `except ValueError: return None`), aermod_outputs.py:283-289 (`_coerce` keeps the string), output_parser.py:174-178 (`_float_or_nan`)
- What: F13.5 (PSTFRM/PLTFRM, setup.f:1789-1790) prints 13 asterisks for |value| >= 1e7 (also a UTM northing of exactly 10,000,000 at the equator, F13.5). `PostfileParser._parse_data_line` raises inside the try and returns None, so the receptor/hour row vanishes without a warning; the file then has fewer rows than receptors, which skews max-by-receptor, means and rankings. `read_aermod_aux_file` keeps `"*************"` as a str, giving an object-dtype column; the .out parser turns asterisks into NaN. 
- Evidence: VERIFIED (repro/slice-e/t7.py, width-preserving edit of tests/fixtures/postfile_types/conc/high_1h.plt): read_postfile returns 2 of 3 rows; read_aermod_aux_file returns 3 with AVERAGE_CONC a str.
- Fix: one helper in _fortran.py (`fortran_float_or_nan`: stars -> nan, existing NaN/Inf handling) used by all three modules; in postfile.py store NaN instead of returning None, and warn once ("n rows had overflowed fields").

### E3 [BUG] [medium] PostfileParser mis-reads the multi-year "MAX DAILY ... AVERAGED OVER n YEARS" PLOTFILE (open 11-11 item: still present)
- Where: postfile.py:615-629 (header regex, `_is_plotfile` only for "PLOT FILE OF HIGH"), 672-727 (row layout)
- What: PLOTFL with PM25AVE/NO2AVE/SO2AVE (output.f:437, FORMAT 9009, PLTFRM coset.f:1367) writes `X Y SUMHNH ZELEV ZHILL ZFLAG AVE GRP RANK NETID` followed by NUMYRS pairs (value, date). Header text is `PLOT FILE OF   1ST-HIGHEST MAX DAILY 24-HR VALUES AVERAGED OVER n YEARS FOR SOURCE GROUP: ALL`: `_is_plotfile` stays False, so `date` = the RANK token ("1ST"), `rank` is absent, the per-year values/dates are discarded, and `header.source_group` stays None (the optional FOR SOURCE GROUP group is not reachable after "AVERAGED OVER n YEARS"). tests/test_real_cases.py:526 already notes the parser "doesn't fully handle yet".
- Evidence: VERIFIED on a synthetic file written with the real FORMAT (repro/slice-e/t3.py): read_postfile gives date "1ST"; read_aermod_aux_file reads the same file correctly (names AVER_CONC_YR1, DATE_YR1, ...) because it slices by the printed FORMAT. 
- Fix: detect `\d+(ST|ND|RD|TH)-HIGHEST MAX DAILY` as a plotfile with rank at parts[7+k] and treat the tail (value, date) pairs as `yr{n}_value`/`yr{n}_date` columns; or, better, see C2 (build PostfileParser on the aux reader). Group regex: allow text between VALUES and FOR SOURCE GROUP.

### E4 [BUG] [medium] aermod_outputs header detection fails on real files: file_type None for RANKFILE, MAXIFILE, SEASONHR; averaging_period/rank wrong or None for short-term PLOTFILEs; read_deposition rejects real deposition files
- Where: aermod_outputs.py:60-64 (`_TYPE_RE`), 80-87 (`_AVG_RE`, `_RANK_RE`), 330-346 (`_infer_columns`), 462-464 (`read_deposition`)
- What (all against real AERMOD headers: ouset.f:1175 `MAXI-FILE FOR`, output.f:2963 `RANK-FILE OF`, output.f:2827 `FILE OF SEASON/HOUR VALUES`, output.f:567 `PLOT FILE OF  HIGH   1ST HIGH 24-HR VALUES`):
  1. `_TYPE_RE` needs `RANKFILE`/`RANK FILE`/`SEASONHR`/`MAXIFILE`; real headers are `RANK-FILE`, `MAXI-FILE`, `SEASON/HOUR`, so file_type is None. `_read_expecting` then accepts any file (its mix-up guard is off): read_rankfile on a PLOTFILE passes, read_plotfile on a RANKFILE passes.
  2. Real short-term PLOTFILE headers give `averaging_period=None` (the `_AVG_RE` alternatives never meet "HIGH  1-HR VALUES") and `rank`: `(HIGH|H)[- ]?(\d+)` skips "HIGH   1ST" (three spaces) and "HIGH  1-HR" (two) but matches "HIGH 24-HR": the 24-HR and 12-HR fixture files report rank 24 and 12 for the 1st-highest file.
  3. DDEP/WDEP/TOTDEP are not file types AERMOD writes (deposition goes in a PLOTFILE with a `DRY DEPO` column), so `read_deposition(ddep_01H.plt)` raises "looks like 'PLOTFILE'"; it only accepts invented files. `concentration_column` returns None for such a file, so `.values()` is empty.
  4. `_infer_columns("SEASONHR")` (X, Y + 96 season-hour slots) is unreachable (file_type is never SEASONHR) and wrong: SHOUT (output.f:2814) writes one row per receptor, season, hour: X Y value ZELEV ZHILL ZFLAG GRP NHRS SEAS HOUR NETID.
- Evidence: VERIFIED: repro/slice-e/t2.py over every fixture (all real `.plt` short-term files: averaging None; pyaermod_24H.plt rank 24; rank_1h.rnk and maxi_1h.max file_type None), t8.py (SEASONHR file_type None, headerless columns COL1..), t9.py (read_deposition error). Consumers are not hurt today because run_results.py:243 prefers the AVE column and ensemble.py reads columns by name; `aermod parse`/`plotfile` CLI prints "averaging: ?", and tests only use invented headers (test_aermod_outputs.py:45 `rank == 8`).
- Fix: replace the type table with the real headings (`PLOT FILE OF`, `POST/PLOT FILE`, `MAXI-FILE`, `RANK-FILE`, `SEASON/HOUR`), take the period from `HIGH\s+\w+\s+HIGH\s+(\S+)\s+VALUES`/`PERIOD`, the rank from `HIGH\s+(\d+)(?:ST|ND|RD|TH)\s+HIGH`; drop DDEP/WDEP/TOTDEP (keep `read_deposition` as an alias of read_plotfile that checks for a deposition column); delete the SEASONHR branch of `_infer_columns`. About 20 lines changed.

### E5 [BUG] [medium] read_toxxfile / ToxxFile.read() cannot read a real TOXXFILE (it is unformatted binary)
- Where: aermod_outputs.py:457-459, pathways.py:1500-1526
- What: ouset.f:2438 opens the file `FORM='UNFORMATTED'`; calc2.f:3141 writes arrays of IDCONC (int, `100000*ILINE + 1000*IG + IREC`) and TXCONC (double) after 3 header records (ouset.f:2446-2449). The reader decodes it as latin-1 text lines. pathways.py's docstring already says "which reads the text layout of the same records", i.e. the text layout is invented.
- Evidence: VERIFIED: a binary file built to that layout returns 4 garbage records with file_type None (repro/slice-e/t14.py); no real TOXXFILE exists in tests/fixtures.
- Fix: either a small binary reader (3 header records, then pairs of records NPAIR ints / NPAIR doubles; NPAIR is not in the file, so take it from the record length) or make read_toxxfile raise NotImplementedError for a non-text file. TOXXFILE is rarely used; the minimum fix is a guard.

### E6 [BUG] [low-medium] On real AERMOD output ModelRunInfo's date/period/jobname fields are never filled; CLI and plot titles show "Unknown"
- Where: output_parser.py:318-330, 332-343, 356-361, 379-387
- What: the regexes look for `Jobname:`, `Run Date:`, `Run Time:`, `Averaging Time Period`, `** Model Setup Options Selected **`, `STARTING DATE:`. None of those strings exists in AERMOD's Fortran (grep of aermod/*.f finds none); they come from hand-written test text. A real .out gives jobname "Unknown", run_date/run_time/start_date/end_date None, averaging_periods []. `visualization.py:261` then titles plots "ANNUAL Average Concentration\nUnknown", and `aermod parse` prints `jobname: Unknown` and no averaging line. `urban_option` is never set.
- Evidence: VERIFIED over all 6 real .out fixtures (repro/slice-e/t4.py): version/title/pollutant/terrain/counts fine, the others empty. Real text available: banner ` *** AERMOD - VERSION 26135 *** *** title *** 09/29/26` plus the AERMET line's HH:MM:SS; `**Model Calculates  3 Short Term Average(s) of:   1-HR   3-HR  24-HR` / `and Calculates PERIOD Averages`; `**This Run Includes:` already parsed.
- Fix: read run_date/run_time from the two banner lines, averaging_periods from the "Short Term Average(s) of:" line plus "Calculates (PERIOD|ANNUAL)"; use title (not jobname) in visualization.py:261; keep the old regexes only if C1 is declined.

### E7 [BUG] [low] Discrete polar receptors are returned as (range, radial) in the x/y fields
- Where: output_parser.py:612-634 (`_parse_receptors_epa`)
- What: inpsum.f:3770-3790 (FORMAT 9047) prints DISCPOLR receptors as `SRCID: (range, radial, ZELEV, ZHILL, ZFLAG)` relative to the source `IREF`. The parser stores range/radial as x_coord/y_coord.
- Evidence: VERIFIED with a section text in the real format (repro/slice-e/t13.py): `(500.0, 45.0)` returned for a receptor 500 m at 45 degrees from STACK1.
- Fix: for the POLAR section look the source up by the `SRCID:` prefix in self.sources and convert: x = xs + r*sin(a), y = ys + r*cos(a) (a from north, clockwise, as inpsum.f's DATAN2(XRMS,YRMS)). About 8 lines.

### E8 [BUG] [low] A source with FLAT in a mixed run is dropped from the source list
- Where: output_parser.py:517-543 (`_parse_epa_source_section`, `float(parts[5])`)
- What: inpsum.f:2193 writes base elevation as `4X,"FLAT"` for a source flagged FLAT (soset.f:2238, mixed FLAT/ELEV run). `float("FLAT")` raises, the `except` skips the source silently, and `_parse_sources` then sets `num_sources = len(self.sources)` (line 425-426), overwriting the correct "This Run Includes" count with the parsed (smaller) one.
- Evidence: VERIFIED (repro/slice-e/t5.py: the ddep_only POINT row edited to FLAT elevation gives 0 sources).
- Fix: `base = 0.0 if parts[5] == "FLAT" else float(parts[5])`; do not overwrite num_sources when a row failed to parse (keep max, as receptors do at line 571).

### E9 [BUG] [low] aermod_outputs value typing: NaN/Infinity stay strings; DATE is int in this module, zero-padded str in postfile.py
- Where: aermod_outputs.py:283-289 (`_coerce`); postfile.py:722-724
- What: `_coerce` tries fortran_float only when the token has "." or "e", so `NaN`, `Infinity`, `Inf` (which _fortran.py says gfortran writes) stay strings and make the column object-typed. DATE columns become ints, so POSTFILE `05010112` reads as `5010112`, while read_postfile returns "05010112"; code switching between the two readers must zfill.
- Evidence: VERIFIED for the date (repro/slice-e/t6.py, year_2005 fixture); READ for NaN.
- Fix: in `_coerce` try int, then fortran_float, then str; keep DATE as str (or document ints).

### E10 [BUG/PERF] [medium] Both POSTFILE readers build a Python dict per row; a year of hourly values for 1,000 receptors needs ~5 GB
- Where: postfile.py:1011-1024 (binary), 442-465 (text), aermod_outputs.py:309-327
- What: `data_rows.append({...})` per receptor per record, then `pd.DataFrame(list_of_dicts)`. Hourly POSTFILEs are the input of the NAAQS design-value functions (design_values.py), so the slow path is the main path.
- Evidence: VERIFIED (repro/slice-e/t11.py): 2.4 M rows (1,000 receptors x 2,400 hourly records) take 3.4 s and 1.5 GB peak; 8.76 M rows would take ~12 s and ~5.5 GB.
- Fix: binary: `np.frombuffer(payload, '<f8', offset=16)` per record, then build the frame once with `np.tile`/`np.repeat` for x, y, grp, ave, date and reshape(numtyp, n) for the value columns (~15 lines, shorter than now). Text: `pd.read_fwf(colspecs=slices)` using the file's FORMAT (also fixes E2).

### E11 [BUG] [medium] 24-h and PERIOD means from an hourly POSTFILE ignore calm/missing hours and AERMOD's 75% floor (open 11-11 item: still present)
- Where: design_values.py:259 (`_daily_series(how="mean")`) and the `_annual_means`/`_no2_highest_complete_year` means (design_values.py:449, 1024); data comes from postfile.py rows
- What: AERMOD forms a short-term mean as sum / max(NUMHRS-NUMCLM-NUMMSG, NINT(0.75*NUMHRS+0.4)) (calc2.f:2439 `AVER`), and the PERIOD/ANNUAL mean as sum / (IANHRS-IANCLM-IANMSG) (output.f:31 `PERAVE`). An hourly POSTFILE has a row for every hour including calm/missing ones (POSTFL runs every hour, aermod.f:1865-1902; the hour's value is 0), and nothing in the row says it was calm. `groupby(...).mean()` therefore divides by the row count (24, or N hours): with 4 calm hours AERMOD divides by 20 where pyaermod divides by 24 (about 17% low; up to 25% at the 18-hour floor). 
- Evidence: READ with Fortran citations (not re-run; the tests/fixtures/output_parser/calm_missing run could be used: compare AERMOD's 24-HR table to the mean of a 1-HR POSTFILE).
- Fix: cannot be repaired from the hourly file alone. Options: (a) document and recommend `POSTFILE 24`/`PERIOD` from AERMOD itself for PM2.5/PM10/annual values; (b) accept an optional calm/missing hour count or the met file's calm mask. Not a parser fix, listed here because the brief asked.

### E12 [BUG] [low] Binary reader edge cases: truncated or short records end the read silently; byte order fixed
- Where: postfile.py:1118-1146
- What: a leading marker with fewer bytes than promised, or an EOF in the trailing marker, returns None (read stops without warning), so a run killed mid-write gives a shorter file that parses "successfully" (VERIFIED: a file cut 20 bytes short loses the last record, no warning, repro/slice-e/t10.py). A payload shorter than 16 bytes also returns None, which ends the whole read even if more records follow. Markers/values are hard-coded little-endian; a big-endian write (`-fconvert=big-endian`, other platforms) would raise "Record length mismatch" or read nonsense (PLAUSIBLE; AERMOD builds in the repo's scripts use gfortran defaults, so little-endian). Negative markers (gfortran subrecords for records over 2 GB) would make `f.read(rec_len)` read the rest of the file (PLAUSIBLE, extreme).
- Fix: raise (or warn) on a truncated final record; `warnings.warn("truncated record")` at minimum. Optional: sanity-check the first marker and retry with `>` before failing.

### E13 [BUG] [low] Two-digit-year century is a fixed pivot (yy < 50 -> 20yy) in design_values, outside these modules
- Where: design_values.py:116-124 (consumer of postfile `date`)
- What: AERMOD itself resolves the century from the met data's first year (meset.f:2450-2480 LONG_DATE with ISTRT_WIND/ISTRT_CENT), the POSTFILE carries only YYMMDDHH. Met data from 1940s (yy 40-49) are read as 2040s. PLAUSIBLE/rare; mentioned so the postfile layer can offer a `century` hint if ever needed. No change recommended now.

---

## Concision (which module owns what)

Ownership proposal: `_fortran.py` owns number parsing (float, NaN/stars, ints). `aermod_outputs.py` owns every AERMOD text *file* with a printed FORMAT and header comment block (PLOTFILE, POSTFILE, MAXI, RANK, SEASONHR). `postfile.py` keeps only the binary reader and the PostfileResult/output-type semantics. `output_parser.py` owns the `.out` printed report, including the EVENT block parser now in aermod_outputs.

### C1 [CONCISION] [medium] output_parser.py carries ~250 lines for a text format no producer writes
- Where: output_parser.py:318-330 + 332-343 + 356-361 (Jobname/Run Date/Model Setup Options/Averaging Time Period), 412-423 and 428-457 (`*** SOURCE LOCATIONS ***`), 557-568 and 575-598 (`*** RECEPTOR LOCATIONS ***`), 649-670 (fallback period patterns), 814-915 (`_parse_concentration_table`, `*** ANNUAL RESULTS ***`), 917-982 (`_parse_epa_value_is_format`)
- What: none of those headings exists in AERMOD (grep of the Fortran finds none) and no src code emits them (grep src/docs: only tests). They are reached only from hand-written strings in tests/test_output_parser.py, _large.py, _coverage.py, test_integration.py, test_priority2_gaps.py, test_fortran_exponents.py. `_parse_epa_value_is_format` is a second, weaker copy of `_summary_row` (no group, rank, date, zelev, flag handling in the DataFrame beyond x/y/flag). Three places compute max_value/max_location the same way (lines 797-812, 905-915, 972-982).
- Specific change: delete the legacy paths; point those tests at real excerpts from tests/fixtures/output_parser/* (the README says five real runs exist). About 250 lines out of 1279. Risk: behaviour change for anyone who feeds the invented format; decide with the maintainer (it is "removing a feature" only in the sense of a format never produced by AERMOD). Tests covering it today: the six files above.
- If declined: at least merge the three max-row computations into one `_max_of(df)` helper (~15 lines).

### C2 [CONCISION] [medium] PostfileParser re-implements the aux reader's header, FORMAT and row parsing
- Where: postfile.py:561-670 (`_parse_header_line`: version/title/model options/avertime/group regexes, FORMAT line counted by regex at 643-660, label line at 662-670), 672-727 (`_parse_data_line` by `split()`), vs aermod_outputs.py:99-206 (`parse_fortran_format`, `_format_field_slices`, `_split_column_labels`), 209-269 (`parse_aermod_header`: version, group, period, FORMAT, columns), 292-306 (`_split_row` by slices).
- What: both modules parse the same PLOTFILE/POSTFILE header and rows. postfile counts value columns with `(\d+)\(1X,[FE]13` regexes that only work for one hard-coded layout, while parse_fortran_format already gives exact field widths. The two readers also disagree on multi-year layouts (E3), overflow fields (E2), and date types (E9).
- Specific change: `PostfileParser.parse` = `read_aermod_aux_file` + a rename step: NUMTYP = number of 13-wide data fields before the first ZELEV-width field (or the AVERAGE CONC/DRY DEPO labels that `_split_column_labels` already returns); map X,Y,AVERAGE_CONC... to x,y,concentration..., build `ave/grp/date/rank` from RANK/AVE/GRP/DATE columns. Remove `_parse_header_line`'s FORMAT, label and avertime branches and `_parse_data_line`: about 100-150 lines out of 1311, plus the E3 fix for free. Keep the pyaermod-synthetic `AVERTIME:/POLLUTID:/SRCGROUP:` headers only if tests need them (they are invented, like C1). Tests covering it: tests/test_postfile*.py, test_postfile_types*, test_fortran_exponents.py, test_regression_epa.py.

### C3 [CONCISION] [low] Duplicate number/empty-frame/version helpers
- `_float_or_nan` (output_parser.py:174-178), `_coerce` (aermod_outputs.py:283-289), bare `float()` for x/y/zelev (postfile.py:707-712): fold into one `_fortran` helper (E2/E9), about 10 lines saved and one behaviour.
- Empty-frame column lists are built twice in postfile.py (466-472 text, 1032-1038 binary): one `_empty_frame(value_cols, plotfile)` helper, ~8 lines.
- Version regexes: output_parser.py:296/312, postfile.py:589, aermod_outputs.py:87 each match the same `AERMOD (…)` banner differently; the header-comment one lives in `parse_aermod_header` after C2.

### C4 [CONCISION] [low] Small removable items (grep src/ and tests/ done)
- output_parser.py:1251-1279: `if __name__ == "__main__"` demo (29 lines); the `aermod parse` CLI (cli.py:135) does the same; no test or doc runs `python -m pyaermod.output_parser`.
- aermod_outputs.py:35-38, 395-397: optional-pandas machinery (`optional_import`, `HAS_PANDAS`, `require`) while pandas is a hard dependency (pyproject.toml:31) and output_parser.py/postfile.py import it unconditionally; only tests/test_optional_helper.py:57 pins `HAS_PANDAS`. ~6 lines.
- aermod_outputs.py:468-565 (`read_event_output`, EventContribution): parses the `.out` of an EVENT run, so it belongs with the `.out` parser (output_parser.py). Move only; no line change. Tests: test_aermod_outputs.py:381-386 and tests/regulatory/test_event_rewrite.py.
- `AERMODFileHeader.raw_lines` is set but read nowhere in src or tests; `ModelRunInfo.urban_option` is never populated (E6). Public dataclass fields, so only note.
- `PostfileResult._primary_column`/`flagpole_heights` are only internal helpers (fine); `ConcentrationResult.max_row` is used by the GUIs (not dead).

### Estimated total
C1 ~250 lines, C2 ~100-150, C3+C4 ~60 (+10 to move), E10 changes net-negative in size. Roughly 400 of 3172 lines (about 12%) with behaviour fixes E2, E3, E4, E9 coming along.

## Not looked at
- design_values.py beyond lines cited (E11, E13), ensemble.py, visualization.py, gui_v2 consumers, wasm paths.
- `read_event_output` against evoutput.f (only skimmed the regexes; no EVENT fixture run).
- RLINE/BUOYLINE/OPENPIT source rows in `_parse_epa_source_section` (generic first 6 columns only; not compared with each inpsum.f format), SWPOINT sections (no type_map entry), gridded receptor echo.
- MAXDAILY file (`MXDFRM`, 11 fields incl. JDAY/hour) and MAXDCONT outputs: no reader exists in these modules; not assessed whether one is wanted.
- Files above the 500 MB head+tail mode (read the code only).
- AERMOD deposition averaging: AVER (calc2.f:2437) divides only output type 1 (CONC) by SNUM and PERAVE only CONC, so DDEP/WDEP short-term/period values are sums, not means. pyaermod's docs may call them averages; not checked.

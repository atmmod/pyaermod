# Slice B review: deck reader (input_reader.py 2780 lines, unparsed.py 110 lines)

Read both files in full. Repros are in
<scratch>/repro/slice-b/
(base.py is the template deck; t1..t15 are the scripts). Run with the scratchpad venv.
Also ran all 252 decks under tests/fixtures and test_cases through parse -> write(validate=False) -> reparse -> write:
no parse crash on any real deck (the 10 failures are non-decks such as `JOB` files and aermap.inp), and every rewrite is idempotent.
With validate=True, 91 of 252 decks fail to WRITE (see B4, B5): the reader is far ahead of the validator here.

Not looked at: pathways.py / sources.py writers beyond what the reader constructs; the validator except where a read->write failure points at it;
gui and browser callers of `_input_file_slots`; AERMOD semantics of every keyword (checked only the ones cited).

## Status of the open 11-11 items at HEAD

| Item | Status |
|---|---|
| H4 quoted paths pass sandbox=True | FIXED (VERIFIED t3.py: quoted escapes/absolutes rejected for SURFFILE, SUMMFILE, ERRORFIL, PLOTFILE, SAVEFILE) |
| quoted filenames with spaces truncated on rewrite | FIXED (VERIFIED t13.py: 20 file-bearing keywords round-trip a quoted name with a blank, none truncated) |
| crash on `SURFDATA 14735.0` | FIXED as a crash; see B9 (kept verbatim, but the writer also emits its own default SURFDATA) |
| alphanumeric station ID | now a clear `ValueError: line N: SURFDATA expects a whole number` ; matches AERMOD (meset.f SFDATA reads field 3 with STONUM, E208). Fine, not a bug |
| bare HALFLIFE | STILL PRESENT (IndexError), see B1 |
| Latin-1 bytes | STILL PRESENT (UnicodeDecodeError), see B8 |
| case-sensitive source IDs / pathway names | STILL PRESENT, see B3 |
| LOW_WIND keeps only first field | STILL PRESENT, see B7 |
| SURFFILE format field lost | benign: meset.f SURFIL only warns W293 "format field no longer used". Dropping it is correct; no action |
| SURFDATA name/coords, UAIRDATA year lost | STILL PRESENT, see B9 (low) |
| RECTABLE rank rewriting | STILL PRESENT and wider than the ticket, see B6 |

## Bugs

### B1 [BUG] [medium] Bad or Fortran-style numbers crash with a raw exception (or are silently lost) at ~50 plain float()/int(float()) sites
- Where: input_reader.py:564, 566, 574 (HALFLIFE, DCAYCOEF, FLAGPOLE), 1040, 1057-1063 (LOCATION x/y/extra), 2009 (WDROTATE), the 19 `int(float(` sites (e.g. 1993, 2016, 2030, 2118, 2180, 2220), the 14 `contextlib.suppress(ValueError)` sites (580, 605, 617, 625, 631, 638, 643, 646, 656 ...), and 692/699 (URBANOPT).
- What: AERMOD reads numbers with STODBL, so `1.0D5` is a valid number; Python `float("1.0D5")` is not. The module already has `fortran_float(strict=True)`/`_floats`/`_whole_number` and uses them for newer keywords, but the older sites do not.
- Evidence (VERIFIED, t1.py, t12.py, t15.py):
  - `LOCATION S2 POINT 1.0D5 0 0`, `HALFLIFE 1.0D3`, `DCAYCOEF 1D-3`, `WDROTATE 1.0D1`, `FLAGPOLE 1D0` raise `ValueError: could not convert string to float: '1.0D5'` with no line number. A valid deck cannot be read.
  - bare `HALFLIFE` / bare `DCAYCOEF` raise `IndexError`. tests/test_input_reader_fuzz.py states the contract is ValueError only, so this violates the project's own contract.
  - `NUMYEARS inf`, `STARTEND 2019 1 1 2019 inf 31`, `RANKFILE 24 1e999 r.out`, `GDSEASON 12*inf`, `SAVEFILE s.sav inf` raise `OverflowError`.
  - `URBANOPT 1.0D6 CITY` and `NO2STACK 5D-1` are silently dropped (no value, no unparsed line, so a valid urban area is lost on rewrite).
  - `LOCATION S2 POINT nan 0 0` and `... 1_0 0 0` are accepted (x = nan / 10.0); AERMOD rejects both (E208).
  - Already acknowledged in .10x/reviews/2026-11-17-pr70-review-verification.md ("~48 sites"), so this is the known follow-up, now with concrete failing inputs.
- Fix: one helper `_num(tok, keyword, lineno) -> float` (strict `fortran_float`, raises `ValueError(f"line {ln}: {keyword} expects a number, got {tok!r}")`) and `_int(...)` built on `_whole_number`; replace the raw sites. For the lenient "drop and keep verbatim" sites use `_floats(...)` and `_drop`. Saves lines too (see C2).

### B2 [BUG] [medium] Malformed lines are dropped without being kept verbatim, contradicting "Nothing is dropped silently"
- Where: every `continue` without `_drop` and every `suppress(ValueError)`: BUILDHGT/WID/LEN/XBADJ/YBADJ (1087-1092), AREAVERT (1101-1106), BLPINPUT/BLPGROUP (1125-1133), SBARRIER (1203-1214), RBARRIER/RDEPRESS/VBARRIER (1180-1200), NO2RATIO (1156-1160), EMISUNIT/CONCUNIT/DEPOUNIT (1165-1172), GASDEPOS (1259-1263), PARTDIAM/MASSFRAX/PARTDENS (1292-1319), NO2STACK, O3SECTOR, NOXSECTR, GASDEPDF, GASDEPVD, GDSEASON, GDLANUSE, SAVEFILE day increment (579-656), MAXTABLE (2101-2104), MAXDCONT THRESH (2222-2223), SEASONHR/EVALFILE (error path drops, ok).
- Evidence (VERIFIED, t11.py): `PARTDIAM STACK1 abc`, `GASDEPOS STACK1 1 2`, `BUILDHGT STACK1 x y`, `NO2RATIO STACK1 abc`, `EMISUNIT abc g/s ug`, `NO2STACK abc`, `O3SECTOR 1 x`, `GASDEPVD x`, `MAXDCONT G 5 THRESH 1` all vanish from the rewritten deck and from `unparsed_lines`; no warning. `MAXTABLE ALLAVE x` keeps the table but silently loses the rank (stays 10).
- All of these are AERMOD errors in the source deck, so severity is bounded, but the docstring (L47-53) and unparsed.py promise otherwise, and the sibling branches (OZONEVAL, ARMRATIO, SCIMBYHR) do it right.
- Fix: make failure the default: each handler either assigns or calls `_drop`. A table-driven structure (C1, C3) makes the silent path impossible. Test to add: for each keyword, a malformed line lands in `unparsed_lines`.

### B3 [BUG] [medium] Pathway codes and source/group IDs are case-sensitive; AERMOD upper-cases the whole line
- Where: 257, 266 (`tokens[0] in PATHWAYS`), 285 (`toks[0].upper() == current.name` is fine but the earlier checks are not), 1039 (`sid = toks[0]`), 1078, 1089 ... every `sid = toks[0]`, 1148/1151 (group names), and the membership checks `toks[0] not in locs`, `tok in known_ids` (870, 1336).
- What: setup.f LWRUPR (setup.f:135, 319-360) upper-cases every character of the image before DEFINE splits it. Keywords here are `.upper()`-ed, so the reader is half case-insensitive.
- Evidence (VERIFIED, t4.py, t7.py):
  - A deck with `co starting` ... `co finished` is rejected: `ValueError: line 1: content outside any pathway block`.
  - `LOCATION Stack9 POINT 5 5 0` with `SRCPARAM STACK9 ...` builds no source: both lines are kept as unparsed (they are different keys), a warning says "not modelled", and the rewrite carries them verbatim (so nothing is lost, but the source is invisible to the model/GUI/validator).
  - `SRCGROUP G1 stack1` with source `STACK1`: group member not matched; write fails validation ("source ID 'stack1' not found").
- Fix: upper-case the pathway token before the `in PATHWAYS` tests and key `locs`, `src_types`, groups, `known_ids` on `sid.upper()`. Caveat: the writer should emit the upper-case form (AERMOD reads it that way anyway). Filenames must keep their case (RUNST1 keeps the original for file names, meset.f:343-347), so only IDs, not path fields, are folded.

### B4 [BUG] [medium] Valid SO decks parse but cannot be written: SRCGROUP members the validator rejects
- Where: reader keeps the raw tokens (1134-1148, `src_groups`), validator.py:1663-1670 requires every member to be a literal source ID.
- Evidence (VERIFIED, t5.py, t10.py, t9.py): each fails `to_aermod_input()` with `source ID '...' not found in project sources`:
  - `SRCGROUP G1 STACK1-STACK2` (a range, soset.f ASNGRP; the reader even has `_in_id_range` for this and uses it for GASDEPOS/URBANSRC/BLPGROUP, but not for SRCGROUP/OLMGROUP/PSDGROUP validation).
  - `INCLUDED src.dat` plus `SRCGROUP G1 INC1 INC2` (sources defined in the included file; the reader explicitly supports this pattern, comment at 1415-1419).
  - `SRCGROUP ALL BACKGROUND` (EPA's own bg_no2_*.inp, 14 decks): 'BACKGROUND' is a flag, not a source.
- Fix (validator, not reader): skip members containing `-` (or check them with the reader's `_in_id_range`), skip `BACKGROUND` for the ALL group, and downgrade to a warning when the pathway holds an INCLUDED line in unparsed_lines. Alternatively `include_all_group`/members handling in the reader could drop the BACKGROUND token into a flag. Flagging because it makes `read_aermod_input(...).write(...)` fail on real EPA decks.

### B5 [BUG] [medium] `URBANOPT 1000` (no name) + `URBANSRC`: reader sets urban_areas, validator wants urban_option
- Where: reader 701-705 sets `urban = first_area.urban_id or first_area.name` (None when the deck gives a bare population); validator.py:337 checks only `control.urban_option`.
- Evidence (VERIFIED, t6.py): `URBANOPT 1000` + `URBANSRC ALL` parses, `to_aermod_input()` raises "sources have is_urban=True but ControlPathway.urban_option is not set". With a name (`URBANOPT 1000 CITY`) it works. coset.f URBOPT accepts one card with IFC 3 (population only), so the deck is valid. EPA's blp_urban.inp fails the same way.
- Fix: validator line 337: `not control.urban_option and not control.urban_areas`. (Also `urban_population is not None` is what the writer keys on at pathways.py:913.)

### B6 [BUG] [medium] RECTABLE / MAXTABLE / DAYTABLE lose their averaging periods and collapse to `ALLAVE`
- Where: 2091-2106 (reader) and pathways.py:1668-1679 (writer, slice owner elsewhere).
- Evidence (VERIFIED, t8.py): `RECTABLE 1 1-3` + `RECTABLE 24 1` reads and rewrites as the single line `RECTABLE ALLAVE 1-3`; `RECTABLE ALLAVE FIRST SECOND` -> `ALLAVE 1-2`; `MAXTABLE 24 5` then `MAXTABLE ALLAVE 10` -> rank 10 (last wins, while RECTABLE takes the maximum; `MAXTABLE 1 3` after `MAXTABLE 1 5` gives 3). `DAYTABLE 24` becomes a bare DAYTABLE. The output changes meaning: the deck asked for short-term tables only, the rewrite prints tables for every period in AVERTIME.
- Fix: cheapest honest fix is to model only the exact form the writer emits (period field ALLAVE, one line) and send every other RECTABLE/MAXTABLE/DAYTABLE line to `_drop` (unparsed); then nothing is lost. Better: keep `[(period, rank)]` lists. The "rank rewriting" ticket from 11-11 is this item.

### B7 [BUG] [low] LOW_WIND keeps only its first field
- Where: 577-578 (`low_wind = toks[0]`).
- Evidence (VERIFIED, t1.py): `LOW_WIND 1.0 0.2 0.5 0.3` -> rewrites `LOW_WIND  1.0`. coset.f LOW_WND (6808-6870) takes up to seven fields (IFC <= 9): SVMIN, WSMIN, FRANMAX and more, each range-checked; fields 2..n are silently discarded, changing the model results. Requires ALPHA, so rarely hit.
- Fix: `low_wind = "  ".join(toks) or None`. Check regulatory.py:158 (`lwo not in allowed_low_wind`) first; it compares the whole string, which for a multi-field string would just warn.

### B8 [BUG] [low] UTF-8-only file read: Latin-1 decks and BOM decks fail with unhelpful errors
- Where: 2413 `p.read_text(encoding="utf-8")`.
- Evidence (VERIFIED, t3.py): a deck saved from a Windows editor with `Caf\xe9` in a title raises `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9` (a ValueError subclass, but the message gives no hint that the file is Latin-1). A UTF-8 BOM (Notepad) raises `ValueError: line 1: content outside any pathway block: '﻿CO STARTING'`. tests read EPA decks as latin-1 (tests/test_epa_deck_roundtrip.py:228), which shows the case is expected. No EPA fixture is actually non-UTF-8 (checked all 252).
- Fix: `read_text(encoding="utf-8-sig")` with a `UnicodeDecodeError` fallback to `latin-1` (AERMOD itself is byte-oriented). Two lines.

### B9 [BUG] [low] ME: UAIRDATA year and SURFDATA name/coords are not kept; a one-field SURFDATA/UAIRDATA gives a duplicate keyword
- Where: 1959-1963.
- Evidence (VERIFIED, t11.py, t2.py):
  - `SURFDATA 1 2019` + `UAIRDATA 2 2018` rewrites `UAIRDATA 2 2019` (the writer uses `data_start_year` for both; reader takes the year from SURFDATA only). meset.f UADATA stores IUYEAR separately from ISYEAR.
  - `SURFDATA 14735 2020 ALBANY 42.7 -73.8` loses the name and coordinates (SFNAME/SFX/SFY, meset.f SFDATA fields 5-7, optional).
  - A deck whose only SURFDATA is `SURFDATA 14735.0` (one field, E201 in AERMOD): the line is kept verbatim AND the writer still emits its own `SURFDATA 0 2020`, so the output has the keyword twice with an invented station 0 and year 2020 (t2.py "only_surfdata_float").
- Fix: keep `toks[2:]` of SURFDATA/UAIRDATA beyond the year as unparsed-style extras or add `upper_air_start_year`/`surface_station_name`; at minimum `_drop` when len(toks) > 2 or the UAIRDATA year differs. For the one-field case drop the modelled defaults when the keyword was seen but kept verbatim (or raise: the deck is invalid).

### B10 [BUG] [low] An incomplete GRIDCART/GRIDPOLR invents a default grid
- Where: 1896-1926 (`CartesianGrid(**grid)` with missing keys falls to dataclass defaults).
- Evidence (VERIFIED, t14.py): `GRIDCART C1 STA` + `GRIDCART C1 END` (no XYINC/XPNTS) yields a 10 x 10 grid at 100 m from (0, 0); `XPNTS` without `YPNTS` yields y_num=10, y_delta=100; a short `XYINC 0 3 100` yields the default grid and ALSO keeps the line verbatim, so the rewrite carries both. Same for a polar grid without DIST/ORIG (origin (0,0), 10 rings). AERMOD reports an error for each of these decks; the reader fabricates receptors the deck never defined.
- Fix: require (x/y init+num+delta or points) and (dist and dir for polar) before building; otherwise `_drop` every line of that network.

## Items checked, no defect found
- Continuation lines (blank keyword columns), repeated SRCGROUP/URBANSRC/BLPGROUP lines accumulating, tab-separated lines, `**` and `!` comments (note: AERMOD does not treat `!` as a comment, the reader is more lenient; harmless), CRLF line endings, INCLUDED (kept verbatim and path-checked by the sandbox), quoted names, ID ranges for GASDEPOS/NO2RATIO/METHOD_2/URBANSRC/BLPGROUP.
- Sandbox: every file-bearing field I could find is checked, including unparsed lines; symlinks resolve before the check.
- `_split_pathways`/`_is_continuation` follow setup.f DEFINE.

## Concision

Whole module: ~2780 lines. A realistic, behaviour-preserving target is ~2250 (-500, about 19%), mostly from C1-C4. All of it is covered by tests/test_input_reader*.py (7 files), test_so_source_construction.py, test_so_deck_acceptance.py, test_reader_roundtrip_fidelity.py, test_epa_deck_roundtrip.py, test_epa_source_roundtrip.py, test_input_reader_fuzz.py, test_property_*.py, test_regression_epa_official.py; B1/B2 work should be done first because the shared helper deletes most of the repetition.

### C1 [CONCISION] [medium] `_parse_sources` (987-1732, 746 lines) is three functions and a stringly-typed dict
- Where / shape:
  - Collect pass 1034-1355 (320 lines): each keyword branch is `toks` -> `sid = toks[0]` -> `_floats(toks[1:])` -> `locs.setdefault(sid, {})[key] = ...` -> `.setdefault("_lines", []).append(ln)`. `locs.setdefault(` appears 13 times; `if not toks: continue` 9 times; the dict keys `_lines/_building/_vertices/_rbarrier/_rdepress/_vbarrier/_platform/params/extra_loc/z_elev/x_coord/y_coord/_flat_source` are read back with `.get(key, default)` throughout the build loop. Replace the dict with a small `@dataclass _SrcDef` (typed fields, `lines: List[int]`) in a `defaultdict(_SrcDef)`; `touch(sid, ln)` helper replaces the 13 two-level setdefaults.
  - Table for the per-source float-list keywords: `PARTDIAM/MASSFRAX/PARTDENS` (1290-1319, 30 lines, three identical blocks differing only in the dict key `diameters/mass_fractions/densities`) become one branch with `_PART_KW = {"PARTDIAM": "diameters", ...}`; `BUILDHGT..YBADJ` (1085-1096) already is. -20 lines.
  - Build pass 1414-1633 (220 lines): 10 branches each doing `if len(params) < N: keep_lines(data); continue`, then `Cls(**common, emission_rate=params[0], x=params[1] if len(params) > 1 else D, ...)`. `params[i] if len(params) > i else default` occurs about 30 times. Use `_Builder = (min_params, needs_extra, fn)` table keyed by type, a helper `_opt(params, i, default)`, one shared pre-check (`keep_lines`+continue appears 8 times, 24 lines), and merge LINE/RLINE (1490-1522, identical apart from class and three defaults: -15 lines). Each builder becomes a 6-10 line function; the loop is ~15 lines.
  - Extract the BUOYLINE assembly 1635-1701 (67 lines) into `_assemble_buoylines(...)` and the final `SourcePathway(...)` construction 1703-1732 stays in the parent.
- Savings: ~100-130 lines and no function over ~80 lines. Risk: low-medium (largest behaviour surface, but densely tested by test_so_source_construction.py). Keep the order in which `sources` are appended (non-BUOYLINE sources in LOCATION order, then buoyline groups) since tests compare lists.

### C2 [CONCISION] [medium] One numeric helper replaces ~50 try/except and suppress sites
- Where: the 14 `contextlib.suppress(ValueError)`, 18 `except ValueError`, 19 `int(float(`, 33 `float(toks` sites listed in B1.
- Shape: `_num`, `_int` (strict, line-numbered ValueError) and `_floats` (None on failure). Branches that currently read
  `try: X = int(float(toks[2])) ... except ValueError: _drop(dropped, ln); continue` collapse to one `_floats`/`None` check. In `_parse_output` (2062-2271, 210 lines) the RANKFILE / SEASONHR / EVALFILE / TOXXFILE / MAXIFILE / MAXDAILY / MXDYBYYR / MAXDCONT blocks (2109-2240) share "required fields + optional trailing integer unit"; with `_opt_unit(toks, i)` each is 3-5 lines. -40 to -60 lines in `_parse_output`, -30 in `_parse_control`. Also fixes B1.
- Risk: low, provided `_int` keeps accepting `1988.0` (as `_whole_number` does) and `RANKFILE 24 1e999` raises the clear ValueError.

### C3 [CONCISION] [medium] `_parse_control` (448-804, 357 lines): table the flags, split the assembly
- Where / shape:
  - 450-500: ~45 local variables mirrored 1:1 in the 40-kwarg `ControlPathway(...)` at 761-804. Collect into a dict `kw: Dict[str, Any]` (or a small `_ControlState`) and `ControlPathway(**kw)`; assignments become `kw["half_life"] = ...`. -40 lines, no behaviour change.
  - MODELOPT 511-552 (42 lines): `CONC/DEPOS/DDEP/WDEP/ALPHA/BETA/PSDCREDIT/DFAULT` are eight `elif up == X: flag = True` branches; a `_MODELOPT_FLAGS = {"CONC": "calculate_concentration", ...}` dict loop saves ~15 lines. Keep FLAT/ELEV/FLATSRCS, chemistry and depletion tokens as explicit branches (order-dependent, comments explain AERMOD quirks).
  - Scalar keywords 563-574, 579-581, 636-646 (HALFLIFE, DCAYCOEF, FLAGPOLE, NO2STACK, GASDEPVD, GDSEASON, GDLANUSE): `{kw: (field, convert)}` table, after B2 makes bad values drop. -20 lines.
  - Ozone/NOx are written twice: 601-627 (O3*/NOX_* branches), 710-733 (assembly of `OzoneData` vs `NOxBackground`, same eight fields under different names). Hold per-gas state in a tiny `_Bg(specs, sectors, units)` object keyed by the keyword triple: -25 lines. Leave the O3VALUES legacy forms (601-611) as they are: ozone-only and subtle.
  - Extract three pure functions: `_build_urban(urban_lines)` (675-705), `_build_chemistry(...)` (707-744), `_resolve_terrain(...)` (746-759). Pure readability, no line savings.
- Savings: ~100 lines (357 -> ~250 spread over 4 functions). Leave alone: the URBANOPT card-count logic and the MODELOPT terrain decision; both encode AERMOD quirks documented in comments.

### C4 [CONCISION] [low] Two near-identical field splitters
- Where: `_runstream_tokens` (2419-2447) and `runstream_fields` (2450-2477): same 20-line state machine; the only difference is whether the quotes stay on the field (`line[i:end]` vs `text[i+1:end]`, and the end index).
- Fix: one `_split_fields(text, keep_quotes)`; `runstream_fields = partial(_split_fields, keep_quotes=False)`. -18 lines; covered by test_input_reader_quoting.py and the doctests. Risk: low (watch the unterminated-quote case: end of line, quote not closed).

### C5 [CONCISION] [low] GRIDCART and GRIDPOLR sub-keyword handling
- Where: 1795-1874 and 1896-1926. The ELEV/HILL/FLAG branch is character-for-character the same in both (1825-1829 vs 1870-1874) and the `rows` -> list conversion repeats (1899-1902 vs 1917-1919). A shared `_add_rows(grid, sub, values, dropped, ln)` and `_ROW_ATTRS = {"cart": ..., "polar": ...}` saves ~20 lines. Marginal; do it with B10 since both touch the same lines. The XYINC/GDIR/ORIG branches are distinct, leave them.

### C6 [CONCISION] [low] Small duplications and dead code (greps done on src/ and tests/)
- `_PathwayBlock.lines` (field at L198, appended at L279): written, never read anywhere in src/ or tests/. Delete both (-3 lines). `_PathwayBlock.record` is used by parse_aermod_input and tests, keep; it is an O(n) scan per unparsed line (O(n*m) overall; fine for decks, could be a dict).
- `PATHWAYS` (176) is the same tuple as `unparsed.PATHWAY_ORDER`; import it. (runner_utils.py:176, gui_v2/run_results.py:80, tests/e2e/fake_aermod.py:50 keep their own copies; outside this slice.)
- `_ORDINAL_WORDS` (154-157) duplicates `pathways.PLOT_RANK_WORDS`; `{w: i for i, w in enumerate(PLOT_RANK_WORDS, 1)}`.
- `dropped: Optional[List[int]] = None` on all six `_parse_*` functions and the `if dropped is not None` guard in `_drop` (370-373): only parse_aermod_input calls them (no test calls them directly), and it always passes a list. Make it required and replace `_drop(dropped, ln)` with `dropped.append(ln)` (47 sites; -8 lines).
- `_group_keywords` docstring (330-341) describes the pathway-code stripping and continuation handling that `_split_pathways` now does; the function only expands `N*V`. Update the docstring or inline it (`_expand_shorthand` per record at the 6 call sites).
- unparsed.py: no dead code; `UnparsedLine.to_aermod_line` relies on `a + b if cond else c` precedence (correct, but a one-line parenthesisation would save the next reader a minute).

### Leave alone
- `_background_from` (895-984) and the BACKGRND/BGSECTOR bookkeeping: long, but each branch is a documented AERMOD probe result; a table would hide the whole-or-nothing rules.
- `_parse_control` URBANOPT card-count logic, MODELOPT terrain resolution, SBARRIER state machine (1201-1221), PLOTFILE (2123-2159), MAXDCONT (2216-2240): small, order- or arity-dependent, each already commented against the Fortran.
- `_validate_paths_within` and `_input_file_slots`: long lists, but flat and exhaustive; folding them into a table keyed by attribute path would be shorter only by hiding which fields are covered (a security-relevant list).

## Counts
Bugs: 0 high, 6 medium (B1-B6; B1 and B2 share a root cause; B4 and B5 are validator-side), 4 low (B7-B10). Concision: 2 medium, 4 low. Docs: none in this slice beyond the stale `_group_keywords` docstring.

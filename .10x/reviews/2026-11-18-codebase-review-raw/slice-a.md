# Slice A review: deck model and writer (sources.py, pathways.py, input_generator.py, _fields.py, _fortran.py)

Method: read all five files in full; generated decks with the repo venv and ran them through the local AERMOD binary
(<repo>/bin/aermod, version 24142, `RUNORNOT NOT`-style parse runs; met-file E500 ignored).
Repro scripts: <scratch>/repro/slice-a/
(`srcs.py` is the harness: `run(project, label)` writes a deck, runs aermod, prints the SO/CO/RE message lines).
VBARRIER/SBARRIER are v26135-only, so the 24142 binary rejects them (E105); I did not check those two against a v26135 binary.
Not looked at: validator.py, receptors.py, input_reader.py (other slices), except where a finding crosses into them; the
OutputPathway MAXIFILE/RANKFILE/TOXX/EVENT writers were read against ouset.f only by reading, not run.

Counts: BUG high 2 (A1, A2), medium 5 (A3-A7), low 7 (A8-A14); CONCISION 6 items (C1-C6, about -150 lines in sources.py and -45 in pathways.py without touching fields or output); dead code 6 (D1-D6).

## BUGS

### A1 [BUG] [high] `ControlPathway.elevation_units` writes `CO ELEVUNIT`, which AERMOD rejects; SO ELEVUNIT is never written
- Where: src/pyaermod/pathways.py:895-896 (writer), :655 (field); reader side input_reader.py:567 (dead branch); tests/test_coverage_gaps.py:423, :589 assert the bad output.
- What: ELEVUNIT is a keyword of the SO and RE pathways only (soset.f:276 -> SOELUN, reset.f:94 -> REELUN); coset.f COCARD has no branch for it. `elevation_units="FEET"` therefore emits a fatal CO card, and the source elevations (which the SO ELEVUNIT would convert) can never be declared in feet. RE gets its own `ReceptorPathway.elevation_units` (receptors.py:427), so the two fields can disagree.
- Evidence: VERIFIED (t7.py, c1.inp): `ControlPathway("t", elevation_units="FEET")` -> aermod: `CO E110 COCARD: Keyword is Not Valid for This Pathway. Keyword is ELEVUNIT`.
- Fix: delete the CO write; have `SourcePathway.to_aermod_input` emit `   ELEVUNIT  FEET` as its first card (needs the control's units passed in, like `chemistry`/`psd_credit`), and let `AERMODProject.to_aermod_input` pass `control.elevation_units` to both SO and RE. Drop the CO branch in the reader (a CO ELEVUNIT line should go to unparsed_lines). Prior review item "CO ELEVUNIT written": still present at HEAD.

### A2 [BUG] [high] Multi-urban-area decks cannot be written: `URBANSRC` drops the area ID the reader kept
- Where: src/pyaermod/sources.py (every `URBANSRC  {source_id}`: 502, 576, 696, 772, 863, 953, 1037, 1186, 1328, 1456, 1639); `urban_area_name` is never read by any writer. Reader sets it at input_reader.py:1396.
- What: with two or more `CO URBANOPT` cards AERMOD switches URBANSRC to `URBANSRC urbid srcid...` (soset.f URBANS, L_MULTURB branch: field 3 is the urban ID, sources start at field 4). The writer always writes the single-area form. tests/test_coverage_gaps.py:316-326 asserts `urban_area_name` is never written; that is right only for one area.
- Evidence: VERIFIED (urb.py/t2.py). Read an EPA-style deck with `URBANOPT A1 500000`, `URBANOPT B2 200000`, `URBANSRC A1 S1`, `URBANSRC B2 S2`: the reader gives `urban_area_name` A1/B2, the rewrite writes `URBANSRC  S1` / `URBANSRC  S2`; aermod: `SO E301 URBANS: Urban Area ID Has Not Been Defined. URBID = S1`, `SO E318 No Sources Defined for Urban Area. URBID = A1`, `SO E130 Missing ... URBANSRC`. The ID-first original runs clean (u2.inp).
- Fix: `SourcePathway.to_aermod_input` takes `multi_urban: bool` (`len(control.urban_areas) > 1`) and the shared tail helper (see C1) writes `URBANSRC  {urban_area_name} {id}` when set; update the two tests to parametrise on one vs several areas. When several areas exist and a source has `is_urban` with no name, the validator should say so (AERMOD cannot read it).

### A3 [BUG] [medium] `SourcePathway.background` is never added to any source group, so the background silently does nothing
- Where: src/pyaermod/sources.py:2065-2066 (BACKGRND written), :2103-2127 (groups written without BACKGROUND).
- What: soset.f SOGRP:5867-5886 states BACKGRND is not automatically in group ALL; only a `BACKGROUND` member on the SRCGROUP card adds it (otherwise W298 NOBACKGROUND, and SRCQA W321 "BACKGROUND concs are NOT included in any SRCGROUP", soset.f:1353). A `BackgroundConcentration(uniform_value=3.0)` on a default project writes BACKGRND and a bare `SRCGROUP  ALL`, so the reported concentrations contain no background. The validator is silent. The user must know to add `SourceGroupDefinition("ALL", ["BACKGROUND"])` (the tests do).
- Evidence: VERIFIED (t4.py bg-uniform, t6.py): deck has `BACKGRND  ANNUAL  3` and `SRCGROUP  ALL`; aermod prints `SO W298 ... NOBACKGROUND` and `SO W321 BACKGROUND concs are NOT included in any SRCGROUP!`; Validator.validate returns no message about it.
- Fix: smallest is a validator warning when `background` is set and no `group_definitions` member list contains BACKGROUND/BACKGRND (also check unparsed lines). Better: a `BackgroundConcentration.in_group_all: bool = True` that makes the writer append `BACKGROUND` to the ALL card when no definition already does; docs must say so either way.

### A4 [BUG] [medium] BUOYLINE deposition cards name the group ID, not a source; AERMOD dies with a Fortran runtime error
- Where: src/pyaermod/sources.py:1448-1451 (`_deposition_to_aermod_lines(self.source_id, ...)`); NO2RATIO and URBANSRC just above/below correctly loop over `seg.source_id` (:1443-1445, :1455-1456).
- What: `BuoyLineSource.source_id` is the BLPGROUP ID (BLPINPUT/BLPGROUP use it); the LOCATION/SRCPARAM cards use the segment IDs. GASDEPOS/PARTDIAM/MASSFRAX/PARTDENS/METHOD_2 are keyed by source ID, so they refer to an undefined source.
- Evidence: VERIFIED (srcs.py "buoy-dep"): `PARTDIAM  BLD  5  10` with segments L1/L2 -> `Fortran runtime error: Index '0' of dimension 1 of array 'l_method2' below lower bound of 1` at soset.f:4831 and no output. (Source lookup returns 0 for BLD and the code indexes with it.)
- Fix: emit the deposition lines once per segment ID (same loop as NO2RATIO). The validator should also check a deposition card never names a non-source ID.

### A5 [BUG] [medium] Cards longer than 512 characters are truncated silently by AERMOD; only some writers wrap
- Where: src/pyaermod/sources.py:1822-1834 (`_group_lines`, user `member_source_ids` on one line), :1857 (HOUREMIS), :2055/:2057 (ARCFTSRC, HBPSRCID), :1440 (BLPGROUP); only the hoisted per-source groups are chunked (`_GROUP_IDS_PER_CARD`, :2125). validator.py has no length check (grep for 512/ISTRG: none).
- What: modules.f ISTRG=512; the runstream record is read with A512, so the rest of the line is dropped. A cut at a space is silent; a cut inside an ID is an unrelated E3xx.
- Evidence: VERIFIED (long2.py): `SourceGroupDefinition("GRP1", [100 IDs of 9 chars])` writes one 1021-character `SRCGROUP GRP1` card; AERMOD's echo of it ends at `STACK0048` (511 characters), no SO error, members STACK0049..STACK0099 are not in the group. Also (long.py): a BUOYLINE group of 60 segments gives `SO E254 BLPGRP: SrcID specified on BLPGROUP keyword not defined: LINESE` (cut inside an ID, so at least loud).
- Fix: one helper `member_cards(keyword, label, ids, per_card)` that wraps on token boundaries at ~480 characters. SRCGROUP/OLMGROUP/PSDGROUP are continuable; confirm continuation for BLPGROUP/HOUREMIS/ARCFTSRC/HBPSRCID in soset.f before wrapping those (otherwise have the validator error on a line over 512).

### A6 [BUG] [medium] AREACIRC `Szinit` (SRCPARAM field 6) is silently dropped on read and cannot be set
- Where: src/pyaermod/sources.py:753-758 (AreaCircSource writer), class has no `initial_sigma_z`.
- What: soset.f ACPARM:3270-3300 reads `emis hs radius [nverts [szinit]]` (IFC == 8). AreaSource, AreaPolySource, LineSource, RLine and Volume model their Szinit; AREACIRC does not, and the reader does not put the line in `unparsed_lines`.
- Evidence: VERIFIED (ac.py): deck `SRCPARAM C1 0.001 2 50 16 3.5` is rewritten `SRCPARAM  C1  0.001000  2.00  50.00  16`; `unparsed_lines == []`.
- Fix: add `initial_sigma_z: float = 0.0` at the END of AreaCircSource (constructor order unchanged), write `{nverts} {szinit}` when non-zero, read the fifth value. Same check for other classes: AREAPOLY, VOLUME, LINE, OPENPIT, RLINE(EXT) are complete against APPARM/OPARM/LPARM/RLPARM.

### A7 [BUG] [medium] `NO2STACK 0.5` is invented for every OLM/PVMRM/GRSM/TTRM deck (known open item, still present)
- Where: src/pyaermod/pathways.py:506 (`default_no2_ratio: float = 0.5`), :965-968 (always written); reader input_reader.py:739 fills 0.5 when the deck had none.
- What: without NO2STACK, coset.f:636 resets the ratios to -9 and soset.f:1763 makes any source without its own NO2RATIO E336 ("No in-stack ratio specified"). The writer's NO2STACK 0.5 removes that check, so a deck whose sources lack a ratio (AERMOD error on the original) runs with 0.5, and a deck that gave every source a NO2RATIO gets a spurious NO2STACK line. The default is also a regulatory-looking number AERMOD deliberately does not have (setup.f:1708 removed the 0.10 default in 2023).
- Evidence: VERIFIED (t1.py): `ChemistryOptions(OLM, ozone_data=OzoneData(uniform_value=40))` with no ratio anywhere writes `NO2STACK  0.5000`. Fortran: coset.f:343-360, 636-642; soset.f:1757-1766.
- Fix: `default_no2_ratio: Optional[float] = None`; write NO2STACK only when set; validator error when it is None and any source lacks `no2_ratio` (that is E336). Keep reading 0.5 users' decks as explicit values. Needs a changelog line since the default changes output.

### A8 [BUG] [low] Fixed-decimal formats lose digits the reader keeps (round-trip drift)
- Where: sources.py:258-262 (PARTDIAM/PARTDENS `.4g`, MASSFRAX `.6f`), :492 etc. (NO2RATIO `.4f`, 11 places); pathways.py:890 (HALFLIFE `.4f`), :898 (FLAGPOLE `.2f`), :1197 (WDROTATE `.2f`), :907/:911/:919/:927 (URBANOPT population `.1f`, roughness `.2f`), :968 (NO2STACK `.4f`).
- Evidence: VERIFIED (rt.py): read `NO2RATIO 0.12345`, `PARTDIAM 1.23456 12.3456`, `PARTDENS 2.65432 1.23456`, `FLAGPOLE 1.525` -> written `0.1235`, `1.235  12.35`, `2.654  1.235`, `1.52`. MASSFRAX `.6f` is harmless (AERMOD allows +/-2 %, soset.f:1161). The module already has `exact_num` and `one_decimal_or_exact` for this.
- Fix: use `exact_num` for PARTDIAM, PARTDENS, NO2RATIO, NO2STACK, HALFLIFE, FLAGPOLE, WDROTATE, roughness (all numbers in these fields are plain decimals AERMOD reads; `exact_num` can emit `1e-05`, so use `_aermod_number`-style mantissa handling for values below 1e-4). Test impact: tests asserting `0.5000`/`.4f` text.

### A9 [BUG] [low] Half-specified RBARRIER/RDEPRESS are dropped without a message
- Where: sources.py:1285-1296 (needs both `barrier_height_1` and `barrier_dcl_1`; the second barrier is ignored unless the first is complete), :1299 (all three depression fields).
- Evidence: VERIFIED (t3.py): `RLineExtSource(barrier_height_1=3, barrier_height_2=4, barrier_dcl_2=6, depression_depth=-2, depression_wtop=10)` writes only LOCATION and SRCPARAM; validator returns nothing for it (`_validate_rline_configuration`, validator.py:1601, only gates complete pairs). A `vegetative_barriers` list longer than 2 is truncated at :1312 but the validator does reject that.
- Fix: validator errors for a barrier height without its dcl (and vice versa), a barrier 2 without barrier 1, and an incomplete depression triple.

### A10 [BUG] [low] `half_life` is documented as hours; AERMOD reads seconds
- Where: pathways.py:657 (`# hours, for decay`); no `described()` units on the field. coset.f:2633-2637: `DECOEF = 0.693/HAFLIF`, with DCAYCOEF in 1/s (the 4.81D-5 urban SO2 default is ln2 / 4 h in seconds).
- What: someone following the comment writes `HALFLIFE 4.0000` and gets a decay 3600 times too fast. The `.4f` format also writes 0.0000 for any value below 5e-5.
- Fix: say seconds, add `described("s", ...)` (the GUI then shows it), use `exact_num`.

### A11 [BUG] [low] Integer/NumPy inputs reach the writer as raw TypeErrors or misleading validator text
- Where: sources.py:312-318 (`isinstance(values, (int, float))`), pathways.py:882 (`' '.join(self.averaging_periods)`).
- Evidence: VERIFIED (t3.py, t9.py): `PointSource(building_height=np.float32(10))` / `np.int64(10)` -> `TypeError: object of type 'numpy.float32' has no len()` (np.float64 works because it subclasses float); `ControlPathway(averaging_periods=[1, 24, "annual"])`: validator says `invalid averaging period '1'; valid values: ['1', '12', ...]` (str() of the int hides why) and rejects lowercase `annual` although AERMOD upper-cases the card; with `validate=False` the writer raises `sequence item 0: expected str instance, int found`.
- Fix: `numbers.Real` in `_format_building_keyword`; `str(p).strip().upper()` for the periods in writer and validator.

### A12 [BUG] [low] The writer never quotes file names that contain a blank
- Where: pathways.py:1159-1160 (SURFFILE/PROFFILE), :436-441 (OZONEFIL/NOX_FILE), :1687 (SUMMFILE), plot/post/rank/season/eval/toxx/maxi file names, sources.py:1857 (HOUREMIS). `quote_path` exists (pathways.py:61) but no writer calls it; only the GUI upload path (browser.py:468) applies it to a field.
- Evidence: VERIFIED (t11.py): `MeteorologyPathway("My Met/a.sfc", ...)`, `OutputPathway(summary_file="my out.sum")` write `SURFFILE  My Met/a.sfc` and `SUMMFILE  my out.sum`; validator silent. AERMOD counts fields, so these are too-many-parameter errors (PLAUSIBLE, not run).
- Fix: apply `quote_path` at write time (it is idempotent only if the value is not already quoted: have it skip values that already start with `"`), so Python-API users get what GUI users get.

### A13 [BUG] [low] Building-downwash fields on AREA and VOLUME are written but ignored by AERMOD; partial POINT downwash is not validated
- Where: sources.py:413-417/615-619/894-898 (fields), :480, :682, :939 (`_building_downwash_lines`).
- Evidence: VERIFIED (t7.py): AreaSource/VolumeSource with `building_height` etc. -> `SO W233 DSBLDG: Building Dimensions Specified for Non-POINT Source` per card (20 warnings for an area with all five); a POINT with only `building_height=10.0` -> `SO E237/E241/E246/E247 Not Enough BUILDWIDs/BUILDLENs/XBADJs/YBADJs` (t7.py "point-only-hgt"); validator.py:950-1000 reports only height >= stack height (t8.py).
- Fix: validator error for a POINT with some but not all five downwash fields, warning for building fields on AREA/VOLUME. The fields themselves are API; consider deprecating them on non-POINT classes (see C3).

### A14 [BUG] [low] `AERMODProject.write(event_filename=...)` does nothing when `events` is empty, and the files are opened without an encoding
- Where: input_generator.py:286-289 (`if self.events and event_filename`), :282 and :288 (`open(..., 'w')`).
- What: asking for an event deck with no events silently writes none (docstring says it "needs events"); the platform default encoding is used, so a title with a non-ASCII character differs between macOS/Linux and Windows. Low because the title is rarely non-ASCII.
- Fix: raise `ValueError` for `event_filename` without events; `encoding="utf-8"` (or the Latin-1 the reader assumes; pick one and use it both ways).

## CONCISION

### C1 [CONCISION] [medium] Identical card tail repeated in nine `to_aermod_input` methods (~105 lines)
- Where: sources.py Point 490-502, Area 684-696, AreaCirc 760-772, AreaPoly 851-863, Volume 941-953, Line 1025-1037, RLine 1174-1186, RLineExt 1316-1328, OpenPit 1627-1639 (SidewashPoint 573-576 and BuoyLine 1442-1456 are variants of the same).
- What: `NO2RATIO` / `_deposition_to_aermod_lines(...)` / `URBANSRC` in the same order, each 13 lines, character for character.
- Change: one module function `_tail_lines(src, ids=None)` (ids = `[src.source_id]`, or segment IDs for BuoyLine, which also fixes A4 and A2) returning those lines; each method ends `lines.extend(_tail_lines(self))`. About -105 lines +20 for the helper; output byte-identical. Tests: tests/test_coverage_gaps.py (TestUrbanSourceAllTypes, ALL_SOURCE_TYPES parametrisation), test_so_deck_acceptance.py, test_so_source_construction.py, test_input_generator.py.

### C2 [CONCISION] [low] LOCATION line built eleven times with the same FLAT/elevation expression (~25 lines)
- Where: sources.py:467-470, 566-567, 663-666, 748-751, 825-828, 926-929, 1009-1013, 1161-1165, 1270-1275, 1411-1415, 1606-1609 (`('    FLAT' if self.flat_source else _f8_2(self.base_elevation))`).
- Change: `_location(src, type_text, *coords, elev=None)` returning the card; BuoyLine passes the per-segment elevation. -25 lines. Same tests as C1.

### C3 [CONCISION] [low] Building-downwash code is triplicated, and a wrapper exists only for one test
- Where: `set_building_from_bpip` 448-460, 654-656, 917-919 (plus module `_set_building_from_bpip` 351-378); `PointSource._format_building_keyword` 442-446 (used by tests/test_advanced_features.py:800 only; the module function has 10 test uses).
- Change: a field-less mixin `_HasBuilding` with the method (a plain class adds no dataclass fields, so order and constructor are unchanged); drop the wrapper and point the one test at the module function. -20 lines. Fields stay (see A13 for why they are no-ops on AREA/VOLUME).

### C4 [CONCISION] [low] Source-type Union spelled out twice, source-ID flattening twice
- Where: sources.py:1871-1874 and 1923-1926 (the Union), 1934-1943 and 1945-1968 (both branch on `isinstance(source, BuoyLineSource)` to get IDs).
- Change: `AnySource = Union[...]` alias and `_ids(source)`; -12 lines and one place to add a new source class. Tests: test_coverage_gaps.py::test_per_source_groups_*.

### C5 [CONCISION] [low] pathways.py repeated patterns (~45 lines in total)
- `file_unit` suffix: pathways.py:1443-1446, 1468-1471, 1494-1497, 1517-1521, 1691-1695, 1744-1747, 1751-1755: seven copies of `if unit is not None: line += f"  {unit}"`; a `_with_unit(line, unit)` helper saves ~14, and MaxiFile/MaxDailyFile/MaxDailyContribution could get a `to_aermod_line` like the other four so OutputPathway.to_aermod_input loses ~25 lines of inline formatting.
- URBANOPT: 901-928 has two near-identical emitters (the `urban_areas` list and the legacy `urban_option/urban_population/urban_roughness` triple). Build `areas = self.urban_areas or [UrbanArea(...)] ` once and loop: -12 lines. Behaviour difference to keep: the single-area form raises `ValueError` for roughness without a name (the list form writes "URBAN").
- `period_plot_file_names` / `period_postfile_names` (1618-1630) differ only in attribute and suffix: one private `_period_names(stem, periods, suffix)` -5; `_ozone_lines`/`_nox_lines` (448-476) share the sector loop: -8.
- MeteorologyPathway STARTEND (1176-1187) writes two f-strings that differ by the hour fields: -5; `if event_processing: pass elif ...` (980-983) reads better as `restart = not event_processing`.
- Tests: tests/test_control_debug_depletion.py, test_output_*.py, test_coverage_gaps.py (TestControlPathwayOptions).

### C6 [CONCISION] [info] The ten source dataclasses' field blocks (~160 lines) cannot be shared without changing the signature
- Where: the tail fields (`source_groups`, `is_urban`, `urban_area_name`, `no2_ratio`, gas/particle/deposition_method/method_2) at 419-434, 557-561, 621-636, 726-741, 800-815, 900-915, 987-1002, 1132-1147, 1237-1252, 1375-1390, 1486-1501.
- What: they sit after the class-specific fields, so a base dataclass would put them first and shift every positional argument, `dataclasses.fields()` order (GUI forms, ProjectSerializer) and asdict key order. A `kw_only` base would keep the class bodies short but moves them to keyword-only, which the brief excludes. Recommendation: leave the fields; take C1/C2/C3 which need no field changes. There is no `__post_init__` validation in the source classes (all of it is in validator.py), so nothing to share there.

## DEAD CODE (greps over src/ and tests/ done)
- D1 sources.py:205-216 `_FIXED_COLUMNS` and `_fx`: used only by tests/test_input_generator.py:964-995; production code calls the four bound columns. -12 lines if the test uses `_fixed_column(spec)` directly.
- D2 sources.py:442-446 `PointSource._format_building_keyword`: one test caller (see C3).
- D3 pathways.py:89-103 `SourceType` enum: never referenced in src or tests except re-export lists (api.py, input_generator.py) and `__all__`/name-lists in tests/test_init.py, test_api_core.py. Public name, so keep and mark deprecated rather than delete.
- D4 `deposition_method` (10 fields), `DepositionMethod`, and the `deposition_method` parameter of `_deposition_to_aermod_lines` (sources.py:233-247): documented as writing nothing (AERMOD has no METHOD keyword, soset.f/modules.f). Kept deliberately for old projects; chemistry_presets.py and tests still set it. Candidate for a deprecation note, not removal.
- D5 `OutputPathway.output_type` (pathways.py:1583-1590): the comment says it is ignored by the writer; same status as D4.
- D6 input_generator.py:225 and :231 `getattr(self.control, "chemistry", None)` / `getattr(self.control, "psd_credit", False)`: `control` is always a `ControlPathway`, so plain attribute access works; stale comment at :279-281 refers to a deprecation warning that does not exist.
- `ControlPathway.urban_option/urban_population/urban_roughness` duplicate `urban_areas` (see C5); not dead, but a second spelling kept for compatibility.

## Earlier-review items in this slice (state at HEAD)
- CO ELEVUNIT written: present, and worse than the review said (E110, A1).
- NO2STACK 0.5 invented: present (A7).
- PARTDIAM `.4g`: present (A8).
- Mutable defaults: none found (all `default_factory`; `OpenPitSource.from_area` deep-copies nested objects).
- Enum/string mismatches: `TerrainType` and `ChemistryMethod` tokens match coset.f (ELEV not ELEVATED); no mismatch found. `ControlPathway.pollutant_id` strings are written verbatim (AERMOD upper-cases the card).
- Number formatting: `_fixed_column`/`_aermod_number` always yield a mantissa with a decimal point (no E208). Values below 1e-6 are written with `.6g`, which is fine for STODBL. No free-format rejection found.
- Checked against the Fortran and found correct: BLPINPUT field order (BL_AVGINP), RLINE/RLINEXT SRCPARAM (RLPARM), AREAPOLY/AREA/LINE/OPENPIT/VOLUME SRCPARAM, PLOTFILE MONTH form (OUPLOT), PSD/SRCGROUP order rules, SRCGROUP ALL BACKGROUND handling (only A3's missing default).

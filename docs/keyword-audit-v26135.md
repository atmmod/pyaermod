# AERMOD v26135 keyword audit

**Scope.** Every runstream keyword the AERMOD v26135 Fortran source
recognises, compared against what `pyaermod.input_reader` parses and
what `tests/test_input_reader.py` exercises.

**Source of truth.** `aermod_source_v26135/modules.f` declares the
canonical keyword table (`DATA (KEYWD(I),I=1,IKN)`, `IKN=122`); the
per-pathway dispatch lives in `coset.f`, `soset.f`, `reset.f`, `meset.f`,
`ouset.f` and `evset.f` (`IF (KEYWRD .EQ. '...')`). Extracted with:

```bash
# The first filter drops fixed-form comment lines (column 1 = C/!/*).
# Without it soset.f reports 37 keywords instead of 36: SBARSRCGRP is
# present only as a commented-out dispatch branch.
grep -E "^[^C!*]" coset.f \
  | grep -ohE "KEYWRD\s*\.EQ\.\s*'[A-Z0-9_]+'" \
  | grep -oE "'[A-Z0-9_]+'" | tr -d "'" | sort -u
```

Only `soset.f` has such a branch; the other five files give the same total
with or without the filter.

"Handled" means the keyword appears as a string literal in
`src/pyaermod/input_reader.py` and is either stored structurally or
consciously recognised and passed through. "Tested" means a deck in
`tests/test_input_reader.py` exercises that parse path. Unhandled
keywords fall into the reader's generic path: the line is ignored without
error (verified for every keyword below by the
`test_unhandled_*_keywords_pass_through` parametrised tests), so decks
that use them still open but do not round-trip those lines.

**Parse rate on EPA's real decks.** All **53 / 53** `.inp` decks in the
v26135 test-case archive (`test_cases/aermet26135_aermod26135/inputs/`;
the deck files are byte-identical across the three EPA reference sets)
parse without exception through `parse_aermod_input` (decoded as
Latin-1). The project's earlier "138/138" figure referred to the
pre-2026 archive layout.

**Validator.** `src/pyaermod/validator.py` validates the object model
(`AERMODProject` dataclasses), not keyword text, so it carries no keyword
literals. Its checks map onto the handled keywords through the fields
those keywords populate (e.g. `NO2STACK`/`OZONEVAL`/`OZONEFIL` →
`_validate_chemistry`, `BACKGRND`/`BGSECTOR` → `_validate_background`,
`GASDEPOS`/`PARTDIAM`/`MASSFRAX`/`PARTDENS` → `_validate_deposition_params`,
`LOCATION`/`SRCPARAM` → the per-source-type validators, `GRIDCART`/
`GRIDPOLR` → `_validate_cartesian_grid`/`_validate_polar_grid`). Unhandled
keywords therefore never reach the validator.

## Summary

| Pathway | v26135 keywords | Handled + tested | Handled + untested | Unhandled |
|---|---:|---:|---:|---:|
| CO | 37 | 32 | 0 | 5 |
| SO | 36 | 18 | 0 | 18 |
| RE | 7 | 7 | 0 | 0 |
| ME | 14 | 8 | 0 | 6 |
| OU | 16 | 11 | 0 | 5 |
| EV | 5 | 1 | 0 | 4 |

Reader completeness tranche 1 (this branch) moved 18 keywords from
"Unhandled" to "Handled + tested" -- the restart/multi-year trio, the NOx
background family with the ozone sector and unit keywords, the OU
design-value keywords and the gas-deposition defaults -- and each is
stored structurally *and* written back, not merely recognised. The field
layouts were read off `coset.f` / `ouset.f` with `scripts/keyword_oracle.py`
(the same script prints them from a fresh EPA source tree) and every form
the writer emits passes AERMOD's setup pass in
`tests/test_source_deck_acceptance.py`; `tests/test_epa_deck_roundtrip.py`
checks that all 53 EPA decks round-trip those keyword lines token for
token (five are vendored so the check also runs without the archive).

(`STARTING`/`FINISHED` are structural and excluded from the counts.)
`src/pyaermod/input_reader.py` statement coverage from its own test file:
85.0 % before this audit, 99.8 % after (the single remaining miss,
line 168, is an unreachable guard: pathway lines are stripped and
non-empty before they reach `_group_keywords`).

## Handled + tested

**CO (32):** AVERTIME, DCAYCOEF, DEBUGOPT, ERRORFIL, FLAGPOLE, GASDEPDF,
GASDEPVD, GDLANUSE, GDSEASON, HALFLIFE, INITFILE, LOW_WIND, MODELOPT,
MULTYEAR, NO2EQUIL, NO2STACK, NOXSECTR, NOXVALUE, NOX_FILE, NOX_UNIT,
NOX_VALS, O3SECTOR, O3VALUES, OZONEFIL, OZONEVAL, OZONUNIT, POLLUTID,
RUNORNOT, SAVEFILE, TITLEONE, TITLETWO, URBANOPT.
Field layouts, from `coset.f`: `MULTYEAR [H6H] savfil [initfil]` (H6H is
optional and warned about, W352); `SAVEFILE [savfil [dayinc [savfl2]]]`
and `INITFILE [inifil]` (a bare keyword means `SAVE.FIL`); the background
keywords take `[SECTn] value [units]` (OZONEVAL, NOXVALUE), `[SECTn] file
[units [format]]` (OZONEFIL, NOX_FILE) and `[SECTn] flag values...`
(O3VALUES, NOX_VALS, accumulating over lines, same flags as EMISFACT);
O3SECTOR/NOXSECTR take 2-6 ascending start directions; OZONUNIT/NOX_UNIT
one of PPB, PPM, UG/M3; `GASDEPDF fo fseas2 fseas5 [refspe]`;
`GASDEPVD uservd`; GDSEASON 12 categories in 1-5; GDLANUSE 36 categories
in 1-9. Ozone and NOx sector forms are stored per sector
(`OzoneData.by_sector`, `NOxBackground.by_sector`).
MODELOPT options understood: CONC, DEPOS, DDEP, WDEP, FLAT, ELEV/ELEVATED,
FLATSRCS, DFAULT, OLM, PVMRM, ARM2, GRSM, NOCHKD. Any other option token
(v26135 also accepts ALPHA, BETA, FASTALL, FASTAREA, SCREEN, TOXICS, TTRM,
TTRM2, PSDCREDIT, NOURBTRAN, NOWARN, WARNCHKD, VECTORWS, ROMBERG, AREADPLT,
AREAMNDR, BAREDGE, RLINEFDH, AWMADW, DRYDPLT/NODRYDPLT, WETDPLT/NOWETDPLT,
NOMINO3, HBP, PLATFORM, AIRCRAFT, SWPOINT, RLINE, LINE, AREA, SBARRIER,
VBARRIER, SCIM, METEOR, URBANDB, BLPDBUG, HBPDBG, NOSTD, PRIME, PERIOD,
ANNUAL, MODEL, DEFAULT) is ignored without error.

**SO (18):** BACKGRND, BACKUNIT, BGSECTOR, BUILDHGT, BUILDLEN, BUILDWID,
ELEVUNIT, EMISFACT, GASDEPOS, HOUREMIS, INCLUDED, LOCATION, MASSFRAX,
PARTDENS, PARTDIAM, SRCGROUP, SRCPARAM, URBANSRC — plus XBADJ and YBADJ,
which are in the keyword table but dispatched outside the
`KEYWRD .EQ.` pattern in `soset.f`.
LOCATION source types constructed: POINT, AREA, VOLUME, LINE, RLINE,
OPENPIT, AREACIRC. Recognised but **not constructed** (the LOCATION line
parses, the source is dropped): RLINEXT, AREAPOLY, BUOYLINE, POINTCAP,
POINTHOR, SWPOINT, OPEN_PIT (v26135 spelling).

**RE (7):** DISCCART, DISCPOLR, ELEVUNIT, EVALCART, GRIDCART (including
the single-line `XYINC` form and the continuation-line form), GRIDPOLR
(ORIG/DIST/GDIR in both the init/num/delta and explicit-list forms),
INCLUDED.

**ME (8):** PROFBASE, PROFFILE, SITEDATA, STARTEND, SURFDATA, SURFFILE,
UAIRDATA, WDROTATE.

**OU (11):** DAYTABLE, FILEFORM, MAXDAILY, MAXDCONT, MAXIFILE, MAXTABLE,
MXDYBYYR, PLOTFILE (ALL and per-group), POSTFILE, RECTABLE (numeric and
`FIRST-THIRD` style ranks), SUMMFILE.
Field layouts, from `ouset.f`: `MAXDAILY grpid filnam [funit]` and
`MXDYBYYR grpid filnam [funit]` (no averaging-period field; the period is
implied by the NAAQS processing, and AERMOD rejects both unless
NO2AVE/SO2AVE/PM25AVE is active, E162/E163); `MAXDCONT grpid upper lower
filnam [funit]` or `MAXDCONT grpid upper THRESH thresh filnam [funit]`,
incompatible with SAVEFILE/INITFILE/MULTYEAR (E153); `FILEFORM FIX|EXP`.
The MAXDAILY and MXDYBYYR files are read by
`pyaermod.design_values.read_maxdaily` / `read_mxdybyyr`.

**EV (1):** INCLUDED (the EV pathway is recognised by the splitter; its
other keywords are unhandled, see below).

## Handled + untested

None remaining after this audit. Before it, `STARTEND`, `RECTABLE` and
`MAXTABLE` were handled without a dedicated reader test, and roughly
forty single-line branches (MODELOPT deposition flags, `FLATSRCS`,
`DCAYCOEF`, CO `ELEVUNIT`, file-form `O3VALUES`, non-enum `POLLUTID`,
every malformed-line guard in the SO parser, the source-construction
guards, the explicit-direction `GDIR` forms, short RE lines, `WDROTATE`,
`MAXIFILE`, and the sandbox chemistry/per-group-plotfile checks) were
uncovered.

## Unhandled (pass-through only)

Each of these is ignored by the reader; a deck using it parses, but the
line is not represented on the `AERMODProject` and is lost on rewrite.
None of the 53 EPA decks fail because of them (they are all in the
pass-through path), but several are common in practice and are the
natural next reader features.

**CO (5):** ARCFTOPT, ARMRATIO, AWMADWNW, EVENTFIL, ORD_DWNW.
(`EVENTFIL` is written by `ControlPathway.eventfil` but not read back.)

**SO (18):** ARCFTSRC, AREAVERT, BLPGROUP, BLPINPUT, CONCUNIT, DEPOUNIT,
EMISUNIT, HBPSRCID, METHOD_2, NO2RATIO, OLMGROUP, PLATFORM, PSDGROUP,
RBARRIER, RDEPRESS, RLEMCONV, SBARRIER, VBARRIER.
Highest value: `AREAVERT` (needed before AREAPOLY sources can be
constructed), `BLPINPUT`/`BLPGROUP` (BUOYLINE), `OLMGROUP`/`PSDGROUP`
(group semantics for OLM and PSD-credit runs), `NO2RATIO`, `EMISUNIT`/
`CONCUNIT`/`DEPOUNIT`, and the RLINE barrier/depression keywords
(`RBARRIER`, `RDEPRESS`, `SBARRIER`, `VBARRIER`, `RLEMCONV`). (`SBARSRCGRP`
appears in `soset.f` only as a commented-out dispatch line — `soset.f:596`
— and nowhere in the canonical `modules.f` table, so it is not counted.)

**ME (6):** DAYRANGE, NOTURBCO, NOTURBST, NUMYEARS, SCIMBYHR, WINDCATS.
The keyword table also lists NOTURB, NOSA, NOSW, NOSAST, NOSWST, NOSACO,
NOSWCO (turbulence-suppression flags), which `meset.f` does not dispatch
through the `KEYWRD .EQ.` pattern.

**OU (5):** EVALFILE, NOHEADER, RANKFILE, SEASONHR, TOXXFILE.

**EV (4):** EVENTLOC, EVENTOUT, EVENTPER, FILEFORM.

## Discrepancies and follow-ups

1. **`MAXIFILE` argument order.** AERMOD's syntax is
   `MAXIFILE <aveper> <grpid> <thresh> <filename>`; the reader stores the
   *first* token as `OutputPathway.max_file`. The existing behaviour is
   pinned by `test_maxifile_filename_captured` so the discrepancy is
   visible; fixing it means teaching the writer the same four-field form.
2. **RLINEXT / AREAPOLY / BUOYLINE** LOCATION lines are recognised but the
   sources are dropped because their multi-line companions (`AREAVERT`,
   `BLPINPUT`, per-end z values) are not reconstructed.
3. **`GRIDPOLR DIST/GDIR` heuristics.** Three numeric tokens are
   interpreted as init/num/delta when the integer-looking token is in the
   expected position, otherwise as an explicit list; a three-distance
   explicit list with an integer-looking middle value is misread.
4. **No unknown-keyword report.** The module docstring promises unknown
   keywords are "collected in `AERMODProject.unparsed_lines`"; the
   current implementation silently drops them. Either implement the
   collection or correct the docstring.
5. **Pass-through tests pin behaviour, not support.** The
   `test_unhandled_*_keywords_pass_through` cases assert only that the
   deck still parses; when support for a keyword is added, replace the
   corresponding parametrised entry with a structural assertion. (Done
   for the 18 keywords of tranche 1: see `TestCORestartKeywords`,
   `TestCONOxAndOzoneBackground`, `TestCOGasDepositionDefaults` and the
   design-value cases in `TestMEOUKeywordsV26135`.)
6. **Ozone writer forms.** Before tranche 1 the writer emitted every
   ozone input as `O3VALUES` (`O3VALUES <file>`, `O3VALUES UNIFORM v`,
   `O3VALUES SECTOR n v`) and the NOx file as `NOXVALUE <file>`; AERMOD
   rejects all four (E201/E203/E208). Fixed: OZONEFIL, OZONEVAL,
   `OZONEVAL SECTn`, NOX_FILE. The reader keeps accepting the two legacy
   `O3VALUES` spellings so older pyaermod decks still open.
7. **`GasDepositionParams` field semantics.** AERMOD's `GASDEPOS` fields
   are `Da Dw rcl Henry` (EPA's `testgas` deck: `0.08962 1.04E-5 2.51E4
   557.0`); pyaermod's validator reads the third as a 0-1 reactivity and
   rejects EPA's own values. Not a reader defect (the values round-trip),
   but the writer-side model needs the same treatment as the keywords
   above (WP-2).

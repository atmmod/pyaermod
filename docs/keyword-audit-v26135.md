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
| SO | 36 | 32 | 0 | 4 |
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

Reader completeness tranche 2 (source construction) moved 14 SO keywords
from "Unhandled" to "Handled + tested": AREAVERT, BLPINPUT, BLPGROUP,
OLMGROUP, PSDGROUP, NO2RATIO, EMISUNIT, CONCUNIT, DEPOUNIT, RBARRIER,
RDEPRESS, SBARRIER, VBARRIER and RLEMCONV, so AREAPOLY, BUOYLINE and
RLINEXT sources are constructed and written back, and the OLM, PSD-credit,
unit-conversion and RLINE-barrier keywords round-trip. The field layouts
came from `soset.f` (ARVERT, APPARM, BL_AVGINP, BLPGRP, OLMGRP, PSDGRP,
NO2RAT, EMUNIT, COUNIT, DPUNIT, RLINEBAR_INPUTS, RLINEDPR_INPUTS,
SBARRIER_INPUTS, VBARRIER_INPUTS, GASDEP, URBANS, SOLOCA, SOPARM); the
probe decks `scripts/oracle_decks/13`-`18` record what AERMOD said about
the first guesses. Evidence: `tests/test_so_deck_acceptance.py` (20 forms
through the setup pass), `tests/test_epa_source_roundtrip.py` (token for
token on all 53 decks, seven more vendored), and
`tests/regulatory/test_epa_rewritten_so.py`, which runs the fourteen EPA
decks that use these keywords with pyaermod's rewritten SO pathway and
scores every POSTFILE against EPA's reference (all at slope 1.000000).
Handled keywords now total 91 of 115.

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
FLATSRCS, DFAULT, OLM, PVMRM, ARM2, GRSM, NOCHKD, and (tranche 2) ALPHA,
BETA and PSDCREDIT, which are stored on `ControlPathway.alpha` / `.beta` /
`.psd_credit` and written back; before tranche 2 they were dropped, so a
rewritten RLINEXT, GASDEPOS or PSDGROUP deck failed E198 / E146. Any other
option token (v26135 also accepts FASTALL, FASTAREA, SCREEN, TOXICS, TTRM,
TTRM2, NOURBTRAN, NOWARN, WARNCHKD, VECTORWS, ROMBERG, AREADPLT,
AREAMNDR, BAREDGE, RLINEFDH, AWMADW, DRYDPLT/NODRYDPLT, WETDPLT/NOWETDPLT,
NOMINO3, HBP, PLATFORM, AIRCRAFT, SWPOINT, RLINE, LINE, AREA, SBARRIER,
VBARRIER, SCIM, METEOR, URBANDB, BLPDBUG, HBPDBG, NOSTD, PRIME, PERIOD,
ANNUAL, MODEL, DEFAULT) is ignored without error.
`URBANOPT` is read in both of `coset.f` URBOPT's field orders
(`population [name] [roughness]` for one urban area, `urbanid population
[name] [roughness]` when a deck has several cards) and written in the
single-area order; only one urban area is modelled, and a later card
overrides an earlier one.

**SO (32):** AREAVERT, BACKGRND, BACKUNIT, BGSECTOR, BLPGROUP, BLPINPUT,
BUILDHGT, BUILDLEN, BUILDWID, CONCUNIT, DEPOUNIT, ELEVUNIT, EMISFACT,
EMISUNIT, GASDEPOS, HOUREMIS, INCLUDED, LOCATION, MASSFRAX, NO2RATIO,
OLMGROUP, PARTDENS, PARTDIAM, PSDGROUP, RBARRIER, RDEPRESS, RLEMCONV,
SBARRIER, SRCGROUP, SRCPARAM, URBANSRC, VBARRIER — plus XBADJ and YBADJ,
which are in the keyword table but dispatched outside the
`KEYWRD .EQ.` pattern in `soset.f`.
LOCATION source types constructed: POINT, AREA, VOLUME, LINE, RLINE,
OPENPIT, AREACIRC, and (tranche 2) AREAPOLY, BUOYLINE, RLINEXT.
Recognised but **not constructed** (the LOCATION line parses, the source
is dropped): POINTCAP, POINTHOR, SWPOINT, OPEN_PIT (v26135 spelling);
POINTCAP and POINTHOR take POINT's SRCPARAM layout and are the natural
next step (EPA's `capped` decks).
Field layouts, from `soset.f`: `LOCATION srcid TYPE x y [zelev|FLAT]`,
with `x1 y1 x2 y2` for LINE/RLINE/BUOYLINE and `x1 y1 z1 x2 y2 z2` for
RLINEXT before the optional elevation (SOLOCA; every elevation is now
applied to `base_elevation`, which the reader used to drop); SRCPARAM
field counts per type (SOPARM): AREAPOLY `emis relhgt nverts [szinit]`,
LINE `emis relhgt width [szinit]`, RLINEXT exactly `emis dcl width
szinit`, BUOYLINE exactly `emis relhgt`; `AREAVERT srcid x y ...` in pairs
over any number of lines, the first pair equal to LOCATION (E262), up to
`nverts+1` pairs read (ARVERT); `BLPINPUT [grpid] len bhgt bwid lwid bsep
fprm` — eight fields file the parameters under the implicit group ALL,
nine name the group, a second eight-field record is E201 (BL_AVGINP);
`BLPGROUP grpid members|ALL` with ranges and continuation (BLPGRP);
`OLMGROUP grpid [members]` (bare ALL allowed, OLM required, E144);
`PSDGROUP INCRCONS|RETRBASE|NONRBASE members` (PSDCREDIT required, E146;
SRCGROUP then E105; other IDs E287); `NO2RATIO srcid|range ratio`
(exactly two fields, 0-1, E336); `EMISUNIT|CONCUNIT|DEPOUNIT factor
emislabel outlabel` (exactly three; EMISUNIT with CONCUNIT/DEPOUNIT E159,
with two output types E158); `RBARRIER srcid ht dcl [ht2 dcl2]`,
`RDEPRESS srcid depth wtop wbottom`, `VBARRIER srcid ht wt dcl lai lm
[x2]` (8 or 13 fields), `SBARRIER barid STA n` / `barid xbb ybb xbe ybe
ht z` / `barid END`, all needing ALPHA and FLAT (E198 / E713);
`RLEMCONV` bare; `GASDEPOS srcid|range Da Dw rcl Henry` (exactly four,
positive, 0 selecting a built-in value for HG0/HGII/TCDD/BAP/SO2/NO2;
ALPHA required, GASDEPVD excluded); `URBANSRC ALL`, `URBANSRC ids...`
(one urban area) or `URBANSRC urbanid ids...` (several), with ranges.
Two behaviours of `soset.f` shape the writer: a group continuation card
(SRCGROUP, OLMGROUP, PSDGROUP, BLPGROUP) that is not adjacent to its
group is filed under the *last* group defined, and the BACKGROUND flag
of `SRCGROUP ALL` is read only from the card that defines ALL, so
continuation lines are merged on read and each group is written on
consecutive cards; and STODBL reads an exponent only after a mantissa
with a decimal point (`1.0e+06`, not `1e+06`).

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

**SO (4):** ARCFTSRC, HBPSRCID, METHOD_2, PLATFORM.
`METHOD_2` matters most: EPA's `testpart` and `testprt2` decks use it for
particle deposition, so a rewrite of either changes the answer.
(`SBARSRCGRP` appears in `soset.f` only as a commented-out dispatch line —
`soset.f:596` — and nowhere in the canonical `modules.f` table, so it is
not counted.)

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
2. **RLINEXT / AREAPOLY / BUOYLINE** — closed by tranche 2. All three are
   constructed from their multi-line companions and written back;
   `tests/regulatory/test_epa_rewritten_so.py` shows EPA's `allsrcs`,
   `blp_urban`, the three `aermod-baldwin*` and the four RLINEXT `Test*`
   decks at slope 1.000000 with pyaermod's SO pathway. Still dropped:
   POINTCAP, POINTHOR, SWPOINT (see the SO section).
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
   design-value cases in `TestMEOUKeywordsV26135`; and for the 14 SO
   keywords of tranche 2 in `tests/test_so_source_construction.py`.)
6. **Ozone writer forms.** Before tranche 1 the writer emitted every
   ozone input as `O3VALUES` (`O3VALUES <file>`, `O3VALUES UNIFORM v`,
   `O3VALUES SECTOR n v`) and the NOx file as `NOXVALUE <file>`; AERMOD
   rejects all four (E201/E203/E208). Fixed: OZONEFIL, OZONEVAL,
   `OZONEVAL SECTn`, NOX_FILE. The reader keeps accepting the two legacy
   `O3VALUES` spellings so older pyaermod decks still open.
7. **`GasDepositionParams` field semantics** — closed by tranche 2. The
   dataclass is now `diffusivity`, `diffusivity_water`,
   `cuticular_resistance`, `henry_constant` (`GASDEPOS srcid Da Dw rcl
   Henry`, all required), the validator applies `soset.f` GASDEP's rules
   (positive, 0 only for the six pollutants with built-in values, ALPHA
   required, GASDEPVD excluded), and EPA's `testgas` values validate and
   are written back unchanged (`tests/test_so_deck_acceptance.py`
   `gasdepos-epa-testgas`).
8. **Rewriting whole EPA decks.** With the SO pathway complete for the
   fourteen decks above, nine of them also reach parity as whole
   rewritten decks; the other five are held back by receptor and output
   forms outside this tranche — `GRIDPOLR DIST` explicit lists and
   `ORIG` by source ID (item 3), two-field `DISCCART` lines, and more
   than one `POSTFILE` or a multi-rank `RECTABLE` — which WP-3 owns.
9. **Urban areas.** `ControlPathway` models one urban area. EPA's
   `multurb` deck (four `URBANOPT` cards, `URBANSRC urbanid ids`) reads
   the last card only; the multi-area `URBANSRC` form is parsed but the
   writer emits the single-area form. A list of urban areas on the
   control pathway would close this.

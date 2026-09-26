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

"Handled" means the keyword is stored structurally on the
`AERMODProject` by `src/pyaermod/input_reader.py` and written back by the
writer. "Tested" means a deck in `tests/test_input_reader.py` or
`tests/test_reader_roundtrip_fidelity.py` exercises that parse path.
Every other line -- an unhandled keyword, or a form of a handled keyword
the model cannot hold -- is kept verbatim in
`AERMODProject.unparsed_lines` (pathway, keyword, fields, line number),
reported through `logging`, and written back into its pathway on output
(`pyaermod.unparsed`; the placement rules are in
`input_generator._with_preserved`). Decks that use such keywords open,
rewrite with every line present, and pass AERMOD's setup pass; what they
do not get is structural access to those lines. The
`test_unhandled_*_keywords_pass_through` parametrised tests still hold,
and `tests/test_epa_deck_roundtrip.py::unaccounted_lines` asserts over
all 53 EPA decks that no line is in neither category.

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
| CO | 37 | 37 | 0 | 0 |
| SO | 36 | 36 | 0 | 0 |
| RE | 7 | 7 | 0 | 0 |
| ME | 14 | 14 | 0 | 0 |
| OU | 16 | 16 | 0 | 0 |
| EV | 5 | 5 | 0 | 0 |

Every one of the 115 dispatched keywords is recognised and tested. 104
have a field on the model; the eleven that are "handled" without one
(ERRORFIL, DEBUGOPT, NO2EQUIL, EMISFACT, HOUREMIS, INCLUDED, BACKUNIT,
SO ELEVUNIT, EVALCART, DISCPOLR, SITEDATA) are stored verbatim by
decision, each with its reason in "Stored only, by design" below.

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

Reader completeness tranche 3 (`claude/wp3-audit-roundtrip`) changed no
count in the table but closed the audit's items 1, 3,
4 and 5 and, in doing so, re-read the RE and OU parsers and the CO writer
against `reset.f`, `ouset.f`, `coset.f` and `setup.f`. What it found is
in "Round-trip guarantee" and "Discrepancies and follow-ups" below; the
short version is that four writer forms pyaermod had emitted since its
first release were fatal in AERMOD (every polar grid, `ELEVATED`,
`NO2STACK` under ARM2, a single name-first `URBANOPT`), and that EPA's
own decks rely on a runstream feature the reader did not implement (a
line blank through the keyword columns continues the previous keyword).

Reader completeness tranche 4 (WP-5, `claude/wp5-ev-me-ou-keywords`)
moved the last 24 keywords from "Unhandled" to "Handled + tested": the EV
pathway (EVENTPER, EVENTLOC, EVENTOUT and the EV dispatch of FILEFORM),
DAYRANGE, NUMYEARS, WINDCATS, SCIMBYHR and the nine turbulence keywords
on ME, NOHEADER, RANKFILE, SEASONHR, EVALFILE and TOXXFILE on OU,
ARMRATIO, AWMADWNW, ORD_DWNW and ARCFTOPT on CO, METHOD_2, PLATFORM,
ARCFTSRC and HBPSRCID on SO, and the construction of POINTCAP, POINTHOR
and SWPOINT sources. The layouts came from `evset.f` (EVPER, EVLOC,
OEVENT, EV_OUCARD), `meset.f` (DAYRNG, NUMYR, WSCATS, SCIMIT, TURBOPT),
`ouset.f` (NOHEADER, OURANK, OUSEAS, OUEVAL, OUTOXX), `coset.f`
(ARM2_Ratios, AWMA_DOWNWASH, ORD_DOWNWASH, EVNTFL) and `soset.f` (METH_2,
PLATFM, AIRCRAFT, HBPSOURCE, PPARM, SWPARM, SOLOCA); probe decks 20-30
record what AERMOD said, and the deck AERMOD wrote itself for EVENTFIL
(29b) is the EV layout reference. What the tranche found on the way is
in "Round-trip guarantee" and item 10 below: the writer's METHOD line
was never a keyword (E105), its EVENTPER card never had the right field
count (E201), the EV block went where PRESET never looks, an exit
velocity of 0.001 m/s was rounded to 0.00 by the SRCPARAM column, and a
`LOCATION ... FLAT` source lost its flag (flatelev at slope 1.17 before,
1.000000 after).

(`STARTING`/`FINISHED` are structural and excluded from the counts.)
`src/pyaermod/input_reader.py` statement coverage from its own test file:
85.0 % before this audit, 99.8 % after (the single remaining miss,
line 168, is an unreachable guard: pathway lines are stripped and
non-empty before they reach `_group_keywords`).

## Handled + tested

**CO (37):** ARCFTOPT, ARMRATIO, AVERTIME, AWMADWNW, DCAYCOEF, DEBUGOPT,
ERRORFIL, EVENTFIL, FLAGPOLE, GASDEPDF, GASDEPVD, GDLANUSE, GDSEASON,
HALFLIFE, INITFILE, LOW_WIND, MODELOPT, MULTYEAR, NO2EQUIL, NO2STACK,
NOXSECTR, NOXVALUE, NOX_FILE, NOX_UNIT, NOX_VALS, O3SECTOR, O3VALUES,
ORD_DWNW, OZONEFIL, OZONEVAL, OZONUNIT, POLLUTID, RUNORNOT, SAVEFILE,
TITLEONE, TITLETWO, URBANOPT.
Of these, DEBUGOPT, ERRORFIL and NO2EQUIL have no field and travel in
`unparsed_lines` (see "Stored only, by design"); RUNORNOT
(`ControlPathway.run_model`), EVENTFIL (`.eventfil` and
`.eventfil_option`, coset.f EVNTFL: `evfile [SOCONT|DETAIL]`; the bare
form, AERMOD's EVENTS.INP with W207, is kept verbatim) and URBANOPT are
stored. Tranche 4: `ARMRATIO min max` (`.arm2_ratios`; ARM2_Ratios wants
exactly two fields, ARM2 (E145), 0 < min <= max <= 1 and 0.5-0.9 under
DFAULT (E380, probe 24b)); `AWMADWNW` one to five of STREAMLINE,
AWMAUEFF, AWMAUTURB, AWMAUTURBHX, AWMAENTRAIN (`.awma_downwash`; ALPHA
E122, STREAMLINE needs AWMAUTURB or AWMAUTURBHX E126, no duplicates
E121) and `ORD_DWNW` one to three of ORDCAV, ORDUEFF, ORDTURB
(`.ord_downwash`; ALPHA E123), with AWMAUEFF and ORDUEFF in conflict
(E124, probe 24c); `ARCFTOPT [airport]` (`.aircraft_option`,
`.airport_id`), written right after MODELOPT as coset.f requires (E140). `URBANOPT` follows `coset.f` URBOPT: with one card
the fields are `pop [name [z0]]`, with several `id pop [name [z0]]`
(`ControlPathway.urban_areas`, a `UrbanArea` per line; PREURB counts the
cards). The legacy `urban_option`/`urban_population` pair is written in
the one-card layout, and the name-first line earlier releases wrote is
still read.
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
MODELOPT options with a field: CONC, DEPOS, DDEP, WDEP, FLAT, ELEV,
DFAULT, ALPHA, BETA, PSDCREDIT (tranche 2: `ControlPathway.alpha` /
`.beta` / `.psd_credit`), OLM, PVMRM, ARM2, GRSM, TTRM, TTRM2. Terrain follows
`coset.f` MODOPT: `ELEV` is the token (the writer used to emit
`ELEVATED`, which is E203), `FLAT` then `ELEV` on one line means flat
sources in elevated terrain (`TerrainType.FLATSRCS`, which has no token
of its own and is written as that pair), and a `FLAT` after `ELEV` is
ignored (W206). Every other option token (FASTALL, SCREEN, TOXICS,
PSDCREDIT, NOCHKD, NOURBTRAN, VECTORWS, SCIM, ...) is kept in
`ControlPathway.extra_model_options` and written back as given.
`URBANOPT` follows `coset.f` URBOPT: with one card the fields are
`pop [name [z0]]`, with several `id pop [name [z0]]` (PREURB counts the
cards). Every card is kept (`ControlPathway.urban_areas`, a `UrbanArea`
per line, closing item 9 below); `urban_option` / `urban_population` /
`urban_roughness` describe the first area and are written in the one-card
layout when `urban_areas` is empty. The name-first single card earlier
releases wrote (E208 in AERMOD) is still read.

**SO (36):** ARCFTSRC, AREAVERT, BACKGRND, BACKUNIT, BGSECTOR, BLPGROUP,
BLPINPUT, BUILDHGT, BUILDLEN, BUILDWID, CONCUNIT, DEPOUNIT, ELEVUNIT,
EMISFACT, EMISUNIT, GASDEPOS, HBPSRCID, HOUREMIS, INCLUDED, LOCATION,
MASSFRAX, METHOD_2, NO2RATIO, OLMGROUP, PARTDENS, PARTDIAM, PLATFORM,
PSDGROUP, RBARRIER, RDEPRESS, RLEMCONV, SBARRIER, SRCGROUP, SRCPARAM,
URBANSRC, VBARRIER — plus XBADJ and YBADJ, which are in the keyword
table but dispatched outside the `KEYWRD .EQ.` pattern in `soset.f`.
LOCATION source types constructed: every type `soset.f` SOLOCA accepts --
POINT, POINTCAP, POINTHOR, SWPOINT, AREA, AREACIRC, AREAPOLY, VOLUME,
LINE, RLINE, RLINEXT, BUOYLINE and OPENPIT (also spelt OPEN_PIT and
OPEN-PIT, which SOLOCA folds to OPENPIT). POINTCAP and POINTHOR are
`PointCapSource` / `PointHorSource`, subclasses of `PointSource` with
POINT's SRCPARAM layout (PPARM; probe 23); SWPOINT is
`SidewashPointSource` with `emis hs bw bl bh ba` (SWPARM, exactly six,
ALPHA required: E198, probe 23b). The `FLAT` literal in the elevation
field (`flat_source`) is kept and written back. Tranche 4 keywords:
`METHOD_2 srcid|range finemass dg` (`method_2`, `Method2Params`, on every
source type; METH_2 reads exactly two values, needs ALPHA without
DFAULT (E198/E197, probes 21/21b), 0-1 for the fraction (E332), and
excludes PARTDIAM on the same source (E386)); `PLATFORM srcid elev hb wb`
(`PointSource.platform`, `PlatformParams`; PLATFM reads two or three
values, POINT types only E631, ALPHA E198, probe 22); `ARCFTSRC` and
`HBPSRCID` member tokens (`SourcePathway.aircraft_sources`,
`.hbp_sources`, kept as written -- IDs, ranges or ALL -- and written on
one card before the group keywords; ARCFTSRC needs ARCFTOPT (E821), an
HOUREMIS file with the aircraft record (E823) and a VOLUME or AREA
source (E833, probe 25b); HBPSRCID needs MODELOPT HBP (E130) and ALPHA).
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

**RE (7):** DISCCART, DISCPOLR, ELEVUNIT, EVALCART, GRIDCART, GRIDPOLR,
INCLUDED. DISCPOLR, EVALCART and INCLUDED have no field and travel in
`unparsed_lines`. The network sub-keywords follow `reset.f`: GRIDCART
takes `XYINC` (six fields) or explicit `XPNTS`/`YPNTS` lists
(`CartesianGrid.x_points`/`.y_points`; the two forms are exclusive per
network, E180) and `ELEV`/`HILL`/`FLAG` rows (`row v1 v2 ...`,
accumulating; `.grid_elevations`/`.grid_hills`/`.grid_flags`). GRIDPOLR
takes `ORIG x y` or `ORIG srcid` (POLORG; `PolarGrid.origin_source_id`),
`DIST d1 d2 ...` -- POLDST reads every field as a ring distance, there is
no init/num/delta form (`.distances`) -- `GDIR num init delta` (GENPOL,
exactly three fields, count first) or `DDIR a1 a2 ...` (RADRNG;
`.directions`), and the same three row keywords. On every one of these
lines the network ID may be omitted (REPOLR/RECART take a bare
sub-keyword as the current network), and the keyword columns may be
blank (setup.f EXKEY inherits the previous keyword), which is how twenty
EPA decks write their polar blocks. DISCCART takes `x y` alone in FLAT
runs (a third field is W229 there) or `x y zelev [zhill [zflag]]`.

**ME (14):** DAYRANGE, NUMYEARS, PROFBASE, PROFFILE, SCIMBYHR, SITEDATA,
STARTEND, SURFDATA, SURFFILE, UAIRDATA, WDROTATE, WINDCATS, and the nine
turbulence keywords NOTURB, NOTURBST, NOTURBCO, NOSA, NOSW, NOSAST,
NOSWST, NOSACO, NOSWCO, which `meset.f` dispatches together (one
`KEYWRD .EQ.` chain, one status switch) and which count as one keyword
in the table. SITEDATA has no field and travels in `unparsed_lines`.
STARTEND takes six fields or eight (`meset.f` STAEND: an hour after each
date; `MeteorologyPathway.start_hour`/`.end_hour`), which EPA's
five-year PM10 chain uses. Tranche 4: `DAYRANGE` fields are kept as
written in `.day_ranges` and accumulate over cards (DAYRNG's four forms
-- a Julian day, a Julian range, a month/day, a month/day range -- are
what the validator accepts; E154 under SCIM); `NUMYEARS n` (`.num_years`,
NUMYR: one integer, E202 for two); `WINDCATS u1..u5`
(`.wind_speed_categories`, WSCATS: exactly five increasing values in
1-20 m/s, any other count is E200, probe 26b); `SCIMBYHR` (`.scim`,
`ScimOptions`, SCIMIT's 4-, 6- and 8-field forms, a six-field card
holding the obsolete wet-SCIM pair when numeric and the two summary
files otherwise; dispatched only under MODELOPT SCIM, which is
non-DFAULT); one turbulence keyword (`.turbulence_option`; a second is
E135 and is kept verbatim). STARTEND and DAYRANGE are dispatched only
when the run is not an EVENT run (`.NOT.EVONLY`) and the writer leaves
them off an event deck.

**OU (16):** DAYTABLE, EVALFILE, EVENTOUT, FILEFORM, MAXDAILY, MAXDCONT,
MAXIFILE, MAXTABLE, MXDYBYYR, NOHEADER, PLOTFILE (ALL and per-group),
POSTFILE, RANKFILE, RECTABLE (numeric and `FIRST-THIRD` style ranks),
SEASONHR, SUMMFILE, TOXXFILE.
Tranche 4: `NOHEADER ALL|types...` (`OutputPathway.no_header`; one to
eight of MAXIFILE, POSTFILE, PLOTFILE, SEASONHR, RANKFILE, MAXDAILY,
MXDYBYYR, MAXDCONT, each of which must be in use, E164 at OUTQA, probe
28b); `RANKFILE aveper rank filnam [funit]` (`.rank_files`, `RankFile`;
one per period, E211); `SEASONHR grpid filnam [funit]`
(`.season_hour_files`, `SeasonHourFile`; one per group, E154 under
SCIM); `EVALFILE srcid filnam [funit]` (`.eval_files`, `EvalFile`; needs
EVALCART receptors, E256, probe 28c); `TOXXFILE aveper thresh filnam
[funit]` (`.toxx_files`, `ToxxFile`; an unformatted file, W296 for any
period but 1 hour); `EVENTOUT SOCONT|DETAIL` (`.event_output`), the one
OU keyword besides FILEFORM that an EVENT deck may carry (evset.f
EV_OUCARD; a RECTABLE there is E110). `RankFile.read()`,
`SeasonHourFile.read()` and `ToxxFile.read()` hand the file to
`pyaermod.aermod_outputs.read_rankfile` / `read_seasonhr` /
`read_toxxfile`.
Field layouts, from `ouset.f`: `MAXIFILE aveper grpid thresh filnam
[funit]` (OUMXFL, fields 3-6 with an optional unit in 7; fewer is E201,
so there is no filename-only form; `OutputPathway.maxi_files`, a
`MaxiFile` per line); a PLOTFILE whose rank is not the highest value or
that carries a unit, and every POSTFILE after the first, have no place on
the model and travel in `unparsed_lines`; `MAXDAILY grpid filnam [funit]` and
`MXDYBYYR grpid filnam [funit]` (no averaging-period field; the period is
implied by the NAAQS processing, and AERMOD rejects both unless
NO2AVE/SO2AVE/PM25AVE is active, E162/E163); `MAXDCONT grpid upper lower
filnam [funit]` or `MAXDCONT grpid upper THRESH thresh filnam [funit]`,
incompatible with SAVEFILE/INITFILE/MULTYEAR (E153); `FILEFORM FIX|EXP`.
The MAXDAILY and MXDYBYYR files are read by
`pyaermod.design_values.read_maxdaily` / `read_mxdybyyr`.

**EV (5):** EVENTLOC, EVENTOUT, EVENTPER, FILEFORM, INCLUDED. An EV
pathway makes the deck an EVENT run (aermod.f PRESET sets EVONLY), whose
pathways are CO, SO, ME, EV and OU in that order: no RE, and the EV block
must precede OU because PRESET stops reading at `OU FINISHED` (probe 30).
`AERMODProject.event_processing` records it and the writer produces that
layout, leaving off the CO and ME keywords coset.f/meset.f dispatch only
under `.NOT.EVONLY` (EVENTFIL, SAVEFILE, INITFILE, MULTYEAR, STARTEND,
DAYRANGE). Field layouts, from `evset.f` and the deck AERMOD writes
itself (output.f MXEVNT, probe 29b): `EVENTPER evname aveper grpid date
conc` (EVPER: exactly five fields, the period on AVERTIME and at most 24
hours E297, the group defined, the date YYMMDDHH of the period's last
hour, the concentration of the main run; `EventPeriod`); `EVENTLOC
evname XR= x YR= y zelev [zhill [zflag]]` or `RNG= r DIR= d ...`
(EVLOC: eight to ten fields on the card, so the elevation is not
optional -- E201 without it, probe 30; `EventLocation`); every event
needs one (E130). Event names are ten characters (`EVNAME*10`; AERMOD's
own are `H001H01001`). INCLUDED in EV is kept verbatim like the SO and
RE ones. EVENTOUT and FILEFORM are dispatched by `evset.f` EV_OUCARD in
the OU pathway of the event deck and are counted there as well.

## Handled + untested

None remaining after this audit. Before it, `STARTEND`, `RECTABLE` and
`MAXTABLE` were handled without a dedicated reader test, and roughly
forty single-line branches (MODELOPT deposition flags, `FLATSRCS`,
`DCAYCOEF`, CO `ELEVUNIT`, file-form `O3VALUES`, non-enum `POLLUTID`,
every malformed-line guard in the SO parser, the source-construction
guards, the explicit-direction `GDIR` forms, short RE lines, `WDROTATE`,
`MAXIFILE`, and the sandbox chemistry/per-group-plotfile checks) were
uncovered.

## Stored only, by design

No keyword is unhandled. These are the lines that still travel in
`AERMODProject.unparsed_lines`, each a decision rather than a gap. They
are read, reported, written back in their pathway where AERMOD accepts
them, and the round-trip and acceptance suites cover them; what they do
not get is a field on the model, for the reason given.

**Whole keywords (11).**
`ERRORFIL`, `DEBUGOPT` (CO): file names and debug switches for AERMOD's
own diagnostics; they change no result, and modelling them would invite
callers to set them where the runner already manages the run directory.
`NO2EQUIL` (CO): the equilibrium NO2/NOx ratio of the OLM/PVMRM options,
one number AERMOD defaults to 0.90; kept verbatim until a caller needs it
(the validator's chemistry checks do not depend on it).
`EMISFACT`, `HOUREMIS` (SO): variable emissions. EMISFACT carries up to
2016 values per source in twelve flag layouts (the same table as
O3VALUES, `TEMPORAL_FLAG_COUNTS`) and HOUREMIS names a file whose record
layout varies by source type; both are pure data the model would only
copy, and EPA's hrdow (33 EMISFACT lines) and mcr (HOUREMIS) decks reach
parity with the lines carried verbatim.
`INCLUDED` (SO, RE, EV): a file of more cards. Reading it would mean
resolving a path at parse time; the writer keeps the card and AERMOD
reads the file where it always did (EPA's lovett, flatelev and multurb
decks).
`BACKUNIT` (SO): the unit of the BACKGRND values, one of PPB, PPM,
UG/M3; `BackgroundConcentration` holds no unit field, and the values are
written back unchanged beside the card.
`ELEVUNIT` (SO): the unit of the source elevations, which AERMOD
requires as the first SO card (E152) and the writer places there.
`EVALCART` (RE): model-evaluation receptor arcs (six fields, EVCART),
used by EVALFILE; 360 lines in EPA's allsrcs deck, no result depends on
them beyond the EVALFILE output itself.
`DISCPOLR` (RE): discrete polar receptors relative to a source;
`DiscreteReceptor` is Cartesian and a conversion would move the receptor
by AERMOD's own rounding.
`SITEDATA` (ME): the on-site station ID and year, which AERMOD reads and
prints but does not use (the surface file carries the data).

**Forms of handled keywords.** A BACKGRND hourly file, a PLOTFILE whose
rank is not the highest value or that carries a unit, every POSTFILE
after the first, a bare EVENTFIL (AERMOD's EVENTS.INP), a second
turbulence keyword (E135), an EVENTLOC for an event the deck does not
define, and any card with a field count its routine rejects (a MAXIFILE
short of its file name, a WINDCATS with four values, a SWPOINT SRCPARAM
with five). Each is kept so the deck AERMOD sees is the deck that was
read; the validator, not the writer, is where the fatal ones are named.

**Token lists kept as written.** `DAYRANGE` fields,
`SourcePathway.aircraft_sources` and `.hbp_sources`, and the option lists
of `AWMADWNW`, `ORD_DWNW` and `NOHEADER` are stored as the tokens AERMOD
reads (IDs, ranges, `ALL`, option names) rather than resolved against the
sources or expanded into flags. AERMOD resolves them itself at setup, the
validator checks the vocabulary and the cross-keyword rules, and a
resolved form would not survive a rewrite of a deck whose sources live in
an INCLUDED file.

## Round-trip guarantee

Two suites hold the guarantee, both over every deck in the v26135
archive when it is unpacked under `test_cases/` and over eleven vendored
decks otherwise:

- `tests/test_epa_deck_roundtrip.py` parses each deck, writes it, parses
  the result, and requires the CO, RE, ME and OU pathways equal field for
  field, the SO group definitions and source IDs equal, the preserved
  lines equal as (pathway, keyword, fields), the lines of the
  token-compared keywords (the tranche-1 set plus MAXIFILE, URBANOPT,
  STARTEND) equal as multisets, and every line of the original deck to be
  either a modelled keyword or present in `unparsed_lines`. 53 of 53
  decks pass.
- `tests/test_epa_deck_acceptance.py` runs the deck pyaermod writes for
  each EPA case through AERMOD's setup pass (`RUNORNOT NOT`) in a copy of
  EPA's `inputs/` tree, next to EPA's original, and requires the same
  fatal-error set. 49 decks are accepted clean. The other four
  (`testpm10_1987` to `_1990`) are the chained MULTYEAR years, whose
  MULTYEAR line names the previous year's save file; without a full run
  of the year before, EPA's own deck reports CO E500 and so does ours.
  The writer forms this tranche changed (polar and Cartesian grids,
  MAXIFILE, URBANOPT, `ELEV`, STARTEND with hours, and the placement of
  preserved lines) have setup-pass cases of their own in the same file.

The first sweep of that acceptance test, before the fixes, is worth
recording as the reason the guarantee needs the binary: 28 of 53 written
decks were rejected. SO E152 on 25 (a preserved ELEVUNIT was not first),
RE E185 on every polar grid (below), CO E203 for `ELEVATED`, CO E600 for
NO2STACK under ARM2, CO E208 for one URBANOPT card written in the
several-card layout, E105 for preserved lines whose short keyword was
not padded to eight columns (`XBADJ  STACK1` reads as keyword `XBADJ  S`),
E310 for a source defined in an INCLUDED file and re-defined at the
origin from its inline SRCPARAM, OU E203 for PLOTFILE lines whose ranks
had all become FIRST, and ME E203 for a STARTEND whose hours were read as
the end date. Every one is now pinned by a test that fails without its
fix.

Tranche 4 adds three suites to the guarantee: every writer form it
introduced has a setup-pass case in `tests/test_epa_deck_acceptance.py`
(the event layout with SOCONT and DETAIL/EXP, the four ME forms and the
three SCIMBYHR forms, NOHEADER and the four OU files, EVALFILE with an
EVALCART arc carried in `unparsed_lines`, METHOD_2 for a source and a
range, PLATFORM, the three point types, ARMRATIO, AWMADWNW with ORD_DWNW,
HBPSRCID, ARCFTSRC with an aircraft HOUREMIS file, and EPA's capped and
AERMOD's generated event deck rewritten);
`tests/regulatory/test_epa_rewritten_so.py` fully rewrites the ten EPA
decks whose answer depends on a tranche-4 keyword (testpart, testprt2,
openpits, capped, the two ARM2 decks, flatelev, lovett, mcr, hrdow) and
scores every POSTFILE against EPA's reference, all at slope 1.000000;
and `tests/regulatory/test_event_rewrite.py` runs the event deck AERMOD
wrote for probe 29 and pyaermod's rewrite of it and requires every
group value and source contribution to agree, which they do.

Probe decks 20-30 record the tranche-4 verdicts: 20 the METHOD line the
old writer emitted (E105), 21/21b METHOD_2 with and without DFAULT, 22
PLATFORM, 23/23b the three point types with and without ALPHA, 24-24e
ARMRATIO and the AWMA/ORD option sets, 25-25c HBPSRCID and ARCFTSRC
(E833 on a POINT source, E823 without HOUREMIS), 26/26b the ME keywords
and the counts meset.f rejects, 27-27c the SCIMBYHR forms, 28-28c the OU
files (E256 without EVALCART, E164 for an unused NOHEADER type), 29/29b
the main run that made AERMOD write an event deck and that deck itself,
30 the EVENTLOC field counts and the EV-before-OU rule.

Probe decks 13-19 under `scripts/oracle_decks/` record what AERMOD said
about the forms in question: 13 is the polar block pyaermod wrote before
this tranche (E185, no receptors: GENPOL read `GDIR 0.0 36 10.0` as zero
directions, POLDST read `DIST 100 10 100` as three rings), 14 the forms
`reset.f` parses (120 receptors), 15 GRIDCART with XPNTS/YPNTS on
continuation lines (16), 16 a filename-only MAXIFILE (E201), 17 the
four-field MAXIFILE with a unit (accepted), 18 blank-keyword continuation
lines with and without the network ID (60 receptors), 19 a keyword
starting in column 2 (E100: columns 1-2 are the pathway field).

## Discrepancies and follow-ups

1. **`MAXIFILE` argument order.** Resolved. `OutputPathway.maxi_files`
   holds `MaxiFile(averaging_period, source_group, threshold, filename,
   file_unit)` in the layout `ouset.f` OUMXFL reads; the reader and the
   writer agree, `tests/test_epa_deck_acceptance.py` runs the writer's
   line through AERMOD, and EPA's `testpm10.inp`/`testpm25.inp` lines
   round-trip token for token. `OutputPathway.max_file` is removed: the
   one-field line it wrote was E201 in every AERMOD release (probe 16).
2. **RLINEXT / AREAPOLY / BUOYLINE** — closed by tranche 2, and the
   remainder (POINTCAP, POINTHOR, SWPOINT) by tranche 4. All three are
   constructed from their multi-line companions and written back;
   `tests/regulatory/test_epa_rewritten_so.py` shows EPA's `allsrcs`,
   `blp_urban`, the three `aermod-baldwin*` and the four RLINEXT `Test*`
   decks at slope 1.000000 with pyaermod's SO pathway, and `capped.inp`
   fully rewritten (POINTCAP and POINTHOR constructed, the 0.001 m/s exit
   velocities kept) at slope 1.000000 on all nine of its POSTFILEs. A
   source of a type AERMOD does not know still keeps its definition lines
   verbatim, as does an incomplete definition.
3. **`GRIDPOLR DIST/GDIR` heuristics.** Resolved; there is no heuristic.
   `reset.f` never has an init/num/delta form for DIST (POLDST reads a
   list) and GDIR is always the three fields `num init delta` (GENPOL);
   explicit directions are DDIR. The reader mirrors that, `PolarGrid`
   carries `distances`/`directions` beside the generator fields, and the
   writer emits the list and `GDIR num init delta`. This also fixed the
   writer: the `DIST init num delta` / `GDIR init num delta` block every
   earlier release wrote produced a network with no receptors (RE E185,
   probe 13).
4. **No unknown-keyword report.** Resolved as the module docstring
   promised: `AERMODProject.unparsed_lines` (see "Round-trip guarantee"
   and `pyaermod.unparsed`). Re-emission is on by default
   (`to_aermod_input(preserve_unparsed=True)`): the lines were part of
   the deck, and dropping them was the bug. Placement follows what
   `soset.f`/`reset.f` enforce -- ELEVUNIT first in its pathway, SO lines
   before SRCGROUP/OLMGROUP/PSDGROUP, everything else before FINISHED --
   and a keyword shorter than eight characters is padded so the data
   starts in column 13. When WP-2 gives a keyword a field, its lines stop
   appearing here without any further change.
5. **Pass-through tests pin behaviour, not support.** Resolved for this
   tranche's keywords: MAXIFILE, the GRIDPOLR/GRIDCART forms, URBANOPT,
   STARTEND, RUNORNOT and EVENTFIL have structural assertions in
   `tests/test_reader_roundtrip_fidelity.py`; the remaining
   `test_unhandled_*_keywords_pass_through` entries (the SO keywords, the
   CO/ME/OU keywords in "Unhandled" above) now also imply the line is in
   `unparsed_lines`, which `unaccounted_lines()` checks over the archive.
   Replace an entry with a structural assertion when its keyword gains a
   field.
6. **Ozone writer forms.** Documented design decision, fixed in tranche 1:
   OZONEFIL, OZONEVAL, `OZONEVAL SECTn` and NOX_FILE are the only spellings
   the writer emits; the two legacy `O3VALUES` spellings (`O3VALUES
   <file>`, `O3VALUES UNIFORM v`) stay readable so decks written by
   pyaermod < 2.1 open, and are written back in the correct form.
7. **`GasDepositionParams` field semantics** — closed by tranche 2. The
   dataclass is now `diffusivity`, `diffusivity_water`,
   `cuticular_resistance`, `henry_constant` (`GASDEPOS srcid Da Dw rcl
   Henry`, all required), the validator applies `soset.f` GASDEP's rules
   (positive, 0 only for the six pollutants with built-in values, ALPHA
   required, GASDEPVD excluded), and EPA's `testgas` values validate and
   are written back unchanged (`tests/test_so_deck_acceptance.py`
   `gasdepos-epa-testgas`).
8. **Rewriting whole EPA decks** -- closed by tranche 3 for the receptor
   and output forms it named: `GRIDPOLR DIST` lists and `ORIG` by source
   ID are modelled (item 3), two-field `DISCCART` lines are read as the
   FLAT form, and further `POSTFILE` lines are kept verbatim. All 53
   rewritten decks now pass AERMOD's setup pass ("Round-trip guarantee"
   above). A multi-rank `RECTABLE` still collapses to one `ALLAVE` line
   at the highest rank, which changes the tables printed, not the run.
9. **Urban areas** -- closed by tranche 3: `ControlPathway.urban_areas`
   keeps every `URBANOPT` card in the layout `coset.f` reads for the
   number of cards; EPA's `multurb` deck round-trips all four areas and
   passes the setup pass.

Found by the acceptance sweep and fixed here rather than listed, because
each made a written deck fatal: `ELEVATED` as a MODELOPT token, NO2STACK
under ARM2, a single name-first URBANOPT, GRIDCART XPNTS/YPNTS read as
the default grid, STARTEND with hours, sources defined in INCLUDED files
re-defined from their inline SRCPARAM, and `SRCGROUP ALL` invented for a
PSDCREDIT deck (`SourcePathway.include_all_group`).

10. **Scalar building-downwash values.** Found by the tranche-4 POINTCAP
   acceptance case and left as is: a `PointSource` whose
   `building_height` is a single float writes one BUILDHGT value, and
   AERMOD wants 36 (E236). The reader always produces 36-value lists, so
   no rewritten deck is affected; a project built in Python with scalar
   downwash values has been fatal since the field existed and needs a
   writer change (repeat the value 36 times) that belongs with a look at
   `apply_bpip_to_project`, which fills the lists.
11. **`deposition_method`** is kept on every source for compatibility but
   writes nothing: the `METHOD srcid option value` line it produced was
   never an AERMOD keyword (E105, probe 20) and `chemistry_presets`
   assigns it an enum the writer could not even unpack. Method 2 particle
   deposition is `method_2`; a later release can remove the old field.

Still lossy on rewrite, by design of the model rather than the reader,
and not fatal: several RECTABLE lines with different periods collapse to
one `ALLAVE` line at the highest rank; SURFDATA/UAIRDATA drop the station
name; `DiscreteReceptor` always writes an elevation, which is W229 in a
FLAT run.

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
Latin-1).

**Validator.** `src/pyaermod/validator.py` validates the object model
(`AERMODProject` dataclasses), not keyword text, so unhandled keywords never
reach it. Its OPENPIT, Method 1 particle and DFAULT-with-FLAT rules follow
v26135's own checks and carry AERMOD's message codes; each is checked against
a real run in `tests/fixtures/validator_openpit/`
(`tests/test_validator_openpit_method1.py`). [Common errors](common-errors.md)
describes them.

## Summary

| Pathway | v26135 keywords | Handled + tested | Handled + untested | Unhandled |
|---|---:|---:|---:|---:|
| CO | 37 | 37 | 0 | 0 |
| SO | 36 | 36 | 0 | 0 |
| RE | 7 | 7 | 0 | 0 |
| ME | 14 | 14 | 0 | 0 |
| OU | 16 | 16 | 0 | 0 |
| EV | 5 | 5 | 0 | 0 |

Every one of the 115 dispatched keywords is recognised and tested. 105
have a field on the model; the ten that are "handled" without one
(ERRORFIL, NO2EQUIL, EMISFACT, HOUREMIS, INCLUDED, BACKUNIT,
SO ELEVUNIT, EVALCART, DISCPOLR, SITEDATA) are stored verbatim by
decision, each with its reason in "Stored only, by design" below.

(`STARTING`/`FINISHED` are structural and excluded from the counts.)

## Handled + tested

**CO (37):** ARCFTOPT, ARMRATIO, AVERTIME, AWMADWNW, DCAYCOEF, DEBUGOPT,
ERRORFIL, EVENTFIL, FLAGPOLE, GASDEPDF, GASDEPVD, GDLANUSE, GDSEASON,
HALFLIFE, INITFILE, LOW_WIND, MODELOPT, MULTYEAR, NO2EQUIL, NO2STACK,
NOXSECTR, NOXVALUE, NOX_FILE, NOX_UNIT, NOX_VALS, O3SECTOR, O3VALUES,
ORD_DWNW, OZONEFIL, OZONEVAL, OZONUNIT, POLLUTID, RUNORNOT, SAVEFILE,
TITLEONE, TITLETWO, URBANOPT.
Of these, ERRORFIL and NO2EQUIL have no field and travel in
`unparsed_lines` (see "Stored only, by design"); DEBUGOPT
(`ControlPathway.debug_options`, the fields as written: options and the
file names after them, which keep their case; coset.f DEBOPT pools the
fields of repeated cards and checks DEPOS against MODELOPT, so the writer
puts the line after MODELOPT, and one card takes at most 11 fields,
E202, so a longer list goes on several cards split between options;
v24142 takes one card only, E135), RUNORNOT
(`ControlPathway.run_model`), EVENTFIL (`.eventfil` and
`.eventfil_option`, coset.f EVNTFL: `evfile [SOCONT|DETAIL]`; the bare
form, AERMOD's EVENTS.INP with W207, is kept verbatim) and URBANOPT are
stored. `ARMRATIO min max` (`.arm2_ratios`; ARM2_Ratios wants
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
DFAULT, ALPHA, BETA, PSDCREDIT (`ControlPathway.alpha` /
`.beta` / `.psd_credit`), OLM, PVMRM, ARM2, GRSM, TTRM, TTRM2, and the
depletion switches DRYDPLT / NODRYDPLT and WETDPLT / NOWETDPLT
(`.dry_depletion` / `.wet_depletion`: True, False, or None for AERMOD's
default, depletion on whenever the run has deposition inputs; a token
contradicting an earlier one, E149, is kept in `extra_model_options` so
the rewrite fails the same way). Terrain follows
`coset.f` MODOPT: `ELEV` is the token (the writer used to emit
`ELEVATED`, which is E203), `FLAT` then `ELEV` on one line means flat
sources in elevated terrain (`TerrainType.FLATSRCS`, which has no token
of its own and is written as that pair; `ELEV FLAT` in the other order
means the same). A MODELOPT with no terrain token runs with ELEV
(MODOPT leaves ELEV only for FLAT), so the reader reads it as
`TerrainType.ELEVATED`. With `DFAULT`, AERMOD sets ELEV, drops any `FLAT` with
W206 and runs in elevated terrain, so the validator warns when
`regulatory_default=True` meets `FLAT` or `FLATSRCS`. Every other option token (FASTALL, SCREEN, TOXICS,
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
field (`flat_source`) is kept and written back. Further keywords:
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
runs (a third field is W229 there), `x y zflag` in FLAT runs with CO
FLAGPOLE, and `x y zelev zhill [zflag]` under elevated terrain (a missing
hill height is W228); reset.f DISCAR decides by the run's options, and so
do the reader and the writer (`ControlPathway.elevated_terrain`,
`.flag_pole_height`). A bare `FLAGPOLE` still switches flagpole receptors
on (coset.f FLAGDF, height 0, W205) and is read as `flag_pole_height=0.0`.
Under elevated terrain a Cartesian grid without ELEV and HILL rows is
W214, so the writer fills both from `CartesianGrid.z_elev` / `.z_hill`;
a grid given only one set is written as given and stays E218. A row of
one value is written as `N*value`, which STODBL reads as N copies, in
plain fixed-point: STODBL reads an exponent only after a decimal point
(`3*1e-05` is E208).

**ME (14):** DAYRANGE, NUMYEARS, PROFBASE, PROFFILE, SCIMBYHR, SITEDATA,
STARTEND, SURFDATA, SURFFILE, UAIRDATA, WDROTATE, WINDCATS, and the nine
turbulence keywords NOTURB, NOTURBST, NOTURBCO, NOSA, NOSW, NOSAST,
NOSWST, NOSACO, NOSWCO, which `meset.f` dispatches together (one
`KEYWRD .EQ.` chain, one status switch) and which count as one keyword
in the table. SITEDATA has no field and travels in `unparsed_lines`.
STARTEND takes six fields or eight (`meset.f` STAEND: an hour after each
date; `MeteorologyPathway.start_hour`/`.end_hour`), which EPA's
five-year PM10 chain uses. `DAYRANGE` fields are kept as
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
`NOHEADER ALL|types...` (`OutputPathway.no_header`; one to
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

## Stored only, by design

No keyword is unhandled. These are the lines that still travel in
`AERMODProject.unparsed_lines`, each a decision rather than a gap. They
are read, reported, written back in their pathway where AERMOD accepts
them, and the round-trip and acceptance suites cover them; what they do
not get is a field on the model, for the reason given.

**Whole keywords (10).**
`ERRORFIL` (CO): the file name of AERMOD's message file; it changes no
result, and modelling it would invite callers to set it where the runner
already manages the run directory. (`DEBUGOPT` was stored this way
until a caller needed AREA and DEPOS debug output; it is
now `ControlPathway.debug_options`.)
`NO2EQUIL` (CO): the equilibrium NO2/NOx ratio of the OLM/PVMRM options,
one number AERMOD defaults to 0.90; kept verbatim until a caller needs it
(the validator's chemistry checks do not depend on it).
`EMISFACT`, `HOUREMIS` (SO): variable emissions. EMISFACT carries up to
2016 values per source in twelve flag layouts (the same table as
O3VALUES, `TEMPORAL_FLAG_COUNTS`) and HOUREMIS names a file whose record
layout varies by source type; both are pure data the model would only
copy, and EPA's hrdow (33 EMISFACT lines) and mcr (HOUREMIS) decks reach
parity with the lines carried verbatim. The writer can also generate a
HOUREMIS card and its rate-only file for AREA, AREACIRC, AREAPOLY,
OPENPIT, VOLUME, LINE, RLINE and RLINEXT sources
(`SourcePathway.hourly_emissions`,
`pyaermod.hourly_emissions`); a deck that is read keeps its card verbatim.
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

**Forms of handled keywords.** A BACKGRND hourly file (and, when a
sector has one, every BGSECTOR and BACKGRND line), a PLOTFILE whose
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
  token-compared keywords (the restart and multi-year, NOx-background, OU design-value and
  gas-deposition keywords, plus MAXIFILE, URBANOPT, STARTEND) equal as multisets, and every line of the original deck to be
  either a modelled keyword or present in `unparsed_lines`. 53 of 53
  decks pass.
- `tests/test_epa_deck_acceptance.py` runs the deck pyaermod writes for
  each EPA case through AERMOD's setup pass (`RUNORNOT NOT`) in a copy of
  EPA's `inputs/` tree, next to EPA's original, and requires the same
  fatal-error set. 49 decks are accepted clean. The other four
  (`testpm10_1987` to `_1990`) are the chained MULTYEAR years, whose
  MULTYEAR line names the previous year's save file; without a full run
  of the year before, EPA's own deck reports CO E500 and so does ours.
  The polar and Cartesian grid, MAXIFILE, URBANOPT, `ELEV`, STARTEND-with-hours
  and preserved-line writer forms have setup-pass cases of their own in the
  same file.

Probe decks under `scripts/oracle_decks/` record what AERMOD said about the
forms in question.

## Known limits

- Several `RECTABLE` lines with different periods collapse to one `ALLAVE`
  line at the highest rank on rewrite. This changes the tables printed, not
  the run.
- `SURFDATA` and `UAIRDATA` drop the station name on rewrite.
- `DiscreteReceptor` always writes an elevation, which is W229 in a FLAT run.
- `deposition_method` is kept on every source for compatibility but writes
  nothing: the `METHOD srcid option value` line it produced was never an
  AERMOD keyword (E105). Method 2 particle deposition is `method_2`.

# EPA official AERMOD test cases

Selected files from EPA's official **AERMOD Test Cases** archive, used
as regression fixtures to ensure pyaermod stays compatible with the
real-world AERMOD reference.

## Files checked in

Source archive:
<https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_test_cases.zip>
(EPA release of 2026-07-09, ~489 MB), reference set
`aermet26135_aermod26135` unless noted. Vendored 2026-08-22.

| File | Source | Purpose |
|---|---|---|
| `aertest.inp` | `aermet26135_aermod26135/inputs/aertest.inp` | Canonical "simple point source with PRIME downwash" example. Differs from the 24142 copy only in whitespace and the lower-case met filenames (`aermet2.sfc`). |
| `AERMET2.SFC` / `AERMET2.PFL` | `aermet26135_aermod26135/meteorology/aermet2.{sfc,pfl}` (renamed to upper case) | Meteorology for AERTEST, produced by AERMET v26135. Values identical to the 24142 files; v26135 writes four-digit years (`1988` vs `88`). |
| `AERTEST_01H.PLT` | `aermet26135_aermod26135/plotfiles/AERTEST_01H.PLT` | 1-hour HIGH-1ST PLOTFILE produced by AERMOD v26135. Data rows are byte-identical to the 24142 plotfile; only the two banner lines (version, date) differ. |
| `AERTEST.SUM` | `aermet_24142_aermod_24142/Outputs/AERTEST.SUM` | AERMOD **24142** summary output for AERTEST. Kept at 24142 deliberately: the 26135 summary echoes the four-digit-year met through a two-character field (`**` in the year column), and `tests/test_cli.py` asserts the 24142 banner. |
| `bg_no2_olm_ppb.inp` | `aermet26135_aermod26135/inputs/` | OLM with an hourly background file and `BACKUNIT PPB`. |
| `testpm10_1986.inp`, `testpm10_1987.inp` | `aermet26135_aermod26135/inputs/` | First two years of the five-year `MULTYEAR` PM10 chain (the first year has no init file, the second names the first's save file). |
| `no2_1yrAK_grsm.inp` | `aermet26135_aermod26135/inputs/` | GRSM: `NOXVALUE 10.0 PPB`, `OZONEVAL`/`OZONEFIL` with units and a Fortran read format, `MAXDCONT ALL 8 8`. |
| `testgas2.inp` | `aermet26135_aermod26135/inputs/` | Gas deposition: `GDSEASON` and `GDLANUSE 36*4`. |
| `testprt2.inp` | `aermet26135_aermod26135/inputs/` | `FILEFORM EXP` among the plot/post files. |
| `allsrcs.inp` | `aermet26135_aermod26135/inputs/` | GRIDCART with explicit `XPNTS`/`YPNTS`, DISCPOLR and EVALCART; one source of every type: AREAPOLY with a two-line `AREAVERT` ring and the fourth `SRCPARAM` field, three BUOYLINE segments under an eight-field `BLPINPUT` (no group ID, no BLPGROUP), RLINEXT with `RBARRIER` and `RDEPRESS`, `LINE` with `szinit`, and continuation `SRCGROUP` lines. |
| `blp_urban.inp` | `aermet26135_aermod26135/inputs/` | Two buoyant-line groups: nine-field `BLPINPUT` per group, `BLPGROUP`, single-area `URBANOPT` / `URBANSRC`. |
| `olmgrp.inp` | `aermet26135_aermod26135/inputs/` | `OLMGROUP ALL`. |
| `psdcred.inp` | `aermet26135_aermod26135/inputs/` | `PSDCREDIT` with the three `PSDGROUP` IDs and no SRCGROUP (the writer must not invent one). |
| `Test3_Base_cart_3cond_SNC_bar.inp`, `Test4_Base_cart_3cond_SNC_dep.inp` | `aermet26135_aermod26135/inputs/` | RLINEXT with the eleven-field LOCATION (base elevation), `RBARRIER` and `RDEPRESS`. |
| `testgas.inp` | `aermet26135_aermod26135/inputs/` | `GASDEPOS 0.08962 1.04E-5 2.51E4 557.0` (Da Dw rcl Henry) and `DEPOUNIT`. |
| `hrdow.inp` | `aermet26135_aermod26135/inputs/` | GRIDPOLR written with blank keyword columns (`POL1 GDIR 18 10. 20.`), 33 EMISFACT lines, six SEASONHR and six POSTFILE lines. |
| `testpm25.inp` | `aermet26135_aermod26135/inputs/` | `MAXIFILE 24 ALL 35.0 <file>`, the four-field layout. |
| `capped.inp` | `aermet26135_aermod26135/inputs/` | POINTCAP and POINTHOR sources with full downwash arrays (`PointCapSource`, `PointHorSource`), and stacks with an exit velocity of 0.001 m/s that the fixed-column SRCPARAM writer used to round to 0.00. |
| `multurb.inp` | `aermet26135_aermod26135/inputs/` | Four URBANOPT areas (ID-first layout) with the sources and polar grid in INCLUDED files (not vendored). |
| `flatelev.inp` | `aermet26135_aermod26135/inputs/` | A `RANKFILE` per short-term period and a `LOCATION ... FLAT` source beside an elevated one under `MODELOPT FLAT ELEV`; receptors in an INCLUDED file (not vendored). |
| `scimtest.inp` | `aermet26135_aermod26135/inputs/` | `MODELOPT SCIM` with the eight-field `SCIMBYHR` (wet-SCIM fields and the two summary files). |
| `no2_1yrAK_arm2.inp` | `aermet26135_aermod26135/inputs/` | `ARMRATIO 0.5 0.9` under ARM2. |
| `events_generated.inp` | written by AERMOD v26135 for `scripts/oracle_decks/29_event_main.inp` | The event deck AERMOD itself writes for a main run with `EVENTFIL ... SOCONT`: CO, SO and ME copied from the main deck, the EV pathway before OU, an OU pathway of `EVENTOUT` only. Not an archive deck (the archive has no EVENT case); it is the layout reference for `EventPathway` and the fixture for `tests/regulatory/test_event_rewrite.py`, which runs it against the vendored meteorology. |

The decks from `bg_no2_olm_ppb.inp` down are the round-trip fixtures for
`tests/test_epa_deck_roundtrip.py`; together they use every form of the
restart, NOx/ozone background, gas-deposition, design-value, MAXIFILE,
URBANOPT, RANKFILE, SEASONHR, SCIMBYHR, ARMRATIO, METHOD_2 and EV keywords
that appears anywhere in the 53-deck archive (or, for the EV pathway, in
the deck AERMOD generates), and the runstream forms (blank-keyword
continuation lines, explicit grid lists) the RE parser was rewritten for. `allsrcs`, `blp_urban`, `olmgrp`,
`psdcred`, the two `Test*` decks, `testgas`, `testgas2`, `capped` and
`testprt2` are also the fixtures for `tests/test_epa_source_roundtrip.py`,
and carry every source-construction keyword the archive uses (AREAVERT,
BLPINPUT, BLPGROUP, OLMGROUP, PSDGROUP, DEPOUNIT, RBARRIER, RDEPRESS,
GASDEPOS, URBANSRC, METHOD_2, POINTCAP and POINTHOR); NO2RATIO, EMISUNIT,
CONCUNIT, SBARRIER, VBARRIER, RLEMCONV, PLATFORM, ARCFTSRC, HBPSRCID and
SWPOINT appear in no EPA deck and are covered by the acceptance tests
instead.
The decks' trailing blanks are part of the fixture: the pre-commit
whitespace hooks skip `tests/fixtures/`.

All files are products of U.S. EPA and are in the public domain.

## What the fixtures prove

`tests/test_real_aermod.py` runs `aertest.inp` through a real AERMOD
binary and compares every receptor against `AERTEST_01H.PLT`. With a
gfortran -O2 build of AERMOD v26135 all 144 receptors match bit-for-bit.
Refreshing this plotfile to 26135 changed only its two banner lines — the
data rows a 24142 build would be checked against are byte-identical — but
a 24142 build has not been re-run against it. See
`src/pyaermod/versions.py` for what "validated" means project-wide and
`docs/validation.md` for the full-suite parity report.

## Full archive

The full EPA test-case bundle (~489 MB zipped, ~10.6 GB unpacked) ships
three reference sets side by side:

| Set | Meteorology | Model |
|---|---|---|
| `aermet24142_aermod24142` | AERMET 24142 | AERMOD 24142 |
| `aermet24142_aermod26135` | AERMET 24142 | AERMOD 26135 |
| `aermet26135_aermod26135` | AERMET 26135 | AERMOD 26135 |

Each set has the same layout (`inputs/` 53 decks, `meteorology/`,
`postfiles/` 143 reference `.PST`, `plotfiles/`, `Outputs/`). Note the
naming changed from the pre-2026 bundle's `aermet_24142_aermod_24142`;
`pyaermod.epa_testcases.find_epa_testcase_set` accepts both spellings and
picks the set matching the AERMOD binary on PATH (or
`$PYAERMOD_EPA_TESTCASES`).

Unpack the archive under `<repo>/test_cases/` (gitignored) to enable
`tests/regulatory/`, `tests/test_epa_cases.py`, `tests/test_real_cases.py`
and `scripts/run_epa_parity.py`; the scheduled `epa_parity.yml` workflow
does this automatically. `download_all.py` fetches the same archive into
`tests/fixtures/epa_official/full/` for the regression tests in
`tests/test_regression_epa_official.py`.

## Versions

Fixtures in this directory track AERMOD v26135 / AERMET v26135
(`AERTEST.SUM` excepted, see above). When a new AERMOD release ships:

1. Unpack the new archive (see above) and diff each vendored file against
   the new set's copy; vendor the new copy only if the differences are
   provenance-only (banner, date, formatting) or you have re-verified the
   bit-exact AERTEST regression against a build of the new release.
2. Update `VALIDATED_AERMOD_VERSIONS` / `VALIDATED_AERMET_VERSIONS` in
   `src/pyaermod/versions.py` once the parity suite passes against the
   new release's reference set.
3. Run `pytest tests/test_real_aermod.py tests/test_regression_epa_official.py`
   and update any asserted values that shift.

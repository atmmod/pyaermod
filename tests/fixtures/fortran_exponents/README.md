# Recorded AERMOD runs with three-digit exponents

AERMOD writes its output files in exponential form when the deck says
`OU FILEFORM EXP`: the values are Fortran `E13.6` (`E14.6` in the
summary tables). When a value's decimal exponent needs three digits,
Fortran drops the letter E to make room, so 2.82465e-104 is printed as

    0.282465-103

These runs make AERMOD print such numbers, so that
`tests/test_fortran_exponents.py` can pin how every pyaermod reader of
AERMOD's numeric output reads them. None of the output files is
hand-edited.

- **Program:** AERMOD v26135, EPA's source archive `aermod_source.zip`
  (top-level directory `aermod_source_v26135`).
- **Build:** `scripts/build_aermod.sh` with GNU Fortran 15.2.0 (Homebrew
  GCC) and the script's default flags, `-O2 -fbounds-check
  -Wuninitialized`, on macOS arm64.
- **Recorded:** 2026-09-30.

## How the values get that small

The source is an open pit (1000 m by 1000 m, 10^8 m^3, 1e-5 g/s/m^2 of
6.055 um particles of density 2.65, the basis run of the demonstration
study's ensemble, where these numbers were first seen). At 20:00 on
21 May 1993 the Cordero surface file has 137.2 mm of precipitation with
an 11.4 m/s wind from 246 degrees. AERMOD's wet depletion
(`WETDPLT`, on by default when a source has particle inputs) removes
the plume as `exp(-Lambda x / u)`, so receptors 15 to 27 km downwind
get concentrations and deposition fluxes of 1e-103 to 1e-193. Receptors
at 2 and 6 km get ordinary small numbers (`0.568898E-13`,
`0.221944E-41`).

## Cases

Every case directory holds the deck (`aermod.inp`), the `aermod.out`
AERMOD wrote, its stdout (`stdout.txt`) and the output files the deck
names. Each run exited with code 0, finished with
`*** AERMOD Finishes Successfully ***` and wrote nothing to stderr.

| Case | Deck | Files with three-digit exponents |
|---|---|---|
| `washout/` | `MODELOPT CONC DEPOS DDEP WDEP ELEV DFAULT`, `AVERTIME 1 PERIOD`, seven receptors on a line 60 degrees from north, hours 19 to 21 | `post_1h.pst` (1-hour POSTFILE), `high_1h.plt` (PLOTFILE of first-highest 1-hour values) and `period.plt` (PERIOD PLOTFILE), all four value columns; the receptor tables and the summary tables of `aermod.out` (`3RD HIGHEST VALUE IS  0.260859-103 AT ...`). Hours 19 and 21 give zeros or ordinary values, so the files mix the two forms. |
| `washout_conc/` | The same source with `MODELOPT CONC ELEV DFAULT`, hour 20 only and only the five far receptors | With one output type AERMOD also writes the MAXIFILE (`maxi_1h.max`) and RANKFILE (`rank_1h.rnk`) in `E13.6`; with several (as in `washout/`) those two stay `F13.5`. The highest 1-hour value itself (`HIGH 1ST HIGH VALUE IS  0.782577-103 ON 93052120:`) has a three-digit exponent. |
| `events/` | An EVENT run (`EV` pathway, `EVENTOUT SOCONT`, `FILEFORM EXP`) with a second, smaller pit; events `NEAR` (1732.05, 1000.00) and `FAR` (12833.05, 7427.88), both for hour 20 | `aermod.out`: `*** GROUP VALUE =   0.282465-103 ***` and the source contributions `PIT 0.282465-103`, `PIT2 0.378148-112`. |

`FILEFORM EXP` has no effect on MAXDAILY, MXDYBYYR or MAXDCONT files
under `DFAULT` with a criteria pollutant (AERMOD resets it to FIX with
W595), and those files need a year of met, so they are not recorded
here. Without `DFAULT` the MAXDAILY format (`MXDFRM` in `ouset.f`) is
`E13.6` too.

## Met data

`CORDERO_1993-05-21.SFC` and `CORDERO_1993-05-21.PFL` are the header line
and the 24 records for 21 May 1993 of `cordero.sfc`, and the 24 records
for that day of `cordero.pfl`, byte for byte (CRLF line ends included).
Those files are the met data of EPA's AERMOD test cases for v26135
(`aermet26135_aermod26135/meteorology/` in `aermod_test_cases.zip`,
used by the `SURFCOAL` case). SHA-256 of the full files:

- `cordero.sfc`: `aaa6b1a1a03bbd8604b0476e3b906a8963b32692ea562ae8c1e1f47e575ae5b0`
- `cordero.pfl`: `f43a0deb5955a88564716c39a903fab6362e1aab78d84f18924c5ff4dab8234b`

## Regenerating

Build AERMOD with `scripts/build_aermod.sh`, then run

```bash
python tests/fixtures/fortran_exponents/regenerate.py bin/aermod
```

The script runs each deck in a scratch directory beside the met day and
copies back `aermod.out`, the output files the deck names and stdout.
Only the run date and time in the headers should change. With
`--cordero <dir of EPA's cordero.sfc and cordero.pfl>` it cuts the met
day again first. It fails if a run did not finish or if any recorded file
no longer holds a number with a three-digit exponent.

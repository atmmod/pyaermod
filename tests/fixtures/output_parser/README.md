# Recorded AERMOD runs for the output parser

These are five real AERMOD runs. `tests/test_output_parser_real_runs.py`
reads their `aermod.out` files to pin how `AERMODOutputParser` reads
AERMOD's summary tables. None of the output files is hand-edited.

- **Program:** AERMOD v26135, EPA's source archive `aermod_source.zip`
  (top-level directory `aermod_source_v26135`).
- **Build:** `scripts/build_aermod.sh` with GNU Fortran 15.2.0 (Homebrew
  GCC) and the script's default flags, `-O2 -fbounds-check
  -Wuninitialized`, on macOS arm64. The same binary reproduces the
  `albany_success` recording of `tests/fixtures/gui/aermod_recordings/`
  (a Linux gfortran 13.3 build) line for line, apart from the run date.
- **Recorded:** 2026-09-29; `ddep_only` again on 2026-09-30, with the
  same binary, when its deck gained the plot files; `so2_8th_only` on
  2026-09-30 with the same binary.

Every case directory holds the deck (`aermod.inp`), the `aermod.out`
AERMOD wrote and its stdout (`stdout.txt`), and `ddep_only/` its plot files. Each run exited with code 0,
finished with `*** AERMOD Finishes Successfully ***` and wrote nothing to
stderr. The source is the "Albany stack" of `PLAN-gui.md` (100 g/s from a
65 m stack at the origin); the met data are the Albany files of
`../epa_official/` (1 to 4 March 1988) unless a case says otherwise.

| Case | Deck | What the summary tables show |
|---|---|---|
| `calm_missing/` | `AVERTIME 1 3 24 PERIOD`, SO2, the 360-receptor polar grid; met `CALM.SFC` (below) | AERMOD counts 4 calm and 3 missing hours. Short-term values whose average includes them carry a flag after the number: `41.81475m` (3-hour), `2.63736c` (3-hour), and `b` on all four 24-hour values, the highest `15.94753b`. The highest 3-hour value, `52.64624`, is unflagged; `59.57654`, the highest without the missing hour, is gone. |
| `full_year/` | `AVERTIME 1 ANNUAL`, SO2, a 72-receptor polar grid; met `YEAR.SFC` / `YEAR.PFL` (below) | `THE SUMMARY OF MAXIMUM ANNUAL RESULTS AVERAGED OVER 1 YEARS` (highest 5.42148) and, because SO2 with 1-hour averages turns on AERMOD's 1-hour NAAQS processing, the four `THE SUMMARY OF MAXIMUM nTH-HIGHEST MAX DAILY 1-HR RESULTS` tables instead of the usual 1-hour summary. There is no PERIOD table. The setup message W361 mentions "PERIOD/ANNUAL". |
| `conc_ddep/` | `MODELOPT CONC DDEP FLAT ALPHA`, `GASDEPVD 0.01`, `AVERTIME 1 24 PERIOD`, pollutant OTHER | Two sets of summary tables: concentrations in MICROGRAMS/M**3 (1-hour 76.04726), then dry deposition (`DRY DEPO`) in GRAMS/M**2 (1-hour 0.00274). |
| `ddep_only/` | The same deck with `MODELOPT DDEP FLAT ALPHA`, and two plot files: `PLOTFILE 1 ALL FIRST ddep_01H.plt` and `PLOTFILE PERIOD ALL ddep_PERIOD.plt` | Only dry-deposition tables. The plot files hold the dry deposition (column `DRY DEPO`) where a concentration run has `AVERAGE CONC`; the highest 1-hour value, 0.00274 at (519.62, -300.00), is the summary table's. |
| `so2_8th_only/` | `full_year`'s deck with `AVERTIME 1`, `RECTABLE 1 8TH` and `MAXTABLE 1 10`; met `YEAR.SFC` / `YEAR.PFL` | The only 1-hour summary table is `THE SUMMARY OF MAXIMUM 8TH-HIGHEST MAX DAILY 1-HR RESULTS AVERAGED OVER 1 YEARS` (highest 76.07952, equal to `full_year`'s 4th-highest because the four days repeat). SO2's design value is the 4th-highest, which this run does not print. |

`CALM.SFC` is `AERMET2.SFC` with a calm hour (wind speed 0) at hour 5 of
every day, and missing wind (speed and direction 999) at hour 12 of
1 March and hour 20 of 2 and 3 March. `YEAR.SFC` and `YEAR.PFL` (used by `full_year` and
`so2_8th_only`) repeat the four Albany days over every day of 1988; they are not real weather, only
a complete year that AERMOD accepts, and at 1.5 MB each they are not
kept (the script writes them when it runs).

## Regenerating

Build AERMOD with `scripts/build_aermod.sh`, then run

```bash
python tests/fixtures/output_parser/regenerate.py bin/aermod [case ...]
```

The script writes `calm_missing/CALM.SFC`, runs each deck (or only the
cases named) in a scratch directory with its met files and copies back
`aermod.out`, `stdout.txt` and any `*.plt` plot files. Only the run date and time in the page headers should
change. If anything else changes, a new AERMOD release has changed its
output, and `tests/test_output_parser_real_runs.py` says whether the
parser still reads it.

# Recorded AERMOD runs for the runner's success rule

These are three real AERMOD runs. `tests/test_runner_status.py` reads
them to pin how `AERMODRunner` decides whether a run succeeded, and its
fake `aermod` replays them. None of the files is hand-edited.

- **Program:** AERMOD v26135, EPA's source archive `aermod_source.zip`
  (top-level directory `aermod_source_v26135`).
- **Build:** `scripts/build_aermod.sh` with GNU Fortran 13.3.0 and the
  script's default flags, `-O2 -fbounds-check -Wuninitialized`.
- **Recorded:** 2026-09-28, on Linux x86_64.
- **Meteorology:** `../epa_official/AERMET2.SFC` and `AERMET2.PFL`
  (Albany, New York, 1 to 4 March 1988, 96 hours). The decks name the
  files without a directory, so a run needs copies beside the deck.

Every case directory holds the deck (`aermod.inp`), the `aermod.out`
AERMOD wrote, AERMOD's stdout (`stdout.txt`) and its exit code
(`exit_code.txt`). AERMOD wrote nothing to stderr in any case.

| Case | Deck | Exit code | What AERMOD reports |
|---|---|---|---|
| `success/` | A 100 g/s, 65 m stack, a 360-receptor polar grid, `AVERTIME 1 3 24 PERIOD` | 0 | 0 fatal errors, 6 warnings (W206, W361, W362 twice, W214, W403) and `*** AERMOD Finishes Successfully ***` |
| `runtime_error_e480/` | The deck the GUI wrote on 2026-09-28, with `AVERTIME 1 ANNUAL` | 0 | Fatal error `MX E480 ... MAIN: Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave  NUMYRS=0` once the four days of met data are read, then `*** AERMOD Finishes UN-successfully ***` |
| `setup_error_e500/` | The `success/` deck with `SURFFILE MISSING.SFC` | 0 | Fatal error `ME E500 ... MEOPEN: Fatal Error Occurs Opening the Data File of  SURFFILE` during setup, then `*** SETUP Finishes UN-successfully ***` and `*** AERMOD Finishes UN-successfully ***` |

Things these recordings show, and that the runner relies on:

- AERMOD exits with code 0 after a fatal error, both at setup and at run
  time. The exit code says nothing about success.
- A run with setup messages carries two message summaries: "Message
  Summary For AERMOD Model Setup" and, at the end, "Message Summary :
  AERMOD Model Execution". The second one lists every message again, setup
  messages included. The E480 run's setup summary lists 4 warnings and its
  final summary lists 1 fatal error and 5 warnings.
- The E480 run prints `*** SETUP Finishes Successfully ***` before it
  fails, so a search for "FINISHES SUCCESSFULLY" alone passes a failed
  run. Only a completed run prints `*** AERMOD Finishes Successfully ***`.
- Each message line has the layout of `FORMAT(1X,A2,1X,A1,A3,I8,1X,A12,': ',A50,1X,A12)`
  in `SUMTBL` (aermod.f): pathway, severity, number, line, routine, a
  50-character text and a 12-character detail.

The `success/` deck asks for first-highest tables only (`RECTABLE ALLAVE
FIRST`). The GUI's `RECTABLE ALLAVE 1-10` and `MAXTABLE ALLAVE 10` make
the same run's `aermod.out` about 410 KB instead of 83 KB and change
nothing in its message summary. The run's maxima are the reference
scenario's in `PLAN-gui.md`: 76.07952 (1-hour), 59.57654 (3-hour),
16.85665 (24-hour) and 5.40459 (PERIOD) µg/m³, all at (519.62, -300.00).

## Regenerating

Build AERMOD with `scripts/build_aermod.sh`, then run

```bash
tests/fixtures/runner/regenerate.sh bin/aermod
```

The script runs each deck in a scratch directory with the met files and
copies back `aermod.out`, `stdout.txt` and `exit_code.txt`. Only the run
date and time in the page headers should change. If anything else
changes, a new AERMOD release has changed its output, and the tests in
`tests/test_runner_status.py` say whether the runner still reads it.

# Recorded AERMOD runs for the runner's success rule

These are six real AERMOD runs. `tests/test_runner_status.py` and
`tests/test_runner_batch.py` read them to pin how `AERMODRunner` decides
whether a run succeeded and how `resume_batch` decides whether a run is
done, and their fake `aermod` replays them. None of the files is
hand-edited.

- **Program:** AERMOD v26135, EPA's source archive `aermod_source.zip`
  (top-level directory `aermod_source_v26135`).
- **Build:** `scripts/build_aermod.sh` with the script's default flags,
  `-O2 -fbounds-check -Wuninitialized`.
- **Recorded:** `success/`, `runtime_error_e480/` and `setup_error_e500/`
  on 2026-09-28 on Linux x86_64 with GNU Fortran 13.3.0; the other three
  on 2026-09-29 on macOS arm64 with GNU Fortran 15.2.0 (Homebrew).
- **Meteorology:** `../epa_official/AERMET2.SFC` and `AERMET2.PFL`
  (Albany, New York, 1 to 4 March 1988, 96 hours). The decks name the
  files without a directory, so a run needs copies beside the deck.

Every case directory holds the deck (`aermod.inp`), the `aermod.out`
AERMOD wrote, AERMOD's stdout (`stdout.txt`) and its exit code
(`exit_code.txt`, as the shell reports it). AERMOD wrote nothing to
stderr in any case.

| Case | Deck | Exit code | What AERMOD reports |
|---|---|---|---|
| `success/` | A 100 g/s, 65 m stack, a 360-receptor polar grid, `AVERTIME 1 3 24 PERIOD` | 0 | 0 fatal errors, 6 warnings (W206, W361, W362 twice, W214, W403) and `*** AERMOD Finishes Successfully ***` |
| `runtime_error_e480/` | The deck the GUI wrote on 2026-09-28, with `AVERTIME 1 ANNUAL` | 0 | Fatal error `MX E480 ... MAIN: Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave  NUMYRS=0` once the four days of met data are read, then `*** AERMOD Finishes UN-successfully ***` |
| `setup_error_e500/` | The `success/` deck with `SURFFILE MISSING.SFC` | 0 | Fatal error `ME E500 ... MEOPEN: Fatal Error Occurs Opening the Data File of  SURFFILE` during setup, then `*** SETUP Finishes UN-successfully ***` and `*** AERMOD Finishes UN-successfully ***` |
| `setup_error_e322_openpit/` | The 2026-09-29 library audit's OPENPIT deck `D_hs_gt_depth`: release height 150 m in a 24,000,000 m³ pit of 600 × 400 m, whose effective depth is 100 m | 0 | Fatal error `SO E322 ... OPARM: Release Height Exceeds Effective Depth for OPENPIT  PIT` during setup (`OPARM` in `soset.f`, which takes the effective depth as volume / (length × width)), then both UN-successfully banners |
| `setup_error_e140_srcgroup/` | The audit's two-pit deck `H`, with the `SRCGROUP` line pyaermod writes inside each source's block, and `RUNORNOT NOT` | 0 | Fatal error `SO E140 ... SOCARD: Invalid Order of Keyword. The Troubled Keyword is  SRCGROUP`, twice, then both UN-successfully banners |
| `killed_sigterm/` | The `success/` deck plus a 500 × 500 m AREA source, which makes the run take about 3 s; `regenerate.sh` sends AERMOD SIGTERM 1 s after it starts | 143 (128 + SIGTERM's 15) | No final message summary and no AERMOD banner. The `.out` holds the setup summary, `*** SETUP Finishes Successfully ***` and the input summary up to the met data header, where the kill cut it off; stdout is empty because AERMOD's buffered output was lost with the process |

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
- A killed run leaves an `.out` that simply stops. It carries the
  setup banner and nothing that says the run failed, so only the absence
  of the final banner shows it did not finish. Python reports the exit
  as `-15` (`subprocess` gives a signal as a negative return code).
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
tests/fixtures/runner/regenerate.sh bin/aermod            # every case
tests/fixtures/runner/regenerate.sh bin/aermod killed_sigterm
```

The script runs each deck in a scratch directory with the met files and
copies back `aermod.out`, `stdout.txt` and `exit_code.txt`. Only the run
date and time in the page headers should change, except in
`killed_sigterm/`, whose `.out` ends wherever the kill found it; the
script refuses that recording unless the kill came after setup and
before the end of the run (set `KILL_AFTER`, in seconds, on a slower or
faster machine). If anything else
changes, a new AERMOD release has changed its output, and the tests in
`tests/test_runner_status.py` say whether the runner still reads it.

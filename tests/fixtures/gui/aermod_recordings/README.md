# AERMOD recordings for the GUI journeys

Each directory here records what a real AERMOD binary did with one deck
that the GUI writes. The end-to-end journeys in `tests/e2e/` replay these
recordings through `tests/e2e/fake_aermod.py` (tier T2), so the GUI meets
the real binary's stdout, output files and exit code without needing the
binary. Hand-written `.out` text is not allowed in new GUI tests
(PLAN-gui.md, "Test strategy").

## Where they came from

- **AERMOD version:** 26135 (EPA's v26135 source, as printed in every `.out`).
- **Build:** `scripts/build_aermod.sh aermod` with its default flags
  (`-O2 -fbounds-check -Wuninitialized`): gfortran 13.3 on Linux x86_64
  for `aertest`, and gfortran 15.2 on macOS arm64 for the three Albany
  scenarios. Each `manifest.json` records the build and the binary's
  SHA-256.
- **Recorded:** `aertest` on 2026-09-28; the Albany scenarios again on
  2026-09-29 (WP-G3), when the GUI's default deck gained a plot file and a
  POSTFILE for every averaging period. Apart from those files and the
  lines that list them, the new `.out` files equal the first recordings
  line for line, dates aside, and so do the maxima.

## Scenarios

| Directory | Deck | What AERMOD did |
|---|---|---|
| `albany_success` | The reference scenario of PLAN-gui.md ("Albany stack") with averaging periods 1, 3, 24 and PERIOD | Finished successfully: 0 fatal errors, 6 warnings. Maxima 76.07952 (1-hour), 59.57654 (3-hour), 16.85665 (24-hour) and 5.40459 µg/m³ (PERIOD), all at (519.62, −300.00). |
| `albany_e480` | The same scenario with the GUI's default averaging periods, 1 and ANNUAL | Processed all 96 hours, then stopped with fatal error E480 (less than a year of data for ANNUAL). Exit code 0. |
| `missing_met` | The same scenario with the default periods and a surface file, `MISSING.SFC`, that does not exist | Stopped during setup with fatal error E500. Exit code 0. |
| `aertest` | EPA's `tests/fixtures/epa_official/aertest.inp` with its paths flattened as `tests/test_real_aermod.py` does (`aertest.inp` here), imported with `read_aermod_input` and written back (`aermod.inp`) | Finished successfully. Its `AERTEST_01H.PLT` equals EPA's published reference for all 144 receptors. |

The Albany decks ask for `PLOTFILE` and `POSTFILE` output for every
averaging period (`pyaermod_01H.plt`, `pyaermod_01H.pst`, ...), which the
GUI turns on by default for its Results step; those files are in
`outputs/`. AERMOD writes the plot files only at the end of a run, so the
two failed runs leave them empty, and the E480 run keeps the 1-hour
POSTFILE it wrote while it processed the hours.

Every scenario's deck is built with the library exactly as the GUI writes
it: start from `pyaermod.gui_v2.state._empty_project()`, add the objects,
and render with `to_aermod_input(validate=False)`. The met files
(`AERMET2.SFC` and `AERMET2.PFL` from `tests/fixtures/epa_official/`) are
copied next to the deck and named without a directory, so no recording
carries a path from the machine that made it.

The slow run that journey J9 needs is not a separate recording: the fake
replays a recording with `PYAERMOD_E2E_DELAY` seconds between stdout lines.

## Layout of a recording

```
<scenario>/
  manifest.json    version, build, date, command, exit code, message counts,
                   output files and the maxima the library parses
  aermod.inp       the deck AERMOD read; the fake compares the GUI's deck to it
  aertest.inp      (aertest only) the flattened EPA deck a user imports
  stdout.txt       AERMOD's stdout, replayed line by line
  stderr.txt       AERMOD's stderr (empty for these runs)
  outputs/         every file the run created, under the name AERMOD gave it
                   (the main output is aermod.out)
```

A file larger than 500 KB, the limit of the repository's pre-commit
`check-added-large-files` hook, is stored as `<name>.gz` and listed under
`gzipped_outputs` in the manifest; the fake decompresses it when it
replays the run. AERTEST's 1.5 MB POSTFILE and the Albany 1-hour and
3-hour POSTFILEs are stored that way.

The fake compares decks after ignoring `TITLEONE` and `TITLETWO`, comments
and blank lines; it compares met file paths by base name and numbers by
value (`14735.0` equals `14735`). Any other difference makes it print a
diff and exit with code 2, and the journey fails.

## Regenerating

Build AERMOD and record every scenario again:

```bash
sudo apt-get install gfortran          # or: brew install gcc
./scripts/build_aermod.sh aermod       # -> ./bin/aermod
python scripts/record_aermod_fixtures.py --aermod bin/aermod
```

Use `--only albany_e480` to record one scenario, and `--build-note` to
describe a binary built another way. `tests/e2e/test_harness.py` fails
when the library starts writing a different deck for a scenario, which is
the signal to re-record. Re-recording rewrites the run date and time inside
each `.out` file; review any other change to the outputs before committing
it, and update this README and PLAN-gui.md if the numbers move.

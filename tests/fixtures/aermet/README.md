# Recorded AERMET runs for the deck writers and the runner's success rule

`ex01/` holds EPA's AERMET test case EX01 (Albany, New York, March 1988)
as EPA ships it in `aermet_test_cases.zip`
(`aermet_def_testcases_24142/EX01/` and `output_files/`): the TD-6201
upper-air file `14735-88.UA`, the CD-144 surface file `S1473588.144`,
EPA's own decks `EX01_S1.INP` and `EX01_S2.INP`, and the `EX01_MP.SFC`
and `EX01_MP.PFL` that AERMET 24142 wrote from them. None of these files
is edited.

`ex01_decks.py` writes the same two runs with pyaermod
(`AERMETStage1` and `AERMETStage3`), using EPA's station metadata,
dates, options and surface characteristics.

`runs/` holds six real AERMET runs. `tests/test_aermet_status.py` reads
them to pin the deck writers and how `AERMETRunner` decides whether a run
succeeded, and its fake `aermet` replays them. None of the files is
hand-edited.

- **Program:** AERMET v26135, EPA's source archive `aermet_source.zip`
  (SHA-256 `11b0f7efaaa384fe20651d6553aed6c3604803f0a3e8bd103b925e88f7088686`).
- **Build:** `scripts/build_aermod.sh aermet` with GNU Fortran 15.2.0 and
  the script's default flags, `-O2 -fbounds-check -Wuninitialized`.
- **Recorded:** 2026-09-29, on macOS arm64.

Every case directory holds the deck (`deck.inp`), AERMET's stdout
(`stdout.txt`), its exit code (`exit_code.txt`) and the REPORT and
MESSAGES files the deck names (`deck_not_found/` has neither). AERMET wrote
nothing to stderr in any case.

| Case | Deck | Exit code | What AERMET reports |
|---|---|---|---|
| `stage1_success/` | `ex01_decks.py`'s Stage 1 | 0 | 0 errors, 0 warnings, 16 information and 30 QA messages; `AERMET FINISHED SUCCESSFULLY` |
| `metprep_success/` | `ex01_decks.py`'s METPREP, run after its Stage 1 in the same directory | 0 | 0 errors, 9 warnings (W70, four W45, four W76); `AERMET FINISHED SUCCESSFULLY`. Its `EX01_MP.SFC` and `EX01_MP.PFL` are kept |
| `metprep_without_stage1/` | The same METPREP deck with no Stage 1 files present | 0 | Error `METPREP E70 PBL_TEST NO DATA PERIODS DATES OVERLAP`; `AERMET FINISHED UN-SUCCESSFULLY` |
| `stage1_wrong_format/` | The Stage 1 deck with the TD-6201 file declared `FSL` | 0 | Errors `UPPERAIR E30 READ_FSL SOUNDING IS NOT FSL FORMAT` and `E39 NO SOUNDINGS RETRIEVED`; `AERMET FINISHED UN-SUCCESSFULLY` |
| `legacy_stage1/` | The Stage 1 deck pyaermod wrote for EX01 before the writer was rewritten (its MESSAGES file is named `2`) | 0 | 6 errors: `E01 INVALID KEYWORD: ANEMHGT`, two `E05 INVALID FORMAT FOR STATION COORDINATE`, `E05 -5 GMT TO LST IS MORE THAN THREE HOURS`, `E01 INVALID KEYWORD: ELEVATION`, `E01 INVALID PATH QA`; `AERMET FINISHED UN-SUCCESSFULLY` |
| `deck_not_found/` | A deck named `deck.inp ` (a trailing blank, which AERMET's `trim` drops), so AERMET looks for `deck.inp` and does not find it | 0 | `Input file deck.inp not found`; no banner, no REPORT and no MESSAGES file (`readinp` in `mod_read_input.f90` stops) |

Things these recordings show, and that the writers and the runner rely on:

- AERMET exits with code 0 after an error. The exit code says nothing
  about success. The old runner called every one of these runs a
  success, since none prints "FATAL".
- Only a completed run prints `AERMET FINISHED SUCCESSFULLY`; a failed
  one prints `AERMET FINISHED UN-SUCCESSFULLY` (`aermet.f90`). A run that
  cannot open its runstream prints neither, counts no error and still
  exits 0 (`deck_not_found/`): only the banner tells it failed.
- The REPORT file's MESSAGE SUMMARY counts the messages by severity, in
  the layout `(//2(1x,a),1x,i8,1x,a/)` of `write_msg` in
  `mod_reports.f90` (`ERROR MESSAGES        6 MESSAGES`).
- Each MESSAGES line has the layout `(1x,a10,1x,a3,5x,a10,1x,...)`:
  pathway (blank for a message about the deck as a whole), code, routine
  and text.
- The METPREP run's `EX01_MP.SFC` and `EX01_MP.PFL` carry the same values
  as EPA's 24142 files in `ex01/`, hour for hour; they differ only in the
  version in the header and the year, which 26135 writes with four digits.
- METPREP warns W70 (`LOCATION KEYWORD NOT NEEDED`) when upper-air data
  are present, as it does for EPA's own EX01 deck; the warning is harmless.

## Regenerating

Build AERMET with `scripts/build_aermod.sh aermet`, then run

```bash
PYTHON=python tests/fixtures/aermet/regenerate.sh bin/aermet
```

with an interpreter that imports this checkout's pyaermod. The script
writes the decks with `ex01_decks.py`, runs each case in a scratch
directory holding the EX01 data files, and copies back the outputs. Only
the run dates and times should change. If a deck changes, the writer has
changed; if anything else changes, a new AERMET release has changed its
output, and the tests in `tests/test_aermet_status.py` say which rule no
longer holds.

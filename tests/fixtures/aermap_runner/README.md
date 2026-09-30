# Recorded AERMAP runs for the AERMAP writer and runner

These are three real AERMAP runs. `tests/test_aermap_runner_status.py`
reads them to pin how `AERMAPRunner` decides whether a run succeeded,
and its fake `aermap` replays them. `tests/test_aermap.py` checks that
`AERMAPProject.to_aermap_input` still writes the `success/` deck. None of
the files is hand-edited.

- **Program:** AERMAP 24142, EPA's source archive `aermap_source.zip`
  (top-level directory `aermap_source_code_24142`). This is EPA's
  current AERMAP; AERMAP has no 26135 release.
- **Build:** `scripts/build_aermod.sh aermap` with GNU Fortran 15.2.0 and the
  script's default flags, `-O2 -fbounds-check -Wuninitialized`.
- **Recorded:** 2026-09-29, on macOS arm64.
- **Terrain:** `synth.dem`, the 7 × 7 node USGS-format DEM that
  `_write_synthetic_dem` in `tests/test_real_aermap.py` writes: UTM zone
  13, NAD27, nodes 100 m apart from (500000, 4000000), elevation
  `100 + 2 i + 3 j` metres at node (i, j). The decks name it without a
  directory, so a run needs a copy beside the deck.

Every case directory holds the deck (`aermap.inp`), the `aermap.out`
message file AERMAP wrote, its stdout (`stdout.txt`), its exit code
(`exit_code.txt`) and, when AERMAP wrote them, the `RECEPTOR` and
`SOURCLOC` files (`aermap_receptors.out`, `aermap_sources.out`). AERMAP
wrote nothing to stderr in any case.

| Case | Deck | Exit code | What AERMAP reports |
|---|---|---|---|
| `success/` | What `AERMAPProject.to_aermap_input` writes for one discrete receptor, a 3 × 2 grid and one point source, with `DOMAINXY` inside the DEM | 0 | 0 fatal errors, 0 warnings, `*** AERMAP Finishes Successfully ***`; elevations 105 (receptor), 108 to 115 (grid) and 113 (source), the analytic plane |
| `domain_error_e310/` | The `success/` deck with a `DOMAINXY` that reaches 1 km past the DEM | 0 | Four fatal `OU E310 ... CHKEXT:Domain Coordinate is NOT Inside a DEM File`, `*** AERMAP Finishes UN-successfully ***`, and empty receptor and source files |
| `old_writer_setup_errors/` | What `to_aermap_input` wrote before the fix, for the same receptors and source | 0 | 11 fatal errors (E203 `TERRHGTS ELEVATED`, E200 four-field `DOMAINXY`, E130 no `ANCHORXY`, E130 no `RUNORNOT`, E208 receptor ID in `DISCCART`, E200 `GRIDCART` without `STA`, E105 `RECOUTPUT`, `SRCOUTPUT` and `MSGOUTPUT`, E120 `SO` after `RE`, E194 no `RECEPTOR` or `SOURCLOC`), 3 warnings, `*** AERMAP Finishes UN-successfully ***`, no receptor or source file |

Things these recordings show, and that the runner relies on:

- AERMAP exits with code 0 after fatal errors, at setup and later. The
  exit code says nothing about success.
- A run that fails can still leave its `RECEPTOR` and `SOURCLOC` files
  behind, empty (`domain_error_e310/`), so their presence says nothing
  either.
- AERMAP writes its verdict to the message file, named after the input
  file (`aermap.inp` gives `aermap.out`), not to a file the deck names.
  A run with setup messages carries two message summaries, "Message
  Summary For AERMAP Setup" and "Message Summary For AERMAP Execution",
  and a `*** SETUP Finishes ... ***` line before the final
  `*** AERMAP Finishes ... ***` line.
- Each message line has the layout of
  `FORMAT(1X,A2,1X,A1,A3,I8,1X,A6,':',A50,1X,A12)` in `SUMTBL`
  (aermap.f): pathway, severity, number, line, a six-character routine,
  a 50-character text and a 12-character detail. AERMOD's own layout
  differs (a twelve-character routine and `': '`).

## Regenerating

Build AERMAP from EPA's source (as `real_aermap.yml` does), then run

```bash
tests/fixtures/aermap_runner/regenerate.sh path/to/aermap
```

The script runs each deck in a scratch directory beside `synth.dem` and
copies back what AERMAP wrote. Only the run date and time in the headers
should change. If anything else changes, a new AERMAP release has
changed its output, and the tests in `tests/test_aermap_runner_status.py`
say whether the runner still reads it. If the writer changes the deck it
writes, record `success/` again from the new deck.

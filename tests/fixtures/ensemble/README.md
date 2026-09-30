# Recorded AERMOD runs for `pyaermod.ensemble`

`tests/test_ensemble.py` runs the design in `design.py` through
`run_design` with a fake `aermod` that replays these recordings: it finds
the recording whose deck matches the run's `aermod.inp`, writes back its
stdout, `aermod.out` and the files under `outputs/`, and exits with its
exit code. Every file here is what a real AERMOD wrote; none is
hand-edited.

- **Program:** AERMOD v26135, EPA's source archive `aermod_source.zip`
  (top-level directory `aermod_source_v26135`), built with
  `scripts/build_aermod.sh` and its default flags
  (`-O2 -fbounds-check -Wuninitialized`).
- **Recorded:** 2026-09-30 on macOS arm64 with GNU Fortran 15.2.0
  (Homebrew), by `regenerate.py`.
- **Meteorology:** `../epa_official/AERMET2.SFC` and `AERMET2.PFL`
  (Albany, New York, 1 to 4 March 1988, 96 hours), which `run_design`
  links into each run directory, so the decks name them without a
  directory.

Each case directory is one row of `design.RECORDED_ROWS`, named after
its `case` factor. It holds the deck `run_design` wrote (`aermod.inp`),
the `aermod.out` AERMOD wrote, AERMOD's stdout (`stdout.txt`), its exit
code (`exit_code.txt`) and the two PLOTFILEs the deck names
(`outputs/pit.plt`, PERIOD, and `outputs/pit_1h.plt`, 1-hour first
highest). `build()` names them `../shared/pit.plt` and
`/nonexistent-pyaermod-dir/pit_1h.plt`; the decks show `run_design`'s
rewrite to bare names.

| Case | Deck | What AERMOD reports |
|---|---|---|
| `d2p5_rho1`, `d10_rho1`, `d2p5_rho2p65`, `d10_rho2p65` | One OPENPIT source (600 × 400 m, 2.4e7 m³) with one particle size, 2.5 or 10 µm, density 1.0 or 2.65 g/cm³; `MODELOPT CONC DDEP FLAT`; 72 polar receptors at 1 and 2 km; `AVERTIME 1 PERIOD` | Exit code 0, 0 fatal errors, warnings W403 and W496 (no precipitation in the met), `*** AERMOD Finishes Successfully ***`; each PLOTFILE has 72 data rows with `AVERAGE CONC` and `DRY DEPO` columns, different in every case |
| `annual_e480` | The 10 µm, density 1.0 deck with `AVERTIME 1 ANNUAL` | Exit code 0, fatal error E480 (less than a year of met for ANNUAL averages) after the met is read, `*** AERMOD Finishes UN-successfully ***`; both PLOTFILEs are empty, because AERMOD opens them at setup |

## Regenerating

Build AERMOD with `scripts/build_aermod.sh`, then run

```bash
python tests/fixtures/ensemble/regenerate.py bin/aermod
```

Only the run date and time in the `.out` page headers and PLOTFILE
headers should change. If a deck changes, `pyaermod`'s writer has
changed and the recordings must be made again for the replay to find
them; if anything else changes, a new AERMOD release has changed its
output.

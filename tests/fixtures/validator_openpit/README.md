# Recorded AERMOD runs for the OPENPIT, Method 1 and DFAULT/FLAT rules

These are real AERMOD runs. `tests/test_validator_openpit_method1.py`
reads each deck back with `read_aermod_input`, validates it, and requires
the validator to name exactly the message codes AERMOD raised for it. It
also reads the PERIOD tables of the two `inpit` runs to find the
receptors AERMOD left at zero. None of the files is hand-edited.

- **Program:** AERMOD v26135, EPA's source archive `aermod_source.zip`
  (top-level directory `aermod_source_v26135`).
- **Build:** `scripts/build_aermod.sh` with GNU Fortran 15.2.0 (Homebrew)
  and the script's default flags, `-O2 -fbounds-check -Wuninitialized`.
- **Recorded:** 2026-09-29, on macOS arm64.
- **Meteorology:** `../epa_official/AERMET2.SFC` and `AERMET2.PFL`
  (Albany, New York, 1 to 4 March 1988, 96 hours). The decks name the
  files without a directory, so a run needs copies beside the deck.
- **Decks:** written by `make_decks.py` (`python make_decks.py .` from
  this directory), which says in comments what each source or receptor
  tests.

Every case directory holds the deck (`aermod.inp`), the `aermod.out`
AERMOD wrote, AERMOD's stdout (`stdout.txt`) and its exit code
(`exit_code.txt`, 0 in every case, including the failed ones). AERMOD
wrote nothing to stderr.

| Case | What it holds | What AERMOD reports |
|---|---|---|
| `openpit_limits/` | Seven pits: Qemis = 0, Hs = 210 m in a 300 m-deep pit, Xinit = 2100 m, Yinit = 2100 m, Angle = 190, a 12:1 pit, Xinit = 0 | W320 for QS, HS, XINIT, YINIT, ANGLE and XINIT again (the zero, which OPARM raises to 1e-5 m), W392 for the 12:1 pit and the zero-width one; the run completes |
| `openpit_errors/` | Xinit = -100, Hs = -1, Hs = 100.1 m in a 100 m-deep pit, Hs = 100 m in a 100 m-deep pit | E209 for XINIT and HS, E322 for the 100.1 m release and for the negative-Xinit pit (its effective depth is negative); none for Hs equal to the depth; setup fails |
| `method1/` | Seven VOLUME sources with PARTDIAM/MASSFRAX/PARTDENS | E335 for diameters 0.001 and 1001 (not 0.0011 or 1000), E332 for fractions 1.1 and -0.1, E334 for density 0, W334 for density 0.1 (not 0.11), W330 for sums 0.975 and 1.021 (not 0.98), E240 for 3 diameters with 2 fractions; setup fails |
| `openpit_tiny_dimension/` | Xinit = 5e-6 m, Yinit = 100 m, Volume = 1e-3 m³, Hs = 1.5 m | W320 for XINIT (raised to 1e-5 m), W392, and E322: the depth from the raised width is 1 m (from the raw width it would be 2 m); setup fails |
| `inpit/` | A 600 x 400 m pit and six discrete receptors: two inside, one on the east edge, one 1 m outside it, the SW vertex, one well outside | PERIOD 0 at the two inside receptors only; no message code; the input summary lists those two as OPENPIT |
| `inpit_rotated/` | The same pit rotated 30 degrees about its SW corner, three receptors | PERIOD 0 at the two inside receptors only; no message code; the input summary lists those two as OPENPIT |
| `bins25/` | One pit with 25 particle categories (0.5 to 24.5 µm), DDEP | No particle message; the run completes |
| `dfault_flat/` | `MODELOPT CONC FLAT DFAULT` | W206 for FLAT; the header shows the run in ELEV |
| `dfault_flatsrcs/` | `MODELOPT CONC FLAT ELEV DFAULT` | W206 for FLAT |
| `dfault_elev/` | `MODELOPT CONC ELEV DFAULT` | No W206 |

Things these recordings show, and that the validator relies on:

- Each message is listed twice in `aermod.out` (the setup summary and the
  final one); `parse_aermod_messages` reads the final one.
- OPARM's `ELSE IF (AHS .GT. 3000)` branch (E324) follows the `> 200`
  branch and can never run, so no OPENPIT release height draws E324.
- A zero Xinit or Yinit is a warning, not an error: OPARM substitutes
  1e-5 m and the run completes.
- AERMOD raises no message code for receptors inside a pit. It lists
  each one in the input summary's "source-receptor combinations for
  which calculations may not be performed" table with `OPENPIT` in the
  distance column (`inpsum.f` CHKREC), and PITCALC leaves 0 for it in
  the output tables. The test checks both.
- The `method1` deck uses 1001, not 1000.5, for its out-of-range
  diameter. pyaermod writes `PARTDIAM` to 4 significant figures, so a
  read-back 1000.5 would be written, and validated, as 1000.

## Regenerating

Build AERMOD with `scripts/build_aermod.sh`, then run

```bash
tests/fixtures/validator_openpit/regenerate.sh bin/aermod
```

The script runs each deck in a scratch directory with the met files and
copies back `aermod.out`, `stdout.txt` and `exit_code.txt`. Only the run
date and time in the page headers should change.

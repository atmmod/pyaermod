# Common Errors and Fixes

AERMOD's error messages are terse and its crashes are cryptic. This
page lists the failures pyaermod users hit most often, what causes
them, and which pyaermod helper catches them earlier.

## Input-file generation errors

### "duplicate source ID"

- **Cause:** multiple sources added with the same `source_id`.
- **Fix:** `Validator.validate(project)` will flag this before write.
- **Where:** `validator.py` line ~195.

### "averaging period not supported for pollutant"

- **Cause:** ANNUAL for 1-hour-designed pollutants, or 1-hour for
  ANNUAL-only criteria pollutants.
- **Fix:** check `ControlPathway.averaging_periods` vs.
  `PollutantType`.

### Open pit: "Release Height Exceeds Effective Depth for OPENPIT" (E322)

- **Cause:** an `OpenPitSource` whose `release_height` is above its
  effective depth, `pit_volume / (x_dimension * y_dimension)`. AERMOD
  refuses the deck at setup (`soset.f` OPARM).
- **Fix:** `Validator.validate(project)` reports it as an error, and
  `project.write()` refuses to write the deck. Lower the release height
  or check the volume and dimensions.

### Open pit: zero concentration at receptors inside the pit

- **Cause:** AERMOD does not model an `OPENPIT` source at receptors that
  lie strictly inside the pit; it skips them and leaves 0 for that source
  there (`calc1.f` PITCALC). AERMOD raises no error or warning code for
  them. It only lists each one, with `OPENPIT` in the distance column, in
  the input summary's table headed "source-receptor combinations for
  which calculations may not be performed" (`inpsum.f` CHKREC).
  Receptors on the pit's edge are modelled.
- **Fix:** the validator warns with the number of receptors inside each
  pit and the first few of their coordinates. Drop those receptors, or
  read their values as "not modelled" rather than "clean air".

### Particle categories: E335, E332, E334, W334, W330

- **Cause:** `ParticleDepositionParams` values AERMOD rejects: a diameter
  of 0.001 microns or less, or above 1000 (E335); a mass fraction outside
  0-1 (E332); a density of 0 or less (E334). AERMOD warns for a density of
  0.1 g/cm³ or less (W334) and for fractions that sum outside 0.98-1.02
  (W330). There is no limit on the number of categories. AERMOD checks
  the numbers in the deck, and pyaermod writes diameters and densities
  to 4 significant figures and mass fractions to 6 decimals, so the
  validator checks the rounded values: 1000.4 microns is written, and
  accepted, as 1000.
- **Fix:** `Validator.validate(project)` reports each with AERMOD's code.

### DFAULT with FLAT terrain (W206)

- **Cause:** `ControlPathway` defaults to `terrain_type=FLAT` with
  `regulatory_default=True`, which writes `MODELOPT ... FLAT DFAULT`.
  Under DFAULT, AERMOD drops FLAT with warning W206 and runs the deck in
  elevated terrain, using the receptor and source elevations. A DFAULT
  deck read with `read_aermod_input` whose `MODELOPT` names no terrain
  token also draws the warning: the reader maps it to FLAT, so pyaermod
  would write it back as `FLAT DFAULT`, although AERMOD runs the original
  deck in elevated terrain without W206.
- **Fix:** the validator warns. Set `regulatory_default=False` for a
  flat-terrain run, or `terrain_type=TerrainType.ELEVATED` to write what
  AERMOD will do.

## AERMOD runtime failures

### Immediate crash, ERRMSG.TMP has `E101` {#e101}

- **Cause:** missing input or met file.
- **Fix:** run `Validator.validate(project, check_files=True)` —
  catches this in-process.

### `E480`: "Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave" {#e480}

- **Cause:** ANNUAL averages (or MULTYEAR, or MAXDCONT) with met data
  that hold no complete year. AERMOD processes every hour and then stops;
  it exits with code 0 all the same. A year ends at the hour before the
  first hour of data, one year on, so a file that starts at hour 1 of
  1 March needs data through hour 24 of the last day of February.
  During setup the same code flags a STARTEND window shorter than a year.
- **Fix:** use a year or more of met data, or averaging periods without
  ANNUAL (PERIOD averages over whatever the file holds).
  `check_annual_met_coverage(project)` in `validator_advanced` reads the
  surface file and warns before the run, and the GUI's Review & Run step
  shows that warning; `read_surface_period(path)` in `aermet` says which
  days a file holds.

### `E500`: "Fatal Error Occurs Opening the Data File of SURFFILE" {#e500}

- **Cause:** AERMOD could not open a met file (`SURFFILE` or `PROFFILE`,
  named at the end of the message). A relative path is opened from the
  directory AERMOD runs in, not from where the deck was written. AERMOD
  does not expand `~`, so `~/met.sfc` is a relative path too. AERMOD
  stops during setup and still exits with code 0.
- **Fix:** give the full path, or copy the file into the working
  directory. `Validator.validate(project, check_files=True)` checks the
  paths first.

### Runs but writes no output

- **Cause:** `RUNORNOT NOT` in the CO pathway.
- **Fix:** `ControlPathway` defaults to `RUN`; if you see `NOT`
  somewhere, that's why.

### "The working directory ... already holds another deck named aermod.inp"

- **Cause:** AERMOD reads its deck from `aermod.inp` in the working
  directory and writes `aermod.out` there. The runner links your deck
  to that name and renames the outputs after the run. When the
  directory already holds a different deck named `aermod.inp`, such as
  a base case kept under EPA's default name beside its variants, the
  run would replace that deck and overwrite its `aermod.out`, so the
  runner refuses and starts nothing. In `run_batch` only the variants
  fail this way; the `aermod.inp` deck itself runs in place.
- **Fix:** rename the base deck (`base.inp`), or give the variant its
  own `working_dir`. A deck that is itself `aermod.inp`, or that
  `aermod.inp` is a symbolic link to, runs in place and the link is left
  as it is; its outputs are named after the file the link points to. A
  link named `aermod.inp` that points to some other file is replaced for
  the run and removed after it; the file it pointed to is not touched.
- **Where links cannot be made** (Windows without the symbolic-link
  privilege), the runner copies the deck to `aermod.inp` for the run and
  writes `.pyaermod-aermod-inp.sha256` beside it; both are removed after
  the run. If the Python process is killed mid-run (a closed terminal,
  Task Manager, a restarted GUI server), they stay behind, and the next
  run in that directory knows the copy as its own, by the SHA-256 in
  that file, and replaces it. Any other `aermod.inp` is a deck and is
  kept, even one with the same bytes as the deck being run (a variant
  copied from the base deck and not yet edited); a stray copy made by
  hand, or by a runner older than this marker, has to be deleted by hand.

### "ANNUAL average requested, ran for single day"

- **Cause:** `met.start_*` / `met.end_*` specify a single day but
  AVERTIME includes ANNUAL.
- **Fix:** `advanced_validate(project)` raises an error for this.

### Silent underprediction near the stack

- **Cause:** stack height at or above GEP — AERMOD models no
  downwash.
- **Fix:** use `assess_source_downwash(src, buildings)` to confirm
  it's by design, or lower the stack.

### "receptor outside DEM bounds"

- **Cause:** AERMAP fetched a DEM that doesn't cover all receptors.
- **Fix:** widen the DEM bbox; see
  [`aermap-troubleshooting.md`](aermap-troubleshooting.md).

### Buoyancy-related NaNs in output

- **Cause:** `exit_velocity = 0` but `stack_temp > ambient` — AERMOD
  can't compute momentum flux.
- **Fix:** `advanced_validate` flags this combination as a warning.

## Cryptic Fortran crashes

| AERMOD message | Likely cause |
|---|---|
| `** FATAL ** negative U*` | AERMET produced implausible friction velocity; re-run QA/QC |
| `** FATAL ** bad mixing height` | zic / zim inconsistent with L sign |
| `*** ERROR *** XY array out of bounds` | receptor grid > AERMOD's recompile limit |
| `*** ERROR *** pollutant not recognized` | typo in `POLLUTID` — use the `PollutantType` enum |

## Using the runner diagnostics

When `AERMODRunner.run()` returns `success=False`, capture context
with:

```python
from pyaermod import summarize_failure
print(summarize_failure(result.input_file, working_dir))
```

That prints ERRMSG content plus the tail of `.OUT`, which is almost
always enough to identify the cause without copying files manually.

### "AERMOD was stopped by SIGTERM (signal 15) before it finished"

- **Cause:** something outside AERMOD ended the process: `kill`, a job
  scheduler's time limit, a closed terminal. On POSIX the runner sees
  the signal as a negative return code (`result.return_code == -15`)
  and names it. The `.out` ends wherever the run was cut off; it can
  hold `*** SETUP Finishes Successfully ***` but never AERMOD's final
  banner.
- **Timeouts** read "Execution timed out after N seconds; AERMOD was
  stopped before it finished". The partial `.out` is kept as
  `<deck>.out`, so it can be inspected, and it replaces whatever an
  earlier run of the deck left there.
- **Fix:** run the deck again with more time. `resume_batch` counts
  either kind of run as still to do.

## Batch runs

### Every run fails with "A process in the process pool was terminated abruptly"

- **Cause:** the script calls `run_batch` (or `BatchRunner.parameter_sweep`)
  at the top level, without an `if __name__ == "__main__":` guard. On
  macOS and Windows, Python starts the worker processes with `spawn`,
  which imports the calling script again in each worker; each worker
  then tries to start a batch of its own and stops with "An attempt has
  been made to start a new process before the current process has
  finished its bootstrapping phase". Linux uses `fork` and does not
  show the problem, so a script can work there and fail on a laptop.
- **Fix:** put the batch under the guard:

```python
from pyaermod import AERMODRunner

if __name__ == "__main__":
    runner = AERMODRunner()
    results = runner.run_batch(["a.inp", "b.inp", "c.inp"], n_workers=3)
    for deck, result in zip(["a.inp", "b.inp", "c.inp"], results):
        print(deck, result.success)
```

### Pairing results with decks

`run_batch` returns the results in the order of its input list, whatever
order the runs finish in, so `zip(input_files, results)` pairs each deck
with its own result (earlier versions returned the list in finishing
order). Each result's `input_file` is the deck's absolute path. With
`stop_on_error=True` the list still holds one result per deck: runs
already under way when the batch stops finish and keep their place, and
a deck that was never started has `success=False` and the
`error_message` "Not run: the batch stopped after an earlier run
failed".

### Resuming an interrupted batch

`resume_batch(input_files, output_dir)` counts a deck as done only when
its `<deck>.out` passes the same test `AERMODRunner.run` applies (the
`*** AERMOD Finishes Successfully ***` line and no fatal error in the
final message summary) and came from the deck as it is now. AERMOD
copies the runstream to the top of the `.out`, and `resume_batch`
compares that copy with the deck's text. A failed, killed or timed-out
run, and an `.out` left from before the deck was edited, are all still
to do.

Because the check reads content, not file times, a script may write
every deck again before it resumes (as `BatchRunner.parameter_sweep`
does): a deck written with the same text stays done, and so does one
copied without `cp -p`. File times decide only what the copy cannot
show. A deck with `NO ECHO` is run again when it is newer than its
`.out`, and so is a deck whose `INCLUDED` file (looked up relative to
the deck's directory) is newer than its `.out`. Met files and other
inputs the deck names are not checked: after changing one of those,
delete the affected `.out` files.

## Before you file a bug

1. `Validator.validate(project, check_files=True)` — any errors?
2. `advanced_validate(project)` — any warnings?
3. `EPA_APPENDIX_W_2017.check(project)` (or your profile) — any
   regulatory lint?
4. `run_all_qaqc(surface_records)` on the SFC file.
5. Confirm the minimal reproducer is actually minimal — prefer a
   single source over 50 of them.

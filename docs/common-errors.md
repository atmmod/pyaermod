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
  stops during setup and still exits with code 0.
- **Fix:** give the full path, or copy the file into the working
  directory. `Validator.validate(project, check_files=True)` checks the
  paths first.

### Runs but writes no output

- **Cause:** `RUNORNOT NOT` in the CO pathway.
- **Fix:** `ControlPathway` defaults to `RUN`; if you see `NOT`
  somewhere, that's why.

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

## Before you file a bug

1. `Validator.validate(project, check_files=True)` — any errors?
2. `advanced_validate(project)` — any warnings?
3. `EPA_APPENDIX_W_2017.check(project)` (or your profile) — any
   regulatory lint?
4. `run_all_qaqc(surface_records)` on the SFC file.
5. Confirm the minimal reproducer is actually minimal — prefer a
   single source over 50 of them.

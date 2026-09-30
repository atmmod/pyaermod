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

### Immediate crash, ERRMSG.TMP has `E101`

- **Cause:** missing input or met file.
- **Fix:** run `Validator.validate(project, check_files=True)` —
  catches this in-process.

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
final message summary) and is not older than the deck. A failed, killed
or timed-out run, and an `.out` left from before the deck was edited,
are all still to do. A deck whose modification time moved only because
it was copied without `cp -p` is run again, which costs time but never
a wrong result.

## Before you file a bug

1. `Validator.validate(project, check_files=True)` — any errors?
2. `advanced_validate(project)` — any warnings?
3. `EPA_APPENDIX_W_2017.check(project)` (or your profile) — any
   regulatory lint?
4. `run_all_qaqc(surface_records)` on the SFC file.
5. Confirm the minimal reproducer is actually minimal — prefer a
   single source over 50 of them.

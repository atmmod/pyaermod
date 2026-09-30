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
  there, without any message (`calc1.f` PITCALC). Receptors on the pit's
  edge are modelled.
- **Fix:** the validator warns with the number of receptors inside each
  pit and the first few of their coordinates. Drop those receptors, or
  read their values as "not modelled" rather than "clean air".

### Particle categories: E335, E332, E334, W334, W330

- **Cause:** `ParticleDepositionParams` values AERMOD rejects: a diameter
  of 0.001 microns or less, or above 1000 (E335); a mass fraction outside
  0-1 (E332); a density of 0 or less (E334). AERMOD warns for a density of
  0.1 g/cm³ or less (W334) and for fractions that sum outside 0.98-1.02
  (W330). There is no limit on the number of categories.
- **Fix:** `Validator.validate(project)` reports each with AERMOD's code.

### DFAULT with FLAT terrain (W206)

- **Cause:** `ControlPathway` defaults to `terrain_type=FLAT` with
  `regulatory_default=True`, which writes `MODELOPT ... FLAT DFAULT`.
  Under DFAULT, AERMOD drops FLAT with warning W206 and runs the deck in
  elevated terrain, using the receptor and source elevations.
- **Fix:** the validator warns. Set `regulatory_default=False` for a
  flat-terrain run, or `terrain_type=TerrainType.ELEVATED` to write what
  AERMOD will do.

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

## Before you file a bug

1. `Validator.validate(project, check_files=True)` — any errors?
2. `advanced_validate(project)` — any warnings?
3. `EPA_APPENDIX_W_2017.check(project)` (or your profile) — any
   regulatory lint?
4. `run_all_qaqc(surface_records)` on the SFC file.
5. Confirm the minimal reproducer is actually minimal — prefer a
   single source over 50 of them.

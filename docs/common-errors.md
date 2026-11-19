# Common errors and fixes

Failures seen most often, their causes, and the pyaermod check that
catches each before the run. AERMOD reports problems as codes such as
`E500` (error) and `W206` (warning) in the `.out` file.

## AERMOD runtime failures

### Missing deck or met file (the GUI links this as `E101`) {#e101}

- **Cause:** AERMOD has no message code E101. A deck it cannot open
  stops it at once with "Error Opening Runstream Input File!  Aborting."
  on the screen (`aermod.f`). A met file it cannot open gives
  [E500](#e500).
- **Fix:** `Validator.validate(project, check_files=True)` checks the
  paths in-process.

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

- **Cause:** `RUNORNOT NOT` makes AERMOD check the input and stop.
- **Fix:** `ControlPathway` defaults to `RUN`; look for a `NOT` that came
  from a deck you read.

### "The working directory ... already holds another deck named aermod.inp"

- **Cause:** AERMOD reads `aermod.inp` in the working directory and writes
  `aermod.out` there. The runner links your deck to that name and renames
  the outputs after the run. When the directory already holds a different
  deck named `aermod.inp` (a base case beside its variants), the run would
  replace it, so the runner refuses and starts nothing. In `run_batch` only
  the variants fail this way; the `aermod.inp` deck itself runs in place.
- **Fix:** rename the base deck (`base.inp`), or give the variant its own
  `working_dir`. A deck that is `aermod.inp`, or that `aermod.inp` links
  to, runs in place. Where links cannot be made (Windows without the
  symbolic-link privilege) the runner copies the deck and removes the copy
  after the run; if the process is killed, a stray copy marked by
  `.pyaermod-aermod-inp.sha256` is replaced by the next run, and any other
  `aermod.inp` is kept.

### "AERMOD was stopped by SIGTERM (signal 15) before it finished"

- **Cause:** something outside AERMOD ended the process: `kill`, a job
  scheduler's time limit, a closed terminal. On POSIX the runner sees the
  signal as a negative return code (`result.return_code == -15`). The
  `.out` ends where the run was cut off and never holds AERMOD's final
  banner.
- **Timeouts** read "Execution timed out after N seconds; AERMOD was
  stopped before it finished". The partial `.out` is kept as `<deck>.out`
  and replaces whatever an earlier run left there.
- **Fix:** run the deck again with more time. `resume_batch` counts either
  kind of run as still to do.

When `AERMODRunner.run()` returns `success=False`, print the ERRMSG
content and the tail of the `.out`:

```python
from pyaermod import summarize_failure
print(summarize_failure(result.input_file, working_dir))
```

## Checks pyaermod makes before the run

### "duplicate source ID"

- **Cause:** two sources with the same `source_id`.
- **Fix:** `Validator.validate(project)` flags it before the write.

### "ANNUAL averaging requested but met range is a single day"

- **Cause:** `met.start_*` and `met.end_*` name a single day and the
  averaging periods include ANNUAL.
- **Fix:** `advanced_validate(project)` reports this as an error. Use a
  longer met range (see also [E480](#e480)).

### "exit_velocity = 0 but stack_temp ... (>> ambient)"

- **Cause:** a hot stack with zero exit velocity.
- **Fix:** `advanced_validate` warns that the combination is
  inconsistent. Give the stack its real exit velocity.

### "receptor outside DEM bounds"

- **Cause:** AERMAP was given a DEM that does not cover every receptor.
- **Fix:** widen the DEM bounding box; see
  [AERMAP troubleshooting](aermap-troubleshooting.md).

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

### Deposition with RLINE, RLINEXT or BUOYLINE (E251)

- **Cause:** `DEPOS`, `DDEP` or `WDEP` in `MODELOPT` (any of
  `ControlPathway.calculate_deposition`, `calculate_dry_deposition`,
  `calculate_wet_deposition`) in a deck with an `RLineSource`,
  `RLineExtSource` or `BuoyLineSource`. AERMOD refuses the deck at setup
  (`soset.f` SRCQA, E251), although pyaermod's dataclasses for those
  sources carry `gas_deposition` and `particle_deposition` fields.
- **Fix:** `Validator.validate(project)` reports an error on each such
  source. Turn deposition off, or model the road or line as a `LINE`,
  `AREA` or `VOLUME` source, which take deposition.

### Particle categories: E335, E332, E334, W334, W330

- **Cause:** `ParticleDepositionParams` values AERMOD rejects: a diameter
  of 0.001 microns or less, or above 1000 (E335); a mass fraction outside
  0-1 (E332); a density of 0 or less (E334). AERMOD warns for a density of
  0.1 g/cm³ or less (W334) and for fractions that sum outside 0.98-1.02
  (W330). pyaermod writes diameters and densities to 4 significant figures
  and mass fractions to 6 decimals, and the validator checks the rounded
  values: 1000.4 microns is written, and accepted, as 1000.
- **Fix:** `Validator.validate(project)` reports each with AERMOD's code.

### Particle categories: aerodynamic diameters beside a density above 1

- **Cause:** `PARTDIAM` values that are aerodynamic diameters (as AP-42
  size multipliers and impactors report) written beside a `PARTDENS` other
  than 1. AERMOD settles each category by Stokes' law from the diameter and
  density together (`soset.f` VDP1), so it reads `PARTDIAM` as the physical
  diameter. It has no message code for this, because it cannot tell the
  two kinds of diameter apart.
- **Fix:** `to_deposition_params(density=...)` converts to Stokes
  diameters whenever the density is not 1 and records
  `diameter_convention="stokes"`; the validator warns when the convention
  is `"aerodynamic"` and any density is not 1. For hand-built categories,
  convert with `pyaermod.psd.aerodynamic_to_stokes` or use a density of
  1.0. See
  [Particle size distributions](psd.md#what-aermod-does-with-the-diameter).

### Open pit: "Release Height Exceeds Effective Depth for OPENPIT" (E322)

- **Cause:** an `OpenPitSource` whose `release_height` is above its
  effective depth, `pit_volume / (x_dimension * y_dimension)`. AERMOD
  refuses the deck at setup (`soset.f` OPARM).
- **Fix:** `Validator.validate(project)` reports it as an error, and
  `project.write()` refuses to write the deck. Lower the release height
  or check the volume and dimensions.

### Open pit: zero concentration at receptors inside the pit

- **Cause:** AERMOD skips receptors strictly inside an `OPENPIT` source and
  reports 0 for that source there (`calc1.f` PITCALC), with no message
  code. It lists them, with `OPENPIT` in the distance column, only in the
  `.out` table "source-receptor combinations for which calculations may
  not be performed" (`inpsum.f` CHKREC). Receptors on the pit's edge are
  modelled.
- **Fix:** the validator warns with the number of receptors inside each
  pit and the first few coordinates. Drop those receptors, or read their
  values as "not modelled" rather than "clean air".

### Open pit: an AREA source used for a pit

- **Cause:** a rectangular `AreaSource` with the pit's footprint stands in
  for the pit. AERMOD models a flat surface release: nothing settles
  inside the pit and every receptor over the footprint is modelled. An
  `OPENPIT` source instead lets each particle category leave the pit with
  the escape fraction `1 / (1 + Vg / (0.029 U_ref))` (1 for a gas;
  `pitarea.f`, `soset.f`), releases the plume with σz0 = effective depth /
  4.3 from an effective area on the upwind side of the pit, and skips
  receptors inside the pit (the entry above). The two sources deposit
  different amounts outside the pit when the categories are coarse enough
  to settle.
- **Fix:** `OpenPitSource.from_area(area, depth=...)` (or `volume=`)
  builds the OPENPIT from the AREA's corner, sides, angle, emission rate
  and deposition fields. Set `AreaSource.depth_hint` on an AREA that
  stands in for a pit: it is written nowhere, and the validator then
  advises the OPENPIT whenever deposition is on or the source has
  particle categories.

## Batch runs

### Every run fails with "A process in the process pool was terminated abruptly"

- **Cause:** the script calls `run_batch` (or `BatchRunner.parameter_sweep`)
  at the top level, without an `if __name__ == "__main__":` guard. On macOS
  and Windows, Python starts workers with `spawn`, which imports the script
  again in each worker; each worker then tries to start a batch of its own.
  Linux uses `fork` and does not show the problem, so a script can work
  there and fail on a laptop.
- **Fix:** put the batch under the guard:

```python
from pyaermod import AERMODRunner

if __name__ == "__main__":
    runner = AERMODRunner()
    results = runner.run_batch(["a.inp", "b.inp", "c.inp"], n_workers=3)
```

`run_batch` returns results in input order, so `zip(input_files, results)`
pairs each deck with its result. `resume_batch(input_files, output_dir)`
runs again only the decks whose `<deck>.out` is missing, failed, or made
from an earlier version of the deck; see [Ensembles](ensemble.md#resuming) for
resuming.

## Before you file a bug

1. `Validator.validate(project, check_files=True)` — any errors?
2. `advanced_validate(project)` — any warnings?
3. `EPA_APPENDIX_W_2017.check(project)` (or your profile) — any
   regulatory lint?
4. Check the surface file with `run_all_qaqc` (see the
   [AERMET tuning guide](aermet-tuning-guide.md)).
5. Cut the reproducer down: one source, not 50.

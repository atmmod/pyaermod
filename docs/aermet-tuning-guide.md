# AERMET Tuning Guide

AERMET is the meteorological preprocessor for AERMOD. Bad met data
silently produces bad dispersion results — this guide covers the
choices and quality checks pyaermod surfaces to help you get them
right.

## Input data sources supported

pyaermod exposes four upstream met-data channels through
`pyaermod.met_ingest`:

| Source | Use for | Module |
|---|---|---|
| ISD / ISD-Lite (NOAA) | hourly surface observations at airport / METAR stations | `ISDFetcher` |
| ASOS 1-minute DSI-6405 | sub-hourly wind data for AERMINUTE preprocessing | `parse_asos_1min_file` + `aggregate_1min_to_hourly` |
| IGRA v2 | upper-air radiosonde soundings | `IGRAFetcher` + `parse_igra_v2` |
| MMIF | prognostic (WRF / MM5 / RAMS) fields in AERMOD-ready format | `MMIFConfig` |

Cache directories are supported on both network fetchers so repeated
runs for the same station / year don't redownload.

## The two AERMET runs

AERMET 11 and later (including the current releases, 24142 and 26135)
run in two stages, each from its own runstream file:

1. **Stage 1** reads the raw upper-air, surface and on-site data
   (`DATA`), writes what it read (`EXTRACT`) and the quality-assured
   data (`QAOUT`). `AERMETStage1` writes this deck.
2. **METPREP** (AERMET's "stage 2") reads the Stage 1 `QAOUT` files,
   merges them itself, computes the boundary-layer parameters
   (Monin-Obukhov length, friction velocity, convective and mechanical
   mixing heights) and writes the `.SFC` (`OUTPUT`) and `.PFL`
   (`PROFILE`) files AERMOD reads. `AERMETStage3` writes this deck; it
   keeps its old name so existing code runs.

The separate merge stage of AERMET 06341 and earlier is gone: AERMET
ignores a `MERGE` pathway with warning W01. `AERMETStage2` is deprecated
and writes no deck.

What the writers take care of, following AERMET's Fortran:

| Keyword | What pyaermod writes |
|---|---|
| `JOB MESSAGES` | a file name (`message_file`); AERMET has no message level |
| `LOCATION` | `id 42.75N 73.8W adj [elev]`: unsigned coordinates with a hemisphere letter, the GMT-to-LST adjustment AERMET subtracts from each hour, and the station elevation |
| the adjustment | `-time_zone` for data recorded in GMT (upper air, ISHD), 0 for data in local time (CD144, SAMSON, HUSWO, on-site); for SCRAM and GHCN surface data set `surface_time_adjustment` |
| `UPPERAIR LOCATION` elevation | required (`UpperAirStation.elevation`); AERMET 24142+ stops with E05 without it |
| upper-air formats | `FSL`, `IGRA`, `6201FB`, `6201VB` (`upper_air_format`) |
| `ONSITE` | `OnsiteData`: `READ`/`FORMAT` records, `THRESHOLD`, `OSHEIGHTS`, `DELTA_TEMP`, `OBS/HOUR` |
| surface characteristics | `FREQ_SECT`, `SECTOR`, `SITE_CHAR` (from `site_char` records, or from the 12 monthly `albedo`/`bowen`/`roughness` values), or an AERSURFACE file (`AERSURF`); `SITE_CHAR2` etc. for a secondary site |
| `METHOD`, `NWS_HGT` | `methods`, e.g. `[("WIND_DIR", "RANDOM")]`; `METHOD REFLEVEL SUBNWS` is added to every deck with NWS surface data and no on-site data (AERMET 26135 stops with E87 without it); `NWS_HGT WIND` from `nws_height` or the station's anemometer height, required with SUBNWS (E72 otherwise) |

`run_aermet_pipeline(stage1, None, stage3, working_dir=...)` writes and
runs both decks; the METPREP deck reads the `QAOUT` files the Stage 1
deck names (`AERMETStage3.with_inputs_from`). pyaermod's decks for EPA's
AERMET test cases EX01, EX04 (Houston) and Cordero reproduce EPA's
`.SFC` and `.PFL` files line for line
(`tests/test_real_aermet_binary.py`; EX04 and Cordero need EPA's test
cases in `aermet_test_cases/`).

### Did the run succeed?

AERMET exits with code 0 when it fails, so the exit code says nothing.
`AERMETRunner` (and the pipeline) reports success only when AERMET
prints `AERMET FINISHED SUCCESSFULLY` and neither its MESSAGES file nor
the REPORT file's message summary lists an error. `result.errors` holds
the parsed error messages, and `result.error_message` starts with the
first one:

```python
results = run_aermet_pipeline(stage1, None, stage3, working_dir="met")
for r in results:
    if not r.success:
        print(r.stage, r.error_message)   # e.g. "UPPERAIR E30 READ_FSL: SOUNDING IS NOT FSL FORMAT ..."
```

## Quality assurance

Every AERMET run should be followed by a `met_qaqc` pass on the
resulting `.SFC` output:

```python
from pyaermod import read_surface_file, run_all_qaqc

records = read_surface_file("stn.sfc")["data"].to_dict("records")
report = run_all_qaqc(records)
print(report.summary())
if report.n_errors:
    print(report.dump(limit=10))
```

`read_surface_file` returns the hours as a DataFrame under `"data"`,
with the `.SFC` column names (`wind_speed`, `L`, `Zic`, ...).
`run_all_qaqc` looks up the field names of `met_ingest`'s hourly records
(`wind_speed_ms`, `monin_obukhov_m`, ...), so on `.SFC` records it
currently reports every field as missing; until the two agree, rename
the columns before the check.

`run_all_qaqc` runs five checks:

| Check | What it catches |
|---|---|
| `check_missing_data` | >10% missing in any primary field; long (≥24 h) gaps |
| `check_extremes` | physically implausible values (T, wind, mixing height, u\*, L) |
| `check_stability_consistency` | CBL regime (L<0) with zic=0, or SBL (L>0) with zic>0 |
| `check_low_wind_bias` | >25% of hours at/below 0.5 m/s — often an anemometer artifact |
| `check_profile_monotonic` | non-decreasing pressure in a radiosonde ascent |

Any finding at "error" severity means AERMOD will either fail or
produce statistics you can't defend. "warning" findings are worth
reviewing before the run.

## Low-wind options

AERMOD's LOWWIND family adjusts how the model handles stable, calm
hours. Appendix W (2017) currently allows `LOWWIND3` when documented.

`pyaermod.regulatory.EPA_APPENDIX_W_2017.check(project)` will warn if
`low_wind_option` is outside the allowed set.

## ADJ_U* and surface characteristics

The METPREP deck is where the friction-velocity adjustment (ADJ_U*) is
enabled, as `METHOD STABLEBL ADJ_U*`. pyaermod does not enable it for
you: pass `methods=[("STABLEBL", "ADJ_U*")]` to `AERMETStage3`
explicitly and include it in your modeling protocol.

## Common AERMET failures

| Symptom | Likely cause | Check / fix |
|---|---|---|
| `result.success` is False | AERMET listed an error | `result.errors`, and the REPORT and MESSAGES files |
| AERMOD crashes with "missing hour" errors | METPREP couldn't produce a full annual record | `find_missing_runs(records, "wind_speed_ms")` |
| Very low predicted impacts | calm-bias inflating | `check_low_wind_bias(records)` |
| Predicted impacts ignore elevated plumes | profile file missing upper-air data | `read_profile_file("stn.pfl")` and inspect level count |
| Station far from project site | surface obs unrepresentative | document distance + terrain similarity; consider MMIF |

## Recommended workflow

```python
from pyaermod import (
    ISDFetcher, ISDStationId, IGRAFetcher,
    AERMETStage1, AERMETStage3, run_aermet_pipeline,
    read_surface_file, run_all_qaqc,
)

# 1. Fetch raw obs (cached)
surface = ISDFetcher(cache_dir="cache/isd").read_hourly(
    ISDStationId("723010", "13880"), 2020,
)
upper = IGRAFetcher(cache_dir="cache/igra").read_soundings("USM00072469")

# 2. Describe Stage 1 (AERMETStage1) and METPREP (AERMETStage3)
# 3. Run both with the aermet binary; stop on AERMET's own verdict
results = run_aermet_pipeline(stage1, None, stage3, working_dir="met")
if not all(r.success for r in results):
    raise SystemExit("; ".join(r.error_message for r in results if not r.success))

# 4. QA the METPREP output before feeding AERMOD
records = read_surface_file("stn.sfc")["data"].to_dict("records")
report = run_all_qaqc(records)
if report.n_errors:
    raise SystemExit(report.dump())
```

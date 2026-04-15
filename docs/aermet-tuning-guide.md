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

## Stage 1, 2, 3 at a glance

AERMET runs in three stages:

1. **Stage 1** ingests raw surface + upper-air data, applies basic
   range / consistency QA, and writes intermediate data files.
2. **Stage 2** merges surface, upper-air, and (optionally) 1-minute
   ASOS data into a single hourly file.
3. **Stage 3** computes boundary-layer parameters (Monin-Obukhov
   length, friction velocity, convective/mechanical mixing heights)
   and writes the final `.SFC` + `.PFL` files that AERMOD consumes.

`pyaermod.aermet` provides `AERMETStage1`, `AERMETStage2`, and
`AERMETStage3` dataclasses plus `write_aermet_runfile()` to emit each
stage's input deck.

## Quality assurance

Every AERMET run should be followed by a `met_qaqc` pass on the
resulting `.SFC` output:

```python
from pyaermod import read_surface_file, run_all_qaqc

records = read_surface_file("stn.sfc")["records"]
report = run_all_qaqc(records)
print(report.summary())
if report.n_errors:
    print(report.dump(limit=10))
```

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

Stage 3 is where the friction-velocity adjustment (ADJ_U*) is enabled
in AERMET's run file.  AERMOD couples with this through profile
inputs; pyaermod does not auto-enable it — set
`AERMETStage3.adj_ustar = True` explicitly and include it in your
modeling protocol.

## Common AERMET failures

| Symptom | Likely cause | Check / fix |
|---|---|---|
| AERMOD crashes with "missing hour" errors | Stage 2 couldn't produce a full annual record | `find_missing_runs(records, "wind_speed_ms")` |
| Very low predicted impacts | calm-bias inflating | `check_low_wind_bias(records)` |
| Predicted impacts ignore elevated plumes | profile file missing upper-air data | `read_profile_file("stn.pfl")` and inspect level count |
| Station far from project site | surface obs unrepresentative | document distance + terrain similarity; consider MMIF |

## Recommended workflow

```python
from pyaermod import (
    ISDFetcher, ISDStationId, IGRAFetcher,
    AERMETStage1, AERMETStage2, AERMETStage3,
    read_surface_file, run_all_qaqc,
)

# 1. Fetch raw obs (cached)
surface = ISDFetcher(cache_dir="cache/isd").read_hourly(
    ISDStationId("723010", "13880"), 2020,
)
upper = IGRAFetcher(cache_dir="cache/igra").read_soundings("USM00072469")

# 2. Write AERMET run decks for stages 1-3 (see aermet.write_aermet_runfile)

# 3. Run aermet (external binary) for each stage

# 4. QA the Stage 3 output before feeding AERMOD
records = read_surface_file("stn.sfc")["records"]
report = run_all_qaqc(records)
if report.n_errors:
    raise SystemExit(report.dump())
```

# 8. Tutorial 5 — Processing Meteorological Data with AERMET

**Goal:** Use pyaermod to write the two AERMET input files (Stage 1 and
Stage 2, called METPREP) that turn raw weather station data into AERMOD-ready
meteorological files.

> **This tutorial uses a short Python script, not the GUI.** The GUI's
> Meteorology step only points AERMOD at finished `.sfc` and `.pfl` files; it
> has no AERMET page. You don't need programming experience: you copy the
> script below into a file, change the values, and run it.

**Time:** 30--40 minutes

**What you'll learn:**
- What AERMET does and why AERMOD needs it
- How AERMET's two stages, Stage 1 and Stage 2 (METPREP), work
- How to configure each stage with pyaermod
- What the monthly surface parameters mean and how to choose values

**Prerequisite:** pyaermod writes AERMET *input files*; running them needs
the `aermet` executable, installed as in
[Section 3.2](setup.md#32-install-the-aermod-and-aermet-executables).
`which aermet` (Mac/Linux) or `where aermet` (Windows) shows whether it is
found.

## Conceptual Background

AERMOD cannot use raw station observations. It reads two processed files:

- **Hourly surface data** (`.sfc` file): wind speed, wind direction, ambient
  temperature, atmospheric stability class, mixing height, friction velocity,
  Monin-Obukhov length, and other boundary-layer parameters.
- **Hourly profile data** (`.pfl` file): vertical profiles of wind speed, wind
  direction, and temperature at multiple heights above ground.

**AERMET** turns raw station observations into these two files in two runs,
Stage 1 and Stage 2 (METPREP), each from its own input file:

```
Raw weather data (NOAA archives)
          |
   Stage 1: Extract & QA/QC
          |
   Quality-assured hourly data (QAOUT files)
          |
   Stage 2 (METPREP): merge surface + upper air, compute boundary-layer parameters
          |
   aermod.sfc  +  aermod.pfl   (ready for AERMOD)
```

## What Data Does AERMET Need?

AERMET requires two types of weather observations:

1. **Surface observations** — hourly weather data from a ground-level station
   (typically an airport). Includes wind speed, wind direction, temperature,
   cloud cover, and ceiling height. In the U.S., this data is available from
   NOAA's Integrated Surface Hourly Data (ISHD) archive.

2. **Upper air soundings** — twice-daily vertical profiles of temperature,
   humidity, and wind measured by weather balloons (radiosondes). Available
   from NOAA's Radiosonde Database. The closest upper air station may be
   100+ km away — that's normal.

> **Your instructor should provide** the station IDs, data files, and date
> ranges for your region. If you need to download your own data, NOAA's
> archives are at https://www.ncei.noaa.gov/.

## Step 1: Start the Script

1. Make a folder for this tutorial and put your raw data files in it.
2. In that folder, create a text file named `make_aermet_inputs.py` and
   start it with these lines:

```python
from pathlib import Path

from pyaermod.aermet import AERMETStage1, AERMETStage3, AERMETStation, UpperAirStation
```

You will add to this file in Steps 2 and 3 and run it in Step 4. The script
describes Stage 1 and Stage 2. The class for Stage 2 keeps its old name,
`AERMETStage3`.

## Step 2: Configure Stage 1 — Extract & QA/QC

**Purpose:** Stage 1 reads raw station data, checks its quality (flagging
missing or suspicious values) and extracts the variables AERMET needs.

### Surface Station

Describe the surface station. Your instructor should provide these
values. Example for Atlanta, GA:

| Parameter | Example Value | What It Means |
|---|---|---|
| Station ID | `13874` | The station's WBAN number (Weather-Bureau-Army-Navy; Atlanta Hartsfield, ICAO code `KATL`). AERMET reads it as a number, so `KATL` makes Stage 2 stop |
| Station Name | `Atlanta Hartsfield` | Descriptive name (for your reference) |
| Latitude | `33.6300` | Station latitude (decimal degrees, negative = south) |
| Longitude | `-84.4400` | Station longitude (decimal degrees, negative = west) |
| Time Zone (UTC offset) | `-5` | Eastern Standard Time = UTC-5 |
| Elevation (m) | `315.0` | Station elevation above sea level |
| Anemometer Height (m) | `10.0` | Height of the wind sensor (usually 10 m) |
| Data Format | `ISHD` | Integrated Surface Hourly Data (ISHD, NOAA); the other formats are listed in `pyaermod.aermet.SURFACE_FORMATS` |

Add the station to your script:

```python
surface = AERMETStation(
    station_id="13874",
    station_name="Atlanta Hartsfield",
    latitude=33.6300,
    longitude=-84.4400,
    time_zone=-5,
    elevation=315.0,
    anemometer_height=10.0,
)
```

The data format goes into Stage 1 itself, below.

### Upper Air Station

Describe the upper air (radiosonde) station. Example:

| Parameter | Example Value | What It Means |
|---|---|---|
| Station ID | `72215` | WMO station number |
| Station Name | `Peachtree City` | Closest radiosonde launch site |
| Latitude | `33.3600` | |
| Longitude | `-84.5700` | |
| Elevation (m) | `245.0` | Station elevation above sea level; check it against the station list of your data source |

```python
upper_air = UpperAirStation(
    station_id="72215",
    station_name="Peachtree City",
    latitude=33.3600,
    longitude=-84.5700,
    elevation=245.0,
)
```

> **Finding your upper air station:** The closest radiosonde station may be
> far from your surface station. In the U.S., there are only about 90 upper
> air stations (compared to thousands of surface stations). Use the one that
> is most representative of your area's upper-atmosphere conditions.

### Data Files and Date Range

| Parameter | Example Value | What It Means |
|---|---|---|
| Surface Data File | `72219013874.dat` | Path to the raw ISHD surface data file |
| Upper Air Data File | `72215.dat` | Path to the raw upper air data file |
| Start Date | `2020/01/01` | First day of the period to process |
| End Date | `2020/12/31` | Last day (typically 1--5 years of data) |

Add Stage 1 to your script:

```python
stage1 = AERMETStage1(
    surface_station=surface,
    surface_data_file="72219013874.dat",
    surface_format="ISHD",
    upper_air_station=upper_air,
    upper_air_data_file="72215.dat",
    start_date="2020/01/01",
    end_date="2020/12/31",
)
```

### What Stage 1's Input File Contains

The file this produces (you will write it in Step 4) contains keywords like:

- `JOB` — identifies the processing job and names its report and message files
- `SURFACE` with a `DATA` line — points to the surface data file and
  specifies the format
- `UPPERAIR` with a `DATA` line — points to the upper air data file
- `XDATES` — specifies the date range to extract

## Step 3: Configure Stage 2 (METPREP) — Boundary Layer Parameters

**Purpose:** METPREP merges Stage 1's quality-assured data and computes the
boundary-layer parameters AERMOD reads: friction velocity, Monin-Obukhov
length, convective velocity scale and mixing height. They depend on the
weather data and on the **surface characteristics** around the station.

### File Paths

| Parameter | Example Value |
|---|---|
| Start Date | `2020/01/01` |
| End Date | `2020/12/31` |
| Surface Output (.sfc) | `aermod.sfc` |
| Profile Output (.pfl) | `aermod.pfl` |

### Monthly Surface Parameters

METPREP takes three parameters for each month; choosing them takes the most
judgment:

| Parameter | What It Controls | Typical Range |
|---|---|---|
| **Albedo** | Surface reflectivity (fraction of sunlight reflected). Snow-covered ground has high albedo; dark pavement has low albedo. | 0.10 -- 0.60 |
| **Bowen Ratio** | Ratio of sensible heat to latent heat. Dry surfaces (deserts, cities) have high Bowen ratios; moist surfaces (wetlands, irrigated fields) have low values. | 0.1 -- 10.0 |
| **Roughness (m)** | Aerodynamic roughness length — how "bumpy" the surface is to wind flow. Open water is very smooth (~0.001 m); a city center is very rough (~1.0 m). | 0.001 -- 2.0 |

This tutorial uses **suburban values** (moderate development: residential
neighborhoods, scattered trees):

| Month | Albedo | Bowen Ratio | Roughness (m) |
|---|---|---|---|
| Jan | 0.35 | 1.5 | 0.30 |
| Feb | 0.35 | 1.5 | 0.30 |
| Mar | 0.25 | 1.0 | 0.30 |
| Apr | 0.18 | 0.8 | 0.30 |
| May | 0.15 | 0.6 | 0.50 |
| Jun | 0.15 | 0.5 | 0.50 |
| Jul | 0.15 | 0.5 | 0.50 |
| Aug | 0.15 | 0.5 | 0.50 |
| Sep | 0.18 | 0.6 | 0.50 |
| Oct | 0.25 | 0.8 | 0.30 |
| Nov | 0.35 | 1.0 | 0.30 |
| Dec | 0.35 | 1.5 | 0.30 |

> **How to customize these values:**
>
> - **If your site is in a rural/agricultural area:** Lower roughness
>   (0.05--0.15 m), albedo varies by crop/season, Bowen ratio varies by
>   irrigation.
> - **If your site is in a dense urban area:** Higher roughness
>   (0.5--1.5 m), higher Bowen ratio (dry impervious surfaces), lower albedo
>   (dark pavement).
> - **If there's winter snow cover:** Increase albedo to 0.50--0.70 during
>   snowy months.

In the script each parameter is a list of twelve numbers, January first. To
change a month, edit its number in the list.

### Site Location

`station=surface` tells METPREP to use the surface station you described for
Stage 1, with its latitude and longitude.

Add Stage 2 to your script:

```python
stage3 = AERMETStage3(
    station=surface,
    #        Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep   Oct   Nov   Dec
    albedo=[0.35, 0.35, 0.25, 0.18, 0.15, 0.15, 0.15, 0.15, 0.18, 0.25, 0.35, 0.35],
    bowen=[1.5, 1.5, 1.0, 0.8, 0.6, 0.5, 0.5, 0.5, 0.6, 0.8, 1.0, 1.5],
    roughness=[0.30, 0.30, 0.30, 0.30, 0.50, 0.50, 0.50, 0.50, 0.50, 0.30, 0.30, 0.30],
    methods=[("REFLEVEL", "SUBNWS")],
    start_date="2020/01/01",
    end_date="2020/12/31",
    surface_file="aermod.sfc",
    profile_file="aermod.pfl",
).with_inputs_from(stage1)
```

`methods=[("REFLEVEL", "SUBNWS")]` tells AERMET that the wind data come from
a National Weather Service station, which current AERMET requires to be
stated. `.with_inputs_from(stage1)` points METPREP at the files Stage 1
writes.

## Step 4: Write the Two Input Files

End your script with the lines that write the two files:

```python
Path("aermet_stage1.inp").write_text(stage1.to_aermet_input())
Path("aermet_stage2.inp").write_text(stage3.to_aermet_input())
print("Wrote aermet_stage1.inp and aermet_stage2.inp")
```

Run it in a terminal, from the folder that holds the script:

```bash
python make_aermet_inputs.py
```

You now have two AERMET input files to run:

| File | Stage | What It Does |
|---|---|---|
| `aermet_stage1.inp` | Extract & QA/QC | Reads raw data, checks quality |
| `aermet_stage2.inp` | Stage 2 (METPREP) | Merges surface + upper air, computes AERMOD-ready parameters |

Open them in a text editor and find the keywords listed in Step 2 and your
monthly surface parameters (`SITE_CHAR` lines) in the Stage 2 file.

## Step 5: Run AERMET

AERMET itself must be run separately (it's a different executable from AERMOD).
If `which aermet` (`where aermet` on Windows) prints nothing, install it
from [Section 3.2](setup.md#32-install-the-aermod-and-aermet-executables).

In a terminal, go to the directory with your input files and run each stage:

```bash
# Stage 1
aermet aermet_stage1.inp

# Stage 2 (METPREP: merge + boundary layer)
aermet aermet_stage2.inp
```

Give the input file as an argument: `aermet file.inp`. METPREP reads the
QAOUT files Stage 1 writes, so run the stages **in order**. When METPREP
completes you have `aermod.sfc` and `aermod.pfl`.

AERMET exits without an error code even when it fails. Check that the
screen output ends with `AERMET FINISHED SUCCESSFULLY` and read the messages
file each deck names (`MESSAGES`) for lines with an `E` code such as `E05`.
From Python, `pyaermod.aermet_runner.run_aermet_pipeline` runs both decks
and reports each run's `success` and first error for you.

If a run fails, read the messages file; the codes are explained under
[Common AERMET failures](../../aermet-tuning-guide.md#common-aermet-failures).

## Step 6: Use the Processed Met Data in AERMOD

Once you have `aermod.sfc` and `aermod.pfl`:

1. Launch the GUI (`pyaermod-app`) and go to the **Meteorology** step.
2. Under **Met files**, enter the full paths to your new `aermod.sfc` and
   `aermod.pfl` files in **Surface file** and **Profile file**. The step
   then says what the surface file holds.
3. Under **Stations**, enter **Surface station ID** `13874`, **Upper air
   station ID** `72215` and **Data start year** `2020`, the stations and
   year you processed.
4. Continue with your AERMOD run (Tutorial 3).

## Understanding What AERMET Produced

The `.sfc` file contains one line per hour with columns including:

- Year, month, day, hour
- Sensible heat flux (W/m2) — energy driving vertical mixing
- Friction velocity (m/s) — a measure of wind turbulence near the ground
- Monin-Obukhov length (m) — characterizes atmospheric stability
  (negative = unstable, positive = stable)
- Mixing height (m) — the depth of the turbulent boundary layer
- Wind speed, direction, and temperature

The `.pfl` file contains vertical wind and temperature profiles for each
hour — the information AERMOD uses to model how the plume disperses at
different heights.

AERMOD reads these files itself. If your maximum concentrations all fall at
night, look at the stable hours (small positive Monin-Obukhov length, low
mixing height): they hold the plume near the ground.

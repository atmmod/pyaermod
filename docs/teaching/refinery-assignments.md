# Houston Refinery Modeling Assignments

Tutorials 6--8: AERMET for Houston, AERMAP terrain, and a ten-source
refinery model. They assume [Tutorials 1--5](student-guide/index.md). The
model is built in the GUI (`pyaermod-app`); the steps the GUI does not cover
(AERMET input files, AERMAP elevations, a background concentration,
POSTFILE analysis) use short Python scripts you copy and run, as in
Tutorial 5.

1. [Tutorial 6: AERMET for Houston, Texas](#tutorial-6-aermet-for-houston-texas)
2. [Tutorial 7: Terrain Processing with AERMAP](#tutorial-7-terrain-processing-with-aermap)
3. [Tutorial 8: Modeling a Simplified Oil Refinery](#tutorial-8-modeling-a-simplified-oil-refinery)
4. [Assignment Deliverables](#assignment-deliverables)
5. [Supplemental Reference Tables](#supplemental-reference-tables)

---

## Tutorial 6: AERMET for Houston, Texas

**Goal:** Generate AERMOD-ready meteorological files (`.sfc` and `.pfl`)
for the Houston Ship Channel from real station data and Houston surface
parameters.

**Time:** 40--50 minutes

**What you'll learn:**
- How to identify surface and upper air stations for a location
- How to select monthly surface parameters for an industrial/coastal setting
- How to run AERMET's two stages (Stage 1 and Stage 2, METPREP) and verify
  the output

### Background: Why Houston?

The Houston Ship Channel holds one of the largest concentrations of
refining and petrochemical plants in the world. Its meteorology:

- **Winds** from the south-southeast (Gulf of Mexico) in summer, turning
  northerly in winter cold fronts.
- **High humidity** all year, which lowers the Bowen ratio compared with
  arid inland sites.
- **Sea breezes** that can reverse the wind along the coast in the
  afternoon (Discussion Question 3).
- **Unstable** summer days and **stable** clear winter nights.

### Step 1: Identify the Meteorological Stations

For a refinery near the Houston Ship Channel (approximately 29.75 N,
95.10 W), we need two weather stations:

#### Surface Station — Houston Hobby Airport (KHOU)

| Parameter | Value | Notes |
|---|---|---|
| Station ID | `12918` | WBAN number (Weather-Bureau-Army-Navy; ICAO code `KHOU`). AERMET reads the surface ID as a number, so it needs the WBAN |
| Station Name | `Houston Hobby Airport` | |
| Latitude | `29.6454` | Decimal degrees |
| Longitude | `-95.2789` | Negative = west |
| Time Zone (UTC offset) | `-6` | Central Standard Time |
| Elevation (m) | `14.0` | Near sea level — typical for coastal Houston |
| Anemometer Height (m) | `10.0` | Standard |
| Data Format | `ISHD` | Integrated Surface Hourly Data (NOAA) |

> **Why Hobby instead of Intercontinental?** Hobby is closer to the Ship
> Channel and more coastal and industrial. George Bush Intercontinental
> (KIAH) is 35 km north-northwest in a more suburban, forested setting.

#### Upper Air Station — Lake Charles, Louisiana

| Parameter | Value | Notes |
|---|---|---|
| Station ID | `72240` | WMO station number |
| Station Name | `Lake Charles, LA` | |
| Latitude | `30.1200` | |
| Longitude | `-93.2200` | |
| Elevation (m) | `4.6` | Station elevation above sea level |

> **Why Lake Charles?** It is the closest radiosonde station (about 200 km
> east); the alternative, Corpus Christi, is about 330 km southwest.

#### Data Files and Date Range

For this tutorial, process **one full calendar year** of data. Your
instructor will provide the raw data files, or you can download them from
NOAA's NCEI archive.

| Parameter | Value |
|---|---|
| Surface Data File | `khou_2023.dat` |
| Upper Air Data File | `72240_2023.dat` |
| Start Date | `2023/01/01` |
| End Date | `2023/12/31` |

### Step 2: Configure Stage 1

As in Tutorial 5, the AERMET input files come from a short Python script.
Create `make_houston_aermet.py` and start it with the stations and
Stage 1 (`AERMETStage1`), using the values above:

```python
from pathlib import Path

from pyaermod.aermet import AERMETStage1, AERMETStage3, AERMETStation, UpperAirStation

surface = AERMETStation(
    station_id="12918",
    station_name="Houston Hobby Airport",
    latitude=29.6454,
    longitude=-95.2789,
    time_zone=-6,
    elevation=14.0,
    anemometer_height=10.0,
)

upper_air = UpperAirStation(
    station_id="72240",
    station_name="Lake Charles LA",
    latitude=30.1200,
    longitude=-93.2200,
    elevation=4.6,
)

stage1 = AERMETStage1(
    surface_station=surface,
    surface_data_file="khou_2023.dat",
    surface_format="ISHD",
    upper_air_station=upper_air,
    upper_air_data_file="72240_2023.dat",
    start_date="2023/01/01",
    end_date="2023/12/31",
)
```

You write the file in Step 3, as `aermet_houston_s1.inp`.

### Step 3: Configure Stage 2 (METPREP) — Houston Surface Parameters

The land around the Ship Channel is a mix of **industrial facilities, port
infrastructure, open water and coastal grassland**, unlike the suburban
values of Tutorial 5. Stage 2 (class `AERMETStage3`) uses these dates and
output files:

| Parameter | Value |
|---|---|
| Start Date | `2023/01/01` |
| End Date | `2023/12/31` |
| Surface Output | `houston_2023.sfc` |
| Profile Output | `houston_2023.pfl` |

#### Houston Ship Channel Monthly Surface Parameters

| Month | Albedo | Bowen Ratio | Roughness (m) | Rationale |
|---|---|---|---|---|
| Jan | 0.18 | 0.8 | 0.40 | Bare deciduous trees, dormant grass, dry winter |
| Feb | 0.18 | 0.7 | 0.40 | Pre-spring, some rain events |
| Mar | 0.16 | 0.5 | 0.50 | Vegetation greening, increasing moisture |
| Apr | 0.14 | 0.4 | 0.60 | Full leaf-out, higher transpiration |
| May | 0.14 | 0.3 | 0.60 | Lush vegetation, humid air, frequent rain |
| Jun | 0.14 | 0.3 | 0.60 | Peak humidity, tropical moisture |
| Jul | 0.14 | 0.3 | 0.60 | Peak summer — hot and humid |
| Aug | 0.14 | 0.3 | 0.60 | Same as July |
| Sep | 0.15 | 0.4 | 0.60 | Slight drying, still warm |
| Oct | 0.16 | 0.5 | 0.50 | Transitional, vegetation still green |
| Nov | 0.17 | 0.7 | 0.45 | Leaf drop begins, drier air |
| Dec | 0.18 | 0.8 | 0.40 | Dormant season, some cold fronts |

> **Compared with Tutorial 5's suburban values:** albedo is lower
> (0.14--0.18 vs 0.15--0.35), the Bowen ratio is lower (0.3--0.8 vs
> 0.5--1.5) and roughness is higher (0.40--0.60 vs 0.30--0.50). Moist Gulf
> Coast surfaces put more energy into evaporation (a lower Bowen ratio),
> and tanks, stacks and buildings add roughness. Compare the `.sfc` files
> from the two sets to see the effect.

Add Stage 2 to your script with the Houston values, and the lines that
write both files. `station=surface` uses the Stage 1 surface station.

```python
stage3 = AERMETStage3(
    station=surface,
    #        Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep   Oct   Nov   Dec
    albedo=[0.18, 0.18, 0.16, 0.14, 0.14, 0.14, 0.14, 0.14, 0.15, 0.16, 0.17, 0.18],
    bowen=[0.8, 0.7, 0.5, 0.4, 0.3, 0.3, 0.3, 0.3, 0.4, 0.5, 0.7, 0.8],
    roughness=[0.40, 0.40, 0.50, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.50, 0.45, 0.40],
    methods=[("REFLEVEL", "SUBNWS")],
    start_date="2023/01/01",
    end_date="2023/12/31",
    surface_file="houston_2023.sfc",
    profile_file="houston_2023.pfl",
).with_inputs_from(stage1)

Path("aermet_houston_s1.inp").write_text(stage1.to_aermet_input())
Path("aermet_houston_s2.inp").write_text(stage3.to_aermet_input())
```

Run `python make_houston_aermet.py`. It writes `aermet_houston_s1.inp` and
`aermet_houston_s2.inp`.

### Step 4: Run AERMET

In a terminal, run Stage 1 and then Stage 2:

```bash
aermet aermet_houston_s1.inp
aermet aermet_houston_s2.inp
```

AERMET exits without an error code even when it fails: check that each run
ends with `AERMET FINISHED SUCCESSFULLY`. When Stage 2 completes, the working
directory holds `houston_2023.sfc` and `houston_2023.pfl`.

### Step 5: Verify the Output

Launch the GUI (`pyaermod-app`):

1. Go to the **Meteorology** step.
2. Under **Met files**, enter the full paths to `houston_2023.sfc` and
   `houston_2023.pfl` in **Surface file** and **Profile file**.
3. Read what the step says about the surface file: the period it covers
   and the station IDs in its header should be 2023, `12918` and `72240`.

> **Sanity checks:**
>
> - The `.sfc` file should have ~8,760 lines (one per hour for 365 days,
>   plus a header). Missing hours are normal — a few percent is acceptable.
> - Open the `.sfc` file in a text editor. The wind direction column should
>   show a mix of directions with a preference for south-southeast winds
>   (150--200 degrees) in summer months.
> - Mixing heights should range from ~100 m (stable nighttime) to
>   ~2,000--3,000 m (convective daytime in summer).

### Discussion Questions

1. **Why does the Bowen ratio matter?** If you used a desert Bowen ratio
   (e.g., 5.0) for Houston, how would that affect the boundary layer
   parameters? (Hint: think about how sensible heat drives convective mixing.)

2. **What if you used the wrong surface station?** If you mistakenly used
   a station 100 km inland (less humid, more rural), which surface parameters
   would be most affected?

3. **Sea breeze effects.** Houston experiences afternoon sea breezes that can
   reverse the wind direction. Would you expect to see this in the `.sfc`
   file? How might it affect a refinery's downwind impacts?

---

## Tutorial 7: Terrain Processing with AERMAP

**Goal:** Use pyaermod and AERMAP to assign terrain elevations to
all receptors and sources for a model domain near the Houston Ship Channel.

**Time:** 30--40 minutes

**What you'll learn:**
- Why terrain elevation matters even in "flat" areas like Houston
- How to download digital elevation model (DEM) data
- How to run AERMAP to compute receptor and source elevations
- How to bring AERMAP's elevations into your project
- The difference between FLAT and ELEVATED terrain modes in AERMOD

### Conceptual Background

Tutorials 1--5 used FLAT terrain: every receptor and source at elevation
zero. AERMAP reads digital elevation models (DEMs) and assigns:

1. **Receptor terrain elevation** (`z_elev`): ground height at each receptor.
2. **Receptor hill height** (`z_hill`): the controlling hill height AERMOD
   uses in its terrain calculations.
3. **Source base elevation**: ground height at each source.

Houston is coastal and mostly flat: the Ship Channel is at 0--5 m, the
surrounding neighborhoods at 10--25 m. Even 15 m can matter when the plume
is 50--100 m above ground, and the workflow here, where terrain effects are
small, is the one you use at hilly sites.

### Step 1: Define the Model Domain

Before running AERMAP, you need to know the geographic extent of your
receptor grid. We will use the domain for the refinery model in Tutorial 8.

**Refinery location (approximate center):**
- Latitude: 29.7350 N
- Longitude: -95.1050 W
- UTM (Universal Transverse Mercator) zone 15N, NAD83 datum: approximately
  X = 279,200 m E, Y = 3,291,700 m N

**Receptor grid extent** (5 km x 5 km centered on the refinery):

| Parameter | Value (UTM meters) |
|---|---|
| X Min | `276,700` |
| X Max | `281,700` |
| Y Min | `3,289,200` |
| Y Max | `3,294,200` |

### Step 2: Obtain DEM Data

AERMAP requires elevation data in GeoTIFF or USGS DEM format. The easiest
approach is to use the USGS 3D Elevation Program (3DEP) data at
1/3 arc-second resolution (~10 m).

**Option A — `DEMDownloader`:** it queries the USGS National Map (TNM)
service and downloads the tiles for a bounding box (south 29.700, north
29.770, west -95.140, east -95.060) into a cache directory; see
[job 8](../use-cases.md#8-elevated-and-complex-terrain-with-aermap) for the
call.

**Option B — Manual download:**

1. Go to the USGS National Map Viewer
   (https://apps.nationalmap.gov/downloader/).
2. Search for your area (Houston Ship Channel).
3. Select **Elevation Products (3DEP)** > **1/3 arc-second DEM**.
4. Download the GeoTIFF tile(s) covering your domain.
5. Save to your working directory.

> **Tip:** For the Houston Ship Channel area, you typically need only one
> or two 1-degree tiles. The files are approximately 50--100 MB each.

### Step 3: Set Up the Project in the GUI

1. Launch `pyaermod-app`.
2. On the **Project** step:
   - Title (line 1): `Tutorial 7 - Terrain Processing`
   - Pollutant: `SO2` (we will use this in Tutorial 8)
   - **Terrain: `Elevated (ELEV)`** (this is the key change from previous tutorials)
   - Averaging periods: `1`, `24`, `ANNUAL`

   The coordinates below are UTM zone 15 north (NAD83) meters. The GUI has
   no setting for the zone; you give it to AERMAP in Step 4.

3. Go to **Sources** and add `FCCSTK` as in Tutorial 8, Step 2 (Source 1),
   with **Base elevation (m)** `0` under **Advanced**. Tutorial 8 replaces
   it with the full source inventory, but AERMAP needs one source.

4. Go to **Receptors** and add a `CartesianGrid`:

   | Parameter | Value |
   |---|---|
   | Grid name | `GRID1` |
   | X init (m) | `276700` |
   | X num | `51` |
   | X delta (m) | `100` |
   | Y init (m) | `3289200` |
   | Y num | `51` |
   | Y delta (m) | `100` |

   This gives a **51 x 51 = 2,601 receptor** grid at 100 m resolution,
   from 276700 to 281700 east and 3289200 to 3294200 north.

5. On the **Project** step, click **Save as...** and save the project as
   `tutorial7.json`. Move the downloaded file into your working directory.

### Step 4: Run AERMAP

AERMAP is a separate executable from AERMOD (from the EPA's SCRAM site). If
it is on your PATH, pyaermod can write the AERMAP input file from your saved
project, run AERMAP and put the elevations into the project. In your
working directory, create `run_terrain.py`:

```python
from pyaermod.gui_v2.project_io import load_project, save_project
from pyaermod.terrain import TerrainProcessor

project = load_project("tutorial7.json")

project = TerrainProcessor().process(
    project,
    bounds=(-95.40, 29.65, -95.15, 29.85),  # west, south, east, north (degrees)
    dem_files=["houston_dem.tif"],           # the DEM file(s) you downloaded
    skip_download=True,
    utm_zone=15,
    datum="NAD83",
    working_dir="aermap_run",
)

save_project(project, "tutorial7_terrain.json")
```

Replace `houston_dem.tif` with the name of your DEM file and run
`python run_terrain.py`. AERMAP runs in the `aermap_run` folder and leaves
its input file and two output files there:

- **Receptor output** — elevation and hill height for each grid point
- **Source output** — base elevation for each source

The script saves a copy of your project with those elevations as
`tutorial7_terrain.json`. If AERMAP stops with an error, see the
[AERMAP troubleshooting guide](../aermap-troubleshooting.md).

If AERMAP stops with an error, see the
[AERMAP troubleshooting guide](../aermap-troubleshooting.md).

### Step 5: Open the Project with Its Elevations

The GUI has no AERMAP import. The elevations arrive with the project file
the script wrote:

1. In the GUI, go to the **Project** step and click **Open...**.
2. Choose `tutorial7_terrain.json`.
3. On the **Sources** step, click **Edit** on `FCCSTK` and open
   **Advanced**: **Base elevation (m)** now holds AERMAP's value.
4. On the **Receptors** step, click **Edit** on the grid and open
   **Advanced**: **Grid elevations** and **Grid hills** show that the grid
   now carries a terrain elevation (`z_elev`) and a controlling hill height
   (`z_hill`) for each receptor. These two are read-only in the GUI.

> **What you should see:**
>
> - Most receptor elevations will be between 0 and 25 meters (the Ship
>   Channel area is low-lying). The deck preview in Step 6 shows them all.
> - Hill heights may be slightly higher, reflecting terrain features within
>   a radius of influence around each receptor.
> - The source base elevation will be close to sea level (likely 3--8 m).

### Step 6: Verify the Terrain Data

With the project open, go to the **Review & Run** step and read the **Deck
preview**. Look for:

1. In the `RE` pathway, `GRIDCART` lines should now include `ELEV` and
   `HILL` rows with varying elevation values (not all zeros).

2. In the `SO` pathway, the `LOCATION` line for your source should have
   a non-zero base elevation.

3. The `MODELOPT` line of the `CO` pathway should contain `ELEV` (not `FLAT`).

> **Compare FLAT vs ELEVATED:** save this project, make a FLAT copy
> (change **Terrain** on the Project step and untick **Regulatory default
> options (DFAULT)**) and compare the two input files: the FLAT one omits
> all elevation data. Run both with the same meteorology and compare the
> maximum concentrations.

### Discussion Questions

1. **Terrain resolution trade-off.** We used 100 m receptor spacing. What
   happens if you use 50 m spacing? (More receptors = more computation time,
   but potentially catches terrain features between the 100 m points.)

2. **Hill height vs terrain elevation.** AERMAP reports both `z_elev`
   (actual ground height at the receptor) and `z_hill` (the highest
   terrain feature influencing the receptor). Why does AERMOD need both?
   (Hint: the "dividing streamline" concept in AERMOD's terrain algorithm.)

3. **Flat areas still matter.** Even though Houston's terrain varies by
   only ~25 m across our domain, that variation could be significant for
   a 50 m stack. Calculate the ratio: (terrain variation) / (effective
   stack height). If this ratio exceeds ~0.1, terrain effects are non-
   negligible.

---

## Tutorial 8: Modeling a Simplified Oil Refinery

**Goal:** Build a complete AERMOD model for a simplified petroleum refinery
near the Houston Ship Channel, including multiple source types, realistic
emission parameters, terrain, meteorology, and regulatory compliance
analysis.

**Time:** 60--90 minutes

**What you'll learn:**
- How to characterize refinery emission sources for AERMOD
- How to combine point, area, and volume sources in a complex facility
- How to use source groups to separate contributions
- How to set up a multi-scale receptor network
- How to perform a regulatory compliance analysis for SO2 and PM2.5
- How to interpret results from a multi-source industrial facility

### Facility Overview

You are modeling a **simplified petroleum refinery** located along the
Houston Ship Channel at approximately:

- **Latitude:** 29.735 N
- **Longitude:** -95.105 W
- **UTM Zone 15N:** X = 279,200 m E, Y = 3,291,700 m N
- **Base elevation:** ~5 m above sea level

The refinery processes 150,000 barrels per day (150 kbpd) of crude oil into
gasoline, diesel, jet fuel and petrochemical feedstocks. Its main sources
(NOx is nitrogen oxides, VOC volatile organic compounds, H2S hydrogen
sulfide, FCC fluid catalytic cracking):

| Unit | Source Type | Primary Pollutant | Description |
|---|---|---|---|
| FCC regenerator stack | Point | SO2, PM2.5 | Fluid Catalytic Cracking unit — burns off catalyst coke |
| Process heater stack #1 | Point | SO2, NOx | Crude unit charge heater |
| Process heater stack #2 | Point | SO2, NOx | Vacuum unit charge heater |
| Boiler stack | Point | SO2, PM2.5 | Steam generation for process heat |
| Flare (ground-level equiv.) | Point | SO2 | Emergency/routine flaring, modeled as a short stack |
| Crude tank farm | Area | VOC | Floating roof tanks with seal losses |
| Product loading rack | Area | VOC | Truck and railcar loading vapors |
| Wastewater treatment | Area | VOC, H2S | API separators and aeration basins |
| Cooling towers | Volume | PM2.5 | Drift from cooling water (mineral salts) |
| Equipment leaks (fugitives) | Volume | VOC | Valves, pumps, flanges throughout process area |

This assignment models **SO2**, which has a 1-hour National Ambient Air
Quality Standard (NAAQS) of 196 µg/m³ (75 ppb). The same steps apply to
PM2.5, NO2 or any other pollutant; only the emission rates and standards
change. A real permit application would have hundreds of sources and
several pollutants; ten sources are enough here to show the main concepts.

### Step 1: Set Up the Project

1. Launch `pyaermod-app`.
2. On the **Project** step:

   | Parameter | Value |
   |---|---|
   | Title (line 1) | `Houston Refinery SO2 Assessment` |
   | Title (line 2) | `Simplified 150 kbpd refinery - Tutorial 8` |
   | Pollutant | `SO2` |
   | Averaging periods | `1`, `3`, `24`, `ANNUAL` |
   | Terrain | `Elevated (ELEV)` |

   All coordinates in this tutorial are UTM zone 15 north (NAD83) meters.

> **Why these averaging periods?** The SO2 NAAQS is a 1-hour standard
> (75 ppb = 196 µg/m³). We also include 3-hour, 24-hour, and annual for
> secondary NAAQS comparison and general analysis. Regulatory practice
> requires demonstrating compliance with all applicable standards.

### Step 2: Define Emission Sources

Go to **Sources** and add the ten sources below one at a time: set **Type**,
click **Add**, fill in the editor and click **Save**. **Base elevation (m)**
is under **Advanced**; it is `5.0` for every source. The process units are
in the center and the tank farms to the south.

**Point sources** (type `PointSource`):

| Source ID | X (m) | Y (m) | Stack height (m) | Stack temp (K) | Exit velocity (m/s) | Stack diameter (m) | Emission rate (g/s) |
|---|---|---|---|---|---|---|---|
| `FCCSTK` | 279200 | 3291750 | 60 | 470 | 20 | 3.0 | 5.0 |
| `HTR1` | 279100 | 3291800 | 40 | 420 | 12 | 1.8 | 2.0 |
| `HTR2` | 279300 | 3291850 | 35 | 410 | 10 | 1.5 | 1.5 |
| `BOILER` | 279050 | 3291600 | 45 | 430 | 14 | 2.0 | 3.0 |
| `FLARE` | 279400 | 3291500 | 15 | 1273 | 20 | 1.0 | 1.0 |

- `FCCSTK` is the FCC regenerator stack, the largest source. Its tall, hot
  plume may put the effective release height at 120--180 m, so expect the
  peak 1--3 km downwind; check this against your results.
- `FLARE` is a short, hot point source, a simplification. Real flares are
  modeled with EPA's flare guidance (flame length, radiative heat loss,
  effective release parameters).

**Area and volume sources:**

| Source ID | Type | X (m) | Y (m) | Release height (m) | Size | Emission rate |
|---|---|---|---|---|---|---|
| `TANKS` | `AreaSource` | 279150 | 3291300 | 15 | X side 200 m, Y side 150 m, angle 0 | 0.000010 g/(s·m²) |
| `LOADRK` | `AreaSource` | 279350 | 3291400 | 4 | X side 80 m, Y side 30 m, angle 0 | 0.000005 g/(s·m²) |
| `WWATER` | `AreaCircSource` | 278900 | 3291400 | 1 | radius 50 m, 20 vertices (**Advanced**) | 0.000030 g/(s·m²) |
| `COOL1` | `VolumeSource` | 279250 | 3291550 | 12 | initial lateral 8 m, initial vertical 6 m | 0.2 g/s |
| `FUGITV` | `VolumeSource` | 279200 | 3291700 | 5 | initial lateral 25 m, initial vertical 4 m | 0.5 g/s |

- For an area source, X and Y are the southwest corner, and AERMOD takes the
  two sides as full lengths, not half-widths. The emission rate is per unit
  area: `TANKS` emits 0.00001 × (200 × 150) = **0.3 g/s** and `WWATER`
  0.00003 × (π × 50²) = **0.24 g/s**.
- For a volume source, the initial lateral dimension (σy) is about the
  source width / 4.3 and the initial vertical dimension (σz) about its
  height / 2.15 (EPA guidance).
- `TANKS`, `LOADRK` and `WWATER` stand for small SO2 releases (fugitive
  losses from sour crude and wastewater); `COOL1` is cooling-tower drift
  and `FUGITV` the aggregate of valve, pump and flange leaks.

### Step 3: Create Source Groups

Source groups report the contribution of different parts of the refinery
separately.

A source belongs to the groups named in its **Source groups** field. There
is no separate list of groups to create:

1. On the **Sources** step, click **Edit** on a source and open **Advanced**.
2. In **Source groups**, type the source's groups, one name per line
   (`FCCSTK` gets two lines: `STACKS` and `FCCONLY`), and click **Save**.
3. Repeat for every source, so that the groups come out as:

| Group Name | Sources | What It Represents |
|---|---|---|
| `STACKS` | FCCSTK, HTR1, HTR2, BOILER, FLARE | All elevated point sources |
| `FUGITIV` | TANKS, LOADRK, WWATER, FUGITV | All fugitive/area/volume sources |
| `FCCONLY` | FCCSTK | FCC unit alone (largest single source) |
| `ALL` | All 10 sources | Total facility impact |

Do not type `ALL`: AERMOD's `ALL` group holds every source, and pyaermod
writes it for you.

> If a regulator asks what a scrubber on the FCC unit would do, compare the
> `FCCONLY` results before and after, without rerunning the other sources.

### Step 4: Set Up a Multi-Scale Receptor Network

Three receptor sets cover the near-field peak and the wider impact area:

#### Receptor Set 1 — Fine Grid (Near-Field)

On the **Receptors** step, add a `CartesianGrid`:

| Parameter | Value |
|---|---|
| Grid name | `FINE` |
| X init (m) | `278200` |
| X num | `41` |
| X delta (m) | `50` |
| Y init (m) | `3290700` |
| Y num | `41` |
| Y delta (m) | `50` |

This gives a **41 x 41 = 1,681 receptor** grid at 50 m spacing, covering
a 2 km x 2 km area centered on the refinery.

#### Receptor Set 2 — Coarse Grid (Far-Field)

Add a second `CartesianGrid`:

| Parameter | Value |
|---|---|
| Grid name | `COARSE` |
| X init (m) | `276700` |
| X num | `26` |
| X delta (m) | `200` |
| Y init (m) | `3289200` |
| Y num | `26` |
| Y delta (m) | `200` |

This gives a **26 x 26 = 676 receptor** grid at 200 m spacing, covering
a 5 km x 5 km area.

#### Receptor Set 3 — Discrete Sensitive Receptors

Discrete receptors stand for nearby communities, schools and monitors.

1. Set **Type** to `DiscreteReceptor` and click **Add** once for each row,
   entering **Label**, **X coord (m)** and **Y coord (m)**:

| Label | X | Y | What It Represents |
|---|---|---|---|
| `Community NW` | `278100` | `3292500` | Residential neighborhood NW of refinery |
| `Community NE` | `280300` | `3292400` | Neighborhood NE of refinery |
| `Community S` | `279200` | `3290200` | Neighborhood south of Ship Channel |
| `School` | `278500` | `3293000` | Elementary school, 1.5 km NW |
| `Hospital` | `280000` | `3292800` | Medical center, 1.2 km NE |
| `Monitor` | `279500` | `3292200` | Air quality monitoring station |

> Total: 1,681 + 676 + 6 = **2,363 receptors**.

### Step 5: Connect Meteorology

1. Go to **Meteorology**.
2. Under **Met files**, enter the full paths to your Houston `.sfc` and
   `.pfl` files from Tutorial 6:
   - Surface file: `houston_2023.sfc`
   - Profile file: `houston_2023.pfl`
3. Under **Stations**, enter **Surface station ID** `12918`, **Upper air
   station ID** `72240` and **Data start year** `2023`.

### Step 6: Import Terrain Data (Optional but Recommended)

If you completed Tutorial 7:

1. Save the project (**Project** step, **Save as...**) as
   `refinery_project.json` in your working directory.
2. Run your `run_terrain.py` script from Tutorial 7 with the two file names
   changed: load `refinery_project.json` and save
   `refinery_terrain.json`.
3. Open `refinery_terrain.json` in the GUI (**Project** step, **Open...**)
   and verify in the **Review & Run** step's deck preview that elevations
   have been applied.

If you did not complete Tutorial 7, you can proceed with FLAT terrain by
changing **Terrain** to `Flat (FLAT)` on the Project step and unticking
**Regulatory default options (DFAULT)**. The results will be
slightly different but the analysis workflow is the same.

### Step 7: Configure Output

1. Go to the **Output** step.
2. Under **Files for the Results step**, leave both boxes ticked:
   - **Plot file for every averaging period** — the Results step draws its
     map from these.
   - **POSTFILE for every averaging period** — needed for the POSTFILE
     analysis in Step 9D. The 1-hour POSTFILE of this model holds about 20
     million values and takes on the order of a gigabyte or more; untick
     the box if you skip 9D.
3. Under **Tables in the .out file**, leave **Receptor table** and **Max
   table** ticked.

These files are for the source group `ALL`. The GUI cannot add plot files
for the other source groups. You do not need them here: AERMOD's `.out`
file reports the highest values of every source group, and the Results
step shows them under **Summary tables**.

### Step 8: Review and Run

1. Go to **Review & Run** and read the **Readiness checklist**.

   Common issues at this stage:
   - Missing meteorological file paths, or paths that are not full paths
   - Source ID longer than 8 characters
   - A source placed outside the receptor grid by a typing mistake (the
     checklist does not catch this: check the plan view on the Sources
     step, where all sources should fall within the FINE grid)

2. **Read the Deck preview** and verify:
   - 10 sources in the SO pathway (5 POINT, 2 AREA, 1 AREACIRC, 2 VOLUME)
   - 4 source groups defined (`SRCGROUP` lines for ALL, STACKS, FUGITIV,
     FCCONLY)
   - Receptor grids FINE and COARSE plus 6 discrete receptors
   - Correct met file paths

3. Set the **Working directory** and click **Run AERMOD**.

> **Runtime:** with about 2,400 receptors, 10 sources and 8,760 hours of
> meteorology, expect roughly 5--15 minutes, depending on your computer.

### Step 9: Analyze the Results

Once AERMOD completes, go to the **Results** step.

#### 9A. Concentration Map

1. In **Map shows**, select the 1-hour plot file.
2. Observe the spatial pattern:
   - The plume should extend primarily to the **north-northwest** (downwind
     of the prevailing south-southeast winds in Houston).
   - The maximum 1-hour concentration will be located 0.5--2 km downwind
     of the tallest stacks.
3. Switch to the **ANNUAL** plot file. The pattern should be more symmetric
   because annual averages include winds from all directions.
4. The map has no street or satellite background. To see the pattern over
   the Ship Channel and the surrounding neighborhoods, click **Download
   KMZ** (under **Downloads**; enter UTM zone `15`) and open the file in
   Google Earth. The KMZ download needs pyproj: `pip install pyproj`.

#### 9B. Regulatory Compliance

Use the **Maximum for each averaging period**, **Comparison with the
NAAQS** and **Summary tables** sections to answer these questions:

**Question 1: Does the refinery comply with the SO2 1-hour NAAQS?**

The SO2 1-hour standard is **196 µg/m³** (equivalent to 75 ppb).

- What does the **Comparison with the NAAQS** table report for the 1-hour
  standard, and which value did it compare (the **Value from** column)?
- How many receptors exceed this standard? Download the 1-hour plot file
  from **Downloads**: it is a text file with one row per receptor (X, Y
  and the highest 1-hour concentration there). Open it in a spreadsheet
  and count the rows above `196`.
- What is the maximum 1-hour concentration?
- Where is the maximum located (coordinates)?

> **Regulatory context:** Under EPA's Guideline on Air Quality Models, a
> facility demonstrates compliance if the modeled concentration (including
> background) does not exceed the NAAQS at any receptor. For SO2, the
> "design value" is the 99th percentile of daily maximum 1-hour values
> averaged over 3 years.

**Question 2: What is the maximum annual average?**

There is no annual SO2 NAAQS (it was revoked in 2010), but the annual
average is useful for understanding chronic exposure.

- What is the maximum annual concentration?
- At which receptor?
- How does it compare to the 1-hour maximum? (It should be much smaller.)

**Question 3: Sensitive receptor analysis.**

Check the concentrations at each discrete receptor. Find each receptor's
row, by its coordinates, in the plot file of each averaging period
(**Downloads**):

| Receptor | 1-hr Max | 24-hr Max | Annual | Above NAAQS? |
|---|---|---|---|---|
| Community NW | | | | |
| Community NE | | | | |
| Community S | | | | |
| School | | | | |
| Hospital | | | | |
| Monitor | | | | |

Which sensitive receptor has the highest impact? Is this consistent with
the wind direction pattern you observed on the map?

#### 9C. Source Group Analysis

The **Summary tables** section lists the highest values of every source
group (the group column), read from AERMOD's `.out` file:

**Question 4: Source contribution analysis.**

Compare the maximum 1-hour concentrations from each source group:

| Source Group | Max 1-hr (µg/m³) | % of Total |
|---|---|---|
| ALL (total) | | 100% |
| STACKS | | |
| FUGITIV | | |
| FCCONLY | | |

- What percentage of the total impact comes from stacks vs fugitive sources?
- What percentage comes from the FCC unit alone?
- If you could eliminate the FCC stack emissions entirely, would the
  remaining sources still comply with the NAAQS?

#### 9D. POSTFILE Analysis (Advanced)

If you enabled POSTFILE output:

The GUI has no POSTFILE viewer; this part uses Python. The 1-hour POSTFILE
is listed under **Downloads** with its path on disk (`pyaermod_01H.pst` in
the run's working directory).

1. Read the POSTFILE and find the hour with the highest concentration:

```python
from pyaermod.postfile import read_postfile

post = read_postfile("pyaermod_01H.pst")   # use the path from Downloads
values = post.to_dataframe()               # columns x, y, concentration, date ...
peak = values.loc[values["concentration"].idxmax()]
print(peak)                                # date is YYMMDDHH
```

2. What were the meteorological conditions during this hour? (You can check
   the `.sfc` file for the matching date/time.)
3. Use `post.get_timestep("YYMMDDHH")` (the date as text) to get the
   concentrations at every receptor for one hour. Look at the hours of the
   day that includes the peak: how does the pattern move through the day?

### Step 10: Sensitivity Analysis (Assignment Extension)

Change one thing per run.

#### Scenario A: Taller FCC Stack

Change the FCC stack height from 60 m to 90 m. Keep everything else the same.

- How does the maximum 1-hour concentration change?
- How does the location of the maximum shift?
- Is this consistent with what you learned in Tutorial 2?

#### Scenario B: Reduced Emission Rate

Simulate the effect of installing a flue gas desulfurization (FGD) scrubber
on the FCC unit. Reduce the FCC emission rate from 5.0 g/s to 1.0 g/s
(80% removal efficiency).

- What is the new maximum 1-hour concentration?
- Does the facility now comply at all receptors?

#### Scenario C: Background Concentration

Real air carries background SO2 from regional sources. The GUI cannot enter
a background concentration; add one to a saved project from Python:

1. Save the project as `refinery_project.json` (**Project** step, **Save
   as...**).
2. Run this script in the same folder:

```python
from pyaermod.gui_v2.project_io import load_project, save_project
from pyaermod.input_generator import BackgroundConcentration

project = load_project("refinery_project.json")
project.sources.background = BackgroundConcentration(uniform_value=10.0)  # µg/m³
save_project(project, "refinery_background.json")
```

3. Open `refinery_background.json` in the GUI (**Open...**). The deck
   preview now has a `BACKGRND` line. Run it.

- How does the background change the compliance picture?
- At what background level would the facility fail to comply (if it didn't
  already)?

#### Scenario D: Flat vs Elevated Terrain

If you have terrain data from Tutorial 7, run the model with both FLAT
and ELEVATED terrain:

- What is the maximum concentration difference between the two terrain modes?
- Where do the differences occur? (Hint: look at receptors on higher terrain.)

---

## Assignment Deliverables

Submit the following files and documents:

### From Tutorial 6 (AERMET)
- [ ] Two AERMET input files (`aermet_houston_s1.inp`, `aermet_houston_s3.inp`)
- [ ] Written answers to the three Discussion Questions
- [ ] Brief description of the monthly surface parameter choices and
  rationale

### From Tutorial 7 (Terrain)
- [ ] Screenshot of the Review & Run step's deck preview showing the
  receptor grid's `ELEV` and `HILL` rows with AERMAP's elevations
- [ ] Comparison of FLAT vs ELEVATED generated input files (highlight
  differences)
- [ ] Written answers to the three Discussion Questions

### From Tutorial 8 (Refinery Model)
- [ ] Project JSON file (`refinery_project.json`) — saved from the GUI
  (**Save as...**)
- [ ] Generated AERMOD input file (`refinery.inp`) — **Download deck** on the
  Review & Run step, renamed
- [ ] Technical report (3--5 pages):
  - Introduction: the facility, pollutant and modeling objectives
  - Model configuration: source inventory table, receptor network,
    meteorology, terrain
  - Results: answers to Questions 1--4, with maps from the Results step and
    a compliance table
  - Sensitivity analysis: Scenarios A--D and what they show about control
    strategies
  - Conclusions: does the refinery comply with the SO2 NAAQS, and what would
    you recommend if it does not

### Grading Rubric

| Component | Points | Criteria |
|---|---|---|
| AERMET configuration (Tutorial 6) | 15 | Correct station selection, appropriate surface parameters, answers to discussion questions |
| Terrain processing (Tutorial 7) | 15 | Successful AERMAP run, imported elevations, FLAT vs ELEVATED comparison |
| Source inventory (Tutorial 8, Steps 1--3) | 20 | All 10 sources correctly entered with realistic parameters, source groups defined |
| Receptor network (Tutorial 8, Step 4) | 10 | Multi-scale grid design, appropriate sensitive receptor placement |
| Compliance analysis (Tutorial 8, Step 9) | 20 | Correct NAAQS comparison, receptor-specific analysis, source contribution breakdown |
| Sensitivity analysis (Tutorial 8, Step 10) | 10 | At least two scenarios completed with clear interpretation |
| Report quality | 10 | Clear writing, professional tables/figures, sound engineering judgment |
| **Total** | **100** | |

---

## Supplemental Reference Tables

### Typical Refinery Emission Rates (SO2, g/s)

Teaching estimates for a 150 kbpd refinery burning low-sulfur fuel gas
(50--150 ppm H2S), not measured data. Actual rates depend on sulfur
content, controls and operating conditions.

| Source | Typical SO2 (g/s) | Range |
|---|---|---|
| FCC regenerator | 3--8 | With electrostatic precipitator / third-stage separator |
| Process heater (large) | 1--4 | Depends on fuel sulfur content |
| Process heater (small) | 0.5--2 | |
| Boiler | 1--5 | Depends on fuel type and controls |
| Flare (normal) | 0.2--2 | Much higher during upset conditions |
| Tank farm (fugitive) | 0.05--0.5 | Total; primarily H2S oxidized to SO2 |
| Cooling tower | 0.01--0.3 | Drift PM, minimal SO2 |

NAAQS values are in the `pyaermod.naaqs` module ([reference](../api/naaqs.md)).

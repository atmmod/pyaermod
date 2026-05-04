# Houston Refinery Modeling Assignments

Advanced tutorials for the PyAERMOD GUI: from meteorological preprocessing
through terrain processing to a complete oil refinery dispersion model.

These three tutorials build on [Tutorials 1--5](student-guide.md) and assume
you are comfortable with the PyAERMOD GUI, point/area sources, receptor grids,
and basic AERMET concepts.

---

## Table of Contents

1. [Tutorial 6 — AERMET for Houston, Texas](#tutorial-6--aermet-for-houston-texas)
2. [Tutorial 7 — Terrain Processing with AERMAP](#tutorial-7--terrain-processing-with-aermap)
3. [Tutorial 8 — Modeling a Simplified Oil Refinery](#tutorial-8--modeling-a-simplified-oil-refinery)
4. [Assignment Deliverables](#assignment-deliverables)
5. [Supplemental Reference Tables](#supplemental-reference-tables)

---

## Tutorial 6 — AERMET for Houston, Texas

**Goal:** Generate a complete set of AERMOD-ready meteorological files
(`.sfc` and `.pfl`) for the Houston Ship Channel area using real station
data and site-appropriate surface parameters.

**Time:** 40--50 minutes

**What you'll learn:**
- How to identify surface and upper air stations for a specific location
- How Gulf Coast meteorology differs from inland sites
- How to select monthly surface parameters for an industrial/coastal setting
- How to run all three AERMET stages and verify the output

### Background: Why Houston?

The Houston Ship Channel and surrounding area contains one of the largest
concentrations of petroleum refining and petrochemical manufacturing in the
world. The meteorology of this region is distinctive:

- **Prevailing winds** from the south-southeast (Gulf of Mexico) during
  summer, rotating to northerly during winter cold fronts.
- **High humidity** year-round reduces the Bowen ratio compared to arid
  inland sites.
- **Sea-breeze circulation** can reverse wind direction along the coast
  during afternoon hours, recirculating pollutants back over populated areas.
- **Atmospheric stability** is frequently unstable during summer days (strong
  solar heating) but can become very stable during clear winter nights.

These characteristics make Houston a challenging and instructive location for
air quality modeling.

### Step 1: Identify the Meteorological Stations

For a refinery near the Houston Ship Channel (approximately 29.75 N,
95.10 W), we need two weather stations:

#### Surface Station — Houston Hobby Airport (KHOU)

| Parameter | Value | Notes |
|---|---|---|
| Station ID | `KHOU` | ICAO code; WBAN 12918 |
| Station Name | `Houston Hobby Airport` | |
| Latitude | `29.6454` | Decimal degrees |
| Longitude | `-95.2789` | Negative = west |
| Time Zone (UTC offset) | `-6` | Central Standard Time |
| Elevation (m) | `14.0` | Near sea level — typical for coastal Houston |
| Anemometer Height (m) | `10.0` | Standard |
| Data Format | `ISHD` | NOAA Integrated Surface Hourly Data |

> **Why Hobby instead of Intercontinental?** Houston Hobby Airport (KHOU) is
> closer to the Ship Channel and more representative of the coastal/industrial
> area. George Bush Intercontinental (KIAH) is 35 km north-northwest and sits
> in a more suburban/forested environment with different roughness and moisture
> characteristics.

#### Upper Air Station — Lake Charles, Louisiana

| Parameter | Value | Notes |
|---|---|---|
| Station ID | `72240` | WMO station number |
| Station Name | `Lake Charles, LA` | |
| Latitude | `30.1200` | |
| Longitude | `-93.2200` | |

> **Why Lake Charles?** It is the closest radiosonde station to Houston
> (~200 km east). The only alternative would be Corpus Christi (~330 km
> southwest). Lake Charles is more representative of the Houston area's
> upper-atmosphere conditions because it shares the Gulf Coast environment.

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

### Step 2: Configure Stage 1 in the GUI

1. Launch `pyaermod-app`.
2. On **Project Setup**, set:
   - UTM Zone: `15`
   - Hemisphere: `N`
   - Datum: `NAD83`
   - Map Center Latitude: `29.75`
   - Map Center Longitude: `-95.10`
3. Go to **Meteorology** and select **Configure AERMET**.
4. On the **Stage 1** tab, enter all the surface and upper air station
   parameters from the tables above.
5. Enter the data file paths and date range.
6. Click **Save Stage 1 Configuration**.
7. Expand **Preview Stage 1 Input** and verify the keywords.

> **Check yourself:** The preview should contain:
> - A `SURFACE` block with `DATA khou_2023.dat ISHD`
> - An `UPPERAIR` block with `DATA 72240_2023.dat FSL`
> - An `XDATES` line showing `2023/01/01 TO 2023/12/31`

8. Click **Download Stage 1 Input File** — save as `aermet_houston_s1.inp`.

### Step 3: Configure Stage 2

1. Click the **Stage 2** tab.
2. Enter the filenames that Stage 1 will produce:

   | Parameter | Value |
   |---|---|
   | Surface Extract File | `khou_extract.sfc` |
   | Upper Air Extract File | `lch_extract.ua` |
   | Start Date | `2023/01/01` |
   | End Date | `2023/12/31` |
   | Merge Output File | `houston_merged.mrg` |

3. Save and download as `aermet_houston_s2.inp`.

### Step 4: Configure Stage 3 — Houston Surface Parameters

This is where your knowledge of the Houston area matters. The land around the
Ship Channel is a mix of **industrial facilities, port infrastructure, open
water, and coastal grassland**. This is very different from the suburban
defaults in the GUI.

1. Click the **Stage 3** tab.
2. Enter file paths:

   | Parameter | Value |
   |---|---|
   | Merge File | `houston_merged.mrg` |
   | Start Date | `2023/01/01` |
   | End Date | `2023/12/31` |
   | Surface Output | `houston_2023.sfc` |
   | Profile Output | `houston_2023.pfl` |

3. **Edit the monthly surface parameters table** using the Houston-specific
   values below:

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

> **Key differences from the suburban defaults (Tutorial 5):**
>
> - **Lower albedo** (0.14--0.18 vs 0.15--0.35): Houston's dark industrial
>   surfaces, asphalt, and green vegetation absorb more sunlight than light-
>   colored suburban roofs and snow cover.
> - **Lower Bowen ratio** (0.3--0.8 vs 0.5--1.5): The Gulf Coast moisture
>   keeps latent heat flux high. Moist surfaces partition more energy into
>   evaporation than sensible heating.
> - **Higher roughness** (0.40--0.60 vs 0.30--0.50): The industrial Ship
>   Channel area has large structures (tanks, stacks, buildings) that create
>   more aerodynamic drag than low-rise suburban neighborhoods.

4. Leave the **Use Stage 1 surface station** checkbox checked.
5. Save and download as `aermet_houston_s3.inp`.

### Step 5: Run AERMET

In a terminal, run the three stages in order:

```bash
aermet < aermet_houston_s1.inp
aermet < aermet_houston_s2.inp
aermet < aermet_houston_s3.inp
```

When Stage 3 completes, you should have `houston_2023.sfc` and
`houston_2023.pfl` in your working directory.

### Step 6: Verify the Output

Return to the GUI:

1. Go to **Meteorology** and switch to **Use Existing Files**.
2. Enter the paths to `houston_2023.sfc` and `houston_2023.pfl`.

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

### Checkpoint

- [x] Surface and upper air station selection for a specific area
- [x] How Gulf Coast climate affects surface parameter choices
- [x] The role of albedo, Bowen ratio, and roughness in boundary layer
  calculations
- [x] Running AERMET and verifying the output files
- [x] Why station representativeness matters for regulatory modeling

---

## Tutorial 7 — Terrain Processing with AERMAP

**Goal:** Use the PyAERMOD GUI and AERMAP to assign terrain elevations to
all receptors and sources for a model domain near the Houston Ship Channel.

**Time:** 30--40 minutes

**What you'll learn:**
- Why terrain elevation matters even in "flat" areas like Houston
- How to download digital elevation model (DEM) data
- How to run AERMAP to compute receptor and source elevations
- How to import AERMAP results back into the GUI
- The difference between FLAT and ELEVATED terrain modes in AERMOD

### Conceptual Background

In Tutorials 1--5, we used FLAT terrain — meaning every receptor and source
sat at elevation zero. This is a simplification. In reality, even modest
elevation differences can affect concentrations:

- **Elevated receptors** (on a hill or ridge) can intercept the plume at
  a height closer to the effective plume centerline, increasing concentrations.
- **Depressed receptors** (in a valley) may be partially shielded, but
  channeling effects can concentrate pollutants.
- **Source base elevation** determines where the plume originates relative to
  the surrounding terrain.

AERMAP is the terrain preprocessor that extracts elevation data from digital
elevation models (DEMs) and assigns:

1. **Receptor terrain elevation** (`z_elev`) — ground height at each receptor.
2. **Receptor hill height** (`z_hill`) — the controlling hill height that
   AERMOD uses for terrain-aware plume calculations.
3. **Source base elevation** — ground height at each emission source.

```
Digital Elevation Model (DEM)
         |
    AERMAP preprocessor
         |
    +-----------------+
    | z_elev, z_hill  |  --> Receptor elevations
    | for each        |  --> Source base elevations
    | receptor/source |
    +-----------------+
         |
    Import into AERMOD project
```

### Why Bother Near Houston?

Houston is coastal and mostly flat, but "flat" is relative:

- The Ship Channel itself sits near sea level (0--5 m elevation).
- Surrounding neighborhoods are 10--25 m above sea level.
- The terrain rises gradually to 30--50 m northwest of the city.
- Even a 15 m elevation difference can influence concentrations when the
  plume effective height is 50--100 m.

For regulatory work, EPA requires terrain processing for virtually all
analyses. Learning the workflow here — where terrain effects are small —
prepares you for mountainous or hilly sites where terrain is critical.

### Step 1: Define the Model Domain

Before running AERMAP, you need to know the geographic extent of your
receptor grid. We will use the domain for the refinery model in Tutorial 8.

**Refinery location (approximate center):**
- Latitude: 29.7350 N
- Longitude: -95.1050 W
- UTM Zone 15N: approximately X = 279,200 m E, Y = 3,291,700 m N

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

**Option A — PyAERMOD's built-in downloader (if available):**

PyAERMOD includes a `DEMDownloader` class that can query the USGS TNM API
and download the needed tiles automatically. Your instructor may provide
a script or notebook for this. The downloader needs:

- Bounding box in latitude/longitude
- South: 29.700
- North: 29.770
- West: -95.140
- East: -95.060
- A local cache directory for downloaded tiles

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
2. On **Project Setup**:
   - Title: `Tutorial 7 - Terrain Processing`
   - UTM Zone: `15`, Hemisphere: `N`, Datum: `NAD83`
   - Map Center: Lat `29.735`, Lon `-95.105`
   - Pollutant: `SO2` (we will use this in Tutorial 8)
   - **Terrain Type: `ELEVATED`** (this is the key change from previous tutorials)
   - Averaging Periods: `1-HR`, `24-HR`, `ANNUAL`

3. Go to **Source Editor** and add a placeholder point source at the
   refinery center. We will replace this with the full source inventory in
   Tutorial 8, but AERMAP needs at least one source to process.

   | Parameter | Value |
   |---|---|
   | Source ID | `FCCSTK` |
   | X Coordinate | `279200` |
   | Y Coordinate | `3291700` |
   | Base Elevation | `0` |
   | Stack Height | `60` |
   | Exit Temperature | `470` |
   | Exit Velocity | `20` |
   | Stack Diameter | `3.0` |
   | Emission Rate | `5.0` |

4. Go to **Receptor Editor** and add the Cartesian grid:

   | Parameter | Value |
   |---|---|
   | X Min | `276700` |
   | X Max | `281700` |
   | Y Min | `3289200` |
   | Y Max | `3294200` |
   | Spacing | `100` |

   This gives a **51 x 51 = 2,601 receptor** grid at 100 m resolution.

### Step 4: Run AERMAP

AERMAP is a separate executable from AERMOD (download from EPA SCRAM). The
process differs slightly depending on how your instructor has set things up:

**Option A — Using PyAERMOD's terrain module (recommended):**

If the AERMAP executable is installed:

1. PyAERMOD can generate the AERMAP input file from your project
   configuration.
2. The AERMAP input references your DEM files and the receptor/source
   coordinates from the GUI.
3. Run AERMAP, which produces two output files:
   - **Receptor output** — elevation and hill height for each grid point
   - **Source output** — base elevation for each source

**Option B — Command line:**

Your instructor may provide the AERMAP input file. Run it as:

```bash
aermap < aermap_houston.inp
```

AERMAP typically runs in under a minute for a domain this size.

### Step 5: Import AERMAP Results into the GUI

1. Go to **Receptor Editor**.
2. Click the **AERMAP Elevation Import** tab (the fifth tab).
3. Upload the **receptor output file** from AERMAP.
   - The GUI will match each receptor by (x, y) coordinates (within 0.5 m
     tolerance).
   - Each receptor will be updated with its terrain elevation (`z_elev`)
     and controlling hill height (`z_hill`).
4. Upload the **source output file** from AERMAP.
   - Each source's base elevation will be updated automatically.

> **What you should see:**
>
> - Most receptor elevations will be between 0 and 25 meters (the Ship
>   Channel area is low-lying).
> - Hill heights may be slightly higher, reflecting terrain features within
>   a radius of influence around each receptor.
> - The source base elevation will be close to sea level (likely 3--8 m).

### Step 6: Verify the Terrain Data

After importing, go to the **Run AERMOD** page and expand the **Generated
Input File**. Look for:

1. In the `RE` pathway, `GRIDCART` lines should now include `ELEV` and
   `HILL` rows with varying elevation values (not all zeros).

2. In the `SO` pathway, the `LOCATION` line for your source should have
   a non-zero base elevation.

3. The `CO` pathway should contain `MODELOPT DFAULT ELEV` (not `FLAT`).

> **Compare FLAT vs ELEVATED:** If you save this project and create a
> FLAT-terrain copy (change Terrain Type on Project Setup), you can compare
> the two input files. The FLAT version omits all elevation data. When you
> run both through AERMOD with the same meteorology, the ELEVATED version
> will typically produce slightly higher maximum concentrations because
> nearby terrain "lifts" some receptors closer to the plume centerline.

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

### Checkpoint

- [x] Why even modest terrain matters for regulatory modeling
- [x] How to obtain DEM data for a project domain
- [x] How AERMAP processes DEMs to produce receptor/source elevations
- [x] How to import AERMAP output into the GUI
- [x] The difference between FLAT and ELEVATED terrain modes in AERMOD

---

## Tutorial 8 — Modeling a Simplified Oil Refinery

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

The refinery processes 150,000 barrels per day of crude oil into gasoline,
diesel, jet fuel, and petrochemical feedstocks. Its main emission sources
include:

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

For this assignment, we will model **SO2** as the primary pollutant. SO2 is
a classic refinery pollutant with a clear 1-hour NAAQS (196 ug/m3, the
equivalent of 75 ppb). The principles apply equally to PM2.5, NO2, or any
other pollutant — only the emission rates and standards change.

> **Real-world note:** An actual refinery permit application would include
> hundreds of emission sources and multiple pollutants. We simplify to
> ~10 sources to keep the assignment manageable while demonstrating all the
> key concepts.

### Step 1: Project Setup

1. Launch `pyaermod-app`.
2. On **Project Setup**:

   | Parameter | Value |
   |---|---|
   | Title Line 1 | `Houston Refinery SO2 Assessment` |
   | Title Line 2 | `Simplified 150 kbpd refinery - Tutorial 8` |
   | UTM Zone | `15` |
   | Hemisphere | `N` |
   | Datum | `NAD83` |
   | Map Center Lat | `29.735` |
   | Map Center Lon | `-95.105` |
   | Pollutant | `SO2` |
   | Terrain Type | `ELEVATED` |
   | Averaging Periods | `1-HR`, `3-HR`, `24-HR`, `ANNUAL` |

> **Why these averaging periods?** The SO2 NAAQS is a 1-hour standard
> (75 ppb = 196 ug/m3). We also include 3-hour, 24-hour, and annual for
> secondary NAAQS comparison and general analysis. Regulatory practice
> requires demonstrating compliance with all applicable standards.

### Step 2: Define Emission Sources

Now add all the refinery sources. Go to **Source Editor** and add them one
at a time in the order below. The refinery is oriented roughly north-south
along the Ship Channel, with process units in the center and tank farms to
the south.

#### Source 1 — FCC Regenerator Stack (FCCSTK)

The fluid catalytic cracking (FCC) unit is the largest single SO2 source
at most refineries. The regenerator burns coke off the catalyst, releasing
SO2, CO, and particulate matter through a tall stack.

Source type: **Point**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `FCCSTK` | FCC regenerator stack |
| X Coordinate | `279200` | Center of the process area |
| Y Coordinate | `3291750` | |
| Base Elevation | `5.0` | Near sea level |
| Stack Height | `60.0` | Tall stack — regulatory requirement for FCC units |
| Exit Temperature | `470.0` | Hot regenerator flue gas (~197 C) |
| Exit Velocity | `20.0` | High velocity through large stack |
| Stack Diameter | `3.0` | Large diameter for high flow volume |
| Emission Rate | `5.0` | 5 g/s SO2 — major source |

> **Intuition:** The FCC stack is the "big gun" of the refinery. Its tall
> stack and hot exhaust give it substantial plume rise (the effective release
> height could be 120--180 m), so peak ground-level impacts will be
> 1--3 km downwind despite the high emission rate.

#### Source 2 — Process Heater #1 (HTR1)

Crude unit charge heater — burns refinery fuel gas to heat crude oil.

Source type: **Point**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `HTR1` | Crude unit heater |
| X Coordinate | `279100` | West of FCC, within process area |
| Y Coordinate | `3291800` | |
| Base Elevation | `5.0` | |
| Stack Height | `40.0` | Shorter than FCC — typical for heaters |
| Exit Temperature | `420.0` | Hot flue gas (~147 C) |
| Exit Velocity | `12.0` | Moderate velocity |
| Stack Diameter | `1.8` | Smaller than FCC |
| Emission Rate | `2.0` | 2 g/s SO2 |

#### Source 3 — Process Heater #2 (HTR2)

Vacuum unit charge heater — similar to Heater #1 but slightly smaller.

Source type: **Point**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `HTR2` | Vacuum unit heater |
| X Coordinate | `279300` | East of FCC |
| Y Coordinate | `3291850` | |
| Base Elevation | `5.0` | |
| Stack Height | `35.0` | Slightly shorter |
| Exit Temperature | `410.0` | |
| Exit Velocity | `10.0` | |
| Stack Diameter | `1.5` | |
| Emission Rate | `1.5` | 1.5 g/s SO2 |

#### Source 4 — Boiler Stack (BOILER)

Package boiler generating steam for process heat and utilities.

Source type: **Point**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `BOILER` | Utility boiler |
| X Coordinate | `279050` | Utility area, west side of refinery |
| Y Coordinate | `3291600` | South of process area |
| Base Elevation | `5.0` | |
| Stack Height | `45.0` | Mid-height industrial stack |
| Exit Temperature | `430.0` | |
| Exit Velocity | `14.0` | |
| Stack Diameter | `2.0` | |
| Emission Rate | `3.0` | 3 g/s SO2 — second-largest source |

#### Source 5 — Flare (FLARE)

The refinery's ground-level flare (modeled as a short elevated point source
for simplicity). During normal operations, the flare burns small amounts of
waste gas. During upsets, emissions can be much higher.

Source type: **Point**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `FLARE` | Ground flare |
| X Coordinate | `279400` | East side of refinery, away from process units |
| Y Coordinate | `3291500` | |
| Base Elevation | `5.0` | |
| Stack Height | `15.0` | Low effective height for ground flare |
| Exit Temperature | `1,273.0` | Very hot (~1000 C) — combustion temperature |
| Exit Velocity | `20.0` | High exit velocity |
| Stack Diameter | `1.0` | |
| Emission Rate | `1.0` | 1 g/s SO2 — normal operations |

> **Note on flare modeling:** In real regulatory work, flares are modeled
> using EPA's flare modeling guidance, which accounts for flame length,
> radiative heat loss, and effective release parameters. Our simplified
> point source is an approximation suitable for teaching.

#### Source 6 — Crude Tank Farm (TANKS)

A rectangular area of large floating-roof crude oil storage tanks.
The emission rate represents fugitive losses through the floating roof
seals. For this SO2 model, we use a small emission rate representing
H2S/SO2 emissions from sour crude storage.

Source type: **Area (Rectangular)**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `TANKS` | Crude tank farm |
| X Coordinate | `279150` | Center of the tank farm |
| Y Coordinate | `3291300` | South of the process area |
| Base Elevation | `5.0` | |
| Release Height | `15.0` | Tank top height (~15 m for large tanks) |
| Half-Width Y | `75.0` | 150 m total north-south |
| Half-Width X | `100.0` | 200 m total east-west |
| Rotation Angle | `0` | Aligned with grid |
| Emission Rate | `0.000010` | 0.00001 g/s/m2 — small fugitive rate |

> **Emission rate calculation:**
> Area = 150 m x 200 m = 30,000 m2.
> Total emission = 0.00001 x 30,000 = **0.3 g/s** from the entire tank farm.
> This is small compared to the stacks — fugitive SO2 from tanks is minor.

#### Source 7 — Loading Rack (LOADRK)

The truck/railcar loading area where refined products are loaded for
distribution. Vapor displacement during loading produces emissions.

Source type: **Area (Rectangular)**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `LOADRK` | Product loading rack |
| X Coordinate | `279350` | East side of the refinery |
| Y Coordinate | `3291400` | |
| Base Elevation | `5.0` | |
| Release Height | `4.0` | Vehicle height |
| Half-Width Y | `15.0` | 30 m north-south |
| Half-Width X | `40.0` | 80 m east-west |
| Rotation Angle | `0` | |
| Emission Rate | `0.000005` | 0.000005 g/s/m2 — very low SO2 |

#### Source 8 — Wastewater Treatment (WWATER)

The wastewater treatment area includes API oil-water separators and
aeration basins. H2S and SO2 can be released from exposed water surfaces.

Source type: **Area (Circular)**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `WWATER` | Wastewater treatment |
| X Coordinate | `278900` | West side, buffered from process area |
| Y Coordinate | `3291400` | |
| Base Elevation | `5.0` | |
| Release Height | `1.0` | At ground level (open basins) |
| Radius | `50.0` | 50 m radius circular treatment area |
| Num Vertices | `20` | |
| Emission Rate | `0.000030` | 0.00003 g/s/m2 |

> **Emission rate calculation:**
> Area = pi x 50^2 = ~7,854 m2.
> Total emission = 0.00003 x 7,854 = **0.24 g/s**.

#### Source 9 — Cooling Towers (COOL1)

Large mechanical-draft cooling towers. Drift (small water droplets carrying
dissolved minerals) escapes from the tower. We model these as volume sources
because emissions come from the entire tower structure.

Source type: **Volume**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `COOL1` | Cooling tower bank |
| X Coordinate | `279250` | Adjacent to process area |
| Y Coordinate | `3291550` | |
| Base Elevation | `5.0` | |
| Release Height | `12.0` | Tower exit height |
| Initial Sigma-Y | `8.0` | ~ tower width / 4.3 (EPA guidance) |
| Initial Sigma-Z | `6.0` | ~ tower height / 2.15 |
| Emission Rate | `0.2` | 0.2 g/s total (drift PM, minor SO2 content) |

> **Volume source parameters:** EPA guidance recommends:
> - Initial sigma-Y = building width / 4.3
> - Initial sigma-Z = building height / 2.15
> These represent the initial lateral and vertical spread of the plume
> caused by the source's physical dimensions.

#### Source 10 — Equipment Leak Fugitives (FUGITV)

Distributed fugitive emissions from thousands of valves, pumps, flanges,
and connections throughout the refinery process area. Modeled as a single
large volume source representing the aggregate.

Source type: **Volume**

| Parameter | Value | Rationale |
|---|---|---|
| Source ID | `FUGITV` | Process area fugitives |
| X Coordinate | `279200` | Center of process area |
| Y Coordinate | `3291700` | |
| Base Elevation | `5.0` | |
| Release Height | `5.0` | Average equipment height |
| Initial Sigma-Y | `25.0` | Large lateral extent (~100 m process area) |
| Initial Sigma-Z | `4.0` | Low release height |
| Emission Rate | `0.5` | 0.5 g/s total from all leak points |

### Step 3: Create Source Groups

Source groups let you evaluate the contribution of different parts of the
refinery separately. This is required for regulatory work and invaluable
for understanding where impacts come from.

1. In the **Source Editor**, navigate to the **Source Groups** section.
2. Create these groups:

| Group Name | Sources | What It Represents |
|---|---|---|
| `STACKS` | FCCSTK, HTR1, HTR2, BOILER, FLARE | All elevated point sources |
| `FUGITIV` | TANKS, LOADRK, WWATER, FUGITV | All fugitive/area/volume sources |
| `FCCONLY` | FCCSTK | FCC unit alone (largest single source) |
| `ALL` | All 10 sources | Total facility impact |

> **Why source groups?** When the regulator asks "What happens if you add
> a scrubber to the FCC unit?", you can compare the FCCONLY group results
> before and after to quantify the benefit — without re-running the entire
> model.

### Step 4: Set Up a Multi-Scale Receptor Network

A good receptor network captures both the near-field peak and the broader
impact area. We will use three receptor configurations:

#### Receptor Set 1 — Fine Grid (Near-Field)

This captures the peak concentration close to the refinery.

| Parameter | Value |
|---|---|
| Grid Name | `FINE` |
| X Min | `278200` |
| X Max | `280200` |
| Y Min | `3290700` |
| Y Max | `3292700` |
| Spacing | `50` |

This gives a **41 x 41 = 1,681 receptor** grid at 50 m spacing, covering
a 2 km x 2 km area centered on the refinery.

#### Receptor Set 2 — Coarse Grid (Far-Field)

This captures impacts several kilometers downwind.

| Parameter | Value |
|---|---|
| Grid Name | `COARSE` |
| X Min | `276700` |
| X Max | `281700` |
| Y Min | `3289200` |
| Y Max | `3294200` |
| Spacing | `200` |

This gives a **26 x 26 = 676 receptor** grid at 200 m spacing, covering
a 5 km x 5 km area.

#### Receptor Set 3 — Discrete Sensitive Receptors

Add discrete receptors at locations of special concern. These represent
nearby communities, schools, and monitoring stations.

1. On the **Discrete Receptors** tab, add:

| Label | X | Y | What It Represents |
|---|---|---|---|
| `Community NW` | `278100` | `3292500` | Residential neighborhood NW of refinery |
| `Community NE` | `280300` | `3292400` | Neighborhood NE of refinery |
| `Community S` | `279200` | `3290200` | Neighborhood south of Ship Channel |
| `School` | `278500` | `3293000` | Elementary school, 1.5 km NW |
| `Hospital` | `280000` | `3292800` | Medical center, 1.2 km NE |
| `Monitor` | `279500` | `3292200` | Air quality monitoring station |

> **Total receptor count:** 1,681 + 676 + 6 = **2,363 receptors**.
> With hourly meteorology over one year and 10 sources, this is a
> moderately large model that may take 5--15 minutes to run.

### Step 5: Connect Meteorology

1. Go to **Meteorology** and select **Use Existing Files**.
2. Enter the paths to your Houston `.sfc` and `.pfl` files from
   Tutorial 6:
   - Surface file: `houston_2023.sfc`
   - Profile file: `houston_2023.pfl`

### Step 6: Import Terrain Data (Optional but Recommended)

If you completed Tutorial 7:

1. Go to **Receptor Editor** > **AERMAP Elevation Import** tab.
2. Upload the AERMAP receptor and source output files.
3. Verify that elevations have been applied.

If you did not complete Tutorial 7, you can proceed with FLAT terrain by
changing the Terrain Type to FLAT on Project Setup. The results will be
slightly different but the analysis workflow is the same.

### Step 7: Configure Output

1. Go to **Run AERMOD**.
2. Under **Output Configuration**:
   - **Receptor table:** On
   - **Max value table:** On
   - Enable **POSTFILE** output:
     - Format: `PLOT`
     - Averaging period: `1`  (1-hour — needed for NAAQS comparison)
     - Source group: `ALL`
3. Enable separate plot files for each source group:
   - `STACKS` — 1-hour averaging
   - `FCCONLY` — 1-hour averaging

### Step 8: Validate and Run

1. Click **Validate** to check for errors.

   Common issues at this stage:
   - Source coordinates outside the receptor grid (verify all sources are
     within the FINE grid)
   - Missing meteorological file paths
   - Source ID longer than 8 characters

2. **Preview the input file.** Expand it and verify:
   - 10 sources in the SO pathway (5 POINT, 2 AREA, 1 AREAPOL, 2 VOLUME)
   - 4 source groups defined (STACKS, FUGITIV, FCCONLY, ALL)
   - Receptor grids FINE and COARSE plus 6 discrete receptors
   - Correct met file paths

3. Set the **Working Directory** and click **Run AERMOD**.

> **Runtime estimate:** With ~2,400 receptors, 10 sources, and 8,760 hours
> of meteorology, expect approximately 5--15 minutes depending on your
> computer.

### Step 9: Analyze the Results

Once AERMOD completes, go to **Results Viewer**.

#### 9A. Interactive Map

1. Select **1-hour** averaging period.
2. Observe the spatial pattern:
   - The plume should extend primarily to the **north-northwest** (downwind
     of the prevailing south-southeast winds in Houston).
   - The maximum 1-hour concentration will be located 0.5--2 km downwind
     of the tallest stacks.
3. Switch to **ANNUAL** averaging. The pattern should be more symmetric
   because annual averages include winds from all directions.
4. Toggle between the street map and satellite basemap. Can you see the
   Ship Channel and surrounding neighborhoods?

#### 9B. Statistics — Regulatory Compliance

Go to the **Statistics** tab and answer these questions:

**Question 1: Does the refinery comply with the SO2 1-hour NAAQS?**

The SO2 1-hour standard is **196 ug/m3** (equivalent to 75 ppb).

- Enter `196` in the exceedance threshold.
- How many receptors exceed this standard?
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

Check the concentrations at each discrete receptor:

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

If you generated separate plot files for each source group:

**Question 4: Source contribution analysis.**

Compare the maximum 1-hour concentrations from each source group:

| Source Group | Max 1-hr (ug/m3) | % of Total |
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

1. Go to the **POSTFILE Viewer** tab.
2. Upload the POSTFILE.
3. Use the timestep slider to find the hour with the highest concentration.
4. What were the meteorological conditions during this hour? (You can check
   the `.sfc` file for the matching date/time.)
5. Generate an animation GIF showing the hourly concentration evolution
   over a 24-hour period that includes the peak hour.

### Step 10: Sensitivity Analysis (Assignment Extension)

Repeat the model run with one change at a time to understand how each factor
affects the results. This is the heart of engineering analysis.

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

Real air has background SO2 from regional sources (power plants, shipping,
other refineries). Add a background concentration:

1. In the **Source Editor**, go to the **Background** section.
2. Select **Uniform** mode.
3. Enter **10 ug/m3** as the background for all periods.

- How does the background change the compliance picture?
- At what background level would the facility fail to comply (if it didn't
  already)?

#### Scenario D: Flat vs Elevated Terrain

If you have terrain data from Tutorial 7, run the model with both FLAT
and ELEVATED terrain:

- What is the maximum concentration difference between the two terrain modes?
- Where do the differences occur? (Hint: look at receptors on higher terrain.)

### Report Template

Compile your results into a brief technical report (3--5 pages) with these
sections:

1. **Introduction** — Describe the facility, pollutant, and modeling
   objectives (1 paragraph).

2. **Model Configuration** — Summarize source inventory (table), receptor
   network, meteorological data, and terrain data used.

3. **Results** — Present your answers to Questions 1--4 above, with
   supporting maps and tables from the Results Viewer.

4. **Sensitivity Analysis** — Summarize Scenarios A--D and what they reveal
   about the most effective control strategies.

5. **Conclusions** — Does the simplified refinery comply with the SO2 NAAQS?
   What would you recommend to the facility operator if it does not?

---

## Assignment Deliverables

Submit the following files and documents:

### From Tutorial 6 (AERMET)
- [ ] Three AERMET input files (`aermet_houston_s1.inp`, `s2.inp`, `s3.inp`)
- [ ] Written answers to the three Discussion Questions
- [ ] Brief description of the monthly surface parameter choices and
  rationale

### From Tutorial 7 (Terrain)
- [ ] Screenshot of the GUI showing imported terrain elevations in the
  receptor grid
- [ ] Comparison of FLAT vs ELEVATED generated input files (highlight
  differences)
- [ ] Written answers to the three Discussion Questions

### From Tutorial 8 (Refinery Model)
- [ ] Project JSON file (`refinery_project.json`) — saved from the GUI
- [ ] Generated AERMOD input file (`refinery.inp`)
- [ ] Technical report (3--5 pages) including:
  - Source inventory table
  - Results maps (screenshots from the Interactive Map)
  - Compliance analysis table
  - Source contribution analysis
  - Sensitivity analysis results (Scenarios A--D)
  - Conclusions and recommendations

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

### Houston-Area Meteorological Stations

| Station | ID | Type | Lat | Lon | Elev (m) | Notes |
|---|---|---|---|---|---|---|
| Houston Hobby | KHOU / 12918 | Surface | 29.6454 | -95.2789 | 14 | Recommended for Ship Channel area |
| Houston IAH | KIAH / 12960 | Surface | 29.9844 | -95.3414 | 29 | Better for north Houston |
| Galveston | KGLS / 12923 | Surface | 29.2653 | -94.8603 | 5 | Coastal, high winds |
| Lake Charles, LA | 72240 | Upper Air | 30.12 | -93.22 | 5 | Closest radiosonde to Houston |
| Corpus Christi | 72251 | Upper Air | 27.77 | -97.50 | 14 | Alternative (far south) |

### Typical Refinery Emission Rates (SO2, g/s)

These are approximate emission rates for a 150,000 bpd refinery burning
low-sulfur fuel gas (50--150 ppm H2S). Actual rates depend on sulfur
content, control equipment, and operating conditions.

| Source | Typical SO2 (g/s) | Range |
|---|---|---|
| FCC regenerator | 3--8 | With electrostatic precipitator / third-stage separator |
| Process heater (large) | 1--4 | Depends on fuel sulfur content |
| Process heater (small) | 0.5--2 | |
| Boiler | 1--5 | Depends on fuel type and controls |
| Flare (normal) | 0.2--2 | Much higher during upset conditions |
| Tank farm (fugitive) | 0.05--0.5 | Total; primarily H2S oxidized to SO2 |
| Cooling tower | 0.01--0.3 | Drift PM, minimal SO2 |

### NAAQS Quick Reference

| Pollutant | Averaging Period | Standard (ug/m3) | Standard (ppb) | Form |
|---|---|---|---|---|
| SO2 | 1-hour | 196 | 75 | 99th percentile of daily max, averaged over 3 years |
| PM2.5 | Annual | 9.0 | — | Annual mean, averaged over 3 years |
| PM2.5 | 24-hour | 35 | — | 98th percentile, averaged over 3 years |
| PM10 | 24-hour | 150 | — | Not to be exceeded more than once per year |
| NO2 | 1-hour | 188 | 100 | 98th percentile of daily max, averaged over 3 years |
| NO2 | Annual | 100 | 53 | Annual mean |
| CO | 1-hour | 40,000 | 35,000 | Not to be exceeded more than once per year |
| CO | 8-hour | 10,000 | 9,000 | Not to be exceeded more than once per year |
| O3 | 8-hour | 137 | 70 | Annual 4th-highest, averaged over 3 years |

### Land Use Surface Parameters for Coastal Texas

| Land Cover | Season | Albedo | Bowen Ratio | Roughness (m) |
|---|---|---|---|---|
| Open water | All | 0.10 | 0.0 | 0.001 |
| Coastal marsh | Summer | 0.14 | 0.2 | 0.15 |
| Coastal marsh | Winter | 0.18 | 0.5 | 0.10 |
| Industrial/port | All | 0.18 | 0.8--1.5 | 0.50--1.00 |
| Residential suburban | Summer | 0.16 | 0.5 | 0.50 |
| Residential suburban | Winter | 0.20 | 1.0 | 0.30 |
| Grassland/pasture | Summer | 0.18 | 0.3 | 0.10 |
| Grassland/pasture | Winter | 0.20 | 0.8 | 0.05 |
| Forest (mixed) | Summer | 0.12 | 0.3 | 1.00 |
| Forest (mixed) | Winter | 0.18 | 0.8 | 0.50 |

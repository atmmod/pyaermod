# Introduction to Air Dispersion Modeling with PyAERMOD

A hands-on guide for students who have never used a dispersion model before.
No programming is required — all three tutorials use the PyAERMOD graphical
interface (GUI) in your web browser.

---

## Table of Contents

1. [What Is Air Dispersion Modeling?](#1-what-is-air-dispersion-modeling)
2. [Key Concepts](#2-key-concepts)
3. [Setting Up PyAERMOD](#3-setting-up-pyaermod)
4. [Tutorial 1 — Your First Point Source](#4-tutorial-1--your-first-point-source)
5. [Tutorial 2 — Comparing Stack Heights](#5-tutorial-2--comparing-stack-heights)
6. [Tutorial 3 — Running AERMOD and Reading Results](#6-tutorial-3--running-aermod-and-reading-results)
7. [What's Next?](#7-whats-next)
8. [Glossary](#8-glossary)

---

## 1. What Is Air Dispersion Modeling?

When a factory, power plant, or vehicle emits pollutants into the air, those
pollutants don't stay in one place. Wind carries them downwind, and turbulence
spreads them out in all directions. An **air dispersion model** is a computer
program that predicts *where* those pollutants go and *how concentrated* they
are at ground level.

### Why Does It Matter?

- **Protecting public health.** Regulatory agencies (like the U.S. EPA) use
  dispersion models to decide whether a proposed factory will cause air quality
  problems in nearby neighborhoods.
- **Designing better facilities.** Engineers use models to determine how tall a
  smokestack needs to be, or whether adding a scrubber will bring concentrations
  below safe limits.
- **Emergency planning.** If there's an accidental release of a toxic gas,
  models help predict which areas might be affected.

### What Is AERMOD?

**AERMOD** (AMS/EPA Regulatory Model) is the U.S. EPA's preferred model for
near-field (< 50 km) regulatory air quality assessments. It has been the
standard since 2005 and is used worldwide.

AERMOD is a **steady-state Gaussian plume model**, which means:

- **Steady-state**: it assumes meteorological conditions are constant during
  each hour of simulation.
- **Gaussian plume**: it models the spreading pollutant cloud as a bell-shaped
  (Gaussian) distribution in both the horizontal and vertical directions.

PyAERMOD is a Python wrapper that lets you set up, run, and analyze AERMOD
models through a graphical interface or Python code, instead of editing text
files by hand.

---

## 2. Key Concepts

Before diving into the tutorials, here are the core ideas you'll need.

### 2.1 Emission Sources

An **emission source** is anything that releases pollutants into the air.
AERMOD supports several types:

| Source Type | Real-World Example |
|---|---|
| **Point** | Smokestack, exhaust vent |
| **Area** | Storage pile, parking lot, landfill |
| **Volume** | Conveyor transfer point, building vent |
| **Line** | Roadway, railway, pipeline |
| **Open Pit** | Quarry, surface mine |

For these tutorials, we'll focus on **point sources** (smokestacks) because
they're the most common and the easiest to understand.

#### Key Point Source Parameters

- **Stack height** (meters): How tall the smokestack is. Taller stacks release
  pollutants higher up, giving them more time to dilute before reaching the
  ground.
- **Stack diameter** (meters): The inner diameter of the stack opening.
- **Exit velocity** (m/s): How fast the exhaust gas leaves the stack. Faster
  gas shoots the plume higher (this is called **momentum rise**).
- **Exit temperature** (Kelvin): Hot exhaust gas is buoyant — it rises because
  it's lighter than the surrounding air. This is called **buoyancy rise**. The
  combination of momentum and buoyancy rise is called **plume rise**.
- **Emission rate** (g/s): The mass of pollutant released per second.

> **Intuition:** Imagine holding a lit candle. The hot smoke rises (buoyancy).
> If you blow on it, the smoke bends sideways (wind). If you raise the candle
> overhead, the smoke takes longer to reach the floor (stack height). These are
> the same physics AERMOD captures mathematically.

### 2.2 Receptors

**Receptors** are the locations where AERMOD calculates the ground-level
pollutant concentration. Think of them as virtual air quality monitors placed
across a map.

Common receptor layouts:

- **Cartesian grid**: A regular rectangular grid of points (like graph paper
  laid over a map). You specify the boundaries and spacing. A 2 km x 2 km
  area with 100 m spacing gives 441 receptors.
- **Polar grid**: Rings of points radiating out from a central location (like a
  dartboard). Useful for studying how concentration changes with distance from
  a source.
- **Discrete receptors**: Individual points at specific locations of interest
  (a school, a hospital, a property boundary).

### 2.3 Meteorology

Wind and atmospheric stability are the two most important factors controlling
dispersion:

- **Wind speed and direction** determine where the plume goes.
- **Atmospheric stability** determines how much the plume spreads:
  - **Unstable** (sunny daytime): strong vertical mixing, plume spreads
    rapidly, concentrations drop quickly with distance.
  - **Stable** (clear nighttime): weak mixing, plume stays narrow and compact,
    can travel far with less dilution.
  - **Neutral** (overcast, windy): moderate mixing.

AERMOD uses **hourly meteorological data** — typically one to five years of
observations from a nearby weather station, preprocessed by the AERMET
program into `.sfc` (surface) and `.pfl` (profile) files. For tutorials 1
and 2 you won't need actual met data because we'll only generate the input
file. Tutorial 3 shows how to connect real meteorological files.

### 2.4 What AERMOD Produces

For each receptor, AERMOD calculates the **pollutant concentration** (typically
in micrograms per cubic meter, ug/m3) for each hour of the simulation. It then
computes summary statistics:

- **Annual average** — the mean concentration over all hours. Compared to the
  annual NAAQS (National Ambient Air Quality Standard).
- **24-hour average** — the highest 24-hour average over the simulation period.
- **1-hour average** — the highest single-hour concentration.

The results let you answer questions like: *"Will this factory cause the
annual PM2.5 concentration at the nearest school to exceed 12 ug/m3?"*

### 2.5 The Modeling Workflow

Every AERMOD analysis follows this sequence:

```
Define the problem
       |
       v
Set up sources, receptors, and meteorology
       |
       v
Generate the AERMOD input file (.inp)
       |
       v
Run AERMOD  -->  Output file (.out)
       |
       v
Analyze results (tables, maps, compliance checks)
```

The PyAERMOD GUI walks you through each of these steps in order.

---

## 3. Setting Up PyAERMOD

### 3.1 Install

Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and run:

```bash
pip install pyaermod[gui]
```

This installs the core package plus everything needed for the graphical
interface (Streamlit, Folium maps, matplotlib plots).

To verify the install worked:

```bash
pyaermod
```

You should see version information and a feature list.

### 3.2 Launch the GUI

```bash
pyaermod-gui
```

Your web browser will open automatically to `http://localhost:8501`. You'll see
the PyAERMOD interface with a sidebar on the left and the **Project Setup**
page in the main area.

> **Tip:** The GUI runs as a local web app. It never sends your data to the
> internet — everything stays on your computer.

### 3.3 GUI Layout

- **Sidebar (left):** Navigation between the 7 workflow pages, plus a progress
  checklist showing which steps are complete.
- **Main area (center):** The active page — forms, maps, tables, and plots.

The 7 pages, in workflow order:

1. **Project Setup** — project name, pollutant, terrain, coordinate system
2. **Source Editor** — add and configure emission sources on a map
3. **Receptor Editor** — define where concentrations are calculated
4. **Meteorology** — point to weather data files
5. **Run AERMOD** — validate, preview, and execute the model
6. **Results Viewer** — maps, plots, statistics, compliance checks
7. **Export** — download results as GeoTIFF, Shapefile, CSV, etc.

---

## 4. Tutorial 1 — Your First Point Source

**Goal:** Create a simple AERMOD input file for a single smokestack emitting
PM2.5, and understand what each setting means.

**Time:** 15--20 minutes

**What you'll learn:**
- How to configure a project in the GUI
- How to define a point source (smokestack)
- How to set up a receptor grid
- How to specify meteorology file paths
- How to preview and download the generated AERMOD input file

### Step 1: Project Setup

1. Launch the GUI (`pyaermod-gui`).
2. On the **Project Setup** page, fill in:
   - **Title Line 1:** `Tutorial 1 - My First Model`
   - **Title Line 2:** `Single point source, PM2.5`
   - **UTM Zone:** Pick the zone for your area. (If unsure, use `17` for the
     eastern U.S. or `10` for the western U.S. The exact zone doesn't matter
     for learning.)
   - **Hemisphere:** `N` (Northern)
   - **Datum:** `WGS84`
   - **Map Center Latitude:** `35.0` (or your local latitude)
   - **Map Center Longitude:** `-80.0` (or your local longitude)
   - **Pollutant Type:** `PM25`
   - **Terrain Type:** `FLAT`
   - **Averaging Periods:** Select `ANNUAL` and `24`

> **What you just did:** You told AERMOD what pollutant you're modeling (PM2.5),
> that the terrain is flat (no hills), and that you want annual and 24-hour
> average results. The coordinate system settings let the GUI convert between
> the map (latitude/longitude) and AERMOD's coordinate system (UTM meters).

### Step 2: Add a Point Source

1. Click **Source Editor** in the sidebar.
2. You'll see an interactive map. Below it, select source type: **Point**.
3. Fill in the source form:

   | Parameter | Value | What It Means |
   |---|---|---|
   | Source ID | `STACK1` | A short name for this source |
   | X Coordinate | `500000` | Easting in UTM meters (or click the map) |
   | Y Coordinate | `3870000` | Northing in UTM meters (or click the map) |
   | Base Elevation | `0` | Ground elevation at the stack base (meters) |
   | Stack Height | `50` | The stack is 50 meters tall |
   | Exit Temperature | `400` | Exhaust gas temperature: 400 K (about 127 C) |
   | Exit Velocity | `15` | Gas exits at 15 m/s |
   | Stack Diameter | `2` | Stack opening is 2 meters across |
   | Emission Rate | `1.5` | Emitting 1.5 grams of PM2.5 per second |

4. Click **Add Source**.

> **What you just did:** You defined a medium-sized industrial smokestack. The
> hot, fast-moving exhaust gas will rise well above the 50 m physical stack
> height (plume rise), so the "effective" release height might be 80--120 m
> depending on meteorological conditions. This is why AERMOD needs the
> temperature and velocity — not just the physical height.

You should see your source appear as a marker on the map and in the source
table below.

### Step 3: Set Up Receptors

1. Click **Receptor Editor** in the sidebar.
2. On the **Cartesian Grid** tab, enter:

   | Parameter | Value | What It Means |
   |---|---|---|
   | X Min | `498000` | Western edge of the grid |
   | X Max | `502000` | Eastern edge (4 km total width) |
   | Y Min | `3868000` | Southern edge |
   | Y Max | `3872000` | Northern edge (4 km total height) |
   | Spacing | `200` | One receptor every 200 meters |

3. The GUI will show: **21 x 21 = 441 receptors**. Click **Add Grid**.

> **What you just did:** You placed a 4 km x 4 km grid of virtual air quality
> monitors centered on your source, with a receptor every 200 meters. AERMOD
> will calculate the ground-level PM2.5 concentration at each of these 441
> points.

### Step 4: Specify Meteorology

1. Click **Meteorology** in the sidebar.
2. Select **Use Existing Files** mode.
3. Enter file paths:
   - **Surface file:** `met_data.sfc`
   - **Profile file:** `met_data.pfl`

> **Note:** You don't need actual meteorological files for this tutorial — we're
> just generating the input file. When you're ready to actually run AERMOD
> (Tutorial 3), you'll need real `.sfc` and `.pfl` files.

### Step 5: Preview the Input File

1. Click **Run AERMOD** in the sidebar.
2. Expand the **Generated Input File** section. You'll see the complete AERMOD
   input file — a text file organized into five pathways:

   - **CO** (Control): Project title, pollutant, options
   - **SO** (Source): Your stack parameters
   - **RE** (Receptor): Your grid definition
   - **ME** (Meteorology): File paths
   - **OU** (Output): What results to produce

3. Click **Download Input File** to save it as `aermod.inp`.

> **What you just did:** You generated a complete, valid AERMOD input file
> without editing a single line of text. Open the `.inp` file in a text
> editor and compare it to what the GUI showed you — they're identical.

### Checkpoint

At this point you should understand:

- [x] The five AERMOD pathways (CO, SO, RE, ME, OU)
- [x] What stack height, temperature, velocity, and emission rate represent
- [x] How a Cartesian receptor grid covers an area around the source
- [x] That AERMOD needs hourly meteorological data in `.sfc` / `.pfl` format

---

## 5. Tutorial 2 — Comparing Stack Heights

**Goal:** Create two versions of the same facility — one with a 20 m stack and
one with a 60 m stack — to understand how stack height affects ground-level
concentrations.

**Time:** 15--20 minutes

**What you'll learn:**
- How stack height controls plume rise and ground-level impact
- How to use the Project Save/Load feature to create scenario variants
- How to read an AERMOD input file and spot key differences

### Conceptual Background

Imagine two identical factories, both emitting 2 g/s of SO2. The only
difference is the smokestack:

- **Factory A:** 20 m stack (about 6 stories tall)
- **Factory B:** 60 m stack (about 20 stories tall)

Which factory will cause higher ground-level concentrations? Intuitively,
Factory A — its emissions are released closer to the ground, so they have
less distance to dilute before reaching people.

But *how much* of a difference does it make? That's exactly what AERMOD
calculates.

### Step 1: Build the Base Scenario

Follow the same steps as Tutorial 1, but with these settings:

**Project Setup:**
- Title: `Tutorial 2 - Stack Height Comparison (20m)`
- Pollutant: `SO2`
- Averaging Periods: `1`, `24`, and `ANNUAL`
- Terrain: `FLAT`

**Source (Point):**
- Source ID: `STACK1`
- Stack Height: `20`
- Exit Temperature: `420` K
- Exit Velocity: `15` m/s
- Stack Diameter: `2` m
- Emission Rate: `2.0` g/s

**Receptors (Cartesian Grid):**
- 4 km x 4 km area centered on the source, 100 m spacing

**Meteorology:**
- Surface file: `met_data.sfc`
- Profile file: `met_data.pfl`

### Step 2: Save the Project

1. Go back to **Project Setup**.
2. Click **Download Project** to save the project as a JSON file. Name it
   `tutorial2_20m.json`.

### Step 3: Download the 20 m Input File

1. Go to **Run AERMOD**.
2. Download the input file. Name it `stack_20m.inp`.

### Step 4: Create the 60 m Variant

1. Go to **Source Editor**.
2. Delete the existing source (select it in the table and click **Delete**).
3. Add a new source with the same parameters, **except Stack Height: `60`**.
4. Update the project title to `Tutorial 2 - Stack Height Comparison (60m)`.
5. Save this project as `tutorial2_60m.json`.
6. Download the input file as `stack_60m.inp`.

### Step 5: Compare the Input Files

Open both `.inp` files in a text editor and find the `SO SRCPARAM` line:

**20 m stack:**
```
SO SRCPARAM  STACK1   2.0   20.0   420.0   15.0   2.0
```

**60 m stack:**
```
SO SRCPARAM  STACK1   2.0   60.0   420.0   15.0   2.0
```

The only difference is the second number (stack height). Everything else is
identical, making this a controlled experiment.

### What to Expect When You Run These (Tutorial 3)

When you eventually run both files through AERMOD with real meteorological data:

- The **20 m stack** will produce **higher** maximum ground-level concentrations,
  especially close to the source (within 500 m).
- The **60 m stack** will produce **lower** maximum concentrations because the
  plume is released higher and has more room to dilute.
- The **location** of the maximum concentration will also shift — taller stacks
  push the peak concentration **farther downwind** because the plume takes
  longer to mix down to ground level.

This is a fundamental principle in air quality engineering: **effective stack
height is the single most important factor for ground-level concentrations**
from a point source.

### Checkpoint

At this point you should understand:

- [x] Taller stacks reduce ground-level concentrations
- [x] Taller stacks push the peak concentration farther downwind
- [x] The Project Save/Load feature lets you create scenario variants
- [x] The `SO SRCPARAM` line contains all point source parameters

---

## 6. Tutorial 3 — Running AERMOD and Reading Results

**Goal:** Run AERMOD with real meteorological data and interpret the results
using the GUI's Results Viewer.

**Time:** 30--45 minutes

**What you'll need:**
- AERMOD executable installed and on your PATH (download from
  [EPA SCRAM](https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models#aermod))
- Meteorological data files (`.sfc` and `.pfl`). Your instructor may provide
  these, or you can process your own with AERMET.

> **If you don't have met data yet:** Your instructor should provide a pair of
> `.sfc` and `.pfl` files for your region. These are typically generated from
> NOAA weather station data using the AERMET preprocessor. Ask your instructor
> which files to use and where to find them.

### Step 1: Verify AERMOD Is Installed

Open a terminal and type:

```bash
aermod
```

If AERMOD is installed, you'll see an error about missing input files (that's
OK — it just confirms the executable is found). If you get "command not found,"
you need to install AERMOD or add it to your PATH.

### Step 2: Set Up the Model

Load one of your Tutorial 2 project files, or create a new project:

**Project Setup:**
- Title: `Tutorial 3 - Full AERMOD Run`
- Pollutant: `PM25`
- Averaging Periods: `ANNUAL` and `24`
- Terrain: `FLAT`

**Source:**
- A single point source with realistic parameters (see Tutorial 1)

**Receptors:**
- Cartesian grid: 4 km x 4 km, 100 m spacing (441 receptors)

**Meteorology:**
- Click **Meteorology** in the sidebar.
- Select **Use Existing Files**.
- Enter the paths to your `.sfc` and `.pfl` files. You can also use the
  **Upload** buttons to copy the files into the working directory.

### Step 3: Validate and Run

1. Click **Run AERMOD** in the sidebar.
2. The GUI will run validation checks. Fix any errors that appear (common
   issues: missing met file paths, no sources defined, no receptors defined).
3. Verify the **Working Directory** path — this is where AERMOD will write its
   output.
4. Verify the **AERMOD Executable Path** (default: `aermod`).
5. Click **Run AERMOD**.

A spinner will appear while AERMOD runs. Depending on your grid size and the
number of hours of met data, this may take anywhere from 10 seconds to a few
minutes.

When it finishes, you'll see either:
- A green **success** banner with runtime info, or
- A red **error** banner. Read the error message — the most common issue is
  AERMOD not finding the meteorological files.

### Step 4: Explore the Results

Click **Results Viewer** in the sidebar. You now have four tabs:

#### Tab 1: Interactive Map

- Select an averaging period (e.g., `ANNUAL`).
- The map shows color-coded concentration values at each receptor location,
  with your source marked.
- **Zoom in** to see individual receptor values. **Pan** to explore the spatial
  pattern.
- Notice the **plume shape**: concentrations are highest downwind of the source
  and decrease with distance. The elongated pattern reflects the prevailing
  wind direction in your met data.

#### Tab 2: Static Plots

- A contour plot showing smooth concentration isopleths (lines of equal
  concentration).
- The concentric pattern around the source shows how concentrations decrease
  with distance — the **concentration gradient**.

#### Tab 3: Statistics

This is where you do compliance analysis:

- **Maximum concentration**: The highest value at any receptor. This is what
  regulators compare to the NAAQS.
- **Mean and median**: How polluted the area is on average.
- **Top 10 receptors**: Where are the worst-case locations?
- **Exceedance analysis**: Enter the NAAQS value to see how many receptors
  exceed the standard.

**Common NAAQS values to try:**

| Pollutant | Period | Standard (ug/m3) |
|---|---|---|
| PM2.5 | Annual | 9.0 |
| PM2.5 | 24-hour | 35 |
| PM10 | 24-hour | 150 |
| SO2 | 1-hour | 196 |
| NO2 | 1-hour | 188 |
| CO | 8-hour | 10,000 |

#### Tab 4: POSTFILE Viewer (Advanced)

If you enabled POSTFILE output on the Run page, you can upload the file here
to see hour-by-hour concentration animations. This is optional for beginners.

### Step 5: Interpret What You See

Ask yourself these questions:

1. **Where is the maximum concentration?** It should be downwind of the source,
   at a distance that depends on stack height and meteorology. For a 50 m
   stack, the peak is typically 500--2000 m downwind.

2. **What direction does the plume extend?** This reflects the prevailing wind
   direction in your met data. If the wind usually blows from west to east,
   the highest concentrations will be east of the source.

3. **Does the maximum exceed the NAAQS?** Enter the relevant standard in the
   exceedance analysis. If any receptors exceed it, the facility would need
   additional controls (taller stack, emission reduction, scrubbers, etc.).

4. **How quickly do concentrations drop with distance?** Look at the contour
   plot — concentrations typically drop to 10% of the maximum within 1--2 km
   for elevated point sources.

### Checkpoint

At this point you should understand:

- [x] How to run AERMOD from the GUI
- [x] How to read the interactive map and identify the plume direction
- [x] How to find the maximum concentration and where it occurs
- [x] How to check whether a facility complies with air quality standards
- [x] That wind direction and stack height are the dominant factors in where
  the plume goes and how concentrated it is

---

## 7. What's Next?

Now that you understand the basics, here are some directions to explore:

### More Source Types

Try adding **area sources** (Source Editor > Area) to model a parking lot or
storage pile. Area sources use emission rates per unit area (g/s/m2) rather
than total emission rate (g/s), so the numbers will be much smaller.

### Multiple Sources

Add several stacks to the same project and see how their plumes overlap.
Use **source groups** (Source Editor > Source Groups) to separate contributions
from different parts of a facility.

### Terrain Effects

Change the terrain type from FLAT to ELEVATED. Elevated terrain can
significantly increase concentrations on hilltops that are close to the
effective plume height. This requires terrain elevation data processed by
AERMAP.

### The Python API

Once you're comfortable with the GUI concepts, try the Jupyter notebooks in
`examples/notebooks/` to do the same work with Python code. The Python API
gives you more flexibility for parameter sweeps, batch runs, and custom
analysis.

### Useful References

- [AERMOD User's Guide (EPA)](https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models#aermod) —
  The official 300+ page reference for all AERMOD options.
- [AERMOD Model Formulation Document (EPA)](https://www.epa.gov/scram) —
  The mathematical basis behind the model.
- [40 CFR Part 51, Appendix W](https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-51/appendix-Appendix%20W%20to%20Part%2051) —
  EPA's Guideline on Air Quality Models (the regulatory framework for when
  and how to use AERMOD).

---

## 8. Glossary

| Term | Definition |
|---|---|
| **AERMOD** | AMS/EPA Regulatory Model — the U.S. EPA's preferred near-field dispersion model |
| **AERMET** | AERMOD's meteorological preprocessor; converts raw weather data into `.sfc` and `.pfl` files |
| **AERMAP** | AERMOD's terrain preprocessor; extracts elevation data for receptors and sources |
| **Averaging period** | The time window over which concentrations are averaged (1-hour, 24-hour, annual, etc.) |
| **Base elevation** | The ground-level elevation at the base of a source or receptor (meters above sea level) |
| **Buoyancy rise** | The upward motion of a hot plume due to its lower density relative to ambient air |
| **Cartesian grid** | A rectangular array of evenly spaced receptor points |
| **Concentration** | The amount of pollutant in a given volume of air, typically in ug/m3 |
| **Discrete receptor** | A single receptor placed at a specific location of interest |
| **Effective stack height** | Physical stack height + plume rise; the height at which the plume levels off |
| **Emission rate** | The mass of pollutant released per unit time (g/s for point sources, g/s/m2 for area sources) |
| **Exceedance** | When a predicted concentration is higher than the applicable air quality standard |
| **Exit velocity** | Speed of exhaust gas leaving the stack (m/s) |
| **Gaussian plume** | A mathematical model where pollutant concentration follows a bell curve in both horizontal and vertical cross-sections |
| **Momentum rise** | The upward motion of a plume due to the velocity of the exhaust gas |
| **NAAQS** | National Ambient Air Quality Standards — EPA's health-based concentration limits |
| **Pathway** | One of AERMOD's five input sections: CO (Control), SO (Source), RE (Receptor), ME (Meteorology), OU (Output) |
| **Plume rise** | The total height gain of exhaust gas above the physical stack top, from both buoyancy and momentum |
| **Polar grid** | A set of receptor points arranged in concentric rings at regular angular intervals around a center point |
| **POSTFILE** | An optional AERMOD output file containing concentration values at every receptor for every hour |
| **Receptor** | A location where AERMOD calculates ground-level pollutant concentration |
| **Source group** | A named subset of emission sources whose combined impact is reported separately |
| **Stability** | A measure of atmospheric turbulence: unstable (strong mixing), neutral, or stable (weak mixing) |
| **Steady-state** | An assumption that conditions (wind, stability) are constant during each simulation hour |
| **UTM** | Universal Transverse Mercator — a coordinate system that measures position in meters (easting, northing) within numbered zones |

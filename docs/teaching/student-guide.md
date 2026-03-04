# Introduction to Air Dispersion Modeling with PyAERMOD

A hands-on guide for students who have never used a dispersion model before.
No programming is required — all five tutorials use the PyAERMOD graphical
interface (GUI) in your web browser.

---

## Table of Contents

1. [What Is Air Dispersion Modeling?](#1-what-is-air-dispersion-modeling)
2. [Key Concepts](#2-key-concepts)
3. [Setting Up PyAERMOD](#3-setting-up-pyaermod)
4. [Tutorial 1 — Your First Point Source](#4-tutorial-1--your-first-point-source)
5. [Tutorial 2 — Comparing Stack Heights](#5-tutorial-2--comparing-stack-heights)
6. [Tutorial 3 — Running AERMOD and Reading Results](#6-tutorial-3--running-aermod-and-reading-results)
7. [Tutorial 4 — Area Sources: Modeling a Facility with Fugitive Emissions](#7-tutorial-4--area-sources-modeling-a-facility-with-fugitive-emissions)
8. [Tutorial 5 — Processing Meteorological Data with AERMET](#8-tutorial-5--processing-meteorological-data-with-aermet)
9. [What's Next?](#9-whats-next)
10. [Glossary](#10-glossary)

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

### 3.2 Install the AERMOD and AERMET Executables

Tutorials 1–2 only generate input files, so you can skip this step initially.
However, **Tutorial 3** (running AERMOD) and **Tutorial 5** (AERMET processing)
require the actual Fortran executables on your computer.

#### Option A: Download pre-compiled binaries (macOS Apple Silicon)

1. Go to the [latest PyAERMOD release](https://github.com/atmmod/pyaermod/releases/latest).
2. Under **Assets**, download `aermod` and `aermap`.
3. Move them to a permanent location and make them executable:

```bash
mkdir -p ~/bin
mv ~/Downloads/aermod ~/Downloads/aermap ~/bin/
chmod +x ~/bin/aermod ~/bin/aermap
```

4. Add `~/bin` to your PATH so PyAERMOD can find them. Add this line to your
   `~/.zshrc` (or `~/.bashrc` on Linux):

```bash
export PATH="$HOME/bin:$PATH"
```

Then restart your terminal, or run `source ~/.zshrc`.

5. Verify they work:

```bash
aermod
```

You should see AERMOD print its version header and then exit (it will show an
error about missing input — that's normal).

#### Option B: Compile from source (macOS Intel, Linux)

This requires `gfortran`. On macOS, install it with Homebrew:

```bash
brew install gcc
```

Then clone the repository and run the build script:

```bash
git clone https://github.com/atmmod/pyaermod.git
cd pyaermod
./scripts/build_aermod.sh all
```

This creates `bin/aermod` and `bin/aermap`. Move them to your PATH as in
Option A above:

```bash
cp bin/aermod bin/aermap ~/bin/
```

#### Option C: Windows

Download the official AERMOD executable from the
[EPA SCRAM website](https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models).
Place `aermod.exe` in a folder that's on your system PATH, or note the full
path to enter in the GUI when prompted.

> **Note:** The GUI's "Run AERMOD" page will automatically search your PATH
> for the executable. If it can't find it, you can browse to the file location
> directly.

### 3.3 Launch the GUI

```bash
pyaermod-gui
```

Your web browser will open automatically to `http://localhost:8501`. You'll see
the PyAERMOD interface with a sidebar on the left and the **Project Setup**
page in the main area.

> **Tip:** The GUI runs as a local web app. It never sends your data to the
> internet — everything stays on your computer.

### 3.4 GUI Layout

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

## 7. Tutorial 4 — Area Sources: Modeling a Facility with Fugitive Emissions

**Goal:** Model a construction site with three types of area sources —
a rectangular stockpile, a circular staging area, and an irregular polygon
site boundary — alongside a point source (generator exhaust).

**Time:** 25--30 minutes

**What you'll learn:**
- The difference between point source and area source emission rates
- How to add rectangular, circular, and polygonal area sources in the GUI
- How to combine point and area sources in one model
- How source groups let you analyze contributions separately

### Conceptual Background

Not all emissions come from smokestacks. Many facilities also have **fugitive
emissions** — pollutants that escape from ground-level or low-height sources
rather than through a defined stack. Examples include:

| Source | Why It Emits |
|---|---|
| Dirt stockpile | Wind blows dust off exposed surfaces |
| Parking lot | Vehicle exhaust, tire/brake wear, re-entrained road dust |
| Construction site | Earth-moving equipment, exposed soil |
| Tank farm | Vapors escape through tank vents and seals |
| Landfill | Gases seep through the surface over a large area |

These sources are modeled as **area sources** in AERMOD. The key difference
from point sources is how emission rates are specified:

- **Point source**: total mass emitted per second (**g/s**)
- **Area source**: mass emitted per second *per unit area* (**g/s/m2**)

Because area sources spread emissions over a large surface, the per-square-meter
rate is typically a very small number (e.g., 0.0001 g/s/m2).

> **Example calculation:**
> A 100 m x 50 m stockpile emits 0.5 g/s total.
> Area = 100 x 50 = 5,000 m2.
> Emission rate = 0.5 / 5,000 = **0.0001 g/s/m2**.

### Step 1: Project Setup

1. Launch the GUI (`pyaermod-gui`).
2. On the **Project Setup** page:
   - **Title Line 1:** `Tutorial 4 - Area Source Facility`
   - **Title Line 2:** `Construction site with mixed source types`
   - **Pollutant Type:** `PM10`
   - **Averaging Periods:** Select `24` and `ANNUAL`
   - **Terrain Type:** `FLAT`

### Step 2: Add a Point Source (Generator)

1. Click **Source Editor** in the sidebar.
2. Select source type: **Point**.
3. Fill in the form:

   | Parameter | Value | What It Represents |
   |---|---|---|
   | Source ID | `GENSET` | Diesel generator exhaust |
   | X Coordinate | `500050` | UTM meters (or click the map) |
   | Y Coordinate | `3870050` | UTM meters (or click the map) |
   | Base Elevation | `0` | |
   | Stack Height | `5` | Short exhaust stack |
   | Exit Temperature | `700` | Diesel exhaust is very hot (K) |
   | Exit Velocity | `10` | |
   | Stack Diameter | `0.3` | Small pipe |
   | Emission Rate | `0.3` | 0.3 g/s of PM10 |

4. Click **Add Source**.

> **Why start with the point source?** It gives you a reference marker on the
> map. You'll place the area sources around it.

### Step 3: Add a Rectangular Area Source (Stockpile)

1. In the source type selector, choose **Area (Rectangular)**.
2. Fill in the form:

   | Parameter | Value | What It Represents |
   |---|---|---|
   | Source ID | `PILE1` | Dirt/gravel stockpile |
   | X Coordinate | `500000` | Southwest corner X |
   | Y Coordinate | `3870000` | Southwest corner Y |
   | Base Elevation | `0` | |
   | Release Height | `2.0` | Dust lifts off ~2 m above the pile surface |
   | Half-Width Y | `25.0` | 50 m total in the Y direction |
   | Half-Width X | `50.0` | 100 m total in the X direction |
   | Rotation Angle | `0` | Aligned with the grid (no rotation) |
   | Emission Rate | `0.000100` | 0.0001 g/s/m2 (see calculation above) |

3. Click **Add Area Source**.

> **Understanding half-widths:** AERMOD defines rectangular area sources by
> their *half-widths* from the source coordinate. A "Half-Width X" of 50 means
> the source extends 50 m from the center in each X direction (100 m total
> width). This can be confusing at first — just remember to enter **half** the
> actual dimension.

### Step 4: Add a Circular Area Source (Staging Area)

1. Select source type: **Area (Circular)**.
2. Fill in the form:

   | Parameter | Value | What It Represents |
   |---|---|---|
   | Source ID | `STAGING` | Equipment staging / laydown area |
   | X Coordinate | `500200` | Center of the circle |
   | Y Coordinate | `3870100` | |
   | Base Elevation | `0` | |
   | Release Height | `1.0` | Low-level dust from vehicle traffic |
   | Radius | `60` | 60 m radius circle |
   | Num Vertices | `20` | How many sides to approximate the circle |
   | Emission Rate | `0.000050` | Lower rate — less disturbed surface |

3. Click **Add Circular Area Source**.

> **Num Vertices:** AERMOD approximates circles as polygons. 20 vertices gives
> a smooth-enough circle for most purposes. More vertices is more accurate but
> takes slightly longer to compute.

### Step 5: Add a Polygonal Area Source (Site Boundary)

1. Select source type: **Area (Polygon)**.
2. Set **Number of Vertices** to `5` (this selector appears *above* the form).
3. Fill in the form:

   | Parameter | Value |
   |---|---|
   | Source ID | `SITEBND` |
   | Base Elevation | `0` |
   | Release Height | `0.5` |
   | Emission Rate | `0.000020` |

4. Enter vertex coordinates (these define the irregular site boundary):

   | Vertex | X | Y |
   |---|---|---|
   | V1 | `499900` | `3869900` |
   | V2 | `500350` | `3869900` |
   | V3 | `500400` | `3870100` |
   | V4 | `500300` | `3870250` |
   | V5 | `499900` | `3870200` |

5. Click **Add Polygon Source**.

> **Vertex order matters:** The vertices should trace the outline of the area
> in order (clockwise or counterclockwise). AERMOD closes the polygon
> automatically — you don't need to repeat the first vertex.

### Step 6: Set Up Receptors

1. Click **Receptor Editor** in the sidebar.
2. On the **Cartesian Grid** tab:

   | Parameter | Value |
   |---|---|
   | X Min | `499500` |
   | X Max | `500800` |
   | Y Min | `3869500` |
   | Y Max | `3870700` |
   | Spacing | `50` |

3. Click **Add Grid**. You should get roughly 600+ receptors covering the
   site and a buffer zone around it.

### Step 7: Meteorology and Preview

1. Click **Meteorology** > **Use Existing Files** > enter paths to `.sfc`
   and `.pfl` files (or placeholder names for now).
2. Click **Run AERMOD** to preview the generated input file.

Expand the **Generated Input File** section and look for the `SO` pathway.
You should see four sources — one POINT and three area types:

```
SO LOCATION  GENSET   POINT   500050.00  3870050.00  0.00
SO LOCATION  PILE1    AREA    500000.00  3870000.00  0.00
SO LOCATION  STAGING  AREAPOL 500200.00  3870100.00  0.00
SO LOCATION  SITEBND  AREAPOL 499900.00  3869900.00  0.00
```

Notice how each source type generates different `SO SRCPARAM` lines:
- **POINT**: emission rate, stack height, temperature, velocity, diameter
- **AREA**: emission rate, release height, half-width-Y, half-width-X
- **AREAPOL**: emission rate, release height, number of vertices

### Step 8: Interpret Area Source Results (After Running)

When you eventually run this model, look for these patterns in the Results
Viewer:

- **The generator (point source)** produces a concentrated plume downwind of
  the stack — a narrow elongated shape.
- **The stockpile (rectangular area)** produces a broader, lower-concentration
  pattern centered on the pile. Concentrations are highest at the downwind
  edge of the pile.
- **The site boundary (polygon)** produces the most diffuse pattern — low
  concentrations spread over a wide area.
- **Combined impact** is highest where plumes from multiple sources overlap.

### Checkpoint

At this point you should understand:

- [x] Area source emission rates are per unit area (g/s/m2), not total (g/s)
- [x] Rectangular area sources are defined by half-widths, not full dimensions
- [x] Circular sources are approximated by polygons (Num Vertices)
- [x] Polygon sources are defined by a list of corner coordinates
- [x] Different source types produce different spatial patterns in results

---

## 8. Tutorial 5 — Processing Meteorological Data with AERMET

**Goal:** Use the GUI's AERMET configuration page to generate the three-stage
AERMET input files needed to process raw weather station data into AERMOD-ready
meteorological files.

**Time:** 30--40 minutes

**What you'll learn:**
- What AERMET does and why AERMOD needs it
- How the three AERMET stages work
- How to configure each stage in the GUI
- What the monthly surface parameters mean and how to choose values

### Conceptual Background

AERMOD cannot use raw weather data directly. Raw data from weather stations
comes in formats designed for archival and general forecasting — not
atmospheric dispersion modeling. AERMOD needs specially processed files that
contain:

- **Hourly surface data** (`.sfc` file): wind speed, wind direction, ambient
  temperature, atmospheric stability class, mixing height, friction velocity,
  Monin-Obukhov length, and other boundary-layer parameters.
- **Hourly profile data** (`.pfl` file): vertical profiles of wind speed, wind
  direction, and temperature at multiple heights above ground.

**AERMET** is the preprocessor that transforms raw weather station observations
into these two files. It runs in three stages:

```
Raw weather data (NOAA archives)
          |
   Stage 1: Extract & QA/QC
          |
   Extracted hourly data
          |
   Stage 2: Merge surface + upper air
          |
   Merged dataset
          |
   Stage 3: Compute boundary-layer parameters
          |
   aermod.sfc  +  aermod.pfl   (ready for AERMOD)
```

### What Data Does AERMET Need?

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

### Step 1: Navigate to the AERMET Page

1. Launch the GUI (`pyaermod-gui`).
2. First, set up your **Project Setup** page with the correct UTM zone and
   map center for your area (see Tutorial 1). AERMET Stage 3 may use these
   coordinates.
3. Click **Meteorology** in the sidebar.
4. Select the **Configure AERMET** radio button (not "Use existing files").

You'll see three tabs: **Stage 1**, **Stage 2**, and **Stage 3**.

### Step 2: Configure Stage 1 — Extract & QA/QC

Click the **Stage 1: Data Extract** tab.

**Purpose:** Stage 1 reads raw weather station data, performs quality assurance
checks (flagging missing or suspicious values), and extracts the variables
AERMET needs.

#### Surface Station

Fill in the surface station information. Your instructor should provide these
values. Example for Atlanta, GA:

| Parameter | Example Value | What It Means |
|---|---|---|
| Station ID | `KATL` | ICAO airport code or WBAN number |
| Station Name | `Atlanta Hartsfield` | Descriptive name (for your reference) |
| Latitude | `33.6300` | Station latitude (decimal degrees, negative = south) |
| Longitude | `-84.4400` | Station longitude (decimal degrees, negative = west) |
| Time Zone (UTC offset) | `-5` | Eastern Standard Time = UTC-5 |
| Elevation (m) | `315.0` | Station elevation above sea level |
| Anemometer Height (m) | `10.0` | Height of the wind sensor (usually 10 m) |
| Data Format | `ISHD` | NOAA Integrated Surface Hourly Data (most common) |

> **Data Format options:**
> - **ISHD** — Integrated Surface Hourly Data (NOAA, post-2006). This is the
>   most common format for recent U.S. data.
> - **HUSWO** — Hourly US Weather Observations (legacy NCDC format).
> - **SCRAM** — EPA SCRAM format (older pre-processed data).
> - **SAMSON** — Solar and Meteorological Surface Observational Network.

#### Upper Air Station

Fill in the upper air (radiosonde) station. Example:

| Parameter | Example Value | What It Means |
|---|---|---|
| Station ID | `72215` | WMO station number |
| Station Name | `Peachtree City` | Closest radiosonde launch site |
| Latitude | `33.3600` | |
| Longitude | `-84.5700` | |

> **Finding your upper air station:** The closest radiosonde station may be
> far from your surface station. In the U.S., there are only about 90 upper
> air stations (compared to thousands of surface stations). Use the one that
> is most representative of your area's upper-atmosphere conditions.

#### Data Files and Date Range

| Parameter | Example Value | What It Means |
|---|---|---|
| Surface Data File | `72219013874.dat` | Path to the raw ISHD surface data file |
| Upper Air Data File | `72215.dat` | Path to the raw upper air data file |
| Start Date | `2020/01/01` | First day of the period to process |
| End Date | `2020/12/31` | Last day (typically 1--5 years of data) |

Click **Save Stage 1 Configuration**.

#### Preview and Download

Expand **Preview Stage 1 Input** to see the generated AERMET input file. It
will contain keywords like:

- `JOB` — identifies the processing job
- `SURFACE DATA` — points to the surface data file and specifies the format
- `UPPERAIR DATA` — points to the upper air data file
- `XDATES` — specifies the date range to extract

Click **Download Stage 1 Input File** to save it as `aermet_stage1.inp`.

### Step 3: Configure Stage 2 — Merge

Click the **Stage 2: Merge** tab.

**Purpose:** Stage 2 takes the extracted surface and upper air data from
Stage 1 and merges them into a single hourly dataset, aligning timestamps and
interpolating upper air soundings to each hour.

| Parameter | Example Value | What It Means |
|---|---|---|
| Surface Extract File | `stage1.ext` | Output from Stage 1 (surface data) |
| Upper Air Extract File | `stage1_ua.ext` | Output from Stage 1 (upper air) |
| Start Date | `2020/01/01` | Should match Stage 1 |
| End Date | `2020/12/31` | Should match Stage 1 |
| Merge Output File | `stage2.mrg` | Where to write the merged dataset |

Click **Save Stage 2 Configuration**, then preview and download.

### Step 4: Configure Stage 3 — Boundary Layer Parameters

Click the **Stage 3: Boundary Layer** tab.

**Purpose:** This is the most important stage. Stage 3 reads the merged data
and computes the **planetary boundary layer parameters** that AERMOD needs:
friction velocity, Monin-Obukhov length, convective velocity scale, mixing
height, and more. These parameters depend on both the meteorological data and
the **surface characteristics** around the station.

#### File Paths

| Parameter | Example Value |
|---|---|
| Merge File | `stage2.mrg` |
| Start Date | `2020/01/01` |
| End Date | `2020/12/31` |
| Surface Output (.sfc) | `aermod.sfc` |
| Profile Output (.pfl) | `aermod.pfl` |

#### Monthly Surface Parameters

This is the part that requires the most judgment. The GUI shows an editable
table with three parameters for each month:

| Parameter | What It Controls | Typical Range |
|---|---|---|
| **Albedo** | Surface reflectivity (fraction of sunlight reflected). Snow-covered ground has high albedo; dark pavement has low albedo. | 0.10 -- 0.60 |
| **Bowen Ratio** | Ratio of sensible heat to latent heat. Dry surfaces (deserts, cities) have high Bowen ratios; moist surfaces (wetlands, irrigated fields) have low values. | 0.1 -- 10.0 |
| **Roughness (m)** | Aerodynamic roughness length — how "bumpy" the surface is to wind flow. Open water is very smooth (~0.001 m); a city center is very rough (~1.0 m). | 0.001 -- 2.0 |

The GUI pre-fills **suburban defaults** — these are reasonable starting values
for an area with moderate development (residential neighborhoods, scattered
trees):

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
> - **When in doubt:** Use the pre-filled suburban defaults. They're
>   conservative and widely used in regulatory work.

Click in any cell in the table to edit it. The values update in real time.

#### Site Location

The **Use Stage 1 surface station** checkbox (checked by default) tells
AERMET to use the latitude and longitude you entered in Stage 1. If you
uncheck it, AERMET will use the project center coordinates from the Project
Setup page.

Click **Save Stage 3 Configuration**.

### Step 5: Download All Three Input Files

You now have three AERMET input files:

| File | Stage | What It Does |
|---|---|---|
| `aermet_stage1.inp` | Extract & QA/QC | Reads raw data, checks quality |
| `aermet_stage2.inp` | Merge | Combines surface + upper air |
| `aermet_stage3.inp` | Boundary Layer | Computes AERMOD-ready parameters |

Download all three from their respective preview sections.

### Step 6: Run AERMET (Outside the GUI)

AERMET itself must be run separately (it's a different executable from AERMOD).
In a terminal:

```bash
# Stage 1
aermet < aermet_stage1.inp

# Stage 2
aermet < aermet_stage2.inp

# Stage 3
aermet < aermet_stage3.inp
```

Each stage reads the output of the previous stage, so they must be run **in
order**. When Stage 3 completes, you'll have your `aermod.sfc` and
`aermod.pfl` files — the meteorological inputs AERMOD needs.

> **Troubleshooting common errors:**
>
> - *"File not found"*: Check that the data file paths in Stage 1 are correct
>   and the files exist in the working directory.
> - *"Missing data exceeds threshold"*: Your raw data has too many gaps.
>   AERMET flags this in the Stage 1 output. You may need to use a different
>   station or a year with more complete records.
> - *"Upper air sounding missing"*: The upper air station may not have data
>   for all dates. A few missing soundings are normal; AERMET interpolates.

### Step 7: Use the Processed Met Data in AERMOD

Once you have `aermod.sfc` and `aermod.pfl`:

1. Go back to the **Meteorology** page in the GUI.
2. Switch to **Use existing .sfc/.pfl files** mode.
3. Enter the paths to your new `aermod.sfc` and `aermod.pfl` files.
4. Continue with your AERMOD run (Tutorial 3).

Alternatively, Stage 3's **Save** button automatically updates the
Meteorology Pathway to point to the `.sfc` and `.pfl` files you specified,
so you may already be set.

### Understanding What AERMET Produced

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

You don't need to read these files directly — AERMOD reads them
automatically — but understanding what's in them helps you interpret your
results. For example, if your maximum concentrations all occur during
nighttime hours, it's likely because stable conditions (high Monin-Obukhov
length, low mixing height) trapped the plume near the ground.

### Checkpoint

At this point you should understand:

- [x] Why AERMOD needs preprocessed meteorological data (not raw observations)
- [x] The three AERMET stages: Extract, Merge, Boundary Layer
- [x] That surface characteristics (albedo, Bowen ratio, roughness) vary by
  land use and season
- [x] How to generate the three AERMET input files using the GUI
- [x] That AERMET must be run in order (Stage 1 → 2 → 3) to produce `.sfc`
  and `.pfl` files

---

## 9. What's Next?

Now that you've completed all five tutorials, here are some directions to
explore:

### Advanced Tutorials: Houston Refinery Modeling (Tutorials 6--8)

The **[Houston Refinery Modeling Assignments](refinery-assignments.md)**
extend this guide with three advanced tutorials that take you through a
realistic industrial modeling project:

- **Tutorial 6** — Process meteorological data with AERMET for a specific
  Gulf Coast location (Houston Ship Channel), with site-appropriate surface
  parameters for a coastal/industrial area.
- **Tutorial 7** — Use AERMAP to process digital elevation data and assign
  terrain elevations to all receptors and sources, even in a relatively
  flat area like Houston.
- **Tutorial 8** — Build a complete AERMOD model for a simplified 150,000
  barrel-per-day petroleum refinery with 10 emission sources (point, area,
  and volume), multi-scale receptors, source groups, regulatory compliance
  analysis, and sensitivity studies. Includes a technical report assignment.

These tutorials build directly on the skills from Tutorials 1--5 and
include assignment deliverables and a grading rubric suitable for a
university course.

### Multiple Sources and Source Groups

Add several stacks and area sources to the same project and see how their
plumes overlap. Use **source groups** (Source Editor > Source Groups) to
separate contributions from different parts of a facility — for example,
"STACKS" vs. "FUGITIVE" — and compare their relative impact.

### Terrain Effects

Change the terrain type from FLAT to ELEVATED. Elevated terrain can
significantly increase concentrations on hilltops that are close to the
effective plume height. This requires terrain elevation data processed by
AERMAP.

### Background Concentrations

Real-world air quality is never zero — there's always some background
pollution from regional sources, traffic, and natural sources. AERMOD can add
a background concentration to its predictions using the **Background** option
in the Source Editor (see Notebook 07 for the Python API approach).

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
- [AERMET User's Guide (EPA)](https://www.epa.gov/scram) —
  Detailed documentation of all AERMET options and data formats.
- [40 CFR Part 51, Appendix W](https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-51/appendix-Appendix%20W%20to%20Part%2051) —
  EPA's Guideline on Air Quality Models (the regulatory framework for when
  and how to use AERMOD).

---

## 10. Glossary

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
| **Albedo** | The fraction of incoming sunlight reflected by the ground surface (0 = absorbs all, 1 = reflects all). Fresh snow ~0.7, dark pavement ~0.1 |
| **Bowen ratio** | Ratio of sensible heat flux to latent heat flux at the surface. High values (dry/urban), low values (moist/vegetated) |
| **Friction velocity** | A measure of wind-driven turbulence near the ground surface (m/s). Higher values mean more mechanical mixing |
| **Fugitive emissions** | Pollutants released from diffuse, ground-level sources (piles, lots, open areas) rather than through defined stacks |
| **Half-width** | AERMOD defines rectangular area sources by half the dimension in each direction from the source coordinate |
| **ISHD** | Integrated Surface Hourly Data — NOAA's standard format for recent U.S. surface weather observations |
| **Mixing height** | The depth of the atmospheric boundary layer (meters). Pollutants released below this height mix vertically within it |
| **Monin-Obukhov length** | A parameter characterizing atmospheric stability. Negative = unstable (good mixing), positive = stable (poor mixing) |
| **Radiosonde** | An instrument carried aloft by a weather balloon to measure vertical profiles of temperature, humidity, and wind |
| **Roughness length** | Aerodynamic parameter describing how rough the ground surface is to wind flow. Open water ~0.001 m, city center ~1.0 m |
| **Surface characteristics** | Albedo, Bowen ratio, and roughness length — the three land-surface parameters AERMET needs for each month |
| **UTM** | Universal Transverse Mercator — a coordinate system that measures position in meters (easting, northing) within numbered zones |

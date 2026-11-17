# 4. Tutorial 1 — Your First Point Source

**Goal:** Create a simple AERMOD input file for a single smokestack emitting
PM2.5, and understand what each setting means.

**Time:** 15--20 minutes

**What you'll learn:**
- How to configure a project in the GUI
- How to define a point source (smokestack)
- How to set up a receptor grid
- How to specify meteorology file paths
- How to preview and download the generated AERMOD input file

## Step 1: Set Up the Project

1. Launch the GUI (`pyaermod-app`).
2. On the **Project** step, fill in:
   - **Title (line 1):** `Tutorial 1 - My First Model`
   - **Title (line 2):** `Single point source, PM2.5`
   - **Pollutant:** `PM25`
   - **Averaging periods:** Select `24` and `ANNUAL` (a new project starts
     with `1` and `ANNUAL`; remove `1`)
   - **Terrain:** `Flat (FLAT)`
   - Untick **Regulatory default options (DFAULT)**. AERMOD ignores FLAT
     while DFAULT is on; the GUI shows a warning on the Project step if you
     leave it ticked.

> **What you just did:** You told AERMOD what pollutant you're modeling (PM2.5),
> that the terrain is flat (no hills), and that you want annual and 24-hour
> average results.

## Step 2: Add a Point Source

1. Click **Sources** in the step list.
2. Set **Type** to `PointSource` and click **Add**. An editor opens.
3. Fill in the source form:

   | Parameter | Value | What It Means |
   |---|---|---|
   | Source ID | `STACK1` | A short name for this source |
   | X coord (m) | `500000` | Easting in UTM meters |
   | Y coord (m) | `3870000` | Northing in UTM meters |
   | Stack height (m) | `50` | The stack is 50 meters tall |
   | Stack temp (K) | `400` | Exhaust gas temperature: 400 K (about 127 C) |
   | Exit velocity (m/s) | `15` | Gas exits at 15 m/s |
   | Stack diameter (m) | `2` | Stack opening is 2 meters across |
   | Emission rate (g/s) | `1.5` | Emitting 1.5 grams of PM2.5 per second |
   | Base elevation (m), under **Advanced** | `0` | Ground elevation at the stack base (meters) |

4. Click **Save**. (**Close** discards the source.)

> **What you just did:** You defined a medium-sized industrial smokestack. The
> hot, fast-moving exhaust gas will rise well above the 50 m physical stack
> height (plume rise), so the "effective" release height might be 80--120 m
> depending on meteorological conditions. This is why AERMOD needs the
> temperature and velocity — not just the physical height.

You should see your source appear in the source table and as a marker in the
plan view beside it.

## Step 3: Set Up Receptors

1. Click **Receptors** in the step list.
2. Set **Type** to `CartesianGrid` and click **Add**. In the editor, enter:

   | Parameter | Value | What It Means |
   |---|---|---|
   | Grid name | `GRID1` | A short name for this grid |
   | X init (m) | `498000` | Western edge of the grid |
   | X num | `21` | 21 points across: 4 km total width |
   | X delta (m) | `200` | One receptor every 200 meters |
   | Y init (m) | `3868000` | Southern edge |
   | Y num | `21` | 21 points up: 4 km total height |
   | Y delta (m) | `200` | One receptor every 200 meters |

3. Click **Save**. The table shows the grid with the summary **21 x 21**:
   441 receptors.

> **What you just did:** You placed a 4 km x 4 km grid of virtual air quality
> monitors centered on your source, with a receptor every 200 meters. AERMOD
> will calculate the ground-level PM2.5 concentration at each of these 441
> points.

## Step 4: Specify Meteorology

1. Click **Meteorology** in the step list.
2. Under **Met files**, enter:
   - **Surface file:** `met_data.sfc`
   - **Profile file:** `met_data.pfl`

> **Note:** You don't need actual meteorological files for this tutorial — we're
> just generating the input file. Because these files don't exist, the GUI
> marks the Meteorology step with an error and the header reads "Not ready to
> run". That is expected here. When you're ready to actually run AERMOD
> (Tutorial 3), you'll need real `.sfc` and `.pfl` files.

## Step 5: Preview the Input File

1. Click **Review & Run** in the step list.
2. Look at the **Deck preview** section. You'll see the complete AERMOD
   input file — a text file organized into five pathways:

   - **CO** (Control): Project title, pollutant, options
   - **SO** (Source): Your stack parameters
   - **RE** (Receptor): Your grid definition
   - **ME** (Meteorology): File paths
   - **OU** (Output): What results to produce

3. Click **Download deck** to save it. The download is named
   `pyaermod_gui.inp`; rename it `aermod.inp`.

> **What you just did:** You generated a complete, valid AERMOD input file
> without editing a single line of text. Open the `.inp` file in a text
> editor and compare it to what the GUI showed you — they're identical.

## Checkpoint

At this point you should understand:

- [x] The five AERMOD pathways (CO, SO, RE, ME, OU)
- [x] What stack height, temperature, velocity, and emission rate represent
- [x] How a Cartesian receptor grid covers an area around the source
- [x] That AERMOD needs hourly meteorological data in `.sfc` / `.pfl` format

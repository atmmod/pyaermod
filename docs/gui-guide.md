# GUI User Guide

PyAERMOD includes an interactive web GUI built with Streamlit. The GUI
provides a complete modeling workflow -- from project setup through results
visualization and export -- without writing any Python code.

## Launching the GUI

```bash
# Option 1: module invocation
streamlit run -m pyaermod.gui

# Option 2: console entry point (if installed)
pyaermod-gui
```

Requires the GUI extras: `pip install pyaermod[gui]`

The GUI opens in your default browser at `http://localhost:8501`.

## Workflow Overview

The sidebar displays a **Workflow Progress** checklist showing which steps
have been completed:

- Project configured
- Sources defined
- Receptors defined
- Meteorology set
- Results available

Use the sidebar radio buttons to navigate between 7 pages. The typical
workflow follows this order:

**Project Setup** &rarr; **Source Editor** &rarr; **Receptor Editor** &rarr;
**Meteorology** &rarr; **Run AERMOD** &rarr; **Results Viewer** &rarr; **Export**

---

## Page 1: Project Setup

Configure the base project parameters and coordinate reference system.

### Project Titles

Two text fields for AERMOD title lines that appear in output file headers.

### Coordinate Reference System

Three selectors in a row:

- **UTM Zone** (1--60)
- **Hemisphere** (N or S)
- **Datum** (WGS84, NAD83, NAD27)

These settings control coordinate transformations between the interactive
map (lat/lon) and AERMOD inputs (UTM meters).

### Map Center

Latitude and longitude inputs that center the interactive map used in the
Source Editor and Receptor Editor pages.

### Model Configuration

- **Pollutant Type** -- dropdown: PM2.5, PM10, NO2, SO2, CO, O3, OTHER
- **Terrain Type** -- dropdown: FLAT, ELEVATED, FLATSRCS
- **Averaging Periods** -- multi-select: 1-HR through ANNUAL

### NO2 Chemistry Options

When **NO2** is selected as the pollutant, an expandable **Chemistry Options**
section appears with:

- **Chemistry Method** -- OLM, PVMRM, ARM2, or GRSM
- **Default NO2/NOx Ratio** -- slider (0.0--1.0)
- **Ozone Data** -- radio selector:
    - *None* -- no ozone data
    - *File* -- path to ozone data file
    - *Uniform Value* -- single ozone concentration (ppb)
    - *Sector Values* -- per-sector ozone concentrations
- **NOx File** -- only visible when GRSM is selected

These settings generate the `MODELOPT`, `O3VALUES`, `OZONEFIL`, and `NOXFIL`
keywords in the AERMOD input.

### Project Save / Load

- **Download Project** -- serializes the entire session state (sources,
  receptors, meteorology, settings) to a JSON file via `ProjectSerializer`.
- **Load Project** -- uploads a previously saved JSON file and restores all
  session state. Useful for resuming work across browser sessions.

---

## Page 2: Source Editor

Add, visualize, and manage emission sources on an interactive map.

### Interactive Map

A Folium map (left column) displays all defined sources and buildings.
Click the map to set coordinates for a new source -- the clicked UTM
coordinates auto-populate the source form.

### Source Type Selection

A radio button lets you choose from all 10 AERMOD source types:

| Source Type | Description |
|-------------|-------------|
| Point | Elevated stack emissions |
| Area (Rectangular) | Rectangular ground-level area |
| Area (Circular) | Circular area source |
| Area (Polygon) | Irregular polygon area |
| Volume | 3D volume emission region |
| Line | Generic line source |
| RLine (Roadway) | Near-road dispersion |
| RLineExt (Extended Roadway) | Extended roadway with width |
| BuoyLine (Buoyant Line) | Buoyant line (e.g. aluminum smelter) |
| OpenPit (Open Pit Mine) | Open pit with internal circulation |

Each source type renders a dedicated form with the relevant parameters
(coordinates, emission rate, stack height, temperature, etc.). Point sources
include an optional **NO2/NOx Ratio** field (0--1) for per-source NO2
conversion ratios when using chemistry options.

### Source Table

A table below the form lists all defined sources with their ID, type,
coordinates, and emission rate. Use the select box and **Delete** button
to remove sources.

### Source Groups

Manage custom source groups for separate impact analysis:

- **Source Groups Table** -- lists existing groups (name, member sources,
  description).
- **Add Source Group** -- expandable form with:
    - Group name (max 8 characters, AERMOD requirement)
    - Multi-select of source IDs from defined sources
    - Optional description
- **Delete Source Group** -- select a group and remove it.

Source groups generate `SRCGROUP` keywords in the AERMOD input. Per-group
PLOTFILE output can be configured on the **Run AERMOD** page.

### Building Downwash (BPIP)

An expandable section for defining buildings near point, area, and volume
sources:

1. **Add Building** -- form for building ID, height, and corner coordinates.
2. **Buildings Table** -- lists all buildings with geometry summary.
3. **Calculate BPIP** -- select a source (point, area, or volume) and
   building, then run the BPIP calculator. It computes direction-dependent
   downwash parameters (BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ) for
   36 wind directions and applies them to the selected source.

See also: [bpip API reference](api/bpip.md)

---

## Page 3: Receptor Editor

Define where concentrations are calculated. Five tabs provide different
receptor definition methods.

### Tab 1: Cartesian Grid

Create a rectangular receptor grid by specifying X/Y bounds and spacing.
Uses `CartesianGrid.from_bounds()` internally. The form shows the calculated
total number of receptor points before you submit.

### Tab 2: Polar Grid

Create a radial receptor pattern centered on a specified origin. Configure
the number of distance rings, ring spacing, number of directions, and
starting angle. Useful for fence-line or radial impact assessments.

### Tab 3: Discrete Receptors

Place individual receptors by clicking the interactive map or entering UTM
coordinates manually. Each receptor can have an optional elevation (Z).

### Tab 4: Import CSV

Upload a CSV file with columns `x`, `y`, and optionally `z_elev`. The GUI
previews the first 10 rows, then batch-imports all receptors on confirmation.

### Tab 5: Import AERMAP Elevations

Upload an AERMAP receptor output file (`.out` format). The GUI parses
receptor elevations and matches them to existing discrete receptors by
(X, Y) coordinates within a 0.5 m tolerance. A separate section handles
source elevations.

See also: [terrain API reference](api/terrain.md)

### Receptor Summary

A metrics bar at the bottom shows total receptor count broken down by type
(Cartesian, Polar, Discrete). A **Clear All Receptors** button resets the
receptor pathway.

---

## Page 4: Meteorology

Configure meteorological data for the AERMOD simulation. Two modes are
available via a radio button at the top of the page.

### Mode 1: Use Existing Files

For users who already have processed `.sfc` (surface) and `.pfl` (profile)
files from AERMET or another source:

- Text inputs for surface and profile file paths
- Optional file upload to copy files into the working directory
- Working directory path input

### Mode 2: Configure AERMET

Full AERMET three-stage meteorological preprocessing, organized as three
tabs:

**Stage 1 -- Extract & QA/QC**

- **Surface Station**: station ID, name, latitude, longitude, time zone,
  elevation, anemometer height, and data format (ISHD, HUSWO, SCRAM, or
  SAMSON).
- **Upper Air Station**: station ID, name, latitude, longitude.
- **Data Files**: paths to surface and upper air data files.
- **Date Range**: start and end dates (YYYY/MM/DD).
- Preview and download the generated Stage 1 input file.

**Stage 2 -- Merge**

- Paths to the surface and upper air extract files from Stage 1.
- Date range and output merge file name.
- Preview and download the generated Stage 2 input file.

**Stage 3 -- Boundary Layer Parameters**

- Merge file path, date range, and output `.sfc`/`.pfl` file names.
- **Monthly Surface Parameters** table (editable): albedo, Bowen ratio, and
  surface roughness for each month, pre-filled with suburban defaults.
- Site location (uses Stage 1 station coordinates or falls back to the
  project center from the Project Setup page).
- Saving Stage 3 automatically updates the Meteorology Pathway to point to
  the generated `.sfc` and `.pfl` files.

See also: [aermet API reference](api/aermet.md)

---

## Page 5: Run AERMOD

Validate the project, preview the generated input file, and execute AERMOD.

### Validation

If the validator module is available, the GUI runs all validation checks and
displays errors and warnings. A green success banner appears when all checks
pass.

### Generated Input File

An expandable section shows the complete AERMOD `.inp` file that will be
written. Review it before running.

### Output Configuration

- **Receptor Table** -- checkbox (default: on)
- **Max Value Table** -- checkbox (default: on)
- **Generate POSTFILE** -- checkbox (default: off). When enabled, two
  additional selectors appear:
    - **Format**: PLOT (formatted text) or UNFORM (binary)
    - **Averaging Period**: 1, 3, 8, 24, ANNUAL, or PERIOD

### Per-Group PLOTFILE

If source groups have been defined (see Source Editor), an expandable section
shows per-group PLOTFILE options. For each source group, you can enable a
PLOTFILE and select its averaging period. These generate additional
`PLOTFILE` keywords with the group name.

### Execute

- **Working Directory** -- where AERMOD will run and write output.
- **AERMOD Executable Path** -- path to the `aermod` binary (default:
  `aermod` on PATH).
- **Run AERMOD** button -- writes the input file, runs AERMOD with a
  spinner, and reports success or failure. On success, the output is
  automatically parsed and stored for the Results Viewer.

See also: [runner API reference](api/runner.md),
[output_parser API reference](api/output_parser.md)

---

## Page 6: Results Viewer

Visualize and analyze AERMOD concentration results. You can also upload
a `.out` file directly if you ran AERMOD outside the GUI.

### Run Summary

Metrics row showing source count, receptor count, and pollutant ID from the
parsed results.

### Tab 1: Interactive Map

Select an averaging period and view a Folium concentration map with source
markers and receptor locations overlaid. Requires the geospatial extras.

### Tab 2: Static Plots

Contour plot of concentrations for the selected averaging period, rendered
with matplotlib.

### Tab 3: Statistics

Detailed statistical analysis for the selected averaging period:

- **Metrics**: maximum, mean, median, standard deviation
- **Percentile Distribution**: table with 50th through 100th percentiles
- **Top 10 Receptors**: table of highest-concentration receptor locations
- **Exceedance Analysis**: enter a threshold value to see how many receptors
  exceed it (count and percentage)

### Tab 4: POSTFILE Viewer

Upload an AERMOD POSTFILE (text PLOT or binary UNFORM format). The GUI
auto-detects the format and displays:

- **Metadata**: AERMOD version, pollutant, averaging period, source group
- **Timestep Viewer**: slider to step through dates (YYMMDDHH), with a
  contour or scatter plot and summary metrics for each timestep
- **Receptor Time Series**: select a receptor location and view its
  concentration over all timesteps as a line chart
- **Animation**: set a frame interval and generate an animated GIF of
  concentrations across all timesteps. Download the GIF when done.

See also: [postfile API reference](api/postfile.md),
[visualization API reference](api/visualization.md)

---

## Page 7: Export

Export concentration results and model inputs to geospatial formats.
Requires `pip install pyaermod[geo]`.

### Available Formats

**GeoTIFF** -- Raster export with configurable resolution (meters) and
interpolation method (cubic, linear, nearest). Downloads as
`concentration_{period}.tif`.

**GeoPackage / Shapefile / GeoJSON** -- Vector export. Choose what to
include:

- Sources (point/polygon features)
- Receptors (point features)
- Concentrations as points
- Concentrations as contour polygons

**CSV with Lat/Lon** -- Tabular export of concentration data with
coordinates transformed from UTM to WGS84 latitude/longitude. Preview of
the first 20 rows is shown before download.

See also: [geospatial API reference](api/geospatial.md)

---

## Tips

- **Save often** -- Streamlit sessions can reset if the browser tab is
  closed. Use the Project Save/Load feature on the Project Setup page.
- **Optional dependencies** -- Some features (interactive maps, geospatial
  export, AERMET configuration) require optional packages. Install with
  `pip install pyaermod[all]` to get everything.
- **AERMOD executable** -- The GUI does not include AERMOD itself. Download
  the compiled binary from [EPA SCRAM](https://www.epa.gov/scram) and
  ensure it is on your PATH or specify the full path on the Run page.

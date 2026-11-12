# Run pyaermod in Your Browser

[Open the app](https://atmmod.github.io/pyaermod/app/){ .md-button .md-button--primary }
[Open the notebooks](https://atmmod.github.io/pyaermod/lite/lab/index.html?path=01_run_aermod_in_your_browser.ipynb){ .md-button }

This site runs pyaermod and AERMOD in the browser in two ways: an app with the same
seven steps as the [pyaermod GUI](gui-guide.md), and a set of Jupyter notebooks. Neither
needs an install, a signed download or a server. Nothing you enter is sent anywhere.

!!! warning "Not for regulatory use"
    The AERMOD here is EPA's public-domain source code compiled to WebAssembly by
    pyaermod. It is not EPA's executable. Use it to learn, teach and explore. Use EPA's
    executable for permit or compliance modeling.

## The app

The app at [`/app/`](https://atmmod.github.io/pyaermod/app/) is the pyaermod GUI without
the Python install. It has the same steps as `pyaermod-app`: Project, Sources, Receptors,
Meteorology, Output, Review & Run and Results. Its project files are the same `.json`
files, so a project saved in one opens in the other.

- **Meteorology.** Pick one of the two samples (Albany, NY, March 1988, from EPA's
  AERTEST; Houston, February 1996, with rain, from EPA's AERMET test case EX04), or upload
  your own AERMET `.SFC` and `.PFL` files.
- **Terrain.** With elevated terrain, upload AERMAP's receptor or source output, or a CSV
  of `x, y, elevation, hill height`, on the Receptors step. AERMAP does not run in the
  browser.
- **Import deck** reads an AERMOD `.inp` file. Pick the met files and any other files it
  names in the same dialog. Every file the deck reads is looked for by its name alone
  (`../meteorology/a.sfc` becomes `a.sfc`), and a deck that has AERMOD write a file
  outside its own folder is refused.
- **Review & Run** lists what still blocks a run, including files the deck names that
  have not been uploaded, and shows the deck. AERMOD runs in a background worker, so the
  page stays usable; **Cancel** stops the run by restarting the worker, which reloads
  Python (a few seconds once the browser has it cached).
- **Results** shows AERMOD's maxima for each averaging period, maps from the plot files,
  the NAAQS comparison, every summary table (the first 500 rows of each; download the
  `.out` file for all) and the output files to download.

The project and the uploaded files are kept in this browser between visits, until you
clear the site's data. The first visit downloads about 30 MB (Python, numpy, pandas and
matplotlib from the jsDelivr CDN, and pyaermod and AERMOD from this site); later visits
use the browser's cache.

The app cannot run AERMET, AERMAP or BPIP, export KMZ or GeoTIFF files, or keep a run
history beyond the current page. For those, install the GUI (`pipx install
"pyaermod[gui]"`; see the [GUI User Guide](gui-guide.md#install)).

## The notebooks

The notebooks run in a copy of JupyterLite, a version of Jupyter that runs entirely in the
browser, with pyaermod and AERMOD installed. Build an AERMOD input file, run AERMOD on it
and map the results in Python. The files you make stay in your browser's storage until you
clear it.


| Notebook | What it does |
|---|---|
| `01_run_aermod_in_your_browser` | Builds a one-stack project with pyaermod, runs AERMOD and draws a contour map of the period average. Change the stack and run it again. |
| `02_reproduce_epa_aertest` | Runs EPA's AERTEST example and compares every receptor's 1-hour concentration with EPA's published values. |

Both use four days of meteorology from Albany, NY (March 1988), the data that EPA ships
with its AERMOD test cases. To use your own data, upload your AERMET `.SFC` and `.PFL`
files with the file browser's upload button. Then set `surface_file` and `profile_file`
in `MeteorologyPathway` to their names.

## How it is checked

AERMOD is compiled with LLVM Flang, patched by the webR project to produce WebAssembly,
and Emscripten (`scripts/build_aermod_wasm.sh`). On every change to that build, the
`WebAssembly AERMOD` workflow does the following:

- It runs pyaermod's real-AERMOD tests against the build. These tests compare AERTEST's
  1-hour concentrations with EPA's published values (they must agree within 0.01 % at
  all 144 receptors). They also check that pyaermod reads AERMOD's fatal setup and
  runtime errors correctly.
- It runs AERTEST again through pyaermod inside Pyodide, the Python that runs in the
  browser, under Node. This is the same path the notebooks take.

At AERMOD version 26135, the browser build reproduces EPA's AERTEST values exactly.

Two changes to EPA's source are needed for Flang:

- AERMOD 26135 calls `DSIND`, `DCOSD` and `DTAND`. These are gfortran's
  double-precision degree functions, which Flang does not have. The build replaces them
  with the Fortran 2023 functions `SIND`, `COSD` and `TAND`, which give the same results
  for AERMOD's double-precision arguments.
- Flang gets one Fortran runtime call wrong when it compiles for WebAssembly: the call
  behind `INQUIRE (..., OPENED=)` and `INQUIRE (..., EXIST=)`. A small C shim
  (`scripts/wasm/inquire_shim.c`) makes that call correctly. The build stops if any
  other runtime call does not match.

Flang's runtime also differs from gfortran's on one kind of input file. AERMOD steps back
one line in the surface file every hour, and Flang cannot step back over a last line that
has no line ending. EPA's executable reads such a file, so before each run pyaermod adds
the missing line ending to the surface and profile files the deck names.

## What does not work in the browser

- **AERMET, AERMAP and the other EPA programs** are not compiled. Bring AERMET output
  files, and give receptor elevations directly.
- **Terrain and met-data downloads** usually fail, because most data servers do not allow
  requests from web pages.
- **Background runs** (`AERMODRunner.start` and `run_batch`) need threads or processes,
  which the browser's Python does not have. Use `AERMODRunner.run`.
- **Time limits.** A run has none. In a notebook it cannot be stopped, and the notebook
  does not respond until it ends; in the app the page stays usable and Cancel stops it.
  Keep grids and met periods small.

## Build the site yourself

The documentation workflow builds the notebooks into `/lite/` and the app into `/app/`. To
build both locally from a WebAssembly AERMOD build (`aermod.js`, `aermod.wasm`,
`BUILD.txt`), run:

```bash
pip install -r docs/lite/requirements.txt
bash scripts/wasm/build_lite_site.sh <wasm build dir> _site/lite
python -m http.server --directory _site 8000
```

Then open `http://127.0.0.1:8000/app/` or `http://127.0.0.1:8000/lite/`.

To work on the app without a WebAssembly build, serve it against pyaermod in your own
Python, with the `aermod` on your PATH or a replay of a recorded run:

```bash
python scripts/wasm/app_dev_server.py --replay albany_success
```

The app's page is in `webapp/`, and everything it asks of Python goes through one module,
`pyaermod.browser`.

The `WebAssembly AERMOD` workflow uploads that build as an artifact. To make one
yourself, run `scripts/build_aermod_wasm.sh` inside the `ghcr.io/r-wasm/flang-wasm`
container (amd64 only). The notebooks are written by `scripts/wasm/make_lite_notebooks.py`.

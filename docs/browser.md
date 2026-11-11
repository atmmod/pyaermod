# Run pyaermod in Your Browser

[Open the notebooks](https://atmmod.github.io/pyaermod/lite/lab/index.html?path=01_run_aermod_in_your_browser.ipynb){ .md-button .md-button--primary }

This site includes a copy of JupyterLite, a version of Jupyter that runs entirely in the
browser. It comes with pyaermod and AERMOD itself, so you can build an AERMOD input file,
run AERMOD on it and map the results without installing anything. Nothing is sent to a
server. The files you make stay in your browser's storage until you clear it.

!!! warning "Not for regulatory use"
    The AERMOD in these notebooks is EPA's public-domain source code compiled to
    WebAssembly by pyaermod. It is not EPA's executable. Use it to learn, teach and
    explore. Use EPA's executable for permit or compliance modeling.

## The notebooks

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

## What does not work in the browser

- **AERMET, AERMAP and the other EPA programs** are not compiled. Bring AERMET output
  files, and give receptor elevations directly.
- **Terrain and met-data downloads** usually fail, because most data servers do not allow
  requests from web pages.
- **Background runs** (`AERMODRunner.start`, `run_batch` with several workers) need
  threads or processes, which the browser's Python does not have. Use
  `AERMODRunner.run`.
- **Timeouts.** A run cannot be stopped once it starts, and the page does not respond
  until it ends. Keep grids and met periods small.
- **The pyaermod GUI** needs a Python server; install it with
  `pip install "pyaermod[gui]"` (see the [GUI User Guide](gui-guide.md)).

## Build the site yourself

The documentation workflow builds the site into `/lite/`. To build it locally from a
WebAssembly AERMOD build (`aermod.js`, `aermod.wasm`, `BUILD.txt`), run:

```bash
pip install -r docs/lite/requirements.txt
bash scripts/wasm/build_lite_site.sh <wasm build dir> _site/lite
python -m http.server --directory _site/lite 8000
```

The `WebAssembly AERMOD` workflow uploads that build as an artifact. To make one
yourself, run `scripts/build_aermod_wasm.sh` inside the `ghcr.io/r-wasm/flang-wasm`
container (amd64 only). The notebooks are written by `scripts/wasm/make_lite_notebooks.py`.

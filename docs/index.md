# PyAERMOD

**Python wrapper for EPA's AERMOD atmospheric dispersion model.**

PyAERMOD lets you build, run, and analyze AERMOD simulations entirely from
Python or through an interactive web GUI. It generates standards-compliant
input files, executes AERMOD/AERMET/AERMAP, parses output into pandas
DataFrames, and exports results to geospatial formats.

## Features

- **13 source types**: POINT, POINTCAP, POINTHOR, SWPOINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT, BUOYLINE, OPENPIT
- **Run AERMOD** directly from Python with `run_aermod()`
- **Parse output** to pandas DataFrames with `parse_aermod_output()`
- **POSTFILE support**: formatted (PLOT) and binary (UNFORM) with timestep-level data
- **Visualization**: contour plots, interactive Folium maps, 3D surfaces, wind roses, animations
- **Preprocessors**: AERMET (Stage 1 and METPREP runstreams), AERMAP (terrain), BPIP (building downwash)
- **Geospatial export**: GeoTIFF, GeoPackage, Shapefile, GeoJSON
- **Interactive GUI**: a seven-step NiceGUI app (`pyaermod-app` in the browser, `pyaermod-desktop` as a native window)
- **Nothing to install**: the same seven steps, and Jupyter notebooks, [run in your browser](browser.md) with AERMOD compiled to WebAssembly (not for regulatory use)

## Getting Started

- [Run pyaermod in your browser](browser.md) -- build, run and map an AERMOD model in a notebook, with nothing to install
- [Quick Start Guide](quickstart.md) -- your first AERMOD run in Python
- [Ten Common AERMOD Jobs](use-cases.md) -- runnable, tested scripts for permitting, downwash, roads, NO2, terrain, deposition and air toxics
- [GUI User Guide](gui-guide.md) -- using the interactive web interface
- [API Reference](api/index.md) -- module-by-module documentation
- [How pyaermod is organised](architecture.md) -- a map of the code for contributors

### Practitioner guides

- [AERMET Tuning Guide](aermet-tuning-guide.md) -- data sources, stages, QA/QC
- [AERMAP Troubleshooting](aermap-troubleshooting.md) -- datums, DEMs, hill heights
- [Common Errors and Fixes](common-errors.md) -- cryptic crashes decoded
- [Regulatory Compliance Matrix](regulatory-matrix.md) -- Appendix W / screening profiles

## Installation

```bash
pip install pyaermod               # the library
pip install "pyaermod[all]"        # with plotting, GIS export and the GUI
```

[Install](install.md) has the extras, the GUI on its own, conda, getting
AERMOD itself, and what to do when an install fails.

## Requirements

- Python >= 3.11
- numpy, pandas (core dependencies)
- AERMOD executable from [EPA SCRAM](https://www.epa.gov/scram) (for running simulations)

## Citing PyAERMOD

If PyAERMOD contributes to published work, please cite the archival
release. The repository's `CITATION.cff` carries the metadata in a form
GitHub, Zenodo and reference managers read directly:

> Capps, S. (2026). *PyAERMOD: Python wrapper for EPA's AERMOD air
> dispersion model* (version 2.2.0) [Computer software].
> https://doi.org/10.5281/zenodo.23512927

A journal article describing PyAERMOD and its validation is in
preparation for the *Journal of the Air & Waste Management Association*;
once published, citing the article is preferred.

## License

MIT

# pyaermod

pyaermod writes, runs and reads AERMOD simulations from Python or a
graphical interface. It writes AERMOD input files, runs AERMOD, AERMET,
AERMAP and the other EPA programs, reads their output into pandas
DataFrames, and exports results to GIS formats.

## What it does

- **13 source types**: POINT, POINTCAP, POINTHOR, SWPOINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT, BUOYLINE, OPENPIT
- **Run and read**: `run_aermod()`, `parse_aermod_output()`, plot files, and POSTFILEs in both formats (text PLOT and binary UNFORM)
- **Plots and export**: contour plots, Folium maps, 3-D surfaces, wind roses, animations; GeoTIFF, GeoPackage, Shapefile, GeoJSON, KMZ
- **EPA programs**: AERMET (Stage 1 and Stage 2, METPREP), AERMAP (terrain), AERSURFACE, AERSCREEN, and BPIP-PRIME building downwash
- **GUI**: a seven-step NiceGUI app, `pyaermod-app` in a browser tab and `pyaermod-desktop` in a native window
- **Nothing to install**: the same seven steps, and Jupyter notebooks, [run in your browser](browser.md) with AERMOD compiled to WebAssembly (not for regulatory use)

## Getting started

[Install](install.md) has the extras, the GUI on its own, conda, getting
AERMOD itself, and what to do when an install fails.

- [Run pyaermod in your browser](browser.md): build, run and map an AERMOD model in a notebook, with nothing to install
- [Quick start](quickstart.md): your first AERMOD run in Python
- [Ten common AERMOD jobs](use-cases.md): runnable, tested scripts for permitting, downwash, roads, NO2, terrain, deposition and air toxics
- [GUI user guide](gui-guide.md): the interactive interface
- [API reference](api/index.md): module-by-module documentation
- [How pyaermod is organised](architecture.md): a map of the code for contributors

### Practitioner guides

- [AERMET tuning guide](aermet-tuning-guide.md): data sources, stages, QA/QC
- [AERMAP troubleshooting](aermap-troubleshooting.md): datums, DEMs, hill heights
- [Common errors and fixes](common-errors.md): AERMOD messages and pyaermod's checks
- [Regulatory compliance matrix](regulatory-matrix.md): Appendix W and screening profiles

To cite pyaermod, see the README and `CITATION.cff` in the repository.

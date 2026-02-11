# PyAERMOD

**Python wrapper for EPA's AERMOD atmospheric dispersion model.**

PyAERMOD lets you build, run, and analyze AERMOD simulations entirely from
Python or through an interactive web GUI. It generates standards-compliant
input files, executes AERMOD/AERMET/AERMAP, parses output into pandas
DataFrames, and exports results to geospatial formats.

## Features

- **10 source types**: POINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT, BUOYLINE, OPENPIT
- **Run AERMOD** directly from Python with `run_aermod()`
- **Parse output** to pandas DataFrames with `parse_aermod_output()`
- **POSTFILE support**: formatted (PLOT) and binary (UNFORM) with timestep-level data
- **Visualization**: contour plots, interactive Folium maps, 3D surfaces, wind roses, animations
- **Preprocessors**: AERMET (3-stage meteorology), AERMAP (terrain), BPIP (building downwash)
- **Geospatial export**: GeoTIFF, GeoPackage, Shapefile, GeoJSON
- **Interactive GUI**: 7-page Streamlit web interface

## Getting Started

- [Quick Start Guide](quickstart.md) -- your first AERMOD run in Python
- [GUI User Guide](gui-guide.md) -- using the interactive web interface
- [API Reference](api/index.md) -- module-by-module documentation
- [Architecture](architecture.md) -- technical design overview

## Installation

```bash
# Core (input generation, running, parsing)
pip install pyaermod

# With visualization
pip install pyaermod[viz]

# With geospatial export
pip install pyaermod[geo]

# With Streamlit GUI
pip install pyaermod[gui]

# Everything
pip install pyaermod[all]
```

## Requirements

- Python >= 3.11
- numpy, pandas (core dependencies)
- AERMOD executable from [EPA SCRAM](https://www.epa.gov/scram) (for running simulations)

## License

MIT

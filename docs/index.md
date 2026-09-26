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

### Practitioner guides

- [AERMET Tuning Guide](aermet-tuning-guide.md) -- data sources, stages, QA/QC
- [AERMAP Troubleshooting](aermap-troubleshooting.md) -- datums, DEMs, hill heights
- [Common Errors and Fixes](common-errors.md) -- cryptic crashes decoded
- [Regulatory Compliance Matrix](regulatory-matrix.md) -- Appendix W / screening profiles

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

## Citing PyAERMOD

If PyAERMOD contributes to published work, please cite the archival
release. The repository's `CITATION.cff` carries the metadata in a form
GitHub, Zenodo and reference managers read directly:

> Capps, S. (2026). *PyAERMOD: Python wrapper for EPA's AERMOD air
> dispersion model* (version 2.2.0) [Computer software].
> https://github.com/atmmod/pyaermod. DOI: 10.5281/zenodo.XXXXXXX
> (the Zenodo DOI is minted when the v2.2.0 release is published and is
> recorded in `CITATION.cff`).

A journal article describing PyAERMOD and its validation is in
preparation for the *Journal of the Air & Waste Management Association*;
once published, citing the article is preferred.

## License

MIT

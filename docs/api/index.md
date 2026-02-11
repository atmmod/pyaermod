# API Reference

PyAERMOD v0.2.0 provides 14 modules organized by workflow stage.

## Core Modules

| Module | Description |
|--------|-------------|
| [input_generator](input_generator.md) | AERMOD input file generation with all 10 source types, pathways, and project assembly |
| [validator](validator.md) | Configuration validation for all pathways before input file generation |
| [runner](runner.md) | AERMOD subprocess execution with timeout, batch processing, and result capture |
| [output_parser](output_parser.md) | Parse AERMOD `.out` files into pandas DataFrames |
| [postfile](postfile.md) | Parse POSTFILE output -- formatted (PLOT) and unformatted (binary) |

## Visualization

| Module | Description |
|--------|-------------|
| [visualization](visualization.md) | Contour plots, interactive Folium maps, and raster export |
| [advanced_viz](advanced_viz.md) | 3D surface plots, wind roses, concentration animations |

## Preprocessors

| Module | Description |
|--------|-------------|
| [aermet](aermet.md) | AERMET meteorological preprocessor (Stages 1-3) |
| [aermap](aermap.md) | AERMAP terrain preprocessor input generation |
| [terrain](terrain.md) | DEM download and AERMAP pipeline automation |

## Geospatial and Building Downwash

| Module | Description |
|--------|-------------|
| [geospatial](geospatial.md) | Coordinate transforms (UTM/WGS84), GIS export (GeoTIFF, Shapefile, GeoPackage) |
| [bpip](bpip.md) | BPIP building downwash calculations (direction-dependent parameters) |

## GUI

| Module | Description |
|--------|-------------|
| [gui](gui.md) | Streamlit interactive web GUI with 7-page modeling workflow |

## Optional Dependencies

Different modules require different optional packages. Install what you need:

| Extras Group | Modules Enabled | Install Command |
|--------------|----------------|-----------------|
| `viz` | visualization, advanced_viz | `pip install pyaermod[viz]` |
| `geo` | geospatial, terrain | `pip install pyaermod[geo]` |
| `gui` | gui (includes viz) | `pip install pyaermod[gui]` |
| `all` | Everything | `pip install pyaermod[all]` |

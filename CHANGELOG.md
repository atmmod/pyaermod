# Changelog

All notable changes to PyAERMOD will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-02-10

### Added

#### Source Types
- **AreaSource** — rectangular area sources with rotation angle
- **AreaCircSource** — circular area sources with configurable vertex count
- **AreaPolySource** — irregular polygonal area sources
- **VolumeSource** — 3D emission volumes with initial dispersion
- **LineSource** — general linear sources (conveyors, pipelines)
- **RLineSource** — roadway-specific sources with mobile source physics
- **RLineExtSource** — extended roadway with per-endpoint elevations, optional barriers and road depression
- **BuoyLineSource** / **BuoyLineSegment** — buoyant line source groups with BLPINPUT/BLPGROUP
- **OpenPitSource** — open pit mine/quarry sources

#### Modules
- **Validator** (`pyaermod.validator`) — configuration validation for all 5 AERMOD pathways with cross-field checks
- **BPIP** (`pyaermod.bpip`) — building downwash / BPIP integration with 36-direction building parameters
- **AERMET** (`pyaermod.aermet`) — meteorological preprocessor input generation (Stages 1-3)
- **AERMAP** (`pyaermod.aermap`) — terrain preprocessor input generation with `from_aermod_project()` bridge
- **POSTFILE** (`pyaermod.postfile`) — POSTFILE output parser with timestep/receptor queries
- **Geospatial** (`pyaermod.geospatial`) — coordinate transforms (UTM/WGS84), GeoDataFrame creation, contour generation, GeoTIFF/GeoPackage/Shapefile/GeoJSON export
- **Terrain** (`pyaermod.terrain`) — DEM tile download from USGS TNM, AERMAP runner, output parser, elevation update pipeline
- **GUI** (`pyaermod.gui`) — 7-page Streamlit web application for interactive AERMOD workflow

#### Testing
- 429 tests across 14 test files covering all modules
- Integration tests for end-to-end workflow validation

#### Documentation
- 5 Jupyter tutorial notebooks (Getting Started through Visualization)
- 5 example scripts (area sources, volume sources, line sources, BPIP, end-to-end)

### Changed
- **Package layout**: moved from flat root modules to `src/pyaermod/` package structure
- **Imports**: `from pyaermod.input_generator import ...` (was `from pyaermod_input_generator import ...`)
- **Python**: minimum version raised to 3.9 (was 3.8)
- Updated `setup.py` extras: added `[geo]`, `[gui]`, `[terrain]`, `[all]` dependency groups

## [0.1.0] - 2026-02-04

### Added
- **PointSource** with full stack parameters and building downwash (PRIME) support
- **Receptor grids**: Cartesian, polar, and discrete receptors
- **AERMOD input generation** for all 5 pathways (CO, SO, RE, ME, OU)
- **Output parser**: parse `.out` files to pandas DataFrames, extract metadata, find max concentrations
- **Visualization**: contour plots (matplotlib), interactive maps (folium)
- **Runner**: `AERMODRunner` with subprocess execution, `BatchRunner` for parallel processing
- Project setup: `setup.py`, MIT license, `.gitignore`

---

[Unreleased]: https://github.com/atmmod/pyaermod/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/atmmod/pyaermod/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/atmmod/pyaermod/releases/tag/v0.1.0

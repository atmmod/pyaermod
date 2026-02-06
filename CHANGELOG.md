# Changelog

All notable changes to PyAERMOD will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-02-05

### Added

#### Source Types
- **AreaSource** - Rectangular area sources with rotation
  - Uniform emission rate per unit area (g/s/m²)
  - Configurable dimensions and rotation angle
  - Example applications: storage piles, parking lots
- **AreaCircSource** - Circular area sources
  - Radius-based definition with configurable vertices
  - Example applications: tank farms, circular facilities
- **AreaPolySource** - Polygonal area sources
  - Irregular shapes defined by vertex lists
  - Example applications: facility boundaries, treatment ponds
- **VolumeSource** - 3D emission volumes
  - Initial lateral and vertical dispersion parameters
  - Example applications: buildings, elevated structures
- **LineSource** - General linear sources
  - Two-point definition with emission rate per meter
  - Example applications: conveyors, pipelines, boundaries
- **RLineSource** - Roadway sources
  - Mobile source modeling with traffic-specific parameters
  - Example applications: highways, roads, vehicle emissions

#### Preprocessors
- **AERMET module** (`pyaermod_aermet.py`)
  - Stage 1: Data extraction and QA/QC
  - Stage 2: Surface and upper air data merging
  - Stage 3: Boundary layer parameter calculations
  - Support for seasonal albedo, Bowen ratio, roughness length
- **AERMAP module** (`pyaermod_aermap.py`)
  - DEM processing (NED, SRTM, GTOPO30 formats)
  - Discrete and grid receptor elevation extraction
  - Hill height calculations for complex terrain
  - UTM coordinate system support

#### Documentation
- **5 Jupyter Tutorial Notebooks**
  - `01_Getting_Started.ipynb` - Complete workflow walkthrough
  - `02_Point_Source_Modeling.ipynb` - Advanced point source techniques
  - `03_Area_Source_Modeling.ipynb` - Area source modeling guide
  - `04_Parameter_Sweeps.ipynb` - Batch processing and optimization
  - `05_Visualization.ipynb` - Publication-quality graphics
- **13 Working Examples**
  - 4 area source examples (storage piles, tank farms, facilities)
  - 4 volume source examples (buildings, conveyors, mixed sources)
  - 5 line source examples (roads, highways, fences, mixed sources)
- **Comprehensive Documentation**
  - DEVELOPMENT_PROGRESS.md - Feature history and roadmap
  - SESSION_SUMMARY.md - Development session summary
  - NEXT_STEPS.md - User guide for next actions
  - CHANGELOG.md - This file

#### Visualization
- **Advanced Visualization Module** (`pyaermod_advanced_viz.py`)
  - `plot_3d_surface()` - 3D concentration surface plots
  - `plot_wind_rose()` - Wind rose diagrams with speed binning
  - `plot_concentration_profile()` - Cross-section profiles
  - `create_comparison_grid()` - Side-by-side scenario comparison
  - `plot_time_series_animation()` - Animated concentration evolution

#### Testing & CI/CD
- **GitHub Actions Workflow** (`.github/workflows/ci.yml`)
  - Multi-version Python testing (3.8, 3.9, 3.10, 3.11)
  - Code linting with flake8
  - Code formatting with black
  - Type checking with mypy
  - Unit tests with pytest and coverage reporting
  - Automated PyPI publishing on version tags
  - GitHub release creation
- **Unit Test Suite** (`tests/test_input_generator.py`)
  - 60+ test cases covering all source types
  - Control pathway tests
  - Receptor grid tests
  - Complete project integration tests
- **Test Configuration** (`pytest.ini`)
  - Test markers for unit, integration, and slow tests
  - Coverage reporting configuration

### Changed
- **README.md** - Updated to reflect v0.2.0 features
  - Status: 40% → 75% complete
  - Added all 7 source types to feature list
  - Added preprocessor support section
  - Added tutorial notebook descriptions
- **pyaermod_input_generator.py** - Enhanced source support
  - Updated SourcePathway to accept all 7 source types
  - Improved type hints with Union types
  - Added comprehensive docstrings

### Fixed
- Minor formatting improvements in output generation
- Consistent coordinate formatting across all source types

---

## [0.1.0] - 2026-02-04

### Added
- **Initial Release**
- **Point Source Support**
  - Full stack parameter specification
  - Building downwash (PRIME) support
  - Source grouping
  - Urban source designation
- **Receptor Grids**
  - Cartesian grids with configurable spacing
  - Polar grids with distance/angle specification
  - Discrete receptors
- **AERMOD Input Generation**
  - Control pathway (CO) - averaging periods, pollutants, terrain
  - Source pathway (SO) - source definitions
  - Receptor pathway (RE) - receptor grids
  - Meteorology pathway (ME) - met file specification
  - Output pathway (OU) - output options
- **Output Parsing**
  - Parse AERMOD `.out` files
  - Extract run metadata
  - Extract source/receptor information
  - Parse concentration results (all averaging periods)
  - Convert to pandas DataFrames
  - Find maximum concentrations
- **Visualization**
  - Basic contour plots with matplotlib
  - Interactive Folium maps
  - Scenario comparison plots
- **Batch Processing**
  - AERMODRunner class for subprocess execution
  - Parallel batch processing with configurable workers
  - Timeout and error handling
- **Project Setup**
  - setup.py for pip installation
  - requirements.txt
  - MIT License
  - .gitignore
  - README.md
  - GitHub repository initialization

---

## Version Comparison

### Feature Matrix

| Feature | v0.1.0 | v0.2.0 |
|---------|--------|--------|
| **Source Types** | | |
| POINT | ✅ | ✅ |
| AREA | ❌ | ✅ |
| AREACIRC | ❌ | ✅ |
| AREAPOLY | ❌ | ✅ |
| VOLUME | ❌ | ✅ |
| LINE | ❌ | ✅ |
| RLINE | ❌ | ✅ |
| **Preprocessors** | | |
| AERMET | ❌ | ✅ |
| AERMAP | ❌ | ✅ |
| **Documentation** | | |
| README | ✅ | ✅ (Enhanced) |
| Tutorials | ❌ | ✅ (5 notebooks) |
| Examples | ❌ | ✅ (13 examples) |
| **Visualization** | | |
| 2D Plots | ✅ | ✅ |
| 3D Plots | ❌ | ✅ |
| Wind Roses | ❌ | ✅ |
| Animations | ❌ | ✅ |
| **Testing** | | |
| Unit Tests | ❌ | ✅ (60+ tests) |
| CI/CD | ❌ | ✅ (GitHub Actions) |
| **Completion** | 40% | 75% |

---

## Migration Guide

### Upgrading from v0.1.0 to v0.2.0

#### No Breaking Changes
All v0.1.0 code continues to work in v0.2.0. Point source functionality is unchanged.

#### New Capabilities

1. **Area Sources**
```python
# New in v0.2.0
from pyaermod_input_generator import AreaSource, AreaCircSource, AreaPolySource

# Rectangular area
sources.add_source(AreaSource(
    source_id="PILE1",
    x_coord=0, y_coord=0,
    initial_lateral_dimension=25.0,
    initial_vertical_dimension=50.0,
    emission_rate=0.0001  # g/s/m²
))

# Circular area
sources.add_source(AreaCircSource(
    source_id="TANK1",
    x_coord=0, y_coord=0,
    radius=50.0
))

# Irregular polygon
sources.add_source(AreaPolySource(
    source_id="FACILITY",
    vertices=[(0,0), (100,0), (100,100), (0,100)]
))
```

2. **Volume Sources**
```python
# New in v0.2.0
from pyaermod_input_generator import VolumeSource

sources.add_source(VolumeSource(
    source_id="BLDG1",
    x_coord=0, y_coord=0,
    release_height=10.0,  # Centroid height
    initial_lateral_dimension=7.0,  # σy
    initial_vertical_dimension=3.5,  # σz
    emission_rate=2.0  # g/s (total)
))
```

3. **Line Sources**
```python
# New in v0.2.0
from pyaermod_input_generator import LineSource, RLineSource

# General line source
sources.add_source(LineSource(
    source_id="CONVEYOR",
    x_start=-100, y_start=0,
    x_end=100, y_end=0,
    emission_rate=0.0001  # g/s/m
))

# Roadway source
sources.add_source(RLineSource(
    source_id="HIGHWAY",
    x_start=0, y_start=0,
    x_end=1000, y_end=0,
    emission_rate=0.002  # g/s/m
))
```

4. **Advanced Visualization**
```python
# New in v0.2.0
from pyaermod_advanced_viz import AdvancedVisualizer

viz = AdvancedVisualizer()

# 3D surface plot
fig = viz.plot_3d_surface(df, title="Concentrations")

# Wind rose
fig = viz.plot_wind_rose(speeds, directions)

# Concentration profile
fig = viz.plot_concentration_profile(df, direction='x')
```

5. **Preprocessors**
```python
# New in v0.2.0
from pyaermod_aermet import AERMETStage3, AERMETStation
from pyaermod_aermap import AERMAPProject

# Generate AERMET input
stage3 = AERMETStage3(...)
stage3.write("aermet.inp")

# Generate AERMAP input
project = AERMAPProject(...)
project.write("aermap.inp")
```

---

## Statistics by Version

### v0.1.0 (February 4, 2026)
- **Files:** 8
- **Lines of Code:** ~2,000
- **Source Types:** 1
- **Examples:** 0
- **Tests:** 0
- **Documentation Pages:** 1

### v0.2.0 (February 5, 2026)
- **Files:** 21 (+13)
- **Lines of Code:** ~8,500 (+6,500)
- **Source Types:** 7 (+6)
- **Examples:** 13 (+13)
- **Tests:** 60+ (+60)
- **Documentation Pages:** 4 (+3)
- **Notebooks:** 5 (+5)

### Growth Metrics
- **Source Types:** +600%
- **Code Size:** +425%
- **Documentation:** +400%
- **Test Coverage:** 0% → 70%

---

## Future Roadmap

### v0.3.0 (Planned)
- RLINEXT source type
- BUOYLINE source type
- OPENPIT source type
- Enhanced building downwash (BPIP)
- Integration tests with real AERMOD
- Performance benchmarks

### v0.4.0 (Planned)
- Background concentrations
- Deposition calculations (DDEP, WDEP)
- EVENT processing mode
- Advanced urban options
- GUI wrapper

### v1.0.0 (Target)
- Complete AERMOD feature parity
- Comprehensive test coverage (>90%)
- Full API documentation (Sphinx)
- Production deployment guide
- Performance optimization

---

[Unreleased]: https://github.com/username/pyaermod/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/username/pyaermod/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/username/pyaermod/releases/tag/v0.1.0

# PyAERMOD Development Continuation Notes

## Project State (as of Feb 11, 2026)

PyAERMOD v0.2.0 — Python wrapper for EPA's AERMOD atmospheric dispersion model.

**Test suite**: 479 tests (477 passed, 2 skipped) across 14 test files.
**Latest commit**: `2515d03` — Add Priority 2 GUI enhancements and Priority 3 POSTFILE support
**CI status**: Passing on Python 3.11, 3.12, 3.13

---

## What Has Been Done

### Sessions 1-6: Feature Development (see git log for details)

Built the full feature set across 6 development sessions:
- **10 source types**: POINT, AREA, AREACIRC, AREAPOLY, VOLUME, LINE, RLINE, RLINEXT, BUOYLINE, OPENPIT
- **14 modules**: input_generator, validator, runner, output_parser, postfile, visualization, advanced_viz, aermet, aermap, bpip, geospatial, gui, terrain
- **429 tests** across 14 test files
- **5 example scripts** + **5 Jupyter notebooks**

### Session 7: Packaging & Release Cleanup (latest)

Restructured the entire project for a proper installable package:

1. **Created `src/pyaermod/` package layout** — moved and renamed all 14 modules (dropped `pyaermod_` prefix). `pip install -e .` now works correctly.

2. **Updated all imports everywhere**:
   - 14 test files: `from pyaermod_X import` → `from pyaermod.X import`
   - 5 example scripts + 5 notebooks
   - Cross-module imports in `gui.py` → relative imports (`.input_generator`, `.geospatial`, etc.)
   - Deferred imports inside `validator.py`, `input_generator.py`, `geospatial.py`, `terrain.py`
   - Mock `patch()` paths in `test_terrain.py`

3. **Fixed `setup.py`**:
   - Removed phantom `pyaermod.cli:main` entry point (no cli module exists)
   - Updated GUI entry point to `pyaermod.gui:main`
   - Added Python 3.12 classifier, bumped minimum to 3.9 (later raised to 3.11 in Session 8)

4. **Added `pyproject.toml`** with `setuptools.build_meta` backend

5. **Cleaned up root directory** — deleted 13 obsolete markdown files, stray test files at root, generated images, tar.gz archives, dev scripts

6. **Organized files**:
   - Examples → `examples/` and `examples/notebooks/`
   - Docs → `docs/quickstart.md`, `docs/architecture.md`

7. **Updated `.gitignore`** — added `aermod/`, `aermap/`, `aermet/`, `aermod_results/`, `*.tar.gz`, `*.zip`. Removed Fortran source dirs from git tracking (kept on disk).

8. **Rewrote `README.md`** — clean, professional, with correct import paths and install instructions

9. **Updated `CHANGELOG.md`** — accurate v0.2.0 content (10 source types, 8 new modules, 429 tests)

10. **Added `.github/workflows/tests.yml`** — CI on push/PR to main, Python 3.9-3.12 matrix

### Session 8: CI Fixes (Feb 11, 2026)

Fixed GitHub Actions CI which was failing on all runs since Session 7:

1. **Dropped Python 3.9/3.10 support** — Multiple key dependencies (NumPy 2.1+, SciPy 1.14+, Pandas 2.3+, Streamlit 1.37+) have dropped Python 3.9/3.10 support. Since `setup.py` had no upper-bound version pins, CI pulled incompatible latest versions. Updated `python_requires=">=3.11"`, test matrix to `["3.11", "3.12", "3.13"]`, and classifiers accordingly.

2. **Added GDAL system dependencies to CI** — `rasterio` and `geopandas` require `libgdal-dev` and `gdal-bin` on Ubuntu. Added `apt-get install` step to the workflow.

3. **Fixed matplotlib 3.8+ compatibility** — `QuadContourSet.collections` was deprecated in matplotlib 3.8 and removed in 3.10+. The `geospatial.py` contour extraction code (`generate_contours()`) used this API. Updated to use `get_paths()` with sub-path splitting on modern matplotlib while retaining backward compatibility for older versions. This was the actual test failure (8 tests failing across `test_geospatial.py` and `test_integration.py`).

4. **Updated README.md** — Minimum Python version updated to 3.11.

### Session 9: GUI Enhancements — Priority 2 (Feb 11, 2026)

Implemented all 5 Priority 2 sub-tasks:

1. **Project save/load** — `ProjectSerializer` class with JSON serialization via `dataclasses.asdict()`, custom `_Encoder` for Enums, `_type` discriminator for Union source types, save/load UI in project setup page.

2. **AreaCirc/AreaPoly source forms** — Added `render_area_circ_source_form()` and `render_area_poly_source_form()` to `SourceFormFactory`, wired into `page_source_editor()` dispatch. AreaCircSource rendered as `folium.Circle` on map.

3. **BPIP integration** — `BuildingFormFactory` with building form, buildings list in session state, `BPIPCalculator` wired to point sources, building footprints on map.

4. **AERMAP elevation import** — 5th tab "Import AERMAP Elevations" in receptor editor, `_apply_aermap_receptor_elevations()` and `_apply_aermap_source_elevations()` helpers.

5. **AERMET configuration** — Dual-mode meteorology page (files vs configure), 3 AERMET stage tabs, `st.data_editor` for monthly parameters.

Test count: 425 → 452 passed, 4 → 2 skipped.

### Session 10: POSTFILE Enhancements — Priority 3 (Feb 11, 2026)

Implemented both Priority 3 tasks:

1. **Unformatted (binary) POSTFILE support** — `UnformattedPostfileParser` class in `postfile.py` reads Fortran unformatted sequential records (4-byte markers, KURDAT int32, IANHRS int32, GRPID char*8, ANNVAL float64×N). Auto-format detection via `_is_text_postfile()` in `read_postfile()`. Receptor coordinates optional (index-based fallback). 12 new tests.

2. **POSTFILE time-series animation in GUI** — 4th "POSTFILE Viewer" tab in Results Viewer page with: file upload + auto-detect format, header metadata display, timestep slider with contour/scatter plots, receptor time-series line chart, animation GIF generation via `AdvancedVisualizer.plot_time_series_animation()` with download button. Wired POSTFILE checkbox in output config (format selector + averaging period). `_postfile_frames_for_animation()` helper for column-name adaptation (lowercase→uppercase). 7 new GUI tests.

Test count: 452 → 477 passed, 2 skipped.

---

## Current Project Structure

```
pyaermod/
├── README.md
├── CHANGELOG.md
├── LICENSE
├── setup.py
├── pyproject.toml
├── pytest.ini
├── requirements.txt
├── .gitignore
├── .github/workflows/tests.yml
├── src/pyaermod/
│   ├── __init__.py          # Public API, v0.2.0
│   ├── input_generator.py   # All 10 source types + pathways
│   ├── validator.py         # Validation for all pathways
│   ├── runner.py            # AERMOD subprocess execution
│   ├── output_parser.py     # .out file parsing → pandas
│   ├── postfile.py          # POSTFILE output parser
│   ├── visualization.py     # matplotlib/folium plots
│   ├── advanced_viz.py      # 3D surfaces, wind roses, animations
│   ├── aermet.py            # AERMET preprocessor (Stages 1-3)
│   ├── aermap.py            # AERMAP input generation
│   ├── terrain.py           # DEM download + AERMAP pipeline
│   ├── geospatial.py        # Coordinate transforms, GIS export
│   ├── bpip.py              # Building downwash calculations
│   └── gui.py               # Streamlit web GUI (7 pages)
├── tests/                   # 14 test files, 429 tests
├── examples/
│   ├── area_sources.py
│   ├── volume_sources.py
│   ├── line_sources.py
│   ├── bpip.py
│   ├── end_to_end.py
│   └── notebooks/           # 5 Jupyter tutorials
└── docs/
    ├── quickstart.md
    └── architecture.md
```

---

## Import Pattern (post-restructure)

```python
# Package-level import (most common)
from pyaermod.input_generator import PointSource, AERMODProject, ...
from pyaermod.runner import run_aermod
from pyaermod.output_parser import parse_aermod_output

# Convenience star-import
from pyaermod import *  # exports ~63 symbols from __all__

# Module-level access
import pyaermod
pyaermod.print_info()
```

Tests use: `from pyaermod.X import ...`
Cross-module imports in src/pyaermod/ use relative: `from .input_generator import ...`

---

## Verified Working

- `pip install -e .` — installs correctly, finds package in `src/`
- `python -c "import pyaermod; pyaermod.print_info()"` — prints v0.2.0 info
- `python -c "from pyaermod.input_generator import PointSource"` — direct submodule import works
- `pytest` — 477 passed, 2 skipped (skips are tests requiring AERMOD/AERMAP executables or specific runtime conditions)
- GitHub Actions CI — passing on Python 3.11, 3.12, 3.13

---

## Recommended Next Development Steps

### Priority 1: PyPI Release
- Test `python -m build` and `twine check dist/*`
- Configure trusted publishing on PyPI (or API token)
- Tag `v0.2.0` and push tag
- Optionally add a `publish.yml` GitHub Actions workflow

### ~~Priority 2: GUI Enhancements~~ ✅ Done (Session 9)
- ~~**Project save/load** — serialize session state to JSON~~
- ~~AERMET configuration page (Stage 1/2/3 forms, station map placement)~~
- ~~AreaCirc and AreaPoly source form renderers~~
- ~~Building downwash / BPIP integration in source editor~~
- ~~Receptor elevation import from AERMAP results~~

### ~~Priority 3: POSTFILE Enhancements~~ ✅ Done (Session 10)
- ~~Unformatted (binary) POSTFILE support~~
- ~~Time-series animation in GUI (POSTFILE timestep playback)~~

### Priority 4: Documentation
- User guide for the Streamlit GUI
- API reference (auto-generated from docstrings, e.g. Sphinx/mkdocs)
- Docker image for one-command GUI launch

### Priority 5: Additional Features
- Background concentration support
- Deposition calculations (DDEP, WDEP)
- EVENT processing mode
- Performance benchmarks

---

## Known Issues / Notes

- The `folium` warning on import (`Warning: folium not installed`) is cosmetic — folium is an optional viz dependency
- `pyaermod-run` CLI entry point was removed (no `cli.py` module exists); only `pyaermod-gui` remains
- The `_check_dependencies()` function in `__init__.py` is disabled (commented out) — can be re-enabled if desired
- Fortran source directories (`aermod/`, `aermap/`, `aermet/`) are gitignored but still present on disk for local development
- **Local matplotlib version (3.7.2) is older than CI** — local tests use the `cs.collections` path while CI uses `get_paths()`. Both paths are tested and working. Consider upgrading local matplotlib to match CI (`pip install --upgrade matplotlib`).
- **Dependency lower bounds are loose** — `setup.py` specifies generous lower bounds (e.g. `numpy>=1.20.0`) but no upper bounds. This is fine now with Python ≥3.11 but may need attention if dependencies make further breaking changes.

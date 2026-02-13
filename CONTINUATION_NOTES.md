# PyAERMOD Development Continuation Notes

## Project State (as of Feb 13, 2026)

PyAERMOD v0.2.0 — Python wrapper for EPA's AERMOD atmospheric dispersion model.

**Test suite**: 622 tests (622 passed, 2 skipped) across 15 test files. **89.0% code coverage.**
**CI status**: Passing on Python 3.11, 3.12, 3.13 (with ruff lint + coverage reporting)

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

### Session 11: Documentation — Priority 4 (Feb 11, 2026)

Set up mkdocs documentation site with auto-generated API reference, GUI user guide, and fixed quickstart:

1. **mkdocs with Material theme** — `mkdocs.yml` at project root, `mkdocstrings[python]` plugin with `paths: [src]` for src-layout discovery, `docstring_style: numpy`. Builds successfully with `mkdocs build`.

2. **API Reference** — `docs/api/index.md` with module table grouped by category (Core, Visualization, Preprocessors, Geospatial, GUI). 14 per-module pages (`docs/api/*.md`) using `:::` directives for auto-generated content from docstrings.

3. **GUI User Guide** — `docs/gui-guide.md` (~280 lines) with page-by-page walkthrough of all 7 GUI pages: Project Setup, Source Editor, Receptor Editor, Meteorology, Run AERMOD, Results Viewer, Export. Includes launch instructions, workflow overview, and cross-references to API docs.

4. **Fixed quickstart.md** — Complete rewrite: all imports updated from `pyaermod_input_generator` to `pyaermod.input_generator`, removed "coming soon" sections, added runner/parser/visualization/POSTFILE/validation usage examples, updated AERMOD keywords to include all 10 source types, fixed license to MIT.

5. **Landing page** — `docs/index.md` with feature highlights, installation, and navigation links.

6. **Stale URL fixes** — `__init__.py` doc URLs updated (`QUICKSTART.md` → `quickstart.md`), `setup.py` project_urls Documentation pointed to GitHub Pages site.

7. **Build infrastructure** — `docs/requirements.txt` (mkdocs, mkdocs-material, mkdocstrings), `site/` added to `.gitignore`.

### Session 14: Testing & Quality — Priority 6 (Feb 13, 2026)

Implemented all 8 Priority 6 sub-tasks:

1. **Coverage infrastructure** — `.coveragerc` with source/omit/exclude config, `pytest.ini` updated with `--cov` flags, `.gitignore` updated for `htmlcov/`, `coverage.xml`, `.coverage`.

2. **Ruff linting** — Replaced flake8 with ruff in `setup.py` dev deps. Added `[tool.ruff]` to `pyproject.toml` (E/W/F/I/UP/B/SIM/RUF rules, line-length=120, py311 target). Auto-fixed 75 violations, manually fixed 54 more across 14 source/test files. Zero violations remaining.

3. **Shared fixtures** — `tests/conftest.py` with `valid_point_source`, `valid_area_source`, `valid_volume_source`, `valid_project`, `sample_concentration_df`, `fake_aermod_exe` fixtures.

4. **Parametrized tests** — Added `@pytest.mark.parametrize` tests: 10-case source keyword check, 9-case deposition keyword check, 15-case point source field validation, 14-case cross-source emission validation, 6-case release height validation.

5. **Coverage gap-filling** — 15 new runner tests (run_aermod convenience, _extract_error_message 6 paths, timeout/OSError, run_batch 3 paths, parameter_sweep). 5 new visualization tests (quick_plot, contour save PNG/PDF). 9 new output parser tests (warnings, empty/malformed files, edge cases).

6. **Hypothesis property-based tests** — `tests/test_property_based.py` with 10 tests using custom strategies (source_ids, coords, positive_floats). Fuzz PointSource/AreaSource/VolumeSource/CartesianGrid generation, validator boundary detection, deposition/background roundtrips.

7. **CI pipeline** — `.github/workflows/tests.yml` updated: ruff lint step before tests, pytest with `--cov` and XML report, coverage artifact upload on Python 3.12.

8. **Pre-commit** — `.pre-commit-config.yaml` with ruff (check + format) and pre-commit-hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files).

Test count: 525 → 622 passed, 2 skipped. **Code coverage: 89.0%.** Hypothesis tests marked `@pytest.mark.slow`.

### Session 13: Additional Features — Priority 5 (Feb 12, 2026)

Implemented all 4 Priority 5 sub-tasks:

1. **Background concentration support** — `BackgroundConcentration` and `BackgroundSector` dataclasses with three modes: uniform value (`SO BACKGRND {value}`), period-specific (`SO BACKGRND {period} {value}`), and sector-dependent (`SO BGSECTOR` + per-sector `SO BACKGRND`). Added `background` field to `SourcePathway`, `_validate_background()` in validator, GUI expander in source editor, serializer support. 13 new tests.

2. **Deposition calculations (DDEP, WDEP)** — `DepositionMethod` enum, `GasDepositionParams`, `ParticleDepositionParams` dataclasses, shared `_deposition_to_aermod_lines()` helper. Added 3 deposition fields to all 10 source types. `OutputPathway.output_type` (CONC/DEPOS/DDEP/WDEP/DETH) wired into PLOTFILE/POSTFILE generation. `_validate_deposition_params()` in validator. GUI: deposition checkboxes in project setup, output type selector. 21 new tests.

3. **EVENT processing mode** — `EventPeriod` and `EventPathway` dataclasses generating `EV STARTING`/`EVENTPER`/`EV FINISHED`. `ControlPathway.eventfil` for `EVENTFIL` keyword. `AERMODProject.write()` extended with `event_filename` parameter. `_validate_events()` in validator. GUI: event editor in Run AERMOD page. 14 new tests.

4. **Performance benchmarks** — `benchmarks/` directory with 3 standalone scripts: `bench_input_gen.py` (source generation speed, 1-1000 sources × 3 types), `bench_output_parse.py` (output parsing, 100-5000 receptors), `bench_postfile.py` (text vs binary parsing). Uses `time.perf_counter()` with no external dependencies. README.md with run instructions.

Test count: 477 → 525 passed, 2 skipped. 7 new exports in `__init__.py`.

### Session 12: Docker Image — Priority 4 Completion (Feb 11, 2026)

Added Docker support for one-command GUI launch:

1. **Dockerfile** — Based on `python:3.11-slim-bookworm` with GDAL system deps (`libgdal-dev`, `gdal-bin`, `gcc`, `g++`). Installs PyAERMOD with `[all]` extras. Streamlit config at `/root/.streamlit/config.toml` (headless, port 8501, 0.0.0.0). Healthcheck on `/_stcore/health`. Image size: ~1.9 GB.

2. **.dockerignore** — Excludes `.git`, `__pycache__`, venvs, Fortran source dirs, IDE files, test artifacts, mkdocs `site/`.

3. **Usage**: `docker build -t pyaermod .` then `docker run -p 8501:8501 pyaermod`, open `http://localhost:8501`.

4. **Tested**: Docker build succeeds, container starts, health endpoint returns HTTP 200, main page serves Streamlit HTML.

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
├── mkdocs.yml               # mkdocs documentation config
├── Dockerfile               # One-command GUI launch
├── .dockerignore
├── benchmarks/              # Performance benchmarks (3 scripts)
├── tests/                   # 15 test files, 622 tests (89% coverage)
├── examples/
│   ├── area_sources.py
│   ├── volume_sources.py
│   ├── line_sources.py
│   ├── bpip.py
│   ├── end_to_end.py
│   └── notebooks/           # 5 Jupyter tutorials
└── docs/
    ├── index.md             # mkdocs landing page
    ├── quickstart.md        # Quick start guide (updated for v0.2.0)
    ├── gui-guide.md         # GUI user guide (7-page walkthrough)
    ├── architecture.md      # Technical design document
    ├── requirements.txt     # mkdocs build dependencies
    └── api/                 # Auto-generated API reference
        ├── index.md         # Module overview table
        └── *.md             # 14 per-module pages (mkdocstrings)
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
- `pytest` — 622 passed, 2 skipped (skips are tests requiring AERMOD/AERMAP executables or specific runtime conditions)
- `ruff check src/ tests/` — passes with zero violations
- GitHub Actions CI — passing on Python 3.11, 3.12, 3.13

---

## Completed Development Priorities

### Priority 1: PyPI Release
- Test `python -m build` and `twine check dist/*`
- Configure trusted publishing on PyPI (or API token)
- Tag `v0.2.0` and push tag
- Optionally add a `publish.yml` GitHub Actions workflow

### ~~Priority 2: GUI Enhancements~~ ✅ Done (Session 9)
### ~~Priority 3: POSTFILE Enhancements~~ ✅ Done (Session 10)
### ~~Priority 4: Documentation & Docker~~ ✅ Done (Sessions 11-12)
### ~~Priority 5: Additional Features~~ ✅ Done (Session 13)
### ~~Priority 6: Testing & Quality~~ ✅ Done (Session 14)

## Recommended Next Development Steps

### Priority 7: Advanced Features
- Multi-source group management (custom SRCGROUP definitions)
- NO2/SO2 chemistry options (OLM, PVMRM, ARM2)
- Building downwash wake effects (PRIME algorithm integration)
- Terrain processing pipeline improvements (multi-DEM stitching)

### Priority 8: Release & Distribution
- PyPI publish workflow (GitHub Actions)
- Conda-forge recipe
- Pre-built Docker images on Docker Hub/GHCR

---

## Known Issues / Notes

- The `folium` warning on import (`Warning: folium not installed`) is cosmetic — folium is an optional viz dependency
- `pyaermod-run` CLI entry point was removed (no `cli.py` module exists); only `pyaermod-gui` remains
- The `_check_dependencies()` function in `__init__.py` is disabled (commented out) — can be re-enabled if desired
- Fortran source directories (`aermod/`, `aermap/`, `aermet/`) are gitignored but still present on disk for local development
- **Local matplotlib version (3.7.2) is older than CI** — local tests use the `cs.collections` path while CI uses `get_paths()`. Both paths are tested and working. Consider upgrading local matplotlib to match CI (`pip install --upgrade matplotlib`).
- **Dependency lower bounds are loose** — `setup.py` specifies generous lower bounds (e.g. `numpy>=1.20.0`) but no upper bounds. This is fine now with Python ≥3.11 but may need attention if dependencies make further breaking changes.

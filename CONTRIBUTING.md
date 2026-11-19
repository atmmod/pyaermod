# Contributing to pyaermod

## Development Setup

```bash
# Clone the repository
git clone https://github.com/atmmod/pyaermod.git
cd pyaermod

# Install in editable mode with all dev dependencies
pip install -e ".[dev,all]"

# Install the pre-commit hooks (pre-commit is not in the dev extra)
pip install pre-commit
pre-commit install
```

### System Dependencies

The `[geo]` extra (and therefore `[all]`) pulls in `rasterio` and `pyproj`,
which need the GDAL/PROJ native libraries. Install GDAL **before**
`pip install -e ".[dev,all]"` — without it the `rasterio` build fails and
the geospatial tests (GeoTIFF export, coordinate transforms, terrain
download) are skipped rather than run:

```bash
# Ubuntu / Debian
sudo apt-get install libgdal-dev gdal-bin

# macOS (Homebrew)
brew install gdal
```

Everything outside `[geo]` installs without system packages.

## Running Tests

The `Makefile` wraps the commands CI runs:

```bash
make test        # core suite with whatever extras you have installed
make test-full   # pip install -e ".[dev,all]" (needs GDAL, see above), then
                 # the whole suite including slow tests, with coverage
make lint        # ruff check src/ tests/
make typecheck   # mypy ratchet gate: fails only if the error count grows
                 # beyond mypy-baseline.txt (lower it with
                 # `python scripts/mypy_gate.py --update`)
```

`make test-full` is what to run before opening a pull request: a green
`make test` on a bare install proves less than it looks, because tests for
optional features (geospatial, visualization, NiceGUI) are skipped when their
extra is missing. It also runs `tests/e2e` when Playwright is installed.
CI's `min-deps` job runs the suite against the oldest supported dependency
versions (`min-constraints.txt`); keep that file and the `>=` floors in
`pyproject.toml` in sync.

Or call pytest directly:

```bash
pytest                                  # default suite (no slow tests, no browser journeys)
pytest tests/test_input_generator.py    # one file
pytest -k "test_point_source"           # tests matching a keyword
pytest -m "not e2e"                     # adds the slow tests (-m replaces pytest.ini's filter)
pytest -o addopts="" -m e2e tests/e2e   # browser journeys: pip install -e ".[e2e]" and
                                        # python -m playwright install chromium
```

CI gates coverage at **95%** (`--cov-fail-under=95` in
`.github/workflows/tests.yml`). New features should include tests that
maintain or improve this threshold. Library code must log, not print:
`import pyaermod` is asserted silent by `tests/test_import_silence.py`,
and the NiceGUI GUI is tested headlessly in the `tests/test_gui_v2_*.py`
files (requires the `[gui]` extra and `pytest-asyncio`) and in the
browser journeys under `tests/e2e/` (`make test-gui-e2e`, requires the
`[e2e]` extra and a Playwright Chromium).

## Code Style

pyaermod uses [ruff](https://docs.astral.sh/ruff/) for linting and import
sorting. Configuration is in `pyproject.toml`.

```bash
# Check for lint errors
ruff check src/ tests/

# Auto-fix where possible
ruff check --fix src/ tests/
```

Key style rules:

- **Line length**: 120 characters
- **Python**: 3.11+ (type hints use `typing` module style, not `X | Y`)
- **Imports**: sorted by ruff/isort with `pyaermod` as first-party
- **Docstrings**: NumPy style
- **Dataclasses**: used throughout for configuration objects

## Adding a New Source Type

1. Define the dataclass in `src/pyaermod/sources.py` following existing
   patterns (e.g., `PointSource`); `input_generator.py` re-exports it
2. Implement `to_aermod_input()` to generate valid AERMOD keywords
3. Add validation rules in `src/pyaermod/validator.py`
4. Register the type for the GUI: add it to the `_SOURCE_TYPES` dict in
   `src/pyaermod/gui_v2/pages/sources.py`, give its required fields
   placeholder values in that module's `_DEFAULTS` so the editor opens
   cleanly, and list any field that does not belong on the LOCATION and
   SRCPARAM cards in `ADVANCED_FIELDS`. The editor itself is generated
   from the dataclass; the badge logic in `gui_v2/steps.py` already
   files every `*Source` validator message under the Sources step
5. Update `__init__.py` exports and `__all__`
6. Add tests in `tests/test_input_generator.py` and
   `tests/test_gui_v2_sources.py`
7. Add it to the source-type list in `docs/index.md`

## Building the browser app and notebooks

The documentation workflow builds the notebooks into `/lite/` and the app into `/app/`. To
build both locally from a WebAssembly AERMOD build (`aermod.js`, `aermod.wasm`,
`BUILD.txt`), run:

```bash
pip install -r docs/lite/requirements.txt
bash scripts/wasm/build_lite_site.sh <wasm build dir> _site/lite
python -m http.server --directory _site 8000
```

Then open `http://127.0.0.1:8000/app/` or `http://127.0.0.1:8000/lite/`.

To work on the app without a WebAssembly build, serve it against pyaermod in your own
Python, with the `aermod` on your PATH or a replay of a recorded run:

```bash
python scripts/wasm/app_dev_server.py --replay albany_success
```

The app's page is in `webapp/`, and everything it asks of Python goes through
`pyaermod.browser`.

The `WebAssembly AERMOD` workflow uploads that build as an artifact. To make one
yourself, run `scripts/build_aermod_wasm.sh` inside the `ghcr.io/r-wasm/flang-wasm`
container (amd64 only). The notebooks are written by `scripts/wasm/make_lite_notebooks.py`.

## Submitting Changes

1. **Fork** the repository and create a feature branch
2. **Write tests** for any new functionality
3. **Run the full test suite**: `pytest`
4. **Run the linter**: `ruff check src/ tests/`
5. **Update documentation** if you changed user-facing behavior
6. **Open a pull request** against `main` with a clear description

### Commit Messages

Use clear, descriptive commit messages:

- `Add RLINEXT source type with barrier support`
- `Fix POSTFILE binary parser for big-endian systems`
- `Update quickstart guide with deposition examples`

### Pull Request Checklist

- [ ] Tests pass (`pytest`)
- [ ] Linter passes (`ruff check src/ tests/`)
- [ ] New features have tests
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated under `[Unreleased]`

## Reporting Issues

Please include:

- Python version and OS
- pyaermod version- Minimal reproducible example
- Full error traceback

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.

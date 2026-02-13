# Contributing to PyAERMOD

Thank you for your interest in contributing to PyAERMOD! This guide covers
the development workflow, coding standards, and submission process.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/atmmod/pyaermod.git
cd pyaermod

# Install in editable mode with all dev dependencies
pip install -e ".[dev,all]"

# Install pre-commit hooks
pre-commit install
```

### System Dependencies

For geospatial features (GeoTIFF export, coordinate transforms), you need
GDAL:

```bash
# Ubuntu / Debian
sudo apt-get install libgdal-dev gdal-bin

# macOS (Homebrew)
brew install gdal
```

## Running Tests

```bash
# Run full test suite with coverage
pytest

# Run a specific test file
pytest tests/test_input_generator.py

# Run tests matching a keyword
pytest -k "test_point_source"

# Skip slow property-based tests
pytest -m "not slow"
```

The project targets **89%+ code coverage**. New features should include
tests that maintain or improve this threshold.

## Code Style

PyAERMOD uses [ruff](https://docs.astral.sh/ruff/) for linting and import
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

## Project Layout

```
src/pyaermod/          # Package source (src layout)
tests/                 # Test files (test_*.py)
docs/                  # MkDocs documentation
examples/              # Example scripts and notebooks
benchmarks/            # Performance benchmarks
```

### Key Patterns

- **Source types** are dataclasses with a `to_aermod_input() -> str` method
- **Validation** uses `isinstance` dispatch in `validator.py`
- **Optional dependencies** use `try/except ImportError` with `HAS_*` flags
  and `_require_*()` guard functions
- **GUI** uses Streamlit with `st.session_state` for state management

## Adding a New Source Type

1. Define the dataclass in `src/pyaermod/input_generator.py` following
   existing patterns (e.g., `PointSource`)
2. Implement `to_aermod_input()` to generate valid AERMOD keywords
3. Add validation rules in `src/pyaermod/validator.py`
4. Add the type to `SourceFormFactory.SOURCE_TYPES` in `gui.py`
5. Update `__init__.py` exports and `__all__`
6. Add tests in `tests/test_input_generator.py` and `tests/test_gui.py`
7. Update documentation in `docs/quickstart.md`

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
- PyAERMOD version (`python -c "import pyaermod; print(pyaermod.__version__)"`)
- Minimal reproducible example
- Full error traceback

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.

"""
PyAERMOD - Python wrapper for EPA's AERMOD atmospheric dispersion model

A complete Python toolkit for AERMOD air dispersion modeling that automates
input generation, execution, output parsing, and visualization. Includes
AERMET meteorological preprocessing and POSTFILE output parsing.

The **public API is defined in** :mod:`pyaermod.api` and re-exported here
for convenience — `from pyaermod import *` and `from pyaermod.api import *`
expose the same stable surface. Internal modules (e.g. `pyaermod.validator`,
`pyaermod.input_generator`) remain importable for code that needs access
to implementation details, but their layout is not guaranteed to stay
stable across releases.

Example:
    >>> from pyaermod import *
    >>>
    >>> project = AERMODProject(control, sources, receptors, met, output)
    >>> project.write("facility.inp")
    >>> result = run_aermod("facility.inp")
    >>> results = parse_aermod_output(result.output_file)
    >>> viz = AERMODVisualizer(results)
    >>> viz.plot_contours(save_path="plot.png")

Website: https://github.com/atmmod/pyaermod
Documentation: https://github.com/atmmod/pyaermod/blob/main/docs/quickstart.md
"""

from __future__ import annotations

# Package metadata
__version__ = "2.0.0"
__author__ = "Shannon Capps"
__email__ = "shannon.capps@gmail.com"
__license__ = "MIT"
__url__ = "https://github.com/atmmod/pyaermod"

# ---------------------------------------------------------------------------
# Single source of truth for the public surface.
# Everything listed in api.__all__ is re-exported unchanged.
# ---------------------------------------------------------------------------
from . import api
from . import api as _api
from .api import *  # noqa: F403  -- intentional wildcard re-export

# Expose the same names via an explicit __all__ for type-checkers and
# linters. The list is kept in sync automatically.
__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "__license__",
    "__url__",
    "get_version",
    "print_info",
    "api",
    *list(_api.__all__),
]


def _check_dependencies() -> None:
    """Emit ImportWarning for missing optional visualization deps.

    Uses `builtins.__import__` directly so test fixtures that monkey-
    patch that symbol still see the import attempt. The equivalent
    information is also available via `HAS_GEOSPATIAL` / `HAS_TERRAIN`
    on :mod:`pyaermod.api`.
    """
    import builtins
    import warnings

    for name, hint in (
        ("matplotlib", "Static plotting will be unavailable. pip install matplotlib"),
        ("folium", "Interactive maps will be unavailable. pip install folium"),
        ("scipy", "Contour interpolation will be limited. pip install scipy"),
    ):
        try:
            builtins.__import__(name)
        except ImportError:
            warnings.warn(
                f"{name} not installed. {hint}",
                ImportWarning,
                stacklevel=2,
            )


def get_version() -> str:
    """Return the pyaermod version string."""
    return __version__


def print_info() -> None:
    """Print a one-screen banner of pyaermod features and entry points."""
    print(f"""
PyAERMOD v{__version__}
======================

Python wrapper for EPA's AERMOD atmospheric dispersion model

Author: {__author__} <{__email__}>
License: {__license__}
Repository: {__url__}

Features:
  * Generate AERMOD input files from Python
  * Execute AERMOD automatically
  * Parse outputs to pandas DataFrames
  * Parse POSTFILE formatted output
  * AERMET meteorological preprocessing
  * Create visualizations (plots and maps)
  * Batch processing with tqdm / SLURM integration
  * Geospatial: UTM/WGS84 transforms, GeoTIFF & Shapefile export
  * Interactive Streamlit GUI (pip install pyaermod[gui])
  * Regulatory profile presets (EPA Appendix W 2017 / 2023)
  * Advanced cross-field validation + PRIME/GEP downwash helpers

Quick Start:
  >>> from pyaermod import *
  >>> project = AERMODProject(...)
  >>> project.write("facility.inp")
  >>> result = run_aermod("facility.inp")
  >>> results = parse_aermod_output(result.output_file)

Documentation: {__url__}/blob/main/docs/quickstart.md
""")

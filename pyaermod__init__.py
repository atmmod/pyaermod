"""
PyAERMOD - Python wrapper for EPA's AERMOD atmospheric dispersion model

A complete Python toolkit for AERMOD air dispersion modeling that automates
input generation, execution, output parsing, and visualization. Includes
AERMET meteorological preprocessing and POSTFILE output parsing.

Example:
    >>> from pyaermod import *
    >>>
    >>> # Generate input
    >>> project = AERMODProject(control, sources, receptors, met, output)
    >>> project.write("facility.inp")
    >>>
    >>> # Run AERMOD
    >>> result = run_aermod("facility.inp")
    >>>
    >>> # Parse results
    >>> results = parse_aermod_output(result.output_file)
    >>> df = results.get_concentrations('ANNUAL')
    >>>
    >>> # Parse POSTFILE output
    >>> post = read_postfile("postfile.out")
    >>> print(post.max_concentration, post.max_location)
    >>>
    >>> # Visualize
    >>> viz = AERMODVisualizer(results)
    >>> viz.plot_contours(save_path="plot.png")

Website: https://github.com/atmmod/pyaermod
Documentation: https://github.com/atmmod/pyaermod/blob/main/docs/QUICKSTART.md
"""

__version__ = "0.2.0"
__author__ = "Shannon Capps"
__email__ = "shannon.capps@gmail.com"
__license__ = "MIT"
__url__ = "https://github.com/atmmod/pyaermod"

# Import main components for easy access
from .input_generator import (
    # Main project class
    AERMODProject,

    # Pathway classes
    ControlPathway,
    SourcePathway,
    ReceptorPathway,
    MeteorologyPathway,
    OutputPathway,

    # Source types
    PointSource,

    # Receptor types
    CartesianGrid,
    PolarGrid,
    DiscreteReceptor,

    # Enums
    PollutantType,
    TerrainType,
    SourceType,
)

from .runner import (
    # Runner classes
    AERMODRunner,
    AERMODRunResult,
    BatchRunner,

    # Convenience functions
    run_aermod,
)

from .output_parser import (
    # Result classes
    AERMODResults,
    ModelRunInfo,
    SourceSummary,
    ReceptorInfo,
    ConcentrationResult,

    # Parser classes
    AERMODOutputParser,

    # Convenience functions
    parse_aermod_output,
    quick_summary,
)

from .visualization import (
    # Visualizer class
    AERMODVisualizer,

    # Convenience functions
    quick_plot,
    quick_map,
)

from .aermet import (
    # Station metadata
    AERMETStation,
    UpperAirStation,

    # Processing stages
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,

    # Utility functions
    write_aermet_runfile,
)

from .postfile import (
    # Data classes
    PostfileHeader,
    PostfileResult,

    # Parser
    PostfileParser,

    # Convenience functions
    read_postfile,
)

# AERMAP terrain preprocessor input generator
from .aermap import (
    AERMAPProject,
    AERMAPDomain,
    AERMAPReceptor,
    AERMAPSource,
)

# Geospatial utilities (optional - requires pyproj, geopandas, rasterio, shapely)
try:
    from .geospatial import (
        CoordinateTransformer,
        GeoDataFrameFactory,
        ContourGenerator,
        RasterExporter,
        VectorExporter,
        utm_to_latlon,
        latlon_to_utm,
        export_concentration_geotiff,
        export_concentration_shapefile,
    )
    HAS_GEOSPATIAL = True
except ImportError:
    HAS_GEOSPATIAL = False

# Terrain processing pipeline (optional - requires requests)
try:
    from .terrain import (
        DEMTileInfo,
        DEMDownloader,
        AERMAPRunner,
        AERMAPRunResult,
        AERMAPOutputParser,
        TerrainProcessor,
        run_aermap,
    )
    HAS_TERRAIN = True
except ImportError:
    HAS_TERRAIN = False

# Define public API
__all__ = [
    # Version info
    '__version__',
    '__author__',
    '__email__',

    # Input generation
    'AERMODProject',
    'ControlPathway',
    'SourcePathway',
    'ReceptorPathway',
    'MeteorologyPathway',
    'OutputPathway',
    'PointSource',
    'CartesianGrid',
    'PolarGrid',
    'DiscreteReceptor',
    'PollutantType',
    'TerrainType',
    'SourceType',

    # Runner
    'AERMODRunner',
    'AERMODRunResult',
    'BatchRunner',
    'run_aermod',

    # Output parser
    'AERMODResults',
    'ModelRunInfo',
    'SourceSummary',
    'ReceptorInfo',
    'ConcentrationResult',
    'AERMODOutputParser',
    'parse_aermod_output',
    'quick_summary',

    # Visualization
    'AERMODVisualizer',
    'quick_plot',
    'quick_map',

    # AERMET preprocessor
    'AERMETStation',
    'UpperAirStation',
    'AERMETStage1',
    'AERMETStage2',
    'AERMETStage3',
    'write_aermet_runfile',

    # POSTFILE parser
    'PostfileHeader',
    'PostfileResult',
    'PostfileParser',
    'read_postfile',

    # AERMAP terrain preprocessor
    'AERMAPProject',
    'AERMAPDomain',
    'AERMAPReceptor',
    'AERMAPSource',

    # Geospatial utilities (when available)
    'CoordinateTransformer',
    'GeoDataFrameFactory',
    'ContourGenerator',
    'RasterExporter',
    'VectorExporter',
    'utm_to_latlon',
    'latlon_to_utm',
    'export_concentration_geotiff',
    'export_concentration_shapefile',

    # Terrain processing (when available)
    'DEMTileInfo',
    'DEMDownloader',
    'AERMAPRunner',
    'AERMAPRunResult',
    'AERMAPOutputParser',
    'TerrainProcessor',
    'run_aermap',
]


def get_version():
    """Get PyAERMOD version"""
    return __version__


def print_info():
    """Print package information"""
    print(f"""
PyAERMOD v{__version__}
======================

Python wrapper for EPA's AERMOD atmospheric dispersion model

Author: {__author__} <{__email__}>
License: {__license__}
Repository: {__url__}

Features:
  • Generate AERMOD input files from Python
  • Execute AERMOD automatically
  • Parse outputs to pandas DataFrames
  • Parse POSTFILE formatted output
  • AERMET meteorological preprocessing
  • Create visualizations (plots and maps)
  • Batch processing and parameter sweeps
  • Geospatial: UTM/WGS84 transforms, GeoTIFF & Shapefile export
  • Interactive Streamlit GUI (pip install pyaermod[gui])

Quick Start:
  >>> from pyaermod import *
  >>> project = AERMODProject(...)
  >>> project.write("facility.inp")
  >>> result = run_aermod("facility.inp")
  >>> results = parse_aermod_output(result.output_file)

Documentation: {__url__}/blob/main/docs/QUICKSTART.md
    """)


# Optional: Check for dependencies on import
def _check_dependencies():
    """Check if optional dependencies are available"""
    import warnings

    try:
        import matplotlib
    except ImportError:
        warnings.warn(
            "matplotlib not installed. Static plotting will be unavailable. "
            "Install with: pip install matplotlib",
            ImportWarning
        )

    try:
        import folium
    except ImportError:
        warnings.warn(
            "folium not installed. Interactive maps will be unavailable. "
            "Install with: pip install folium",
            ImportWarning
        )

    try:
        import scipy
    except ImportError:
        warnings.warn(
            "scipy not installed. Contour interpolation will be limited. "
            "Install with: pip install scipy",
            ImportWarning
        )


# Run dependency check on import (optional, can be disabled)
# _check_dependencies()

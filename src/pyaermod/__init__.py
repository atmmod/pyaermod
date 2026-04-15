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
Documentation: https://github.com/atmmod/pyaermod/blob/main/docs/quickstart.md
"""

__version__ = "1.3.0"
__author__ = "Shannon Capps"
__email__ = "shannon.capps@gmail.com"
__license__ = "MIT"
__url__ = "https://github.com/atmmod/pyaermod"

# Import main components for easy access
# AERMAP terrain preprocessor input generator
from .aermap import (
    AERMAPDomain,
    AERMAPProject,
    AERMAPReceptor,
    AERMAPSource,
)
from .aermet import (
    # Processing stages
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,
    # Station metadata
    AERMETStation,
    ProfileFileHeader,
    # Output file parsers
    SurfaceFileHeader,
    UpperAirStation,
    read_profile_file,
    read_surface_file,
    # Utility functions
    write_aermet_runfile,
)
from .input_generator import (
    # Main project class
    AERMODProject,
    # Source types
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    # Background concentration
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    # Receptor types
    CartesianGrid,
    # NO2 chemistry options
    ChemistryMethod,
    ChemistryOptions,
    # Pathway classes
    ControlPathway,
    # Deposition
    DepositionMethod,
    DiscreteReceptor,
    # Event processing
    EventPathway,
    EventPeriod,
    GasDepositionParams,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    OzoneData,
    ParticleDepositionParams,
    PointSource,
    PolarGrid,
    # Enums
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    # Source group management
    SourceGroupDefinition,
    SourcePathway,
    SourceType,
    # Street canyon approximation
    StreetCanyon,
    TerrainType,
    VolumeSource,
)
from .output_parser import (
    # Parser classes
    AERMODOutputParser,
    # Result classes
    AERMODResults,
    ConcentrationResult,
    ModelRunInfo,
    ReceptorInfo,
    SourceSummary,
    # Convenience functions
    parse_aermod_output,
    quick_summary,
)
from .postfile import (
    # Data classes
    PostfileHeader,
    # Parsers
    PostfileParser,
    PostfileResult,
    UnformattedPostfileParser,
    # Convenience functions
    read_postfile,
)
from .runner import (
    # Runner classes
    AERMODRunner,
    AERMODRunResult,
    BatchRunner,
    # Convenience functions
    run_aermod,
)
from .visualization import (
    # Visualizer class
    AERMODVisualizer,
    quick_map,
    # Convenience functions
    quick_plot,
)
from .met_ingest import (
    ASOS1MinRecord,
    IGRAFetcher,
    IGRASounding,
    ISDFetcher,
    ISDStationId,
    MMIFConfig,
    aggregate_1min_to_hourly,
    parse_asos_1min_file,
    parse_asos_1min_line,
    parse_igra_v2,
)
from .validator_advanced import advanced_validate
from .chemistry_presets import (
    DEPOSITION_DEFAULTS,
    PollutantDepositionDefaults,
    arm2_preset,
    deposition_defaults_for,
    deposition_diagnostics,
    grsm_preset,
    olm_preset,
    pvmrm_preset,
    suggest_chemistry_for,
)
from .regulatory import (
    ALL_PROFILES,
    EPA_APPENDIX_W_2017,
    EPA_APPENDIX_W_2023,
    SCREENING_PROFILE,
    RegulatoryProfile,
    get_profile,
)
from .runner_utils import (
    ERRMSGInfo,
    LoggingProgress,
    NoOpProgress,
    ProgressReporter,
    RunManifest,
    RunManifestEntry,
    TqdmProgress,
    extract_errmsg,
    generate_slurm_script,
    resume_batch,
    summarize_failure,
    tail_output,
)
from .terrain_utils import (
    DatumTransformer,
    EPSG_NAD27,
    EPSG_NAD83,
    EPSG_WGS84,
    HillHeightAnomaly,
    SRTMTileInfo,
    async_fetch_tiles,
    hill_height_diagnostics,
    srtm_tile_name,
    srtm_tiles_for_bbox,
    utm_epsg,
    utm_zone_for_lon,
)
from .aermod_outputs import (
    AERMODAuxResult,
    AERMODFileHeader,
    parse_aermod_header,
    read_aermod_aux_file,
    read_deposition,
    read_maxifile,
    read_plotfile,
    read_rankfile,
    read_seasonhr,
    read_toxxfile,
)
from .prime import (
    DownwashAssessment,
    GEP_FLOOR_M,
    apply_bpip_to_project,
    assess_source_downwash,
    cavity_length,
    gep_from_building,
    gep_stack_height,
    in_cavity_region,
    suggest_downwash_config,
)
from .met_qaqc import (
    QAQCFinding,
    QAQCReport,
    check_extremes,
    check_low_wind_bias,
    check_missing_data,
    check_profile_monotonic,
    check_stability_consistency,
    find_missing_runs,
    run_all_qaqc,
)

# Geospatial utilities (optional - requires pyproj, geopandas, rasterio, shapely)
try:
    from .geospatial import (
        ContourGenerator,
        CoordinateTransformer,
        GeoDataFrameFactory,
        RasterExporter,
        VectorExporter,
        export_concentration_geotiff,
        export_concentration_shapefile,
        latlon_to_utm,
        utm_to_latlon,
    )
    HAS_GEOSPATIAL = True
except ImportError:
    HAS_GEOSPATIAL = False

# Terrain processing pipeline (optional - requires requests)
try:
    from .terrain import (
        AERMAPOutputParser,
        AERMAPRunner,
        AERMAPRunResult,
        DEMDownloader,
        DEMTileInfo,
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
    # Source types
    'PointSource',
    'AreaSource',
    'AreaCircSource',
    'AreaPolySource',
    'VolumeSource',
    'LineSource',
    'RLineSource',
    'RLineExtSource',
    'BuoyLineSource',
    'BuoyLineSegment',
    'OpenPitSource',
    'StreetCanyon',
    # Receptor types
    'CartesianGrid',
    'PolarGrid',
    'DiscreteReceptor',
    # Enums
    'PollutantType',
    'TerrainType',
    'SourceType',
    'BackgroundConcentration',
    'BackgroundSector',
    'DepositionMethod',
    'GasDepositionParams',
    'ParticleDepositionParams',
    'EventPeriod',
    'EventPathway',
    'SourceGroupDefinition',
    'ChemistryMethod',
    'ChemistryOptions',
    'OzoneData',

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
    'SurfaceFileHeader',
    'ProfileFileHeader',
    'read_surface_file',
    'read_profile_file',

    # Met data ingest (ASOS 1-min, ISD, IGRA, MMIF)
    'ASOS1MinRecord',
    'parse_asos_1min_line',
    'parse_asos_1min_file',
    'aggregate_1min_to_hourly',
    'ISDStationId',
    'ISDFetcher',
    'IGRASounding',
    'parse_igra_v2',
    'IGRAFetcher',
    'MMIFConfig',

    # Met QA/QC
    'QAQCFinding',
    'QAQCReport',
    'find_missing_runs',
    'check_missing_data',
    'check_extremes',
    'check_stability_consistency',
    'check_low_wind_bias',
    'check_profile_monotonic',
    'run_all_qaqc',

    # Advanced validator (cross-field AERMOD checks)
    'advanced_validate',

    # Chemistry / deposition presets
    'olm_preset',
    'pvmrm_preset',
    'arm2_preset',
    'grsm_preset',
    'suggest_chemistry_for',
    'PollutantDepositionDefaults',
    'DEPOSITION_DEFAULTS',
    'deposition_defaults_for',
    'deposition_diagnostics',

    # Regulatory profiles
    'RegulatoryProfile',
    'EPA_APPENDIX_W_2017',
    'EPA_APPENDIX_W_2023',
    'SCREENING_PROFILE',
    'ALL_PROFILES',
    'get_profile',

    # Runner UX (progress, failure diagnostics, resume, SLURM)
    'ERRMSGInfo',
    'extract_errmsg',
    'tail_output',
    'summarize_failure',
    'ProgressReporter',
    'NoOpProgress',
    'LoggingProgress',
    'TqdmProgress',
    'resume_batch',
    'RunManifest',
    'RunManifestEntry',
    'generate_slurm_script',

    # Terrain utilities (datums, SRTM, mosaic, reproject, diagnostics)
    'DatumTransformer',
    'EPSG_WGS84',
    'EPSG_NAD83',
    'EPSG_NAD27',
    'utm_zone_for_lon',
    'utm_epsg',
    'SRTMTileInfo',
    'srtm_tile_name',
    'srtm_tiles_for_bbox',
    'async_fetch_tiles',
    'HillHeightAnomaly',
    'hill_height_diagnostics',

    # AERMOD auxiliary output readers (PLOTFILE, MAXIFILE, RANKFILE, SEASONHR, TOXXFILE, deposition)
    'AERMODFileHeader',
    'AERMODAuxResult',
    'parse_aermod_header',
    'read_aermod_aux_file',
    'read_plotfile',
    'read_maxifile',
    'read_rankfile',
    'read_seasonhr',
    'read_toxxfile',
    'read_deposition',

    # PRIME / GEP downwash helpers
    'GEP_FLOOR_M',
    'gep_stack_height',
    'gep_from_building',
    'cavity_length',
    'in_cavity_region',
    'DownwashAssessment',
    'assess_source_downwash',
    'apply_bpip_to_project',
    'suggest_downwash_config',

    # POSTFILE parser
    'PostfileHeader',
    'PostfileResult',
    'PostfileParser',
    'UnformattedPostfileParser',
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

Documentation: {__url__}/blob/main/docs/quickstart.md
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
            ImportWarning,
            stacklevel=2,
        )

    try:
        import folium
    except ImportError:
        warnings.warn(
            "folium not installed. Interactive maps will be unavailable. "
            "Install with: pip install folium",
            ImportWarning,
            stacklevel=2,
        )

    try:
        import scipy
    except ImportError:
        warnings.warn(
            "scipy not installed. Contour interpolation will be limited. "
            "Install with: pip install scipy",
            ImportWarning,
            stacklevel=2,
        )


# Run dependency check on import (optional, can be disabled)
# _check_dependencies()

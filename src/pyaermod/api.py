"""
PyAERMOD public API surface.

This module is the narrow, stable entry point for downstream code.
Prefer `from pyaermod.api import X` over `from pyaermod.X import Y` —
internal module layout may change between versions, but the names
exported here are guaranteed to remain available.

Groups:
    - Project building (input generation, pathways, sources, receptors)
    - Validation (base + advanced)
    - Execution (runner + UX helpers)
    - Outputs (parsing .OUT, POSTFILE, auxiliary text outputs)
    - Visualization
    - Meteorology (ingest + QA/QC + AERMET preprocessor)
    - Terrain (AERMAP + datum/mosaic/diagnostics)
    - Regulatory presets
    - PRIME downwash helpers

Each exported name has a stable signature — deprecations will be
announced via a `DeprecationWarning` for at least one minor release
before removal.
"""

from __future__ import annotations

# Package metadata
__version__ = "1.3.0"

# --- Project building -----------------------------------------------------
from .input_reader import parse_aermod_input, read_aermod_input
from .input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    DepositionMethod,
    DiscreteReceptor,
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
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SourceGroupDefinition,
    SourcePathway,
    SourceType,
    StreetCanyon,
    TerrainType,
    VolumeSource,
)

# --- Validation -----------------------------------------------------------
from .validator import ValidationError, ValidationResult, Validator
from .validator_advanced import advanced_validate

# --- Execution ------------------------------------------------------------
from .runner import AERMODRunner, AERMODRunResult, BatchRunner, run_aermod
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

# --- Outputs --------------------------------------------------------------
from .output_parser import (
    AERMODOutputParser,
    AERMODResults,
    ConcentrationResult,
    ModelRunInfo,
    ReceptorInfo,
    SourceSummary,
    parse_aermod_output,
    quick_summary,
)
from .postfile import (
    PostfileHeader,
    PostfileParser,
    PostfileResult,
    UnformattedPostfileParser,
    read_postfile,
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

# --- Visualization --------------------------------------------------------
from .visualization import AERMODVisualizer, quick_map, quick_plot

# --- Meteorology ----------------------------------------------------------
from .aermet import (
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,
    AERMETStation,
    ProfileFileHeader,
    SurfaceFileHeader,
    UpperAirStation,
    read_profile_file,
    read_surface_file,
    write_aermet_runfile,
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

# --- Terrain --------------------------------------------------------------
from .aermap import AERMAPDomain, AERMAPProject, AERMAPReceptor, AERMAPSource
from .terrain_utils import (
    EPSG_NAD27,
    EPSG_NAD83,
    EPSG_WGS84,
    DatumTransformer,
    HillHeightAnomaly,
    SRTMTileInfo,
    async_fetch_tiles,
    hill_height_diagnostics,
    srtm_tile_name,
    srtm_tiles_for_bbox,
    utm_epsg,
    utm_zone_for_lon,
)

# --- Regulatory -----------------------------------------------------------
from .regulatory import (
    ALL_PROFILES,
    EPA_APPENDIX_W_2017,
    EPA_APPENDIX_W_2023,
    SCREENING_PROFILE,
    RegulatoryProfile,
    get_profile,
)

# --- PRIME / downwash -----------------------------------------------------
from .bpip import BPIPCalculator, BPIPResult, Building
from .prime import (
    GEP_FLOOR_M,
    DownwashAssessment,
    apply_bpip_to_project,
    assess_source_downwash,
    cavity_length,
    gep_from_building,
    gep_stack_height,
    in_cavity_region,
    suggest_downwash_config,
)

# --- Chemistry / deposition presets ---------------------------------------
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

# --- Optional-dependency surface -----------------------------------------
# These are only importable when the underlying extras are installed. We
# still list them in `__all__` so users discover them via tab-completion
# and IDEs; at import time the flags below advertise availability.

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

__all__ = [
    "__version__",
    # project
    "AERMODProject", "ControlPathway", "SourcePathway", "ReceptorPathway",
    "MeteorologyPathway", "OutputPathway", "EventPathway", "EventPeriod",
    "PointSource", "AreaSource", "AreaCircSource", "AreaPolySource",
    "VolumeSource", "LineSource", "RLineSource", "RLineExtSource",
    "BuoyLineSource", "BuoyLineSegment", "OpenPitSource", "StreetCanyon",
    "CartesianGrid", "PolarGrid", "DiscreteReceptor",
    "PollutantType", "TerrainType", "SourceType",
    "BackgroundConcentration", "BackgroundSector",
    "DepositionMethod", "GasDepositionParams", "ParticleDepositionParams",
    "SourceGroupDefinition", "ChemistryMethod", "ChemistryOptions", "OzoneData",
    # validation
    "Validator", "ValidationResult", "ValidationError", "advanced_validate",
    # execution
    "AERMODRunner", "AERMODRunResult", "BatchRunner", "run_aermod",
    "ProgressReporter", "NoOpProgress", "LoggingProgress", "TqdmProgress",
    "ERRMSGInfo", "RunManifestEntry",
    "extract_errmsg", "tail_output", "summarize_failure",
    "resume_batch", "RunManifest", "generate_slurm_script",
    # outputs
    "AERMODResults", "ModelRunInfo", "ConcentrationResult", "AERMODOutputParser",
    "ReceptorInfo", "SourceSummary", "parse_aermod_output", "quick_summary",
    "PostfileHeader", "PostfileResult", "PostfileParser",
    "UnformattedPostfileParser", "read_postfile",
    "AERMODFileHeader", "AERMODAuxResult", "parse_aermod_header", "read_aermod_aux_file",
    "read_plotfile", "read_maxifile", "read_rankfile", "read_seasonhr",
    "read_toxxfile", "read_deposition",
    # visualization
    "AERMODVisualizer", "quick_plot", "quick_map",
    # meteorology
    "AERMETStation", "UpperAirStation", "AERMETStage1", "AERMETStage2",
    "AERMETStage3", "SurfaceFileHeader", "ProfileFileHeader",
    "write_aermet_runfile", "read_surface_file", "read_profile_file",
    "ASOS1MinRecord", "parse_asos_1min_line", "parse_asos_1min_file",
    "aggregate_1min_to_hourly", "ISDStationId", "ISDFetcher", "IGRASounding",
    "parse_igra_v2", "IGRAFetcher", "MMIFConfig",
    "QAQCFinding", "QAQCReport", "find_missing_runs",
    "check_missing_data", "check_extremes",
    "check_stability_consistency", "check_low_wind_bias",
    "check_profile_monotonic", "run_all_qaqc",
    # terrain
    "AERMAPProject", "AERMAPDomain", "AERMAPReceptor", "AERMAPSource",
    "DatumTransformer", "utm_zone_for_lon", "utm_epsg",
    "EPSG_WGS84", "EPSG_NAD83", "EPSG_NAD27",
    "SRTMTileInfo", "srtm_tile_name", "srtm_tiles_for_bbox",
    "async_fetch_tiles", "HillHeightAnomaly", "hill_height_diagnostics",
    # regulatory
    "RegulatoryProfile", "EPA_APPENDIX_W_2017", "EPA_APPENDIX_W_2023",
    "SCREENING_PROFILE", "ALL_PROFILES", "get_profile",
    # PRIME
    "Building", "BPIPCalculator", "BPIPResult", "GEP_FLOOR_M",
    "gep_stack_height", "gep_from_building", "cavity_length", "in_cavity_region",
    "DownwashAssessment", "assess_source_downwash", "apply_bpip_to_project",
    "suggest_downwash_config",
    # chemistry presets
    "olm_preset", "pvmrm_preset", "arm2_preset", "grsm_preset",
    "suggest_chemistry_for", "PollutantDepositionDefaults",
    "DEPOSITION_DEFAULTS", "deposition_defaults_for", "deposition_diagnostics",
    # .inp file reader
    "parse_aermod_input", "read_aermod_input",
    # optional-dep availability flags
    "HAS_GEOSPATIAL", "HAS_TERRAIN",
]

# Optional-dep symbols (only added to __all__ when the extras are installed)
if HAS_GEOSPATIAL:
    __all__.extend([
        "ContourGenerator", "CoordinateTransformer", "GeoDataFrameFactory",
        "RasterExporter", "VectorExporter",
        "export_concentration_geotiff", "export_concentration_shapefile",
        "latlon_to_utm", "utm_to_latlon",
    ])
if HAS_TERRAIN:
    __all__.extend([
        "AERMAPOutputParser", "AERMAPRunner", "AERMAPRunResult",
        "DEMDownloader", "DEMTileInfo", "TerrainProcessor", "run_aermap",
    ])

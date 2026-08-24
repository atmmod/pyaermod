"""
PyAERMOD public API surface.

This module is the stable entry point for downstream code. Prefer
`from pyaermod.api import X` over `from pyaermod.sources import Y` —
internal module layout may change between minor versions, but names
exported here are guaranteed to remain available.

Two tiers:

**Core** (the ``CORE_NAMES`` frozenset and the ``pyaermod.api.core``
submodule): the ~30 names that cover 90% of real workflows — pathways,
source types, the runner, the CLI, and the most common helpers. If
you're writing production code that ideally never has to change,
stick to these.

**Full** (the module-level exports — ``__all__``): everything that's
publicly useful, including advanced integrations (BPIP, PRIME,
chemistry presets, regulatory profiles, terrain utilities, met ingest,
etc.). Every name has a stable signature; deprecations will be
announced via a ``DeprecationWarning`` for at least one minor release
before removal.

Groups (full surface):
    - Project building (input generation, pathways, sources, receptors, reader)
    - Validation (base + advanced + regulatory profiles)
    - Execution (runner + UX helpers + CLI)
    - Outputs (parsing .OUT, POSTFILE, auxiliary text outputs)
    - Visualization
    - Meteorology (ingest + QA/QC + AERMET preprocessor + runner)
    - Terrain (AERMAP + datum/mosaic/diagnostics)
    - Chemistry presets + project wiring
    - PRIME downwash helpers
"""

from __future__ import annotations

# Package metadata
__version__ = "2.0.0"

# --- Project building -----------------------------------------------------
# --- Terrain --------------------------------------------------------------
from .aermap import AERMAPDomain, AERMAPProject, AERMAPReceptor, AERMAPSource

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
from .aermet_runner import (
    AERMETRunner,
    AERMETRunResult,
    run_aermet_pipeline,
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
from .aerscreen import AERSCREENConfig, AERSCREENSourceType
from .aerscreen_runner import AERSCREENRunner, AERSCREENRunResult
from .aersurface import AERSURFACEConfig
from .aersurface_runner import AERSURFACERunner, AERSURFACERunResult

# --- PRIME / downwash -----------------------------------------------------
from .bpip import BPIPCalculator, BPIPResult, Building

# --- Chemistry / deposition presets ---------------------------------------
from .chemistry_presets import (
    DEPOSITION_DEFAULTS,
    PollutantDepositionDefaults,
    apply_chemistry,
    apply_deposition_defaults,
    arm2_preset,
    deposition_defaults_for,
    deposition_diagnostics,
    grsm_preset,
    olm_preset,
    pvmrm_preset,
    suggest_chemistry_for,
)
from .design_values import (
    DesignValue,
    add_background,
    annual_mean,
    naaqs_compliance_report,
    no2_1hr_design_value,
    o3_8hr_design_value,
    pm10_24hr_design_value,
    pm25_24hr_design_value,
    so2_1hr_design_value,
)
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
from .input_reader import parse_aermod_input, read_aermod_input
from .kmz_export import ContourPolygon, to_kmz
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
from .naaqs import NAAQS_TABLE, NAAQSStandard, get_naaqs

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

# --- Regulatory -----------------------------------------------------------
from .regulatory import (
    ALL_PROFILES,
    EPA_APPENDIX_W_2017,
    EPA_APPENDIX_W_2023,
    SCREENING_PROFILE,
    RegulatoryProfile,
    get_profile,
)

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
from .source_importers import from_dxf, from_shapefile
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

# --- Validation -----------------------------------------------------------
from .validator import ValidationError, ValidationResult, Validator
from .validator_advanced import advanced_validate
from .versions import VALIDATED_AERMET_VERSIONS, VALIDATED_AERMOD_VERSIONS

# --- Visualization --------------------------------------------------------
from .visualization import AERMODVisualizer, quick_map, quick_plot

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
    "VALIDATED_AERMOD_VERSIONS", "VALIDATED_AERMET_VERSIONS",
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
    "AERMETRunner", "AERMETRunResult", "run_aermet_pipeline",
    "AERSURFACEConfig", "AERSURFACERunner", "AERSURFACERunResult",
    "AERSCREENConfig", "AERSCREENSourceType", "AERSCREENRunner",
    "AERSCREENRunResult",
    # Design values + NAAQS
    "DesignValue", "NAAQSStandard", "NAAQS_TABLE", "get_naaqs",
    "add_background", "annual_mean",
    "pm25_24hr_design_value", "no2_1hr_design_value",
    "so2_1hr_design_value", "pm10_24hr_design_value",
    "o3_8hr_design_value", "naaqs_compliance_report",
    # KMZ export
    "ContourPolygon", "to_kmz",
    # Source importers
    "from_shapefile", "from_dxf",
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
    "apply_chemistry", "apply_deposition_defaults",
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
        "AERMAPOutputParser",
        "AERMAPRunResult",
        "AERMAPRunner",
        "DEMDownloader",
        "DEMTileInfo",
        "TerrainProcessor",
        "run_aermap",
    ])


# ---------------------------------------------------------------------------
# Stable-core subset
# ---------------------------------------------------------------------------
# The ~30 names below cover 90% of real AERMOD workflows. They are the
# subset you can trust to keep their names and signatures across every
# 1.x release. New names are added here sparingly and only after a
# minor-version soak with the wider __all__ surface.

CORE_NAMES: frozenset = frozenset({
    # Project building — core types
    "AERMODProject",
    "ControlPathway", "SourcePathway", "ReceptorPathway",
    "MeteorologyPathway", "OutputPathway",
    # Source types used in 95%+ of projects
    "PointSource", "AreaSource", "VolumeSource", "LineSource",
    # Receptors
    "CartesianGrid", "PolarGrid", "DiscreteReceptor",
    # Enums
    "PollutantType", "TerrainType", "SourceType",
    # Input read / write
    "parse_aermod_input", "read_aermod_input",
    # Validation
    "Validator", "ValidationResult",
    # Execution
    "AERMODRunner", "run_aermod",
    # Output parsing
    "parse_aermod_output", "AERMODResults",
    "read_plotfile", "read_postfile",
    # Regulatory + chemistry (the commonest presets)
    "EPA_APPENDIX_W_2017", "EPA_APPENDIX_W_2023",
    "olm_preset", "pvmrm_preset", "grsm_preset",
})

# Module version marker for downstream consumers who want to gate on
# API-surface changes without parsing the package version string.
API_VERSION: str = "2.0"

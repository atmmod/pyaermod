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

from .__init__ import __version__

# --- Project building -----------------------------------------------------
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
    LoggingProgress,
    NoOpProgress,
    ProgressReporter,
    RunManifest,
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
    parse_aermod_output,
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
    UpperAirStation,
    read_profile_file,
    read_surface_file,
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
    run_all_qaqc,
)

# --- Terrain --------------------------------------------------------------
from .aermap import AERMAPDomain, AERMAPProject, AERMAPReceptor, AERMAPSource
from .terrain_utils import (
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
    DownwashAssessment,
    apply_bpip_to_project,
    assess_source_downwash,
    cavity_length,
    gep_from_building,
    gep_stack_height,
    in_cavity_region,
    suggest_downwash_config,
)

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
    "extract_errmsg", "tail_output", "summarize_failure",
    "resume_batch", "RunManifest", "generate_slurm_script",
    # outputs
    "AERMODResults", "ModelRunInfo", "ConcentrationResult", "AERMODOutputParser",
    "parse_aermod_output",
    "PostfileHeader", "PostfileResult", "PostfileParser",
    "UnformattedPostfileParser", "read_postfile",
    "AERMODFileHeader", "AERMODAuxResult", "read_aermod_aux_file",
    "read_plotfile", "read_maxifile", "read_rankfile", "read_seasonhr",
    "read_toxxfile", "read_deposition",
    # visualization
    "AERMODVisualizer", "quick_plot", "quick_map",
    # meteorology
    "AERMETStation", "UpperAirStation", "AERMETStage1", "AERMETStage2",
    "AERMETStage3", "read_surface_file", "read_profile_file",
    "ASOS1MinRecord", "parse_asos_1min_line", "parse_asos_1min_file",
    "aggregate_1min_to_hourly", "ISDStationId", "ISDFetcher", "IGRASounding",
    "parse_igra_v2", "IGRAFetcher", "MMIFConfig",
    "QAQCFinding", "QAQCReport", "check_missing_data", "check_extremes",
    "check_stability_consistency", "check_low_wind_bias",
    "check_profile_monotonic", "run_all_qaqc",
    # terrain
    "AERMAPProject", "AERMAPDomain", "AERMAPReceptor", "AERMAPSource",
    "DatumTransformer", "utm_zone_for_lon", "utm_epsg",
    "SRTMTileInfo", "srtm_tile_name", "srtm_tiles_for_bbox",
    "async_fetch_tiles", "HillHeightAnomaly", "hill_height_diagnostics",
    # regulatory
    "RegulatoryProfile", "EPA_APPENDIX_W_2017", "EPA_APPENDIX_W_2023",
    "SCREENING_PROFILE", "ALL_PROFILES", "get_profile",
    # PRIME
    "Building", "BPIPCalculator", "BPIPResult",
    "gep_stack_height", "gep_from_building", "cavity_length", "in_cavity_region",
    "DownwashAssessment", "assess_source_downwash", "apply_bpip_to_project",
    "suggest_downwash_config",
]

"""Smoke tests that pyaermod.api exposes the documented public surface."""

from __future__ import annotations

import importlib

import pytest


PUBLIC_NAMES = [
    # project
    "AERMODProject", "ControlPathway", "SourcePathway", "ReceptorPathway",
    "MeteorologyPathway", "OutputPathway",
    "PointSource", "AreaSource", "VolumeSource", "LineSource",
    "CartesianGrid", "PolarGrid", "DiscreteReceptor",
    # validation
    "Validator", "ValidationResult", "ValidationError", "advanced_validate",
    # execution
    "AERMODRunner", "BatchRunner", "run_aermod",
    "NoOpProgress", "LoggingProgress", "TqdmProgress",
    "extract_errmsg", "summarize_failure", "resume_batch",
    "RunManifest", "generate_slurm_script",
    # outputs
    "AERMODResults", "parse_aermod_output",
    "read_postfile", "read_plotfile", "read_maxifile", "read_rankfile",
    "read_seasonhr", "read_toxxfile", "read_deposition",
    # viz
    "AERMODVisualizer", "quick_plot",
    # met
    "AERMETStage1", "AERMETStage2", "AERMETStage3",
    "ISDFetcher", "IGRAFetcher", "MMIFConfig",
    "run_all_qaqc", "QAQCReport",
    # terrain
    "AERMAPProject", "DatumTransformer", "utm_zone_for_lon",
    "srtm_tiles_for_bbox", "hill_height_diagnostics",
    # regulatory
    "RegulatoryProfile", "EPA_APPENDIX_W_2017", "EPA_APPENDIX_W_2023",
    "SCREENING_PROFILE", "get_profile",
    # PRIME
    "Building", "BPIPCalculator",
    "gep_stack_height", "assess_source_downwash", "apply_bpip_to_project",
]


def test_api_module_imports():
    import pyaermod.api  # noqa: F401


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_public_name_available(name):
    api = importlib.import_module("pyaermod.api")
    assert hasattr(api, name), f"pyaermod.api missing '{name}'"


def test_api_all_list_covers_exports():
    """__all__ should include every name we document here."""
    from pyaermod import api as A

    missing = [n for n in PUBLIC_NAMES if n not in A.__all__]
    assert not missing, f"__all__ missing: {missing}"


def test_version_string_available():
    from pyaermod.api import __version__
    assert isinstance(__version__, str) and __version__


def test_py_typed_marker_present():
    import pyaermod
    from pathlib import Path
    marker = Path(pyaermod.__file__).parent / "py.typed"
    assert marker.exists(), "py.typed PEP 561 marker missing"

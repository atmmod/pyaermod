"""Tests that pyaermod.api.CORE_NAMES is a stable contract.

CORE_NAMES is the narrow subset of the api surface that's guaranteed
to keep its names and signatures across every 1.x release. These
tests pin the current contents so accidental removals fail loudly.

When adding to CORE_NAMES:
1. Soak the new name in `__all__` for at least one minor release
2. Add it to CORE_NAMES + the list below in the same commit
3. Document the promotion in CHANGELOG

When removing from CORE_NAMES: don't. Deprecate with a
DeprecationWarning for at least one minor release, then bump the
MAJOR version.
"""

from __future__ import annotations

import pyaermod.api as api

# The exact set promised in docs/api/index.md. This list must be
# kept in lock-step with api.CORE_NAMES.
EXPECTED_CORE = frozenset({
    "AERMODProject",
    "ControlPathway", "SourcePathway", "ReceptorPathway",
    "MeteorologyPathway", "OutputPathway",
    "PointSource", "AreaSource", "VolumeSource", "LineSource",
    "CartesianGrid", "PolarGrid", "DiscreteReceptor",
    "PollutantType", "TerrainType", "SourceType",
    "parse_aermod_input", "read_aermod_input",
    "Validator", "ValidationResult",
    "AERMODRunner", "run_aermod",
    "parse_aermod_output", "AERMODResults",
    "read_plotfile", "read_postfile",
    "EPA_APPENDIX_W_2017", "EPA_APPENDIX_W_2023",
    "olm_preset", "pvmrm_preset", "grsm_preset",
})


def test_core_names_is_frozenset():
    """CORE_NAMES must be frozen — callers rely on its immutability."""
    assert isinstance(api.CORE_NAMES, frozenset)


def test_core_names_matches_expected_set():
    """Exact-match pin. Any drift is a breaking change and fails CI."""
    assert api.CORE_NAMES == EXPECTED_CORE


def test_every_core_name_is_importable_from_api():
    """Every name in CORE_NAMES must be resolvable as an attribute of
    pyaermod.api (i.e. actually exported)."""
    missing = [n for n in api.CORE_NAMES if not hasattr(api, n)]
    assert not missing, f"CORE_NAMES referenced but missing from api: {missing}"


def test_every_core_name_is_in_all():
    """CORE must be a subset of the full __all__ surface."""
    all_names = set(api.__all__)
    not_in_all = api.CORE_NAMES - all_names
    assert not not_in_all, (
        f"CORE_NAMES contains names not in __all__: {not_in_all}"
    )


def test_api_version_string():
    """API_VERSION is a 'major.minor' string suitable for gating."""
    v = api.API_VERSION
    assert isinstance(v, str)
    # Should look like "1.5" or similar
    parts = v.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts[:2])

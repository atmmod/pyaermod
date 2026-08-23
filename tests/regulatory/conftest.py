"""
Shared fixtures for the EPA AERMOD test-suite parity harness.

The fixtures themselves are not vendored in the repo; this test
directory is automatically skipped when no EPA test-case set is present
under ``test_cases/`` or the AERMOD binary isn't on PATH.

Which set is used is decided by :func:`pyaermod.epa_testcases.find_epa_testcase_set`:
``$PYAERMOD_EPA_TESTCASES`` if set, else the ``test_cases/aermet*_aermod*``
set whose AERMOD version matches the ``aermod`` binary on PATH (falling
back to the newest set). Both EPA naming conventions
(``aermet_24142_aermod_24142`` and ``aermet24142_aermod26135``) are accepted.
"""

from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path

import pytest

from pyaermod.epa_testcases import (
    ENV_VAR,
    aermod_binary_version,
    find_epa_testcase_set,
)

ROOT = Path(__file__).resolve().parent.parent.parent
EPA_TESTCASE_ROOT = ROOT / "test_cases"

_AERMOD_EXE = shutil.which("aermod")
# Only probe the binary when there is something to choose between; keeps
# the default (no fixtures) collection path free of subprocess calls.
AERMOD_VERSION = (
    aermod_binary_version(_AERMOD_EXE)
    if _AERMOD_EXE and (EPA_TESTCASE_ROOT.is_dir() or os.environ.get(ENV_VAR))
    else None
)

EPA_SET = find_epa_testcase_set(EPA_TESTCASE_ROOT, aermod_version=AERMOD_VERSION)
EPA_SET_NAME = EPA_SET.name if EPA_SET else "no-epa-set"
EPA_TESTCASE_DIR = (
    EPA_SET.path if EPA_SET else EPA_TESTCASE_ROOT / "aermet_24142_aermod_24142"
)
EPA_INPUTS_DIR = EPA_TESTCASE_DIR / "inputs"
EPA_MET_DIR = EPA_TESTCASE_DIR / "meteorology"
EPA_REF_PST_DIR = EPA_TESTCASE_DIR / "postfiles"


def _aermod_available() -> bool:
    return _AERMOD_EXE is not None


def _fixtures_available() -> bool:
    return EPA_SET is not None and EPA_SET.exists()


def _missing_reason() -> str:
    chosen = EPA_SET.describe() if EPA_SET else "none"
    return (
        "EPA AERMOD test-case fixtures or AERMOD binary not available. "
        f"Looked under {EPA_TESTCASE_ROOT} (override with ${ENV_VAR}); "
        f"chosen set: {chosen}; aermod on PATH: {_AERMOD_EXE or 'no'}."
    )


# Module-level skip applies to every test in tests/regulatory/.
collect_ignore_glob: list[str] = []
if not _fixtures_available() or not _aermod_available():
    # Mark the entire directory skipped; pytest will still discover
    # but emit a single skip summary rather than per-test noise.
    pytestmark = pytest.mark.skip(reason=_missing_reason())


@pytest.fixture(scope="session")
def epa_testcase_dir() -> Path:
    if not _fixtures_available():
        pytest.skip(_missing_reason())
    if AERMOD_VERSION and EPA_SET.aermod_version and EPA_SET.aermod_version != AERMOD_VERSION:
        warnings.warn(
            f"AERMOD binary is {AERMOD_VERSION} but the reference set is "
            f"{EPA_SET.describe()}; parity differences may be model-version "
            "changes rather than pyaermod regressions.",
            stacklevel=1,
        )
    return EPA_TESTCASE_DIR


@pytest.fixture(scope="session")
def aermod_binary() -> Path:
    if _AERMOD_EXE is None:
        pytest.skip("AERMOD binary not found on PATH")
    return Path(_AERMOD_EXE)

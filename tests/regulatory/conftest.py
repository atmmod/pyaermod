"""
Shared fixtures for the EPA AERMOD test-suite parity harness.

The fixtures themselves (~35 MB) are not vendored in the repo; this
test directory is automatically skipped when the test_cases/ tree is
missing or the AERMOD binary isn't on PATH. Drop the EPA-published
``test_cases/aermet_24142_aermod_24142`` distribution into the repo
root to enable.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

EPA_TESTCASE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "test_cases" / "aermet_24142_aermod_24142"
)
EPA_INPUTS_DIR = EPA_TESTCASE_DIR / "inputs"
EPA_MET_DIR = EPA_TESTCASE_DIR / "meteorology"
EPA_REF_PST_DIR = EPA_TESTCASE_DIR / "postfiles"


def _aermod_available() -> bool:
    return shutil.which("aermod") is not None


def _fixtures_available() -> bool:
    return EPA_INPUTS_DIR.exists() and EPA_REF_PST_DIR.exists()


# Module-level skip applies to every test in tests/regulatory/.
collect_ignore_glob: list[str] = []
if not _fixtures_available() or not _aermod_available():
    # Mark the entire directory skipped; pytest will still discover
    # but emit a single skip summary rather than per-test noise.
    pytestmark = pytest.mark.skip(
        reason=(
            "EPA AERMOD test-case fixtures or AERMOD binary not available. "
            f"Expected fixtures at {EPA_TESTCASE_DIR}."
        )
    )


@pytest.fixture(scope="session")
def epa_testcase_dir() -> Path:
    if not _fixtures_available():
        pytest.skip(f"EPA test cases not present at {EPA_TESTCASE_DIR}")
    return EPA_TESTCASE_DIR


@pytest.fixture(scope="session")
def aermod_binary() -> Path:
    exe = shutil.which("aermod")
    if exe is None:
        pytest.skip("AERMOD binary not found on PATH")
    return Path(exe)

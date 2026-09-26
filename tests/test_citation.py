"""CITATION.cff: present, CFF 1.2.0, and in step with the package version.

The structural checks need no third-party parser (CITATION.cff is flat
YAML and the fields pinned here are all top-level scalars). Full schema
validation runs through ``cffconvert --validate`` when the tool is on
PATH; ``.github/workflows/tests.yml`` installs it, so CI always runs that
half, and a developer without it sees one skip with the reason.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

import pyaermod

REPO = Path(__file__).parent.parent
CFF = REPO / "CITATION.cff"


def _top_level_scalars(text: str) -> dict[str, str]:
    """Return ``{key: value}`` for every unindented ``key: value`` line.

    Trailing ``# comments`` are stripped, as are the quotes around a
    quoted scalar. Block keys (``authors:``) map to an empty string.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0] in " #-":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


@pytest.fixture(scope="module")
def cff() -> dict[str, str]:
    assert CFF.exists(), "CITATION.cff missing from the repository root"
    return _top_level_scalars(CFF.read_text(encoding="utf-8"))


def test_is_cff_1_2_0(cff):
    assert cff["cff-version"] == "1.2.0"
    assert cff["type"] == "software"
    for required in ("message", "title", "version", "date-released", "license"):
        assert cff.get(required), f"CITATION.cff is missing {required!r}"


def test_version_matches_package(cff):
    """The release bump touches three files; this ties the third to the first two."""
    assert cff["version"] == pyaermod.__version__
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert m and m.group(1) == pyaermod.__version__


def test_metadata_matches_pyproject(cff):
    assert cff["license"] == "MIT"
    assert cff["repository-code"] == "https://github.com/atmmod/pyaermod"
    text = CFF.read_text(encoding="utf-8")
    assert "family-names: Capps" in text and "given-names: Shannon" in text


def test_release_placeholders_are_well_formed(cff):
    """Zenodo mints the DOI after the release, so the file ships placeholders.

    They must still be schema-valid values (a DOI-shaped DOI, an ISO
    date) so the file validates before and after they are filled in, and
    the comments must say what to replace them with.
    """
    assert re.fullmatch(r"10\.\d{4,9}/\S+", cff["doi"]), cff["doi"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cff["date-released"]), cff["date-released"]
    text = CFF.read_text(encoding="utf-8")
    assert "placeholder" in text.lower()
    assert "zenodo" in text.lower()


def test_preferred_citation_stub_for_the_paper():
    text = CFF.read_text(encoding="utf-8")
    assert "preferred-citation:" in text
    assert "type: article" in text
    assert "Journal of the Air & Waste Management Association" in text


@pytest.mark.skipif(shutil.which("cffconvert") is None,
                    reason="cffconvert not on PATH (pip install cffconvert)")
def test_validates_against_the_cff_schema():
    proc = subprocess.run(
        ["cffconvert", "--validate", "-i", str(CFF)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "valid" in proc.stdout.lower()

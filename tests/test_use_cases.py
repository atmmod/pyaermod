"""
docs/use-cases.md shows ten scripts from examples/use_cases/ and the
figure each one drew.

The fast tests check that the page includes every script verbatim (by
snippet) with its figure, and that every script compiles. The slow test
runs each script end to end, as the page tells a user to: AERMOD on
PATH, the EPA met files in ``$AERMOD_MET_DIR`` (or the ``meteorology``
folder of the EPA test-case set ``find_epa_testcase_set`` picks), and
checks that it exits cleanly and writes its figure. Use case 8 also
needs AERMAP and downloads USGS terrain, so it is skipped without
``aermap`` on PATH.
"""

from __future__ import annotations

import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pyaermod.epa_testcases import find_epa_testcase_set

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((REPO / "examples" / "use_cases").glob("[0-9][0-9]_*.py"))
PAGE = REPO / "docs" / "use-cases.md"
MET_FILES = ("LOVETT.SFC", "LOVETT.PFL", "HOUSTON_ADJU.SFC", "HOUSTON_ADJU.PFL")


def _met_dir() -> Path | None:
    if os.environ.get("AERMOD_MET_DIR"):
        return Path(os.environ["AERMOD_MET_DIR"])
    found = find_epa_testcase_set(REPO / "test_cases")
    return found.path / "meteorology" if found else None


def test_ten_scripts():
    assert len(SCRIPTS) == 10


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_page_includes_script_and_figure(script):
    page = PAGE.read_text(encoding="utf-8")
    assert f'--8<-- "examples/use_cases/{script.name}"' in page
    figure = f"images/use-cases/{script.stem}.png"
    assert f"({figure})" in page
    assert (REPO / "docs" / figure).is_file()


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_script_compiles(script):
    py_compile.compile(str(script), doraise=True)


@pytest.mark.slow
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_script_runs(script, tmp_path):
    if shutil.which("aermod") is None:
        pytest.skip("aermod not on PATH")
    if script.stem.startswith("08_") and shutil.which("aermap") is None:
        pytest.skip("aermap not on PATH")
    met = _met_dir()
    if met is None or not all((met / f).is_file() for f in MET_FILES):
        pytest.skip("EPA LOVETT/HOUSTON_ADJU met files not found")
    env = {**os.environ, "AERMOD_MET_DIR": str(met), "USE_CASE_OUT": "out", "MPLBACKEND": "Agg"}
    # Run from an empty directory with a relative output path, as a user would.
    proc = subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=1800)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert (tmp_path / "out" / script.stem / f"{script.stem}.png").is_file()
    assert re.search(r"Figure: ", proc.stdout)

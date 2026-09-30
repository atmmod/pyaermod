"""pyaermod.ensemble against a real AERMOD.

Skips unless ``aermod`` is on PATH. Runs the four-run design of
``tests/fixtures/ensemble/design.py`` on four workers and checks that
every run kept its own PLOTFILEs and that a second call makes no run.
With AERMOD v26135, the release the recordings in
``tests/fixtures/ensemble/`` were made with, it also checks that the
PLOTFILE values match them to AERMOD's print precision (the replaying
tests in ``tests/test_ensemble.py`` rely on those).
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

from pyaermod.aermod_outputs import read_plotfile
from pyaermod.ensemble import collect_plotfiles, run_design

FIXTURES = Path(__file__).parent / "fixtures" / "ensemble"
_spec = importlib.util.spec_from_file_location("ensemble_design", FIXTURES / "design.py")
design = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(design)

pytestmark = pytest.mark.skipif(
    shutil.which("aermod") is None, reason="AERMOD binary not found on PATH",
)


# The recordings come from a gfortran 15.2 -O2 -fbounds-check build on
# macOS arm64; CI builds with -O2 on Linux x86_64. Allow for the last
# printed digit, as tests/test_real_aermod.py does.
REL_TOL = 1e-4
ABS_TOL = 2e-5
RECORDED_VERSION = "26135"


def _assert_same_field(path: Path, recorded: Path) -> None:
    ours, ref = read_plotfile(path), read_plotfile(recorded)
    assert [(r["X"], r["Y"]) for r in ours.records] == [(r["X"], r["Y"]) for r in ref.records]
    for col in ("AVERAGE_CONC", "DRY_DEPO"):
        assert ours.values(col) == pytest.approx(ref.values(col), rel=REL_TOL, abs=ABS_TOL)


def test_four_run_design_on_four_workers(tmp_path):
    root = tmp_path / "design"
    result = run_design(design.ROWS, design.build, root, n_workers=4)
    assert result.all_succeeded, [r.entry.error_message for r in result.values()]
    assert len({r.run_dir for r in result.values()}) == 4
    versions = {r.entry.aermod_version for r in result.values()}
    assert len(versions) == 1 and re.fullmatch(r"\d{5}", versions.pop() or "")
    for run in result.values():
        # The recordings are v26135's; another release may print other values.
        if run.entry.aermod_version == RECORDED_VERSION:
            for name in ("pit.plt", "pit_1h.plt"):
                recorded = FIXTURES / run.factors["case"] / "outputs" / name
                _assert_same_field(run.run_dir / name, recorded)
    assert len({(r.run_dir / "pit.plt").read_text() for r in result.values()}) == 4

    again = run_design(design.ROWS, design.build, root, n_workers=4)
    assert again.n_skipped == 4 and again.n_run == 0

    table = collect_plotfiles(root)
    assert len(table) == 4 * 2 * 72

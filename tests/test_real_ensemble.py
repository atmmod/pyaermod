"""pyaermod.ensemble and BatchRunner.parameter_sweep against a real AERMOD.

Skips unless ``aermod`` is on PATH. Runs the four-run design of
``tests/fixtures/ensemble/design.py`` on four workers and checks that
every run kept its own PLOTFILEs and that a second call makes no run.
With AERMOD v26135, the release the recordings in
``tests/fixtures/ensemble/`` were made with, it also checks that the
PLOTFILE values match them to AERMOD's print precision (the replaying
tests in ``tests/test_ensemble.py`` rely on those). A sweep over two
particle size distributions (the 2026-09-29 audit's crash) must return
one result per distribution.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

from pyaermod.aermod_outputs import read_plotfile
from pyaermod.ensemble import collect_plotfiles, run_design
from pyaermod.input_generator import ParticleDepositionParams
from pyaermod.runner import AERMODRunner, BatchRunner

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


def test_size_distribution_sweep(tmp_path):
    project = design.build(design.ROWS[0])
    psds = [ParticleDepositionParams([2.5, 10.0], [0.5, 0.5], [2.6, 2.6]),
            ParticleDepositionParams([5.0, 20.0], [0.3, 0.7], [2.6, 2.6])]
    # The sweep's decks sit in one directory and name the met files from it
    for name in ("AERMET2.SFC", "AERMET2.PFL"):
        shutil.copy(design.MET / name, tmp_path / name)
    project.meteorology.surface_file = "AERMET2.SFC"
    project.meteorology.profile_file = "AERMET2.PFL"
    runner = AERMODRunner(log_level="WARNING")
    results = BatchRunner(runner).parameter_sweep(
        project, "particle_deposition", psds, tmp_path, n_workers=2)
    assert len(results) == 2
    plots = []
    for psd in psds:
        result = results[psd]
        assert result.success, result.error_message
        stem = Path(result.input_file).stem
        plots.append((tmp_path / f"{stem}_pit.plt").read_text())
    assert _data_rows_differ(plots)


def _data_rows_differ(texts: list) -> bool:
    rows = [[ln for ln in t.splitlines() if not ln.startswith("*")] for t in texts]
    return all(rows) and rows[0] != rows[1]

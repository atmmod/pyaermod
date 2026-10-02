"""pyaermod.ensemble and BatchRunner.parameter_sweep against a real AERMOD.

Skips unless ``aermod`` is on PATH. Runs the four-run design of
``tests/fixtures/ensemble/design.py`` on four workers and checks that
every run kept its own PLOTFILEs and that a second call makes no run.
With AERMOD v26135, the release the recordings in
``tests/fixtures/ensemble/`` were made with, it also checks that the
PLOTFILE values match them to AERMOD's print precision (the replaying
tests in ``tests/test_ensemble.py`` rely on those). A sweep over two
particle size distributions (which used to crash) must return
one result per distribution. The design's ``extras`` row, whose hourly
emission file, second POSTFILE and 2ND PLOTFILE the model holds only as
lines kept verbatim, must keep every output in its run directory, and
scaling its emission file by ten must make a new run whose
concentrations are ten times as large. A design with
``ControlPathway.debug_options`` on two workers must leave each run's
AREA and METEOR debug files in its own directory.
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


def test_extras_and_an_edited_emission_file(tmp_path, monkeypatch):
    houremis = tmp_path / "in" / "houremis.dat"
    houremis.parent.mkdir()
    houremis.write_text(design.houremis_lines())
    monkeypatch.setattr(design, "HOUREMIS", houremis)
    root = tmp_path / "design"
    first = run_design([design.EXTRAS_ROW], design.build, root, n_workers=1)
    old = next(iter(first.values()))
    assert old.success, old.entry.error_message
    for names in old.entry.outputs.values():
        for name in names:
            assert (old.run_dir / name).stat().st_size > 0, name
    if old.entry.aermod_version == RECORDED_VERSION:
        for name in ("pit.plt", "pit_1h.plt", "pit_1h_2nd.plt"):
            _assert_same_field(old.run_dir / name, FIXTURES / "extras" / "outputs" / name)
    assert not (root / "shared").exists() and not (root / "runs" / "shared").exists()

    houremis.write_text(design.houremis_lines(scale=10.0))
    again = run_design([design.EXTRAS_ROW], design.build, root, n_workers=1)
    new = next(iter(again.values()))
    assert again.n_skipped == 0 and new.success and new.run_id != old.run_id
    before = read_plotfile(old.run_dir / "pit.plt").values("AVERAGE_CONC")
    after = read_plotfile(new.run_dir / "pit.plt").values("AVERAGE_CONC")
    assert after == pytest.approx([10 * v for v in before], rel=1e-3, abs=1e-4)
    assert set(collect_plotfiles(root, out_stem=None)["run_id"]) == {new.run_id}


def test_debug_files_on_two_workers(tmp_path):
    """ControlPathway.debug_options names files outside the run directory
    (one relative, one absolute): each run writes its own AREA and METEOR
    debug files in its own directory, the manifest records them, and a
    run whose debug file is removed is made again."""
    def build(factors):
        project = design.build(factors)
        project.control.debug_options = [
            "AREA", "../shared/area.dbg", "METEOR", "/nonexistent-pyaermod-dir/met.dbg",
        ]
        return project

    root = tmp_path / "design"
    rows = design.ROWS[:2]
    result = run_design(rows, build, root, n_workers=2)
    assert result.all_succeeded, [r.entry.error_message for r in result.values()]
    runs = list(result.values())
    assert len({r.run_dir for r in runs}) == 2
    for run in runs:
        assert run.entry.outputs["DEBUGOPT"] == ["area.dbg", "met.dbg"]
        assert "DEBUGOPT  AREA  area.dbg  METEOR  met.dbg" in (run.run_dir / "run.inp").read_text()
        for name in ("area.dbg", "met.dbg"):
            assert (run.run_dir / name).stat().st_size > 0
    # The AREA debug output follows the particle size, so the runs'
    # files differ: neither run wrote over the other's.
    assert (runs[0].run_dir / "area.dbg").read_bytes() != (runs[1].run_dir / "area.dbg").read_bytes()
    assert not (tmp_path / "shared").exists() and not (root / "shared").exists()

    assert run_design(rows, build, root, n_workers=2).n_skipped == 2
    (runs[1].run_dir / "met.dbg").unlink()
    again = run_design(rows, build, root, n_workers=2)
    assert again.n_run == 1 and not again[runs[1].run_id].skipped
    assert (runs[1].run_dir / "met.dbg").stat().st_size > 0

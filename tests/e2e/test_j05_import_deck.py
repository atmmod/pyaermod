"""J5: import EPA's AERTEST deck with its met files, run it and open Results.

What the user must see (PLAN-gui.md): the steps are populated from the
deck, the run succeeds, and the 1-hour plot-file values match EPA's
``AERTEST_01H.PLT`` within the tolerance ``tests/test_real_aermod.py``
uses. Tier T2 replays recording ``aertest``; tier T3 runs the real binary.

The deck imported is the one in the recording: EPA's ``aertest.inp`` with
its archive paths flattened, as ``tests/test_real_aermod.py`` does, so its
output files land in the run's working directory.
"""

from __future__ import annotations

import shutil

import pytest

from pyaermod import read_plotfile

from .harness import EPA_FIXTURES
from .reference import AERTEST_RECORDING

pytestmark = pytest.mark.e2e

# The tolerance of tests/test_real_aermod.py.
REL_TOL = 1e-4
ABS_TOL = 1e-3


def _plot_values(path):
    plot = read_plotfile(path)
    column = plot.concentration_column
    return {(round(r["X"], 3), round(r["Y"], 3)): r[column] for r in plot.records}


@pytest.mark.aermod_recording("aertest")
def test_j05_import_and_run_aertest(gui, step, known_gap, run_dir, tmp_path):
    deck_dir = tmp_path / "aertest"
    deck_dir.mkdir()
    shutil.copy(AERTEST_RECORDING / "aertest.inp", deck_dir)
    for met in ("AERMET2.SFC", "AERMET2.PFL"):
        shutil.copy(EPA_FIXTURES / met, deck_dir)

    gui.open()
    step("blank_project")
    with known_gap("WP-G6", "no deck import"):
        gui.project.import_deck(deck_dir / "aertest.inp")
    step("imported")

    gui.sources.expect_ids(["STACK1"])
    gui.receptors.expect_names(["POL1"])
    gui.meteorology.set_met_files(deck_dir / "AERMET2.SFC", deck_dir / "AERMET2.PFL")
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    step("run_finished")
    gui.run.reports_success()

    got = _plot_values(run_dir / "AERTEST_01H.PLT")
    ref = _plot_values(EPA_FIXTURES / "AERTEST_01H.PLT")
    assert set(got) == set(ref)
    for coord, value in ref.items():
        assert abs(got[coord] - value) <= ABS_TOL + REL_TOL * abs(value), coord

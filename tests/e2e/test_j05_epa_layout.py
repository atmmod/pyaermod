"""J5 with EPA's own ``aertest.inp``, in the folders of EPA's test archive.

J5 imports the recording's copy of the deck, whose paths are flattened so
that its outputs land in the run's working directory. EPA's deck itself
runs from ``inputs/`` and writes into ``../Outputs``, ``../plotfiles`` and
``../postfiles``, which a GUI run in a blank working directory (a new,
empty folder) does not have: AERMOD, which creates no folders, would stop
with E500. This journey imports the deck from its path, as the Import
step advises for such a deck, and checks that Review & Run says so before
the run, that the run succeeds once the working directory is the deck's
own folder, and that Results reads the plot file and POSTFILE from where
the deck put them.

Tier T3 only: the fake AERMOD writes a recording's outputs into its
working directory, so no recording can stand for a deck that writes
elsewhere.
"""

from __future__ import annotations

import shutil

import pytest

from pyaermod import read_plotfile

from .harness import EPA_FIXTURES, REAL_AERMOD
from .reference import AERTEST_MAXIMA

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not REAL_AERMOD, reason="tier T3 only: the fake AERMOD writes its "
                       "outputs into the working directory, not the deck's folders"),
]

# The tolerance of tests/test_real_aermod.py, as in J5.
REL_TOL = 1e-4
ABS_TOL = 1e-3


def _plot_values(path):
    plot = read_plotfile(path)
    column = plot.concentration_column
    return {(round(r["X"], 3), round(r["Y"], 3)): r[column] for r in plot.records}


def test_j05_epa_deck_runs_in_its_own_folder(gui, step, tmp_path):
    root = tmp_path / "aermod_test_cases"
    for folder in ("inputs", "meteorology", "Outputs", "plotfiles", "postfiles"):
        (root / folder).mkdir(parents=True)
    deck = root / "inputs" / "aertest.inp"
    shutil.copy(EPA_FIXTURES / "aertest.inp", deck)
    # The deck names ../meteorology/aermet2.sfc and .pfl.
    shutil.copy(EPA_FIXTURES / "AERMET2.SFC", root / "meteorology" / "aermet2.sfc")
    shutil.copy(EPA_FIXTURES / "AERMET2.PFL", root / "meteorology" / "aermet2.pfl")

    gui.open()
    gui.project.import_deck_from_path(deck)
    step("imported")
    gui.sources.expect_ids(["STACK1"])
    gui.meteorology.expect_met_files(str(root / "meteorology" / "aermet2.sfc"),
                                     str(root / "meteorology" / "aermet2.pfl"))

    gui.run.open()
    step("review_blank_working_directory")
    gui.run.expect_run_blocked()
    gui.run.expect_checklist_names("../Outputs/AERTEST.SUM", "../plotfiles/AERTEST_01H.PLT",
                                   "../postfiles/AERTEST_01H.PST",
                                   "../Outputs/AERTEST_ERRORS.OUT")
    gui.run.set_working_directory(deck.parent)
    gui.run.expect_run_allowed()
    gui.run.expect_checklist_clear_of("../Outputs")
    gui.run.start()
    gui.run.wait_until_finished()
    step("run_finished")
    gui.run.reports_success()

    got = _plot_values(root / "plotfiles" / "AERTEST_01H.PLT")
    ref = _plot_values(EPA_FIXTURES / "AERTEST_01H.PLT")
    assert set(got) == set(ref)
    for coord, value in ref.items():
        assert abs(got[coord] - value) <= ABS_TOL + REL_TOL * abs(value), coord

    gui.results.open()
    step("results")
    shown = {r["Period"].replace("-", ""): (r["Max"], r["X (m)"], r["Y (m)"])
             for r in gui.results.maxima_rows()}
    assert shown == AERTEST_MAXIMA
    gui.results.expect_map()
    gui.results.expect_naaqs_design_value_from("AERTEST_01H.PST")

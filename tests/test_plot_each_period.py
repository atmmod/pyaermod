"""``OutputPathway.plot_each_period``: a PLOTFILE for every averaging period.

The GUI's new projects turn it on so that the Results step can draw a
concentration map for any period the user picks. The recorded run of the
reference scenario (tests/fixtures/gui/aermod_recordings/albany_success)
shows that AERMOD v26135 accepts the deck and what it writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod import read_plotfile
from pyaermod.gui_v2.project_io import project_from_json, project_to_json
from pyaermod.gui_v2.state import PLOT_FILE_STEM, _empty_project
from pyaermod.input_generator import OutputPathway
from pyaermod.input_reader import read_aermod_input

RECORDINGS = Path(__file__).parent / "fixtures" / "gui" / "aermod_recordings"


def _plot_lines(text: str):
    return [" ".join(line.split()) for line in text.splitlines() if "PLOTFILE" in line]


def test_one_plot_file_per_period_named_after_the_period():
    out = OutputPathway(plot_each_period="run")
    text = out.to_aermod_input(averaging_periods=["1", 3.0, "24", "MONTH", "PERIOD"])
    assert _plot_lines(text) == [
        "PLOTFILE 1 ALL FIRST run_01H.PLT",
        "PLOTFILE 3 ALL FIRST run_03H.PLT",
        "PLOTFILE 24 ALL FIRST run_24H.PLT",
        "PLOTFILE MONTH ALL FIRST run_MON.PLT",
        "PLOTFILE PERIOD ALL run_PER.PLT",
    ]
    assert out.plot_each_period_files(["ANNUAL"]) == [("ANNUAL", "run_ANN.PLT")]


def test_without_a_receptor_table_only_long_term_files_are_written():
    # AERMOD refuses "PLOTFILE 1 ALL FIRST" unless a RECTABLE asks for the
    # first-highest value (OUPLOT E203, HIVALU).
    out = OutputPathway(plot_each_period="run", receptor_table=False)
    text = out.to_aermod_input(averaging_periods=["1", "24", "ANNUAL"])
    assert _plot_lines(text) == ["PLOTFILE ANNUAL ALL run_ANN.PLT"]


def test_off_by_default_and_nothing_without_periods():
    assert OutputPathway().plot_each_period is None
    assert _plot_lines(OutputPathway().to_aermod_input(averaging_periods=["1"])) == []
    assert _plot_lines(OutputPathway(plot_each_period="run").to_aermod_input()) == []


def test_the_project_writes_its_own_periods():
    project = _empty_project()
    assert project.output.plot_each_period == PLOT_FILE_STEM
    project.control.averaging_periods = ["1", "3", "24", "PERIOD"]
    assert _plot_lines(project.to_aermod_input(validate=False)) == [
        f"PLOTFILE 1 ALL FIRST {PLOT_FILE_STEM}_01H.PLT",
        f"PLOTFILE 3 ALL FIRST {PLOT_FILE_STEM}_03H.PLT",
        f"PLOTFILE 24 ALL FIRST {PLOT_FILE_STEM}_24H.PLT",
        f"PLOTFILE PERIOD ALL {PLOT_FILE_STEM}_PER.PLT",
    ]


def test_a_deck_read_back_writes_the_same_plot_files(tmp_path):
    project = _empty_project()
    project.control.averaging_periods = ["1", "24", "PERIOD"]
    deck = project.to_aermod_input(validate=False)
    path = tmp_path / "run.inp"
    path.write_text(deck)
    again = read_aermod_input(path).to_aermod_input(validate=False)
    assert _plot_lines(again) == _plot_lines(deck)


def test_the_project_file_keeps_it():
    project = _empty_project()
    project.output.plot_each_period = "mine"
    assert project_from_json(project_to_json(project)).output.plot_each_period == "mine"


@pytest.mark.parametrize(("name", "period", "value"), [
    ("pyaermod_gui_01H.PLT", "1HR", 76.07952),
    ("pyaermod_gui_03H.PLT", "3HR", 59.57654),
    ("pyaermod_gui_24H.PLT", "24HR", 16.85665),
    ("pyaermod_gui_PER.PLT", "PERIOD", 5.40459),
])
def test_the_recorded_plot_files_hold_every_receptor_and_the_summary_maximum(
        name, period, value):
    plot = read_plotfile(RECORDINGS / "albany_success" / "outputs" / name)
    assert plot.n_records == 360
    column = plot.concentration_column
    best = max(plot.records, key=lambda r: r[column])
    # The same maximum and receptor as AERMOD's summary table (manifest).
    assert best[column] == pytest.approx(value, abs=5e-6), period
    assert (best["X"], best["Y"]) == pytest.approx((519.62, -300.0), abs=5e-3)

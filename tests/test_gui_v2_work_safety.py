"""The GUI keeps the user's work and says what its results are (2026-11-18 review).

Unit tests for the fixes behind the journeys in tests/e2e/test_j10_work_safety.py
and tests/e2e/test_b03_browser_app_work_safety.py: the session's runs (one deck
per run, temporary folders removed, a run shared with a forked tab), the met
file checks the header, badges and checklist share, the editors' checks, and
the Results step's notice when the project has changed since the run it shows.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from pyaermod.gui_v2 import run_results
from pyaermod.gui_v2._form import (
    _parse_numbers,
    _parse_pairs,
    _unread_number_lines,
    _unread_pair_lines,
    source_id_problem,
)
from pyaermod.gui_v2.readiness import (
    item_findings,
    met_file_findings,
    met_header_findings,
    review,
)
from pyaermod.gui_v2.session import (
    RunRecord,
    Session,
    SessionEvent,
    remove_temp_run_dirs,
    run_deck_name,
)
from pyaermod.gui_v2.steps import readiness, step_statuses
from pyaermod.input_generator import CartesianGrid, DiscreteReceptor, PointSource
from pyaermod.runner import AERMODRunResult

EPA = Path(__file__).resolve().parent / "fixtures" / "epa_official"


def _point(sid="S", **kw):
    values = dict(x_coord=0, y_coord=0, stack_height=10, stack_temp=400, exit_velocity=10,
                  stack_diameter=1, emission_rate=1)
    values.update(kw)
    return PointSource(source_id=sid, **values)


def _session() -> Session:
    s = Session()
    s.add_source(_point())
    s.add_receptor(DiscreteReceptor(x_coord=100, y_coord=0))
    return s


class _Runner:
    """Writes the .out file the runner would (named after the deck)."""

    def __init__(self):
        self.decks = []

    def run(self, input_file, working_dir, timeout):
        self.decks.append(Path(input_file))
        out = Path(working_dir) / (Path(input_file).stem + ".out")
        out.write_text(f"AERMOD output of {Path(input_file).name}\n")
        return AERMODRunResult(success=False, input_file=str(input_file), output_file=str(out),
                               error_message="fake")


class _Handle:
    def __init__(self):
        self.cancelled = False
        self.progress = None

    def cancel(self):
        self.cancelled = True
        return True


class _Background:
    """A background runner whose run ends only when the test says so."""

    def start(self, input_file, working_dir, timeout, on_progress, on_finish):
        self.on_progress, self.on_finish = on_progress, on_finish
        self.handle = _Handle()
        self.input_file = Path(input_file)
        return self.handle

    def finish(self):
        self.on_finish(AERMODRunResult(success=False, input_file=str(self.input_file),
                                       error_message="fake"))


# ----------------------------------------------------------------------
# code-G4: each run has its own deck and .out file
# ----------------------------------------------------------------------

def test_each_run_writes_a_deck_of_its_own(tmp_path):
    s, runner = _session(), _Runner()
    first = s.start_run(working_dir=tmp_path, runner=runner)
    second = s.start_run(working_dir=tmp_path, runner=runner)
    assert [d.name for d in runner.decks] == [run_deck_name(1), run_deck_name(2)]
    assert first.deck_path != second.deck_path
    assert Path(first.result.output_file).name == "pyaermod_gui_run1.out"


def test_two_tabs_running_in_one_folder_never_share_a_deck(tmp_path):
    a, b = _session(), _session()
    runner_a, runner_b = _Background(), _Background()
    a.start_run(working_dir=tmp_path, runner=runner_a, background=True)
    b.start_run(working_dir=tmp_path, runner=runner_b, background=True)
    assert runner_a.input_file != runner_b.input_file      # both are "run 1"
    assert runner_b.input_file.name == "pyaermod_gui_run1_2.inp"
    runner_a.finish()
    runner_b.finish()
    # Free again once the runs have ended.
    c = _session()
    assert c.start_run(working_dir=tmp_path, runner=_Runner()).deck_path.name == run_deck_name(1)


def test_a_plot_file_written_after_the_run_finished_is_not_the_runs(tmp_path):
    deck = tmp_path / run_deck_name(1)
    deck.write_text("OU STARTING\n   PLOTFILE 1 ALL 1ST later.plt\nOU FINISHED\n")
    later = tmp_path / "later.plt"
    later.write_text("* a later run's plot file\n")
    now = datetime.now()
    record = RunRecord(number=1, work_dir=tmp_path, deck_path=deck,
                       started_at=now - timedelta(minutes=10),
                       finished_at=now - timedelta(minutes=5))
    assert run_results._written_by(record, "OU PLOTFILE", (".PLT",)) == []
    record = RunRecord(number=1, work_dir=tmp_path, deck_path=deck,
                       started_at=now - timedelta(minutes=10), finished_at=now)
    assert run_results._written_by(record, "OU PLOTFILE", (".PLT",)) == [later]


# ----------------------------------------------------------------------
# code-G8: temporary run folders go with their runs
# ----------------------------------------------------------------------

def test_open_removes_the_temporary_folders_of_the_runs_it_discards(tmp_path):
    s = _session()
    temp = Path(s.start_run(working_dir=None, runner=_Runner()).work_dir)
    kept = Path(s.start_run(working_dir=tmp_path / "mine", runner=_Runner()).work_dir)
    assert temp.is_dir() and kept.is_dir()
    s.open_json(_blank_json())
    assert not temp.exists()
    assert kept.is_dir()                    # a folder the user chose is theirs


def _blank_json() -> str:
    from pyaermod.gui_v2.project_io import project_to_json

    return project_to_json(Session().project)


def test_a_temporary_folder_a_fork_still_lists_is_kept():
    s = _session()
    temp = Path(s.start_run(working_dir=None, runner=_Runner()).work_dir)
    other = s.fork("other tab")
    try:
        s.new()
        assert temp.is_dir()                # the other tab still shows that run
        other.new()
        assert not temp.exists()
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_the_temporary_folders_go_when_the_app_stops():
    s = _session()
    temp = Path(s.start_run(working_dir=None, runner=_Runner()).work_dir)
    try:
        remove_temp_run_dirs()
        assert not temp.exists()
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_a_stopped_temporary_run_is_removed_when_it_ends():
    s, runner = _session(), _Background()
    record = s.start_run(working_dir=None, runner=runner, background=True)
    temp = Path(record.work_dir)
    try:
        s.new()                             # stops the run
        assert runner.handle.cancelled and temp.is_dir()   # AERMOD may still be writing
        runner.finish()
        assert not temp.exists()
    finally:
        shutil.rmtree(temp, ignore_errors=True)


# ----------------------------------------------------------------------
# code-G7: a tab forked during a run (a desktop reload) shares the run
# ----------------------------------------------------------------------

def test_a_fork_shows_the_run_and_both_tabs_record_its_end(tmp_path):
    s, runner = _session(), _Background()
    s.start_run(working_dir=tmp_path, runner=runner, background=True)
    other = s.fork("reloaded")
    finished = []
    other.subscribe(SessionEvent.RUN_FINISHED, finished.append)
    assert other.run_in_progress is not None
    assert other.cancel_run() and runner.handle.cancelled     # Cancel works there
    runner.finish()
    assert finished and finished[0].run.number == 1
    assert [r.number for r in other.runs] == [r.number for r in s.runs] == [1]
    assert s.run_in_progress is None and other.run_in_progress is None


def test_replacing_the_project_in_one_tab_leaves_the_shared_run_to_the_other(tmp_path):
    s, runner = _session(), _Background()
    s.start_run(working_dir=tmp_path, runner=runner, background=True)
    other = s.fork("duplicate")
    s.new()
    assert not runner.handle.cancelled      # the other tab still shows it
    assert s.run_in_progress is None and other.run_in_progress is not None
    runner.finish()
    assert [r.number for r in other.runs] == [1] and s.runs == []


# ----------------------------------------------------------------------
# live-G5: the project changed since the run
# ----------------------------------------------------------------------

def test_the_session_knows_when_the_project_changed_since_a_run(tmp_path):
    s = _session()
    record = s.start_run(working_dir=tmp_path, runner=_Runner())
    assert not s.changed_since(record)
    s.project.sources.sources[0].emission_rate = 200.0
    assert s.changed_since(record)
    s.project.sources.sources[0].emission_rate = 1
    assert not s.changed_since(record)


# ----------------------------------------------------------------------
# code-G3: the header, the badges and the checklist agree on the met files
# ----------------------------------------------------------------------

def _met_session(surface, profile, working_dir="") -> Session:
    s = _session()
    met = s.project.meteorology
    met.surface_file, met.profile_file = surface, profile
    met.surface_station_id = met.upper_air_station_id = 14735
    met.data_start_year = 1988
    s.set_control(averaging_periods=["1"])
    s.run_options.working_dir = working_dir
    s.validate(check_files=True)
    return s


@pytest.mark.parametrize("which", ["surface", "profile"])
def test_a_missing_met_file_blocks_everywhere(tmp_path, which):
    files = {"surface": str(EPA / "AERMET2.SFC"), "profile": str(EPA / "AERMET2.PFL")}
    files[which] = str(tmp_path / "missing")
    s = _met_session(files["surface"], files["profile"])
    assert readiness(s.validation) == "Not ready to run: 1 problem in Meteorology"
    assert step_statuses(s.project, s.validation, s.runs)["meteorology"] == "error"
    found = review(s, have_binary=True)
    assert not found.ready
    assert found.blocking[0].problems == [f"{which} file {tmp_path / 'missing'} does not exist"]


def test_relative_met_files_are_looked_for_in_the_working_directory(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(tmp_path)
    s = _met_session("AERMET2.SFC", "AERMET2.PFL", working_dir=str(work))
    assert readiness(s.validation).startswith("Not ready")
    for name in ("AERMET2.SFC", "AERMET2.PFL"):
        shutil.copy(EPA / name, work / name)
    s.validate(check_files=True)
    assert readiness(s.validation) == "Ready to run"
    assert review(s, have_binary=True).ready
    assert met_file_findings(s.project.meteorology, "") != []      # blank: a new folder


# ----------------------------------------------------------------------
# live-G7: the surface file's header against the Stations
# ----------------------------------------------------------------------

def test_stations_that_differ_from_the_surface_file_are_a_warning():
    s = _met_session(str(EPA / "AERMET2.SFC"), str(EPA / "AERMET2.PFL"))
    assert step_statuses(s.project, s.validation, s.runs)["meteorology"] == "complete"
    met = s.project.meteorology
    met.surface_station_id, met.upper_air_station_id, met.data_start_year = 0, 0, 2020
    s.validate(check_files=True)
    assert step_statuses(s.project, s.validation, s.runs)["meteorology"] == "warning"
    assert readiness(s.validation) == "Ready to run, with 3 warnings"
    period = s.met_coverage().period
    assert [(f.field, f.message) for f in met_header_findings(met, period)] == [
        ("surface_station_id", "is 0, but the surface file's header names surface station 14735"),
        ("upper_air_station_id",
         "is 0, but the surface file's header names upper-air station 00014735"),
        ("data_start_year", "is 2020, but the surface file's data start in 1988")]


def test_use_the_files_values_fills_the_stations():
    from pyaermod.gui_v2.pages.meteorology import header_values, use_header_values

    s = _met_session(str(EPA / "AERMET2.SFC"), str(EPA / "AERMET2.PFL"))
    met = s.project.meteorology
    met.surface_station_id, met.upper_air_station_id, met.data_start_year = 0, 0, 2020
    assert header_values(s) == {"surface_station_id": 14735, "upper_air_station_id": 14735,
                                "data_start_year": 1988}
    use_header_values(s)
    assert (met.surface_station_id, met.upper_air_station_id, met.data_start_year) == (
        14735, 14735, 1988)
    assert s.dirty and header_values(s) == {}


# ----------------------------------------------------------------------
# code-G5, live-G4, live-G8: what the editors read and refuse
# ----------------------------------------------------------------------

def test_vertices_and_numbers_in_aermods_own_spelling_are_read():
    assert _parse_pairs("100 200\n300, 400\n300;500\n0 0 10 0") == [
        (100.0, 200.0), (300.0, 400.0), (300.0, 500.0), (0.0, 0.0), (10.0, 0.0)]
    assert _parse_numbers("1 2\n3, 4\n5") == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_lines_that_cannot_be_read_are_named_not_dropped():
    assert _unread_pair_lines("100 200\n\n100\nx y\n1,5 2") == [3, 4, 5]
    assert _unread_number_lines("1\n1,5\nabc\n2") == [2, 3]     # a decimal comma is not guessed


@pytest.mark.parametrize(("value", "problem"), [
    ("STACK1", None), ("ABCDEFGHIJKL", None),
    ("", "Enter an ID"), ("   ", "Enter an ID"),
    ("A B", "No blanks: AERMOD reads a deck line's fields split at blanks"),
    ("ABCDEFGHIJKLM", "At most 12 characters (13 now)"),
])
def test_a_source_id_aermod_cannot_read_is_flagged(value, problem):
    assert source_id_problem(value) == problem


def test_an_items_own_problems_are_found_for_its_editor():
    s = _session()
    assert item_findings(s.project, _point(stack_height=-5.0)) == [
        "PointSource S stack height must be >= 0, got -5.0 (AERMOD E209)"]
    assert item_findings(s.project, _point()) == []
    grid = CartesianGrid(grid_name="G", x_init=0, x_num=0, x_delta=10, y_init=0, y_num=3,
                         y_delta=10)
    assert item_findings(s.project, grid)


# ----------------------------------------------------------------------
# live-G2: closing the tab asks while work would be lost
# ----------------------------------------------------------------------

def test_leaving_asks_only_while_work_would_be_lost(tmp_path):
    from pyaermod.gui_v2.app import must_warn_before_leaving

    s = Session()
    assert not must_warn_before_leaving(s)
    s.set_control(title_one="Edited")
    assert must_warn_before_leaving(s)
    s.save_as(tmp_path / "saved.json")
    assert not must_warn_before_leaving(s)
    runner = _Background()
    s.add_source(_point())
    s.save()
    s.start_run(working_dir=tmp_path, runner=runner, background=True)
    assert must_warn_before_leaving(s)
    runner.finish()
    assert not must_warn_before_leaving(s)


# ----------------------------------------------------------------------
# code-G2: a huge grid never freezes the plan view
# ----------------------------------------------------------------------

def test_a_grid_with_a_billion_receptors_is_counted_not_expanded():
    from pyaermod.gui_v2.plan_view import plan_view_svg

    s = _session()
    s.project.receptors.cartesian_grids.append(
        CartesianGrid(grid_name="TYPO", x_init=0, x_num=30000, x_delta=1,
                      y_init=0, y_num=30000, y_delta=1))
    start = time.perf_counter()
    svg = plan_view_svg(s.project)
    assert time.perf_counter() - start < 0.5
    assert "900000000 receptors" in svg

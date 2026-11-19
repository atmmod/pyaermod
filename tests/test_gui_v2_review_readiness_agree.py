"""G3: the header/badge and the Review & Run checklist must agree about the met files."""

import shutil
from pathlib import Path

from pyaermod.gui_v2.readiness import review
from pyaermod.gui_v2.session import Session
from pyaermod.gui_v2.steps import readiness, step_statuses
from pyaermod.input_generator import DiscreteReceptor, PointSource

EPA = Path(__file__).resolve().parent / "fixtures" / "epa_official"


def _session(surface, profile, working_dir=""):
    s = Session()
    s.add_source(PointSource(source_id="S", x_coord=0, y_coord=0, stack_height=10, stack_temp=400,
                             exit_velocity=10, stack_diameter=1, emission_rate=1))
    s.add_receptor(DiscreteReceptor(x_coord=100, y_coord=0))
    m = s.project.meteorology
    m.surface_file, m.profile_file = surface, profile
    m.surface_station_id = m.upper_air_station_id = 14735
    m.data_start_year = 1988
    s.set_control(averaging_periods=["1"])
    s.run_options.working_dir = working_dir
    s.validate(check_files=True)
    return s


def _header_says_ready(s):
    return readiness(s.validation).startswith("Ready")


def test_an_absolute_profile_file_that_is_missing_blocks_the_checklist_too(tmp_path):
    s = _session(str(EPA / "AERMET2.SFC"), str(tmp_path / "missing.PFL"))
    assert not _header_says_ready(s)
    assert step_statuses(s.project, s.validation, s.runs)["meteorology"] == "error"
    assert not review(s, have_binary=True).ready      # AERMOD would stop in setup (E500)


def test_relative_met_files_that_exist_in_the_working_directory_are_not_called_missing(
        tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    for name in ("AERMET2.SFC", "AERMET2.PFL"):
        shutil.copy(EPA / name, work / name)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    s = _session("AERMET2.SFC", "AERMET2.PFL", working_dir=str(work))
    assert review(s, have_binary=True).ready
    assert _header_says_ready(s), readiness(s.validation)

"""The Review & Run step's review and wording, without a UI (tier T0).

``pages/run.py`` builds its checklist, warnings and status lines from
these functions; the in-process page tests (``test_gui_v2_smoke.py``) and
the journeys (J2, J6, J9) check what the page shows.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from pyaermod.gui_v2.pages import run as run_page
from pyaermod.gui_v2.session import RunRecord, Session
from pyaermod.input_generator import PointSource, PolarGrid
from pyaermod.runner import AERMODMessage, AERMODProgress, AERMODRunResult
from pyaermod.validator import ValidationError

REPO = Path(__file__).resolve().parent.parent
ALBANY_SFC = REPO / "tests" / "fixtures" / "epa_official" / "AERMET2.SFC"


def _ready_session(periods=("1", "3", "24", "PERIOD")) -> Session:
    s = Session()
    s.add_source(PointSource(source_id="STACK1", x_coord=0.0, y_coord=0.0, stack_height=65.0,
                             stack_temp=425.0, exit_velocity=18.0, stack_diameter=3.0,
                             emission_rate=100.0))
    s.add_receptor(PolarGrid(grid_name="GRID1"))
    met = s.project.meteorology
    met.surface_file, met.profile_file = str(ALBANY_SFC), str(ALBANY_SFC.with_suffix(".PFL"))
    s.project.control.averaging_periods = list(periods)
    return s


def _steps(items):
    return [i.step for i in items]


class TestReview:
    def test_a_blank_project_names_the_missing_source_receptors_and_met_files(self):
        found = run_page.review(Session())
        assert not found.ready
        assert _steps(found.blocking) == ["sources", "receptors", "meteorology"]
        sources, receptors, met = found.blocking
        assert (sources.title, sources.problems) == (
            "Sources", ["sources must contain at least one source"])
        assert receptors.problems == [
            "must have at least one receptor grid or discrete receptor"]
        assert met.problems == ["surface file must not be empty",
                                "profile file must not be empty"]
        assert found.deck is not None and "CO STARTING" in found.deck

    def test_a_complete_project_is_ready_and_shows_its_met_period(self):
        found = run_page.review(_ready_session())
        assert found.ready and found.blocking == [] and found.warnings == []
        assert found.met_summary == "AERMET2.SFC holds 1988-03-01 to 1988-03-04 (4 days, 96 hours)."
        assert found.deck == _ready_session().deck_text()

    def test_annual_with_four_days_is_a_warning_not_a_block(self):
        found = run_page.review(_ready_session(("1", "ANNUAL")))
        assert found.ready
        [warning] = found.warnings
        assert warning.step == "meteorology"
        assert re.search(r"ANNUAL.*\byear\b", warning.problems[0])

    def test_a_missing_binary_blocks_the_run(self):
        found = run_page.review(_ready_session(), have_binary=False)
        [item] = found.blocking
        assert (item.step, item.title, item.problems) == ("run", "Review & Run",
                                                          [run_page.NO_BINARY])

    def test_a_surface_file_that_cannot_be_read_is_a_warning(self, tmp_path):
        s = _ready_session()
        s.project.meteorology.surface_file = str(tmp_path / "MISSING.SFC")
        found = run_page.review(s)
        assert found.ready
        [warning] = found.warnings
        assert warning.problems == [f"surface file {tmp_path / 'MISSING.SFC'} does not exist"]

    def test_a_relative_surface_file_is_looked_for_in_the_working_directory(self):
        s = _ready_session(("1", "ANNUAL"))
        s.project.meteorology.surface_file = "AERMET2.SFC"
        s.run_options.working_dir = str(ALBANY_SFC.parent)
        [warning] = run_page.review(s).warnings
        assert "AERMET2.SFC holds" in warning.problems[0]

    def test_a_relative_met_file_needs_a_working_directory(self, monkeypatch):
        """A blank working directory is a new temp folder: AERMOD would not find
        the file there (E500), so it is not read from the server's own directory."""
        monkeypatch.chdir(ALBANY_SFC.parent)                 # the file is right here
        s = _ready_session(("1", "ANNUAL"))
        s.project.meteorology.surface_file = "AERMET2.SFC"
        s.project.meteorology.profile_file = "AERMET2.PFL"
        found = run_page.review(s)
        assert not found.ready
        [item] = found.blocking
        assert item.step == "meteorology"
        assert item.problems == [
            run_page.RELATIVE_MET.format(label="surface file", name="AERMET2.SFC"),
            run_page.RELATIVE_MET.format(label="profile file", name="AERMET2.PFL")]
        assert found.met_summary is None and found.warnings == []

        s.run_options.working_dir = str(ALBANY_SFC.parent)
        found = run_page.review(s)
        assert found.ready and found.met_summary.startswith("AERMET2.SFC holds")

    @pytest.mark.parametrize("working_dir", ["", "WORKDIR"])
    def test_a_met_file_starting_with_a_tilde_blocks_the_run(self, tmp_path, monkeypatch,
                                                             working_dir):
        """AERMOD does not expand ~ (the deck says SURFFILE ~/...), so the review
        must not read the file from the home folder and call the run ready."""
        monkeypatch.setenv("HOME", str(ALBANY_SFC.parent))    # the files are "at ~"
        s = _ready_session(("1", "ANNUAL"))
        s.project.meteorology.surface_file = "~/AERMET2.SFC"
        s.project.meteorology.profile_file = "~/AERMET2.PFL"
        s.run_options.working_dir = str(tmp_path) if working_dir else ""
        assert "   SURFFILE  ~/AERMET2.SFC" in s.deck_text().splitlines()
        found = run_page.review(s)
        assert not found.ready
        [item] = found.blocking
        assert item.step == "meteorology"
        assert item.problems == [
            run_page.HOME_MET.format(label="surface file", name="~/AERMET2.SFC"),
            run_page.HOME_MET.format(label="profile file", name="~/AERMET2.PFL")]
        assert found.met_summary is None and found.met_file is None

    def test_a_deck_the_project_cannot_be_written_as_names_the_step(self):
        s = _ready_session()
        s.project.meteorology.start_year = 2020.5
        found = run_page.review(s)
        assert found.deck is None
        [item] = found.blocking
        assert item.step == "meteorology"
        # The validator's own finding first, then the deck's.
        assert item.problems == [
            "partial date range: 1 of 6 date fields set; set all or none",
            "the deck cannot be written: project.meteorology.start_year "
            "must be a whole number, not 2020.5"]

    def test_a_validator_that_raises_blocks_the_run(self, monkeypatch):
        from pyaermod.validator import Validator

        def broken(project, **kwargs):
            raise TypeError("'<' not supported")

        monkeypatch.setattr(Validator, "validate", broken)
        [item] = run_page.review(_ready_session()).blocking
        assert item.problems == ["the project could not be checked: '<' not supported"]


class TestStepMapping:
    @pytest.mark.parametrize(("pathway", "step"), [
        ("ControlPathway", "project"), ("ChemistryOptions", "project"),
        ("EventPathway", "project"), ("SourcePathway", "sources"),
        ("PointSource(STACK1)", "sources"), ("BuoyLineSegment(B1)", "sources"),
        ("BackgroundConcentration", "sources"), ("SolidBarrier(W1)", "sources"),
        ("ReceptorPathway", "receptors"), ("PolarGrid(GRID1)", "receptors"),
        ("CartesianGrid(G)", "receptors"), ("MeteorologyPathway", "meteorology"),
        ("OutputPathway", "output"), ("Something new", "project"),
    ])
    def test_validator_pathways(self, pathway, step):
        assert run_page._step_for_pathway(pathway) == step

    @pytest.mark.parametrize(("message", "step"), [
        ("project.meteorology.start_year must be a whole number", "meteorology"),
        ("project.sources[2].stack_height must be a number", "sources"),
        ("project.control.title_one is not text", "project"),
        ("boom", "project"), ("", "project"),
    ])
    def test_deck_errors(self, message, step):
        assert run_page._step_for_deck_error(message) == step

    def test_a_finding_about_one_source_names_it(self):
        e = ValidationError("PointSource(STACK1)", "stack_height", "must be > 0, got -5.0")
        assert run_page._problem_text(e) == "PointSource STACK1 stack height must be > 0, got -5.0"

    def test_step_ids_match_the_titles(self):
        assert list(run_page.STEP_TITLES) == list(run_page.STEP_IDS)


def _record(**kw) -> RunRecord:
    base = RunRecord(number=1, work_dir=Path("/w"), deck_path=Path("/w/d.inp"),
                     started_at=datetime(2026, 9, 29, 12, 0, 0))
    return replace(base, **kw)


def _finished(result=None, **kw) -> RunRecord:
    return _record(finished_at=datetime(2026, 9, 29, 12, 0, 2), result=result, **kw)


E480 = AERMODMessage(severity="E", pathway="MX", code="E480", line="97", module="MAIN",
                     text="Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave",
                     detail="NUMYRS=0")


class TestWording:
    def test_status_lines(self):
        assert run_page.run_status_text(None) == "AERMOD has not been run for this project yet."
        assert run_page.run_status_text(_record()) == "Running AERMOD in /w ..."
        ok = AERMODRunResult(success=True, input_file="x", runtime_seconds=0.14)
        assert run_page.run_status_text(_finished(ok)) == (
            "Succeeded in 0.1 s. See the Results step.")
        stopped = AERMODRunResult(success=False, input_file="x", runtime_seconds=3.2,
                                  cancelled=True)
        assert run_page.run_status_text(_finished(stopped)) == "Cancelled after 3.2 s."
        failed = AERMODRunResult(success=False, input_file="x", error_message=str(E480))
        assert run_page.run_status_text(_finished(failed)) == f"Failed: {E480}"
        assert run_page.run_status_text(_finished(error="no aermod")) == "Failed: no aermod"
        bare = AERMODRunResult(success=False, input_file="x", return_code=3)
        assert run_page.run_status_text(_finished(bare)) == "Failed: exit code 3"

    def test_every_status_line_starts_with_its_status(self):
        for record in (_record(), _finished(error="x"),
                       _finished(AERMODRunResult(success=True, input_file="x")),
                       _finished(AERMODRunResult(success=False, input_file="x",
                                                 cancelled=True))):
            assert run_page.run_status_text(record).split()[0].rstrip(":") in (
                "Running", "Succeeded", "Failed", "Cancelled")

    def test_message_counts(self):
        result = AERMODRunResult(success=False, input_file="x", messages=[E480],
                                 message_counts={"E": 1, "W": 6, "I": 1})
        assert run_page.message_counts_text(_finished(result)) == (
            "AERMOD reported 1 fatal error, 6 warnings and 1 informational message.")
        assert run_page.message_counts_text(_finished(error="x")) == ""
        assert run_page.message_counts_text(_finished(
            AERMODRunResult(success=False, input_file="x"))) == ""
        assert run_page.message_counts_text(_finished(
            AERMODRunResult(success=False, input_file="x", cancelled=True,
                            messages=[E480]))) == ""

    def test_progress(self):
        assert run_page.progress_text(None) == ""
        assert run_page.progress_text(_record()) == "Starting AERMOD ..."
        setup = AERMODProgress(stage="setup")
        assert run_page.progress_text(_record(progress=setup)) == "Reading the deck (setup) ..."
        assert run_page.progress_text(_finished(error="x", progress=setup)) == (
            "Stopped during setup")
        day = AERMODProgress(stage="day", day=62, year=1988, days_processed=2)
        assert run_page.progress_text(_record(progress=day, expected_days=4)) == (
            "Day 62 of 1988 (2 of 4 days)")
        assert run_page.progress_text(_record(progress=day)) == (
            "Day 62 of 1988 (2 days processed)")
        out = replace(day, stage="output")
        assert run_page.progress_text(_record(progress=out, expected_days=2)) == (
            "Day 62 of 1988 (2 of 2 days), writing the results")
        assert run_page.progress_text(_record(progress=AERMODProgress(stage="output"))) == (
            "Writing the results ...")

    def test_cancel_is_offered_once_aermod_speaks_or_after_a_while(self):
        started = datetime(2026, 9, 29, 12, 0, 0)
        assert not run_page.can_cancel(None)
        assert not run_page.can_cancel(_finished(error="x"))
        assert not run_page.can_cancel(_record(), now=started + timedelta(seconds=0.5))
        assert run_page.can_cancel(_record(progress=AERMODProgress(stage="setup")),
                                   now=started)
        assert run_page.can_cancel(_record(), now=started + timedelta(
            seconds=run_page.CANCEL_WITHOUT_OUTPUT_S))

    def test_elapsed(self):
        assert [run_page.elapsed_text(s) for s in (0, 5.9, 65, -1)] == [
            "0:00", "0:05", "1:05", "0:00"]

    def test_run_log(self):
        assert run_page.run_log_text(None) == ""
        assert run_page.run_log_text(_finished(error="boom")) == "boom\n"
        text = run_page.run_log_text(_finished(AERMODRunResult(
            success=True, input_file="x", return_code=0, runtime_seconds=1.0,
            stdout="+Now Processing SETUP Information")))
        assert text.startswith("return_code=0, runtime=1.0 s") and "SETUP" in text


class TestCommonErrorsLinks:
    def test_each_link_has_an_entry_on_the_common_errors_page(self):
        page = (REPO / "docs" / "common-errors.md").read_text(encoding="utf-8")
        for code, anchor in run_page.COMMON_ERRORS.items():
            assert re.search(rf"^#+ .*{code}.*\{{#{anchor}\}}\s*$", page, re.M), code

    def test_help_url(self):
        assert run_page.help_url("e480") == run_page.COMMON_ERRORS_URL + "#e480"
        assert run_page.help_url("W206") is None

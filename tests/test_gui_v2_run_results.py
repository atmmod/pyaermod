"""``pyaermod.gui_v2.run_results``: what Results shows, from a run's files (T0).

The runs are real AERMOD output (tests/fixtures/output_parser/, see its
README): each ``aermod.out`` is placed in a working directory as a run
of the GUI would leave it, and the view is built from it.
"""

from __future__ import annotations

import gc
import shutil
import weakref
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytest

from pyaermod.gui_v2 import run_results as rr
from pyaermod.gui_v2.session import Change, RunRecord, Session, SessionEvent
from pyaermod.runner import AERMODRunResult, parse_aermod_messages

RUNS = Path(__file__).parent / "fixtures" / "output_parser"


def _record(case: str, tmp_path: Path, number: int = 1,
            work_dir: Optional[Path] = None) -> RunRecord:
    wd = work_dir or tmp_path / case
    wd.mkdir(parents=True, exist_ok=True)
    started = datetime.now() - timedelta(seconds=1)
    deck = wd / "pyaermod_gui.inp"
    shutil.copy(RUNS / case / "aermod.inp", deck)
    out = wd / "pyaermod_gui.out"
    shutil.copy(RUNS / case / "aermod.out", out)
    for plot in (RUNS / case).glob("*.plt"):
        shutil.copy(plot, wd)
    messages = parse_aermod_messages(out)
    result = AERMODRunResult(success=True, input_file=str(deck), return_code=0,
                             output_file=str(out), messages=messages,
                             finished_successfully=True)
    return RunRecord(number=number, work_dir=wd, deck_path=deck, started_at=started,
                     finished_at=datetime.now(), result=result)


def test_flags_are_kept_on_the_maxima(tmp_path):
    view = rr.build_view(_record("calm_missing", tmp_path))
    assert view.succeeded and view.headline == "Run 1 succeeded"
    tables = {t.averaging_period: t for t in view.concentration_tables()}
    assert list(tables) == ["1HR", "3HR", "24HR", "PERIOD"]
    day = tables["24HR"].max_row
    assert (day["value_text"], day["flag"]) == ("15.94753", "b")
    assert rr.FLAG_MEANINGS["b"] == "includes calm and missing hours"


def test_deposition_is_shown_as_deposition(tmp_path):
    view = rr.build_view(_record("conc_ddep", tmp_path))
    assert [t.averaging_period for t in view.concentration_tables()] == ["1HR", "24HR", "PERIOD"]
    dep = view.deposition_tables()
    assert [(t.output_type, t.averaging_period, t.units) for t in dep] == [
        ("DDEP", "1HR", "g/m^2"), ("DDEP", "24HR", "g/m^2"), ("DDEP", "PERIOD", "g/m^2")]
    assert dep[0].max_row["value_text"] == "0.00274"
    # Pollutant OTHER has no NAAQS.
    assert view.naaqs == ()


def test_a_deposition_only_run_has_no_concentration_tables(tmp_path):
    view = rr.build_view(_record("ddep_only", tmp_path))
    assert view.concentration_tables() == []
    assert [t.output_type for t in view.deposition_tables()] == ["DDEP"] * 3


def test_a_deposition_only_run_is_mapped_as_deposition(tmp_path):
    """Its plot files hold DRY DEPO where a concentration run has AVERAGE CONC."""
    from pyaermod.gui_v2.results_map import map_description

    view = rr.build_view(_record("ddep_only", tmp_path))
    assert [(p.file.name, p.period, p.output_type) for p in view.plots] == [
        ("ddep_01H.plt", "1HR", "DDEP"), ("ddep_PERIOD.plt", "PERIOD", "DDEP")]
    one = view.plots[0]
    assert one.title == "1ST highest 1-HR dry deposition values, source group ALL"
    assert view.plot_units(one) == "g/m^2"
    # The plot file's peak is the summary table's: 0.00274 at (519.62, -300.00).
    x, y, value = one.peak
    assert (round(x, 2), round(y, 2), value) == (519.62, -300.0, 0.00274)
    assert view.deposition_tables()[0].max_value == pytest.approx(value)
    assert map_description(one, "g/m²") == (
        "Dry deposition map of the 1ST highest 1-HR dry deposition values, source group "
        "ALL from ddep_01H.plt: 72 receptors, highest 0.00274 g/m² at (519.62, -300.00).")
    assert [f.name for f in view.files] == [
        "pyaermod_gui.inp", "pyaermod_gui.out", "ddep_01H.plt", "ddep_PERIOD.plt"]


def test_a_design_value_table_is_labelled_with_its_rank():
    """Headings as AERMOD prints them (full_year here, EPA's testpm25)."""
    assert rr.table_qualifier("THE SUMMARY OF HIGHEST 24-HR RESULTS") == ""
    assert rr.table_qualifier("THE SUMMARY OF MAXIMUM PERIOD ( 96 HRS) RESULTS") == ""
    assert rr.table_qualifier("THE SUMMARY OF MAXIMUM ANNUAL RESULTS AVERAGED OVER 5 YEARS") == ""
    assert rr.table_qualifier(
        "THE SUMMARY OF MAXIMUM 1ST-HIGHEST MAX DAILY 1-HR RESULTS AVERAGED OVER 1 YEARS") == ""
    assert rr.table_qualifier(
        "THE SUMMARY OF MAXIMUM 4TH-HIGHEST MAX DAILY 1-HR RESULTS AVERAGED OVER 1 YEARS"
    ) == "4th-highest daily maximum, averaged over 1 year"
    assert rr.table_qualifier(
        "THE SUMMARY OF MAXIMUM 8TH-HIGHEST 24-HR RESULTS AVERAGED OVER 5 YEARS"
    ) == "8th-highest, averaged over 5 years"


def test_aermods_own_design_value_is_compared_with_the_naaqs(tmp_path):
    """SO2, AVERTIME 1 ANNUAL, a year of met: AERMOD's 4TH-HIGHEST table."""
    view = rr.build_view(_record("full_year", tmp_path))
    [check] = view.naaqs
    assert check.label == "SO2 1-hour (99th percentile of daily max)"
    assert check.basis == "design value"
    assert check.how == ('AERMOD\'s table "THE SUMMARY OF MAXIMUM 4TH-HIGHEST MAX DAILY '
                         '1-HR RESULTS AVERAGED OVER 1 YEARS" (1 year of met data)')
    assert check.value == pytest.approx(76.07952, abs=5e-6)
    assert check.location == pytest.approx((519.62, -300.0))
    assert check.level_ugm3 == pytest.approx(196.39, abs=0.01)
    assert check.verdict == "Below the NAAQS"
    assert check.level_text == "196.4 µg/m³ (75 ppb)"


def test_a_design_value_table_at_another_rank_is_not_a_screen(tmp_path):
    """SO2 with RECTABLE 1 8TH: the only 1-hour table is the 8th-highest daily
    maximum, which can be below the 4th-highest design value."""
    view = rr.build_view(_record("so2_8th_only", tmp_path))
    [check] = view.naaqs
    assert check.label == "SO2 1-hour (99th percentile of daily max)"
    assert check.basis == "not compared"
    assert check.value is None
    assert check.verdict == "Not compared"
    assert check.how == ("the run has only AERMOD's 1-HR table of the 8th-highest daily "
                         "maximum, averaged over 1 year, which can be below the design "
                         "value; the design value is the 4th-highest")


def test_a_file_changed_after_the_run_is_not_offered(tmp_path):
    record = _record("calm_missing", tmp_path)
    view = rr.build_view(record)
    assert view.deck.read() == record.deck_path.read_bytes()
    record.deck_path.write_text("CO STARTING\n")
    with pytest.raises(rr.StaleFileError, match="has changed since run 1 finished"):
        view.deck.read()


def test_a_run_that_did_not_start_has_no_results(tmp_path):
    wd = tmp_path / "run"
    wd.mkdir()
    (wd / "pyaermod_gui.inp").write_text("CO STARTING\n")
    record = RunRecord(number=1, work_dir=wd, deck_path=wd / "pyaermod_gui.inp",
                       started_at=datetime.now(), finished_at=datetime.now(),
                       error="no aermod on PATH")
    view = rr.build_view(record)
    assert not view.succeeded and view.results is None
    assert view.detail == "AERMOD could not be run: no aermod on PATH"
    assert [f.name for f in view.files] == ["pyaermod_gui.inp"]


def test_views_are_built_when_runs_finish_and_kept(tmp_path):
    session = Session()
    unsubscribe = rr.watch(session)
    record = _record("full_year", tmp_path)
    session.runs.append(record)
    session._emit(Change(SessionEvent.RUN_FINISHED, run=record))
    view = rr.view_of(record)
    # The files are overwritten by a later run in the same directory ...
    shutil.copy(RUNS / "calm_missing" / "aermod.out", record.work_dir / "pyaermod_gui.out")
    later = _record("calm_missing", tmp_path, number=2, work_dir=record.work_dir)
    session.runs.append(later)
    # ... and the first run's view still holds its own values.
    assert rr.view_of(record) is view
    assert list(view.results.concentrations) == ["ANNUAL", "1HR"]
    assert rr.overwritten_by(session, record) is later
    assert rr.overwritten_by(session, later) is None
    assert rr.completed_runs(session) == [later, record]
    unsubscribe()
    assert session._observers == []


def test_a_view_goes_with_its_run(tmp_path):
    """The cache holds a view only while its run record is alive."""
    record = _record("calm_missing", tmp_path)
    view = rr.view_of(record)
    assert rr.view_of(record) is view
    key, alive = id(record), weakref.ref(record)
    del record
    gc.collect()
    assert alive() is None
    assert key not in rr._VIEWS
    # The view is still usable on its own.
    assert view.headline == "Run 1 succeeded" and view.started_at is not None


def test_a_run_that_could_not_start_is_listed(tmp_path):
    session = Session()
    ran = _record("calm_missing", tmp_path)
    wd = tmp_path / "second"
    wd.mkdir()
    (wd / "pyaermod_gui.inp").write_text("CO STARTING\n")
    did_not = RunRecord(number=2, work_dir=wd, deck_path=wd / "pyaermod_gui.inp",
                        started_at=datetime.now(), finished_at=datetime.now(),
                        error="no aermod on PATH")
    in_progress = RunRecord(number=3, work_dir=wd, deck_path=wd / "pyaermod_gui.inp",
                            started_at=datetime.now())
    session.runs.extend([ran, did_not, in_progress])
    assert rr.completed_runs(session) == [did_not, ran]
    view = rr.view_of(did_not)
    assert (view.headline, view.ran) == ("Run 2 failed", False)


def test_period_labels():
    assert rr.period_label("1HR") == "1-HR" and rr.period_label("PERIOD") == "PERIOD"
    assert sorted(["PERIOD", "24HR", "1HR", "ANNUAL", "3HR"], key=rr.period_sort_key) == [
        "1HR", "3HR", "24HR", "PERIOD", "ANNUAL"]

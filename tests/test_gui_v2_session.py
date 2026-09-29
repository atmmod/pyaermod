"""Tier T0 tests for the GUI's :class:`~pyaermod.gui_v2.session.Session`.

No NiceGUI here: the session is the UI-free half of the GUI, and every
user operation is checked as an operation plus the change events it
emits (PLAN-gui.md, "Test strategy").
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from pyaermod.gui_v2.project_io import load_project, project_to_json, save_project
from pyaermod.gui_v2.session import (
    DECK_NAME,
    Change,
    DeckError,
    ProjectFileError,
    RunInProgressError,
    RunRecord,
    Session,
    SessionEvent,
    clean_file_name,
)
from pyaermod.gui_v2.state import _empty_project
from pyaermod.input_generator import (
    CartesianGrid,
    DiscreteReceptor,
    PointSource,
    PolarGrid,
    PollutantType,
    VolumeSource,
)
from tests.e2e.harness import install_fake_aermod

REPO = Path(__file__).resolve().parent.parent
RECORDINGS = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings"


def _load_recorder():
    """``scripts/record_aermod_fixtures.py``, whose project builders made the recordings."""
    spec = importlib.util.spec_from_file_location(
        "record_aermod_fixtures", REPO / "scripts" / "record_aermod_fixtures.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses look their module up in sys.modules while being built.
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


_albany_project = _load_recorder()._albany_project

E = SessionEvent


class Recorder:
    """Subscribes to every event and keeps the changes in order."""

    def __init__(self, session: Session):
        self.changes: list[Change] = []
        self.unsubscribe = session.subscribe(list(SessionEvent), self.changes.append)

    @property
    def events(self) -> list[SessionEvent]:
        return [c.event for c in self.changes]

    def clear(self) -> None:
        self.changes.clear()


def _point(sid: str = "STK1", **kw) -> PointSource:
    return PointSource(source_id=sid, x_coord=0.0, y_coord=0.0, **kw)


# ---------------------------------------------------------------------
# Basics and observers
# ---------------------------------------------------------------------

def test_new_session_is_blank_and_clean():
    s = Session()
    assert s.project.control.title_one == "Untitled run"
    assert s.project_path is None and s.file_name is None
    assert s.dirty is False
    assert s.runs == [] and s.last_run is None and s.last_completed_run is None
    assert s.run_in_progress is None and s.validation is None
    assert s.title == "PyAERMOD — Untitled"
    assert s.suggested_file_name() == "project.json"
    assert s.source_entries() == [] and s.receptor_entries() == []


def test_title_names_the_file_and_marks_changes():
    s = Session()
    s.file_name = "myproject.json"
    assert s.title == "PyAERMOD — myproject.json"
    s.dirty = True
    assert s.title == "PyAERMOD — myproject.json (modified)"
    assert s.suggested_file_name() == "myproject.json"


def test_sessions_compare_by_identity():
    # Refreshables and observer lists hang off sessions; two tabs with equal
    # content must never be mistaken for one.
    assert Session() != Session()


def test_subscribe_receives_changes_in_order_and_unsubscribe_stops_them():
    s = Session()
    seen: list[tuple[str, SessionEvent, str | None]] = []
    unsub_a = s.subscribe(E.PROJECT_CHANGED, lambda c: seen.append(("a", c.event, c.part)))
    s.subscribe([E.PROJECT_CHANGED, E.DIRTY_CHANGED], lambda c: seen.append(("b", c.event, c.part)))
    s.set_control(title_one="T")
    assert seen == [
        ("a", E.PROJECT_CHANGED, "control"),
        ("b", E.PROJECT_CHANGED, "control"),
        ("b", E.DIRTY_CHANGED, None),
    ]
    seen.clear()
    unsub_a()
    unsub_a()                     # idempotent
    s.set_control(title_one="U")
    assert seen == [("b", E.PROJECT_CHANGED, "control")]   # already dirty: no DIRTY_CHANGED


def test_failing_observer_is_logged_and_others_still_run(caplog):
    s = Session()
    seen = []

    def boom(_change):
        raise RuntimeError("observer broke")

    s.subscribe(E.PROJECT_REPLACED, boom)
    s.subscribe(E.PROJECT_REPLACED, seen.append)
    with caplog.at_level(logging.ERROR, logger="pyaermod.gui_v2.session"):
        s.new()
    assert [c.event for c in seen] == [E.PROJECT_REPLACED]
    assert any("observer broke" in (r.exc_text or "") for r in caplog.records)


# ---------------------------------------------------------------------
# New and Open
# ---------------------------------------------------------------------

def test_new_replaces_project_object_and_clears_path_runs_validation_keys(tmp_path):
    s = Session()
    old = s.project
    key = s.add_source(_point())
    s.validate()
    s.project_path, s.file_name = tmp_path / "x.json", "x.json"
    s.runs.append(_finished_record(s, tmp_path))
    rec = Recorder(s)
    s.new()
    assert s.project is not old
    assert s.project.control.title_one == "Untitled run"
    assert s.project_path is None and s.file_name is None
    assert s.runs == [] and s.validation is None and s._keys == {}
    assert s.dirty is False
    assert rec.events == [E.PROJECT_REPLACED, E.DIRTY_CHANGED]
    assert s.delete_source(key) is None          # the old key means nothing now


def test_new_on_a_clean_untitled_session_emits_only_the_replacement():
    s = Session()
    rec = Recorder(s)
    s.new()
    assert rec.events == [E.PROJECT_REPLACED]


def _finished_record(s: Session, tmp_path: Path):
    from datetime import datetime

    from pyaermod.gui_v2.session import RunRecord
    from pyaermod.runner import AERMODRunResult
    now = datetime.now()
    return RunRecord(number=len(s.runs) + 1, work_dir=tmp_path, deck_path=tmp_path / DECK_NAME,
                     started_at=now, finished_at=now,
                     result=AERMODRunResult(success=True, input_file="x"))


def test_open_json_path_sets_path_and_name_and_clears_runs(tmp_path):
    project = _empty_project()
    project.control.title_one = "From disk"
    path = save_project(project, tmp_path / "disk.json")
    s = Session()
    s.set_control(title_one="unsaved")
    s.runs.append(_finished_record(s, tmp_path))
    rec = Recorder(s)
    s.open_json(path)
    assert s.project.control.title_one == "From disk"
    assert s.project_path == path and s.file_name == "disk.json"
    assert s.runs == [] and s.dirty is False
    assert rec.events == [E.PROJECT_REPLACED, E.DIRTY_CHANGED]


def test_open_json_text_sets_name_not_path():
    project = _empty_project()
    project.sources.sources.append(_point("UPLOADED"))
    s = Session()
    s.open_json(project_to_json(project), name="upload.json")
    assert s.project_path is None and s.file_name == "upload.json"
    assert [src.source_id for _k, src in s.source_entries()] == ["UPLOADED"]
    s.open_json(project_to_json(project).encode("utf-8"))
    assert s.file_name is None


_NEWER = json.dumps({"save_format_version": 999, "project": {}})


@pytest.mark.parametrize("text", [
    "{not json",
    "[]",
    "{}",
    '{"project": []}',
    '{"project": {"control": []}}',
    _NEWER,
    b"\xff\xfe\x00not utf-8",
], ids=["invalid-json", "list", "empty-object", "project-list", "control-list",
        "newer-format", "undecodable-bytes"])
def test_open_json_bad_input_raises_and_changes_nothing(text):
    s = Session()
    s.set_control(title_one="keep me")
    project = s.project
    rec = Recorder(s)
    with pytest.raises(ProjectFileError, match=r"^bad\.json: "):
        s.open_json(text, name="bad.json")
    assert s.project is project and s.project.control.title_one == "keep me"
    assert s.dirty is True and s.file_name is None
    assert rec.events == []


def test_open_json_missing_file_raises_project_file_error(tmp_path):
    s = Session()
    with pytest.raises(ProjectFileError, match=r"missing\.json"):
        s.open_json(tmp_path / "missing.json")


# ---------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------

def test_save_without_path_raises():
    with pytest.raises(ValueError, match="save_as"):
        Session().save()


def test_save_writes_to_project_path(tmp_path):
    path = save_project(_empty_project(), tmp_path / "p.json")
    s = Session()
    s.open_json(path)
    s.set_control(title_one="Edited")
    rec = Recorder(s)
    assert s.save() == path
    assert load_project(path).control.title_one == "Edited"
    assert s.dirty is False
    assert rec.events == [E.DIRTY_CHANGED]


def test_save_as_path(tmp_path):
    s = Session()
    s.set_control(title_one="Desktop")
    rec = Recorder(s)
    target = s.save_as(tmp_path / "sub" / "chosen.json")
    assert target == tmp_path / "sub" / "chosen.json"
    assert load_project(target).control.title_one == "Desktop"
    assert s.project_path == target and s.file_name == "chosen.json"
    assert s.dirty is False and "chosen.json" in s.title
    assert rec.events == [E.DIRTY_CHANGED]


def test_save_as_download_returns_loadable_bytes_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Session()
    s.set_control(title_one="Downloaded")
    s.project_path = tmp_path / "old.json"
    rec = Recorder(s)
    data = s.save_as_download("dl")
    assert isinstance(data, bytes)
    from pyaermod.gui_v2.project_io import project_from_json
    assert project_from_json(data).control.title_one == "Downloaded"
    assert s.file_name == "dl.json" and s.project_path is None and s.dirty is False
    assert rec.events == [E.DIRTY_CHANGED]
    assert list(tmp_path.iterdir()) == []


def _unreopenable(kind: str) -> Session:
    """A session whose project holds a value its file could not be opened with."""
    s = Session()
    if kind == "empty-number":           # an emptied number box stores None
        s.add_source(_point(emission_rate=None))
    elif kind == "text-for-objects":     # the list text area over a List[BuoyLineSegment]
        from pyaermod.input_generator import BuoyLineSegment, BuoyLineSource
        seg = BuoyLineSegment("SEG1", 0.0, 0.0, 10.0, 0.0, 1.0, 5.0)
        s.add_source(BuoyLineSource("BL", 100.0, 10.0, 20.0, 5.0, 2.0, 1000.0,
                                    line_segments=[str(seg)]))
    else:                                # "nan"
        s.add_source(PointSource(source_id="STK1", x_coord=float("nan"), y_coord=0.0))
    return s


_UNREOPENABLE = {
    "empty-number": r"sources\[0\]\.emission_rate must be a number, not null",
    "text-for-objects": r"sources\[0\]\.line_segments\[0\] must be a JSON object, not text",
    "nan": r"sources\[0\]\.x_coord must be a finite number, not nan",
}


@pytest.mark.parametrize("kind", sorted(_UNREOPENABLE))
def test_every_save_refuses_a_project_its_file_could_not_reopen(kind, tmp_path):
    s = _unreopenable(kind)
    path = save_project(_empty_project(), tmp_path / "p.json")
    before = path.read_bytes()
    s.project_path, s.file_name = path, "p.json"
    rec = Recorder(s)
    message = f"^cannot save the project: project\\.sources\\.{_UNREOPENABLE[kind]}"
    for save in (s.save, lambda: s.save_as(tmp_path / "other.json"),
                 lambda: s.save_as_download("dl.json")):
        with pytest.raises(ValueError, match=message):
            save()
    assert s.dirty is True and s.file_name == "p.json" and s.project_path == path
    assert path.read_bytes() == before and not (tmp_path / "other.json").exists()
    assert rec.events == []


def test_save_as_download_same_name_when_clean_emits_nothing():
    s = Session()
    s.save_as_download("a.json")
    rec = Recorder(s)
    s.save_as_download("a.json")
    assert rec.events == []


@pytest.mark.parametrize("given, cleaned", [
    ("smoke.json", "smoke.json"),
    ("smoke", "smoke.json"),
    ("SMOKE.JSON", "SMOKE.JSON"),
    ("notes.txt", "notes.txt.json"),
    ("  padded.json  ", "padded.json"),
    ("../../etc/passwd", "passwd.json"),
    ("/abs/dir/p.json", "p.json"),
    (r"C:\Users\me\p.json", "p.json"),
    ("", "project.json"),
    ("   ", "project.json"),
    (None, "project.json"),
    ("dir/", "dir.json"),
    # What Chromium's download of each name is called: the header must agree.
    ('résumé "q".json', "résumé _q_.json"),
    ("a:b*c?d<e>f|g.json", "a_b_c_d_e_f_g.json"),
    ("tab\tname", "tab_name.json"),
])
def test_download_file_names_are_cleaned(given, cleaned):
    assert clean_file_name(given) == cleaned


# ---------------------------------------------------------------------
# Sources, receptors and control
# ---------------------------------------------------------------------

def test_source_ops_use_stable_keys_mark_dirty_and_emit_sources_changes():
    s = Session()
    rec = Recorder(s)
    k1 = s.add_source(_point("DUP"))
    k2 = s.add_source(_point("DUP"))           # duplicate ids are allowed
    k3 = s.add_source(_point("THIRD"))
    assert len({k1, k2, k3}) == 3
    assert rec.changes[0] == Change(E.PROJECT_CHANGED, part="sources")
    assert rec.events == [E.PROJECT_CHANGED, E.DIRTY_CHANGED, E.PROJECT_CHANGED, E.PROJECT_CHANGED]
    assert s.dirty

    # Deleting another item leaves the remaining keys valid.
    removed = s.delete_source(k1)
    assert removed is not None and removed.source_id == "DUP"
    assert [k for k, _ in s.source_entries()] == [k2, k3]

    # update_source hands the key to the new object.
    replacement = _point("RENAMED")
    rec.clear()
    assert s.update_source(k2, replacement) is True
    assert s.source_entries()[0] == (k2, replacement)
    assert rec.events == [E.PROJECT_CHANGED]

    # Gone keys do nothing and emit nothing.
    rec.clear()
    assert s.delete_source(k1) is None
    assert s.update_source(k1, _point("X")) is False
    assert s.update_source("r99", _point("X")) is False
    assert rec.events == []
    assert [src.source_id for src in s.project.sources.sources] == ["RENAMED", "THIRD"]


def test_receptor_ops_dispatch_by_type_and_check_kind():
    s = Session()
    kc = s.add_receptor(CartesianGrid(grid_name="C"))
    kp = s.add_receptor(PolarGrid(grid_name="P"))
    kd = s.add_receptor(DiscreteReceptor(x_coord=1.0, y_coord=2.0))
    rp = s.project.receptors
    assert [g.grid_name for g in rp.cartesian_grids] == ["C"]
    assert [g.grid_name for g in rp.polar_grids] == ["P"]
    assert len(rp.discrete_receptors) == 1
    assert [(k, kind) for k, kind, _ in s.receptor_entries()] == [
        (kc, "CartesianGrid"), (kp, "PolarGrid"), (kd, "DiscreteReceptor")]

    with pytest.raises(TypeError, match="not a receptor type"):
        s.add_receptor(_point())
    with pytest.raises(TypeError, match="cannot replace a PolarGrid"):
        s.update_receptor(kp, CartesianGrid())

    rec = Recorder(s)
    new_polar = PolarGrid(grid_name="P2")
    assert s.update_receptor(kp, new_polar) is True
    assert rp.polar_grids == [new_polar]
    assert rec.changes == [Change(E.PROJECT_CHANGED, part="receptors")]
    assert s.delete_receptor(kc).grid_name == "C"
    assert s.delete_receptor(kc) is None
    assert s.update_receptor(kc, CartesianGrid()) is False
    assert [k for k, _kind, _ in s.receptor_entries()] == [kp, kd]


def test_entries_assign_keys_to_items_added_directly():
    s = Session()
    src = _point("DIRECT")
    s.project.sources.sources.append(src)
    s.project.receptors.polar_grids.append(PolarGrid(grid_name="PD"))
    (key, obj), = s.source_entries()
    assert obj is src and key.startswith("s")
    assert s.source_entries()[0][0] == key       # stable across calls
    (rkey, kind, _), = s.receptor_entries()
    assert kind == "PolarGrid" and rkey.startswith("r")
    # A directly removed item's key is pruned and not reused.
    s.project.sources.sources.clear()
    assert s.source_entries() == []
    assert id(src) not in s._keys
    assert s.delete_source(key) is None


def test_set_control_sets_fields():
    s = Session()
    rec = Recorder(s)
    s.set_control(title_one="A", title_two="B", pollutant_id=PollutantType.NO2)
    c = s.project.control
    assert (c.title_one, c.title_two, c.pollutant_id) == ("A", "B", PollutantType.NO2)
    assert rec.changes == [Change(E.PROJECT_CHANGED, part="control"), Change(E.DIRTY_CHANGED)]


def test_set_control_same_value_is_a_no_op():
    s = Session()
    rec = Recorder(s)
    s.set_control(title_one="Untitled run", pollutant_id=PollutantType.SO2)
    assert rec.events == [] and s.dirty is False


def test_set_control_unknown_field_raises():
    s = Session()
    with pytest.raises(AttributeError, match="no_such"):
        s.set_control(title_one="X", no_such=1)
    assert s.project.control.title_one == "Untitled run"


def test_mark_edited_marks_dirty_and_rejects_unknown_part():
    s = Session()
    rec = Recorder(s)
    s.mark_edited("meteorology")
    assert s.dirty
    assert rec.changes == [Change(E.PROJECT_CHANGED, part="meteorology"), Change(E.DIRTY_CHANGED)]
    with pytest.raises(ValueError, match="unknown project part"):
        s.mark_edited("weather")


def test_validate_stores_result_and_emits():
    s = Session()
    rec = Recorder(s)
    result = s.validate()
    assert s.validation is result
    assert not result.is_valid          # a blank project has no source
    assert rec.events == [E.VALIDATION_CHANGED]
    assert s.dirty is False


# ---------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------

posix_only = pytest.mark.skipif(platform.system() == "Windows",
                                reason="the fake AERMOD is a POSIX script")


@posix_only
def test_start_run_replays_a_recording(tmp_path, monkeypatch):
    from pyaermod.runner import AERMODRunner

    exe = install_fake_aermod(tmp_path / "bin")
    monkeypatch.setenv("PYAERMOD_E2E_RECORDING", str(RECORDINGS / "albany_e480"))
    monkeypatch.delenv("PYAERMOD_E2E_DELAY", raising=False)
    monkeypatch.delenv("PYAERMOD_E2E_FAKE_LOG", raising=False)
    s = Session(_albany_project(["1", "ANNUAL"], "AERMET2.SFC"))
    rec = Recorder(s)
    work_dir = tmp_path / "work" / ".." / "run"         # never resolved
    record = s.start_run(working_dir=str(work_dir), timeout=60,
                         runner=AERMODRunner(executable_path=exe, log_level="WARNING"))
    assert rec.events == [E.RUN_STARTED, E.RUN_FINISHED]
    started, finished = rec.changes
    assert started.run is not None and started.run.in_progress
    assert finished.run is record and not record.in_progress
    assert record.number == 1 and record.work_dir == work_dir
    assert record.deck_path == work_dir / DECK_NAME and record.deck_path.exists()
    assert "STACK1" in record.deck_path.read_text()
    assert record.error is None and record.result is not None
    assert record.success is False and record.result.success is False
    assert "E480" in [m.code for m in record.result.messages]
    assert s.runs == [record] and s.last_run is record and s.last_completed_run is record
    assert s.run_in_progress is None
    assert s.dirty is False                     # a run does not change the project


class _StubRunner:
    def __init__(self, session: Session, result=None, exc: Exception | None = None):
        self.session, self.result, self.exc = session, result, exc
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        assert self.session.run_in_progress is not None
        assert self.session.run_in_progress.in_progress
        # A synchronous run cannot be interrupted.
        assert self.session.cancel_run() is False
        if self.exc is not None:
            raise self.exc
        return self.result


def test_a_synchronous_run_is_in_progress_during_the_run_and_cannot_be_cancelled(tmp_path):
    from pyaermod.runner import AERMODRunResult
    s = Session()
    runner = _StubRunner(s, result=AERMODRunResult(success=True, input_file="x"))
    record = s.start_run(working_dir=tmp_path, timeout=5, runner=runner)
    assert runner.calls == [{"input_file": tmp_path / DECK_NAME, "working_dir": tmp_path,
                             "timeout": 5}]
    assert record.success and s.run_in_progress is None
    assert s.cancel_run() is False


def test_start_run_records_runner_exception(tmp_path):
    s = Session()
    rec = Recorder(s)
    record = s.start_run(working_dir=tmp_path, runner=_StubRunner(s, exc=FileNotFoundError("no aermod")))
    assert record.error == "no aermod" and record.result is None and not record.success
    assert s.last_run is record and s.last_completed_run is None
    assert rec.events == [E.RUN_STARTED, E.RUN_FINISHED]


def test_a_runner_bug_is_logged_with_its_traceback(tmp_path, caplog):
    s = Session()
    with caplog.at_level(logging.WARNING, logger="pyaermod.gui_v2.session"):
        record = s.start_run(working_dir=tmp_path,
                             runner=_StubRunner(s, exc=AttributeError("'NoneType' has no x")))
    assert record.error == "'NoneType' has no x"
    [logged] = caplog.records
    assert logged.levelno == logging.ERROR and logged.getMessage() == "AERMOD run 1 raised"
    assert "AttributeError" in (logged.exc_text or "")


def test_a_missing_binary_is_logged_without_a_traceback(tmp_path, caplog):
    s = Session()
    with caplog.at_level(logging.WARNING, logger="pyaermod.gui_v2.session"):
        s.start_run(working_dir=tmp_path, runner=_StubRunner(s, exc=FileNotFoundError("no aermod")))
    [logged] = caplog.records
    assert logged.levelno == logging.WARNING and logged.exc_info is None
    assert logged.getMessage() == "AERMOD run 1 could not start: no aermod"


def test_start_run_without_a_binary_records_the_runner_construction_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    s = Session()
    record = s.start_run(working_dir=tmp_path / "run")
    assert record.error and record.result is None
    assert (tmp_path / "run" / DECK_NAME).exists()


def test_deck_failure_raises_deck_error_without_record_or_events(tmp_path, monkeypatch):
    s = Session()

    def boom(self, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(type(s.project), "to_aermod_input", boom)
    rec = Recorder(s)
    with pytest.raises(DeckError, match="boom"):
        s.start_run(working_dir=tmp_path / "never")
    assert s.runs == [] and rec.events == [] and not (tmp_path / "never").exists()


def test_a_deck_writer_bug_is_logged_with_its_traceback(tmp_path, monkeypatch, caplog):
    s = Session()

    def bug(self, **kwargs):
        raise TypeError("'<' not supported between instances of 'tuple' and 'int'")

    monkeypatch.setattr(type(s.project), "to_aermod_input", bug)
    with caplog.at_level(logging.WARNING, logger="pyaermod.gui_v2.session"), \
            pytest.raises(DeckError, match=r"^'<' not supported"):
        s.start_run(working_dir=tmp_path / "never")
    [logged] = caplog.records
    assert logged.levelno == logging.ERROR and logged.getMessage() == "Writing the deck raised"
    assert "TypeError" in (logged.exc_text or "")


def test_a_deck_the_user_can_fix_is_refused_without_a_log_record(tmp_path, caplog):
    s = Session()
    s.project.meteorology.start_year = 12.5
    with caplog.at_level(logging.DEBUG, logger="pyaermod.gui_v2.session"), \
            pytest.raises(DeckError, match=(
                r"^project\.meteorology\.start_year must be a whole number, not 12\.5$")):
        s.start_run(working_dir=tmp_path / "never")
    assert caplog.records == [] and s.runs == [] and not (tmp_path / "never").exists()


def test_the_deck_is_written_with_whole_numbers_the_number_boxes_stored_as_floats(tmp_path):
    """ui.number stores 2020.0; the deck writer formats STARTEND with "d"."""
    s = Session()
    s.add_source(PointSource(source_id="STACK1", x_coord=0.0, y_coord=0.0))
    met = s.project.meteorology
    met.start_year, met.start_month, met.start_day = 2020.0, 1.0, 1.0
    met.end_year, met.end_month, met.end_day = 2020.0, 12.0, 31.0
    met.surface_station_id, met.upper_air_station_id, met.data_start_year = 14735.0, 14735.0, 1988.0
    record = s.start_run(working_dir=tmp_path, runner=_StubRunner(s, exc=FileNotFoundError("x")))
    deck = record.deck_path.read_text(encoding="utf-8")
    assert re.search(r"^\s*STARTEND\s+2020\s+1\s+1\s+2020\s+12\s+31\s*$", deck, re.M)
    assert re.search(r"^\s*SURFDATA\s+14735\s+1988\s*$", deck, re.M)
    assert met.start_year == 2020.0          # the session's own project is not replaced


def test_a_decoder_bug_while_opening_is_logged_with_its_traceback(monkeypatch, caplog):
    import pyaermod.gui_v2.session as session_module

    def bug(data, *, origin):
        raise TypeError("unhashable type: 'dict'")

    monkeypatch.setattr(session_module, "project_from_json", bug)
    s = Session()
    with caplog.at_level(logging.WARNING, logger="pyaermod.gui_v2.session"), \
            pytest.raises(ProjectFileError, match=r"^bad\.json: unhashable type: 'dict'$"):
        s.open_json(b"{}", name="bad.json")
    [logged] = caplog.records
    assert logged.levelno == logging.ERROR
    assert logged.getMessage() == "Reading project file bad.json raised"
    assert "TypeError" in (logged.exc_text or "")


def test_a_file_the_user_can_fix_is_refused_without_a_log_record(caplog):
    s = Session()
    with caplog.at_level(logging.DEBUG, logger="pyaermod.gui_v2.session"), \
            pytest.raises(ProjectFileError, match=r"^bad\.json: not valid JSON"):
        s.open_json(b"{nope", name="bad.json")
    assert caplog.records == []


def test_start_run_uses_a_temp_dir_when_none_given(tmp_path, monkeypatch):
    from pyaermod.runner import AERMODRunResult
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", None)          # re-read TMPDIR
    s = Session()
    for blank in (None, "   "):
        record = s.start_run(working_dir=blank, runner=_StubRunner(
            s, result=AERMODRunResult(success=False, input_file="x")))
        assert record.work_dir.parent == tmp_path
        assert record.work_dir.name.startswith("pyaermod_")
    assert [r.number for r in s.runs] == [1, 2]


def test_cancel_run_without_run_returns_false():
    assert Session().cancel_run() is False


# ---------------------------------------------------------------------
# Background runs (WP-G4)
# ---------------------------------------------------------------------

ALBANY_SFC = str(REPO / "tests" / "fixtures" / "epa_official" / "AERMET2.SFC")


class _Loop:
    """A stand-in for the GUI's event loop: callbacks queue until pumped."""

    def __init__(self) -> None:
        self.queue: list = []
        self.lock = threading.Lock()

    def __call__(self, callback) -> None:           # Session.dispatch
        with self.lock:
            self.queue.append(callback)

    def pump(self) -> int:
        with self.lock:
            callbacks, self.queue = self.queue, []
        for callback in callbacks:
            callback()
        return len(callbacks)

    def run_until(self, done, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while not done():
            assert time.monotonic() < deadline, "timed out"
            self.pump()
            time.sleep(0.01)


@pytest.fixture
def albany_fake(tmp_path, monkeypatch):
    """A session holding the E480 scenario, a fake AERMOD replaying it, and a loop."""
    from pyaermod.runner import AERMODRunner

    exe = install_fake_aermod(tmp_path / "bin")
    monkeypatch.setenv("PYAERMOD_E2E_RECORDING", str(RECORDINGS / "albany_e480"))
    monkeypatch.delenv("PYAERMOD_E2E_DELAY", raising=False)
    monkeypatch.delenv("PYAERMOD_E2E_FAKE_LOG", raising=False)
    s = Session(_albany_project(["1", "ANNUAL"], ALBANY_SFC))
    loop = _Loop()
    s.dispatch = loop
    return s, loop, AERMODRunner(executable_path=exe, log_level="WARNING"), tmp_path / "run"


@posix_only
def test_a_background_run_reports_progress_on_the_owners_thread(albany_fake):
    s, loop, runner, work = albany_fake
    rec = Recorder(s)
    record = s.start_run(working_dir=work, runner=runner, background=True)
    assert record is s.run_in_progress and record.in_progress and record.status == "Running"
    assert record.expected_days == 4                    # AERMET2.SFC: 1 to 4 March 1988
    assert rec.events == [E.RUN_STARTED]                # the rest waits for the loop
    loop.run_until(lambda: s.run_in_progress is None)
    events = rec.events
    assert events[0] is E.RUN_STARTED and events[-1] is E.RUN_FINISHED
    progress = [c.run.progress for c in rec.changes if c.event is E.RUN_PROGRESS]
    assert progress and all(p is not None for p in progress)
    days = [p.days_processed for p in progress]
    assert days == sorted(days)                          # bursts are coalesced, never reordered
    [finished] = s.runs
    assert finished.status == "Failed" and "E480" in [m.code for m in finished.result.messages]
    assert finished.progress.stage == "output" and finished.progress.day == 64
    assert finished.fraction_done == 1.0
    assert s.last_completed_run is finished


@posix_only
def test_a_burst_of_progress_is_one_event(albany_fake):
    s, loop, runner, work = albany_fake
    rec = Recorder(s)
    s.start_run(working_dir=work, runner=runner, background=True)
    handle = s._run_handle
    handle.wait(30)                                      # every line arrived; nothing pumped
    loop.run_until(lambda: s.run_in_progress is None)
    assert rec.events == [E.RUN_STARTED, E.RUN_PROGRESS, E.RUN_FINISHED]
    assert rec.changes[1].run.progress.stage == "output"


@posix_only
def test_a_second_run_while_one_runs_is_refused(albany_fake, monkeypatch):
    s, loop, runner, work = albany_fake
    monkeypatch.setenv("PYAERMOD_E2E_DELAY", "0.2")
    s.start_run(working_dir=work, runner=runner, background=True)
    rec = Recorder(s)
    with pytest.raises(RunInProgressError, match="already running"):
        s.start_run(working_dir=work, runner=runner, background=True)
    assert rec.events == []
    assert s.cancel_run() is True
    loop.run_until(lambda: s.run_in_progress is None)


@posix_only
def test_cancel_run_stops_aermod_and_records_a_cancelled_run(albany_fake, monkeypatch):
    s, loop, runner, work = albany_fake
    monkeypatch.setenv("PYAERMOD_E2E_DELAY", "0.5")
    s.start_run(working_dir=work, runner=runner, background=True)
    loop.run_until(lambda: s.run_in_progress.progress is not None)
    pid = s._run_handle.pid
    assert s.cancel_run() is True
    assert s.cancel_run() is False                       # already asked
    loop.run_until(lambda: s.run_in_progress is None)
    [record] = s.runs
    assert record.status == "Cancelled" and record.cancelled and not record.success
    assert s.last_run is record and s.last_completed_run is None
    from tests.e2e.harness import process_running
    assert not process_running(pid)
    assert s.cancel_run() is False


@posix_only
def test_new_during_a_run_stops_it_and_forgets_it(albany_fake, monkeypatch):
    s, loop, runner, work = albany_fake
    monkeypatch.setenv("PYAERMOD_E2E_DELAY", "0.5")
    s.start_run(working_dir=work, runner=runner, background=True)
    handle = s._run_handle
    rec = Recorder(s)
    s.new()
    assert s.run_in_progress is None and s.runs == []
    assert handle.cancel_requested
    handle.wait(20)
    loop.pump()
    assert s.runs == [] and E.RUN_FINISHED not in rec.events
    # The next run is recorded as usual.
    s2_record = s.start_run(working_dir=work, runner=_StubRunner(
        s, exc=FileNotFoundError("no aermod")))
    assert s.runs == [s2_record]


def test_a_runner_that_cannot_start_in_the_background_finishes_at_once(tmp_path):
    class _Broken:
        def start(self, **kwargs):
            raise FileNotFoundError("no aermod")

    s = Session()
    rec = Recorder(s)
    record = s.start_run(working_dir=tmp_path, runner=_Broken(), background=True)
    assert record.status == "Failed" and record.error == "no aermod"
    assert s.run_in_progress is None and s.runs == [record]
    assert rec.events == [E.RUN_STARTED, E.RUN_FINISHED]


def test_a_synchronous_run_cannot_be_cancelled(tmp_path):
    assert Session().cancel_run() is False


def test_record_status_and_fraction():
    from datetime import datetime

    from pyaermod.runner import AERMODProgress, AERMODRunResult

    base = RunRecord(number=1, work_dir=Path("w"), deck_path=Path("w/d.inp"),
                     started_at=datetime(2026, 1, 1), expected_days=4)
    assert base.status == "Running" and base.fraction_done is None
    half = replace(base, progress=AERMODProgress(stage="day", day=62, year=1988,
                                                 days_processed=2))
    assert half.fraction_done == 0.5
    done = replace(half, finished_at=datetime(2026, 1, 1, 0, 1))
    assert replace(done, result=AERMODRunResult(success=True, input_file="x")).status == "Succeeded"
    assert replace(done, result=AERMODRunResult(success=False, input_file="x",
                                                cancelled=True)).status == "Cancelled"
    assert replace(done, error="boom").status == "Failed"
    assert replace(base, expected_days=None, progress=half.progress).fraction_done is None


def test_deck_text_is_the_deck_start_run_writes(tmp_path):
    s = Session(_albany_project(["1", "ANNUAL"], "AERMET2.SFC"))
    record = s.start_run(working_dir=tmp_path, runner=_StubRunner(s, exc=FileNotFoundError("x")))
    assert record.deck_path.read_text(encoding="utf-8") == s.deck_text()
    s.project.meteorology.start_year = 12.5
    with pytest.raises(DeckError, match="start_year must be a whole number"):
        s.deck_text()


def test_met_period_reads_and_caches_the_surface_file(tmp_path, monkeypatch):
    from pyaermod import aermet

    s = Session(_albany_project(["1", "ANNUAL"], ALBANY_SFC))
    path, period, problem = s.met_period()
    assert path == Path(ALBANY_SFC) and problem is None and period.days == 4
    calls = []
    monkeypatch.setattr(aermet, "read_surface_period", lambda p: calls.append(p))
    assert s.met_period()[1] == period and calls == []   # cached by mtime
    s.project.meteorology.surface_file = "AERMET2.SFC"         # relative: the same file
    assert s.met_period(REPO / "tests" / "fixtures" / "epa_official")[1] == period
    monkeypatch.undo()
    s.project.meteorology.surface_file = "missing.sfc"
    assert s.met_period(tmp_path) == (tmp_path / "missing.sfc", None,
                                      f"{tmp_path / 'missing.sfc'} does not exist")
    s.project.meteorology.surface_file = str(tmp_path)
    assert "is a directory" in s.met_period()[2]
    s.project.meteorology.surface_file = ""
    assert s.met_period() == (None, None, None)


# ---------------------------------------------------------------------
# Fork and imports
# ---------------------------------------------------------------------

def test_fork_is_deep_keeps_runs_and_drops_observers(tmp_path):
    s = Session(tab_id="A")
    key = s.add_source(_point("ORIG"))
    s.file_name, s.project_path = "f.json", tmp_path / "f.json"
    s.runs.append(_finished_record(s, tmp_path))
    s.run_options.working_dir = "/w"
    s.validate()
    seen = []
    s.subscribe(list(SessionEvent), seen.append)
    seen.clear()

    f = s.fork("B")
    assert f.tab_id == "B" and s.tab_id == "A"
    assert f.project is not s.project
    assert f.project.sources.sources[0] is not s.project.sources.sources[0]
    assert (f.file_name, f.project_path, f.dirty) == ("f.json", tmp_path / "f.json", True)
    assert f.runs == s.runs and f.runs is not s.runs
    assert f.validation is s.validation
    assert f.run_options == s.run_options and f.run_options is not s.run_options
    assert f.run_in_progress is None and f._keys == {}

    f.add_source(_point("FORKED"))
    f.set_control(title_one="fork")
    assert seen == []                           # the original's observers stay behind
    assert [x.source_id for x in s.project.sources.sources] == ["ORIG"]
    assert s.project.control.title_one == "Untitled run"
    assert s.delete_source(key) is not None


def test_fork_of_a_subclass_is_the_subclass():
    class Tracked(Session):
        pass

    assert type(Tracked().fork("x")) is Tracked


def _imports_run_at_import_time(path: Path, package: str):
    """Module names ``path`` imports when it is imported.

    Skips function bodies and ``if TYPE_CHECKING:`` blocks, which do not
    run at import time; resolves relative imports against ``package``.
    """
    import ast

    def walk(nodes):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
                yield from walk(node.orelse)
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                    module = f"{base}.{node.module}" if node.module else base
                else:
                    module = node.module
                yield module
                for alias in node.names:        # "from . import x" may name a submodule
                    yield f"{module}.{alias.name}"
            yield from walk(ast.iter_child_nodes(node))

    yield from walk(ast.parse(path.read_text(encoding="utf-8")).body)


def _pyaermod_file(module: str):
    """The source file of pyaermod module ``module``, or None if it is not one."""
    if module != "pyaermod" and not module.startswith("pyaermod."):
        return None
    base = REPO / "src" / Path(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def test_session_module_does_not_import_nicegui():
    """Importing the session (and what it imports) never imports NiceGUI.

    Read from the source rather than by importing in a fresh interpreter,
    which takes most of a minute on a loaded machine.
    """
    start = ["pyaermod", "pyaermod.gui_v2", "pyaermod.gui_v2.session"]
    todo, seen, imported = list(start), set(), set()
    while todo:
        module = todo.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _pyaermod_file(module)
        if path is None:
            continue
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for name in _imports_run_at_import_time(path, package):
            imported.add(name)
            todo.append(name)
    assert "pyaermod.gui_v2.project_io" in seen            # the scan follows imports
    assert "pandas" in imported                              # and sees third-party ones
    assert not [m for m in imported if m == "nicegui" or m.startswith("nicegui.")]


@pytest.mark.slow
def test_session_module_does_not_import_nicegui_in_a_fresh_interpreter():
    code = ("import sys; import pyaermod.gui_v2.session; "
            "print('nicegui' in sys.modules)")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(REPO / "src")] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env, check=True, timeout=600)
    assert out.stdout.strip() == "False"


# ---------------------------------------------------------------------
# Ported from the AppState tests (tests/test_gui_v2_state.py before WP-G2)
# ---------------------------------------------------------------------

class TestPortedFromAppState:
    def test_starts_clean(self):
        s = Session()
        assert s.project is not None and s.project_path is None and s.dirty is False

    def test_dirty_clean_round_trip(self):
        s = Session()
        s.mark_edited("output")
        assert s.dirty is True
        s.save_as_download("x.json")
        assert s.dirty is False

    def test_new_drops_path_and_dirty(self):
        s = Session()
        s.project_path, s.file_name = Path("/somewhere/foo.json"), "foo.json"
        s.mark_edited("control")
        s.new()
        assert s.project_path is None and s.dirty is False
        assert s.project.control.title_one == "Untitled run"

    def test_title_untitled_when_no_file(self):
        assert "Untitled" in Session().title

    def test_last_run_default_none(self):
        assert Session().last_run is None

    def test_key_prefixes_tell_sources_from_receptors(self):
        s = Session()
        assert s.add_source(VolumeSource(source_id="V", x_coord=0.0, y_coord=0.0)).startswith("s")
        assert s.add_receptor(PolarGrid()).startswith("r")

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
import subprocess
import sys
from pathlib import Path

import pytest

from pyaermod.gui_v2.project_io import load_project, project_to_json, save_project
from pyaermod.gui_v2.session import (
    DECK_NAME,
    Change,
    DeckError,
    ProjectFileError,
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
        with pytest.raises(NotImplementedError, match="WP-G4"):
            self.session.cancel_run()
        if self.exc is not None:
            raise self.exc
        return self.result


def test_start_run_is_in_progress_during_the_run_and_cancel_is_not_yet_supported(tmp_path):
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

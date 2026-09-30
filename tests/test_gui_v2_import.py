"""Tier T0 tests for deck import and the recent-files list (WP-G6).

:meth:`Session.import_inp` and the UI-free half of
:mod:`pyaermod.gui_v2.files`: no NiceGUI here. Each import is checked as
what the project holds afterwards plus the change events it emitted.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path

import pytest

from pyaermod.gui_v2 import files
from pyaermod.gui_v2.session import (
    DeckImportError,
    Session,
    SessionEvent,
)
from pyaermod.input_reader import read_aermod_input

REPO = Path(__file__).resolve().parent.parent
EPA = REPO / "tests" / "fixtures" / "epa_official"
AERTEST = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings" / "aertest" / "aertest.inp"

#: EPA's archive layout: aertest.inp reads ../meteorology/aermet2.sfc.
ARCHIVE_MET = {"aermet2.sfc": EPA / "AERMET2.SFC", "aermet2.pfl": EPA / "AERMET2.PFL"}


def _recorder(session: Session) -> list:
    events: list = []
    session.subscribe(set(SessionEvent), lambda c: events.append(c.event))
    return events


def _archive(tmp_path: Path) -> Path:
    """aertest.inp in EPA's archive layout, with its met files beside it."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "meteorology").mkdir()
    deck = tmp_path / "inputs" / "aertest.inp"
    shutil.copy(EPA / "aertest.inp", deck)
    for name, src in ARCHIVE_MET.items():
        shutil.copy(src, tmp_path / "meteorology" / name)
    return deck


def _with_houremis(folder: Path) -> Path:
    """The recorded aertest deck reading hourly emissions from hourly.emi.

    SO HOUREMIS has no field in PyAERMOD: the line is kept as written, at
    line 52 of this deck.
    """
    text = AERTEST.read_text(encoding="utf-8").replace(
        "SO FINISHED", "   HOUREMIS  hourly.emi  STACK1\nSO FINISHED", 1)
    deck = folder / "hourly.inp"
    deck.write_text(text, encoding="utf-8")
    return deck


class TestUpload:
    def test_an_uploaded_deck_populates_the_project(self):
        session = Session()
        session.set_control(title_one="discarded")
        events = _recorder(session)
        report = session.import_inp(AERTEST.read_bytes(), name="aertest.inp")

        project = session.project
        assert [s.source_id for s in project.sources.sources] == ["STACK1"]
        assert [g.grid_name for g in project.receptors.polar_grids] == ["POL1"]
        assert project.control.title_one.startswith("A Simple Example Problem")
        assert project.control.averaging_periods == ["1", "3", "8", "24", "PERIOD"]
        assert events == [SessionEvent.PROJECT_REPLACED, SessionEvent.DIRTY_CHANGED]
        # Nothing is saved yet: the header names the deck and says so.
        assert session.dirty is True
        assert session.project_path is None and session.file_name is None
        assert session.title == "PyAERMOD — aertest.inp (modified)"
        assert session.suggested_file_name() == "aertest.json"
        assert session.last_import is report and session.show_import_notice

    def test_the_report_lists_kept_lines_and_the_met_files_to_supply(self):
        session = Session()
        report = session.import_inp(AERTEST.read_bytes(), name="aertest.inp")
        assert report.name == "aertest.inp" and report.path is None
        assert [(u.pathway, u.keyword) for u in report.unparsed] == [
            ("CO", "ERRORFIL"), ("SO", "ELEVUNIT"), ("ME", "SITEDATA")]
        assert report.met_found == ()
        assert report.met_needed == (("surface_file", "AERMET2.SFC"),
                                     ("profile_file", "AERMET2.PFL"))

    def test_the_project_is_what_the_library_reads(self):
        session = Session()
        session.import_inp(AERTEST.read_text(encoding="utf-8"), name="aertest.inp")
        expected = read_aermod_input(AERTEST).to_aermod_input(validate=False)
        assert session.project.to_aermod_input(validate=False) == expected

    def test_a_deck_naming_files_outside_its_folder_is_refused_with_every_path(self):
        session = Session()
        session.set_control(title_one="kept")
        events = _recorder(session)
        with pytest.raises(DeckImportError) as caught:
            session.import_inp((EPA / "aertest.inp").read_bytes(), name="aertest.inp")
        message = str(caught.value)
        assert message.startswith(
            "aertest.inp: an uploaded deck may only name files in its own folder")
        for path in ("../meteorology/aermet2.sfc", "../meteorology/aermet2.pfl",
                     "../plotfiles/AERTEST_01H.PLT", "../postfiles/AERTEST_01H.PST"):
            assert path in message
        assert "Import it from its path on this computer instead" in message
        # Nothing changed.
        assert events == []
        assert session.project.control.title_one == "kept"
        assert session.last_import is None

    def test_a_kept_line_naming_a_file_outside_is_refused(self):
        text = AERTEST.read_text(encoding="utf-8").replace(
            "ERRORFIL  AERTEST_ERRORS.OUT", "ERRORFIL  /tmp/elsewhere/errors.out")
        session = Session()
        with pytest.raises(DeckImportError) as caught:
            session.import_inp(text, name="aertest.inp")
        assert ("names /tmp/elsewhere/errors.out (CO ERRORFIL at line 14)"
                in str(caught.value))
        assert session.last_import is None

    def test_the_files_it_reads_are_to_be_supplied(self, tmp_path):
        deck = _with_houremis(tmp_path)
        report = Session().import_inp(deck.read_bytes(), name=deck.name)
        assert report.inputs_found == ()
        assert report.inputs_missing == (("SO HOUREMIS at line 52", "hourly.emi"),)

    def test_a_long_name_is_shortened_for_the_header(self):
        name = "a" * 300 + ".inp"
        session = Session()
        report = session.import_inp(AERTEST.read_bytes(), name=name)
        assert len(report.name) == 120
        assert report.name == "a" * 113 + "....inp"
        assert session.title == f"PyAERMOD — {report.name} (modified)"
        assert [s.source_id for s in session.project.sources.sources] == ["STACK1"]

    def test_a_deck_that_cannot_be_stored_is_refused(self, monkeypatch):
        def full(self, data):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(Path, "write_bytes", full)
        session = Session()
        with pytest.raises(DeckImportError,
                           match=r"^aertest\.inp: could not be stored for reading: "
                                 r"No space left on device$"):
            session.import_inp(AERTEST.read_bytes(), name="aertest.inp")
        assert session.last_import is None

    @pytest.mark.parametrize("data, reason", [
        (b"\xff\xfe\x00C", "not a UTF-8 text file"),
        (b"shopping list\n", "not an AERMOD deck PyAERMOD can read: "
                             "line 1: content outside any pathway block: 'shopping list'"),
        (b"CO STARTING\nCO FINISHED\n", "not an AERMOD deck PyAERMOD can read: "
                                         "AERMOD input is missing required pathway SO"),
    ], ids=["undecodable", "not-a-deck", "no-sources"])
    def test_a_file_that_is_not_a_deck_is_refused_by_name(self, data, reason):
        session = Session()
        with pytest.raises(DeckImportError, match=f"^notes.txt: {re.escape(reason)}$"):
            session.import_inp(data, name="notes.txt")
        assert session.last_import is None and not session.dirty

    @pytest.mark.parametrize("name, cleaned", [
        ("../../elsewhere/aertest.inp", "aertest.inp"),
        ("C:\\decks\\aertest.inp", "aertest.inp"),
        ('what?.inp', "what_.inp"),
        ("", "deck.inp"),
        (None, "deck.inp"),
    ])
    def test_an_upload_is_read_under_its_bare_name(self, name, cleaned):
        report = Session().import_inp(AERTEST.read_bytes(), name=name)
        assert report.name == cleaned

    def test_a_reader_bug_is_logged_and_reported(self, monkeypatch, caplog):
        import pyaermod.input_reader as reader

        def broken(*_a, **_k):
            raise KeyError("oops")

        monkeypatch.setattr(reader, "read_aermod_input", broken)
        with caplog.at_level(logging.ERROR), pytest.raises(
                DeckImportError, match=r"^x.inp: could not be read \(KeyError: 'oops'\)$"):
            Session().import_inp(b"CO STARTING", name="x.inp")
        assert "Reading deck x.inp raised" in caplog.text


class TestPath:
    def test_met_files_beside_the_deck_come_along(self, tmp_path):
        deck = _archive(tmp_path)
        session = Session()
        report = session.import_inp(deck)
        met = session.project.meteorology
        assert Path(met.surface_file) == (tmp_path / "meteorology" / "aermet2.sfc")
        assert Path(met.profile_file) == (tmp_path / "meteorology" / "aermet2.pfl")
        assert Path(met.surface_file).is_absolute()
        assert report.path == deck
        assert report.met_found == ("surface_file", "profile_file")
        assert report.met_needed == ()
        # Output paths stay as the deck wrote them.
        assert session.project.output.plot_file == "../plotfiles/AERTEST_01H.PLT"

    def test_met_files_not_beside_the_deck_are_to_be_supplied(self):
        report = Session().import_inp(EPA / "aertest.inp")
        assert report.met_found == ()
        assert report.met_needed == (("surface_file", "../meteorology/aermet2.sfc"),
                                     ("profile_file", "../meteorology/aermet2.pfl"))

    def test_an_absolute_met_file_that_exists_is_not_asked_for(self, tmp_path):
        text = AERTEST.read_text(encoding="utf-8").replace(
            "AERMET2.SFC", str(EPA / "AERMET2.SFC"))
        deck = tmp_path / "abs.inp"
        deck.write_text(text, encoding="utf-8")
        report = Session().import_inp(deck)
        assert report.met_found == ()
        assert report.met_needed == (("profile_file", "AERMET2.PFL"),)

    def test_other_files_beside_the_deck_come_along(self, tmp_path):
        deck = _with_houremis(tmp_path)
        (tmp_path / "hourly.emi").write_text("x")
        session = Session()
        report = session.import_inp(deck)
        assert report.inputs_found == (("SO HOUREMIS at line 52", "hourly.emi"),)
        assert report.inputs_missing == ()
        assert (f"HOUREMIS  {tmp_path / 'hourly.emi'}  STACK1"
                in session.project.to_aermod_input(validate=False))

    def test_other_files_not_beside_the_deck_are_named(self, tmp_path):
        report = Session().import_inp(_with_houremis(tmp_path))
        assert report.inputs_found == ()
        assert report.inputs_missing == (("SO HOUREMIS at line 52", "hourly.emi"),)

    def test_a_missing_file_is_refused(self, tmp_path):
        session = Session()
        with pytest.raises(DeckImportError, match=r"^gone\.inp: No such file"):
            session.import_inp(tmp_path / "gone.inp")
        assert session.last_import is None

    @pytest.mark.parametrize("deck", sorted(EPA.glob("*.inp")), ids=lambda p: p.name)
    def test_every_epa_deck_imports_from_its_path(self, deck):
        session = Session()
        report = session.import_inp(deck)
        expected = read_aermod_input(deck)
        assert ([s.source_id for s in session.project.sources.sources]
                == [s.source_id for s in expected.sources.sources])
        assert len(report.unparsed) == len(expected.unparsed_lines)


class TestSessionLifecycle:
    def test_new_and_open_forget_the_import(self, tmp_path):
        session = Session()
        session.import_inp(AERTEST.read_bytes(), name="aertest.inp")
        session.new()
        assert session.last_import is None and not session.show_import_notice
        assert session.title == "PyAERMOD — Untitled"
        assert session.suggested_file_name() == "project.json"

    def test_saving_names_the_project_after_itself(self, tmp_path):
        session = Session()
        session.import_inp(AERTEST.read_bytes(), name="aertest.inp")
        data = session.save_as_download(session.suggested_file_name())
        assert session.title == "PyAERMOD — aertest.json"
        reopened = Session()
        reopened.open_json(data, name="aertest.json")
        assert (reopened.project.to_aermod_input(validate=False)
                == session.project.to_aermod_input(validate=False))

    def test_a_fork_keeps_the_notice(self):
        session = Session()
        session.import_inp(AERTEST.read_bytes(), name="aertest.inp")
        session.show_import_notice = False
        other = session.fork("tab-2")
        assert other.last_import is session.last_import
        assert other.show_import_notice is False
        assert other.title == session.title


class TestFileProblem:
    def test_cases(self, tmp_path):
        existing = tmp_path / "a.sfc"
        existing.write_text("x")
        assert files.file_problem("") is None
        assert files.file_problem(None) is None
        assert files.file_problem(str(existing)) is None
        assert files.file_problem(f"  {existing}  ") is None
        assert files.file_problem("a.sfc").startswith("Give the full path")
        assert files.file_problem(str(tmp_path / "b.sfc")) == "No such file on this computer"
        assert files.file_problem(str(tmp_path)) == "This is a folder, not a file"

    def test_home_is_expanded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "met.sfc").write_text("x")
        assert files.file_problem("~/met.sfc") is None


class TestRecentFiles:
    @pytest.fixture(autouse=True)
    def _store(self, tmp_path, monkeypatch):
        self.store = tmp_path / "cfg" / "recent.json"
        monkeypatch.setenv(files.RECENT_FILES_ENV, str(self.store))

    def test_default_location_is_in_the_home_directory(self, monkeypatch, tmp_path):
        monkeypatch.delenv(files.RECENT_FILES_ENV)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert files.recent_files_path() == Path.home() / ".pyaermod" / "recent_files.json"

    def test_newest_first_without_duplicates_and_capped(self, tmp_path):
        paths = [tmp_path / f"p{i}.json" for i in range(files.MAX_RECENT + 2)]
        for p in paths:
            files.remember(p, files.PROJECT)
        files.remember(paths[3], files.PROJECT)
        listed = [e.path for e in files.load_recent()]
        assert listed[0] == paths[3]
        assert len(listed) == files.MAX_RECENT
        assert len(set(listed)) == len(listed)
        assert paths[0] not in listed and paths[1] not in listed

    def test_kind_and_relative_paths(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        files.remember(Path("deck.inp"), files.DECK)
        (entry,) = files.load_recent()
        assert entry.path == tmp_path / "deck.inp" and entry.kind == files.DECK
        assert entry.exists is False
        (tmp_path / "deck.inp").write_text("x")
        assert entry.exists is True
        with pytest.raises(ValueError, match="unknown kind"):
            files.remember(tmp_path / "x", "photo")

    def test_forget(self, tmp_path):
        files.remember(tmp_path / "a.json", files.PROJECT)
        files.remember(tmp_path / "b.inp", files.DECK)
        assert [e.path.name for e in files.forget(tmp_path / "a.json")] == ["b.inp"]
        assert [e.path.name for e in files.load_recent()] == ["b.inp"]

    @pytest.mark.parametrize("content", [
        "{not json", '["a"]', '{"files": "a"}',
        '{"files": [{"path": 3, "kind": "project"}, {"path": "/x", "kind": "movie"}]}',
    ])
    def test_an_unreadable_list_reads_as_empty(self, content):
        self.store.parent.mkdir(parents=True)
        self.store.write_text(content)
        assert files.load_recent() == []

    def test_a_list_that_cannot_be_written_is_only_a_warning(self, tmp_path, caplog,
                                                              monkeypatch):
        blocker = tmp_path / "blocker"
        blocker.write_text("a file where the folder should be")
        monkeypatch.setenv(files.RECENT_FILES_ENV, str(blocker / "recent.json"))
        with caplog.at_level(logging.WARNING):
            entries = files.remember(tmp_path / "a.json", files.PROJECT)
        assert [e.path.name for e in entries] == ["a.json"]
        assert "Could not update the recent-files list" in caplog.text

    def test_the_file_is_versioned_json(self, tmp_path):
        files.remember(tmp_path / "a.json", files.PROJECT)
        data = json.loads(self.store.read_text())
        assert data == {"version": 1, "files": [
            {"path": str(tmp_path / "a.json"), "kind": "project"}]}
        assert [p.name for p in self.store.parent.iterdir()] == ["recent.json"]


class TestNativeOpenDialog:
    class _Window:
        def __init__(self, result):
            self.result = result
            self.calls: list = []

        def create_file_dialog(self, kind, **kwargs):
            self.calls.append((kind, kwargs))
            return self.result

    @pytest.mark.parametrize("result, expected", [
        (("/data/a.inp",), Path("/data/a.inp")),
        ("/data/b.inp", Path("/data/b.inp")),
        ((), None),
        (None, None),
    ])
    def test_the_chosen_path_or_none(self, monkeypatch, result, expected):
        from pyaermod.gui_v2 import _native

        window = self._Window(result)
        monkeypatch.setattr(_native, "_WINDOW", window)
        assert files.ask_open_path(files.DECK_FILE_TYPES) == expected
        ((_kind, kwargs),) = window.calls
        assert kwargs == {"allow_multiple": False, "file_types": files.DECK_FILE_TYPES}

    def test_it_needs_the_desktop_window(self, monkeypatch):
        from pyaermod.gui_v2 import _native

        monkeypatch.setattr(_native, "_WINDOW", None)
        with pytest.raises(RuntimeError, match="pyaermod-desktop"):
            files.ask_open_path(files.DECK_FILE_TYPES)


@pytest.mark.slow
def test_files_module_does_not_import_nicegui_in_a_fresh_interpreter():
    import subprocess
    import sys

    code = ("import sys; import pyaermod.gui_v2.files; "
            "print('nicegui' in sys.modules)")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(REPO / "src")] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env, check=True, timeout=600)
    assert out.stdout.strip() == "False"

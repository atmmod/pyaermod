"""Tier T1 tests for deck import, met file pickers and recent files (WP-G6).

The app shell runs in-process under ``nicegui.testing.User`` through the
``gui`` fixture of :mod:`tests.test_gui_v2_smoke`, and every test asserts
what the user sees: notifications, the import notice, table rows and
field values (PLAN-gui.md, "Rules for every GUI test"). Uploads are sent
through the Import control's own uploader, as the browser sends them.

The acceptance test of WP-G6 is :func:`test_every_epa_deck_uploads_or_says_why_not`:
every deck in ``tests/fixtures/epa_official/`` either populates the
project or shows a clear notice, with no exception (the ``gui`` fixture
fails a test that leaves an ERROR record in the log).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

# As in tests/test_gui_v2_smoke.py, whose ``gui`` fixture this module uses:
# the in-process harness needs NiceGUI >= 3.4.
pytest.importorskip("nicegui", minversion="3.4.0")
pytest.importorskip(
    "nicegui.testing.user_simulation",
    reason="NiceGUI >=3.4.0 provides the user_simulation test harness",
)

from nicegui import ElementFilter, ui
from nicegui.elements.upload_files import SmallFileUpload
from nicegui.testing.user_interaction import UserInteraction

from pyaermod.gui_v2 import files
from pyaermod.input_reader import PathTraversalError, read_aermod_input

from . import test_gui_v2_smoke as smoke
from .test_gui_v2_smoke import (
    GuiSession,
    _click,
    _one,
    _receptors_table,
    _rows_become,
    _settle,
    _sources_table,
    _title_input,
    _value_becomes,
)

# The smoke module's fixtures and skip marker, used here by name.
gui = smoke.gui
_cheap_garbage_collection = smoke._cheap_garbage_collection
pytestmark = smoke.pytestmark

REPO = Path(__file__).resolve().parent.parent
EPA = REPO / "tests" / "fixtures" / "epa_official"
EPA_DECKS = sorted(EPA.glob("*.inp"))
AERTEST = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings" / "aertest" / "aertest.inp"

BLANK_TITLE = "Untitled run"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

async def _upload_deck(gui: GuiSession, name: str, data: bytes) -> None:
    """Send ``data`` as the deck the user chose through Import deck..."""
    with gui.user:
        uploader = next(iter(ElementFilter(kind=ui.upload, marker="import-upload",
                                           local_scope=False)))
        await uploader.handle_uploads([SmallFileUpload(name, "text/plain", data)])
    for _ in range(5):
        await asyncio.sleep(0)


def _read_from_path(gui: GuiSession, path) -> None:
    field = _one(gui, kind=ui.input, content="Deck file path")
    UserInteraction(gui.user, {field}, None).clear().type(str(path))
    gui.user.find(kind=ui.button, content="Read deck").click()


def _expected_title(deck: Path) -> str:
    return read_aermod_input(deck).control.title_one


def _outside(deck: Path, tmp_path: Path):
    """The library's verdict on ``deck`` read from a folder of its own."""
    copy = tmp_path / "sandbox" / deck.name
    copy.parent.mkdir()
    shutil.copy(deck, copy)
    try:
        read_aermod_input(copy, sandbox=True)
    except PathTraversalError as exc:
        return exc.violations
    return None


def _source_ids(deck: Path) -> list:
    return [s.source_id for s in read_aermod_input(deck).sources.sources]


# ---------------------------------------------------------------------
# Acceptance: every EPA deck
# ---------------------------------------------------------------------

@pytest.mark.parametrize("deck", EPA_DECKS, ids=[d.name for d in EPA_DECKS])
@pytest.mark.asyncio
async def test_every_epa_deck_uploads_or_says_why_not(gui, deck, tmp_path):
    outside = _outside(deck, tmp_path)
    await gui.open()
    await _upload_deck(gui, deck.name, deck.read_bytes())
    if outside is None:
        await gui.user.should_see(f"Imported {deck.name}")
        await _rows_become(gui, _sources_table, "id", _source_ids(deck))
        await _value_becomes(lambda: _title_input(gui).value, _expected_title(deck))
        await gui.user.should_see(f"PyAERMOD — {deck.name} (modified)")
    else:
        # A clear notice: which deck, why, every path at fault, what to do.
        await gui.user.should_see(
            f"Import failed: {deck.name}: an uploaded deck may only name files in its own folder")
        for violation in outside:
            await gui.user.should_see(violation.path)
        await gui.user.should_see("Import it from its path on this computer instead")
        await _settle(gui)
        assert _title_input(gui).value == BLANK_TITLE
        assert _sources_table(gui).rows == []
        await gui.user.should_see("PyAERMOD — Untitled")


# Every EPA deck is read from its path by the T0 test of the same name in
# tests/test_gui_v2_import.py; here two stand for them in the GUI: the deck
# J5 imports, with several kept lines, and one with a single kept line.
PATH_DECKS = [EPA / "aertest.inp", EPA / "olmgrp.inp"]


@pytest.mark.parametrize("deck", PATH_DECKS, ids=[d.name for d in PATH_DECKS])
@pytest.mark.asyncio
async def test_an_epa_deck_imports_from_its_path(gui, deck):
    await gui.open()
    _read_from_path(gui, deck)
    await gui.user.should_see(f"Imported {deck.name}")
    await _rows_become(gui, _sources_table, "id", _source_ids(deck))
    await _value_becomes(lambda: _title_input(gui).value, _expected_title(deck))
    expected = read_aermod_input(deck)
    await gui.user.should_see(f"Imported {deck.name} from {deck.parent}.")
    if expected.unparsed_lines:
        count = len(expected.unparsed_lines)
        await gui.user.should_see(f"{count} line{'s' if count != 1 else ''} of the deck")
        first = expected.unparsed_lines[0]
        await gui.user.should_see(f"{first.pathway} {first.keyword}: ")


# ---------------------------------------------------------------------
# The import notice and the met file pickers
# ---------------------------------------------------------------------

class TestImportNotice:
    @pytest.mark.asyncio
    async def test_upload_lists_kept_lines_and_asks_for_the_met_files(self, gui):
        await gui.open()
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see("Imported aertest.inp")
        await gui.user.should_see(kind=ui.card, marker="import-notice")
        await gui.user.should_see("3 lines of the deck have no field in PyAERMOD")
        for summary in ("CO ERRORFIL: 1 line", "SO ELEVUNIT: 1 line", "ME SITEDATA: 1 line"):
            await gui.user.should_see(summary)
        await gui.user.should_see("line 14: ERRORFIL  AERTEST_ERRORS.OUT")
        await gui.user.should_see(
            "Choose the deck's met files. The deck names AERMET2.SFC (surface), "
            "AERMET2.PFL (profile). An uploaded deck brings no met files.")
        surface = _one(gui, kind=ui.input, content="Surface met file (full path)")
        profile = _one(gui, kind=ui.input, content="Profile met file (full path)")
        assert (surface.value, profile.value) == ("AERMET2.SFC", "AERMET2.PFL")
        assert surface.error and surface.error.startswith("Give the full path")
        await _rows_become(gui, _receptors_table, "label", ["POL1"])

    @pytest.mark.asyncio
    async def test_choosing_a_met_file_checks_it_and_reaches_the_meteorology_step(self, gui,
                                                                                  tmp_path):
        await gui.open()
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see("Imported aertest.inp")
        surface = _one(gui, kind=ui.input, content="Surface met file (full path)")
        UserInteraction(gui.user, {surface}, None).clear().type(str(tmp_path / "nope.sfc"))
        await _value_becomes(lambda: surface.error, "No such file on this computer")
        sfc = EPA / "AERMET2.SFC"
        UserInteraction(gui.user, {surface}, None).clear().type(str(sfc))
        await _value_becomes(lambda: surface.error, None)
        # The Meteorology step shows the same file.
        await _value_becomes(lambda: _one(gui, kind=ui.input, content="surface file").value,
                             str(sfc))
        assert gui.session.project.meteorology.surface_file == str(sfc)
        await gui.user.should_see("PyAERMOD — aertest.inp (modified)")

    @pytest.mark.asyncio
    async def test_met_files_found_beside_the_deck_are_named(self, gui, tmp_path):
        (tmp_path / "inputs").mkdir()
        (tmp_path / "meteorology").mkdir()
        deck = tmp_path / "inputs" / "aertest.inp"
        shutil.copy(EPA / "aertest.inp", deck)
        shutil.copy(EPA / "AERMET2.SFC", tmp_path / "meteorology" / "aermet2.sfc")
        shutil.copy(EPA / "AERMET2.PFL", tmp_path / "meteorology" / "aermet2.pfl")
        await gui.open()
        _read_from_path(gui, deck)
        await gui.user.should_see("Found its surface, profile met files beside the deck.")
        await gui.user.should_not_see("Choose the deck's met files")
        await _value_becomes(lambda: _one(gui, kind=ui.input, content="surface file").value,
                             str(tmp_path / "meteorology" / "aermet2.sfc"))

    @pytest.mark.asyncio
    async def test_the_other_files_the_deck_reads_are_named(self, gui, tmp_path):
        text = AERTEST.read_text(encoding="utf-8").replace(
            "SO FINISHED", "   HOUREMIS  hourly.emi  STACK1\nSO FINISHED", 1)
        await gui.open()
        await _upload_deck(gui, "hourly.inp", text.encode("utf-8"))
        await gui.user.should_see(
            "The deck also reads files that are not on this computer as it names them: "
            "hourly.emi (SO HOUREMIS at line 52). An uploaded deck brings no files.")
        # Read from its path, with the file beside it, it brings the file along.
        deck = tmp_path / "hourly.inp"
        deck.write_text(text, encoding="utf-8")
        (tmp_path / "hourly.emi").write_text("x")
        _read_from_path(gui, deck)
        await gui.user.should_see(
            "Found the other files it reads beside the deck: hourly.emi (SO HOUREMIS at line 52).")
        await gui.user.should_not_see("The deck also reads files")

    @pytest.mark.asyncio
    async def test_dismiss_hides_the_notice_until_the_next_import(self, gui):
        await gui.open()
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see(kind=ui.card, marker="import-notice")
        gui.user.find(kind=ui.button, content="Dismiss").click()
        await gui.user.should_not_see(kind=ui.card, marker="import-notice")
        await gui.open()                              # a reload keeps it dismissed
        await _settle(gui)
        await gui.user.should_not_see(kind=ui.card, marker="import-notice")
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see(kind=ui.card, marker="import-notice")

    @pytest.mark.asyncio
    async def test_a_reload_keeps_the_notice_and_new_clears_it(self, gui):
        await gui.open()
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see(kind=ui.card, marker="import-notice")
        await gui.open()
        await gui.user.should_see(kind=ui.card, marker="import-notice")
        await gui.user.should_see("Imported aertest.inp.")
        gui.user.find(kind=ui.button, marker="project-new").click()
        await gui.user.should_not_see(kind=ui.card, marker="import-notice")
        await gui.user.should_see("PyAERMOD — Untitled")

    @pytest.mark.asyncio
    async def test_a_failed_import_keeps_the_project_and_its_changes(self, gui):
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Keep me")
        await _upload_deck(gui, "notes.txt", b"shopping list\n")
        await gui.user.should_see("Import failed: notes.txt: not an AERMOD deck PyAERMOD can read")
        assert _title_input(gui).value == "Keep me"
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        await gui.user.should_not_see(kind=ui.card, marker="import-notice")
        # The uploader was reset: a deck chosen next is sent.
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see("Imported aertest.inp")

    @pytest.mark.asyncio
    async def test_the_goto_link_names_the_meteorology_step(self, gui, monkeypatch):
        from pyaermod.gui_v2.pages import project as project_page

        visited: list = []
        original = files.import_controls
        monkeypatch.setattr(project_page.files, "import_controls",
                            lambda session, **kw: original(session, goto=visited.append,
                                                           dialogs=kw.get("dialogs")))
        await gui.open()
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        gui.user.find(kind=ui.button, content="Go to Meteorology").click()
        assert visited == ["meteorology"]

    @pytest.mark.asyncio
    async def test_without_goto_there_is_no_link(self, gui):
        await gui.open()
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see(kind=ui.card, marker="import-notice")
        await gui.user.should_not_see(kind=ui.button, content="Go to Meteorology")


class TestPathImport:
    @pytest.mark.asyncio
    async def test_a_path_that_is_not_a_file_is_refused_where_typed(self, gui, tmp_path):
        await gui.open()
        field = _one(gui, kind=ui.input, content="Deck file path")
        _read_from_path(gui, tmp_path / "gone.inp")
        await gui.user.should_see("Import failed: No such file on this computer")
        await _value_becomes(lambda: field.error, "No such file on this computer")
        assert _title_input(gui).value == BLANK_TITLE

    @pytest.mark.asyncio
    async def test_an_empty_path_asks_for_one(self, gui):
        await gui.open()
        gui.user.find(kind=ui.button, content="Read deck").click()
        await gui.user.should_see("Import failed: give the path of a deck")


# ---------------------------------------------------------------------
# Recent files
# ---------------------------------------------------------------------

class TestRecentFiles:
    @pytest.mark.asyncio
    async def test_no_list_until_a_file_is_opened_by_path(self, gui):
        await gui.open()
        await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
        await gui.user.should_see("Imported aertest.inp")
        await _settle(gui)
        await gui.user.should_not_see("Recent files")

    @pytest.mark.asyncio
    async def test_a_deck_read_from_its_path_is_listed_and_reopens(self, gui, tmp_path):
        deck = tmp_path / "aertest.inp"
        shutil.copy(AERTEST, deck)
        await gui.open()
        _read_from_path(gui, deck)
        await gui.user.should_see("Imported aertest.inp")
        await gui.user.should_see("Recent files")
        await gui.user.should_see(kind=ui.button, content="aertest.inp")
        await gui.user.should_see(f"AERMOD deck · {tmp_path}")
        gui.user.find(kind=ui.button, marker="project-new").click()
        await _rows_become(gui, _sources_table, "id", [])
        gui.user.find(kind=ui.button, content="aertest.inp").click()
        await _rows_become(gui, _sources_table, "id", ["STACK1"])

    @pytest.mark.asyncio
    async def test_decks_of_one_name_are_told_apart_by_their_folder(self, gui, tmp_path):
        first, second = tmp_path / "first" / "aertest.inp", tmp_path / "second" / "aertest.inp"
        for deck in (first, second):
            deck.parent.mkdir()
        shutil.copy(AERTEST, first)
        second.write_text(AERTEST.read_text(encoding="utf-8").replace(
            "A Simple Example Problem", "The second copy"), encoding="utf-8")
        await gui.open()
        for deck in (first, second):
            _read_from_path(gui, deck)
            await gui.user.should_see(f"Imported aertest.inp from {deck.parent}.")
        await gui.user.should_see(f"AERMOD deck · {first.parent}")
        buttons = {b.props.get("aria-label"): b for b in
                   gui.user.find(kind=ui.button, content="aertest.inp").elements}
        assert set(buttons) == {f"Reopen aertest.inp from {first.parent}",
                                f"Reopen aertest.inp from {second.parent}"}
        _click(gui, buttons[f"Reopen aertest.inp from {first.parent}"])
        await _value_becomes(lambda: _title_input(gui).value,
                             "A Simple Example Problem for the AERMOD Model with PRIME")

    @pytest.mark.asyncio
    async def test_a_project_saved_by_path_is_listed_and_reopens(self, gui, tmp_path,
                                                                 monkeypatch):
        from pyaermod.gui_v2 import _native
        chosen = tmp_path / "saved.json"
        monkeypatch.setattr(_native, "native_window", lambda: object())
        monkeypatch.setattr(_native, "ask_save_path", lambda name: chosen)
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Listed")
        gui.user.find(kind=ui.button, marker="project-save-as").click()
        await gui.user.should_see("Saved saved.json")
        await gui.user.should_see(kind=ui.button, content="saved.json")
        await gui.user.should_see(f"project · {tmp_path}")
        gui.user.find(kind=ui.button, marker="project-new").click()
        await _value_becomes(lambda: _title_input(gui).value, BLANK_TITLE)
        gui.user.find(kind=ui.button, content="saved.json").click()
        await gui.user.should_see("Loaded saved.json")
        await _value_becomes(lambda: _title_input(gui).value, "Listed")

    @pytest.mark.asyncio
    async def test_a_file_that_is_gone_is_said_so_and_dropped(self, gui, tmp_path):
        deck = tmp_path / "aertest.inp"
        shutil.copy(AERTEST, deck)
        files.remember(deck, files.DECK)
        deck.unlink()
        await gui.open()
        await gui.user.should_see(f"AERMOD deck, missing · {tmp_path}")
        gui.user.find(kind=ui.button, content="aertest.inp").click()
        await gui.user.should_see(f"aertest.inp is no longer at {tmp_path}")
        await gui.user.should_not_see("Recent files")
        assert files.load_recent() == []

    @pytest.mark.asyncio
    async def test_a_recent_project_that_no_longer_opens_is_reported(self, gui, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{not json")
        files.remember(broken, files.PROJECT)
        await gui.open()
        gui.user.find(kind=ui.button, content="broken.json").click()
        await gui.user.should_see("Load failed: ")
        assert _title_input(gui).value == BLANK_TITLE


# ---------------------------------------------------------------------
# Desktop mode: native dialogs
# ---------------------------------------------------------------------

class TestDesktop:
    @pytest.fixture(autouse=True)
    def _desktop(self, monkeypatch):
        from pyaermod.gui_v2 import _native
        monkeypatch.setattr(_native, "native_window", lambda: object())
        self.asked: list = []
        self.answers: list = []

        def ask(file_types):
            self.asked.append(tuple(file_types))
            return self.answers.pop(0) if self.answers else None

        monkeypatch.setattr(files, "ask_open_path", ask)

    @pytest.mark.asyncio
    async def test_import_opens_a_native_dialog_and_reads_the_chosen_deck(self, gui, tmp_path):
        deck = tmp_path / "aertest.inp"
        shutil.copy(AERTEST, deck)
        self.answers.append(deck)
        await gui.open()
        await gui.user.should_not_see(kind=ui.upload, marker="import-upload")
        gui.user.find(kind=ui.button, marker="import-deck").click()
        await gui.user.should_see("Imported aertest.inp")
        await _rows_become(gui, _sources_table, "id", ["STACK1"])
        assert self.asked == [files.DECK_FILE_TYPES]
        await gui.user.should_see(kind=ui.button, content="aertest.inp")   # recent

    @pytest.mark.asyncio
    async def test_cancelling_the_dialog_changes_nothing(self, gui):
        await gui.open()
        gui.user.find(kind=ui.button, marker="import-deck").click()
        await _settle(gui)
        assert self.asked == [files.DECK_FILE_TYPES]
        await gui.user.should_not_see("Imported")
        assert _title_input(gui).value == BLANK_TITLE

    @pytest.mark.asyncio
    async def test_browse_fills_a_met_file(self, gui):
        await gui.open()
        await _upload_deck_through_path(gui)
        sfc = EPA / "AERMET2.SFC"
        self.answers.append(sfc)
        gui.user.find(kind=ui.button, marker="browse-surface_file").click()
        surface = _one(gui, kind=ui.input, content="Surface met file (full path)")
        await _value_becomes(lambda: surface.value, str(sfc))
        await _value_becomes(lambda: surface.error, None)
        assert gui.session.project.meteorology.surface_file == str(sfc)
        assert self.asked[-1] == files.MET_FILE_TYPES["surface_file"]


async def _upload_deck_through_path(gui: GuiSession) -> None:
    """In desktop mode there is no uploader: import the recorded deck by path."""
    _read_from_path(gui, AERTEST)
    await gui.user.should_see("Imported aertest.inp")
    await gui.user.should_see(kind=ui.card, marker="import-notice")

"""G1: importing a deck or reopening a recent file must ask before it discards unsaved edits."""

from __future__ import annotations

import asyncio
import shutil

import pytest

pytest.importorskip("nicegui", minversion="3.4.0")

from nicegui import ui

from pyaermod.gui_v2 import files

from . import test_gui_v2_smoke as smoke
from .test_gui_v2_files import AERTEST, _read_from_path, _upload_deck
from .test_gui_v2_smoke import _open_dialogs, _settle, _title_input

gui = smoke.gui
pytestmark = smoke.pytestmark


async def _edit(gui):
    gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("My unsaved work")
    await _settle(gui)
    assert gui.session.dirty


async def _asked(gui) -> bool:
    for _ in range(30):
        if _open_dialogs(gui, "confirm-dialog"):
            return True
        await asyncio.sleep(0.01)
    return False


@pytest.mark.asyncio
async def test_reading_a_deck_by_path_asks_before_discarding_edits(gui, tmp_path):
    deck = tmp_path / "aertest.inp"
    shutil.copy(AERTEST, deck)
    await gui.open()
    await _edit(gui)
    _read_from_path(gui, deck)
    assert await _asked(gui), "no prompt: the unsaved project was replaced silently"
    assert _title_input(gui).value == "My unsaved work"


@pytest.mark.asyncio
async def test_uploading_a_deck_asks_before_discarding_edits(gui):
    await gui.open()
    await _edit(gui)
    await _upload_deck(gui, "aertest.inp", AERTEST.read_bytes())
    assert await _asked(gui), "no prompt: the unsaved project was replaced silently"
    assert gui.session.project.control.title_one == "My unsaved work"


@pytest.mark.asyncio
async def test_a_recent_file_asks_before_discarding_edits(gui, tmp_path):
    deck = tmp_path / "aertest.inp"
    shutil.copy(AERTEST, deck)
    files.remember(deck, files.DECK)
    await gui.open()
    await _edit(gui)
    gui.user.find(kind=ui.button, content="aertest.inp").click()
    assert await _asked(gui), "no prompt: the unsaved project was replaced silently"
    assert gui.session.project.control.title_one == "My unsaved work"

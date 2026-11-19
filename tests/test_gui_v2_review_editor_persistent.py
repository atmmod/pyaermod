"""G6: the source and receptor editors hold a draft; a stray click or Esc must not discard it.

NiceGUI's ``ui.dialog`` is dismissible by backdrop click and Esc unless the dialog carries
the ``persistent`` prop (dialog.py docstring, NiceGUI 4.0.0). The simulated user cannot
click a backdrop, so the test asserts the prop that decides it.
"""

import pytest

pytest.importorskip("nicegui", minversion="3.4.0")

from . import test_gui_v2_smoke as smoke
from .test_gui_v2_smoke import _add_receptor, _add_source, _dialog_opens, _open_dialogs

gui = smoke.gui
pytestmark = smoke.pytestmark


@pytest.mark.asyncio
async def test_the_source_editor_does_not_close_on_a_click_outside_or_esc(gui):
    await gui.open()
    _add_source(gui)
    await _dialog_opens(gui, "editor-dialog")
    (dialog,) = _open_dialogs(gui, "editor-dialog")
    assert "persistent" in dialog.props, "a click outside or Esc discards the draft silently"


@pytest.mark.asyncio
async def test_the_receptor_editor_does_not_close_on_a_click_outside_or_esc(gui):
    await gui.open()
    _add_receptor(gui)
    await _dialog_opens(gui, "editor-dialog")
    (dialog,) = _open_dialogs(gui, "editor-dialog")
    assert "persistent" in dialog.props, "a click outside or Esc discards the draft silently"

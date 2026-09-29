"""
The desktop window, for the pages that need native dialogs.

``pyaermod-desktop`` (:mod:`pyaermod.gui_v2.desktop`) runs the NiceGUI
server in a thread and opens its own pywebview window; it hands that
window to :func:`set_window`. The pages ask :func:`native_window` whether
they run inside it, and in that case use a native save dialog
(:func:`ask_save_path`) instead of a browser download.

This module is imported by the pages and by ``desktop.main`` alike and is
never an entry script, so both always see the same module object (the
PyInstaller bundle starts from ``packaging/desktop_entry.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

_WINDOW: Any = None

#: What the save dialog offers, in pywebview's "Description (*.ext)" form.
PROJECT_FILE_TYPES = ("PyAERMOD project (*.json)",)

# pywebview's value for a save dialog, for versions without FileDialog.
_SAVE_DIALOG_FALLBACK = 30


def set_window(window: Any) -> None:
    """Record the pywebview window the desktop app opened (None to forget it)."""
    global _WINDOW
    _WINDOW = window


def native_window() -> Any:
    """The desktop window, or None when the GUI runs in a browser."""
    return _WINDOW


def _save_dialog_kind() -> Any:
    try:
        import webview

        return webview.FileDialog.SAVE
    except (ImportError, AttributeError):
        return _SAVE_DIALOG_FALLBACK


def ask_save_path(suggested: str) -> Optional[Path]:
    """Ask where to save the project; None if the user cancelled.

    Blocks until the dialog closes, so call it through ``run.io_bound``.
    """
    window = _WINDOW
    if window is None:
        raise RuntimeError("no desktop window; ask_save_path is for pyaermod-desktop")
    result = window.create_file_dialog(
        _save_dialog_kind(), save_filename=suggested, file_types=PROJECT_FILE_TYPES,
    )
    # pywebview returns a tuple of paths; some backends return one string.
    if isinstance(result, (list, tuple)):
        result = result[0] if result else None
    return Path(result) if result else None


__all__ = ["PROJECT_FILE_TYPES", "ask_save_path", "native_window", "set_window"]

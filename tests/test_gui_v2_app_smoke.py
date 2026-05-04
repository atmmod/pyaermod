"""Smoke tests for the NiceGUI app shell.

These tests confirm that the app modules import cleanly and that the
``main`` / ``build_app`` symbols are reachable. They deliberately do
not start the NiceGUI server — that's exercised end-to-end during
manual testing and in v1.9-E's pywebview-bundle smoke job.

Pages are exercised via ``nicegui.testing`` in v1.9-B onward; for
v1.9-A we just check the import surface.
"""

from __future__ import annotations

import pytest


def test_main_entry_point_importable():
    from pyaermod.gui_v2 import main
    assert callable(main)


def test_build_app_importable():
    pytest.importorskip("nicegui")
    from pyaermod.gui_v2.app import build_and_run, build_app
    assert callable(build_app)
    assert callable(build_and_run)


def test_desktop_main_importable():
    from pyaermod.gui_v2.desktop import main as desktop_main
    assert callable(desktop_main)


def test_pages_have_render_callable():
    pytest.importorskip("nicegui")
    from pyaermod.gui_v2 import pages
    for name in (
        "project", "sources", "receptors", "meteorology",
        "output", "run", "results",
    ):
        mod = getattr(pages, name)
        assert callable(mod.render), f"pages.{name}.render is not callable"


def test_project_io_in_public_api():
    """Save/load are accessible without going through the GUI."""
    from pyaermod.gui_v2.project_io import load_project, save_project
    assert callable(save_project)
    assert callable(load_project)

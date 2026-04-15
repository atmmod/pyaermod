"""Import-only smoke tests for pyaermod.gui.

These complement tests/test_gui_apptest.py — the AppTest tests require
a working Streamlit + pyarrow stack that isn't guaranteed on every
local environment. The tests here only exercise the import surface so
gui.py picks up at least a little coverage in every test run.
"""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit")


def test_gui_module_imports():
    import pyaermod.gui


def test_page_functions_are_callables():
    """Each page render function must be callable."""
    import pyaermod.gui as gui
    for attr_name in (
        "page_project_setup", "page_source_editor", "page_receptor_editor",
        "page_meteorology", "page_run_aermod", "page_results_viewer",
        "page_export",
    ):
        assert callable(getattr(gui, attr_name)), f"gui.{attr_name} not callable"


def test_app_entry_points_exist():
    import pyaermod.gui as gui
    assert callable(gui.main)
    assert callable(gui._app)


def test_session_state_manager_initializes_shape():
    import pyaermod.gui as gui
    assert hasattr(gui, "SessionStateManager")
    assert callable(gui.SessionStateManager.initialize)


def test_source_form_factory_exposes_all_types():
    import pyaermod.gui as gui
    ffc = gui.SourceFormFactory
    assert hasattr(ffc, "SOURCE_TYPES")
    assert len(ffc.SOURCE_TYPES) > 0

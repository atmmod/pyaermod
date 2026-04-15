"""Streamlit AppTest smoke tests for pyaermod.gui.

These tests exercise the Streamlit app via the headless AppTest harness
so the GUI module is no longer 0% covered. They focus on:
- App boots without errors
- Session state initializes with correct defaults
- Each top-level page renders without exceptions
- Navigation between pages updates the active page
- Sidebar progress indicators reflect session state

Heavy interactions (map widgets, file uploads, AERMOD execution) are
out of scope; those require integration environments.
"""

from __future__ import annotations

import pytest

streamlit = pytest.importorskip("streamlit")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

# streamlit-folium imports pyarrow; skip gracefully if the local
# environment has a pyarrow/numpy ABI mismatch (common on conda).
try:
    import pyarrow  # type: ignore
except Exception:  # pragma: no cover - env-specific
    pytest.skip(
        "pyarrow unavailable in this environment; skipping GUI AppTest",
        allow_module_level=True,
    )

RUNNER = "src/pyaermod/_gui_runner.py"

# Pages visible in the sidebar radio, in rendering order.
PAGES = [
    "Project Setup",
    "Source Editor",
    "Receptor Editor",
    "Meteorology",
    "Run AERMOD",
    "Results Viewer",
    "Export",
]


@pytest.fixture
def app():
    """Boot the Streamlit app for each test in isolation."""
    at = AppTest.from_file(RUNNER, default_timeout=30)
    return at


class TestAppBoots:
    def test_app_renders_without_exception(self, app):
        app.run()
        assert not app.exception, f"app raised: {app.exception}"

    def test_title_in_sidebar(self, app):
        app.run()
        # Title renders in the sidebar
        title_texts = [t.value for t in app.sidebar.title]
        assert any("PyAERMOD" in t for t in title_texts)


class TestDefaultState:
    def test_session_state_initialized(self, app):
        app.run()
        required_keys = [
            "project_control",
            "project_sources",
            "project_receptors",
            "project_meteorology",
            "project_output",
        ]
        for key in required_keys:
            # Attribute access raises if not initialized
            assert app.session_state[key] is not None, f"missing key: {key}"

    def test_progress_checkboxes_default_off(self, app):
        app.run()
        labels = [cb.label for cb in app.sidebar.checkbox]
        # At minimum, sources/receptors/met/results should be unchecked
        assert "Sources defined" in labels
        assert "Receptors defined" in labels
        assert "Meteorology set" in labels
        for cb in app.sidebar.checkbox:
            if cb.label in ("Sources defined", "Receptors defined",
                            "Meteorology set", "Results available"):
                assert cb.value is False


class TestPageNavigation:
    @pytest.mark.parametrize("page", PAGES)
    def test_each_page_renders(self, page):
        at = AppTest.from_file(RUNNER, default_timeout=30)
        at.run()
        # Click the radio value for this page
        nav = at.sidebar.radio[0]
        nav.set_value(page).run()
        assert not at.exception, f"'{page}' raised: {at.exception}"

    def test_navigation_idempotent(self, app):
        app.run()
        nav = app.sidebar.radio[0]
        nav.set_value("Source Editor").run()
        nav.set_value("Source Editor").run()  # no-op
        assert not app.exception


class TestSidebarProgressReflectsState:
    def test_sources_flag_flips_when_source_added(self, app):
        from pyaermod import PointSource
        app.session_state["project_sources"].sources.append(
            PointSource(
                source_id="S1", x_coord=0, y_coord=0, stack_height=30.0,
                stack_temp=400.0, exit_velocity=10.0,
                stack_diameter=2.0, emission_rate=1.0,
            )
        )
        app.run()
        sources_cb = next(
            cb for cb in app.sidebar.checkbox if cb.label == "Sources defined"
        )
        assert sources_cb.value is True

    def test_met_flag_flips_when_surface_file_set(self, app):
        app.session_state["project_meteorology"].surface_file = "x.sfc"
        app.run()
        met_cb = next(
            cb for cb in app.sidebar.checkbox if cb.label == "Meteorology set"
        )
        assert met_cb.value is True

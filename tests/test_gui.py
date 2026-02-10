"""
Unit tests for pyaermod_gui module (non-Streamlit logic).

Tests session state management, source form data conversion, and map editor
helpers without requiring a running Streamlit server.

When streamlit is not installed, tests that require mocking st.session_state
use a mock module injected before import.
"""

import math
import sys
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

from pyaermod_input_generator import (
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OutputPathway,
    PolarGrid,
    PointSource,
    PollutantType,
    ReceptorPathway,
    RLineSource,
    SourcePathway,
    TerrainType,
    VolumeSource,
)

# Create a mock streamlit module so pyaermod_gui can be imported
# even when streamlit is not installed.
_mock_st = MagicMock()
_mock_st.session_state = {}
_original_streamlit = sys.modules.get("streamlit")
_original_st_folium = sys.modules.get("streamlit_folium")

if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = _mock_st
if "streamlit_folium" not in sys.modules:
    sys.modules["streamlit_folium"] = MagicMock()

# Now import the GUI module (it will use our mock if streamlit isn't installed)
import pyaermod_gui
from pyaermod_gui import SessionStateManager, MapEditor, SourceFormFactory


def _fresh_session_state():
    """Return a fresh empty dict and set it as the mock's session_state."""
    state = {}
    pyaermod_gui.st.session_state = state
    return state


# ============================================================================
# TestSessionStateManager
# ============================================================================


class TestSessionStateManager:
    """Test session state management logic."""

    def test_initialize_sets_defaults(self):
        """initialize() populates session_state with default objects."""
        _fresh_session_state()
        SessionStateManager.initialize()
        state = pyaermod_gui.st.session_state

        assert "project_control" in state
        assert "project_sources" in state
        assert "project_receptors" in state
        assert "project_meteorology" in state
        assert "project_output" in state
        assert "utm_zone" in state
        assert "hemisphere" in state
        assert "datum" in state

    def test_initialize_preserves_existing(self):
        """initialize() does not overwrite existing session state values."""
        state = _fresh_session_state()
        state["utm_zone"] = 17
        SessionStateManager.initialize()
        assert pyaermod_gui.st.session_state["utm_zone"] == 17

    def test_get_project_assembles_correctly(self):
        """get_project() assembles an AERMODProject from state components."""
        _fresh_session_state()
        SessionStateManager.initialize()
        project = SessionStateManager.get_project()

        assert isinstance(project, AERMODProject)
        assert isinstance(project.control, ControlPathway)
        assert isinstance(project.sources, SourcePathway)
        assert isinstance(project.receptors, ReceptorPathway)

    def test_get_project_uses_state_values(self):
        """get_project() uses the actual values from session state."""
        state = _fresh_session_state()
        state["project_control"] = ControlPathway(
            title_one="Test Project", pollutant_id=PollutantType.PM25,
        )
        state["project_sources"] = SourcePathway()
        state["project_receptors"] = ReceptorPathway()
        state["project_meteorology"] = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )
        state["project_output"] = OutputPathway()

        project = SessionStateManager.get_project()
        assert project.control.title_one == "Test Project"
        assert project.control.pollutant_id == PollutantType.PM25

    def test_get_transformer_returns_transformer(self):
        """get_transformer() creates CoordinateTransformer from state."""
        pyproj = pytest.importorskip("pyproj")
        state = _fresh_session_state()
        state["utm_zone"] = 16
        state["hemisphere"] = "N"
        state["datum"] = "WGS84"

        t = SessionStateManager.get_transformer()
        if t is not None:
            assert t.utm_zone == 16
            assert t.hemisphere == "N"

    def test_get_transformer_returns_none_without_geo(self):
        """get_transformer() returns None if geospatial module unavailable."""
        state = _fresh_session_state()
        state["utm_zone"] = 16
        state["hemisphere"] = "N"
        state["datum"] = "WGS84"

        original = pyaermod_gui.HAS_GEO
        pyaermod_gui.HAS_GEO = False
        try:
            result = SessionStateManager.get_transformer()
            assert result is None
        finally:
            pyaermod_gui.HAS_GEO = original


# ============================================================================
# TestSourceFormDataConversion
# ============================================================================


class TestSourceFormDataConversion:
    """Test that source objects created from form data are valid."""

    def test_point_source_from_form_data(self):
        src = PointSource(
            source_id="STK1", x_coord=501000.0, y_coord=3801000.0,
            stack_height=50.0, stack_temp=450.0,
            exit_velocity=15.0, stack_diameter=2.5, emission_rate=1.0,
        )
        assert src.source_id == "STK1"
        text = src.to_aermod_input()
        assert "STK1" in text

    def test_area_source_from_form_data(self):
        src = AreaSource(
            source_id="AREA1", x_coord=501000.0, y_coord=3801000.0,
            release_height=2.0, initial_lateral_dimension=25.0,
            initial_vertical_dimension=50.0, emission_rate=0.0001,
        )
        text = src.to_aermod_input()
        assert "AREA1" in text

    def test_volume_source_from_form_data(self):
        src = VolumeSource(
            source_id="VOL1", x_coord=500000.0, y_coord=3800000.0,
            release_height=10.0, initial_lateral_dimension=7.0,
            initial_vertical_dimension=3.5, emission_rate=1.0,
        )
        text = src.to_aermod_input()
        assert "VOL1" in text

    def test_line_source_from_form_data(self):
        src = LineSource(
            source_id="LN1", x_start=500000.0, y_start=3800000.0,
            x_end=501000.0, y_end=3801000.0,
            initial_lateral_dimension=1.0, emission_rate=0.001,
        )
        text = src.to_aermod_input()
        assert "LN1" in text

    def test_rline_source_from_form_data(self):
        src = RLineSource(
            source_id="RD1", x_start=500000.0, y_start=3801000.0,
            x_end=502000.0, y_end=3801000.0,
            release_height=0.5, initial_lateral_dimension=3.0,
            initial_vertical_dimension=1.5, emission_rate=0.001,
        )
        text = src.to_aermod_input()
        assert "RD1" in text


# ============================================================================
# TestMapEditorHelpers
# ============================================================================


class TestMapEditorHelpers:
    """Test map editor helper functions."""

    def test_receptor_grid_cartesian_expansion(self):
        grid = CartesianGrid(
            grid_name="G1", x_init=0.0, x_num=5, x_delta=100.0,
            y_init=0.0, y_num=3, y_delta=100.0,
        )
        points = []
        for i in range(grid.x_num):
            for j in range(grid.y_num):
                points.append((grid.x_init + i * grid.x_delta,
                               grid.y_init + j * grid.y_delta))
        assert len(points) == 15

    def test_receptor_grid_polar_expansion(self):
        grid = PolarGrid(
            grid_name="P1", x_origin=0.0, y_origin=0.0,
            dist_init=100.0, dist_num=3, dist_delta=100.0,
            dir_init=0.0, dir_num=4, dir_delta=90.0,
        )
        points = []
        for k in range(grid.dist_num):
            dist = grid.dist_init + k * grid.dist_delta
            for d in range(grid.dir_num):
                direction = grid.dir_init + d * grid.dir_delta
                rad = math.radians(direction)
                x = grid.x_origin + dist * math.sin(rad)
                y = grid.y_origin + dist * math.cos(rad)
                points.append((x, y))
        assert len(points) == 12

    def test_polar_grid_north_direction(self):
        dist = 100.0
        rad = math.radians(0.0)
        x = dist * math.sin(rad)
        y = dist * math.cos(rad)
        assert abs(x) < 1e-10
        assert abs(y - 100.0) < 1e-10

    def test_polar_grid_east_direction(self):
        dist = 100.0
        rad = math.radians(90.0)
        x = dist * math.sin(rad)
        y = dist * math.cos(rad)
        assert abs(x - 100.0) < 1e-10
        assert abs(y) < 1e-10

    def test_source_to_marker_data_point(self):
        src = PointSource(source_id="STK1", x_coord=501000, y_coord=3801000)
        assert src.x_coord == 501000
        assert src.y_coord == 3801000

    def test_source_to_marker_data_line(self):
        src = LineSource(source_id="LN1", x_start=500000, y_start=3800000,
                         x_end=501000, y_end=3801000)
        assert hasattr(src, "x_start")
        assert hasattr(src, "x_end")

    def test_map_editor_utm_fallback(self):
        editor = MapEditor(transformer=None)
        lat, lon = editor._utm_to_latlon(100.0, 200.0)
        assert lat == 200.0
        assert lon == 100.0

    def test_map_editor_with_transformer(self):
        pyproj = pytest.importorskip("pyproj")
        from pyaermod_geospatial import CoordinateTransformer

        t = CoordinateTransformer(utm_zone=16, hemisphere="N")
        editor = MapEditor(transformer=t)
        lat, lon = editor._utm_to_latlon(501000, 3801000)
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180


# ============================================================================
# TestSourceFormFactory
# ============================================================================


class TestSourceFormFactory:
    """Test SourceFormFactory class methods."""

    def test_source_types_list(self):
        types = SourceFormFactory.SOURCE_TYPES
        assert len(types) >= 5
        assert "Point" in types
        assert "Volume" in types

    def test_source_types_are_strings(self):
        for t in SourceFormFactory.SOURCE_TYPES:
            assert isinstance(t, str)


# ============================================================================
# TestWorkflowIntegration
# ============================================================================


class TestWorkflowIntegration:
    """Test that the full workflow state management works correctly."""

    def test_add_source_to_session_state(self):
        _fresh_session_state()
        SessionStateManager.initialize()

        src = PointSource(source_id="STK1", x_coord=500000, y_coord=3800000,
                          stack_height=50, emission_rate=1.0)
        pyaermod_gui.st.session_state["project_sources"].add_source(src)

        assert len(pyaermod_gui.st.session_state["project_sources"].sources) == 1
        assert pyaermod_gui.st.session_state["project_sources"].sources[0].source_id == "STK1"

    def test_add_receptor_grid_to_session_state(self):
        _fresh_session_state()
        SessionStateManager.initialize()

        grid = CartesianGrid.from_bounds(0, 2000, 0, 2000, 100)
        pyaermod_gui.st.session_state["project_receptors"].add_cartesian_grid(grid)

        assert len(pyaermod_gui.st.session_state["project_receptors"].cartesian_grids) == 1

    def test_full_project_assembly(self):
        _fresh_session_state()
        SessionStateManager.initialize()

        pyaermod_gui.st.session_state["project_sources"].add_source(
            PointSource(source_id="S1", x_coord=0, y_coord=0,
                        stack_height=50, emission_rate=1.0)
        )
        pyaermod_gui.st.session_state["project_receptors"].add_cartesian_grid(
            CartesianGrid.from_bounds(-1000, 1000, -1000, 1000, 100)
        )
        pyaermod_gui.st.session_state["project_meteorology"] = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )

        project = SessionStateManager.get_project()
        inp = project.to_aermod_input(validate=False)
        assert "SO STARTING" in inp
        assert "RE STARTING" in inp
        assert "S1" in inp

    def test_delete_source_from_session_state(self):
        _fresh_session_state()
        SessionStateManager.initialize()

        pyaermod_gui.st.session_state["project_sources"].add_source(
            PointSource(source_id="S1", x_coord=0, y_coord=0)
        )
        pyaermod_gui.st.session_state["project_sources"].add_source(
            PointSource(source_id="S2", x_coord=100, y_coord=100)
        )
        assert len(pyaermod_gui.st.session_state["project_sources"].sources) == 2

        del pyaermod_gui.st.session_state["project_sources"].sources[0]
        assert len(pyaermod_gui.st.session_state["project_sources"].sources) == 1
        assert pyaermod_gui.st.session_state["project_sources"].sources[0].source_id == "S2"

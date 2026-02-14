"""
Unit tests for pyaermod_gui module (non-Streamlit logic).

Tests session state management, source form data conversion, and map editor
helpers without requiring a running Streamlit server.

When streamlit is not installed, tests that require mocking st.session_state
use a mock module injected before import.
"""

import math
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from pyaermod.input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    OzoneData,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SourceGroupDefinition,
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
import pyaermod.gui as pyaermod_gui  # noqa: E402
from pyaermod.gui import (  # noqa: E402
    MapEditor,
    ProjectSerializer,
    SessionStateManager,
    SourceFormFactory,
    _postfile_frames_for_animation,
)
from pyaermod.postfile import PostfileHeader, PostfileResult  # noqa: E402


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

    def test_rlinext_source_from_form_data(self):
        src = RLineExtSource(
            source_id="RLX1",
            x_start=500000.0, y_start=3801000.0, z_start=0.5,
            x_end=502000.0, y_end=3801000.0, z_end=0.5,
            emission_rate=0.001, road_width=30.0, init_sigma_z=1.5,
        )
        text = src.to_aermod_input()
        assert "RLX1" in text
        assert "RLINEXT" in text

    def test_buoyline_source_from_form_data(self):
        src = BuoyLineSource(
            source_id="BLP1",
            avg_line_length=100.0, avg_building_height=15.0,
            avg_building_width=20.0, avg_line_width=5.0,
            avg_building_separation=10.0, avg_buoyancy_parameter=0.5,
            line_segments=[
                BuoyLineSegment("BL01", 0, 0, 100, 0, emission_rate=1.0, release_height=10.0),
            ],
        )
        text = src.to_aermod_input()
        assert "BUOYLINE" in text
        assert "BLPINPUT" in text
        assert "BLPGROUP" in text

    def test_openpit_source_from_form_data(self):
        src = OpenPitSource(
            source_id="PIT1", x_coord=500000.0, y_coord=3800000.0,
            emission_rate=0.01, x_dimension=200.0, y_dimension=150.0,
            pit_volume=100000.0,
        )
        text = src.to_aermod_input()
        assert "PIT1" in text
        assert "OPENPIT" in text

    def test_area_circ_source_from_form_data(self):
        src = AreaCircSource(
            source_id="CIRC1", x_coord=500000.0, y_coord=3800000.0,
            release_height=2.0, radius=100.0, num_vertices=20,
            emission_rate=0.0001,
        )
        text = src.to_aermod_input()
        assert "CIRC1" in text
        assert "AREACIRC" in text

    def test_area_poly_source_from_form_data(self):
        vertices = [
            (500000.0, 3800000.0), (500100.0, 3800000.0),
            (500100.0, 3800100.0), (500000.0, 3800100.0),
        ]
        src = AreaPolySource(
            source_id="POLY1", vertices=vertices,
            release_height=2.0, emission_rate=0.0001,
        )
        text = src.to_aermod_input()
        assert "POLY1" in text
        assert "AREAPOLY" in text
        assert "AREAVERT" in text


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
        from pyaermod.geospatial import CoordinateTransformer

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
        assert len(types) >= 8
        assert "Point" in types
        assert "Volume" in types
        assert any("RLineExt" in t for t in types)
        assert any("BuoyLine" in t for t in types)
        assert any("OpenPit" in t for t in types)

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


# ============================================================================
# TestProjectSerializer
# ============================================================================


class TestProjectSerializer:
    """Test project save/load round-tripping."""

    def _setup_and_serialize(self):
        """Initialize session state, return serialized JSON."""
        _fresh_session_state()
        SessionStateManager.initialize()
        return ProjectSerializer.serialize_session_state()

    def test_round_trip_empty_project(self):
        json_str = self._setup_and_serialize()
        data = ProjectSerializer.deserialize_session_state(json_str)
        assert "project_control" in data
        assert "project_sources" in data
        assert len(data["project_sources"].sources) == 0

    def test_version_field_present(self):
        import json
        json_str = self._setup_and_serialize()
        data = json.loads(json_str)
        assert "pyaermod_version" in data
        assert "save_format_version" in data
        assert data["save_format_version"] == 1

    def test_load_rejects_unknown_format_version(self):
        import json
        json_str = self._setup_and_serialize()
        data = json.loads(json_str)
        data["save_format_version"] = 999
        with pytest.raises(ValueError, match="Unsupported save format version"):
            ProjectSerializer.deserialize_session_state(json.dumps(data))

    def test_round_trip_with_point_source(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        src = PointSource(
            source_id="STK1", x_coord=500000.0, y_coord=3800000.0,
            stack_height=50.0, stack_temp=450.0,
            exit_velocity=15.0, stack_diameter=2.5, emission_rate=1.0,
        )
        pyaermod_gui.st.session_state["project_sources"].add_source(src)
        json_str = ProjectSerializer.serialize_session_state()

        _fresh_session_state()
        SessionStateManager.initialize()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        for k, v in new_state.items():
            pyaermod_gui.st.session_state[k] = v

        loaded = pyaermod_gui.st.session_state["project_sources"].sources
        assert len(loaded) == 1
        assert loaded[0].source_id == "STK1"
        assert loaded[0].stack_height == 50.0
        assert loaded[0].emission_rate == 1.0

    def test_round_trip_with_all_source_types(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="P1", x_coord=0, y_coord=0, emission_rate=1.0))
        sp.add_source(AreaSource(source_id="A1", x_coord=0, y_coord=0, emission_rate=0.01))
        sp.add_source(AreaCircSource(source_id="C1", x_coord=0, y_coord=0, radius=50.0, emission_rate=0.01))
        sp.add_source(AreaPolySource(
            source_id="PY1",
            vertices=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
            emission_rate=0.01,
        ))
        sp.add_source(VolumeSource(source_id="V1", x_coord=0, y_coord=0, emission_rate=1.0))
        sp.add_source(LineSource(
            source_id="L1", x_start=0, y_start=0, x_end=100, y_end=0,
            initial_lateral_dimension=1.0, emission_rate=0.01,
        ))
        sp.add_source(RLineSource(
            source_id="R1", x_start=0, y_start=0, x_end=100, y_end=0,
            initial_lateral_dimension=3.0, emission_rate=0.01,
        ))
        sp.add_source(RLineExtSource(
            source_id="RX1", x_start=0, y_start=0, z_start=0,
            x_end=100, y_end=0, z_end=0,
            emission_rate=0.01, road_width=30.0, init_sigma_z=1.5,
        ))
        sp.add_source(BuoyLineSource(
            source_id="BL1",
            avg_line_length=100, avg_building_height=15,
            avg_building_width=20, avg_line_width=5,
            avg_building_separation=10, avg_buoyancy_parameter=0.5,
            line_segments=[
                BuoyLineSegment("BLS1", 0, 0, 100, 0, emission_rate=1.0),
            ],
        ))
        sp.add_source(OpenPitSource(
            source_id="OP1", x_coord=0, y_coord=0,
            emission_rate=0.01, x_dimension=200, y_dimension=150, pit_volume=100000,
        ))

        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded = new_state["project_sources"].sources

        assert len(loaded) == 10
        type_names = [type(s).__name__ for s in loaded]
        assert "PointSource" in type_names
        assert "AreaCircSource" in type_names
        assert "AreaPolySource" in type_names
        assert "BuoyLineSource" in type_names
        assert "OpenPitSource" in type_names

    def test_round_trip_area_poly_vertices(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        verts = [(100.0, 200.0), (300.0, 200.0), (300.0, 400.0)]
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(AreaPolySource(source_id="PY1", vertices=verts, emission_rate=0.01))

        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded_src = new_state["project_sources"].sources[0]
        assert isinstance(loaded_src, AreaPolySource)
        assert all(isinstance(v, tuple) for v in loaded_src.vertices)
        assert loaded_src.vertices[0] == (100.0, 200.0)

    def test_round_trip_buoyline_segments(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(BuoyLineSource(
            source_id="BL1",
            avg_line_length=100, avg_building_height=15,
            avg_building_width=20, avg_line_width=5,
            avg_building_separation=10, avg_buoyancy_parameter=0.5,
            line_segments=[
                BuoyLineSegment("S1", 0, 0, 50, 0, emission_rate=1.0),
                BuoyLineSegment("S2", 50, 0, 100, 0, emission_rate=2.0),
            ],
        ))
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded = new_state["project_sources"].sources[0]
        assert isinstance(loaded, BuoyLineSource)
        assert len(loaded.line_segments) == 2
        assert loaded.line_segments[0].source_id == "S1"
        assert loaded.line_segments[1].emission_rate == 2.0

    def test_round_trip_preserves_enums(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.PM25,
            terrain_type=TerrainType.ELEVATED,
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        ctrl = new_state["project_control"]
        assert ctrl.pollutant_id == PollutantType.PM25
        assert ctrl.terrain_type == TerrainType.ELEVATED

    def test_round_trip_preserves_geo_settings(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["utm_zone"] = 17
        pyaermod_gui.st.session_state["hemisphere"] = "S"
        pyaermod_gui.st.session_state["center_lat"] = -33.87
        json_str = ProjectSerializer.serialize_session_state()

        new_state = ProjectSerializer.deserialize_session_state(json_str)
        assert new_state["utm_zone"] == 17
        assert new_state["hemisphere"] == "S"
        assert new_state["center_lat"] == -33.87

    def test_round_trip_with_building_downwash(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        src = PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=50, emission_rate=1.0,
            building_height=[20.0] * 36,
            building_width=[15.0] * 36,
            building_length=[30.0] * 36,
            building_x_offset=[5.0] * 36,
            building_y_offset=[3.0] * 36,
        )
        pyaermod_gui.st.session_state["project_sources"].add_source(src)
        json_str = ProjectSerializer.serialize_session_state()

        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded = new_state["project_sources"].sources[0]
        assert isinstance(loaded.building_height, list)
        assert len(loaded.building_height) == 36
        assert loaded.building_height[0] == 20.0

    def test_round_trip_with_receptors(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        rp = pyaermod_gui.st.session_state["project_receptors"]
        rp.add_cartesian_grid(CartesianGrid.from_bounds(0, 1000, 0, 1000, 100))
        rp.add_polar_grid(PolarGrid(grid_name="PG1", x_origin=500, y_origin=500))
        rp.add_discrete_receptor(DiscreteReceptor(250.0, 250.0, z_elev=10.0))

        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded_rp = new_state["project_receptors"]
        assert len(loaded_rp.cartesian_grids) == 1
        assert len(loaded_rp.polar_grids) == 1
        assert len(loaded_rp.discrete_receptors) == 1
        assert loaded_rp.discrete_receptors[0].z_elev == 10.0


# ============================================================================
# TestAERMAPElevationImport
# ============================================================================


class TestAERMAPElevationImport:
    """Test AERMAP elevation import logic."""

    def test_apply_receptor_elevations(self):
        from pyaermod.gui import _apply_aermap_receptor_elevations

        recs = [
            DiscreteReceptor(500000.0, 3800000.0, 0.0),
            DiscreteReceptor(500100.0, 3800100.0, 0.0),
            DiscreteReceptor(999999.0, 999999.0, 0.0),  # no match
        ]
        rec_df = pd.DataFrame([
            {"x": 500000.0, "y": 3800000.0, "zelev": 150.5, "zhill": 200.0},
            {"x": 500100.0, "y": 3800100.0, "zelev": 155.3, "zhill": 210.0},
        ])
        updated = _apply_aermap_receptor_elevations(recs, rec_df)
        assert updated == 2
        assert recs[0].z_elev == 150.5
        assert recs[0].z_hill == 200.0
        assert recs[1].z_elev == 155.3
        assert recs[2].z_elev == 0.0  # unchanged

    def test_apply_source_elevations(self):
        from pyaermod.gui import _apply_aermap_source_elevations

        sources = [
            PointSource(source_id="STK1", x_coord=500000, y_coord=3800000),
            PointSource(source_id="STK2", x_coord=500100, y_coord=3800100),
        ]
        src_df = pd.DataFrame([
            {"source_id": "STK1", "source_type": "POINT", "x": 500000.0, "y": 3800000.0, "zelev": 120.0},
        ])
        updated = _apply_aermap_source_elevations(sources, src_df)
        assert updated == 1
        assert sources[0].base_elevation == 120.0
        assert sources[1].base_elevation == 0.0  # unchanged


# ============================================================================
# TestBPIPIntegration
# ============================================================================


class TestBPIPIntegration:
    """Test BPIP building downwash integration in GUI."""

    def test_buildings_in_session_state(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        assert "buildings" in pyaermod_gui.st.session_state
        assert pyaermod_gui.st.session_state["buildings"] == []

    def test_add_building_to_session_state(self):
        from pyaermod.bpip import Building
        _fresh_session_state()
        SessionStateManager.initialize()
        bldg = Building("B1", [(0, 0), (50, 0), (50, 30), (0, 30)], 20.0)
        pyaermod_gui.st.session_state["buildings"].append(bldg)
        assert len(pyaermod_gui.st.session_state["buildings"]) == 1
        assert pyaermod_gui.st.session_state["buildings"][0].building_id == "B1"

    def test_bpip_calculation_populates_point_source(self):
        from pyaermod.bpip import BPIPCalculator, Building
        bldg = Building("B1", [(0, 0), (50, 0), (50, 30), (0, 30)], 20.0)
        src = PointSource(
            source_id="STK1", x_coord=25.0, y_coord=15.0,
            stack_height=50.0, emission_rate=1.0,
        )
        calc = BPIPCalculator(bldg, src.x_coord, src.y_coord)
        result = calc.calculate_all()
        src.building_height = result.buildhgt
        src.building_width = result.buildwid
        src.building_length = result.buildlen
        src.building_x_offset = result.xbadj
        src.building_y_offset = result.ybadj

        assert len(src.building_height) == 36
        assert all(h > 0 for h in src.building_height)
        text = src.to_aermod_input()
        assert "BUILDHGT" in text
        assert "BUILDWID" in text

    def test_building_serialization_round_trip(self):
        import json

        from pyaermod.bpip import Building
        _fresh_session_state()
        SessionStateManager.initialize()
        bldg = Building("B1", [(0, 0), (50, 0), (50, 30), (0, 30)], 20.0)
        pyaermod_gui.st.session_state["buildings"].append(bldg)

        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)

        assert len(new_state["buildings"]) == 1
        loaded = new_state["buildings"][0]
        assert loaded.building_id == "B1"
        assert loaded.height == 20.0
        assert all(isinstance(c, tuple) for c in loaded.corners)


# ============================================================================
# TestAERMETConfiguration
# ============================================================================


class TestAERMETConfiguration:
    """Test AERMET configuration page integration."""

    def test_aermet_mode_default(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        assert pyaermod_gui.st.session_state["aermet_mode"] == "files"

    def test_aermet_session_state_keys(self):
        _fresh_session_state()
        SessionStateManager.initialize()
        assert "aermet_stage1" in pyaermod_gui.st.session_state
        assert "aermet_stage2" in pyaermod_gui.st.session_state
        assert "aermet_stage3" in pyaermod_gui.st.session_state
        assert pyaermod_gui.st.session_state["aermet_stage1"] is None

    def test_aermet_stage1_construction(self):
        from pyaermod.aermet import AERMETStage1, AERMETStation, UpperAirStation
        station = AERMETStation(
            station_id="KATL", station_name="Atlanta",
            latitude=33.63, longitude=-84.44, time_zone=-5,
            elevation=315.0, anemometer_height=10.0,
        )
        ua = UpperAirStation(
            station_id="72215", station_name="Peachtree",
            latitude=33.36, longitude=-84.57,
        )
        stage1 = AERMETStage1(
            surface_station=station, surface_data_file="data.ishd",
            upper_air_station=ua, upper_air_data_file="ua.fsl",
        )
        text = stage1.to_aermet_input()
        assert "SURFACE" in text
        assert "UPPERAIR" in text
        assert "KATL" in text

    def test_aermet_stage3_monthly_arrays(self):
        from pyaermod.aermet import AERMETStage3
        stage3 = AERMETStage3(
            albedo=[0.15] * 12,
            bowen=[1.0] * 12,
            roughness=[0.1] * 12,
        )
        text = stage3.to_aermet_input()
        assert "ALBEDO" in text
        assert "BOWEN" in text
        assert "ROUGHNESS" in text

    def test_aermet_stage3_rejects_wrong_length(self):
        from pyaermod.aermet import AERMETStage3
        with pytest.raises(ValueError, match="albedo must have exactly 12"):
            AERMETStage3(albedo=[0.15] * 6)

    def test_aermet_serialization_round_trip(self):
        from pyaermod.aermet import AERMETStage1, AERMETStage3, AERMETStation, UpperAirStation
        _fresh_session_state()
        SessionStateManager.initialize()

        station = AERMETStation(
            station_id="KATL", station_name="Atlanta",
            latitude=33.63, longitude=-84.44, time_zone=-5,
        )
        ua = UpperAirStation(
            station_id="72215", station_name="Peachtree",
            latitude=33.36, longitude=-84.57,
        )
        pyaermod_gui.st.session_state["aermet_mode"] = "configure"
        pyaermod_gui.st.session_state["aermet_stage1"] = AERMETStage1(
            surface_station=station,
            upper_air_station=ua,
            surface_data_file="data.ishd",
            upper_air_data_file="ua.fsl",
        )
        pyaermod_gui.st.session_state["aermet_stage3"] = AERMETStage3(
            station=station,
            albedo=[0.2] * 12,
            bowen=[0.8] * 12,
            roughness=[0.15] * 12,
        )

        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)

        assert new_state["aermet_mode"] == "configure"
        assert new_state["aermet_stage1"].surface_station.station_id == "KATL"
        assert new_state["aermet_stage1"].upper_air_station.station_id == "72215"
        assert new_state["aermet_stage3"].albedo == [0.2] * 12
        assert new_state["aermet_stage3"].station.latitude == 33.63


# ============================================================================
# TestPostfileGUI
# ============================================================================


class TestPostfileGUI:
    """Test POSTFILE GUI helper functions and session state integration."""

    def _make_postfile_result(self, num_receptors=4, num_timesteps=3):
        """Create a synthetic PostfileResult for testing."""
        rows = []
        xs = [float(i * 100) for i in range(num_receptors)]
        for t in range(num_timesteps):
            date = f"260101{t + 1:02d}"
            for i, x in enumerate(xs):
                rows.append({
                    "x": x,
                    "y": 0.0,
                    "concentration": float((t + 1) * (i + 1) * 1.5),
                    "zelev": 0.0,
                    "zhill": 0.0,
                    "zflag": 0.0,
                    "ave": "1-HR",
                    "grp": "ALL",
                    "date": date,
                })
        header = PostfileHeader(
            version="24142",
            averaging_period="1-HR",
            pollutant_id="SO2",
            source_group="ALL",
        )
        return PostfileResult(header=header, data=pd.DataFrame(rows))

    def test_postfile_frame_extraction_count(self):
        """_postfile_frames_for_animation returns correct number of frames."""
        pf = self._make_postfile_result(num_receptors=4, num_timesteps=3)
        frames, dates = _postfile_frames_for_animation(pf)

        assert len(frames) == 3
        assert len(dates) == 3

    def test_postfile_frame_extraction_columns(self):
        """Frames have uppercase X, Y, CONC columns for animation."""
        pf = self._make_postfile_result(num_receptors=4, num_timesteps=2)
        frames, _dates = _postfile_frames_for_animation(pf)

        for frame in frames:
            assert "X" in frame.columns
            assert "Y" in frame.columns
            assert "CONC" in frame.columns
            # Original lowercase columns should not be present (they were renamed)
            assert "x" not in frame.columns
            assert "y" not in frame.columns
            assert "concentration" not in frame.columns

    def test_postfile_frame_extraction_values(self):
        """Frame concentration values match the original data."""
        pf = self._make_postfile_result(num_receptors=3, num_timesteps=2)
        frames, dates = _postfile_frames_for_animation(pf)

        # First frame = first timestep
        assert dates[0] == "26010101"
        frame0 = frames[0]
        assert len(frame0) == 3
        # First receptor, first timestep: (0+1) * (0+1) * 1.5 = 1.5
        assert abs(frame0.iloc[0]["CONC"] - 1.5) < 1e-10

    def test_postfile_frame_extraction_sorted_dates(self):
        """Dates are returned in sorted order."""
        pf = self._make_postfile_result(num_receptors=2, num_timesteps=5)
        _frames, dates = _postfile_frames_for_animation(pf)

        assert dates == sorted(dates)
        assert len(dates) == 5

    def test_postfile_session_state_storage(self):
        """PostfileResult can be stored in and retrieved from session state."""
        state = _fresh_session_state()
        SessionStateManager.initialize()

        assert state["postfile_results"] is None

        pf = self._make_postfile_result()
        state["postfile_results"] = pf

        retrieved = state["postfile_results"]
        assert isinstance(retrieved, PostfileResult)
        assert len(retrieved.data) == 12  # 4 receptors × 3 timesteps

    def test_postfile_output_pathway_with_postfile(self):
        """OutputPathway generates POSTFILE keyword when enabled."""
        ou = OutputPathway(
            receptor_table=True,
            max_table=True,
            postfile="postfile.pst",
            postfile_averaging="1",
            postfile_source_group="ALL",
            postfile_format="PLOT",
        )
        output = ou.to_aermod_input()
        assert "POSTFILE" in output
        assert "postfile.pst" in output
        assert "PLOT" in output

    def test_postfile_output_pathway_unform_format(self):
        """OutputPathway generates UNFORM format keyword."""
        ou = OutputPathway(
            postfile="binary.pst",
            postfile_averaging="1",
            postfile_source_group="ALL",
            postfile_format="UNFORM",
        )
        output = ou.to_aermod_input()
        assert "UNFORM" in output
        assert "binary.pst" in output


# ============================================================================
# TestChemistrySerializerRoundTrip
# ============================================================================


class TestChemistrySerializerRoundTrip:
    """Test round-trip serialization of chemistry options."""

    def test_round_trip_chemistry_arm2(self):
        """ChemistryOptions with ARM2 method round-trips correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="NO2 Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.ARM2,
                default_no2_ratio=0.5,
            ),
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        ctrl = new_state["project_control"]
        assert ctrl.chemistry is not None
        assert ctrl.chemistry.method == ChemistryMethod.ARM2
        assert ctrl.chemistry.default_no2_ratio == 0.5

    def test_round_trip_chemistry_olm_with_ozone_file(self):
        """OLM method with ozone file round-trips."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="OLM Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.OLM,
                ozone_data=OzoneData(ozone_file="/path/to/o3.dat"),
            ),
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        chem = new_state["project_control"].chemistry
        assert chem.method == ChemistryMethod.OLM
        assert chem.ozone_data.ozone_file == "/path/to/o3.dat"

    def test_round_trip_chemistry_pvmrm_uniform_ozone(self):
        """PVMRM with uniform ozone value round-trips."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="PVMRM Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.PVMRM,
                ozone_data=OzoneData(uniform_value=40.0),
            ),
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        chem = new_state["project_control"].chemistry
        assert chem.method == ChemistryMethod.PVMRM
        assert chem.ozone_data.uniform_value == 40.0

    def test_round_trip_chemistry_grsm_with_nox_file(self):
        """GRSM with nox_file round-trips."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="GRSM Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.GRSM,
                nox_file="/path/nox.dat",
                ozone_data=OzoneData(uniform_value=50.0),
            ),
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        chem = new_state["project_control"].chemistry
        assert chem.method == ChemistryMethod.GRSM
        assert chem.nox_file == "/path/nox.dat"

    def test_round_trip_chemistry_sector_ozone_int_keys(self):
        """OzoneData.sector_values with int keys survives JSON round-trip."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="Sector O3",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.OLM,
                ozone_data=OzoneData(sector_values={1: 30.0, 2: 45.0, 3: 55.0}),
            ),
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        oz = new_state["project_control"].chemistry.ozone_data
        assert oz.sector_values == {1: 30.0, 2: 45.0, 3: 55.0}
        # Verify keys are int, not str
        assert all(isinstance(k, int) for k in oz.sector_values)

    def test_round_trip_chemistry_olm_groups(self):
        """ChemistryOptions with olm_groups round-trips."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="OLM Groups",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.OLM,
                olm_groups=[
                    SourceGroupDefinition("OLM1", ["S1", "S2"]),
                    SourceGroupDefinition("OLM2", ["S3"]),
                ],
            ),
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        chem = new_state["project_control"].chemistry
        assert len(chem.olm_groups) == 2
        assert chem.olm_groups[0].group_name == "OLM1"
        assert chem.olm_groups[0].member_source_ids == ["S1", "S2"]
        assert chem.olm_groups[1].group_name == "OLM2"

    def test_round_trip_control_without_chemistry(self):
        """ControlPathway with chemistry=None round-trips correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="No Chemistry",
            pollutant_id=PollutantType.PM25,
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        ctrl = new_state["project_control"]
        assert ctrl.chemistry is None

    def test_round_trip_point_source_with_no2_ratio(self):
        """PointSource with no2_ratio round-trips correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        src = PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=50, emission_rate=1.0,
            no2_ratio=0.75,
        )
        pyaermod_gui.st.session_state["project_sources"].add_source(src)
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded = new_state["project_sources"].sources[0]
        assert loaded.no2_ratio == 0.75


# ============================================================================
# TestSourceGroupSerializerRoundTrip
# ============================================================================


class TestSourceGroupSerializerRoundTrip:
    """Test round-trip serialization of source group definitions."""

    def test_round_trip_with_source_groups(self):
        """SourceGroupDefinition round-trips through serializer."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))
        sp.add_source(PointSource(source_id="S2", x_coord=100, y_coord=0, emission_rate=1.0))
        sp.group_definitions.append(
            SourceGroupDefinition("GRP1", ["S1", "S2"], "Test group")
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        groups = new_state["project_sources"].group_definitions
        assert len(groups) == 1
        assert groups[0].group_name == "GRP1"
        assert groups[0].member_source_ids == ["S1", "S2"]
        assert groups[0].description == "Test group"

    def test_round_trip_multiple_groups(self):
        """Multiple source groups round-trip correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))
        sp.add_source(PointSource(source_id="S2", x_coord=100, y_coord=0, emission_rate=1.0))
        sp.add_source(PointSource(source_id="S3", x_coord=200, y_coord=0, emission_rate=1.0))
        sp.group_definitions.append(SourceGroupDefinition("GRP1", ["S1", "S2"]))
        sp.group_definitions.append(SourceGroupDefinition("GRP2", ["S3"]))
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        groups = new_state["project_sources"].group_definitions
        assert len(groups) == 2
        assert groups[1].group_name == "GRP2"

    def test_round_trip_empty_group_definitions(self):
        """Empty group_definitions round-trips as empty list."""
        _fresh_session_state()
        SessionStateManager.initialize()
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        groups = new_state["project_sources"].group_definitions
        assert groups == []

    def test_backward_compat_missing_group_definitions(self):
        """Old JSON without group_definitions deserializes with empty list."""
        import json
        _fresh_session_state()
        SessionStateManager.initialize()
        json_str = ProjectSerializer.serialize_session_state()
        data = json.loads(json_str)
        # Remove group_definitions to simulate old format
        if "group_definitions" in data.get("project_sources", {}):
            del data["project_sources"]["group_definitions"]
        new_state = ProjectSerializer.deserialize_session_state(json.dumps(data))
        groups = new_state["project_sources"].group_definitions
        assert groups == []


# ============================================================================
# TestOutputPathwaySerializerRoundTrip
# ============================================================================


class TestOutputPathwaySerializerRoundTrip:
    """Test round-trip serialization of OutputPathway with plot_file_groups."""

    def test_round_trip_with_plot_file_groups(self):
        """plot_file_groups tuples round-trip correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_output"] = OutputPathway(
            plot_file_groups=[("ANNUAL", "GRP1", "plot_grp1.plt")],
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        out = new_state["project_output"]
        assert len(out.plot_file_groups) == 1
        assert out.plot_file_groups[0] == ("ANNUAL", "GRP1", "plot_grp1.plt")
        assert isinstance(out.plot_file_groups[0], tuple)

    def test_round_trip_empty_plot_file_groups(self):
        """Default OutputPathway has empty plot_file_groups."""
        _fresh_session_state()
        SessionStateManager.initialize()
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        out = new_state["project_output"]
        assert out.plot_file_groups == []

    def test_round_trip_multiple_plot_file_groups(self):
        """Multiple plot_file_groups entries round-trip correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["project_output"] = OutputPathway(
            plot_file_groups=[
                ("ANNUAL", "GRP1", "plot_grp1.plt"),
                ("1-HR", "GRP2", "plot_grp2.plt"),
                ("24-HR", "ALL", "plot_all.plt"),
            ],
        )
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        out = new_state["project_output"]
        assert len(out.plot_file_groups) == 3
        assert out.plot_file_groups[1] == ("1-HR", "GRP2", "plot_grp2.plt")


# ============================================================================
# TestBuildingDownwashAreaVolume
# ============================================================================


class TestBuildingDownwashAreaVolume:
    """Test building downwash serialization for Area and Volume sources."""

    def test_area_source_building_fields_round_trip(self):
        """AreaSource with building fields round-trips correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        src = AreaSource(
            source_id="AREA1", x_coord=0, y_coord=0,
            emission_rate=0.01,
            building_height=[20.0] * 36,
            building_width=[15.0] * 36,
            building_length=[30.0] * 36,
            building_x_offset=[5.0] * 36,
            building_y_offset=[3.0] * 36,
        )
        pyaermod_gui.st.session_state["project_sources"].add_source(src)
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded = new_state["project_sources"].sources[0]
        assert isinstance(loaded, AreaSource)
        assert isinstance(loaded.building_height, list)
        assert len(loaded.building_height) == 36
        assert loaded.building_height[0] == 20.0

    def test_volume_source_building_fields_round_trip(self):
        """VolumeSource with building fields round-trips correctly."""
        _fresh_session_state()
        SessionStateManager.initialize()
        src = VolumeSource(
            source_id="VOL1", x_coord=0, y_coord=0,
            emission_rate=1.0,
            building_height=[25.0] * 36,
            building_width=[10.0] * 36,
            building_length=[20.0] * 36,
            building_x_offset=[2.0] * 36,
            building_y_offset=[1.0] * 36,
        )
        pyaermod_gui.st.session_state["project_sources"].add_source(src)
        json_str = ProjectSerializer.serialize_session_state()
        new_state = ProjectSerializer.deserialize_session_state(json_str)
        loaded = new_state["project_sources"].sources[0]
        assert isinstance(loaded, VolumeSource)
        assert len(loaded.building_height) == 36
        assert loaded.building_width[0] == 10.0

    def test_area_source_bpip_populates_fields(self):
        """BPIP calculation populates building fields on AreaSource."""
        from pyaermod.bpip import BPIPCalculator, Building
        bldg = Building("B1", [(0, 0), (50, 0), (50, 30), (0, 30)], 20.0)
        src = AreaSource(
            source_id="AREA1", x_coord=25.0, y_coord=15.0,
            emission_rate=0.01,
        )
        calc = BPIPCalculator(bldg, src.x_coord, src.y_coord)
        result = calc.calculate_all()
        src.building_height = result.buildhgt
        src.building_width = result.buildwid
        src.building_length = result.buildlen
        src.building_x_offset = result.xbadj
        src.building_y_offset = result.ybadj

        assert len(src.building_height) == 36
        assert all(h > 0 for h in src.building_height)
        text = src.to_aermod_input()
        assert "BUILDHGT" in text

    def test_volume_source_bpip_populates_fields(self):
        """BPIP calculation populates building fields on VolumeSource."""
        from pyaermod.bpip import BPIPCalculator, Building
        bldg = Building("B1", [(0, 0), (50, 0), (50, 30), (0, 30)], 20.0)
        src = VolumeSource(
            source_id="VOL1", x_coord=25.0, y_coord=15.0,
            emission_rate=1.0,
        )
        calc = BPIPCalculator(bldg, src.x_coord, src.y_coord)
        result = calc.calculate_all()
        src.building_height = result.buildhgt
        src.building_width = result.buildwid
        src.building_length = result.buildlen
        src.building_x_offset = result.xbadj
        src.building_y_offset = result.ybadj

        assert len(src.building_height) == 36
        text = src.to_aermod_input()
        assert "BUILDHGT" in text


# ============================================================================
# TestSourceGroupWorkflow
# ============================================================================


class TestSourceGroupWorkflow:
    """Test source group management workflow via session state."""

    def test_source_group_default_empty(self):
        """Session state initializes with empty group_definitions."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        assert sp.group_definitions == []

    def test_add_source_group_to_session_state(self):
        """Source group can be added to session state."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))
        sp.group_definitions.append(SourceGroupDefinition("GRP1", ["S1"]))
        assert len(sp.group_definitions) == 1
        assert sp.group_definitions[0].group_name == "GRP1"

    def test_source_group_in_aermod_output(self):
        """SRCGROUP keyword appears in generated AERMOD input."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))
        sp.add_source(PointSource(source_id="S2", x_coord=100, y_coord=0, emission_rate=1.0))
        sp.group_definitions.append(SourceGroupDefinition("MYGRP", ["S1", "S2"]))

        pyaermod_gui.st.session_state["project_meteorology"] = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )
        project = SessionStateManager.get_project()
        inp = project.to_aermod_input(validate=False)
        assert "SRCGROUP" in inp
        assert "MYGRP" in inp

    def test_delete_source_group(self):
        """Source group can be deleted from session state."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.group_definitions.append(SourceGroupDefinition("GRP1", ["S1"]))
        sp.group_definitions.append(SourceGroupDefinition("GRP2", ["S2"]))
        assert len(sp.group_definitions) == 2
        del sp.group_definitions[0]
        assert len(sp.group_definitions) == 1
        assert sp.group_definitions[0].group_name == "GRP2"

    def test_plot_file_groups_in_aermod_output(self):
        """PLOTFILE with group name appears in generated AERMOD input."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))

        pyaermod_gui.st.session_state["project_output"] = OutputPathway(
            plot_file_groups=[("ANNUAL", "GRP1", "plot_grp1.plt")],
        )
        pyaermod_gui.st.session_state["project_meteorology"] = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )
        project = SessionStateManager.get_project()
        inp = project.to_aermod_input(validate=False)
        assert "PLOTFILE" in inp
        assert "GRP1" in inp


# ============================================================================
# TestPageRunAermod
# ============================================================================


class TestPageRunAermod:
    """Test page_run_aermod() functionality via its underlying logic."""

    def test_generates_input_preview(self):
        """SessionStateManager → project → to_aermod_input() works."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))
        pyaermod_gui.st.session_state["project_meteorology"] = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )
        project = SessionStateManager.get_project()
        inp_text = project.to_aermod_input(validate=False)
        assert "CO STARTING" in inp_text
        assert "SO STARTING" in inp_text
        assert "OU STARTING" in inp_text

    def test_output_config_postfile(self):
        """OutputPathway with POSTFILE generates correct keywords."""
        ou = OutputPathway(
            postfile="output.pst",
            postfile_averaging="1",
            postfile_source_group="ALL",
            postfile_format="UNFORM",
        )
        output = ou.to_aermod_input()
        assert "POSTFILE" in output
        assert "UNFORM" in output
        assert "ALL" in output

    def test_event_processing(self):
        """EventPathway + eventfil in ControlPathway produces EV pathway."""
        from pyaermod.input_generator import EventPathway, EventPeriod

        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))
        pyaermod_gui.st.session_state["project_meteorology"] = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )
        pyaermod_gui.st.session_state["project_control"] = ControlPathway(
            title_one="Event Test",
            eventfil="events.inp",
        )
        pyaermod_gui.st.session_state["project_events"] = EventPathway(
            events=[EventPeriod(event_name="EVT01", start_date="24010101", end_date="24010124")]
        )

        project = SessionStateManager.get_project()
        inp = project.to_aermod_input(validate=False)
        assert "EVENTFIL" in inp

    def test_deposition_output_types(self):
        """CONC/DEPOS/DDEP/WDEP/DETH all accepted in OutputPathway."""
        for otype in ["CONC", "DEPOS", "DDEP", "WDEP", "DETH"]:
            ou = OutputPathway(output_type=otype)
            output = ou.to_aermod_input()
            # Just verify it generates without error
            assert "OU STARTING" in output


# ============================================================================
# TestPageExport
# ============================================================================


class TestPageExport:
    """Test page_export() guard conditions."""

    def test_export_no_crash_without_geo(self):
        """With HAS_GEO=False, page_export() calls st.error but doesn't crash."""
        _fresh_session_state()
        SessionStateManager.initialize()
        original = pyaermod_gui.HAS_GEO
        try:
            pyaermod_gui.HAS_GEO = False
            pyaermod_gui.page_export()
            # st.error should have been called
            pyaermod_gui.st.error.assert_called()
        finally:
            pyaermod_gui.HAS_GEO = original

    def test_export_no_crash_without_transformer(self):
        """With HAS_GEO=True but no UTM zone → st.warning, no crash."""
        _fresh_session_state()
        SessionStateManager.initialize()
        # Ensure no transformer (utm_zone=0 → get_transformer returns None)
        pyaermod_gui.st.session_state["utm_zone"] = 0
        original = pyaermod_gui.HAS_GEO
        try:
            pyaermod_gui.HAS_GEO = True
            pyaermod_gui.page_export()
            # Should call st.warning about configuring UTM
            pyaermod_gui.st.warning.assert_called()
        finally:
            pyaermod_gui.HAS_GEO = original


# ============================================================================
# TestMainFunction
# ============================================================================


class TestMainFunction:
    """Test the main() entry point."""

    def test_main_has_streamlit_guard(self):
        """main() raises ImportError if HAS_STREAMLIT is False."""
        original = pyaermod_gui.HAS_STREAMLIT
        try:
            pyaermod_gui.HAS_STREAMLIT = False
            with pytest.raises(ImportError, match="Streamlit"):
                pyaermod_gui.main()
        finally:
            pyaermod_gui.HAS_STREAMLIT = original

    def test_page_functions_exist(self):
        """All 7 page functions exist as attributes on gui module."""
        pages = [
            "page_project_setup",
            "page_source_editor",
            "page_receptor_editor",
            "page_meteorology",
            "page_run_aermod",
            "page_results_viewer",
            "page_export",
        ]
        for name in pages:
            assert hasattr(pyaermod_gui, name), f"Missing: {name}"
            assert callable(getattr(pyaermod_gui, name))


# ============================================================================
# TestPageResultsViewer
# ============================================================================


class TestPageResultsViewer:
    """Test page_results_viewer() guard conditions."""

    def test_no_results_no_crash(self):
        """page_results_viewer() with no parsed_results doesn't crash."""
        _fresh_session_state()
        SessionStateManager.initialize()
        pyaermod_gui.st.session_state["parsed_results"] = None
        # Ensure file_uploader returns None (no uploaded file)
        pyaermod_gui.st.file_uploader.return_value = None
        # Should not raise
        pyaermod_gui.page_results_viewer()

    def test_page_run_aermod_no_crash(self):
        """page_run_aermod() runs through without crashing."""
        _fresh_session_state()
        SessionStateManager.initialize()
        sp = pyaermod_gui.st.session_state["project_sources"]
        sp.add_source(PointSource(source_id="S1", x_coord=0, y_coord=0, emission_rate=1.0))
        pyaermod_gui.st.session_state["project_meteorology"] = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )
        # Mock st.columns to return a tuple of MagicMocks with context manager
        col_mock = MagicMock()
        col_mock.__enter__ = MagicMock(return_value=col_mock)
        col_mock.__exit__ = MagicMock(return_value=False)
        pyaermod_gui.st.columns.return_value = [col_mock, col_mock]
        pyaermod_gui.st.checkbox.return_value = False
        pyaermod_gui.st.button.return_value = False
        pyaermod_gui.st.expander.return_value.__enter__ = MagicMock()
        pyaermod_gui.st.expander.return_value.__exit__ = MagicMock(return_value=False)
        # Should not raise
        pyaermod_gui.page_run_aermod()

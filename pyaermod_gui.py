"""
PyAERMOD Streamlit GUI

Interactive web-based GUI for the full AERMOD workflow:
project setup -> source/receptor editing on maps -> run AERMOD -> visualize -> export.

Launch with:
    streamlit run pyaermod_gui.py
    # or
    pyaermod-gui

Requires: pip install pyaermod[gui]
"""

import io
import math
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False
    st = None  # Allow module import for testing; main() will check

try:
    import folium
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# PyAERMOD imports
from pyaermod_input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    PolarGrid,
    PointSource,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SourcePathway,
    SourceType,
    TerrainType,
    VolumeSource,
)

try:
    from pyaermod_geospatial import (
        CoordinateTransformer,
        ContourGenerator,
        GeoDataFrameFactory,
        RasterExporter,
        VectorExporter,
        export_concentration_geotiff,
        export_concentration_shapefile,
    )
    HAS_GEO = True
except ImportError:
    HAS_GEO = False

try:
    from pyaermod_runner import AERMODRunner, run_aermod
    HAS_RUNNER = True
except ImportError:
    HAS_RUNNER = False

try:
    from pyaermod_output_parser import AERMODOutputParser, parse_aermod_output
    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False

try:
    from pyaermod_postfile import PostfileParser, read_postfile
    HAS_POSTFILE = True
except ImportError:
    HAS_POSTFILE = False

try:
    from pyaermod_validator import Validator
    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False

try:
    from pyaermod_visualization import AERMODVisualizer
    HAS_VIZ = True
except ImportError:
    HAS_VIZ = False


# ============================================================================
# SESSION STATE MANAGEMENT
# ============================================================================


class SessionStateManager:
    """Manages the AERMODProject and related state in st.session_state."""

    @staticmethod
    def initialize():
        """Set default session state values if not already present."""
        defaults = {
            "project_control": ControlPathway(
                title_one="New PyAERMOD Project",
                title_two="Created with PyAERMOD GUI",
            ),
            "project_sources": SourcePathway(),
            "project_receptors": ReceptorPathway(),
            "project_meteorology": MeteorologyPathway(
                surface_file="", profile_file="",
            ),
            "project_output": OutputPathway(),
            "utm_zone": 16,
            "hemisphere": "N",
            "datum": "WGS84",
            "center_lat": 33.75,
            "center_lon": -84.39,
            "run_result": None,
            "parsed_results": None,
            "postfile_results": None,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def get_project() -> AERMODProject:
        """Assemble an AERMODProject from session state components."""
        return AERMODProject(
            control=st.session_state["project_control"],
            sources=st.session_state["project_sources"],
            receptors=st.session_state["project_receptors"],
            meteorology=st.session_state["project_meteorology"],
            output=st.session_state["project_output"],
        )

    @staticmethod
    def get_transformer() -> Optional["CoordinateTransformer"]:
        """Get CoordinateTransformer from session state UTM settings."""
        if not HAS_GEO:
            return None
        try:
            return CoordinateTransformer(
                utm_zone=st.session_state["utm_zone"],
                hemisphere=st.session_state["hemisphere"],
                datum=st.session_state["datum"],
            )
        except Exception:
            return None


# ============================================================================
# MAP EDITOR
# ============================================================================


class MapEditor:
    """Interactive map editor using streamlit-folium."""

    def __init__(
        self,
        transformer: Optional["CoordinateTransformer"] = None,
        center: Optional[Tuple[float, float]] = None,
        zoom: int = 13,
    ):
        self.transformer = transformer
        self.center = center or (33.75, -84.39)
        self.zoom = zoom

    def _create_base_map(self) -> "folium.Map":
        """Create a folium Map with multiple tile layers."""
        m = folium.Map(location=self.center, zoom_start=self.zoom)

        # Additional tile layers
        folium.TileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Satellite",
        ).add_to(m)
        folium.TileLayer(
            "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
            attr="OpenTopoMap",
            name="Terrain",
        ).add_to(m)
        folium.LayerControl().add_to(m)
        return m

    def _utm_to_latlon(self, x: float, y: float) -> Tuple[float, float]:
        """Convert UTM to (lat, lon) using the transformer."""
        if self.transformer:
            return self.transformer.utm_to_latlon(x, y)
        return (y, x)  # fallback: treat as lat/lon

    def _latlon_to_utm(self, lat: float, lon: float) -> Tuple[float, float]:
        """Convert (lat, lon) to UTM using the transformer."""
        if self.transformer:
            return self.transformer.latlon_to_utm(lat, lon)
        return (lon, lat)  # fallback

    def add_sources_to_map(self, m: "folium.Map", sources: list):
        """Add source markers to a folium map."""
        from pyaermod_input_generator import (
            LineSource, RLineSource, RLineExtSource,
            BuoyLineSource, OpenPitSource, AreaPolySource,
        )

        for src in sources:
            sid = getattr(src, "source_id", "?")
            if isinstance(src, RLineExtSource):
                start = self._utm_to_latlon(src.x_start, src.y_start)
                end = self._utm_to_latlon(src.x_end, src.y_end)
                folium.PolyLine(
                    [start, end], color="purple", weight=4,
                    popup=f"{sid} (RLINEXT)",
                ).add_to(m)
            elif isinstance(src, BuoyLineSource):
                for seg in src.line_segments:
                    start = self._utm_to_latlon(seg.x_start, seg.y_start)
                    end = self._utm_to_latlon(seg.x_end, seg.y_end)
                    folium.PolyLine(
                        [start, end], color="green", weight=3,
                        popup=f"{seg.source_id} (BUOYLINE)",
                    ).add_to(m)
            elif isinstance(src, OpenPitSource):
                # Rectangle from SW corner + dimensions
                corners = [
                    (src.x_coord, src.y_coord),
                    (src.x_coord + src.x_dimension, src.y_coord),
                    (src.x_coord + src.x_dimension, src.y_coord + src.y_dimension),
                    (src.x_coord, src.y_coord + src.y_dimension),
                ]
                verts = [self._utm_to_latlon(x, y) for x, y in corners]
                verts.append(verts[0])
                folium.Polygon(
                    verts, color="brown", fill=True, fill_opacity=0.3,
                    popup=f"{sid} (OPENPIT)",
                ).add_to(m)
            elif isinstance(src, (LineSource, RLineSource)):
                start = self._utm_to_latlon(src.x_start, src.y_start)
                end = self._utm_to_latlon(src.x_end, src.y_end)
                folium.PolyLine(
                    [start, end], color="red", weight=3,
                    popup=f"{sid} ({type(src).__name__})",
                ).add_to(m)
            elif isinstance(src, AreaPolySource):
                verts = [self._utm_to_latlon(x, y) for x, y in src.vertices]
                verts.append(verts[0])  # close polygon
                folium.Polygon(
                    verts, color="orange", fill=True, fill_opacity=0.3,
                    popup=f"{sid} (AreaPoly)",
                ).add_to(m)
            else:
                x = getattr(src, "x_coord", 0)
                y = getattr(src, "y_coord", 0)
                ll = self._utm_to_latlon(x, y)
                folium.Marker(
                    ll,
                    popup=f"{sid} ({type(src).__name__})",
                    icon=folium.Icon(color="red", icon="industry", prefix="fa"),
                ).add_to(m)

    def add_receptors_to_map(self, m: "folium.Map", receptors: "ReceptorPathway",
                             max_points: int = 2500):
        """Add receptor points to a folium map (with throttling)."""
        points = []
        for grid in receptors.cartesian_grids:
            for i in range(grid.x_num):
                for j in range(grid.y_num):
                    x = grid.x_init + i * grid.x_delta
                    y = grid.y_init + j * grid.y_delta
                    points.append((x, y))

        for grid in receptors.polar_grids:
            for k in range(grid.dist_num):
                dist = grid.dist_init + k * grid.dist_delta
                for d in range(grid.dir_num):
                    direction = grid.dir_init + d * grid.dir_delta
                    rad = math.radians(direction)
                    x = grid.x_origin + dist * math.sin(rad)
                    y = grid.y_origin + dist * math.cos(rad)
                    points.append((x, y))

        for rec in receptors.discrete_receptors:
            points.append((rec.x_coord, rec.y_coord))

        if len(points) > max_points:
            # Show boundary rectangle instead
            if points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                corners = [
                    self._utm_to_latlon(min(xs), min(ys)),
                    self._utm_to_latlon(max(xs), min(ys)),
                    self._utm_to_latlon(max(xs), max(ys)),
                    self._utm_to_latlon(min(xs), max(ys)),
                ]
                folium.Polygon(
                    corners, color="blue", fill=True, fill_opacity=0.1,
                    popup=f"Receptor grid ({len(points)} points)",
                ).add_to(m)
        else:
            for x, y in points:
                ll = self._utm_to_latlon(x, y)
                folium.CircleMarker(
                    ll, radius=2, color="blue", fill=True,
                    fill_opacity=0.6, weight=1,
                ).add_to(m)

    def render_source_editor(self, sources: list) -> Optional[Tuple[float, float]]:
        """Render interactive map for source placement. Returns clicked UTM coords."""
        if not HAS_FOLIUM:
            st.warning("folium and streamlit-folium required for interactive maps.")
            return None

        m = self._create_base_map()
        self.add_sources_to_map(m, sources)

        map_data = st_folium(m, width=700, height=500, key="source_map")

        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
            return self._latlon_to_utm(lat, lon)
        return None

    def render_receptor_editor(self, receptors, sources=None):
        """Render map with receptors and optionally sources."""
        if not HAS_FOLIUM:
            st.warning("folium and streamlit-folium required for interactive maps.")
            return None

        m = self._create_base_map()
        if sources:
            self.add_sources_to_map(m, sources)
        self.add_receptors_to_map(m, receptors)

        map_data = st_folium(m, width=700, height=500, key="receptor_map")

        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
            return self._latlon_to_utm(lat, lon)
        return None

    def render_concentration_map(
        self, df: pd.DataFrame, sources: Optional[list] = None,
    ):
        """Render concentration results on an interactive map."""
        if not HAS_FOLIUM:
            st.warning("folium required for interactive maps.")
            return

        m = self._create_base_map()

        if sources:
            self.add_sources_to_map(m, sources)

        # Add concentration heatmap
        if self.transformer:
            heat_data = []
            for _, row in df.iterrows():
                lat, lon = self.transformer.utm_to_latlon(row["x"], row["y"])
                heat_data.append([lat, lon, float(row["concentration"])])

            if heat_data:
                from folium.plugins import HeatMap
                HeatMap(
                    heat_data, min_opacity=0.3, radius=15,
                    blur=10, max_zoom=18,
                ).add_to(m)

        # Mark max concentration
        if not df.empty:
            max_row = df.loc[df["concentration"].idxmax()]
            max_ll = self._utm_to_latlon(max_row["x"], max_row["y"])
            folium.Marker(
                max_ll,
                popup=f"Max: {max_row['concentration']:.4g}",
                icon=folium.Icon(color="green", icon="star"),
            ).add_to(m)

        st_folium(m, width=700, height=500, key="results_map")


# ============================================================================
# SOURCE FORM FACTORY
# ============================================================================


class SourceFormFactory:
    """Generates Streamlit form widgets for each AERMOD source type."""

    SOURCE_TYPES = [
        "Point", "Area (Rectangular)", "Area (Circular)",
        "Area (Polygon)", "Volume", "Line", "RLine (Roadway)",
        "RLineExt (Extended Roadway)", "BuoyLine (Buoyant Line)",
        "OpenPit (Open Pit Mine)",
    ]

    @staticmethod
    def render_source_type_selector() -> str:
        return st.selectbox("Source Type", SourceFormFactory.SOURCE_TYPES)

    @staticmethod
    def render_point_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[PointSource]:
        with st.form("point_source_form"):
            st.subheader("Point Source Parameters")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="STACK1")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                height = st.number_input("Stack Height (m)", value=50.0, min_value=0.0)
                temp = st.number_input("Stack Temperature (K)", value=450.0, min_value=0.0)
                vel = st.number_input("Exit Velocity (m/s)", value=15.0, min_value=0.0)
                diam = st.number_input("Stack Diameter (m)", value=2.5, min_value=0.0)
            erate = st.number_input("Emission Rate (g/s)", value=1.0, min_value=0.0, format="%.6f")

            if st.form_submit_button("Add Point Source"):
                return PointSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    stack_height=height, stack_temp=temp,
                    exit_velocity=vel, stack_diameter=diam,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_area_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[AreaSource]:
        with st.form("area_source_form"):
            st.subheader("Rectangular Area Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="AREA1")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                rh = st.number_input("Release Height (m)", value=2.0, min_value=0.0)
                lat_dim = st.number_input("Half-Width Y (m)", value=25.0, min_value=0.0)
                vert_dim = st.number_input("Half-Width X (m)", value=50.0, min_value=0.0)
                angle = st.number_input("Rotation Angle (deg)", value=0.0)
            erate = st.number_input("Emission Rate (g/s/m2)", value=0.0001, format="%.6f")

            if st.form_submit_button("Add Area Source"):
                return AreaSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    release_height=rh, initial_lateral_dimension=lat_dim,
                    initial_vertical_dimension=vert_dim, angle=angle,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_volume_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[VolumeSource]:
        with st.form("volume_source_form"):
            st.subheader("Volume Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="VOL1")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                rh = st.number_input("Release Height (m)", value=10.0, min_value=0.0)
                lat_dim = st.number_input("Initial Sigma-Y (m)", value=7.0, min_value=0.0)
                vert_dim = st.number_input("Initial Sigma-Z (m)", value=3.5, min_value=0.0)
            erate = st.number_input("Emission Rate (g/s)", value=1.0, format="%.6f")

            if st.form_submit_button("Add Volume Source"):
                return VolumeSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    release_height=rh, initial_lateral_dimension=lat_dim,
                    initial_vertical_dimension=vert_dim,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_line_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[LineSource]:
        with st.form("line_source_form"):
            st.subheader("Line Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="LINE1")
                xs = st.number_input("X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Y Start (UTM m)", value=default_y, format="%.2f")
            with col2:
                xe = st.number_input("X End (UTM m)", value=default_x + 500, format="%.2f")
                ye = st.number_input("Y End (UTM m)", value=default_y, format="%.2f")
                rh = st.number_input("Release Height (m)", value=0.0, min_value=0.0)
            lat_dim = st.number_input("Initial Sigma-Y (m)", value=1.0, min_value=0.0)
            erate = st.number_input("Emission Rate (g/s/m)", value=0.001, format="%.6f")

            if st.form_submit_button("Add Line Source"):
                return LineSource(
                    source_id=sid, x_start=xs, y_start=ys,
                    x_end=xe, y_end=ye, release_height=rh,
                    initial_lateral_dimension=lat_dim,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_rline_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[RLineSource]:
        with st.form("rline_source_form"):
            st.subheader("Roadway (RLINE) Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="ROAD1")
                xs = st.number_input("X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Y Start (UTM m)", value=default_y, format="%.2f")
            with col2:
                xe = st.number_input("X End (UTM m)", value=default_x + 1000, format="%.2f")
                ye = st.number_input("Y End (UTM m)", value=default_y, format="%.2f")
                rh = st.number_input("Release Height (m)", value=0.5, min_value=0.0)
            col3, col4 = st.columns(2)
            with col3:
                lat_dim = st.number_input("Lane Half-Width (m)", value=3.0, min_value=0.0)
            with col4:
                vert_dim = st.number_input("Initial Mixing (m)", value=1.5, min_value=0.0)
            erate = st.number_input("Emission Rate (g/s/m)", value=0.001, format="%.6f")

            if st.form_submit_button("Add Roadway Source"):
                return RLineSource(
                    source_id=sid, x_start=xs, y_start=ys,
                    x_end=xe, y_end=ye, release_height=rh,
                    initial_lateral_dimension=lat_dim,
                    initial_vertical_dimension=vert_dim,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_rlinext_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[RLineExtSource]:
        with st.form("rlinext_source_form"):
            st.subheader("Extended Roadway (RLINEXT) Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="REXT1")
                xs = st.number_input("X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Y Start (UTM m)", value=default_y, format="%.2f")
                zs = st.number_input("Z Start (m)", value=1.5, min_value=0.0)
            with col2:
                xe = st.number_input("X End (UTM m)", value=default_x + 500, format="%.2f")
                ye = st.number_input("Y End (UTM m)", value=default_y, format="%.2f")
                ze = st.number_input("Z End (m)", value=1.5, min_value=0.0)
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            col3, col4 = st.columns(2)
            with col3:
                width = st.number_input("Road Width (m)", value=30.0, min_value=0.1)
                dcl = st.number_input("Centerline Offset (m)", value=0.0)
            with col4:
                isz = st.number_input("Initial Sigma-Z (m)", value=1.5, min_value=0.0)
            erate = st.number_input("Emission Rate (g/m/s)", value=0.001, format="%.6f")

            st.markdown("**Depression (optional)**")
            col5, col6 = st.columns(2)
            with col5:
                depth = st.number_input("Depression Depth (m, negative)", value=0.0, max_value=0.0)
                wtop = st.number_input("Depression Top Width (m)", value=0.0, min_value=0.0)
            with col6:
                wbot = st.number_input("Depression Bottom Width (m)", value=0.0, min_value=0.0)

            if st.form_submit_button("Add RLINEXT Source"):
                kwargs = dict(
                    source_id=sid, x_start=xs, y_start=ys, z_start=zs,
                    x_end=xe, y_end=ye, z_end=ze, base_elevation=elev,
                    emission_rate=erate, dcl=dcl, road_width=width,
                    init_sigma_z=isz,
                )
                if depth < 0:
                    kwargs.update(depression_depth=depth, depression_wtop=wtop,
                                  depression_wbottom=wbot)
                return RLineExtSource(**kwargs)
        return None

    @staticmethod
    def render_buoyline_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[BuoyLineSource]:
        with st.form("buoyline_source_form"):
            st.subheader("Buoyant Line Source")
            sid = st.text_input("Group ID", value="BLP1")
            st.markdown("**Average Plume Rise Parameters (BLPINPUT)**")
            col1, col2 = st.columns(2)
            with col1:
                avg_ll = st.number_input("Avg Line Length (m)", value=100.0, min_value=0.1)
                avg_bh = st.number_input("Avg Building Height (m)", value=15.0, min_value=0.1)
                avg_bw = st.number_input("Avg Building Width (m)", value=10.0, min_value=0.1)
            with col2:
                avg_lw = st.number_input("Avg Line Width (m)", value=5.0, min_value=0.1)
                avg_bs = st.number_input("Avg Building Separation (m)", value=20.0, min_value=0.0)
                avg_bp = st.number_input("Avg Buoyancy Param (m4/s3)", value=500.0, min_value=0.0, format="%.2f")
            st.markdown("**Line Segment**")
            col3, col4 = st.columns(2)
            with col3:
                seg_id = st.text_input("Segment ID", value="BL01")
                xs = st.number_input("Seg X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Seg Y Start (UTM m)", value=default_y, format="%.2f")
            with col4:
                xe = st.number_input("Seg X End (UTM m)", value=default_x + 100, format="%.2f")
                ye = st.number_input("Seg Y End (UTM m)", value=default_y, format="%.2f")
                rh = st.number_input("Seg Release Height (m)", value=4.5, min_value=0.0)
            erate = st.number_input("Seg Emission Rate (g/s)", value=10.0, format="%.6f")

            if st.form_submit_button("Add Buoyant Line Source"):
                seg = BuoyLineSegment(
                    source_id=seg_id, x_start=xs, y_start=ys,
                    x_end=xe, y_end=ye, emission_rate=erate,
                    release_height=rh,
                )
                return BuoyLineSource(
                    source_id=sid,
                    avg_line_length=avg_ll, avg_building_height=avg_bh,
                    avg_building_width=avg_bw, avg_line_width=avg_lw,
                    avg_building_separation=avg_bs, avg_buoyancy_parameter=avg_bp,
                    line_segments=[seg],
                )
        return None

    @staticmethod
    def render_openpit_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[OpenPitSource]:
        with st.form("openpit_source_form"):
            st.subheader("Open Pit Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="PIT1")
                x = st.number_input("SW Corner X (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("SW Corner Y (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                xdim = st.number_input("X Dimension (m)", value=200.0, min_value=0.1)
                ydim = st.number_input("Y Dimension (m)", value=100.0, min_value=0.1)
                vol = st.number_input("Pit Volume (m3)", value=100000.0, min_value=0.1, format="%.2f")
                angle = st.number_input("Rotation Angle (deg)", value=0.0)
            erate = st.number_input("Emission Rate (g/s/m2)", value=0.005, format="%.6f")
            rh = st.number_input("Release Height (m)", value=0.0, min_value=0.0)

            if st.form_submit_button("Add Open Pit Source"):
                return OpenPitSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    emission_rate=erate, release_height=rh,
                    x_dimension=xdim, y_dimension=ydim,
                    pit_volume=vol, angle=angle,
                )
        return None


# ============================================================================
# GUI PAGES
# ============================================================================


def page_project_setup():
    """Project Setup page."""
    st.header("Project Setup")

    st.subheader("Project Titles")
    title1 = st.text_input(
        "Title Line 1",
        value=st.session_state["project_control"].title_one,
    )
    title2 = st.text_input(
        "Title Line 2",
        value=st.session_state["project_control"].title_two or "",
    )

    st.subheader("Coordinate Reference System")
    col1, col2, col3 = st.columns(3)
    with col1:
        utm_zone = st.number_input(
            "UTM Zone", min_value=1, max_value=60,
            value=st.session_state["utm_zone"],
        )
    with col2:
        hemisphere = st.selectbox(
            "Hemisphere",
            ["N", "S"],
            index=0 if st.session_state["hemisphere"] == "N" else 1,
        )
    with col3:
        datum = st.selectbox(
            "Datum",
            ["WGS84", "NAD83", "NAD27"],
            index=["WGS84", "NAD83", "NAD27"].index(st.session_state["datum"]),
        )

    st.subheader("Map Center (for interactive map views)")
    col4, col5 = st.columns(2)
    with col4:
        center_lat = st.number_input(
            "Latitude", value=st.session_state["center_lat"],
            min_value=-90.0, max_value=90.0, format="%.6f",
        )
    with col5:
        center_lon = st.number_input(
            "Longitude", value=st.session_state["center_lon"],
            min_value=-180.0, max_value=180.0, format="%.6f",
        )

    st.subheader("Model Configuration")
    col6, col7 = st.columns(2)
    with col6:
        pollutant_names = [p.name for p in PollutantType]
        current_poll = st.session_state["project_control"].pollutant_id
        if isinstance(current_poll, PollutantType):
            current_idx = pollutant_names.index(current_poll.name)
        else:
            current_idx = 0
        pollutant = st.selectbox("Pollutant", pollutant_names, index=current_idx)

    with col7:
        terrain_names = [t.name for t in TerrainType]
        current_terrain = st.session_state["project_control"].terrain_type
        if isinstance(current_terrain, TerrainType):
            terrain_idx = terrain_names.index(current_terrain.name)
        else:
            terrain_idx = 0
        terrain = st.selectbox("Terrain Type", terrain_names, index=terrain_idx)

    avg_options = ["1-HR", "2-HR", "3-HR", "4-HR", "6-HR", "8-HR", "12-HR", "24-HR",
                   "ANNUAL", "MONTH", "PERIOD"]
    current_avg = st.session_state["project_control"].averaging_periods
    avg_periods = st.multiselect("Averaging Periods", avg_options, default=current_avg)

    # Save to session state
    st.session_state["utm_zone"] = utm_zone
    st.session_state["hemisphere"] = hemisphere
    st.session_state["datum"] = datum
    st.session_state["center_lat"] = center_lat
    st.session_state["center_lon"] = center_lon
    st.session_state["project_control"] = ControlPathway(
        title_one=title1,
        title_two=title2 if title2 else None,
        pollutant_id=PollutantType[pollutant],
        averaging_periods=avg_periods if avg_periods else ["ANNUAL"],
        terrain_type=TerrainType[terrain],
    )

    st.success("Project settings saved automatically.")


def page_source_editor():
    """Source Editor page with interactive map."""
    st.header("Source Editor")

    sources = st.session_state["project_sources"].sources
    transformer = SessionStateManager.get_transformer()

    # Map and form in columns
    map_col, form_col = st.columns([3, 2])

    clicked_utm = None
    with map_col:
        st.subheader("Source Map")
        if HAS_FOLIUM and transformer:
            editor = MapEditor(
                transformer=transformer,
                center=(st.session_state["center_lat"], st.session_state["center_lon"]),
            )
            clicked_utm = editor.render_source_editor(sources)
            if clicked_utm:
                st.info(f"Clicked: UTM ({clicked_utm[0]:.2f}, {clicked_utm[1]:.2f})")
        else:
            st.info("Install pyproj and streamlit-folium for interactive map editing.")

    with form_col:
        st.subheader("Add Source")
        source_type = SourceFormFactory.render_source_type_selector()

        default_x = clicked_utm[0] if clicked_utm else 0.0
        default_y = clicked_utm[1] if clicked_utm else 0.0

        new_source = None
        if source_type == "Point":
            new_source = SourceFormFactory.render_point_source_form(default_x, default_y)
        elif source_type == "Area (Rectangular)":
            new_source = SourceFormFactory.render_area_source_form(default_x, default_y)
        elif source_type == "Volume":
            new_source = SourceFormFactory.render_volume_source_form(default_x, default_y)
        elif source_type == "Line":
            new_source = SourceFormFactory.render_line_source_form(default_x, default_y)
        elif source_type == "RLine (Roadway)":
            new_source = SourceFormFactory.render_rline_source_form(default_x, default_y)
        elif source_type == "RLineExt (Extended Roadway)":
            new_source = SourceFormFactory.render_rlinext_source_form(default_x, default_y)
        elif source_type == "BuoyLine (Buoyant Line)":
            new_source = SourceFormFactory.render_buoyline_source_form(default_x, default_y)
        elif source_type == "OpenPit (Open Pit Mine)":
            new_source = SourceFormFactory.render_openpit_source_form(default_x, default_y)

        if new_source:
            st.session_state["project_sources"].add_source(new_source)
            st.success(f"Added {type(new_source).__name__}: {new_source.source_id}")
            st.rerun()

    # Source table
    st.subheader("Current Sources")
    if sources:
        rows = []
        for s in sources:
            row = {"ID": s.source_id, "Type": type(s).__name__}
            if hasattr(s, "x_coord"):
                row["X"] = s.x_coord
                row["Y"] = s.y_coord
            elif hasattr(s, "x_start"):
                row["X"] = s.x_start
                row["Y"] = s.y_start
            row["Emission Rate"] = s.emission_rate
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # Delete source
        delete_idx = st.selectbox(
            "Select source to delete",
            range(len(sources)),
            format_func=lambda i: f"{sources[i].source_id} ({type(sources[i]).__name__})",
        )
        if st.button("Delete Selected Source", type="secondary"):
            del st.session_state["project_sources"].sources[delete_idx]
            st.rerun()
    else:
        st.info("No sources defined yet. Use the form above or click on the map to add sources.")


def page_receptor_editor():
    """Receptor Editor page with grid definition and map preview."""
    st.header("Receptor Editor")

    receptors = st.session_state["project_receptors"]
    transformer = SessionStateManager.get_transformer()

    tab_cart, tab_polar, tab_discrete, tab_import = st.tabs([
        "Cartesian Grid", "Polar Grid", "Discrete Receptors", "Import CSV",
    ])

    with tab_cart:
        st.subheader("Cartesian Receptor Grid")
        with st.form("cartesian_grid_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Grid Name", value="GRID1")
                x_min = st.number_input("X Min (UTM m)", value=0.0, format="%.2f")
                x_max = st.number_input("X Max (UTM m)", value=2000.0, format="%.2f")
            with col2:
                spacing = st.number_input("Spacing (m)", value=100.0, min_value=1.0)
                y_min = st.number_input("Y Min (UTM m)", value=0.0, format="%.2f")
                y_max = st.number_input("Y Max (UTM m)", value=2000.0, format="%.2f")

            if st.form_submit_button("Add Cartesian Grid"):
                grid = CartesianGrid.from_bounds(x_min, x_max, y_min, y_max, spacing, name)
                receptors.add_cartesian_grid(grid)
                n_pts = grid.x_num * grid.y_num
                st.success(f"Added grid '{name}' ({grid.x_num} x {grid.y_num} = {n_pts} receptors)")
                st.rerun()

    with tab_polar:
        st.subheader("Polar Receptor Grid")
        with st.form("polar_grid_form"):
            col1, col2 = st.columns(2)
            with col1:
                pname = st.text_input("Grid Name", value="POLAR1")
                x_orig = st.number_input("X Origin (UTM m)", value=0.0, format="%.2f")
                y_orig = st.number_input("Y Origin (UTM m)", value=0.0, format="%.2f")
            with col2:
                d_init = st.number_input("Start Distance (m)", value=100.0, min_value=0.0)
                d_num = st.number_input("Number of Rings", value=10, min_value=1, step=1)
                d_delta = st.number_input("Distance Increment (m)", value=100.0, min_value=1.0)
            dir_num = st.number_input("Number of Directions", value=36, min_value=1, step=1)

            if st.form_submit_button("Add Polar Grid"):
                grid = PolarGrid(
                    grid_name=pname, x_origin=x_orig, y_origin=y_orig,
                    dist_init=d_init, dist_num=int(d_num), dist_delta=d_delta,
                    dir_init=0.0, dir_num=int(dir_num),
                    dir_delta=360.0 / int(dir_num),
                )
                receptors.add_polar_grid(grid)
                st.success(f"Added polar grid '{pname}' ({int(d_num)} x {int(dir_num)} = {int(d_num) * int(dir_num)} receptors)")
                st.rerun()

    with tab_discrete:
        st.subheader("Discrete Receptors")

        # Click-to-place via map
        if HAS_FOLIUM and transformer:
            editor = MapEditor(
                transformer=transformer,
                center=(st.session_state["center_lat"], st.session_state["center_lon"]),
            )
            clicked = editor.render_receptor_editor(
                receptors, st.session_state["project_sources"].sources,
            )
            if clicked:
                st.info(f"Clicked: UTM ({clicked[0]:.2f}, {clicked[1]:.2f})")

        with st.form("discrete_receptor_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                dx = st.number_input("X (UTM m)", value=0.0, format="%.2f", key="disc_x")
            with col2:
                dy = st.number_input("Y (UTM m)", value=0.0, format="%.2f", key="disc_y")
            with col3:
                dz = st.number_input("Z Elevation (m)", value=0.0, format="%.2f", key="disc_z")

            if st.form_submit_button("Add Discrete Receptor"):
                receptors.add_discrete_receptor(DiscreteReceptor(dx, dy, dz))
                st.success(f"Added receptor at ({dx:.2f}, {dy:.2f})")
                st.rerun()

    with tab_import:
        st.subheader("Import Receptors from CSV")
        st.info("Upload a CSV with columns: x, y (and optionally z_elev)")
        uploaded = st.file_uploader("Upload CSV", type=["csv"], key="receptor_csv")
        if uploaded:
            df = pd.read_csv(uploaded)
            st.dataframe(df.head(10))
            if st.button("Import Receptors"):
                count = 0
                for _, row in df.iterrows():
                    z = row.get("z_elev", 0.0)
                    receptors.add_discrete_receptor(
                        DiscreteReceptor(float(row["x"]), float(row["y"]), float(z))
                    )
                    count += 1
                st.success(f"Imported {count} discrete receptors")
                st.rerun()

    # Summary
    st.subheader("Receptor Summary")
    n_cart = sum(g.x_num * g.y_num for g in receptors.cartesian_grids)
    n_polar = sum(g.dist_num * g.dir_num for g in receptors.polar_grids)
    n_disc = len(receptors.discrete_receptors)
    st.metric("Total Receptors", n_cart + n_polar + n_disc)
    col1, col2, col3 = st.columns(3)
    col1.metric("Cartesian", n_cart)
    col2.metric("Polar", n_polar)
    col3.metric("Discrete", n_disc)

    if receptors.cartesian_grids or receptors.polar_grids or receptors.discrete_receptors:
        if st.button("Clear All Receptors", type="secondary"):
            st.session_state["project_receptors"] = ReceptorPathway()
            st.rerun()


def page_meteorology():
    """Meteorology configuration page."""
    st.header("Meteorology")

    met = st.session_state["project_meteorology"]

    st.subheader("Meteorology Files")
    sfc_file = st.text_input("Surface File (.sfc)", value=met.surface_file or "")
    pfl_file = st.text_input("Profile File (.pfl)", value=met.profile_file or "")

    st.subheader("File Upload (optional)")
    st.info("Upload met files to a working directory for the AERMOD run.")
    sfc_upload = st.file_uploader("Upload Surface File", type=["sfc"], key="sfc_upload")
    pfl_upload = st.file_uploader("Upload Profile File", type=["pfl"], key="pfl_upload")

    work_dir = st.text_input("Working Directory", value=str(Path.cwd()))

    if sfc_upload:
        sfc_path = Path(work_dir) / sfc_upload.name
        sfc_path.write_bytes(sfc_upload.getvalue())
        sfc_file = str(sfc_path)
        st.success(f"Saved: {sfc_path}")

    if pfl_upload:
        pfl_path = Path(work_dir) / pfl_upload.name
        pfl_path.write_bytes(pfl_upload.getvalue())
        pfl_file = str(pfl_path)
        st.success(f"Saved: {pfl_path}")

    # Save
    st.session_state["project_meteorology"] = MeteorologyPathway(
        surface_file=sfc_file,
        profile_file=pfl_file,
    )
    st.success("Meteorology settings saved.")


def page_run_aermod():
    """Run AERMOD page with validation, preview, and execution."""
    st.header("Run AERMOD")

    project = SessionStateManager.get_project()

    # Validation
    st.subheader("Validation")
    if HAS_VALIDATOR:
        try:
            validator = Validator()
            result = validator.validate(project)
            if result.errors:
                for err in result.errors:
                    st.error(f"{err.field}: {err.message}")
            if result.warnings:
                for warn in result.warnings:
                    st.warning(f"{warn.field}: {warn.message}")
            if not result.errors and not result.warnings:
                st.success("All validation checks passed.")
        except Exception as e:
            st.warning(f"Validation error: {e}")
    else:
        st.info("Validator module not available.")

    # Input preview
    st.subheader("Generated Input File")
    try:
        inp_text = project.to_aermod_input(validate=False)
        with st.expander("View AERMOD Input File", expanded=False):
            st.code(inp_text, language="text")
    except Exception as e:
        st.error(f"Error generating input: {e}")
        inp_text = None

    # Output configuration
    st.subheader("Output Configuration")
    col1, col2 = st.columns(2)
    with col1:
        receptor_table = st.checkbox("Receptor Table", value=True)
        max_table = st.checkbox("Max Value Table", value=True)
    with col2:
        postfile_enabled = st.checkbox("Generate POSTFILE", value=False)

    st.session_state["project_output"] = OutputPathway(
        receptor_table=receptor_table,
        max_table=max_table,
    )

    # Run
    st.subheader("Execute AERMOD")
    work_dir = st.text_input("Working Directory", value=str(Path.cwd()), key="run_workdir")
    aermod_exe = st.text_input("AERMOD Executable Path", value="aermod")

    if st.button("Run AERMOD", type="primary"):
        if not inp_text:
            st.error("Cannot run: input file generation failed.")
            return

        with st.spinner("Running AERMOD..."):
            try:
                inp_path = Path(work_dir) / "aermod.inp"
                inp_path.write_text(inp_text)

                if HAS_RUNNER:
                    result = run_aermod(str(inp_path), aermod_executable=aermod_exe)
                    st.session_state["run_result"] = result

                    if result.success:
                        st.success(f"AERMOD completed successfully. Output: {result.output_file}")

                        # Auto-parse results
                        if HAS_PARSER and result.output_file:
                            parsed = parse_aermod_output(result.output_file)
                            st.session_state["parsed_results"] = parsed
                            st.info("Results parsed automatically. Go to Results Viewer.")
                    else:
                        st.error(f"AERMOD failed. Return code: {result.return_code}")
                        if result.stderr:
                            st.code(result.stderr)
                else:
                    st.error("Runner module not available.")
            except Exception as e:
                st.error(f"Execution error: {e}")


def page_results_viewer():
    """Results Viewer page."""
    st.header("Results Viewer")

    results = st.session_state.get("parsed_results")

    # Allow loading from file
    st.subheader("Load Results")
    uploaded_out = st.file_uploader("Upload AERMOD .out file", type=["out"], key="out_upload")
    if uploaded_out:
        with tempfile.NamedTemporaryFile(suffix=".out", delete=False, mode="w") as f:
            f.write(uploaded_out.getvalue().decode("utf-8"))
            f.flush()
            if HAS_PARSER:
                results = parse_aermod_output(f.name)
                st.session_state["parsed_results"] = results
                st.success("Results loaded and parsed.")

    if results is None:
        st.info("No results available. Run AERMOD or upload an .out file.")
        return

    # Summary
    st.subheader("Run Summary")
    if hasattr(results, "run_info") and results.run_info:
        info = results.run_info
        col1, col2, col3 = st.columns(3)
        col1.metric("Sources", getattr(info, "num_sources", "N/A"))
        col2.metric("Receptors", getattr(info, "num_receptors", "N/A"))
        col3.metric("Pollutant", getattr(info, "pollutant_id", "N/A"))

    # Tabs for different views
    tab_map, tab_static, tab_stats = st.tabs(["Interactive Map", "Static Plots", "Statistics"])

    # Get available averaging periods
    avail_periods = list(getattr(results, "concentrations", {}).keys())
    if not avail_periods:
        avail_periods = ["ANNUAL"]

    with tab_map:
        st.subheader("Concentration Map")
        period = st.selectbox("Averaging Period", avail_periods, key="map_period")

        conc_df = results.get_concentrations(period)
        if conc_df is not None and not conc_df.empty:
            transformer = SessionStateManager.get_transformer()
            if transformer and HAS_FOLIUM:
                editor = MapEditor(
                    transformer=transformer,
                    center=(st.session_state["center_lat"], st.session_state["center_lon"]),
                )
                editor.render_concentration_map(
                    conc_df, st.session_state["project_sources"].sources,
                )
            else:
                st.warning("Install pyproj and streamlit-folium for interactive maps.")
        else:
            st.info(f"No concentration data for {period}.")

    with tab_static:
        st.subheader("Static Plots")
        period2 = st.selectbox("Averaging Period", avail_periods, key="static_period")

        if HAS_VIZ:
            viz = AERMODVisualizer(results)

            # Contour plot
            try:
                fig = viz.plot_contours(averaging_period=period2)
                if fig:
                    st.pyplot(fig)
                    plt.close(fig)
            except Exception as e:
                st.warning(f"Could not generate contour plot: {e}")
        else:
            st.info("Install matplotlib for static plots.")

    with tab_stats:
        st.subheader("Concentration Statistics")
        period3 = st.selectbox("Averaging Period", avail_periods, key="stats_period")

        conc_df3 = results.get_concentrations(period3)
        if conc_df3 is not None and not conc_df3.empty:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Maximum", f"{conc_df3['concentration'].max():.4g}")
            col2.metric("Mean", f"{conc_df3['concentration'].mean():.4g}")
            col3.metric("Median", f"{conc_df3['concentration'].median():.4g}")
            col4.metric("Std Dev", f"{conc_df3['concentration'].std():.4g}")

            # Percentile table
            st.subheader("Percentile Distribution")
            percentiles = [50, 75, 90, 95, 98, 99, 99.5, 100]
            pct_data = {
                f"{p}th": conc_df3["concentration"].quantile(p / 100)
                for p in percentiles
            }
            st.dataframe(pd.DataFrame([pct_data]), use_container_width=True)

            # Top receptors
            st.subheader("Top 10 Receptor Concentrations")
            top10 = conc_df3.nlargest(10, "concentration")
            st.dataframe(top10, use_container_width=True)

            # Threshold exceedance
            st.subheader("Exceedance Analysis")
            threshold = st.number_input("Threshold Value", value=0.0, format="%.4g")
            if threshold > 0:
                exceed = conc_df3[conc_df3["concentration"] > threshold]
                st.metric(
                    "Receptors Exceeding Threshold",
                    f"{len(exceed)} / {len(conc_df3)} ({100 * len(exceed) / len(conc_df3):.1f}%)",
                )


def page_export():
    """Export page for GeoTIFF, Shapefile, and other formats."""
    st.header("Export")

    results = st.session_state.get("parsed_results")
    transformer = SessionStateManager.get_transformer()

    if not HAS_GEO:
        st.error("Geospatial module required. Install with: pip install pyaermod[geo]")
        return

    if not transformer:
        st.warning("Configure UTM zone in Project Setup first.")
        return

    avail_periods = []
    if results:
        avail_periods = list(getattr(results, "concentrations", {}).keys())

    # Export format selection
    fmt = st.selectbox("Export Format", [
        "GeoTIFF (.tif)",
        "GeoPackage (.gpkg)",
        "Shapefile (.shp)",
        "GeoJSON (.geojson)",
        "CSV with Lat/Lon",
    ])

    if fmt == "GeoTIFF (.tif)":
        st.subheader("GeoTIFF Export")
        if not avail_periods:
            st.info("No concentration results to export. Run AERMOD first.")
            return

        period = st.selectbox("Averaging Period", avail_periods, key="tif_period")
        resolution = st.number_input("Resolution (m)", value=50.0, min_value=1.0)
        method = st.selectbox("Interpolation", ["cubic", "linear", "nearest"])

        if st.button("Generate GeoTIFF"):
            conc_df = results.get_concentrations(period)
            if conc_df is not None and not conc_df.empty:
                with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
                    exporter = RasterExporter(transformer)
                    exporter.export_geotiff(
                        conc_df, f.name, resolution=resolution, method=method,
                    )
                    with open(f.name, "rb") as tif:
                        st.download_button(
                            "Download GeoTIFF",
                            tif.read(),
                            file_name=f"concentration_{period}.tif",
                            mime="image/tiff",
                        )

    elif fmt in ("GeoPackage (.gpkg)", "Shapefile (.shp)", "GeoJSON (.geojson)"):
        driver_map = {
            "GeoPackage (.gpkg)": ("GPKG", ".gpkg"),
            "Shapefile (.shp)": ("ESRI Shapefile", ".shp"),
            "GeoJSON (.geojson)": ("GeoJSON", ".geojson"),
        }
        driver, ext = driver_map[fmt]

        st.subheader(f"{fmt.split('(')[0].strip()} Export")

        export_what = st.multiselect(
            "What to export",
            ["Sources", "Receptors", "Concentrations (points)", "Concentrations (contours)"],
        )

        if "Concentrations (points)" in export_what or "Concentrations (contours)" in export_what:
            if avail_periods:
                period = st.selectbox("Averaging Period", avail_periods, key="vec_period")
            else:
                st.warning("No results available.")

        if st.button("Generate Export"):
            factory = GeoDataFrameFactory(transformer)

            with tempfile.TemporaryDirectory() as tmpdir:
                files_to_download = {}

                if "Sources" in export_what:
                    sources = st.session_state["project_sources"].sources
                    if sources:
                        path = Path(tmpdir) / f"sources{ext}"
                        VectorExporter(factory).export_sources(sources, path, driver)
                        files_to_download["sources"] = path

                if "Receptors" in export_what:
                    recs = st.session_state["project_receptors"]
                    path = Path(tmpdir) / f"receptors{ext}"
                    VectorExporter(factory).export_receptors(recs, path, driver)
                    files_to_download["receptors"] = path

                if results and avail_periods:
                    conc_df = results.get_concentrations(period)
                    if conc_df is not None and not conc_df.empty:
                        if "Concentrations (points)" in export_what:
                            path = Path(tmpdir) / f"conc_points{ext}"
                            VectorExporter(factory).export_concentrations(
                                conc_df, path, driver, as_contours=False,
                            )
                            files_to_download["conc_points"] = path
                        if "Concentrations (contours)" in export_what:
                            path = Path(tmpdir) / f"conc_contours{ext}"
                            VectorExporter(factory).export_concentrations(
                                conc_df, path, driver, as_contours=True,
                            )
                            files_to_download["conc_contours"] = path

                for name, path in files_to_download.items():
                    if path.exists():
                        with open(path, "rb") as f:
                            st.download_button(
                                f"Download {name}{ext}",
                                f.read(),
                                file_name=f"{name}{ext}",
                                key=f"dl_{name}",
                            )

    elif fmt == "CSV with Lat/Lon":
        st.subheader("CSV Export with Geographic Coordinates")
        if not avail_periods:
            st.info("No concentration results to export.")
            return

        period = st.selectbox("Averaging Period", avail_periods, key="csv_period")
        conc_df = results.get_concentrations(period)
        if conc_df is not None and not conc_df.empty:
            df_geo = transformer.transform_dataframe(conc_df)
            csv = df_geo.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv.encode("utf-8"),
                file_name=f"concentration_{period}_latlon.csv",
                mime="text/csv",
            )
            st.dataframe(df_geo.head(20), use_container_width=True)


# ============================================================================
# MAIN APPLICATION
# ============================================================================


def main():
    """Main Streamlit application entry point."""
    if not HAS_STREAMLIT:
        raise ImportError(
            "Streamlit is required for the GUI. Install with: pip install pyaermod[gui]"
        )
    st.set_page_config(
        page_title="PyAERMOD",
        page_icon=":wind_face:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    SessionStateManager.initialize()

    # Sidebar navigation
    st.sidebar.title("PyAERMOD")
    st.sidebar.caption("Atmospheric Dispersion Modeling")

    pages = {
        "Project Setup": page_project_setup,
        "Source Editor": page_source_editor,
        "Receptor Editor": page_receptor_editor,
        "Meteorology": page_meteorology,
        "Run AERMOD": page_run_aermod,
        "Results Viewer": page_results_viewer,
        "Export": page_export,
    }

    # Workflow progress indicator
    st.sidebar.markdown("---")
    st.sidebar.subheader("Workflow Progress")
    has_sources = len(st.session_state["project_sources"].sources) > 0
    has_receptors = (
        len(st.session_state["project_receptors"].cartesian_grids) > 0
        or len(st.session_state["project_receptors"].polar_grids) > 0
        or len(st.session_state["project_receptors"].discrete_receptors) > 0
    )
    has_met = bool(st.session_state["project_meteorology"].surface_file)
    has_results = st.session_state.get("parsed_results") is not None

    st.sidebar.checkbox("Project configured", value=True, disabled=True)
    st.sidebar.checkbox("Sources defined", value=has_sources, disabled=True)
    st.sidebar.checkbox("Receptors defined", value=has_receptors, disabled=True)
    st.sidebar.checkbox("Meteorology set", value=has_met, disabled=True)
    st.sidebar.checkbox("Results available", value=has_results, disabled=True)

    st.sidebar.markdown("---")
    selection = st.sidebar.radio("Navigation", list(pages.keys()))

    # Render selected page
    pages[selection]()


if __name__ == "__main__":
    main()

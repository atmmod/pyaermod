"""
PyAERMOD Streamlit GUI

Interactive web-based GUI for the full AERMOD workflow:
project setup -> source/receptor editing on maps -> run AERMOD -> visualize -> export.

Launch with:
    streamlit run -m pyaermod.gui
    # or
    pyaermod-gui

Requires: pip install pyaermod[gui]
"""

import dataclasses
import json
import math
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

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
from .input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    EventPathway,
    EventPeriod,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    PointSource,
    PolarGrid,
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
    from .geospatial import (
        ContourGenerator,  # noqa: F401
        CoordinateTransformer,
        GeoDataFrameFactory,
        RasterExporter,
        VectorExporter,
        export_concentration_geotiff,  # noqa: F401
        export_concentration_shapefile,  # noqa: F401
    )
    HAS_GEO = True
except ImportError:
    HAS_GEO = False

try:
    from .runner import AERMODRunner, run_aermod  # noqa: F401
    HAS_RUNNER = True
except ImportError:
    HAS_RUNNER = False

try:
    from .output_parser import AERMODOutputParser, parse_aermod_output  # noqa: F401
    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False

try:
    from .postfile import (
        PostfileParser,  # noqa: F401
        PostfileResult,  # noqa: F401
        UnformattedPostfileParser,  # noqa: F401
        read_postfile,
    )
    HAS_POSTFILE = True
except ImportError:
    HAS_POSTFILE = False

try:
    from .advanced_viz import AdvancedVisualizer
    HAS_ADVANCED_VIZ = True
except ImportError:
    HAS_ADVANCED_VIZ = False

try:
    from .validator import Validator
    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False

try:
    from .visualization import AERMODVisualizer
    HAS_VIZ = True
except ImportError:
    HAS_VIZ = False

try:
    from .terrain import AERMAPOutputParser
    HAS_TERRAIN = True
except ImportError:
    HAS_TERRAIN = False

try:
    from .bpip import BPIPCalculator, BPIPResult, Building  # noqa: F401
    HAS_BPIP = True
except ImportError:
    HAS_BPIP = False

try:
    from .aermet import (
        AERMETStage1,
        AERMETStage2,
        AERMETStage3,
        AERMETStation,
        UpperAirStation,
    )
    HAS_AERMET = True
except ImportError:
    HAS_AERMET = False


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
            "buildings": [],
            "aermet_mode": "files",
            "aermet_stage1": None,
            "aermet_stage2": None,
            "aermet_stage3": None,
            "project_events": None,
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
            events=st.session_state.get("project_events"),
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
# PROJECT SERIALIZER
# ============================================================================


class ProjectSerializer:
    """Serialize/deserialize PyAERMOD GUI session state to/from JSON."""

    SAVE_FORMAT_VERSION = 1

    SOURCE_TYPE_MAP = {
        "PointSource": PointSource,
        "AreaSource": AreaSource,
        "AreaCircSource": AreaCircSource,
        "AreaPolySource": AreaPolySource,
        "VolumeSource": VolumeSource,
        "LineSource": LineSource,
        "RLineSource": RLineSource,
        "RLineExtSource": RLineExtSource,
        "BuoyLineSource": BuoyLineSource,
        "OpenPitSource": OpenPitSource,
    }

    RECEPTOR_TYPE_MAP = {
        "CartesianGrid": CartesianGrid,
        "PolarGrid": PolarGrid,
        "DiscreteReceptor": DiscreteReceptor,
    }

    PATHWAY_FIELDS = [
        "project_control", "project_sources", "project_receptors",
        "project_meteorology", "project_output",
    ]

    GEO_FIELDS = ["utm_zone", "hemisphere", "datum", "center_lat", "center_lon"]

    class _Encoder(json.JSONEncoder):
        """Custom JSON encoder for dataclasses and Enums."""

        def default(self, obj):
            if isinstance(obj, Enum):
                return {"_enum": f"{type(obj).__name__}.{obj.name}"}
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                d = dataclasses.asdict(obj)
                d["_type"] = type(obj).__name__
                return d
            return super().default(obj)

    @classmethod
    def serialize_session_state(cls) -> str:
        """Convert current session state to JSON string."""
        from pyaermod import __version__

        data = {
            "pyaermod_version": __version__,
            "save_format_version": cls.SAVE_FORMAT_VERSION,
        }

        # Pathways
        for key in cls.PATHWAY_FIELDS:
            obj = st.session_state.get(key)
            if obj is not None:
                if key == "project_sources":
                    # Inject _type for each source
                    src_list = []
                    for src in obj.sources:
                        d = dataclasses.asdict(src)
                        d["_type"] = type(src).__name__
                        src_list.append(d)
                    bg_data = None
                    if obj.background is not None:
                        bg_data = dataclasses.asdict(obj.background)
                    data[key] = {"sources": src_list, "background": bg_data}
                elif key == "project_receptors":
                    data[key] = {
                        "cartesian_grids": [dataclasses.asdict(g) for g in obj.cartesian_grids],
                        "polar_grids": [dataclasses.asdict(g) for g in obj.polar_grids],
                        "discrete_receptors": [dataclasses.asdict(r) for r in obj.discrete_receptors],
                        "elevation_units": obj.elevation_units,
                    }
                else:
                    data[key] = dataclasses.asdict(obj)

        # Geo settings
        data["geo_settings"] = {k: st.session_state.get(k) for k in cls.GEO_FIELDS}

        # Buildings (for BPIP)
        buildings = st.session_state.get("buildings", [])
        data["buildings"] = [dataclasses.asdict(b) for b in buildings]

        # AERMET config
        aermet_config = {"mode": st.session_state.get("aermet_mode", "files")}
        for key in ("aermet_stage1", "aermet_stage2", "aermet_stage3"):
            obj = st.session_state.get(key)
            if obj is not None:
                d = dataclasses.asdict(obj)
                d["_type"] = type(obj).__name__
                aermet_config[key] = d
            else:
                aermet_config[key] = None
        data["aermet_config"] = aermet_config

        # Event processing
        events = st.session_state.get("project_events")
        if events is not None:
            data["project_events"] = dataclasses.asdict(events)
        else:
            data["project_events"] = None

        return json.dumps(data, cls=cls._Encoder, indent=2)

    @classmethod
    def deserialize_session_state(cls, json_str: str) -> dict:
        """Parse JSON and reconstruct session state objects."""
        data = json.loads(json_str)

        version = data.get("save_format_version", 0)
        if version > cls.SAVE_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported save format version {version} "
                f"(max supported: {cls.SAVE_FORMAT_VERSION})"
            )

        result = {}

        # Control pathway
        if "project_control" in data:
            result["project_control"] = cls._deserialize_control(data["project_control"])

        # Sources
        if "project_sources" in data:
            sources = []
            for src_data in data["project_sources"].get("sources", []):
                sources.append(cls._deserialize_source(src_data))
            sp = SourcePathway()
            sp.sources = sources
            bg_data = data["project_sources"].get("background")
            if bg_data:
                sectors = None
                if bg_data.get("sectors"):
                    sectors = [
                        BackgroundSector(**s) for s in bg_data["sectors"]
                    ]
                sector_values = None
                if bg_data.get("sector_values"):
                    sector_values = {
                        (item[0], item[1]): item[2]
                        for item in bg_data["sector_values"]
                    }
                sp.background = BackgroundConcentration(
                    uniform_value=bg_data.get("uniform_value"),
                    period_values=bg_data.get("period_values"),
                    sectors=sectors,
                    sector_values=sector_values,
                )
            result["project_sources"] = sp

        # Receptors
        if "project_receptors" in data:
            result["project_receptors"] = cls._deserialize_receptors(data["project_receptors"])

        # Meteorology
        if "project_meteorology" in data:
            d = data["project_meteorology"]
            d.pop("_type", None)
            result["project_meteorology"] = MeteorologyPathway(**d)

        # Output
        if "project_output" in data:
            d = data["project_output"]
            d.pop("_type", None)
            result["project_output"] = OutputPathway(**d)

        # Geo settings
        geo = data.get("geo_settings", {})
        for k in cls.GEO_FIELDS:
            if k in geo:
                result[k] = geo[k]

        # Buildings
        if "buildings" in data:
            try:
                from .bpip import Building  # noqa: F401 — guard import
                result["buildings"] = [cls._deserialize_building(b) for b in data["buildings"]]
            except ImportError:
                result["buildings"] = []

        # AERMET config
        aermet = data.get("aermet_config", {})
        if aermet:
            result["aermet_mode"] = aermet.get("mode", "files")
            for key, stage_cls in [
                ("aermet_stage1", AERMETStage1 if HAS_AERMET else None),
                ("aermet_stage2", AERMETStage2 if HAS_AERMET else None),
                ("aermet_stage3", AERMETStage3 if HAS_AERMET else None),
            ]:
                d = aermet.get(key)
                if d is not None and stage_cls is not None:
                    result[key] = cls._deserialize_aermet_stage(d, stage_cls)
                else:
                    result[key] = None

        # Events
        events_data = data.get("project_events")
        if events_data:
            event_list = [
                EventPeriod(**ep) for ep in events_data.get("events", [])
            ]
            result["project_events"] = EventPathway(events=event_list)
        else:
            result["project_events"] = None

        return result

    @classmethod
    def _resolve_enum(cls, value):
        """Resolve an enum dict like {'_enum': 'PollutantType.PM25'} to actual Enum."""
        if isinstance(value, dict) and "_enum" in value:
            enum_str = value["_enum"]
            cls_name, member_name = enum_str.split(".", 1)
            enum_classes = {
                "PollutantType": PollutantType,
                "TerrainType": TerrainType,
                "SourceType": SourceType,
            }
            enum_cls = enum_classes.get(cls_name)
            if enum_cls:
                return enum_cls[member_name]
        return value

    @classmethod
    def _deserialize_control(cls, data: dict) -> ControlPathway:
        """Reconstruct ControlPathway with enums."""
        d = dict(data)
        d.pop("_type", None)
        if "pollutant_id" in d:
            d["pollutant_id"] = cls._resolve_enum(d["pollutant_id"])
        if "terrain_type" in d:
            d["terrain_type"] = cls._resolve_enum(d["terrain_type"])
        return ControlPathway(**d)

    @classmethod
    def _deserialize_source(cls, data: dict):
        """Reconstruct a source object from dict with _type key."""
        d = dict(data)
        type_name = d.pop("_type", None)
        if type_name not in cls.SOURCE_TYPE_MAP:
            raise ValueError(f"Unknown source type: {type_name}")

        src_cls = cls.SOURCE_TYPE_MAP[type_name]

        # Handle AreaPolySource: convert vertex lists back to tuples
        if type_name == "AreaPolySource" and "vertices" in d:
            d["vertices"] = [tuple(v) for v in d["vertices"]]

        # Handle BuoyLineSource: reconstruct nested BuoyLineSegments
        if type_name == "BuoyLineSource" and "line_segments" in d:
            segments = []
            for seg_data in d["line_segments"]:
                seg_data.pop("_type", None)
                segments.append(BuoyLineSegment(**seg_data))
            d["line_segments"] = segments

        return src_cls(**d)

    @classmethod
    def _deserialize_receptors(cls, data: dict) -> ReceptorPathway:
        """Reconstruct ReceptorPathway with grids and discrete receptors."""
        rp = ReceptorPathway()
        rp.elevation_units = data.get("elevation_units", "METERS")

        for g in data.get("cartesian_grids", []):
            g.pop("_type", None)
            rp.cartesian_grids.append(CartesianGrid(**g))
        for g in data.get("polar_grids", []):
            g.pop("_type", None)
            rp.polar_grids.append(PolarGrid(**g))
        for r in data.get("discrete_receptors", []):
            r.pop("_type", None)
            rp.discrete_receptors.append(DiscreteReceptor(**r))

        return rp

    @classmethod
    def _deserialize_building(cls, data: dict):
        """Reconstruct a Building object from dict."""
        from .bpip import Building
        d = dict(data)
        d.pop("_type", None)
        # Convert corner lists to tuples
        if "corners" in d:
            d["corners"] = [tuple(c) for c in d["corners"]]
        # Convert tier lists to tuples
        if d.get("tiers") is not None:
            d["tiers"] = [tuple(t) for t in d["tiers"]]
        return Building(**d)

    @classmethod
    def _deserialize_aermet_stage(cls, data: dict, stage_cls):
        """Reconstruct an AERMET stage object from dict."""
        d = dict(data)
        d.pop("_type", None)

        # Reconstruct nested station objects
        if "surface_station" in d and d["surface_station"] is not None:
            sd = dict(d["surface_station"])
            sd.pop("_type", None)
            d["surface_station"] = AERMETStation(**sd)
        if "upper_air_station" in d and d["upper_air_station"] is not None:
            ud = dict(d["upper_air_station"])
            ud.pop("_type", None)
            d["upper_air_station"] = UpperAirStation(**ud)
        if "station" in d and d["station"] is not None:
            sd = dict(d["station"])
            sd.pop("_type", None)
            d["station"] = AERMETStation(**sd)

        return stage_cls(**d)


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
        from .input_generator import (
            AreaCircSource,
            AreaPolySource,
            BuoyLineSource,
            LineSource,
            OpenPitSource,
            RLineExtSource,
            RLineSource,
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
            elif isinstance(src, AreaCircSource):
                center = self._utm_to_latlon(src.x_coord, src.y_coord)
                folium.Circle(
                    center, radius=src.radius, color="orange",
                    fill=True, fill_opacity=0.3,
                    popup=f"{sid} (AreaCirc, r={src.radius}m)",
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

    def add_buildings_to_map(self, m: "folium.Map", buildings: list):
        """Add building footprints to a folium map."""
        for bldg in buildings:
            verts = [self._utm_to_latlon(x, y) for x, y in bldg.corners]
            verts.append(verts[0])  # close polygon
            folium.Polygon(
                verts, color="gray", fill=True, fill_opacity=0.5,
                popup=f"{bldg.building_id} (h={bldg.height}m)",
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

    def render_source_editor(self, sources: list, buildings: Optional[list] = None) -> Optional[Tuple[float, float]]:
        """Render interactive map for source placement. Returns clicked UTM coords."""
        if not HAS_FOLIUM:
            st.warning("folium and streamlit-folium required for interactive maps.")
            return None

        m = self._create_base_map()
        self.add_sources_to_map(m, sources)
        if buildings:
            self.add_buildings_to_map(m, buildings)

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
    def render_area_circ_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[AreaCircSource]:
        with st.form("area_circ_source_form"):
            st.subheader("Circular Area Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="CIRC1")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                rh = st.number_input("Release Height (m)", value=2.0, min_value=0.0)
                radius = st.number_input("Radius (m)", value=100.0, min_value=0.1)
                nverts = st.number_input("Num Vertices", value=20, min_value=3, step=1)
            erate = st.number_input("Emission Rate (g/s/m2)", value=0.0001, format="%.6f")

            if st.form_submit_button("Add Circular Area Source"):
                return AreaCircSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    release_height=rh, radius=radius,
                    num_vertices=int(nverts), emission_rate=erate,
                )
        return None

    @staticmethod
    def render_area_poly_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[AreaPolySource]:
        nv = st.number_input(
            "Number of Vertices", value=4, min_value=3, max_value=20, step=1,
            key="poly_vertex_count",
        )
        with st.form("area_poly_source_form"):
            st.subheader("Polygonal Area Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="POLY1")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                rh = st.number_input("Release Height (m)", value=2.0, min_value=0.0)
                erate = st.number_input("Emission Rate (g/s/m2)", value=0.0001, format="%.6f")

            st.markdown("**Vertex Coordinates (UTM m)**")
            vertices = []
            for i in range(int(nv)):
                c1, c2 = st.columns(2)
                with c1:
                    vx = st.number_input(
                        f"V{i+1} X", value=default_x + i * 50.0,
                        format="%.2f", key=f"poly_vx_{i}",
                    )
                with c2:
                    vy = st.number_input(
                        f"V{i+1} Y", value=default_y + (i % 2) * 50.0,
                        format="%.2f", key=f"poly_vy_{i}",
                    )
                vertices.append((vx, vy))

            if st.form_submit_button("Add Polygon Source"):
                return AreaPolySource(
                    source_id=sid, vertices=vertices, base_elevation=elev,
                    release_height=rh, emission_rate=erate,
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
# BUILDING FORM FACTORY (BPIP)
# ============================================================================


class BuildingFormFactory:
    """Generates Streamlit form widgets for building definitions."""

    @staticmethod
    def render_building_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional["Building"]:
        if not HAS_BPIP:
            st.warning("BPIP module not available.")
            return None

        with st.form("building_form"):
            st.subheader("Building Definition")
            col1, col2 = st.columns(2)
            with col1:
                bid = st.text_input("Building ID", value="BLDG1")
                height = st.number_input("Building Height (m)", value=20.0, min_value=0.1)
            with col2:
                st.markdown("**4 corners (counterclockwise)**")

            st.markdown("**Corner Coordinates (UTM m)**")
            # Default: rectangular building around center
            default_corners = [
                (default_x, default_y),
                (default_x + 50, default_y),
                (default_x + 50, default_y + 30),
                (default_x, default_y + 30),
            ]
            corners = []
            for i in range(4):
                c1, c2 = st.columns(2)
                with c1:
                    cx = st.number_input(
                        f"Corner {i+1} X", value=default_corners[i][0],
                        format="%.2f", key=f"bldg_cx_{i}",
                    )
                with c2:
                    cy = st.number_input(
                        f"Corner {i+1} Y", value=default_corners[i][1],
                        format="%.2f", key=f"bldg_cy_{i}",
                    )
                corners.append((cx, cy))

            if st.form_submit_button("Add Building"):
                try:
                    return Building(
                        building_id=bid, corners=corners, height=height,
                    )
                except ValueError as e:
                    st.error(str(e))
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

    # Deposition options
    with st.expander("Deposition Options"):
        dep_col1, dep_col2 = st.columns(2)
        with dep_col1:
            calc_ddep = st.checkbox(
                "Dry Deposition (DDEP)",
                value=st.session_state["project_control"].calculate_dry_deposition,
                key="setup_ddep",
            )
            calc_wdep = st.checkbox(
                "Wet Deposition (WDEP)",
                value=st.session_state["project_control"].calculate_wet_deposition,
                key="setup_wdep",
            )
        with dep_col2:
            calc_depos = st.checkbox(
                "Total Deposition (DEPOS)",
                value=st.session_state["project_control"].calculate_deposition,
                key="setup_depos",
            )

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
        calculate_dry_deposition=calc_ddep,
        calculate_wet_deposition=calc_wdep,
        calculate_deposition=calc_depos,
    )

    st.success("Project settings saved automatically.")

    # ------------------------------------------------------------------
    # Project Save / Load
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Project File")
    col_save, col_load = st.columns(2)

    with col_save:
        json_str = ProjectSerializer.serialize_session_state()
        st.download_button(
            "Download Project (.json)",
            json_str.encode("utf-8"),
            file_name="pyaermod_project.json",
            mime="application/json",
        )

    with col_load:
        uploaded = st.file_uploader("Load Project", type=["json"], key="project_load")
        if uploaded:
            raw = uploaded.getvalue().decode("utf-8")
            try:
                new_state = ProjectSerializer.deserialize_session_state(raw)
                for key, value in new_state.items():
                    st.session_state[key] = value
                st.success("Project loaded successfully.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to load project: {e}")


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
            clicked_utm = editor.render_source_editor(
                sources, st.session_state.get("buildings", []),
            )
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
        elif source_type == "Area (Circular)":
            new_source = SourceFormFactory.render_area_circ_source_form(default_x, default_y)
        elif source_type == "Area (Polygon)":
            new_source = SourceFormFactory.render_area_poly_source_form(default_x, default_y)
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

    # ------------------------------------------------------------------
    # Building Downwash (BPIP)
    # ------------------------------------------------------------------
    if HAS_BPIP:
        st.markdown("---")
        st.subheader("Building Downwash (BPIP)")

        buildings = st.session_state.get("buildings", [])

        with st.expander("Add Building", expanded=not bool(buildings)):
            new_building = BuildingFormFactory.render_building_form(
                default_x, default_y,
            )
            if new_building:
                st.session_state["buildings"].append(new_building)
                st.success(f"Added building: {new_building.building_id}")
                st.rerun()

        if buildings:
            bldg_rows = []
            for b in buildings:
                centroid = b.get_centroid()
                bldg_rows.append({
                    "ID": b.building_id,
                    "Height (m)": b.height,
                    "X (centroid)": f"{centroid[0]:.2f}",
                    "Y (centroid)": f"{centroid[1]:.2f}",
                    "Area (m2)": f"{b.get_footprint_area():.1f}",
                })
            st.dataframe(pd.DataFrame(bldg_rows), use_container_width=True)

            del_idx = st.selectbox(
                "Select building to delete",
                range(len(buildings)),
                format_func=lambda i: buildings[i].building_id,
                key="bldg_delete_idx",
            )
            if st.button("Delete Building", type="secondary"):
                del st.session_state["buildings"][del_idx]
                st.rerun()

            # Run BPIP calculation
            point_sources = [s for s in sources if isinstance(s, PointSource)]
            if point_sources:
                st.markdown("**Calculate Downwash**")
                col_src, col_bldg = st.columns(2)
                with col_src:
                    src_idx = st.selectbox(
                        "Point Source",
                        range(len(point_sources)),
                        format_func=lambda i: point_sources[i].source_id,
                        key="bpip_src_idx",
                    )
                with col_bldg:
                    bldg_idx = st.selectbox(
                        "Building",
                        range(len(buildings)),
                        format_func=lambda i: buildings[i].building_id,
                        key="bpip_bldg_idx",
                    )
                if st.button("Run BPIP Calculation", type="primary"):
                    ps = point_sources[src_idx]
                    bldg = buildings[bldg_idx]
                    try:
                        calc = BPIPCalculator(bldg, ps.x_coord, ps.y_coord)
                        result = calc.calculate_all()
                        ps.building_height = result.buildhgt
                        ps.building_width = result.buildwid
                        ps.building_length = result.buildlen
                        ps.building_x_offset = result.xbadj
                        ps.building_y_offset = result.ybadj
                        st.success(
                            f"Downwash calculated for {ps.source_id} "
                            f"from {bldg.building_id}"
                        )
                        with st.expander("View BPIP Results"):
                            dirs = [f"{(i+1)*10}\u00b0" for i in range(36)]
                            bpip_df = pd.DataFrame({
                                "Direction": dirs,
                                "BUILDHGT": result.buildhgt,
                                "BUILDWID": result.buildwid,
                                "BUILDLEN": result.buildlen,
                                "XBADJ": result.xbadj,
                                "YBADJ": result.ybadj,
                            })
                            st.dataframe(bpip_df, use_container_width=True)
                    except Exception as e:
                        st.error(f"BPIP calculation failed: {e}")
            else:
                st.info("Add point sources to calculate building downwash.")

    # ------------------------------------------------------------------
    # Background Concentration
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Background Concentration")

    bg = st.session_state["project_sources"].background
    bg_mode = st.radio(
        "Background Mode",
        ["None", "Uniform", "Period-specific", "Sector-dependent"],
        index=0 if bg is None else (
            1 if bg.uniform_value is not None else (
                2 if bg.period_values else 3
            )
        ),
        key="bg_mode",
        horizontal=True,
    )

    if bg_mode == "Uniform":
        bg_val = st.number_input(
            "Background Concentration (ug/m3)", min_value=0.0, value=0.0,
            key="bg_uniform_val",
        )
        st.session_state["project_sources"].background = BackgroundConcentration(
            uniform_value=bg_val,
        )
    elif bg_mode == "Period-specific":
        avg_periods = st.session_state["project_control"].averaging_periods
        if not avg_periods:
            avg_periods = ["ANNUAL"]
        period_vals = {}
        for period in avg_periods:
            val = st.number_input(
                f"Background for {period} (ug/m3)", min_value=0.0, value=0.0,
                key=f"bg_period_{period}",
            )
            period_vals[period] = val
        st.session_state["project_sources"].background = BackgroundConcentration(
            period_values=period_vals,
        )
    elif bg_mode == "Sector-dependent":
        n_sectors = st.number_input(
            "Number of Sectors", min_value=2, max_value=12, value=4,
            key="bg_n_sectors",
        )
        sectors = []
        sector_values = {}
        step = 360.0 / n_sectors
        avg_periods = st.session_state["project_control"].averaging_periods or ["ANNUAL"]

        for i in range(n_sectors):
            sid = i + 1
            start_dir = i * step
            end_dir = (i + 1) * step
            sectors.append(BackgroundSector(sid, start_dir, end_dir))
            col_dir, col_val = st.columns([1, 2])
            with col_dir:
                st.text(f"Sector {sid}: {start_dir:.0f}-{end_dir:.0f} deg")
            with col_val:
                for period in avg_periods:
                    val = st.number_input(
                        f"S{sid} {period} (ug/m3)", min_value=0.0, value=0.0,
                        key=f"bg_sector_{sid}_{period}",
                    )
                    sector_values[(sid, period)] = val
        st.session_state["project_sources"].background = BackgroundConcentration(
            sectors=sectors,
            sector_values=sector_values,
        )
    else:
        st.session_state["project_sources"].background = None


def _apply_aermap_receptor_elevations(
    discrete_receptors: list, rec_df: "pd.DataFrame", tolerance: float = 0.5,
) -> int:
    """Match AERMAP receptor output to discrete receptors by (x, y) within tolerance."""
    updated = 0
    for rec in discrete_receptors:
        mask = (
            (rec_df["x"] - rec.x_coord).abs() < tolerance
        ) & (
            (rec_df["y"] - rec.y_coord).abs() < tolerance
        )
        match = rec_df[mask]
        if not match.empty:
            rec.z_elev = float(match.iloc[0]["zelev"])
            if "zhill" in match.columns:
                rec.z_hill = float(match.iloc[0]["zhill"])
            updated += 1
    return updated


def _apply_aermap_source_elevations(
    sources: list, src_df: "pd.DataFrame",
) -> int:
    """Match AERMAP source output to sources by source_id."""
    updated = 0
    for source in sources:
        mask = src_df["source_id"].str.strip() == source.source_id.strip()
        match = src_df[mask]
        if not match.empty:
            source.base_elevation = float(match.iloc[0]["zelev"])
            updated += 1
    return updated


def page_receptor_editor():
    """Receptor Editor page with grid definition and map preview."""
    st.header("Receptor Editor")

    receptors = st.session_state["project_receptors"]
    transformer = SessionStateManager.get_transformer()

    tab_cart, tab_polar, tab_discrete, tab_import, tab_aermap = st.tabs([
        "Cartesian Grid", "Polar Grid", "Discrete Receptors",
        "Import CSV", "Import AERMAP Elevations",
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

    with tab_aermap:
        st.subheader("Import Elevations from AERMAP Output")
        if not HAS_TERRAIN:
            st.warning("Terrain module not available. Install with: pip install pyaermod[terrain]")
        else:
            st.info(
                "Upload AERMAP receptor and/or source output files. "
                "Elevations will be matched to existing discrete receptors by (x, y) "
                "coordinate (0.5 m tolerance)."
            )

            # --- Receptor elevations ---
            rec_file = st.file_uploader(
                "AERMAP Receptor Output File",
                type=["out", "txt", "dat"],
                key="aermap_rec_upload",
            )
            if rec_file:
                with tempfile.NamedTemporaryFile(
                    suffix=".out", delete=False, mode="w",
                ) as f:
                    f.write(rec_file.getvalue().decode("utf-8"))
                    temp_path = f.name
                try:
                    rec_df = AERMAPOutputParser.parse_receptor_output(temp_path)
                    st.success(f"Parsed {len(rec_df)} receptor elevations.")
                    st.dataframe(rec_df.head(20), use_container_width=True)

                    if not receptors.discrete_receptors:
                        st.warning(
                            "No discrete receptors to update. AERMAP elevation "
                            "import applies to discrete receptors only."
                        )
                    elif st.button("Apply Receptor Elevations"):
                        updated = _apply_aermap_receptor_elevations(
                            receptors.discrete_receptors, rec_df,
                        )
                        st.success(
                            f"Updated {updated} of "
                            f"{len(receptors.discrete_receptors)} discrete receptors."
                        )
                        st.rerun()
                except Exception as e:
                    st.error(f"Error parsing AERMAP receptor output: {e}")

            # --- Source elevations ---
            st.markdown("---")
            src_file = st.file_uploader(
                "AERMAP Source Output File (optional)",
                type=["out", "txt", "dat"],
                key="aermap_src_upload",
            )
            if src_file:
                with tempfile.NamedTemporaryFile(
                    suffix=".out", delete=False, mode="w",
                ) as f:
                    f.write(src_file.getvalue().decode("utf-8"))
                    temp_path = f.name
                try:
                    src_df = AERMAPOutputParser.parse_source_output(temp_path)
                    st.success(f"Parsed {len(src_df)} source elevations.")
                    st.dataframe(src_df, use_container_width=True)

                    sources = st.session_state["project_sources"].sources
                    if not sources:
                        st.warning("No sources defined to update.")
                    elif st.button("Apply Source Elevations"):
                        updated = _apply_aermap_source_elevations(sources, src_df)
                        st.success(f"Updated {updated} of {len(sources)} source elevations.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error parsing AERMAP source output: {e}")

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

    if receptors.cartesian_grids or receptors.polar_grids or receptors.discrete_receptors:  # noqa: SIM102
        if st.button("Clear All Receptors", type="secondary"):
            st.session_state["project_receptors"] = ReceptorPathway()
            st.rerun()


def page_meteorology():
    """Meteorology configuration page with dual mode: files or AERMET config."""
    st.header("Meteorology")

    mode_options = ["Use existing .sfc/.pfl files", "Configure AERMET"]
    current_mode = st.session_state.get("aermet_mode", "files")
    mode_idx = 0 if current_mode == "files" else 1
    mode = st.radio("Meteorology Mode", mode_options, index=mode_idx, horizontal=True)
    st.session_state["aermet_mode"] = "files" if mode == mode_options[0] else "configure"

    if st.session_state["aermet_mode"] == "files":
        _render_met_files_mode()
    else:
        _render_aermet_config_mode()


def _render_met_files_mode():
    """Existing .sfc/.pfl file mode for users who ran AERMET externally."""
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

    st.session_state["project_meteorology"] = MeteorologyPathway(
        surface_file=sfc_file,
        profile_file=pfl_file,
    )
    st.success("Meteorology settings saved.")


def _render_aermet_config_mode():
    """Full AERMET configuration mode with 3 stages."""
    if not HAS_AERMET:
        st.warning("AERMET module not available.")
        return

    tab1, tab2, tab3 = st.tabs([
        "Stage 1: Data Extract", "Stage 2: Merge", "Stage 3: Boundary Layer",
    ])

    with tab1:
        _render_aermet_stage1()

    with tab2:
        _render_aermet_stage2()

    with tab3:
        _render_aermet_stage3()


def _render_aermet_stage1():
    """AERMET Stage 1: surface/upper-air station config, data files, date range."""
    st.subheader("Stage 1: Extract and QA/QC")

    st.markdown("**Surface Station**")
    col1, col2 = st.columns(2)
    with col1:
        sfc_id = st.text_input("Station ID", value="KATL", key="sfc_station_id")
        sfc_name = st.text_input("Station Name", value="Atlanta Hartsfield", key="sfc_station_name")
        sfc_lat = st.number_input(
            "Latitude", value=33.63, min_value=-90.0, max_value=90.0,
            format="%.4f", key="sfc_lat",
        )
        sfc_lon = st.number_input(
            "Longitude", value=-84.44, min_value=-180.0, max_value=180.0,
            format="%.4f", key="sfc_lon",
        )
    with col2:
        sfc_tz = st.number_input(
            "Time Zone (UTC offset)", value=-5, min_value=-12, max_value=12,
            step=1, key="sfc_tz",
        )
        sfc_elev = st.number_input("Elevation (m)", value=315.0, format="%.1f", key="sfc_elev")
        sfc_anem = st.number_input(
            "Anemometer Height (m)", value=10.0, min_value=0.1, key="sfc_anem",
        )
        sfc_format = st.selectbox(
            "Data Format", ["ISHD", "HUSWO", "SCRAM", "SAMSON"], key="sfc_format",
        )

    st.markdown("**Upper Air Station**")
    col3, col4 = st.columns(2)
    with col3:
        ua_id = st.text_input("Station ID", value="72215", key="ua_station_id")
        ua_name = st.text_input("Station Name", value="Peachtree City", key="ua_station_name")
    with col4:
        ua_lat = st.number_input("Latitude", value=33.36, format="%.4f", key="ua_lat")
        ua_lon = st.number_input("Longitude", value=-84.57, format="%.4f", key="ua_lon")

    st.markdown("**Data Files and Date Range**")
    col5, col6 = st.columns(2)
    with col5:
        sfc_data = st.text_input("Surface Data File", value="", key="sfc_data_file")
        ua_data = st.text_input("Upper Air Data File", value="", key="ua_data_file")
    with col6:
        start_date = st.text_input("Start Date (YYYY/MM/DD)", value="2020/01/01", key="aermet_s1_start")
        end_date = st.text_input("End Date (YYYY/MM/DD)", value="2020/12/31", key="aermet_s1_end")

    if st.button("Save Stage 1 Configuration", key="save_stage1"):
        try:
            sfc_station = AERMETStation(
                station_id=sfc_id, station_name=sfc_name,
                latitude=sfc_lat, longitude=sfc_lon,
                time_zone=int(sfc_tz), elevation=sfc_elev,
                anemometer_height=sfc_anem,
            )
            ua_station = UpperAirStation(
                station_id=ua_id, station_name=ua_name,
                latitude=ua_lat, longitude=ua_lon,
            )
            stage1 = AERMETStage1(
                surface_station=sfc_station, surface_data_file=sfc_data,
                surface_format=sfc_format,
                upper_air_station=ua_station, upper_air_data_file=ua_data,
                start_date=start_date, end_date=end_date,
            )
            st.session_state["aermet_stage1"] = stage1
            st.success("Stage 1 configuration saved.")
        except ValueError as e:
            st.error(str(e))

    # Preview
    stage1 = st.session_state.get("aermet_stage1")
    if stage1 is not None:
        with st.expander("Preview Stage 1 Input"):
            st.code(stage1.to_aermet_input(), language="text")
        st.download_button(
            "Download Stage 1 Input File",
            stage1.to_aermet_input().encode("utf-8"),
            file_name="aermet_stage1.inp",
            mime="text/plain",
            key="dl_stage1",
        )


def _render_aermet_stage2():
    """AERMET Stage 2: merge configuration."""
    st.subheader("Stage 2: Merge Data")

    col1, col2 = st.columns(2)
    with col1:
        sfc_ext = st.text_input("Surface Extract File", value="stage1.ext", key="s2_sfc_ext")
        ua_ext = st.text_input("Upper Air Extract File", value="stage1_ua.ext", key="s2_ua_ext")
    with col2:
        start_date = st.text_input("Start Date", value="2020/01/01", key="aermet_s2_start")
        end_date = st.text_input("End Date", value="2020/12/31", key="aermet_s2_end")
        merge_file = st.text_input("Merge Output File", value="stage2.mrg", key="s2_merge")

    if st.button("Save Stage 2 Configuration", key="save_stage2"):
        stage2 = AERMETStage2(
            surface_extract=sfc_ext,
            upper_air_extract=ua_ext if ua_ext else None,
            start_date=start_date, end_date=end_date,
            merge_file=merge_file,
        )
        st.session_state["aermet_stage2"] = stage2
        st.success("Stage 2 configuration saved.")

    stage2 = st.session_state.get("aermet_stage2")
    if stage2 is not None:
        with st.expander("Preview Stage 2 Input"):
            st.code(stage2.to_aermet_input(), language="text")
        st.download_button(
            "Download Stage 2 Input File",
            stage2.to_aermet_input().encode("utf-8"),
            file_name="aermet_stage2.inp",
            mime="text/plain",
            key="dl_stage2",
        )


def _render_aermet_stage3():
    """AERMET Stage 3: boundary layer parameters with monthly arrays."""
    st.subheader("Stage 3: Boundary Layer Parameters")

    col1, col2 = st.columns(2)
    with col1:
        merge_file = st.text_input("Merge File", value="stage2.mrg", key="s3_merge")
        start_date = st.text_input("Start Date", value="2020/01/01", key="aermet_s3_start")
        end_date = st.text_input("End Date", value="2020/12/31", key="aermet_s3_end")
    with col2:
        sfc_out = st.text_input("Surface Output (.sfc)", value="aermod.sfc", key="s3_sfc_out")
        pfl_out = st.text_input("Profile Output (.pfl)", value="aermod.pfl", key="s3_pfl_out")

    st.markdown("**Monthly Surface Parameters** (12 months: Jan-Dec)")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    # Defaults for suburban area
    default_albedo = [0.35, 0.35, 0.25, 0.18, 0.15, 0.15, 0.15, 0.15, 0.18, 0.25, 0.35, 0.35]
    default_bowen = [1.5, 1.5, 1.0, 0.8, 0.6, 0.5, 0.5, 0.5, 0.6, 0.8, 1.0, 1.5]
    default_roughness = [0.30, 0.30, 0.30, 0.30, 0.50, 0.50, 0.50, 0.50, 0.50, 0.30, 0.30, 0.30]

    monthly_df = pd.DataFrame({
        "Month": months,
        "Albedo": default_albedo,
        "Bowen Ratio": default_bowen,
        "Roughness (m)": default_roughness,
    })

    edited_df = st.data_editor(
        monthly_df, num_rows="fixed", use_container_width=True,
        disabled=["Month"], key="s3_monthly_editor",
    )

    st.markdown("**Site Location** (uses Stage 1 station if configured)")
    use_stage1 = st.checkbox("Use Stage 1 surface station", value=True, key="s3_use_stage1")

    if st.button("Save Stage 3 Configuration", key="save_stage3"):
        try:
            albedo = edited_df["Albedo"].tolist()
            bowen = edited_df["Bowen Ratio"].tolist()
            roughness = edited_df["Roughness (m)"].tolist()

            station = None
            lat = lon = tz = None
            if use_stage1:
                s1 = st.session_state.get("aermet_stage1")
                if s1 and s1.surface_station:
                    station = s1.surface_station
            if station is None:
                st.warning("No Stage 1 station configured. Using project center coordinates.")
                lat = st.session_state.get("center_lat", 33.75)
                lon = st.session_state.get("center_lon", -84.39)
                tz = -5

            stage3 = AERMETStage3(
                merge_file=merge_file,
                station=station,
                latitude=lat, longitude=lon, time_zone=tz,
                albedo=albedo, bowen=bowen, roughness=roughness,
                start_date=start_date, end_date=end_date,
                surface_file=sfc_out, profile_file=pfl_out,
            )
            st.session_state["aermet_stage3"] = stage3

            # Also update the meteorology pathway so AERMOD can find the files
            st.session_state["project_meteorology"] = MeteorologyPathway(
                surface_file=sfc_out,
                profile_file=pfl_out,
            )
            st.success("Stage 3 configuration saved. Meteorology pathway updated.")
        except ValueError as e:
            st.error(str(e))

    stage3 = st.session_state.get("aermet_stage3")
    if stage3 is not None:
        with st.expander("Preview Stage 3 Input"):
            st.code(stage3.to_aermet_input(), language="text")
        st.download_button(
            "Download Stage 3 Input File",
            stage3.to_aermet_input().encode("utf-8"),
            file_name="aermet_stage3.inp",
            mime="text/plain",
            key="dl_stage3",
        )


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
        if postfile_enabled:
            postfile_format = st.selectbox(
                "POSTFILE Format", ["PLOT", "UNFORM"],
                help="PLOT = formatted text, UNFORM = binary",
            )
            postfile_avg = st.selectbox(
                "POSTFILE Averaging Period",
                ["1", "3", "8", "24", "ANNUAL", "PERIOD"],
                help="Averaging period to output in POSTFILE",
            )

    # Output type (shown when deposition is enabled)
    dep_enabled = (
        st.session_state["project_control"].calculate_deposition
        or st.session_state["project_control"].calculate_dry_deposition
        or st.session_state["project_control"].calculate_wet_deposition
    )
    output_type = "CONC"
    if dep_enabled:
        output_type = st.selectbox(
            "Output Type",
            ["CONC", "DEPOS", "DDEP", "WDEP", "DETH"],
            help="Type of output: concentration (CONC) or deposition flux",
        )

    out_kwargs = dict(
        receptor_table=receptor_table,
        max_table=max_table,
        output_type=output_type,
    )
    if postfile_enabled:
        out_kwargs.update(
            postfile="postfile.pst",
            postfile_averaging=postfile_avg,
            postfile_source_group="ALL",
            postfile_format=postfile_format,
        )
    st.session_state["project_output"] = OutputPathway(**out_kwargs)

    # Event processing
    with st.expander("Event Processing"):
        event_enabled = st.checkbox("Enable Event Processing", value=False, key="event_enabled")
        if event_enabled:
            n_events = st.number_input(
                "Number of Events", min_value=1, max_value=50, value=1,
                key="n_events",
            )
            events = []
            for i in range(n_events):
                ev_col1, ev_col2, ev_col3 = st.columns(3)
                with ev_col1:
                    ev_name = st.text_input(
                        f"Event {i+1} Name", value=f"EVT{i+1:02d}",
                        max_chars=8, key=f"ev_name_{i}",
                    )
                with ev_col2:
                    ev_start = st.text_input(
                        "Start (YYMMDDHH)", value="24010101",
                        max_chars=8, key=f"ev_start_{i}",
                    )
                with ev_col3:
                    ev_end = st.text_input(
                        "End (YYMMDDHH)", value="24010124",
                        max_chars=8, key=f"ev_end_{i}",
                    )
                events.append(EventPeriod(
                    event_name=ev_name,
                    start_date=ev_start,
                    end_date=ev_end,
                ))
            st.session_state["project_events"] = EventPathway(events=events)
            st.session_state["project_control"] = ControlPathway(
                **{
                    **{
                        f.name: getattr(st.session_state["project_control"], f.name)
                        for f in st.session_state["project_control"].__dataclass_fields__.values()
                    },
                    "eventfil": "events.inp",
                }
            )
        else:
            st.session_state["project_events"] = None

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
    tab_map, tab_static, tab_stats, tab_postfile = st.tabs([
        "Interactive Map", "Static Plots", "Statistics", "POSTFILE Viewer",
    ])

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

    with tab_postfile:
        _render_postfile_viewer()


# ---------------------------------------------------------------------------
# POSTFILE Viewer helpers
# ---------------------------------------------------------------------------

def _postfile_frames_for_animation(postfile_result):
    """
    Extract per-timestep DataFrames with uppercase column names for
    ``AdvancedVisualizer.plot_time_series_animation()``.

    Parameters
    ----------
    postfile_result : PostfileResult
        Parsed POSTFILE data.

    Returns
    -------
    frames : list of pd.DataFrame
        One DataFrame per timestep with columns ``X``, ``Y``, ``CONC``.
    dates : list of str
        Sorted date strings corresponding to each frame.
    """
    dates = sorted(postfile_result.data["date"].unique())
    frames = []
    for date in dates:
        df = postfile_result.get_timestep(date)
        frames.append(df.rename(columns={
            "x": "X", "y": "Y", "concentration": "CONC",
        }))
    return frames, dates


def _render_postfile_viewer():
    """Render the POSTFILE Viewer sub-tab content."""
    st.subheader("POSTFILE Viewer")

    if not HAS_POSTFILE:
        st.warning("POSTFILE parser is not available.")
        return

    # File upload
    uploaded_pst = st.file_uploader(
        "Upload POSTFILE",
        type=["pst", "plt", "out", "dat", "bin"],
        key="postfile_upload",
        help="Upload an AERMOD POSTFILE (text PLOT or binary UNFORM format).",
    )

    if uploaded_pst:
        with tempfile.NamedTemporaryFile(
            suffix=".pst", delete=False,
        ) as tmp:
            tmp.write(uploaded_pst.getvalue())
            tmp.flush()
            try:
                pf_result = read_postfile(tmp.name)
                st.session_state["postfile_results"] = pf_result
                st.success(
                    f"POSTFILE loaded: {len(pf_result.data)} data rows, "
                    f"{pf_result.data['date'].nunique()} timesteps."
                )
            except Exception as e:
                st.error(f"Failed to parse POSTFILE: {e}")

    pf_result = st.session_state.get("postfile_results")
    if pf_result is None or pf_result.data.empty:
        st.info("Upload a POSTFILE to view concentration data over time.")
        return

    # -- Header metadata --
    st.subheader("POSTFILE Metadata")
    hdr = pf_result.header
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Version", hdr.version or "N/A")
    mc2.metric("Pollutant", hdr.pollutant_id or "N/A")
    mc3.metric("Averaging", hdr.averaging_period or "N/A")
    mc4.metric("Source Group", hdr.source_group or "N/A")

    # -- Timestep selector --
    dates = sorted(pf_result.data["date"].unique())
    st.subheader("Timestep Viewer")

    selected_date = st.select_slider(
        "Select Timestep (YYMMDDHH)",
        options=dates,
        value=dates[0],
        key="pf_date_slider",
    )

    ts_df = pf_result.get_timestep(selected_date)
    st.write(f"**{len(ts_df)} receptors** at timestep {selected_date}")

    # Summary metrics for selected timestep
    if not ts_df.empty:
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Max Conc.", f"{ts_df['concentration'].max():.4g}")
        sc2.metric("Mean Conc.", f"{ts_df['concentration'].mean():.4g}")
        sc3.metric("Min Conc.", f"{ts_df['concentration'].min():.4g}")

    # Contour plot for the selected timestep (if matplotlib available)
    if HAS_MATPLOTLIB and not ts_df.empty:
        x_vals = ts_df["x"].values
        y_vals = ts_df["y"].values
        conc_vals = ts_df["concentration"].values

        x_unique = np.unique(x_vals)
        y_unique = np.unique(y_vals)

        # Only produce contour if data forms a grid
        if len(x_unique) > 1 and len(y_unique) > 1 and len(x_unique) * len(y_unique) == len(ts_df):
            try:
                X_grid, Y_grid = np.meshgrid(x_unique, y_unique)
                Z_grid = conc_vals.reshape(len(y_unique), len(x_unique))

                fig, ax = plt.subplots(figsize=(8, 6))
                cf = ax.contourf(X_grid, Y_grid, Z_grid, levels=15, cmap="YlOrRd")
                fig.colorbar(cf, ax=ax, label="Concentration")
                ax.set_xlabel("X (m)")
                ax.set_ylabel("Y (m)")
                ax.set_title(f"Concentration — {selected_date}")
                ax.set_aspect("equal")
                st.pyplot(fig)
                plt.close(fig)
            except Exception as e:
                st.warning(f"Could not render contour plot: {e}")
        else:
            # Non-gridded data — show as scatter plot
            try:
                fig, ax = plt.subplots(figsize=(8, 6))
                sc = ax.scatter(x_vals, y_vals, c=conc_vals, cmap="YlOrRd", s=20)
                fig.colorbar(sc, ax=ax, label="Concentration")
                ax.set_xlabel("X (m)")
                ax.set_ylabel("Y (m)")
                ax.set_title(f"Concentration — {selected_date}")
                ax.set_aspect("equal")
                st.pyplot(fig)
                plt.close(fig)
            except Exception as e:
                st.warning(f"Could not render scatter plot: {e}")

    # -- Data table for selected timestep --
    with st.expander("View Timestep Data Table"):
        st.dataframe(ts_df, use_container_width=True)

    # -- Time-series at a receptor --
    st.subheader("Receptor Time Series")
    receptor_locs = pf_result.data.groupby(["x", "y"]).size().reset_index(name="count")
    receptor_options = [
        f"({row['x']:.1f}, {row['y']:.1f})" for _, row in receptor_locs.iterrows()
    ]
    if receptor_options:
        selected_receptor = st.selectbox(
            "Select Receptor", receptor_options, key="pf_receptor_select"
        )
        # Parse selected coordinates
        parts = selected_receptor.strip("()").split(",")
        rx, ry = float(parts[0].strip()), float(parts[1].strip())
        rec_df = pf_result.get_receptor(rx, ry)

        if not rec_df.empty and HAS_MATPLOTLIB:
            fig_ts, ax_ts = plt.subplots(figsize=(10, 4))
            rec_sorted = rec_df.sort_values("date")
            ax_ts.plot(
                rec_sorted["date"], rec_sorted["concentration"],
                marker="o", markersize=3, linewidth=1,
            )
            ax_ts.set_xlabel("Date (YYMMDDHH)")
            ax_ts.set_ylabel("Concentration")
            ax_ts.set_title(f"Time Series at ({rx:.1f}, {ry:.1f})")
            ax_ts.tick_params(axis="x", rotation=45)
            fig_ts.tight_layout()
            st.pyplot(fig_ts)
            plt.close(fig_ts)

    # -- Animation --
    st.subheader("Animation")
    if not HAS_ADVANCED_VIZ:
        st.info("Advanced visualization module not available for animation.")
    elif len(dates) < 2:
        st.info("Need at least 2 timesteps for animation.")
    else:
        anim_interval = st.slider(
            "Frame interval (ms)", min_value=100, max_value=2000,
            value=500, step=100, key="pf_anim_interval",
        )
        if st.button("Generate Animation GIF", key="pf_gen_anim"):
            frames, frame_dates = _postfile_frames_for_animation(pf_result)

            # Verify frames have gridded data
            df0 = frames[0]
            xu = np.unique(df0["X"].values)
            yu = np.unique(df0["Y"].values)
            if len(xu) < 2 or len(yu) < 2:
                st.warning("Animation requires gridded receptor data with at least 2 unique X and Y values.")
            else:
                with st.spinner("Generating animation..."):
                    try:
                        gif_path = os.path.join(
                            tempfile.gettempdir(), "postfile_animation.gif"
                        )
                        AdvancedVisualizer.plot_time_series_animation(
                            dataframes=frames,
                            timestamps=frame_dates,
                            title="POSTFILE Concentration",
                            interval=anim_interval,
                            save_path=gif_path,
                        )
                        plt.close("all")

                        if os.path.exists(gif_path) and os.path.getsize(gif_path) > 0:
                            st.image(gif_path, caption="Concentration Animation")
                            with open(gif_path, "rb") as gf:
                                st.download_button(
                                    "Download GIF",
                                    data=gf.read(),
                                    file_name="postfile_animation.gif",
                                    mime="image/gif",
                                )
                        else:
                            st.warning("Animation file was not generated.")
                    except Exception as e:
                        st.warning(f"Could not generate animation: {e}")


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

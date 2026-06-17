"""Interactive folium map editor for the PyAERMOD GUI."""
from ._env import *


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
        from ..input_generator import (
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



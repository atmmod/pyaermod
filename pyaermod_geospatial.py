"""
PyAERMOD Geospatial Utilities

Coordinate transformations (UTM <-> WGS84), GeoDataFrame creation,
contour polygon generation, and GIS export (GeoTIFF, Shapefile, GeoPackage).

Requires optional dependencies: pyproj, geopandas, rasterio, shapely.
Install with: pip install pyaermod[geo]
"""

import math
import numpy as np
import pandas as pd
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    import pyproj
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

try:
    import geopandas as gpd
    from shapely.geometry import (
        LineString, MultiPolygon, Point, Polygon, mapping,
    )
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

try:
    import rasterio
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    from scipy.interpolate import griddata
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def _require(lib_name: str, flag: bool) -> None:
    """Raise ImportError with install instructions if a dependency is missing."""
    if not flag:
        extras = {
            "pyproj": "geo",
            "geopandas": "geo",
            "rasterio": "geo",
            "scipy": "geo",
            "matplotlib": "viz",
        }
        extra = extras.get(lib_name, "geo")
        raise ImportError(
            f"{lib_name} is required for this function. "
            f"Install with: pip install pyaermod[{extra}]"
        )


# ============================================================================
# COORDINATE TRANSFORMER
# ============================================================================


@dataclass
class CoordinateTransformer:
    """Bidirectional UTM <-> WGS84 coordinate transformer.

    Parameters
    ----------
    utm_zone : int
        UTM zone number (1-60).
    hemisphere : str
        'N' or 'S' for northern/southern hemisphere. Default 'N'.
    datum : str
        Datum string: 'WGS84', 'NAD83', or 'NAD27'. Default 'WGS84'.
    """
    utm_zone: int
    hemisphere: str = "N"
    datum: str = "WGS84"

    def __post_init__(self):
        _require("pyproj", HAS_PYPROJ)

        if not 1 <= self.utm_zone <= 60:
            raise ValueError(f"UTM zone must be 1-60, got {self.utm_zone}")
        if self.hemisphere.upper() not in ("N", "S"):
            raise ValueError(f"hemisphere must be 'N' or 'S', got {self.hemisphere!r}")
        self.hemisphere = self.hemisphere.upper()

        # Build CRS objects
        self._utm_crs = pyproj.CRS(
            proj="utm", zone=self.utm_zone,
            south=(self.hemisphere == "S"), datum=self.datum,
        )
        self._geographic_crs = pyproj.CRS("EPSG:4326")

        # Transformers (always_xy ensures (lon, lat) order for geographic)
        self._to_latlon = pyproj.Transformer.from_crs(
            self._utm_crs, self._geographic_crs, always_xy=True,
        )
        self._to_utm = pyproj.Transformer.from_crs(
            self._geographic_crs, self._utm_crs, always_xy=True,
        )

    # -- class methods -------------------------------------------------------

    @classmethod
    def from_aermap_domain(cls, domain) -> "CoordinateTransformer":
        """Create transformer from an AERMAPDomain object.

        Reads ``utm_zone`` and ``datum`` from the domain. Hemisphere is
        inferred as 'N' (AERMOD is predominantly used in the northern
        hemisphere); override after creation if needed.
        """
        return cls(
            utm_zone=domain.utm_zone,
            datum=getattr(domain, "datum", "NAD83"),
        )

    @classmethod
    def from_latlon(
        cls, latitude: float, longitude: float, datum: str = "WGS84",
    ) -> "CoordinateTransformer":
        """Auto-detect UTM zone from a lat/lon point."""
        zone = int((longitude + 180) / 6) + 1
        hemisphere = "N" if latitude >= 0 else "S"
        return cls(utm_zone=zone, hemisphere=hemisphere, datum=datum)

    # -- single-point transforms ---------------------------------------------

    def utm_to_latlon(self, x: float, y: float) -> Tuple[float, float]:
        """Convert UTM easting/northing to (latitude, longitude)."""
        lon, lat = self._to_latlon.transform(x, y)
        return (lat, lon)

    def latlon_to_utm(self, lat: float, lon: float) -> Tuple[float, float]:
        """Convert (latitude, longitude) to UTM (easting, northing)."""
        x, y = self._to_utm.transform(lon, lat)
        return (x, y)

    # -- batch transforms on DataFrames --------------------------------------

    def transform_dataframe(
        self,
        df: pd.DataFrame,
        x_col: str = "x",
        y_col: str = "y",
        to_latlon: bool = True,
    ) -> pd.DataFrame:
        """Add transformed coordinate columns to a DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Input DataFrame.
        x_col, y_col : str
            Column names for existing coordinates.
        to_latlon : bool
            If True (default), adds ``latitude`` and ``longitude`` columns
            by converting UTM to WGS84. If False, adds ``utm_x`` and
            ``utm_y`` columns by converting lat/lon to UTM.

        Returns
        -------
        pd.DataFrame
            Copy of *df* with new columns appended.
        """
        result = df.copy()
        xs = result[x_col].values
        ys = result[y_col].values

        if to_latlon:
            lons, lats = self._to_latlon.transform(xs, ys)
            result["latitude"] = lats
            result["longitude"] = lons
        else:
            utm_x, utm_y = self._to_utm.transform(xs, ys)
            result["utm_x"] = utm_x
            result["utm_y"] = utm_y

        return result

    # -- CRS properties ------------------------------------------------------

    @property
    def utm_crs(self):
        """Return the ``pyproj.CRS`` for this UTM zone."""
        return self._utm_crs

    @property
    def geographic_crs(self):
        """Return the WGS84 geographic ``pyproj.CRS``."""
        return self._geographic_crs


# ============================================================================
# GEODATAFRAME FACTORY
# ============================================================================


class GeoDataFrameFactory:
    """Create GeoDataFrames from pyaermod objects.

    Parameters
    ----------
    transformer : CoordinateTransformer
        Coordinate transformer for CRS assignment.
    """

    def __init__(self, transformer: CoordinateTransformer):
        _require("geopandas", HAS_GEOPANDAS)
        self.transformer = transformer

    # -- sources -------------------------------------------------------------

    def sources_to_geodataframe(self, sources: list) -> "gpd.GeoDataFrame":
        """Convert a list of source objects to a GeoDataFrame.

        Returns Point geometries for point/area/volume/circular sources,
        LineString geometries for line/rline sources, and Polygon
        geometries for polygonal area sources.
        """
        from pyaermod_input_generator import (
            AreaCircSource, AreaPolySource, AreaSource,
            LineSource, PointSource, RLineSource, VolumeSource,
            RLineExtSource, BuoyLineSource, OpenPitSource,
        )

        records = []
        geometries = []

        for src in sources:
            rec: Dict = {"source_id": getattr(src, "source_id", "")}

            if isinstance(src, RLineExtSource):
                rec["source_type"] = "RLINEXT"
                rec["emission_rate"] = src.emission_rate
                rec["road_width"] = src.road_width
                geometries.append(
                    LineString([(src.x_start, src.y_start), (src.x_end, src.y_end)])
                )
            elif isinstance(src, BuoyLineSource):
                rec["source_type"] = "BUOYLINE"
                rec["emission_rate"] = src.emission_rate
                if src.line_segments:
                    from shapely.geometry import MultiLineString
                    segment_lines = [
                        ((seg.x_start, seg.y_start), (seg.x_end, seg.y_end))
                        for seg in src.line_segments
                    ]
                    geometries.append(MultiLineString(segment_lines))
                else:
                    geometries.append(Point(0, 0))
            elif isinstance(src, OpenPitSource):
                rec["source_type"] = "OPENPIT"
                rec["emission_rate"] = src.emission_rate
                rec["pit_volume"] = src.pit_volume
                # Build rotated rectangle from SW corner + dimensions
                cx, cy = src.x_coord, src.y_coord
                xd, yd = src.x_dimension, src.y_dimension
                corners = [
                    (cx, cy), (cx + xd, cy),
                    (cx + xd, cy + yd), (cx, cy + yd),
                ]
                if src.angle != 0.0:
                    rad = math.radians(src.angle)
                    cos_a, sin_a = math.cos(rad), math.sin(rad)
                    corners = [
                        (
                            cx + (x - cx) * cos_a - (y - cy) * sin_a,
                            cy + (x - cx) * sin_a + (y - cy) * cos_a,
                        )
                        for x, y in corners
                    ]
                geometries.append(Polygon(corners))
            elif isinstance(src, (LineSource, RLineSource)):
                rec["source_type"] = "LINE" if isinstance(src, LineSource) else "RLINE"
                rec["emission_rate"] = src.emission_rate
                rec["release_height"] = src.release_height
                geometries.append(
                    LineString([(src.x_start, src.y_start), (src.x_end, src.y_end)])
                )
            elif isinstance(src, AreaPolySource):
                rec["source_type"] = "AREAPOLY"
                rec["emission_rate"] = src.emission_rate
                rec["release_height"] = src.release_height
                geometries.append(Polygon(src.vertices))
            elif isinstance(src, AreaCircSource):
                rec["source_type"] = "AREACIRC"
                rec["emission_rate"] = src.emission_rate
                rec["release_height"] = src.release_height
                # Approximate circle as polygon
                circle_pts = [
                    (
                        src.x_coord + src.radius * math.cos(math.radians(a)),
                        src.y_coord + src.radius * math.sin(math.radians(a)),
                    )
                    for a in range(0, 360, max(1, 360 // max(src.num_vertices, 6)))
                ]
                geometries.append(Polygon(circle_pts))
            elif isinstance(src, AreaSource):
                rec["source_type"] = "AREA"
                rec["emission_rate"] = src.emission_rate
                rec["release_height"] = src.release_height
                # Build rectangle from center + half-dimensions
                hw = src.initial_lateral_dimension
                hl = src.initial_vertical_dimension
                cx, cy = src.x_coord, src.y_coord
                corners = [
                    (cx - hl, cy - hw), (cx + hl, cy - hw),
                    (cx + hl, cy + hw), (cx - hl, cy + hw),
                ]
                if src.angle != 0.0:
                    rad = math.radians(src.angle)
                    cos_a, sin_a = math.cos(rad), math.sin(rad)
                    corners = [
                        (
                            cx + (x - cx) * cos_a - (y - cy) * sin_a,
                            cy + (x - cx) * sin_a + (y - cy) * cos_a,
                        )
                        for x, y in corners
                    ]
                geometries.append(Polygon(corners))
            elif isinstance(src, PointSource):
                rec["source_type"] = "POINT"
                rec["emission_rate"] = src.emission_rate
                rec["stack_height"] = src.stack_height
                geometries.append(Point(src.x_coord, src.y_coord))
            elif isinstance(src, VolumeSource):
                rec["source_type"] = "VOLUME"
                rec["emission_rate"] = src.emission_rate
                rec["release_height"] = src.release_height
                geometries.append(Point(src.x_coord, src.y_coord))
            else:
                # Fallback: try to get x_coord/y_coord
                rec["source_type"] = type(src).__name__
                x = getattr(src, "x_coord", 0.0)
                y = getattr(src, "y_coord", 0.0)
                geometries.append(Point(x, y))

            records.append(rec)

        gdf = gpd.GeoDataFrame(records, geometry=geometries, crs=self.transformer.utm_crs)
        return gdf

    def sources_from_results(self, results) -> "gpd.GeoDataFrame":
        """Convert parsed AERMODResults source summaries to a GeoDataFrame."""
        df = results.get_sources_dataframe()
        geometry = [Point(row.x, row.y) for row in df.itertuples()]
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=self.transformer.utm_crs)
        return gdf

    # -- receptors -----------------------------------------------------------

    def receptors_to_geodataframe(self, receptors) -> "gpd.GeoDataFrame":
        """Convert a ReceptorPathway to a GeoDataFrame of receptor points.

        Expands CartesianGrid and PolarGrid definitions into individual
        receptor locations.
        """
        points = []
        attrs = []

        # Expand Cartesian grids
        for grid in receptors.cartesian_grids:
            for i in range(grid.x_num):
                for j in range(grid.y_num):
                    x = grid.x_init + i * grid.x_delta
                    y = grid.y_init + j * grid.y_delta
                    points.append(Point(x, y))
                    attrs.append({
                        "grid_name": grid.grid_name,
                        "grid_type": "cartesian",
                        "z_elev": grid.z_elev,
                    })

        # Expand Polar grids
        for grid in receptors.polar_grids:
            for k in range(grid.dist_num):
                dist = grid.dist_init + k * grid.dist_delta
                for m in range(grid.dir_num):
                    direction = grid.dir_init + m * grid.dir_delta
                    rad = math.radians(direction)
                    x = grid.x_origin + dist * math.sin(rad)
                    y = grid.y_origin + dist * math.cos(rad)
                    points.append(Point(x, y))
                    attrs.append({
                        "grid_name": grid.grid_name,
                        "grid_type": "polar",
                        "z_elev": 0.0,
                    })

        # Discrete receptors
        for rec in receptors.discrete_receptors:
            points.append(Point(rec.x_coord, rec.y_coord))
            attrs.append({
                "grid_name": "discrete",
                "grid_type": "discrete",
                "z_elev": rec.z_elev,
            })

        if not points:
            return gpd.GeoDataFrame(
                columns=["grid_name", "grid_type", "z_elev", "geometry"],
                crs=self.transformer.utm_crs,
            )

        gdf = gpd.GeoDataFrame(attrs, geometry=points, crs=self.transformer.utm_crs)
        return gdf

    # -- concentrations ------------------------------------------------------

    def concentrations_to_geodataframe(
        self,
        df: pd.DataFrame,
        value_col: str = "concentration",
        x_col: str = "x",
        y_col: str = "y",
    ) -> "gpd.GeoDataFrame":
        """Convert a concentration DataFrame to a GeoDataFrame with Point geometries."""
        geometry = [Point(row[x_col], row[y_col]) for _, row in df.iterrows()]
        gdf = gpd.GeoDataFrame(df.copy(), geometry=geometry, crs=self.transformer.utm_crs)
        return gdf

    def postfile_to_geodataframe(
        self, result, timestep: Optional[str] = None,
    ) -> "gpd.GeoDataFrame":
        """Convert a PostfileResult to a GeoDataFrame.

        Parameters
        ----------
        result : PostfileResult
            Parsed POSTFILE data.
        timestep : str, optional
            If given, filter to this YYMMDDHH date string.
        """
        data = result.get_timestep(timestep) if timestep else result.data.copy()
        geometry = [Point(row.x, row.y) for row in data.itertuples()]
        gdf = gpd.GeoDataFrame(data, geometry=geometry, crs=self.transformer.utm_crs)
        return gdf


# ============================================================================
# CONTOUR GENERATOR
# ============================================================================


class ContourGenerator:
    """Generate contour polygons from concentration data.

    Uses scipy.griddata interpolation and matplotlib contourf to compute
    filled contour paths, then converts them to Shapely Polygons.

    Parameters
    ----------
    transformer : CoordinateTransformer
        For CRS assignment on output GeoDataFrames.
    """

    def __init__(self, transformer: CoordinateTransformer):
        _require("geopandas", HAS_GEOPANDAS)
        _require("scipy", HAS_SCIPY)
        _require("matplotlib", HAS_MATPLOTLIB)
        self.transformer = transformer

    def generate_contours(
        self,
        df: pd.DataFrame,
        levels: Optional[List[float]] = None,
        n_levels: int = 10,
        method: str = "cubic",
        grid_resolution: int = 200,
        x_col: str = "x",
        y_col: str = "y",
        value_col: str = "concentration",
    ) -> "gpd.GeoDataFrame":
        """Generate filled contour polygons as a GeoDataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Must contain *x_col*, *y_col*, and *value_col* columns.
        levels : list of float, optional
            Explicit contour levels. If None, *n_levels* equally-spaced
            levels are computed from the data range.
        n_levels : int
            Number of auto-computed levels when *levels* is None.
        method : str
            Interpolation method for ``scipy.interpolate.griddata``.
        grid_resolution : int
            Number of cells in each direction for the interpolation grid.
        x_col, y_col, value_col : str
            Column names.

        Returns
        -------
        geopandas.GeoDataFrame
            Columns: ``geometry``, ``level_min``, ``level_max``, ``level_label``.
            CRS is set to the UTM CRS of the transformer.
        """
        x = df[x_col].values
        y = df[y_col].values
        z = df[value_col].values

        # Build regular grid
        xi = np.linspace(x.min(), x.max(), grid_resolution)
        yi = np.linspace(y.min(), y.max(), grid_resolution)
        xi_grid, yi_grid = np.meshgrid(xi, yi)

        # Interpolate
        zi = griddata((x, y), z, (xi_grid, yi_grid), method=method)

        # Fall back to linear if cubic produced too many NaN
        if method == "cubic" and zi is not None:
            nan_frac = np.isnan(zi).sum() / zi.size
            if nan_frac > 0.3:
                zi = griddata((x, y), z, (xi_grid, yi_grid), method="linear")

        # Auto levels
        if levels is None:
            zmin = np.nanmin(zi) if zi is not None else 0.0
            zmax = np.nanmax(zi) if zi is not None else 1.0
            if zmin == zmax:
                zmax = zmin + 1.0
            levels = np.linspace(zmin, zmax, n_levels + 1).tolist()

        # Generate contours via matplotlib (non-interactive)
        fig, ax = plt.subplots()
        cs = ax.contourf(xi_grid, yi_grid, zi, levels=levels)
        plt.close(fig)

        # Extract polygons from contour collections
        records = []
        geoms = []
        for i, collection in enumerate(cs.collections):
            paths = collection.get_paths()
            if not paths:
                continue
            polys = []
            for path in paths:
                try:
                    coords = path.vertices
                    if len(coords) >= 4:
                        polys.append(Polygon(coords))
                except Exception:
                    continue
            if polys:
                merged = polys[0] if len(polys) == 1 else MultiPolygon(polys)
                level_min = levels[i]
                level_max = levels[i + 1] if i + 1 < len(levels) else levels[i]
                records.append({
                    "level_min": level_min,
                    "level_max": level_max,
                    "level_label": f"{level_min:.4g} - {level_max:.4g}",
                })
                geoms.append(merged)

        gdf = gpd.GeoDataFrame(records, geometry=geoms, crs=self.transformer.utm_crs)
        return gdf

    def generate_contours_latlon(
        self, df: pd.DataFrame, **kwargs,
    ) -> "gpd.GeoDataFrame":
        """Same as ``generate_contours`` but reprojected to WGS84 (EPSG:4326)."""
        gdf = self.generate_contours(df, **kwargs)
        return gdf.to_crs(epsg=4326)


# ============================================================================
# RASTER EXPORTER
# ============================================================================


class RasterExporter:
    """Export concentration data as georeferenced GeoTIFF rasters.

    Parameters
    ----------
    transformer : CoordinateTransformer
        Provides the CRS for the output raster.
    """

    def __init__(self, transformer: CoordinateTransformer):
        _require("rasterio", HAS_RASTERIO)
        _require("scipy", HAS_SCIPY)
        self.transformer = transformer

    def export_geotiff(
        self,
        df: pd.DataFrame,
        output_path: Union[str, Path],
        resolution: Optional[float] = None,
        method: str = "cubic",
        nodata: float = -9999.0,
        x_col: str = "x",
        y_col: str = "y",
        value_col: str = "concentration",
    ) -> Path:
        """Export a concentration DataFrame as a single-band GeoTIFF.

        Parameters
        ----------
        df : pd.DataFrame
            Must have *x_col*, *y_col*, and *value_col* columns.
        output_path : str or Path
            Destination ``.tif`` file.
        resolution : float, optional
            Pixel size in meters. If None, auto-detected from data spacing.
        method : str
            Interpolation method for ``scipy.interpolate.griddata``.
        nodata : float
            NoData value written to the raster.

        Returns
        -------
        Path
            The written file path.
        """
        output_path = Path(output_path)

        x = df[x_col].values
        y = df[y_col].values
        z = df[value_col].values

        # Auto-detect resolution
        if resolution is None:
            x_sorted = np.sort(np.unique(x))
            if len(x_sorted) > 1:
                resolution = float(np.median(np.diff(x_sorted)))
            else:
                resolution = 100.0  # fallback

        # Build regular grid
        x_min, x_max = x.min(), x.max()
        y_min, y_max = y.min(), y.max()
        ncols = max(1, int(np.ceil((x_max - x_min) / resolution)) + 1)
        nrows = max(1, int(np.ceil((y_max - y_min) / resolution)) + 1)

        xi = np.linspace(x_min, x_max, ncols)
        yi = np.linspace(y_min, y_max, nrows)
        xi_grid, yi_grid = np.meshgrid(xi, yi)

        # Interpolate
        zi = griddata((x, y), z, (xi_grid, yi_grid), method=method)

        # Fall back to linear if cubic produced too many NaN
        if method == "cubic" and zi is not None:
            nan_frac = np.isnan(zi).sum() / zi.size
            if nan_frac > 0.3:
                zi = griddata((x, y), z, (xi_grid, yi_grid), method="linear")

        # Replace remaining NaN with nodata
        if zi is not None:
            zi = np.where(np.isnan(zi), nodata, zi)
        else:
            zi = np.full((nrows, ncols), nodata)

        # Flip so row 0 is the top (northernmost)
        zi = np.flipud(zi)

        # Build affine transform
        transform = from_bounds(x_min, y_min, x_max, y_max, ncols, nrows)

        # Write GeoTIFF
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=nrows,
            width=ncols,
            count=1,
            dtype=zi.dtype,
            crs=self.transformer.utm_crs.to_wkt(),
            transform=transform,
            nodata=nodata,
        ) as dst:
            dst.write(zi, 1)

        return output_path


# ============================================================================
# VECTOR EXPORTER
# ============================================================================


class VectorExporter:
    """Export pyaermod data as vector GIS files (Shapefile, GeoPackage, GeoJSON).

    Parameters
    ----------
    factory : GeoDataFrameFactory
        For creating GeoDataFrames from pyaermod objects.
    """

    def __init__(self, factory: GeoDataFrameFactory):
        self.factory = factory

    def export_sources(
        self,
        sources: list,
        output_path: Union[str, Path],
        driver: str = "GPKG",
    ) -> Path:
        """Export source objects as a vector file."""
        gdf = self.factory.sources_to_geodataframe(sources)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(output_path, driver=driver)
        return output_path

    def export_receptors(
        self,
        receptors,
        output_path: Union[str, Path],
        driver: str = "GPKG",
    ) -> Path:
        """Export receptor locations as a point vector file."""
        gdf = self.factory.receptors_to_geodataframe(receptors)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(output_path, driver=driver)
        return output_path

    def export_concentrations(
        self,
        df: pd.DataFrame,
        output_path: Union[str, Path],
        driver: str = "GPKG",
        as_contours: bool = False,
        contour_levels: Optional[List[float]] = None,
    ) -> Path:
        """Export concentration data as points or contour polygons.

        Parameters
        ----------
        df : pd.DataFrame
            Concentration DataFrame with x, y, concentration columns.
        output_path : str or Path
            Output file path.
        driver : str
            OGR driver name (``'GPKG'``, ``'ESRI Shapefile'``, ``'GeoJSON'``).
        as_contours : bool
            If True, generate filled contour polygons instead of points.
        contour_levels : list of float, optional
            Contour levels (only used when ``as_contours=True``).
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if as_contours:
            gen = ContourGenerator(self.factory.transformer)
            gdf = gen.generate_contours(df, levels=contour_levels)
        else:
            gdf = self.factory.concentrations_to_geodataframe(df)

        gdf.to_file(output_path, driver=driver)
        return output_path

    def export_all(
        self,
        project,
        results=None,
        output_dir: Union[str, Path] = ".",
        driver: str = "GPKG",
    ) -> Dict[str, Path]:
        """Export all project components to a directory.

        Parameters
        ----------
        project : AERMODProject
            The project to export.
        results : AERMODResults, optional
            Parsed results (required for concentration export).
        output_dir : str or Path
            Output directory.
        driver : str
            OGR driver.

        Returns
        -------
        dict
            Mapping of component name to output file path.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        ext = {"GPKG": ".gpkg", "ESRI Shapefile": ".shp", "GeoJSON": ".geojson"}.get(
            driver, ".gpkg"
        )
        paths: Dict[str, Path] = {}

        # Sources
        if project.sources.sources:
            paths["sources"] = self.export_sources(
                project.sources.sources, output_dir / f"sources{ext}", driver,
            )

        # Receptors
        paths["receptors"] = self.export_receptors(
            project.receptors, output_dir / f"receptors{ext}", driver,
        )

        # Concentrations (if results available)
        if results is not None:
            for period in getattr(results, "concentrations", {}):
                conc = results.get_concentrations(period)
                if conc is not None and not conc.empty:
                    safe_period = period.replace("/", "_").replace(" ", "_")
                    paths[f"conc_{safe_period}"] = self.export_concentrations(
                        conc,
                        output_dir / f"concentrations_{safe_period}{ext}",
                        driver,
                    )

        return paths


# ============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ============================================================================


def utm_to_latlon(
    x: float,
    y: float,
    utm_zone: int,
    hemisphere: str = "N",
    datum: str = "WGS84",
) -> Tuple[float, float]:
    """Quick single-point UTM to (latitude, longitude) conversion."""
    t = CoordinateTransformer(utm_zone=utm_zone, hemisphere=hemisphere, datum=datum)
    return t.utm_to_latlon(x, y)


def latlon_to_utm(
    lat: float,
    lon: float,
    datum: str = "WGS84",
) -> Tuple[float, float, int, str]:
    """Quick single-point (lat, lon) to UTM conversion.

    Returns
    -------
    tuple
        ``(easting, northing, utm_zone, hemisphere)``
    """
    t = CoordinateTransformer.from_latlon(lat, lon, datum=datum)
    x, y = t.latlon_to_utm(lat, lon)
    return (x, y, t.utm_zone, t.hemisphere)


def export_concentration_geotiff(
    df: pd.DataFrame,
    output_path: Union[str, Path],
    utm_zone: int,
    hemisphere: str = "N",
    datum: str = "WGS84",
    **kwargs,
) -> Path:
    """One-liner GeoTIFF export from a concentration DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must have ``x``, ``y``, ``concentration`` columns.
    output_path : str or Path
        Destination ``.tif`` file.
    utm_zone : int
        UTM zone number.
    **kwargs
        Passed to ``RasterExporter.export_geotiff``.

    Returns
    -------
    Path
        Written file path.
    """
    t = CoordinateTransformer(utm_zone=utm_zone, hemisphere=hemisphere, datum=datum)
    exporter = RasterExporter(t)
    return exporter.export_geotiff(df, output_path, **kwargs)


def export_concentration_shapefile(
    df: pd.DataFrame,
    output_path: Union[str, Path],
    utm_zone: int,
    hemisphere: str = "N",
    datum: str = "WGS84",
    as_contours: bool = True,
    driver: str = "GPKG",
    **kwargs,
) -> Path:
    """One-liner vector export from a concentration DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must have ``x``, ``y``, ``concentration`` columns.
    output_path : str or Path
        Destination file.
    utm_zone : int
        UTM zone number.
    as_contours : bool
        If True, export filled contour polygons; if False, export points.
    driver : str
        OGR driver name (default ``'GPKG'``).

    Returns
    -------
    Path
        Written file path.
    """
    t = CoordinateTransformer(utm_zone=utm_zone, hemisphere=hemisphere, datum=datum)
    factory = GeoDataFrameFactory(t)
    exporter = VectorExporter(factory)
    return exporter.export_concentrations(
        df, output_path, driver=driver, as_contours=as_contours, **kwargs,
    )

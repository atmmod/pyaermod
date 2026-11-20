"""
PyAERMOD Geospatial Utilities

Coordinate transformations (UTM <-> WGS84), GeoDataFrame creation,
contour polygon generation, and GIS export (GeoTIFF, Shapefile, GeoPackage).

Requires optional dependencies: pyproj, geopandas, rasterio, shapely.
Install with: pip install pyaermod[geo]
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

try:
    import pyproj
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

try:
    import geopandas as gpd
    from shapely.geometry import (
        LineString,
        Point,
        Polygon,
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
    # A Figure made directly, not through pyplot, needs no backend; this
    # module used to switch the whole process to Agg on import, which hid
    # every plt.show() in the notebook that imported it.
    from matplotlib.figure import Figure
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
        zone = min(int((longitude + 180) // 6) + 1, 60)  # 180 E is the edge of zone 60
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

        Returns Point geometries for point and volume sources, Polygon
        geometries for AREA, AREACIRC, AREAPOLY and OPENPIT sources,
        LineString geometries for line and roadway sources and
        MultiLineString for buoyant lines of several segments. The
        outlines are the ones AERMOD builds (:mod:`pyaermod.footprints`):
        an AREA or OPENPIT ``LOCATION`` is its south-west corner and the
        rectangle is rotated clockwise about it.
        """
        from shapely.geometry import MultiLineString

        from pyaermod.footprints import LINES, POINT, POLYGON, source_footprint
        from pyaermod.input_generator import (
            AreaCircSource,
            AreaPolySource,
            AreaSource,
            BuoyLineSource,
            LineSource,
            OpenPitSource,
            PointSource,
            RLineExtSource,
            RLineSource,
            VolumeSource,
        )

        # What each source type carries beside its outline.
        attributes = (
            (RLineExtSource, "RLINEXT", ("emission_rate", "road_width")),
            (BuoyLineSource, "BUOYLINE", ("emission_rate",)),
            (OpenPitSource, "OPENPIT", ("emission_rate", "pit_volume")),
            (LineSource, "LINE", ("emission_rate", "release_height")),
            (RLineSource, "RLINE", ("emission_rate", "release_height")),
            (AreaPolySource, "AREAPOLY", ("emission_rate", "release_height")),
            (AreaCircSource, "AREACIRC", ("emission_rate", "release_height")),
            (AreaSource, "AREA", ("emission_rate", "release_height")),
            (PointSource, "POINT", ("emission_rate", "stack_height")),
            (VolumeSource, "VOLUME", ("emission_rate", "release_height")),
        )

        records = []
        geometries = []

        for src in sources:
            rec: Dict = {"source_id": getattr(src, "source_id", "")}
            for cls, label, names in attributes:
                if isinstance(src, cls):
                    rec["source_type"] = label
                    for name in names:
                        rec[name] = getattr(src, name)
                    break
            else:
                rec["source_type"] = type(src).__name__

            # The outline is the one AERMOD builds (footprints.py), not a
            # reading of the field names.
            fp = source_footprint(src)
            if fp.kind == POINT:
                geometries.append(Point(fp.parts[0][0]))
            elif fp.kind == POLYGON:
                geometries.append(Polygon(fp.parts[0]))
            elif fp.kind == LINES:
                # A buoyant line is always a MultiLineString, so the column
                # keeps one geometry type however many segments it has.
                single = len(fp.parts) == 1 and not isinstance(src, BuoyLineSource)
                geometries.append(
                    LineString(fp.parts[0]) if single else MultiLineString(list(fp.parts))
                )
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

    def receptors_to_geodataframe(self, receptors, sources=()) -> "gpd.GeoDataFrame":
        """Convert a ReceptorPathway to a GeoDataFrame of receptor points.

        Expands CartesianGrid and PolarGrid definitions into individual
        receptor locations. A polar grid is centred on its
        ``origin_source_id`` source when that source is in ``sources``
        (the ``LOCATION`` of ``GRIDPOLR ORIG srcid``), otherwise on
        ``x_origin``/``y_origin``.
        """
        from pyaermod.footprints import receptor_points

        sources = list(sources)
        points = []
        attrs = []

        for grids, grid_type in ((receptors.cartesian_grids, "cartesian"),
                                 (receptors.polar_grids, "polar")):
            for grid in grids:
                for x, y in receptor_points(grid, sources=sources):
                    points.append(Point(x, y))
                    attrs.append({
                        "grid_name": grid.grid_name,
                        "grid_type": grid_type,
                        "z_elev": grid.z_elev,
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

        # Generate contours via matplotlib (an off-screen figure)
        ax = Figure().subplots()
        cs = ax.contourf(xi_grid, yi_grid, zi, levels=levels)

        # Extract the polygons of each band. matplotlib < 3.8 keeps one
        # collection of paths per level; 3.8+ deprecated cs.collections and
        # get_paths() returns one compound Path per level. Either way a
        # Path holds every ring of its band, outer rings and holes alike,
        # each starting at a MOVETO, so Path.to_polygons() gives the rings.
        records = []
        geoms = []

        if hasattr(cs, "collections") and cs.collections:
            level_paths = [col.get_paths() for col in cs.collections]
        else:
            level_paths = [[path] for path in cs.get_paths()]

        for i, paths in enumerate(level_paths):
            # Even-odd fill: a ring inside another is a hole in it, a ring
            # inside that hole an island again. Turning each ring into a
            # solid polygon would cover the holes and overlap the bands.
            band = None
            for path in paths:
                for ring in path.to_polygons(closed_only=True):
                    if len(ring) < 4:
                        continue
                    poly = Polygon(ring)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.is_empty:
                        continue
                    band = poly if band is None else band.symmetric_difference(poly)
            if band is None or band.is_empty:
                continue
            level_min = levels[i]
            level_max = levels[i + 1] if i + 1 < len(levels) else levels[i]
            records.append({
                "level_min": level_min,
                "level_max": level_max,
                "level_label": f"{level_min:.4g} - {level_max:.4g}",
            })
            geoms.append(band)

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
            The receptors are the pixel centres, so a 100 m grid gives
            100 m pixels whose edges lie 50 m beyond the outer receptors.
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

        # Build a regular grid whose pixel centres are the receptors: a
        # grid from x_min to x_max at spacing ``resolution`` has
        # (x_max - x_min) / resolution + 1 centres, and its pixels reach
        # half a pixel beyond the outermost receptors.
        x_min, x_max = x.min(), x.max()
        y_min, y_max = y.min(), y.max()
        ncols = max(1, int(np.ceil((x_max - x_min) / resolution - 1e-9)) + 1)
        nrows = max(1, int(np.ceil((y_max - y_min) / resolution - 1e-9)) + 1)

        xi = x_min + resolution * np.arange(ncols)
        yi = y_min + resolution * np.arange(nrows)
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

        # Affine transform from the top-left pixel's outer corner
        half = resolution / 2.0
        transform = from_bounds(x_min - half, y_min - half,
                                xi[-1] + half, yi[-1] + half, ncols, nrows)

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
        """Export source objects as a vector file.

        A shapefile holds one geometry type, so ``driver='ESRI Shapefile'``
        raises ``ValueError`` for sources that mix points, lines and
        polygons. GeoPackage and GeoJSON hold them together.
        """
        gdf = self.factory.sources_to_geodataframe(sources)
        if driver == "ESRI Shapefile":
            # LineString and MultiLineString are one shapefile type.
            kinds = sorted({t.removeprefix("Multi") for t in gdf.geom_type.dropna()})
            if len(kinds) > 1:
                raise ValueError(
                    "a shapefile holds one geometry type, and these sources have "
                    f"{', '.join(kinds[:-1])} and {kinds[-1]} geometries; use "
                    "driver='GPKG' or driver='GeoJSON', or export each kind of "
                    "source to its own shapefile"
                )
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(output_path, driver=driver)
        return output_path

    def export_receptors(
        self,
        receptors,
        output_path: Union[str, Path],
        driver: str = "GPKG",
        sources=(),
    ) -> Path:
        """Export receptor locations as a point vector file.

        ``sources`` places a polar grid centred on a source (see
        :meth:`GeoDataFrameFactory.receptors_to_geodataframe`).
        """
        gdf = self.factory.receptors_to_geodataframe(receptors, sources=sources)
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
            OGR driver. ``'ESRI Shapefile'`` raises ``ValueError`` when
            the sources mix points, lines and polygons (see
            :meth:`export_sources`).

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
            sources=project.sources.sources,
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

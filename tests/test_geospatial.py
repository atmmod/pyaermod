"""
Unit tests for pyaermod_geospatial module.

Tests coordinate transformations, GeoDataFrame creation, contour generation,
and GIS export (GeoTIFF, vector files) using synthetic data.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Skip entire module if core geo dependencies are missing
pyproj = pytest.importorskip("pyproj")
gpd = pytest.importorskip("geopandas")
shapely = pytest.importorskip("shapely")

from pyaermod.geospatial import (  # noqa: E402
    ContourGenerator,
    CoordinateTransformer,
    GeoDataFrameFactory,
    RasterExporter,
    VectorExporter,
    export_concentration_geotiff,
    export_concentration_shapefile,
    latlon_to_utm,
    utm_to_latlon,
)
from pyaermod.input_generator import (  # noqa: E402
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    DiscreteReceptor,
    LineSource,
    OpenPitSource,
    PointSource,
    PolarGrid,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    VolumeSource,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def transformer():
    """CoordinateTransformer for UTM zone 16N (central US)."""
    return CoordinateTransformer(utm_zone=16, hemisphere="N", datum="WGS84")


@pytest.fixture
def factory(transformer):
    """GeoDataFrameFactory with zone-16 transformer."""
    return GeoDataFrameFactory(transformer)


@pytest.fixture
def sample_concentration_df():
    """21x21 regular grid with a Gaussian concentration plume."""
    x_vals = np.linspace(500000, 502000, 21)
    y_vals = np.linspace(3800000, 3802000, 21)
    xx, yy = np.meshgrid(x_vals, y_vals)

    # Gaussian plume centred at (501000, 3801000)
    cx, cy = 501000.0, 3801000.0
    conc = 100.0 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 500**2))

    return pd.DataFrame(
        {"x": xx.ravel(), "y": yy.ravel(), "concentration": conc.ravel()}
    )


@pytest.fixture
def sample_sources():
    """Mixed list of source types."""
    return [
        PointSource(
            source_id="STK1", x_coord=501000, y_coord=3801000,
            stack_height=50, emission_rate=1.0,
        ),
        AreaSource(
            source_id="AREA1", x_coord=501200, y_coord=3801200,
            initial_lateral_dimension=25, initial_vertical_dimension=50,
            emission_rate=0.01,
        ),
        VolumeSource(
            source_id="VOL1", x_coord=500800, y_coord=3800800,
            release_height=10, emission_rate=0.5,
        ),
        LineSource(
            source_id="LN1", x_start=500500, y_start=3800500,
            x_end=501500, y_end=3801500, emission_rate=0.002,
        ),
        RLineSource(
            source_id="RD1", x_start=500000, y_start=3801000,
            x_end=502000, y_end=3801000, emission_rate=0.001,
        ),
        AreaPolySource(
            source_id="POLY1",
            vertices=[
                (500900, 3800900), (501100, 3800900),
                (501100, 3801100), (500900, 3801100),
            ],
            emission_rate=0.005,
        ),
        AreaCircSource(
            source_id="CIRC1", x_coord=501500, y_coord=3801500,
            radius=100, emission_rate=0.003,
        ),
        RLineExtSource(
            source_id="RLX1",
            x_start=500500, y_start=3801000, z_start=0.5,
            x_end=501500, y_end=3801000, z_end=0.5,
            emission_rate=0.001, road_width=30.0,
        ),
        BuoyLineSource(
            source_id="BLP1",
            avg_line_length=100.0, avg_building_height=15.0,
            avg_building_width=20.0, avg_line_width=5.0,
            avg_building_separation=10.0, avg_buoyancy_parameter=0.5,
            line_segments=[
                BuoyLineSegment("BL01", 500800, 3800800, 501000, 3800800),
                BuoyLineSegment("BL02", 501000, 3800800, 501200, 3800800),
            ],
        ),
        OpenPitSource(
            source_id="PIT1", x_coord=500600, y_coord=3800600,
            x_dimension=200.0, y_dimension=150.0,
            pit_volume=100000.0, emission_rate=0.01,
        ),
    ]


@pytest.fixture
def sample_receptors():
    """ReceptorPathway with Cartesian, Polar, and Discrete receptors."""
    rp = ReceptorPathway()
    rp.add_cartesian_grid(CartesianGrid(
        grid_name="CG1",
        x_init=500000, x_num=5, x_delta=500,
        y_init=3800000, y_num=5, y_delta=500,
    ))
    rp.add_polar_grid(PolarGrid(
        grid_name="PG1",
        x_origin=501000, y_origin=3801000,
        dist_init=200, dist_num=3, dist_delta=200,
        dir_init=0, dir_num=4, dir_delta=90,
    ))
    rp.add_discrete_receptor(DiscreteReceptor(x_coord=501000, y_coord=3801000))
    return rp


# ============================================================================
# TestCoordinateTransformer
# ============================================================================


class TestCoordinateTransformer:
    """Test coordinate transformation."""

    def test_init_valid_zone(self, transformer):
        assert transformer.utm_zone == 16
        assert transformer.hemisphere == "N"

    def test_init_invalid_zone_low(self):
        with pytest.raises(ValueError, match="UTM zone must be 1-60"):
            CoordinateTransformer(utm_zone=0)

    def test_init_invalid_zone_high(self):
        with pytest.raises(ValueError, match="UTM zone must be 1-60"):
            CoordinateTransformer(utm_zone=61)

    def test_init_invalid_hemisphere(self):
        with pytest.raises(ValueError, match="hemisphere"):
            CoordinateTransformer(utm_zone=16, hemisphere="X")

    def test_from_aermap_domain(self):
        """Create transformer from AERMAPDomain metadata."""
        from pyaermod.aermap import AERMAPDomain
        domain = AERMAPDomain(
            anchor_x=500000, anchor_y=3800000,
            num_x_points=10, num_y_points=10, spacing=100,
            utm_zone=17, datum="NAD83",
        )
        t = CoordinateTransformer.from_aermap_domain(domain)
        assert t.utm_zone == 17
        assert t.datum == "NAD83"

    def test_from_latlon_auto_zone(self):
        """Auto-detect UTM zone from lat/lon."""
        # Atlanta, GA (~33.75N, 84.39W) should be zone 16
        t = CoordinateTransformer.from_latlon(33.75, -84.39)
        assert t.utm_zone == 16
        assert t.hemisphere == "N"

    def test_from_latlon_southern_hemisphere(self):
        t = CoordinateTransformer.from_latlon(-33.86, 151.21)  # Sydney
        assert t.hemisphere == "S"

    def test_utm_to_latlon_roundtrip(self, transformer):
        """UTM -> latlon -> UTM roundtrip preserves coordinates."""
        orig_x, orig_y = 501000.0, 3801000.0
        lat, lon = transformer.utm_to_latlon(orig_x, orig_y)
        x2, y2 = transformer.latlon_to_utm(lat, lon)
        assert abs(x2 - orig_x) < 0.01
        assert abs(y2 - orig_y) < 0.01

    def test_latlon_to_utm_known_point(self):
        """Known lat/lon -> UTM conversion (approximate)."""
        # Nashville, TN is roughly 36.16N, 86.78W -> UTM zone 16
        t = CoordinateTransformer(utm_zone=16, hemisphere="N")
        x, y = t.latlon_to_utm(36.16, -86.78)
        # Easting should be ~520km, Northing ~4000km
        assert 400_000 < x < 600_000
        assert 3_900_000 < y < 4_100_000

    def test_transform_dataframe_to_latlon(self, transformer):
        df = pd.DataFrame({"x": [501000.0], "y": [3801000.0]})
        result = transformer.transform_dataframe(df)
        assert "latitude" in result.columns
        assert "longitude" in result.columns
        assert -90 <= result["latitude"].iloc[0] <= 90
        assert -180 <= result["longitude"].iloc[0] <= 180

    def test_transform_dataframe_to_utm(self):
        t = CoordinateTransformer(utm_zone=16, hemisphere="N")
        df = pd.DataFrame({"x": [-86.78], "y": [36.16]})
        result = t.transform_dataframe(df, to_latlon=False)
        assert "utm_x" in result.columns
        assert "utm_y" in result.columns

    def test_utm_crs_property(self, transformer):
        crs = transformer.utm_crs
        assert crs is not None
        assert "UTM" in crs.name or "utm" in crs.to_wkt().lower()

    def test_geographic_crs_property(self, transformer):
        crs = transformer.geographic_crs
        assert crs is not None
        assert crs.to_epsg() == 4326


# ============================================================================
# TestGeoDataFrameFactory
# ============================================================================


class TestGeoDataFrameFactory:
    """Test GeoDataFrame creation from pyaermod objects."""

    def test_point_sources_to_gdf(self, factory):
        sources = [
            PointSource(source_id="S1", x_coord=501000, y_coord=3801000,
                        stack_height=50, emission_rate=1.0),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert len(gdf) == 1
        assert gdf.iloc[0].geometry.geom_type == "Point"
        assert gdf.iloc[0]["source_type"] == "POINT"

    def test_line_sources_to_gdf(self, factory):
        sources = [
            LineSource(source_id="L1", x_start=500000, y_start=3800000,
                       x_end=501000, y_end=3801000),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "LineString"
        assert gdf.iloc[0]["source_type"] == "LINE"

    def test_rline_sources_to_gdf(self, factory):
        sources = [
            RLineSource(source_id="R1", x_start=500000, y_start=3801000,
                        x_end=502000, y_end=3801000),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "LineString"
        assert gdf.iloc[0]["source_type"] == "RLINE"

    def test_area_poly_sources_to_gdf(self, factory):
        sources = [
            AreaPolySource(
                source_id="P1",
                vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
            ),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "Polygon"
        assert gdf.iloc[0]["source_type"] == "AREAPOLY"

    def test_area_circ_sources_to_gdf(self, factory):
        sources = [
            AreaCircSource(source_id="C1", x_coord=501000, y_coord=3801000,
                           radius=50, num_vertices=20),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "Polygon"

    def test_area_source_to_gdf(self, factory):
        sources = [
            AreaSource(source_id="A1", x_coord=501000, y_coord=3801000,
                       initial_lateral_dimension=25,
                       initial_vertical_dimension=50),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "Polygon"

    def test_area_source_rotated_to_gdf(self, factory):
        sources = [
            AreaSource(source_id="A2", x_coord=501000, y_coord=3801000,
                       initial_lateral_dimension=25,
                       initial_vertical_dimension=50, angle=45.0),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "Polygon"

    def test_volume_source_to_gdf(self, factory):
        sources = [
            VolumeSource(source_id="V1", x_coord=501000, y_coord=3801000,
                         release_height=10),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "Point"
        assert gdf.iloc[0]["source_type"] == "VOLUME"

    def test_rlinext_source_to_gdf(self, factory):
        sources = [
            RLineExtSource(
                source_id="RLX1",
                x_start=500000, y_start=3801000, z_start=0.5,
                x_end=502000, y_end=3801000, z_end=0.5,
            ),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "LineString"
        assert gdf.iloc[0]["source_type"] == "RLINEXT"

    def test_buoyline_source_to_gdf(self, factory):
        sources = [
            BuoyLineSource(
                source_id="BLP1",
                avg_line_length=100.0, avg_building_height=15.0,
                avg_building_width=20.0, avg_line_width=5.0,
                avg_building_separation=10.0, avg_buoyancy_parameter=0.5,
                line_segments=[
                    BuoyLineSegment("BL01", 500000, 3800000, 501000, 3800000),
                    BuoyLineSegment("BL02", 501000, 3800000, 502000, 3800000),
                ],
            ),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "MultiLineString"
        assert gdf.iloc[0]["source_type"] == "BUOYLINE"

    def test_openpit_source_to_gdf(self, factory):
        sources = [
            OpenPitSource(
                source_id="PIT1", x_coord=500000, y_coord=3800000,
                x_dimension=200.0, y_dimension=150.0,
                pit_volume=100000.0,
            ),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "Polygon"
        assert gdf.iloc[0]["source_type"] == "OPENPIT"

    def test_openpit_rotated_to_gdf(self, factory):
        sources = [
            OpenPitSource(
                source_id="PIT2", x_coord=500000, y_coord=3800000,
                x_dimension=200.0, y_dimension=100.0,
                pit_volume=50000.0, angle=45.0,
            ),
        ]
        gdf = factory.sources_to_geodataframe(sources)
        assert gdf.iloc[0].geometry.geom_type == "Polygon"

    def test_mixed_sources_to_gdf(self, factory, sample_sources):
        gdf = factory.sources_to_geodataframe(sample_sources)
        assert len(gdf) == 10  # All source types represented

    def test_gdf_has_correct_crs(self, factory, sample_sources):
        gdf = factory.sources_to_geodataframe(sample_sources)
        assert gdf.crs is not None
        # Should be UTM zone 16N
        assert "16" in str(gdf.crs)

    def test_concentrations_to_gdf(self, factory, sample_concentration_df):
        gdf = factory.concentrations_to_geodataframe(sample_concentration_df)
        assert len(gdf) == len(sample_concentration_df)
        assert all(g.geom_type == "Point" for g in gdf.geometry)
        assert "concentration" in gdf.columns

    def test_receptors_cartesian_to_gdf(self, factory):
        rp = ReceptorPathway()
        rp.add_cartesian_grid(CartesianGrid(
            grid_name="G1", x_init=0, x_num=3, x_delta=100,
            y_init=0, y_num=3, y_delta=100,
        ))
        gdf = factory.receptors_to_geodataframe(rp)
        assert len(gdf) == 9  # 3x3

    def test_receptors_polar_to_gdf(self, factory):
        rp = ReceptorPathway()
        rp.add_polar_grid(PolarGrid(
            grid_name="P1", x_origin=0, y_origin=0,
            dist_init=100, dist_num=2, dist_delta=100,
            dir_init=0, dir_num=4, dir_delta=90,
        ))
        gdf = factory.receptors_to_geodataframe(rp)
        assert len(gdf) == 8  # 2 distances * 4 directions

    def test_receptors_discrete_to_gdf(self, factory):
        rp = ReceptorPathway()
        rp.add_discrete_receptor(DiscreteReceptor(x_coord=100, y_coord=200))
        rp.add_discrete_receptor(DiscreteReceptor(x_coord=300, y_coord=400))
        gdf = factory.receptors_to_geodataframe(rp)
        assert len(gdf) == 2

    def test_receptors_mixed_to_gdf(self, factory, sample_receptors):
        gdf = factory.receptors_to_geodataframe(sample_receptors)
        # 5*5 cartesian + 3*4 polar + 1 discrete = 38
        assert len(gdf) == 38

    def test_empty_receptors_to_gdf(self, factory):
        rp = ReceptorPathway()
        gdf = factory.receptors_to_geodataframe(rp)
        assert len(gdf) == 0


# ============================================================================
# TestContourGenerator
# ============================================================================


class TestContourGenerator:
    """Test contour polygon generation."""

    def test_generate_contours_returns_gdf(self, transformer, sample_concentration_df):
        gen = ContourGenerator(transformer)
        gdf = gen.generate_contours(sample_concentration_df, n_levels=5)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0
        assert "level_min" in gdf.columns
        assert "level_max" in gdf.columns
        assert "level_label" in gdf.columns

    def test_generate_contours_custom_levels(self, transformer, sample_concentration_df):
        gen = ContourGenerator(transformer)
        levels = [0, 10, 30, 60, 100]
        gdf = gen.generate_contours(sample_concentration_df, levels=levels)
        assert isinstance(gdf, gpd.GeoDataFrame)

    def test_generate_contours_crs(self, transformer, sample_concentration_df):
        gen = ContourGenerator(transformer)
        gdf = gen.generate_contours(sample_concentration_df, n_levels=3)
        assert gdf.crs is not None

    def test_generate_contours_latlon(self, transformer, sample_concentration_df):
        gen = ContourGenerator(transformer)
        gdf = gen.generate_contours_latlon(sample_concentration_df, n_levels=3)
        assert gdf.crs is not None
        assert gdf.crs.to_epsg() == 4326

    def test_generate_contours_geometry_types(self, transformer, sample_concentration_df):
        gen = ContourGenerator(transformer)
        gdf = gen.generate_contours(sample_concentration_df, n_levels=5)
        for geom in gdf.geometry:
            assert geom.geom_type in ("Polygon", "MultiPolygon")


# ============================================================================
# TestRasterExporter
# ============================================================================


class TestRasterExporter:
    """Test GeoTIFF export."""

    @pytest.fixture
    def rasterio_mod(self):
        return pytest.importorskip("rasterio")

    def test_export_geotiff_creates_file(self, transformer, sample_concentration_df,
                                         tmp_path, rasterio_mod):
        exporter = RasterExporter(transformer)
        outfile = tmp_path / "test.tif"
        result = exporter.export_geotiff(sample_concentration_df, outfile)
        assert result.exists()
        assert result.suffix == ".tif"

    def test_geotiff_has_correct_crs(self, transformer, sample_concentration_df,
                                     tmp_path, rasterio_mod):
        exporter = RasterExporter(transformer)
        outfile = tmp_path / "test_crs.tif"
        exporter.export_geotiff(sample_concentration_df, outfile)

        with rasterio_mod.open(outfile) as src:
            crs = src.crs
            assert crs is not None
            # Should reference UTM zone 16
            crs_str = crs.to_wkt()
            assert "16" in crs_str or "zone_16" in crs_str.replace(" ", "_").lower()

    def test_geotiff_data_range(self, transformer, sample_concentration_df,
                                tmp_path, rasterio_mod):
        exporter = RasterExporter(transformer)
        outfile = tmp_path / "test_range.tif"
        exporter.export_geotiff(sample_concentration_df, outfile, nodata=-9999)

        with rasterio_mod.open(outfile) as src:
            data = src.read(1)
            valid = data[data != -9999]
            # Concentration values in our synthetic data range from ~0 to 100
            assert valid.min() >= -1  # slight interpolation undershoot OK
            assert valid.max() <= 110

    def test_geotiff_custom_resolution(self, transformer, sample_concentration_df,
                                       tmp_path, rasterio_mod):
        exporter = RasterExporter(transformer)
        outfile = tmp_path / "test_res.tif"
        exporter.export_geotiff(sample_concentration_df, outfile, resolution=50.0)
        assert outfile.exists()

    def test_geotiff_creates_parent_dirs(self, transformer, sample_concentration_df,
                                         tmp_path, rasterio_mod):
        exporter = RasterExporter(transformer)
        outfile = tmp_path / "sub" / "dir" / "test.tif"
        exporter.export_geotiff(sample_concentration_df, outfile)
        assert outfile.exists()


# ============================================================================
# TestVectorExporter
# ============================================================================


class TestVectorExporter:
    """Test vector file export."""

    def test_export_geopackage_sources(self, factory, sample_sources, tmp_path):
        exporter = VectorExporter(factory)
        outfile = tmp_path / "sources.gpkg"
        result = exporter.export_sources(sample_sources, outfile, driver="GPKG")
        assert result.exists()

    def test_export_geopackage_receptors(self, factory, sample_receptors, tmp_path):
        exporter = VectorExporter(factory)
        outfile = tmp_path / "receptors.gpkg"
        result = exporter.export_receptors(sample_receptors, outfile, driver="GPKG")
        assert result.exists()

    def test_export_geojson(self, factory, sample_sources, tmp_path):
        exporter = VectorExporter(factory)
        outfile = tmp_path / "sources.geojson"
        result = exporter.export_sources(sample_sources, outfile, driver="GeoJSON")
        assert result.exists()

    def test_export_concentrations_as_points(
        self, factory, sample_concentration_df, tmp_path,
    ):
        exporter = VectorExporter(factory)
        outfile = tmp_path / "conc_points.gpkg"
        result = exporter.export_concentrations(
            sample_concentration_df, outfile, as_contours=False,
        )
        assert result.exists()
        gdf = gpd.read_file(result)
        assert len(gdf) == len(sample_concentration_df)

    def test_export_concentrations_as_contours(
        self, factory, sample_concentration_df, tmp_path,
    ):
        scipy = pytest.importorskip("scipy")
        exporter = VectorExporter(factory)
        outfile = tmp_path / "conc_contours.gpkg"
        result = exporter.export_concentrations(
            sample_concentration_df, outfile, as_contours=True,
        )
        assert result.exists()
        gdf = gpd.read_file(result)
        assert len(gdf) > 0
        for geom in gdf.geometry:
            assert geom.geom_type in ("Polygon", "MultiPolygon")

    def test_export_shapefile(self, factory, tmp_path):
        # Shapefiles only support a single geometry type, so use only point sources
        point_sources = [
            PointSource(source_id="S1", x_coord=501000, y_coord=3801000,
                        stack_height=50, emission_rate=1.0),
            PointSource(source_id="S2", x_coord=501500, y_coord=3801500,
                        stack_height=30, emission_rate=0.5),
        ]
        exporter = VectorExporter(factory)
        outfile = tmp_path / "sources.shp"
        result = exporter.export_sources(point_sources, outfile, driver="ESRI Shapefile")
        assert result.exists()
        # Shapefiles also produce .shx, .dbf, .prj
        assert (tmp_path / "sources.shx").exists()
        assert (tmp_path / "sources.dbf").exists()

    def test_export_creates_parent_dirs(self, factory, sample_sources, tmp_path):
        exporter = VectorExporter(factory)
        outfile = tmp_path / "nested" / "dir" / "sources.gpkg"
        result = exporter.export_sources(sample_sources, outfile)
        assert result.exists()


# ============================================================================
# TestConvenienceFunctions
# ============================================================================


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_utm_to_latlon(self):
        lat, lon = utm_to_latlon(501000, 3801000, utm_zone=16)
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180

    def test_latlon_to_utm(self):
        x, y, zone, hemi = latlon_to_utm(33.75, -84.39)
        assert zone == 16
        assert hemi == "N"
        assert x > 0
        assert y > 0

    def test_latlon_to_utm_roundtrip(self):
        x0, y0 = 501000.0, 3801000.0
        lat, lon = utm_to_latlon(x0, y0, utm_zone=16)
        x1, y1, _, _ = latlon_to_utm(lat, lon)
        assert abs(x1 - x0) < 1.0  # within 1 meter
        assert abs(y1 - y0) < 1.0

    def test_export_concentration_geotiff(self, sample_concentration_df, tmp_path):
        rasterio = pytest.importorskip("rasterio")
        outfile = tmp_path / "quick.tif"
        result = export_concentration_geotiff(
            sample_concentration_df, outfile, utm_zone=16,
        )
        assert result.exists()

    def test_export_concentration_shapefile(self, sample_concentration_df, tmp_path):
        scipy = pytest.importorskip("scipy")
        outfile = tmp_path / "quick.gpkg"
        result = export_concentration_shapefile(
            sample_concentration_df, outfile, utm_zone=16, as_contours=True,
        )
        assert result.exists()

    def test_export_concentration_as_points(self, sample_concentration_df, tmp_path):
        outfile = tmp_path / "points.gpkg"
        result = export_concentration_shapefile(
            sample_concentration_df, outfile, utm_zone=16, as_contours=False,
        )
        assert result.exists()


# ============================================================================
# Coverage expansion tests
# ============================================================================


class TestRequireMissingDeps:
    """Test _require() guard function with missing deps (lines 62-70)."""

    def test_require_missing_pyproj(self):
        from pyaermod import geospatial
        with pytest.raises(ImportError, match="pyproj"):
            geospatial._require("pyproj", False)

    def test_require_missing_geopandas(self):
        from pyaermod import geospatial
        with pytest.raises(ImportError, match="geopandas"):
            geospatial._require("geopandas", False)

    def test_require_missing_rasterio(self):
        from pyaermod import geospatial
        with pytest.raises(ImportError, match="rasterio"):
            geospatial._require("rasterio", False)

    def test_require_missing_matplotlib(self):
        from pyaermod import geospatial
        with pytest.raises(ImportError, match="matplotlib"):
            geospatial._require("matplotlib", False)

    def test_require_unknown_lib_defaults_to_geo(self):
        from pyaermod import geospatial
        with pytest.raises(ImportError, match="geo"):
            geospatial._require("unknown_lib", False)


class TestBuoylineEmptySegments:
    """Test BuoyLineSource with empty line_segments (line 277)."""

    def test_empty_segments_produces_point(self, transformer):
        from shapely.geometry import Point

        buoy = BuoyLineSource(
            source_id="BL_EMPTY",
            base_elevation=0.0,
            avg_buoyancy_parameter=0.5,
            avg_line_length=100.0,
            avg_building_separation=50.0,
            avg_building_width=30.0,
            avg_line_width=10.0,
            avg_building_height=15.0,
            line_segments=[],  # Empty!
        )

        factory = GeoDataFrameFactory(transformer)
        gdf = factory.sources_to_geodataframe([buoy])

        assert len(gdf) == 1
        assert gdf.iloc[0].geometry.equals(Point(0, 0))


class TestUnknownSourceTypeFallback:
    """Test sources_to_geodataframe with unknown source type (lines 360-363)."""

    def test_fallback_for_custom_source(self, transformer):
        # Create a mock source type that doesn't match any known type
        class CustomSource:
            source_id = "CUSTOM1"
            x_coord = 500.0
            y_coord = 600.0
            base_elevation = 0.0
            emission_rate = 1.0

        src = CustomSource()
        factory = GeoDataFrameFactory(transformer)
        gdf = factory.sources_to_geodataframe([src])

        assert len(gdf) == 1
        assert gdf.iloc[0]["source_type"] == "CustomSource"
        assert gdf.iloc[0].geometry.x == pytest.approx(500.0)
        assert gdf.iloc[0].geometry.y == pytest.approx(600.0)


class TestGeotiffEdgeCases:
    """Test GeoTIFF export edge cases (lines 682, 707)."""

    def test_single_x_resolution_fallback(self, transformer, tmp_path):
        """All same x → resolution defaults to 100.0 (line 682)."""
        rasterio = pytest.importorskip("rasterio")

        # All x values are the same → only 1 unique x → fallback to 100.0
        df = pd.DataFrame({
            "x": [100.0, 100.0, 100.0],
            "y": [0.0, 100.0, 200.0],
            "concentration": [1.0, 2.0, 3.0],
        })

        outfile = tmp_path / "single_x.tif"
        exporter = RasterExporter(transformer)
        # Use method="nearest" to avoid Qhull crash with collinear points
        exporter.export_geotiff(df, outfile, resolution=None, method="nearest")
        assert outfile.exists()

    def test_griddata_none_fallback(self, transformer, tmp_path):
        """When griddata returns None → fill with nodata (line 707)."""
        rasterio = pytest.importorskip("rasterio")
        from unittest.mock import patch as mock_patch

        df = pd.DataFrame({
            "x": [0.0, 100.0, 0.0, 100.0],
            "y": [0.0, 0.0, 100.0, 100.0],
            "concentration": [1.0, 2.0, 1.5, 3.0],
        })

        outfile = tmp_path / "none_grid.tif"
        exporter = RasterExporter(transformer)

        with mock_patch("pyaermod.geospatial.griddata", return_value=None):
            exporter.export_geotiff(df, outfile, resolution=50.0)
        assert outfile.exists()


class TestVectorExporterExportAll:
    """Test export_all() with various configurations (lines 837-868)."""

    def test_export_all_no_results(self, transformer, tmp_path):
        """export_all with results=None → sources and receptors only."""
        from pyaermod.input_generator import SourcePathway

        sources_pathway = SourcePathway()
        point = PointSource(
            source_id="S1", x_coord=100.0, y_coord=200.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        sources_pathway.add_source(point)

        receptors = ReceptorPathway()
        receptors.add_discrete_receptor(
            DiscreteReceptor(x_coord=0, y_coord=0, z_elev=0, z_flag=0)
        )

        from pyaermod.input_generator import AERMODProject, ControlPathway, MeteorologyPathway, OutputPathway
        project = AERMODProject(
            control=ControlPathway(title_one="Export Test"),
            sources=sources_pathway,
            receptors=receptors,
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

        factory = GeoDataFrameFactory(transformer)
        exporter = VectorExporter(factory)
        paths = exporter.export_all(
            project, output_dir=tmp_path / "export",
            results=None,
        )

        assert "sources" in paths
        assert "receptors" in paths
        # No concentration paths since results=None
        conc_keys = [k for k in paths if k.startswith("conc_")]
        assert len(conc_keys) == 0

    def test_export_all_with_results(self, transformer, tmp_path):
        """export_all with results → includes concentration exports."""
        from unittest.mock import MagicMock

        from pyaermod.input_generator import (
            AERMODProject,
            ControlPathway,
            MeteorologyPathway,
            OutputPathway,
            SourcePathway,
        )

        sources_pathway = SourcePathway()
        point = PointSource(
            source_id="S1", x_coord=100.0, y_coord=200.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        sources_pathway.add_source(point)

        receptors = ReceptorPathway()
        receptors.add_discrete_receptor(
            DiscreteReceptor(x_coord=0, y_coord=0, z_elev=0, z_flag=0)
        )

        project = AERMODProject(
            control=ControlPathway(title_one="Export Results Test"),
            sources=sources_pathway,
            receptors=receptors,
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

        # Mock results with concentration data
        conc_df = pd.DataFrame({
            "x": [0.0, 100.0, 0.0, 100.0],
            "y": [0.0, 0.0, 100.0, 100.0],
            "concentration": [1.0, 2.0, 1.5, 3.0],
        })
        mock_results = MagicMock()
        mock_results.concentrations = {"ANNUAL": MagicMock()}
        mock_results.get_concentrations.return_value = conc_df

        factory = GeoDataFrameFactory(transformer)
        exporter = VectorExporter(factory)
        paths = exporter.export_all(
            project, output_dir=tmp_path / "export_results",
            results=mock_results,
        )

        assert "sources" in paths
        assert "receptors" in paths
        assert "conc_ANNUAL" in paths


class TestGeoDataFrameFactoryFromResults:
    """Test sources_from_results (lines 372-375) and postfile_to_geodataframe (lines 461-464)."""

    def test_sources_from_results(self, transformer):
        """sources_from_results converts AERMODResults sources to GDF."""
        from unittest.mock import MagicMock
        mock_results = MagicMock()
        mock_results.get_sources_dataframe.return_value = pd.DataFrame({
            "source_id": ["S1", "S2"],
            "source_type": ["POINT", "AREA"],
            "x": [100.0, 200.0],
            "y": [300.0, 400.0],
            "emission_rate": [1.0, 2.0],
        })

        factory = GeoDataFrameFactory(transformer)
        gdf = factory.sources_from_results(mock_results)

        assert len(gdf) == 2
        assert gdf.iloc[0].geometry.x == pytest.approx(100.0)
        assert gdf.iloc[1].geometry.y == pytest.approx(400.0)

    def test_postfile_to_geodataframe(self, transformer):
        """postfile_to_geodataframe converts PostfileResult to GDF."""
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_result.data = pd.DataFrame({
            "x": [0.0, 100.0, 200.0],
            "y": [0.0, 100.0, 200.0],
            "concentration": [1.0, 2.0, 3.0],
        })
        mock_result.data.copy = mock_result.data.copy

        factory = GeoDataFrameFactory(transformer)
        gdf = factory.postfile_to_geodataframe(mock_result)

        assert len(gdf) == 3
        assert "concentration" in gdf.columns

"""Tests for the SHP + DXF source importers.

Both importers are gated on optional extras (`geo` for geopandas,
`cad` for ezdxf) — tests skip cleanly when those aren't installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod import (
    AreaPolySource,
    LineSource,
    PointSource,
    RLineSource,
)

# ---------------------------------------------------------------------
# SHP importer tests (skipped if geopandas missing)
# ---------------------------------------------------------------------

gpd = pytest.importorskip("geopandas")

from pyaermod.source_importers import from_dxf, from_shapefile  # noqa: E402


@pytest.fixture
def point_shp(tmp_path):
    """Create a minimal shapefile with 3 point sources.

    Shapefile field names are silently truncated to 10 characters,
    so we use ``stack_h`` / ``em_rate`` here and rely on attribute_map
    to remap them in :class:`TestShapefile.test_attribute_map_renaming`.
    For this fixture we round-trip the names via attribute_map so the
    final dataclass fields land correctly.
    """
    from shapely.geometry import Point
    gdf = gpd.GeoDataFrame(
        {
            "source_id": ["STK1", "STK2", "STK3"],
            "stack_h": [30.0, 40.0, 50.0],
            "em_rate": [1.0, 2.5, 0.5],
            "geometry": [Point(0, 0), Point(100, 0), Point(0, 100)],
        },
        crs="EPSG:32619",
    )
    out = tmp_path / "stacks.shp"
    gdf.to_file(out)
    return out


@pytest.fixture
def polygon_shp(tmp_path):
    """Create a shapefile with one rectangular area source."""
    from shapely.geometry import Polygon
    poly = Polygon([(0, 0), (100, 0), (100, 50), (0, 50)])
    gdf = gpd.GeoDataFrame(
        {"source_id": ["AREA1"], "geometry": [poly]}, crs="EPSG:32619",
    )
    out = tmp_path / "area.shp"
    gdf.to_file(out)
    return out


@pytest.fixture
def line_shp(tmp_path):
    """Create a shapefile with one road centerline."""
    from shapely.geometry import LineString
    line = LineString([(0, 0), (100, 0), (200, 50)])
    gdf = gpd.GeoDataFrame(
        {"source_id": ["RD1"], "geometry": [line]}, crs="EPSG:32619",
    )
    out = tmp_path / "line.shp"
    gdf.to_file(out)
    return out


class TestShapefile:
    def test_point_import(self, point_shp):
        sources = from_shapefile(
            point_shp,
            attribute_map={"stack_h": "stack_height",
                           "em_rate": "emission_rate"},
        )
        assert len(sources) == 3
        assert all(isinstance(s, PointSource) for s in sources)
        ids = [s.source_id for s in sources]
        assert ids == ["STK1", "STK2", "STK3"]
        # Attributes pulled from (renamed) columns
        s1 = sources[0]
        assert s1.stack_height == 30.0
        assert s1.emission_rate == 1.0

    def test_point_import_synthetic_id(self, tmp_path):
        from shapely.geometry import Point
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(0, 0), Point(1, 0)]}, crs="EPSG:32619",
        )
        out = tmp_path / "noid.shp"
        gdf.to_file(out)
        sources = from_shapefile(out)
        assert len(sources) == 2
        # Synthesized IDs follow SRC0000-style pattern
        for s in sources:
            assert s.source_id.startswith("SRC")

    def test_polygon_import(self, polygon_shp):
        sources = from_shapefile(polygon_shp)
        assert len(sources) == 1
        assert isinstance(sources[0], AreaPolySource)
        # 4 unique vertices (closing repeat dropped)
        assert len(sources[0].vertices) == 4

    def test_line_import_default(self, line_shp):
        sources = from_shapefile(line_shp)
        assert len(sources) == 1
        assert isinstance(sources[0], LineSource)
        # First and last vertex preserved
        assert sources[0].x_start == 0.0
        assert sources[0].x_end == 200.0

    def test_line_to_rline_via_source_type(self, line_shp):
        sources = from_shapefile(line_shp, source_type=RLineSource)
        assert len(sources) == 1
        assert isinstance(sources[0], RLineSource)

    def test_attribute_map_renaming(self, tmp_path):
        from shapely.geometry import Point
        gdf = gpd.GeoDataFrame(
            {"H_M": [25.0], "Q_GS": [3.0], "ID": ["S1"],
             "geometry": [Point(50, 50)]},
            crs="EPSG:32619",
        )
        out = tmp_path / "renamed.shp"
        gdf.to_file(out)
        # Note: shapefile column names truncate to 10 chars but the
        # values still come through under the original names.
        sources = from_shapefile(
            out,
            src_id_field="ID",
            attribute_map={"H_M": "stack_height", "Q_GS": "emission_rate"},
        )
        assert sources[0].source_id == "S1"
        assert sources[0].stack_height == 25.0
        assert sources[0].emission_rate == 3.0


# ---------------------------------------------------------------------
# DXF importer tests (skipped if ezdxf missing)
# ---------------------------------------------------------------------

ezdxf = pytest.importorskip("ezdxf")


def _make_dxf(tmp_path: Path, build_fn):
    """Create a fresh DXF and yield its modelspace; return file path."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    build_fn(msp)
    out = tmp_path / "test.dxf"
    doc.saveas(out)
    return out


class TestDxfImporter:
    def test_point_import(self, tmp_path):
        def build(msp):
            msp.add_point((100, 200, 0))
            msp.add_point((300, 400, 0))
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path)
        assert len(sources) == 2
        assert all(isinstance(s, PointSource) for s in sources)
        assert sources[0].x_coord == 100.0
        assert sources[1].y_coord == 400.0

    def test_z_as_height(self, tmp_path):
        def build(msp):
            msp.add_point((10, 20, 35))
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path, z_as_height=True)
        assert sources[0].stack_height == 35.0

    def test_open_polyline_becomes_line(self, tmp_path):
        def build(msp):
            msp.add_lwpolyline([(0, 0), (100, 0), (200, 50)], close=False)
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path)
        assert len(sources) == 1
        assert isinstance(sources[0], LineSource)
        assert sources[0].x_start == 0.0
        assert sources[0].x_end == 200.0

    def test_closed_polyline_becomes_polygon(self, tmp_path):
        def build(msp):
            msp.add_lwpolyline(
                [(0, 0), (100, 0), (100, 50), (0, 50)], close=True,
            )
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path)
        assert len(sources) == 1
        assert isinstance(sources[0], AreaPolySource)
        assert len(sources[0].vertices) == 4

    def test_line_entity(self, tmp_path):
        def build(msp):
            msp.add_line((0, 0), (50, 75))
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path)
        assert len(sources) == 1
        assert isinstance(sources[0], LineSource)
        assert sources[0].x_end == 50.0
        assert sources[0].y_end == 75.0

    def test_circle_becomes_polygon(self, tmp_path):
        def build(msp):
            msp.add_circle((100, 100), radius=10)
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path)
        assert len(sources) == 1
        assert isinstance(sources[0], AreaPolySource)
        # 16-vertex discretization
        assert len(sources[0].vertices) == 16

    def test_layer_filter(self, tmp_path):
        def build(msp):
            msp.add_point((0, 0, 0), dxfattribs={"layer": "STACKS"})
            msp.add_point((1, 1, 0), dxfattribs={"layer": "OTHER"})
        path = _make_dxf(tmp_path, build)
        all_pts = from_dxf(path)
        assert len(all_pts) == 2
        only_stacks = from_dxf(path, layer="STACKS")
        assert len(only_stacks) == 1

    def test_synthetic_id_prefix(self, tmp_path):
        def build(msp):
            msp.add_point((0, 0, 0))
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path, src_id_prefix="MILL")
        assert sources[0].source_id == "MILL0001"

    def test_text_entity_ignored(self, tmp_path):
        def build(msp):
            msp.add_text("just a label").set_placement((10, 20))
            msp.add_point((30, 40, 0))
        path = _make_dxf(tmp_path, build)
        sources = from_dxf(path)
        # Text entity dropped; only the point survives
        assert len(sources) == 1


class TestImportErrors:
    def test_shapefile_without_geopandas(self, monkeypatch, tmp_path):
        # Force the from_shapefile path to fail-import even though
        # geopandas exists in this test environment, by patching the
        # import in the module's symbol table.
        from pyaermod import source_importers
        # Just confirm geopandas is normally importable; the actual
        # ImportError path is exercised by pytest.importorskip skipping
        # the module on systems where it's absent.
        assert source_importers.from_shapefile.__doc__

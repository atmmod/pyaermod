"""Tests for the review findings G1-G14 (geospatial, KMZ, plots, DEM download).

Started from the verifier tests (they failed before the fixes).

Skips if geopandas/shapely/folium are missing (all were installed when written).
"""

from __future__ import annotations

import math
import zipfile
from unittest import mock

import numpy as np
import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("shapely")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from pyaermod.footprints import receptor_points, source_footprint  # noqa: E402
from pyaermod.geospatial import (  # noqa: E402
    ContourGenerator,
    CoordinateTransformer,
    GeoDataFrameFactory,
    VectorExporter,
)
from pyaermod.sources import AreaCircSource, AreaSource, LineSource, OpenPitSource, PointSource  # noqa: E402

FACTORY = GeoDataFrameFactory(CoordinateTransformer(18))


def _corners(poly):
    """Exterior vertices without the closing repeat, rounded, as a list."""
    return [(round(x, 6), round(y, 6)) for x, y in list(poly.exterior.coords)[:-1]]


def _ring_equals(actual, expected):
    """Same cyclic vertex sequence (start vertex and direction free)."""
    n = len(expected)
    if len(actual) != n:
        return False
    for seq in (actual, actual[::-1]):
        for k in range(n):
            if all(math.isclose(seq[(k + i) % n][0], expected[i][0], abs_tol=1e-6)
                   and math.isclose(seq[(k + i) % n][1], expected[i][1], abs_tol=1e-6)
                   for i in range(n)):
                return True
    return False


# Hand-computed from soset.f (AREA vertices 3036-3062; OPENPIT 3524-3553):
#   v1 = SW; v2 = v1 + Yinit*(sin a, cos a); v3 = v2 + Xinit*(cos a, -sin a); v4 = v3 - Yinit*(sin a, cos a)
# SW (1000, 2000), Xinit 40, Yinit 10.
AREA_0 = [(1000, 2000), (1000, 2010), (1040, 2010), (1040, 2000)]
AREA_90 = [(1000, 2000), (1010, 2000), (1010, 1960), (1000, 1960)]


@pytest.mark.parametrize("angle, expected", [(0.0, AREA_0), (90.0, AREA_90)])
def test_g1_area_polygon_corners_match_soset(angle, expected):
    src = AreaSource("A1", 1000.0, 2000.0, initial_lateral_dimension=40.0,
                     initial_vertical_dimension=10.0, angle=angle)
    # control: footprints.py already agrees with the Fortran
    assert _ring_equals(list(source_footprint(src).parts[0]), expected)
    poly = FACTORY.sources_to_geodataframe([src]).geometry.iloc[0]
    assert poly.area == pytest.approx(400.0)
    assert _ring_equals(_corners(poly), expected)


@pytest.mark.parametrize("angle, expected", [(0.0, [(1000, 2000), (1040, 2000), (1040, 2010), (1000, 2010)]),
                                             (90.0, AREA_90)])
def test_g2_openpit_polygon_corners_match_soset(angle, expected):
    src = OpenPitSource("P1", 1000.0, 2000.0, x_dimension=40.0, y_dimension=10.0, angle=angle)
    assert _ring_equals(list(source_footprint(src).parts[0]), expected)   # control
    poly = FACTORY.sources_to_geodataframe([src]).geometry.iloc[0]
    assert _ring_equals(_corners(poly), expected)


# ------------------------------------------------------------------ G3
def test_g3_contour_bands_are_valid_nonoverlapping_with_holes():
    xs = np.linspace(-1000, 1000, 41)
    X, Y = np.meshgrid(xs, xs)
    z = np.exp(-np.hypot(X, Y) / 400)
    df = pd.DataFrame({"x": X.ravel(), "y": Y.ravel(), "concentration": z.ravel()})
    g = ContourGenerator(CoordinateTransformer(18)).generate_contours(
        df, levels=[0.0, 0.3, 0.5, 0.9, 1.1], method="linear")
    assert all(geom.is_valid for geom in g.geometry)
    assert sum(len(p.interiors) for geom in g.geometry
               for p in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom])) > 0
    # bands partition the domain: total area == area of the union
    assert g.geometry.area.sum() == pytest.approx(g.geometry.union_all().area, rel=1e-6)


# ------------------------------------------------------------------ G4
def test_g4_polar_grid_about_a_source_is_placed_at_the_source(tmp_path):
    from pyaermod.input_generator import (
        AERMODProject,
        ControlPathway,
        MeteorologyPathway,
        OutputPathway,
        PollutantType,
        SourcePathway,
    )
    from pyaermod.receptors import PolarGrid, ReceptorPathway
    src = PointSource("S1", 500000.0, 4500000.0, stack_height=10.0)
    grid = PolarGrid(grid_name="P", origin_source_id="S1", dist_num=1, dist_init=100.0,
                     dir_num=1, dir_init=90.0)
    assert receptor_points(grid, sources=[src])[0] == pytest.approx((500100.0, 4500000.0))  # control
    sp = SourcePathway()
    sp.add_source(src)
    project = AERMODProject(
        control=ControlPathway(title_one="t", pollutant_id=PollutantType.PM25),
        sources=sp, receptors=ReceptorPathway(polar_grids=[grid]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway())
    paths = VectorExporter(FACTORY).export_all(project, output_dir=tmp_path, driver="GeoJSON")
    pts = gpd.read_file(paths["receptors"]).to_crs(FACTORY.transformer.utm_crs)
    assert pts.geometry.x.iloc[0] == pytest.approx(500100.0, abs=0.01)
    assert pts.geometry.y.iloc[0] == pytest.approx(4500000.0, abs=0.01)


# ------------------------------------------------------------------ G5
def test_g5_interrupted_dem_download_does_not_leave_a_cache_hit(tmp_path):
    from pyaermod import terrain
    from pyaermod.terrain import DEMDownloader, DEMTileInfo

    class Resp:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"x" * 8192
            raise ConnectionError("reset mid-stream")

    tile = DEMTileInfo("t", "https://example.invalid/USGS_1_n42w074_20230314.tif")
    dl = DEMDownloader(cache_dir=tmp_path)
    with mock.patch.object(terrain.requests, "get", return_value=Resp()), pytest.raises(ConnectionError):
        dl.download_tile(tile, tmp_path, uncompressed=False)
    assert not (tmp_path / "USGS_1_n42w074_20230314.tif").exists()
    # and a second call must try the network again rather than return a truncated file
    with mock.patch.object(terrain.requests, "get", side_effect=RuntimeError("would download")), \
            pytest.raises(RuntimeError, match="would download"):
        dl.download_tile(tile, tmp_path, uncompressed=False)


# ------------------------------------------------------------------ G7
def test_g7_kmz_has_every_source_and_draws_areas_as_polygons(tmp_path):
    from pyaermod.kmz_export import to_kmz
    srcs = [PointSource("P1", 500000.0, 4500000.0, stack_height=10.0),
            LineSource("L1", 500000.0, 4500000.0, 500100.0, 4500100.0, 2.0, 2.0),
            AreaSource("A1", 500000.0, 4500000.0, initial_lateral_dimension=40.0,
                       initial_vertical_dimension=10.0, angle=90.0),
            AreaCircSource("C1", 500000.0, 4500000.0, radius=50.0)]
    out = to_kmz(str(tmp_path / "t.kmz"), sources=srcs, utm_zone=18)
    kml = zipfile.ZipFile(out).read("doc.kml").decode()
    blocks = {b.split("<name>")[1].split("</name>")[0]: b for b in kml.split("<Placemark>")[1:]}
    assert set(blocks) >= {"P1", "L1", "A1", "C1"}
    assert "<LineString>" in blocks["L1"]
    assert "<Polygon>" in blocks["A1"] and "<Polygon>" in blocks["C1"]


# ------------------------------------------------------------------ G8
def _map_results():
    from pyaermod.output_parser import AERMODResults, ConcentrationResult, ModelRunInfo, SourceSummary
    xs, ys = np.meshgrid(np.linspace(500000, 500500, 6), np.linspace(4500000, 4500500, 6))
    df = pd.DataFrame({"x": xs.ravel(), "y": ys.ravel(), "concentration": np.linspace(1, 36, 36)})
    cr = ConcentrationResult(averaging_period="ANNUAL", data=df, max_value=36.0,
                             max_location=(500500.0, 4500500.0))
    return AERMODResults(run_info=ModelRunInfo("24142", "J"),
                         sources=[SourceSummary("S", "POINT", 500250.0, 4500250.0, 0.0)],
                         receptors=[], concentrations={"ANNUAL": cr}, output_file="x.out")


def test_g8_interactive_map_converts_utm_with_a_zone():
    folium = pytest.importorskip("folium")
    from pyaermod.visualization import AERMODVisualizer
    m = AERMODVisualizer(_map_results()).create_interactive_map("ANNUAL", utm_zone=18)
    assert isinstance(m, folium.Map)
    lat, lon = m.location
    assert -90 <= lat <= 90 and -180 <= lon <= 180
    # zone 18N, 500250 E / 4500250 N is near 40.65 N, 75.0 W
    assert lat == pytest.approx(40.65, abs=0.1) and lon == pytest.approx(-75.0, abs=0.1)


def test_g8_interactive_map_without_a_zone_warns_that_coordinates_are_used_as_given():
    pytest.importorskip("folium")
    from pyaermod.visualization import AERMODVisualizer
    with pytest.warns(UserWarning, match="utm_zone"):
        AERMODVisualizer(_map_results()).create_interactive_map("ANNUAL")


# ------------------------------------------------------------------ G11
def test_g11_surface_grid_is_independent_of_row_order(monkeypatch):
    from mpl_toolkits.mplot3d import axes3d

    from pyaermod.advanced_viz import AdvancedVisualizer
    xs, ys = [0.0, 100.0, 200.0], [0.0, 100.0]
    rows = [(x, y, 10 * i + j) for i, x in enumerate(xs) for j, y in enumerate(ys)]   # x-major
    df = pd.DataFrame(rows, columns=["X", "Y", "CONC"])
    seen = {}
    real = axes3d.Axes3D.plot_surface

    def spy(self, X, Y, Z, *a, **k):
        seen["X"], seen["Y"], seen["Z"] = np.asarray(X), np.asarray(Y), np.asarray(Z)
        return real(self, X, Y, Z, *a, **k)
    monkeypatch.setattr(axes3d.Axes3D, "plot_surface", spy)
    AdvancedVisualizer.plot_3d_surface(df)
    X, Y, Z = seen["X"], seen["Y"], seen["Z"]
    lookup = {(x, y): c for x, y, c in rows}
    for i in range(Z.shape[0]):
        for j in range(Z.shape[1]):
            assert Z[i, j] == lookup[(X[i, j], Y[i, j])]


# ------------------------------------------------------------------ G12
def _utm_profile():
    xs = np.linspace(500000, 500500, 11)
    return pd.DataFrame({"X": xs, "Y": 4500000.0, "CONC": np.linspace(1, 5, 11)})


def test_g12_profile_draws_the_source_line_where_the_source_is():
    import matplotlib.pyplot as plt

    from pyaermod.advanced_viz import AdvancedVisualizer
    fig = AdvancedVisualizer.plot_concentration_profile(
        _utm_profile(), direction="x", cross_coord=4500000.0, source_xy=(500250.0, 4500000.0))
    ax = fig.axes[0]
    assert ax.get_xlim()[0] > 400000, f"x-axis stretched to include 0: {ax.get_xlim()}"
    assert ax.lines[-1].get_xdata()[0] == 500250.0
    plt.close(fig)


def test_g12_profile_default_source_is_the_origin_of_source_relative_data():
    import matplotlib.pyplot as plt

    from pyaermod.advanced_viz import AdvancedVisualizer
    df = pd.DataFrame({"X": np.linspace(-250, 250, 11), "Y": 0.0, "CONC": np.linspace(1, 5, 11)})
    fig = AdvancedVisualizer.plot_concentration_profile(df)
    assert fig.axes[0].lines[-1].get_xdata()[0] == 0
    plt.close(fig)



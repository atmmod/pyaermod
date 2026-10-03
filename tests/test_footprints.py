"""pyaermod.footprints: source outlines and receptor locations in model coordinates.

The expected geometry is AERMOD v26135's own: ``soset.f`` ARVERT for AREA
and OPENPIT rectangles, GENCIR for AREACIRC, and ``reset.f`` SETPOL for
polar receptors (see the module docstring).
"""

from __future__ import annotations

import math

import pytest

from pyaermod.footprints import LINES, POINT, POLYGON, receptor_points, source_footprint
from pyaermod.input_generator import (
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    DiscreteReceptor,
    LineSource,
    OpenPitSource,
    PointCapSource,
    PointSource,
    PolarGrid,
    RLineExtSource,
    RLineSource,
    SidewashPointSource,
    VolumeSource,
)


def _close(points, expected, tol=1e-9):
    assert len(points) == len(expected)
    for (x, y), (ex, ey) in zip(points, expected, strict=True):
        assert abs(x - ex) <= tol and abs(y - ey) <= tol, (points, expected)


class TestPointLikeSources:
    @pytest.mark.parametrize("src", [
        PointSource("S1", 10.0, 20.0),
        PointCapSource("S1", 10.0, 20.0),
        VolumeSource("S1", 10.0, 20.0),
        SidewashPointSource("S1", 10.0, 20.0),
    ])
    def test_location_is_the_footprint(self, src):
        fp = source_footprint(src)
        assert fp.kind == POINT
        assert fp.points() == [(10.0, 20.0)]
        assert fp.anchor() == (10.0, 20.0)
        assert fp.source_id == "S1"


class TestRectangles:
    def test_unrotated_area_starts_at_the_south_west_corner(self):
        # Xinit is the east-west side and Yinit the north-south side.
        fp = source_footprint(AreaSource("A1", 100.0, 200.0, initial_lateral_dimension=30.0,
                                         initial_vertical_dimension=10.0))
        assert fp.kind == POLYGON
        _close(fp.points(), [(100, 200), (100, 210), (130, 210), (130, 200)])

    def test_rotation_is_clockwise_about_the_corner(self):
        fp = source_footprint(AreaSource("A1", 0.0, 0.0, initial_lateral_dimension=20.0,
                                         initial_vertical_dimension=10.0, angle=90.0))
        # 90 degrees clockwise: the Y side points east, the X side south.
        _close(fp.points(), [(0, 0), (10, 0), (10, -20), (0, -20)])

    def test_open_pit_uses_its_dimensions(self):
        fp = source_footprint(OpenPitSource("P1", 5.0, 5.0, x_dimension=40.0, y_dimension=20.0,
                                            angle=30.0))
        s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
        p2 = (5 + 20 * s, 5 + 20 * c)
        p3 = (p2[0] + 40 * c, p2[1] - 40 * s)
        _close(fp.points(), [(5, 5), p2, p3, (p3[0] - 20 * s, p3[1] - 20 * c)])


class TestCircle:
    def test_equal_area_polygon_first_vertex_north(self):
        fp = source_footprint(AreaCircSource("C1", 0.0, 0.0, radius=100.0, num_vertices=20))
        pts = fp.points()
        assert fp.kind == POLYGON and len(pts) == 20
        assert abs(pts[0][0]) < 1e-9 and pts[0][1] > 100.0     # slightly outside the circle
        # Shoelace area equals the circle's area (GENCIR's construction).
        area = 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
                             in zip(pts, pts[1:] + pts[:1], strict=True)))
        assert area == pytest.approx(math.pi * 100.0 ** 2, rel=1e-9)


class TestPolygonsAndLines:
    def test_area_poly_keeps_its_vertices(self):
        verts = [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0)]
        fp = source_footprint(AreaPolySource("P1", vertices=verts))
        assert fp.kind == POLYGON and fp.points() == verts

    def test_area_poly_without_vertices_is_refused(self):
        src = AreaPolySource("P1", vertices=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
        src.vertices = []
        with pytest.raises(ValueError, match="P1"):
            source_footprint(src)

    @pytest.mark.parametrize("cls", [LineSource, RLineSource])
    def test_lines(self, cls):
        fp = source_footprint(cls("L1", 0.0, 1.0, 100.0, 2.0))
        assert fp.kind == LINES and fp.parts == (((0.0, 1.0), (100.0, 2.0)),)

    def test_rline_ext(self):
        fp = source_footprint(RLineExtSource("R1", 0.0, 1.0, 0.5, 50.0, 2.0, 0.5))
        assert fp.kind == LINES and fp.parts == (((0.0, 1.0), (50.0, 2.0)),)

    def test_buoyant_line_segments(self):
        segs = [BuoyLineSegment("B1", 0.0, 0.0, 10.0, 0.0),
                BuoyLineSegment("B2", 0.0, 5.0, 10.0, 5.0)]
        src = BuoyLineSource("BL", 10, 5, 10, 2, 3, 5, line_segments=segs)
        fp = source_footprint(src)
        assert fp.kind == LINES and len(fp.parts) == 2 and fp.anchor() == (0.0, 0.0)

    def test_not_a_source(self):
        with pytest.raises(TypeError):
            source_footprint(object())


class TestReceptorPoints:
    def test_cartesian_grid_expands_every_node(self):
        pts = receptor_points(CartesianGrid(x_init=-100, x_num=3, x_delta=100,
                                            y_init=0, y_num=2, y_delta=50))
        assert sorted(pts) == sorted([(x, y) for x in (-100, 0, 100) for y in (0, 50)])

    def test_cartesian_explicit_points(self):
        grid = CartesianGrid(x_points=[1.0, 2.0], y_points=[3.0])
        assert sorted(receptor_points(grid)) == [(1.0, 3.0), (2.0, 3.0)]

    def test_polar_grid_directions_clockwise_from_north(self):
        grid = PolarGrid(x_origin=10.0, y_origin=20.0, dist_init=100.0, dist_num=1,
                         dir_init=0.0, dir_num=4, dir_delta=90.0)
        _close(receptor_points(grid), [(10, 120), (110, 20), (10, -80), (-90, 20)])

    def test_reference_grid_size(self):
        assert len(receptor_points(PolarGrid())) == PolarGrid().receptor_count == 360

    def test_polar_grid_on_a_source(self):
        grid = PolarGrid(dist_init=10.0, dist_num=1, dir_num=1, origin_source_id="S1")
        pts = receptor_points(grid, sources=[PointSource("S1", 500.0, 600.0)])
        _close(pts, [(500.0, 610.0)])
        # Without the source the numeric origin stands.
        _close(receptor_points(grid), [(0.0, 10.0)])

    def test_discrete(self):
        assert receptor_points(DiscreteReceptor(3.0, 4.0)) == [(3.0, 4.0)]

    def test_not_a_receptor(self):
        with pytest.raises(TypeError):
            receptor_points(PointSource("S1", 0.0, 0.0))

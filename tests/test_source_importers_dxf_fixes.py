"""H-4: z_as_height for every entity, circle area, and the polyline chord warning (DXF)."""

import math
import warnings

import pytest

ezdxf = pytest.importorskip("ezdxf")

from pyaermod.source_importers import from_dxf  # noqa: E402


def _dxf(tmp_path, build):
    doc = ezdxf.new("R2010")
    build(doc.modelspace())
    out = tmp_path / "t.dxf"
    doc.saveas(out)
    return out


def _area(vertices):
    n = len(vertices)
    return abs(sum(vertices[i][0] * vertices[(i + 1) % n][1] - vertices[(i + 1) % n][0] * vertices[i][1]
                   for i in range(n))) / 2


def test_z_as_height_applies_to_polylines_lines_and_circles(tmp_path):
    def build(msp):
        msp.add_lwpolyline([(0, 0), (10, 0)], close=False, dxfattribs={"elevation": 12})
        msp.add_line((0, 0, 7), (5, 5, 7))
        msp.add_circle((0, 0, 9), radius=5)
    line_poly, line, circle = from_dxf(_dxf(tmp_path, build), z_as_height=True)
    assert line_poly.release_height == 12.0
    assert line.release_height == 7.0
    assert circle.release_height == 9.0


def test_a_circle_keeps_its_area(tmp_path):
    (src,) = from_dxf(_dxf(tmp_path, lambda msp: msp.add_circle((0, 0), radius=10)))
    assert _area(src.vertices) == pytest.approx(math.pi * 100, rel=1e-6)


def test_a_multi_vertex_polyline_warns_that_it_is_a_chord(tmp_path):
    def build(msp):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)], close=False)
    with pytest.warns(UserWarning, match="straight segment"):
        from_dxf(_dxf(tmp_path, build))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        from_dxf(_dxf(tmp_path, lambda msp: msp.add_lwpolyline([(0, 0), (10, 0)], close=False)))

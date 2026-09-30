"""The plan view's SVG, built from the project with no UI (tier T0)."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

from pyaermod.gui_v2.plan_view import MAX_POINTS, PLAN_VIEW_NAME, nice_step, plan_view_svg
from pyaermod.gui_v2.state import _empty_project
from pyaermod.input_generator import (
    AreaSource,
    CartesianGrid,
    DiscreteReceptor,
    LineSource,
    PointSource,
    PolarGrid,
)

SVG = "{http://www.w3.org/2000/svg}"


def _project():
    project = _empty_project()
    project.sources.sources += [
        PointSource("STACK1", 0.0, 0.0),
        AreaSource("AREA1", 200.0, 100.0, initial_lateral_dimension=100.0,
                   initial_vertical_dimension=50.0, angle=30.0),
        LineSource("ROAD", -800.0, -600.0, 600.0, -700.0),
    ]
    project.receptors.polar_grids.append(PolarGrid(grid_name="GRID1"))
    project.receptors.cartesian_grids.append(CartesianGrid(grid_name="CART1", x_num=3, y_num=3))
    project.receptors.discrete_receptors.append(DiscreteReceptor(250.0, 250.0))
    return project


def test_it_is_a_named_image_that_names_every_item():
    svg = plan_view_svg(_project())
    root = ET.fromstring(svg)                       # well-formed
    assert root.get("role") == "img" and root.get("aria-label") == PLAN_VIEW_NAME
    text = "".join(root.itertext())
    for name in ("STACK1", "AREA1", "ROAD", "GRID1", "CART1"):
        assert name in text
    assert "3 sources and 370 receptors" in text     # 360 + 9 + 1
    assert "Polar grid GRID1: 360 receptors" in text
    kinds = [el.tag.removeprefix(SVG) for el in root.iter()]
    assert "circle" in kinds and "polygon" in kinds and "polyline" in kinds


def test_an_empty_project_says_so():
    root = ET.fromstring(plan_view_svg(_empty_project()))
    assert "Nothing to show yet" in "".join(root.itertext())


def test_names_are_escaped():
    project = _empty_project()
    project.sources.sources.append(PointSource("A<&>", 0.0, 0.0))
    svg = plan_view_svg(project)
    assert "A&lt;&amp;&gt;" in svg
    assert "A<&>" in "".join(ET.fromstring(svg).itertext())


def test_one_scale_on_both_axes():
    project = _empty_project()
    project.sources.sources += [PointSource("W", 0.0, 0.0), PointSource("E", 1000.0, 0.0),
                                PointSource("N", 0.0, 500.0)]
    root = ET.fromstring(plan_view_svg(project))
    pts = [(float(c.get("cx")), float(c.get("cy")))
           for g in root.iter(f"{SVG}g") if g.get("class") == "source"
           for c in g.iter(f"{SVG}circle")]
    (wx, wy), (ex, ey), (nx, ny) = pts
    assert abs((ex - wx) / 1000.0 - (wy - ny) / 500.0) < 0.01    # px per metre, both ways
    assert ny < wy                                                   # north is up
    assert ey == wy and nx == wx                                     # axes are not skewed


def test_ticks_are_round():
    assert nice_step(1000) == 200 and nice_step(90) == 20 and nice_step(7) == 2 and nice_step(6) == 1


def test_ten_thousand_receptors_are_quick_and_bounded():
    project = _empty_project()
    project.receptors.discrete_receptors = [DiscreteReceptor(float(i % 100), float(i // 100))
                                            for i in range(10_000)]
    start = time.perf_counter()
    svg = plan_view_svg(project)
    assert time.perf_counter() - start < 1.0
    assert "10000 discrete receptors" in svg
    assert len(re.findall(r"M[-\d.]+ [-\d.]+h0", svg)) == 10_000 <= MAX_POINTS

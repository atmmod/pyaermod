"""G2: a huge receptor grid must not make the plan view expand every point."""

import time

import pytest

from pyaermod.gui_v2.plan_view import MAX_POINTS, plan_view_svg
from pyaermod.gui_v2.session import Session
from pyaermod.input_generator import CartesianGrid, PolarGrid


def _project():
    return Session().project


def test_a_four_million_point_cartesian_grid_is_drawn_quickly():
    project = _project()
    project.receptors.cartesian_grids.append(
        CartesianGrid(grid_name="BIG", x_init=-10000, x_num=2000, x_delta=10,
                      y_init=-10000, y_num=2000, y_delta=10))
    start = time.perf_counter()
    svg = plan_view_svg(project)
    elapsed = time.perf_counter() - start
    assert svg.startswith("<svg")
    assert "4000000 receptors" in svg or "4,000,000 receptors" in svg   # the true count is still stated
    assert elapsed < 0.5, f"plan view took {elapsed:.1f} s for 4e6 receptors"


def test_a_large_polar_grid_is_drawn_quickly():
    project = _project()
    project.receptors.polar_grids.append(
        PolarGrid(grid_name="POL", x_origin=0, y_origin=0, dist_init=10, dist_num=2000,
                  dist_delta=5, dir_init=0, dir_num=2000, dir_delta=0.18))
    start = time.perf_counter()
    svg = plan_view_svg(project)
    assert svg.startswith("<svg")
    assert time.perf_counter() - start < 0.5

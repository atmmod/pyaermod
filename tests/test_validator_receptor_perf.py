"""Regression tests for validator_advanced receptor-checking performance.

Before the v1.5 fix, _receptor_bbox iterated every receptor coordinate
individually (materializing a list of x_num*y_num tuples in memory).
For a 500x500 Cartesian grid that's 250,000 tuples created purely to
compute the 4 bbox corners — absurd for a check designed to flag
large-grid projects.

_check_receptors also called _receptor_bbox BEFORE checking the hard
limit, so a 500x500 project (over the hard limit) paid the cost
regardless.

These tests verify the current implementation:
1. Short-circuits on hard-limit projects (no bbox materialization)
2. Computes the bbox analytically from grid definitions (fast even on
   huge grids)
"""

from __future__ import annotations

import time

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.validator_advanced import (
    RECEPTOR_GRID_HARD_LIMIT,
    _check_receptors,
    _count_receptors,
    _receptor_bbox,
)


def _project_with_receptors(receptors: ReceptorPathway) -> AERMODProject:
    return AERMODProject(
        control=ControlPathway(
            title_one="perf", pollutant_id=PollutantType.SO2,
            averaging_periods=["ANNUAL"],
        ),
        sources=SourcePathway(sources=[PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=30.0, stack_temp=400.0,
            exit_velocity=10.0, stack_diameter=2.0,
            emission_rate=1.0,
        )]),
        receptors=receptors,
        meteorology=MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
        ),
        output=OutputPathway(),
    )


# ---------------------------------------------------------------------------
# Fast bbox
# ---------------------------------------------------------------------------

class TestBBoxPerformance:
    def test_bbox_cheap_for_large_grid(self):
        """500x500 grid = 250,000 receptors. Bbox must compute in
        well under a second. Old implementation would materialize 250k
        (x,y) tuples."""
        grid = CartesianGrid(
            grid_name="BIG",
            x_init=0, x_num=500, x_delta=100,
            y_init=0, y_num=500, y_delta=100,
        )
        recs = ReceptorPathway(cartesian_grids=[grid])

        t0 = time.perf_counter()
        bbox = _receptor_bbox(recs)
        elapsed = time.perf_counter() - t0

        assert bbox is not None
        # x_init=0, x_end = 499*100 = 49_900; same for y
        assert bbox == (0.0, 0.0, 49_900.0, 49_900.0)
        # Must be fast — old implementation was O(250k), new is O(4).
        assert elapsed < 0.1, f"bbox took {elapsed:.3f}s; expected < 0.1"

    def test_bbox_covers_polar_grid(self):
        grid = PolarGrid(
            grid_name="P", x_origin=500.0, y_origin=1000.0,
            dist_init=100.0, dist_num=10, dist_delta=100.0,
        )
        recs = ReceptorPathway(polar_grids=[grid])
        bbox = _receptor_bbox(recs)
        # max radius = 100 + 9*100 = 1000
        assert bbox == (-500.0, 0.0, 1500.0, 2000.0)

    def test_bbox_none_for_empty_receptors(self):
        recs = ReceptorPathway()
        assert _receptor_bbox(recs) is None

    def test_bbox_includes_discrete_receptors(self):
        grid = CartesianGrid(
            grid_name="G", x_init=0, x_num=2, x_delta=100,
            y_init=0, y_num=2, y_delta=100,
        )
        recs = ReceptorPathway(
            cartesian_grids=[grid],
            discrete_receptors=[
                DiscreteReceptor(x_coord=-9999, y_coord=-9999),
                DiscreteReceptor(x_coord=9999, y_coord=9999),
            ],
        )
        bbox = _receptor_bbox(recs)
        assert bbox == (-9999.0, -9999.0, 9999.0, 9999.0)


# ---------------------------------------------------------------------------
# Early return on hard-limit
# ---------------------------------------------------------------------------

class TestHardLimitEarlyReturn:
    def test_over_hard_limit_returns_immediately(self):
        """A project with more receptors than AERMOD's hard limit must
        produce an error and NOT compute the bbox or source comparison."""
        # RECEPTOR_GRID_HARD_LIMIT is 100_000 by default; 400x400=160k
        grid = CartesianGrid(
            grid_name="HUGE", x_init=0, x_num=400, x_delta=100,
            y_init=0, y_num=400, y_delta=100,
        )
        recs = ReceptorPathway(cartesian_grids=[grid])
        n = _count_receptors(recs)
        assert n > RECEPTOR_GRID_HARD_LIMIT

        sources = SourcePathway(sources=[PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=30.0, stack_temp=400.0,
            exit_velocity=10.0, stack_diameter=2.0,
            emission_rate=1.0,
        )])

        t0 = time.perf_counter()
        errors = _check_receptors(recs, sources)
        elapsed = time.perf_counter() - t0

        # Exactly one error — the hard-limit one — and nothing else
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "hard limit" in errors[0].message
        # Early return: must be fast
        assert elapsed < 0.1, f"check took {elapsed:.3f}s after early-return fix"

    def test_under_warn_limit_no_flags(self):
        """Small project flows through without flags."""
        grid = CartesianGrid(
            grid_name="G", x_init=0, x_num=10, x_delta=100,
            y_init=0, y_num=10, y_delta=100,
        )
        recs = ReceptorPathway(cartesian_grids=[grid])
        sources = SourcePathway(sources=[PointSource(
            source_id="S1", x_coord=500, y_coord=500,
            stack_height=30.0, stack_temp=400.0,
            exit_velocity=10.0, stack_diameter=2.0,
            emission_rate=1.0,
        )])
        errors = _check_receptors(recs, sources)
        assert errors == []

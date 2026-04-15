"""Tests for PRIME downwash helpers."""

from __future__ import annotations

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.bpip import Building
from pyaermod.prime import (
    GEP_FLOOR_M,
    apply_bpip_to_project,
    assess_source_downwash,
    cavity_length,
    gep_from_building,
    gep_stack_height,
    in_cavity_region,
    suggest_downwash_config,
)


def _square_building(bid="B1", half_side=10.0, height=20.0):
    """Return a square building centered on origin with given height."""
    return Building(
        building_id=bid,
        corners=[
            (-half_side, -half_side),
            (half_side, -half_side),
            (half_side, half_side),
            (-half_side, half_side),
        ],
        height=height,
    )


# ---------------------------------------------------------------------------
# GEP
# ---------------------------------------------------------------------------

class TestGEPStackHeight:
    def test_floor_used_when_building_tiny(self):
        # 5 m building, 3 m lesser dim -> floor of 65 wins
        assert gep_stack_height(5.0, 3.0) == GEP_FLOOR_M

    def test_formula_used_when_building_large(self):
        # 50 m building, 40 m lesser dim -> 50 + 1.5*40 = 110
        assert gep_stack_height(50.0, 40.0) == pytest.approx(110.0)

    def test_rejects_negatives(self):
        with pytest.raises(ValueError):
            gep_stack_height(-1.0, 5.0)
        with pytest.raises(ValueError):
            gep_stack_height(5.0, -1.0)

    def test_gep_from_building_tiny(self):
        b = _square_building(height=5.0, half_side=5.0)
        gep = gep_from_building(b, stack_x=0.0, stack_y=0.0)
        assert gep == GEP_FLOOR_M

    def test_gep_from_building_large(self):
        b = _square_building(height=40.0, half_side=30.0)
        gep = gep_from_building(b, stack_x=0.0, stack_y=0.0)
        assert gep > GEP_FLOOR_M


# ---------------------------------------------------------------------------
# Cavity
# ---------------------------------------------------------------------------

class TestCavity:
    def test_zero_size_returns_zero(self):
        assert cavity_length(0, 10) == 0.0
        assert cavity_length(10, 0) == 0.0

    def test_cavity_scales_with_height(self):
        # Same W/H ratio, bigger H -> bigger Lc
        l1 = cavity_length(10, 20)
        l2 = cavity_length(20, 40)
        assert l2 > l1

    def test_in_cavity_when_downwind_short(self):
        b = _square_building(height=30.0, half_side=15.0)
        # Stack at (10, 0) with wind from west (270°); stack is downwind of bldg center
        assert in_cavity_region(
            stack_x=20.0, stack_y=0.0, stack_height=5.0,
            building=b, wind_direction_deg=270.0,
        )

    def test_not_in_cavity_when_upwind(self):
        b = _square_building(height=30.0, half_side=15.0)
        # Wind from east (90°), stack to east of building — stack is upwind
        assert not in_cavity_region(
            stack_x=20.0, stack_y=0.0, stack_height=5.0,
            building=b, wind_direction_deg=90.0,
        )

    def test_not_in_cavity_when_stack_above_building(self):
        b = _square_building(height=20.0, half_side=15.0)
        assert not in_cavity_region(
            stack_x=10.0, stack_y=0.0, stack_height=50.0,
            building=b, wind_direction_deg=270.0,
        )


# ---------------------------------------------------------------------------
# Source assessment
# ---------------------------------------------------------------------------

def _point_source(sid="S1", sh=30.0, x=0.0, y=0.0, **kw):
    base = dict(
        source_id=sid, x_coord=x, y_coord=y, stack_height=sh,
        stack_temp=450.0, exit_velocity=10.0, stack_diameter=2.0,
        emission_rate=1.0,
    )
    base.update(kw)
    return PointSource(**base)


class TestAssessDownwash:
    def test_no_buildings_defaults_to_floor(self):
        src = _point_source(sh=100.0)
        a = assess_source_downwash(src, buildings=[])
        assert a.gep_height_m == GEP_FLOOR_M
        assert a.is_below_gep is False
        assert a.affected_by_building is None

    def test_short_stack_near_building_is_below_gep(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=10.0, x=5.0, y=0.0)
        a = assess_source_downwash(src, [b])
        assert a.is_below_gep is True
        assert a.affected_by_building == b.building_id

    def test_tall_stack_near_building_not_below_gep(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=200.0, x=5.0, y=0.0)
        a = assess_source_downwash(src, [b])
        assert a.is_below_gep is False

    def test_far_away_stack_ignores_building(self):
        b = _square_building(height=10.0, half_side=5.0)
        src = _point_source(sh=50.0, x=10_000.0, y=0.0)
        a = assess_source_downwash(src, [b])
        assert a.affected_by_building is None


# ---------------------------------------------------------------------------
# Project-level apply
# ---------------------------------------------------------------------------

def _tiny_project(sources):
    g = CartesianGrid(grid_name="G", x_init=0, x_num=5, x_delta=100,
                      y_init=0, y_num=5, y_delta=100)
    return AERMODProject(
        control=ControlPathway(
            title_one="t", pollutant_id=PollutantType.SO2,
            averaging_periods=["ANNUAL"]),
        sources=SourcePathway(sources=sources),
        receptors=ReceptorPathway(cartesian_grids=[g]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


class TestApplyBPIP:
    def test_populates_36_sector_arrays(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=15.0, x=10.0, y=0.0)  # below GEP
        project = _tiny_project([src])
        assessments = apply_bpip_to_project(project, [b])
        assert len(assessments) == 1 and assessments[0].is_below_gep is True
        assert isinstance(src.building_height, list) and len(src.building_height) == 36

    def test_skips_sources_above_gep_by_default(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=200.0, x=10.0, y=0.0)  # above GEP
        project = _tiny_project([src])
        apply_bpip_to_project(project, [b])
        assert src.building_height is None or src.building_height == []

    def test_force_below_gep_only_false_assigns_anyway(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=200.0, x=10.0, y=0.0)
        project = _tiny_project([src])
        apply_bpip_to_project(project, [b], only_below_gep=False)
        assert isinstance(src.building_height, list) and len(src.building_height) == 36


class TestSuggestDownwashConfig:
    def test_below_gep_no_data_warns(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=10.0, x=5.0, y=0.0)
        project = _tiny_project([src])
        warns = suggest_downwash_config(project, [b])
        assert any("below GEP" in w for w in warns)

    def test_above_gep_with_data_warns(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=200.0, x=10.0, y=0.0)
        src.building_height = [10.0] * 36
        src.building_width = [20.0] * 36
        src.building_length = [20.0] * 36
        src.building_x_offset = [0.0] * 36
        src.building_y_offset = [0.0] * 36
        project = _tiny_project([src])
        warns = suggest_downwash_config(project, [b])
        assert any("at/above GEP" in w for w in warns)

    def test_wrong_length_array_warns(self):
        b = _square_building(height=40.0, half_side=25.0)
        src = _point_source(sh=10.0, x=5.0, y=0.0)
        src.building_height = [1.0] * 24  # wrong length
        project = _tiny_project([src])
        warns = suggest_downwash_config(project, [b])
        assert any("24 values" in w for w in warns)

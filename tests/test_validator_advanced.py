"""Tests for validator_advanced (cross-field AERMOD validation)."""

from __future__ import annotations

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.validator_advanced import (
    advanced_validate,
    _check_dfault_consistency,
    _check_met_dates,
    _check_point_source,
    _check_receptors,
    _count_receptors,
    _receptor_bbox,
)


def _good_control(**kw):
    base = dict(
        title_one="t",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["1", "ANNUAL"],
    )
    base.update(kw)
    return ControlPathway(**base)


def _good_point(**kw):
    base = dict(
        source_id="S1",
        x_coord=0.0, y_coord=0.0,
        stack_height=30.0,
        stack_temp=450.0,
        exit_velocity=10.0,
        stack_diameter=2.0,
        emission_rate=1.0,
    )
    base.update(kw)
    return PointSource(**base)


def _good_met(**kw):
    base = dict(surface_file="a.sfc", profile_file="a.pfl")
    base.update(kw)
    return MeteorologyPathway(**base)


# ---------------------------------------------------------------------------
# Point-source consistency
# ---------------------------------------------------------------------------

class TestPointSourceChecks:
    def test_tiny_diameter_warns(self):
        findings = _check_point_source(_good_point(stack_diameter=0.001))
        assert any("stack_diameter" in f.field for f in findings)

    def test_giant_diameter_warns(self):
        findings = _check_point_source(_good_point(stack_diameter=100.0))
        assert any("stack_diameter" in f.field for f in findings)

    def test_zero_velocity_hot_stack_warns(self):
        findings = _check_point_source(_good_point(exit_velocity=0.0, stack_temp=500.0))
        assert any("exit_velocity" in f.field for f in findings)

    def test_supersonic_velocity_warns(self):
        findings = _check_point_source(_good_point(exit_velocity=500.0))
        assert any("exit_velocity" in f.field for f in findings)

    def test_zero_emission_warns(self):
        findings = _check_point_source(_good_point(emission_rate=0.0))
        assert any("emission_rate" in f.field for f in findings)

    def test_ambient_neutral_warns(self):
        # stack_temp ~ ambient and Ve = 0 => no plume rise
        findings = _check_point_source(_good_point(stack_temp=293.15, exit_velocity=0.0))
        assert any("plume rise" in f.message for f in findings)

    def test_good_source_no_warnings(self):
        findings = _check_point_source(_good_point())
        assert findings == []


# ---------------------------------------------------------------------------
# Receptor checks
# ---------------------------------------------------------------------------

class TestReceptorChecks:
    def test_count_receptors_discrete(self):
        recs = ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(x_coord=1.0, y_coord=1.0)],
        )
        assert _count_receptors(recs) == 1

    def test_count_receptors_grid(self):
        g = CartesianGrid(
            grid_name="G1",
            x_init=-500, x_num=5, x_delta=100,
            y_init=-500, y_num=4, y_delta=100,
        )
        recs = ReceptorPathway(cartesian_grids=[g])
        assert _count_receptors(recs) == 20

    def test_bbox_computation(self):
        recs = ReceptorPathway(discrete_receptors=[
            DiscreteReceptor(x_coord=0.0, y_coord=0.0),
            DiscreteReceptor(x_coord=100.0, y_coord=200.0),
        ])
        assert _receptor_bbox(recs) == (0.0, 0.0, 100.0, 200.0)

    def test_huge_grid_warns(self):
        g = CartesianGrid(
            grid_name="BIG",
            x_init=0, x_num=200, x_delta=10,
            y_init=0, y_num=200, y_delta=10,
        )
        recs = ReceptorPathway(cartesian_grids=[g])
        src = SourcePathway(sources=[_good_point()])
        findings = _check_receptors(recs, src)
        assert any("10000" in f.message or "receptors" in f.field for f in findings)

    def test_source_way_outside_grid_warns(self):
        g = CartesianGrid(
            grid_name="G1",
            x_init=0, x_num=10, x_delta=10,
            y_init=0, y_num=10, y_delta=10,
        )
        recs = ReceptorPathway(cartesian_grids=[g])
        src = SourcePathway(sources=[_good_point(x_coord=200_000, y_coord=0)])
        findings = _check_receptors(recs, src)
        assert any("outside receptor grid" in f.message for f in findings)


# ---------------------------------------------------------------------------
# DFAULT consistency
# ---------------------------------------------------------------------------

class TestDFAULTConsistency:
    def test_clean_project_no_errors(self):
        control = _good_control(regulatory_default=True)
        findings = _check_dfault_consistency(control)
        assert findings == []

    def test_nondefault_flag_with_regulatory_default_errors(self):
        control = _good_control(regulatory_default=True)
        # Fake a non-default option
        control.flat_terrain = True
        findings = _check_dfault_consistency(control)
        assert len(findings) == 1
        assert "regulatory_default" in findings[0].field

    def test_nondefault_flag_without_regulatory_default_ok(self):
        control = _good_control(regulatory_default=False)
        control.flat_terrain = True
        findings = _check_dfault_consistency(control)
        assert findings == []


# ---------------------------------------------------------------------------
# Met date checks
# ---------------------------------------------------------------------------

class TestMetDates:
    def test_no_annual_skipped(self):
        control = _good_control(averaging_periods=["24"])
        met = _good_met()
        assert _check_met_dates(control, met) == []

    def test_partial_year_warns(self):
        control = _good_control(averaging_periods=["ANNUAL"])
        met = _good_met(
            start_year=2020, start_month=6, start_day=1,
            end_year=2020, end_month=8, end_day=31,
        )
        findings = _check_met_dates(control, met)
        assert any(f.severity == "warning" for f in findings)

    def test_single_day_errors(self):
        control = _good_control(averaging_periods=["ANNUAL"])
        met = _good_met(
            start_year=2020, start_month=3, start_day=15,
            end_year=2020, end_month=3, end_day=15,
        )
        findings = _check_met_dates(control, met)
        assert any(f.severity == "error" for f in findings)

    def test_full_year_clean(self):
        control = _good_control(averaging_periods=["ANNUAL"])
        met = _good_met(
            start_year=2020, start_month=1, start_day=1,
            end_year=2020, end_month=12, end_day=31,
        )
        assert _check_met_dates(control, met) == []

    def test_partial_dates_deferred_to_base(self):
        control = _good_control(averaging_periods=["ANNUAL"])
        met = _good_met(start_year=2020)  # incomplete
        # Should not produce findings here (base validator handles)
        assert _check_met_dates(control, met) == []


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

class TestAdvancedValidateEnd2End:
    def _project(self, **src_kw):
        g = CartesianGrid(
            grid_name="G1",
            x_init=-500, x_num=5, x_delta=100,
            y_init=-500, y_num=4, y_delta=100,
        )
        return AERMODProject(
            control=_good_control(),
            sources=SourcePathway(sources=[_good_point(**src_kw)]),
            receptors=ReceptorPathway(cartesian_grids=[g]),
            meteorology=_good_met(),
            output=OutputPathway(),
        )

    def test_clean_project(self):
        findings = advanced_validate(self._project())
        # May still find minor warnings; ensure no errors
        assert not any(f.severity == "error" for f in findings)

    def test_catches_bad_point_source(self):
        findings = advanced_validate(self._project(emission_rate=0.0))
        assert any("emission_rate" in f.field for f in findings)

"""Validator rules for the SO keywords of reader tranche 2.

Each rule mirrors a fatal error in soset.f and is pinned in both
directions: the offending configuration raises the error naming the
AERMOD code, and the corrected one does not.
"""

from __future__ import annotations

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    EmissionUnits,
    MeteorologyPathway,
    OutputPathway,
    OzoneData,
    ReceptorPathway,
    SolidBarrier,
    SolidBarrierSegment,
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
    VegetativeBarrier,
)
from pyaermod.sources import PointSource, RLineExtSource, VolumeSource
from pyaermod.validator import Validator


def _stack(sid="STK1", **kw):
    return PointSource(sid, 500.0, 500.0, stack_height=30.0, stack_diameter=1.5,
                       stack_temp=400.0, exit_velocity=10.0, emission_rate=1.0, **kw)


def _project(control=None, sources=None):
    return AERMODProject(
        control=control or ControlPathway(title_one="t", averaging_periods=["1"], pollutant_id="SO2"),
        sources=sources or SourcePathway(sources=[_stack()]),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
        output=OutputPathway(),
    )


def _errors(project, field=None):
    result = Validator.validate(project)
    return [e for e in result.errors
            if e.severity != "warning" and (field is None or field in e.field)]


def _codes(project, field=None):
    return {code for e in _errors(project, field)
            for code in ("E105", "E144", "E146", "E158", "E159", "E198", "E201", "E287",
                         "E320", "E371", "E372", "E373", "E374", "E713")
            if code in e.message}


# ---------------------------------------------------------------------
# PSDGROUP / PSDCREDIT
# ---------------------------------------------------------------------

def _psd_control(**kw):
    return ControlPathway(
        title_one="t", averaging_periods=["1"], pollutant_id="NO2",
        regulatory_default=False, alpha=True, beta=True,
        chemistry=ChemistryOptions(method=ChemistryMethod.PVMRM, default_no2_ratio=0.1,
                                   ozone_data=OzoneData(uniform_value=40.0)), **kw)


class TestPsdGroups:
    def test_valid_psdcredit_run(self):
        p = _project(_psd_control(psd_credit=True), SourcePathway(
            sources=[_stack("STK1"), _stack("STK2")],
            psd_groups=[SourceGroupDefinition("INCRCONS", ["STK1"]),
                        SourceGroupDefinition("NONRBASE", ["STK2"])]))
        assert not _errors(p, "psd_groups") and not _errors(p, "group_definitions")

    def test_psdgroup_needs_psdcredit(self):
        p = _project(_psd_control(), SourcePathway(
            sources=[_stack()], psd_groups=[SourceGroupDefinition("INCRCONS", ["STK1"])]))
        assert "E146" in _codes(p, "psd_groups")

    def test_psdcredit_forbids_srcgroup(self):
        p = _project(_psd_control(psd_credit=True), SourcePathway(
            sources=[_stack()], psd_groups=[SourceGroupDefinition("INCRCONS", ["STK1"])],
            group_definitions=[SourceGroupDefinition("G1", ["STK1"])]))
        assert "E105" in _codes(p, "group_definitions")

    def test_only_the_three_ids_are_accepted(self):
        p = _project(_psd_control(psd_credit=True), SourcePathway(
            sources=[_stack()], psd_groups=[SourceGroupDefinition("INC", ["STK1"])]))
        assert "E287" in _codes(p, "psd_groups")

    def test_psdgroup_without_members(self):
        p = _project(_psd_control(psd_credit=True), SourcePathway(
            sources=[_stack()], psd_groups=[SourceGroupDefinition("INCRCONS")]))
        assert "E201" in _codes(p, "psd_groups")

    def test_psdcredit_without_any_psdgroup(self):
        p = _project(_psd_control(psd_credit=True), SourcePathway(sources=[_stack()]))
        assert _errors(p, "psd_groups")


# ---------------------------------------------------------------------
# EMISUNIT / CONCUNIT / DEPOUNIT
# ---------------------------------------------------------------------

class TestUnitConversions:
    def test_emisunit_alone_is_fine(self):
        p = _project(sources=SourcePathway(
            sources=[_stack()], emission_units=EmissionUnits(1000.0, "GRAMS/SEC", "MILLIGRAMS/M**3")))
        assert not _errors(p, "units")

    def test_emisunit_conflicts_with_concunit(self):
        p = _project(sources=SourcePathway(
            sources=[_stack()],
            emission_units=EmissionUnits(1000.0, "GRAMS/SEC", "MILLIGRAMS/M**3"),
            concentration_units=EmissionUnits(1e6, "GRAMS/SEC", "MICROGRAMS/M**3")))
        assert "E159" in _codes(p, "emission_units")

    def test_emisunit_with_two_output_types(self):
        control = ControlPathway(title_one="t", averaging_periods=["1"], pollutant_id="SO2",
                                 calculate_dry_deposition=True, alpha=True,
                                 regulatory_default=False)
        p = _project(control, SourcePathway(
            sources=[_stack()], emission_units=EmissionUnits(1000.0, "GRAMS/SEC", "MILLIGRAMS/M**3")))
        assert "E158" in _codes(p, "emission_units")

    def test_concunit_and_depounit_together_are_fine(self):
        control = ControlPathway(title_one="t", averaging_periods=["1"], pollutant_id="SO2",
                                 calculate_dry_deposition=True, alpha=True,
                                 regulatory_default=False)
        p = _project(control, SourcePathway(
            sources=[_stack()],
            concentration_units=EmissionUnits(1e6, "GRAMS/SEC", "MICROGRAMS/M**3"),
            deposition_units=EmissionUnits(3.6e9, "GRAM/SEC", "MICROGRAMS/M**2")))
        assert not _errors(p, "units")

    @pytest.mark.parametrize("factor", [0.0, -1.0])
    def test_factor_must_be_positive(self, factor):
        p = _project(sources=SourcePathway(
            sources=[_stack()], deposition_units=EmissionUnits(factor, "A", "B")))
        assert _errors(p, "deposition_units.factor")


# ---------------------------------------------------------------------
# RLINEXT barriers and depressions, SBARRIER
# ---------------------------------------------------------------------

def _rlinext(**kw):
    return RLineExtSource("R1", 0.0, -100.0, 1.0, 0.0, 100.0, 1.0,
                          emission_rate=1.0, road_width=3.6, init_sigma_z=2.0, **kw)


def _alpha_flat(**kw):
    kw.setdefault("terrain_type", TerrainType.FLAT)
    kw.setdefault("alpha", True)
    return ControlPathway(title_one="t", averaging_periods=["1"], pollutant_id="OTHER",
                          regulatory_default=False, **kw)


class TestRlineConfiguration:
    def test_barriers_valid_with_alpha_and_flat(self):
        p = _project(_alpha_flat(), SourcePathway(sources=[_rlinext(
            barrier_height_1=10.0, barrier_dcl_1=10.0,
            depression_depth=-12.5, depression_wtop=50.0, depression_wbottom=25.0,
            vegetative_barriers=[VegetativeBarrier(5.0, 5.0, 8.0, 6.0, 1.0)])]))
        assert not _errors(p, "RLineExtSource")

    def test_rbarrier_needs_alpha(self):
        p = _project(_alpha_flat(alpha=False), SourcePathway(sources=[_rlinext(
            barrier_height_1=10.0, barrier_dcl_1=10.0)]))
        assert "E198" in _codes(p, "barrier_height_1")

    def test_rdepress_needs_flat(self):
        p = _project(_alpha_flat(terrain_type=TerrainType.ELEVATED), SourcePathway(sources=[_rlinext(
            depression_depth=-12.5, depression_wtop=50.0, depression_wbottom=25.0)]))
        assert "E713" in _codes(p, "depression_depth")

    @pytest.mark.parametrize("attr,value,code", [
        ("height", 12.0, "E371"), ("width", 1.0, "E372"),
        ("leaf_area_index", 3.0, "E373"), ("mixing_length", 4.0, "E374"),
    ])
    def test_vbarrier_ranges(self, attr, value, code):
        kw = dict(height=5.0, width=5.0, dcl=8.0, leaf_area_index=6.0, mixing_length=1.0)
        kw[attr] = value
        p = _project(_alpha_flat(), SourcePathway(sources=[_rlinext(
            vegetative_barriers=[VegetativeBarrier(**kw)])]))
        assert code in _codes(p, f"vegetative_barriers[1].{attr}")

    def test_more_than_two_vbarriers(self):
        p = _project(_alpha_flat(), SourcePathway(sources=[_rlinext(
            vegetative_barriers=[VegetativeBarrier(5.0, 5.0, 8.0, 6.0, 1.0)] * 3)]))
        assert _errors(p, "vegetative_barriers")

    def test_sbarrier_valid(self):
        p = _project(_alpha_flat(), SourcePathway(
            sources=[_rlinext()],
            solid_barriers=[SolidBarrier("W1", [SolidBarrierSegment(-50, 10, 50, 10, 4.0)])]))
        assert not _errors(p, "SolidBarrier") and not _errors(p, "solid_barriers")

    def test_sbarrier_needs_alpha_and_flat(self):
        p = _project(_alpha_flat(alpha=False, terrain_type=TerrainType.ELEVATED), SourcePathway(
            sources=[_rlinext()],
            solid_barriers=[SolidBarrier("W1", [SolidBarrierSegment(-50, 10, 50, 10, 4.0)])]))
        assert {"E198", "E713"} <= _codes(p, "solid_barriers")

    @pytest.mark.parametrize("height", [2.0, 12.5])
    def test_sbarrier_height_range(self, height):
        p = _project(_alpha_flat(), SourcePathway(
            sources=[_rlinext()],
            solid_barriers=[SolidBarrier("W1", [SolidBarrierSegment(-50, 10, 50, 10, height)])]))
        assert "E320" in _codes(p, "segments[1].height")

    def test_sbarrier_segment_count(self):
        p = _project(_alpha_flat(), SourcePathway(
            sources=[_rlinext()], solid_barriers=[SolidBarrier("W1", [])]))
        assert "E320" in _codes(p, "segments")


# ---------------------------------------------------------------------
# OLMGROUP and NO2RATIO
# ---------------------------------------------------------------------

class TestOlmAndNo2Ratio:
    def test_olmgroup_needs_olm(self):
        control = ControlPathway(
            title_one="t", averaging_periods=["1"], pollutant_id="NO2", regulatory_default=False,
            chemistry=ChemistryOptions(method=ChemistryMethod.PVMRM, default_no2_ratio=0.1,
                                       ozone_data=OzoneData(uniform_value=40.0),
                                       olm_groups=[SourceGroupDefinition("ALL")]))
        assert "E144" in _codes(_project(control), "olm_groups")

    def test_olmgroup_with_olm_is_fine(self):
        control = ControlPathway(
            title_one="t", averaging_periods=["1"], pollutant_id="NO2", regulatory_default=False,
            chemistry=ChemistryOptions(method=ChemistryMethod.OLM, default_no2_ratio=0.1,
                                       ozone_data=OzoneData(uniform_value=40.0),
                                       olm_groups=[SourceGroupDefinition("ALL")]))
        assert not _errors(_project(control), "olm_groups")

    def test_no2_ratio_range_on_any_source_type(self):
        src = VolumeSource("V1", 0.0, 0.0, release_height=10.0, emission_rate=1.0, no2_ratio=1.5)
        assert _errors(_project(sources=SourcePathway(sources=[src])), "no2_ratio")
        src.no2_ratio = 0.5
        assert not _errors(_project(sources=SourcePathway(sources=[src])), "no2_ratio")

"""Tests for regulatory profile presets."""

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
    TerrainType,
)
from pyaermod.regulatory import (
    ALL_PROFILES,
    EPA_APPENDIX_W_2017,
    EPA_APPENDIX_W_2023,
    SCREENING_PROFILE,
    RegulatoryProfile,
    get_profile,
)


def _make_project(**ctrl_kw) -> AERMODProject:
    ctrl = ControlPathway(
        title_one="t",
        pollutant_id=PollutantType.NO2,
        averaging_periods=["1", "ANNUAL"],
        **ctrl_kw,
    )
    src = PointSource(
        source_id="S1", x_coord=0, y_coord=0,
        stack_height=30.0, stack_temp=400.0, exit_velocity=10.0,
        stack_diameter=2.0, emission_rate=1.0,
    )
    return AERMODProject(
        control=ctrl,
        sources=SourcePathway(sources=[src]),
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(grid_name="G", x_init=0, x_num=2, x_delta=100,
                          y_init=0, y_num=2, y_delta=100),
        ]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


class TestApply:
    def test_apply_sets_regulatory_default(self):
        project = _make_project(regulatory_default=False)
        changes = EPA_APPENDIX_W_2017.apply(project)
        assert any("regulatory_default" in c for c in changes)
        assert project.control.regulatory_default is True

    def test_apply_switches_terrain_to_elev(self):
        project = _make_project(terrain_type=TerrainType.FLAT)
        changes = EPA_APPENDIX_W_2017.apply(project)
        assert any("terrain_type" in c for c in changes)
        assert project.control.terrain_type == "ELEV"

    def test_apply_disables_nondefault_flags(self):
        project = _make_project()
        project.control.flat_terrain = True
        project.control.no_stack_tip_downwash = True
        changes = EPA_APPENDIX_W_2017.apply(project)
        assert any("flat_terrain" in c for c in changes)
        assert any("no_stack_tip_downwash" in c for c in changes)
        assert project.control.flat_terrain is False
        assert project.control.no_stack_tip_downwash is False

    def test_apply_is_idempotent(self):
        project = _make_project()
        EPA_APPENDIX_W_2017.apply(project)
        changes2 = EPA_APPENDIX_W_2017.apply(project)
        assert changes2 == []


class TestCheck:
    def test_clean_project_no_warnings(self):
        project = _make_project(regulatory_default=True, terrain_type="ELEV")
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert warnings == []

    def test_missing_dfault_warns(self):
        project = _make_project(regulatory_default=False)
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert any("regulatory_default" in w for w in warnings)

    def test_flat_terrain_warns(self):
        project = _make_project(terrain_type=TerrainType.FLAT)
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert any("terrain_type" in w for w in warnings)

    def test_forbidden_flag_warns(self):
        project = _make_project()
        project.control.use_lowwind1 = True
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert any("use_lowwind1" in w for w in warnings)

    def test_disallowed_low_wind_warns(self):
        project = _make_project(low_wind_option="LOWWIND1")
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert any("low_wind_option" in w for w in warnings)

    def test_screening_forbids_any_low_wind(self):
        project = _make_project(low_wind_option="LOWWIND3")
        warnings = SCREENING_PROFILE.check(project)
        assert any("low_wind_option" in w for w in warnings)


class TestProfileRegistry:
    def test_get_profile_lookup(self):
        p = get_profile("EPA-AppendixW-2017")
        assert isinstance(p, RegulatoryProfile)

    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError):
            get_profile("nope")

    def test_all_profiles_apply_cleanly_to_default_project(self):
        # Every canonical profile should leave a default project in a
        # clean state (no self-conflict).
        for name, profile in ALL_PROFILES.items():
            project = _make_project()
            profile.apply(project)
            warnings = profile.check(project)
            assert warnings == [], f"{name} post-apply warnings: {warnings}"


class TestProfile2023BetaChemistry:
    """PVMRM2 and GRSM are BETA in AERMOD v23132/v24142 per EPA
    Appendix W 2023 memos. Neither is DFAULT-compatible; they require
    case-by-case agency concurrence. The profile's primary
    allow_chemistry_methods tuple therefore keeps only OLM and PVMRM;
    BETA methods live in a separate tuple."""

    def test_beta_methods_constant_exported(self):
        from pyaermod.regulatory import EPA_APPENDIX_W_2023_BETA_METHODS
        assert "PVMRM2" in EPA_APPENDIX_W_2023_BETA_METHODS
        assert "GRSM" in EPA_APPENDIX_W_2023_BETA_METHODS

    def test_pvmrm2_not_in_2023_default_allow(self):
        """PVMRM2 remains BETA — must NOT be silently in allow list."""
        assert "PVMRM2" not in EPA_APPENDIX_W_2023.allow_chemistry_methods

    def test_grsm_not_in_2023_default_allow(self):
        """GRSM remains BETA — same rule."""
        assert "GRSM" not in EPA_APPENDIX_W_2023.allow_chemistry_methods

    def test_olm_and_pvmrm_still_in_2023(self):
        """OLM + PVMRM remain the two DFAULT-compatible methods."""
        assert "OLM" in EPA_APPENDIX_W_2023.allow_chemistry_methods
        assert "PVMRM" in EPA_APPENDIX_W_2023.allow_chemistry_methods

    def test_2017_unchanged(self):
        assert "PVMRM2" not in EPA_APPENDIX_W_2017.allow_chemistry_methods
        assert "GRSM" not in EPA_APPENDIX_W_2017.allow_chemistry_methods

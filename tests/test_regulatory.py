"""Tests for regulatory profile presets."""

from __future__ import annotations

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
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
    EPA_APPENDIX_W_2024,
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
        # The real switches (these tests once set attributes ControlPathway
        # does not have, so the profile never acted on a real project).
        project = _make_project(extra_model_options=["FLAT", "NOSTD", "FASTAREA"],
                                beta=True)
        changes = EPA_APPENDIX_W_2017.apply(project)
        assert any("flat_terrain" in c for c in changes)
        assert any("no_stack_tip_downwash" in c for c in changes)
        assert any("beta_options" in c for c in changes)
        assert project.control.extra_model_options == ["FASTAREA"]
        assert project.control.beta is False

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
        project = _make_project(extra_model_options=["LOWWIND1"])
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert any("use_lowwind1" in w for w in warnings)

    def test_custom_profile_forbids_a_modelopt_token(self):
        profile = RegulatoryProfile(name="X", description="",
                                    forbid_nondefault_flags=("FASTAREA", "psd_credit"))
        project = _make_project(extra_model_options=["fastarea"], psd_credit=True,
                                terrain_type="ELEV")
        assert len(profile.check(project)) == 2
        profile.apply(project)
        assert project.control.extra_model_options == []
        assert project.control.psd_credit is False

    @pytest.mark.parametrize("name", sorted(ALL_PROFILES))
    @pytest.mark.parametrize("option", ["LOWWIND3", "0.3 0.5"])
    def test_no_profile_accepts_a_low_wind_option(self, name, option):
        """CO LOW_WIND needs ALPHA, which AERMOD refuses beside DFAULT; the
        2017 rule declined LOWWIND3 and v18081 removed LOWWIND1/2/3."""
        profile = ALL_PROFILES[name]
        assert profile.allowed_low_wind == ()
        project = _make_project(low_wind_option=option)
        assert any("low_wind_option" in w for w in profile.check(project))

    def test_apply_clears_a_low_wind_option(self):
        project = _make_project(low_wind_option="0.3 0.5")
        changes = EPA_APPENDIX_W_2024.apply(project)
        assert project.control.low_wind_option is None
        assert any("low_wind_option" in c for c in changes)
        assert EPA_APPENDIX_W_2024.check(project) == []


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


def _chem(method: str) -> ChemistryOptions:
    return ChemistryOptions(method=ChemistryMethod[method])


class TestNO2Tiers:
    """Appendix W 4.2.3.4: ARM2 is Tier 2 in the 2017 and 2024 revisions;
    OLM and PVMRM are Tier 3 in both, GRSM from the 2024 revision
    (89 FR 95034; regulatory in AERMOD from v24142, BETA in v23132)."""

    @pytest.mark.parametrize("name", sorted(ALL_PROFILES))
    @pytest.mark.parametrize("method", ["ARM2", "OLM", "PVMRM"])
    def test_every_profile_accepts_arm2_olm_and_pvmrm(self, name, method):
        project = _make_project(chemistry=_chem(method), terrain_type="ELEV")
        assert ALL_PROFILES[name].check(project) == []

    @pytest.mark.parametrize("profile,accepted", [
        (EPA_APPENDIX_W_2017, False),
        (EPA_APPENDIX_W_2023, False),
        (EPA_APPENDIX_W_2024, True),
    ], ids=["2017", "2023", "2024"])
    def test_grsm_is_accepted_from_the_2024_revision(self, profile, accepted):
        project = _make_project(chemistry=_chem("GRSM"), terrain_type="ELEV")
        flagged = any("GRSM" in w for w in profile.check(project))
        assert flagged is not accepted

    @pytest.mark.parametrize("name", sorted(ALL_PROFILES))
    @pytest.mark.parametrize("method", ["TTRM", "TTRM2"])
    def test_alpha_methods_are_flagged(self, name, method):
        project = _make_project(chemistry=_chem(method), terrain_type="ELEV")
        assert any(method in w for w in ALL_PROFILES[name].check(project))

    @pytest.mark.parametrize("method", ["OLM", "PVMRM", "GRSM"])
    def test_tier3_gives_the_consultation_note_and_no_finding(self, method):
        project = _make_project(chemistry=_chem(method), terrain_type="ELEV")
        assert EPA_APPENDIX_W_2024.check(project) == []
        notes = EPA_APPENDIX_W_2024.advisories(project)
        assert len(notes) == 1
        assert "Regional Office" in notes[0] and "4.2.3.4(e)" in notes[0]

    @pytest.mark.parametrize("chemistry", [None, "ARM2"])
    def test_tiers_1_and_2_give_no_note(self, chemistry):
        kw = {"chemistry": _chem(chemistry)} if chemistry else {}
        assert EPA_APPENDIX_W_2024.advisories(_make_project(**kw)) == []

    def test_a_refused_method_gives_a_finding_not_a_note(self):
        project = _make_project(chemistry=_chem("GRSM"))
        assert EPA_APPENDIX_W_2017.advisories(project) == []

    def test_no_profile_mentions_pvmrm2(self):
        """The 2017 rule made the PVMRM2 method the regulatory PVMRM
        (v16216); the keyword no longer exists."""
        from pyaermod.regulatory import EPA_APPENDIX_W_2023_BETA_METHODS
        assert EPA_APPENDIX_W_2023_BETA_METHODS == ("GRSM",)
        for profile in ALL_PROFILES.values():
            text = profile.description + " ".join(profile.notes)
            assert "PVMRM2" not in text
            assert "PVMRM2" not in profile.allow_chemistry_methods

    def test_the_2024_profile_is_registered_and_exported(self):
        import pyaermod
        assert get_profile("EPA-AppendixW-2024") is EPA_APPENDIX_W_2024
        assert pyaermod.EPA_APPENDIX_W_2024 is EPA_APPENDIX_W_2024
        assert "89 FR 95034" in EPA_APPENDIX_W_2024.description

    def test_the_2023_profile_says_what_it_is(self):
        assert "no 2023 revision" in EPA_APPENDIX_W_2023.description
        assert (EPA_APPENDIX_W_2023.allow_chemistry_methods
                == EPA_APPENDIX_W_2017.allow_chemistry_methods)

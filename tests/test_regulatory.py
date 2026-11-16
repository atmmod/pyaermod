"""Tests for regulatory profile presets."""

from __future__ import annotations

from pathlib import Path

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
from pyaermod.input_reader import parse_aermod_input
from pyaermod.regulatory import (
    ALL_PROFILES,
    EPA_APPENDIX_W_2017,
    EPA_APPENDIX_W_2023,
    SCREENING_PROFILE,
    RegulatoryProfile,
    get_profile,
)

#: Every MODELOPT token without a field of its own that coset.f MODOPT
#: drops (W206) or refuses (E204, E133, E198, E203) when DFAULT is on the
#: line, as the reader stores it in extra_model_options (probe decks
#: scripts/oracle_decks/31a-31f, AERMOD v26135). ALPHA, BETA and PSDCREDIT have fields.
DFAULT_TOKENS = [
    "FLAT", "NOSTD", "NOCHKD", "SCREEN",
    "AREADPLT", "SCIM", "TOXICS", "HBP", "TTRM2", "FASTAREA", "FASTALL",
    "NOURBTRAN", "AREAMNDR",
    "LOW_WIND", "TTRM", "RLINEFDH",
    "LOWWIND1", "LOWWIND2", "LOWWIND3",
]


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

    @pytest.mark.parametrize("token", DFAULT_TOKENS)
    def test_apply_removes_nondefault_modelopt_token(self, token):
        project = _make_project(terrain_type="ELEV", extra_model_options=[token, "NOWARN"])
        changes = EPA_APPENDIX_W_2017.apply(project)
        assert any(token in c for c in changes)
        assert project.control.extra_model_options == ["NOWARN"]
        assert token not in project.control._model_options()

    @pytest.mark.parametrize("field_name", ["alpha", "beta", "psd_credit"])
    def test_apply_clears_nondefault_switch(self, field_name):
        project = _make_project(terrain_type="ELEV", **{field_name: True})
        changes = EPA_APPENDIX_W_2017.apply(project)
        assert any(field_name in c for c in changes)
        assert getattr(project.control, field_name) is False

    def test_apply_clears_low_wind_card(self):
        # CO LOW_WIND needs ALPHA (E133), and DFAULT refuses ALPHA (E204).
        project = _make_project(terrain_type="ELEV", low_wind_option="0.5")
        changes = EPA_APPENDIX_W_2017.apply(project)
        assert any("low_wind_option" in c for c in changes)
        assert project.control.low_wind_option is None
        assert "LOW_WIND" not in project.control.to_aermod_input()

    def test_apply_leaves_a_clean_project_clean(self):
        project = _make_project(
            terrain_type=TerrainType.FLAT, alpha=True, beta=True,
            low_wind_option="0.5", extra_model_options=["NOSTD", "FASTALL"],
        )
        EPA_APPENDIX_W_2017.apply(project)
        assert EPA_APPENDIX_W_2017.check(project) == []

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

    @pytest.mark.parametrize("token", DFAULT_TOKENS)
    def test_nondefault_modelopt_token_warns(self, token):
        project = _make_project(terrain_type="ELEV", extra_model_options=[token])
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert len(warnings) == 1
        assert token in warnings[0]

    @pytest.mark.parametrize("field_name, token", [
        ("alpha", "ALPHA"), ("beta", "BETA"), ("psd_credit", "PSDCREDIT"),
    ])
    def test_nondefault_switch_warns(self, field_name, token):
        project = _make_project(terrain_type="ELEV", **{field_name: True})
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert any(token in w and "E204" in w for w in warnings)

    def test_nostd_names_the_override(self):
        project = _make_project(terrain_type="ELEV", extra_model_options=["NOSTD"])
        (warning,) = EPA_APPENDIX_W_2017.check(project)
        assert "W206" in warning

    def test_a_deck_read_from_disk_is_flagged_and_fixed(self):
        # The case the old attribute names could never see: NOSTD read
        # from a real deck lands in extra_model_options.
        deck = Path(__file__).parents[1] / "scripts" / "oracle_decks" / "31a_modelopt_dfault_overrides.inp"
        project = parse_aermod_input(deck.read_text())
        warnings = EPA_APPENDIX_W_2017.check(project)
        for token in ("NOSTD", "NOCHKD", "SCREEN", "ALPHA", "BETA"):
            assert any(token in w for w in warnings), token
        EPA_APPENDIX_W_2017.apply(project)
        assert EPA_APPENDIX_W_2017.check(project) == []
        assert "NOSTD" not in project.control.to_aermod_input()

    def test_dfault_accepted_options_do_not_warn(self):
        project = _make_project(
            terrain_type="ELEV",
            extra_model_options=["NOWARN", "WARNCHKD", "NODRYDPLT"],
        )
        assert EPA_APPENDIX_W_2017.check(project) == []

    def test_low_wind_card_warns_under_dfault(self):
        project = _make_project(terrain_type="ELEV", low_wind_option="0.5")
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert any("low_wind_option" in w and "E133" in w for w in warnings)

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

"""DFAULT consistency on real ControlPathway fields (F1, C8, DOCS-6).

The regulatory profiles and the advanced DFAULT check used to look at
attributes ControlPathway does not have (flat_terrain, use_lowwind1, ...).
These tests use the real switches: ``alpha``, ``beta``, ``psd_credit``
and MODELOPT tokens in ``extra_model_options``.

AERMOD v24142 coset.f MODOPT, with DFAULT on MODELOPT:
  E204 (fatal): ALPHA 1868-1872, BETA 1880-1885, PSDCREDIT 1852-1861,
                FASTAREA 1887-1899, FASTALL 1900-1916, SCIM 1766-1773,
                NOURBTRAN 1917-1929, AREADPLT 1705-1712, HBP 1794-1805,
                TTRM2 1817-1828
  W206 (option dropped, run continues): FLAT 1639-1645, NOSTD 1728-1736,
                NOCHKD 1738-1748, SCREEN 1756-1765
Setup-only bin/aermod runs reproduce E204 for ALPHA, BETA, FASTAREA and
W206 for NOSTD and FLAT.
"""

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.regulatory import ALL_PROFILES, RegulatoryProfile
from pyaermod.validator import Validator
from pyaermod.validator_advanced import advanced_validate


def _project(**ctrl_kw) -> AERMODProject:
    ctrl_kw.setdefault("terrain_type", "ELEV")
    return AERMODProject(
        control=ControlPathway(title_one="t", **ctrl_kw),
        sources=SourcePathway(sources=[PointSource(
            source_id="S1", x_coord=0, y_coord=0, stack_height=30.0,
            stack_temp=400.0, exit_velocity=10.0, stack_diameter=2.0,
            emission_rate=1.0)]),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid(
            grid_name="G", x_init=-100, x_num=5, x_delta=50,
            y_init=-100, y_num=5, y_delta=50)]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


def _findings(project):
    return list(Validator.validate(project).errors) + list(advanced_validate(project))


def _modelopt(project):
    return next(line for line in project.control.to_aermod_input().splitlines()
                if "MODELOPT" in line).split()[1:]


# ---------------------------------------------------------------------------
# Regulatory profiles (F1, DOCS-6)
# ---------------------------------------------------------------------------

NONDEFAULT = [
    ("alpha", {"alpha": True}, "ALPHA"),
    ("beta", {"beta": True}, "BETA"),
    ("NOSTD", {"extra_model_options": ["NOSTD"]}, "NOSTD"),
]


@pytest.mark.parametrize("profile", sorted(ALL_PROFILES))
@pytest.mark.parametrize("label,kw,token", NONDEFAULT, ids=[n[0] for n in NONDEFAULT])
def test_profile_check_reports_nondefault_option(profile, label, kw, token):
    project = _project(**kw)
    assert ALL_PROFILES[profile].check(project), (
        f"{profile}.check() said nothing about MODELOPT {token}")


@pytest.mark.parametrize("profile", sorted(ALL_PROFILES))
@pytest.mark.parametrize("label,kw,token", NONDEFAULT, ids=[n[0] for n in NONDEFAULT])
def test_profile_apply_removes_nondefault_option(profile, label, kw, token):
    project = _project(**kw)
    ALL_PROFILES[profile].apply(project)
    assert token not in _modelopt(project)


# ---------------------------------------------------------------------------
# Validator: DFAULT with a non-DFAULT option (C8)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kw", [
    {"alpha": True},
    {"beta": True},
    {"psd_credit": True, "alpha": True},
    {"extra_model_options": ["FASTAREA"]},
    {"extra_model_options": ["FASTALL"]},
    {"extra_model_options": ["SCIM"]},
    {"extra_model_options": ["NOURBTRAN"]},
    {"extra_model_options": ["AREADPLT"]},
], ids=["ALPHA", "BETA", "PSDCREDIT", "FASTAREA", "FASTALL", "SCIM", "NOURBTRAN", "AREADPLT"])
def test_dfault_with_fatal_nondefault_option_is_an_error(kw):
    project = _project(regulatory_default=True, **kw)
    assert any(f.severity == "error"
               and ("DFAULT" in f.message or f.field == "regulatory_default")
               for f in _findings(project))


@pytest.mark.parametrize("token", ["NOSTD", "NOCHKD", "SCREEN"])
def test_dfault_overridden_option_is_warned(token):
    project = _project(regulatory_default=True, extra_model_options=[token])
    assert any(token in f.message for f in _findings(project))


def test_nondefault_options_without_dfault_are_fine():
    project = _project(regulatory_default=False, alpha=True, beta=True,
                       extra_model_options=["NOSTD", "FASTAREA"])
    assert [f for f in _findings(project)
            if f.severity == "error" and f.field == "regulatory_default"] == []


@pytest.mark.parametrize("kw", [
    {"extra_model_options": ["HBP"]},
    {"extra_model_options": ["TTRM2"]},
], ids=["HBP", "TTRM2"])
def test_dfault_with_other_fatal_options_is_an_error(kw):
    project = _project(regulatory_default=True, **kw)
    assert any(e.severity == "error" and e.field == "regulatory_default"
               for e in Validator.validate(project).errors)


def test_dfault_finding_is_reported_once_by_validate():
    project = _project(regulatory_default=True, beta=True)
    found = [e for e in Validator.validate(project).errors
             if e.field == "regulatory_default"]
    assert len(found) == 1


def test_legacy_names_map_to_real_switches():
    profile = RegulatoryProfile(name="X", description="",
                                forbid_nondefault_flags=("use_lowwind2", "beta_options"))
    project = _project(beta=True, extra_model_options=["LOWWIND2"])
    assert len(profile.check(project)) == 2
    profile.apply(project)
    assert "BETA" not in _modelopt(project)
    assert "LOWWIND2" not in _modelopt(project)

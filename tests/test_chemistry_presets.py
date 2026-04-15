"""Tests for chemistry_presets."""

from __future__ import annotations

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ChemistryMethod,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.chemistry_presets import (
    DEPOSITION_DEFAULTS,
    arm2_preset,
    deposition_defaults_for,
    deposition_diagnostics,
    grsm_preset,
    olm_preset,
    pvmrm_preset,
    suggest_chemistry_for,
)


# ---------------------------------------------------------------------------
# Chemistry presets
# ---------------------------------------------------------------------------

class TestOLM:
    def test_with_uniform_ozone(self):
        c = olm_preset(ozone_ppb=30.0)
        assert c.method == ChemistryMethod.OLM
        assert c.ozone_data.uniform_value == 30.0

    def test_with_ozone_file(self):
        c = olm_preset(ozone_file="o3.dat")
        assert c.ozone_data.ozone_file == "o3.dat"

    def test_requires_ozone_source(self):
        with pytest.raises(ValueError):
            olm_preset()


class TestPVMRM:
    def test_preset(self):
        c = pvmrm_preset(ozone_ppb=25.0)
        assert c.method == ChemistryMethod.PVMRM

    def test_requires_ozone(self):
        with pytest.raises(ValueError):
            pvmrm_preset()


class TestARM2:
    def test_preset_no_ozone_needed(self):
        c = arm2_preset()
        assert c.method == ChemistryMethod.ARM2
        assert c.ozone_data is None


class TestGRSM:
    def test_preset(self):
        c = grsm_preset(ozone_ppb=20.0, nox_background_file="nox.dat")
        assert c.method == ChemistryMethod.GRSM
        assert c.nox_file == "nox.dat"

    def test_requires_ozone(self):
        with pytest.raises(ValueError):
            grsm_preset()


class TestSuggestChemistry:
    def test_non_no2_returns_none(self):
        assert suggest_chemistry_for(PollutantType.SO2, n_sources=5, has_ozone_data=True) == "NONE"

    def test_no_ozone_arm2(self):
        assert suggest_chemistry_for(PollutantType.NO2, 3, has_ozone_data=False) == "ARM2"

    def test_ozone_with_nox_is_grsm(self):
        assert suggest_chemistry_for(
            PollutantType.NO2, 3, has_ozone_data=True, has_nox_background=True
        ) == "GRSM"

    def test_many_sources_pvmrm(self):
        assert suggest_chemistry_for(PollutantType.NO2, 10, has_ozone_data=True) == "PVMRM"

    def test_few_sources_olm(self):
        assert suggest_chemistry_for(PollutantType.NO2, 2, has_ozone_data=True) == "OLM"


# ---------------------------------------------------------------------------
# Deposition defaults
# ---------------------------------------------------------------------------

class TestDepositionDefaults:
    def test_lookup_so2(self):
        d = deposition_defaults_for("SO2")
        assert d.pollutant == "SO2"
        assert d.gas is not None and d.particle is None

    def test_lookup_pm25(self):
        d = deposition_defaults_for("PM25")
        assert d.particle is not None and d.gas is None

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            deposition_defaults_for("CLOUD9")

    def test_registry_covers_common_pollutants(self):
        for key in ("SO2", "NOX", "NO2", "PM25", "PM10", "HG"):
            assert key in DEPOSITION_DEFAULTS


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _project_with_source(src) -> AERMODProject:
    return AERMODProject(
        control=ControlPathway(
            title_one="t", pollutant_id=PollutantType.SO2,
            averaging_periods=["ANNUAL"], calculate_dry_deposition=False,
        ),
        sources=SourcePathway(sources=[src]),
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(x_init=0, x_num=2, x_delta=100, y_init=0, y_num=2, y_delta=100)
        ]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


def _src(**kw):
    base = dict(
        source_id="S1", x_coord=0, y_coord=0, stack_height=30.0,
        stack_temp=400.0, exit_velocity=10.0, stack_diameter=2.0,
        emission_rate=1.0,
    )
    base.update(kw)
    return PointSource(**base)


class TestDiagnostics:
    def test_clean_project_no_warnings(self):
        project = _project_with_source(_src())
        assert deposition_diagnostics(project) == []

    def test_method_without_params_warns(self):
        src = _src()
        from pyaermod import DepositionMethod
        src.deposition_method = DepositionMethod.GASDEPVD
        project = _project_with_source(src)
        warns = deposition_diagnostics(project)
        assert any("no gas_deposition" in w for w in warns)

    def test_both_gas_and_particle_warns(self):
        src = _src()
        src.gas_deposition = deposition_defaults_for("SO2").gas
        src.particle_deposition = deposition_defaults_for("PM25").particle
        project = _project_with_source(src)
        warns = deposition_diagnostics(project)
        assert any("both gas_deposition and particle_deposition" in w for w in warns)

    def test_dry_deposition_requested_without_params_warns(self):
        src = _src()
        project = _project_with_source(src)
        project.control.calculate_dry_deposition = True
        warns = deposition_diagnostics(project)
        assert any("no source has" in w for w in warns)

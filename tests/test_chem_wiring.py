"""Tests for chemistry / deposition project-level wiring helpers."""

from __future__ import annotations

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ChemistryMethod,
    ControlPathway,
    DepositionMethod,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourceGroupDefinition,
    SourcePathway,
)
from pyaermod.chemistry_presets import (
    apply_chemistry,
    apply_deposition_defaults,
    grsm_preset,
    olm_preset,
)


def _project(*, pollutant=PollutantType.SO2, n_sources=2,
             extra_group: SourceGroupDefinition = None) -> AERMODProject:
    sources = []
    for i in range(n_sources):
        sources.append(PointSource(
            source_id=f"S{i+1}", x_coord=100.0 * i, y_coord=0.0,
            stack_height=30.0, stack_temp=400.0, exit_velocity=10.0,
            stack_diameter=2.0, emission_rate=1.0,
        ))
    sp = SourcePathway(sources=sources)
    if extra_group:
        sp.group_definitions.append(extra_group)
    return AERMODProject(
        control=ControlPathway(
            title_one="t", pollutant_id=pollutant,
            averaging_periods=["ANNUAL"],
        ),
        sources=sp,
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(x_init=0, x_num=2, x_delta=100,
                          y_init=0, y_num=2, y_delta=100),
        ]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


# ---------------------------------------------------------------------------
# apply_chemistry
# ---------------------------------------------------------------------------

class TestApplyChemistry:
    def test_installs_chemistry_on_control(self):
        project = _project(pollutant=PollutantType.NO2)
        changes = apply_chemistry(project, olm_preset(ozone_ppb=25.0))
        assert project.control.chemistry is not None
        assert project.control.chemistry.method == ChemistryMethod.OLM
        assert any("installed chemistry" in c for c in changes)

    def test_replaces_existing_chemistry(self):
        project = _project(pollutant=PollutantType.NO2)
        apply_chemistry(project, olm_preset(ozone_ppb=25.0))
        changes = apply_chemistry(project, grsm_preset(ozone_ppb=30.0,
                                                       nox_background_file="nox.dat"))
        assert project.control.chemistry.method == ChemistryMethod.GRSM
        assert any("replaced chemistry" in c for c in changes)

    def test_wires_existing_olm_group(self):
        grp = SourceGroupDefinition(group_name="GRP1", member_source_ids=["S1"])
        project = _project(pollutant=PollutantType.NO2, extra_group=grp)
        changes = apply_chemistry(
            project, olm_preset(ozone_ppb=25.0),
            olm_source_group_names=["GRP1"],
        )
        assert project.control.chemistry.olm_groups == [grp]
        assert any("wired olm_group GRP1" in c for c in changes)

    def test_warns_when_olm_group_missing(self):
        project = _project(pollutant=PollutantType.NO2)
        changes = apply_chemistry(
            project, olm_preset(ozone_ppb=25.0),
            olm_source_group_names=["NOPE"],
        )
        assert any("WARN" in c and "NOPE" in c for c in changes)


# ---------------------------------------------------------------------------
# apply_deposition_defaults
# ---------------------------------------------------------------------------

class TestApplyDepositionDefaults:
    def test_sets_gas_deposition_for_so2(self):
        project = _project(pollutant=PollutantType.SO2)
        changes = apply_deposition_defaults(project)
        for src in project.sources.sources:
            assert src.gas_deposition is not None
            assert src.deposition_method == DepositionMethod.GASDEPVD
        assert len(changes) == len(project.sources.sources)

    def test_sets_particle_deposition_for_pm25(self):
        project = _project(pollutant=PollutantType.PM25)
        apply_deposition_defaults(project)
        for src in project.sources.sources:
            assert src.particle_deposition is not None

    def test_no_defaults_for_unknown_pollutant_returns_warning(self):
        project = _project(pollutant=PollutantType.OTHER)
        changes = apply_deposition_defaults(project, pollutant="OTHER")
        assert len(changes) == 1
        assert "no deposition defaults" in changes[0]

    def test_overwrite_false_preserves_existing(self):
        from pyaermod.chemistry_presets import deposition_defaults_for
        project = _project(pollutant=PollutantType.SO2)
        # Pre-populate S1 with custom gas deposition
        existing = deposition_defaults_for("NO2").gas
        project.sources.sources[0].gas_deposition = existing
        # Apply SO2 defaults without overwrite — S1 stays NO2-ish
        apply_deposition_defaults(project, overwrite=False)
        assert project.sources.sources[0].gas_deposition is existing
        # S2 gets SO2 defaults applied
        assert project.sources.sources[1].gas_deposition is not None

    def test_overwrite_true_replaces_existing(self):
        from pyaermod.chemistry_presets import deposition_defaults_for
        project = _project(pollutant=PollutantType.SO2)
        project.sources.sources[0].gas_deposition = deposition_defaults_for("NO2").gas
        apply_deposition_defaults(project, overwrite=True)
        so2_default = deposition_defaults_for("SO2").gas
        assert project.sources.sources[0].gas_deposition is so2_default

    def test_include_source_ids_limits_scope(self):
        project = _project(pollutant=PollutantType.SO2, n_sources=3)
        changes = apply_deposition_defaults(project, include_source_ids=["S2"])
        assert len(changes) == 1
        assert project.sources.sources[0].gas_deposition is None
        assert project.sources.sources[1].gas_deposition is not None
        assert project.sources.sources[2].gas_deposition is None

    def test_exclude_source_ids_skips_listed(self):
        project = _project(pollutant=PollutantType.SO2, n_sources=3)
        apply_deposition_defaults(project, exclude_source_ids=["S2"])
        assert project.sources.sources[1].gas_deposition is None
        assert project.sources.sources[0].gas_deposition is not None

    def test_include_and_exclude_together_errors(self):
        project = _project()
        with pytest.raises(ValueError, match="not both"):
            apply_deposition_defaults(
                project, include_source_ids=["S1"], exclude_source_ids=["S2"],
            )

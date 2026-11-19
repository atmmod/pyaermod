"""F2: apply_deposition_defaults must leave a project the GUI can save."""

import pytest

from pyaermod import (
    AERMODProject,
    AreaSource,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.chemistry_presets import apply_deposition_defaults
from pyaermod.gui_v2.project_io import check_project


def _project(pollutant):
    src = AreaSource(source_id="A1", x_coord=0, y_coord=0, emission_rate=1e-5, release_height=1.0,
                     initial_sigma_z=1.0)
    return AERMODProject(
        control=ControlPathway(title_one="t", pollutant_id=pollutant),
        sources=SourcePathway(sources=[src]), receptors=ReceptorPathway(),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway())


@pytest.mark.parametrize("pollutant,name", [(PollutantType.SO2, "SO2"), (PollutantType.PM25, "PM25")])
def test_a_project_with_deposition_defaults_applied_can_be_saved(pollutant, name):
    project = _project(pollutant)
    changes = apply_deposition_defaults(project, name)
    assert changes, "the preset applied nothing, so the test proves nothing"
    check_project(project)       # raised: deposition_method must be a JSON list, not a JSON object

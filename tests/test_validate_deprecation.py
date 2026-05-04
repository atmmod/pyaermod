"""Tests for the validate=None DeprecationWarning on to_aermod_input.

In pyaermod 2.0 the default for validate= will flip from False to
True so projects that don't specify get auto-validated. The 1.x
deprecation cycle is:

- validate=None (the new default): behave like False, emit a
  DeprecationWarning pointing at the upcoming 2.0 behavior change
- validate=True: run validator, raise on errors
- validate=False: skip validation silently
"""

from __future__ import annotations

import warnings

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


@pytest.fixture
def good_project():
    return AERMODProject(
        control=ControlPathway(
            title_one="t", pollutant_id=PollutantType.SO2,
            averaging_periods=["ANNUAL"],
        ),
        sources=SourcePathway(sources=[PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=30.0, stack_temp=400.0,
            exit_velocity=10.0, stack_diameter=2.0,
            emission_rate=1.0,
        )]),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
        ),
        output=OutputPathway(),
    )


class TestValidateDefault:
    def test_no_arg_emits_deprecation_warning(self, good_project):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            good_project.to_aermod_input()
        msgs = [str(w.message) for w in caught
                if issubclass(w.category, DeprecationWarning)]
        assert any("validate=" in m for m in msgs)
        assert any("2.0" in m for m in msgs)

    def test_explicit_true_no_warning(self, good_project):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            good_project.to_aermod_input(validate=True)
        depwarns = [w for w in caught
                    if issubclass(w.category, DeprecationWarning)]
        assert len(depwarns) == 0, f"unexpected DeprecationWarnings: {depwarns}"

    def test_explicit_false_no_warning(self, good_project):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            good_project.to_aermod_input(validate=False)
        depwarns = [w for w in caught
                    if issubclass(w.category, DeprecationWarning)]
        assert len(depwarns) == 0


class TestWriteForwarding:
    def test_write_without_validate_arg_warns(self, good_project, tmp_path):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            good_project.write(tmp_path / "out.inp")
        msgs = [str(w.message) for w in caught
                if issubclass(w.category, DeprecationWarning)]
        assert any("validate=" in m for m in msgs)

    def test_write_with_validate_true_no_warning(self, good_project, tmp_path):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            good_project.write(tmp_path / "out.inp", validate=True)
        depwarns = [w for w in caught
                    if issubclass(w.category, DeprecationWarning)]
        assert len(depwarns) == 0


class TestValidateActuallyValidates:
    def test_invalid_project_raises_with_validate_true(self, good_project):
        # Make the project invalid: empty title
        good_project.control.title_one = ""
        with pytest.raises(ValueError, match="title_one"):
            good_project.to_aermod_input(validate=True)

    def test_invalid_project_silent_with_validate_false(self, good_project):
        good_project.control.title_one = ""
        # No exception
        good_project.to_aermod_input(validate=False)

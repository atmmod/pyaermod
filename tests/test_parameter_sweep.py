"""Tests for BatchRunner.parameter_sweep (formerly a stub)."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from pyaermod import (
    AERMODProject,
    BatchRunner,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.runner import AERMODRunner, _set_sweep_parameter


@pytest.fixture
def base_project():
    return AERMODProject(
        control=ControlPathway(
            title_one="Sweep Test",
            pollutant_id=PollutantType.SO2,
            averaging_periods=["ANNUAL"],
        ),
        sources=SourcePathway(sources=[
            PointSource(
                source_id="S1", x_coord=0.0, y_coord=0.0,
                stack_height=30.0, stack_temp=400.0,
                exit_velocity=10.0, stack_diameter=2.0,
                emission_rate=1.0,
            ),
        ]),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
        ),
        output=OutputPathway(),
    )


@pytest.fixture
def fake_aermod_exe(tmp_path):
    if platform.system() == "Windows":
        exe = tmp_path / "aermod.bat"
        exe.write_text("@echo off\nexit /b 0\n")
    else:
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        exe.chmod(0o755)
    return exe


# ---------------------------------------------------------------------------
# _set_sweep_parameter
# ---------------------------------------------------------------------------

class TestSetSweepParameter:
    def test_plain_attr_mutates_first_source(self, base_project):
        _set_sweep_parameter(base_project, "emission_rate", 2.5)
        assert base_project.sources.sources[0].emission_rate == 2.5

    def test_source_index_picks_different_source(self, base_project):
        base_project.sources.sources.append(PointSource(
            source_id="S2", x_coord=100, y_coord=0,
            stack_height=30.0, stack_temp=400.0,
            exit_velocity=10.0, stack_diameter=2.0, emission_rate=1.0,
        ))
        _set_sweep_parameter(base_project, "emission_rate", 9.9, source_index=1)
        assert base_project.sources.sources[0].emission_rate == 1.0  # unchanged
        assert base_project.sources.sources[1].emission_rate == 9.9

    def test_dotted_path_mutates_project_root(self, base_project):
        _set_sweep_parameter(base_project, "control.title_one", "Swept")
        assert base_project.control.title_one == "Swept"

    def test_bad_index_raises(self, base_project):
        with pytest.raises(IndexError, match="source_index"):
            _set_sweep_parameter(base_project, "emission_rate", 1.0, source_index=99)

    def test_no_sources_raises(self, base_project):
        base_project.sources.sources = []
        with pytest.raises(ValueError, match="no sources"):
            _set_sweep_parameter(base_project, "emission_rate", 1.0)


# ---------------------------------------------------------------------------
# BatchRunner.parameter_sweep
# ---------------------------------------------------------------------------

class TestParameterSweep:
    def test_writes_one_inp_per_value(self, base_project, fake_aermod_exe, tmp_path):
        runner = AERMODRunner(executable_path=fake_aermod_exe,
                              working_dir=tmp_path)
        batch = BatchRunner(runner)
        # run_batch will spawn subprocesses for each file; use 1 worker
        # so we don't fight the fake-exe over temp dirs.
        results = batch.parameter_sweep(
            base_project,
            parameter_name="emission_rate",
            parameter_values=[0.5, 1.0, 2.0],
            output_dir=tmp_path / "sweep",
            n_workers=1,
        )
        # One .inp file per value
        inps = sorted((tmp_path / "sweep").glob("*.inp"))
        assert len(inps) == 3
        # Result map keyed by parameter values
        assert set(results.keys()) == {0.5, 1.0, 2.0}

    def test_each_inp_has_correct_emission_rate(
        self, base_project, fake_aermod_exe, tmp_path,
    ):
        runner = AERMODRunner(executable_path=fake_aermod_exe,
                              working_dir=tmp_path)
        batch = BatchRunner(runner)
        batch.parameter_sweep(
            base_project,
            parameter_name="emission_rate",
            parameter_values=[0.5, 2.5],
            output_dir=tmp_path / "sweep",
            n_workers=1,
        )
        # Parse each generated .inp and check the SRCPARAM value
        half = (tmp_path / "sweep" / "run_emission_rate_0.5.inp").read_text()
        two_five = (tmp_path / "sweep" / "run_emission_rate_2.5.inp").read_text()
        # Emission rate appears as the first numeric on SRCPARAM line
        assert "0.500000" in half
        assert "2.500000" in two_five

    def test_dotted_path_sweep(self, base_project, fake_aermod_exe, tmp_path):
        runner = AERMODRunner(executable_path=fake_aermod_exe,
                              working_dir=tmp_path)
        batch = BatchRunner(runner)
        batch.parameter_sweep(
            base_project,
            parameter_name="control.title_one",
            parameter_values=["Case A", "Case B"],
            output_dir=tmp_path / "sweep",
            n_workers=1,
        )
        # Filename sanitizer replaces the space
        files = sorted((tmp_path / "sweep").glob("*.inp"))
        assert len(files) == 2
        names = [f.name for f in files]
        assert any("Case_A" in n for n in names)
        assert any("Case_B" in n for n in names)

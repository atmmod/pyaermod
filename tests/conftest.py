"""Shared test fixtures for the pyaermod test suite."""

import platform

import numpy as np
import pandas as pd
import pytest

from pyaermod.input_generator import (
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    VolumeSource,
)


@pytest.fixture
def valid_point_source():
    """A minimal valid PointSource."""
    return PointSource(
        source_id="STK1",
        x_coord=500.0,
        y_coord=500.0,
        stack_height=30.0,
        stack_diameter=1.5,
        stack_temp=400.0,
        exit_velocity=10.0,
        emission_rate=1.0,
    )


@pytest.fixture
def valid_area_source():
    """A minimal valid AreaSource."""
    return AreaSource(
        source_id="AREA1",
        x_coord=0.0,
        y_coord=0.0,
        emission_rate=0.5,
        initial_lateral_dimension=100.0,
        initial_vertical_dimension=100.0,
        release_height=3.0,
    )


@pytest.fixture
def valid_volume_source():
    """A minimal valid VolumeSource."""
    return VolumeSource(
        source_id="VOL1",
        x_coord=100.0,
        y_coord=100.0,
        emission_rate=0.3,
        release_height=5.0,
        initial_lateral_dimension=10.0,
        initial_vertical_dimension=5.0,
    )


@pytest.fixture
def valid_project(valid_point_source):
    """A minimal valid AERMODProject with one point source."""
    sources = SourcePathway()
    sources.add_source(valid_point_source)
    return AERMODProject(
        control=ControlPathway(
            title_one="Test Project",
            pollutant_id=PollutantType.PM25,
        ),
        sources=sources,
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(
            surface_file="test.sfc",
            profile_file="test.pfl",
        ),
        output=OutputPathway(),
    )


@pytest.fixture
def sample_concentration_df():
    """A 21x21 grid of synthetic concentration data."""
    xs = np.linspace(-500, 500, 21)
    ys = np.linspace(-500, 500, 21)
    X, Y = np.meshgrid(xs, ys)
    dist = np.sqrt(X**2 + Y**2) + 1
    conc = 10.0 / dist * 100
    return pd.DataFrame({
        "x": X.flatten(),
        "y": Y.flatten(),
        "concentration": conc.flatten(),
    })


@pytest.fixture
def fake_aermod_exe(tmp_path):
    """Create a fake AERMOD executable that exits successfully."""
    if platform.system() == "Windows":
        exe = tmp_path / "aermod.bat"
        exe.write_text("@echo off\nexit /b 0\n")
    else:
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        exe.chmod(0o755)
    return exe

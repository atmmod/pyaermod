"""Property-based tests using Hypothesis for pyaermod."""

import dataclasses

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyaermod.input_generator import (
    AERMODProject,
    AreaSource,
    BackgroundConcentration,
    CartesianGrid,
    ControlPathway,
    GasDepositionParams,
    MeteorologyPathway,
    OutputPathway,
    ParticleDepositionParams,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    VolumeSource,
)
from pyaermod.validator import Validator

# --- Strategies ---
source_ids = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=8,
)
coords = st.floats(
    min_value=-1e7, max_value=1e7, allow_nan=False, allow_infinity=False
)
positive_floats = st.floats(
    min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False
)
nonneg_floats = st.floats(
    min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False
)


@st.composite
def point_sources(draw):
    return PointSource(
        source_id=draw(source_ids),
        x_coord=draw(coords),
        y_coord=draw(coords),
        stack_height=draw(positive_floats),
        stack_temp=draw(positive_floats),
        exit_velocity=draw(nonneg_floats),
        stack_diameter=draw(positive_floats),
        emission_rate=draw(nonneg_floats),
    )


@st.composite
def area_sources(draw):
    return AreaSource(
        source_id=draw(source_ids),
        x_coord=draw(coords),
        y_coord=draw(coords),
        emission_rate=draw(nonneg_floats),
        initial_lateral_dimension=draw(positive_floats),
        initial_vertical_dimension=draw(positive_floats),
        release_height=draw(nonneg_floats),
    )


@st.composite
def volume_sources(draw):
    return VolumeSource(
        source_id=draw(source_ids),
        x_coord=draw(coords),
        y_coord=draw(coords),
        emission_rate=draw(nonneg_floats),
        release_height=draw(positive_floats),
        initial_lateral_dimension=draw(positive_floats),
        initial_vertical_dimension=draw(positive_floats),
    )


# --- Tests ---


@pytest.mark.slow
class TestPropertyBased:
    """Property-based tests using Hypothesis."""

    @given(source=point_sources())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_point_source_to_aermod_never_crashes(self, source):
        """to_aermod_input() should never raise for any valid-typed inputs."""
        output = source.to_aermod_input()
        assert isinstance(output, str)
        assert len(output) > 0

    @given(source=area_sources())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_area_source_to_aermod_never_crashes(self, source):
        output = source.to_aermod_input()
        assert isinstance(output, str)
        assert len(output) > 0

    @given(source=volume_sources())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_volume_source_to_aermod_never_crashes(self, source):
        output = source.to_aermod_input()
        assert isinstance(output, str)
        assert len(output) > 0

    @given(source=point_sources())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_point_source_contains_keywords(self, source):
        output = source.to_aermod_input()
        assert "LOCATION" in output
        assert "SRCPARAM" in output
        assert source.source_id in output

    @given(
        stack_height=st.floats(
            min_value=-1e6,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_validator_catches_negative_stack_height(self, stack_height):
        source = PointSource(
            source_id="S1",
            x_coord=0.0,
            y_coord=0.0,
            stack_height=stack_height,
            stack_diameter=1.5,
            stack_temp=400.0,
            exit_velocity=10.0,
            emission_rate=1.0,
        )
        sources = SourcePathway()
        sources.add_source(source)
        project = AERMODProject(
            control=ControlPathway(
                title_one="T", pollutant_id=PollutantType.PM25
            ),
            sources=sources,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(
                surface_file="t.sfc", profile_file="t.pfl"
            ),
            output=OutputPathway(),
        )
        result = Validator.validate(project)
        if stack_height <= 0:
            assert not result.is_valid

    @given(
        emission_rate=st.floats(
            min_value=-1e6,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_validator_catches_negative_emission(self, emission_rate):
        source = PointSource(
            source_id="S1",
            x_coord=0.0,
            y_coord=0.0,
            stack_height=50.0,
            stack_diameter=1.5,
            stack_temp=400.0,
            exit_velocity=10.0,
            emission_rate=emission_rate,
        )
        sources = SourcePathway()
        sources.add_source(source)
        project = AERMODProject(
            control=ControlPathway(
                title_one="T", pollutant_id=PollutantType.PM25
            ),
            sources=sources,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(
                surface_file="t.sfc", profile_file="t.pfl"
            ),
            output=OutputPathway(),
        )
        result = Validator.validate(project)
        if emission_rate < 0:
            assert not result.is_valid

    @given(
        value=st.floats(
            min_value=0.001,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_background_uniform_roundtrip(self, value):
        bg = BackgroundConcentration(uniform_value=value)
        output = bg.to_aermod_input()
        assert "BACKGRND" in output

    @given(
        n=st.integers(min_value=1, max_value=10),
        data=st.data(),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_particle_dep_to_aermod_never_crashes(self, n, data):
        diameters = [
            data.draw(
                st.floats(
                    min_value=0.1,
                    max_value=100.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            for _ in range(n)
        ]
        densities = [
            data.draw(
                st.floats(
                    min_value=0.1,
                    max_value=10.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            for _ in range(n)
        ]
        # Make fractions sum to 1.0
        raw = [
            data.draw(
                st.floats(
                    min_value=0.01,
                    max_value=1.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            for _ in range(n)
        ]
        total = sum(raw)
        fractions = [r / total for r in raw]
        params = ParticleDepositionParams(
            diameters=diameters, mass_fractions=fractions, densities=densities
        )
        source = PointSource(
            source_id="S1",
            x_coord=0.0,
            y_coord=0.0,
            stack_height=50.0,
            stack_diameter=1.5,
            stack_temp=400.0,
            exit_velocity=10.0,
            emission_rate=1.0,
            particle_deposition=params,
        )
        output = source.to_aermod_input()
        assert "PARTDIAM" in output
        assert "MASSFRAX" in output
        assert "PARTDENS" in output

    @given(source=point_sources())
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_gas_dep_to_aermod_never_crashes(self, source):
        gas_dep = GasDepositionParams(
            diffusivity=0.15,
            alpha_r=2.0,
            reactivity=0.5,
            henry_constant=0.01,
        )
        # Create a new source with gas deposition
        source_with_dep = dataclasses.replace(source, gas_deposition=gas_dep)
        output = source_with_dep.to_aermod_input()
        assert "GASDEPOS" in output

    @given(
        x_init=st.floats(
            min_value=-1000,
            max_value=1000,
            allow_nan=False,
            allow_infinity=False,
        ),
        y_init=st.floats(
            min_value=-1000,
            max_value=1000,
            allow_nan=False,
            allow_infinity=False,
        ),
        x_num=st.integers(min_value=1, max_value=50),
        y_num=st.integers(min_value=1, max_value=50),
        x_delta=st.floats(
            min_value=1.0,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        y_delta=st.floats(
            min_value=1.0,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_cartesian_grid_to_aermod_never_crashes(
        self, x_init, y_init, x_num, y_num, x_delta, y_delta
    ):
        grid = CartesianGrid(
            x_init=x_init,
            y_init=y_init,
            x_num=x_num,
            y_num=y_num,
            x_delta=x_delta,
            y_delta=y_delta,
        )
        output = grid.to_aermod_input()
        assert isinstance(output, str)
        assert "GRIDCART" in output

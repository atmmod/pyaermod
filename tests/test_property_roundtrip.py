"""
Property-based round-trip tests for the .inp reader / writer.

Complements tests/test_property_based.py (which generates projects +
exercises the validator). Here we verify the fundamental contract:

    project -> project.to_aermod_input() -> parse_aermod_input() == project

for the subset of features the v1 reader supports. When hypothesis
finds a project where round-trip silently drops information, it
prints a minimal failing case — a much better bug report than
hand-written regression tests.

Scope (supported by v1 reader):
- PointSource, AreaSource, VolumeSource (SRCPARAM fields)
- 36-sector BUILDHGT arrays on PointSource
- ControlPathway: title, pollutant, averaging_periods, terrain_type,
  regulatory_default, flag_pole_height, urban_option
- ReceptorPathway: CartesianGrid, DiscreteReceptor
- MeteorologyPathway: files, station IDs, year, profile base, date range
- OutputPathway: RECTABLE, MAXTABLE, SUMMFILE, PLOTFILE, POSTFILE

Out of scope:
- LINE/RLINE/RLINEXT/BUOYLINE/OPENPIT/AREACIRC/AREAPOLY (reader skips
  advanced source types; those tests live in test_input_reader.py)
- Chemistry sub-blocks (reader drops)
- Deposition sub-blocks (reader drops)
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pyaermod.input_generator import (
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
    VolumeSource,
)
from pyaermod.input_reader import parse_aermod_input

# ---------------------------------------------------------------------------
# Strategies: narrower than test_property_based.py (we need values that
# round-trip cleanly through the text format)
# ---------------------------------------------------------------------------

source_ids = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=8,
)


# Bounded floats; the .inp format uses fixed-width fields, so very
# small / very large magnitudes lose precision across round-trip.
def bounded_float(lo: float, hi: float) -> st.SearchStrategy[float]:
    return st.floats(
        min_value=lo, max_value=hi,
        allow_nan=False, allow_infinity=False,
    ).filter(lambda v: abs(v) < 1e8)


coord = bounded_float(-99_999.0, 99_999.0)
stack_h = bounded_float(1.0, 500.0)
stack_d = bounded_float(0.1, 10.0)
stack_t = bounded_float(250.0, 800.0)
exit_v = bounded_float(0.1, 100.0)
emission = bounded_float(0.001, 1000.0)


@st.composite
def point_sources(draw, sid_strategy=source_ids):
    sid = draw(sid_strategy)
    return PointSource(
        source_id=sid,
        x_coord=draw(coord), y_coord=draw(coord),
        stack_height=draw(stack_h),
        stack_temp=draw(stack_t),
        exit_velocity=draw(exit_v),
        stack_diameter=draw(stack_d),
        emission_rate=draw(emission),
    )


@st.composite
def area_sources(draw, sid_strategy=source_ids):
    sid = draw(sid_strategy)
    return AreaSource(
        source_id=sid,
        x_coord=draw(coord), y_coord=draw(coord),
        emission_rate=draw(emission),
        release_height=draw(bounded_float(0.0, 100.0)),
        initial_lateral_dimension=draw(bounded_float(1.0, 1000.0)),
        initial_vertical_dimension=draw(bounded_float(1.0, 1000.0)),
    )


@st.composite
def volume_sources(draw, sid_strategy=source_ids):
    sid = draw(sid_strategy)
    return VolumeSource(
        source_id=sid,
        x_coord=draw(coord), y_coord=draw(coord),
        emission_rate=draw(emission),
        release_height=draw(bounded_float(0.0, 100.0)),
        initial_lateral_dimension=draw(bounded_float(0.1, 100.0)),
        initial_vertical_dimension=draw(bounded_float(0.1, 100.0)),
    )


@st.composite
def control_pathways(draw):
    return ControlPathway(
        title_one=draw(st.text(min_size=1, max_size=40,
                               alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")))),
        pollutant_id=draw(st.sampled_from([
            PollutantType.SO2, PollutantType.NO2,
            PollutantType.PM25, PollutantType.PM10, PollutantType.CO,
        ])),
        averaging_periods=draw(st.lists(
            st.sampled_from(["1", "3", "8", "24", "ANNUAL", "PERIOD"]),
            min_size=1, max_size=4, unique=True,
        )),
        terrain_type=draw(st.sampled_from([TerrainType.FLAT, TerrainType.ELEVATED])),
        regulatory_default=draw(st.booleans()),
    )


@st.composite
def cartesian_grids(draw):
    return CartesianGrid(
        grid_name=draw(st.text(min_size=1, max_size=8,
                               alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))),
        x_init=draw(bounded_float(-10000.0, 10000.0)),
        x_num=draw(st.integers(min_value=2, max_value=50)),
        x_delta=draw(bounded_float(1.0, 1000.0)),
        y_init=draw(bounded_float(-10000.0, 10000.0)),
        y_num=draw(st.integers(min_value=2, max_value=50)),
        y_delta=draw(bounded_float(1.0, 1000.0)),
    )


@st.composite
def projects_point_source(draw):
    """A minimal AERMODProject with one point source and one grid."""
    ctrl = draw(control_pathways())
    src = draw(point_sources())
    grid = draw(cartesian_grids())
    return AERMODProject(
        control=ctrl,
        sources=SourcePathway(sources=[src]),
        receptors=ReceptorPathway(cartesian_grids=[grid]),
        meteorology=MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
        ),
        output=OutputPathway(),
    )


# ---------------------------------------------------------------------------
# Round-trip properties
# ---------------------------------------------------------------------------

# Hypothesis slow-test marker lets us skip these in fast-CI modes
# (they're also deselected by default via the existing `--deselect`
# on the full suite). We use fewer examples + generous health-check
# relaxation since construction of a full AERMODProject is heavy.
_SETTINGS = settings(
    max_examples=25,
    deadline=1500,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@pytest.mark.slow
@_SETTINGS
@given(projects_point_source())
def test_point_source_project_roundtrip(project):
    """Writing then re-reading a point-source project preserves core fields."""
    inp_text = project.to_aermod_input()
    parsed = parse_aermod_input(inp_text)

    # Title + pollutant preserved
    assert parsed.control.title_one == project.control.title_one
    # PollutantType comparison: either direct or string match
    orig_poll = (
        project.control.pollutant_id.value
        if hasattr(project.control.pollutant_id, "value")
        else project.control.pollutant_id
    )
    got_poll = (
        parsed.control.pollutant_id.value
        if hasattr(parsed.control.pollutant_id, "value")
        else parsed.control.pollutant_id
    )
    assert got_poll == orig_poll

    # Averaging periods preserved as a set (order may differ due to writer)
    assert set(parsed.control.averaging_periods) == set(project.control.averaging_periods)

    # Source preserved: same id, coords, stack geometry
    assert len(parsed.sources.sources) == 1
    src_in = project.sources.sources[0]
    src_out = parsed.sources.sources[0]
    assert src_out.source_id == src_in.source_id
    assert src_out.x_coord == pytest.approx(src_in.x_coord, rel=0.001, abs=0.01)
    assert src_out.y_coord == pytest.approx(src_in.y_coord, rel=0.001, abs=0.01)
    assert src_out.stack_height == pytest.approx(src_in.stack_height, rel=0.01)
    assert src_out.emission_rate == pytest.approx(src_in.emission_rate, rel=0.01)


@pytest.mark.slow
@_SETTINGS
@given(
    control_pathways(),
    st.lists(point_sources(), min_size=1, max_size=5, unique_by=lambda s: s.source_id),
)
def test_multi_source_roundtrip_preserves_count(ctrl, sources):
    """Multi-source project round-trips with correct source count."""
    # Uniqueness is enforced by `unique_by`; assume guards against
    # downstream surprises from empty or duplicate strategies.
    assume(len(sources) == len({s.source_id for s in sources}))

    project = AERMODProject(
        control=ctrl,
        sources=SourcePathway(sources=sources),
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(x_init=0, x_num=3, x_delta=100,
                          y_init=0, y_num=3, y_delta=100),
        ]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )
    parsed = parse_aermod_input(project.to_aermod_input())
    assert len(parsed.sources.sources) == len(sources)
    assert {s.source_id for s in parsed.sources.sources} == {s.source_id for s in sources}


@pytest.mark.slow
@_SETTINGS
@given(area_sources())
def test_area_source_roundtrip(area):
    project = AERMODProject(
        control=ControlPathway(title_one="t", pollutant_id=PollutantType.PM25,
                               averaging_periods=["ANNUAL"]),
        sources=SourcePathway(sources=[area]),
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(x_init=0, x_num=2, x_delta=100, y_init=0, y_num=2, y_delta=100),
        ]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )
    parsed = parse_aermod_input(project.to_aermod_input())
    src_out = parsed.sources.sources[0]
    assert isinstance(src_out, AreaSource)
    assert src_out.source_id == area.source_id
    assert src_out.emission_rate == pytest.approx(area.emission_rate, rel=0.01)
    assert src_out.release_height == pytest.approx(area.release_height, abs=0.1)


@pytest.mark.slow
@_SETTINGS
@given(
    point_sources(),
    st.lists(bounded_float(0.0, 200.0), min_size=36, max_size=36),
)
def test_building_height_array_roundtrip(src, heights):
    """36-sector BUILDHGT values survive the writer->reader cycle."""
    src.building_height = list(heights)
    project = AERMODProject(
        control=ControlPathway(title_one="t", pollutant_id=PollutantType.SO2,
                               averaging_periods=["ANNUAL"]),
        sources=SourcePathway(sources=[src]),
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(x_init=0, x_num=2, x_delta=100, y_init=0, y_num=2, y_delta=100),
        ]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )
    parsed = parse_aermod_input(project.to_aermod_input())
    got = parsed.sources.sources[0].building_height
    assert isinstance(got, list) and len(got) == 36
    for v_in, v_out in zip(heights, got):
        assert v_out == pytest.approx(v_in, abs=0.1)


@pytest.mark.slow
@_SETTINGS
@given(cartesian_grids())
def test_cartesian_grid_roundtrip(grid):
    project = AERMODProject(
        control=ControlPathway(title_one="t", pollutant_id=PollutantType.SO2,
                               averaging_periods=["ANNUAL"]),
        sources=SourcePathway(sources=[
            PointSource(source_id="S1", x_coord=0, y_coord=0,
                        stack_height=30, stack_temp=400, exit_velocity=10,
                        stack_diameter=2, emission_rate=1),
        ]),
        receptors=ReceptorPathway(cartesian_grids=[grid]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )
    parsed = parse_aermod_input(project.to_aermod_input())
    g = parsed.receptors.cartesian_grids[0]
    assert g.grid_name == grid.grid_name
    assert g.x_num == grid.x_num and g.y_num == grid.y_num
    assert g.x_init == pytest.approx(grid.x_init, rel=0.001, abs=0.01)
    assert g.x_delta == pytest.approx(grid.x_delta, rel=0.001)


@pytest.mark.slow
@_SETTINGS
@given(
    st.lists(
        st.tuples(coord, coord),
        min_size=1, max_size=10, unique=True,
    ),
)
def test_discrete_receptors_roundtrip(xys):
    receptors = [DiscreteReceptor(x_coord=x, y_coord=y) for x, y in xys]
    project = AERMODProject(
        control=ControlPathway(title_one="t", pollutant_id=PollutantType.SO2,
                               averaging_periods=["ANNUAL"]),
        sources=SourcePathway(sources=[
            PointSource(source_id="S1", x_coord=0, y_coord=0,
                        stack_height=30, stack_temp=400, exit_velocity=10,
                        stack_diameter=2, emission_rate=1),
        ]),
        receptors=ReceptorPathway(discrete_receptors=receptors),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )
    parsed = parse_aermod_input(project.to_aermod_input())
    assert len(parsed.receptors.discrete_receptors) == len(receptors)

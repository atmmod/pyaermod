"""Property-based round-trip over every source type and every pathway.

``tests/test_property_roundtrip.py`` covers point, area and volume
sources -- the three the reader supported when it was written. This
module covers all ten, plus the pathway fields, and exists because the
gap was invisible: a deck containing an AREAPOLY, RLINEXT or BUOYLINE
parsed *successfully* and came back with zero sources. No error, no
warning, just a project quietly missing its emissions.

The property under test is the same one for every type::

    source -> project.to_aermod_input() -> parse_aermod_input()
           -> a source of the same type with the same defining values

Values are drawn inside the ranges the fixed-width ``.inp`` fields can
represent; anything wider is a formatting question, not a round-trip
one, and belongs in the writer's own tests.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyaermod.input_generator import (
    AERMODProject,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.sources import (
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    LineSource,
    OpenPitSource,
    PointSource,
    RLineExtSource,
    RLineSource,
    VolumeSource,
)

_SETTINGS = settings(
    max_examples=30,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


def num(lo: float, hi: float) -> st.SearchStrategy[float]:
    """Values that survive the .inp fixed-width fields (2 decimals)."""
    return st.integers(
        min_value=int(lo * 100), max_value=int(hi * 100)
    ).map(lambda v: v / 100.0)


coord = num(-99_999.0, 99_999.0)
positive = num(0.1, 500.0)
emission = num(0.01, 1000.0)

source_ids = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
    min_size=1, max_size=8,
)


@st.composite
def line_endpoints(draw):
    """Two distinct endpoints.

    A zero-length line is rejected by the validator before it can be
    written, so generating one tests the validator, not the round trip.
    """
    x1, y1 = draw(coord), draw(coord)
    dx, dy = draw(num(1.0, 5000.0)), draw(num(0.0, 5000.0))
    return x1, y1, x1 + dx, y1 + dy


def roundtrip(source):
    """Write a one-source project and read it back."""
    project = AERMODProject(
        control=ControlPathway(title_one="property"),
        sources=SourcePathway(sources=[source]),
        receptors=ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(500.0, 500.0)]
        ),
        meteorology=MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
            surface_station_id=1, upper_air_station_id=2,
            data_start_year=2020,
        ),
        output=OutputPathway(),
    )
    parsed = parse_aermod_input(project.to_aermod_input())
    got = parsed.sources.sources
    assert len(got) == 1, (
        f"{type(source).__name__} round-tripped to {len(got)} sources, not 1"
        f"\n{project.to_aermod_input()}"
    )
    assert type(got[0]) is type(source), (
        f"{type(source).__name__} came back as {type(got[0]).__name__}"
    )
    return got[0]


def close(a: float, b: float, tol: float = 0.011) -> bool:
    return abs(a - b) <= tol


# ---------------------------------------------------------------------
# One property per source type
# ---------------------------------------------------------------------

@pytest.mark.slow
@_SETTINGS
@given(source_ids, coord, coord, positive, num(0.1, 10.0),
       num(250.0, 800.0), num(0.1, 100.0), emission)
def test_point(sid, x, y, height, diameter, temp, velocity, rate):
    src = PointSource(sid, x, y, stack_height=height, stack_diameter=diameter,
                      stack_temp=temp, exit_velocity=velocity,
                      emission_rate=rate)
    got = roundtrip(src)
    assert close(got.x_coord, x) and close(got.y_coord, y)
    assert close(got.stack_height, height)
    assert close(got.stack_diameter, diameter)
    assert close(got.stack_temp, temp)
    assert close(got.exit_velocity, velocity)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, coord, coord, num(0.0, 100.0), positive, positive, emission)
def test_area(sid, x, y, height, xinit, yinit, rate):
    src = AreaSource(sid, x, y, release_height=height,
                     initial_lateral_dimension=xinit,
                     initial_vertical_dimension=yinit, emission_rate=rate)
    got = roundtrip(src)
    assert close(got.x_coord, x) and close(got.y_coord, y)
    assert close(got.release_height, height)
    assert close(got.initial_lateral_dimension, xinit)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, coord, coord, num(0.0, 100.0), positive,
       st.integers(min_value=3, max_value=50), emission)
def test_areacirc(sid, x, y, height, radius, nverts, rate):
    src = AreaCircSource(sid, x, y, release_height=height, radius=radius,
                         num_vertices=nverts, emission_rate=rate)
    got = roundtrip(src)
    assert close(got.radius, radius)
    assert got.num_vertices == nverts


@pytest.mark.slow
@_SETTINGS
@given(source_ids,
       st.lists(st.tuples(coord, coord), min_size=3, max_size=8, unique=True),
       num(0.0, 100.0), emission)
def test_areapoly(sid, vertices, height, rate):
    src = AreaPolySource(sid, vertices=vertices, release_height=height,
                         emission_rate=rate)
    got = roundtrip(src)
    assert len(got.vertices) == len(vertices)
    for (gx, gy), (x, y) in zip(got.vertices, vertices):
        assert close(gx, x) and close(gy, y)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, coord, coord, num(0.0, 100.0), positive, positive, emission)
def test_volume(sid, x, y, height, sy, sz, rate):
    src = VolumeSource(sid, x, y, release_height=height,
                       initial_lateral_dimension=sy,
                       initial_vertical_dimension=sz, emission_rate=rate)
    got = roundtrip(src)
    assert close(got.initial_lateral_dimension, sy)
    assert close(got.initial_vertical_dimension, sz)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, line_endpoints(), num(0.0, 50.0), positive, emission)
def test_line(sid, endpoints, height, width, rate):
    x1, y1, x2, y2 = endpoints
    src = LineSource(sid, x1, y1, x2, y2, release_height=height,
                     initial_lateral_dimension=width, emission_rate=rate)
    got = roundtrip(src)
    assert close(got.x_start, x1) and close(got.y_start, y1)
    assert close(got.x_end, x2) and close(got.y_end, y2)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, line_endpoints(), num(0.0, 50.0), positive, positive,
       emission)
def test_rline(sid, endpoints, height, sy, sz, rate):
    x1, y1, x2, y2 = endpoints
    src = RLineSource(sid, x1, y1, x2, y2, release_height=height,
                      initial_lateral_dimension=sy,
                      initial_vertical_dimension=sz, emission_rate=rate)
    got = roundtrip(src)
    assert close(got.x_end, x2) and close(got.y_end, y2)
    assert close(got.release_height, height)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, line_endpoints(), num(0.0, 50.0), num(0.0, 50.0),
       positive, emission)
def test_rlinext(sid, endpoints, z1, z2, width, rate):
    x1, y1, x2, y2 = endpoints
    src = RLineExtSource(sid, x1, y1, z1, x2, y2, z2,
                         road_width=width, emission_rate=rate)
    got = roundtrip(src)
    assert close(got.x_start, x1) and close(got.y_start, y1)
    assert close(got.z_start, z1) and close(got.z_end, z2)
    assert close(got.road_width, width)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, positive, positive, positive, positive, positive, positive,
       st.lists(st.tuples(source_ids, line_endpoints(), emission),
                min_size=1, max_size=3, unique_by=lambda t: t[0]))
def test_buoyline(sid, llen, bhgt, bwid, lwid, bsep, buoy, segments):
    src = BuoyLineSource(
        sid, llen, bhgt, bwid, lwid, bsep, buoy,
        line_segments=[
            BuoyLineSegment(seg_id, *endpoints, emission_rate=rate)
            for seg_id, endpoints, rate in segments
        ],
    )
    got = roundtrip(src)
    assert close(got.avg_line_length, llen)
    assert close(got.avg_buoyancy_parameter, buoy, tol=0.02)
    assert len(got.line_segments) == len(segments)


@pytest.mark.slow
@_SETTINGS
@given(source_ids, coord, coord, positive, positive, num(1.0, 1e5), emission)
def test_openpit(sid, x, y, xdim, ydim, volume, rate):
    src = OpenPitSource(sid, x, y, release_height=0.0, x_dimension=xdim,
                        y_dimension=ydim, pit_volume=volume,
                        emission_rate=rate)
    got = roundtrip(src)
    assert close(got.x_dimension, xdim) and close(got.y_dimension, ydim)
    assert close(got.pit_volume, volume)


# ---------------------------------------------------------------------
# Coverage guard
# ---------------------------------------------------------------------

def test_every_source_type_has_a_property():
    """Fail when pyaermod grows a source type this module does not cover."""
    import pyaermod.sources as sources_module

    exported = {
        name for name in dir(sources_module)
        if name.endswith("Source") and not name.startswith("_")
    }
    covered = {
        "PointSource", "AreaSource", "AreaCircSource", "AreaPolySource",
        "VolumeSource", "LineSource", "RLineSource", "RLineExtSource",
        "BuoyLineSource", "OpenPitSource",
    }
    assert exported == covered, (
        f"uncovered source types: {sorted(exported - covered)}; "
        f"stale entries: {sorted(covered - exported)}"
    )


def test_reader_does_not_silently_drop_sources():
    """The regression that motivated this module, pinned directly.

    Each of these parsed without error and produced an empty source
    list, so a project could lose its emissions with nothing to show
    for it.
    """
    for src in (
        AreaPolySource("P1", vertices=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
                       release_height=5.0, emission_rate=1e-4),
        RLineExtSource("R1", 0.0, 0.0, 1.0, 100.0, 50.0, 2.0,
                       emission_rate=0.5, road_width=10.0),
        BuoyLineSource("B1", 100.0, 10.0, 8.0, 5.0, 12.0, 30.0,
                       line_segments=[BuoyLineSegment(
                           "S1", 0.0, 0.0, 100.0, 50.0, emission_rate=1.0)]),
    ):
        assert roundtrip(src) is not None

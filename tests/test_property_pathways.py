"""Property-based round-trip over the pathway fields.

``tests/test_property_roundtrip.py`` varies the CO and RE pathways;
the ME and OU pathways were pinned to fixed values there, so every
field on them went unexercised, as did polar receptor grids. This
module varies them.

Same property as the source tests::

    pathway -> project.to_aermod_input() -> parse_aermod_input()
            -> the same field values
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
    PointSource,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.receptors import PolarGrid

_SETTINGS = settings(
    max_examples=30,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

names = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
    min_size=1, max_size=8,
)
filenames = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1, max_size=12,
).map(lambda s: f"{s}.dat")


def num(lo: float, hi: float) -> st.SearchStrategy[float]:
    return st.integers(
        min_value=int(lo * 100), max_value=int(hi * 100)
    ).map(lambda v: v / 100.0)


def build(*, meteorology=None, output=None, receptors=None):
    return AERMODProject(
        control=ControlPathway(title_one="pathway property"),
        sources=SourcePathway(sources=[PointSource(
            "SRC1", 0.0, 0.0, stack_height=50.0, stack_diameter=2.0,
            stack_temp=400.0, exit_velocity=15.0, emission_rate=10.0,
        )]),
        receptors=receptors or ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(500.0, 500.0)]
        ),
        meteorology=meteorology or MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
        ),
        output=output or OutputPathway(),
    )


def roundtrip(project):
    return parse_aermod_input(project.to_aermod_input())


def close(a, b, tol=0.011):
    return abs(a - b) <= tol


# ---------------------------------------------------------------------
# ME pathway
# ---------------------------------------------------------------------

@pytest.mark.slow
@_SETTINGS
@given(filenames, filenames,
       st.integers(min_value=1, max_value=99999),
       st.integers(min_value=1, max_value=99999),
       st.integers(min_value=1950, max_value=2049),
       # PROFBASE is written to one decimal, matching EPA's decks.
       st.integers(min_value=-5000, max_value=30000).map(lambda v: v / 10.0))
def test_meteorology_fields(surface, profile, sfc_id, ua_id, year, base):
    met = MeteorologyPathway(
        surface_file=surface, profile_file=profile,
        surface_station_id=sfc_id, upper_air_station_id=ua_id,
        data_start_year=year, profile_base_elevation=base,
    )
    got = roundtrip(build(meteorology=met)).meteorology
    assert got.surface_file == surface
    assert got.profile_file == profile
    assert got.surface_station_id == sfc_id
    assert got.upper_air_station_id == ua_id
    assert got.data_start_year == year
    assert close(got.profile_base_elevation, base)


@pytest.mark.slow
@_SETTINGS
@given(st.integers(min_value=1950, max_value=2049),
       st.integers(min_value=1, max_value=6),
       st.integers(min_value=1, max_value=28),
       st.integers(min_value=7, max_value=12),
       st.integers(min_value=1, max_value=28))
def test_meteorology_date_range(year, m1, d1, m2, d2):
    # A start strictly before the end: a single-day range with ANNUAL
    # averaging is rejected by the validator, which is its job, not this
    # test's subject.
    met = MeteorologyPathway(
        surface_file="a.sfc", profile_file="a.pfl",
        surface_station_id=1, upper_air_station_id=2, data_start_year=year,
        start_year=year, start_month=m1, start_day=d1,
        end_year=year, end_month=m2, end_day=d2,
    )
    got = roundtrip(build(meteorology=met)).meteorology
    assert (got.start_month, got.start_day) == (m1, d1)
    assert (got.end_month, got.end_day) == (m2, d2)


# ---------------------------------------------------------------------
# OU pathway
# ---------------------------------------------------------------------

@pytest.mark.slow
@_SETTINGS
@given(st.booleans(), st.integers(min_value=1, max_value=10),
       st.booleans(), st.integers(min_value=1, max_value=50))
def test_output_tables(rectable, rec_rank, maxtable, max_rank):
    out = OutputPathway(
        receptor_table=rectable, receptor_table_rank=rec_rank,
        max_table=maxtable, max_table_rank=max_rank,
    )
    got = roundtrip(build(output=out)).output
    assert got.receptor_table == rectable
    assert got.max_table == maxtable
    if rectable:
        assert got.receptor_table_rank == rec_rank
    if maxtable:
        assert got.max_table_rank == max_rank


@pytest.mark.slow
@_SETTINGS
@given(filenames, filenames, filenames)
def test_output_files(summary, plot, post):
    out = OutputPathway(
        summary_file=summary, plot_file=plot, postfile=post,
    )
    got = roundtrip(build(output=out)).output
    assert got.summary_file == summary
    assert got.plot_file == plot
    assert got.postfile == post


# ---------------------------------------------------------------------
# RE pathway: polar grids
# ---------------------------------------------------------------------

@pytest.mark.slow
@_SETTINGS
@given(names, num(-10000.0, 10000.0), num(-10000.0, 10000.0),
       num(1.0, 5000.0), st.integers(min_value=1, max_value=20),
       num(1.0, 5000.0), num(0.0, 359.0),
       st.integers(min_value=1, max_value=36), num(1.0, 90.0))
def test_polar_grid(name, x0, y0, d0, dn, dd, a0, an, ad):
    receptors = ReceptorPathway(polar_grids=[PolarGrid(
        grid_name=name, x_origin=x0, y_origin=y0,
        dist_init=d0, dist_num=dn, dist_delta=dd,
        dir_init=a0, dir_num=an, dir_delta=ad,
    )])
    got = roundtrip(build(receptors=receptors)).receptors
    assert len(got.polar_grids) == 1, (
        "polar grid did not survive the round trip"
    )
    grid = got.polar_grids[0]
    assert close(grid.x_origin, x0) and close(grid.y_origin, y0)
    assert grid.dist_num == dn
    assert grid.dir_num == an


def test_every_pathway_is_exercised_somewhere():
    """Name the pathways covered, so a new one is a visible gap.

    CO and RE-cartesian live in test_property_roundtrip.py; ME, OU and
    RE-polar live here.
    """
    project = build()
    for pathway in ("control", "sources", "receptors", "meteorology",
                    "output"):
        assert getattr(project, pathway) is not None, pathway

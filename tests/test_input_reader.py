"""Tests for the AERMOD .inp file reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod import (
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
from pyaermod.input_reader import parse_aermod_input, read_aermod_input

FIXT = Path(__file__).parent / "fixtures" / "epa_style"


# ---------------------------------------------------------------------------
# Basic pathway parsing
# ---------------------------------------------------------------------------

class TestControlParsing:
    def test_minimal_project_parses(self):
        text = """\
CO STARTING
   TITLEONE  my title
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  1 ANNUAL
   POLLUTID  SO2
   RUNORNOT  RUN
CO FINISHED

SO STARTING
   LOCATION  S1   POINT        0.0       0.0     0.00
   SRCPARAM  S1     1.0    30.0   400.0    10.0     2.0
   SRCGROUP  ALL
SO FINISHED

RE STARTING
   GRIDCART  G  STA
                       XYINC       0.00     5   100.00       0.00     5   100.00
   GRIDCART  G  END
RE FINISHED

ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0  METERS
ME FINISHED

OU STARTING
OU FINISHED
"""
        project = parse_aermod_input(text)
        assert project.control.title_one == "my title"
        assert project.control.averaging_periods == ["1", "ANNUAL"]
        assert project.control.pollutant_id == PollutantType.SO2
        assert project.control.regulatory_default is True
        assert project.control.terrain_type == TerrainType.ELEVATED
        assert project.control.calculate_concentration is True

    def test_title_two_and_options(self):
        text = """\
CO STARTING
   TITLEONE  one
   TITLETWO  two
   MODELOPT  CONC FLAT
   AVERTIME  ANNUAL
   POLLUTID  NO2
   FLAGPOLE  1.5
   URBANOPT  CITY  1000000
   LOW_WIND  LOWWIND3
   HALFLIFE  4.0
CO FINISHED

SO STARTING
   LOCATION S1 POINT 0 0
   SRCPARAM S1 1 10 400 5 1
SO FINISHED

RE STARTING
   DISCCART  10.0 20.0 0.0
RE FINISHED

ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED

OU STARTING
OU FINISHED
"""
        p = parse_aermod_input(text)
        assert p.control.title_two == "two"
        assert p.control.terrain_type == TerrainType.FLAT
        assert p.control.flag_pole_height == 1.5
        assert p.control.urban_option == "CITY"
        assert p.control.urban_population == 1_000_000
        assert p.control.low_wind_option == "LOWWIND3"
        assert p.control.half_life == 4.0


class TestSourceParsing:
    def _with_sources(self, so_body: str) -> AERMODProject:
        return parse_aermod_input(f"""\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED

SO STARTING
{so_body}
SO FINISHED

RE STARTING
   DISCCART  0 0 0
RE FINISHED

ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED

OU STARTING
OU FINISHED
""")

    def test_point_source_roundtrip(self):
        p = self._with_sources(
            "   LOCATION  S1   POINT  100.0  200.0  10.0\n"
            "   SRCPARAM  S1  2.5  45.0  420.0  8.0  1.5"
        )
        assert len(p.sources.sources) == 1
        src = p.sources.sources[0]
        assert isinstance(src, PointSource)
        assert src.source_id == "S1"
        assert src.x_coord == 100.0 and src.y_coord == 200.0
        assert src.emission_rate == 2.5
        assert src.stack_height == 45.0

    def test_area_source(self):
        p = self._with_sources(
            "   LOCATION  A1   AREA   0.0  0.0  0.0\n"
            "   SRCPARAM  A1  0.01  3.0  50.0  50.0"
        )
        assert isinstance(p.sources.sources[0], AreaSource)
        assert p.sources.sources[0].emission_rate == 0.01

    def test_volume_source(self):
        p = self._with_sources(
            "   LOCATION  V1   VOLUME   0.0  0.0  0.0\n"
            "   SRCPARAM  V1  0.5  5.0  10.0  8.0"
        )
        assert isinstance(p.sources.sources[0], VolumeSource)

    def test_srcgroup_captured(self):
        p = self._with_sources(
            "   LOCATION S1 POINT 0 0\n"
            "   SRCPARAM S1 1 10 400 5 1\n"
            "   LOCATION S2 POINT 100 0\n"
            "   SRCPARAM S2 1 10 400 5 1\n"
            "   SRCGROUP ALL S1 S2\n"
            "   SRCGROUP GRP1 S1"
        )
        groups = p.sources.group_definitions
        # "SRCGROUP ALL" (bare) is auto-regenerated on write and not
        # captured as an explicit group definition.
        grp1 = next(g for g in groups if g.group_name == "GRP1")
        assert grp1.member_source_ids == ["S1"]


class TestReceptors:
    def _minimal_with_re(self, re_body):
        return parse_aermod_input(f"""\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION S1 POINT 0 0
   SRCPARAM S1 1 10 400 5 1
SO FINISHED
RE STARTING
{re_body}
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
OU FINISHED
""")

    def test_cartesian_grid(self):
        p = self._minimal_with_re(
            "   GRIDCART  G  STA\n"
            "                       XYINC  -1000.0   10   200.0   -500.0  5  100.0\n"
            "   GRIDCART  G  END"
        )
        grid = p.receptors.cartesian_grids[0]
        assert grid.grid_name == "G"
        assert grid.x_init == -1000.0
        assert grid.x_num == 10 and grid.y_num == 5

    def test_polar_grid(self):
        p = self._minimal_with_re(
            "   GRIDPOLR  P  STA\n"
            "   GRIDPOLR  P  ORIG  0.0  0.0\n"
            "   GRIDPOLR  P  DIST  100.0  10  100.0\n"
            "   GRIDPOLR  P  GDIR  0.0  36  10.0\n"
            "   GRIDPOLR  P  END"
        )
        g = p.receptors.polar_grids[0]
        assert g.dir_num == 36 and g.dist_num == 10

    def test_discrete_receptors(self):
        p = self._minimal_with_re(
            "   DISCCART  100.0  200.0  5.0\n"
            "   DISCCART  300.0  400.0  6.0  7.0  8.0"
        )
        recs = p.receptors.discrete_receptors
        assert len(recs) == 2
        assert recs[1].z_hill == 7.0 and recs[1].z_flag == 8.0


# ---------------------------------------------------------------------------
# Round-trip of the golden file
# ---------------------------------------------------------------------------

class TestGoldenFileRoundTrip:
    def test_golden_parses(self):
        project = read_aermod_input(FIXT / "simple_point.inp.expected")
        assert project.control.title_one == "Regression case: single SO2 point source"
        assert project.control.regulatory_default is True
        assert project.control.pollutant_id == PollutantType.SO2
        assert len(project.sources.sources) == 1
        src = project.sources.sources[0]
        assert src.source_id == "STACK1"
        assert src.emission_rate == pytest.approx(5.0)

    def test_golden_roundtrip_byte_identical(self, tmp_path):
        original = (FIXT / "simple_point.inp.expected").read_text()
        project = read_aermod_input(FIXT / "simple_point.inp.expected")
        out = tmp_path / "rt.inp"
        project.write(str(out))
        regenerated = out.read_text()
        assert regenerated == original, (
            "Round-trip not byte-identical. Diff suggests the reader "
            "dropped or normalized something the writer can't re-emit."
        )


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestErrors:
    def test_missing_required_pathway(self):
        with pytest.raises(ValueError, match="required pathway"):
            parse_aermod_input("CO STARTING\nCO FINISHED\n")

    def test_starting_without_finished(self):
        with pytest.raises(ValueError, match="STARTING without FINISHED"):
            parse_aermod_input("CO STARTING\n")

    def test_content_outside_pathway(self):
        with pytest.raises(ValueError, match="outside any pathway"):
            parse_aermod_input("TITLEONE stray line\nCO STARTING\nCO FINISHED\n")

    def test_comments_skipped(self):
        text = """\
** this is a comment
CO STARTING
   ** inside-pathway comment skipped
   TITLEONE  t
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION S1 POINT 0 0
   SRCPARAM S1 1 10 400 5 1
SO FINISHED
RE STARTING
   DISCCART 0 0 0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1 2020
   UAIRDATA  1 2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
OU FINISHED
"""
        p = parse_aermod_input(text)
        assert p.control.title_one == "t"

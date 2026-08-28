"""Tests for the AERMOD .inp file reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod import (
    AERMODProject,
    AreaPolySource,
    AreaSource,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
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

class TestFlatSourceKeyword:
    """AERMOD LOCATION lines may have 'FLAT' instead of a numeric elevation."""

    def _project_with_flat(self, so_body: str) -> AERMODProject:
        return parse_aermod_input(f"""\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC FLAT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
{so_body}
SO FINISHED
RE STARTING
   DISCCART 0 0 0
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

    def test_flat_keyword_as_elevation(self):
        p = self._project_with_flat(
            "   LOCATION  FS  POINT  100.0  200.0  FLAT\n"
            "   SRCPARAM  FS  1 30 400 10 2"
        )
        assert len(p.sources.sources) == 1
        assert p.sources.sources[0].source_id == "FS"

    def test_numeric_elevation_still_works(self):
        p = self._project_with_flat(
            "   LOCATION  S1  POINT  100.0  200.0  5.5\n"
            "   SRCPARAM  S1  1 30 400 10 2"
        )
        assert len(p.sources.sources) == 1


class TestExplicitDistancePolarGrid:
    """GRIDPOLR DIST can be an explicit list (d1 d2 d3 ...) instead of
    init/num/delta."""

    def _project_with_grid(self, re_body: str) -> AERMODProject:
        return parse_aermod_input(f"""\
CO STARTING
   TITLEONE t
   MODELOPT CONC ELEVATED DFAULT
   AVERTIME ANNUAL
   POLLUTID SO2
CO FINISHED
SO STARTING
   LOCATION S1 POINT 0 0
   SRCPARAM S1 1 10 400 5 1
SO FINISHED
RE STARTING
{re_body}
RE FINISHED
ME STARTING
   SURFFILE a.sfc
   PROFFILE a.pfl
   SURFDATA 1 2020
   UAIRDATA 1 2020
   PROFBASE 0.0
ME FINISHED
OU STARTING
OU FINISHED
""")

    def test_explicit_distances(self):
        p = self._project_with_grid(
            "   GRIDPOLR P STA\n"
            "   GRIDPOLR P ORIG 0 0\n"
            "   GRIDPOLR P DIST 100. 500. 5000. 20000.\n"
            "   GRIDPOLR P GDIR 18 10. 20.\n"
            "   GRIDPOLR P END"
        )
        g = p.receptors.polar_grids[0]
        assert g.dist_num == 4  # 4 explicit distances
        assert g.dist_init == pytest.approx(100.0)
        assert g.dir_num == 18  # standard init/num/delta form


class TestBuildingArrays:
    """BUILDHGT / BUILDWID / BUILDLEN / XBADJ / YBADJ support (a.k.a. SO-prefixed
    multi-line parameter arrays) including the N*VALUE shorthand."""

    def _project_with_building(self, building_lines: str) -> AERMODProject:
        return parse_aermod_input(f"""\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION S1 POINT 0 0 0
   SRCPARAM S1 1 30 400 10 2
{building_lines}
SO FINISHED
RE STARTING
   DISCCART 0 0 0
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

    def test_shorthand_repeat_expanded(self):
        p = self._project_with_building("SO BUILDHGT S1 36*50.")
        src = p.sources.sources[0]
        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36
        assert all(h == 50.0 for h in src.building_height)

    def test_multi_line_accumulation(self):
        p = self._project_with_building(
            "SO BUILDWID S1 10 20 30 40 50 60\n"
            "SO BUILDWID S1 70 80 90 100 110 120"
        )
        src = p.sources.sources[0]
        assert src.building_width == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]

    def test_so_prefix_stripped(self):
        """BUILDHGT lines may or may not have the SO prefix; both must work."""
        p = self._project_with_building(
            "SO BUILDHGT S1 5 5 5\n"
            "   BUILDHGT S1 5 5 5"
        )
        src = p.sources.sources[0]
        assert src.building_height == [5, 5, 5, 5, 5, 5]


class TestAdvancedSourceTypes:
    def _project_wrap(self, so_body: str) -> AERMODProject:
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
   DISCCART 0 0 0
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

    def test_line_source(self):
        from pyaermod import LineSource
        p = self._project_wrap(
            "   LOCATION  L1  LINE  0.0 0.0 100.0 0.0\n"
            "   SRCPARAM  L1  0.001  2.5  1.0"
        )
        src = p.sources.sources[0]
        assert isinstance(src, LineSource)
        assert src.x_start == 0.0 and src.x_end == 100.0
        assert src.emission_rate == 0.001
        assert src.release_height == 2.5

    def test_rline_source(self):
        from pyaermod import RLineSource
        p = self._project_wrap(
            "   LOCATION  R1  RLINE  -500 0 500 0\n"
            "   SRCPARAM  R1  0.01  1.5  3.0  1.5"
        )
        src = p.sources.sources[0]
        assert isinstance(src, RLineSource)
        assert src.x_end == 500.0

    def test_openpit_source(self):
        from pyaermod import OpenPitSource
        p = self._project_wrap(
            "   LOCATION  P1  OPENPIT  100 200 5.0\n"
            "   SRCPARAM  P1  0.005  2.0  50  100  10000  45"
        )
        src = p.sources.sources[0]
        assert isinstance(src, OpenPitSource)
        assert src.x_dimension == 50.0
        assert src.pit_volume == 10000.0
        assert src.angle == 45.0

    def test_areacirc_source(self):
        from pyaermod import AreaCircSource
        p = self._project_wrap(
            "   LOCATION  C1  AREACIRC  0 0 0\n"
            "   SRCPARAM  C1  0.003  1.0  25.0  12"
        )
        src = p.sources.sources[0]
        assert isinstance(src, AreaCircSource)
        assert src.radius == 25.0
        assert src.num_vertices == 12

    def test_unsupported_type_skipped_cleanly(self):
        """AREAPOLY requires AREAVERT vertex lists we don't reconstruct;
        the reader should skip it without crashing the whole project."""
        p = self._project_wrap(
            "   LOCATION  G1  AREAPOLY  0 0 0\n"
            "   LOCATION  P1  POINT    100 100 0\n"
            "   SRCPARAM  P1  1 10 400 5 1"
        )
        # G1 dropped, P1 preserved
        src_ids = [s.source_id for s in p.sources.sources]
        assert "P1" in src_ids


class TestAertestFullFixture:
    """After A.1 the whole AERTEST building-downwash block must parse."""
    def test_aertest_building_height_array(self):
        from pyaermod.input_reader import read_aermod_input
        p = read_aermod_input(FIXT.parent / "epa_official" / "aertest.inp")
        src = p.sources.sources[0]
        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36
        assert all(h == 50.0 for h in src.building_height)

    def test_aertest_building_width_matches_epa(self):
        from pyaermod.input_reader import read_aermod_input
        p = read_aermod_input(FIXT.parent / "epa_official" / "aertest.inp")
        src = p.sources.sources[0]
        assert len(src.building_width) == 36
        # Spot check: first three from the EPA file are 62.26, 72.64, 80.80
        assert src.building_width[0] == pytest.approx(62.26)
        assert src.building_width[1] == pytest.approx(72.64)
        assert src.building_width[2] == pytest.approx(80.80)


class TestOutputKeywords:
    def _with_output(self, ou_body: str) -> AERMODProject:
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
   DISCCART 0 0 0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
{ou_body}
OU FINISHED
""")

    def test_summfile_captured(self):
        p = self._with_output("   SUMMFILE  out/run.sum")
        assert p.output.summary_file == "out/run.sum"

    def test_plotfile_all_captured(self):
        p = self._with_output(
            "   PLOTFILE  1  ALL  FIRST  plots/run_01H.plt"
        )
        assert p.output.plot_file == "plots/run_01H.plt"
        assert p.output.plot_file_averaging == "1"

    def test_plotfile_per_group_captured(self):
        p = self._with_output(
            "   PLOTFILE  24  GRP1  FIRST  plots/grp1.plt\n"
            "   PLOTFILE  1   GRP2  FIRST  plots/grp2.plt"
        )
        groups = p.output.plot_file_groups
        assert len(groups) == 2
        assert groups[0] == ("24", "GRP1", "plots/grp1.plt")

    def test_postfile_captured(self):
        p = self._with_output(
            "   POSTFILE  1  ALL  PLOT  post/out.pst"
        )
        assert p.output.postfile == "post/out.pst"
        assert p.output.postfile_averaging == "1"
        assert p.output.postfile_format == "PLOT"

    def test_daytable_toggle(self):
        p = self._with_output("   DAYTABLE")
        assert p.output.day_table is True


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


# ---------------------------------------------------------------------------
# New keyword tests (v1.4)
# ---------------------------------------------------------------------------

_MINIMAL_WRAPPER = """\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC ELEVATED DFAULT {co_extra}
   AVERTIME  ANNUAL
   POLLUTID  NO2
{co_kw}
CO FINISHED
SO STARTING
{so_body}
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
"""

_DEFAULT_SO = """\
   LOCATION S1 POINT 0 0 0
   SRCPARAM S1 1 30 400 10 2
"""

_DEFAULT_RE = "   DISCCART 0 0 0\n"


def _wrap(co_kw="", co_extra="", so_body=_DEFAULT_SO, re_body=_DEFAULT_RE):
    return parse_aermod_input(
        _MINIMAL_WRAPPER.format(
            co_extra=co_extra, co_kw=co_kw, so_body=so_body, re_body=re_body,
        )
    )


class TestCOChemistryKeywords:
    """Tests for new CO pathway keywords added in v1.4."""

    def test_olm_in_modelopt_sets_chemistry_method(self):
        from pyaermod.input_generator import ChemistryMethod
        p = _wrap(co_extra="OLM")
        assert p.control.chemistry is not None
        assert p.control.chemistry.method == ChemistryMethod.OLM

    def test_pvmrm_in_modelopt(self):
        from pyaermod.input_generator import ChemistryMethod
        p = _wrap(co_extra="PVMRM")
        assert p.control.chemistry.method == ChemistryMethod.PVMRM

    def test_nochkd_in_modelopt_does_not_crash(self):
        """NOCHKD is recognized and silently ignored (no structural field)."""
        p = _wrap(co_extra="NOCHKD")
        # Should parse cleanly; chemistry is None because no chemistry kwds present
        assert p.control.chemistry is None

    def test_no2stack_parsed(self):
        p = _wrap(co_extra="OLM", co_kw="   NO2STACK 0.10")
        assert p.control.chemistry is not None
        assert p.control.chemistry.default_no2_ratio == pytest.approx(0.10)

    def test_no2equil_recognized_does_not_crash(self):
        """NO2EQUIL is recognized and silently ignored; no structural field."""
        p = _wrap(co_extra="OLM", co_kw="   NO2EQUIL 0.90\n   NO2STACK 0.10")
        assert p.control.chemistry is not None

    def test_ozoneval_uniform_numeric(self):
        from pyaermod.input_generator import OzoneData
        p = _wrap(co_extra="OLM", co_kw="   OZONEVAL 60.0 UG/M3")
        assert isinstance(p.control.chemistry.ozone_data, OzoneData)
        assert p.control.chemistry.ozone_data.uniform_value == pytest.approx(60.0)

    def test_ozoneval_uniform_keyword(self):
        from pyaermod.input_generator import OzoneData
        p = _wrap(co_extra="OLM", co_kw="   O3VALUES UNIFORM 40.0")
        assert p.control.chemistry.ozone_data.uniform_value == pytest.approx(40.0)

    def test_ozonefil_parsed(self):
        p = _wrap(co_extra="OLM", co_kw="   OZONEFIL ozone.dat")
        assert p.control.chemistry.ozone_data.ozone_file == "ozone.dat"

    def test_errorfil_recognized_does_not_crash(self):
        p = _wrap(co_kw="   ERRORFIL run.err")
        assert p.control.chemistry is None  # no chemistry from this alone

    def test_debugopt_recognized_does_not_crash(self):
        p = _wrap(co_kw="   DEBUGOPT 2")
        assert p.control.chemistry is None

    def test_bg_no2_olm_fixture_parses(self):
        """The vendored EPA bg_no2_olm_ppb.inp fixture must parse without error."""
        from pyaermod.input_generator import ChemistryMethod
        p = read_aermod_input(FIXT.parent / "epa_official" / "bg_no2_olm_ppb.inp")
        assert p.control.chemistry is not None
        assert p.control.chemistry.method == ChemistryMethod.OLM


class TestSOBackgroundKeywords:
    """Tests for SO BACKGRND / BGSECTOR / BACKUNIT keywords."""

    def _with_so(self, so_extra: str):
        return _wrap(so_body=_DEFAULT_SO + so_extra)

    def test_backgrnd_uniform_value(self):
        from pyaermod.input_generator import BackgroundConcentration
        p = self._with_so("   BACKGRND 5.0\n")
        assert isinstance(p.sources.background, BackgroundConcentration)
        assert p.sources.background.uniform_value == pytest.approx(5.0)

    def test_backgrnd_period_values(self):
        p = self._with_so(
            "   BACKGRND ANNUAL 3.5\n"
            "   BACKGRND 1 1.2\n"
        )
        bg = p.sources.background
        assert bg is not None
        assert bg.period_values["ANNUAL"] == pytest.approx(3.5)
        assert bg.period_values["1"] == pytest.approx(1.2)

    def test_backgrnd_sector_values(self):
        p = self._with_so(
            "   BGSECTOR 0.0 60.0 120.0\n"
            "   BACKGRND SECT1 ANNUAL 2.0\n"
            "   BACKGRND SECT2 ANNUAL 3.0\n"
        )
        bg = p.sources.background
        assert bg is not None
        assert len(bg.sectors) == 3
        assert bg.sector_values[(1, "ANNUAL")] == pytest.approx(2.0)

    def test_backgrnd_file_based_does_not_crash(self):
        """File-based BACKGRND (HOURLY filename) is recognized but not stored structurally."""
        p = self._with_so("   BACKGRND HOURLY bg.dat\n   BACKUNIT PPB\n")
        # background may be None (file-based not stored) — must not raise
        assert p.sources is not None

    def test_backunit_recognized_does_not_crash(self):
        p = self._with_so("   BACKUNIT PPB\n")
        assert p.sources.background is None  # no BACKGRND value


class TestSODepositionKeywords:
    """Tests for SO GASDEPOS / PARTDIAM / MASSFRAX / PARTDENS keywords."""

    def _with_so(self, so_extra: str):
        return _wrap(so_body=_DEFAULT_SO + so_extra)

    def test_gasdepos_parsed(self):
        from pyaermod.input_generator import GasDepositionParams
        p = self._with_so(
            "   GASDEPOS S1 0.25 0.01 0.5 0.001\n"
        )
        src = p.sources.sources[0]
        assert isinstance(src.gas_deposition, GasDepositionParams)
        assert src.gas_deposition.diffusivity == pytest.approx(0.25)
        assert src.gas_deposition.alpha_r == pytest.approx(0.01)
        assert src.gas_deposition.reactivity == pytest.approx(0.5)
        assert src.gas_deposition.henry_constant == pytest.approx(0.001)

    def test_particle_deposition_parsed(self):
        from pyaermod.input_generator import ParticleDepositionParams
        p = self._with_so(
            "   PARTDIAM S1 1.0 2.5 5.0\n"
            "   MASSFRAX S1 0.3 0.5 0.2\n"
            "   PARTDENS S1 1.5 1.5 1.5\n"
        )
        src = p.sources.sources[0]
        assert isinstance(src.particle_deposition, ParticleDepositionParams)
        assert src.particle_deposition.diameters == pytest.approx([1.0, 2.5, 5.0])
        assert src.particle_deposition.mass_fractions == pytest.approx([0.3, 0.5, 0.2])
        assert src.particle_deposition.densities == pytest.approx([1.5, 1.5, 1.5])

    def test_emisfact_recognized_does_not_crash(self):
        p = self._with_so("   EMISFACT S1 SEASON 1.0 1.0 1.0 1.0\n")
        assert p.sources.sources[0].source_id == "S1"

    def test_houremis_recognized_does_not_crash(self):
        p = self._with_so("   HOUREMIS S1 hourly_emis.dat\n")
        assert p.sources.sources[0].source_id == "S1"

    def test_included_so_recognized_does_not_crash(self):
        p = self._with_so("   INCLUDED extra_sources.inp\n")
        assert len(p.sources.sources) >= 1


class TestSOUrbanSrc:
    """Tests for SO URBANSRC keyword."""

    def test_urbansrc_sets_is_urban(self):
        p = _wrap(so_body=_DEFAULT_SO + "   URBANSRC S1 MYURBAN\n")
        src = p.sources.sources[0]
        assert src.is_urban is True
        assert src.urban_area_name == "MYURBAN"


class TestRENewKeywords:
    """Tests for RE EVALCART, DISCPOLR, INCLUDED keywords."""

    def test_evalcart_recognized_does_not_crash(self):
        p = _wrap(re_body="   EVALCART 100.0 200.0 0.0\n")
        # No discrete receptors stored, but must not raise
        assert p.receptors is not None

    def test_discpolr_recognized_does_not_crash(self):
        p = _wrap(re_body="   DISCPOLR 45.0 500.0 0.0\n")
        assert p.receptors is not None

    def test_included_re_recognized_does_not_crash(self):
        p = _wrap(re_body="   INCLUDED extra_receptors.inp\n")
        assert p.receptors is not None


class TestMENewKeywords:
    """Tests for ME SITEDATA keyword."""

    def test_sitedata_recognized_does_not_crash(self):
        text = """\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION S1 POINT 0 0 0
   SRCPARAM S1 1 30 400 10 2
SO FINISHED
RE STARTING
   DISCCART 0 0 0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
   SITEDATA  99999  2020  URBAN
ME FINISHED
OU STARTING
OU FINISHED
"""
        p = parse_aermod_input(text)
        assert p.meteorology.surface_station_id == 1


# ---------------------------------------------------------------------------
# AERMOD v26135 keyword audit (docs/keyword-audit-v26135.md): one-line
# decks that exercise every handled-but-previously-untested parse path.
# ---------------------------------------------------------------------------

class TestCOKeywordsV26135:
    def test_modelopt_deposition_flags(self):
        c = _wrap(co_extra="DEPOS DDEP WDEP").control
        assert c.calculate_deposition
        assert c.calculate_dry_deposition
        assert c.calculate_wet_deposition

    def test_modelopt_flatsrcs(self):
        from pyaermod.input_generator import TerrainType
        assert _wrap(co_extra="FLATSRCS").control.terrain_type == TerrainType.FLATSRCS

    def test_dcaycoef(self):
        assert _wrap(co_kw="   DCAYCOEF 0.0001").control.decay_coefficient == pytest.approx(1e-4)

    def test_halflife(self):
        assert _wrap(co_kw="   HALFLIFE 3600").control.half_life == pytest.approx(3600.0)

    def test_elevunit_in_co(self):
        assert _wrap(co_kw="   ELEVUNIT FEET").control.elevation_units == "FEET"

    def test_o3values_filename_form(self):
        chem = _wrap(co_kw="   O3VALUES o3hourly.dat").control.chemistry
        assert chem is not None
        assert chem.ozone_data.ozone_file == "o3hourly.dat"
        assert chem.ozone_data.uniform_value is None

    def test_unknown_pollutid_kept_as_string(self):
        # A later POLLUTID overrides the wrapper's NO2; non-enum names survive.
        assert _wrap(co_kw="   POLLUTID xylene99").control.pollutant_id == "XYLENE99"

    @pytest.mark.parametrize("line", [
        "RUNORNOT RUN", "MULTYEAR H6H ../save.sav", "SAVEFILE save.sav",
        "INITFILE init.sav", "EVENTFIL events.inp", "GASDEPDF 0.2 0.5 1.0 0.0",
        "GDSEASON 1 1 2 3 3 4 4 4 4 5 5 1", "GDLANUSE 36*1", "GASDEPVD 0.01",
        "OZONUNIT PPB", "O3SECTOR 0 90 180 270", "ARMRATIO 0.2 0.9",
        "NOXVALUE 30", "NOX_FILE nox.dat", "NOX_VALS SEASON 1 2 3 4",
        "NOX_UNIT PPB", "NOXSECTR 0 180", "AWMADWNW", "ORD_DWNW", "ARCFTOPT",
    ])
    def test_unhandled_co_keywords_pass_through(self, line):
        """v26135 CO keywords the reader does not model must not break parsing."""
        p = _wrap(co_kw=f"   {line}")
        assert p.control.title_one == "t"


class TestSOKeywordsV26135:
    @pytest.mark.parametrize("line", [
        "LOCATION S9 POINT",          # LOCATION needs srcid type x y
        "SRCPARAM",                   # bare keyword
        "BUILDHGT",                   # bare keyword
        "BUILDHGT S1 abc def",        # non-numeric building values
        "SRCGROUP",                   # bare keyword
        "GASDEPOS S1 0.1",            # too few parameters
        "GASDEPOS S1 a b c",          # non-numeric
        "PARTDIAM", "PARTDIAM S1 x",
        "MASSFRAX", "MASSFRAX S1 x",
        "PARTDENS", "PARTDENS S1 x",
    ])
    def test_malformed_lines_are_skipped_not_fatal(self, line):
        p = _wrap(so_body=_DEFAULT_SO + f"   {line}\n")
        srcs = p.sources.sources
        assert [s.source_id for s in srcs] == ["S1"]
        assert srcs[0].emission_rate == pytest.approx(1.0)
        assert getattr(srcs[0], "gas_deposition", None) is None
        assert getattr(srcs[0], "particle_deposition", None) is None

    def test_line_source_with_elevation_token(self):
        so = "   LOCATION L1 LINE 0 0 100 0 12.5\n   SRCPARAM L1 1 2 3\n"
        src = _wrap(so_body=so).sources.sources[0]
        assert isinstance(src, LineSource)
        assert (src.x_end, src.y_end) == (100.0, 0.0)
        assert src.initial_lateral_dimension == pytest.approx(3.0)

    def test_rlinext_is_constructed_with_both_endpoint_elevations(self):
        # RLINEXT carries z at both ends; SRCPARAM is
        # (emission, dcl, road width, initial sigma-z).
        so = "   LOCATION R1 RLINEXT 0 0 1 100 0 2\n   SRCPARAM R1 1 2 3 4\n"
        src = _wrap(so_body=so).sources.sources[0]
        assert isinstance(src, RLineExtSource)
        assert (src.x_start, src.y_start, src.z_start) == (0.0, 0.0, 1.0)
        assert (src.x_end, src.y_end, src.z_end) == (100.0, 0.0, 2.0)
        assert src.emission_rate == pytest.approx(1.0)
        assert src.dcl == pytest.approx(2.0)
        assert src.road_width == pytest.approx(3.0)
        assert src.init_sigma_z == pytest.approx(4.0)

    def test_areapoly_is_constructed_from_areavert(self):
        so = (
            "   LOCATION A1 AREAPOLY 0 0 0\n"
            "   SRCPARAM A1 1 5 4\n"
            "   AREAVERT A1 0 0 10 0 10 10 0 10\n"
        )
        src = _wrap(so_body=so).sources.sources[0]
        assert isinstance(src, AreaPolySource)
        assert src.vertices == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0),
                                (0.0, 10.0)]
        assert src.release_height == pytest.approx(5.0)

    def test_buoyline_group_is_assembled_from_its_segments(self):
        so = (
            "   LOCATION SEG1 BUOYLINE 0 0 100 50 0\n"
            "   SRCPARAM SEG1 1.5 10\n"
            "   BLPINPUT B1 100 10 8 5 12 30\n"
            "   BLPGROUP B1 SEG1\n"
        )
        src = _wrap(so_body=so).sources.sources[0]
        assert isinstance(src, BuoyLineSource)
        assert src.source_id == "B1"
        assert src.avg_line_length == pytest.approx(100.0)
        assert src.avg_buoyancy_parameter == pytest.approx(30.0)
        assert [s.source_id for s in src.line_segments] == ["SEG1"]
        assert src.line_segments[0].emission_rate == pytest.approx(1.5)

    def test_buoyline_without_a_group_id_uses_all(self):
        # An 8-field BLPINPUT (no group ID) puts every BUOYLINE segment
        # in the implicit group "ALL", as AERMOD does.
        so = (
            "   LOCATION SEG1 BUOYLINE 0 0 100 50 0\n"
            "   SRCPARAM SEG1 1 10\n"
            "   BLPINPUT 100 10 8 5 12 30\n"
        )
        src = _wrap(so_body=so).sources.sources[0]
        assert isinstance(src, BuoyLineSource)
        assert src.source_id == "ALL"
        assert len(src.line_segments) == 1

    @pytest.mark.parametrize(("so", "why"), [
        ("   LOCATION S1 POINT 0 0 0\n   SRCPARAM S1 1 30\n", "POINT needs 5 SRCPARAM values"),
        ("   LOCATION A1 AREA 0 0 0\n", "AREA without SRCPARAM"),
        ("   LOCATION V1 VOLUME 0 0 0\n", "VOLUME without SRCPARAM"),
        ("   LOCATION L1 LINE 0 0\n   SRCPARAM L1 1\n", "LINE without end point"),
        ("   LOCATION R1 RLINE 0 0\n   SRCPARAM R1 1\n", "RLINE without end point"),
        ("   LOCATION P1 OPENPIT 0 0 0\n   SRCPARAM P1 1 2\n", "OPENPIT needs 5 values"),
        ("   LOCATION C1 AREACIRC 0 0 0\n", "AREACIRC without SRCPARAM"),
    ])
    def test_incomplete_source_definitions_are_dropped(self, so, why):
        assert _wrap(so_body=so).sources.sources == [], why

    @pytest.mark.parametrize("line", [
        "EMISUNIT 1.0 GRAMS/SEC MICROGRAMS/M**3", "CONCUNIT 1.0 GRAMS/SEC MICROGRAMS/M**3",
        "DEPOUNIT 1.0 GRAMS/SEC GRAMS/M**2", "METHOD_2 S1 0.5 2.0", "NO2RATIO S1 0.5",
        "AREAVERT A1 0 0 10 0 10 10", "OLMGROUP OLM1 S1", "PSDGROUP INC S1",
        "BLPINPUT 1 30.0 5.0", "BLPGROUP BL1 S1", "RBARRIER S1 3.0 5.0",
        "RDEPRESS S1 2.0 10.0", "RLEMCONV", "SBARRIER S1 3.0 5.0", "VBARRIER S1 3.0 5.0 0.5",
        "PLATFORM S1 10.0 20.0", "HBPSRCID S1", "ARCFTSRC S1",
    ])
    def test_unhandled_so_keywords_pass_through(self, line):
        """v26135 SO keywords the reader does not model must not break parsing."""
        p = _wrap(so_body=_DEFAULT_SO + f"   {line}\n")
        assert [s.source_id for s in p.sources.sources] == ["S1"]


class TestREKeywordsV26135:
    def test_elevunit_in_re(self):
        p = _wrap(re_body="   ELEVUNIT FEET\n   DISCCART 0 0 0\n")
        assert p.receptors.elevation_units == "FEET"

    def test_gridcart_xyinc_on_one_line(self):
        p = _wrap(re_body="   GRIDCART G1 XYINC 0 5 100 0 4 50\n")
        g = p.receptors.cartesian_grids[0]
        assert (g.x_init, g.x_num, g.x_delta) == (0.0, 5, 100.0)
        assert (g.y_init, g.y_num, g.y_delta) == (0.0, 4, 50.0)

    @pytest.mark.parametrize("line", ["GRIDCART G1", "GRIDPOLR P1", "DISCCART 0 0"])
    def test_short_receptor_lines_are_skipped(self, line):
        p = _wrap(re_body=f"   {line}\n   DISCCART 0 0 0\n")
        assert len(p.receptors.discrete_receptors) == 1
        assert p.receptors.cartesian_grids == []
        assert p.receptors.polar_grids == []

    _POLAR = "   GRIDPOLR P ORIG 0 0\n   GRIDPOLR P DIST 100. 500. 1000.\n"

    def test_gridpolr_gdir_three_explicit_directions(self):
        p = _wrap(re_body=self._POLAR + "   GRIDPOLR P GDIR 0.0 120.0 240.0\n")
        g = p.receptors.polar_grids[0]
        assert (g.dir_init, g.dir_num, g.dir_delta) == (0.0, 3, 120.0)

    def test_gridpolr_gdir_explicit_list(self):
        p = _wrap(re_body=self._POLAR + "   GRIDPOLR P GDIR 0 45 90 135\n")
        g = p.receptors.polar_grids[0]
        assert (g.dir_init, g.dir_num, g.dir_delta) == (0.0, 4, 45.0)

    @pytest.mark.parametrize("line", ["EVALCART 0 0 0 0 0 ARC1", "DISCPOLR S1 100 45", "INCLUDED recs.inc"])
    def test_recognised_re_keywords_pass_through(self, line):
        p = _wrap(re_body=f"   {line}\n   DISCCART 0 0 0\n")
        assert len(p.receptors.discrete_receptors) == 1


class TestMEOUKeywordsV26135:
    def _deck(self, me_extra="", ou_body=""):
        return parse_aermod_input(f"""\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC FLAT
   AVERTIME  1 24 PERIOD
   POLLUTID  SO2
CO FINISHED
SO STARTING
{_DEFAULT_SO}SO FINISHED
RE STARTING
{_DEFAULT_RE}RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
{me_extra}
ME FINISHED
OU STARTING
{ou_body}
OU FINISHED
""")

    def test_wdrotate(self):
        assert self._deck(me_extra="   WDROTATE 10.5").meteorology.wind_rotation == pytest.approx(10.5)

    def test_startend(self):
        met = self._deck(me_extra="   STARTEND 2020 3 1 2020 3 31").meteorology
        assert (met.start_year, met.start_month, met.start_day) == (2020, 3, 1)
        assert (met.end_year, met.end_month, met.end_day) == (2020, 3, 31)

    def test_rectable_numeric_and_keyword_ranks(self):
        out = self._deck(ou_body="   RECTABLE ALLAVE 2").output
        assert out.receptor_table and out.receptor_table_rank == 2
        # Ordinal-word and range forms both resolve to their highest rank.
        out = self._deck(ou_body="   RECTABLE ALLAVE FIRST-THIRD").output
        assert out.receptor_table and out.receptor_table_rank == 3
        out = self._deck(ou_body="   RECTABLE ALLAVE 1-10").output
        assert out.receptor_table and out.receptor_table_rank == 10
        out = self._deck(ou_body="   RECTABLE ALLAVE EIGHTH").output
        assert out.receptor_table and out.receptor_table_rank == 8

    def test_maxtable(self):
        out = self._deck(ou_body="   MAXTABLE ALLAVE 50").output
        assert out.max_table and out.max_table_rank == 50

    @pytest.mark.parametrize("line", [
        "DAYRANGE 1/1 12/31", "SCIMBYHR 1 4", "WINDCATS 1.54 3.09 5.14 8.23 10.8",
        "NUMYEARS 5", "NOTURBST", "NOTURBCO",
    ])
    def test_unhandled_me_keywords_pass_through(self, line):
        assert self._deck(me_extra=f"   {line}").meteorology.surface_file == "a.sfc"

    def test_maxifile_filename_captured(self):
        # The reader stores the first token as the filename; AERMOD's full
        # syntax is MAXIFILE <aveper> <grpid> <thresh> <filename> (audit follow-up).
        assert self._deck(ou_body="   MAXIFILE maxi.txt").output.max_file == "maxi.txt"

    @pytest.mark.parametrize("line", [
        "TOXXFILE 1 ALL 1.0 toxx.dat", "SEASONHR ALL seasonhr.dat", "RANKFILE 1 10 rank.dat",
        "EVALFILE S1 eval.dat", "FILEFORM EXP", "MAXDAILY 24 ALL maxdaily.dat",
        "MXDYBYYR 24 ALL mxdy.dat", "MAXDCONT ALL 8 UPPER 1.0 100.0 maxdcont.dat", "NOHEADER ALL",
    ])
    def test_unhandled_ou_keywords_pass_through(self, line):
        out = self._deck(ou_body=f"   {line}").output
        assert out.plot_file is None


class TestPathwayOrderErrorsV26135:
    def test_starting_before_previous_finished(self):
        with pytest.raises(ValueError, match="SO STARTING before previous CO FINISHED"):
            parse_aermod_input("CO STARTING\n   TITLEONE t\nSO STARTING\nSO FINISHED\n")

    def test_finished_without_matching_starting(self):
        with pytest.raises(ValueError, match="SO FINISHED without matching STARTING"):
            parse_aermod_input("CO STARTING\n   TITLEONE t\nSO FINISHED\n")


class TestSandboxPathChecksV26135:
    """Exercise the chemistry + per-group PLOTFILE branches of the sandbox check."""

    _DECK = """\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC FLAT OLM
   AVERTIME  1
   POLLUTID  NO2
   NO2STACK  0.5
   OZONEFIL  {ozone}
CO FINISHED
SO STARTING
   LOCATION S1 POINT 0 0 0
   SRCPARAM S1 1 30 400 10 2
   SRCGROUP G1 S1
SO FINISHED
RE STARTING
   DISCCART 0 0 0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
   PLOTFILE 1 G1 1 {plot}
OU FINISHED
"""

    def test_ozone_and_group_plotfile_inside_sandbox_pass(self, tmp_path):
        deck = tmp_path / "ok.inp"
        deck.write_text(self._DECK.format(ozone="o3.dat", plot="g1.plt"), encoding="utf-8")
        p = read_aermod_input(deck, sandbox=True)
        assert p.control.chemistry.ozone_data.ozone_file == "o3.dat"
        assert p.output.plot_file_groups == [("1", "G1", "g1.plt")]

    def test_ozone_file_escaping_sandbox_is_rejected(self, tmp_path):
        from pyaermod.input_reader import PathTraversalError
        deck = tmp_path / "bad_o3.inp"
        deck.write_text(self._DECK.format(ozone="../o3.dat", plot="g1.plt"), encoding="utf-8")
        with pytest.raises(PathTraversalError, match="ozone_file"):
            read_aermod_input(deck, sandbox=True)

    def test_group_plotfile_escaping_sandbox_is_rejected(self, tmp_path):
        from pyaermod.input_reader import PathTraversalError
        deck = tmp_path / "bad_plt.inp"
        deck.write_text(self._DECK.format(ozone="o3.dat", plot="../g1.plt"), encoding="utf-8")
        with pytest.raises(PathTraversalError, match="plot_file_groups"):
            read_aermod_input(deck, sandbox=True)

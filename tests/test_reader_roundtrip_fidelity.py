"""Reader and writer fidelity for the RE grids, MAXIFILE, and the lines
pyaermod has no model for (``AERMODProject.unparsed_lines``).

Every field layout asserted here was read off AERMOD v26135's Fortran
(``reset.f`` POLDST / GENPOL / RADRNG / POLORG / XYPNTS / TERHGT,
``ouset.f`` OUMXFL, ``setup.f`` DEFINE / EXKEY, ``coset.f`` MODOPT /
URBOPT, ``meset.f`` STAEND) and checked against the binary with the probe
decks under ``scripts/oracle_decks`` (13-19); the comments in those decks
record what AERMOD said.
"""

from __future__ import annotations

import logging

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    DiscreteReceptor,
    EventLocation,
    MaxiFile,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PolarGrid,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
    UnparsedLine,
    UrbanArea,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.unparsed import PRESERVED_BANNER, preserved_block, unparsed_summary

DECK = """\
CO STARTING
   TITLEONE  fidelity
   MODELOPT  CONC {modelopt}
   AVERTIME  1  24  ANNUAL
   POLLUTID  SO2
{co_extra}
   RUNORNOT  RUN
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
{me_extra}
ME FINISHED
OU STARTING
{ou_body}
OU FINISHED
"""

SO_DEFAULT = """\
   LOCATION  S1  POINT  0  0  0
   SRCPARAM  S1  1  30  400  10  2
   SRCGROUP  ALL
"""
RE_DEFAULT = "   DISCCART  0  0  0"


def deck(modelopt="FLAT", co_extra="", so_body=SO_DEFAULT, re_body=RE_DEFAULT,
         me_extra="", ou_body="   RECTABLE  ALLAVE  FIRST"):
    return DECK.format(modelopt=modelopt, co_extra=co_extra, so_body=so_body,
                       re_body=re_body, me_extra=me_extra, ou_body=ou_body)


def parse(**kw) -> AERMODProject:
    return parse_aermod_input(deck(**kw))


def rewrite(project: AERMODProject, **kw) -> AERMODProject:
    return parse_aermod_input(project.to_aermod_input(validate=False, **kw))


def keyword_lines(text: str, keyword: str) -> list[list[str]]:
    return [line.split()[1:] for line in text.splitlines()
            if line.split() and line.split()[0].upper() == keyword]


EVENT_DECK = """\
CO STARTING
   TITLEONE  event fidelity
   MODELOPT  CONC  FLAT
   AVERTIME  1  24
   POLLUTID  SO2
   RUNORNOT  RUN
CO FINISHED
SO STARTING
   LOCATION  S1  POINT  0  0  0
   SRCPARAM  S1  1  30  400  10  2
   LOCATION  S2  POINT  100  0  0
   SRCPARAM  S2  1  30  400  10  2
   SRCGROUP  G2  S2
   SRCGROUP  ALL
SO FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  1988
   UAIRDATA  1  1988
   PROFBASE  0.0
ME FINISHED
EV STARTING
{ev_body}EV FINISHED
OU STARTING
{ou_body}
OU FINISHED
"""

#: The events AERMOD itself wrote for probe deck 29 (scripts/oracle_decks/29b).
EV_GENERATED = (
    "   EVENTPER H001H01001   1  G2         88030214          52.33812\n"
    "   EVENTLOC H001H01001 XR=      500.000000 YR=      500.000000     0.0000     0.0000     0.0000\n"
    "   EVENTPER H001H24002  24  ALL        88030224          16.54005\n"
    "   EVENTLOC H001H24002 XR=      500.000000 YR=      500.000000     0.0000     0.0000     0.0000\n"
)


def event_deck(ev_body=EV_GENERATED, ou_body="   EVENTOUT  SOCONT"):
    return EVENT_DECK.format(ev_body=ev_body, ou_body=ou_body)


# ---------------------------------------------------------------------------
# Runstream layout: blank keyword columns continue the previous keyword
# ---------------------------------------------------------------------------

class TestContinuationLines:
    def test_blank_keyword_columns_inherit_the_keyword(self):
        # As EPA's hrdow.inp writes it: the GDIR line repeats the network
        # ID but leaves the keyword columns blank. Probe deck 18: 60 receptors.
        re_body = (
            "   GRIDPOLR  POL1  STA\n"
            "   GRIDPOLR  POL1  ORIG  0.0  0.0\n"
            "   GRIDPOLR  POL1  DIST  100.  1000.\n"
            "             POL1  GDIR  18    10.   20.\n"
            "   GRIDPOLR  POL1  END\n"
        )
        grid = parse(re_body=re_body).receptors.polar_grids[0]
        assert grid.distances == [100.0, 1000.0]
        assert (grid.dir_num, grid.dir_init, grid.dir_delta) == (18, 10.0, 20.0)
        assert grid.receptor_count == 36

    def test_continuation_without_network_id(self):
        # reset.f REPOLR takes a bare sub-keyword as the current network.
        re_body = (
            "   GRIDPOLR  POL2  STA\n"
            "                   ORIG  S1\n"
            "                   DIST  175.  500.\n"
            "                   GDIR  12  0  30\n"
            "   GRIDPOLR  POL2  END\n"
        )
        grid = parse(re_body=re_body).receptors.polar_grids[0]
        assert grid.origin_source_id == "S1"
        assert grid.distances == [175.0, 500.0]
        assert grid.dir_num == 12 and grid.receptor_count == 24

    def test_layout_follows_the_first_line_of_the_deck(self):
        # setup.f DEFINE fixes the pathway column from line 1; with the
        # deck indented by one, a line indented 12 is still a continuation
        # and a keyword at column 5 is still a keyword.
        text = "\n".join(" " + line for line in deck(re_body=(
            "   GRIDPOLR  P  STA\n"
            "   GRIDPOLR  P  ORIG  0  0\n"
            "            P  DIST  100.  200.\n"
            "   GRIDPOLR  P  GDIR  4  0  90\n"
            "   GRIDPOLR  P  END\n"
        )).splitlines())
        grid = parse_aermod_input(text).receptors.polar_grids[0]
        assert grid.distances == [100.0, 200.0]

    def test_pyaermod_own_xyinc_continuation_still_reads(self):
        project = AERMODProject(
            control=ControlPathway(title_one="t"),
            sources=SourcePathway(sources=[PointSource("S1", 0, 0, stack_height=10)]),
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid(
                grid_name="G", x_init=0, x_num=3, x_delta=50, y_init=10, y_num=2, y_delta=25,
            )]),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )
        grid = rewrite(project).receptors.cartesian_grids[0]
        assert (grid.x_init, grid.x_num, grid.x_delta) == (0.0, 3, 50.0)
        assert (grid.y_init, grid.y_num, grid.y_delta) == (10.0, 2, 25.0)
        assert grid.x_points is None


# ---------------------------------------------------------------------------
# GRIDPOLR / GRIDCART: the forms reset.f parses, nothing heuristic
# ---------------------------------------------------------------------------

class TestPolarGridForms:
    _HEAD = "   GRIDPOLR  P  STA\n   GRIDPOLR  P  ORIG  0  0\n"
    _TAIL = "   GRIDPOLR  P  END\n"

    def _grid(self, *lines):
        re_body = self._HEAD + "".join(f"   GRIDPOLR  P  {ln}\n" for ln in lines) + self._TAIL
        return parse(re_body=re_body).receptors.polar_grids[0]

    def test_dist_is_always_an_explicit_list(self):
        # The audit's item 3: 100/10/100 used to read as init/num/delta.
        # POLDST reads three rings (probe 14: RE W250 for the duplicate).
        grid = self._grid("DIST 100 10 100", "GDIR 36 0 10")
        assert grid.distances == [100.0, 10.0, 100.0]
        assert grid.ring_distances() == [100.0, 10.0, 100.0]

    def test_dist_accumulates_over_lines(self):
        grid = self._grid("DIST 100. 200.", "DIST 300.", "GDIR 36 0 10")
        assert grid.distances == [100.0, 200.0, 300.0]
        assert (grid.dist_init, grid.dist_num, grid.dist_delta) == (100.0, 3, 100.0)

    def test_gdir_is_num_init_delta(self):
        # EPA's bg_no2_olm_ppb.inp: 36 directions from 10 every 10.
        grid = self._grid("DIST 10 100", "GDIR 36 10 10")
        assert (grid.dir_num, grid.dir_init, grid.dir_delta) == (36, 10.0, 10.0)
        assert grid.directions is None
        assert grid.direction_angles()[:3] == [10.0, 20.0, 30.0]

    def test_gdir_with_wrong_field_count_is_kept_verbatim(self):
        # GENPOL: fewer or more than three fields is E201/E202.
        project = parse(re_body=self._HEAD + "   GRIDPOLR  P  DIST 100\n"
                        "   GRIDPOLR  P  GDIR 0 45 90 135\n" + self._TAIL)
        grid = project.receptors.polar_grids[0]
        assert grid.dir_num == 36  # untouched default
        assert [(u.pathway, u.keyword, u.fields) for u in project.unparsed_lines] == [
            ("RE", "GRIDPOLR", ["P", "GDIR", "0", "45", "90", "135"]),
        ]

    def test_ddir_is_the_explicit_direction_list(self):
        grid = self._grid("DIST 100", "DDIR 0. 90. 180. 270.")
        assert grid.directions == [0.0, 90.0, 180.0, 270.0]
        assert grid.direction_angles() == [0.0, 90.0, 180.0, 270.0]
        assert grid.receptor_count == 4

    def test_orig_may_name_a_source(self):
        grid = self._grid("ORIG S1", "DIST 100", "GDIR 4 0 90")
        assert grid.origin_source_id == "S1"

    def test_elev_hill_flag_rows(self):
        grid = self._grid("DIST 100 200", "GDIR 2 0 180",
                          "ELEV 1 10. 20.", "ELEV 2 30. 40.",
                          "HILL 1 11. 21.", "HILL 2 31. 41.",
                          "FLAG 1 1.5 1.5", "FLAG 2 1.5 1.5")
        assert grid.elevations == [[10.0, 20.0], [30.0, 40.0]]
        assert grid.hills == [[11.0, 21.0], [31.0, 41.0]]
        assert grid.flags == [[1.5, 1.5], [1.5, 1.5]]

    def test_writer_emits_aermod_forms(self):
        # Probe deck 13: the old ``DIST init num delta`` / ``GDIR init num
        # delta`` block had no receptors at all (RE E185).
        text = PolarGrid(grid_name="POL1", dist_init=100, dist_num=3, dist_delta=100,
                         dir_init=0, dir_num=36, dir_delta=10).to_aermod_input()
        assert keyword_lines(text, "GRIDPOLR") == [
            ["POL1", "STA"], ["POL1", "ORIG", "0.00", "0.00"],
            ["POL1", "DIST", "100", "200", "300"],
            ["POL1", "GDIR", "36", "0", "10"], ["POL1", "END"],
        ]

    def test_writer_explicit_lists_and_source_origin(self):
        text = PolarGrid(grid_name="P", origin_source_id="S1", distances=[50, 75],
                         directions=[0, 120, 240]).to_aermod_input()
        assert ["P", "ORIG", "S1"] in keyword_lines(text, "GRIDPOLR")
        assert ["P", "DIST", "50", "75"] in keyword_lines(text, "GRIDPOLR")
        assert ["P", "DDIR", "0", "120", "240"] in keyword_lines(text, "GRIDPOLR")
        assert not any("GDIR" in ln for ln in keyword_lines(text, "GRIDPOLR"))

    def test_long_lists_wrap_and_reassemble(self):
        grid = PolarGrid(grid_name="P", distances=[float(10 * i) for i in range(1, 26)],
                         dir_num=4, dir_init=0, dir_delta=90)
        text = grid.to_aermod_input()
        assert sum(1 for ln in keyword_lines(text, "GRIDPOLR") if ln[1] == "DIST") == 3
        project = AERMODProject(
            control=ControlPathway(title_one="t"),
            sources=SourcePathway(sources=[PointSource("S1", 0, 0, stack_height=10)]),
            receptors=ReceptorPathway(polar_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )
        assert rewrite(project).receptors.polar_grids[0].distances == grid.distances

    def test_round_trip_keeps_every_form(self):
        grid = self._grid("ORIG S1", "DIST 100 250 1000", "DDIR 0 90 180 270",
                          "ELEV 1 1 2 3", "ELEV 2 4 5 6", "ELEV 3 7 8 9", "ELEV 4 1 1 1")
        project = parse(re_body=self._HEAD.replace("ORIG  0  0", "ORIG  S1")
                        + "   GRIDPOLR  P  DIST 100 250 1000\n"
                        + "   GRIDPOLR  P  DDIR 0 90 180 270\n"
                        + "".join(f"   GRIDPOLR  P  ELEV {i} {i} {i} {i}\n" for i in range(1, 5))
                        + self._TAIL)
        again = rewrite(project).receptors.polar_grids[0]
        assert again == project.receptors.polar_grids[0]
        assert grid.origin_source_id == again.origin_source_id == "S1"


class TestCartesianGridForms:
    def _grid(self, *lines, name="C1"):
        re_body = (f"   GRIDCART  {name}  STA\n"
                   + "".join(f"                 {ln}\n" for ln in lines)
                   + f"   GRIDCART  {name}  END\n")
        return parse(re_body=re_body).receptors.cartesian_grids[0]

    def test_xpnts_ypnts_explicit_points(self):
        # EPA's allsrcs.inp; probe deck 15: 16 receptors. Before this
        # branch the network silently became the default 10 x 10 grid.
        grid = self._grid("XPNTS  -1000. -500. 500. 1000.", "YPNTS  -1000. -500.",
                          "YPNTS  500. 1000.")
        assert grid.x_points == [-1000.0, -500.0, 500.0, 1000.0]
        assert grid.y_points == [-1000.0, -500.0, 500.0, 1000.0]
        assert grid.receptor_count == 16
        assert (grid.x_init, grid.x_num) == (-1000.0, 4)

    def test_points_write_back_as_xpnts_ypnts(self):
        text = CartesianGrid(grid_name="C", x_points=[0, 100], y_points=[5, 10, 15]).to_aermod_input()
        assert ["C", "XPNTS", "0", "100"] in keyword_lines(text, "GRIDCART")
        assert ["C", "YPNTS", "5", "10", "15"] in keyword_lines(text, "GRIDCART")
        assert "XYINC" not in text

    def test_elev_hill_flag_rows_read_into_the_existing_fields(self):
        grid = self._grid("XYINC 0 2 100 0 2 100",
                          "ELEV 1 10. 11.", "ELEV 2 12. 13.",
                          "HILL 1 20. 21.", "HILL 2 22. 23.",
                          "FLAG 1 2. 2.", "FLAG 2 2. 2.")
        assert grid.grid_elevations == [[10.0, 11.0], [12.0, 13.0]]
        assert grid.grid_hills == [[20.0, 21.0], [22.0, 23.0]]
        assert grid.grid_flags == [[2.0, 2.0], [2.0, 2.0]]

    def test_elev_rows_round_trip_through_the_writer(self):
        grid = CartesianGrid(grid_name="C", x_num=2, y_num=2,
                             grid_elevations=[[1.0, 2.0], [3.0, 4.0]],
                             grid_hills=[[5.0, 6.0], [7.0, 8.0]],
                             grid_flags=[[0.5, 0.5], [0.5, 0.5]])
        project = AERMODProject(
            control=ControlPathway(title_one="t", terrain_type=TerrainType.ELEVATED),
            sources=SourcePathway(sources=[PointSource("S1", 0, 0, stack_height=10)]),
            receptors=ReceptorPathway(cartesian_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )
        assert rewrite(project).receptors.cartesian_grids[0] == grid

    def test_short_or_unknown_grid_lines_are_kept_verbatim(self):
        project = parse(re_body="   GRIDCART  G1\n   GRIDCART  G1  STA\n"
                        "   GRIDCART  G1  XYINC  0  2\n   GRIDCART  G1  END\n   DISCCART  0  0  0\n")
        assert [u.fields for u in project.unparsed_lines] == [["G1"], ["G1", "XYINC", "0", "2"]]


# ---------------------------------------------------------------------------
# OU MAXIFILE: aveper grpid thresh filename [funit]
# ---------------------------------------------------------------------------

class TestMaxiFile:
    def test_four_field_form_is_read(self):
        # EPA's testpm25.inp. The audit's item 1 pinned the first token
        # being stored as the filename.
        out = parse(ou_body="   MAXIFILE  24  ALL  35.0  ../Outputs/MAX24PM.FIL").output
        assert out.maxi_files == [MaxiFile("24", "ALL", 35.0, "../Outputs/MAX24PM.FIL")]

    def test_unit_field_and_several_lines(self):
        out = parse(ou_body="   MAXIFILE  1   ALL  30.0  m01.dat\n"
                    "   MAXIFILE  24  ALL  12.5  m24.dat  45").output
        assert [m.averaging_period for m in out.maxi_files] == ["1", "24"]
        assert out.maxi_files[1].file_unit == 45

    def test_short_line_is_kept_verbatim_not_guessed(self):
        # Probe deck 16: ``MAXIFILE filename`` alone is OU E201 in AERMOD.
        project = parse(ou_body="   MAXIFILE  maxi.txt")
        assert project.output.maxi_files == []
        assert [u.keyword for u in project.unparsed_lines] == ["MAXIFILE"]

    def test_writer_layout(self):
        text = OutputPathway(maxi_files=[
            MaxiFile("1", "ALL", 30.0, "m01.dat"), MaxiFile("24", "G2", 12.5, "m24.dat", 45),
        ]).to_aermod_input()
        assert keyword_lines(text, "MAXIFILE") == [
            ["1", "ALL", "30", "m01.dat"], ["24", "G2", "12.5", "m24.dat", "45"],
        ]

    def test_round_trip(self):
        first = parse(ou_body="   MAXIFILE  MONTH  ALL  1.5E2  m.dat  50")
        assert rewrite(first).output.maxi_files == first.output.maxi_files

    def test_max_file_field_is_gone(self):
        with pytest.raises(TypeError):
            OutputPathway(max_file="maxi.txt")  # type: ignore[call-arg]

    def test_sandbox_checks_maxifile_paths(self, tmp_path):
        from pyaermod.input_reader import PathTraversalError, read_aermod_input
        inp = tmp_path / "d.inp"
        inp.write_text(deck(ou_body="   MAXIFILE  1  ALL  1.0  ../../escape.dat"))
        with pytest.raises(PathTraversalError, match="maxi_files"):
            read_aermod_input(inp, sandbox=True)


# ---------------------------------------------------------------------------
# unparsed_lines: collected, reported, written back
# ---------------------------------------------------------------------------

class TestUnparsedLines:
    def test_lines_are_collected_with_pathway_keyword_and_position(self):
        project = parse(co_extra="   ERRORFIL  errors.out\n   DEBUGOPT  MODEL",
                        me_extra="   SITEDATA  99999  2020  HERE",
                        ou_body="   RECTABLE  ALLAVE  FIRST\n   RANKFILE  1  100  rank.dat")
        got = [(u.pathway, u.keyword, u.fields) for u in project.unparsed_lines]
        assert got == [
            ("CO", "ERRORFIL", ["errors.out"]),
            ("CO", "DEBUGOPT", ["MODEL"]),
            ("ME", "SITEDATA", ["99999", "2020", "HERE"]),
            ("OU", "RANKFILE", ["1", "100", "rank.dat"]),
        ]
        assert [u.lineno for u in project.unparsed_lines] == sorted(u.lineno for u in project.unparsed_lines)
        assert project.unparsed_lines[0].raw == "   ERRORFIL  errors.out"

    def test_shorthand_is_kept_as_written(self):
        so = SO_DEFAULT + "   EMISFACT  S1  HROFDY  24*0.25\n"
        line = parse(so_body=so).unparsed_lines[0]
        assert line.fields == ["S1", "HROFDY", "24*0.25"]
        assert line.to_aermod_line() == "   EMISFACT  S1  HROFDY  24*0.25"

    def test_short_keyword_is_padded_to_eight_columns(self):
        # Probe: ``   XBADJ  STACK1`` reads as keyword ``XBADJ  S`` (E105).
        line = UnparsedLine("SO", "XBADJ", ["S1", "1.0"], 1, "")
        assert line.to_aermod_line() == "   XBADJ     S1  1.0"
        assert line.to_aermod_line()[12] == " "  # data starts in column 13

    def test_continuation_line_is_written_with_its_keyword(self):
        so = SO_DEFAULT + "   HOUREMIS  hr.dat  S1\n                    S1\n"
        lines = parse(so_body=so).unparsed_lines
        assert [u.keyword for u in lines] == ["HOUREMIS", "HOUREMIS"]
        assert lines[1].to_aermod_line() == "   HOUREMIS  S1"

    def test_parse_logs_one_warning_per_pathway_and_keyword(self, caplog):
        with caplog.at_level(logging.WARNING, logger="pyaermod.input_reader"):
            parse(so_body=SO_DEFAULT + "   EMISFACT S1 SEASON 1 1 1 1\n   EMISFACT S1 SEASON 2 2 2 2\n",
                  ou_body="   NOHEADER  ALL")
        messages = [r.getMessage() for r in caplog.records]
        assert any(m.startswith("SO EMISFACT: 2 lines") for m in messages)
        assert any(m.startswith("OU NOHEADER: 1 line ") for m in messages)
        assert len(messages) == 2

    def test_clean_deck_has_no_unparsed_lines_and_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="pyaermod.input_reader"):
            project = parse()
        assert project.unparsed_lines == []
        assert caplog.records == []

    def test_written_back_into_the_right_pathway_by_default(self):
        project = parse(co_extra="   ERRORFIL  errors.out",
                        so_body=SO_DEFAULT + "   HOUREMIS  hr.dat  S1\n",
                        re_body=RE_DEFAULT + "\n   DISCPOLR  S1  100.  45.",
                        me_extra="   SITEDATA  99999  2020",
                        ou_body="   RECTABLE  ALLAVE  FIRST\n   SEASONHR  ALL  seas.dat")
        text = project.to_aermod_input(validate=False)
        for code, keyword in (("CO", "ERRORFIL"), ("SO", "HOUREMIS"), ("RE", "DISCPOLR"),
                              ("ME", "SITEDATA"), ("OU", "SEASONHR")):
            start = text.index(f"{code} STARTING")
            end = text.index(f"{code} FINISHED")
            assert keyword in text[start:end], (code, keyword)
        assert text.count(PRESERVED_BANNER) == 5
        again = parse_aermod_input(text)
        assert [(u.pathway, u.keyword, u.fields) for u in again.unparsed_lines] == \
            [(u.pathway, u.keyword, u.fields) for u in project.unparsed_lines]

    def test_preserve_unparsed_false_drops_them(self):
        project = parse(ou_body="   RECTABLE  ALLAVE  FIRST\n   SEASONHR  ALL  seas.dat")
        text = project.to_aermod_input(validate=False, preserve_unparsed=False)
        assert "SEASONHR" not in text and PRESERVED_BANNER not in text

    def test_so_lines_go_before_the_group_keywords(self):
        # soset.f resolves SRCGROUP members among the sources defined so
        # far (E300): an INCLUDED file or a LOCATION kept verbatim must
        # come before the groups the writer generates.
        so = "   INCLUDED  more_sources.dat\n" + SO_DEFAULT + "   SRCGROUP  G2  S1  S9\n"
        text = parse(so_body=so).to_aermod_input(validate=False)
        so_text = text[text.index("SO STARTING"):text.index("SO FINISHED")]
        assert so_text.index("INCLUDED") < so_text.index("SRCGROUP")

    def test_elevunit_is_written_first_in_its_pathway(self):
        # soset.f E152: ELEVUNIT must be the first SO card.
        so = "   ELEVUNIT  FEET\n" + SO_DEFAULT
        text = parse(so_body=so).to_aermod_input(validate=False)
        so_lines = [ln for ln in text[text.index("SO STARTING"):].splitlines()[1:] if ln.strip()]
        assert so_lines[0].split() == ["ELEVUNIT", "FEET"]

    def test_ev_lines_without_a_model_stay_in_the_ev_block(self):
        # An EVENTPER with the wrong field count, an EVENTLOC for an
        # unknown event and INCLUDED are kept verbatim, inside EV.
        project = parse_aermod_input(event_deck(
            "   EVENTPER  E1  1  ALL  88030214\n"
            "   EVENTLOC  E9  XR=  100.  YR=  200.  0.\n"
            "   INCLUDED  more_events.inc\n"))
        assert [u.keyword for u in project.unparsed_lines] == ["EVENTPER", "EVENTLOC", "INCLUDED"]
        written = project.to_aermod_input(validate=False)
        ev = written[written.index("EV STARTING"):written.index("EV FINISHED")]
        assert "INCLUDED  more_events.inc" in ev and "EVENTLOC  E9" in ev

    def test_helpers(self):
        lines = [UnparsedLine("OU", "RANKFILE", ["1"], 9), UnparsedLine("CO", "ERRORFIL", ["e"], 2),
                 UnparsedLine("OU", "RANKFILE", ["24"], 10)]
        assert list(unparsed_summary(lines).items()) == [(("CO", "ERRORFIL"), 1), (("OU", "RANKFILE"), 2)]
        assert preserved_block("OU", lines) == [PRESERVED_BANNER, "   RANKFILE  1", "   RANKFILE  24"]
        assert preserved_block("ME", lines) == []

    def test_project_built_in_python_has_none(self):
        project = AERMODProject(
            control=ControlPathway(title_one="t"),
            sources=SourcePathway(sources=[PointSource("S1", 0, 0, stack_height=10)]),
            receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(1, 1)]),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )
        assert project.unparsed_lines == []
        assert PRESERVED_BANNER not in project.to_aermod_input(validate=False)


class TestSourceLinesKeptVerbatim:
    def test_unconstructed_source_type_keeps_its_definition(self, caplog):
        # EPA's capped.inp: POINTCAP / POINTHOR are not constructed yet
        # (audit item 2, WP-2); before this branch the source vanished.
        so = SO_DEFAULT + ("   LOCATION  S1C  POINTCAP  0  0  0\n"
                           "   SRCPARAM  S1C  1  30  400  10  2\n"
                           "   BUILDHGT  S1C  36*50.\n"
                           "   URBANSRC  S1C\n")
        with caplog.at_level(logging.WARNING, logger="pyaermod.input_reader"):
            project = parse(so_body=so)
        assert [s.source_id for s in project.sources.sources] == ["S1"]
        assert [u.keyword for u in project.unparsed_lines] == [
            "LOCATION", "SRCPARAM", "BUILDHGT", "URBANSRC"]
        assert any("S1C (POINTCAP)" in r.getMessage() for r in caplog.records)
        text = project.to_aermod_input(validate=False)
        assert "LOCATION  S1C  POINTCAP" in text

    def test_lines_for_sources_defined_elsewhere_are_kept(self):
        # EPA's lovett.inp defines the LOCATION in an INCLUDED file and
        # gives SRCPARAM inline; surfcoal.inp gives PARTDIAM for a range.
        so = ("   INCLUDED  src.dat\n   SRCPARAM  STK  312.6  145.  382.  23.1  4.5\n"
              "   PARTDIAM  A-Z9999999  7.77  3.88\n   SRCGROUP  ALL\n")
        project = parse(so_body=so)
        assert project.sources.sources == []
        assert [u.keyword for u in project.unparsed_lines] == ["INCLUDED", "SRCPARAM", "PARTDIAM"]
        text = project.to_aermod_input(validate=False)
        so_text = text[text.index("SO STARTING"):text.index("SO FINISHED")]
        assert so_text.index("INCLUDED") < so_text.index("SRCPARAM") < so_text.index("SRCGROUP  ALL")

    def test_srcgroup_all_is_written_back_when_the_deck_had_it(self):
        project = parse(so_body="   INCLUDED  src.dat\n   SRCGROUP  ALL\n")
        assert project.sources.include_all_group is True
        assert "SRCGROUP  ALL" in project.to_aermod_input(validate=False)

    def test_srcgroup_all_is_not_invented_for_grouped_decks(self):
        # EPA's psdcred.inp groups with PSDGROUP; SRCGROUP is E140 there.
        so = ("   LOCATION S1 POINT 0 0 0\n   SRCPARAM S1 1 30 400 10 2\n"
              "   PSDGROUP INCRCONS S1\n")
        project = parse(modelopt="FLAT PSDCREDIT", so_body=so)
        assert project.sources.include_all_group is False
        text = project.to_aermod_input(validate=False)
        assert "SRCGROUP" not in text and "PSDGROUP" in text
        # ... and a deck that names custom groups without ALL gets no ALL either.
        project = parse(so_body=SO_DEFAULT.replace("SRCGROUP  ALL", "SRCGROUP  G1  S1"))
        assert project.sources.include_all_group is False
        assert "SRCGROUP  ALL" not in project.to_aermod_input(validate=False)

    def test_python_projects_keep_the_automatic_all_group(self):
        pathway = SourcePathway(sources=[PointSource("S1", 0, 0, stack_height=10)])
        assert pathway.include_all_group is None
        assert "SRCGROUP  ALL" in pathway.to_aermod_input()
        assert "SRCGROUP" not in SourcePathway().to_aermod_input()


# ---------------------------------------------------------------------------
# The EV pathway (evset.f EVPER / EVLOC / OEVENT; probe decks 29b and 30)
# ---------------------------------------------------------------------------

class TestEventPathway:
    def test_an_ev_pathway_makes_the_deck_an_event_run(self):
        project = parse_aermod_input(event_deck())
        assert project.event_processing is True
        assert project.receptors.discrete_receptors == [] and project.receptors.polar_grids == []
        assert project.unparsed_lines == []
        assert project.output.event_output == "SOCONT"
        assert not project.output.receptor_table and not project.output.max_table

    def test_eventper_and_eventloc_fields(self):
        events = parse_aermod_input(event_deck()).events.events
        assert [e.event_name for e in events] == ["H001H01001", "H001H24002"]
        first = events[0]
        assert (first.averaging_period, first.source_group, first.date) == (1, "G2", "88030214")
        assert first.original_conc == pytest.approx(52.33812)
        assert first.location == EventLocation(500.0, 500.0, 0.0, 0.0, 0.0)
        assert events[1].averaging_period == 24 and events[1].source_group == "ALL"

    def test_eventloc_field_counts_and_polar_form(self):
        # EVLOC: name XR= x YR= y zelev [zhill [zflag]]; RNG=/DIR= for range
        # and direction. Probe 30: the elevation is not optional (E201).
        ev = ("   EVENTPER  E1  1  ALL  88030101  0.0\n   EVENTLOC  E1  XR=  1.  YR=  2.  3.\n"
              "   EVENTPER  E2  1  ALL  88030102  0.0\n   EVENTLOC  E2  XR=  1.  YR=  2.  3.  4.\n"
              "   EVENTPER  E3  1  ALL  88030103  0.0\n   EVENTLOC  E3  RNG=  700.  DIR=  45.  0.  0.  1.5\n"
              "   EVENTPER  E4  1  ALL  88030104  0.0\n   EVENTLOC  E4  XR=  1.  YR=  2.\n")
        project = parse_aermod_input(event_deck(ev))
        locs = {e.event_name: e.location for e in project.events.events}
        assert locs["E1"] == EventLocation(1.0, 2.0, 3.0, 0.0, None)
        assert locs["E2"] == EventLocation(1.0, 2.0, 3.0, 4.0, None)
        assert locs["E3"] == EventLocation(700.0, 45.0, 0.0, 0.0, 1.5, polar=True)
        assert locs["E4"] is None
        assert [u.fields for u in project.unparsed_lines] == [["E4", "XR=", "1.", "YR=", "2."]]
        text = project.to_aermod_input(validate=False)
        assert keyword_lines(text, "EVENTLOC")[0][:4] == ["E1", "XR=", "1.000000", "YR="]
        assert len(keyword_lines(text, "EVENTLOC")[0]) == 7   # no flagpole field
        assert len(keyword_lines(text, "EVENTLOC")[1]) == 7
        assert keyword_lines(text, "EVENTLOC")[2] == ["E3", "RNG=", "700.000000", "DIR=", "45.000000",
                                                       "0.0000", "0.0000", "1.5000"]

    def test_event_deck_round_trips_token_for_token(self):
        text = event_deck()
        project = parse_aermod_input(text)
        written = project.to_aermod_input(validate=False)
        for kw in ("EVENTPER", "EVENTLOC", "EVENTOUT"):
            assert keyword_lines(written, kw) == keyword_lines(text, kw), kw
        again = rewrite(project)
        assert again.events == project.events
        assert again.output == project.output and again.event_processing

    def test_event_deck_layout_is_co_so_me_ev_ou(self):
        written = parse_aermod_input(event_deck()).to_aermod_input(validate=False)
        assert [ln.split()[0] for ln in written.splitlines() if ln.endswith("STARTING")] == \
            ["CO", "SO", "ME", "EV", "OU"]
        ou = written[written.index("OU STARTING"):]
        assert ou.splitlines()[1:-1] == ["   EVENTOUT  SOCONT"]

    def test_validator_accepts_the_generated_deck(self):
        project = parse_aermod_input(event_deck())
        from pyaermod.validator import Validator
        result = Validator.validate(project)
        assert [e for e in result.errors if e.severity == "error"] == [], str(result)

    def test_a_normal_deck_has_no_events(self):
        project = parse()
        assert project.events is None and project.event_processing is False
        assert "EV STARTING" not in project.to_aermod_input(validate=False)

    def test_event_deck_written_as_a_normal_run_keeps_eventout(self):
        # Nothing is dropped; the validator, not the writer, says the
        # combination is wrong.
        project = parse_aermod_input(event_deck())
        text = project.to_aermod_input(validate=False, event_processing=False)
        assert "RE STARTING" in text and "   EVENTOUT  SOCONT" in text


# ---------------------------------------------------------------------------
# CO / ME fields the sweep over EPA's decks showed were lost or misspelt
# ---------------------------------------------------------------------------

class TestControlPathwayFidelity:
    def test_elevated_terrain_is_spelt_elev(self):
        # coset.f MODOPT knows FLAT and ELEV; ELEVATED was E203 (flatelev.inp).
        text = ControlPathway(title_one="t", terrain_type=TerrainType.ELEVATED).to_aermod_input()
        opts = keyword_lines(text, "MODELOPT")[0]
        assert "ELEV" in opts and "ELEVATED" not in opts

    def test_flatsrcs_is_flat_then_elev(self):
        text = ControlPathway(title_one="t", terrain_type=TerrainType.FLATSRCS).to_aermod_input()
        opts = keyword_lines(text, "MODELOPT")[0]
        assert opts.index("FLAT") < opts.index("ELEV") and "FLATSRCS" not in opts

    def test_flat_then_elev_reads_as_flatsrcs_and_back(self):
        control = parse(modelopt="FLAT ELEV").control
        assert control.terrain_type == TerrainType.FLATSRCS
        assert parse(modelopt="ELEV FLAT").control.terrain_type == TerrainType.ELEVATED
        assert parse(modelopt="ELEV").control.terrain_type == TerrainType.ELEVATED
        assert parse(modelopt="ELEVATED").control.terrain_type == TerrainType.ELEVATED

    def test_unknown_modelopt_tokens_survive(self):
        control = parse(modelopt="FLAT SCREEN PSDCREDIT NOCHKD ALPHA BETA").control
        assert control.extra_model_options == ["SCREEN", "NOCHKD"]
        assert control.alpha and control.beta and control.psd_credit
        opts = keyword_lines(control.to_aermod_input(), "MODELOPT")[0]
        assert {"SCREEN", "PSDCREDIT", "NOCHKD", "ALPHA", "BETA"} <= set(opts)

    def test_ttrm_is_a_chemistry_method(self):
        control = parse(modelopt="FLAT TTRM", co_extra="   NO2STACK  0.2").control
        assert control.chemistry.method == ChemistryMethod.TTRM
        opts = keyword_lines(control.to_aermod_input(), "MODELOPT")[0]
        assert "TTRM" in opts and "ARM2" not in opts

    def test_no2stack_is_not_written_for_arm2(self):
        # bg_no2_arm2_ppb.inp: coset.f E600 without PVMRM/OLM/GRSM/TTRM.
        text = ControlPathway(title_one="t", chemistry=ChemistryOptions(
            method=ChemistryMethod.ARM2)).to_aermod_input()
        assert "NO2STACK" not in text
        text = ControlPathway(title_one="t", chemistry=ChemistryOptions(
            method=ChemistryMethod.OLM, default_no2_ratio=0.2)).to_aermod_input()
        assert ["0.2000"] in keyword_lines(text, "NO2STACK")

    def test_runornot_not_round_trips(self):
        control = parse().control
        assert control.run_model is True
        text = deck().replace("RUNORNOT  RUN", "RUNORNOT  NOT")
        control = parse_aermod_input(text).control
        assert control.run_model is False
        assert keyword_lines(control.to_aermod_input(), "RUNORNOT") == [["NOT"]]

    def test_eventfil_with_and_without_its_option(self):
        # coset.f EVNTFL: EVENTFIL evfile [SOCONT|DETAIL].
        project = parse(co_extra="   EVENTFIL  ev.inp  SOCONT")
        assert (project.control.eventfil, project.control.eventfil_option) == ("ev.inp", "SOCONT")
        assert project.unparsed_lines == []
        assert keyword_lines(project.to_aermod_input(validate=False), "EVENTFIL") == [["ev.inp", "SOCONT"]]
        project = parse(co_extra="   EVENTFIL  ev.inp")
        assert (project.control.eventfil, project.control.eventfil_option) == ("ev.inp", None)
        assert keyword_lines(project.to_aermod_input(validate=False), "EVENTFIL") == [["ev.inp"]]

    def test_bare_eventfil_is_kept_verbatim(self):
        # The bare form means EVENTS.INP with W207; there is no field for it.
        project = parse(co_extra="   EVENTFIL")
        assert project.control.eventfil is None
        assert [u.keyword for u in project.unparsed_lines] == ["EVENTFIL"]

    def test_single_urbanopt_is_pop_name_roughness(self):
        control = parse(co_extra="   URBANOPT  2000000  Denver  1.0").control
        assert control.urban_areas == [UrbanArea(2000000.0, None, "Denver", 1.0)]
        assert (control.urban_option, control.urban_population) == ("Denver", 2000000.0)
        assert keyword_lines(control.to_aermod_input(), "URBANOPT") == [["2000000.0", "Denver", "1.00"]]

    def test_several_urbanopt_lines_are_id_first(self):
        # EPA's multurb.inp; coset.f PREURB switches the layout when
        # there is more than one card. Collapsing to one lost the areas
        # and wrote a card AERMOD read as a population (E208).
        co = "   URBANOPT  URBAREA1  2.5E6  Somewhere  1.0\n   URBANOPT  URBAREA2  1.5E6\n"
        control = parse(co_extra=co).control
        assert [a.urban_id for a in control.urban_areas] == ["URBAREA1", "URBAREA2"]
        assert control.urban_areas[1] == UrbanArea(1500000.0, "URBAREA2")
        assert keyword_lines(control.to_aermod_input(), "URBANOPT") == [
            ["URBAREA1", "2500000.0", "Somewhere", "1.00"], ["URBAREA2", "1500000.0"],
        ]
        assert rewrite(parse(co_extra=co)).control.urban_areas == control.urban_areas

    def test_legacy_urban_fields_still_write(self):
        text = ControlPathway(title_one="t", urban_option="URB", urban_population=5e5).to_aermod_input()
        assert keyword_lines(text, "URBANOPT") == [["500000.0", "URB"]]
        # ... and the name-first line older pyaermod wrote reads back as one area.
        control = parse(co_extra="   URBANOPT  URB  500000.0").control
        assert control.urban_areas == [UrbanArea(500000.0, "URB")]
        assert (control.urban_option, control.urban_population) == ("URB", 500000.0)


class TestMeteorologyFidelity:
    def test_startend_with_hours(self):
        # EPA's testpm10_1986.inp: meset.f STAEND takes eight fields with
        # an hour after each date; six fields were read and two dropped.
        met = parse(me_extra="   startend  86 1 1 1  86 12 31 24").meteorology
        assert (met.start_year, met.start_month, met.start_day, met.start_hour) == (86, 1, 1, 1)
        assert (met.end_year, met.end_month, met.end_day, met.end_hour) == (86, 12, 31, 24)
        assert keyword_lines(met.to_aermod_input(), "STARTEND") == [
            ["86", "1", "1", "1", "86", "12", "31", "24"]]

    def test_startend_six_fields_unchanged(self):
        met = parse(me_extra="   STARTEND  2020 3 1 2020 3 31").meteorology
        assert met.start_hour is None and met.end_hour is None
        assert keyword_lines(met.to_aermod_input(), "STARTEND") == [
            ["2020", "3", "1", "2020", "3", "31"]]

    def test_startend_with_other_field_counts_is_kept_verbatim(self):
        project = parse(me_extra="   STARTEND  2020 3 1 2020 3")
        assert project.meteorology.start_year is None
        assert project.unparsed_lines[0].keyword == "STARTEND"


class TestOutputFidelity:
    def test_plotfile_with_a_lower_rank_is_kept_verbatim(self):
        # surfcoal.inp asks for 1ST..8TH; the model has no rank field and
        # wrote FIRST eight times (OU E203).
        ou = ("   RECTABLE  ALLAVE  FIRST-SECOND\n   PLOTFILE  24 ALL 1ST  p1.dat\n"
              "   PLOTFILE  24 ALL 2ND  p2.dat\n   PLOTFILE  1  ALL FIRST p3.dat  31\n")
        project = parse(ou_body=ou)
        assert project.output.plot_file == "p1.dat"
        assert [u.fields for u in project.unparsed_lines] == [
            ["24", "ALL", "2ND", "p2.dat"], ["1", "ALL", "FIRST", "p3.dat", "31"]]

    def test_second_postfile_is_kept_verbatim(self):
        ou = ("   RECTABLE  ALLAVE  FIRST\n   POSTFILE  1  ALL  PLOT  a.pst\n"
              "   POSTFILE  1  G2  PLOT  b.pst\n")
        project = parse(ou_body=ou)
        assert project.output.postfile == "a.pst"
        assert [u.fields for u in project.unparsed_lines] == [["1", "G2", "PLOT", "b.pst"]]
        text = project.to_aermod_input(validate=False)
        assert keyword_lines(text, "POSTFILE") == [["1", "ALL", "PLOT", "a.pst"], ["1", "G2", "PLOT", "b.pst"]]

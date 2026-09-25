"""Reader and writer coverage for the SO keywords of reader tranche 2.

Every keyword here was "recognised but not constructed" (or read into
the wrong model) in the v26135 audit. The field layouts asserted come
from ``soset.f`` (``scripts/keyword_oracle.py source ...``): ARVERT,
APPARM, BL_AVGINP, BLPGRP, OLMGRP, PSDGRP, NO2RAT, EMUNIT / COUNIT /
DPUNIT, RLINEBAR_INPUTS, RLINEDPR_INPUTS, SBARRIER_INPUTS,
VBARRIER_INPUTS, GASDEP, URBANS, SOLOCA and SOPARM. The forms the writer
emits are the ones ``tests/test_so_deck_acceptance.py`` runs through
AERMOD's setup pass.

Each test parses a deck, and most write it back and parse the result
again, so the writer is pinned to the same layout as the reader.
"""

from __future__ import annotations

import dataclasses

import pytest

from pyaermod.input_generator import (
    AreaPolySource,
    BuoyLineSource,
    ChemistryMethod,
    EmissionUnits,
    LineSource,
    PointSource,
    RLineExtSource,
    SolidBarrier,
    VegetativeBarrier,
)
from pyaermod.input_reader import (
    _expand_source_ids,
    _in_id_range,
    parse_aermod_input,
)

_DECK = """\
CO STARTING
   TITLEONE  tranche 2
   MODELOPT  {modelopt}
   AVERTIME  1
   POLLUTID  {pollutant}
{co_extra}   RUNORNOT  RUN
CO FINISHED
SO STARTING
{so_body}SO FINISHED
RE STARTING
   DISCCART  500 500 0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  14735 1988
   UAIRDATA  14735 1988
ME FINISHED
OU STARTING
OU FINISHED
"""

_STACK = "   LOCATION S1 POINT 0 0 12.5\n   SRCPARAM S1 1 30 400 10 2\n"


def _parse(so_body, modelopt="CONC FLAT", pollutant="SO2", co_extra=""):
    return parse_aermod_input(_DECK.format(
        modelopt=modelopt, pollutant=pollutant, co_extra=co_extra, so_body=so_body))


def _roundtrip(project):
    """Write with the validator off (the decks here are fragments) and re-read."""
    return parse_aermod_input(project.to_aermod_input(validate=False))


def _so_lines(project, keyword):
    text = project.to_aermod_input(validate=False)
    return [ln.split() for ln in text.splitlines() if ln.split()[:1] == [keyword]]


# ---------------------------------------------------------------------
# Source-ID ranges (SETIDG / ASNGRP)
# ---------------------------------------------------------------------

class TestSourceIdRanges:
    @pytest.mark.parametrize("sid,low,high,inside", [
        ("STK2", "STK1", "STK9", True),
        ("STK10", "STK1", "STK12", True),      # numeric part compares as a number
        ("STK13", "STK1", "STK12", False),
        ("STACK5", "STK1", "STK9", False),     # character part outside the range
        ("STK1A", "STK1", "STK9", False),      # trailing part outside the range
        ("STK1", "STK1", "STK1", True),
    ])
    def test_in_id_range_follows_asngrp(self, sid, low, high, inside):
        assert _in_id_range(sid, low, high) is inside

    def test_expand_keeps_literals_and_resolves_ranges(self):
        known = ["STK1", "STK2", "STK3", "AREA1"]
        assert _expand_source_ids(["AREA1", "STK1-STK2"], known) == ["AREA1", "STK1", "STK2"]

    def test_expand_drops_unknown_ids(self):
        assert _expand_source_ids(["NOPE", "STK1"], ["STK1"]) == ["STK1"]


# ---------------------------------------------------------------------
# AREAPOLY / AREAVERT
# ---------------------------------------------------------------------

class TestAreaPoly:
    # EPA's allsrcs deck: eight vertices over two AREAVERT lines and the
    # optional fourth SRCPARAM field (szinit)
    SO = (
        "   LOCATION  AREAP    AREAPOLY     0.0    0.0   0.0\n"
        "   SRCPARAM  AREAP  0.001  1.0  8  2.0\n"
        "   AREAVERT  AREAP  0.0 0.0  10.0 0.0  10.0 10.0  0.0 10.0  0.0 20.0\n"
        "   AREAVERT  AREAP  -10.0 20.0  -10.0 10.0  -10.0 0.0\n"
    )

    def test_vertices_accumulate_over_lines_and_szinit_is_read(self):
        src = _parse(self.SO).sources.sources[0]
        assert isinstance(src, AreaPolySource)
        assert len(src.vertices) == 8
        assert src.vertices[4] == (0.0, 20.0)
        assert src.vertices[-1] == (-10.0, 0.0)
        assert src.initial_vertical_dimension == pytest.approx(2.0)
        assert src.release_height == pytest.approx(1.0)

    def test_closing_vertex_is_dropped(self):
        # ARVERT accepts NVERTS+1 pairs; AERMOD closes the ring itself.
        so = (
            "   LOCATION  P1  AREAPOLY  0 0 0\n"
            "   SRCPARAM  P1  1 0 4\n"
            "   AREAVERT  P1  0 0  10 0  10 10  0 10  0 0\n"
        )
        src = _parse(so).sources.sources[0]
        assert len(src.vertices) == 4

    def test_writer_reproduces_srcparam_fields(self):
        p = _parse(self.SO)
        (srcparam,) = _so_lines(p, "SRCPARAM")
        assert [float(t) for t in srcparam[2:]] == [0.001, 1.0, 8, 2.0]
        again = _roundtrip(p).sources.sources[0]
        assert again == p.sources.sources[0]

    def test_three_field_srcparam_writes_no_szinit(self):
        so = self.SO.replace("SRCPARAM  AREAP  0.001  1.0  8  2.0", "SRCPARAM  AREAP  0.001  1.0  8")
        p = _parse(so)
        assert p.sources.sources[0].initial_vertical_dimension is None
        (srcparam,) = _so_lines(p, "SRCPARAM")
        assert len(srcparam) == 5


# ---------------------------------------------------------------------
# BUOYLINE / BLPINPUT / BLPGROUP
# ---------------------------------------------------------------------

_BLINES = (
    "   LOCATION  BLINE1  BUOYLINE  300.0  800.0   900.0  200.0  0.0\n"
    "   LOCATION  BLINE2  BUOYLINE  300.0  1100.0  900.0  400.0  0.0\n"
    "   LOCATION  BLINE3  BUOYLINE  300.0  1200.0  900.0  600.0  0.0\n"
    "   SRCPARAM  BLINE1      100.0   20.0\n"
    "   SRCPARAM  BLINE2      100.0   20.0\n"
    "   SRCPARAM  BLINE3      100.0   20.0\n"
)


class TestBuoyLine:
    def test_eight_field_blpinput_without_blpgroup_is_the_all_group(self):
        # EPA's allsrcs / baldwin decks: the legacy single-source form.
        p = _parse(_BLINES + "   BLPINPUT   848.0  20.0  100.0     2.0   37.5    300.0\n")
        (src,) = p.sources.sources
        assert isinstance(src, BuoyLineSource)
        assert src.source_id == "ALL"
        assert [s.source_id for s in src.line_segments] == ["BLINE1", "BLINE2", "BLINE3"]
        assert src.avg_buoyancy_parameter == pytest.approx(300.0)
        # and the writer keeps that form: no group ID, no BLPGROUP
        (blpinput,) = _so_lines(p, "BLPINPUT")
        assert len(blpinput) == 7
        assert _so_lines(p, "BLPGROUP") == []
        assert _roundtrip(p).sources.sources == p.sources.sources

    def test_two_groups_with_continuation_range_and_all(self):
        so = _BLINES + (
            "   BLPINPUT  G1  648.0  30.0  150.0  2.0  37.5  400.0\n"
            "   BLPINPUT  G2  848.0  20.0  100.0  2.0  37.5  300.0\n"
            "   BLPGROUP  G1  BLINE1\n"
            "   BLPGROUP  G2  BLINE2-BLINE3\n"
            "   BLPGROUP  G1  BLINE3\n"        # continuation of G1
        )
        p = _parse(so)
        groups = {s.source_id: [seg.source_id for seg in s.line_segments]
                  for s in p.sources.sources}
        assert groups == {"G1": ["BLINE1", "BLINE3"], "G2": ["BLINE2", "BLINE3"]}
        assert _so_lines(p, "BLPGROUP") == [
            ["BLPGROUP", "G1", "BLINE1", "BLINE3"], ["BLPGROUP", "G2", "BLINE2", "BLINE3"]]
        assert _roundtrip(p).sources.sources == p.sources.sources

    def test_blpgroup_all_names_every_buoyline(self):
        so = _BLINES + (
            "   BLPINPUT  ALL  848.0  20.0  100.0  2.0  37.5  300.0\n"
            "   BLPGROUP  ALL\n"
        )
        (src,) = _parse(so).sources.sources
        assert len(src.line_segments) == 3

    def test_per_segment_elevation_and_urban(self):
        so = (
            "   LOCATION  2S26  BUOYLINE  200.0   700.0   800.0  600.0  5.0\n"
            "   LOCATION  2S29  BUOYLINE  200.0  1100.0   800.0 1000.0  7.5\n"
            "   SRCPARAM  2S26     100.0   30.0\n"
            "   SRCPARAM  2S29     100.0   30.0\n"
            "   BLPINPUT  2S26 648.0  30.0  150.0     2.0   37.5    400.0\n"
            "   URBANSRC  2S26\n"
            "   BLPGROUP  2S26 2S26 2S29\n"
        )
        p = _parse(so, co_extra="   URBANOPT  700000.  INDIANAPOLIS\n")
        (src,) = p.sources.sources
        assert src.is_urban is True
        assert [seg.base_elevation for seg in src.line_segments] == [5.0, 7.5]
        locations = _so_lines(p, "LOCATION")
        assert [float(ln[-1]) for ln in locations] == [5.0, 7.5]
        assert _so_lines(p, "URBANSRC") == [["URBANSRC", "2S26"], ["URBANSRC", "2S29"]]

    def test_shared_elevation_moves_to_the_group(self):
        p = _parse(_BLINES.replace("  0.0\n", "  3.0\n")
                   + "   BLPINPUT   848.0  20.0  100.0     2.0   37.5    300.0\n")
        (src,) = p.sources.sources
        assert src.base_elevation == pytest.approx(3.0)
        assert all(seg.base_elevation is None for seg in src.line_segments)


# ---------------------------------------------------------------------
# RLINEXT and the barrier family
# ---------------------------------------------------------------------

_RLINEXT = (
    "   LOCATION  BASE  RLINEXT   0.0   -100.0    1.0     0.0   100.0     1.5     3.0\n"
    "   SRCPARAM  BASE           1.0      0.0       3.6       2.0\n"
)


class TestRLineExt:
    def test_location_reads_both_end_heights_and_the_elevation(self):
        src = _parse(_RLINEXT, modelopt="CONC FLAT ALPHA").sources.sources[0]
        assert isinstance(src, RLineExtSource)
        assert (src.z_start, src.z_end) == (1.0, 1.5)
        assert src.base_elevation == pytest.approx(3.0)
        assert (src.dcl, src.road_width, src.init_sigma_z) == (0.0, 3.6, 2.0)

    def test_writer_emits_the_eleven_field_location(self):
        p = _parse(_RLINEXT, modelopt="CONC FLAT ALPHA")
        (loc,) = _so_lines(p, "LOCATION")
        assert len(loc) == 10  # LOCATION srcid RLINEXT + 7 numbers
        assert float(loc[-1]) == 3.0

    def test_rbarrier_rdepress_vbarrier_round_trip(self):
        so = _RLINEXT + (
            "   RBARRIER  BASE  10.0  10.0  6.0  -8.0\n"
            "   RDEPRESS  BASE  -12.5  50.0  25.0\n"
            "   VBARRIER  BASE  5.0 5.0 8.0 6.0 1.0  4.0 4.0 -8.0 5.0 1.2\n"
        )
        p = _parse(so, modelopt="CONC FLAT ALPHA")
        src = p.sources.sources[0]
        assert (src.barrier_height_1, src.barrier_dcl_1) == (10.0, 10.0)
        assert (src.barrier_height_2, src.barrier_dcl_2) == (6.0, -8.0)
        assert (src.depression_depth, src.depression_wtop, src.depression_wbottom) == (-12.5, 50.0, 25.0)
        assert src.vegetative_barriers == [
            VegetativeBarrier(5.0, 5.0, 8.0, 6.0, 1.0), VegetativeBarrier(4.0, 4.0, -8.0, 5.0, 1.2)]
        assert _so_lines(p, "RBARRIER") == [["RBARRIER", "BASE", "10.00", "10.00", "6.00", "-8.00"]]
        assert _so_lines(p, "RDEPRESS") == [["RDEPRESS", "BASE", "-12.50", "50.00", "25.00"]]
        assert len(_so_lines(p, "VBARRIER")[0]) == 12
        assert _roundtrip(p).sources.sources == p.sources.sources

    def test_single_rbarrier_keeps_two_fields(self):
        p = _parse(_RLINEXT + "   RBARRIER  BASE  10.0  10.0\n", modelopt="CONC FLAT ALPHA")
        src = p.sources.sources[0]
        assert src.barrier_height_2 is None
        assert _so_lines(p, "RBARRIER") == [["RBARRIER", "BASE", "10.00", "10.00"]]

    def test_sbarrier_block_round_trips(self):
        so = _RLINEXT + (
            "   SBARRIER  WALL1  STA  2\n"
            "   SBARRIER  WALL1  -50.0  10.0  50.0  10.0  4.0  0.0\n"
            "   SBARRIER  WALL1   50.0  10.0  60.0  30.0  4.5  0.0\n"
            "   SBARRIER  WALL1  END\n"
        )
        p = _parse(so, modelopt="CONC FLAT ALPHA")
        (barrier,) = p.sources.solid_barriers
        assert isinstance(barrier, SolidBarrier)
        assert barrier.barrier_id == "WALL1"
        assert [(s.x_start, s.y_start, s.x_end, s.y_end, s.height) for s in barrier.segments] == [
            (-50.0, 10.0, 50.0, 10.0, 4.0), (50.0, 10.0, 60.0, 30.0, 4.5)]
        lines = _so_lines(p, "SBARRIER")
        assert lines[0] == ["SBARRIER", "WALL1", "STA", "2"]
        assert lines[-1] == ["SBARRIER", "WALL1", "END"]
        assert len(lines) == 4
        assert _roundtrip(p).sources.solid_barriers == p.sources.solid_barriers

    def test_rlemconv_is_a_bare_flag(self):
        p = _parse("   RLEMCONV\n" + _RLINEXT, modelopt="CONC FLAT ALPHA")
        assert p.sources.rline_moves_units is True
        assert _so_lines(p, "RLEMCONV") == [["RLEMCONV"]]
        assert _roundtrip(p).sources.rline_moves_units is True


class TestLineSzinit:
    def test_line_fourth_srcparam_field_round_trips(self):
        # soset.f LPARM: emission relhgt width [szinit]; EPA's allsrcs
        # LINE1 has 20.0 in the fourth field.
        so = "   LOCATION  LINE1  LINE  300.0  800.0  900.0  200.0  0.0\n   SRCPARAM  LINE1  0.001  1.0  20.  20.\n"
        p = _parse(so)
        src = p.sources.sources[0]
        assert isinstance(src, LineSource)
        assert src.initial_vertical_dimension == pytest.approx(20.0)
        (srcparam,) = _so_lines(p, "SRCPARAM")
        assert [float(t) for t in srcparam[2:]] == [0.001, 1.0, 20.0, 20.0]


# ---------------------------------------------------------------------
# OLMGROUP / PSDGROUP / NO2RATIO
# ---------------------------------------------------------------------

_STACKS = (
    "   LOCATION STACK1 POINT 0 0 0\n   SRCPARAM STACK1 50 35 432 11.7 2.4\n"
    "   LOCATION STACK2 POINT 0 0 0\n   SRCPARAM STACK2 50 35 432 11.7 2.4\n"
    "   LOCATION STACK3 POINT 0 0 0\n   SRCPARAM STACK3 50 35 432 11.7 2.4\n"
)
_OLM_CO = "   OZONEVAL 40. PPB\n   NO2STACK 0.10\n"


class TestOlmGroups:
    def test_bare_olmgroup_all(self):
        p = _parse(_STACKS + "SO OLMGROUP ALL\n", modelopt="CONC FLAT OLM",
                   pollutant="NO2", co_extra=_OLM_CO)
        chem = p.control.chemistry
        assert chem.method is ChemistryMethod.OLM
        assert [(g.group_name, g.member_source_ids) for g in chem.olm_groups] == [("ALL", [])]
        assert _so_lines(p, "OLMGROUP") == [["OLMGROUP", "ALL"]]

    def test_named_groups_with_ranges_and_continuation(self):
        so = _STACKS + (
            "   OLMGROUP  OLM1  STACK1-STACK2\n"
            "   OLMGROUP  OLM2  STACK3\n"
            "   OLMGROUP  OLM1  STACK3\n"
        )
        p = _parse(so, modelopt="CONC FLAT OLM", pollutant="NO2", co_extra=_OLM_CO)
        groups = {g.group_name: g.member_source_ids for g in p.control.chemistry.olm_groups}
        # member tokens are kept as written, so the range survives a rewrite
        assert groups == {"OLM1": ["STACK1-STACK2", "STACK3"], "OLM2": ["STACK3"]}
        again = _roundtrip(p)
        assert again.control.chemistry.olm_groups == p.control.chemistry.olm_groups

    def test_olmgroup_without_olm_option_is_kept_as_olm(self):
        # AERMOD refuses this deck (E144); the groups are kept so it can
        # be repaired rather than silently losing them.
        p = _parse(_STACKS + "   OLMGROUP ALL\n", pollutant="NO2")
        assert p.control.chemistry.method is ChemistryMethod.OLM
        assert p.control.chemistry.olm_groups[0].group_name == "ALL"


class TestPsdGroups:
    SO = _STACKS + (
        "   PSDGROUP INCRCONS  STACK1\n"
        "   PSDGROUP RETRBASE  STACK2\n"
        "   PSDGROUP NONRBASE  STACK3\n"
    )

    def test_psdgroup_and_psdcredit_round_trip(self):
        p = _parse(self.SO, modelopt="CONC FLAT PVMRM BETA PSDCREDIT ALPHA",
                   pollutant="NO2", co_extra=_OLM_CO)
        assert p.control.psd_credit is True
        assert p.control.alpha is True and p.control.beta is True
        assert [(g.group_name, g.member_source_ids) for g in p.sources.psd_groups] == [
            ("INCRCONS", ["STACK1"]), ("RETRBASE", ["STACK2"]), ("NONRBASE", ["STACK3"])]
        text = p.to_aermod_input(validate=False)
        assert "PSDCREDIT" in text
        assert "SRCGROUP" not in text, "PSDCREDIT forbids SRCGROUP (E105)"
        assert _so_lines(p, "PSDGROUP") == [
            ["PSDGROUP", "INCRCONS", "STACK1"], ["PSDGROUP", "RETRBASE", "STACK2"],
            ["PSDGROUP", "NONRBASE", "STACK3"]]
        again = _roundtrip(p)
        assert again.sources.psd_groups == p.sources.psd_groups
        assert again.control.psd_credit is True


class TestNo2Ratio:
    def test_no2ratio_by_id_and_range(self):
        so = _STACKS + "   NO2RATIO STACK1 0.2\n   NO2RATIO STACK2-STACK3 0.35\n"
        p = _parse(so, modelopt="CONC FLAT PVMRM", pollutant="NO2", co_extra=_OLM_CO)
        assert [s.no2_ratio for s in p.sources.sources] == [0.2, 0.35, 0.35]
        assert _so_lines(p, "NO2RATIO") == [
            ["NO2RATIO", "STACK1", "0.2000"], ["NO2RATIO", "STACK2", "0.3500"],
            ["NO2RATIO", "STACK3", "0.3500"]]
        assert [s.no2_ratio for s in _roundtrip(p).sources.sources] == [0.2, 0.35, 0.35]

    def test_no2ratio_on_a_volume_source(self):
        so = "   LOCATION V1 VOLUME 0 0 0\n   SRCPARAM V1 1 10 2 2\n   NO2RATIO V1 0.5\n"
        p = _parse(so, modelopt="CONC FLAT PVMRM", pollutant="NO2", co_extra=_OLM_CO)
        assert p.sources.sources[0].no2_ratio == 0.5


# ---------------------------------------------------------------------
# EMISUNIT / CONCUNIT / DEPOUNIT
# ---------------------------------------------------------------------

class TestUnitKeywords:
    @pytest.mark.parametrize("keyword,attr", [
        ("EMISUNIT", "emission_units"),
        ("CONCUNIT", "concentration_units"),
        ("DEPOUNIT", "deposition_units"),
    ])
    def test_unit_keyword_round_trips(self, keyword, attr):
        p = _parse(_STACK + f"   {keyword}  3.6E9   GRAM/SEC  MICROGRAMS/M**2\n")
        units = getattr(p.sources, attr)
        assert units == EmissionUnits(3.6e9, "GRAM/SEC", "MICROGRAMS/M**2")
        (line,) = _so_lines(p, keyword)
        assert line[0] == keyword and float(line[1]) == 3.6e9
        assert line[1] == "3.6e+09", "STODBL needs a decimal point before the exponent"
        assert getattr(_roundtrip(p).sources, attr) == units

    def test_labels_keep_their_case(self):
        p = _parse(_STACK + "   DEPOUNIT  3.6D6   grams/sec  milligrams/sq-m\n")
        assert p.sources.deposition_units.emission_label == "grams/sec"

    def test_factor_without_exponent_needs_no_decimal_point(self):
        p = _parse(_STACK + "   EMISUNIT  1000  GRAMS/SEC  MILLIGRAMS/M**3\n")
        (line,) = _so_lines(p, "EMISUNIT")
        assert line[1] == "1000"


# ---------------------------------------------------------------------
# GASDEPOS as AERMOD reads it: Da Dw rcl Henry
# ---------------------------------------------------------------------

class TestGasDepos:
    def test_epa_testgas_line_round_trips(self):
        so = _STACK + "   GASDEPOS  S1  0.08962      1.04E-5      2.51E4          557.0\n"
        p = _parse(so, modelopt="CONC DDEP WDEP FLAT ALPHA")
        gd = p.sources.sources[0].gas_deposition
        assert dataclasses.astuple(gd) == pytest.approx((0.08962, 1.04e-5, 2.51e4, 557.0))
        (line,) = _so_lines(p, "GASDEPOS")
        assert [float(t) for t in line[2:]] == pytest.approx([0.08962, 1.04e-5, 2.51e4, 557.0])
        assert _roundtrip(p).sources.sources[0].gas_deposition == gd

    def test_gasdepos_by_range(self):
        so = _STACKS + "   GASDEPOS  STACK1-STACK2  0.1 1e-5 700 72\n"
        p = _parse(so, modelopt="CONC DDEP FLAT ALPHA")
        assert [s.gas_deposition is not None for s in p.sources.sources] == [True, True, False]

    def test_three_value_gasdepos_is_not_a_source_parameter(self):
        # GASDEP needs exactly four values (E201); nothing is stored.
        p = _parse(_STACK + "   GASDEPOS  S1  0.1 1e-5 700\n", modelopt="CONC DDEP FLAT ALPHA")
        assert p.sources.sources[0].gas_deposition is None


# ---------------------------------------------------------------------
# URBANSRC forms and MODELOPT flags
# ---------------------------------------------------------------------

class TestUrbanAndModelOptions:
    def test_urbansrc_all(self):
        p = _parse(_STACKS + "   URBANSRC ALL\n", co_extra="   URBANOPT 1000000\n")
        assert all(s.is_urban for s in p.sources.sources)

    def test_urbansrc_ids_and_ranges(self):
        p = _parse(_STACKS + "   URBANSRC STACK1 STACK3\n", co_extra="   URBANOPT 1000000\n")
        assert [s.is_urban for s in p.sources.sources] == [True, False, True]
        assert _so_lines(p, "URBANSRC") == [["URBANSRC", "STACK1"], ["URBANSRC", "STACK3"]]

    def test_urbansrc_multi_area_form(self):
        p = _parse(_STACKS + "   URBANSRC URBAREA1 STACK1-STACK2\n",
                   co_extra="   URBANOPT URBAREA1 2.5E6 Somewhere_in_USA 1.0\n")
        assert [s.urban_area_name for s in p.sources.sources] == ["URBAREA1", "URBAREA1", None]
        assert (p.control.urban_option, p.control.urban_population,
                p.control.urban_roughness) == ("URBAREA1", 2.5e6, 1.0)

    @pytest.mark.parametrize("line,expected", [
        ("URBANOPT 700000. INDIANAPOLIS", ("INDIANAPOLIS", 700000.0, None)),
        ("URBANOPT 70889.0", (None, 70889.0, None)),
        ("URBANOPT 500000 CITY 1.2", ("CITY", 500000.0, 1.2)),
    ])
    def test_urbanopt_single_area_forms(self, line, expected):
        c = _parse(_STACK, co_extra=f"   {line}\n").control
        assert (c.urban_option, c.urban_population, c.urban_roughness) == expected
        written = [ln.split() for ln in c.to_aermod_input().splitlines() if "URBANOPT" in ln]
        assert written[0][1] == f"{expected[1]:.1f}", "population is the first field"

    def test_alpha_beta_psdcredit_are_read_and_written(self):
        p = _parse(_STACK, modelopt="CONC FLAT WARNCHKD BETA ALPHA")
        assert (p.control.alpha, p.control.beta, p.control.psd_credit) == (True, True, False)
        modelopt = next(ln for ln in p.to_aermod_input(validate=False).splitlines()
                        if "MODELOPT" in ln)
        assert "ALPHA" in modelopt and "BETA" in modelopt

    def test_base_elevation_is_read_for_every_source(self):
        # A regression: LOCATION's elevation field used to be parsed and dropped.
        p = _parse(_STACK)
        assert p.sources.sources[0].base_elevation == pytest.approx(12.5)
        assert isinstance(p.sources.sources[0], PointSource)


class TestSrcgroupContinuation:
    def test_continuation_lines_merge_and_all_keeps_background(self):
        so = _STACKS + (
            "   BACKGRND ANNUAL 5.0\n"
            "   SRCGROUP STK STACK1\n"
            "   SRCGROUP STK STACK2\n"
            "   SRCGROUP BGD BACKGROUND\n"
            "   SRCGROUP ALL BACKGROUND\n"
        )
        p = _parse(so)
        groups = {g.group_name: g.member_source_ids for g in p.sources.group_definitions}
        assert groups == {"STK": ["STACK1", "STACK2"], "BGD": ["BACKGROUND"], "ALL": ["BACKGROUND"]}
        lines = _so_lines(p, "SRCGROUP")
        # SOGRP reads BACKGROUND from the ALL card that defines the group
        # and files a non-adjacent continuation under the last group.
        assert lines[0] == ["SRCGROUP", "ALL", "BACKGROUND"]
        assert lines.count(["SRCGROUP", "ALL", "BACKGROUND"]) == 1
        assert ["SRCGROUP", "STK", "STACK1", "STACK2"] in lines

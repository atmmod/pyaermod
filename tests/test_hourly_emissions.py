"""HOUREMIS writer, the SO HOUREMIS card, and the AP-42 wind profile.

The layouts are AERMOD v26135's: soset.f HREMIS reads the card
(``HOUREMIS file srcid|range|ALL ...``, one file per card, a source on
one card only: E834/E835) and aermod.f HRQREAD reads each record as
``SO HOUREMIS yy mm dd hh srcid qemis`` (eight fields for AREA, AREACIRC,
AREAPOLY, OPENPIT, VOLUME, LINE, RLINE and RLINEXT; seven, no rate, is a
zero-emission hour with W344).
HRLOOP reads, for every met hour, one record per hourly source in the
order the deck defines the sources (E342 on a mismatch, E455 on a date
that is not the met hour). tests/test_real_aermod_source_writers.py runs
the decks these writers produce through the binary.
"""

from __future__ import annotations

import dataclasses
import math
import shutil
from pathlib import Path

import pytest

from pyaermod.hourly_emissions import (
    WindEmissionProfile,
    ap42_wind_profile,
    hourly_emission_record,
    write_hourly_emissions,
)
from pyaermod.input_generator import (
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    HourlyEmissionFile,
    LineSource,
    OpenPitSource,
    PointSource,
    RLineExtSource,
    RLineSource,
    SidewashPointSource,
    SourceGroupDefinition,
    SourcePathway,
    VolumeSource,
)
from pyaermod.input_reader import parse_aermod_input

FIXT = Path(__file__).parent / "fixtures" / "epa_official"

# First record of EPA's pset2pa.emi (surface coal mine test case, the
# HOUREMIS file of surfcoal.inp), which the writer's layout follows.
PSET2PA_FIRST = "SO HOUREMIS  93  5 19  1  R0010201  0.390291E-04"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

class TestRecord:
    def test_layout_matches_pset2pa(self):
        line = hourly_emission_record((93, 5, 19, 1), "R0010201", 0.390291e-04)
        assert line == "SO HOUREMIS  93  5 19  1  R0010201  3.902910E-05"
        # Same columns as EPA's record up to the rate, and the same fields.
        assert line[:34] == PSET2PA_FIRST[:34]
        assert [float(t) for t in line.split()[2:6]] == [float(t) for t in PSET2PA_FIRST.split()[2:6]]
        assert float(line.split()[-1]) == float(PSET2PA_FIRST.split()[-1])

    def test_four_digit_year_keeps_a_field_separator(self):
        assert hourly_emission_record((1988, 3, 1, 24), "PIT", 0.0).split()[:6] == \
            ["SO", "HOUREMIS", "1988", "3", "1", "24"]

    def test_rate_keeps_seven_significant_figures(self):
        rate = 9.4712345e-7
        text = hourly_emission_record((88, 3, 1, 1), "PIT", rate).split()[-1]
        assert text == "9.471235E-07"
        # STODBL reads an exponent only after a mantissa with a point.
        assert "." in text.split("E")[0]

    @pytest.mark.parametrize("missing", [None, float("nan")])
    def test_missing_rate_writes_seven_fields(self, missing):
        line = hourly_emission_record((88, 3, 1, 6), "PIT", missing)
        assert line == "SO HOUREMIS  88  3  1  6  PIT"
        assert len(line.split()) == 7

    @pytest.mark.parametrize("bad", [-1e-6, float("inf")])
    def test_negative_or_infinite_rate_is_refused(self, bad):
        with pytest.raises(ValueError, match="finite number >= 0"):
            hourly_emission_record((88, 3, 1, 1), "PIT", bad)


class TestWriteFile:
    HOURS = [(88, 3, 1, 1), (88, 3, 1, 2)]

    def test_hour_major_in_mapping_order(self, tmp_path):
        path = write_hourly_emissions(tmp_path / "q.emi", self.HOURS,
                                      {"PIT": [1e-5, 2e-5], "A1": [3e-6, None]})
        assert path.read_text().splitlines() == [
            "SO HOUREMIS  88  3  1  1  PIT       1.000000E-05",
            "SO HOUREMIS  88  3  1  1  A1        3.000000E-06",
            "SO HOUREMIS  88  3  1  2  PIT       2.000000E-05",
            "SO HOUREMIS  88  3  1  2  A1",
        ]

    def test_rate_count_must_match_hours(self, tmp_path):
        with pytest.raises(ValueError, match="1 hourly rates for 2 hours"):
            write_hourly_emissions(tmp_path / "q.emi", self.HOURS, {"PIT": [1.0]})

    def test_needs_a_source(self, tmp_path):
        with pytest.raises(ValueError, match="at least one source"):
            write_hourly_emissions(tmp_path / "q.emi", self.HOURS, {})

    @pytest.mark.parametrize("hour", [(88, 13, 1, 1), (88, 3, 1, 0), (88, 3, 1, 25), (88, 3, 1)])
    def test_invalid_hour_is_refused(self, tmp_path, hour):
        with pytest.raises(ValueError, match="hours\\[0\\]"):
            write_hourly_emissions(tmp_path / "q.emi", [hour], {"PIT": [1.0]})


# ---------------------------------------------------------------------------
# The SO HOUREMIS card and SourcePathway.add_hourly_emissions
# ---------------------------------------------------------------------------

def _sources():
    return [
        OpenPitSource("PIT", -300.0, -200.0, emission_rate=1e-5, x_dimension=600.0,
                      y_dimension=400.0, pit_volume=2.4e7, source_groups=["DUST"]),
        PointSource("STK", 0.0, 0.0),
        AreaSource("A1", -500.0, -500.0, emission_rate=2e-6),
        AreaCircSource("AC1", 800.0, 0.0),
        AreaPolySource("AP1", vertices=[(0, 900), (100, 900), (100, 1000)]),
    ]


class TestCard:
    def test_card_text(self):
        card = HourlyEmissionFile("pit_w.emi", ["PIT", "A1"])
        assert card.to_aermod_input() == "   HOUREMIS  pit_w.emi  PIT A1"

    def test_card_without_sources_is_refused(self):
        with pytest.raises(ValueError, match="names no source"):
            HourlyEmissionFile("pit_w.emi").to_aermod_input()

    def test_add_writes_records_in_deck_order(self, tmp_path):
        so = SourcePathway(sources=_sources())
        hours = [(88, 3, 1, 1), (88, 3, 1, 2)]
        card = so.add_hourly_emissions(tmp_path / "q.emi", hours,
                                       {"AP1": [1.0, 2.0], "A1": [3.0, 4.0], "PIT": [5.0, 6.0]},
                                       filename="q.emi")
        assert card.source_ids == ["PIT", "A1", "AP1"]
        assert so.hourly_emissions == [card]
        ids = [ln.split()[6] for ln in (tmp_path / "q.emi").read_text().splitlines()]
        assert ids == ["PIT", "A1", "AP1"] * 2

    def test_card_follows_the_sources_and_precedes_the_groups(self, tmp_path):
        so = SourcePathway(sources=_sources(), aircraft_sources=["A1"])
        so.add_hourly_emissions(tmp_path / "q.emi", [(88, 3, 1, 1)], {"PIT": [1.0]}, filename="q.emi")
        cards = [ln.split()[0] for ln in so.to_aermod_input().splitlines()[1:-1]]
        at = cards.index("HOUREMIS")
        # HREMIS flags only sources defined above it; ARCFTSRC needs the
        # card read first (E823); SRCGROUP must follow every source (E140).
        assert "LOCATION" not in cards[at:] and "SRCPARAM" not in cards[at:]
        assert at < cards.index("ARCFTSRC") < cards.index("SRCGROUP")

    def test_default_card_name_is_the_path(self, tmp_path):
        so = SourcePathway(sources=_sources())
        card = so.add_hourly_emissions(tmp_path / "q.emi", [(88, 3, 1, 1)], {"A1": [1.0]})
        assert card.filename == str(tmp_path / "q.emi")

    def test_point_source_is_refused(self, tmp_path):
        so = SourcePathway(sources=_sources())
        with pytest.raises(TypeError, match="STK is a PointSource"):
            so.add_hourly_emissions(tmp_path / "q.emi", [(88, 3, 1, 1)], {"STK": [1.0]})
        assert not (tmp_path / "q.emi").exists()

    @pytest.mark.parametrize("source", [
        VolumeSource("V1", 0.0, 0.0),
        LineSource("V1", 0.0, 0.0, 100.0, 0.0),
        RLineSource("V1", 0.0, 0.0, 100.0, 0.0),
        RLineExtSource("V1", 0.0, 0.0, 1.0, 100.0, 0.0, 1.0),
    ], ids=["VOLUME", "LINE", "RLINE", "RLINEXT"])
    def test_other_rate_only_sources_are_written(self, tmp_path, source):
        """HRQREAD reads an eight-field record for VOLUME and the LINE
        types as for AREA (the real-binary run reproduces the constant
        run for all four)."""
        so = SourcePathway(sources=[source])
        card = so.add_hourly_emissions(tmp_path / "q.emi", [(88, 3, 1, 1)], {"V1": [1.0]})
        assert card.source_ids == ["V1"]
        assert (tmp_path / "q.emi").read_text().split()[2:] == ["88", "3", "1", "1", "V1",
                                                                "1.000000E+00"]

    def test_sidewash_point_is_refused(self, tmp_path):
        so = SourcePathway(sources=[SidewashPointSource("SW1", 0.0, 0.0)])
        with pytest.raises(TypeError, match="SW1 is a SidewashPointSource"):
            so.add_hourly_emissions(tmp_path / "q.emi", [(88, 3, 1, 1)], {"SW1": [1.0]})
        assert not (tmp_path / "q.emi").exists()

    def test_unknown_source_is_refused(self, tmp_path):
        so = SourcePathway(sources=_sources())
        with pytest.raises(KeyError, match="NOPE"):
            so.add_hourly_emissions(tmp_path / "q.emi", [(88, 3, 1, 1)], {"NOPE": [1.0]})

    def test_a_source_goes_on_one_card_only(self, tmp_path):
        so = SourcePathway(sources=_sources())
        so.add_hourly_emissions(tmp_path / "a.emi", [(88, 3, 1, 1)], {"PIT": [1.0]})
        so.add_hourly_emissions(tmp_path / "b.emi", [(88, 3, 1, 1)], {"A1": [1.0]})
        with pytest.raises(ValueError, match="already on a HOUREMIS card: PIT"):
            so.add_hourly_emissions(tmp_path / "c.emi", [(88, 3, 1, 1)], {"PIT": [1.0], "AC1": [1.0]})
        assert [c.source_ids for c in so.hourly_emissions] == [["PIT"], ["A1"]]

    def test_field_is_declared_last(self):
        """Declared after include_all_group, so a positional SourcePathway
        of the older fields binds them as before."""
        names = [f.name for f in dataclasses.fields(SourcePathway)]
        assert names[-2:] == ["include_all_group", "hourly_emissions"]
        assert SourcePathway(*([None] * 11 + [False])).include_all_group is False

    def test_no_card_by_default(self):
        text = SourcePathway(sources=_sources(),
                             group_definitions=[SourceGroupDefinition("G", ["A1"])]).to_aermod_input()
        assert "HOUREMIS" not in text


def test_preserved_so_lines_go_before_a_generated_houremis_card(tmp_path):
    """A source kept verbatim (here an INCLUDED file) must be defined
    before the HOUREMIS card that flags it (soset.f HREMIS)."""
    deck = (FIXT / "aertest.inp").read_text()
    deck = deck.replace("SO STARTING", "SO STARTING\n   INCLUDED  more_sources.dat", 1)
    project = parse_aermod_input(deck)
    project.sources.hourly_emissions.append(HourlyEmissionFile("q.emi", ["STACK1"]))
    so = project.to_aermod_input(validate=False)
    so = so[so.index("SO STARTING"):so.index("SO FINISHED")]
    assert so.index("INCLUDED") < so.index("HOUREMIS") < so.index("SRCGROUP")


# ---------------------------------------------------------------------------
# AP-42 13.2.4 wind profile from a .SFC file
# ---------------------------------------------------------------------------

def _speeds(path: Path):
    return [float(ln.split()[15]) for ln in path.read_text().splitlines()[1:] if ln.strip()]


class TestWindProfile:
    def test_aermet2_counts_and_normalization(self):
        sfc = FIXT / "AERMET2.SFC"
        w = ap42_wind_profile(sfc)
        speeds = _speeds(sfc)
        assert isinstance(w, WindEmissionProfile)
        assert w.wind_speeds == speeds
        assert w.counts == {
            "hours": 96, "valid": 96, "missing": 0, "calm": 0,
            "clipped_low": sum(u < 0.6 for u in speeds),
            "clipped_high": sum(u > 6.7 for u in speeds),
        }
        assert w.counts["clipped_low"] == 11 and w.counts["clipped_high"] == 1
        # The year is kept as the file writes it (four digits in this one).
        assert w.hours[0] == (1988, 3, 1, 1) and w.hours[-1] == (1988, 3, 4, 24)
        assert math.isclose(sum(w.factors) / len(w.factors), 1.0, rel_tol=1e-12)
        raw = [(min(max(u, 0.6), 6.7) / 2.2) ** 1.3 for u in speeds]
        assert w.raw_factors == pytest.approx(raw, rel=1e-15)
        assert w.raw_mean == pytest.approx(sum(raw) / len(raw), rel=1e-15)
        assert w.factors == pytest.approx([r / w.raw_mean for r in raw], rel=1e-15)

    def test_rates_and_summary(self):
        w = ap42_wind_profile(FIXT / "AERMET2.SFC")
        assert w.rates(2.0) == [2.0 * f for f in w.factors]
        summary = w.summary()
        assert summary["hours"] == 96 and summary["u_min"] == 0.6 and summary["exponent"] == 1.3
        assert summary["source_file"].endswith("AERMET2.SFC")

    def _edited(self, tmp_path, speeds_by_line):
        lines = (FIXT / "AERMET2.SFC").read_text().splitlines()
        for i, speed in speeds_by_line.items():
            toks = lines[i].split()
            toks[15] = speed
            lines[i] = " ".join(toks)
        path = tmp_path / "edited.sfc"
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_missing_and_calm_hours(self, tmp_path):
        # metext.f: UREF >= 90 or < 0 is a missing hour, UREF = 0 a calm.
        path = self._edited(tmp_path, {1: "999.0", 2: "-9.0", 3: "0.00"})
        w = ap42_wind_profile(path)
        assert w.counts["missing"] == 2 and w.counts["calm"] == 1
        assert w.counts["valid"] == 94
        assert w.raw_factors[0] is None and w.raw_factors[1] is None
        assert w.factors[0] == w.factors[1] == 1.0
        assert w.raw_factors[2] == pytest.approx((0.6 / 2.2) ** 1.3)
        # The valid hours average to 1, so the missing hours' 1 keeps it.
        assert math.isclose(sum(w.factors) / 96, 1.0, rel_tol=1e-12)

    def test_calm_hours_are_counted_as_clipped_low(self, tmp_path):
        base = ap42_wind_profile(FIXT / "AERMET2.SFC").counts
        w = ap42_wind_profile(self._edited(tmp_path, {1: "0.00", 2: "5.00"}))
        # Line 1 was 0.80 (clipped low already), line 2 0.90: the calm
        # adds one to clipped_low as well as to calm.
        assert w.counts["calm"] == 1
        assert w.counts["clipped_low"] == base["clipped_low"] + 1

    def test_wind_speed_boundaries(self, tmp_path):
        # CHKMSG: UREF .GE. 90 is missing, so 90.0 is, and 89.99 is not.
        w = ap42_wind_profile(self._edited(tmp_path, {1: "90.0", 2: "89.99"}))
        assert w.raw_factors[0] is None
        assert w.raw_factors[1] == pytest.approx((6.7 / 2.2) ** 1.3)
        assert w.counts["missing"] == 1 and w.counts["clipped_high"] == 2

    def _fields(self, tmp_path, edits):
        """AERMET2.SFC with ``edits`` {line: {0-based field: value}}."""
        lines = (FIXT / "AERMET2.SFC").read_text().splitlines()
        for i, fields in edits.items():
            toks = lines[i].split()
            for k, v in fields.items():
                toks[k] = v
            lines[i] = " ".join(toks)
        path = tmp_path / "fields.sfc"
        path.write_text("\n".join(lines) + "\n")
        return ap42_wind_profile(path)

    # Line 1 is a stable hour (L = 7.9 m, no convective height or w*),
    # line 9 a convective one (L = -118.3 m).
    @pytest.mark.parametrize(("line", "fields", "missing"), [
        (1, {16: "999.0"}, True),                  # wind direction > 900
        (1, {16: "-9.0"}, True),                   # wind direction <= -9
        (1, {18: "999.0"}, True),                  # temperature > 900
        (1, {18: "0.0"}, True),                    # temperature <= 0
        (1, {11: "-99999.0"}, True),               # Monin-Obukhov length
        (1, {10: "-999."}, True),                  # mechanical mixing height
        (1, {10: "99999."}, True),
        (1, {6: "-9.000"}, True),                  # u*
        (1, {6: "9.000"}, True),                   # u* >= 9
        (9, {9: "-999."}, True),                   # convective height, convective hour
        (9, {7: "-9.000"}, True),                  # w*, convective hour
        (1, {9: "-999.", 7: "-9.000"}, False),     # both, stable hour: as written by AERMET
        (1, {16: "999.0", 15: "0.00"}, False),     # a calm is never checked (CHKCLM first)
    ])
    def test_hours_aermod_skips_as_missing(self, tmp_path, line, fields, missing):
        """metext.f METCHK: CHKCLM, then CHKMSG's missing-data checks."""
        w = self._fields(tmp_path, {line: fields})
        assert (w.raw_factors[line - 1] is None) is missing
        assert w.counts["missing"] == int(missing)
        assert w.counts["valid"] == 96 - int(missing)

    def test_no_valid_hour_is_refused(self, tmp_path):
        path = self._edited(tmp_path, dict.fromkeys(range(1, 97), "999.0"))
        with pytest.raises(ValueError, match="no hour AERMOD would not skip as missing"):
            ap42_wind_profile(path)

    def test_a_malformed_line_is_an_error_not_a_skip(self, tmp_path):
        """A skipped hour would shift every later record against AERMOD's
        met hours (E455), so the reader stops at it."""
        path = tmp_path / "bad.sfc"
        shutil.copy(FIXT / "AERMET2.SFC", path)
        lines = path.read_text().splitlines()
        lines[5] = lines[5][:40]
        path.write_text("\n".join(lines) + "\n")
        with pytest.raises(ValueError, match=r"bad\.sfc:6: not an AERMET surface record"):
            ap42_wind_profile(path)

    def test_writes_a_file_aermod_can_read(self, tmp_path):
        w = ap42_wind_profile(FIXT / "AERMET2.SFC")
        so = SourcePathway(sources=_sources())
        so.add_hourly_emissions(tmp_path / "w.emi", w.hours, {"PIT": w.rates(1e-5)})
        lines = (tmp_path / "w.emi").read_text().splitlines()
        assert len(lines) == 96
        assert [float(ln.split()[-1]) for ln in lines] == pytest.approx(w.rates(1e-5), rel=1e-6)

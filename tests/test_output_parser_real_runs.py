"""The output parser against real AERMOD runs (tests/fixtures/output_parser/).

Each case is a run of the v26135 binary; its README says how it was made.
The numbers asserted here are the ones AERMOD printed in its own summary
tables (quoted in the comments), not what an earlier version of the parser
returned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.output_parser import AERMODOutputParser

FIXTURES = Path(__file__).parent / "fixtures"
RUNS = FIXTURES / "output_parser"
RECORDED_SUCCESS = FIXTURES / "runner" / "success" / "aermod.out"


def _parse(case: str):
    return AERMODOutputParser(RUNS / case / "aermod.out").parse()


def _rows(result):
    return [(r["rank"], r["value_text"], r["flag"], r["date"])
            for r in result.data.to_dict("records")]


class TestCalmAndMissingFlags:
    """AERMOD appends c, m or b to a short-term value (FORMAT F14.5, A1)."""

    def test_flagged_values_are_kept_with_their_flag(self):
        three = _parse("calm_missing").concentrations["3HR"]
        # HIGH 2ND HIGH VALUE IS 41.81475m ON 88030112
        # HIGH 8TH HIGH VALUE IS  2.63736c ON 88030106
        # HIGH 9TH HIGH VALUE IS  1.58964c ON 88030306
        assert len(three.data) == 10
        rows = _rows(three)
        assert rows[1] == (2, "41.81475", "m", "88030112")
        assert rows[7] == (8, "2.63736", "c", "88030106")
        assert rows[8] == (9, "1.58964", "c", "88030306")
        assert [r[2] for r in rows].count("") == 7
        assert three.data["concentration"].iloc[1] == pytest.approx(41.81475)

    def test_a_period_whose_values_are_all_flagged_is_reported(self):
        day = _parse("calm_missing").concentrations["24HR"]
        # HIGH 1ST HIGH VALUE IS 15.94753b ON 88030124: AT ( 519.62, -300.00, ...
        assert day.max_value == pytest.approx(15.94753)
        assert tuple(day.max_location) == pytest.approx((519.62, -300.0))
        assert [r[2] for r in _rows(day)] == ["b", "b", "b", "b"]
        assert day.max_row["flag"] == "b"

    def test_maxima_equal_the_summary_tables(self):
        conc = _parse("calm_missing").concentrations
        assert set(conc) == {"1HR", "3HR", "24HR", "PERIOD"}
        expected = {"1HR": (76.07952, 519.62, -300.0),
                    "3HR": (52.64624, 563.82, -205.21),
                    "24HR": (15.94753, 519.62, -300.0),
                    "PERIOD": (5.22191, 519.62, -300.0)}
        for period, (value, x, y) in expected.items():
            assert conc[period].max_value == pytest.approx(value, abs=5e-6), period
            assert tuple(conc[period].max_location) == pytest.approx((x, y)), period


class TestAnnualAndPeriod:
    def test_no_annual_result_for_a_run_without_annual(self):
        """W361 says "PERIOD/ANNUAL"; the run has a PERIOD table only."""
        text = RECORDED_SUCCESS.read_text(encoding="latin-1")
        assert "PERIOD/ANNUAL" in text
        conc = AERMODOutputParser(RECORDED_SUCCESS).parse().concentrations
        assert set(conc) == {"1HR", "3HR", "24HR", "PERIOD"}
        assert conc["PERIOD"].max_value == pytest.approx(5.40459, abs=5e-6)

    def test_annual_is_read_from_its_own_table_and_no_period_appears(self):
        results = _parse("full_year")
        conc = results.concentrations
        assert "PERIOD" not in conc
        # THE SUMMARY OF MAXIMUM ANNUAL RESULTS AVERAGED OVER 1 YEARS
        # ALL 1ST HIGHEST VALUE IS 5.42148 AT ( 519.62, -300.00, ...
        annual = conc["ANNUAL"]
        assert annual.max_value == pytest.approx(5.42148, abs=5e-6)
        assert tuple(annual.max_location) == pytest.approx((519.62, -300.0))
        assert annual.title == "THE SUMMARY OF MAXIMUM ANNUAL RESULTS AVERAGED OVER 1 YEARS"

    def test_design_value_tables_are_kept_with_their_titles(self):
        """SO2 with 1-hour averages: AERMOD's own design-value summaries."""
        results = _parse("full_year")
        titles = [s.title for s in results.summaries if s.averaging_period == "1HR"]
        assert titles == [
            f"THE SUMMARY OF MAXIMUM {n}-HIGHEST MAX DAILY 1-HR RESULTS AVERAGED OVER 1 YEARS"
            for n in ("1ST", "2ND", "3RD", "4TH")]
        fourth = next(s for s in results.summaries if s.title == titles[-1])
        assert fourth.max_value == pytest.approx(76.07952, abs=5e-6)
        # 1-hour results are the first (1ST-HIGHEST) of these tables.
        assert results.concentrations["1HR"].title == titles[0]


class TestDeposition:
    def test_concentration_and_dry_deposition_are_kept_apart(self):
        results = _parse("conc_ddep")
        conc = results.concentrations
        assert set(conc) == {"1HR", "24HR", "PERIOD"}
        assert all(c.output_type == "CONC" and c.units == "ug/m^3" for c in conc.values())
        # CONC:  HIGH 1ST HIGH VALUE IS 76.04726; PERIOD 5.40126
        assert conc["1HR"].max_value == pytest.approx(76.04726, abs=5e-6)
        assert conc["PERIOD"].max_value == pytest.approx(5.40126, abs=5e-6)
        ddep = results.deposition["DDEP"]
        assert set(ddep) == {"1HR", "24HR", "PERIOD"}
        assert all(d.output_type == "DDEP" and d.units == "g/m^2" for d in ddep.values())
        # DRY DEPO: 1-HR 0.00274, 24-HR 0.01455, PERIOD 0.01867 GRAMS/M**2
        assert ddep["1HR"].max_value == pytest.approx(0.00274, abs=5e-6)
        assert ddep["24HR"].max_value == pytest.approx(0.01455, abs=5e-6)
        assert ddep["PERIOD"].max_value == pytest.approx(0.01867, abs=5e-6)
        assert [(s.output_type, s.averaging_period) for s in results.summaries] == [
            ("CONC", "PERIOD"), ("CONC", "1HR"), ("CONC", "24HR"),
            ("DDEP", "PERIOD"), ("DDEP", "1HR"), ("DDEP", "24HR")]

    def test_a_deposition_only_run_has_no_concentrations(self):
        results = _parse("ddep_only")
        assert results.concentrations == {}
        assert results.deposition["DDEP"]["1HR"].max_value == pytest.approx(0.00274, abs=5e-6)
        assert results.deposition["DDEP"]["1HR"].units == "g/m^2"


class TestSummaryRows:
    def test_rows_carry_group_rank_date_and_receptor(self):
        one = AERMODOutputParser(RECORDED_SUCCESS).parse().concentrations["1HR"]
        first = one.data.iloc[0].to_dict()
        # ALL HIGH 1ST HIGH VALUE IS 76.07952 ON 88030111: AT ( 519.62, -300.00,
        #   0.00, 0.00, 0.00) GP GRID1
        assert first["group"] == "ALL" and first["rank"] == 1
        assert first["date"] == "88030111" and first["flag"] == ""
        assert (first["receptor_type"], first["grid_id"]) == ("GP", "GRID1")
        assert one.title == "THE SUMMARY OF HIGHEST 1-HR RESULTS"

"""Tests for the design-value / NAAQS roll-up module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pyaermod.design_values import (
    add_background,
    annual_mean,
    naaqs_compliance_report,
    no2_1hr_design_value,
    pm10_24hr_design_value,
    pm25_24hr_design_value,
    so2_1hr_design_value,
)
from pyaermod.naaqs import get_naaqs


def _hourly_postfile(years=(2018, 2019, 2020),
                     receptors=((100.0, 0.0), (200.0, 0.0)),
                     concentration_value=10.0,
                     averaging="1-HR"):
    """Synthesize a POSTFILE-shaped hourly DataFrame."""
    rows = []
    for year in years:
        for month in range(1, 13):
            # 28 days/month is plenty to get into the percentile regime
            for day in range(1, 29):
                for hour in range(1, 25):
                    yy = year % 100
                    date = f"{yy:02d}{month:02d}{day:02d}{hour:02d}"
                    for x, y in receptors:
                        rows.append({
                            "x": x, "y": y, "concentration": concentration_value,
                            "zelev": 0.0, "zhill": 0.0, "zflag": 0.0,
                            "ave": averaging, "grp": "ALL", "date": date,
                        })
    return pd.DataFrame(rows)


class TestAddBackground:
    def test_uniform_addition(self):
        df = _hourly_postfile(years=(2020,), concentration_value=5.0)
        out = add_background(df, 7.0)
        assert (out["concentration"] == 12.0).all()
        # Original is not mutated
        assert (df["concentration"] == 5.0).all()

    def test_dict_keyed_by_date(self):
        df = _hourly_postfile(years=(2020,), concentration_value=1.0)
        # Boost only the first hour of Jan 1
        bg = {"20010101": 99.0}
        with pytest.warns(UserWarning, match="no background value"):
            out = add_background(df, bg)
        ones = out[out["date"] == "20010101"]
        rest = out[out["date"] != "20010101"]
        assert (ones["concentration"] == 100.0).all()
        assert (rest["concentration"] == 1.0).all()

    def test_series_keyed_by_date(self):
        df = _hourly_postfile(years=(2020,), concentration_value=2.0)
        bg = pd.Series({"20010101": 8.0, "20010102": 4.0})
        with pytest.warns(UserWarning, match="no background value"):
            out = add_background(df, bg)
        a = out[out["date"] == "20010101"]["concentration"].iloc[0]
        b = out[out["date"] == "20010102"]["concentration"].iloc[0]
        c = out[out["date"] == "20010103"]["concentration"].iloc[0]
        assert a == 10.0  # 2 + 8
        assert b == 6.0   # 2 + 4
        assert c == 2.0   # unchanged

    def test_a_background_matching_no_date_warns(self):
        df = _hourly_postfile(years=(2020,), concentration_value=2.0)
        with pytest.warns(UserWarning, match="matches no"):
            out = add_background(df, {"2020-01-01": 8.0})
        assert (out["concentration"] == 2.0).all()

    def test_a_background_matching_some_dates_warns_how_many_miss(self):
        # Hours without a background value get none added (fillna(0)),
        # which understates the total there, so a partial match warns
        # with the count of dates left without one.
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),),
                              concentration_value=2.0)
        df = df[df["date"].str.startswith("2001")]   # January 1-28: 672 hours
        with pytest.warns(UserWarning, match="no background value") as caught:
            out = add_background(df, pd.Series({"20010101": 8.0}))
        assert len(caught) == 1
        assert "671 of 672" in str(caught[0].message)
        assert out.loc[out["date"] == "20010101", "concentration"].tolist() == [10.0]

    def test_rows_without_a_date_count_as_unmatched(self):
        # nunique() drops NaN, so a frame of [5010101, NaN, 5010102] read
        # as "1 of 2 dates" missing when two of its three rows got nothing.
        df = pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": 1.0,
                           "date": [5010101.0, np.nan, 5010102.0]})
        with pytest.warns(UserWarning, match="no background value") as caught:
            out = add_background(df, {"05010101": 1.0})
        assert len(caught) == 1
        assert "2 of 3" in str(caught[0].message)
        assert out["concentration"].tolist() == [2.0, 1.0, 1.0]

    @pytest.mark.parametrize("background", [{"05010101": 1.0}, {"bad": 1.0}])
    def test_the_warning_names_the_callers_line_every_time(self, background):
        # The default filter shows a warning once per location; attributed
        # to the library's line, a second mismatched background in the same
        # session went unwarned.
        import warnings

        df = pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": 1.0, "ave": "1-HR",
                           "grp": "ALL", "date": ["05010101", "05010102"]})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("default")
            add_background(df, background)
            add_background(df, background)
            naaqs_compliance_report("NO2", df, background=background)
        mine = [w for w in caught if "background" in str(w.message)]
        assert len(mine) == 3, [str(w.message) for w in caught]
        assert {w.filename for w in mine} == {__file__}

    def test_a_background_covering_every_date_does_not_warn(self):
        import warnings
        df = _hourly_postfile(years=(2020,), concentration_value=2.0)
        bg = dict.fromkeys(df["date"], 3.0)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = add_background(df, bg)
        assert (out["concentration"] == 5.0).all()

    @pytest.mark.parametrize("keys", ["text", "int", "float"])
    @pytest.mark.parametrize("dates", ["text", "int", "float"])
    def test_dates_and_keys_match_whatever_their_type(self, dates, keys):
        # 2005 reads 05010101 as text but 5010101 as a number: both sides
        # are matched as the zero-padded 8-character stamp.
        import warnings
        df = _hourly_postfile(years=(2005,), receptors=((1.0, 0.0),),
                              concentration_value=2.0)
        stamps = list(df["date"])
        convert = {"text": str, "int": int, "float": float}
        df = df.assign(date=[convert[dates](d) for d in stamps])
        bg = {convert[keys](d): 3.0 for d in stamps}
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = add_background(df, bg)
        assert (out["concentration"] == 5.0).all()
        assert out["date"].tolist() == df["date"].tolist()   # left as given

    def test_a_series_with_an_integer_index_matches_text_dates(self):
        df = _hourly_postfile(years=(2005,), receptors=((1.0, 0.0),),
                              concentration_value=2.0)
        df = df[df["date"].isin(["05010101", "05010102"])]
        out = add_background(df, pd.Series([1.0, 4.0], index=[5010101, 5010102]))
        assert out["concentration"].tolist() == [3.0, 6.0]

    def test_keys_that_name_one_stamp_twice_are_refused(self):
        df = _hourly_postfile(years=(2005,), receptors=((1.0, 0.0),))
        with pytest.raises(ValueError, match="05010101"):
            add_background(df, {"05010101": 1.0, 5010101: 2.0})


    @pytest.mark.parametrize("value", [
        np.float32(7.0), np.float64(7.0), np.int64(7), np.int32(7), 7, 7.0,
    ])
    def test_a_uniform_background_may_be_any_real_number(self, value):
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),),
                              concentration_value=5.0)
        out = add_background(df, value)
        assert (out["concentration"] == 12.0).all()

    def test_a_uniform_background_from_numpy_reduces_a_series(self):
        # A background read from a monitor file and averaged is a numpy scalar.
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),),
                              concentration_value=5.0)
        monitor = pd.Series([6.0, 8.0], dtype="float32")
        out = add_background(df, monitor.mean())
        assert (out["concentration"] == 12.0).all()

    @pytest.mark.parametrize("value", [True, np.bool_(True), "7.0", [7.0]])
    def test_a_background_that_is_no_number_series_or_dict_is_refused(self, value):
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),))
        with pytest.raises(TypeError, match="background"):
            add_background(df, value)


class TestAnnualMean:
    @pytest.mark.parametrize("kind", [int, float])
    def test_numeric_dates_of_the_2000s_keep_their_year(self, kind):
        # 2005 written as a number has lost its leading zero (5010101, or
        # 5010101.0 from a CSV with a blank): it is still 2005, not 1950.
        df = _hourly_postfile(years=(2005,), receptors=((1.0, 0.0),),
                              concentration_value=4.0)
        df = df.assign(date=[kind(d) for d in df["date"]])
        out = annual_mean(df)
        assert out["year"].tolist() == [2005]
        assert out["concentration"].tolist() == [pytest.approx(4.0)]

    def test_constant_returns_same_value(self):
        df = _hourly_postfile(years=(2018, 2019), concentration_value=4.0)
        out = annual_mean(df)
        assert np.allclose(out["concentration"], 4.0)
        # Check year column is correctly extracted
        assert set(out["year"].astype(int).tolist()) == {2018, 2019}

    def test_one_row_per_receptor_per_year(self):
        df = _hourly_postfile(years=(2018, 2019),
                              receptors=((1.0, 0.0), (2.0, 0.0)))
        out = annual_mean(df)
        # 2 receptors * 2 years = 4 rows
        assert len(out) == 4


class TestPm25_24hr:
    def test_constant_concentration_dv_is_constant(self):
        df = _hourly_postfile(concentration_value=12.0)
        out = pm25_24hr_design_value(df)
        # Constant: max-of-day = 12, 98th percentile = 12, 3-yr mean = 12
        assert np.allclose(out["concentration"], 12.0)
        assert out["pollutant"].iloc[0] == "PM2.5"
        assert out["averaging_period"].iloc[0] == "24-hour"

    def test_one_row_per_receptor(self):
        df = _hourly_postfile(receptors=((1.0, 0.0), (2.0, 0.0), (3.0, 0.0)))
        out = pm25_24hr_design_value(df)
        assert len(out) == 3


class TestNo2_1hr:
    def test_constant_dv(self):
        df = _hourly_postfile(concentration_value=50.0)
        out = no2_1hr_design_value(df)
        assert np.allclose(out["concentration"], 50.0)
        assert out["pollutant"].iloc[0] == "NO2"

    def test_dv_uses_98th_percentile_not_max(self):
        # Inject a single high spike into one receptor's record.
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),),
                              concentration_value=10.0)
        df.loc[df.index[0], "concentration"] = 999.0
        out = no2_1hr_design_value(df)
        # With 28*12=336 days, the 98th percentile drops the top ~7
        # days, so the 999.0 outlier is excluded; dv should be ~10.
        assert out["concentration"].iloc[0] == pytest.approx(10.0)


class TestSo2_1hr:
    def test_99th_percentile_form(self):
        df = _hourly_postfile(concentration_value=20.0)
        out = so2_1hr_design_value(df)
        assert np.allclose(out["concentration"], 20.0)
        assert "99th" in out["form"].iloc[0]


class TestPm10_24hr:
    def test_h2h_form_averages_the_day(self):
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),),
                              concentration_value=20.0)
        # Inject two distinct hourly peaks on two different days.
        df.loc[(df["date"].str.startswith("200101")) &
               (df["date"].str.endswith("12")), "concentration"] = 100.0
        df.loc[(df["date"].str.startswith("200201")) &
               (df["date"].str.endswith("12")), "concentration"] = 80.0
        out = pm10_24hr_design_value(df)
        # The daily value of a 24-hour standard is the 24-hour *average*,
        # not the day's peak hour: (80 + 23*20) / 24 for the second-ranked
        # day. One year of data -> H2H.
        assert out["form"].iloc[0].startswith("H2H")
        assert out["concentration"].iloc[0] == pytest.approx(
            (80.0 + 23 * 20.0) / 24.0
        )

    def test_h2h_on_daily_input_is_the_second_highest_day(self):
        # Input already carries AERMOD 24-HR block averages, one per day.
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),),
                              concentration_value=20.0, averaging="24-HR")
        df = df[df["date"].str.endswith("24")].copy()
        df.loc[df["date"] == "20010124", "concentration"] = 100.0
        df.loc[df["date"] == "20020124", "concentration"] = 80.0
        out = pm10_24hr_design_value(df)
        assert out["concentration"].iloc[0] == pytest.approx(80.0)

    def test_five_year_record_uses_h6h(self):
        df = _hourly_postfile(years=(2016, 2017, 2018, 2019, 2020),
                              receptors=((1.0, 0.0),),
                              concentration_value=1.0, averaging="24-HR")
        df = df[df["date"].str.endswith("24")].copy()
        # Six descending peaks across the pooled 5-year record.
        peaks = ["16010124", "17010124", "18010124", "19010124",
                 "20010124", "20010224"]
        for i, d in enumerate(peaks):
            df.loc[df["date"] == d, "concentration"] = 100.0 - i
        out = pm10_24hr_design_value(df)
        assert out["form"].iloc[0].startswith("H6H")
        assert out["concentration"].iloc[0] == pytest.approx(95.0)


class TestNaaqsComplianceReport:
    def test_pm25_compliance(self):
        df = _hourly_postfile(concentration_value=20.0)
        rpt = naaqs_compliance_report("PM2.5", df)
        assert rpt["naaqs_level"].iloc[0] == 35.0
        assert (~rpt["exceeds"]).all()  # 20 < 35

    def test_pm25_exceedance_flag(self):
        df = _hourly_postfile(concentration_value=40.0)
        rpt = naaqs_compliance_report("PM2.5", df)
        assert rpt["exceeds"].all()

    def test_pm25_with_background_pushes_over(self):
        df = _hourly_postfile(concentration_value=30.0)
        # 30 + 10 = 40 > 35
        rpt = naaqs_compliance_report("PM2.5", df, background=10.0)
        assert rpt["exceeds"].all()

    def test_no2_compliance(self):
        df = _hourly_postfile(concentration_value=80.0)
        rpt = naaqs_compliance_report("NO2", df)
        assert rpt["naaqs_level"].iloc[0] == 100.0
        assert (~rpt["exceeds"]).all()

    def test_so2_compliance_at_limit(self):
        # 75 ppb of SO2 is 196.4 ug/m3; a design value equal to it does
        # not exceed (strict >)
        level = get_naaqs("SO2", "1-hour").level_ugm3
        df = _hourly_postfile(concentration_value=level)
        rpt = naaqs_compliance_report("SO2", df)
        assert rpt["naaqs_level_ugm3"].iloc[0] == pytest.approx(196.4, abs=0.05)
        assert (~rpt["exceeds"]).all()

    @pytest.mark.parametrize("pollutant, ugm3", [
        ("SO2", 100.0),   # > 75 "ppb" but < 196.4 ug/m3
        ("NO2", 150.0),   # > 100 "ppb" but < 188.0 ug/m3
        ("O3", 100.0),    # > 70 "ppb" but < 137 ug/m3
    ])
    def test_gas_design_value_compared_in_ugm3(self, pollutant, ugm3):
        # AERMOD reports ug/m3; comparing with the ppb level flagged
        # 1324 of 1681 receptors on a real SO2 run instead of 7
        df = _hourly_postfile(concentration_value=ugm3)
        rpt = naaqs_compliance_report(pollutant, df)
        assert (~rpt["exceeds"]).all()
        assert (rpt["naaqs_level_ugm3"] > rpt["naaqs_level"]).all()

    def test_so2_exceeds_above_ugm3_level(self):
        df = _hourly_postfile(concentration_value=200.0)
        rpt = naaqs_compliance_report("SO2", df)
        assert rpt["exceeds"].all()

    def test_unsupported_pollutant_raises(self):
        df = _hourly_postfile(concentration_value=1.0)
        with pytest.raises(ValueError, match="Unsupported pollutant"):
            naaqs_compliance_report("HF", df)

    def test_pm25_annual_form(self):
        df = _hourly_postfile(concentration_value=5.0)
        rpt = naaqs_compliance_report("PM2.5_annual", df)
        assert rpt["naaqs_level"].iloc[0] == 9.0
        assert (~rpt["exceeds"]).all()

    def test_pm10_dv(self):
        df = _hourly_postfile(years=(2020,), concentration_value=50.0)
        rpt = naaqs_compliance_report("PM10", df)
        assert rpt["naaqs_level"].iloc[0] == 150.0


class TestYearParsing:
    def test_year_2000_2049_rollover(self):
        # YY=20 -> 2020; YY=49 -> 2049; YY=50 -> 1950; YY=99 -> 1999
        df = pd.DataFrame({
            "x": [1.0, 1.0, 1.0, 1.0],
            "y": [0.0, 0.0, 0.0, 0.0],
            "concentration": [1.0, 2.0, 3.0, 4.0],
            "ave": ["1-HR"] * 4, "grp": ["ALL"] * 4,
            "zelev": [0.0] * 4, "zhill": [0.0] * 4, "zflag": [0.0] * 4,
            # Dates: YY=01 (2001), YY=49 (2049), YY=50 (1950), YY=99 (1999)
            "date": ["01010101", "49010101", "50010101", "99010101"],
        })
        out = annual_mean(df)
        years = sorted(out["year"].astype(int).tolist())
        assert years == [1950, 1999, 2001, 2049]


# ---------------------------------------------------------------------
# AERMOD's own MAXDAILY / MXDYBYYR / MAXDCONT outputs
# ---------------------------------------------------------------------
#
# tests/fixtures/epa_style/{so2,no2}_1hr_* were produced by AERMOD v26135
# (gfortran build from EPA's source) from the decks alongside them, which
# pyaermod wrote with naaqs_output_pathway(), on EPA's Anchorage 1999
# meteorology (anch-99_adju, a full year). The design value pyaermod
# computes from the MAXDAILY series must be the number AERMOD itself
# ranked: the MXDYBYYR rank row and the MAXDCONT total, to the last
# printed digit.

from pathlib import Path as _Path  # noqa: E402

_EPA_STYLE = _Path(__file__).parent / "fixtures" / "epa_style"


def _maxdcont_totals(path):
    rows = {}
    for line in _Path(path).read_text().splitlines():
        if line.startswith("*") or not line.strip():
            continue
        parts = line.split()
        rows[(float(parts[0]), float(parts[1]))] = float(parts[2])
    return rows


class TestAermodDesignValueOutputs:
    @pytest.mark.parametrize("pollutant, rank, fn", [
        ("so2", 4, so2_1hr_design_value),
        ("no2", 8, no2_1hr_design_value),
    ])
    def test_design_value_from_maxdaily_matches_aermod_ranking(self, pollutant, rank, fn):
        from pyaermod.design_values import mxdybyyr_design_value, read_maxdaily, read_mxdybyyr

        daily = read_maxdaily(_EPA_STYLE / f"{pollutant}_1hr_maxdaily.dat")
        assert len(daily) == 365 * 2, "two receptors, every day of 1999"
        assert set(daily["ave"]) == {"1-HR"} and set(daily["grp"]) == {"ALL"}
        assert daily["date"].str.len().eq(8).all()

        with pytest.warns(UserWarning, match="defined over 3 years"):
            ours = fn(daily).set_index(["x", "y"])["concentration"]
        ranked = read_mxdybyyr(_EPA_STYLE / f"{pollutant}_1hr_mxdybyyr.dat")
        assert sorted(ranked["rank"].unique()) == list(range(1, rank + 1))
        theirs = mxdybyyr_design_value(ranked, rank).set_index(["x", "y"])["concentration"]
        totals = _maxdcont_totals(_EPA_STYLE / f"{pollutant}_1hr_maxdcont.dat")

        assert len(ours) == 2
        for key, value in ours.items():
            assert value == theirs[key], f"{pollutant} at {key}: {value} vs AERMOD {theirs[key]}"
            assert value == totals[key], f"{pollutant} at {key}: MAXDCONT prints {totals[key]}"

    def test_mxdybyyr_needs_the_requested_rank(self):
        from pyaermod.design_values import mxdybyyr_design_value, read_mxdybyyr
        ranked = read_mxdybyyr(_EPA_STYLE / "so2_1hr_mxdybyyr.dat")
        with pytest.raises(ValueError, match="rank 5"):
            mxdybyyr_design_value(ranked, 5)

    def test_short_record_is_an_error(self, tmp_path):
        from pyaermod.design_values import read_maxdaily
        bad = tmp_path / "bad.dat"
        bad.write_text("* header\n 1.0 2.0 3.0\n")
        with pytest.raises(ValueError, match="at least 11 fields"):
            read_maxdaily(bad)

    def test_fixture_decks_are_what_naaqs_output_pathway_writes(self):
        from pyaermod.design_values import naaqs_output_pathway
        for pollutant in ("so2", "no2"):
            deck = (_EPA_STYLE / f"{pollutant}_1hr_design.inp").read_text()
            expected = naaqs_output_pathway(pollutant.upper(), stem=f"{pollutant}_1hr").to_aermod_input()
            assert expected in deck


class TestNaaqsOutputPathway:
    def test_ranks_come_from_the_naaqs_table(self):
        from pyaermod.design_values import naaqs_output_pathway
        from pyaermod.naaqs import get_naaqs
        assert get_naaqs("NO2", "1-hour").design_rank() == 8
        assert get_naaqs("SO2", "1-hour").design_rank() == 4
        assert get_naaqs("PM2.5", "24-hour").design_rank() == 8
        assert get_naaqs("SO2", "1-hour").design_rank(n_days=100) == 1
        with pytest.raises(ValueError, match="not a percentile form"):
            get_naaqs("CO", "1-hour").design_rank()

        so2 = naaqs_output_pathway("SO2")
        assert so2.receptor_table_rank == 4
        mdc = so2.max_daily_contributions[0]
        assert (mdc.upper_rank, mdc.lower_rank, mdc.threshold) == (4, 4, None)
        assert [f.filename for f in so2.max_daily_files] == ["design_maxdaily.dat"]
        assert [f.filename for f in so2.max_daily_by_year_files] == ["design_mxdybyyr.dat"]

        pm = naaqs_output_pathway("PM2.5", source_group="STK", stem="pm")
        assert pm.max_daily_contributions[0].upper_rank == 8
        assert pm.max_daily_files[0].source_group == "STK"
        assert pm.max_daily_files[0].filename == "pm_maxdaily.dat"

    def test_thresh_form_widens_the_rectable_range(self):
        from pyaermod.design_values import naaqs_output_pathway
        no2 = naaqs_output_pathway("NO2", threshold=188.0)
        mdc = no2.max_daily_contributions[0]
        assert (mdc.upper_rank, mdc.lower_rank, mdc.threshold) == (8, None, 188.0)
        # ouset.f E273: the range must exceed the design rank plus 4.
        assert no2.receptor_table_rank == 13
        assert naaqs_output_pathway("NO2", threshold=188.0, receptor_table_rank=25).receptor_table_rank == 25

    def test_validator_accepts_the_generated_pathway(self):
        from pyaermod.design_values import naaqs_output_pathway
        from pyaermod.input_generator import (
            AERMODProject,
            CartesianGrid,
            ControlPathway,
            MeteorologyPathway,
            PointSource,
            ReceptorPathway,
            SourcePathway,
        )
        from pyaermod.validator import Validator
        sources = SourcePathway()
        sources.add_source(PointSource("S", 0.0, 0.0, stack_height=30.0, stack_diameter=1.5,
                                       stack_temp=400.0, exit_velocity=10.0, emission_rate=1.0))
        project = AERMODProject(
            control=ControlPathway(title_one="t", pollutant_id="NO2", averaging_periods=["1"]),
            sources=sources, receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=naaqs_output_pathway("NO2", threshold=188.0),
        )
        result = Validator.validate(project, advanced=False)
        assert not [e for e in result.errors if e.severity == "error"], str(result)

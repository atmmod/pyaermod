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
        out = add_background(df, bg)
        ones = out[out["date"] == "20010101"]
        rest = out[out["date"] != "20010101"]
        assert (ones["concentration"] == 100.0).all()
        assert (rest["concentration"] == 1.0).all()

    def test_series_keyed_by_date(self):
        df = _hourly_postfile(years=(2020,), concentration_value=2.0)
        bg = pd.Series({"20010101": 8.0, "20010102": 4.0})
        out = add_background(df, bg)
        a = out[out["date"] == "20010101"]["concentration"].iloc[0]
        b = out[out["date"] == "20010102"]["concentration"].iloc[0]
        c = out[out["date"] == "20010103"]["concentration"].iloc[0]
        assert a == 10.0  # 2 + 8
        assert b == 6.0   # 2 + 4
        assert c == 2.0   # unchanged


class TestAnnualMean:
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
    def test_h2h_form(self):
        df = _hourly_postfile(years=(2020,), receptors=((1.0, 0.0),),
                              concentration_value=20.0)
        # Inject two distinct daily peaks: one at 100, one at 80
        df.loc[(df["date"].str.startswith("200101")) &
               (df["date"].str.endswith("12")), "concentration"] = 100.0
        df.loc[(df["date"].str.startswith("200201")) &
               (df["date"].str.endswith("12")), "concentration"] = 80.0
        out = pm10_24hr_design_value(df)
        # H2H (2nd highest daily-max) should be 80
        assert out["concentration"].iloc[0] == pytest.approx(80.0)


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
        df = _hourly_postfile(concentration_value=75.0)
        rpt = naaqs_compliance_report("SO2", df)
        # equal to standard does not exceed (strict >)
        assert (~rpt["exceeds"]).all()

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

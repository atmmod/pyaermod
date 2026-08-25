"""Known-answer tests for the EPA rank-based NAAQS percentiles.

The NAAQS percentile forms are order statistics selected from a lookup
table, not interpolated quantiles. These tests pin the tables as they
appear in the regulation and then pin the design values they produce on
series whose answer can be read off by hand.

Sources (transcribed from the CFR text, not paraphrased):

* 40 CFR part 50, appendix N, Table 1 -- 24-hour PM2.5, 98th percentile.
* 40 CFR part 50, appendix S, Table 1 -- 1-hour NO2, 98th percentile.
  Same ranks as appendix N.
* 40 CFR part 50, appendix T, Table 1 -- 1-hour SO2, 99th percentile.

Each appendix says the same thing: sort the year's daily values from
highest to lowest, look the year's count of valid days up in the table,
and take the n-th value from the top.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from pyaermod.design_values import (
    PERCENTILE_98_RANK_TABLE,
    PERCENTILE_99_RANK_TABLE,
    naaqs_percentile_rank,
    no2_1hr_design_value,
    nth_highest_daily_max_design_value,
    pm25_24hr_design_value,
    so2_1hr_design_value,
)

# --- The regulatory tables, written out as (days_low, days_high, rank). ---

# 40 CFR 50 app. N Table 1 / app. S Table 1.
CFR_98TH_TABLE = [
    (1, 50, 1),
    (51, 100, 2),
    (101, 150, 3),
    (151, 200, 4),
    (201, 250, 5),
    (251, 300, 6),
    (301, 350, 7),
    (351, 366, 8),
]

# 40 CFR 50 app. T Table 1.
CFR_99TH_TABLE = [
    (1, 100, 1),
    (101, 200, 2),
    (201, 300, 3),
    (301, 366, 4),
]


class TestRankTables:
    @pytest.mark.parametrize("low,high,rank", CFR_98TH_TABLE)
    def test_98th_matches_cfr_for_every_day_count(self, low, high, rank):
        for n in range(low, high + 1):
            assert naaqs_percentile_rank(n, 98.0) == rank, n

    @pytest.mark.parametrize("low,high,rank", CFR_99TH_TABLE)
    def test_99th_matches_cfr_for_every_day_count(self, low, high, rank):
        for n in range(low, high + 1):
            assert naaqs_percentile_rank(n, 99.0) == rank, n

    def test_module_table_matches_the_cfr_table(self):
        assert list(PERCENTILE_98_RANK_TABLE) == [
            (high, rank) for _, high, rank in CFR_98TH_TABLE
        ]
        assert list(PERCENTILE_99_RANK_TABLE) == [
            (high, rank) for _, high, rank in CFR_99TH_TABLE
        ]

    def test_full_year_landmarks(self):
        # The two ranks a regulatory modeller actually quotes.
        assert naaqs_percentile_rank(365, 98.0) == 8
        assert naaqs_percentile_rank(366, 98.0) == 8
        assert naaqs_percentile_rank(365, 99.0) == 4
        assert naaqs_percentile_rank(366, 99.0) == 4

    def test_rejects_impossible_inputs(self):
        with pytest.raises(ValueError):
            naaqs_percentile_rank(0, 98.0)
        with pytest.raises(ValueError):
            naaqs_percentile_rank(365, 100.0)
        with pytest.raises(ValueError):
            naaqs_percentile_rank(365, 0.0)


# ---------------------------------------------------------------------
# Design values on hand-computable series
# ---------------------------------------------------------------------

def _hourly_year(year: int, daily_peaks, *, receptor=(0.0, 0.0),
                 baseline=0.0, ave="1-HR"):
    """Hourly POSTFILE rows whose day *i* peaks at ``daily_peaks[i]``.

    Every day gets 24 hours: hour 12 carries the peak, the rest carry
    ``baseline``. The daily maximum is therefore the peak and the
    24-hour average is ``(peak + 23 * baseline) / 24``.
    """
    x, y = receptor
    days = pd.date_range(f"{year}-01-01", periods=len(daily_peaks), freq="D")
    rows = []
    for day, peak in zip(days, daily_peaks):
        for hour in range(1, 25):
            rows.append({
                "x": x, "y": y,
                "concentration": float(peak) if hour == 12 else float(baseline),
                "zelev": 0.0, "zhill": 0.0, "zflag": 0.0,
                "ave": ave, "grp": "ALL",
                "date": f"{year % 100:02d}{day.month:02d}{day.day:02d}{hour:02d}",
            })
    return pd.DataFrame(rows)


class TestDesignValuesOnRankedSeries:
    """A year of 365 strictly-decreasing daily peaks: 365, 364, ... 1.

    The k-th highest daily value is exactly ``366 - k``, so every
    expected number below is arithmetic, not a recorded output.
    """

    @staticmethod
    def _three_years():
        peaks = list(range(365, 0, -1))
        return pd.concat(
            [_hourly_year(y, peaks) for y in (2017, 2018, 2019)],
            ignore_index=True,
        )

    def test_no2_is_the_eighth_highest_daily_max(self):
        out = no2_1hr_design_value(self._three_years())
        assert out["concentration"].iloc[0] == pytest.approx(365 - 8 + 1)
        assert out["n_years"].iloc[0] == 3

    def test_so2_is_the_fourth_highest_daily_max(self):
        out = so2_1hr_design_value(self._three_years())
        assert out["concentration"].iloc[0] == pytest.approx(365 - 4 + 1)

    def test_not_an_interpolated_quantile(self):
        # pandas' default linear-interpolation quantile lands between the
        # 8th and 9th highest and returns a value the CFR never defines.
        # This asserts the two disagree, so a silent revert to
        # Series.quantile() fails here instead of shipping.
        peaks = pd.Series(range(365, 0, -1), dtype=float)
        interpolated = peaks.quantile(0.98, interpolation="linear")
        assert interpolated != pytest.approx(358.0)
        out = no2_1hr_design_value(self._three_years())
        assert out["concentration"].iloc[0] == pytest.approx(358.0)

    def test_short_year_moves_the_rank_up_the_list(self):
        # 200 days -> appendix S Table 1 row "151-200" -> 4th highest.
        assert naaqs_percentile_rank(200, 98.0) == 4
        df = _hourly_year(2019, list(range(200, 0, -1)))
        with pytest.warns(UserWarning, match="covers 1"):
            out = no2_1hr_design_value(df, n_years=3)
        assert out["concentration"].iloc[0] == pytest.approx(200 - 4 + 1)

    def test_design_value_averages_annual_ranks_not_the_pooled_record(self):
        # Three years whose 8th-highest values are 358, 258 and 158.
        # Averaging the annual ranks gives 258; ranking the pooled
        # 1095-day record would give a rank-8 value of 361.
        frames = [
            _hourly_year(2017, list(range(365, 0, -1))),
            _hourly_year(2018, [v - 100 for v in range(365, 0, -1)]),
            _hourly_year(2019, [v - 200 for v in range(365, 0, -1)]),
        ]
        out = no2_1hr_design_value(pd.concat(frames, ignore_index=True))
        assert out["concentration"].iloc[0] == pytest.approx(
            (358.0 + 258.0 + 158.0) / 3.0
        )


class TestPm25UsesTheDailyAverage:
    def test_hourly_input_is_averaged_over_the_day(self):
        # One hour at 240 and 23 hours at 0 is a 24-hour average of 10,
        # not a 24-hour value of 240.
        peaks = [240.0] * 365
        df = pd.concat(
            [_hourly_year(y, peaks, baseline=0.0) for y in (2017, 2018, 2019)],
            ignore_index=True,
        )
        out = pm25_24hr_design_value(df)
        assert out["concentration"].iloc[0] == pytest.approx(10.0)

    def test_daily_input_passes_through(self):
        # AERMOD AVE='24-HR' rows are block averages, one per day.
        peaks = list(range(365, 0, -1))
        frames = []
        for y in (2017, 2018, 2019):
            f = _hourly_year(y, peaks, ave="24-HR")
            frames.append(f[f["date"].str.endswith("24")].assign(
                concentration=[float(p) for p in peaks]
            ))
        out = pm25_24hr_design_value(pd.concat(frames, ignore_index=True))
        assert out["concentration"].iloc[0] == pytest.approx(358.0)


class TestGeneralNthHighestForm:
    def test_rank_one_is_the_annual_maximum(self):
        peaks = list(range(365, 0, -1))
        df = pd.concat(
            [_hourly_year(y, peaks) for y in (2018, 2019)], ignore_index=True
        )
        out = nth_highest_daily_max_design_value(df, rank=1)
        assert out["concentration"].iloc[0] == pytest.approx(365.0)
        assert out["n_years"].iloc[0] == 2

    def test_rank_matches_the_percentile_helper(self):
        peaks = list(range(365, 0, -1))
        df = pd.concat(
            [_hourly_year(y, peaks) for y in (2017, 2018, 2019)],
            ignore_index=True,
        )
        rank = naaqs_percentile_rank(365, 98.0)
        general = nth_highest_daily_max_design_value(df, rank=rank)
        specific = no2_1hr_design_value(df)
        assert general["concentration"].iloc[0] == pytest.approx(
            specific["concentration"].iloc[0]
        )

    def test_rejects_rank_below_one(self):
        df = _hourly_year(2019, [1.0, 2.0])
        with pytest.raises(ValueError, match="rank must be"):
            nth_highest_daily_max_design_value(df, rank=0)


class TestClosedFormMatchesTables:
    def test_ceiling_formula_reproduces_both_tables(self):
        # Integer ceiling division -- deliberately not math.ceil(0.02 * n),
        # whose binary rounding breaks on every exact table boundary.
        for n in range(1, 367):
            assert naaqs_percentile_rank(n, 98.0) == -(-n * 2 // 100)
            assert naaqs_percentile_rank(n, 99.0) == -(-n * 1 // 100)

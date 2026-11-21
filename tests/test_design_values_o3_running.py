"""Ozone design values from running 8-hour means (40 CFR 50 Appendix U 3(b)-(d)).

A YYMMDDHH stamp names the hour ending at HH, so the hour Appendix U
calls 07:00 is the row stamped 08.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pyaermod import design_values as dv
from pyaermod.naaqs import get_naaqs

LEVEL = get_naaqs("O3", "8-hour").level_ugm3


def _hourly(start="2019-01-01", days=365, value=0.0, receptors=((0.0, 0.0),)):
    """An hourly frame; ``start_hour`` is each row's hour-beginning time."""
    t = pd.date_range(start, periods=24 * days, freq="h")
    one = pd.DataFrame({
        "start_hour": t,
        "date": [f"{s:%y%m%d}{s.hour + 1:02d}" for s in t],
        "concentration": float(value), "ave": "1-HR", "grp": "ALL",
    })
    return pd.concat([one.assign(x=x, y=y) for x, y in receptors], ignore_index=True)


def _set(f, first_hour, n, value, x=None):
    """Set ``n`` hours starting at ``first_hour`` (hour-beginning) to ``value``."""
    t0 = pd.Timestamp(first_hour)
    hit = (f["start_hour"] >= t0) & (f["start_hour"] < t0 + pd.Timedelta(hours=n))
    if x is not None:
        hit &= f["x"] == x
    f.loc[hit, "concentration"] = value


def _daily(f, level=LEVEL):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = dv._o3_daily_max(f, level)
    return out.set_index("date")["concentration"]


def _quiet(func, *args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return func(*args, **kwargs)


def test_the_design_value_uses_running_means_not_fixed_blocks():
    f = _hourly()
    # Eight hours from 12:00 on four days: the running mean reaches 80,
    # while the blocks ending at hours 16 and 24 each hold four of them (40).
    for day in ("2019-06-01", "2019-06-10", "2019-07-04", "2019-08-15"):
        _set(f, f"{day} 12:00", 8, 80.0)
    out = _quiet(dv.o3_8hr_design_value, f, n_years=1)
    assert out["concentration"].iloc[0] == pytest.approx(80.0)
    assert "running" in out["form"].iloc[0]
    assert int(out["n_years"].iloc[0]) == 1


def test_a_mean_belongs_to_the_day_of_its_first_hour():
    f = _hourly(days=30)
    # 23:00 on the 10th to 07:00 on the 11th: the last of the 10th's 17 means.
    _set(f, "2019-01-10 23:00", 8, 80.0)
    daily = _daily(f)
    assert daily[pd.Timestamp("2019-01-10")] == pytest.approx(80.0)
    assert daily[pd.Timestamp("2019-01-11")] == pytest.approx(0.0)


def test_means_starting_before_0700_are_not_a_days_maximum():
    f = _hourly(days=30)
    _set(f, "2019-01-10 02:00", 8, 80.0)   # 02:00 to 10:00
    daily = _daily(f)
    # The 10th's first counted mean starts at 07:00 and holds three of the hours.
    assert daily[pd.Timestamp("2019-01-10")] == pytest.approx(3 * 80.0 / 8)
    # The 9th's last mean, 23:00 to 07:00, holds five of them.
    assert daily[pd.Timestamp("2019-01-09")] == pytest.approx(5 * 80.0 / 8)


def test_a_mean_with_six_hours_divides_by_the_hours_present():
    f = _hourly(days=30)
    _set(f, "2019-01-10 10:00", 8, 40.0)
    f.loc[f["start_hour"].isin([pd.Timestamp("2019-01-10 12:00"),
                                pd.Timestamp("2019-01-10 13:00")]), "concentration"] = 100.0
    gone = f["start_hour"].isin([pd.Timestamp("2019-01-10 10:00"),
                                 pd.Timestamp("2019-01-10 11:00")])
    daily = _daily(f[~gone])
    # 10:00 to 18:00 keeps six hours: (2 * 100 + 4 * 40) / 6.
    assert daily[pd.Timestamp("2019-01-10")] == pytest.approx(360.0 / 6)


def test_a_mean_with_five_hours_is_valid_only_above_the_level():
    f = _hourly(days=30)
    keep = ~((f["start_hour"] >= "2019-01-10 00:00") & (f["start_hour"] < "2019-01-11 07:00"))
    five = (f["start_hour"] >= "2019-01-10 12:00") & (f["start_hour"] < "2019-01-10 17:00")
    low = f[keep | five].copy()
    low.loc[low["start_hour"].dt.normalize() == "2019-01-10", "concentration"] = 100.0
    assert pd.Timestamp("2019-01-10") not in _daily(low).index   # 500 / 8 is under 137.3
    high = low.copy()
    high.loc[high["start_hour"].dt.normalize() == "2019-01-10", "concentration"] = 300.0
    # 1500 / 8 with the missing hours as zero is above the level: a valid mean and day.
    assert _daily(high)[pd.Timestamp("2019-01-10")] == pytest.approx(1500.0 / 8)


def test_a_day_needs_13_of_its_17_means_unless_it_is_above_the_level():
    f = _hourly(days=30, value=10.0)
    # Keep 07:00 to 19:00 on the 10th: only the seven means starting 07:00 to 13:00
    # have six hours.
    gone = (f["start_hour"] >= "2019-01-10 19:00") & (f["start_hour"] < "2019-01-11 07:00")
    with pytest.warns(UserWarning, match="13 of the 17"):
        daily = dv._o3_daily_max(f[~gone], LEVEL)
    assert pd.Timestamp("2019-01-10") not in set(daily["date"])
    high = f[~gone].copy()
    _set(high, "2019-01-10 07:00", 8, 200.0)
    assert _daily(high)[pd.Timestamp("2019-01-10")] == pytest.approx(200.0)


def test_the_last_day_of_the_record_is_left_out_without_a_warning():
    f = _hourly(days=30, value=10.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        daily = dv._o3_daily_max(f, LEVEL)
    assert daily["date"].max() == pd.Timestamp("2019-01-29")
    assert len(daily) == 29


def test_each_receptor_keeps_its_own_series(monkeypatch):
    f = _hourly(days=40, receptors=((0.0, 0.0), (100.0, 0.0), (200.0, 50.0)))
    for i, x in enumerate((0.0, 100.0)):
        for day in ("05", "09", "14", "21"):
            _set(f, f"2019-01-{day} 11:00", 8, 50.0 + 10 * i, x=x)
    f = f.sample(frac=1.0, random_state=1)                 # row order must not matter
    expected = {(0.0, 0.0): 50.0, (100.0, 0.0): 60.0, (200.0, 50.0): 0.0}
    for cells in (dv._O3_GRID_CELLS, 1):                   # one grid, then one receptor at a time
        monkeypatch.setattr(dv, "_O3_GRID_CELLS", cells)
        out = _quiet(dv.o3_8hr_design_value, f, n_years=1)
        got = {(r.x, r.y): r.concentration for r in out.itertuples()}
        assert got == pytest.approx(expected)


def test_three_years_are_ranked_separately_and_averaged():
    f = _hourly(start="2018-01-01", days=3 * 365)
    for year, value in ((2018, 60.0), (2019, 90.0), (2020, 120.0)):
        for day in ("06-01", "06-10", "07-04", "08-15"):
            _set(f, f"{year}-{day} 12:00", 8, value)
    out = _quiet(dv.o3_8hr_design_value, f)
    assert out["concentration"].iloc[0] == pytest.approx(90.0)
    assert int(out["n_years"].iloc[0]) == 3


def test_block_averages_are_still_read_with_a_warning():
    t = pd.date_range("2019-01-01", periods=365 * 3, freq="8h")
    f = pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": np.arange(len(t), dtype=float),
                      "date": [f"{s:%y%m%d}{s.hour + 8:02d}" for s in t],
                      "ave": "8-HR", "grp": "ALL"})
    with pytest.warns(UserWarning, match="running 8-hour means"):
        out = dv.o3_8hr_design_value(f, n_years=1)
    assert out["concentration"].iloc[0] == pytest.approx(len(t) - 1 - 9)   # 4th-highest day
    assert "blocks" in out["form"].iloc[0]


def test_mixed_averaging_periods_are_refused():
    f = _hourly(days=30)
    f.loc[f.index[:3], "ave"] = "8-HR"
    with pytest.raises(ValueError, match="one averaging period"):
        dv.o3_8hr_design_value(f)


def test_the_compliance_report_takes_hourly_ozone():
    f = _hourly()
    for day in ("2019-06-01", "2019-06-10", "2019-07-04", "2019-08-15"):
        _set(f, f"{day} 12:00", 8, 150.0)
    rpt = _quiet(dv.naaqs_compliance_report, "O3", f, n_years=1)
    assert rpt["design_value"].iloc[0] == pytest.approx(150.0)
    assert bool(rpt["exceeds"].iloc[0])


def test_the_secondary_annual_so2_standard_is_the_mean_of_the_annual_means():
    f = _hourly(start="2018-01-01", days=3 * 365, value=20.0)
    f.loc[f["start_hour"].dt.year == 2020, "concentration"] = 50.0
    rpt = _quiet(dv.naaqs_compliance_report, "SO2_annual", f)
    assert rpt["design_value"].iloc[0] == pytest.approx(30.0)
    assert rpt["naaqs_level"].iloc[0] == 10.0
    assert "50.21" in rpt["cfr_reference"].iloc[0]
    assert bool(rpt["exceeds"].iloc[0])          # 10 ppb is 26.2 ug/m3

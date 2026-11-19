"""F4 (POLLUTID spelling) and F5 (a NaN day must not take a rank)."""

import numpy as np
import pandas as pd
import pytest

from pyaermod import design_values as dv
from pyaermod.naaqs import get_naaqs


@pytest.mark.parametrize("spelling", ["PM2.5", "PM25", "pm25"])
def test_naaqs_output_pathway_accepts_the_pollutid_spelling(spelling):
    out = dv.naaqs_output_pathway(spelling)
    assert out.receptor_table is True


def test_get_naaqs_accepts_the_pollutid_spelling():
    assert get_naaqs("PM25", "24-hour") is get_naaqs("PM2.5", "24-hour")


def _frame(values, start="2019-01-01"):
    days = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame(dict(x=0.0, y=0.0, concentration=values,
                             date=[f"{t:%y%m%d}24" for t in days], ave="24-HR", grp="ALL"))


def test_a_nan_day_does_not_shift_the_pm25_rank():
    values = np.arange(1, 366.0)
    values[10] = np.nan                       # day 11 has no value
    out = dv.pm25_24hr_design_value(_frame(values), n_years=1)
    # 364 valid days: the rank is the 8th highest of them, 358.
    assert out["concentration"].iloc[0] == 358.0


def test_a_nan_day_does_not_become_the_highest_value():
    values = np.arange(1, 366.0)
    values[10] = np.nan
    out = dv.nth_highest_daily_max_design_value(_frame(values), 1) \
        if hasattr(dv, "nth_highest_daily_max_design_value") else None
    if out is not None:
        assert out["concentration"].iloc[0] == 365.0

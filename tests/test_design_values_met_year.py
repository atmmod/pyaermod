"""F3: a met year that does not run January to December must not be split into two years.

AERMOD's year ends on the anniversary of its first met hour (meset.f IENDMN/IENDDY/IENDHOUR,
aermod.f CHK_ENDYR); the design value code groups by calendar year. Either the code is told
the year boundary, or it must at least say that it saw partial years. This test accepts both:
the value of one full year, or a warning that names the partial years.
"""

import warnings

import numpy as np
import pandas as pd

from pyaermod import design_values as dv


def _frame(values, start):
    days = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame(dict(x=0.0, y=0.0, concentration=values,
                             date=[f"{t:%y%m%d}24" for t in days], ave="24-HR", grp="ALL"))


def _says_partial(caught):
    return any("partial" in str(w.message).lower() for w in caught)


def test_one_july_to_june_year_is_ranked_as_one_year():
    f = _frame(np.arange(1, 366.0), "2019-07-01")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = dv.pm25_24hr_design_value(f, n_years=1)
    # 98th percentile of 365 days is the 8th highest: 358.
    assert out["concentration"].iloc[0] == 358.0 or _says_partial(caught)


def test_pm10_does_not_count_four_july_to_june_years_as_five():
    f = _frame(np.arange(1, 4 * 365 + 1, dtype=float)[::-1], "2019-07-01")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = dv.pm10_24hr_design_value(f)
    assert int(out["n_years"].iloc[0]) <= 4 or _says_partial(caught)

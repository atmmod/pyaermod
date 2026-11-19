"""F6 (part): o3_8hr_design_value silently accepts hourly rows and returns the highest hour.

Whether AERMOD's fixed 8-hour blocks (aermod.f ~1854, MOD(IHOUR,KAVE)) may stand in for
Appendix U's running 8-hour mean is the maintainer's call, so no test pins it.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pyaermod import design_values as dv


def test_hourly_rows_are_not_taken_for_8_hour_averages():
    hours = pd.date_range("2019-01-01", periods=24 * 365, freq="h")
    stamps = [f"{t:%y%m%d}{t.hour + 1:02d}" for t in hours]
    f = pd.DataFrame(dict(x=0.0, y=0.0, concentration=np.arange(len(hours), dtype=float),
                          date=stamps, ave="1-HR", grp="ALL"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            dv.o3_8hr_design_value(f, n_years=1)
        except ValueError:
            return
    assert any("8" in str(w.message) for w in caught), "1-HR input was accepted silently"

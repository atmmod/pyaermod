"""Tests for the NAAQS reference table."""

from __future__ import annotations

import pytest

from pyaermod.naaqs import NAAQS_TABLE, get_naaqs


class TestTableShape:
    def test_all_pollutants_have_entries(self):
        for pol, rows in NAAQS_TABLE.items():
            assert rows, f"NAAQS_TABLE[{pol!r}] is empty"
            for r in rows:
                assert r.level > 0
                assert r.units in {"ug/m3", "ppb"}
                assert r.cfr_reference.startswith("40 CFR 50.")

    def test_pm25_24hr_is_35(self):
        rows = NAAQS_TABLE["PM2.5"]
        h24 = next(r for r in rows if r.averaging_period == "24-hour")
        assert h24.level == 35.0
        assert h24.form == "98th percentile"

    def test_pm25_annual_is_9_post_2024(self):
        rows = NAAQS_TABLE["PM2.5"]
        annual = next(r for r in rows if r.averaging_period == "annual")
        assert annual.level == 9.0

    def test_no2_1hr_is_100(self):
        h1 = get_naaqs("NO2", "1-hour")
        assert h1.level == 100.0
        assert h1.units == "ppb"

    def test_so2_1hr_is_75(self):
        h1 = get_naaqs("SO2", "1-hour")
        assert h1.level == 75.0

    def test_o3_8hr_is_70(self):
        h8 = get_naaqs("O3", "8-hour")
        assert h8.level == 70.0

    def test_pm10_24hr_is_150(self):
        h24 = get_naaqs("PM10", "24-hour")
        assert h24.level == 150.0


class TestLookup:
    def test_case_insensitive_pollutant(self):
        a = get_naaqs("pm2.5", "24-hour")
        b = get_naaqs("PM2.5", "24-hour")
        assert a == b

    def test_case_insensitive_period(self):
        a = get_naaqs("NO2", "1-HOUR")
        b = get_naaqs("NO2", "1-hour")
        assert a == b

    def test_unknown_pollutant_raises(self):
        with pytest.raises(KeyError, match="No NAAQS entries"):
            get_naaqs("XENON", "1-hour")

    def test_unknown_period_lists_alternatives(self):
        with pytest.raises(KeyError, match="available"):
            get_naaqs("PM2.5", "minutely")


class TestAveragingPeriods:
    """naaqs_averaging_periods: the AVERTIME tokens a pollutant's NAAQS need."""

    @pytest.mark.parametrize(("pollutant", "periods"), [
        ("SO2", ["1"]),
        ("NO2", ["1", "ANNUAL"]),
        ("PM25", ["24", "ANNUAL"]),       # POLLUTID spelling
        ("PM2.5", ["24", "ANNUAL"]),      # table spelling
        ("PM10", ["24"]),
        ("CO", ["1", "8"]),
        ("O3", ["8"]),
        ("PB", ["MONTH"]),
        (" no2 ", ["1", "ANNUAL"]),
        ("OTHER", []),
    ])
    def test_periods(self, pollutant, periods):
        from pyaermod.naaqs import naaqs_averaging_periods
        assert naaqs_averaging_periods(pollutant) == periods

    def test_every_table_period_has_a_token(self):
        from pyaermod.naaqs import NAAQS_TABLE, naaqs_averaging_periods
        for key, rows in NAAQS_TABLE.items():
            assert len(naaqs_averaging_periods(key)) == len({r.averaging_period for r in rows})


class TestUnits:
    """Levels in µg/m³, the unit AERMOD reports concentrations in."""

    @pytest.mark.parametrize(("pollutant", "period", "ugm3"), [
        # EPA's own round figures: 75 ppb SO2 = 196.4 µg/m³ (the 2010 SO2
        # NAAQS rule), 100 ppb NO2 = 188 µg/m³, 35 ppm CO = 40 mg/m³,
        # 70 ppb O3 = 137 µg/m³.
        ("SO2", "1-hour", 196.4),
        ("NO2", "1-hour", 188.0),
        ("CO", "1-hour", 40071.5),
        ("O3", "8-hour", 137.3),
    ])
    def test_ppb_standards_convert_at_25_c(self, pollutant, period, ugm3):
        assert get_naaqs(pollutant, period).level_ugm3 == pytest.approx(ugm3, abs=0.05)

    def test_ug_standards_are_unchanged(self):
        assert get_naaqs("PM2.5", "24-hour").level_ugm3 == 35.0
        assert get_naaqs("Pb", "rolling 3-month").level_ugm3 == 0.15

    def test_ppb_to_ugm3(self):
        from pyaermod.naaqs import ppb_to_ugm3
        assert ppb_to_ugm3("so2", 1.0) == pytest.approx(64.064 / 24.465)
        with pytest.raises(KeyError, match="no molecular weight"):
            ppb_to_ugm3("PM10", 1.0)

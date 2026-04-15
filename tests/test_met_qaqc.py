"""Tests for met_qaqc module."""

from __future__ import annotations

import pytest

from pyaermod.met_qaqc import (
    QAQCFinding,
    QAQCReport,
    check_extremes,
    check_low_wind_bias,
    check_missing_data,
    check_profile_monotonic,
    check_stability_consistency,
    find_missing_runs,
    run_all_qaqc,
)


def _make_records(n, ws=5.0, wd=180.0, temp=15.0, **overrides):
    records = []
    for i in range(n):
        r = {
            "wind_speed_ms": ws,
            "wind_dir": wd,
            "temp_c": temp,
        }
        for k, v in overrides.items():
            r[k] = v
        records.append(dict(r))
    return records


class TestFindMissingRuns:
    def test_no_missing(self):
        recs = _make_records(10)
        assert find_missing_runs(recs, "wind_speed_ms") == []

    def test_run_at_start(self):
        recs = _make_records(10)
        for i in range(6):
            recs[i]["wind_speed_ms"] = None
        runs = find_missing_runs(recs, "wind_speed_ms", min_run=6)
        assert runs == [(0, 5, 6)]

    def test_run_at_end(self):
        recs = _make_records(10)
        for i in range(4, 10):
            recs[i]["wind_speed_ms"] = None
        runs = find_missing_runs(recs, "wind_speed_ms", min_run=6)
        assert runs == [(4, 9, 6)]

    def test_short_runs_ignored(self):
        recs = _make_records(10)
        recs[3]["wind_speed_ms"] = None
        recs[4]["wind_speed_ms"] = None
        runs = find_missing_runs(recs, "wind_speed_ms", min_run=6)
        assert runs == []


class TestCheckMissingData:
    def test_below_threshold_is_info(self):
        recs = _make_records(100)
        recs[0]["wind_speed_ms"] = None
        rep = check_missing_data(recs, max_missing_fraction=0.10)
        assert rep.n_errors == 0
        assert any(f.category == "missing" and f.level == "info" for f in rep.findings)

    def test_over_threshold_is_error(self):
        recs = _make_records(100)
        for i in range(20):
            recs[i]["wind_speed_ms"] = None
        rep = check_missing_data(recs, max_missing_fraction=0.10)
        assert rep.n_errors >= 1

    def test_long_gap_warns(self):
        recs = _make_records(100)
        for i in range(50):
            recs[i]["wind_speed_ms"] = None
        rep = check_missing_data(recs, max_missing_fraction=0.60, long_run_hours=24)
        warns = [f for f in rep.findings if f.level == "warning" and f.category == "missing"]
        assert len(warns) >= 1


class TestCheckExtremes:
    def test_bad_wind_dir_errors(self):
        recs = _make_records(1, wd=-10)
        rep = check_extremes(recs)
        assert rep.n_errors == 1

    def test_absurd_temperature_errors(self):
        recs = _make_records(1, temp=500.0)
        rep = check_extremes(recs)
        assert rep.n_errors == 1

    def test_tiny_L_warning(self):
        recs = _make_records(1)
        recs[0]["monin_obukhov_m"] = 0.1
        rep = check_extremes(recs)
        assert any(f.category == "extreme" and f.level == "warning" for f in rep.findings)

    def test_normal_values_clean(self):
        recs = _make_records(5)
        rep = check_extremes(recs)
        assert rep.n_errors == 0

    def test_non_numeric_flagged(self):
        recs = [{"wind_speed_ms": "abc", "wind_dir": 90, "temp_c": 15}]
        rep = check_extremes(recs)
        assert rep.n_errors == 1


class TestCheckStabilityConsistency:
    def test_cbl_with_zero_zic_warns(self):
        recs = [{"monin_obukhov_m": -50.0, "convective_mix_height_m": 0,
                 "mechanical_mix_height_m": 500.0}]
        rep = check_stability_consistency(recs)
        assert rep.n_warnings == 1

    def test_sbl_with_nonzero_zic_warns(self):
        recs = [{"monin_obukhov_m": 50.0, "convective_mix_height_m": 300.0,
                 "mechanical_mix_height_m": 100.0}]
        rep = check_stability_consistency(recs)
        assert rep.n_warnings == 1

    def test_consistent_cbl_clean(self):
        recs = [{"monin_obukhov_m": -30.0, "convective_mix_height_m": 1200.0,
                 "mechanical_mix_height_m": 500.0}]
        rep = check_stability_consistency(recs)
        assert len(rep.findings) == 0

    def test_missing_L_skipped(self):
        recs = [{"convective_mix_height_m": 0, "mechanical_mix_height_m": 500.0}]
        rep = check_stability_consistency(recs)
        assert len(rep.findings) == 0


class TestCheckLowWindBias:
    def test_high_calm_fraction_warns(self):
        recs = _make_records(100, ws=0.2)
        rep = check_low_wind_bias(recs)
        assert rep.n_warnings == 1

    def test_normal_winds_clean(self):
        recs = _make_records(100, ws=5.0)
        rep = check_low_wind_bias(recs)
        assert rep.n_warnings == 0

    def test_no_valid_wind_errors(self):
        recs = _make_records(10, ws=None)
        rep = check_low_wind_bias(recs)
        assert rep.n_errors == 1

    def test_empty_is_clean(self):
        assert check_low_wind_bias([]).findings == []


class TestCheckProfileMonotonic:
    def test_decreasing_clean(self):
        levels = [{"pressure_pa": 100000}, {"pressure_pa": 85000}, {"pressure_pa": 50000}]
        rep = check_profile_monotonic(levels)
        assert rep.n_errors == 0

    def test_reversal_errors(self):
        levels = [{"pressure_pa": 100000}, {"pressure_pa": 85000}, {"pressure_pa": 90000}]
        rep = check_profile_monotonic(levels)
        assert rep.n_errors == 1

    def test_missing_pressure_skipped(self):
        levels = [{"pressure_pa": 100000}, {"pressure_pa": None}, {"pressure_pa": 50000}]
        rep = check_profile_monotonic(levels)
        assert rep.n_errors == 0


class TestRunAllQAQC:
    def test_all_checks_merged(self):
        recs = _make_records(100, ws=0.1, temp=-90.0)  # low-wind + extreme cold
        rep = run_all_qaqc(recs)
        assert rep.n_records == 100
        assert rep.n_warnings >= 1
        assert rep.n_errors >= 1

    def test_empty_input(self):
        rep = run_all_qaqc([])
        assert rep.n_records == 0


class TestQAQCReport:
    def test_summary_format(self):
        rep = QAQCReport(n_records=100, n_missing=5)
        s = rep.summary()
        assert "100 records" in s and "5 missing" in s

    def test_dump_truncates(self):
        rep = QAQCReport(n_records=10)
        for i in range(5):
            rep.findings.append(QAQCFinding(level="info", category="extreme", message=f"msg {i}"))
        text = rep.dump(limit=2)
        assert "2 more findings" in text or "3 more findings" in text

    def test_by_category(self):
        rep = QAQCReport(n_records=1)
        rep.findings.append(QAQCFinding(level="warning", category="missing", message="a"))
        rep.findings.append(QAQCFinding(level="warning", category="extreme", message="b"))
        assert len(rep.by_category("missing")) == 1
        assert len(rep.by_category("extreme")) == 1

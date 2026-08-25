"""Smoke-tests for benchmarks/run_benchmarks.py and compare_benchmarks.py."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
RUN = REPO / "benchmarks" / "run_benchmarks.py"
CMP = REPO / "benchmarks" / "compare_benchmarks.py"


def _write(path, ms_by_name):
    data = {
        "pyaermod_version": "0",
        "timestamp": "x",
        "results": [
            {"name": k, "ms_per_call": v, "calls_per_sec": 1.0, "n": 1}
            for k, v in ms_by_name.items()
        ],
    }
    path.write_text(json.dumps(data))


def _compare(tmp_path, base, curr, *extra):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write(a, base)
    _write(b, curr)
    return subprocess.run(
        [sys.executable, str(CMP), "--baseline", str(a), "--current", str(b),
         "--fail-on-regression", *extra],
        capture_output=True, text=True,
    )


class TestRunBenchmarks:
    def test_emits_valid_json(self, tmp_path):
        out = tmp_path / "r.json"
        subprocess.run(
            [sys.executable, str(RUN), "--output", str(out), "--quiet", "--rounds", "2"],
            check=True, capture_output=True,
        )
        data = json.loads(out.read_text())
        assert "pyaermod_version" in data
        assert data["rounds"] == 2
        assert "results" in data and len(data["results"]) > 0
        for r in data["results"]:
            for field in ("name", "ms_per_call", "calls_per_sec", "n"):
                assert field in r
            assert r["ms_per_call"] > 0

    def test_best_of_reports_fastest_round(self):
        """A one-off stall in the first round must not leak into the reported time."""
        from benchmarks.run_benchmarks import _best_of

        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] == 1:  # only the very first call is slow
                time.sleep(0.05)

        best = _best_of(fn, iterations=1, rounds=3)
        assert calls["n"] == 3
        assert best < 0.02  # min over rounds drops the 50 ms stall

    def test_best_of_clamps_rounds_to_one(self):
        from benchmarks.run_benchmarks import _best_of

        calls = {"n": 0}

        def fn():
            calls["n"] += 1

        _best_of(fn, iterations=4, rounds=0)
        assert calls["n"] == 4


class TestCompare:
    def test_no_regression_passes(self, tmp_path):
        r = _compare(tmp_path, {"x": 10.0}, {"x": 10.5})
        assert r.returncode == 0
        assert "No changes" in r.stdout or "REGRESSIONS" not in r.stdout

    def test_regression_fails_when_flag_set(self, tmp_path):
        # Baseline above the 5 ms default noise floor so the gate applies.
        r = _compare(tmp_path, {"x": 10.0}, {"x": 20.0})
        assert r.returncode == 1
        assert "REGRESSIONS" in r.stdout

    def test_missing_baseline_returns_zero(self, tmp_path):
        b = tmp_path / "b.json"
        _write(b, {"x": 1.0})
        r = subprocess.run(
            [sys.executable, str(CMP),
             "--baseline", str(tmp_path / "nope.json"),
             "--current", str(b), "--fail-on-regression"],
            capture_output=True,
        )
        assert r.returncode == 0


class TestNoiseFloor:
    """``--min-baseline-ms`` (default 5.0) stops sub-ms noise from failing PRs."""

    def test_40pct_on_sub_ms_baseline_does_not_fail(self, tmp_path):
        r = _compare(tmp_path, {"aux": 0.2}, {"aux": 0.28})
        assert r.returncode == 0, r.stdout
        assert "REGRESSIONS" not in r.stdout
        assert "IGNORED" in r.stdout and "aux" in r.stdout

    def test_40pct_on_50ms_baseline_fails(self, tmp_path):
        r = _compare(tmp_path, {"big": 50.0}, {"big": 70.0})
        assert r.returncode == 1, r.stdout
        assert "REGRESSIONS" in r.stdout and "big" in r.stdout

    def test_floor_is_per_benchmark(self, tmp_path):
        """One noisy sub-ms bench must not mask a real regression elsewhere."""
        r = _compare(
            tmp_path,
            {"aux": 0.2, "big": 50.0},
            {"aux": 0.28, "big": 70.0},
        )
        assert r.returncode == 1
        assert "IGNORED" in r.stdout and "REGRESSIONS" in r.stdout

    def test_floor_can_be_disabled(self, tmp_path):
        r = _compare(tmp_path, {"aux": 0.2}, {"aux": 0.28}, "--min-baseline-ms", "0")
        assert r.returncode == 1
        assert "REGRESSIONS" in r.stdout

    def test_classify_unit(self):
        from benchmarks.compare_benchmarks import classify

        out = classify(
            {"aux": 0.2, "big": 50.0, "same": 8.0},
            {"aux": 0.28, "big": 70.0, "same": 8.1, "brand_new": 1.0},
            threshold=0.25, min_baseline_ms=5.0,
        )
        assert [r[0] for r in out["regressions"]] == ["big"]
        assert [r[0] for r in out["below_floor"]] == ["aux"]
        assert out["improvements"] == []
        assert out["new"] == ["brand_new"]
        assert out["regressions"][0][3] == pytest.approx(0.4)

"""Smoke-tests for benchmarks/run_benchmarks.py and compare_benchmarks.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
RUN = REPO / "benchmarks" / "run_benchmarks.py"
CMP = REPO / "benchmarks" / "compare_benchmarks.py"


class TestRunBenchmarks:
    def test_emits_valid_json(self, tmp_path):
        out = tmp_path / "r.json"
        subprocess.run(
            [sys.executable, str(RUN), "--output", str(out), "--quiet"],
            check=True, capture_output=True,
        )
        data = json.loads(out.read_text())
        assert "pyaermod_version" in data
        assert "results" in data and len(data["results"]) > 0
        for r in data["results"]:
            for field in ("name", "ms_per_call", "calls_per_sec", "n"):
                assert field in r
            assert r["ms_per_call"] > 0


class TestCompare:
    def _write(self, path, ms_by_name):
        data = {
            "pyaermod_version": "0",
            "timestamp": "x",
            "results": [
                {"name": k, "ms_per_call": v, "calls_per_sec": 1.0, "n": 1}
                for k, v in ms_by_name.items()
            ],
        }
        path.write_text(json.dumps(data))

    def test_no_regression_passes(self, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        self._write(a, {"x": 1.0})
        self._write(b, {"x": 1.05})
        r = subprocess.run(
            [sys.executable, str(CMP), "--baseline", str(a), "--current", str(b),
             "--fail-on-regression"],
            capture_output=True,
        )
        assert r.returncode == 0
        assert b"No changes" in r.stdout or b"REGRESSIONS" not in r.stdout

    def test_regression_fails_when_flag_set(self, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        self._write(a, {"x": 1.0})
        self._write(b, {"x": 2.0})
        r = subprocess.run(
            [sys.executable, str(CMP), "--baseline", str(a), "--current", str(b),
             "--fail-on-regression"],
            capture_output=True,
        )
        assert r.returncode == 1
        assert b"REGRESSIONS" in r.stdout

    def test_missing_baseline_returns_zero(self, tmp_path):
        b = tmp_path / "b.json"
        self._write(b, {"x": 1.0})
        r = subprocess.run(
            [sys.executable, str(CMP),
             "--baseline", str(tmp_path / "nope.json"),
             "--current", str(b), "--fail-on-regression"],
            capture_output=True,
        )
        assert r.returncode == 0

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


# ---------------------------------------------------------------------------
# benchmarks/bench_aermod_runs.py: resolution, staging and the skip path.
# None of this needs a real AERMOD binary; a shell script stands in for it.
# ---------------------------------------------------------------------------

from benchmarks import bench_aermod_runs as bar  # noqa: E402

FAKE_AERMOD = """#!/bin/sh
# Stand-in for AERMOD: `aermod` reads aermod.inp and writes aermod.out,
# `aermod in out` writes out. Either way it must leave an output file.
if [ "$#" -ge 2 ]; then out="$2"; else out="aermod.out"; fi
printf ' *** AERMOD - VERSION 26135 ***  fake\\n' > "$out"
exit 0
"""


@pytest.fixture
def fake_aermod(tmp_path):
    exe = tmp_path / "bin" / "aermod"
    exe.parent.mkdir()
    exe.write_text(FAKE_AERMOD)
    exe.chmod(0o755)
    return exe


def _fake_epa_set(root: Path, name="aermet26135_aermod26135", deck="aertest.inp"):
    s = root / name
    (s / "inputs").mkdir(parents=True)
    (s / "meteorology").mkdir()
    (s / "postfiles").mkdir()
    (s / "inputs" / deck).write_text(
        "CO STARTING\nCO FINISHED\nME STARTING\n"
        "   SURFFILE  ../meteorology/aermet2.sfc\n"
        "   PROFFILE  ../meteorology/aermet2.pfl\n"
        "ME FINISHED\nOU STARTING\n"
        "   PLOTFILE  1  ALL  FIRST  ../plotfiles/AERTEST_01H.PLT\n"
        "OU FINISHED\n"
    )
    # Upper-case on disk, lower-case in the deck: the archive's own mismatch.
    (s / "meteorology" / "AERMET2.SFC").write_text("sfc\n")
    (s / "meteorology" / "AERMET2.PFL").write_text("pfl\n")
    return s


class TestAermodBenchmarkSkips:
    def test_missing_binary_names_the_build_script(self):
        reason = bar.skip_reason(None, None)
        assert reason and "build_aermod.sh" in reason

    def test_unusable_binary_names_the_path(self, tmp_path):
        exe = tmp_path / "nope" / "aermod"
        reason = bar.skip_reason(exe, None)
        assert reason and str(exe) in reason

    def test_missing_case_names_the_archive(self, fake_aermod):
        reason = bar.skip_reason(fake_aermod, None)
        assert reason and "aermod_test_cases.zip" in reason

    def test_nothing_missing_is_none(self, fake_aermod, tmp_path):
        case = bar.BenchmarkCase("x", tmp_path / "x.inp", tmp_path, "test")
        assert bar.skip_reason(fake_aermod, case) is None

    def test_harness_skips_cleanly_with_reason(self, tmp_path):
        """`run_benchmarks.py --aermod` without a binary: exit 0, reason recorded."""
        out = tmp_path / "r.json"
        proc = subprocess.run(
            [sys.executable, str(RUN), "--output", str(out), "--rounds", "1",
             "--aermod", "--aermod-exe", str(tmp_path / "missing" / "aermod")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "SKIP AERMOD benchmarks" in proc.stdout
        data = json.loads(out.read_text())
        assert "not found" in data["aermod"]["skipped"]
        # The ordinary benchmarks still ran and the file is still comparable.
        assert data["results"] and all("aermod" not in r["name"] for r in data["results"])

    def test_harness_require_flag_turns_skip_into_exit_2(self, tmp_path):
        out = tmp_path / "r.json"
        proc = subprocess.run(
            [sys.executable, str(RUN), "--output", str(out), "--rounds", "1", "--quiet",
             "--aermod", "--require-aermod",
             "--aermod-exe", str(tmp_path / "missing" / "aermod")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "SKIP AERMOD benchmarks" in proc.stdout

    def test_standalone_script_skips_the_same_way(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(REPO / "benchmarks" / "bench_aermod_runs.py"),
             "--aermod-exe", str(tmp_path / "missing" / "aermod"), "--require-aermod"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "SKIP AERMOD benchmarks" in proc.stdout


class TestAermodBenchmarkResolution:
    def test_explicit_binary_is_returned_even_if_missing(self, tmp_path):
        assert bar.find_aermod(str(tmp_path / "x")) == tmp_path / "x"

    def test_case_prefers_an_epa_set(self, tmp_path):
        _fake_epa_set(tmp_path)
        case = bar.find_case(str(tmp_path))
        assert case is not None
        assert case.deck == tmp_path / "aermet26135_aermod26135" / "inputs" / "aertest.inp"
        assert case.source.startswith("EPA reference set aermet26135_aermod26135")

    def test_case_falls_back_to_the_vendored_fixture(self, tmp_path):
        case = bar.find_case(str(tmp_path / "no_sets_here"))
        assert case is not None
        assert case.deck == REPO / "tests" / "fixtures" / "epa_official" / "aertest.inp"
        assert "vendored" in case.source

    def test_unknown_case_is_none(self, tmp_path):
        assert bar.find_case(str(tmp_path), "no_such_deck") is None

    def test_workers_spec(self):
        assert bar.parse_workers("1,2,4,auto", cpu_count=8) == [1, 2, 4, 8]
        assert bar.parse_workers("4, auto,1", cpu_count=4) == [1, 4]
        with pytest.raises(ValueError):
            bar.parse_workers("0,2")


class TestAermodBenchmarkStaging:
    def test_paths_flattened_and_met_copied_under_deck_spelling(self, tmp_path):
        s = _fake_epa_set(tmp_path / "sets")
        case = bar.find_case(str(tmp_path / "sets"))
        staged = bar.stage_case(case, tmp_path / "work")
        text = staged.read_text()
        assert "../" not in text
        assert "SURFFILE  aermet2.sfc" in text
        assert "PLOTFILE  1  ALL  FIRST  AERTEST_01H.PLT" in text
        # Copied under the name the deck uses, so the run works on a
        # case-sensitive filesystem.
        assert (tmp_path / "work" / "aermet2.sfc").read_text() == "sfc\n"
        assert (tmp_path / "work" / "aermet2.pfl").read_text() == "pfl\n"
        assert staged.name == "aertest.inp"
        assert s.exists()


class TestAermodBenchmarkWithFakeBinary:
    def test_both_measurements_report(self, fake_aermod, tmp_path):
        _fake_epa_set(tmp_path / "sets")
        case = bar.find_case(str(tmp_path / "sets"))
        report = bar.run(fake_aermod, case, repeats=3, n_runs=3, worker_counts=[1, 2])
        single = report["aermod"]["single_run"]
        assert single["repeats"] == 3
        for key in ("direct_subprocess_ms", "pyaermod_runner_ms"):
            for stat in ("median", "p25", "p75", "min", "max"):
                assert single[key][stat] >= 0
            assert single[key]["n"] == 3
        assert single["overhead_ms"] == pytest.approx(
            single["pyaermod_runner_ms"]["median"] - single["direct_subprocess_ms"]["median"]
        )
        batch = report["aermod"]["batch"]
        assert batch["n_runs"] == 3
        assert [row["workers"] for row in batch["workers"]] == [1, 2]
        assert batch["workers"][0]["speedup"] == pytest.approx(1.0)
        assert all(row["runs_per_min"] > 0 for row in batch["workers"])
        names = [r["name"] for r in report["results"]]
        assert names == [
            "aermod_run/direct_subprocess", "aermod_run/pyaermod_runner",
            "aermod_batch/workers_1", "aermod_batch/workers_2",
        ]
        machine = report["aermod"]["machine"]
        assert machine["cpu_count"] == __import__("os").cpu_count()
        assert machine["aermod_version"] is None or machine["aermod_version"] == "26135"
        assert "direct subprocess" in bar.format_report(report["aermod"])

    def test_failed_run_is_an_error_not_a_number(self, tmp_path):
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/sh\nexit 3\n")
        exe.chmod(0o755)
        _fake_epa_set(tmp_path / "sets")
        case = bar.find_case(str(tmp_path / "sets"))
        with pytest.raises(RuntimeError, match="exit code 3"):
            bar.bench_single_run_overhead(exe, case, repeats=1, workdir=tmp_path / "w")

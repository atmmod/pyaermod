"""AERMOD run benchmarks: what pyaermod costs on top of the binary.

Two measurements, both of one EPA test case run through a real AERMOD
binary:

``single_run``
    The wall time of one run driven through :class:`pyaermod.runner.AERMODRunner`
    against the same binary invoked directly with :func:`subprocess.run`
    in the same directory. The two are interleaved for ``repeats`` rounds
    and the median and quartiles of each are reported, with the
    difference of medians as pyaermod's per-run overhead (the symlink,
    the directory lock, the redirected stdout files and the renames the
    runner does around the process).

``batch``
    ``n_runs`` copies of the case run through
    :meth:`AERMODRunner.run_batch` at 1, 2, 4 and ``os.cpu_count()``
    workers, reported as runs per minute and as the speed-up over one
    worker. Each run has its own working directory because the runner
    locks the directory it runs in.

Both need an AERMOD binary (``bin/aermod`` from
``scripts/build_aermod.sh``, or ``aermod`` on PATH) and the test case.
The case is taken from an unpacked EPA reference set when one is present
(``test_cases/``, resolved with
:func:`pyaermod.epa_testcases.find_epa_testcase_set`) and otherwise from
the copy of ``aertest`` vendored under ``tests/fixtures/epa_official``,
which is the same deck. When the binary or the case is missing the
benchmark reports why and is skipped rather than failing.

Run it on its own::

    python benchmarks/bench_aermod_runs.py [--repeats 20] [--batch-runs 32]

or as part of the harness (``python benchmarks/run_benchmarks.py --aermod``),
which writes the same numbers into ``benchmark_results.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from pyaermod import __version__  # noqa: E402
from pyaermod.epa_testcases import aermod_binary_version, find_epa_testcase_set  # noqa: E402
from pyaermod.runner import AERMODRunner  # noqa: E402

DEFAULT_CASE = "aertest"
DEFAULT_REPEATS = 20
DEFAULT_BATCH_RUNS = 32
DEFAULT_WORKERS = "1,2,4,auto"
VENDORED_FIXTURES = REPO / "tests" / "fixtures" / "epa_official"
RUN_TIMEOUT = 600

# ``../meteorology/aermet2.sfc`` and friends: EPA's decks assume the
# archive layout. Staging flattens every such reference to a bare name.
_ARCHIVE_PATH_RE = re.compile(r"\.\./[A-Za-z_]+/([^\s]+)")


@dataclass(frozen=True)
class BenchmarkCase:
    """One EPA deck plus the directory holding the files it references."""

    name: str
    deck: Path
    support_dir: Path
    source: str  # where the deck came from, for the report


# ---------------------------------------------------------------------------
# Resolution: binary and case, and why either is missing
# ---------------------------------------------------------------------------

def find_aermod(explicit: Optional[str] = None) -> Optional[Path]:
    """The AERMOD binary to benchmark.

    An explicit path is returned as given (even if it does not exist, so
    :func:`skip_reason` can name it). Otherwise ``bin/aermod`` at the
    repository root, then ``aermod`` on PATH.
    """
    if explicit:
        return Path(explicit)
    built = REPO / "bin" / "aermod"
    if built.is_file() and os.access(built, os.X_OK):
        return built
    found = shutil.which("aermod")
    return Path(found) if found else None


def _find_case_insensitive(directory: Path, name: str) -> Optional[Path]:
    if not directory.is_dir():
        return None
    wanted = name.lower()
    for candidate in directory.iterdir():
        if candidate.name.lower() == wanted:
            return candidate
    return None


def find_case(
    testcase_dir: Optional[str] = None,
    case: str = DEFAULT_CASE,
    *,
    vendored_dir: Path = VENDORED_FIXTURES,
) -> Optional[BenchmarkCase]:
    """Locate ``case`` in an EPA reference set, else in the vendored fixtures.

    ``testcase_dir`` is the root holding the unpacked sets
    (``test_cases/`` by default); the set is chosen by
    :func:`find_epa_testcase_set`, honouring ``$PYAERMOD_EPA_TESTCASES``.
    The vendored fallback only exists for ``aertest``, whose deck and
    meteorology are checked in.
    """
    root = Path(testcase_dir) if testcase_dir else REPO / "test_cases"
    epa_set = find_epa_testcase_set(root)
    if epa_set is not None and epa_set.exists():
        deck = _find_case_insensitive(epa_set.inputs, f"{case}.inp")
        if deck is not None:
            return BenchmarkCase(
                name=case, deck=deck, support_dir=epa_set.meteorology,
                source=f"EPA reference set {epa_set.name}",
            )
    deck = _find_case_insensitive(vendored_dir, f"{case}.inp")
    if deck is not None:
        return BenchmarkCase(
            name=case, deck=deck, support_dir=vendored_dir,
            source=f"vendored copy under {vendored_dir.relative_to(REPO) if vendored_dir.is_relative_to(REPO) else vendored_dir}",
        )
    return None


def skip_reason(exe: Optional[Path], case: Optional[BenchmarkCase]) -> Optional[str]:
    """Why the AERMOD benchmarks cannot run, or ``None`` when they can."""
    if exe is None:
        return ("no AERMOD binary: build one with scripts/build_aermod.sh "
                "(bin/aermod) or put aermod on PATH")
    if not exe.is_file() or not os.access(exe, os.X_OK):
        return f"AERMOD binary not found or not executable: {exe}"
    if case is None:
        return ("no test case: unpack EPA's aermod_test_cases.zip under test_cases/ "
                f"or keep the vendored {DEFAULT_CASE} fixture under {VENDORED_FIXTURES.relative_to(REPO)}")
    return None


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------

def stage_case(case: BenchmarkCase, dest: Path) -> Path:
    """Copy the deck into ``dest`` with archive-relative paths flattened.

    Every ``../<dir>/<name>`` reference becomes ``<name>``; the referenced
    files that exist in ``case.support_dir`` (the meteorology) are copied
    in under the name the deck uses, so the case runs from ``dest`` alone
    and writes its outputs there. Returns the staged deck path.
    """
    dest.mkdir(parents=True, exist_ok=True)
    text = case.deck.read_text(encoding="latin-1")

    def _flatten(match: re.Match[str]) -> str:
        name = match.group(1)
        source = _find_case_insensitive(case.support_dir, name)
        if source is not None and not (dest / name).exists():
            shutil.copy(source, dest / name)
        return name

    text = _ARCHIVE_PATH_RE.sub(_flatten, text)
    staged = dest / case.deck.name.lower()
    staged.write_text(text, encoding="latin-1")
    return staged


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

def _summary(samples: Sequence[float]) -> Dict[str, float]:
    """Median and spread of wall times, in milliseconds."""
    ms = sorted(s * 1000.0 for s in samples)
    q = statistics.quantiles(ms, n=4) if len(ms) >= 2 else [ms[0], ms[0], ms[0]]
    return {
        "median": statistics.median(ms),
        "p25": q[0],
        "p75": q[2],
        "min": ms[0],
        "max": ms[-1],
        "mean": statistics.fmean(ms),
        "n": len(ms),
    }


def bench_single_run_overhead(
    exe: Path, case: BenchmarkCase, *, repeats: int = DEFAULT_REPEATS, workdir: Path,
) -> Dict[str, Any]:
    """Interleave direct and pyaermod-driven runs and report both timings."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    staged = stage_case(case, workdir)
    runner = AERMODRunner(executable_path=exe, log_level="WARNING")
    direct: List[float] = []
    driven: List[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        proc = subprocess.run(
            [str(exe), staged.name, f"{staged.stem}_direct.out"],
            cwd=str(workdir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
        direct.append(time.perf_counter() - t0)
        if proc.returncode != 0:
            raise RuntimeError(f"direct AERMOD run failed with exit code {proc.returncode}")

        t0 = time.perf_counter()
        result = runner.run(staged, working_dir=workdir, timeout=RUN_TIMEOUT)
        driven.append(time.perf_counter() - t0)
        if not result.success:
            raise RuntimeError(f"pyaermod-driven AERMOD run failed: {result.error_message}")

    direct_ms = _summary(direct)
    driven_ms = _summary(driven)
    overhead = driven_ms["median"] - direct_ms["median"]
    return {
        "repeats": repeats,
        "direct_subprocess_ms": direct_ms,
        "pyaermod_runner_ms": driven_ms,
        "overhead_ms": overhead,
        "overhead_pct": 100.0 * overhead / direct_ms["median"] if direct_ms["median"] else 0.0,
    }


def parse_workers(spec: str, cpu_count: Optional[int] = None) -> List[int]:
    """``"1,2,4,auto"`` -> ``[1, 2, 4, <cpu count>]``, deduplicated and sorted."""
    cpus = cpu_count or os.cpu_count() or 1
    counts = set()
    for token in spec.split(","):
        token = token.strip().lower()
        if not token:
            continue
        counts.add(cpus if token == "auto" else int(token))
    if any(c < 1 for c in counts):
        raise ValueError(f"worker counts must be positive: {spec!r}")
    return sorted(counts)


def bench_batch_throughput(
    exe: Path, case: BenchmarkCase, *, n_runs: int = DEFAULT_BATCH_RUNS,
    worker_counts: Iterable[int] = (1, 2, 4), workdir: Path,
) -> Dict[str, Any]:
    """Time ``n_runs`` copies of the case through ``run_batch`` per worker count."""
    if n_runs < 1:
        raise ValueError("n_runs must be at least 1")
    runner = AERMODRunner(executable_path=exe, log_level="WARNING")
    rows: List[Dict[str, Any]] = []
    baseline: Optional[float] = None
    for workers in worker_counts:
        batch_dir = workdir / f"batch_w{workers}"
        if batch_dir.exists():
            shutil.rmtree(batch_dir)
        decks = [stage_case(case, batch_dir / f"run_{i:03d}") for i in range(n_runs)]
        t0 = time.perf_counter()
        results = runner.run_batch(decks, n_workers=workers, timeout=RUN_TIMEOUT)
        elapsed = time.perf_counter() - t0
        failed = [r for r in results if not r.success]
        if failed or len(results) != n_runs:
            raise RuntimeError(
                f"batch at {workers} workers: {len(failed)} of {len(results)} runs failed "
                f"({failed[0].error_message if failed else 'missing results'})"
            )
        if baseline is None:
            baseline = elapsed
        rows.append({
            "workers": workers,
            "seconds": elapsed,
            "seconds_per_run": elapsed / n_runs,
            "runs_per_min": 60.0 * n_runs / elapsed,
            "speedup": baseline / elapsed,
        })
        shutil.rmtree(batch_dir, ignore_errors=True)
    return {"n_runs": n_runs, "workers": rows}


# ---------------------------------------------------------------------------
# Provenance and the harness entry point
# ---------------------------------------------------------------------------

def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _first_line(cmd: List[str]) -> Optional[str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    out = (proc.stdout or proc.stderr or "").strip()
    return out.splitlines()[0] if out else None


def machine_info(exe: Path) -> Dict[str, Any]:
    """What the numbers were measured on, for the report."""
    return {
        "platform": platform.platform(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "pyaermod": __version__,
        "aermod_version": aermod_binary_version(exe),
        "aermod_executable": str(exe),
        "gfortran": _first_line(["gfortran", "--version"]),
        "git_commit": _first_line(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"]),
        "ci": "github-actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
    }


def run(
    exe: Path, case: BenchmarkCase, *, repeats: int = DEFAULT_REPEATS,
    n_runs: int = DEFAULT_BATCH_RUNS, worker_counts: Iterable[int] = (1, 2, 4),
) -> Dict[str, Any]:
    """Run both measurements in a scratch directory and return the report.

    The report has an ``aermod`` section (provenance and both
    measurements in full) and a ``results`` list in the harness's
    ``{name, ms_per_call, calls_per_sec, n}`` shape so
    ``compare_benchmarks.py`` can read it.
    """
    worker_counts = list(worker_counts)
    with tempfile.TemporaryDirectory(prefix="pyaermod_bench_") as tmp:
        scratch = Path(tmp)
        single = bench_single_run_overhead(exe, case, repeats=repeats, workdir=scratch / "single")
        batch = bench_batch_throughput(
            exe, case, n_runs=n_runs, worker_counts=worker_counts, workdir=scratch / "batch",
        )
    section = {
        "machine": machine_info(exe),
        "case": {"name": case.name, "deck": str(case.deck), "source": case.source},
        "single_run": single,
        "batch": batch,
    }
    results: List[Dict[str, Any]] = [
        {
            "name": "aermod_run/direct_subprocess",
            "ms_per_call": single["direct_subprocess_ms"]["median"],
            "calls_per_sec": 1000.0 / single["direct_subprocess_ms"]["median"],
            "n": repeats,
        },
        {
            "name": "aermod_run/pyaermod_runner",
            "ms_per_call": single["pyaermod_runner_ms"]["median"],
            "calls_per_sec": 1000.0 / single["pyaermod_runner_ms"]["median"],
            "n": repeats,
        },
    ]
    for row in batch["workers"]:
        results.append({
            "name": f"aermod_batch/workers_{row['workers']}",
            "ms_per_call": 1000.0 * row["seconds_per_run"],
            "calls_per_sec": n_runs / row["seconds"],
            "n": n_runs,
            "workers": row["workers"],
            "runs_per_min": row["runs_per_min"],
            "speedup": row["speedup"],
        })
    return {"aermod": section, "results": results}


def format_report(section: Dict[str, Any]) -> str:
    """Human-readable summary of an ``aermod`` section."""
    m = section["machine"]
    s = section["single_run"]
    d, p = s["direct_subprocess_ms"], s["pyaermod_runner_ms"]
    lines = [
        f"AERMOD {m.get('aermod_version') or '?'} ({m['aermod_executable']}) on "
        f"{m['cpu_model']}, {m['cpu_count']} CPUs, {m['platform']}",
        f"case: {section['case']['name']} ({section['case']['source']})",
        "",
        f"single run, {s['repeats']} repeats (median [p25-p75] ms):",
        f"  direct subprocess  {d['median']:8.1f}  [{d['p25']:.1f}-{d['p75']:.1f}]",
        f"  pyaermod runner    {p['median']:8.1f}  [{p['p25']:.1f}-{p['p75']:.1f}]",
        f"  overhead           {s['overhead_ms']:8.1f} ms  ({s['overhead_pct']:.1f} %)",
        "",
        f"batch of {section['batch']['n_runs']} runs:",
        "  workers   seconds   runs/min   speed-up",
    ]
    for row in section["batch"]["workers"]:
        lines.append(
            f"  {row['workers']:>7d}  {row['seconds']:8.2f}  {row['runs_per_min']:9.1f}   {row['speedup']:.2f}x"
        )
    return "\n".join(lines)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The AERMOD-benchmark options, shared with ``run_benchmarks.py``."""
    parser.add_argument("--aermod-exe", default=None,
                        help="AERMOD binary (default: bin/aermod, then PATH)")
    parser.add_argument("--testcase-dir", default=None,
                        help="root holding unpacked EPA reference sets (default: test_cases/)")
    parser.add_argument("--case", default=DEFAULT_CASE,
                        help=f"deck name without .inp (default {DEFAULT_CASE})")
    parser.add_argument("--aermod-repeats", type=int, default=DEFAULT_REPEATS,
                        help=f"interleaved direct/pyaermod runs for the overhead measurement (default {DEFAULT_REPEATS})")
    parser.add_argument("--aermod-batch-runs", type=int, default=DEFAULT_BATCH_RUNS,
                        help=f"runs per batch for the throughput measurement (default {DEFAULT_BATCH_RUNS})")
    parser.add_argument("--aermod-workers", default=DEFAULT_WORKERS,
                        help=f"comma-separated worker counts, 'auto' = os.cpu_count() (default {DEFAULT_WORKERS})")
    parser.add_argument("--require-aermod", action="store_true",
                        help="exit 2 instead of skipping when the binary or the case is missing")


def run_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    """Resolve the binary and case from parsed options and run, or skip.

    Returns either the report from :func:`run` or ``{"aermod":
    {"skipped": reason}, "results": []}``.
    """
    exe = find_aermod(args.aermod_exe)
    case = find_case(args.testcase_dir, args.case)
    reason = skip_reason(exe, case)
    if reason is not None:
        return {"aermod": {"skipped": reason}, "results": []}
    assert exe is not None and case is not None
    return run(
        exe, case, repeats=args.aermod_repeats, n_runs=args.aermod_batch_runs,
        worker_counts=parse_workers(args.aermod_workers),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    add_arguments(parser)
    parser.add_argument("--output", default=None, help="also write the report as JSON here")
    args = parser.parse_args(argv)
    report = run_from_args(args)
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
    if "skipped" in report["aermod"]:
        print(f"SKIP AERMOD benchmarks: {report['aermod']['skipped']}")
        return 2 if args.require_aermod else 0
    print(format_report(report["aermod"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

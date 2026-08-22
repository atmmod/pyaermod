"""Compare two benchmark_results.json files and flag regressions.

Usage:
    python benchmarks/compare_benchmarks.py --baseline base.json \
        --current current.json [--threshold 0.20] [--min-baseline-ms 5.0] \
        [--fail-on-regression]

Exits with code 1 (when --fail-on-regression) if any benchmark is
slower by more than `threshold` (fraction; default 0.20 = 20%).

Noise floor
-----------
Sub-millisecond operations swing by tens of percent between CI runs for
reasons unrelated to the code under test (CPU frequency scaling, a
shared runner, GC timing). A benchmark whose *baseline* is below
``--min-baseline-ms`` (default 5.0 ms) is therefore reported in an
``IGNORED`` section but never counts as a regression. Pass
``--min-baseline-ms 0`` to disable the floor.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict

DEFAULT_THRESHOLD = 0.20
DEFAULT_MIN_BASELINE_MS = 5.0


def _index(results_file: Path) -> Dict[str, float]:
    data = json.loads(results_file.read_text())
    return {r["name"]: r["ms_per_call"] for r in data.get("results", [])}


def classify(
    base: Dict[str, float],
    curr: Dict[str, float],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    min_baseline_ms: float = DEFAULT_MIN_BASELINE_MS,
) -> Dict[str, list]:
    """Bucket every current benchmark against its baseline.

    Parameters
    ----------
    base, curr
        ``{name: ms_per_call}`` maps for the baseline and current runs.
    threshold
        Fractional slowdown / speedup that counts as a change.
    min_baseline_ms
        Baselines below this are never classified as regressions; a
        slowdown on such a benchmark lands in ``below_floor`` instead.

    Returns
    -------
    dict
        Keys ``regressions``, ``improvements``, ``below_floor`` (each a
        list of ``(name, base_ms, curr_ms, delta)``) and ``new`` (names).
    """
    regressions, improvements, below_floor, new_benches = [], [], [], []
    for name, curr_ms in curr.items():
        if name not in base:
            new_benches.append(name)
            continue
        base_ms = base[name]
        if base_ms <= 0:
            continue
        delta = (curr_ms - base_ms) / base_ms
        if delta > threshold:
            if base_ms < min_baseline_ms:
                below_floor.append((name, base_ms, curr_ms, delta))
            else:
                regressions.append((name, base_ms, curr_ms, delta))
        elif delta < -threshold:
            improvements.append((name, base_ms, curr_ms, delta))
    return {
        "regressions": regressions,
        "improvements": improvements,
        "below_floor": below_floor,
        "new": new_benches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help="Fractional slowdown that counts as a regression (default 0.20).",
    )
    parser.add_argument(
        "--min-baseline-ms", type=float, default=DEFAULT_MIN_BASELINE_MS,
        help="Noise floor: benchmarks whose baseline is below this many "
             "milliseconds are reported but never fail the gate "
             "(default 5.0; 0 disables).",
    )
    parser.add_argument(
        "--fail-on-regression", action="store_true",
        help="Exit code 1 if any benchmark exceeds the threshold.",
    )
    args = parser.parse_args()

    if not args.baseline.exists():
        print(f"Baseline file not found: {args.baseline}")
        return 0  # treat as first run — nothing to compare

    base = _index(args.baseline)
    curr = _index(args.current)
    buckets = classify(
        base, curr,
        threshold=args.threshold, min_baseline_ms=args.min_baseline_ms,
    )
    regressions = buckets["regressions"]
    improvements = buckets["improvements"]
    below_floor = buckets["below_floor"]
    new_benches = buckets["new"]

    print("=== Benchmark comparison ===")
    print(f"Baseline: {args.baseline} ({len(base)} benchmarks)")
    print(f"Current:  {args.current}  ({len(curr)} benchmarks)")
    print(f"Threshold: {args.threshold:.0%}   noise floor: {args.min_baseline_ms:g} ms")
    print()
    if regressions:
        print(f"REGRESSIONS (>{args.threshold:.0%} slower):")
        for name, b, c, d in regressions:
            print(f"  {name:<40s} {b:8.3f} -> {c:8.3f} ms ({d:+.1%})")
    if below_floor:
        print(
            f"IGNORED (>{args.threshold:.0%} slower, but baseline < "
            f"{args.min_baseline_ms:g} ms noise floor — not gated):"
        )
        for name, b, c, d in below_floor:
            print(f"  {name:<40s} {b:8.3f} -> {c:8.3f} ms ({d:+.1%})")
    if improvements:
        print(f"IMPROVEMENTS (>{args.threshold:.0%} faster):")
        for name, b, c, d in improvements:
            print(f"  {name:<40s} {b:8.3f} -> {c:8.3f} ms ({d:+.1%})")
    if new_benches:
        print(f"NEW: {', '.join(new_benches)}")
    if not regressions and not improvements and not below_floor:
        print(f"No changes beyond ±{args.threshold:.0%} threshold.")

    if regressions and args.fail_on_regression:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

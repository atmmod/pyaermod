"""Compare two benchmark_results.json files and flag regressions.

Usage:
    python benchmarks/compare_benchmarks.py --baseline base.json \
        --current current.json [--threshold 0.20] [--fail-on-regression]

Exits with code 1 (when --fail-on-regression) if any benchmark is
slower by more than `threshold` (fraction; default 0.20 = 20%).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict


def _index(results_file: Path) -> Dict[str, float]:
    data = json.loads(results_file.read_text())
    return {r["name"]: r["ms_per_call"] for r in data.get("results", [])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument(
        "--threshold", type=float, default=0.20,
        help="Fractional slowdown that counts as a regression (default 0.20).",
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

    regressions = []
    improvements = []
    new_benches = []

    for name, curr_ms in curr.items():
        if name not in base:
            new_benches.append(name)
            continue
        base_ms = base[name]
        if base_ms <= 0:
            continue
        delta = (curr_ms - base_ms) / base_ms
        if delta > args.threshold:
            regressions.append((name, base_ms, curr_ms, delta))
        elif delta < -args.threshold:
            improvements.append((name, base_ms, curr_ms, delta))

    print("=== Benchmark comparison ===")
    print(f"Baseline: {args.baseline} ({len(base)} benchmarks)")
    print(f"Current:  {args.current}  ({len(curr)} benchmarks)")
    print()
    if regressions:
        print(f"REGRESSIONS (>{args.threshold:.0%} slower):")
        for name, b, c, d in regressions:
            print(f"  {name:<40s} {b:8.3f} -> {c:8.3f} ms ({d:+.1%})")
    if improvements:
        print(f"IMPROVEMENTS (>{args.threshold:.0%} faster):")
        for name, b, c, d in improvements:
            print(f"  {name:<40s} {b:8.3f} -> {c:8.3f} ms ({d:+.1%})")
    if new_benches:
        print(f"NEW: {', '.join(new_benches)}")
    if not regressions and not improvements:
        print(f"No changes beyond ±{args.threshold:.0%} threshold.")

    if regressions and args.fail_on_regression:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

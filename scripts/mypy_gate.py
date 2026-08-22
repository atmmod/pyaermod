#!/usr/bin/env python
"""Ratchet gate for mypy: fail only when the error count grows.

``mypy src/pyaermod`` is not yet clean. Rather than leaving it advisory
(where regressions go unnoticed) or blocking on a full cleanup, CI
compares the current error count against the integer committed in
``mypy-baseline.txt`` at the repo root:

* count  > baseline  -> exit 1 (new type errors were introduced)
* count == baseline  -> exit 0
* count  < baseline  -> exit 0, and prints the command to lower the
  baseline so the improvement is locked in

Usage::

    python scripts/mypy_gate.py            # gate (what CI runs)
    python scripts/mypy_gate.py --update   # rewrite mypy-baseline.txt
    python scripts/mypy_gate.py -- --strict  # pass extra args to mypy

mypy's configuration comes from ``[tool.mypy]`` in ``pyproject.toml``;
the script runs from the repository root so that config is picked up.
The baseline is only meaningful for a fixed mypy version — bump the
pin in ``.github/workflows/tests.yml`` and re-run ``--update`` together.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent
BASELINE_FILE = REPO / "mypy-baseline.txt"
TARGET = "src/pyaermod"

_ERROR_LINE = re.compile(r"^.+?:\d+(?::\d+)?: error: ")
_SUMMARY = re.compile(r"^Found (\d+) errors? in \d+ files?")


def count_errors(mypy_output: str) -> int:
    """Return the number of ``error:`` diagnostics in mypy's stdout.

    Counts ``path:line: error:`` lines directly so the result does not
    depend on ``--no-error-summary``; the ``Found N errors`` summary
    line, when present, is used as a consistency check.
    """
    lines = mypy_output.splitlines()
    n = sum(1 for line in lines if _ERROR_LINE.match(line))
    for line in lines:
        m = _SUMMARY.match(line)
        if m and int(m.group(1)) != n:
            # Summary disagrees (e.g. duplicate-line suppression); trust the
            # larger figure so the gate never under-counts.
            return max(n, int(m.group(1)))
    return n


def read_baseline(path: Path = BASELINE_FILE) -> int:
    """Read the committed baseline integer (``None`` file -> error)."""
    text = path.read_text(encoding="utf-8").strip()
    try:
        return int(text)
    except ValueError as exc:
        raise SystemExit(f"{path}: expected a single integer, got {text!r}") from exc


def evaluate(count: int, baseline: int) -> Tuple[int, str]:
    """Map (current count, baseline) to (exit code, human message)."""
    if count > baseline:
        return 1, (
            f"mypy: {count} errors, baseline is {baseline} "
            f"(+{count - baseline}). New type errors were introduced — "
            f"fix them, or if they are pre-existing and unavoidable, "
            f"run `python scripts/mypy_gate.py --update` and commit "
            f"mypy-baseline.txt with a justification."
        )
    if count < baseline:
        return 0, (
            f"mypy: {count} errors, baseline is {baseline} "
            f"({count - baseline}). Nice — lock it in with "
            f"`python scripts/mypy_gate.py --update` and commit mypy-baseline.txt."
        )
    return 0, f"mypy: {count} errors, matches baseline {baseline}."


def run_mypy(extra_args: List[str]) -> Tuple[int, str]:
    """Run mypy on the library and return (returncode, combined output)."""
    cmd = [sys.executable, "-m", "mypy", TARGET, *extra_args]
    proc = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update", action="store_true",
        help="Write the current error count to mypy-baseline.txt and exit 0.",
    )
    parser.add_argument(
        "--baseline-file", type=Path, default=BASELINE_FILE,
        help=f"Baseline file (default {BASELINE_FILE.relative_to(REPO)}).",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Do not echo mypy's diagnostics, only the verdict.",
    )
    parser.add_argument(
        "mypy_args", nargs="*",
        help="Extra arguments forwarded to mypy (prefix with `--`).",
    )
    args = parser.parse_args(argv)

    rc, output = run_mypy(args.mypy_args)
    if rc not in (0, 1):
        # 2 = mypy crashed / bad usage; surface it verbatim.
        sys.stderr.write(output)
        return rc
    if not args.quiet:
        sys.stdout.write(output)

    count = count_errors(output)

    if args.update:
        args.baseline_file.write_text(f"{count}\n", encoding="utf-8")
        print(f"mypy baseline set to {count} in {args.baseline_file}")
        return 0

    if not args.baseline_file.exists():
        print(
            f"{args.baseline_file} not found; current count is {count}. "
            f"Create it with `python scripts/mypy_gate.py --update`."
        )
        return 1

    code, message = evaluate(count, read_baseline(args.baseline_file))
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())

"""Print a reader-coverage report over the full EPA test-case archive.

Usage::

    python tests/fixtures/epa_official/reader_coverage_report.py \\
        [--archive tests/fixtures/epa_official/full] [--json out.json]

For each .inp file the report shows:
- parse: did `pyaermod.input_reader.read_aermod_input` complete without exception?
- sources: number of sources the reader extracted / estimated actual count from LOCATION lines
- kw_coverage: fraction of distinct keyword/pathway combinations we kept structurally

A summary at the end prints the global parse rate. CI's
``test_regression_epa_official.TestFullArchive`` uses the same
machinery to gate merges.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from pyaermod.input_reader import parse_aermod_input

# Keywords we consider "structurally understood" by the current reader.
# Pathway-prefixed variants (e.g. "SO LOCATION") are normalized in
# `_group_keywords`, so a single-word tag is enough here.
SUPPORTED_KEYWORDS = {
    # CO
    "STARTING", "FINISHED", "TITLEONE", "TITLETWO", "MODELOPT", "AVERTIME",
    "POLLUTID", "RUNORNOT", "HALFLIFE", "DCAYCOEF", "ELEVUNIT", "FLAGPOLE",
    "URBANOPT", "LOW_WIND",
    # SO
    "LOCATION", "SRCPARAM", "SRCGROUP",
    "BUILDHGT", "BUILDWID", "BUILDLEN", "XBADJ", "YBADJ",
    # RE
    "GRIDCART", "GRIDPOLR", "DISCCART", "XYINC",
    # ME
    "SURFFILE", "PROFFILE", "SURFDATA", "UAIRDATA", "PROFBASE", "STARTEND",
    "WDROTATE",
    # OU
    "RECTABLE", "MAXTABLE", "DAYTABLE", "SUMMFILE", "MAXIFILE", "PLOTFILE",
    "POSTFILE",
}


def _keywords_in_file(text: str) -> List[str]:
    """Return the list of leading keywords on non-comment lines."""
    out: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("**") or line.startswith("!"):
            continue
        toks = line.split()
        if not toks:
            continue
        kw = toks[0].upper()
        # Strip pathway prefix (SO/CO/RE/ME/OU/EV)
        if kw in {"CO", "SO", "RE", "ME", "OU", "EV"} and len(toks) > 1:
            kw = toks[1].upper()
        out.append(kw)
    return out


def _one_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    kws = _keywords_in_file(text)
    kw_counts = Counter(kws)
    total_kw = sum(kw_counts.values())
    supported = sum(
        v for k, v in kw_counts.items()
        if k in SUPPORTED_KEYWORDS or k in {"STARTING", "FINISHED"}
    )
    location_lines = sum(
        1 for raw in text.splitlines()
        if re.match(r"^\s*(SO\s+)?LOCATION\b", raw, re.IGNORECASE)
    )

    parsed = False
    n_sources = 0
    err = None
    try:
        project = parse_aermod_input(text)
        parsed = True
        n_sources = len(project.sources.sources)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"

    return {
        "file": path.name,
        "parse": parsed,
        "sources": n_sources,
        "expected_sources": location_lines,
        "kw_coverage": supported / total_kw if total_kw else 1.0,
        "total_keywords": total_kw,
        "error": err,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--archive", type=Path,
        default=Path(__file__).parent / "full",
        help="Path to the unpacked EPA test-case archive",
    )
    parser.add_argument("--json", type=Path, help="Write a JSON report to this path")
    args = parser.parse_args()

    candidates = list(args.archive.rglob("inputs/*.inp")) if args.archive.exists() else []
    if not candidates:
        # Fall back to the vendored fixtures
        root = Path(__file__).parent
        candidates = sorted(root.glob("*.inp"))
    if not candidates:
        print("No .inp files found. Run download_all.py to populate the archive.")
        return 1

    rows = [_one_file(p) for p in sorted(candidates)]

    parsed = sum(1 for r in rows if r["parse"])
    avg_kw_cov = sum(r["kw_coverage"] for r in rows) / len(rows)
    print(f"Scanned {len(rows)} AERMOD .inp files")
    print(f"  parse-rate: {parsed}/{len(rows)} ({parsed/len(rows):.0%})")
    print(f"  avg keyword coverage: {avg_kw_cov:.0%}")
    print()
    print(f"{'file':<45s} parse sources/exp  kw-cov  error")
    print("-" * 90)
    for r in rows:
        err_brief = "" if not r["error"] else r["error"][:40]
        print(
            f"{r['file']:<45s} "
            f"{'OK' if r['parse'] else 'FAIL':<5s} "
            f"{r['sources']:>3d}/{r['expected_sources']:<3d}    "
            f"{r['kw_coverage']:>5.0%}  {err_brief}"
        )

    if args.json:
        args.json.write_text(json.dumps({
            "parse_rate": parsed / len(rows),
            "avg_kw_coverage": avg_kw_cov,
            "files": rows,
        }, indent=2))
        print(f"\nJSON report written to {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

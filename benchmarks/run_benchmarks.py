"""Run all pyaermod benchmarks and emit a JSON result file.

Output schema:
    {
      "pyaermod_version": "1.2.0",
      "timestamp": "2026-04-15T12:00:00Z",
      "results": [
        {"name": "input_gen/PointSource/100", "ms_per_call": 1.23,
         "calls_per_sec": 813.0, "n": 100, "source_type": "PointSource"},
        ...
      ]
    }

Used by CI to track perf trends and by compare_benchmarks.py to flag
regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Make the package importable when running directly from the repo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyaermod import __version__  # noqa: E402
from pyaermod.input_generator import (  # noqa: E402
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    SourcePathway,
    VolumeSource,
)


def _build_sources(cls, n):
    sp = SourcePathway()
    for i in range(n):
        if cls is PointSource:
            sp.add_source(cls(
                source_id=f"S{i:04d}", x_coord=float(100 * i), y_coord=0.0,
                stack_height=50.0, stack_temp=400.0, exit_velocity=15.0,
                stack_diameter=2.0, emission_rate=1.0,
            ))
        elif cls is AreaSource:
            sp.add_source(cls(
                source_id=f"A{i:04d}", x_coord=float(100 * i), y_coord=0.0,
                emission_rate=0.01,
            ))
        elif cls is VolumeSource:
            sp.add_source(cls(
                source_id=f"V{i:04d}", x_coord=float(100 * i), y_coord=0.0,
                emission_rate=1.0,
            ))
    return sp


def _project(sources):
    return AERMODProject(
        control=ControlPathway(title_one="Benchmark"),
        sources=sources,
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
        output=OutputPathway(),
    )


def bench_input_generation(iterations: int = 100) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    counts = [1, 10, 100, 1000]
    for cls in (PointSource, AreaSource, VolumeSource):
        for n in counts:
            project = _project(_build_sources(cls, n))
            start = time.perf_counter()
            for _ in range(iterations):
                project.to_aermod_input()
            elapsed = time.perf_counter() - start
            results.append({
                "name": f"input_gen/{cls.__name__}/{n}",
                "ms_per_call": elapsed / iterations * 1000.0,
                "calls_per_sec": iterations / elapsed,
                "n": n,
                "source_type": cls.__name__,
            })
    return results


def bench_auxiliary_parse(iterations: int = 500) -> List[Dict[str, Any]]:
    from pyaermod.aermod_outputs import read_aermod_aux_file

    tmp = Path(".bench_tmp.plt")
    rows = "\n".join(
        f"    {i:.2f}    0.00    {1e-3 * i:.4e}" for i in range(100)
    )
    tmp.write_text(f"* AERMOD: test PLOTFILE\n* X Y CONC\n{rows}\n")
    try:
        start = time.perf_counter()
        for _ in range(iterations):
            read_aermod_aux_file(tmp)
        elapsed = time.perf_counter() - start
    finally:
        tmp.unlink(missing_ok=True)
    return [{
        "name": "aux_parse/plotfile_100rows",
        "ms_per_call": elapsed / iterations * 1000.0,
        "calls_per_sec": iterations / elapsed,
        "n": 100,
        "source_type": "PLOTFILE",
    }]


def run_all() -> Dict[str, Any]:
    results = []
    results.extend(bench_input_generation())
    results.extend(bench_auxiliary_parse())
    return {
        "pyaermod_version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmark_results.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    summary = run_all()
    Path(args.output).write_text(json.dumps(summary, indent=2))
    if not args.quiet:
        print(f"Wrote {args.output} (version {summary['pyaermod_version']})")
        for r in summary["results"]:
            print(f"  {r['name']:<40s} {r['ms_per_call']:8.3f} ms/call")
    return 0


if __name__ == "__main__":
    sys.exit(main())

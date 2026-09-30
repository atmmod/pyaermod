#!/usr/bin/env python
"""Re-record the AERMOD runs of design.py (see README.md).

Usage:  python tests/fixtures/ensemble/regenerate.py path/to/aermod [case ...]

Runs every row of design.RECORDED_ROWS (or only the named cases) through pyaermod.ensemble.run_design
with the given AERMOD in a scratch directory, then copies each run back
into a directory named after its "case" factor: the deck as aermod.inp,
AERMOD's .out as aermod.out, its stdout as stdout.txt, its exit code as
exit_code.txt, and the files the deck names for AERMOD to write under
outputs/. It also writes houremis.dat, the extras row's hourly emission
file (design.houremis_lines()).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import design  # noqa: E402

from pyaermod.ensemble import run_design  # noqa: E402


def main(exe: str, cases: list) -> None:
    design.HOUREMIS.write_text(design.houremis_lines())
    rows = [r for r in design.RECORDED_ROWS if not cases or r["case"] in cases]
    with tempfile.TemporaryDirectory() as tmp:
        result = run_design(rows, design.build, tmp, n_workers=4,
                            executable=exe, resume=False)
        for run in result.values():
            case = HERE / run.factors["case"]
            shutil.rmtree(case, ignore_errors=True)
            (case / "outputs").mkdir(parents=True)
            shutil.copy(run.run_dir / "run.inp", case / "aermod.inp")
            shutil.copy(run.run_dir / "run.out", case / "aermod.out")
            shutil.copy(run.run_dir / "run.subproc.stdout", case / "stdout.txt")
            (case / "exit_code.txt").write_text(f"{run.entry.return_code}\n")
            for names in run.entry.outputs.values():
                for name in names:
                    if (run.run_dir / name).exists():
                        shutil.copy(run.run_dir / name, case / "outputs" / name)
            print(f"{run.factors['case']}: {run.entry.status}, "
                  f"exit code {run.entry.return_code}, "
                  f"AERMOD {run.entry.aermod_version}, {run.entry.warnings}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])

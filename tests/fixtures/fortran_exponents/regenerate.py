#!/usr/bin/env python3
"""Re-record the AERMOD runs in this directory (see README.md).

Usage::

    python tests/fixtures/fortran_exponents/regenerate.py [path/to/aermod]
    python tests/fixtures/fortran_exponents/regenerate.py bin/aermod \\
        --cordero path/to/aermet26135_aermod26135/meteorology

Each case directory holds its deck, ``aermod.inp``. The script runs the
deck in a scratch directory beside the one day of Cordero met kept here
(``CORDERO_1993-05-21.SFC`` and ``.PFL``) and copies back ``aermod.out``,
the output files the deck names (``CASES``) and stdout (``stdout.txt``).

With ``--cordero DIR`` the met day is first cut again from EPA's full
``cordero.sfc`` and ``cordero.pfl`` in ``DIR`` (the ``meteorology``
directory of ``aermet26135_aermod26135`` in EPA's
``aermod_test_cases.zip``): the surface file's header line and its 24
records for 21 May 1993, and the profile file's 24 records for that day,
byte for byte (CRLF line ends included).

The point of these runs is the numbers AERMOD writes with an exponent
of three digits, which Fortran ``E13.6`` editing prints without the
letter E (``0.282465-103``). The script fails if a case's outputs no
longer hold one, since the fixture would then no longer test anything.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MET = ("CORDERO_1993-05-21.SFC", "CORDERO_1993-05-21.PFL")
DAY = (b"1993", b"5", b"21")

#: case -> the outputs (besides aermod.out) the deck writes.
CASES = {
    "washout": ("post_1h.pst", "high_1h.plt", "period.plt"),
    "washout_conc": ("post_1h.pst", "high_1h.plt", "maxi_1h.max", "rank_1h.rnk", "evfile.inp"),
    "events": (),
}

#: A Fortran E-edited number whose exponent did not fit in two digits.
THREE_DIGIT_EXPONENT = re.compile(r"\d\.\d+[-+]\d{3}(?!\d)")


def cut_met(cordero: Path) -> None:
    """Write the 21 May 1993 records of EPA's Cordero met files here."""
    sfc = (cordero / "cordero.sfc").read_bytes().splitlines(keepends=True)
    pfl = (cordero / "cordero.pfl").read_bytes().splitlines(keepends=True)
    day_sfc = [ln for ln in sfc[1:] if tuple(ln.split()[:3]) == DAY]
    day_pfl = [ln for ln in pfl if tuple(ln.split()[:3]) == DAY]
    if len(day_sfc) != 24 or len(day_pfl) != 24:
        raise SystemExit(f"expected 24 hours of 1993-05-21 in {cordero}, got "
                         f"{len(day_sfc)} surface and {len(day_pfl)} profile records")
    (HERE / MET[0]).write_bytes(sfc[0] + b"".join(day_sfc))
    (HERE / MET[1]).write_bytes(b"".join(day_pfl))


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("aermod", nargs="?", default=shutil.which("aermod"))
    parser.add_argument("--cordero", type=Path,
                        help="directory holding EPA's cordero.sfc and cordero.pfl")
    args = parser.parse_args(argv[1:])
    if not args.aermod or not Path(args.aermod).exists():
        print("aermod not found: pass its path or put it on PATH "
              "(build it with scripts/build_aermod.sh)", file=sys.stderr)
        return 1
    exe = str(Path(args.aermod).resolve())
    if args.cordero:
        cut_met(args.cordero)
    status = 0
    for case, outputs in CASES.items():
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copy(HERE / case / "aermod.inp", work)
            for name in MET:
                shutil.copy(HERE / name, work)
            proc = subprocess.run([exe], cwd=work, capture_output=True, check=False)
            for name in ("aermod.out", *outputs):
                shutil.copy(work / name, HERE / case)
            (HERE / case / "stdout.txt").write_bytes(proc.stdout)
            if proc.stderr:
                print(f"{case}: AERMOD wrote to stderr:\n{proc.stderr.decode()}",
                      file=sys.stderr)
            out = (HERE / case / "aermod.out").read_text(encoding="latin-1")
            ok = "AERMOD Finishes Successfully" in out
            print(f"{case}: exit code {proc.returncode}, "
                  f"{'finished' if ok else 'DID NOT FINISH'}")
            status |= not ok
            for name in ("aermod.out", *outputs):
                text = (HERE / case / name).read_text(encoding="latin-1")
                hits = len(THREE_DIGIT_EXPONENT.findall(text))
                print(f"  {name}: {hits} numbers with a three-digit exponent")
                if not hits:
                    status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))

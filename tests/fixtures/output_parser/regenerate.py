#!/usr/bin/env python3
"""Re-record the AERMOD runs in this directory (see README.md).

Usage::

    python tests/fixtures/output_parser/regenerate.py [path/to/aermod] [case ...]

Each case directory holds its deck, ``aermod.inp``. The script runs the
deck in a scratch directory with the met files the case names, then copies
back the ``aermod.out``, the stdout (``stdout.txt``) and any plot files
(``*.plt``) AERMOD produced. Name cases after the binary to re-record only
those.

The met files are the Albany data of ``tests/fixtures/epa_official/``
(1 to 4 March 1988), except for two cases that need met data those four
days do not have:

``calm_missing``
    ``CALM.SFC`` is ``AERMET2.SFC`` with a calm hour (wind speed 0) at
    hour 5 of every day and missing hours (wind speed and direction 999)
    at hour 12 of day 1 and hour 20 of days 2 and 3. It is written by
    :func:`calm_missing_sfc` and kept in the case directory.
``full_year``
    ``YEAR.SFC`` and ``YEAR.PFL`` repeat the four Albany days over every
    day of 1988 (:func:`full_year_met`). They are not real weather, only a
    complete year AERMOD accepts, so the deck can ask for ANNUAL averages
    and the 1-hour SO2 design value. At 1.5 MB each they are not kept;
    this script writes them into the scratch directory.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EPA = HERE.parent / "epa_official"
ALBANY = ("AERMET2.SFC", "AERMET2.PFL")

#: case -> the met files copied beside its deck (from the case or EPA dir).
CASES = {
    "calm_missing": ("CALM.SFC", "AERMET2.PFL"),
    "full_year": (),
    "conc_ddep": ALBANY,
    "ddep_only": ALBANY,
}

# Surface-file columns (0-based) of the reference wind speed and direction.
_WS, _WD = 15, 16


def _set_field(line: str, index: int, value: str) -> str:
    """``line`` with its ``index``-th blank-separated field set to ``value``,
    right-aligned in the field's width."""
    tok = list(re.finditer(r"\S+", line))[index]
    text = value.rjust(tok.end() - tok.start())
    return line[:tok.end() - len(text)] + text + line[tok.end():]


def calm_missing_sfc() -> str:
    lines = (EPA / "AERMET2.SFC").read_text().splitlines(keepends=True)
    out = [lines[0]]
    for line in lines[1:]:
        fields = line.split()
        day, hour = int(fields[2]), int(fields[4])
        if hour == 5:                                   # calm
            line = _set_field(_set_field(line, _WS, "0.00"), _WD, "0.0")
        if (day, hour) in ((1, 12), (2, 20), (3, 20)):  # missing
            line = _set_field(_set_field(line, _WS, "999.0"), _WD, "999.0")
        out.append(line)
    return "".join(out)


def _by_day(lines):
    days: dict = {}
    for line in lines:
        days.setdefault(int(line.split()[2]), []).append(line)
    return [days[d] for d in sorted(days)]


def _redate(line: str, date: dt.date, julian: bool) -> str:
    values = [str(date.year), str(date.month), str(date.day)]
    if julian:
        values.append(str(date.timetuple().tm_yday))
    for i, value in reversed(list(enumerate(values))):
        line = _set_field(line, i, value)
    return line


def full_year_met(target: Path) -> None:
    sfc = (EPA / "AERMET2.SFC").read_text().splitlines(keepends=True)
    pfl = (EPA / "AERMET2.PFL").read_text().splitlines(keepends=True)
    sfc_days, pfl_days = _by_day(sfc[1:]), _by_day(pfl)
    out_sfc, out_pfl = [sfc[0]], []
    day, i = dt.date(1988, 1, 1), 0
    while day.year == 1988:
        out_sfc += [_redate(line, day, True) for line in sfc_days[i % 4]]
        out_pfl += [_redate(line, day, False) for line in pfl_days[i % 4]]
        day += dt.timedelta(days=1)
        i += 1
    (target / "YEAR.SFC").write_text("".join(out_sfc))
    (target / "YEAR.PFL").write_text("".join(out_pfl))


def main(argv: list) -> int:
    exe = argv[1] if len(argv) > 1 else shutil.which("aermod")
    only = argv[2:] or list(CASES)
    unknown = sorted(set(only) - set(CASES))
    if unknown:
        print(f"unknown case(s) {unknown}; the cases are {sorted(CASES)}", file=sys.stderr)
        return 1
    if not exe or not Path(exe).exists():
        print("aermod not found: pass its path or put it on PATH "
              "(build it with scripts/build_aermod.sh)", file=sys.stderr)
        return 1
    exe = str(Path(exe).resolve())
    (HERE / "calm_missing" / "CALM.SFC").write_text(calm_missing_sfc())
    for case in only:
        met = CASES[case]
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copy(HERE / case / "aermod.inp", work)
            for name in met:
                source = HERE / case / name
                shutil.copy(source if source.exists() else EPA / name, work)
            if case == "full_year":
                full_year_met(work)
            proc = subprocess.run([exe], cwd=work, capture_output=True, check=False)
            shutil.copy(work / "aermod.out", HERE / case)
            for plot in sorted(work.glob("*.plt")):
                shutil.copy(plot, HERE / case)
            (HERE / case / "stdout.txt").write_bytes(proc.stdout)
            if proc.stderr:
                print(f"{case}: AERMOD wrote to stderr:\n{proc.stderr.decode()}",
                      file=sys.stderr)
            lines = (HERE / case / "aermod.out").read_text(encoding="latin-1").count("\n")
            print(f"{case}: exit code {proc.returncode}, {lines} lines of aermod.out")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

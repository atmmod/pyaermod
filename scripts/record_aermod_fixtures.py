#!/usr/bin/env python3
"""Record what a real AERMOD binary does with the decks the GUI writes.

The GUI's end-to-end journeys (``tests/e2e/``) replace AERMOD with a fake
that *replays* these recordings: the stdout, the exit code and every file
the binary wrote. Replaying the real binary's behaviour, rather than
hand-writing it, is what lets the journeys catch the defects the
hand-written fakes hid (PLAN-gui.md, D1: AERMOD aborts with fatal error
E480 and still exits with code 0).

Each scenario's deck is built with the library exactly as the GUI writes
it: start from :func:`pyaermod.gui_v2.state._empty_project`, add the
scenario's objects, and render with ``to_aermod_input(validate=False)``.
The ``aertest`` scenario is EPA's AERTEST deck with its paths flattened
(as ``tests/test_real_aermod.py`` does), imported with
:func:`pyaermod.read_aermod_input` and written back, which is what the
GUI will do once it can import decks (WP-G6).

The binary runs in a fresh temporary directory that holds only the deck
(as ``aermod.inp``, the name AERMOD reads) and the met files it names.
Everything the run creates there is kept, under the name AERMOD gave it
(gzipped when it is larger than the repository's 500 KB file limit).

Usage::

    python scripts/record_aermod_fixtures.py                 # aermod on PATH
    python scripts/record_aermod_fixtures.py --aermod bin/aermod
    python scripts/record_aermod_fixtures.py --only albany_e480

Recordings land in ``tests/fixtures/gui/aermod_recordings/<scenario>/``;
see the README there for the layout and the binary they came from.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
EPA_FIXTURES = REPO / "tests" / "fixtures" / "epa_official"
DEFAULT_OUT = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings"
DEFAULT_BUILD_NOTE = (
    "EPA AERMOD v26135 source compiled with gfortran -O2 by "
    "scripts/build_aermod.sh (FFLAGS -O2 -fbounds-check -Wuninitialized)"
)

# Outputs larger than the repository's pre-commit limit
# (check-added-large-files, 500 KB) are stored as <name>.gz; the fake AERMOD
# decompresses them when it replays the run. Only AERTEST's POSTFILE is.
LARGE_OUTPUT_BYTES = 500 * 1024

# The met files every Albany scenario names. They are copied next to the
# deck and referenced by bare name, so no recording carries a path from
# the machine that made it. The fake AERMOD compares met paths by base
# name for the same reason.
ALBANY_MET = ("AERMET2.SFC", "AERMET2.PFL")

# tests/test_real_aermod.py flattens AERTEST's EPA-archive paths the same
# way; keep the two in step.
AERTEST_REWRITES = {
    "../meteorology/AERMET2.SFC": "AERMET2.SFC",
    "../meteorology/AERMET2.PFL": "AERMET2.PFL",
    "../meteorology/aermet2.sfc": "AERMET2.SFC",
    "../meteorology/aermet2.pfl": "AERMET2.PFL",
    "../Outputs/AERTEST_ERRORS.OUT": "AERTEST_ERRORS.OUT",
    "../Outputs/AERTEST.SUM": "AERTEST.SUM",
    "../plotfiles/AERTEST_01H.PLT": "AERTEST_01H.PLT",
    "../postfiles/AERTEST_01H.PST": "AERTEST_01H.PST",
}


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def _albany_project(averaging_periods: List[str], surface_file: str):
    """The "Albany stack" reference scenario of PLAN-gui.md."""
    from pyaermod.gui_v2.state import _empty_project
    from pyaermod.input_generator import PointSource, PolarGrid, PollutantType

    project = _empty_project()
    project.control.title_one = "Albany stack reference scenario"
    project.control.pollutant_id = PollutantType.SO2
    project.control.averaging_periods = list(averaging_periods)
    project.sources.sources.append(PointSource(
        source_id="STACK1", x_coord=0.0, y_coord=0.0,
        stack_height=65.0, stack_temp=425.0, exit_velocity=18.0,
        stack_diameter=3.0, emission_rate=100.0,
    ))
    # The GUI's default polar grid: 10 rings from 100 m in 100 m steps,
    # 36 radials from 0 degrees in 10 degree steps.
    project.receptors.polar_grids.append(PolarGrid(
        grid_name="GRID1", x_origin=0.0, y_origin=0.0,
        dist_init=100.0, dist_num=10, dist_delta=100.0,
        dir_init=0.0, dir_num=36, dir_delta=10.0,
    ))
    project.meteorology.surface_file = surface_file
    project.meteorology.profile_file = "AERMET2.PFL"
    project.meteorology.surface_station_id = 14735
    project.meteorology.upper_air_station_id = 14735
    project.meteorology.data_start_year = 1988
    return project


def _aertest_source() -> str:
    """EPA's AERTEST deck with its archive-relative paths flattened."""
    text = (EPA_FIXTURES / "aertest.inp").read_text(encoding="utf-8")
    for old, new in AERTEST_REWRITES.items():
        text = text.replace(old, new)
    return text


def _aertest_deck(source_path: Path) -> str:
    from pyaermod.input_reader import read_aermod_input

    return read_aermod_input(source_path).to_aermod_input(validate=False)


@dataclass
class Scenario:
    name: str
    description: str
    met_files: tuple
    # Returns the deck text; receives the run directory so a scenario can
    # write auxiliary inputs there first (aertest writes its source deck).
    build_deck: Callable[[Path], str]
    # Extra input files to keep in the recording, beside the deck.
    keep_inputs: tuple = ()


def _scenarios() -> Dict[str, Scenario]:
    def albany(periods: List[str], surface: str = "AERMET2.SFC"):
        return lambda _run_dir: _albany_project(periods, surface).to_aermod_input(
            validate=False,
        )

    def aertest(run_dir: Path) -> str:
        source = run_dir / "aertest.inp"
        source.write_text(_aertest_source(), encoding="utf-8")
        return _aertest_deck(source)

    return {
        "albany_success": Scenario(
            name="albany_success",
            description=(
                "PLAN-gui.md reference scenario (Albany stack) with averaging "
                "periods 1, 3, 24 and PERIOD. Runs to completion."
            ),
            met_files=ALBANY_MET,
            build_deck=albany(["1", "3", "24", "PERIOD"]),
        ),
        "albany_e480": Scenario(
            name="albany_e480",
            description=(
                "The reference scenario with averaging periods 1 and ANNUAL, "
                "which are the GUI's defaults. Four days of met data are less "
                "than the year ANNUAL needs, so AERMOD stops with fatal error "
                "E480 after processing every hour, and still exits with code 0."
            ),
            met_files=ALBANY_MET,
            build_deck=albany(["1", "ANNUAL"]),
        ),
        "missing_met": Scenario(
            name="missing_met",
            description=(
                "The reference scenario with the GUI's default averaging "
                "periods (1 and ANNUAL) and a surface file, MISSING.SFC, that "
                "does not exist. AERMOD stops during setup with fatal error "
                "E500 and exits with code 0."
            ),
            met_files=("AERMET2.PFL",),
            build_deck=albany(["1", "ANNUAL"], surface="MISSING.SFC"),
        ),
        "aertest": Scenario(
            name="aertest",
            description=(
                "EPA's AERTEST deck (tests/fixtures/epa_official/aertest.inp) "
                "with its paths flattened as tests/test_real_aermod.py does, "
                "imported with read_aermod_input and written back with "
                "to_aermod_input(validate=False). aertest.inp is the "
                "flattened EPA deck that a user imports; aermod.inp is the "
                "deck the GUI then writes."
            ),
            met_files=ALBANY_MET,
            build_deck=aertest,
            keep_inputs=("aertest.inp",),
        ),
    }


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"\*\*\*\s+AERMOD - VERSION\s+(\S+)\s+\*\*\*")
_TOTAL_RE = re.compile(
    r"A Total of\s+(\d+)\s+(Fatal Error|Warning|Informational) Message",
)


def _out_summary(out_text: str) -> dict:
    """Version and final message counts, read from the .out file."""
    version = _VERSION_RE.search(out_text)
    totals: Dict[str, int] = {}
    # The .out repeats the message summary after setup and at the end of
    # the run; the last one is the verdict.
    for count, kind in _TOTAL_RE.findall(out_text):
        totals[kind] = int(count)
    return {
        "aermod_version": version.group(1) if version else None,
        "fatal_errors": totals.get("Fatal Error"),
        "warnings": totals.get("Warning"),
        "informational": totals.get("Informational"),
        "finishes_successfully": "AERMOD Finishes Successfully" in out_text,
    }


def _maxima(out_path: Path) -> Optional[dict]:
    """Highest value per averaging period, as the library parses it."""
    from pyaermod.output_parser import AERMODOutputParser

    try:
        results = AERMODOutputParser(str(out_path)).parse()
    except Exception as exc:
        return {"parse_error": f"{type(exc).__name__}: {exc}"}
    return {
        period: {
            "value": float(c.max_value),
            "x": float(c.max_location[0]),
            "y": float(c.max_location[1]),
            "units": c.units,
        }
        for period, c in results.concentrations.items()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(scenario: Scenario, aermod: Path, out_root: Path, *,
           build_note: str, date: str, timeout: int) -> dict:
    target = out_root / scenario.name
    with tempfile.TemporaryDirectory(prefix=f"record_{scenario.name}_") as tmp:
        run_dir = Path(tmp)
        for name in scenario.met_files:
            shutil.copy2(EPA_FIXTURES / name, run_dir / name)
        deck = scenario.build_deck(run_dir)
        (run_dir / "aermod.inp").write_text(deck, encoding="utf-8")
        before = {p.name for p in run_dir.iterdir()}

        proc = subprocess.run(
            [str(aermod)], cwd=run_dir, capture_output=True,
            timeout=timeout, check=False,
        )

        created = sorted(p for p in run_dir.iterdir()
                         if p.name not in before and p.is_file())
        if target.exists():
            shutil.rmtree(target)
        (target / "outputs").mkdir(parents=True)
        shutil.copy2(run_dir / "aermod.inp", target / "aermod.inp")
        for name in scenario.keep_inputs:
            shutil.copy2(run_dir / name, target / name)
        for path in created:
            data = path.read_bytes()
            if len(data) > LARGE_OUTPUT_BYTES:
                # mtime=0 keeps the archive byte-identical between recordings.
                (target / "outputs" / f"{path.name}.gz").write_bytes(
                    gzip.compress(data, mtime=0))
            else:
                shutil.copy2(path, target / "outputs" / path.name)
        (target / "stdout.txt").write_bytes(proc.stdout)
        (target / "stderr.txt").write_bytes(proc.stderr)

    out_file = target / "outputs" / "aermod.out"
    out_text = (out_file.read_text(encoding="latin-1")
                if out_file.exists() else "")
    manifest = {
        "scenario": scenario.name,
        "description": scenario.description,
        **_out_summary(out_text),
        "exit_code": proc.returncode,
        "build": build_note,
        "aermod_sha256": _sha256(aermod),
        "recorded": date,
        "command": "aermod",
        "working_directory": (
            "a fresh temporary directory holding aermod.inp and the met "
            "files it names"
        ),
        "recorder": "python scripts/record_aermod_fixtures.py",
        "deck": "aermod.inp",
        "inputs": list(scenario.keep_inputs),
        "met_files": list(scenario.met_files),
        "stdout": "stdout.txt",
        "stderr": "stderr.txt",
        "outputs": sorted(p.name.removesuffix(".gz")
                          for p in (target / "outputs").iterdir()),
        "gzipped_outputs": sorted(p.name.removesuffix(".gz")
                                  for p in (target / "outputs").glob("*.gz")),
        "maxima": _maxima(out_file) if out_file.exists() else None,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    scenarios = _scenarios()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--aermod", help="AERMOD binary (default: aermod on PATH)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"recordings root (default: {DEFAULT_OUT.relative_to(REPO)})")
    ap.add_argument("--only", nargs="+", choices=sorted(scenarios),
                    help="record only these scenarios")
    ap.add_argument("--build-note", default=DEFAULT_BUILD_NOTE,
                    help="how the binary was built, for the manifest")
    ap.add_argument("--date", default=_dt.date.today().isoformat(),
                    help="recording date for the manifest (default: today)")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args(argv)

    found = args.aermod or shutil.which("aermod")
    if not found or not Path(found).exists():
        ap.error("no AERMOD binary: put aermod on PATH or pass --aermod "
                 "(build one with scripts/build_aermod.sh aermod)")
    aermod = Path(found).resolve()

    for name in args.only or list(scenarios):
        manifest = record(scenarios[name], aermod, args.out,
                          build_note=args.build_note, date=args.date,
                          timeout=args.timeout)
        maxima = manifest["maxima"] or {}
        peaks = ", ".join(
            f"{p} {m['value']:g} at ({m['x']:g}, {m['y']:g})"
            for p, m in maxima.items() if isinstance(m, dict)
        )
        print(
            f"{name}: exit {manifest['exit_code']}, "
            f"version {manifest['aermod_version']}, "
            f"{manifest['fatal_errors']} fatal, {manifest['warnings']} warnings, "
            f"outputs {manifest['outputs']}"
            + (f"\n    maxima: {peaks}" if peaks else "")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

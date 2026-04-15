"""
pyaermod command-line interface.

Installed as the `pyaermod` console script (see pyproject.toml).
Subcommands wrap the library's most common workflows so users don't
have to write a Python harness for every run.

Subcommands
-----------

``pyaermod info``
    Print package version + feature availability.

``pyaermod validate INPUT``
    Parse INPUT (.inp file), run base + advanced validation, print the
    findings. Exits 1 if any error-severity finding is present.

``pyaermod run INPUT [--working-dir DIR] [--timeout SECS]``
    Parse and validate INPUT, then execute AERMOD. Summarizes the run
    (success, runtime, output files) and returns non-zero on failure.

``pyaermod parse OUTPUT``
    Parse an AERMOD .out file and print a summary (run info, averaging
    periods, peak concentrations per source group).

``pyaermod plotfile FILE``
    Parse a PLOTFILE / MAXIFILE / RANKFILE / deposition file and print
    its headline stats (record count, peak value, receptor range).

``pyaermod profile INPUT --profile NAME [--apply]``
    Lint INPUT against a named regulatory profile (EPA-AppendixW-2017,
    EPA-AppendixW-2023, Screening). With ``--apply``, mutates the
    project in-place and rewrites INPUT.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__


def _cmd_info(args: argparse.Namespace) -> int:
    from . import print_info
    from .api import HAS_GEOSPATIAL, HAS_TERRAIN
    print_info()
    print("Optional dependencies:")
    print(f"  geospatial (pyproj / geopandas / rasterio): "
          f"{'yes' if HAS_GEOSPATIAL else 'no'}")
    print(f"  terrain (requests-based DEM download):     "
          f"{'yes' if HAS_TERRAIN else 'no'}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from .input_reader import read_aermod_input
    from .validator import Validator

    project = read_aermod_input(args.input)
    result = Validator.validate(project, check_files=args.check_files)

    err_count = result.error_count
    warn_count = result.warning_count
    if not result.errors:
        print(f"{args.input}: OK (no findings)")
        return 0

    print(f"{args.input}: {err_count} error(s), {warn_count} warning(s)")
    for e in result.errors:
        print(f"  {e}")
    return 1 if err_count else 0


def _cmd_run(args: argparse.Namespace) -> int:
    from .input_reader import read_aermod_input
    from .runner import AERMODRunner
    from .runner_utils import summarize_failure
    from .validator import Validator

    inp = Path(args.input).resolve()
    project = read_aermod_input(inp)
    result = Validator.validate(project, check_files=False)
    if result.error_count and not args.force:
        print(f"Aborting: {result.error_count} validation error(s).")
        print("Re-run with --force to ignore, or fix:")
        for e in result.errors:
            if e.severity == "error":
                print(f"  {e}")
        return 2

    runner = AERMODRunner(executable_path=args.executable)
    work_dir = Path(args.working_dir or inp.parent).resolve()
    print(f"Running AERMOD on {inp} (workdir={work_dir}) ...")
    run_result = runner.run(str(inp), working_dir=str(work_dir),
                            timeout=args.timeout)
    if run_result.success:
        print(f"Success in {run_result.runtime_seconds:.1f}s")
        for tag, path in (
            ("out", run_result.output_file),
            ("err", run_result.error_file),
            ("sum", run_result.summary_file),
        ):
            if path:
                print(f"  {tag}: {path}")
        return 0

    print(f"AERMOD failed (return_code={run_result.return_code})")
    print(summarize_failure(str(inp), str(work_dir)))
    return run_result.return_code or 1


def _cmd_parse(args: argparse.Namespace) -> int:
    from .output_parser import parse_aermod_output

    results = parse_aermod_output(args.output)
    info = getattr(results, "run_info", None)
    print(f"AERMOD output: {args.output}")
    if info:
        print(f"  version:     {getattr(info, 'version', '?') or '?'}")
        print(f"  jobname:     {getattr(info, 'jobname', '?') or '?'}")
        if getattr(info, "pollutant_id", None):
            print(f"  pollutant:   {info.pollutant_id}")
        if getattr(info, "averaging_periods", None):
            print(f"  averaging:   {' '.join(info.averaging_periods)}")
    ncs = getattr(results, "concentrations", None)
    if ncs is not None and len(ncs):
        print(f"  {len(ncs)} concentration records")
        periods = sorted({r.averaging_period for r in ncs
                          if hasattr(r, "averaging_period")})
        for period in periods:
            peaks = [r.concentration for r in ncs
                     if hasattr(r, "averaging_period")
                     and r.averaging_period == period]
            if peaks:
                print(f"    {period:<8s} peak = {max(peaks):.4g}")
    return 0


def _cmd_plotfile(args: argparse.Namespace) -> int:
    from .aermod_outputs import read_aermod_aux_file

    result = read_aermod_aux_file(args.file)
    h = result.header
    print(f"{args.file}")
    print(f"  type:         {h.file_type or 'unknown'}")
    print(f"  averaging:    {h.averaging_period or '?'}")
    print(f"  source grp:   {h.source_group or '?'}")
    print(f"  records:      {result.n_records}")
    # Try to find a concentration-like column and report extrema
    for col in ("CONC", "AVERAGE", "VALUE"):
        if col in result.column_names:
            vals = [r[col] for r in result.records
                    if isinstance(r[col], (int, float))]
            if vals:
                print(f"  {col} range:  {min(vals):.4g} .. {max(vals):.4g}")
                break
    return 0


def _cmd_profile(args: argparse.Namespace) -> int:
    from .input_reader import read_aermod_input
    from .regulatory import get_profile

    project = read_aermod_input(args.input)
    try:
        profile = get_profile(args.profile)
    except KeyError as e:
        print(f"Unknown profile: {e}", file=sys.stderr)
        return 2

    if args.apply:
        changes = profile.apply(project)
        # Rewrite the file
        project.write(args.input)
        print(f"Applied {profile.name} -> {args.input}")
        for c in changes:
            print(f"  changed: {c}")
    warnings = profile.check(project)
    if not warnings:
        print(f"{args.input}: clean against {profile.name}")
        return 0
    print(f"{args.input}: {len(warnings)} findings vs {profile.name}")
    for w in warnings:
        print(f"  {w}")
    return 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pyaermod",
        description="pyaermod command-line interface",
    )
    p.add_argument("--version", action="version",
                   version=f"pyaermod {__version__}")
    sub = p.add_subparsers(dest="subcommand", required=True)

    sp = sub.add_parser("info", help="Print package info")
    sp.set_defaults(func=_cmd_info)

    sp = sub.add_parser("validate", help="Validate an AERMOD .inp file")
    sp.add_argument("input", help="Path to the .inp file")
    sp.add_argument("--check-files", action="store_true",
                    help="Verify SURFFILE / PROFFILE etc. exist on disk")
    sp.set_defaults(func=_cmd_validate)

    sp = sub.add_parser("run", help="Validate + execute AERMOD on an .inp file")
    sp.add_argument("input", help="Path to the .inp file")
    sp.add_argument("--executable", help="Path to the aermod binary "
                                          "(defaults to $PATH lookup)")
    sp.add_argument("--working-dir", help="Run directory (defaults to input's dir)")
    sp.add_argument("--timeout", type=int, default=3600,
                    help="Max seconds to let AERMOD run (default 3600)")
    sp.add_argument("--force", action="store_true",
                    help="Run even if validation reports errors")
    sp.set_defaults(func=_cmd_run)

    sp = sub.add_parser("parse", help="Parse an AERMOD .out log")
    sp.add_argument("output", help="Path to the .out file")
    sp.set_defaults(func=_cmd_parse)

    sp = sub.add_parser("plotfile", help="Parse an AERMOD auxiliary output "
                                         "(PLOTFILE / MAXIFILE / RANKFILE / "
                                         "deposition)")
    sp.add_argument("file", help="Path to the plot/max/rank file")
    sp.set_defaults(func=_cmd_plotfile)

    sp = sub.add_parser("profile",
                        help="Lint or apply a regulatory profile to an .inp file")
    sp.add_argument("input", help="Path to the .inp file")
    sp.add_argument("--profile", required=True,
                    help="Profile name (e.g. EPA-AppendixW-2017)")
    sp.add_argument("--apply", action="store_true",
                    help="Mutate the project to satisfy the profile and "
                         "rewrite INPUT in place")
    sp.set_defaults(func=_cmd_profile)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    sys.exit(main())

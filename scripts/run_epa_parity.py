#!/usr/bin/env python3
"""
Generate a Markdown parity report against the EPA AERMOD test-case suite.

Runs every input deck in the selected EPA reference set
(``test_cases/aermet*_aermod*/inputs/``) through the local AERMOD binary,
scores each produced POSTFILE against the EPA reference of the same name,
and writes a per-case results table to stdout (or to ``--output`` if
specified).

The reference set is chosen by :func:`pyaermod.epa_testcases.find_epa_testcase_set`:
``--testcase-dir`` / ``$PYAERMOD_EPA_TESTCASES`` if given, else the set
under ``test_cases/`` whose AERMOD version matches the ``aermod`` binary
on PATH (both EPA naming conventions are accepted), else the newest set.

Pass criterion: best-fit slope within ±0.001 of 1.0, matching EPA's own
``Compare_AERMOD_test_cases.R`` margin.

Usage::

    python scripts/run_epa_parity.py
    python scripts/run_epa_parity.py --output docs/validation.md
    python scripts/run_epa_parity.py --filter aertest
    python scripts/run_epa_parity.py --testcase-dir test_cases/aermet24142_aermod26135

Exit status: 0 if every comparison passes, 1 if any fails, 2 if the
fixtures or the AERMOD binary cannot be found.

Skips MULTYEAR-chained decks (run via the dedicated chained test).
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pyaermod import __version__ as PYAERMOD_VERSION  # noqa: E402
from pyaermod.epa_testcases import (  # noqa: E402
    ENV_VAR,
    EPATestCaseSet,
    aermod_binary_version,
    find_epa_testcase_set,
    read_aermod_version,
)
from pyaermod.regulatory_parity import (  # noqa: E402
    DEFAULT_SLOPE_TOLERANCE,
    ParityScore,
    score_postfile_pair,
)
from pyaermod.runner import AERMODRunner  # noqa: E402

TESTCASE_ROOT = ROOT / "test_cases"


def _stage_workdir(work: Path, deck_name: str, epa: EPATestCaseSet) -> Path:
    """Stage inputs + met data so relative paths in the deck resolve."""
    for sub in ("inputs", "meteorology", "postfiles", "plotfiles", "Outputs"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(epa.inputs / deck_name, work / "inputs" / deck_name)
    for f in epa.inputs.iterdir():
        if f.is_file() and f.suffix.lower() != ".inp":
            shutil.copy2(f, work / "inputs" / f.name)
    for f in epa.meteorology.iterdir():
        if f.is_file():
            shutil.copy2(f, work / "meteorology" / f.name)
    return work / "inputs"


def _run_one(deck_name: str, scratch: Path, runner: AERMODRunner,
             epa: EPATestCaseSet, *, clean: bool = False) -> List[ParityScore]:
    """Run one deck and return parity scores for each PST emitted.

    With ``clean=True`` the deck's staged working tree is deleted after
    scoring (keeping only the ``.out`` needed for the version banner), so
    a full-suite run does not accumulate gigabytes of copied met data.
    """
    work = scratch / deck_name.replace(".inp", "")
    work.mkdir()
    inputs_dir = _stage_workdir(work, deck_name, epa)
    res = runner.run(input_file=inputs_dir / deck_name,
                     working_dir=inputs_dir, timeout=300)
    if not res.success:
        scores = [ParityScore(case=f"{deck_name} (run failed)", n_paired=0,
                              slope=float("nan"), mean_abs_error=float("nan"),
                              norm_mean_error=float("nan"),
                              max_abs_error=float("nan"),
                              ref_max=0.0, cand_max=0.0)]
    else:
        scores = []
        for cand in (work / "postfiles").glob("*.PST"):
            ref = epa.postfiles / cand.name
            if ref.exists():
                scores.append(score_postfile_pair(ref, cand, case=cand.name))
    if clean:
        for sub in ("meteorology", "postfiles", "plotfiles", "Outputs"):
            shutil.rmtree(work / sub, ignore_errors=True)
        for f in inputs_dir.iterdir():
            if f.is_file() and f.suffix.lower() != ".out":
                f.unlink()
    return scores


def _first_line(cmd: List[str], cwd: Optional[Path] = None) -> Optional[str]:
    """First stdout line of `cmd`, or None if it cannot be run / fails."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              errors="replace", timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (proc.stdout or "").strip().splitlines()
    return lines[0].strip() if proc.returncode == 0 and lines else None


def _git_describe() -> str:
    """Short SHA of HEAD, suffixed ``-dirty`` if the tree has changes."""
    sha = _first_line(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT)
    if sha is None:
        return "unknown (not a git checkout)"
    try:
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                cwd=ROOT, capture_output=True, text=True,
                                timeout=30, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        status = ""
    return f"{sha}-dirty" if status else sha


def _aermod_version_from_runs(scratch: Path) -> Optional[str]:
    """AERMOD version banner from any ``.out`` the harness produced."""
    for out in sorted(scratch.glob("*/inputs/*.out")):
        version = read_aermod_version(out)
        if version:
            return version
    return None


def _collect_provenance(epa: EPATestCaseSet, aermod_exe: str,
                        probed_version: Optional[str],
                        scratch: Path) -> List[Tuple[str, str]]:
    """Facts that pin down what this report was generated with.

    The AERMOD version is taken from the ``*** AERMOD - VERSION NNNNN ***``
    banner of a produced ``.out`` (the binary that actually ran); the
    ``--help`` probe is the fallback when no deck produced output.
    """
    run_version = _aermod_version_from_runs(scratch)
    if run_version:
        aermod_version = f"{run_version} (from run banner)"
    elif probed_version:
        aermod_version = f"{probed_version} (from `aermod --help`; no run output)"
    else:
        aermod_version = "unknown"
    return [
        ("Generated (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")),
        ("AERMOD version", aermod_version),
        ("AERMOD binary", aermod_exe),
        ("Compiler (`gfortran --version` on PATH)",
         _first_line(["gfortran", "--version"]) or "unavailable"),
        ("EPA reference set", epa.describe()),
        ("pyaermod", PYAERMOD_VERSION),
        ("Git commit", _git_describe()),
        ("Platform", f"{platform.platform()}; Python {platform.python_version()}"),
    ]


def _format_markdown(scores: List[ParityScore],
                     wall_time: float,
                     provenance: Optional[List[Tuple[str, str]]] = None) -> str:
    n_total = len(scores)
    n_pass = sum(1 for s in scores if s.passes())
    n_fail = n_total - n_pass
    lines = [
        "# EPA AERMOD Test-Suite Parity Report",
        "",
        f"Generated by `scripts/run_epa_parity.py` in {wall_time:.1f}s.",
        "",
    ]
    if provenance:
        lines += [
            "## Provenance",
            "",
            "| Field | Value |",
            "|-------|-------|",
        ]
        lines += [f"| {k} | {v} |" for k, v in provenance]
        lines.append("")
    lines += [
        "Pass criterion: best-fit slope of paired (reference, candidate) "
        f"concentrations within ±{DEFAULT_SLOPE_TOLERANCE} of 1.0, matching "
        "EPA's own `Compare_AERMOD_test_cases.R` published margin.",
        "",
        f"**Result: {n_pass} / {n_total} POSTFILE comparisons within tolerance.**",
        "",
        "| Case | Pass | Slope | n paired | Mean |Δ| | Ref max | Cand max |",
        "|------|:----:|------:|---------:|----------:|--------:|---------:|",
    ]
    for s in sorted(scores, key=lambda r: r.case):
        mark = "✅" if s.passes() else "❌"
        slope = f"{s.slope:.6f}" if s.slope == s.slope else "n/a"
        mae = f"{s.mean_abs_error:.4g}" if s.mean_abs_error == s.mean_abs_error else "n/a"
        lines.append(
            f"| {s.case} | {mark} | {slope} | {s.n_paired} | "
            f"{mae} | {s.ref_max:.4g} | {s.cand_max:.4g} |"
        )
    if n_fail:
        lines += ["", "## Failures", ""]
        for s in (s for s in scores if not s.passes()):
            lines.append(
                f"- **{s.case}** — slope={s.slope:.6f}, n={s.n_paired}, "
                f"mean|Δ|={s.mean_abs_error:.4g}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=None,
                    help="Markdown report path (default: stdout)")
    ap.add_argument("--filter", default="",
                    help="Substring filter for deck names")
    ap.add_argument("--scratch", type=Path, default=None,
                    help="Scratch dir for runs (default: temp)")
    ap.add_argument("--testcase-dir", type=Path, default=None,
                    help=("EPA reference set to score against (default: "
                          f"${ENV_VAR}, else the test_cases/aermet*_aermod* set "
                          "matching the aermod binary's version, else the newest)"))
    ap.add_argument("--clean-scratch", action="store_true",
                    help="Delete each deck's staged working tree after scoring "
                         "(keeps disk use flat; the .out files are retained)")
    args = ap.parse_args()

    aermod_exe = shutil.which("aermod")
    if aermod_exe is None:
        print("AERMOD binary not on PATH", file=sys.stderr)
        return 2
    aermod_version = aermod_binary_version(aermod_exe)

    env = dict(os.environ)
    if args.testcase_dir is not None:
        env[ENV_VAR] = str(args.testcase_dir)
    epa: Optional[EPATestCaseSet] = find_epa_testcase_set(
        TESTCASE_ROOT, aermod_version=aermod_version, env=env,
    )
    if epa is None or not epa.exists():
        where = epa.path if epa is not None else TESTCASE_ROOT
        print(f"EPA test cases not found at {where}", file=sys.stderr)
        return 2
    print(f"  reference set: {epa.describe()}; aermod {aermod_version or '?'} "
          f"at {aermod_exe}", file=sys.stderr)
    if aermod_version and epa.aermod_version and aermod_version != epa.aermod_version:
        print(f"  WARNING: binary is AERMOD {aermod_version} but the reference set "
              f"was produced by AERMOD {epa.aermod_version}", file=sys.stderr)

    decks = sorted(p.name for p in epa.inputs.glob("*.inp"))
    if args.filter:
        decks = [d for d in decks if args.filter in d]
    # Skip MULTYEAR-chained decks (need shared workdir; not modeled here).
    decks = [d for d in decks
             if "MULTYEAR" not in (epa.inputs / d).read_text(errors="replace").upper()]

    runner = AERMODRunner(log_level="WARNING")
    scratch = args.scratch or Path(f"/tmp/pyaermod_parity_{int(time.time())}")
    scratch.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    all_scores: List[ParityScore] = []
    for deck in decks:
        print(f"  running {deck} ...", file=sys.stderr)
        all_scores.extend(_run_one(deck, scratch, runner, epa,
                                   clean=args.clean_scratch))
    wall = time.perf_counter() - t0

    provenance = _collect_provenance(epa, aermod_exe, aermod_version, scratch)
    md = _format_markdown(all_scores, wall, provenance)
    if args.output:
        args.output.write_text(md, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0 if all(s.passes() for s in all_scores) else 1


if __name__ == "__main__":
    sys.exit(main())

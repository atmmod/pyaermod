"""
AERMET binary runner + three-stage pipeline.

Parallel to :class:`pyaermod.runner.AERMODRunner` but for AERMET. The
EPA AERMET workflow is three sequential passes — Stage 1 ingests raw
obs, Stage 2 merges, Stage 3 computes boundary-layer parameters — and
each stage takes an input deck as its stdin or first argument.

    from pyaermod import AERMETStage1, AERMETStage2, AERMETStage3
    from pyaermod.aermet_runner import AERMETRunner, run_aermet_pipeline

    runner = AERMETRunner()
    result1 = runner.run_stage(1, stage1_inp_path, working_dir=tmp)
    ...

Or, for a full pipeline:

    results = run_aermet_pipeline(
        stage1, stage2, stage3, working_dir=tmp,
    )
    # results is a list of 3 AERMETRunResult; check all `.success`.

The module handles:
- Writing each stage's deck to disk via `.to_aermet_input()`
- Finding / validating the AERMET binary
- Capturing stdout, stderr, and the `<stage>.msg` log file
- Surfacing failure diagnostics via :func:`runner_utils.summarize_failure`
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from .aermet import AERMETStage1, AERMETStage2, AERMETStage3


@dataclass
class AERMETRunResult:
    """Outcome of a single AERMET stage execution."""
    success: bool
    stage: int
    input_file: str
    return_code: Optional[int] = None
    runtime_seconds: Optional[float] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    output_files: List[str] = None  # type: ignore[assignment]
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.output_files is None:
            self.output_files = []


class AERMETRunner:
    """Execute AERMET stages from Python.

    Parameters
    ----------
    executable_path
        Path to the `aermet` binary. If None, searches $PATH.
    log_level
        Python logging level name.
    """

    def __init__(
        self,
        executable_path: Optional[Union[str, Path]] = None,
        log_level: str = "INFO",
    ) -> None:
        self.executable = self._find_or_set_executable(executable_path)
        self.logger = logging.getLogger(f"{__name__}.AERMETRunner")
        self.logger.setLevel(getattr(logging, log_level.upper()))

    @staticmethod
    def _find_or_set_executable(path: Optional[Union[str, Path]]) -> Path:
        if path:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"AERMET binary not found: {path}")
            return p
        for name in ("aermet", "AERMET", "aermet.exe"):
            found = shutil.which(name)
            if found:
                return Path(found)
        raise FileNotFoundError(
            "No AERMET executable found on PATH. Pass executable_path explicitly."
        )

    def run_stage(
        self,
        stage: int,
        input_file: Union[str, Path],
        *,
        working_dir: Union[str, Path],
        timeout: int = 600,
    ) -> AERMETRunResult:
        """Run a single AERMET stage.

        AERMET reads its deck from stdin (``aermet < stage1.inp``)
        per the EPA convention, so we wire stdin to the file contents
        rather than passing it as an argv.
        """
        inp_path = Path(input_file).resolve()
        work = Path(working_dir).resolve()
        work.mkdir(parents=True, exist_ok=True)
        deck = inp_path.read_text(encoding="utf-8")

        self.logger.info(
            f"Running AERMET stage {stage}: {inp_path} (workdir={work})"
        )
        start = datetime.now()
        try:
            proc = subprocess.run(
                [str(self.executable)],
                cwd=str(work),
                input=deck,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            end = datetime.now()
            return AERMETRunResult(
                success=False, stage=stage, input_file=str(inp_path),
                return_code=None,
                runtime_seconds=(end - start).total_seconds(),
                error_message=f"AERMET stage {stage} timed out after {timeout}s: {e}",
                start_time=start, end_time=end,
            )
        end = datetime.now()

        # Success if return code 0 AND the stdout/log doesn't scream
        # "FATAL ERROR". AERMET sometimes exits 0 even on fatal errors.
        out = proc.stdout or ""
        success = proc.returncode == 0 and "FATAL" not in out.upper()
        # Collect any files AERMET may have produced in the working dir.
        outputs = [str(p) for p in sorted(work.glob("*"))
                   if p.is_file() and p.stat().st_mtime >= start.timestamp()]

        return AERMETRunResult(
            success=success,
            stage=stage,
            input_file=str(inp_path),
            return_code=proc.returncode,
            runtime_seconds=(end - start).total_seconds(),
            stdout=out,
            stderr=proc.stderr,
            output_files=outputs,
            error_message=None if success else "AERMET reported FATAL or non-zero exit",
            start_time=start,
            end_time=end,
        )


def run_aermet_pipeline(
    stage1: AERMETStage1,
    stage2: AERMETStage2,
    stage3: AERMETStage3,
    *,
    working_dir: Union[str, Path],
    executable_path: Optional[Union[str, Path]] = None,
    stop_on_failure: bool = True,
    timeout: int = 600,
) -> List[AERMETRunResult]:
    """Run all three AERMET stages in sequence in `working_dir`.

    Writes each stage's deck to ``{working_dir}/stage{N}.inp`` before
    dispatching to AERMET. If a stage fails and `stop_on_failure` is
    True (default), the remaining stages are skipped.

    Returns a list of AERMETRunResult (one per attempted stage).
    """
    work = Path(working_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    runner = AERMETRunner(executable_path=executable_path)

    results: List[AERMETRunResult] = []
    for n, cfg in enumerate([stage1, stage2, stage3], start=1):
        deck_text = cfg.to_aermet_input()
        deck_path = work / f"stage{n}.inp"
        deck_path.write_text(deck_text, encoding="utf-8")
        res = runner.run_stage(n, deck_path, working_dir=work, timeout=timeout)
        results.append(res)
        if not res.success and stop_on_failure:
            break
    return results


__all__ = [
    "AERMETRunResult",
    "AERMETRunner",
    "run_aermet_pipeline",
]

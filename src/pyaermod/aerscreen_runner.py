"""
AERSCREEN binary runner.

Parallels :class:`pyaermod.aersurface_runner.AERSURFACERunner`. AERSCREEN
is EPA's screening front-end to AERMOD; the runner stages the deck as
``aerscreen.inp`` in the working directory, dispatches to the binary,
and surfaces stdout / stderr / output-file diagnostics.

Typical usage::

    from pyaermod import AERSCREENConfig, AERSCREENSourceType
    from pyaermod.aerscreen_runner import AERSCREENRunner

    cfg = AERSCREENConfig(...)
    runner = AERSCREENRunner()
    result = runner.run(cfg, working_dir="/tmp/aerscreen_so2")
    if result.success:
        # result.output_files contains the .out summary, .pst per-distance
        # impact table, and the full AERMOD-equivalent run logs.
        pass
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from .aerscreen import AERSCREENConfig
from .runner import _read_capped


@dataclass
class AERSCREENRunResult:
    """Outcome of an AERSCREEN execution."""
    success: bool
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


class AERSCREENRunner:
    """Execute AERSCREEN from Python.

    Parameters
    ----------
    executable_path
        Path to the ``aerscreen`` binary. If None, searches $PATH.
    log_level
        Python logging level name.
    """

    def __init__(
        self,
        executable_path: Optional[Union[str, Path]] = None,
        log_level: str = "INFO",
    ) -> None:
        self.executable = self._find_or_set_executable(executable_path)
        self.logger = logging.getLogger(f"{__name__}.AERSCREENRunner")
        self.logger.setLevel(getattr(logging, log_level.upper()))

    @staticmethod
    def _find_or_set_executable(path: Optional[Union[str, Path]]) -> Path:
        if path:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"AERSCREEN binary not found: {path}")
            return p
        for name in ("aerscreen", "AERSCREEN", "aerscreen.exe"):
            found = shutil.which(name)
            if found:
                return Path(found)
        raise FileNotFoundError(
            "No AERSCREEN executable found on PATH. Pass executable_path "
            "explicitly."
        )

    def run(
        self,
        config: AERSCREENConfig,
        *,
        working_dir: Union[str, Path],
        timeout: int = 1800,
    ) -> AERSCREENRunResult:
        """Run AERSCREEN against a configured deck."""
        work = Path(working_dir).resolve()
        work.mkdir(parents=True, exist_ok=True)

        deck_path = work / "aerscreen.inp"
        deck_path.write_text(config.to_aerscreen_input(), encoding="utf-8")

        self.logger.info(
            f"Running AERSCREEN: {deck_path} (workdir={work})"
        )
        start = datetime.now()
        stdout_path = work / "aerscreen.subproc.stdout"
        stderr_path = work / "aerscreen.subproc.stderr"
        # File-redirect to avoid the OS pipe-buffer deadlock — same fix
        # as the AERMOD/AERMET/AERMAP/AERSURFACE runners.
        stdout_fh = open(  # noqa: SIM115
            stdout_path, "w", encoding="utf-8", errors="replace"
        )
        stderr_fh = open(  # noqa: SIM115
            stderr_path, "w", encoding="utf-8", errors="replace"
        )
        try:
            try:
                proc = subprocess.run(
                    [str(self.executable)],
                    cwd=str(work),
                    text=True,
                    stdout=stdout_fh, stderr=stderr_fh,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                end = datetime.now()
                return AERSCREENRunResult(
                    success=False, input_file=str(deck_path),
                    return_code=None,
                    runtime_seconds=(end - start).total_seconds(),
                    error_message=(
                        f"AERSCREEN timed out after {timeout}s: {e}"
                    ),
                    start_time=start, end_time=end,
                )
        finally:
            stdout_fh.close()
            stderr_fh.close()
        end = datetime.now()

        out = _read_capped(stdout_path, 1_000_000)
        err = _read_capped(stderr_path, 1_000_000)
        success = proc.returncode == 0 and "FATAL" not in out.upper()
        outputs = [
            str(p) for p in sorted(work.glob("*"))
            if p.is_file() and p.stat().st_mtime >= start.timestamp()
        ]
        return AERSCREENRunResult(
            success=success,
            input_file=str(deck_path),
            return_code=proc.returncode,
            runtime_seconds=(end - start).total_seconds(),
            stdout=out, stderr=err, output_files=outputs,
            error_message=(
                None if success else "AERSCREEN reported FATAL or non-zero exit"
            ),
            start_time=start, end_time=end,
        )


__all__ = [
    "AERSCREENRunResult",
    "AERSCREENRunner",
]

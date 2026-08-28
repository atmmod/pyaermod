"""
AERSURFACE binary runner.

Parallel to :class:`pyaermod.aermet_runner.AERMETRunner` but for
EPA's AERSURFACE preprocessor, which derives monthly surface
characteristics (albedo, Bowen ratio, surface roughness) from NLCD
land-use rasters for AERMET Stage 3.

Typical usage::

    from pyaermod import AERSURFACEConfig
    from pyaermod.aersurface_runner import AERSURFACERunner

    cfg = AERSURFACEConfig(...)
    runner = AERSURFACERunner()
    result = runner.run(cfg, working_dir="/tmp/aersurface_salem")
    if result.success:
        # result.output_files contains the .sfc characteristic table
        # which can be plugged into AERMETStage3.surface_characteristics
        pass
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from .aersurface import AERSURFACEConfig
from .runner import _read_capped


@dataclass
class AERSURFACERunResult:
    """Outcome of an AERSURFACE execution."""
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


class AERSURFACERunner:
    """Execute AERSURFACE from Python.

    Parameters
    ----------
    executable_path
        Path to the ``aersurface`` binary. If None, searches $PATH.
    log_level
        Python logging level name.
    """

    def __init__(
        self,
        executable_path: Optional[Union[str, Path]] = None,
        log_level: str = "INFO",
    ) -> None:
        self.executable = self._find_or_set_executable(executable_path)
        self.logger = logging.getLogger(f"{__name__}.AERSURFACERunner")
        self.logger.setLevel(getattr(logging, log_level.upper()))

    @staticmethod
    def _find_or_set_executable(path: Optional[Union[str, Path]]) -> Path:
        if path:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"AERSURFACE binary not found: {path}")
            return p
        for name in ("aersurface", "AERSURFACE", "aersurface.exe"):
            found = shutil.which(name)
            if found:
                return Path(found)
        raise FileNotFoundError(
            "No AERSURFACE executable found on PATH. Pass executable_path "
            "explicitly."
        )

    #: Environment variable pointing at a directory of NADCON grid files.
    NADCON_ENV = "PYAERMOD_NADCON_DIR"

    def _stage_nadcon_grids(self, work: Path) -> int:
        """Copy NADCON ``.las`` / ``.los`` grids into the working directory.

        AERSURFACE opens them by bare name (``conus.las``), so they have
        to sit in the directory it runs in. Returns how many were staged.
        """
        candidates = []
        env_dir = os.environ.get(self.NADCON_ENV)
        if env_dir:
            candidates.append(Path(env_dir))
        candidates.append(self.executable.resolve().parent)

        staged = 0
        for directory in candidates:
            if not directory.is_dir():
                continue
            for grid in sorted(directory.glob("*.la[s]")) + sorted(
                directory.glob("*.lo[s]")
            ):
                shutil.copy(grid, work / grid.name)
                staged += 1
            if staged:
                break
        return staged

    def run(
        self,
        config: AERSURFACEConfig,
        *,
        working_dir: Union[str, Path],
        timeout: int = 1800,
    ) -> AERSURFACERunResult:
        """Run AERSURFACE for a configured deck.

        AERSURFACE expects its input deck on stdin or a fixed
        ``aersurface.inp`` file in the cwd, depending on version. We
        use the fixed-filename convention (matching AERMET v24+).
        """
        work = Path(working_dir).resolve()
        work.mkdir(parents=True, exist_ok=True)

        deck_path = work / "aersurface.inp"
        deck_path.write_text(config.to_aersurface_input(), encoding="utf-8")

        if config.datum.upper() == "NAD27":
            staged = self._stage_nadcon_grids(work)
            if not staged:
                return AERSURFACERunResult(
                    success=False, input_file=str(deck_path),
                    return_code=None, runtime_seconds=0.0,
                    error_message=(
                        "datum='NAD27' needs EPA's NADCON grid files "
                        "(conus/alaska/hawaii/prvi .las and .los), which "
                        "AERSURFACE reads from its working directory. None "
                        f"were found beside {self.executable} or in "
                        f"${self.NADCON_ENV}. They ship in EPA's AERSURFACE "
                        "source archive; scripts/build_aersurface.sh "
                        "installs them next to the binary."
                    ),
                )

        self.logger.info(
            f"Running AERSURFACE: {deck_path} (workdir={work})"
        )
        start = datetime.now()
        stdout_path = work / "aersurface.subproc.stdout"
        stderr_path = work / "aersurface.subproc.stderr"
        # File-redirect, not OS pipes — same pipe-deadlock fix as the
        # other runners. AERSURFACE on a continental NLCD can be chatty.
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
                return AERSURFACERunResult(
                    success=False, input_file=str(deck_path),
                    return_code=None,
                    runtime_seconds=(end - start).total_seconds(),
                    error_message=(
                        f"AERSURFACE timed out after {timeout}s: {e}"
                    ),
                    start_time=start, end_time=end,
                )
        finally:
            stdout_fh.close()
            stderr_fh.close()
        end = datetime.now()

        out = _read_capped(stdout_path, 1_000_000)
        err = _read_capped(stderr_path, 1_000_000)
        # AERSURFACE sometimes exits 0 even with FATAL messages logged.
        success = proc.returncode == 0 and "FATAL" not in out.upper()
        outputs = [
            str(p) for p in sorted(work.glob("*"))
            if p.is_file() and p.stat().st_mtime >= start.timestamp()
        ]
        return AERSURFACERunResult(
            success=success,
            input_file=str(deck_path),
            return_code=proc.returncode,
            runtime_seconds=(end - start).total_seconds(),
            stdout=out, stderr=err, output_files=outputs,
            error_message=(
                None if success else "AERSURFACE reported FATAL or non-zero exit"
            ),
            start_time=start, end_time=end,
        )


__all__ = [
    "AERSURFACERunResult",
    "AERSURFACERunner",
]

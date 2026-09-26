"""
AERSCREEN binary runner.

AERSCREEN is interactive and spawns other programs, so running it takes
more staging than the other EPA binaries:

* It reads its answers from stdin, in the order
  :meth:`~pyaermod.aerscreen.AERSCREENConfig.to_stdin_answers` gives
  them, or, when an ``aerscreen.inp`` restart file is in the working
  directory, asks whether to continue with it.
* Before starting a run it checks that ``AERMOD.EXE``, ``MAKEMET.EXE``
  and (when needed) ``BPIPPRM.EXE`` and ``AERMAP.EXE`` exist in the
  working directory, then invokes them through the shell as ``aermod``,
  ``makemet``, ``bpipprm`` and ``aermap``. The runner stages both
  spellings as links to the real binaries and puts the working
  directory first on ``PATH``.
* Its call ``bpipprm <inp> <out> <sum>`` assumes a BPIP-PRIME that takes
  file names; the one ``scripts/build_bpip.sh`` builds reads ``fort.10``
  and writes ``fort.12`` / ``fort.14`` (EPA's OPEN statements are
  commented out), so the staged ``bpipprm`` is a small wrapper that
  bridges the two.
* Auxiliary inputs the configuration names (surface-characteristics
  file, discrete-receptor file, BPIP file, DEMs, NADCON grids) are
  copied in beside it, and ``DEMlist.txt`` is written for terrain runs.

Typical usage::

    from pyaermod import AERSCREENConfig, AERSCREENSourceType
    from pyaermod.aerscreen_runner import AERSCREENRunner

    cfg = AERSCREENConfig(...)
    result = AERSCREENRunner().run(cfg, working_dir="/tmp/aerscreen_so2")
    if result.success:
        print(result.summary.maximum.conc_1hr, "ug/m3 at",
              result.summary.maximum.distance, "m")

Build the binaries with ``scripts/build_aerscreen.sh`` (AERSCREEN and
MAKEMET), ``scripts/build_aermod.sh`` (AERMOD and AERMAP) and
``scripts/build_bpip.sh``.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from .aerscreen import (
    DISCRETE_RECEPTOR_FILE,
    AERSCREENConfig,
    AERSCREENSummary,
    parse_aerscreen_output,
)
from .runner import _read_capped

#: The programs AERSCREEN spawns, and the marker file it checks for each.
_HELPERS = {
    "aermod": "AERMOD.EXE",
    "makemet": "MAKEMET.EXE",
    "bpipprm": "BPIPPRM.EXE",
    "aermap": "AERMAP.EXE",
}

_BPIP_WRAPPER = """#!/bin/sh
# Written by pyaermod.aerscreen_runner. AERSCREEN calls
#   bpipprm <input> <output> <summary>
# but the BPIP-PRIME that scripts/build_bpip.sh builds reads fort.10 and
# writes fort.12 and fort.14 (EPA's OPEN statements are commented out).
rm -f fort.10 fort.12 fort.14
cp "$1" fort.10
"{real}" "$@"
status=$?
[ -f fort.12 ] && mv -f fort.12 "$2"
[ -f fort.14 ] && mv -f fort.14 "$3"
rm -f fort.10
exit $status
"""

#: Lines the NADCON grid files come in pairs of.
_NAD_GRID_SUFFIXES = (".las", ".los")


@dataclass
class AERSCREENRunResult:
    """Outcome of an AERSCREEN execution."""
    success: bool
    input_file: str
    return_code: Optional[int] = None
    runtime_seconds: Optional[float] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    output_files: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    output_file: Optional[str] = None
    log_file: Optional[str] = None
    restart_file: Optional[str] = None
    max_conc_file: Optional[str] = None
    summary: Optional[AERSCREENSummary] = None


class AERSCREENRunner:
    """Execute AERSCREEN from Python.

    Parameters
    ----------
    executable_path
        Path to the ``aerscreen`` binary. If None, searches $PATH.
    aermod_path, makemet_path, bpipprm_path, aermap_path
        The programs AERSCREEN spawns. Each defaults to the first match
        on $PATH; AERMOD and MAKEMET are required for any screening run,
        BPIP-PRIME only with building downwash and AERMAP only with
        terrain, so a missing one is reported when a run needs it.
    log_level
        Python logging level name.
    """

    def __init__(
        self,
        executable_path: Optional[Union[str, Path]] = None,
        *,
        aermod_path: Optional[Union[str, Path]] = None,
        makemet_path: Optional[Union[str, Path]] = None,
        bpipprm_path: Optional[Union[str, Path]] = None,
        aermap_path: Optional[Union[str, Path]] = None,
        log_level: str = "INFO",
    ) -> None:
        self.executable = self._find_or_set_executable(executable_path)
        self.helpers: Dict[str, Optional[Path]] = {
            "aermod": self._optional(aermod_path, "aermod"),
            "makemet": self._optional(makemet_path, "makemet"),
            "bpipprm": self._optional(bpipprm_path, "bpipprm"),
            "aermap": self._optional(aermap_path, "aermap"),
        }
        self.logger = logging.getLogger(f"{__name__}.AERSCREENRunner")
        self.logger.setLevel(getattr(logging, log_level.upper()))

    @staticmethod
    def _find_or_set_executable(path: Optional[Union[str, Path]]) -> Path:
        if path:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"AERSCREEN binary not found: {path}")
            return p.resolve()
        for name in ("aerscreen", "AERSCREEN", "aerscreen.exe"):
            found = shutil.which(name)
            if found:
                return Path(found).resolve()
        raise FileNotFoundError(
            "No AERSCREEN executable found on PATH. Pass executable_path "
            "explicitly (scripts/build_aerscreen.sh builds one into ./bin)."
        )

    @staticmethod
    def _optional(path: Optional[Union[str, Path]], name: str) -> Optional[Path]:
        if path:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"{name} binary not found: {path}")
            return p.resolve()
        for candidate in (name, name.upper(), name + ".exe"):
            found = shutil.which(candidate)
            if found:
                return Path(found).resolve()
        return None

    # ------------------------------------------------------------------
    def required_helpers(self, config: AERSCREENConfig) -> List[str]:
        """The spawned programs this configuration will call."""
        needed = ["makemet"]
        if config.run_aermod:
            needed.insert(0, "aermod")
            if config.downwash:
                needed.append("bpipprm")
            if config.terrain:
                needed.append("aermap")
        return needed

    def stdin_text(self, config: AERSCREENConfig, mode: str) -> str:
        """What the runner types: the prompt answers, or the restart reply."""
        if mode == "restart":
            # readinp shows the restart title and asks "Continue with
            # RESTART File? <press Y>"; validate then waits for <Enter>.
            return "Y\n\n"
        if mode == "prompts":
            return "\n".join(config.to_stdin_answers()) + "\n"
        raise ValueError("mode must be 'prompts' or 'restart'")

    def stage(self, config: AERSCREENConfig, work: Path, mode: str) -> Path:
        """Put everything AERSCREEN will look for into ``work``.

        Returns the path of the file the run reads its configuration
        from: ``aerscreen.inp`` in restart mode, the answers file in
        prompt mode.
        """
        work.mkdir(parents=True, exist_ok=True)

        missing = [
            name for name in self.required_helpers(config)
            if self.helpers.get(name) is None
        ]
        if missing:
            raise FileNotFoundError(
                f"AERSCREEN needs {', '.join(missing)} for this run and "
                "none was found on PATH; pass the path(s) to AERSCREENRunner "
                "(scripts/build_aermod.sh, build_bpip.sh and "
                "build_aerscreen.sh build them into ./bin)."
            )
        for name, path in self.helpers.items():
            if path is None:
                continue
            if name == "bpipprm":
                self._write_executable(
                    work / name, _BPIP_WRAPPER.format(real=path)
                )
            else:
                self._link(path, work / name)
            self._link(work / name, work / _HELPERS[name])

        for src in config.staged_input_files:
            source = Path(src)
            if not source.is_file():
                raise FileNotFoundError(
                    f"AERSCREEN input file not found: {src}"
                )
            target = work / source.name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        if config.discrete_receptors and config.discrete_receptor_file is None:
            (work / DISCRETE_RECEPTOR_FILE).write_text(
                "units: meters\n"
                + "".join(f"{d:g}\n" for d in config.discrete_receptors),
                encoding="ascii",
            )
        if config.terrain:
            self._stage_terrain(config, work)

        restart = work / "aerscreen.inp"
        if mode == "restart":
            restart.write_text(config.to_aerscreen_input(), encoding="ascii")
            return restart
        # A stale restart file would change the prompt sequence.
        if restart.exists():
            restart.unlink()
        answers = work / "aerscreen_answers.txt"
        answers.write_text(self.stdin_text(config, mode), encoding="ascii")
        return answers

    def _stage_terrain(self, config: AERSCREENConfig, work: Path) -> None:
        if not config.dem_files:
            raise ValueError(
                "terrain=True needs dem_files; AERSCREEN lists them in "
                "DEMlist.txt for AERMAP"
            )
        grid_dir = Path(config.nad_grid_dir) if config.nad_grid_dir else None
        grids: List[Path] = []
        if grid_dir is not None:
            grids = sorted(
                p for p in grid_dir.iterdir()
                if p.suffix.lower() in _NAD_GRID_SUFFIXES
            )
            if not grids:
                raise FileNotFoundError(
                    f"no NADCON grid files (*.las, *.los) in {grid_dir}"
                )
            for grid in grids:
                if grid.resolve() != (work / grid.name).resolve():
                    shutil.copy2(grid, work / grid.name)
        elif not any(work.glob("*.las")):
            raise FileNotFoundError(
                "terrain runs need the NADCON grid files (conus.las/.los, "
                "...) beside AERSCREEN even for NAD83 coordinates; name "
                "their directory in nad_grid_dir"
            )
        # readDEM: first token D or N, an optional NADGRIDS line, then one
        # file per line. AERSCREEN reads it as DEMlist.txt.
        lines = [config.dem_type, "NADGRIDS: ./"]
        lines += [Path(f).name for f in config.dem_files]
        (work / "DEMlist.txt").write_text("\n".join(lines) + "\n", encoding="ascii")

    @staticmethod
    def _link(target: Path, link: Path) -> None:
        if link.exists() or link.is_symlink():
            link.unlink()
        try:
            link.symlink_to(target)
        except OSError:
            shutil.copy2(target, link)

    @staticmethod
    def _write_executable(path: Path, text: str) -> None:
        path.write_text(text, encoding="ascii")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # ------------------------------------------------------------------
    def run(
        self,
        config: AERSCREENConfig,
        *,
        working_dir: Union[str, Path],
        timeout: int = 1800,
        mode: str = "prompts",
    ) -> AERSCREENRunResult:
        """Run AERSCREEN for one configuration.

        Parameters
        ----------
        config
            The run.
        working_dir
            Directory AERSCREEN runs in. It fills it with met files,
            AERMOD decks and outputs; use one per run.
        timeout
            Seconds before the run is killed. A flat run takes seconds,
            a terrain run with AERMAP minutes.
        mode
            ``"prompts"`` types the answers of
            :meth:`~pyaermod.aerscreen.AERSCREENConfig.to_stdin_answers`;
            ``"restart"`` writes the restart file of
            :meth:`~pyaermod.aerscreen.AERSCREENConfig.to_aerscreen_input`
            as ``aerscreen.inp`` and accepts it. Both end in the same
            run; the prompt path is the one a user at the keyboard takes,
            and the only one that keeps a title with a comma in it whole
            (AERSCREEN's restart reader cuts the title at the first comma).
        """
        work = Path(working_dir).resolve()
        input_path = self.stage(config, work, mode)
        stdin_text = self.stdin_text(config, mode)

        env = dict(os.environ)
        env["PATH"] = str(work) + os.pathsep + env.get("PATH", "")

        self.logger.info(f"Running AERSCREEN ({mode}): {input_path} (workdir={work})")
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
                    env=env,
                    input=stdin_text,
                    text=True,
                    stdout=stdout_fh, stderr=stderr_fh,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                end = datetime.now()
                return AERSCREENRunResult(
                    success=False, input_file=str(input_path),
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
        stem = config.output_file[:-4]
        output_path = work / config.output_file
        # AERSCREEN writes aerscreen.log and, for a non-default output
        # name, copies it to <stem>.log on the way out (finalwrite).
        log_path = work / (stem + ".log")
        if not log_path.is_file():
            log_path = work / "aerscreen.log"
        # AERSCREEN's own verdict is in its log; the exit code is 0 even
        # when it stops on a validation error.
        log_text = log_path.read_text(encoding="latin-1", errors="replace") \
            if log_path.is_file() else ""
        finished = "AERSCREEN Finished Successfully" in log_text
        success = proc.returncode == 0 and finished and output_path.is_file()
        outputs = [
            str(p) for p in sorted(work.glob("*"))
            if p.is_file() and p.stat().st_mtime >= start.timestamp()
        ]
        summary: Optional[AERSCREENSummary] = None
        if success:
            try:
                summary = parse_aerscreen_output(output_path)
            except ValueError as e:
                self.logger.warning(f"AERSCREEN output not parsed: {e}")
        if success:
            error = None
        elif proc.returncode != 0:
            error = f"AERSCREEN exited with code {proc.returncode}"
        elif not finished:
            error = "AERSCREEN did not finish; see its log"
        else:
            error = f"AERSCREEN produced no {config.output_file}"
        max_conc = work / (stem + "_max_conc_distance.txt")
        if config.output_file.upper() == "AERSCREEN.OUT":
            max_conc = work / "max_conc_distance.txt"
        return AERSCREENRunResult(
            success=success,
            input_file=str(input_path),
            return_code=proc.returncode,
            runtime_seconds=(end - start).total_seconds(),
            stdout=out, stderr=err, output_files=outputs,
            error_message=error,
            start_time=start, end_time=end,
            output_file=str(output_path) if output_path.is_file() else None,
            log_file=str(log_path) if log_path.is_file() else None,
            restart_file=str(work / "aerscreen.inp")
            if (work / "aerscreen.inp").is_file() else None,
            max_conc_file=str(max_conc) if max_conc.is_file() else None,
            summary=summary,
        )


__all__ = [
    "AERSCREENRunResult",
    "AERSCREENRunner",
]

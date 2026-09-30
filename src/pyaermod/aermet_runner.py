"""
AERMET binary runner + pipeline.

Parallel to :class:`pyaermod.runner.AERMODRunner` but for AERMET. AERMET
11 and later run in two stages: Stage 1 extracts and quality-assures the
raw observations (:class:`~pyaermod.aermet.AERMETStage1`), and the
METPREP stage merges them and computes the boundary-layer parameters
(:class:`~pyaermod.aermet.AERMETStage3`, AERMET's "stage 2"). Each run
takes a runstream file named on the command line.

    from pyaermod import AERMETStage1, AERMETStage3
    from pyaermod.aermet_runner import AERMETRunner, run_aermet_pipeline

    runner = AERMETRunner()
    result1 = runner.run_stage(1, stage1_inp_path, working_dir=tmp)
    ...

Or, for the whole pipeline:

    results = run_aermet_pipeline(stage1, None, stage3, working_dir=tmp)
    # one AERMETRunResult per AERMET run; check all `.success`.

How success is decided
----------------------
AERMET exits with code 0 whether or not it succeeds, so the exit code
says nothing. At the end of every run the main program (``aermet.f90``)
prints one of two banners to the screen and to the REPORT file:

    AERMET FINISHED SUCCESSFULLY
    AERMET FINISHED UN-SUCCESSFULLY

and ``write_msg`` (``mod_reports.f90``) writes a MESSAGE SUMMARY to the
REPORT file with the number of ERROR, WARNING, INFORMATION and QA
messages. A run succeeds here only when the exit code is 0, the screen
output carries the "FINISHED SUCCESSFULLY" banner and no error is
counted. The individual messages come from the MESSAGES file, one per
line in the layout ``(1x,a10,1x,a3,5x,a10,1x,...)``: pathway, code
(``E01``), routine and text. A few errors found before the MESSAGES file
is open go to the screen in the same layout, so the screen is read too.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Union

from .aermet import _MAX_FILENAME, AERMETStage1, AERMETStage2, AERMETStage3
from .runner import _read_capped

_FINISHED_SUCCESSFULLY = re.compile(r"^[ \t]*AERMET FINISHED SUCCESSFULLY[ \t]*$", re.MULTILINE)
_FINISHED_UNSUCCESSFULLY = re.compile(r"^[ \t]*AERMET FINISHED UN-SUCCESSFULLY[ \t]*$", re.MULTILINE)
# write_msg: write(rpt_unit,'(//2(1x,a),1x,i8,1x,a/)') type,'MESSAGES',n,'MESSAGES'
_SUMMARY_COUNT = re.compile(
    r"^[ \t]*(ERROR|WARNING|INFORMATION|QA) MESSAGES[ \t]+(\d+)[ \t]+MESSAGES[ \t]*$",
    re.MULTILINE,
)
_SUMMARY_SEVERITY = {"ERROR": "E", "WARNING": "W", "INFORMATION": "I", "QA": "Q"}
# msg_form in mod_main1.f90: '(1x,a10,1x,a3,5x,a10,1x,' followed by the text.
_MESSAGE_LINE = re.compile(r"^ (?P<pathway>.{10}) (?P<code>[EWIQ]\d\d) {5}(?P<rest>.*)$")


@dataclass(frozen=True)
class AERMETMessage:
    """One line of an AERMET MESSAGES file (or of its screen output).

    Attributes:
        pathway: The pathway that raised it (``UPPERAIR``, ``SURFACE``,
            ``ONSITE``, ``METPREP``, ``JOB``), or empty when AERMET leaves
            it blank.
        severity: ``'E'`` (error), ``'W'`` (warning), ``'I'``
            (information) or ``'Q'`` (QA).
        code: The severity and number together, such as ``'E01'``.
        module: The AERMET routine, such as ``'CHECK_LINE'``.
        text: The message text.
    """
    pathway: str
    severity: str
    code: str
    module: str
    text: str = ""

    def __str__(self) -> str:
        where = f"{self.pathway} " if self.pathway else ""
        return f"{where}{self.code} {self.module}: {self.text}".rstrip()


def parse_aermet_messages(text: str) -> List[AERMETMessage]:
    """Parse the messages in the text of an AERMET MESSAGES file."""
    messages = []
    for raw in text.replace("\r\n", "\n").splitlines():
        m = _MESSAGE_LINE.match(raw)
        if m is None:
            continue
        code = m.group("code")
        messages.append(AERMETMessage(
            pathway=m.group("pathway").strip(),
            severity=code[0],
            code=code,
            # a10 routine name, one blank, then the text
            module=m.group("rest")[:10].strip(),
            text=m.group("rest")[11:].strip(),
        ))
    return messages


def read_aermet_messages(message_file: Union[str, Path]) -> List[AERMETMessage]:
    """Read the messages of an AERMET MESSAGES file."""
    return parse_aermet_messages(Path(message_file).read_text(encoding="latin-1"))


def _lf(text: str) -> str:
    """``text`` with LF line endings. A Windows AERMET ends its records with
    CRLF (as EPA's reference outputs do), and a CR before the end of a line
    defeats the ``$`` of the banner and summary patterns."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_text(path: Path) -> str:
    """The last 1 MB of a text file AERMET wrote, with LF line endings."""
    return _lf(_read_capped(path, 1_000_000))


def _summary_counts(report_text: str) -> Dict[str, int]:
    """The ERROR/WARNING/INFORMATION/QA counts of a REPORT file's MESSAGE SUMMARY."""
    return {_SUMMARY_SEVERITY[m.group(1)]: int(m.group(2))
            for m in _SUMMARY_COUNT.finditer(_lf(report_text))}


class _JobFiles(NamedTuple):
    report: Optional[str]
    messages: Optional[str]


def _job_files(deck_text: str) -> _JobFiles:
    """The REPORT and MESSAGES file names a runstream names (JOB pathway)."""
    found: Dict[str, str] = {}
    for raw in deck_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        parts = line.split(None, 1)
        keyword = parts[0].upper()
        if keyword in ("REPORT", "MESSAGES") and keyword not in found and len(parts) == 2:
            found[keyword] = parts[1].strip().strip("'\"")
    return _JobFiles(found.get("REPORT"), found.get("MESSAGES"))


@dataclass
class AERMETRunResult:
    """Outcome of a single AERMET run.

    ``success`` is AERMET's own verdict (see the module docstring).
    ``messages`` are the messages AERMET listed (its MESSAGES file and any
    it printed to the screen), and ``message_counts`` the counts from the
    REPORT file's MESSAGE SUMMARY, keyed ``'E'``, ``'W'``, ``'I'`` and
    ``'Q'``.
    """
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
    messages: List[AERMETMessage] = field(default_factory=list)
    message_counts: Dict[str, int] = field(default_factory=dict)
    finished_successfully: bool = False
    report_file: Optional[str] = None
    message_file: Optional[str] = None

    def __post_init__(self) -> None:
        if self.output_files is None:
            self.output_files = []

    @property
    def errors(self) -> List[AERMETMessage]:
        """The error (``E``) messages AERMET listed."""
        return [m for m in self.messages if m.severity == "E"]

    @property
    def error_count(self) -> int:
        """AERMET's count of error messages (its summary's, else the number listed)."""
        return self.message_counts.get("E", len(self.errors))


class AERMETRunner:
    """Execute AERMET runs from Python.

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

    @staticmethod
    def _deck_argument(inp_path: Path, work: Path) -> str:
        """The runstream name to pass AERMET, copying the deck into ``work`` if needed.

        AERMET reads the runstream named by its first command-line
        argument (readinp in mod_read_input.f90) and opens every file the
        deck names relative to its working directory. A deck outside the
        working directory is copied in under its own name, which also
        keeps the argument within AERMET's 300-character file names.
        """
        try:
            rel = inp_path.relative_to(work)
        except ValueError:
            target = work / inp_path.name
            shutil.copy2(inp_path, target)
            rel = Path(inp_path.name)
        arg = rel.as_posix()
        if len(arg) > _MAX_FILENAME:
            raise ValueError(f"AERMET reads file names of up to {_MAX_FILENAME} characters: {arg}")
        return arg

    def run_stage(
        self,
        stage: int,
        input_file: Union[str, Path],
        *,
        working_dir: Union[str, Path],
        timeout: int = 600,
    ) -> AERMETRunResult:
        """Run AERMET on one runstream file in ``working_dir``.

        ``stage`` labels the run (the result's ``stage`` and the captured
        ``stage{N}.subproc.stdout``/``.stderr`` files); AERMET itself
        decides which stages to run from the pathways in the deck.
        """
        inp_path = Path(input_file).resolve()
        work = Path(working_dir).resolve()
        work.mkdir(parents=True, exist_ok=True)
        deck_text = inp_path.read_text(encoding="latin-1")
        job = _job_files(deck_text)
        report_path = work / job.report if job.report else None
        message_path = work / job.messages if job.messages else None
        deck_arg = self._deck_argument(inp_path, work)

        self.logger.info(
            f"Running AERMET stage {stage}: {inp_path} (workdir={work})"
        )
        start = datetime.now()
        # Pipe-safe stdout/stderr handling: redirect to files instead of
        # OS pipes to avoid deadlock on chatty AERMET stages (the same
        # fix as runner.py applies to AERMOD).
        stdout_path = work / f"stage{stage}.subproc.stdout"
        stderr_path = work / f"stage{stage}.subproc.stderr"
        stdout_fh = open(stdout_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
        stderr_fh = open(stderr_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
        try:
            try:
                proc = subprocess.run(
                    [str(self.executable), deck_arg],
                    cwd=str(work),
                    text=True,
                    stdout=stdout_fh, stderr=stderr_fh,
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
        finally:
            stdout_fh.close()
            stderr_fh.close()
        end = datetime.now()

        # Read captured streams from disk (capped at 1 MB tail), as LF text.
        out = _read_text(stdout_path)
        err = _read_text(stderr_path)

        messages = parse_aermet_messages(out)
        if message_path is not None and message_path.is_file():
            messages += read_aermet_messages(message_path)
        counts: Dict[str, int] = {}
        if report_path is not None and report_path.is_file():
            counts = _summary_counts(_read_text(report_path))
        finished = (_FINISHED_SUCCESSFULLY.search(out) is not None
                    and _FINISHED_UNSUCCESSFULLY.search(out) is None)

        result = AERMETRunResult(
            success=False,
            stage=stage,
            input_file=str(inp_path),
            return_code=proc.returncode,
            runtime_seconds=(end - start).total_seconds(),
            stdout=out,
            stderr=err,
            output_files=[str(p) for p in sorted(work.glob("*"))
                          if p.is_file() and p.stat().st_mtime >= start.timestamp()],
            start_time=start,
            end_time=end,
            messages=messages,
            message_counts=counts,
            finished_successfully=finished,
            report_file=str(report_path) if report_path is not None and report_path.is_file() else None,
            message_file=str(message_path) if message_path is not None and message_path.is_file() else None,
        )
        result.success = proc.returncode == 0 and finished and result.error_count == 0
        if not result.success:
            result.error_message = self._failure_reason(result, out, err)
            self.logger.error(f"AERMET stage {stage} failed: {result.error_message}")
        return result

    @staticmethod
    def _failure_reason(result: AERMETRunResult, out: str, err: str) -> str:
        parts = []
        errors = result.errors
        if errors:
            first = str(errors[0])
            if len(errors) > 1:
                first += f" (and {len(errors) - 1} more error(s))"
            parts.append(first)
        elif result.error_count:
            parts.append(f"AERMET counted {result.error_count} error message(s)")
        if result.return_code not in (0, None):
            parts.append(f"AERMET exited with code {result.return_code}")
        if not result.finished_successfully:
            if _FINISHED_UNSUCCESSFULLY.search(out):
                parts.append("AERMET printed 'AERMET FINISHED UN-SUCCESSFULLY'")
            else:
                tail = " | ".join(line.strip() for line in out.splitlines()[-3:] if line.strip())
                parts.append("AERMET did not print 'AERMET FINISHED SUCCESSFULLY'"
                             + (f" (last output: {tail})" if tail else ""))
        err_lines = [line.strip() for line in err.splitlines() if line.strip()]
        if err_lines:
            # A crashed AERMET ends stderr with a backtrace; gfortran's
            # "Fortran runtime error: ..." line above it says what happened.
            runtime = [line for line in err_lines if "runtime error" in line.lower()]
            parts.append(f"stderr: {(runtime or err_lines)[-1]}")
        return "; ".join(parts)


def run_aermet_pipeline(
    stage1: AERMETStage1,
    stage2: Optional[AERMETStage2],
    stage3: AERMETStage3,
    *,
    working_dir: Union[str, Path],
    executable_path: Optional[Union[str, Path]] = None,
    stop_on_failure: bool = True,
    timeout: int = 600,
) -> List[AERMETRunResult]:
    """Run AERMET's Stage 1 and then its METPREP stage in ``working_dir``.

    Writes ``stage1.inp`` and ``stage3.inp`` into ``working_dir`` and runs
    them in turn. The METPREP deck reads Stage 1's QAOUT files
    (:meth:`AERMETStage3.with_inputs_from`) unless ``stage3`` names its
    own. ``stage2`` is ignored: AERMET 11 and later have no merge stage;
    pass None. If Stage 1 fails and ``stop_on_failure`` is True (default),
    METPREP is not run.

    Returns one :class:`AERMETRunResult` per AERMET run made, with
    ``stage`` 1 and 3 (two results, not three).
    """
    if stage2 is not None:
        warnings.warn(
            "run_aermet_pipeline ignores stage2: AERMET 11 and later have no merge stage; pass None",
            DeprecationWarning, stacklevel=2,
        )
    work = Path(working_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    runner = AERMETRunner(executable_path=executable_path)

    results: List[AERMETRunResult] = []
    for n, cfg in ((1, stage1), (3, stage3.with_inputs_from(stage1))):
        deck_path = work / f"stage{n}.inp"
        deck_path.write_text(cfg.to_aermet_input(), encoding="utf-8")
        res = runner.run_stage(n, deck_path, working_dir=work, timeout=timeout)
        results.append(res)
        if not res.success and stop_on_failure:
            break
    return results


__all__ = [
    "AERMETMessage",
    "AERMETRunResult",
    "AERMETRunner",
    "parse_aermet_messages",
    "read_aermet_messages",
    "run_aermet_pipeline",
]

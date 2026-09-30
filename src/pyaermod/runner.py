"""
PyAERMOD Runner

Executes AERMOD binaries from Python with error handling, progress monitoring,
and batch processing capabilities.
"""

import atexit
import contextlib
import logging
import os
import platform
import re
import shutil
import signal
import subprocess
import threading
import time
import weakref
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

# ============================================================================
# AERMOD'S MESSAGE SUMMARY
# ============================================================================
#
# AERMOD reports whether a run worked only in its .out file. The process
# exits with code 0 even when a fatal error stops the run: v26135 does so
# for the runtime error E480 (ANNUAL averages with under a year of met
# data) and for the setup error E500 (a met file that cannot be opened).
# The recordings in tests/fixtures/runner/ show both.
#
# Near the end of the .out, AERMOD's SUMTBL routine (aermod.f) writes a
# message summary, and the main program then writes one of two banners:
#
#     *** AERMOD Finishes Successfully ***
#     *** AERMOD Finishes UN-successfully ***
#
# A run with setup messages also has an earlier summary, "Message Summary
# For AERMOD Model Setup", followed by "*** SETUP Finishes Successfully
# ***" even when the run fails later. That is why a search for "FINISHES
# SUCCESSFULLY" is not a success test. The final summary re-reads every
# message AERMOD recorded, including the setup messages, so it is the only
# summary parsed here. SUMTBL lists fatal errors and warnings but only
# counts informational messages.

_SUMMARY_HEADING = re.compile(r"\*\*\* Message Summary", re.IGNORECASE)
_FINISH_BANNER = re.compile(
    r"^[ \t]*\*\*\*[ \t]*(?:SETUP|AERMOD) Finishes", re.IGNORECASE | re.MULTILINE
)
_FINISHED_SUCCESSFULLY = re.compile(
    r"^[ \t]*\*\*\*[ \t]*AERMOD Finishes Successfully[ \t]*\*\*\*[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_MESSAGE_TOTAL = re.compile(
    r"^[ \t]*A Total of[ \t]+(\d+)[ \t]+(Fatal Error|Warning|Informational) Message",
    re.IGNORECASE | re.MULTILINE,
)
_TOTAL_SEVERITY = {"fatal error": "E", "warning": "W", "informational": "I"}
# One message, as SUMTBL writes it:
#     FORMAT(1X,A2,1X,A1,A3,I8,1X,A12,': ',A50,1X,A12)
# i.e. pathway, severity, number, line, routine, text, detail.
_MESSAGE_LINE = re.compile(
    r"^ (?P<pathway>.{2}) (?P<severity>[EWI])(?P<number>\d{3})"
    r"(?P<line>[ \d]{7}\d) (?P<module>.{12}): (?P<body>.*?)\s*$"
)
# The summary sits at the end of the file and holds at most 999 fatal
# errors and 999 warnings of about 95 bytes each, so a 1 MB tail always
# contains it when the run got as far as writing the final summary.
_SUMMARY_TAIL_BYTES = 1_000_000


@dataclass(frozen=True)
class AERMODMessage:
    """One message from the message summary in an AERMOD ``.out`` file.

    AERMOD prints each message on one line with the Fortran format
    ``(1X,A2,1X,A1,A3,I8,1X,A12,': ',A50,1X,A12)``, for example::

         MX E480      97         MAIN: Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave     NUMYRS=0

    Attributes:
        severity: ``'E'`` (fatal error), ``'W'`` (warning) or ``'I'``
            (informational).
        pathway: The pathway that raised the message, such as ``'CO'``,
            ``'SO'``, ``'RE'``, ``'ME'``, ``'OU'`` or ``'MX'`` (the
            meteorological data). It is empty when AERMOD leaves it blank.
        code: The severity and number together, such as ``'E480'``.
        line: The line reference as AERMOD prints it. During setup this is
            the line of the input deck. During the run it is the record of
            the data file being read, such as the hour of met data for
            ``MX`` messages.
        module: The AERMOD routine that raised the message, such as
            ``'MAIN'``.
        text: The message text. AERMOD cuts it to 50 characters.
        detail: The detail field of up to 12 characters that follows the
            text, such as ``'NUMYRS=0'`` or ``'SURFFILE'``. It is empty when
            AERMOD prints none.
    """
    severity: str
    pathway: str
    code: str
    line: str
    module: str
    text: str
    detail: str = ""

    def __str__(self) -> str:
        message = f"{self.code} {self.module}: {self.text}"
        return f"{message} {self.detail}" if self.detail else message


class _MessageSummary(NamedTuple):
    """What the final message summary of a ``.out`` file says."""
    messages: List[AERMODMessage]
    # AERMOD's own "A Total of N ... Message(s)" lines, keyed by severity.
    counts: Dict[str, int]
    # True when the file carries the "*** AERMOD Finishes Successfully ***" banner.
    finished_successfully: bool


def _severity_count(messages: Sequence[AERMODMessage],
                    counts: Dict[str, int], severity: str) -> int:
    """AERMOD's own total for ``severity`` when it printed one, else the number listed.

    The totals are the better count: AERMOD lists at most 999 messages of
    each kind, omits the warning list under ``NOWARN``, and never lists
    informational messages.
    """
    if severity in counts:
        return counts[severity]
    return sum(1 for m in messages if m.severity == severity)


def _read_summary_text(path: Path) -> str:
    """Return the end of ``path`` that holds AERMOD's final message summary.

    Reads only the last ``_SUMMARY_TAIL_BYTES`` of a large file, falling
    back to the whole file when that tail has no summary (a run that
    stopped before writing its final one). AERMOD writes Latin-1, and
    that decoding cannot fail. Windows builds end lines with CRLF (EPA's
    own reference outputs do), so line ends are normalized to LF.
    """
    size = path.stat().st_size
    with open(path, "rb") as fh:
        if size > _SUMMARY_TAIL_BYTES:
            fh.seek(size - _SUMMARY_TAIL_BYTES)
            tail = fh.read().decode("latin-1")
            if _SUMMARY_HEADING.search(tail):
                return tail.replace("\r\n", "\n")
            fh.seek(0)
        return fh.read().decode("latin-1").replace("\r\n", "\n")


def _read_message_summary(output_file: Union[str, Path]) -> _MessageSummary:
    """Parse the final message summary and the completion banner of a ``.out`` file."""
    text = _read_summary_text(Path(output_file))
    finished = _FINISHED_SUCCESSFULLY.search(text) is not None

    headings = list(_SUMMARY_HEADING.finditer(text))
    if not headings:
        return _MessageSummary([], {}, finished)
    region = text[headings[-1].start():]
    banner = _FINISH_BANNER.search(region)
    if banner:
        region = region[:banner.start()]

    counts = {
        _TOTAL_SEVERITY[m.group(2).lower()]: int(m.group(1))
        for m in _MESSAGE_TOTAL.finditer(region)
    }
    messages = []
    for raw in region.splitlines():
        m = _MESSAGE_LINE.match(raw)
        if m is None:
            continue
        body = m.group("body")
        messages.append(AERMODMessage(
            severity=m.group("severity"),
            pathway=m.group("pathway").strip(),
            code=m.group("severity") + m.group("number"),
            line=m.group("line").strip(),
            module=m.group("module").strip(),
            # A50 then 1X then A12: the text and the detail sit at fixed columns.
            text=body[:50].strip(),
            detail=body[51:].strip(),
        ))
    return _MessageSummary(messages, counts, finished)


def parse_aermod_messages(output_file: Union[str, Path]) -> List[AERMODMessage]:
    """Read the fatal errors and warnings AERMOD lists in a ``.out`` file.

    The messages come from the file's final message summary, which
    includes the setup messages, in the order AERMOD lists them: fatal
    errors first, then warnings. AERMOD counts informational messages
    but does not list them in the ``.out`` file.

    Args:
        output_file: Path to an AERMOD ``.out`` file.

    Returns:
        The listed messages. The list is empty when the file has no
        message summary.

    Raises:
        FileNotFoundError: If ``output_file`` does not exist.
    """
    return _read_message_summary(output_file).messages


@dataclass
class AERMODRunResult:
    """Result from an AERMOD execution.

    ``success`` is True only when AERMOD exited with code 0, wrote its
    ``.out`` file, printed ``*** AERMOD Finishes Successfully ***`` there
    and reported no fatal errors. The exit code alone says nothing:
    AERMOD exits with 0 after a fatal error.
    """
    success: bool
    input_file: str
    return_code: Optional[int] = None
    runtime_seconds: Optional[float] = None

    # Output files
    output_file: Optional[str] = None
    error_file: Optional[str] = None
    summary_file: Optional[str] = None

    # Execution info
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None

    # Metadata
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # AERMOD's own verdict, read from the final message summary of the .out file
    messages: List[AERMODMessage] = field(default_factory=list)
    message_counts: Dict[str, int] = field(default_factory=dict)
    finished_successfully: bool = False

    # True when the run was stopped by AERMODRun.cancel() before AERMOD ended
    cancelled: bool = False

    @property
    def fatal_messages(self) -> List[AERMODMessage]:
        """The fatal errors AERMOD listed (severity ``'E'``)."""
        return [m for m in self.messages if m.severity == "E"]

    @property
    def warning_messages(self) -> List[AERMODMessage]:
        """The warnings AERMOD listed (severity ``'W'``)."""
        return [m for m in self.messages if m.severity == "W"]

    @property
    def fatal_count(self) -> int:
        """Number of fatal errors, from AERMOD's own total when it printed one."""
        return _severity_count(self.messages, self.message_counts, "E")

    @property
    def warning_count(self) -> int:
        """Number of warnings, from AERMOD's own total when it printed one."""
        return _severity_count(self.messages, self.message_counts, "W")

    @property
    def informational_count(self) -> int:
        """Number of informational messages. AERMOD counts these but does not list them."""
        return _severity_count(self.messages, self.message_counts, "I")

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else ("CANCELLED" if self.cancelled else "FAILED")
        runtime = f"{self.runtime_seconds:.1f}s" if self.runtime_seconds else "N/A"
        return f"AERMODRunResult({status}, {self.input_file}, runtime={runtime})"


class AERMODRunner:
    """
    Execute AERMOD simulations from Python

    Handles subprocess management, file I/O, error detection, and batch processing.
    """

    def __init__(self,
                 executable_path: Optional[Union[str, Path]] = None,
                 working_dir: Optional[Union[str, Path]] = None,
                 log_level: str = "INFO"):
        """
        Initialize AERMOD runner

        Args:
            executable_path: Path to AERMOD executable. If None, searches PATH.
            working_dir: Default working directory for runs
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.executable = self._find_or_set_executable(executable_path)
        self.default_working_dir = Path(working_dir) if working_dir else Path.cwd()

        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(getattr(logging, log_level.upper()))

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.logger.info(f"Initialized AERMOD runner with executable: {self.executable}")

    def _find_or_set_executable(self, path: Optional[Union[str, Path]]) -> Path:
        """Find or validate AERMOD executable"""
        if path:
            exe_path = Path(path)
            if not exe_path.exists():
                raise FileNotFoundError(f"AERMOD executable not found: {path}")
            return exe_path

        # Search in PATH
        system = platform.system()

        # Try common names
        exe_names = ['aermod', 'AERMOD', 'aermod.exe', 'AERMOD.EXE']

        for name in exe_names:
            found = shutil.which(name)
            if found:
                return Path(found)

        # If not found, provide helpful error message
        raise FileNotFoundError(
            "AERMOD executable not found in PATH. Please either:\n"
            "  1. Add AERMOD to your system PATH, or\n"
            "  2. Specify the path explicitly: AERMODRunner(executable_path='/path/to/aermod')\n\n"
            f"System: {system}"
        )

    def run(self,
            input_file: Union[str, Path],
            working_dir: Optional[Union[str, Path]] = None,
            timeout: int = 3600,
            capture_output: bool = True) -> AERMODRunResult:
        """
        Execute AERMOD with given input file

        Blocks until AERMOD ends. :meth:`start` runs AERMOD in the
        background instead, reporting its progress and allowing a cancel.

        Args:
            input_file: Path to AERMOD input file (.inp)
            working_dir: Working directory for execution (defaults to input file location)
            timeout: Maximum execution time in seconds (default 1 hour)
            capture_output: Whether to capture stdout/stderr

        Returns:
            AERMODRunResult with execution details and file paths
        """
        input_path = Path(input_file).resolve()

        if not input_path.exists():
            return AERMODRunResult(
                success=False,
                input_file=str(input_path),
                error_message=f"Input file not found: {input_path}"
            )

        work_dir = self._work_dir_for(input_path, working_dir)
        input_name = input_path.stem

        self.logger.info(f"Running AERMOD: {input_name}")
        self.logger.debug(f"  Executable: {self.executable}")
        self.logger.debug(f"  Working dir: {work_dir}")
        self.logger.debug(f"  Timeout: {timeout}s")

        lock_fh, aermod_inp = self._stage(input_path, work_dir)

        start_time = datetime.now()

        # Pipe-safe output handling: AERMOD can emit 100s of MB of stdout
        # on large runs (receptor-by-hour diagnostics). `capture_output=True`
        # routes stdout/stderr through OS pipes with ~64 KB buffers, which
        # deadlock once the buffer fills and no one is reading. Redirect to
        # temp files instead when capture is requested; we slurp them at
        # the end (bounded by tail-output helpers for large files).
        stdout_path: Optional[Path] = None
        stderr_path: Optional[Path] = None
        stdout_fh = None
        stderr_fh = None
        if capture_output:
            stdout_path = work_dir / f"{input_name}.subproc.stdout"
            stderr_path = work_dir / f"{input_name}.subproc.stderr"
            # Manually manage these file handles — they outlive a single
            # `with` block (handed to subprocess.run, closed in the
            # finally clause below).
            stdout_fh = open(stdout_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
            stderr_fh = open(stderr_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115

        try:
            # Execute AERMOD (reads aermod.inp automatically)
            result = subprocess.run(
                [str(self.executable)],
                cwd=str(work_dir),
                stdout=stdout_fh,
                stderr=stderr_fh,
                text=True,
                timeout=timeout,
                check=False
            )

            if stdout_fh is not None:
                stdout_fh.close()
                stderr_fh.close()
                stdout_fh = stderr_fh = None
                # Populate result.stdout / stderr from the temp files so the
                # AERMODRunResult looks the same as before to callers.
                # Cap at 1 MB to avoid OOM on pathological runs; if the
                # user needs the full log the path is preserved on the
                # AERMODRunResult via `stdout_file` / `stderr_file`.
                result.stdout = _read_capped(stdout_path, 1_000_000)
                result.stderr = _read_capped(stderr_path, 1_000_000)

            return self._collect(result, input_path, work_dir, start_time,
                                 capture_output=capture_output)

        except subprocess.TimeoutExpired:
            return self._timed_out(input_path, start_time, timeout)

        except Exception as e:
            end_time = datetime.now()
            runtime = (end_time - start_time).total_seconds()

            self.logger.error(f"Error running AERMOD: {e}")

            return AERMODRunResult(
                success=False,
                input_file=str(input_path),
                runtime_seconds=runtime,
                error_message=str(e),
                start_time=start_time,
                end_time=end_time
            )

        finally:
            # Ensure stdout/stderr handles are closed even on timeout
            for fh in (stdout_fh, stderr_fh):
                if fh is not None:
                    with contextlib.suppress(Exception):
                        fh.close()
            self._unstage(lock_fh, aermod_inp)

    def start(self,
              input_file: Union[str, Path],
              working_dir: Optional[Union[str, Path]] = None,
              timeout: int = 3600,
              *,
              on_progress: Optional[Callable[["AERMODProgress"], None]] = None,
              on_finish: Optional[Callable[[AERMODRunResult], None]] = None,
              ) -> "AERMODRun":
        """Start AERMOD in the background and return at once.

        The run does what :meth:`run` does, in a thread of its own: it waits
        for the working directory's lock, points ``aermod.inp`` at the deck,
        runs AERMOD, renames its outputs and reads its verdict. The returned
        :class:`AERMODRun` reports AERMOD's progress, can be cancelled and
        can be waited for.

        Args:
            input_file: Path to AERMOD input file (.inp)
            working_dir: Working directory for execution (defaults to input
                file location)
            timeout: Maximum execution time in seconds (default 1 hour)
            on_progress: Called with an :class:`AERMODProgress` for each
                "Now Processing Data For Day No." line AERMOD prints, from
                the thread that reads AERMOD's output.
            on_finish: Called with the :class:`AERMODRunResult` once the run
                has ended (``cancelled=True`` after :meth:`AERMODRun.cancel`),
                from the run's own thread and before :meth:`AERMODRun.wait`
                returns, so it must not wait for the run itself.

        Returns:
            The running :class:`AERMODRun`.
        """
        run = AERMODRun(self, input_file, working_dir, timeout,
                        on_progress=on_progress, on_finish=on_finish)
        run._launch()
        return run

    # ------------------------------------------------------------------
    # The steps run() and start() share
    # ------------------------------------------------------------------
    @staticmethod
    def _work_dir_for(input_path: Path, working_dir: Optional[Union[str, Path]]) -> Path:
        """The directory AERMOD runs in: ``working_dir``, or the deck's own."""
        work_dir = Path(working_dir).resolve() if working_dir else input_path.parent
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def _stage(self, input_path: Path, work_dir: Path) -> Tuple[Any, Path]:
        """Lock ``work_dir`` and point its ``aermod.inp`` at the deck.

        AERMOD reads from a fixed filename (aermod.inp) in its working
        directory. We symlink the user's .inp file to aermod.inp, run AERMOD,
        then rename the output files back to the user's naming convention.

        Concurrency safety: two concurrent runs in the same working_dir would
        clobber each other's symlinks + outputs, so this first acquires an
        exclusive lock on a sentinel file (blocking until it is free).
        :meth:`_unstage` releases it.
        """
        lock_path = work_dir / ".pyaermod.lock"
        lock_fh = _acquire_dir_lock(lock_path)

        # Create symlink: aermod.inp -> <input_name>.inp
        aermod_inp = work_dir / "aermod.inp"
        try:
            if aermod_inp.exists() or aermod_inp.is_symlink():
                aermod_inp.unlink()
            aermod_inp.symlink_to(input_path.name)
        except OSError:
            # Fallback: copy the file
            import shutil
            shutil.copy2(str(input_path), str(aermod_inp))
        return lock_fh, aermod_inp

    @staticmethod
    def _unstage(lock_fh: Any, aermod_inp: Path) -> None:
        """Remove the ``aermod.inp`` link or copy and release the directory lock."""
        if aermod_inp.exists() or aermod_inp.is_symlink():
            with contextlib.suppress(OSError):
                aermod_inp.unlink()
        _release_dir_lock(lock_fh)

    def _collect(self, result: "subprocess.CompletedProcess[str]", input_path: Path,
                 work_dir: Path, start_time: datetime, *, capture_output: bool = True,
                 cancelled: bool = False) -> AERMODRunResult:
        """Rename AERMOD's outputs, read its verdict and build the result."""
        input_name = input_path.stem
        output_files = {
            'output': work_dir / f"{input_name}.out",
            'error': work_dir / f"{input_name}.err",
            'summary': work_dir / f"{input_name}.sum"
        }

        # Rename AERMOD's default output files to match the input name
        written = set()
        for suffix in ['.out', '.err', '.sum']:
            aermod_file = work_dir / f"aermod{suffix}"
            target_file = work_dir / f"{input_name}{suffix}"
            if aermod_file.exists():
                if target_file.exists():
                    target_file.unlink()
                aermod_file.rename(target_file)
                written.add(suffix)

        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()

        self.logger.debug(f"AERMOD completed with return code: {result.returncode}")
        self.logger.debug(f"Runtime: {runtime:.2f}s")

        # Check for output files. AERMOD writes aermod.out, renamed above: an
        # <name>.out left by an earlier run is not this run's, whether this
        # one was cancelled or crashed before writing any.
        has_output = '.out' in written and output_files['output'].exists()

        # AERMOD's verdict is in the .out file, not in its exit code,
        # which is 0 even after a fatal error (see the comment above
        # AERMODMessage).
        summary = _MessageSummary([], {}, False)
        if has_output:
            try:
                summary = _read_message_summary(output_files['output'])
            except OSError as exc:
                self.logger.warning(
                    f"Could not read AERMOD output file {output_files['output']}: {exc}"
                )
        fatal_count = _severity_count(summary.messages, summary.counts, "E")

        # Determine success: exit code 0, an .out file, AERMOD's own
        # completion banner and no fatal errors.
        success = (
            not cancelled
            and result.returncode == 0
            and has_output
            and summary.finished_successfully
            and fatal_count == 0
        )

        error_msg = None
        if cancelled:
            error_msg = "Cancelled before AERMOD finished"
            self.logger.info(f"AERMOD run cancelled after {runtime:.1f}s")
        elif not success:
            error_msg = self._extract_error_message(
                result, output_files,
                messages=summary.messages,
                finished_successfully=summary.finished_successfully,
                has_output=has_output,
            )
            self.logger.error(f"AERMOD run failed: {error_msg}")
        else:
            warnings = _severity_count(summary.messages, summary.counts, "W")
            self.logger.info(
                f"AERMOD run succeeded ({runtime:.1f}s, {warnings} warning(s))"
            )

        return AERMODRunResult(
            success=success,
            input_file=str(input_path),
            return_code=result.returncode,
            runtime_seconds=runtime,
            output_file=str(output_files['output']) if has_output else None,
            error_file=str(output_files['error']) if output_files['error'].exists() else None,
            summary_file=str(output_files['summary']) if output_files['summary'].exists() else None,
            stdout=result.stdout if capture_output else None,
            stderr=result.stderr if capture_output else None,
            error_message=error_msg,
            start_time=start_time,
            end_time=end_time,
            messages=summary.messages,
            message_counts=summary.counts,
            finished_successfully=summary.finished_successfully,
            cancelled=cancelled,
        )

    def _timed_out(self, input_path: Path, start_time: datetime, timeout: float) -> AERMODRunResult:
        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()

        self.logger.error(f"AERMOD execution timed out after {timeout}s")

        return AERMODRunResult(
            success=False,
            input_file=str(input_path),
            runtime_seconds=runtime,
            error_message=f"Execution timed out after {timeout} seconds",
            start_time=start_time,
            end_time=end_time
        )

    def _extract_error_message(self,
                               result: subprocess.CompletedProcess,
                               output_files: Dict[str, Path],
                               messages: Optional[Sequence[AERMODMessage]] = None,
                               finished_successfully: Optional[bool] = None,
                               has_output: Optional[bool] = None) -> str:
        """Explain why a run failed, naming AERMOD's first fatal error when there is one.

        Args:
            result: The finished AERMOD process.
            output_files: Paths of the run's ``output`` and ``error`` files.
            messages: The messages parsed from the ``.out`` file, if any.
            finished_successfully: Whether the ``.out`` file carries
                AERMOD's completion banner; None when it was not checked.
            has_output: Whether this run wrote the ``output`` file; None
                to take any ``output`` file that exists as this run's.
        """
        out = output_files['output']
        wrote_out = out.exists() if has_output is None else has_output
        fatal = [m for m in (messages or ()) if m.severity == "E"]
        parts = []
        if fatal:
            first = str(fatal[0])
            if len(fatal) > 1:
                first += f" (and {len(fatal) - 1} more fatal error(s))"
            parts.append(first)

        parts.extend(self._error_context(result, output_files,
                                         scan_output=not fatal and wrote_out))

        if not fatal and finished_successfully is False and wrote_out:
            parts.append(
                "AERMOD did not report success: no '*** AERMOD Finishes "
                f"Successfully ***' line in {out.name}"
            )

        if result.returncode is not None and result.returncode < 0:
            # Killed by a signal (a crash, or something outside pyaermod).
            try:
                name = f" ({signal.Signals(-result.returncode).name})"
            except ValueError:
                name = ""
            before = "" if wrote_out else f" before writing {out.name}"
            parts.insert(0, f"AERMOD was stopped by signal {-result.returncode}{name}{before}")

        if parts:
            return "; ".join(parts)
        if result.returncode == 0 and not wrote_out:
            return f"AERMOD exited with code 0 but wrote no {out.name}"
        return f"AERMOD failed with return code {result.returncode}"

    def _error_context(self,
                       result: subprocess.CompletedProcess,
                       output_files: Dict[str, Path],
                       scan_output: bool = True) -> List[str]:
        """Collect stderr, the error file and an error line from the ``.out`` file."""
        messages = []

        # Check stderr
        if result.stderr:
            messages.append(f"stderr: {result.stderr[:500]}")

        # AERMOD writes Latin-1 (degree signs, box-drawing characters in
        # the banner). Decode leniently so a stray byte can never hide the
        # very diagnostic we are trying to surface; only I/O failures are
        # tolerated, and those are logged rather than swallowed.

        # Check error file
        if output_files['error'].exists():
            try:
                with open(output_files['error'], encoding="latin-1", errors="replace") as f:
                    error_content = f.read(1000)
                    if error_content.strip():
                        messages.append(f"Error file: {error_content[:500]}")
            except OSError as exc:
                self.logger.debug(
                    f"Could not read AERMOD error file {output_files['error']}: {exc}"
                )

        # Check output file for errors. Parsed fatal messages make this
        # unnecessary, and the "FATAL ERROR MESSAGES" heading of AERMOD's
        # own summary is not an error, so skip it.
        if scan_output and output_files['output'].exists():
            try:
                with open(output_files['output'], encoding="latin-1", errors="replace") as f:
                    content = f.read()
                    # Look for error indicators
                    if 'ERROR' in content or 'FATAL' in content:
                        # Extract relevant lines
                        for line in content.split('\n'):
                            if 'ERROR MESSAGES' in line:
                                continue
                            if 'ERROR' in line or 'FATAL' in line:
                                messages.append(line.strip())
                                break
            except OSError as exc:
                self.logger.debug(
                    f"Could not read AERMOD output file {output_files['output']}: {exc}"
                )

        return messages

    def run_batch(self,
                  input_files: List[Union[str, Path]],
                  n_workers: int = 4,
                  timeout: int = 3600,
                  stop_on_error: bool = False) -> List[AERMODRunResult]:
        """
        Run multiple AERMOD simulations in parallel

        Args:
            input_files: List of input file paths
            n_workers: Number of parallel workers
            timeout: Timeout per run (seconds)
            stop_on_error: Whether to stop if any run fails

        Returns:
            List of AERMODRunResult objects
        """
        self.logger.info(f"Starting batch run: {len(input_files)} files, {n_workers} workers")

        results = []
        failed_count = 0

        exe_path = str(self.executable)
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # Dispatch via a module-level function so workers don't
            # have to pickle `self` (which includes a Logger + Handler
            # that aren't fork-safe under spawn).
            future_to_file = {
                executor.submit(_batch_worker, exe_path, str(inp), timeout): inp
                for inp in input_files
            }

            # Process completed jobs
            for future in as_completed(future_to_file):
                input_file = future_to_file[future]

                try:
                    result = future.result()
                    results.append(result)

                    if result.success:
                        self.logger.info(f"✓ {Path(result.input_file).name} ({result.runtime_seconds:.1f}s)")
                    else:
                        failed_count += 1
                        self.logger.error(f"✗ {Path(result.input_file).name}: {result.error_message}")

                        if stop_on_error:
                            self.logger.error("Stopping batch run due to error")
                            # Cancel pending futures
                            for f in future_to_file:
                                f.cancel()
                            break

                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"✗ {input_file}: Exception: {e}")

                    results.append(AERMODRunResult(
                        success=False,
                        input_file=str(input_file),
                        error_message=str(e)
                    ))

                    if stop_on_error:
                        break

        success_count = len(results) - failed_count
        self.logger.info(
            f"Batch complete: {success_count}/{len(results)} succeeded, "
            f"{failed_count} failed"
        )

        return results

    def validate_input(self, input_file: Union[str, Path]) -> Tuple[bool, List[str]]:
        """
        Validate AERMOD input file (basic checks)

        Args:
            input_file: Path to input file

        Returns:
            (is_valid, list_of_issues)
        """
        issues = []
        input_path = Path(input_file)

        if not input_path.exists():
            return False, [f"Input file does not exist: {input_path}"]

        try:
            with open(input_path) as f:
                content = f.read()

            # Check for required pathways
            required_pathways = ['CO STARTING', 'SO STARTING', 'RE STARTING',
                               'ME STARTING', 'OU STARTING']

            for pathway in required_pathways:
                if pathway not in content:
                    issues.append(f"Missing required pathway: {pathway}")

            # Check for FINISHED statements
            for pathway in ['CO', 'SO', 'RE', 'ME', 'OU']:
                starting = f'{pathway} STARTING'
                finished = f'{pathway} FINISHED'

                if starting in content and finished not in content:
                    issues.append(f"Pathway {pathway} not properly closed (missing {finished})")

            # Check for RUNORNOT
            if 'RUNORNOT' not in content:
                issues.append("Missing RUNORNOT keyword (required in CO pathway)")

        except Exception as e:
            issues.append(f"Error reading file: {e}")

        return len(issues) == 0, issues


# ============================================================================
# BACKGROUND RUNS: PROGRESS AND CANCEL
# ============================================================================
#
# While it runs, AERMOD prints what it is doing (aermod.f): a line when
# setup starts, one per day of met data (HRLOOP, FORMAT 909; EVENT runs
# print "Events" for "Data", evcalc.f), and one when it writes the results:
#
#     +Now Processing SETUP Information
#     +Now Processing Data For Day No.   61 of 1988
#     +Now Processing Output Options
#
# The day is the Julian day and the year the four-digit year. The "+" is
# Fortran carriage control, printed as a character by gfortran. A build
# whose stdout is not a terminal may buffer these lines; gfortran reads
# GFORTRAN_UNBUFFERED_PRECONNECTED, which AERMODRun sets unless the caller
# has. (The gfortran -O2 build of v26135 streamed all 366 day lines of a
# one-year run to AERMODRun one by one with or without it.)

_PROGRESS_LINE = re.compile(
    r"Now Processing (?:Data|Events) For Day No\.\s*(\d+)\s+of\s+(\d+)", re.IGNORECASE)
_SETUP_LINE = re.compile(r"Now Processing SETUP Information", re.IGNORECASE)
_OUTPUT_LINE = re.compile(r"Now Processing Output Options", re.IGNORECASE)

#: Seconds a cancelled AERMOD has to exit after SIGTERM before it is killed.
CANCEL_GRACE_SECONDS = 5.0

# How often the run's thread looks at a cancel request and the timeout.
_POLL_SECONDS = 0.1


def parse_progress_line(line: str) -> Optional[Tuple[int, int]]:
    """``(julian_day, year)`` from an AERMOD progress line, or None.

    >>> parse_progress_line("+Now Processing Data For Day No.   61 of 1988")
    (61, 1988)
    """
    m = _PROGRESS_LINE.search(line)
    return (int(m.group(1)), int(m.group(2))) if m else None


@dataclass(frozen=True)
class AERMODProgress:
    """How far a background AERMOD run has got.

    Attributes:
        stage: ``"setup"`` (AERMOD is reading the deck), ``"day"`` (it is
            processing a day of met data) or ``"output"`` (it is writing
            the results).
        day: The Julian day of the latest "Now Processing Data For Day No."
            line, or 0 before the first.
        year: The year of that day, or 0 before the first.
        days_processed: How many of those lines AERMOD has printed so far.
            Compared with the number of days in the met data (see
            :func:`pyaermod.aermet.read_surface_period`) it gives the run's
            fraction done.
        line: The line as AERMOD printed it.
    """
    stage: str
    day: int = 0
    year: int = 0
    days_processed: int = 0
    line: str = ""


# Every AERMODRun whose process may still be running, so that a Python
# that exits normally does not leave an AERMOD behind.
_ACTIVE_RUNS: "weakref.WeakSet[AERMODRun]" = weakref.WeakSet()


@atexit.register
def _stop_active_runs() -> None:
    for run in list(_ACTIVE_RUNS):
        run._kill()


class AERMODRun:
    """An AERMOD run started in the background by :meth:`AERMODRunner.start`.

    The run executes in a thread of its own. Its state can be read from
    any thread:

    * :attr:`progress` is the latest :class:`AERMODProgress`;
    * :attr:`done` says whether the run has ended, and :attr:`result`
      holds its :class:`AERMODRunResult` once it has;
    * :meth:`cancel` stops AERMOD (SIGTERM, then a kill after
      :data:`CANCEL_GRACE_SECONDS`), and the result then has
      ``cancelled=True`` and ``success=False``;
    * :meth:`wait` blocks until the run has ended and returns the result.

    The process is always waited for, so a cancelled or timed-out run
    leaves neither a running AERMOD nor a zombie behind.
    """

    def __init__(self, runner: AERMODRunner, input_file: Union[str, Path],
                 working_dir: Optional[Union[str, Path]], timeout: float, *,
                 on_progress: Optional[Callable[[AERMODProgress], None]] = None,
                 on_finish: Optional[Callable[[AERMODRunResult], None]] = None) -> None:
        self.input_file = Path(input_file).resolve()
        self.working_dir: Optional[Path] = Path(working_dir) if working_dir else None
        self.timeout = timeout
        self._runner = runner
        self._on_progress = on_progress
        self._on_finish = on_finish
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._cancel_at: Optional[float] = None
        self._progress: Optional[AERMODProgress] = None
        self._result: Optional[AERMODRunResult] = None
        self._thread = threading.Thread(
            target=self._main, name=f"aermod-run-{self.input_file.stem}", daemon=True)

    # -- state -----------------------------------------------------------
    @property
    def pid(self) -> Optional[int]:
        """AERMOD's process id once it has started, else None."""
        proc = self._proc
        return proc.pid if proc is not None else None

    @property
    def progress(self) -> Optional[AERMODProgress]:
        return self._progress

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def result(self) -> Optional[AERMODRunResult]:
        """The run's result once it has ended, else None."""
        return self._result if self._done.is_set() else None

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_at is not None

    # -- control ---------------------------------------------------------
    def cancel(self) -> bool:
        """Stop the run. False if it has already ended or was already cancelled.

        Returns at once; the run ends (and :meth:`wait` returns) once AERMOD
        has exited. A run cancelled before AERMOD started never starts it.
        """
        with self._lock:
            if self._done.is_set() or self._cancel_at is not None:
                return False
            self._cancel_at = time.monotonic()
            proc = self._proc
        if proc is not None:
            with contextlib.suppress(OSError):
                proc.terminate()
        return True

    def wait(self, timeout: Optional[float] = None) -> AERMODRunResult:
        """Block until the run has ended and return its result.

        Raises:
            TimeoutError: if ``timeout`` seconds pass first.
        """
        if not self._done.wait(timeout):
            raise TimeoutError(f"AERMOD run of {self.input_file.name} still running")
        assert self._result is not None
        return self._result

    # -- the run's thread ------------------------------------------------
    def _launch(self) -> None:
        _ACTIVE_RUNS.add(self)
        self._thread.start()

    def _main(self) -> None:
        try:
            result = self._execute()
        except Exception as exc:  # a bug here must still end the run
            self._runner.logger.exception("Background AERMOD run raised")
            result = AERMODRunResult(success=False, input_file=str(self.input_file),
                                     error_message=str(exc) or type(exc).__name__)
        self._result = result
        _ACTIVE_RUNS.discard(self)
        if self._on_finish is not None:
            try:
                self._on_finish(result)
            except Exception:
                self._runner.logger.exception("on_finish callback raised")
        self._done.set()

    def _execute(self) -> AERMODRunResult:
        runner = self._runner
        input_path = self.input_file
        if not input_path.exists():
            return AERMODRunResult(success=False, input_file=str(input_path),
                                   error_message=f"Input file not found: {input_path}")
        work_dir = runner._work_dir_for(input_path, self.working_dir)
        input_name = input_path.stem
        runner.logger.info(f"Starting AERMOD in the background: {input_name}")

        lock_fh, aermod_inp = runner._stage(input_path, work_dir)
        stdout_path = work_dir / f"{input_name}.subproc.stdout"
        stderr_path = work_dir / f"{input_name}.subproc.stderr"
        start_time = datetime.now()
        try:
            with open(stdout_path, "wb") as stdout_fh, open(stderr_path, "wb") as stderr_fh:
                with self._lock:
                    if self._cancel_at is not None:
                        return self._never_started(input_path, start_time)
                    env = dict(os.environ)
                    env.setdefault("GFORTRAN_UNBUFFERED_PRECONNECTED", "y")
                    proc = subprocess.Popen(
                        [str(runner.executable)], cwd=str(work_dir),
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr_fh,
                        env=env,
                    )
                    self._proc = proc
                reader = threading.Thread(target=self._read_stdout,
                                          args=(proc.stdout, stdout_fh),
                                          name=f"aermod-stdout-{input_name}", daemon=True)
                reader.start()
                timed_out = self._wait_for(proc)
                reader.join()
            if timed_out:
                return runner._timed_out(input_path, start_time, self.timeout)
            completed = subprocess.CompletedProcess(
                args=[str(runner.executable)], returncode=proc.returncode,
                stdout=_read_capped(stdout_path, 1_000_000),
                stderr=_read_capped(stderr_path, 1_000_000),
            )
            return runner._collect(completed, input_path, work_dir, start_time,
                                   cancelled=self._cancel_at is not None)
        except OSError as exc:
            runner.logger.error(f"Error running AERMOD: {exc}")
            end_time = datetime.now()
            return AERMODRunResult(
                success=False, input_file=str(input_path),
                runtime_seconds=(end_time - start_time).total_seconds(),
                error_message=str(exc), start_time=start_time, end_time=end_time,
            )
        finally:
            self._kill()                     # nothing may outlive the run
            runner._unstage(lock_fh, aermod_inp)

    def _never_started(self, input_path: Path, start_time: datetime) -> AERMODRunResult:
        self._runner.logger.info("AERMOD run cancelled before it started")
        return AERMODRunResult(success=False, input_file=str(input_path),
                               error_message="Cancelled before AERMOD started",
                               start_time=start_time, end_time=datetime.now(),
                               runtime_seconds=0.0, cancelled=True)

    def _wait_for(self, proc: subprocess.Popen) -> bool:
        """Wait for AERMOD to exit, killing it on timeout or a lingering cancel.

        Returns True when the run timed out.
        """
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                proc.wait(timeout=_POLL_SECONDS)
                return False
            except subprocess.TimeoutExpired:
                pass
            now = time.monotonic()
            cancel_at = self._cancel_at
            if cancel_at is not None and now - cancel_at > CANCEL_GRACE_SECONDS:
                proc.kill()
            elif cancel_at is None and now > deadline:
                proc.kill()
                proc.wait()
                return True

    def _kill(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=10)

    def _read_stdout(self, pipe: Any, sink: Any) -> None:
        """Copy AERMOD's stdout to ``sink`` and report its progress lines."""
        pending = b""
        read = getattr(pipe, "read1", pipe.read)
        try:
            while True:
                chunk = read(65536)
                if not chunk:
                    break
                sink.write(chunk)
                sink.flush()
                *lines, pending = re.split(rb"[\r\n]", pending + chunk)
                for raw in lines:
                    self._progress_line(raw)
            if pending:
                self._progress_line(pending)
        except (OSError, ValueError) as exc:
            self._runner.logger.debug(f"Reading AERMOD's stdout stopped: {exc}")
        finally:
            with contextlib.suppress(Exception):
                pipe.close()

    def _progress_line(self, raw: bytes) -> None:
        line = raw.decode("latin-1").strip()
        last = self._progress or AERMODProgress(stage="setup")
        found = parse_progress_line(line)
        if found is not None:
            progress = AERMODProgress(stage="day", day=found[0], year=found[1],
                                      days_processed=last.days_processed + 1, line=line)
        elif _SETUP_LINE.search(line):
            progress = AERMODProgress(stage="setup", line=line)
        elif _OUTPUT_LINE.search(line):
            progress = AERMODProgress(stage="output", day=last.day, year=last.year,
                                      days_processed=last.days_processed, line=line)
        else:
            return
        self._progress = progress
        if self._on_progress is not None:
            try:
                self._on_progress(progress)
            except Exception:
                self._runner.logger.exception("on_progress callback raised")


def _acquire_dir_lock(lock_path: Path):
    """Acquire an exclusive advisory lock on a sentinel file.

    Returns an open file handle (callers must release via
    `_release_dir_lock`). Blocks until the lock is available — not
    timeout-bounded because AERMOD runs themselves are timeout-bounded
    and a queued lock acquisition just means "wait your turn."

    Uses fcntl.flock on POSIX, msvcrt.locking on Windows. On platforms
    where neither is importable (very rare), the lock is a no-op and a
    log warning is issued.
    """
    fh = open(lock_path, "w")  # noqa: SIM115 — handle outlives the function
    try:
        try:
            import fcntl  # POSIX
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except ImportError:
            try:
                import msvcrt  # Windows
                # Lock the first byte; LOCK_NB would be non-blocking,
                # LOCK_RETRY isn't a thing — use blocking LK_LOCK.
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except ImportError:
                logging.getLogger(__name__).warning(
                    "Neither fcntl nor msvcrt available; concurrent runs "
                    "in the same working_dir are NOT serialized."
                )
    except Exception:
        with contextlib.suppress(Exception):
            fh.close()
        raise
    return fh


def _release_dir_lock(fh) -> None:
    """Release a lock acquired by `_acquire_dir_lock`."""
    if fh is None:
        return
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except ImportError:
            try:
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except ImportError:
                pass
    finally:
        with contextlib.suppress(Exception):
            fh.close()


def _batch_worker(executable_path: str, input_file: str, timeout: int) -> "AERMODRunResult":
    """Top-level ProcessPoolExecutor worker.

    Constructing a fresh AERMODRunner inside the worker process avoids
    pickling the parent's logging.Logger + StreamHandler (which aren't
    fork-safe on macOS/Windows with the `spawn` start method). The
    function is at module scope so it's picklable on all platforms.
    """
    runner = AERMODRunner(executable_path=executable_path, log_level="WARNING")
    return runner.run(input_file, timeout=timeout)


def _read_capped(path: Path, max_bytes: int = 1_000_000) -> str:
    """Read a text file, returning at most the last `max_bytes` bytes.

    Used to populate `AERMODRunResult.stdout`/`.stderr` from the
    subprocess-redirect temp files without OOM on pathological runs.
    If the file is larger than the cap, returns the final `max_bytes`
    bytes prefixed with a "[...truncated...]" marker.
    """
    if not path.exists():
        return ""
    size = path.stat().st_size
    with open(path, "rb") as f:
        if size <= max_bytes:
            return f.read().decode("utf-8", errors="replace")
        # Seek to the tail
        f.seek(size - max_bytes)
        tail = f.read().decode("utf-8", errors="replace")
    return f"[...truncated: {size - max_bytes:,} bytes omitted...]\n" + tail


def _set_sweep_parameter(project, name: str, value, source_index: int = 0) -> None:
    """Apply a parameter-sweep value to a project.

    If ``name`` contains a ``.`` it's treated as a dotted path relative
    to the project (e.g. ``"control.title_one"``). Otherwise it's an
    attribute on the source at ``source_index``.
    """
    if "." in name:
        parts = name.split(".")
        obj = project
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)
        return

    sources = getattr(project, "sources", None)
    source_list = getattr(sources, "sources", None) if sources else None
    if not source_list:
        raise ValueError(
            f"parameter_sweep: project has no sources to mutate '{name}'"
        )
    if source_index >= len(source_list):
        raise IndexError(
            f"parameter_sweep: source_index={source_index} but project "
            f"has only {len(source_list)} source(s)"
        )
    setattr(source_list[source_index], name, value)


class BatchRunner:
    """
    Helper class for running parameter sweeps and scenario comparisons
    """

    def __init__(self, runner: AERMODRunner):
        """Initialize with an AERMODRunner instance"""
        self.runner = runner

    def parameter_sweep(self,
                       base_project,
                       parameter_name: str,
                       parameter_values: List,
                       output_dir: Union[str, Path],
                       n_workers: int = 4,
                       source_index: int = 0) -> Dict:
        """Run AERMOD over a sweep of one parameter on one source.

        For each value in ``parameter_values``:

        1. Deep-copy ``base_project``
        2. Set ``parameter_name`` on the indicated source (or on the
           project if the name contains a dot, e.g. ``"control.title_one"``)
        3. Write the modified project to ``output_dir/run_{name}_{value}.inp``
        4. Queue the file for batch execution

        Parameters
        ----------
        base_project : AERMODProject
            Template project that gets cloned for each run.
        parameter_name : str
            Attribute to modify. If it contains ``.``, it's interpreted as
            a dotted path relative to the project root (e.g.
            ``"control.flag_pole_height"`` or ``"output.receptor_table_rank"``).
            Otherwise it's a field name on the source at ``source_index``
            (e.g. ``"emission_rate"``, ``"stack_height"``).
        parameter_values : list
            Values to substitute in.
        output_dir : Path
            Directory for generated .inp files and AERMOD outputs.
        n_workers : int
            Number of parallel AERMOD workers.
        source_index : int
            Which source to mutate when ``parameter_name`` is a plain
            field name. Defaults to 0 (the first source).

        Returns
        -------
        dict
            Mapping of parameter value -> AERMODRunResult.
        """
        import copy

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        input_files: List[Path] = []
        param_map: Dict[str, Any] = {}

        for value in parameter_values:
            project = copy.deepcopy(base_project)
            _set_sweep_parameter(project, parameter_name, value, source_index)

            # Sanitize the value for filename safety
            value_str = str(value).replace("/", "_").replace(" ", "_")
            filename = output_path / f"run_{parameter_name}_{value_str}.inp"
            project.write(str(filename))

            input_files.append(filename)
            param_map[str(filename)] = value

        results = self.runner.run_batch(input_files, n_workers=n_workers)

        # Map back to parameter values (runner.input_file is an absolute
        # path, so resolve both sides consistently).
        result_map: Dict[Any, AERMODRunResult] = {}
        for result in results:
            key = str(Path(result.input_file).resolve())
            for fp, pv in param_map.items():
                if str(Path(fp).resolve()) == key:
                    result_map[pv] = result
                    break
        return result_map


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def run_aermod(input_file: Union[str, Path],
               executable_path: Optional[Union[str, Path]] = None,
               timeout: int = 3600) -> AERMODRunResult:
    """
    Quick function to run AERMOD

    Args:
        input_file: Path to input file
        executable_path: Optional path to AERMOD executable
        timeout: Timeout in seconds

    Returns:
        AERMODRunResult
    """
    runner = AERMODRunner(executable_path=executable_path, log_level="WARNING")
    return runner.run(input_file, timeout=timeout)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    # Example: Run AERMOD from command line
    if len(sys.argv) > 1:
        input_file = sys.argv[1]

        print(f"Running AERMOD with: {input_file}\n")

        # Initialize runner
        runner = AERMODRunner(log_level="INFO")

        # Validate input
        valid, issues = runner.validate_input(input_file)
        if not valid:
            print("Input validation failed:")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)

        print("Input validation passed\n")

        # Run AERMOD
        result = runner.run(input_file)

        # Display results
        print("\n" + "="*70)
        print("AERMOD Run Results")
        print("="*70)
        print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"Runtime: {result.runtime_seconds:.2f} seconds")
        print(f"Messages: {result.fatal_count} fatal error(s), "
              f"{result.warning_count} warning(s)")
        for msg in result.fatal_messages:
            print(f"  {msg.pathway} {msg}")

        if result.output_file:
            print(f"Output file: {result.output_file}")

        if result.error_message:
            print(f"Error: {result.error_message}")

        print("="*70)

        sys.exit(0 if result.success else 1)

    else:
        print("PyAERMOD Runner")
        print("\nUsage:")
        print("  python -m pyaermod.runner <input_file.inp>")
        print("\nOr import and use:")
        print("  from pyaermod.runner import AERMODRunner")
        print("  runner = AERMODRunner()")
        print("  result = runner.run('myfile.inp')")
        print("  if result.success:")
        print("      print('AERMOD run succeeded!')")

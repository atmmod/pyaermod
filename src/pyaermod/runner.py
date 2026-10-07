"""
PyAERMOD Runner

Executes AERMOD binaries from Python with error handling, progress monitoring,
and batch processing capabilities.
"""

import atexit
import contextlib
import hashlib
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
from collections.abc import ItemsView, Mapping, ValuesView
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

# The files AERMOD writes as aermod.out, aermod.err and aermod.sum, which
# the runner renames after the deck: <stem>.out, <stem>.err, <stem>.sum.
_OUTPUT_SUFFIXES = {"output": ".out", "error": ".err", "summary": ".sum"}

# Where symbolic links fail (Windows without the privilege), the runner
# copies the deck to aermod.inp instead. This file, beside the copy,
# holds the copy's SHA-256, so that a copy left behind when the Python
# process was killed is known as the runner's, not taken for a deck.
_COPY_MARKER = ".pyaermod-aermod-inp.sha256"


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

        AERMOD reads ``<working_dir>/aermod.inp``. The runner links the
        deck to that name for the run and renames ``aermod.out``,
        ``.err`` and ``.sum`` after the deck. A deck that is already
        ``aermod.inp``, or that ``aermod.inp`` links to, runs in place.
        When ``aermod.inp`` is another deck, the run fails without
        starting AERMOD, so that deck and its ``aermod.out`` are kept.
        Where links cannot be made, the deck is copied to ``aermod.inp``
        instead; a copy the runner left behind (its process killed
        mid-run) is replaced, not taken for another deck.
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

        staged = self._stage(input_path, work_dir)
        if isinstance(staged, AERMODRunResult):
            return staged

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
            # subprocess.run has killed AERMOD.
            return self._timed_out(input_path, work_dir, start_time, timeout)

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
            self._unstage(staged)

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

    def _stage(self, input_path: Path, work_dir: Path) -> Union["_Staged", AERMODRunResult]:
        """Lock ``work_dir`` and point its ``aermod.inp`` at the deck.

        AERMOD reads from a fixed filename (aermod.inp) in its working
        directory. We symlink the user's .inp file to aermod.inp, run AERMOD,
        then rename the output files back to the user's naming convention.

        Concurrency safety: two concurrent runs in the same working_dir would
        clobber each other's symlinks + outputs, so this first acquires an
        exclusive lock on a sentinel file (blocking until it is free).
        :meth:`_unstage` releases it.

        Returns the :class:`_Staged` run, or a failed :class:`AERMODRunResult`
        (the lock already released) when ``aermod.inp`` is another deck.
        It is :meth:`_claim` then :meth:`_prepare`.
        """
        staged = self._claim(input_path, work_dir)
        if not isinstance(staged, AERMODRunResult):
            self._prepare(input_path, work_dir, staged)
        return staged

    def _claim(self, input_path: Path, work_dir: Path) -> Union["_Staged", AERMODRunResult]:
        """Lock ``work_dir`` and check its ``aermod.inp``, changing nothing.

        Returns the :class:`_Staged` run, not yet prepared, or a failed
        :class:`AERMODRunResult` (the lock already released) when
        ``aermod.inp`` is another deck. A run that stops here releases
        the lock alone, with :func:`_release_dir_lock`.
        """
        lock_path = work_dir / ".pyaermod.lock"
        lock_fh = _acquire_dir_lock(lock_path)

        # AERMOD reads <work_dir>/aermod.inp. It is in place when it is
        # this deck, or a link to it: run it as it is and leave it there.
        # A regular file named aermod.inp that is another deck (EPA's
        # default name, as in a base case beside its variants) must not
        # be replaced, and the aermod.out this run would write, then
        # rename, may be that deck's results. Refuse before touching
        # anything. A link to another file is one this runner left or
        # one it can re-create, so it is replaced, and so is a copy this
        # runner made (see _is_runner_copy).
        aermod_inp = work_dir / "aermod.inp"
        copy_marker = work_dir / _COPY_MARKER
        in_place = aermod_inp.exists() and aermod_inp.samefile(input_path)
        if (not in_place and aermod_inp.exists() and not aermod_inp.is_symlink()
                and not _is_runner_copy(aermod_inp, copy_marker)):
            _release_dir_lock(lock_fh)
            return AERMODRunResult(
                success=False,
                input_file=str(input_path),
                error_message=(
                    f"The working directory {work_dir} already holds another deck "
                    "named aermod.inp, the file AERMOD reads; running this deck "
                    "there would replace it and overwrite its aermod.out. Rename "
                    "that deck, or give this run a different working_dir"
                ),
            )
        return _Staged(lock_fh, aermod_inp, copy_marker, in_place)

    @staticmethod
    def _prepare(input_path: Path, work_dir: Path, staged: "_Staged") -> None:
        """Remove an earlier run's outputs and point ``aermod.inp`` at the deck."""
        # Files left by an earlier run would otherwise stand in for this
        # one's whenever this run writes none: a timeout before AERMOD
        # opens aermod.out, a cancel, or a crash. The verdict would then be
        # read from the old .out, and resume_batch would count the deck
        # as done. Remove this deck's outputs, and AERMOD's own
        # aermod.out/.err/.sum, before AERMOD starts.
        input_name = input_path.stem
        for suffix in _OUTPUT_SUFFIXES.values():
            for stale in (work_dir / f"{input_name}{suffix}", work_dir / f"aermod{suffix}"):
                with contextlib.suppress(FileNotFoundError):
                    stale.unlink()

        # Create symlink: aermod.inp -> <input_name>.inp, unless the deck
        # is already in place (see _claim).
        if not staged.in_place:
            aermod_inp = staged.aermod_inp
            try:
                if aermod_inp.exists() or aermod_inp.is_symlink():
                    aermod_inp.unlink()
                aermod_inp.symlink_to(os.path.relpath(input_path, work_dir))
            except (OSError, ValueError):
                # Fallback: copy the file (ValueError: relpath across
                # Windows drives). Mark the copy first, so that one left
                # by a killed process is still known as the runner's.
                staged.copy_marker.write_text(_sha256(input_path) + "\n")
                shutil.copy2(str(input_path), str(aermod_inp))

    @staticmethod
    def _unstage(staged: "_Staged") -> None:
        """Remove the ``aermod.inp`` link or copy and release the directory lock.

        A deck that was already ``aermod.inp`` stays: it is the user's.
        """
        if not staged.in_place:
            for made in (staged.aermod_inp, staged.copy_marker):
                if made.exists() or made.is_symlink():
                    with contextlib.suppress(OSError):
                        made.unlink()
        _release_dir_lock(staged.lock_fh)

    def _collect(self, result: "subprocess.CompletedProcess[str]", input_path: Path,
                 work_dir: Path, start_time: datetime, *, capture_output: bool = True,
                 cancelled: bool = False) -> AERMODRunResult:
        """Rename AERMOD's outputs, read its verdict and build the result."""
        input_name = input_path.stem
        output_files = _output_files(work_dir, input_name)

        _rename_aermod_outputs(work_dir, input_name)

        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()

        self.logger.debug(f"AERMOD completed with return code: {result.returncode}")
        self.logger.debug(f"Runtime: {runtime:.2f}s")

        # Check for output files. _stage removed any an earlier run left,
        # so an <name>.out is this run's, whether it finished, was
        # cancelled or crashed.
        has_output = output_files['output'].exists()

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

    def _timed_out(self, input_path: Path, work_dir: Path, start_time: datetime,
                   timeout: float) -> AERMODRunResult:
        """The result of a run killed at its timeout.

        What AERMOD wrote is kept under the deck's name, as after any
        other run: left as aermod.out, it would be taken for the next
        run's output.
        """
        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()

        input_name = input_path.stem
        _rename_aermod_outputs(work_dir, input_name)
        output_files = _output_files(work_dir, input_name)
        has_output = output_files['output'].exists()

        self.logger.error(f"AERMOD execution timed out after {timeout}s")

        return AERMODRunResult(
            success=False,
            input_file=str(input_path),
            runtime_seconds=runtime,
            output_file=str(output_files['output']) if has_output else None,
            error_file=str(output_files['error']) if output_files['error'].exists() else None,
            summary_file=str(output_files['summary']) if output_files['summary'].exists() else None,
            error_message=(
                f"Execution timed out after {timeout} seconds; AERMOD was "
                "stopped before it finished"
            ),
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

        # A negative return code is a POSIX signal: AERMOD was stopped
        # from outside (SIGTERM, SIGKILL, ...) or crashed (SIGSEGV), and
        # its .out, if it wrote one, simply ends where the run was cut
        # off, so neither the .out scan nor the missing banner says
        # anything more.
        killed = result.returncode is not None and result.returncode < 0
        if killed:
            parts.append(_describe_signal(-result.returncode,
                                          None if wrote_out else out.name))

        parts.extend(self._error_context(
            result, output_files, scan_output=not fatal and not killed and wrote_out,
        ))

        if not fatal and not killed and finished_successfully is False and wrote_out:
            parts.append(
                "AERMOD did not report success: no '*** AERMOD Finishes "
                f"Successfully ***' line in {out.name}"
            )

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

        The results come back in the order of ``input_files``, whatever
        order the runs finish in: ``results[i]`` belongs to
        ``input_files[i]``, and its ``input_file`` is that deck's
        absolute path.

        The runs happen in worker processes. On macOS and Windows those
        are started with ``spawn``, which imports the calling script
        again in every worker, so a script must call ``run_batch`` from
        under ``if __name__ == "__main__":``. Without the guard each
        worker stops with Python's "An attempt has been made to start a
        new process before the current process has finished its
        bootstrapping phase" and every run comes back failed with "A
        process in the process pool was terminated abruptly"::

            if __name__ == "__main__":
                results = runner.run_batch(decks, n_workers=4)

        Args:
            input_files: List of input file paths
            n_workers: Number of parallel workers
            timeout: Timeout per run (seconds)
            stop_on_error: Stop at the first failed run. Runs not yet
                started are cancelled and runs already started finish.
                The list still holds one result per deck: a cancelled
                deck's result has ``success=False`` and the
                ``error_message`` "Not run: the batch stopped after an
                earlier run failed".

        Returns:
            List of AERMODRunResult objects, in the order of ``input_files``
        """
        self.logger.info(f"Starting batch run: {len(input_files)} files, {n_workers} workers")

        # Results are filed by the index of their deck, so the list comes
        # back in input order however the runs finish.
        results_by_index: Dict[int, AERMODRunResult] = {}

        def _collect(index: int, future) -> AERMODRunResult:
            input_file = input_files[index]
            try:
                result = future.result()
            except Exception as e:
                self.logger.error(f"✗ {input_file}: Exception: {e}")
                result = AERMODRunResult(
                    success=False,
                    input_file=str(Path(input_file).resolve()),
                    error_message=str(e)
                )
            else:
                if result.success:
                    self.logger.info(f"✓ {Path(result.input_file).name} ({result.runtime_seconds:.1f}s)")
                else:
                    self.logger.error(f"✗ {Path(result.input_file).name}: {result.error_message}")
            results_by_index[index] = result
            return result

        exe_path = str(self.executable)
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # Dispatch via a module-level function so workers don't
            # have to pickle `self` (which includes a Logger + Handler
            # that aren't fork-safe under spawn).
            future_to_index = {
                executor.submit(_batch_worker, exe_path, str(inp), timeout): i
                for i, inp in enumerate(input_files)
            }

            # Process completed jobs
            for future in as_completed(future_to_index):
                result = _collect(future_to_index[future], future)
                if not result.success and stop_on_error:
                    self.logger.error("Stopping batch run due to error")
                    # Cancel the runs not yet started; the ones already
                    # running finish before the executor shuts down.
                    for f in future_to_index:
                        f.cancel()
                    break

        # After a stop, file the runs that were running at the time and
        # mark the cancelled ones, so every deck still has its result.
        not_run = 0
        for future, index in future_to_index.items():
            if index in results_by_index:
                continue
            if future.cancelled():
                not_run += 1
                results_by_index[index] = AERMODRunResult(
                    success=False,
                    input_file=str(Path(input_files[index]).resolve()),
                    error_message="Not run: the batch stopped after an earlier run failed",
                )
            else:
                _collect(index, future)

        results = [results_by_index[i] for i in sorted(results_by_index)]
        success_count = sum(r.success for r in results)
        failed_count = len(results) - success_count - not_run
        self.logger.info(
            f"Batch complete: {success_count}/{len(results)} succeeded, "
            f"{failed_count} failed"
            + (f", {not_run} not run" if not_run else "")
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


def stop_active_runs() -> None:
    """Kill every background AERMOD run still going in this process.

    Runs when Python exits normally (``atexit``), which covers a clean
    exit and Ctrl+C but not a process killed by a signal it does not
    handle, such as SIGTERM: a server should also call this from its own
    shutdown hook (the GUI does, from NiceGUI's ``app.on_shutdown``).
    """
    for run in list(_ACTIVE_RUNS):
        run._kill()


_stop_active_runs = atexit.register(stop_active_runs)


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

        staged = runner._claim(input_path, work_dir)
        if isinstance(staged, AERMODRunResult):
            return staged
        stdout_path = work_dir / f"{input_name}.subproc.stdout"
        stderr_path = work_dir / f"{input_name}.subproc.stderr"
        start_time = datetime.now()
        prepared = False
        try:
            with contextlib.ExitStack() as logs:
                # One hold of the lock from the cancel check to Popen: a
                # run cancelled while it waited for the directory returns
                # before it removes an earlier run's outputs or opens
                # anything, and one cancelled later has an AERMOD to stop.
                with self._lock:
                    if self._cancel_at is not None:
                        return self._never_started(input_path, start_time)
                    prepared = True
                    runner._prepare(input_path, work_dir, staged)
                    stdout_fh = logs.enter_context(open(stdout_path, "wb"))
                    stderr_fh = logs.enter_context(open(stderr_path, "wb"))
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
                return runner._timed_out(input_path, work_dir, start_time, self.timeout)
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
            if prepared:
                runner._unstage(staged)
            else:
                _release_dir_lock(staged.lock_fh)

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


class _Staged(NamedTuple):
    """A deck made ready to run by :meth:`AERMODRunner._stage`."""
    lock_fh: Any
    aermod_inp: Path
    copy_marker: Path
    in_place: bool


def _output_files(work_dir: Path, input_name: str) -> Dict[str, Path]:
    """The run's ``output``, ``error`` and ``summary`` files, named after the deck."""
    return {key: work_dir / f"{input_name}{suffix}" for key, suffix in _OUTPUT_SUFFIXES.items()}


def _rename_aermod_outputs(work_dir: Path, input_name: str) -> None:
    """Rename AERMOD's ``aermod.out``/``.err``/``.sum`` after the deck, as ``<input_name>.*``."""
    for suffix in _OUTPUT_SUFFIXES.values():
        aermod_file = work_dir / f"aermod{suffix}"
        target_file = work_dir / f"{input_name}{suffix}"
        if aermod_file.exists() and aermod_file != target_file:
            aermod_file.replace(target_file)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_runner_copy(aermod_inp: Path, marker: Path) -> bool:
    """Whether a regular ``aermod.inp`` is a copy this runner left behind.

    The copy fallback removes its copy after the run, but not when the
    Python process is killed first. The copy is the runner's when its
    SHA-256 is the one in ``marker``, written before the copy was made.
    Matching bytes alone do not make it the runner's: a base deck kept as
    ``aermod.inp`` beside a variant not yet edited has the variant's
    bytes, and replacing it would delete it and its ``aermod.out``.
    """
    try:
        return marker.read_text().strip() == _sha256(aermod_inp)
    except OSError:
        return False


def _describe_signal(signum: int, unwritten: Optional[str] = None) -> str:
    """Say which signal stopped AERMOD, such as ``SIGTERM (signal 15)``.

    ``unwritten`` names the ``.out`` file when AERMOD was stopped before
    it wrote one (a crash at setup, say), which is then what the message
    says instead of pointing at an output that does not exist.
    """
    try:
        name = f"{signal.Signals(signum).name} (signal {signum})"
    except ValueError:
        name = f"signal {signum}"
    if unwritten is not None:
        return f"AERMOD was stopped by {name} before it finished, and wrote no {unwritten}"
    return (
        f"AERMOD was stopped by {name} before it finished; "
        "its output ends where the run was cut off"
    )


class _FileState(NamedTuple):
    mtime_ns: int
    size: int
    ino: int


def _dir_state(directory: Path) -> Dict[str, _FileState]:
    """The regular files directly in ``directory``, by name, as they stand now.

    Taken just before a program runs, so that :func:`_files_written` can
    tell afterwards which files the run created or changed. Comparing
    each file with its own earlier state, not its mtime with the wall
    clock, matters on Linux, which stamps files from a coarse kernel
    clock: a file written a few ms after ``datetime.now()`` can carry an
    earlier mtime and would be missed.
    """
    state: Dict[str, _FileState] = {}
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return state
    for entry in entries:
        try:
            if entry.is_file():
                st = entry.stat()
                state[entry.name] = _FileState(st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            continue
    return state


def _files_written(directory: Path, before: Dict[str, _FileState]) -> List[str]:
    """The files in ``directory`` that are new or changed since ``before``, sorted.

    A file rewritten in place with the same size within one tick of the
    filesystem's timestamp clock of ``before`` being taken is not seen.
    """
    after = _dir_state(directory)
    return [str(directory / name) for name in sorted(after)
            if before.get(name) != after[name]]


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


# A sweep value keeps its own text in the deck's file name when it is a
# plain number, string or boolean whose text (with every character other
# than letters, digits and ._+- turned into "_") is this long at most
# and differs from every other value's; any other value is named by its
# position and a hash.
_SWEEP_LABEL_MAX = 48
_SWEEP_UNSAFE = re.compile(r"[^A-Za-z0-9._+-]")


def _sweep_labels(values: Sequence[Any]) -> List[str]:
    """File-name labels for sweep values: readable when safe, unique always."""
    plain: List[Optional[str]] = []
    for value in values:
        if isinstance(value, (bool, int, float, str)):
            text = _SWEEP_UNSAFE.sub("_", str(value))
            plain.append(text if 0 < len(text) <= _SWEEP_LABEL_MAX else None)
        else:
            plain.append(None)
    counts: Dict[str, int] = {}
    for candidate in plain:
        if candidate is not None:
            counts[candidate.lower()] = counts.get(candidate.lower(), 0) + 1
    labels: List[str] = []
    for i, (value, candidate) in enumerate(zip(values, plain)):
        if candidate is not None and counts[candidate.lower()] == 1:
            labels.append(candidate)
            continue
        try:
            from .ensemble import canonical_json
            text = canonical_json(value)
        except (TypeError, ValueError):
            text = repr(value)
        labels.append(f"{i:03d}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}")
    return labels


def _values_equal(a: Any, b: Any) -> bool:
    try:
        return bool(a is b or a == b)
    except Exception:  # e.g. NumPy arrays, whose == is element-wise
        return False


class _SweepItemsView(ItemsView):
    def __iter__(self):
        return iter(self._mapping._pairs)


class _SweepValuesView(ValuesView):
    def __iter__(self):
        return (result for _, result in self._mapping._pairs)


class SweepResults(Mapping):
    """The results of :meth:`BatchRunner.parameter_sweep`, by sweep value.

    A read-only mapping from each value of the sweep, in sweep order, to
    its :class:`AERMODRunResult`. Values need not be hashable: looking
    one up compares by ``==``, so ``results[psd]`` works for a
    :class:`~pyaermod.sources.ParticleDepositionParams`. ``keys()``,
    ``items()`` and ``values()`` are the usual mapping views, in sweep
    order.

    It is not a ``dict``: ``isinstance(results, dict)`` is False, it
    cannot be changed, and ``json.dumps`` does not take it. When the
    values are hashable, ``dict(results)`` gives the dict
    ``parameter_sweep`` returned in pyaermod 2.2 and earlier.
    """

    def __init__(self, pairs: Sequence[Tuple[Any, AERMODRunResult]]):
        self._pairs = list(pairs)

    def __getitem__(self, key: Any) -> AERMODRunResult:
        for value, result in self._pairs:
            if _values_equal(value, key):
                return result
        raise KeyError(key)

    def __iter__(self):
        return (value for value, _ in self._pairs)

    def __len__(self) -> int:
        return len(self._pairs)

    def items(self) -> ItemsView:
        """``(value, result)`` pairs in sweep order."""
        return _SweepItemsView(self)

    def values(self) -> ValuesView:
        """Results in sweep order."""
        return _SweepValuesView(self)

    def __repr__(self) -> str:
        return f"SweepResults({self._pairs!r})"


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
                       source_index: int = 0) -> SweepResults:
        """Run AERMOD over a sweep of one parameter on one source.

        For each value in ``parameter_values``:

        1. Deep-copy ``base_project``
        2. Set ``parameter_name`` on the indicated source (or on the
           project if the name contains a dot, e.g. ``"control.title_one"``)
        3. Write the modified project to ``output_dir/run_{name}_{label}.inp``
        4. Queue the file for batch execution

        ``label`` is the value's own text when the value is a number,
        string or boolean whose text is short, holds only letters,
        digits and ``._+-`` once every other character (a space, a
        ``/``) is turned into ``_``, and differs from every other
        value's: ``run_emission_rate_0.5.inp``. Any other value, such as
        a :class:`~pyaermod.sources.ParticleDepositionParams` for a
        size-distribution sweep, is labelled by its position and the
        first 12 hex digits of the SHA-256 of its canonical JSON
        (:func:`pyaermod.ensemble.canonical_json`):
        ``run_particle_deposition_001_3fa9c0d27e41.inp``.

        Every output file the deck names (PLOTFILE, POSTFILE, ...) is
        renamed to ``run_{name}_{label}_<file name>`` in ``output_dir``,
        so the runs do not overwrite each other's results. Files AERMOD
        names itself are not renamed, so the runs share them and the
        last run's copy is kept: the file of a debug option or ERRORFIL
        given without a name, DEPOS's ``GDEP.DAT``, ``PDEP.DAT`` and
        ``DEPOS.DBG``, and PVMRM's ``RelDisp.dbg``.

        All the decks share ``output_dir``, whose lock lets one AERMOD
        run at a time there (see :meth:`AERMODRunner.run`), so the runs
        do not overlap whatever ``n_workers`` is.
        :func:`pyaermod.ensemble.run_design` gives each run its own
        directory and does run them in parallel.

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
            Values to substitute in. They need not be hashable, but no
            two may be equal.
        output_dir : Path
            Directory for generated .inp files and AERMOD outputs.
        n_workers : int
            Number of parallel AERMOD workers.
        source_index : int
            Which source to mutate when ``parameter_name`` is a plain
            field name. Defaults to 0 (the first source).

        Returns
        -------
        SweepResults
            Mapping of parameter value -> AERMODRunResult, in sweep order.

        Raises
        ------
        ValueError
            When two values are equal: they would make the same run.
            Also when two of the deck's output files would get the same
            name once their directories are dropped (compared ignoring
            case), such as ``annual/result.plt`` and
            ``hourly/result.plt``, or when a renamed file name is longer
            than AERMOD's 200 characters
            (:func:`pyaermod.ensemble.rewrite_output_names`).
        """
        import copy

        from .ensemble import rewrite_output_names

        values = list(parameter_values)
        for i, a in enumerate(values):
            for j in range(i):
                if _values_equal(values[j], a):
                    raise ValueError(
                        f"parameter_sweep: values {j} ({values[j]!r}) and {i} "
                        f"({a!r}) are equal, so they would be the same run"
                    )

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        input_files: List[Path] = []
        for value, label in zip(values, _sweep_labels(values)):
            project = copy.deepcopy(base_project)
            _set_sweep_parameter(project, parameter_name, value, source_index)
            stem = f"run_{parameter_name}_{label}"
            rewrite_output_names(project, prefix=f"{stem}_")
            filename = output_path / f"{stem}.inp"
            project.write(str(filename))
            input_files.append(filename)

        # run_batch returns results[i] for input_files[i].
        results = self.runner.run_batch(input_files, n_workers=n_workers)
        return SweepResults(list(zip(values, results)))


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

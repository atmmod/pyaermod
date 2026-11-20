"""
Finding and running the EPA programs.

What every runner (AERMOD, AERMET, AERSCREEN, AERSURFACE, AERMAP) does the
same way: look an executable up, run it with its output captured in files,
stop its whole process tree, and tell which files a run wrote.
"""

import contextlib
import os
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Union, overload


@overload
def find_executable(program_names: Sequence[str],
                    path: Optional[Union[str, Path]] = None, *,
                    label: str,
                    not_found: str,
                    resolve: bool = False) -> Path: ...


@overload
def find_executable(program_names: Sequence[str],
                    path: Optional[Union[str, Path]] = None, *,
                    label: str,
                    not_found: None = None,
                    resolve: bool = False) -> Optional[Path]: ...


def find_executable(program_names: Sequence[str],
                    path: Optional[Union[str, Path]] = None, *,
                    label: str,
                    not_found: Optional[str] = None,
                    resolve: bool = False) -> Optional[Path]:
    """``path`` if given, else the first of ``program_names`` on ``PATH``.

    Raises ``FileNotFoundError`` ("<label> not found: <path>") when ``path``
    does not exist. When nothing is on ``PATH`` it raises
    ``FileNotFoundError(not_found)``, or returns None if ``not_found`` is
    None. ``resolve`` makes the answer absolute, with links followed.
    """
    found: Optional[Path] = None
    if path:
        found = Path(path)
        if not found.exists():
            raise FileNotFoundError(f"{label} not found: {path}")
    else:
        for name in program_names:
            on_path = shutil.which(name)
            if on_path:
                found = Path(on_path)
                break
    if found is None:
        if not_found is None:
            return None
        raise FileNotFoundError(not_found)
    return found.resolve() if resolve else found


class _FileState(NamedTuple):
    mtime_ns: int
    size: int
    ino: int


def _tree_popen_kwargs() -> Dict[str, Any]:
    """Popen arguments that make a child the root of its own process tree.

    POSIX: a session of its own, so ``killpg`` reaches it and everything it
    started. Windows: a new process group (``taskkill /T`` does the walk).
    """
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _kill_tree(proc: "subprocess.Popen[Any]", *, force: bool = True) -> None:
    """Stop ``proc`` and the processes it started.

    ``proc`` must have been started with :func:`_tree_popen_kwargs`.
    ``force=False`` asks politely (SIGTERM) where the platform has such a
    thing; Windows always ends the tree (``taskkill /T /F``, then
    ``proc.kill()`` as a fallback; correct by inspection, not run here).
    """
    if sys.platform == "win32":  # same as os.name == "nt", and mypy follows it
        with contextlib.suppress(Exception):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30, check=False)
        with contextlib.suppress(OSError):
            proc.kill()
        return
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        # The group is gone (or was never ours): the child alone.
        with contextlib.suppress(OSError):
            proc.kill() if force else proc.terminate()


def _run_tree(cmd: Sequence[str], *, timeout: Optional[float] = None,
              input: Optional[str] = None, **popen_kwargs: Any) -> "subprocess.CompletedProcess[str]":
    """``subprocess.run`` that, on a timeout or an interrupt, ends the whole process tree.

    ``subprocess.run`` kills only the process it started; AERSCREEN's
    AERMOD, MAKEMET and AERMAP would run on after the caller was told
    "timed out". Raises :class:`subprocess.TimeoutExpired` like it.
    """
    if input is not None:
        popen_kwargs["stdin"] = subprocess.PIPE
    with subprocess.Popen(cmd, **_tree_popen_kwargs(), **popen_kwargs) as proc:
        try:
            proc.communicate(input, timeout=timeout)
        except BaseException:
            _kill_tree(proc)
            proc.wait()
            raise
    return subprocess.CompletedProcess(list(cmd), proc.returncode)


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


class Captured(NamedTuple):
    """What :func:`run_captured` saw of one run."""
    returncode: Optional[int]  # None when the run timed out
    stdout: str                # empty when the run timed out
    stderr: str
    start: datetime
    end: datetime
    files_written: List[str]   # see _files_written; empty when the run timed out
    timeout: Optional[subprocess.TimeoutExpired]  # set when the run timed out

    @property
    def runtime_seconds(self) -> float:
        return (self.end - self.start).total_seconds()


def run_captured(cmd: Sequence[str], work_dir: Path, stem: str, timeout: Optional[float],
                 *, input: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None) -> Captured:
    """Run ``cmd`` in ``work_dir`` with :func:`_run_tree` and capture its output.

    stdout and stderr go to ``<stem>.subproc.stdout`` and ``.stderr`` in
    ``work_dir``, not through OS pipes: a pipe's buffer (about 64 KB)
    deadlocks a chatty program once it fills and no one is reading. The
    last 1 MB of each is returned. A run that times out has had its
    process tree killed and comes back with ``timeout`` set.
    """
    start = datetime.now()
    before = _dir_state(work_dir)
    stdout_path = work_dir / f"{stem}.subproc.stdout"
    stderr_path = work_dir / f"{stem}.subproc.stderr"
    with open(stdout_path, "w", encoding="utf-8", errors="replace") as stdout_fh, \
            open(stderr_path, "w", encoding="utf-8", errors="replace") as stderr_fh:
        try:
            proc = _run_tree(list(cmd), cwd=str(work_dir), env=env, input=input, text=True,
                             stdout=stdout_fh, stderr=stderr_fh, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            return Captured(None, "", "", start, datetime.now(), [], exc)
    end = datetime.now()
    return Captured(proc.returncode, _read_capped(stdout_path, 1_000_000),
                    _read_capped(stderr_path, 1_000_000), start, end,
                    _files_written(work_dir, before), None)

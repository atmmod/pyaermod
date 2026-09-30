"""
The GUI's session: the project under edit, its runs, and change events.

A :class:`Session` is everything one browser tab of the GUI works on: the
:class:`~pyaermod.input_generator.AERMODProject`, the file it came from,
the unsaved-changes flag, the latest validation result and the history of
AERMOD runs. Every user operation is a method (:meth:`Session.new`,
:meth:`Session.open_json`, :meth:`Session.add_source`,
:meth:`Session.start_run`, ...), and each one tells its observers what
changed by emitting a :class:`Change`.

The pages of the GUI never keep a reference to a part of the project
across a :attr:`SessionEvent.PROJECT_REPLACED` event: they subscribe to
the events that concern them and rebuild from the session (see
:mod:`pyaermod.gui_v2._live`). This module imports nothing from NiceGUI,
so every operation can be tested without a UI.

``Session`` is a plain class compared by identity, never a dataclass: the
NiceGUI refreshables and observer lists that hang off a session must not
mistake two tabs whose sessions happen to hold equal values for one.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
import re
import tempfile
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Union,
)

from ..input_generator import AERMODProject, ControlPathway
from .project_io import check_project, project_from_json, project_to_json, save_project
from .state import _empty_project

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..aermet import SurfaceFilePeriod
    from ..runner import AERMODProgress, AERMODRun, AERMODRunner, AERMODRunResult
    from ..validator import ValidationResult

logger = logging.getLogger(__name__)


class SessionEvent(StrEnum):
    """What changed in a :class:`Session`."""

    PROJECT_REPLACED = "project_replaced"      # new(), open_json()
    PROJECT_CHANGED = "project_changed"        # any in-place change; Change.part names what
    DIRTY_CHANGED = "dirty_changed"            # the dirty flag or the file name changed
    VALIDATION_CHANGED = "validation_changed"  # validate()
    RUN_STARTED = "run_started"
    RUN_PROGRESS = "run_progress"              # a background run printed another day
    RUN_FINISHED = "run_finished"


#: The parts of a project a :attr:`SessionEvent.PROJECT_CHANGED` names.
PARTS = ("control", "sources", "receptors", "meteorology", "output")

#: Receptor kind (the class name) -> the ReceptorPathway list holding it.
_RECEPTOR_LISTS = {
    "CartesianGrid": "cartesian_grids",
    "PolarGrid": "polar_grids",
    "DiscreteReceptor": "discrete_receptors",
}

#: The deck's file name in the run directory. NOT "aermod.inp":
#: AERMODRunner reserves that name for the symlink it points at the real
#: deck (and renames aermod.out -> <stem>.out afterwards). A deck written
#: as aermod.inp would be unlinked and replaced by a self-referencing
#: symlink.
DECK_NAME = "pyaermod_gui.inp"

_DEFAULT_FILE_NAME = "project.json"

#: Characters browsers and file systems replace in a download's name.
_UNSAFE_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f"*:<>?|]')


@dataclass(frozen=True)
class RunRecord:
    """One AERMOD run started from the session.

    ``work_dir`` is kept exactly as the user gave it (never resolved), so
    the GUI shows the directory the user typed.
    """

    number: int
    work_dir: Path
    deck_path: Path
    started_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[AERMODRunResult] = None   # None when the runner raised
    error: Optional[str] = None                # str(exc) when the runner raised
    # WP-G4: a background run's progress, and the days of met data it has
    # to process (from the surface file; None when it could not be read).
    progress: Optional[AERMODProgress] = None
    expected_days: Optional[int] = None

    @property
    def in_progress(self) -> bool:
        return self.finished_at is None

    @property
    def success(self) -> bool:
        return self.result is not None and bool(self.result.success)

    @property
    def cancelled(self) -> bool:
        return self.result is not None and bool(getattr(self.result, "cancelled", False))

    @property
    def status(self) -> str:
        """"Running", "Succeeded", "Cancelled" or "Failed"."""
        if self.in_progress:
            return "Running"
        if self.success:
            return "Succeeded"
        return "Cancelled" if self.cancelled else "Failed"

    @property
    def fraction_done(self) -> Optional[float]:
        """Days processed over the days of met data, in [0, 1]; None if unknown."""
        if self.progress is not None and self.progress.stage == "output":
            return 1.0
        if not self.expected_days or self.progress is None:
            return None
        return min(1.0, self.progress.days_processed / self.expected_days)


@dataclass(frozen=True)
class Change:
    """One change event: what happened, and to which part or run."""

    event: SessionEvent
    part: Optional[str] = None           # PROJECT_CHANGED only
    run: Optional[RunRecord] = None      # RUN_* only


@dataclass
class RunOptions:
    """The Run step's inputs. Not part of the project, and not saved with it."""

    working_dir: str = ""
    timeout_s: int = 600


class ProjectFileError(ValueError):
    """:meth:`Session.open_json` could not read the project file."""


class DeckError(ValueError):
    """The project could not be written as an AERMOD deck."""


class RunInProgressError(RuntimeError):
    """:meth:`Session.start_run` was called while a run is in progress."""


def _call_now(callback: Callable[[], object]) -> None:
    callback()


# (path, mtime_ns, size) -> the period read from that surface file.
_PERIOD_CACHE: Dict[Tuple[str, int, int], Any] = {}
_PERIOD_CACHE_SIZE = 16


def read_met_period(path: Path) -> SurfaceFilePeriod:
    """:func:`~pyaermod.aermet.read_surface_period`, cached by path and mtime.

    Raises what it raises (``OSError``, ``ValueError``).
    """
    from ..aermet import read_surface_period

    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    period = _PERIOD_CACHE.get(key)
    if period is None:
        period = read_surface_period(path)
        if len(_PERIOD_CACHE) >= _PERIOD_CACHE_SIZE:
            _PERIOD_CACHE.pop(next(iter(_PERIOD_CACHE)))
        _PERIOD_CACHE[key] = period
    return period


Observer = Callable[[Change], None]


def _orphan_record(result: Optional[AERMODRunResult]) -> RunRecord:
    """A record for the end of a run the session no longer tracks."""
    deck = Path(result.input_file) if result is not None else Path(DECK_NAME)
    return RunRecord(number=0, work_dir=deck.parent, deck_path=deck, started_at=datetime.now())


def clean_file_name(name: Optional[str]) -> str:
    """The file name a download is offered under.

    Any directory part is dropped (POSIX or Windows spelling), characters
    a browser would rewrite (``"*:<>?|`` and control characters) become
    ``_`` so the header names the file the browser saved, an empty name
    becomes ``project.json`` and a name without a ``.json`` suffix gets one.
    """
    # The last part after either separator; "C:" is not a directory here.
    parts = [p.strip() for p in re.split(r"[\\/]", name or "")]
    parts = [p for p in parts if p not in ("", ".", "..")]
    base = _UNSAFE_NAME_CHARS.sub("_", parts[-1]) if parts else ""
    if not base:
        return _DEFAULT_FILE_NAME
    if not base.lower().endswith(".json"):
        base += ".json"
    return base


class Session:
    """Everything one GUI tab works on, and the operations on it.

    Attributes
    ----------
    project
        The project under edit.
    project_path
        A file on the server's disk that :meth:`save` writes to. Set by
        :meth:`open_json` with a path and by :meth:`save_as` (desktop mode).
    file_name
        The file name the header shows. Every open or save that knows a
        name sets it, including a browser download.
    dirty
        True while the project has changes that were not saved.
    validation
        The result of the latest :meth:`validate`, or None.
    runs
        Every finished run of this session, oldest first.
    run_in_progress
        The run :meth:`start_run` is executing, or None.
    run_options
        The Run step's inputs.
    tab_id
        Which browser tab owns this session. The GUI shell reads and
        writes it; the session never interprets it.
    dispatch
        How a background run's events reach the session's owner:
        ``dispatch(callback)`` must arrange for ``callback()`` to run on the
        thread that owns the session. The GUI passes its event loop's
        ``call_soon_threadsafe``; the default calls at once, on the run's
        own thread (fine for scripts and tests that only wait).
    """

    def __init__(self, project: Optional[AERMODProject] = None, *,
                 tab_id: Optional[str] = None) -> None:
        self.project: AERMODProject = project if project is not None else _empty_project()
        self.project_path: Optional[Path] = None
        self.file_name: Optional[str] = None
        self.dirty: bool = False
        self.validation: Optional[ValidationResult] = None
        self.runs: List[RunRecord] = []
        self.run_in_progress: Optional[RunRecord] = None
        self.run_options = RunOptions()
        self.tab_id: Optional[str] = tab_id
        self.dispatch: Callable[[Callable[[], object]], Any] = _call_now
        self._observers: List[Tuple[frozenset, Observer]] = []
        # The background run in progress: its handle and serial number, and
        # the newest progress not yet applied on the owner's thread.
        self._run_handle: Optional[AERMODRun] = None
        self._run_serial = 0
        self._progress_lock = threading.Lock()
        self._pending_progress: Optional[Tuple[int, AERMODProgress]] = None
        # id(obj) -> (key, obj). Holding obj keeps its id from being reused
        # while the key exists.
        self._keys: Dict[int, Tuple[str, object]] = {}
        self._next_key = 1

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------
    @property
    def last_run(self) -> Optional[RunRecord]:
        """The newest finished run, including one whose runner raised."""
        return self.runs[-1] if self.runs else None

    @property
    def last_completed_run(self) -> Optional[RunRecord]:
        """The newest run AERMOD actually completed (it has a result and was not cancelled)."""
        for record in reversed(self.runs):
            if record.result is not None and not record.cancelled:
                return record
        return None

    @property
    def title(self) -> str:
        """The header text: the file name, and whether it has unsaved changes."""
        name = self.file_name or "Untitled"
        return f"PyAERMOD — {name}{' (modified)' if self.dirty else ''}"

    def suggested_file_name(self) -> str:
        return self.file_name or _DEFAULT_FILE_NAME

    def source_entries(self) -> List[Tuple[str, Any]]:
        """``(key, source)`` for every source, in the project's order."""
        self._prune()
        return [(self._key_for(s), s) for s in self.project.sources.sources]

    def receptor_entries(self) -> List[Tuple[str, str, Any]]:
        """``(key, kind, receptor)`` over Cartesian grids, polar grids, discrete."""
        self._prune()
        entries = []
        for _kind, attr in _RECEPTOR_LISTS.items():
            for rec in getattr(self.project.receptors, attr):
                entries.append((self._key_for(rec), type(rec).__name__, rec))
        return entries

    # ------------------------------------------------------------------
    # Observers
    # ------------------------------------------------------------------
    def subscribe(self, events: Union[SessionEvent, Iterable[SessionEvent]],
                  callback: Observer) -> Callable[[], None]:
        """Call ``callback(change)`` for each of ``events``; return an unsubscribe.

        The returned function may be called any number of times.
        """
        wanted = frozenset([events] if isinstance(events, SessionEvent) else events)
        entry = (wanted, callback)
        self._observers.append(entry)

        def unsubscribe() -> None:
            # Identity, not equality: two subscriptions of one callback are
            # two entries.
            for i, e in enumerate(self._observers):
                if e is entry:
                    del self._observers[i]
                    return

        return unsubscribe

    def _emit(self, change: Change) -> None:
        """Tell every observer of ``change.event``, in subscription order.

        Called only once the session is consistent. An observer that raises
        is logged and the others still run.
        """
        for wanted, callback in list(self._observers):
            if change.event not in wanted:
                continue
            try:
                callback(change)
            except Exception:
                logger.exception("session observer %r failed on %s", callback, change.event)

    def _set_dirty(self, value: bool, *, name_changed: bool = False) -> None:
        flipped = self.dirty != value
        self.dirty = value
        if flipped or name_changed:
            self._emit(Change(SessionEvent.DIRTY_CHANGED))

    def _changed(self, part: str) -> None:
        """The project changed in place: mark it dirty and say what changed."""
        flipped = not self.dirty
        self.dirty = True
        self._emit(Change(SessionEvent.PROJECT_CHANGED, part=part))
        if flipped:
            self._emit(Change(SessionEvent.DIRTY_CHANGED))

    def _replaced(self, project: AERMODProject, *, path: Optional[Path],
                  name: Optional[str]) -> None:
        # Policy (WP-G4): replacing the project stops its run. The run's
        # outputs belong to the discarded project, and its record would go
        # with the discarded history.
        self._abandon_run()
        was_dirty, old_name = self.dirty, self.file_name
        self.project = project
        self.project_path = path
        self.file_name = name
        self.dirty = False
        self.runs = []
        self.validation = None
        self._keys.clear()
        self._emit(Change(SessionEvent.PROJECT_REPLACED))
        if was_dirty or old_name != name:
            self._emit(Change(SessionEvent.DIRTY_CHANGED))

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------
    def _key_for(self, obj: object) -> str:
        entry = self._keys.get(id(obj))
        if entry is not None and entry[1] is obj:
            return entry[0]
        return self._assign_key(obj)

    def _assign_key(self, obj: object, key: Optional[str] = None) -> str:
        if key is None:
            prefix = "s" if hasattr(obj, "source_id") else "r"
            key = f"{prefix}{self._next_key}"
            self._next_key += 1
        self._keys[id(obj)] = (key, obj)
        return key

    def _prune(self) -> None:
        live = {id(s) for s in self.project.sources.sources}
        for attr in _RECEPTOR_LISTS.values():
            live.update(id(r) for r in getattr(self.project.receptors, attr))
        for stale in [i for i in self._keys if i not in live]:
            del self._keys[stale]

    def _locate(self, key: str, lists: Iterable[List[Any]]) -> Optional[Tuple[List[Any], int]]:
        for lst in lists:
            for i, item in enumerate(lst):
                entry = self._keys.get(id(item))
                if entry is not None and entry[1] is item and entry[0] == key:
                    return lst, i
        return None

    def _receptor_lists(self) -> List[List[Any]]:
        return [getattr(self.project.receptors, attr) for attr in _RECEPTOR_LISTS.values()]

    # ------------------------------------------------------------------
    # Project files
    # ------------------------------------------------------------------
    def new(self) -> None:
        """Discard the project and start from the blank one."""
        self._replaced(_empty_project(), path=None, name=None)

    def open_json(self, source: Union[str, bytes, Path], *, name: Optional[str] = None) -> None:
        """Replace the project with one read from a file or its text.

        A :class:`~pathlib.Path` is read from the server's disk and becomes
        :attr:`project_path`; text or bytes (an upload) sets only
        :attr:`file_name`, to ``name``. Nothing changes if the file cannot
        be read: :class:`ProjectFileError` says why.
        """
        if isinstance(source, Path):
            origin = str(source)
            path: Optional[Path] = source
            file_name: Optional[str] = source.name
        else:
            origin = name or "<text>"
            path, file_name = None, name
        try:
            data = source.read_bytes() if isinstance(source, Path) else source
            project = project_from_json(data, origin=origin)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
            # project_from_json raises ValueError for every problem with the
            # file; the others are a second line of defence behind its
            # checks, so they are bugs: keep the traceback in the log.
            if not isinstance(exc, (OSError, ValueError)):
                logger.exception("Reading project file %s raised", origin)
            message = str(exc)
            if not message.startswith(origin):
                message = f"{origin}: {message}"
            raise ProjectFileError(message) from exc
        self._replaced(project, path=path, name=file_name)

    def save(self) -> Path:
        """Write the project to :attr:`project_path` and mark it saved.

        Every save method raises :class:`ValueError` (nothing written, the
        project stays dirty) when the project holds a value the file could
        not be reopened with; see :func:`~.project_io.project_to_json`.
        """
        if self.project_path is None:
            raise ValueError("the project has no file on disk yet; use save_as")
        save_project(self.project, self.project_path)
        self._set_dirty(False)
        return self.project_path

    def save_as(self, path: Union[str, Path]) -> Path:
        """Write the project to ``path`` (desktop mode) and remember it."""
        target = Path(path)
        save_project(self.project, target)
        old_name = self.file_name
        self.project_path = target
        self.file_name = target.name
        self._set_dirty(False, name_changed=old_name != self.file_name)
        return target

    def save_as_download(self, file_name: Optional[str]) -> bytes:
        """The project file's bytes, to deliver as a browser download.

        Writes nothing to disk. The cleaned name (:func:`clean_file_name`)
        becomes :attr:`file_name`, and :attr:`project_path` is cleared: the
        browser decides where the file goes.
        """
        name = clean_file_name(file_name)
        data = project_to_json(self.project).encode("utf-8")
        old_name = self.file_name
        self.file_name = name
        self.project_path = None
        self._set_dirty(False, name_changed=old_name != name)
        return data

    # ------------------------------------------------------------------
    # Sources and receptors
    # ------------------------------------------------------------------
    def add_source(self, src: Any) -> str:
        """Append ``src`` and return its key. Duplicate ``source_id`` is allowed."""
        self.project.sources.sources.append(src)
        key = self._assign_key(src)
        self._changed("sources")
        return key

    def update_source(self, key: str, src: Any) -> bool:
        """Replace the source that has ``key``; False if it no longer exists."""
        found = self._locate(key, [self.project.sources.sources])
        if found is None:
            return False
        lst, i = found
        self._keys.pop(id(lst[i]), None)
        lst[i] = src
        self._assign_key(src, key)
        self._changed("sources")
        return True

    def delete_source(self, key: str) -> Optional[Any]:
        """Remove and return the source that has ``key``; None if it is gone."""
        found = self._locate(key, [self.project.sources.sources])
        if found is None:
            return None
        lst, i = found
        removed = lst.pop(i)
        self._keys.pop(id(removed), None)
        self._changed("sources")
        return removed

    def add_receptor(self, rec: Any) -> str:
        """Append ``rec`` to the list for its type and return its key."""
        attr = _RECEPTOR_LISTS.get(type(rec).__name__)
        if attr is None:
            raise TypeError(f"not a receptor type: {type(rec).__name__}")
        getattr(self.project.receptors, attr).append(rec)
        key = self._assign_key(rec)
        self._changed("receptors")
        return key

    def update_receptor(self, key: str, rec: Any) -> bool:
        """Replace the receptor that has ``key`` with one of the same type."""
        found = self._locate(key, self._receptor_lists())
        if found is None:
            return False
        lst, i = found
        if type(lst[i]).__name__ != type(rec).__name__:
            raise TypeError(
                f"cannot replace a {type(lst[i]).__name__} with a {type(rec).__name__}"
            )
        self._keys.pop(id(lst[i]), None)
        lst[i] = rec
        self._assign_key(rec, key)
        self._changed("receptors")
        return True

    def delete_receptor(self, key: str) -> Optional[Any]:
        """Remove and return the receptor that has ``key``; None if it is gone."""
        found = self._locate(key, self._receptor_lists())
        if found is None:
            return None
        lst, i = found
        removed = lst.pop(i)
        self._keys.pop(id(removed), None)
        self._changed("receptors")
        return removed

    # ------------------------------------------------------------------
    # In-place edits
    # ------------------------------------------------------------------
    def set_control(self, **fields: Any) -> None:
        """Set fields of the project's ControlPathway (titles, pollutant, ...)."""
        known = {f.name for f in dataclasses.fields(ControlPathway)}
        unknown = sorted(set(fields) - known)
        if unknown:
            raise AttributeError(f"ControlPathway has no field(s) {', '.join(unknown)}")
        control = self.project.control
        if all(getattr(control, k) == v for k, v in fields.items()):
            return
        for k, v in fields.items():
            setattr(control, k, v)
        self._changed("control")

    def mark_edited(self, part: str) -> None:
        """Record an edit a widget made in place (Meteorology, Output)."""
        if part not in PARTS:
            raise ValueError(f"unknown project part {part!r}; expected one of {PARTS}")
        self._changed(part)

    def validate(self, check_files: bool = False) -> ValidationResult:
        """Validate the project, keep the result and emit VALIDATION_CHANGED."""
        from ..validator import Validator

        self.validation = Validator.validate(self.project, check_files=check_files)
        self._emit(Change(SessionEvent.VALIDATION_CHANGED))
        return self.validation

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------
    def deck_text(self) -> str:
        """The AERMOD deck :meth:`start_run` would write for the project.

        Written from the project as a file would reopen it: a value the
        loader refuses is refused here by name, and whole numbers the number
        boxes stored as floats are integers again. Raises
        :class:`DeckError` when the project cannot be written as a deck.
        Emits nothing, so a page section may call it.
        """
        try:
            deck_project = check_project(self.project, origin="deck")
            return deck_project.to_aermod_input(validate=False)
        except ValueError as exc:
            raise DeckError(str(exc).removeprefix("deck: ")) from exc
        except Exception as exc:
            # Anything else is a bug in the deck writer or the check.
            logger.exception("Writing the deck raised")
            raise DeckError(str(exc) or type(exc).__name__) from exc

    def met_period(self, base_dir: Union[str, Path, None] = None,
                   ) -> Tuple[Optional[Path], Optional[SurfaceFilePeriod], Optional[str]]:
        """The surface file, the period it covers, and why it could not be read.

        ``(path, period, problem)``: ``path`` is the surface file resolved
        against ``base_dir`` (None when none is set), ``period`` the
        :class:`~pyaermod.aermet.SurfaceFilePeriod` it holds, and
        ``problem`` a sentence saying why it could not be read (then
        ``period`` is None). Reads are cached by the file's mtime. Emits
        nothing.
        """
        from ..validator_advanced import surface_file_path

        path = surface_file_path(self.project.meteorology, base_dir)
        if path is None:
            return None, None, None
        try:
            return path, read_met_period(path), None
        except FileNotFoundError:
            return path, None, f"{path} does not exist"
        except IsADirectoryError:
            return path, None, f"{path} is a directory, not a surface file"
        except (OSError, ValueError) as exc:
            return path, None, f"{path} could not be read: {exc}"

    def start_run(self, *, working_dir: Union[str, Path, None] = None, timeout: int = 600,
                  runner: Optional[AERMODRunner] = None,
                  background: bool = False) -> RunRecord:
        """Write the deck, run AERMOD on it, and record the run.

        Raises :class:`RunInProgressError` while another run is in progress
        (nothing written, nothing emitted), :class:`DeckError` (nothing
        recorded, nothing emitted) when the project cannot be written as a
        deck (see :meth:`deck_text`), and ``OSError`` when the deck cannot
        be written to the working directory. Anything the runner raises,
        including a missing binary, is kept on the record as ``error``.

        With ``background=False`` the run is synchronous: RUN_STARTED, then
        RUN_FINISHED, and the finished record is returned.

        With ``background=True`` AERMOD runs through
        :meth:`AERMODRunner.start <pyaermod.runner.AERMODRunner.start>` and
        this returns the record in progress (:attr:`run_in_progress`) after
        RUN_STARTED. RUN_PROGRESS follows for each day AERMOD reports (a
        burst is coalesced into one event), then RUN_FINISHED, all
        delivered through :attr:`dispatch`. :meth:`cancel_run` stops it. A
        runner that cannot be built or started finishes the run at once,
        as a synchronous run would.
        """
        if self.run_in_progress is not None:
            raise RunInProgressError(
                f"AERMOD is already running (run {self.run_in_progress.number})")
        deck = self.deck_text()

        if working_dir is not None and str(working_dir).strip():
            wd = Path(working_dir).expanduser()
        else:
            wd = Path(tempfile.mkdtemp(prefix="pyaermod_"))
        wd.mkdir(parents=True, exist_ok=True)
        deck_path = wd / DECK_NAME
        deck_path.write_text(deck, encoding="utf-8")

        record = RunRecord(number=len(self.runs) + 1, work_dir=wd, deck_path=deck_path,
                           started_at=datetime.now(), expected_days=self._expected_days(wd))
        self._run_serial += 1
        serial = self._run_serial
        self.run_in_progress = record
        self._emit(Change(SessionEvent.RUN_STARTED, run=record))

        try:
            if runner is None:
                from ..runner import AERMODRunner

                runner = AERMODRunner(log_level="WARNING")
            if not background:
                result = runner.run(input_file=deck_path, working_dir=wd, timeout=timeout)
                return self._finish_run(serial, result=result)
            handle = runner.start(
                input_file=deck_path, working_dir=wd, timeout=timeout,
                on_progress=lambda progress: self._progress_arrived(serial, progress),
                on_finish=lambda result: self._dispatch(
                    lambda: self._finish_run(serial, result=result)),
            )
        except FileNotFoundError as exc:
            # No AERMOD binary, or a file it needs: the user's setup, and the
            # Run step says so. Logged without a traceback.
            logger.warning("AERMOD run %d could not start: %s", record.number, exc)
            return self._finish_run(serial, error=str(exc) or type(exc).__name__)
        except Exception as exc:
            # Anything else is a bug: keep the traceback in the log, and show
            # the message on the Run step.
            logger.exception("AERMOD run %d raised", record.number)
            return self._finish_run(serial, error=str(exc) or type(exc).__name__)
        if self._run_serial == serial and self.run_in_progress is not None:
            self._run_handle = handle
            return self.run_in_progress
        # It ended already (a dispatch that calls at once, and a quick failure).
        return self.runs[-1] if self.runs and self.runs[-1].number == record.number else record

    def cancel_run(self) -> bool:
        """Stop the background run in progress.

        Returns True when a cancel was sent: RUN_FINISHED follows once
        AERMOD has exited, with a record whose status is "Cancelled".
        False when nothing is running, the run was already cancelled, or
        the run is synchronous (it cannot be interrupted).
        """
        if self.run_in_progress is None or self._run_handle is None:
            return False
        return self._run_handle.cancel()

    def _expected_days(self, work_dir: Path) -> Optional[int]:
        """How many "Day No." lines AERMOD will print: the days of met data it reads."""
        _path, period, _problem = self.met_period(work_dir)
        if period is None:
            return None
        from ..validator_advanced import _startend_window

        window = _startend_window(self.project.meteorology)
        if window is None:
            return period.days
        first, last = max(period.first, window[0]), min(period.last, window[1])
        if last <= first:
            return None
        return (last - timedelta(hours=1)).date().toordinal() - first.date().toordinal() + 1

    def _dispatch(self, callback: Callable[[], object]) -> None:
        try:
            self.dispatch(callback)
        except RuntimeError as exc:         # the event loop has closed: the app is stopping
            logger.debug("dropped a run event: %s", exc)

    def _progress_arrived(self, serial: int, progress: AERMODProgress) -> None:
        """From the run's reader thread: apply ``progress`` on the owner's thread."""
        with self._progress_lock:
            already = self._pending_progress is not None
            self._pending_progress = (serial, progress)
        if not already:
            self._dispatch(self._apply_progress)

    def _apply_progress(self) -> None:
        with self._progress_lock:
            pending, self._pending_progress = self._pending_progress, None
        record = self.run_in_progress
        if pending is None or record is None or pending[0] != self._run_serial:
            return
        self.run_in_progress = replace(record, progress=pending[1])
        self._emit(Change(SessionEvent.RUN_PROGRESS, run=self.run_in_progress))

    def _finish_run(self, serial: int, *, result: Optional[AERMODRunResult] = None,
                    error: Optional[str] = None) -> RunRecord:
        """Record the end of run ``serial`` and emit RUN_FINISHED.

        A run that is no longer the one in progress (New or Open replaced
        the project and stopped it) is dropped without an event.
        """
        record = self.run_in_progress
        if record is None or serial != self._run_serial:
            if result is not None:
                logger.info("A stopped run of a replaced project ended: %s", result)
            return replace(record or _orphan_record(result), finished_at=datetime.now(),
                           result=result, error=error)
        handle, self._run_handle = self._run_handle, None
        progress = record.progress
        if handle is not None and handle.progress is not None:
            progress = handle.progress
        finished = replace(record, finished_at=datetime.now(), result=result, error=error,
                           progress=progress)
        self.runs.append(finished)
        self.run_in_progress = None
        self._emit(Change(SessionEvent.RUN_FINISHED, run=finished))
        return finished

    def _abandon_run(self) -> None:
        """Stop the run in progress without recording it (the project is going)."""
        handle, self._run_handle = self._run_handle, None
        if self.run_in_progress is None:
            return
        logger.info("Stopping AERMOD run %d: the project was replaced",
                    self.run_in_progress.number)
        self.run_in_progress = None
        self._run_serial += 1               # its finish no longer matches
        if handle is not None:
            handle.cancel()

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    def fork(self, tab_id: Optional[str]) -> Session:
        """An independent copy for another tab: same content and runs, no observers."""
        other = type(self)(copy.deepcopy(self.project), tab_id=tab_id)
        other.project_path = self.project_path
        other.file_name = self.file_name
        other.dirty = self.dirty
        other.validation = self.validation
        other.runs = list(self.runs)
        other.run_options = replace(self.run_options)
        return other


__all__ = [
    "DECK_NAME",
    "PARTS",
    "Change",
    "DeckError",
    "ProjectFileError",
    "RunInProgressError",
    "RunOptions",
    "RunRecord",
    "Session",
    "SessionEvent",
    "clean_file_name",
    "read_met_period",
]

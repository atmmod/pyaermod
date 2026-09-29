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
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
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
from .project_io import project_from_json, project_to_json, save_project
from .state import _empty_project

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..runner import AERMODRunner, AERMODRunResult
    from ..validator import ValidationResult

logger = logging.getLogger(__name__)


class SessionEvent(StrEnum):
    """What changed in a :class:`Session`."""

    PROJECT_REPLACED = "project_replaced"      # new(), open_json()
    PROJECT_CHANGED = "project_changed"        # any in-place change; Change.part names what
    DIRTY_CHANGED = "dirty_changed"            # the dirty flag or the file name changed
    VALIDATION_CHANGED = "validation_changed"  # validate()
    RUN_STARTED = "run_started"
    RUN_PROGRESS = "run_progress"              # reserved; emitted from WP-G4 on
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

    @property
    def in_progress(self) -> bool:
        return self.finished_at is None

    @property
    def success(self) -> bool:
        return self.result is not None and bool(self.result.success)


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


Observer = Callable[[Change], None]


def clean_file_name(name: Optional[str]) -> str:
    """The file name a download is offered under.

    Any directory part is dropped (POSIX or Windows spelling), an empty
    name becomes ``project.json`` and a name without a ``.json`` suffix
    gets one.
    """
    base = PureWindowsPath(PurePosixPath(name or "").name).name.strip()
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
        self._observers: List[Tuple[frozenset, Observer]] = []
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
        """The newest run AERMOD actually completed (it has a result)."""
        for record in reversed(self.runs):
            if record.result is not None:
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
            text = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
            project = project_from_json(text, origin=origin)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            # UnicodeDecodeError is a ValueError. AttributeError and
            # TypeError are a second line of defence behind the shape
            # checks in project_from_json.
            message = str(exc)
            if not message.startswith(origin):
                message = f"{origin}: {message}"
            raise ProjectFileError(message) from exc
        self._replaced(project, path=path, name=file_name)

    def save(self) -> Path:
        """Write the project to :attr:`project_path` and mark it saved."""
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
    def start_run(self, *, working_dir: Union[str, Path, None] = None, timeout: int = 600,
                  runner: Optional[AERMODRunner] = None) -> RunRecord:
        """Write the deck, run AERMOD on it, and record the run.

        Raises :class:`DeckError` (nothing recorded, nothing emitted) when
        the project cannot be written as a deck, and ``OSError`` when the
        deck cannot be written to the working directory. Anything the
        runner raises, including a missing binary, is kept on the record
        as ``error``. Emits RUN_STARTED and then RUN_FINISHED.

        The run is synchronous; WP-G4 moves it to the background.
        """
        try:
            deck = self.project.to_aermod_input(validate=False)
        except Exception as exc:
            raise DeckError(str(exc)) from exc

        if working_dir is not None and str(working_dir).strip():
            wd = Path(working_dir).expanduser()
        else:
            wd = Path(tempfile.mkdtemp(prefix="pyaermod_"))
        wd.mkdir(parents=True, exist_ok=True)
        deck_path = wd / DECK_NAME
        deck_path.write_text(deck, encoding="utf-8")

        record = RunRecord(number=len(self.runs) + 1, work_dir=wd, deck_path=deck_path,
                           started_at=datetime.now())
        self.run_in_progress = record
        self._emit(Change(SessionEvent.RUN_STARTED, run=record))

        result: Optional[AERMODRunResult] = None
        error: Optional[str] = None
        try:
            if runner is None:
                from ..runner import AERMODRunner

                runner = AERMODRunner(log_level="WARNING")
            result = runner.run(input_file=deck_path, working_dir=wd, timeout=timeout)
        except Exception as exc:
            error = str(exc) or type(exc).__name__

        finished = replace(record, finished_at=datetime.now(), result=result, error=error)
        self.runs.append(finished)
        self.run_in_progress = None
        self._emit(Change(SessionEvent.RUN_FINISHED, run=finished))
        return finished

    def cancel_run(self) -> bool:
        """Stop the run in progress. False when nothing is running.

        Runs are synchronous until WP-G4, which implements cancelling.
        """
        if self.run_in_progress is None:
            return False
        raise NotImplementedError("cancelling arrives with WP-G4")

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
    "RunOptions",
    "RunRecord",
    "Session",
    "SessionEvent",
    "clean_file_name",
]

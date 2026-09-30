"""
Import and files: deck import, met file pickers and the recent-files list.

The Project step calls :func:`import_controls` once; it builds

* **Import deck...**, which imports an AERMOD ``.inp`` deck through
  :meth:`Session.import_inp <pyaermod.gui_v2.session.Session.import_inp>`.
  In a browser the deck is uploaded and read in a sandbox (it may name
  only files beside itself); in ``pyaermod-desktop`` a native dialog
  picks a file on this computer, which is read as it stands;
* a **Deck file path** field, which imports a deck on this computer by
  its path, in either mode;
* the **import notice**: the lines of the deck PyAERMOD keeps as written
  (``unparsed_lines``), and pickers for the met files the deck names
  that are not yet found;
* **Recent files**: projects opened or saved and decks imported through a
  path on this computer, newest first, each one reopened by a click.

:func:`met_file_input` is the met file picker: a path field that says
when the file does not exist, with a **Browse...** button opening a
native dialog in desktop mode. The Meteorology step can place it too.

The recent-files list is kept per user of this computer, in
``~/.pyaermod/recent_files.json`` (``$PYAERMOD_RECENT_FILES`` overrides
the location). Only paths on this computer are listed: an upload or a
browser download has none.

NiceGUI is imported inside the functions, so importing this module does
not import NiceGUI.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import _native
from ._live import live
from .session import (
    MET_FILE_FIELDS,
    DeckImport,
    DeckImportError,
    ProjectFileError,
    Session,
    SessionEvent,
)

logger = logging.getLogger(__name__)

#: Overrides where the recent-files list is kept.
RECENT_FILES_ENV = "PYAERMOD_RECENT_FILES"

#: How many recent files are listed.
MAX_RECENT = 10

#: The kinds of file the recent-files list holds.
PROJECT, DECK = "project", "deck"

#: What the native dialogs offer, in pywebview's "Description (*.ext)" form.
DECK_FILE_TYPES = ("AERMOD input (*.inp;*.INP)", "All files (*.*)")
MET_FILE_TYPES: Dict[str, Tuple[str, ...]] = {
    "surface_file": ("Surface met file (*.sfc;*.SFC)", "All files (*.*)"),
    "profile_file": ("Profile met file (*.pfl;*.PFL)", "All files (*.*)"),
}

# pywebview's value for an open dialog, for versions without FileDialog.
_OPEN_DIALOG_FALLBACK = 10

#: How many kept-as-written lines the notice lists before summarising.
_MAX_LINES_SHOWN = 200


# ---------------------------------------------------------------------------
# Checks and native dialogs (no UI)
# ---------------------------------------------------------------------------

def file_problem(value: Optional[str]) -> Optional[str]:
    """Why ``value`` is not a file this computer can open, or None if it is.

    An empty value is not a problem here (the readiness checks say a file
    is missing). A relative path is: AERMOD would look for it in the run's
    working directory, not where the user thinks.
    """
    text = (value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        return "Give the full path: a relative one is read from the run's working directory"
    if not path.exists():
        return "No such file on this computer"
    if not path.is_file():
        return "This is a folder, not a file"
    return None


def _open_dialog_kind() -> Any:
    try:
        import webview

        return webview.FileDialog.OPEN
    except (ImportError, AttributeError):
        return _OPEN_DIALOG_FALLBACK


def ask_open_path(file_types: Sequence[str]) -> Optional[Path]:
    """Ask for a file to open through the desktop window; None if cancelled.

    Blocks until the dialog closes, so call it through ``run.io_bound``.
    """
    window = _native.native_window()
    if window is None:
        raise RuntimeError("no desktop window; ask_open_path is for pyaermod-desktop")
    result = window.create_file_dialog(
        _open_dialog_kind(), allow_multiple=False, file_types=tuple(file_types),
    )
    # pywebview returns a tuple of paths; some backends return one string.
    if isinstance(result, (list, tuple)):
        result = result[0] if result else None
    return Path(result) if result else None


# ---------------------------------------------------------------------------
# Recent files (no UI)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecentFile:
    """One entry of the recent-files list: a file on this computer."""

    path: Path
    kind: str                    # PROJECT or DECK

    @property
    def exists(self) -> bool:
        return self.path.is_file()


def recent_files_path() -> Path:
    """Where the recent-files list is kept (``$PYAERMOD_RECENT_FILES`` first)."""
    override = os.environ.get(RECENT_FILES_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".pyaermod" / "recent_files.json"


def load_recent() -> List[RecentFile]:
    """The recent files, newest first; an unreadable list reads as empty."""
    store = recent_files_path()
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring the recent-files list %s: %s", store, exc)
        return []
    entries: List[RecentFile] = []
    rows = data.get("files") if isinstance(data, dict) else None
    for row in rows if isinstance(rows, list) else []:
        if (isinstance(row, dict) and isinstance(row.get("path"), str)
                and row.get("kind") in (PROJECT, DECK)):
            entries.append(RecentFile(Path(row["path"]), row["kind"]))
    return entries[:MAX_RECENT]


def _write_recent(entries: List[RecentFile]) -> None:
    store = recent_files_path()
    payload = {"version": 1,
               "files": [{"path": str(e.path), "kind": e.kind} for e in entries]}
    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        # Beside the target, then moved over it: a failed write leaves the
        # earlier list whole.
        fd, tmp = tempfile.mkstemp(dir=store.parent, prefix=".recent_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp, store)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        # The list is a convenience: failing to keep it must not fail the
        # open or save that asked for it.
        logger.warning("Could not update the recent-files list %s: %s", store, exc)


def _same_file(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def remember(path: Path, kind: str) -> List[RecentFile]:
    """Put ``path`` at the top of the recent-files list; return the list."""
    if kind not in (PROJECT, DECK):
        raise ValueError(f"unknown kind of recent file {kind!r}")
    entry = RecentFile(Path(os.path.abspath(path)), kind)
    entries = [entry] + [e for e in load_recent() if not _same_file(e.path, entry.path)]
    entries = entries[:MAX_RECENT]
    _write_recent(entries)
    return entries


def forget(path: Path) -> List[RecentFile]:
    """Remove ``path`` from the recent-files list; return the list."""
    entries = [e for e in load_recent() if not _same_file(e.path, path)]
    _write_recent(entries)
    return entries


# ---------------------------------------------------------------------------
# UI builders
# ---------------------------------------------------------------------------

def _notify(msg: str, *, color: str = "positive") -> None:
    """``ui.notify``; a failure stays until closed, so a long reason can be read."""
    from nicegui import ui

    if color == "negative":
        ui.notify(msg, color=color, multi_line=True, timeout=0, close_button="Close")
    else:
        ui.notify(msg, color=color)


def imported_message(report: DeckImport) -> str:
    """The notification after an import."""
    return f"Imported {report.name}"


def met_file_input(session: Session, field_name: str, *, label: str) -> Any:
    """A path field for one met file of the project, and in desktop mode Browse...

    The field edits ``session.project.meteorology.<field_name>`` and says
    under itself when the path is not a file on this computer. Build it
    only inside a section rebuilt when the project is replaced
    (:func:`~pyaermod.gui_v2._live.live`), since it is bound to the
    project's meteorology. Returns the input.
    """
    from nicegui import run, ui

    met = session.project.meteorology
    kind = dict(MET_FILE_FIELDS).get(field_name, field_name)

    def edited() -> None:
        session.mark_edited("meteorology")

    with ui.row().classes("w-full items-center no-wrap"):
        field = ui.input(label, validation=file_problem).classes("col-grow").bind_value(
            met, field_name)
        field.on_value_change(lambda _e: edited())
        field.validate()
        if _native.native_window() is not None:
            async def browse() -> None:
                path = await run.io_bound(
                    ask_open_path, MET_FILE_TYPES.get(field_name, ("All files (*.*)",)))
                if path is None:
                    return                          # the user cancelled
                field.value = str(path)             # the binding writes it back

            ui.button("Browse...", on_click=browse).props(
                f'flat aria-label="Browse for the {kind} met file"').mark(f"browse-{field_name}")
    return field


def import_controls(session: Session, *, dialogs: Any = None,
                    goto: Optional[Callable[[str], None]] = None) -> None:
    """Build the deck import controls, the import notice and the recent files.

    Call it once per page, outside any live section. ``dialogs`` is the
    page's static dialog container (unused for now: nothing here opens a
    dialog). ``goto(step_id)`` sends the user to another step; when given,
    the notice links to the Meteorology step.
    """
    from nicegui import run, ui

    desktop = _native.native_window() is not None

    # ----- actions ------------------------------------------------------
    def _import_path(path: Path) -> bool:
        try:
            report = session.import_inp(path)
        except DeckImportError as exc:
            _notify(f"Import failed: {exc}", color="negative")
            return False
        remember(path, DECK)
        _recent.refresh()
        _notify(imported_message(report))
        return True

    async def _on_upload(e: Any) -> None:
        name = e.file.name
        try:
            # Read inside the handler: an upload over 1 MiB is a temporary
            # file that goes away with the event.
            data = await e.file.read()
            report = session.import_inp(data, name=name)
        except DeckImportError as exc:
            _notify(f"Import failed: {exc}", color="negative")
            return
        finally:
            # Always, so choosing the same deck again sends it again.
            uploader.reset()
        _notify(imported_message(report))

    async def _import_clicked() -> None:
        path = await run.io_bound(ask_open_path, DECK_FILE_TYPES)
        if path is not None:
            _import_path(path)

    def _read_typed_path() -> None:
        problem = file_problem(path_input.value)
        if not (path_input.value or "").strip() or problem:
            _notify(f"Import failed: {problem or 'give the path of a deck'}",
                    color="negative")
            return
        if _import_path(Path(path_input.value.strip()).expanduser()):
            path_input.value = ""

    def _reopen(entry: RecentFile) -> None:
        if not entry.exists:
            forget(entry.path)
            _recent.refresh()
            _notify(f"{entry.path.name} is no longer at {entry.path.parent}", color="negative")
            return
        if entry.kind == DECK:
            _import_path(entry.path)
            return
        try:
            session.open_json(entry.path)
        except ProjectFileError as exc:
            _notify(f"Load failed: {exc}", color="negative")
            return
        _notify(f"Loaded {entry.path.name}")

    # ----- import controls ----------------------------------------------
    ui.label("Import an AERMOD deck").classes("text-subtitle1")
    with ui.row().classes("w-full items-center q-gutter-md"):
        button = ui.button("Import deck...").mark("import-deck")
        if desktop:
            button.on_click(_import_clicked)
        path_input = ui.input(
            "Deck file path", validation=file_problem,
        ).props('hint="A deck on the computer running PyAERMOD"').classes("col-grow")
        path_input.on("keydown.enter", _read_typed_path)
        ui.button("Read deck", on_click=_read_typed_path).props("flat")
    uploader: Any = None
    if not desktop:
        # Hidden: the Import button opens its chooser. auto_upload sends the
        # deck as soon as it is chosen; no ``accept`` filter, because
        # QUploader drops a filtered-out file without any event.
        uploader = ui.upload(
            label="AERMOD deck (.inp)", auto_upload=True, max_files=1, on_upload=_on_upload,
        ).props("hide-upload-btn").classes("hidden").mark("import-upload")
        # The click opens the browser's file chooser in the browser itself,
        # so it still counts as the user's own action (a chooser opened
        # after a round trip to the server may be blocked).
        button.on("click", js_handler=f"() => runMethod({uploader.id}, 'pickFiles', [])")

    # ----- import notice --------------------------------------------------
    def _dismiss() -> None:
        session.show_import_notice = False
        _notice.refresh()

    @live(session)
    def _notice() -> None:
        report = session.last_import
        if report is None or not session.show_import_notice:
            return
        with ui.card().classes("w-full q-mt-md").props(
                'flat bordered role=region aria-label="Import notice"').mark("import-notice"):
            where = f" from {report.path.parent}" if report.path is not None else ""
            ui.label(f"Imported {report.name}{where}.").classes("text-subtitle2")
            if report.unparsed:
                _unparsed_notice(report)
            if report.met_found:
                found = ", ".join(dict(MET_FILE_FIELDS)[f] for f in report.met_found)
                ui.label(f"Found its {found} met file{'s' if len(report.met_found) > 1 else ''} "
                         "beside the deck.")
            if report.met_needed:
                _met_notice(session, report, goto)
            if report.inputs_found:
                ui.label("Found the other files it reads beside the deck: "
                         f"{_file_list(report.inputs_found)}.")
            if report.inputs_missing:
                _inputs_notice(report)
            ui.button("Dismiss", on_click=_dismiss).props("flat")

    # ----- recent files ---------------------------------------------------
    @ui.refreshable
    def _recent() -> None:
        entries = load_recent()
        if not entries:
            return
        ui.label("Recent files").classes("text-subtitle1 q-mt-md")
        with ui.column().classes("q-gutter-xs").props(
                'role=list aria-label="Recent files"').mark("recent-files"):
            for entry in entries:
                with ui.row().classes("items-center no-wrap").props("role=listitem"):
                    ui.button(entry.path.name, on_click=lambda _e, en=entry: _reopen(en)).props(
                        f'flat no-caps dense aria-label="Reopen {entry.path.name}"'
                    ).tooltip(str(entry.path))
                    kind = "project" if entry.kind == PROJECT else "AERMOD deck"
                    state = "" if entry.exists else ", missing"
                    ui.label(f"{kind}{state} · {entry.path.parent}").classes(
                        "text-caption text-grey-8")

    _recent()

    # A project opened or saved through a path (desktop Open and Save As,
    # a recent project) joins the list, whichever page did it.
    last = {"path": session.project_path}

    def _record(_change: Any) -> None:
        path = session.project_path
        if path is not None and path != last["path"]:
            remember(path, PROJECT)
            _recent.refresh()
        last["path"] = path

    ui.context.client.on_delete(session.subscribe(
        {SessionEvent.PROJECT_REPLACED, SessionEvent.DIRTY_CHANGED}, _record))


def _unparsed_notice(report: DeckImport) -> None:
    from nicegui import ui

    from ..unparsed import unparsed_summary

    count = len(report.unparsed)
    ui.label(
        f"{count} line{'s' if count != 1 else ''} of the deck "
        f"{'have' if count != 1 else 'has'} no field in PyAERMOD. "
        "They are kept as written and go back into the deck on every run and save, "
        "but no step shows or edits them. Check them before you run the deck:")
    with ui.column().classes("q-gutter-none q-ml-md"):
        for (pathway, keyword), n in unparsed_summary(report.unparsed).items():
            ui.label(f"{pathway} {keyword}: {n} line{'s' if n != 1 else ''}")
    with ui.expansion("Show the lines kept as written").classes("w-full"):
        shown = report.unparsed[:_MAX_LINES_SHOWN]
        text = "\n".join(f"line {u.lineno}: {u.raw.strip()}" for u in shown)
        if count > len(shown):
            text += f"\n... and {count - len(shown)} more"
        ui.label(text).classes("font-mono text-caption").style("white-space: pre-wrap")


def _met_notice(session: Session, report: DeckImport,
                goto: Optional[Callable[[str], None]]) -> None:
    from nicegui import ui

    labels = dict(MET_FILE_FIELDS)
    named = [f"{path} ({labels[f]})" for f, path in report.met_needed if path]
    if report.path is None:
        why = "An uploaded deck brings no met files."
    else:
        why = "They were not found beside the deck."
    names = f" The deck names {', '.join(named)}." if named else ""
    ui.label(f"Choose the deck's met files.{names} {why}")
    for field_name, _path in report.met_needed:
        kind = labels[field_name]
        met_file_input(session, field_name, label=f"{kind.capitalize()} met file (full path)")
    if goto is not None:
        ui.button("Go to Meteorology", on_click=lambda: goto("meteorology")).props("flat")


def _file_list(files_: Sequence[Tuple[str, str]]) -> str:
    """``path (KEYWORD), ...`` for the notice."""
    return ", ".join(f"{path} ({keyword})" for keyword, path in files_)


def _inputs_notice(report: DeckImport) -> None:
    from nicegui import ui

    upload = "An uploaded deck brings no files. " if report.path is None else ""
    ui.label(
        "The deck also reads files that are not on this computer as it names them: "
        f"{_file_list(report.inputs_missing)}. {upload}AERMOD reads a relative path "
        "from the run's working directory: put the files there, or give their full "
        "paths in the deck, before you run it.")


__all__ = [
    "DECK",
    "DECK_FILE_TYPES",
    "MAX_RECENT",
    "MET_FILE_TYPES",
    "PROJECT",
    "RECENT_FILES_ENV",
    "RecentFile",
    "ask_open_path",
    "file_problem",
    "forget",
    "import_controls",
    "imported_message",
    "load_recent",
    "met_file_input",
    "recent_files_path",
    "remember",
]

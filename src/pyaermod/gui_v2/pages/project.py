"""
Project tab — file menu (new / open / save / save as) + project metadata.

The file buttons act on the :class:`~pyaermod.gui_v2.session.Session`;
the metadata fields are a live section rebuilt whenever the project is
replaced, so they always show the project the session holds.

Files never pass through the server's disk in the browser: Open reads the
uploaded file's text, and Save As hands the browser a download. In
``pyaermod-desktop`` Save As asks where to save through a native dialog
and Save writes back to that file.
"""

from __future__ import annotations

from typing import Any

from ...input_generator import PollutantType
from .. import _native
from .._live import live
from ..session import ProjectFileError, Session


def render(session: Session, *, dialogs: Any) -> None:
    """Render the Project tab into the current NiceGUI panel.

    ``dialogs`` is the page's static dialog container; the Open and Save
    As dialogs are built there, after the button row, and live as long as
    the page.
    """
    from nicegui import run, ui

    # Built after the button row (below), used by its handlers.
    open_dialog: ui.dialog
    uploader: ui.upload
    save_as_dialog: ui.dialog
    name_input: ui.input

    def _on_new() -> None:
        session.new()
        _notify(f"New project. Title: {session.project.control.title_one!r}")

    async def _save_as_clicked() -> None:
        # async: NiceGUI awaits the handler inside its slot, so the UI calls
        # after the await (notify, open) still know their page.
        if _native.native_window() is not None:
            await _native_save_as()
            return
        name_input.value = session.suggested_file_name()
        save_as_dialog.open()

    async def _native_save_as() -> None:
        path = await run.io_bound(_native.ask_save_path, session.suggested_file_name())
        if path is None:
            return                                  # the user cancelled
        try:
            session.save_as(path)
        except OSError as exc:
            _notify(f"Save failed: {exc}", color="negative")
            return
        _notify(f"Saved {path.name}")

    async def _on_save() -> None:
        if session.project_path is not None:
            try:
                session.save()
            except OSError as exc:
                _notify(f"Save failed: {exc}", color="negative")
                return
            _notify(f"Saved {session.project_path.name}")
        else:
            # Browser: the dialog opens pre-filled, never a silent second
            # download (the browser would save it as "name (1).json").
            await _save_as_clicked()

    with ui.row().classes("q-gutter-md items-center"):
        ui.button("New", on_click=_on_new).mark("project-new")
        ui.button("Open...", on_click=lambda: open_dialog.open()).mark("project-open")
        ui.button("Save", on_click=_on_save).mark("project-save")
        ui.button("Save as...", on_click=_save_as_clicked).mark("project-save-as")

    ui.separator().classes("q-my-md")

    ui.label("Project metadata").classes("text-subtitle1")

    @live(session)
    def _metadata() -> None:
        control = session.project.control
        with ui.row().classes("q-gutter-md"):
            ui.input(
                "Title (line 1)", value=control.title_one,
                on_change=lambda e: session.set_control(title_one=e.value),
            )
            ui.input(
                "Title (line 2)", value=control.title_two or "",
                on_change=lambda e: session.set_control(title_two=e.value or None),
            )
        current = _pollutant_name(control.pollutant_id)
        options = [p.value for p in PollutantType]
        if current not in options:
            # A pollutant AERMOD accepts but the enum does not list (TSP,
            # PB, NOX ... from an imported deck or a saved file) stays a
            # choice, so the select can show it.
            options.append(current)
        ui.select(
            options=options, label="Pollutant", value=current,
            on_change=lambda e: session.set_control(pollutant_id=_pollutant_value(e.value)),
        ).classes("w-48")

    # ----- Open ---------------------------------------------------------
    async def _on_upload(e) -> None:
        name = e.file.name
        try:
            # Read inside the handler: an upload over 1 MiB is a temporary
            # file that goes away with the event. Bytes, so that a file that
            # is not UTF-8 text is refused with its name like any other.
            data = await e.file.read()
            session.open_json(data, name=name)
        except ProjectFileError as exc:
            _notify(f"Load failed: {exc}", color="negative")
            return                                  # the dialog stays open
        finally:
            # Always, so choosing the same file again sends it again.
            uploader.reset()
        open_dialog.close()
        _notify(f"Loaded {name}")

    with dialogs, ui.dialog().mark("open-dialog") as open_dialog, ui.card():
        ui.label("Select project JSON")
        # auto_upload sends the file as soon as it is chosen; the header's
        # upload button (an unnamed icon) is hidden.
        uploader = ui.upload(
            label="Project file (.json)", auto_upload=True, max_files=1,
            on_upload=_on_upload,
        ).props("accept=.json hide-upload-btn")
        ui.button("Cancel", on_click=open_dialog.close).props("flat")

    # ----- Save As (browser) --------------------------------------------
    def _do_save() -> None:
        data = session.save_as_download(name_input.value)
        # Bytes, and looked up on ``ui`` at call time (the T1 harness
        # replaces ui.download).
        ui.download(data, session.file_name, "application/json")
        _notify(f"Saved {session.file_name}")
        save_as_dialog.close()

    with dialogs, ui.dialog().mark("save-as-dialog") as save_as_dialog, ui.card():
        ui.label("Save project as")
        name_input = ui.input("Filename", value=session.suggested_file_name())
        with ui.row():
            ui.button("Cancel", on_click=save_as_dialog.close).props("flat")
            ui.button("Save", on_click=_do_save).props("color=primary")


def _pollutant_name(pollutant: Any) -> str:
    """What the Pollutant select shows for ``control.pollutant_id``."""
    return pollutant.value if isinstance(pollutant, PollutantType) else str(pollutant)


def _pollutant_value(name: str) -> Any:
    """The ``pollutant_id`` for a choice: the enum member, or the text itself."""
    try:
        return PollutantType(name)
    except ValueError:
        return name


def _notify(msg: str, *, color: str = "positive") -> None:
    """Wrapper around ``ui.notify`` so unit tests can monkeypatch it."""
    from nicegui import ui
    ui.notify(msg, color=color)

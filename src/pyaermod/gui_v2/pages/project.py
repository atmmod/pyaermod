"""
Project tab — file menu (new / open / save / save as) + project metadata.

This is the only fully-rendered page in the v1.9-A scaffold; the
others are placeholder banners that get filled in by subsequent
work packages.
"""

from __future__ import annotations

from pathlib import Path

from ...input_generator import PollutantType
from ..project_io import load_project, save_project
from ..state import AppState


def render(state: AppState) -> None:
    """Render the Project tab into the current NiceGUI panel."""
    from nicegui import ui

    with ui.row().classes("q-gutter-md items-center"):
        ui.button("New",     on_click=lambda: _on_new(state))
        ui.button("Open...", on_click=lambda: _on_open(state))
        ui.button("Save",    on_click=lambda: _on_save(state))
        ui.button("Save as...", on_click=lambda: _on_save_as(state))

    ui.separator().classes("q-my-md")

    ui.label("Project metadata").classes("text-subtitle1")
    with ui.row().classes("q-gutter-md"):
        ui.input("Title (line 1)").bind_value(
            state.project.control, "title_one",
        ).on("update:model-value", lambda _: state.mark_dirty())
        ui.input("Title (line 2)").bind_value(
            state.project.control, "title_two",
        ).on("update:model-value", lambda _: state.mark_dirty())

    pollutants = [p.value for p in PollutantType]
    ui.select(
        options=pollutants, label="Pollutant",
        value=state.project.control.pollutant_id.value,
        on_change=lambda e: _set_pollutant(state, e.value),
    ).classes("w-48")


# ---------------------------------------------------------------------
# Handlers (also unit-testable in isolation)
# ---------------------------------------------------------------------

def _on_new(state: AppState) -> None:
    state.reset()
    _notify(f"New project. Title: {state.project.control.title_one!r}")


def _on_open(state: AppState) -> None:
    """Open a project from disk via a file picker dialog."""
    from nicegui import ui

    async def _pick() -> None:
        from nicegui.events import GenericEventArguments  # noqa: F401

        async def handle_upload(e) -> None:
            tmp = Path(e.name)
            text = e.content.read().decode("utf-8")
            path = tmp.with_suffix(".json")
            path.write_text(text, encoding="utf-8")
            try:
                state.project = load_project(path)
                state.project_path = path
                state.mark_clean()
                _notify(f"Loaded {path.name}")
            except Exception as exc:
                _notify(f"Load failed: {exc}", color="negative")
            dialog.close()

        with ui.dialog() as dialog, ui.card():
            ui.label("Select project JSON")
            ui.upload(
                on_upload=handle_upload, multiple=False,
            ).props("accept=.json")
            ui.button("Cancel", on_click=dialog.close).props("flat")
        dialog.open()

    ui.timer(0, _pick, once=True)


def _on_save(state: AppState) -> None:
    if state.project_path is None:
        _on_save_as(state)
        return
    save_project(state.project, state.project_path)
    state.mark_clean()
    _notify(f"Saved {state.project_path.name}")


def _on_save_as(state: AppState) -> None:
    """Prompt for a filename, save the project, and download it."""
    from nicegui import ui

    with ui.dialog() as dialog, ui.card():
        ui.label("Save project as")
        name_input = ui.input(
            "Filename", value=(state.project_path.name
                               if state.project_path else "project.json"),
        )

        def _do_save() -> None:
            target = Path("/tmp") / name_input.value
            save_project(state.project, target)
            state.project_path = target
            state.mark_clean()
            ui.download(str(target))
            _notify(f"Saved {target.name}")
            dialog.close()

        with ui.row():
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Save",   on_click=_do_save).props("color=primary")
    dialog.open()


def _set_pollutant(state: AppState, value: str) -> None:
    state.project.control.pollutant_id = PollutantType(value)
    state.mark_dirty()


def _notify(msg: str, *, color: str = "positive") -> None:
    """Wrapper around ``ui.notify`` so unit tests can monkeypatch it."""
    from nicegui import ui
    ui.notify(msg, color=color)

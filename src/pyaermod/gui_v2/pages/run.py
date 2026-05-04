"""Run tab — placeholder until v1.9-D."""

from __future__ import annotations

from ..state import AppState


def render(state: AppState) -> None:
    from nicegui import ui

    ui.label("Run AERMOD").classes("text-h6")
    last = state.last_run_dir
    last_str = str(last) if last is not None else "(no runs yet)"
    ui.label(
        f"This tab will be ported in v1.9-D. Last run dir: {last_str}."
    ).classes("text-body1 q-mt-sm")

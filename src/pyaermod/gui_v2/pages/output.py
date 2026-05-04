"""Output tab — placeholder until v1.9-D."""

from __future__ import annotations

from ..state import AppState


def render(state: AppState) -> None:
    from nicegui import ui

    ui.label("Output").classes("text-h6")
    ui.label(
        "This tab will be ported in v1.9-D."
    ).classes("text-body1 q-mt-sm")
    _ = state  # silence vulture

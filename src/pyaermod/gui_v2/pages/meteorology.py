"""Meteorology tab — placeholder until v1.9-C."""

from __future__ import annotations

from ..state import AppState


def render(state: AppState) -> None:
    from nicegui import ui

    ui.label("Meteorology").classes("text-h6")
    sf = state.project.meteorology.surface_file or "(unset)"
    pf = state.project.meteorology.profile_file or "(unset)"
    ui.label(
        f"This tab will be ported in v1.9-C. "
        f"Surface file: {sf}; Profile file: {pf}."
    ).classes("text-body1 q-mt-sm")

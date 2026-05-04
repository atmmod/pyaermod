"""Sources tab — fully built in v1.9-B. Currently a placeholder."""

from __future__ import annotations

from ..state import AppState


def render(state: AppState) -> None:
    from nicegui import ui

    ui.label("Sources").classes("text-h6")
    ui.label(
        f"This tab will be ported in v1.9-B. "
        f"Currently the project carries {len(state.project.sources.sources)} "
        f"source(s)."
    ).classes("text-body1 q-mt-sm")
    ui.markdown(
        "Use the legacy Streamlit GUI (`pyaermod-gui`) to edit sources "
        "until this page is implemented."
    ).classes("text-grey")

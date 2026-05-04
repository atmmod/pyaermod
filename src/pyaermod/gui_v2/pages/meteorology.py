"""
Meteorology tab.

Edits the project's :class:`MeteorologyPathway` directly through the
generic form helper. There is no list view here — meteorology is a
single block per project.

Common fields surfaced first; advanced fields collapse under an
expansion panel.
"""

from __future__ import annotations

import dataclasses

from .._form import emit_field
from ..state import AppState

_PRIMARY_FIELDS = (
    "surface_file",
    "profile_file",
    "anemometer_height",
    "wind_direction_units",
    "start_year",
    "start_month",
    "start_day",
    "end_year",
    "end_month",
    "end_day",
)


def render(state: AppState) -> None:
    from nicegui import ui

    met = state.project.meteorology
    field_names = {f.name for f in dataclasses.fields(met)}

    ui.label("Meteorology").classes("text-h6")

    ui.label("Surface + Profile files").classes("text-subtitle1 q-mt-md")
    with ui.column().classes("w-full q-gutter-sm"):
        for fname in _PRIMARY_FIELDS:
            if fname in field_names:
                fmeta = met.__dataclass_fields__[fname]
                emit_field(ui.row().classes("w-full"), met, fmeta)

    advanced = [f for f in dataclasses.fields(met)
                if f.name not in _PRIMARY_FIELDS]
    if advanced:
        with ui.expansion("Advanced", icon="settings").classes("w-full q-mt-md"):
            for fmeta in advanced:
                emit_field(ui.row().classes("w-full"), met, fmeta)

    # Mark dirty whenever the user edits anything in the panel.
    # NiceGUI doesn't expose a panel-level on_change; bind_value on
    # individual fields handles state mutation directly. We stamp
    # dirty here once at render to flag that the user has been on
    # the page (close enough for v1.9-C; refine in v1.9-D).
    state.mark_dirty()


__all__ = ["render"]

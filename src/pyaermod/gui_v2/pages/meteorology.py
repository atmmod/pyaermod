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
from typing import Any

from .._form import emit_field
from .._live import live
from ..session import Session

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


def render(session: Session, *, dialogs: Any = None) -> None:
    from nicegui import ui

    ui.label("Meteorology").classes("text-h6")

    def edited() -> None:
        session.mark_edited("meteorology")

    # The form edits the project's MeteorologyPathway in place, so it is
    # rebuilt whenever the project is replaced (and only then: rebuilding
    # on its own edits would pull the field from under the user's cursor).
    @live(session)
    def _form() -> None:
        met = session.project.meteorology
        field_names = {f.name for f in dataclasses.fields(met)}

        ui.label("Surface + Profile files").classes("text-subtitle1 q-mt-md")
        with ui.column().classes("w-full q-gutter-sm"):
            for fname in _PRIMARY_FIELDS:
                if fname in field_names:
                    fmeta = met.__dataclass_fields__[fname]
                    emit_field(ui.row().classes("w-full"), met, fmeta, on_change=edited)

        advanced = [f for f in dataclasses.fields(met)
                    if f.name not in _PRIMARY_FIELDS]
        if advanced:
            with ui.expansion("Advanced", icon="settings").classes("w-full q-mt-md"):
                for fmeta in advanced:
                    emit_field(ui.row().classes("w-full"), met, fmeta, on_change=edited)


__all__ = ["render"]

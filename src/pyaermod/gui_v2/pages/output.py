"""
Output tab.

Edits the project's :class:`OutputPathway` directly. Single-block
editor with primary-vs-advanced field grouping, mirroring the
Meteorology tab.
"""

from __future__ import annotations

import dataclasses

from .._form import emit_field
from ..state import AppState

_PRIMARY_FIELDS = (
    "summary_file",
    "max_file",
    "plot_file",
    "postfile",
    "postfile_format",
    "postfile_averaging",
    "output_type",
)


def render(state: AppState) -> None:
    from nicegui import ui

    out = state.project.output
    field_names = {f.name for f in dataclasses.fields(out)}

    ui.label("Output").classes("text-h6")
    ui.label("Files + format").classes("text-subtitle1 q-mt-md")
    with ui.column().classes("w-full q-gutter-sm"):
        for fname in _PRIMARY_FIELDS:
            if fname in field_names:
                emit_field(
                    ui.row().classes("w-full"), out,
                    out.__dataclass_fields__[fname],
                )

    advanced = [
        f for f in dataclasses.fields(out) if f.name not in _PRIMARY_FIELDS
    ]
    if advanced:
        with ui.expansion(
            "Advanced", icon="settings",
        ).classes("w-full q-mt-md"):
            for fmeta in advanced:
                emit_field(ui.row().classes("w-full"), out, fmeta)


__all__ = ["render"]

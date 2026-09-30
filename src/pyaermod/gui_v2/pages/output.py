"""
Output tab.

Edits the project's :class:`OutputPathway` directly. Single-block
editor with primary-vs-advanced field grouping, mirroring the
Meteorology tab.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .._form import emit_field
from .._live import live
from ..session import Session

_PRIMARY_FIELDS = (
    "summary_file",
    "plot_file",
    "postfile",
    "postfile_format",
    "postfile_averaging",
    "output_type",
)


def render(session: Session, *, dialogs: Any = None) -> None:
    from nicegui import ui

    ui.label("Output").classes("text-h6")

    def edited() -> None:
        session.mark_edited("output")

    # Rebuilt when the project is replaced; see pages/meteorology.py.
    @live(session)
    def _form() -> None:
        out = session.project.output
        field_names = {f.name for f in dataclasses.fields(out)}

        ui.label("Files + format").classes("text-subtitle1 q-mt-md")
        with ui.column().classes("w-full q-gutter-sm"):
            for fname in _PRIMARY_FIELDS:
                if fname in field_names:
                    emit_field(
                        ui.row().classes("w-full"), out,
                        out.__dataclass_fields__[fname], on_change=edited,
                    )

        advanced = [
            f for f in dataclasses.fields(out) if f.name not in _PRIMARY_FIELDS
        ]
        if advanced:
            with ui.expansion(
                "Advanced", icon="settings",
            ).classes("w-full q-mt-md"):
                for fmeta in advanced:
                    emit_field(ui.row().classes("w-full"), out, fmeta, on_change=edited)


__all__ = ["render"]

"""
Meteorology step.

Edits the project's :class:`MeteorologyPathway` in place through the
generic form helper, in groups: the two AERMET files, the stations
(mandatory for AERMOD), the period to model, and the rest under
"Advanced". There is no list here: meteorology is one block per project.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Set

from .._form import emit_fields
from .._layout import Goto, section, step_page
from .._live import live
from ..session import Session

#: The groups of the step, in order; every other field goes under "Advanced".
GROUPS = (
    ("Met files", "The surface and profile files AERMET wrote for the site.",
     ("surface_file", "profile_file")),
    ("Stations", "SURFDATA, UAIRDATA and PROFBASE: AERMOD checks these against the files.",
     ("surface_station_id", "upper_air_station_id", "data_start_year", "profile_base_elevation")),
    ("Period to model", "STARTEND: leave blank to model every hour of the files.",
     ("start_year", "start_month", "start_day", "start_hour",
      "end_year", "end_month", "end_day", "end_hour")),
)


def render(session: Session, *, dialogs: Any = None, goto: Optional[Goto] = None) -> None:
    from nicegui import ui

    del dialogs, goto

    def edited() -> None:
        session.mark_edited("meteorology")

    with step_page("Meteorology", "The AERMET files the run reads, and the stations "
                   "they came from."):
        # The form edits the project's MeteorologyPathway in place, so it is
        # rebuilt whenever the project is replaced (and only then: rebuilding
        # on its own edits would pull the field from under the user's cursor).
        @live(session)
        def _form() -> None:
            met = session.project.meteorology
            by_name = {f.name: f for f in dataclasses.fields(met)}
            grouped: Set[str] = set()
            for title, intro, names in GROUPS:
                with section(title, intro):
                    emit_fields(met, [by_name[n] for n in names if n in by_name],
                                on_change=edited)
                grouped.update(names)
            advanced = [f for f in dataclasses.fields(met) if f.name not in grouped]
            if advanced:
                with ui.expansion("Advanced", icon="settings").classes("w-full"):
                    emit_fields(met, advanced, on_change=edited)


__all__ = ["GROUPS", "render"]

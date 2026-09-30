"""
Meteorology step.

Edits the project's :class:`MeteorologyPathway` in place through the
generic form helper, in groups: the two AERMET files, the stations
(mandatory for AERMOD), the period to model, and the rest under
"Advanced". There is no list here: meteorology is one block per project.

Below the met files the step says what the surface file holds, as the
next run would read it (:meth:`Session.met_coverage`): the period it
covers, the station IDs and first year in its header, and the warning
that ANNUAL needs a full year of data (AERMOD's E480), with a link to the
Project step, whose averaging periods are the other way to fix it. The
section follows the validation that follows every change.
"""

from __future__ import annotations

import dataclasses
from typing import Any, List, Optional, Set

from ..._fields import help_of
from .. import files
from .._form import emit_fields, field_label
from .._layout import Goto, section, step_page
from .._live import live
from ..session import Session, SessionEvent

#: The met file fields, which WP-G6's checked pickers edit.
MET_FILES = ("surface_file", "profile_file")

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

    del dialogs

    def edited() -> None:
        session.mark_edited("meteorology")

    (files_title, files_intro, _names), *other_groups = GROUPS
    with step_page("Meteorology", "The AERMET files the run reads, and the stations "
                   "they came from."):
        with section(files_title, files_intro):
            # The pickers edit the project's MeteorologyPathway in place, so
            # they are rebuilt whenever the project is replaced (and only
            # then: rebuilding on their own edits would pull the field from
            # under the user's cursor).
            @live(session)
            def _files() -> None:
                by_name = {f.name: f for f in dataclasses.fields(session.project.meteorology)}
                _met_file_pickers(session, [by_name[n] for n in MET_FILES])

            # What the surface file holds: rebuilt after every validation,
            # which follows each change to the met files and the periods.
            @live(session, SessionEvent.VALIDATION_CHANGED)
            def _coverage() -> None:
                _surface_file_summary(ui, session, goto)

        @live(session)
        def _form() -> None:
            met = session.project.meteorology
            by_name = {f.name: f for f in dataclasses.fields(met)}
            grouped: Set[str] = set(MET_FILES)
            for title, intro, names in other_groups:
                with section(title, intro):
                    emit_fields(met, [by_name[n] for n in names if n in by_name],
                                on_change=edited)
                grouped.update(names)
            advanced = [f for f in dataclasses.fields(met) if f.name not in grouped]
            if advanced:
                with ui.expansion("Advanced", icon="settings").classes("w-full"):
                    emit_fields(met, advanced, on_change=edited)


def surface_file_text(session: Session) -> List[str]:
    """What the step says about the surface file the next run would read.

    ``[]`` when there is none to read (no file, or one AERMOD would not
    find, which the picker itself flags).
    """
    coverage = session.met_coverage()
    if coverage.problem is not None:
        # A file that is not there is the picker's to say.
        exists = coverage.path is not None and coverage.path.exists()
        return [f"The surface file {coverage.problem}."] if exists else []
    period = coverage.period
    if period is None:
        return []
    name = coverage.path.name if coverage.path is not None else "The surface file"
    lines = [f"{name} holds {period.describe()}."]
    stations = [f"{what} station {sid}" for what, sid in (
        ("surface", period.surface_station), ("upper-air", period.upper_air_station)) if sid]
    if stations:
        lines.append(f"Its header names {' and '.join(stations)}; its data start in "
                     f"{period.first_year}.")
    else:
        lines.append(f"Its data start in {period.first_year}.")
    return lines


def _surface_file_summary(ui: Any, session: Session, goto: Optional[Goto]) -> None:
    lines = surface_file_text(session)
    if not lines:
        return
    with ui.column().classes("q-gutter-xs q-mt-sm").mark("met-coverage"):
        for line in lines:
            ui.label(line).classes("text-body2")
        for warning in session.met_coverage().warnings:
            with ui.row().classes("items-start no-wrap q-gutter-sm"):
                ui.icon("warning").classes("text-warning").props('aria-hidden="true"')
                ui.label(warning.message).classes("text-body2 text-warning")
            if goto is not None:
                ui.button("Change the averaging periods on the Project step",
                          on_click=lambda: goto("project")).props("flat no-caps")


def _met_file_pickers(session: Session, fmetas: Any) -> None:
    """The met files as WP-G6's pickers: full-width path fields that say when
    the path is not a file on this computer (or is relative, or starts with
    ``~``), with Browse... in desktop mode. Labels and help come from the
    field metadata, as the form helper's do."""
    for fmeta in fmetas:
        field = files.met_file_input(session, fmeta.name, label=field_label(fmeta))
        text = help_of(fmeta)
        if text:
            field.props["hint"] = text


__all__ = ["GROUPS", "MET_FILES", "render", "surface_file_text"]

"""
Output step.

Edits the project's :class:`OutputPathway` in place, in groups: the files
the Results step reads (a plot file and a POSTFILE for every averaging
period, on by default), the tables in AERMOD's ``.out`` file, other
output files, and the rest under "Advanced". What AERMOD computes
(concentration, deposition) is a model option on the Project step; this
step shows it.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional

from ..._fields import help_of
from .._form import emit_fields
from .._layout import Goto, section, step_page
from .._live import live
from ..session import Session, SessionEvent

#: The file-name stem of the per-period plot files and POSTFILEs the GUI writes.
PERIOD_FILE_STEM = "pyaermod"

TABLE_FIELDS = ("receptor_table", "receptor_table_rank", "max_table", "max_table_rank",
                "day_table")
FILE_FIELDS = ("summary_file", "plot_file", "plot_file_averaging", "postfile",
               "postfile_averaging", "postfile_source_group", "postfile_format", "file_format")
#: Shown by the "Files for the Results step" group, not as text boxes.
RESULTS_FIELDS = ("period_plot_files", "period_postfiles")
#: Kept for older projects; the model options decide what AERMOD computes.
HIDDEN_FIELDS = ("output_type",)

_QUANTITIES = (("calculate_concentration", "CONC"), ("calculate_deposition", "DEPOS"),
               ("calculate_dry_deposition", "DDEP"), ("calculate_wet_deposition", "WDEP"))


def output_quantities(control: Any) -> str:
    """The MODELOPT output keywords the project asks for, e.g. ``"CONC DDEP"``."""
    return " ".join(token for attr, token in _QUANTITIES if getattr(control, attr, False))


def period_file_names(project: Any) -> str:
    """The names of the per-period files the project writes, for the Output step."""
    periods = project.control.averaging_periods
    out = project.output
    names = [*out.period_plot_file_names(periods).values(),
             *out.period_postfile_names(periods).values()]
    return f"Files: {', '.join(names)}" if names else "No per-period files."


def render(session: Session, *, dialogs: Any = None, goto: Optional[Goto] = None) -> None:
    from nicegui import ui

    del dialogs

    def edited() -> None:
        session.mark_edited("output")

    with step_page("Output", "What AERMOD writes: the files the Results step reads, the "
                   "tables in its .out file and any other output files."):

        @live(session, SessionEvent.PROJECT_CHANGED, parts={"control"})
        def _computed() -> None:
            control = session.project.control
            with ui.row().classes("items-center gap-2 w-full"):
                ui.input("Output quantities", value=output_quantities(control) or "none").props(
                    'readonly hint="Set by the model options on the Project step"').classes(
                    "w-full sm:w-80")
                if goto is not None:
                    ui.button("Change on the Project step", on_click=lambda: goto("project")
                              ).props("flat")

        with section("Files for the Results step",
                     "A plot file per averaging period is what the concentration map is "
                     "drawn from; a POSTFILE per period holds every averaged value."):

            # Rebuilt when the project is replaced; see pages/meteorology.py.
            @live(session)
            def _results_files() -> None:
                out = session.project.output
                by_name = {f.name: f for f in dataclasses.fields(out)}
                for name, label in (("period_plot_files", "Plot file for every averaging period"),
                                    ("period_postfiles", "POSTFILE for every averaging period")):
                    def toggle(e, name=name) -> None:
                        setattr(out, name, PERIOD_FILE_STEM if e.value else None)
                        edited()

                    box = ui.checkbox(label, value=bool(getattr(out, name)), on_change=toggle)
                    with box:
                        ui.tooltip(help_of(by_name[name]) or "")

            # The names follow the averaging periods and the two boxes above.
            @live(session, SessionEvent.PROJECT_CHANGED, parts={"control", "output"})
            def _names() -> None:
                ui.label(period_file_names(session.project)).classes("text-body2 text-grey-8")

            ui.label("POSTFILEs grow with receptors times hours: a year of 1-hour values "
                     "at 10,000 receptors is several gigabytes.").classes("text-body2 text-grey-8")

        @live(session)
        def _form() -> None:
            out = session.project.output
            by_name = {f.name: f for f in dataclasses.fields(out)}
            grouped = set(TABLE_FIELDS + FILE_FIELDS + RESULTS_FIELDS + HIDDEN_FIELDS)
            with section("Tables in the .out file"):
                emit_fields(out, [by_name[n] for n in TABLE_FIELDS if n in by_name],
                            on_change=edited)
            with section("Other output files",
                         "A name without a folder is written in the run's working directory; "
                         "a path with folders is relative to it, and AERMOD does not create "
                         "the folders."):
                emit_fields(out, [by_name[n] for n in FILE_FIELDS if n in by_name],
                            on_change=edited)
            advanced = [f for f in dataclasses.fields(out) if f.name not in grouped]
            if advanced:
                with ui.expansion("Advanced", icon="settings").classes("w-full"):
                    emit_fields(out, advanced, on_change=edited)


__all__ = ["PERIOD_FILE_STEM", "output_quantities", "period_file_names", "render"]

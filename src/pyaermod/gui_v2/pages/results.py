"""
Results step.

Shows one run of the session: by default the newest run AERMOD completed,
or an earlier one picked from the run history. The step says which run it
shows and whether it succeeded. A failed run's values are never shown: the
step names AERMOD's fatal errors and offers the deck and the ``.out`` file
for diagnosis, nothing else.

For a successful run it shows, from AERMOD's own summary tables:

- a card and a table row with the maximum of each averaging period and
  where it occurred (values as AERMOD printed them, with its calm and
  missing-hour flags explained);
- a concentration map drawn from the run's plot files;
- where the pollutant has a NAAQS, a comparison with it
  (:func:`~pyaermod.gui_v2.run_results.naaqs_checks`);
- every rank of every summary table;
- downloads of the deck, the ``.out`` file, the plot files and a KMZ.

What is shown comes from :func:`pyaermod.gui_v2.run_results.prepare`,
which reads a run's files once, in a thread of its own, when the run
finishes. Until the files are read the step says "Reading the results of
run N ..." and every tab stays usable; the section is rebuilt when the
view is ready, when a run starts or finishes, and on every page build (a
reload shows the last run again). New and Open clear the run history.

``goto(step)`` sends the user to another step (``"run"``, ``"output"``);
the shell wires it to its navigation.
"""

from __future__ import annotations

import asyncio
import base64
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .._live import live
from ..run_results import (
    FLAG_MEANINGS,
    PlotField,
    RunFile,
    RunView,
    StaleFileError,
    cached_view,
    completed_runs,
    overwritten_by,
    period_label,
    prepare,
    table_qualifier,
    watch,
)
from ..session import Session, SessionEvent

#: Shown when the session has no run AERMOD completed.
NO_RUN = "No run yet. Run AERMOD from the Review & Run step."

#: Shown while a finished run's files are being read.
READING = "Reading the results of run {number} ..."

_UNITS = {"ug/m^3": "µg/m³", "g/m^2": "g/m²", "g/m^2/yr": "g/m²/yr"}

_OUTPUT_TYPES = {"CONC": "Concentration", "DEPOS": "Total deposition",
                 "DDEP": "Dry deposition", "WDEP": "Wet deposition"}


def _no_goto(step: str) -> None:
    """The default ``goto``: the step list is the shell's (WP-G3)."""


def render(session: Session, *, dialogs: Any = None,
           goto: Callable[[str], None] = _no_goto) -> None:
    from nicegui import ui

    # Views are built when a run finishes, before a later run can
    # overwrite the files.
    ui.context.client.on_delete(watch(session))
    # The run the user picked from the history, and how many runs the
    # session had then: a new run shows itself again.
    picked: Dict[str, Optional[int]] = {"number": None, "runs": None}
    # The plot shown on the map, per run.
    map_choice: Dict[int, int] = {}
    # The runs whose view this page is waiting for.
    awaited: set = set()
    client = ui.context.client

    def _await_view(record: Any) -> None:
        """Rebuild the section once ``record``'s view has been read."""
        if record.number in awaited:
            return
        awaited.add(record.number)

        async def wait() -> None:
            try:
                await asyncio.wrap_future(prepare(record))
            except Exception:           # build_view logged it; the section says so
                pass
            finally:
                awaited.discard(record.number)
            if not _gone(client):
                _body.refresh()

        from nicegui import background_tasks

        background_tasks.create(wait(), name=f"read the results of run {record.number}")

    @live(session, SessionEvent.RUN_STARTED, SessionEvent.RUN_FINISHED)
    def _body() -> None:
        ui.label("Results").classes("text-h6")
        if session.run_in_progress is not None:
            ui.label(f"Run {session.run_in_progress.number} is in progress; "
                     "its results appear here when it finishes.").classes(
                "text-body2 text-grey-8")
        runs = completed_runs(session)
        if not runs:
            ui.label(NO_RUN).classes("text-grey q-mt-sm")
            ui.button("Go to Review & Run", on_click=lambda: goto("run")).props("flat")
            return

        if picked["runs"] != len(session.runs):
            picked["number"], picked["runs"] = None, len(session.runs)
        record = next((r for r in runs if r.number == picked["number"]), runs[0])
        if len(runs) > 1:
            def _pick(e: Any) -> None:
                picked["number"], picked["runs"] = e.value, len(session.runs)
                _body.refresh()

            ui.select(
                {r.number: _history_label(r, cached_view(r)) for r in runs},
                value=record.number, label="Run shown", on_change=_pick,
            ).classes("w-full").style("max-width: 24rem")

        # Read in a thread (run_results.prepare): the loop that serves
        # every tab must not wait for a large run's files.
        view = cached_view(record)
        if view is None:
            ui.label(READING.format(number=record.number)).props(
                'role=status aria-live=polite').classes("text-body1 q-mt-sm")
            ui.spinner(size="lg").props('aria-hidden="true"')
            _await_view(record)
            return
        later = overwritten_by(session, record)
        _render_view(ui, view, later_run=later.number if later else None,
                     map_choice=map_choice, goto=goto)


def _gone(client: Any) -> bool:
    """Whether the page's client has been deleted (the tab closed)."""
    flag = getattr(client, "is_deleted", None)
    if flag is None:
        flag = getattr(client, "_deleted", False)
    return bool(flag)


def _history_label(record: Any, view: Optional[RunView]) -> str:
    finished = record.finished_at or record.started_at
    status = view.status if view is not None else "succeeded" if record.success else "failed"
    return f"Run {record.number}, finished {finished:%H:%M:%S}: {status}"


# ----------------------------------------------------------------------
# One run
# ----------------------------------------------------------------------

def _render_view(ui: Any, view: RunView, *, later_run: Optional[int],
                 map_choice: Dict[int, int], goto: Callable[[str], None]) -> None:
    _status_card(ui, view)
    if later_run is not None:
        ui.label(
            f"Run {later_run} wrote into the same working directory after this run, so "
            "this run's files on disk are no longer its own. The values below were read "
            "when this run finished; its files cannot be downloaded.",
        ).classes("text-warning q-mt-sm")

    if not view.succeeded:
        ui.label(
            "No results are shown for a failed run: AERMOD did not complete it, so its "
            "output holds no valid concentrations." if view.ran else
            "AERMOD did not run, so this run has no results.",
        ).classes("text-body1 q-mt-sm")
        if view.fatal:
            ui.label("AERMOD's fatal errors").classes("text-subtitle2 q-mt-sm")
            with ui.column().classes("q-gutter-xs"):
                for message in view.fatal:
                    ui.label(message).classes("text-negative text-body2")
        _downloads(ui, view, stale=later_run is not None)
        return

    for note in view.notes:
        ui.label(note).classes("text-negative")
    results = view.results
    if results is None:
        _downloads(ui, view, stale=later_run is not None)
        return

    tables = view.concentration_tables()
    if tables:
        _maxima(ui, view, tables)
    deposition = view.deposition_tables()
    if deposition:
        _deposition_maxima(ui, deposition)
    if not tables and not deposition:
        ui.label("AERMOD's output of this run has no summary tables.").classes(
            "text-grey q-mt-md")

    _map(ui, view, map_choice, goto)
    if view.naaqs:
        _naaqs(ui, view)
    _all_values(ui, tables + deposition)
    _sources(ui, view)
    _downloads(ui, view, stale=later_run is not None, map_choice=map_choice)


def _status_card(ui: Any, view: RunView) -> None:
    with ui.card().classes("w-full q-mt-sm"):
        with ui.row().classes("items-center q-gutter-sm"):
            ui.icon("check_circle" if view.succeeded else "error",
                    color="positive" if view.succeeded else "negative").props(
                'aria-hidden="true"')
            ui.label(view.headline).classes("text-subtitle1 text-weight-medium")
        ui.label(view.detail).classes("text-body2")
        if view.started_at is not None:
            started = f"{view.started_at:%Y-%m-%d %H:%M:%S}"
            finished = f", finished {view.finished_at:%H:%M:%S}" if view.finished_at else ""
            ui.label(f"Started {started}{finished}").classes("text-body2 text-grey-8")
        # A path has no spaces to wrap at; let it break anywhere on a phone.
        ui.label(f"Working directory: {view.work_dir}").classes("text-body2 text-grey-8").style(
            "overflow-wrap: anywhere")
        if view.out is not None:
            ui.label(f"Output file: {view.out.name}").classes("text-body2 text-grey-8")


def _units(label: str) -> str:
    return _UNITS.get(label, label)


def _xy(value: Any) -> str:
    return f"{float(value):.2f}"


def _note(flag: Any) -> str:
    flag = str(flag or "")
    return f"{flag}: {FLAG_MEANINGS[flag]}" if flag in FLAG_MEANINGS else ""


def _maxima(ui: Any, view: RunView, tables: List[Any]) -> None:
    out = view.out.name if view.out else "the .out file"
    ui.label("Maximum for each averaging period").classes("text-subtitle1 q-mt-md")
    ui.label(f"As AERMOD printed them in the summary tables of {out}.").classes(
        "text-body2 text-grey-8")
    rows = []
    with ui.row().classes("q-gutter-md q-mt-xs"):
        for table in tables:
            top = table.max_row or {}
            value = str(top.get("value_text") or table.max_value)
            units = _units(table.units)
            # A period whose only table is one of AERMOD's design-value
            # tables (RECTABLE asking for the 8th highest only, say): its
            # value is that rank's, not the maximum, and is labelled so.
            qualifier = table_qualifier(table.title)
            period = period_label(table.averaging_period)
            if qualifier:
                period = f"{period} ({qualifier})"
            with ui.card().classes("q-pa-md").style("min-width: 11rem"):
                ui.label(period_label(table.averaging_period)).classes(
                    "text-overline text-grey-8")
                if qualifier:
                    ui.label(qualifier.capitalize()).classes("text-caption text-grey-8")
                ui.label(f"{value}{top.get('flag') or ''}").classes("text-h6")
                ui.label(units).classes("text-caption text-grey-8")
                ui.label(f"at ({_xy(table.max_location[0])}, {_xy(table.max_location[1])})"
                         ).classes("text-body2")
                if top.get("date"):
                    ui.label(f"ending {top['date']} (YYMMDDHH)").classes(
                        "text-caption text-grey-8")
            rows.append({
                "period": period,
                "value": value,
                "x": _xy(table.max_location[0]),
                "y": _xy(table.max_location[1]),
                "units": units,
                "group": top.get("group") or "",
                "date": top.get("date") or "",
                "note": _note(top.get("flag")),
                "table": table.title or "",
            })
    ui.table(
        columns=[
            {"name": "period", "label": "Period", "field": "period", "align": "left"},
            {"name": "value", "label": "Max", "field": "value"},
            {"name": "x", "label": "X (m)", "field": "x"},
            {"name": "y", "label": "Y (m)", "field": "y"},
            {"name": "units", "label": "Units", "field": "units", "align": "left"},
            {"name": "group", "label": "Group", "field": "group", "align": "left"},
            {"name": "date", "label": "Date (YYMMDDHH)", "field": "date"},
            {"name": "note", "label": "Note", "field": "note", "align": "left"},
            {"name": "table", "label": "AERMOD table", "field": "table", "align": "left"},
        ],
        rows=rows, row_key="period",
    ).classes("w-full q-mt-sm").props(
        'aria-label="Maximum for each averaging period" flat bordered').mark("results-maxima")
    if any(table_qualifier(t.title) for t in tables):
        ui.label("A period labelled with a rank has only that design-value table in the "
                 ".out file (the receptor table did not ask for the highest values), so "
                 "its value is that rank's, not the period's maximum.").classes(
            "text-caption text-grey-8")
    if any(r["note"] for r in rows):
        ui.label("AERMOD flags a value whose average includes calm hours (c), missing "
                 "hours (m) or both (b).").classes("text-caption text-grey-8")


def _deposition_maxima(ui: Any, tables: List[Any]) -> None:
    ui.label("Deposition: highest value of each averaging period").classes(
        "text-subtitle1 q-mt-md")
    rows = []
    for i, table in enumerate(tables):
        top = table.max_row or {}
        rows.append({
            "key": i,
            "what": _OUTPUT_TYPES.get(table.output_type, table.output_type),
            "period": period_label(table.averaging_period),
            "value": str(top.get("value_text") or table.max_value),
            "x": _xy(table.max_location[0]),
            "y": _xy(table.max_location[1]),
            "units": _units(table.units),
            "note": _note(top.get("flag")),
        })
    ui.table(
        columns=[
            {"name": "what", "label": "Output", "field": "what", "align": "left"},
            {"name": "period", "label": "Period", "field": "period", "align": "left"},
            {"name": "value", "label": "Highest", "field": "value"},
            {"name": "x", "label": "X (m)", "field": "x"},
            {"name": "y", "label": "Y (m)", "field": "y"},
            {"name": "units", "label": "Units", "field": "units", "align": "left"},
            {"name": "note", "label": "Note", "field": "note", "align": "left"},
        ],
        rows=rows, row_key="key",
    ).classes("w-full").props('aria-label="Deposition maxima" flat bordered').mark(
        "results-deposition")


# ----------------------------------------------------------------------
# Map
# ----------------------------------------------------------------------

def _sources_of(view: RunView) -> Tuple[Tuple[str, float, float], ...]:
    if view.results is None:
        return ()
    return tuple((s.source_id, float(s.x_coord), float(s.y_coord))
                 for s in view.results.sources)


def _plot_units(view: RunView, plot: PlotField) -> str:
    units = view.plot_units(plot)
    if units is not None:
        return _units(units)
    return "µg/m³" if plot.output_type == "CONC" else "AERMOD's deposition units"


#: Drawn maps (data URIs), newest last; a map is drawn once per plot file.
_MAPS: OrderedDict[tuple, str] = OrderedDict()
_MAPS_KEPT = 16
_MAPS_LOCK = threading.Lock()


def _map_src(plot: PlotField, units: str, sources: Tuple[Tuple[str, float, float], ...]) -> str:
    """The map of ``plot`` as a data URI (drawn in a worker thread)."""
    from ..results_map import concentration_map_png

    key = (plot, units, sources)
    with _MAPS_LOCK:
        if key in _MAPS:
            _MAPS.move_to_end(key)
            return _MAPS[key]
    png = concentration_map_png(plot, units=units, sources=sources)
    src = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    with _MAPS_LOCK:
        _MAPS[key] = src
        while len(_MAPS) > _MAPS_KEPT:
            _MAPS.popitem(last=False)
    return src


def _drawn_map(plot: PlotField, units: str,
               sources: Tuple[Tuple[str, float, float], ...]) -> Optional[str]:
    with _MAPS_LOCK:
        return _MAPS.get((plot, units, sources))


def _map(ui: Any, view: RunView, map_choice: Dict[int, int],
         goto: Callable[[str], None]) -> None:
    from nicegui import background_tasks, run

    from ..results_map import map_description

    kinds = {p.output_type for p in view.plots}
    ui.label("Concentration map" if kinds <= {"CONC"} else
             "Deposition map" if "CONC" not in kinds else "Map").classes(
        "text-subtitle1 q-mt-md")
    if not view.plots:
        ui.label("This run wrote no plot files, which the map is drawn from. Ask for "
                 "them on the Output step and run again.").classes("text-grey")
        ui.button("Go to Output", on_click=lambda: goto("output")).props("flat")
        return
    index = map_choice.get(view.number, 0)
    index = index if 0 <= index < len(view.plots) else 0

    @ui.refreshable
    def _picture() -> None:
        current = view.plots[map_choice.get(view.number, 0)]
        units = _plot_units(view, current)
        sources = _sources_of(view)
        # Drawing takes a moment; the page is built without waiting for it.
        image = ui.image(_drawn_map(current, units, sources) or "").props(
            f'alt="{map_description(current, units, len(sources))}" fit=contain'
            ' ratio=1.25'
        ).classes("w-full").style("max-width: 760px").mark("results-map")
        if not image.source:
            async def draw() -> None:
                src = await run.io_bound(_map_src, current, units, sources)
                if not getattr(image, "is_deleted", False):
                    image.set_source(src)

            background_tasks.create(draw(), name="draw the map")
        ui.label(f"Drawn from {current.file.name}; the tables hold the values.").classes(
            "text-caption text-grey-8")

    if len(view.plots) > 1:
        def _choose(e: Any) -> None:
            map_choice[view.number] = int(e.value)
            _picture.refresh()

        ui.select(
            {i: f"{period_label(p.period)}: {p.title} ({p.file.name})"
             for i, p in enumerate(view.plots)},
            value=index, label="Map shows", on_change=_choose,
        ).classes("w-full").style("max-width: 760px")
    map_choice[view.number] = index
    _picture()


# ----------------------------------------------------------------------
# NAAQS
# ----------------------------------------------------------------------

def _naaqs(ui: Any, view: RunView) -> None:
    ui.label("Comparison with the NAAQS").classes("text-subtitle1 q-mt-md")
    rows = []
    for i, check in enumerate(view.naaqs):
        rows.append({
            "key": i,
            "standard": check.label,
            "level": check.level_text,
            "value": "" if check.value is None else f"{check.value:.5f} µg/m³",
            "at": "" if check.location is None else
                  f"({_xy(check.location[0])}, {_xy(check.location[1])})",
            "basis": check.basis,
            "verdict": check.verdict,
            "how": check.how,
        })
    ui.table(
        columns=[
            {"name": "standard", "label": "Standard", "field": "standard", "align": "left"},
            {"name": "level", "label": "NAAQS", "field": "level", "align": "left"},
            {"name": "value", "label": "This run", "field": "value"},
            {"name": "at", "label": "At (x, y)", "field": "at"},
            {"name": "basis", "label": "Compared", "field": "basis", "align": "left"},
            {"name": "verdict", "label": "Result", "field": "verdict", "align": "left"},
            {"name": "how", "label": "Value from", "field": "how", "align": "left"},
        ],
        rows=rows, row_key="key",
    ).classes("w-full").props('aria-label="Comparison with the NAAQS" flat bordered').mark(
        "results-naaqs")
    ui.label("A screening comparison uses the highest value of the period, which no "
             "design value can exceed; the NAAQS itself is set on a design value over "
             "several years.").classes("text-caption text-grey-8")


# ----------------------------------------------------------------------
# Every value of every table
# ----------------------------------------------------------------------

def _all_values(ui: Any, tables: List[Any]) -> None:
    if not tables:
        return
    ui.label("Summary tables").classes("text-subtitle1 q-mt-md")
    for table in tables:
        kind = _OUTPUT_TYPES.get(table.output_type, table.output_type)
        name = f"{kind}, {period_label(table.averaging_period)}: {table.title or ''}"
        rows = []
        for i, row in enumerate(table.data.to_dict("records")):
            rows.append({
                "key": i,
                "group": row.get("group") or "",
                "rank": row.get("rank") if row.get("rank") is not None else "",
                "value": str(row.get("value_text") or row.get("concentration")),
                "note": _note(row.get("flag")),
                "date": row.get("date") or "",
                "x": _xy(row["x"]),
                "y": _xy(row["y"]),
                "type": row.get("receptor_type") or "",
                "grid": row.get("grid_id") or "",
            })
        with ui.expansion(name).classes("w-full"):
            ui.table(
                columns=[
                    {"name": "group", "label": "Group", "field": "group", "align": "left"},
                    {"name": "rank", "label": "Rank", "field": "rank"},
                    {"name": "value", "label": f"Value ({_units(table.units)})",
                     "field": "value"},
                    {"name": "note", "label": "Note", "field": "note", "align": "left"},
                    {"name": "date", "label": "Date (YYMMDDHH)", "field": "date"},
                    {"name": "x", "label": "X (m)", "field": "x"},
                    {"name": "y", "label": "Y (m)", "field": "y"},
                    {"name": "type", "label": "Receptor type", "field": "type"},
                    {"name": "grid", "label": "Network", "field": "grid", "align": "left"},
                ],
                rows=rows, row_key="key",
            ).classes("w-full").props(
                f'aria-label="{name}" flat dense').mark(
                "results-table")


def _sources(ui: Any, view: RunView) -> None:
    results = view.results
    if results is None or not results.sources:
        return
    ui.label("Sources").classes("text-subtitle1 q-mt-md")
    ui.table(
        columns=[
            {"name": "id", "label": "ID", "field": "id", "align": "left"},
            {"name": "type", "label": "Type", "field": "type", "align": "left"},
            {"name": "x", "label": "X (m)", "field": "x"},
            {"name": "y", "label": "Y (m)", "field": "y"},
            {"name": "Q", "label": "Q (g/s)", "field": "Q"},
        ],
        rows=[{"key": i, "id": s.source_id, "type": s.source_type,
               "x": _xy(s.x_coord), "y": _xy(s.y_coord), "Q": s.emission_rate}
              for i, s in enumerate(results.sources)],
        row_key="key",
    ).classes("w-full").props('aria-label="Sources in this run" flat dense')


# ----------------------------------------------------------------------
# Downloads
# ----------------------------------------------------------------------

def _download_label(file: RunFile) -> str:
    if file.label == "Deck":
        return "Download deck"
    if file.label.startswith("AERMOD output"):
        return "Download AERMOD output (.out)"
    if file.label.startswith("POSTFILE"):
        return f"Download POSTFILE {file.name}"
    return f"Download plot file {file.name}"


def _downloads(ui: Any, view: RunView, *, stale: bool,
               map_choice: Optional[Dict[int, int]] = None) -> None:
    files = view.files
    if not files:
        return
    ui.label("Downloads").classes("text-subtitle1 q-mt-md")

    def fetch(file: RunFile) -> None:
        try:
            data = file.read()
        except StaleFileError as exc:
            ui.notify(str(exc), color="negative")
            return
        ui.download(data, file.name, "text/plain")

    with ui.row().classes("q-gutter-sm items-center"):
        for file in files:
            button = ui.button(_download_label(file), icon="download",
                               on_click=lambda f=file: fetch(f)).props("outline")
            if stale:
                button.disable()
    with ui.column().classes("q-gutter-none q-mt-xs w-full"):
        for file in files:
            ui.label(f"{file.name}: {file.path}").classes("text-caption text-grey-8").style(
                "overflow-wrap: anywhere")

    if view.succeeded and map_choice is not None and any(
            p.output_type == "CONC" for p in view.plots):
        _kmz(ui, view, map_choice, stale=stale)


def _kmz(ui: Any, view: RunView, map_choice: Dict[int, int], *, stale: bool) -> None:
    with ui.row().classes("items-center q-gutter-md q-mt-sm"):
        zone = ui.number("UTM zone of the coordinates", min=1, max=60, step=1,
                         precision=0).classes("w-64")
        south = ui.checkbox("Southern hemisphere")

        def make() -> None:
            if zone.value is None:
                ui.notify("Enter the UTM zone of the model's x and y (a KMZ is in "
                          "latitude and longitude).", color="warning")
                return
            plot = view.plots[map_choice.get(view.number, 0)]
            if plot.output_type != "CONC":
                ui.notify("The KMZ labels its values as concentrations: show a "
                          "concentration plot file on the map first.", color="warning")
                return
            try:
                data = _kmz_bytes(view, plot, int(zone.value), not south.value)
            except ImportError as exc:
                ui.notify(f"KMZ export needs pyproj: {exc}", color="negative")
                return
            except Exception as exc:
                ui.notify(f"KMZ export failed: {exc}", color="negative")
                return
            ui.download(data, f"run{view.number}_{plot.period}.kmz",
                        "application/vnd.google-earth.kmz")

        button = ui.button("Download KMZ", icon="public", on_click=make).props("outline")
        if stale:
            button.disable()
    ui.label("The KMZ holds the sources and the values of the plot file on the map, "
             "for Google Earth.").classes("text-caption text-grey-8")


def _kmz_bytes(view: RunView, plot: PlotField, zone: int, northern: bool) -> bytes:
    from ...kmz_export import HAS_PYPROJ, to_kmz

    if not HAS_PYPROJ:
        raise ImportError("install pyaermod[geo]")
    sources = view.results.sources if view.results else []
    with tempfile.TemporaryDirectory(prefix="pyaermod_kmz_") as tmp:
        path = Path(tmp) / "run.kmz"
        to_kmz(path, sources=[_Point(s.source_id, s.x_coord, s.y_coord) for s in sources],
               receptors=list(zip(plot.x, plot.y, plot.values)), utm_zone=zone,
               northern_hemisphere=northern,
               title=f"Run {view.number}: {plot.title}")
        return path.read_bytes()


class _Point:
    """A source as kmz_export places it: an id and a point."""

    def __init__(self, source_id: str, x: float, y: float) -> None:
        self.source_id, self.x_coord, self.y_coord = source_id, x, y


__all__ = ["NO_RUN", "render"]

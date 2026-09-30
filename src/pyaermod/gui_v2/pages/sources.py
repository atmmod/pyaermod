"""
Sources step.

A table of the project's sources with Edit and Delete on every row, a
plan view of the sources and receptors, and an editor for any of the 13
AERMOD source types. The editor is generated from the source's dataclass
(:mod:`pyaermod.gui_v2._form`): the fields AERMOD's LOCATION and SRCPARAM
cards need come first, the rest under "Advanced". Labels carry units and
the inputs their help text, from the library's field metadata.

New sources start from :data:`_DEFAULTS`, placeholder values that pass
``__post_init__`` so the editor opens cleanly; the user overrides them
before Save. The table shows one page of rows at a time
(:class:`pyaermod.gui_v2._layout.Pager`).
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Dict, List, Optional, Type

from ..._fields import units_of
from ...input_generator import (
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    LineSource,
    OpenPitSource,
    PointCapSource,
    PointHorSource,
    PointSource,
    RLineExtSource,
    RLineSource,
    SidewashPointSource,
    VolumeSource,
)
from .._form import emit_fields
from .._layout import Goto, Pager, plan_view, section, step_page
from .._live import live
from ..session import Session, SessionEvent

# ---------------------------------------------------------------------
# Source-type registry
# ---------------------------------------------------------------------

_SOURCE_TYPES: Dict[str, Type] = {
    "PointSource":      PointSource,
    "VolumeSource":     VolumeSource,
    "AreaSource":       AreaSource,
    "AreaCircSource":   AreaCircSource,
    "AreaPolySource":   AreaPolySource,
    "LineSource":       LineSource,
    "RLineSource":      RLineSource,
    "RLineExtSource":   RLineExtSource,
    "BuoyLineSource":   BuoyLineSource,
    "OpenPitSource":    OpenPitSource,
    "PointCapSource":  PointCapSource,
    "PointHorSource":  PointHorSource,
    "SidewashPointSource": SidewashPointSource,
}


# Required-field placeholder values for new-source instantiation.
# Each value should pass __post_init__ validation so the dialog can
# open without errors; the user is expected to override before save.
_DEFAULTS: Dict[str, Any] = {
    "source_id":       "NEW_SRC",
    "x_coord":         0.0,
    "y_coord":         0.0,
    "x_start":         0.0,
    "y_start":         0.0,
    "x_end":           100.0,
    "y_end":           0.0,
    "stack_height":    10.0,
    "release_height":  2.0,
    "stack_temp":      400.0,
    "exit_velocity":   10.0,
    "stack_diameter":  1.0,
    "emission_rate":   1.0,
    "x_length":        100.0,
    "y_length":        100.0,
    "radius":          50.0,
    "vertices":        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
    "initial_lateral_dimension":  10.0,
    "initial_vertical_dimension": 5.0,
    "init_sigma_y":               5.0,
    "init_sigma_z":               2.0,
    "pit_volume":                 1000.0,
    "pit_height":                 10.0,
    "depth":                      2.0,
    "width_top":                  20.0,
    "width_bottom":               10.0,
    "line_segments":              [
        BuoyLineSegment(
            source_id="BL_SEG1",
            x_start=0.0, y_start=0.0, x_end=100.0, y_end=0.0,
            emission_rate=1.0, release_height=2.0,
        ),
    ],
    # RLineExtSource z coords (per-endpoint elevations)
    "z_start":  0.0,
    "z_end":    0.0,
    # BuoyLineSource per-line meteorological parameters
    "avg_line_length":           100.0,
    "avg_line_width":             10.0,
    "avg_buoyancy_parameter":      5.0,
    "avg_building_height":         5.0,
    "avg_building_width":         10.0,
    "avg_building_separation":    10.0,
}


def _new_source(type_name: str) -> Any:
    """Construct a default instance of ``type_name`` for editing.

    Pulls from ``_DEFAULTS`` for every field listed there, even if the
    underlying dataclass has its own default — the GUI's defaults are
    intentionally sensible (10 m stack, 1 g/s emission) where the
    dataclass defaults to 0.
    """
    cls = _SOURCE_TYPES[type_name]
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name in _DEFAULTS:
            kwargs[f.name] = _DEFAULTS[f.name]
    return cls(**kwargs)


def _summary_row(src: Any) -> Dict[str, Any]:
    """Compact dict suitable for AG-Grid display."""
    cls_name = type(src).__name__
    if hasattr(src, "x_coord"):
        x, y = src.x_coord, src.y_coord
    elif hasattr(src, "x_start"):
        x, y = src.x_start, src.y_start
    elif hasattr(src, "vertices") and src.vertices:
        x, y = src.vertices[0]
    elif (getattr(src, "line_segments", None)
          and getattr(src.line_segments[0], "x_start", None) is not None):
        # BuoyLineSource: summarise from the first buoyant line segment
        x, y = src.line_segments[0].x_start, src.line_segments[0].y_start
    else:
        x, y = "", ""
    return {
        "id": src.source_id,
        "type": cls_name,
        "x": x,
        "y": y,
        "Q (g/s)": getattr(src, "emission_rate", ""),
    }


# ---------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------

#: Fields the editor puts under "Advanced": everything AERMOD does not need
#: on the LOCATION and SRCPARAM cards. Shared with the Receptors step.
ADVANCED_FIELDS = frozenset({
    "base_elevation", "flat_source",
    "building_height", "building_width", "building_length",
    "building_x_offset", "building_y_offset",
    "source_groups", "is_urban", "urban_area_name", "no2_ratio",
    "gas_deposition", "particle_deposition", "deposition_method", "method_2",
    "platform", "street_canyon", "vegetative_barriers",
    "barrier_height_1", "barrier_dcl_1", "barrier_height_2", "barrier_dcl_2",
    "depression_depth", "depression_wtop", "depression_wbottom", "num_vertices",
    # receptors
    "z_elev", "z_hill", "z_flag", "grid_elevations", "grid_hills", "grid_flags",
    "x_points", "y_points", "distances", "directions", "origin_source_id",
    "elevations", "hills", "flags",
})

_COLUMNS = [
    {"name": "id", "label": "ID", "field": "id", "align": "left"},
    {"name": "type", "label": "Type", "field": "type", "align": "left",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "x", "label": "X (m)", "field": "x", "align": "right",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "y", "label": "Y (m)", "field": "y", "align": "right",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "Q (g/s)", "label": "Emission rate", "field": "Q (g/s)", "align": "right"},
    {"name": "units", "label": "Units", "field": "units", "align": "left",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "actions", "label": "Actions", "field": "key", "align": "right"},
]

#: Row actions, with the item named in each button's accessible name.
ROW_ACTIONS_SLOT = """
<q-td :props="props" class="text-right">
  <q-btn dense flat round icon="edit" :aria-label="`Edit ${props.row.name}`"
         @click="$parent.$emit(`edit`, props.row.key)" />
  <q-btn dense flat round icon="delete" color="negative"
         :aria-label="`Delete ${props.row.name}`"
         @click="$parent.$emit(`delete`, props.row.key)" />
</q-td>
"""


def _emission_units(src: Any) -> str:
    for f in dataclasses.fields(src):
        if f.name == "emission_rate":
            return units_of(f) or ""
    return ""


def split_fields(obj: Any) -> tuple:
    """(basic, advanced) dataclass fields of ``obj`` for the editor."""
    fields = dataclasses.fields(obj)
    return ([f for f in fields if f.name not in ADVANCED_FIELDS],
            [f for f in fields if f.name in ADVANCED_FIELDS])


def editor_body(draft: Any) -> None:
    """The editor's fields: the basic ones, then the rest under "Advanced"."""
    from nicegui import ui

    basic, advanced = split_fields(draft)
    emit_fields(draft, basic)
    if advanced:
        with ui.expansion("Advanced", icon="tune").classes("w-full"):
            emit_fields(draft, advanced)


def render(session: Session, *, dialogs: Any, goto: Optional[Goto] = None) -> None:
    """Render the Sources step.

    The table and its empty-state message are a live section rebuilt when
    the sources change, and so is the plan view. Rows carry the session's
    key for each source; the editor works on a draft (a copy, or a new
    source for Add) that only Save hands to the session.
    """
    from nicegui import ui

    del goto
    pager = Pager()

    def _open_editor(key: Optional[str], draft: Any) -> None:
        with dialogs, ui.dialog().mark("editor-dialog") as dialog, \
                ui.card().classes("w-full max-w-4xl"):
            # "Edit PointSource — NEW_SRC": the page objects and T1 tests
            # find the editor by its first words.
            ui.label(f"Edit {type(draft).__name__} — {draft.source_id}").classes("text-h6")
            with ui.column().classes("w-full gap-2"):
                editor_body(draft)
            with ui.row().classes("justify-end w-full q-gutter-sm q-mt-md"):
                ui.button("Close", on_click=dialog.close).props("flat")

                def _on_save() -> None:
                    if key is None:
                        session.add_source(draft)
                    elif not session.update_source(key, draft):
                        dialog.close()
                        ui.notify("That source was removed", color="warning")
                        return
                    dialog.close()

                ui.button("Save", on_click=_on_save).props("color=primary")
        # A closed editor is gone for good; the next one is built afresh.
        dialog.on_value_change(lambda e: None if e.value else dialog.delete())
        dialog.open()

    def _on_edit(e) -> None:
        for key, src in session.source_entries():
            if key == e.args:
                _open_editor(key, copy.deepcopy(src))
                return

    def _on_delete(e) -> None:
        removed = session.delete_source(e.args)
        if removed is not None:      # None: an event from a row already gone
            ui.notify(f"Deleted {removed.source_id}", color="warning")

    with step_page("Sources", "Add every source of the run. The plan view shows them "
                   "with the receptors, in model coordinates."):
        with ui.row().classes("items-end gap-3 w-full flex-wrap"):
            type_select = ui.select(
                options=list(_SOURCE_TYPES.keys()), label="Type", value="PointSource",
            ).classes("w-full sm:w-64")
            ui.button("Add", icon="add",
                      on_click=lambda: _open_editor(None, _new_source(type_select.value)),
                      ).props("color=primary")

        with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-5 gap-4 w-full items-start"):
            with ui.column().classes("lg:col-span-3 min-w-0 w-full gap-2"):
                @live(session, SessionEvent.PROJECT_CHANGED, parts={"sources"})
                def _table() -> None:
                    entries = session.source_entries()
                    rows: List[Dict[str, Any]] = [
                        {**_summary_row(s), "units": _emission_units(s), "key": key,
                         "name": s.source_id}
                        for key, s in pager.window(entries)
                    ]
                    table = ui.table(columns=_COLUMNS, rows=rows, row_key="key").classes(
                        "w-full").props('flat bordered hide-bottom aria-label="Sources"').mark(
                        "sources-table")
                    table.add_slot("body-cell-actions", ROW_ACTIONS_SLOT)
                    table.on("edit", _on_edit)
                    table.on("delete", _on_delete)
                    pager.controls(len(entries), noun="Sources", refresh=lambda: _table.refresh())
                    if not entries:
                        ui.label("No sources yet. Choose a type and click Add.").classes(
                            "text-grey-8")
            with ui.column().classes("lg:col-span-2 min-w-0 w-full"), \
                    section("Plan view"):
                plan_view(session)


__all__ = ["ADVANCED_FIELDS", "editor_body", "render", "split_fields"]

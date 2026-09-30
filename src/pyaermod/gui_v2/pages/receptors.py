"""
Receptors step.

Three receptor types, each edited through the shared form helper:

- :class:`pyaermod.input_generator.CartesianGrid`
- :class:`pyaermod.input_generator.PolarGrid`
- :class:`pyaermod.input_generator.DiscreteReceptor`

The step mirrors Sources: a table of the receptors with Edit and Delete
on every row, shown one page at a time, the plan view, and an Add button
for the chosen type. A project with ten thousand discrete receptors sends
the browser one page of rows, not ten thousand.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from ...input_generator import (
    CartesianGrid,
    DiscreteReceptor,
    PolarGrid,
    ReceptorPathway,
)
from .._layout import Goto, Pager, plan_view, section, step_page
from .._live import live
from ..session import Session, SessionEvent

_RECEPTOR_TYPES: Dict[str, Type] = {
    "CartesianGrid":     CartesianGrid,
    "PolarGrid":         PolarGrid,
    "DiscreteReceptor":  DiscreteReceptor,
}


# Sensible defaults for new receptors. Only required fields (no
# default / default_factory) need entries; the rest fall back to the
# dataclass's own defaults.
_DEFAULTS: Dict[str, Any] = {
    "grid_name":   "GRID1",
    "x_origin":    0.0,
    "y_origin":    0.0,
    "x_init":      -1000.0,
    "y_init":      -1000.0,
    "x_num":       21,
    "y_num":       21,
    "x_delta":     100.0,
    "y_delta":     100.0,
    "dist_init":   100.0,
    "dist_num":    10,
    "dist_delta":  100.0,
    "dir_init":    0.0,
    "dir_num":     36,
    "dir_delta":   10.0,
    "x_coord":     0.0,
    "y_coord":     0.0,
}


def _new_receptor(type_name: str) -> Any:
    """Construct a default-filled receptor of ``type_name``."""
    cls = _RECEPTOR_TYPES[type_name]
    kwargs = {f.name: _DEFAULTS[f.name]
              for f in dataclasses.fields(cls) if f.name in _DEFAULTS}
    return cls(**kwargs)


def _receptor_lists(rp: ReceptorPathway):
    """Return (kind, target_attr_name, list_ref) triples for each type."""
    return [
        ("CartesianGrid",    "cartesian_grids",    rp.cartesian_grids),
        ("PolarGrid",        "polar_grids",        rp.polar_grids),
        ("DiscreteReceptor", "discrete_receptors", rp.discrete_receptors),
    ]


def _summary_row(rec: Any, *, kind: str, idx: int) -> Dict[str, Any]:
    if kind == "CartesianGrid":
        label = getattr(rec, "grid_name", "") or f"CART{idx}"
        nx = getattr(rec, "x_num", "")
        ny = getattr(rec, "y_num", "")
        return {"key": f"{kind}:{idx}", "label": label, "kind": kind,
                "summary": f"{nx} x {ny}"}
    if kind == "PolarGrid":
        label = getattr(rec, "grid_name", "") or f"POL{idx}"
        nd = getattr(rec, "dist_num", "")
        na = getattr(rec, "dir_num", "")
        return {"key": f"{kind}:{idx}", "label": label, "kind": kind,
                "summary": f"{nd} dist x {na} dir"}
    # DiscreteReceptor
    return {"key": f"{kind}:{idx}", "label": f"DISC{idx}", "kind": kind,
            "summary": f"({rec.x_coord:.1f}, {rec.y_coord:.1f})"}


def _all_rows(entries: Iterable[Tuple[str, str, Any]]) -> List[Dict[str, Any]]:
    """Table rows for ``Session.receptor_entries()``, keyed by session key.

    Receptors are numbered within their kind (``DISC0``, ``DISC1``, ...)
    in the order the session lists them.
    """
    rows = []
    counts: Dict[str, int] = {}
    for key, kind, rec in entries:
        idx = counts.get(kind, 0)
        counts[kind] = idx + 1
        rows.append({**_summary_row(rec, kind=kind, idx=idx), "key": key})
    return rows


# ---------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------

_COLUMNS = [
    {"name": "label",   "label": "Name",    "field": "label",   "align": "left"},
    {"name": "kind",    "label": "Type",    "field": "kind",    "align": "left"},
    {"name": "summary", "label": "Summary", "field": "summary", "align": "left"},
    {"name": "actions", "label": "Actions", "field": "key",     "align": "right"},
]


def render(session: Session, *, dialogs: Any, goto: Optional[Goto] = None) -> None:
    """Render the Receptors step (the same pattern as the Sources step)."""
    from nicegui import ui

    from .sources import ROW_ACTIONS_SLOT, editor_body

    del goto
    pager = Pager(session=session)

    def _open_editor(key: Optional[str], draft: Any) -> None:
        with dialogs, ui.dialog().mark("editor-dialog") as dialog, \
                ui.card().classes("w-full max-w-4xl"):
            ui.label(f"Edit {type(draft).__name__}").classes("text-h6")
            with ui.column().classes("w-full gap-2"):
                editor_body(draft)
            with ui.row().classes("justify-end w-full q-gutter-sm q-mt-md"):
                ui.button("Close", on_click=dialog.close).props("flat")

                def _on_save() -> None:
                    if key is None:
                        session.add_receptor(draft)
                    elif not session.update_receptor(key, draft):
                        dialog.close()
                        ui.notify("That receptor was removed", color="warning")
                        return
                    dialog.close()

                ui.button("Save", on_click=_on_save).props("color=primary")
        dialog.on_value_change(lambda e: None if e.value else dialog.delete())
        dialog.open()

    def _on_edit(e) -> None:
        for key, _kind, rec in session.receptor_entries():
            if key == e.args:
                _open_editor(key, copy.deepcopy(rec))
                return

    def _on_delete(e) -> None:
        # Today's wording: the kind and the item's position within its kind.
        positions: Dict[str, str] = {}
        counts: Dict[str, int] = {}
        for key, kind, _rec in session.receptor_entries():
            positions[key] = f"{kind}[{counts.get(kind, 0)}]"
            counts[kind] = counts.get(kind, 0) + 1
        removed = session.delete_receptor(e.args)
        if removed is not None:      # None: an event from a row already gone
            ui.notify(f"Deleted {positions[e.args]}", color="warning")

    with step_page("Receptors", "Add the receptor networks and discrete receptors "
                   "AERMOD computes concentrations at."):
        with ui.row().classes("items-end gap-3 w-full flex-wrap"):
            type_select = ui.select(
                options=list(_RECEPTOR_TYPES.keys()), value="CartesianGrid", label="Type",
            ).classes("w-full sm:w-64")
            ui.button("Add", icon="add",
                      on_click=lambda: _open_editor(None, _new_receptor(type_select.value)),
                      ).props("color=primary")

        with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-5 gap-4 w-full items-start"):
            with ui.column().classes("lg:col-span-3 min-w-0 w-full gap-2"):
                @live(session, SessionEvent.PROJECT_CHANGED, parts={"receptors"})
                def _table() -> None:
                    rows = _all_rows(session.receptor_entries())
                    shown = [{**row, "name": row["label"]} for row in pager.window(rows)]
                    table = ui.table(columns=_COLUMNS, rows=shown, row_key="key").classes(
                        "w-full").props('flat bordered hide-bottom aria-label="Receptors"').mark(
                        "receptors-table")
                    table.add_slot("body-cell-actions", ROW_ACTIONS_SLOT)
                    table.on("edit", _on_edit)
                    table.on("delete", _on_delete)
                    pager.controls(len(rows), noun="Receptors", refresh=lambda: _table.refresh())
                    if not rows:
                        ui.label("No receptors yet. Choose a type and click Add.").classes(
                            "text-grey-8")
            with ui.column().classes("lg:col-span-2 min-w-0 w-full"), \
                    section("Plan view"):
                plan_view(session)


__all__ = ["render"]

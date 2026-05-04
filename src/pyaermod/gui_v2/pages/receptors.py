"""
Receptors tab.

Three receptor types are supported, each rendered via the shared
generic form helper:

- :class:`pyaermod.input_generator.CartesianGrid`
- :class:`pyaermod.input_generator.PolarGrid`
- :class:`pyaermod.input_generator.DiscreteReceptor`

The page mirrors the Sources tab pattern: a table of existing
receptors with edit / delete actions, plus an "Add" dropdown for
the three types.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Type

from ...input_generator import CartesianGrid, DiscreteReceptor, PolarGrid
from .._form import emit_field
from ..state import AppState

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


def _receptor_lists(state: AppState):
    """Return (key, target_attr_name, list_ref) triples for each type."""
    rp = state.project.receptors
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


def _all_rows(state: AppState):
    rows = []
    for kind, _attr, lst in _receptor_lists(state):
        for i, rec in enumerate(lst):
            rows.append(_summary_row(rec, kind=kind, idx=i))
    return rows


def _find(state: AppState, key: str):
    """Resolve a 'kind:idx' key to (receptor, list_ref, idx, kind)."""
    kind, idx_s = key.split(":", 1)
    idx = int(idx_s)
    for k, _attr, lst in _receptor_lists(state):
        if k == kind:
            return lst[idx], lst, idx, kind
    raise KeyError(key)


# ---------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------

def render(state: AppState) -> None:
    from nicegui import ui

    table_ref: Dict[str, Any] = {"obj": None}

    def _refresh_table():
        if table_ref["obj"] is not None:
            table_ref["obj"].rows[:] = _all_rows(state)
            table_ref["obj"].update()

    with ui.row().classes("items-center q-gutter-md"):
        ui.label("Receptors").classes("text-h6")
        type_select = ui.select(
            options=list(_RECEPTOR_TYPES.keys()),
            value="CartesianGrid", label="Type",
        ).classes("w-48")

        def _on_add():
            new_rec = _new_receptor(type_select.value)
            attr = {
                "CartesianGrid":    "cartesian_grids",
                "PolarGrid":        "polar_grids",
                "DiscreteReceptor": "discrete_receptors",
            }[type_select.value]
            getattr(state.project.receptors, attr).append(new_rec)
            state.mark_dirty()
            _refresh_table()
            _open_editor(new_rec)

        ui.button("Add", on_click=_on_add).props("color=primary")

    ui.separator().classes("q-my-md")

    columns = [
        {"name": "key",     "label": "",        "field": "key",
         "align": "left", "classes": "hidden", "headerClasses": "hidden"},
        {"name": "label",   "label": "Name",    "field": "label",
         "align": "left"},
        {"name": "kind",    "label": "Type",    "field": "kind",
         "align": "left"},
        {"name": "summary", "label": "Summary", "field": "summary",
         "align": "left"},
    ]
    table = ui.table(
        columns=columns, rows=_all_rows(state), row_key="key",
    ).classes("w-full")
    table_ref["obj"] = table

    table.add_slot(
        "body-cell-label",
        '''
        <q-td :props="props">
          <q-btn dense flat icon="edit"
                 @click="$parent.$emit(`edit`, props.row.key)" />
          <q-btn dense flat icon="delete" color="negative"
                 @click="$parent.$emit(`delete`, props.row.key)" />
          {{ props.row.label }}
        </q-td>
        ''',
    )

    def _open_editor(rec: Any):
        with ui.dialog() as dialog, ui.card().classes("min-w-[600px]"):
            ui.label(f"Edit {type(rec).__name__}").classes("text-h6")
            with ui.column().classes("w-full q-gutter-sm"):
                for fmeta in dataclasses.fields(rec):
                    emit_field(ui.row().classes("w-full"), rec, fmeta)
            with ui.row().classes("justify-end q-gutter-sm q-mt-md"):
                ui.button("Close", on_click=dialog.close).props("flat")

                def _on_save():
                    state.mark_dirty()
                    _refresh_table()
                    dialog.close()
                ui.button(
                    "Save", on_click=_on_save,
                ).props("color=primary")
        dialog.open()

    table.on("edit", lambda e: _open_editor(_find(state, e.args)[0]))

    def _on_delete(e):
        _rec, lst, idx, kind = _find(state, e.args)
        del lst[idx]
        state.mark_dirty()
        _refresh_table()
        ui.notify(f"Deleted {kind}[{idx}]", color="warning")

    table.on("delete", _on_delete)

    if not _all_rows(state):
        ui.label("No receptors yet. Add one above.").classes(
            "text-grey q-mt-sm",
        )


__all__ = ["render"]

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

import copy
import dataclasses
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from ...input_generator import (
    CartesianGrid,
    DiscreteReceptor,
    PolarGrid,
    ReceptorPathway,
)
from .._form import emit_field
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
    {"name": "key",     "label": "",        "field": "key",
     "align": "left", "classes": "hidden", "headerClasses": "hidden"},
    {"name": "label",   "label": "Name",    "field": "label",
     "align": "left"},
    {"name": "kind",    "label": "Type",    "field": "kind",
     "align": "left"},
    {"name": "summary", "label": "Summary", "field": "summary",
     "align": "left"},
]


def render(session: Session, *, dialogs: Any) -> None:
    """Render the Receptors tab (the same pattern as the Sources tab)."""
    from nicegui import ui

    with ui.row().classes("items-center q-gutter-md"):
        ui.label("Receptors").classes("text-h6")
        type_select = ui.select(
            options=list(_RECEPTOR_TYPES.keys()),
            value="CartesianGrid", label="Type",
        ).classes("w-48")

        def _on_add() -> None:
            _open_editor(None, _new_receptor(type_select.value))

        ui.button("Add", on_click=_on_add).props("color=primary")

    ui.separator().classes("q-my-md")

    def _open_editor(key: Optional[str], draft: Any) -> None:
        with dialogs, ui.dialog().mark("editor-dialog") as dialog, \
                ui.card().classes("min-w-[600px]"):
            ui.label(f"Edit {type(draft).__name__}").classes("text-h6")
            with ui.column().classes("w-full q-gutter-sm"):
                for fmeta in dataclasses.fields(draft):
                    emit_field(ui.row().classes("w-full"), draft, fmeta)
            with ui.row().classes("justify-end q-gutter-sm q-mt-md"):
                ui.button("Close", on_click=dialog.close).props("flat")

                def _on_save() -> None:
                    if key is None:
                        session.add_receptor(draft)
                    elif not session.update_receptor(key, draft):
                        dialog.close()
                        ui.notify("That receptor was removed", color="warning")
                        return
                    dialog.close()

                ui.button(
                    "Save", on_click=_on_save,
                ).props("color=primary")
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

    @live(session, SessionEvent.PROJECT_CHANGED, parts={"receptors"})
    def _table() -> None:
        rows = _all_rows(session.receptor_entries())
        table = ui.table(
            columns=_COLUMNS, rows=rows, row_key="key",
        ).classes("w-full").mark("receptors-table")
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
        table.on("edit", _on_edit)
        table.on("delete", _on_delete)
        if not rows:
            ui.label("No receptors yet. Add one above.").classes(
                "text-grey q-mt-sm",
            )


__all__ = ["render"]

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
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ...input_generator import ReceptorPathway
from .._layout import Goto, editor_dialog, item_table, plan_view, section, step_page
from ..catalog import RECEPTOR_DEFAULTS as _DEFAULTS  # noqa: F401 - the tests read it here
from ..catalog import RECEPTOR_TYPES as _RECEPTOR_TYPES
from ..catalog import new_receptor as _new_receptor
from ..readiness import item_findings
from ..session import Session


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

    from .sources import editor_body

    del goto

    def _open_editor(key: Optional[str], draft: Any) -> None:
        def save() -> bool:
            if key is None:
                session.add_receptor(draft)
                return True
            return session.update_receptor(key, draft)

        editor_dialog(dialogs, title=f"Edit {type(draft).__name__}",
                      build=lambda changed: editor_body(draft, changed),
                      findings=lambda: item_findings(session.project, draft),
                      refused=list, save=save, gone="That receptor was removed")

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
                item_table(session, part="receptors", noun="Receptors", columns=_COLUMNS,
                           entries=lambda: _all_rows(session.receptor_entries()),
                           row=lambda row: {**row, "name": row["label"]},
                           on_edit=_on_edit, on_delete=_on_delete,
                           empty="No receptors yet. Choose a type and click Add.")
            with ui.column().classes("lg:col-span-2 min-w-0 w-full"), \
                    section("Plan view"):
                plan_view(session)


__all__ = ["render"]

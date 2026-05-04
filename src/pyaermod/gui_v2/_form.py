"""
Shared dataclass-field → NiceGUI widget helper.

Used by every tab that edits a dataclass (sources, receptors,
meteorology, output, control). Keeps the per-tab page modules
small — each just lists which fields to render and the form helper
emits the right widget by introspecting the dataclass.

Field-type → widget mapping
---------------------------

==========================  ====================================
Annotation (string form)    Widget
==========================  ====================================
``str``                     ``ui.input``
``float`` / ``int``         ``ui.number``
``bool``                    ``ui.checkbox``
``Optional[<numeric>]``     ``ui.number`` (clearable)
``List[Tuple[float,float]]`` text area (one ``x, y`` pair per line)
``List[str]``               text area (one entry per line)
unknown                     read-only label (escape hatch)
==========================  ====================================
"""

from __future__ import annotations

import contextlib
import dataclasses
from typing import Any, Iterable, Optional


def is_numeric(type_str: str) -> bool:
    """Annotation contains a float/int substring."""
    return any(t in type_str for t in ("float", "int"))


def is_optional_numeric(type_str: str) -> bool:
    return type_str.startswith("Optional[") and is_numeric(type_str)


def emit_field(parent, obj: Any, fmeta) -> None:
    """Render the right widget for a single dataclass field.

    ``parent`` is a NiceGUI container (e.g. ``ui.row()``); the widget
    is added to it. Mutates ``obj`` directly via ``setattr`` /
    ``bind_value`` whenever the user changes the value.
    """
    from nicegui import ui

    fname = fmeta.name
    type_str = str(fmeta.type)
    cur = getattr(obj, fname)
    label = fname.replace("_", " ")

    if type_str == "str":
        with parent:
            ui.input(label=label, value=cur or "").bind_value(obj, fname)
    elif type_str == "bool":
        with parent:
            ui.checkbox(label, value=bool(cur)).bind_value(obj, fname)
    elif is_numeric(type_str) or is_optional_numeric(type_str):
        with parent:
            ui.number(
                label=label, value=cur if cur is not None else 0,
                format="%.4f",
            ).bind_value(obj, fname)
    elif "List[Tuple[float" in type_str:
        with parent:
            ta = ui.textarea(
                label=label,
                value="\n".join(f"{x:g}, {y:g}" for x, y in (cur or [])),
            ).classes("w-full")

            def _save_verts(_=None):
                rows = []
                for line in ta.value.splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    parts = [
                        p.strip() for p in s.replace(";", ",").split(",")
                    ]
                    if len(parts) >= 2:
                        with contextlib.suppress(ValueError):
                            rows.append((float(parts[0]), float(parts[1])))
                setattr(obj, fname, rows)

            ta.on("update:model-value", _save_verts)
    elif type_str.startswith("List["):
        with parent:
            ta = ui.textarea(
                label=label,
                value="\n".join(str(v) for v in (cur or [])),
            ).classes("w-full")

            def _save_strs(_=None):
                lines = [
                    s.strip() for s in ta.value.splitlines() if s.strip()
                ]
                setattr(obj, fname, lines)

            ta.on("update:model-value", _save_strs)
    else:
        # Escape hatch (Enums, nested dataclasses)
        with parent:
            ui.label(f"{label}: {cur!r}").classes("text-grey")


def emit_form(
    container, obj: Any, *, fields: Optional[Iterable[str]] = None,
) -> None:
    """Render every field of ``obj`` as a stacked form inside ``container``.

    ``fields`` optionally restricts to a subset, preserving order.
    """
    from nicegui import ui

    name_to_meta = {f.name: f for f in dataclasses.fields(obj)}
    chosen = list(fields) if fields else list(name_to_meta.keys())
    with container:
        for name in chosen:
            meta = name_to_meta.get(name)
            if meta is None:
                continue
            emit_field(ui.row().classes("w-full"), obj, meta)


__all__ = [
    "emit_field",
    "emit_form",
    "is_numeric",
    "is_optional_numeric",
]

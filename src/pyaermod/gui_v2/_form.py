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
``str`` / ``Optional[str]`` ``ui.input``
``float`` / ``int``         ``ui.number``
``bool``                    ``ui.checkbox``
``Optional[<numeric>]``     ``ui.number`` (clearable)
``List[Tuple[float,float]]`` text area (one ``x, y`` pair per line)
``List[str]``               text area (one entry per line)
unknown                     read-only label (escape hatch)
==========================  ====================================

"Numeric" means the *resolved* annotation is ``int`` or ``float``,
optionally in a union with ``None`` — never a container or tuple that
merely mentions a float (``List[Tuple[float, float]]``,
``Optional[Tuple[DepositionMethod, float]]``). Annotations are resolved
with :func:`typing.get_type_hints`; string annotations that cannot be
resolved are parsed structurally instead.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import types
import typing
from typing import Any, Iterable, Optional, Tuple, Union

_NUMERIC_TYPES = (int, float)   # bool is excluded on purpose (identity check)
_UNION_WRAPPERS = ("Optional", "Union")


def _numeric_info_type(tp: Any) -> Tuple[bool, bool]:
    """Return ``(is_numeric, allows_none)`` for a resolved typing object."""
    origin = typing.get_origin(tp)
    if origin is Union or origin is types.UnionType:
        args = typing.get_args(tp)
        non_none = [a for a in args if a is not type(None)]
        if not non_none or not all(a in _NUMERIC_TYPES for a in non_none):
            return False, False
        return True, len(non_none) < len(args)
    return (tp in _NUMERIC_TYPES), False


def _wrapper_name(node: ast.expr) -> Optional[str]:
    """``Optional`` / ``Union`` whether written bare or as ``typing.X``."""
    if isinstance(node, ast.Name) and node.id in _UNION_WRAPPERS:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in _UNION_WRAPPERS:
        return node.attr
    return None


def _leaf_names(node: ast.expr) -> list:
    """Flatten ``Optional[...]`` / ``Union[...]`` / ``X | Y`` into leaf names."""
    if isinstance(node, ast.Subscript) and _wrapper_name(node.value):
        sl = node.slice
        elts = list(sl.elts) if isinstance(sl, ast.Tuple) else [sl]
        names: list = []
        for e in elts:
            names.extend(_leaf_names(e))
        if _wrapper_name(node.value) == "Optional":
            names.append("None")
        return names
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _leaf_names(node.left) + _leaf_names(node.right)
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Constant) and node.value is None:
        return ["None"]
    return ["<non-numeric>"]   # containers, tuples, dotted names, ...


def _numeric_info_str(annotation: str) -> Tuple[bool, bool]:
    """Structural equivalent of :func:`_numeric_info_type` for string annotations."""
    try:
        node = ast.parse(annotation.strip(), mode="eval").body
    except SyntaxError:
        return False, False
    names = _leaf_names(node)
    non_none = [n for n in names if n != "None"]
    if not non_none or any(n not in ("int", "float") for n in non_none):
        return False, False
    return True, "None" in names


def _numeric_info(annotation: Any) -> Tuple[bool, bool]:
    if isinstance(annotation, str):
        return _numeric_info_str(annotation)
    return _numeric_info_type(annotation)


def is_numeric(annotation: Any) -> bool:
    """True iff ``annotation`` resolves to ``int``/``float``, optionally with ``None``.

    Accepts a typing object (``float``, ``Optional[int]``) or the string
    form used under ``from __future__ import annotations``. Containers
    and tuples that merely contain a numeric type are *not* numeric.
    """
    return _numeric_info(annotation)[0]


def is_optional_numeric(annotation: Any) -> bool:
    """True iff :func:`is_numeric` holds *and* the annotation admits ``None``."""
    is_num, allows_none = _numeric_info(annotation)
    return is_num and allows_none


_HINTS_CACHE: dict = {}


def _type_hints(cls: type) -> dict:
    """Resolved annotations for ``cls`` (empty if a forward ref cannot be resolved)."""
    if cls not in _HINTS_CACHE:
        try:
            _HINTS_CACHE[cls] = typing.get_type_hints(cls)
        except Exception:   # NameError on an unresolvable forward reference
            _HINTS_CACHE[cls] = {}
    return _HINTS_CACHE[cls]


def resolve_annotation(obj: Any, fmeta) -> Any:
    """The resolved type of field ``fmeta`` on ``obj``, else its raw annotation."""
    return _type_hints(type(obj)).get(fmeta.name, fmeta.type)


def emit_field(parent, obj: Any, fmeta) -> None:
    """Render the right widget for a single dataclass field.

    ``parent`` is a NiceGUI container (e.g. ``ui.row()``); the widget
    is added to it. Mutates ``obj`` directly via ``setattr`` /
    ``bind_value`` whenever the user changes the value.
    """
    from nicegui import ui

    fname = fmeta.name
    type_str = str(fmeta.type)
    annotation = resolve_annotation(obj, fmeta)
    cur = getattr(obj, fname)
    label = fname.replace("_", " ")

    if type_str in ("str", "Optional[str]"):
        # Optional[str] fields (OutputPathway.summary_file, max_file, ...)
        # are plain text inputs too; an empty box reads back as "".
        with parent:
            ui.input(label=label, value=cur or "").bind_value(obj, fname)
    elif type_str == "bool":
        with parent:
            ui.checkbox(label, value=bool(cur)).bind_value(obj, fname)
    # List annotations are dispatched before the numeric check on purpose
    # (polygon vertices once crashed the editor as a ``ui.number``); the
    # numeric check below is type-resolved, so the order is belt-and-braces.
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
    elif is_numeric(annotation):   # int/float, optionally | None
        with parent:
            ui.number(
                label=label, value=cur if cur is not None else 0,
                format="%.4f",
            ).bind_value(obj, fname)
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
    "resolve_annotation",
]

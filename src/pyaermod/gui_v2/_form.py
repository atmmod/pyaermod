"""
Shared dataclass-field → NiceGUI widget helper.

Used by every tab that edits a dataclass (sources, receptors,
meteorology, output, control). Keeps the per-tab page modules
small — each just lists which fields to render and the form helper
emits the right widget by introspecting the dataclass.

Field-type → widget mapping
---------------------------

=======================================  =========================================
Annotation (string form)                 Widget
=======================================  =========================================
``str`` / ``Optional[str]``              ``ui.input``
``float`` / ``int``                      ``ui.number``
``bool``                                 ``ui.checkbox``
``Optional[<numeric>]``                  ``ui.number`` (clearable)
``List[Tuple[float, float]]``            text area (one ``x, y`` pair per line)
``List[str]``                            text area (one entry per line)
``Optional[Union[float, List[float]]]``  ``ui.number`` (clearable) while the
                                         current value is a scalar or ``None``;
                                         text area (one value per line) once it
                                         is already a list
unknown                                  read-only label (escape hatch)
=======================================  =========================================

"Numeric" means the *resolved* annotation is ``int`` or ``float``,
optionally in a union with ``None`` — never a container or tuple that
merely mentions a float (``List[Tuple[float, float]]``,
``Optional[Tuple[DepositionMethod, float]]``). Annotations are resolved
with :func:`typing.get_type_hints`; string annotations that cannot be
resolved are parsed structurally instead.

The "scalar *or* list of numerics" row exists for the building-downwash
dimensions (``building_height``, ``building_width``, ``building_length``,
``building_x_offset``, ``building_y_offset`` on the point/volume/area
sources). AERMOD accepts either one value for every direction or 36 values,
one per 10-degree wind sector, so the field genuinely holds two shapes and
:func:`is_numeric` rightly rejects it. Rather than pick one widget and throw
the other shape away, the form follows the *current* value: the hand-typed
scalar case (and the unset case) gets a number box, and a field already
holding a BPIP-computed 36-value vector gets the list editor. Clearing
either widget stores ``None`` — the writer emits the keyword only for a
non-``None`` value, and an empty list would be rejected as "not 36 values".
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
_LIST_WRAPPERS = ("List", "list")
# Leaf tag for ``List[int]`` / ``list[float]`` in the string-annotation
# parser. Not a legal identifier, so it can never collide with a real name
# and the numeric-only checks below reject it for free.
_NUMERIC_LIST_LEAF = "<numeric-list>"


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


def _is_numeric_list_type(tp: Any) -> bool:
    """True for ``List[int]`` / ``list[float]`` — a list of plain numerics.

    ``List[Tuple[float, float]]`` and bare ``list`` are *not* numeric lists:
    the first holds pairs, the second says nothing about its contents.
    """
    if typing.get_origin(tp) is not list:
        return False
    args = typing.get_args(tp)
    return len(args) == 1 and args[0] in _NUMERIC_TYPES


def _wrapper_name(node: ast.expr) -> Optional[str]:
    """``Optional`` / ``Union`` whether written bare or as ``typing.X``."""
    if isinstance(node, ast.Name) and node.id in _UNION_WRAPPERS:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in _UNION_WRAPPERS:
        return node.attr
    return None


def _is_numeric_list_node(node: ast.expr) -> bool:
    """Structural equivalent of :func:`_is_numeric_list_type`."""
    if not isinstance(node, ast.Subscript):
        return False
    value = node.value
    if isinstance(value, ast.Name):
        name: Optional[str] = value.id
    elif isinstance(value, ast.Attribute):
        name = value.attr          # ``typing.List[float]``
    else:
        name = None
    if name not in _LIST_WRAPPERS:
        return False
    return isinstance(node.slice, ast.Name) and node.slice.id in ("int", "float")


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
    if _is_numeric_list_node(node):
        # Tagged rather than dropped so the scalar-or-list check below can
        # see it; the numeric-only checks still reject the tag, because it
        # is neither "int" nor "float".
        return [_NUMERIC_LIST_LEAF]
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


def _scalar_or_list_info_type(tp: Any) -> Tuple[bool, bool]:
    """``(matches, allows_none)`` for a resolved ``float | List[float] | None``."""
    origin = typing.get_origin(tp)
    if origin is not Union and origin is not types.UnionType:
        return False, False     # a bare ``float`` or ``List[float]`` is not this shape
    args = typing.get_args(tp)
    non_none = [a for a in args if a is not type(None)]
    if not all(a in _NUMERIC_TYPES or _is_numeric_list_type(a) for a in non_none):
        return False, False
    if not any(a in _NUMERIC_TYPES for a in non_none):
        return False, False
    if not any(_is_numeric_list_type(a) for a in non_none):
        return False, False
    return True, len(non_none) < len(args)


def _scalar_or_list_info_str(annotation: str) -> Tuple[bool, bool]:
    """Structural equivalent of :func:`_scalar_or_list_info_type`."""
    try:
        node = ast.parse(annotation.strip(), mode="eval").body
    except SyntaxError:
        return False, False
    names = _leaf_names(node)
    non_none = [n for n in names if n != "None"]
    if not all(n in ("int", "float", _NUMERIC_LIST_LEAF) for n in non_none):
        return False, False
    if not any(n in ("int", "float") for n in non_none):
        return False, False
    if _NUMERIC_LIST_LEAF not in non_none:
        return False, False
    return True, "None" in names


def is_numeric_or_numeric_list(annotation: Any) -> bool:
    """True iff ``annotation`` admits *both* a numeric scalar and a numeric list.

    That is the building-downwash shape,
    ``Optional[Union[float, List[float]]]``: AERMOD takes one value for all
    directions or 36, one per wind sector. Requiring *both* members keeps
    this disjoint from :func:`is_numeric` (a plain ``float`` stays a plain
    number box) and from the ``List[...]`` branch of :func:`emit_field` (a
    plain ``List[float]`` stays a list editor).

    Accepts a typing object or the string form, like :func:`is_numeric`.
    """
    if isinstance(annotation, str):
        return _scalar_or_list_info_str(annotation)[0]
    return _scalar_or_list_info_type(annotation)[0]


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
    elif is_numeric_or_numeric_list(annotation):
        # Building downwash (``Optional[Union[float, List[float]]]``): one
        # value for every direction, or 36 — one per 10-degree wind sector.
        # ``is_numeric`` says False here (correctly: the union holds a list),
        # which used to drop the field into the read-only-label escape hatch
        # and made building dimensions untypeable. The widget follows the
        # *current* value so neither shape is destroyed by rendering.
        with parent:
            if isinstance(cur, (list, tuple)):
                ta = ui.textarea(
                    label=label,
                    placeholder="one value per 10-degree sector",
                    value="\n".join(f"{v:g}" for v in cur),
                ).classes("w-full")

                def _save_nums(_=None):
                    vals = []
                    for line in ta.value.splitlines():
                        s = line.strip()
                        if not s:
                            continue
                        with contextlib.suppress(ValueError):
                            vals.append(float(s))
                    # Emptied box means "no building for this dimension".
                    # ``[]`` would not do: _building_downwash_lines() emits
                    # the keyword for anything non-None and then rejects a
                    # list whose length is not 36.
                    setattr(obj, fname, vals or None)

                ta.on("update:model-value", _save_nums)
            else:
                # ``value=cur`` rather than 0, plus ``clearable``, so an unset
                # dimension stays None instead of being written out as 0.00.
                ui.number(
                    label=label, value=cur, format="%.4f",
                ).props("clearable").bind_value(obj, fname)
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
    "is_numeric_or_numeric_list",
    "is_optional_numeric",
    "resolve_annotation",
]
